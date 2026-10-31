import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from tools import strata_client_settings as clients


class ClientSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.provider = {'adapter': 'anthropic', 'baseUrl': 'http://127.0.0.1:8080/v1',
            'defaultModel': 'test', 'apiKey': 'private-fixture',
            'headers': {'Keep-Me': 'value', 'X-Strata-Effort-Wire': 'old'},
            'modelMaxOutputTokens': {'other-model': 9000}}
        self.settings = {'model': 'strata/test', 'effortLevel': 'medium',
            'autoCompactWindow': 262144, 'env': {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '32000',
            'CLAUDE_CODE_MAX_CONTEXT_TOKENS': '262144'}}
        self.write('.opencodex/config.json', {'providers': {'strata': self.provider}})
        self.write('.claude/settings.json', self.settings)
        self.write('.claude.json', {'mcpServers': {'agent-tools': {'type': 'stdio',
            'command': 'python', 'args': ['dispatcher path.py'], 'env': {'KEY': 'fixture'}}}})

    def write(self, name, value):
        p = self.home/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding='utf-8')

    def test_model_projection_preserves_other_models_and_inputs(self):
        before = json.dumps(self.provider, sort_keys=True)
        out = clients.model_projection(self.provider, self.settings, 262144)
        self.assertEqual(out['modelMaxOutputTokens'], {'other-model': 9000, 'test': 32000})
        self.assertEqual(out['modelContextWindows'], {'test': 262144})
        self.assertEqual(out['modelReasoningEfforts'], {'test': ['low', 'medium', 'high']})
        self.assertEqual(out['headers'], {'Keep-Me': 'value', clients.WIRE_HEADER: clients.WIRE_VERSION})
        self.assertEqual(out['apiKey'], 'private-fixture')
        self.assertEqual(json.dumps(self.provider, sort_keys=True), before)
        self.assertEqual(clients.model_projection(out, self.settings, 262144), out)

    def test_context_switch_round_trip_preserves_other_models_and_compaction_buffer(self):
        def editor(home, base, route, **kwargs):
            data = json.loads((home/'.opencodex/config.json').read_text())
            data['providers']['strata'] = kwargs['body']['provider']
            self.write('.opencodex/config.json', data)
            return {'success': True}, None
        for context, compact in [(1048576, 1000000), (262144, 262144)]:
            with self.subTest(context=context), \
                    patch.object(clients.shared, 'gateway', return_value=('http://127.0.0.1:10100', 'strata/test')), \
                    patch.object(clients.shared, 'health', return_value=context) as health, \
                    patch.object(clients.shared, 'management_json', side_effect=editor):
                result = clients.sync_context(self.home)
                settings = json.loads((self.home/'.claude/settings.json').read_text())
                provider = json.loads((self.home/'.opencodex/config.json').read_text())['providers']['strata']
                self.assertEqual(settings['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], str(context))
                self.assertEqual(settings['env']['CLAUDE_CODE_AUTO_COMPACT_WINDOW'], str(compact))
                self.assertTrue(settings['autoCompactEnabled'])
                self.assertEqual(provider['modelContextWindows']['test'], context)
                self.assertEqual(provider['modelMaxOutputTokens']['other-model'], 9000)
                self.assertEqual(result['claude_compaction_window'], compact)
                self.assertEqual(health.call_count, 1)

    def test_runtime_switch_reads_actual_model_port_output_and_small_context(self):
        self.settings['env'].update(ANTHROPIC_MODEL='strata/test',
                                   ANTHROPIC_DEFAULT_SONNET_MODEL='another/model')
        self.write('.claude/settings.json', self.settings)
        self.write('.claude/'+clients.shared.STATE, {'model': 'strata/test', 'keep': True})
        self.provider['models'] = ['test', 'other-model']
        self.write('.opencodex/config.json', {'providers': {'strata': self.provider, 'keep': {'adapter': 'keep'}}})
        runtime = {'model': 'new/model', 'context': 65536, 'max_output_tokens': 6000,
                   'base_url': 'http://127.0.0.1:18187/v1', 'images': False, 'api_key': 'new-private-fixture'}
        def editor(home, base, route, **kwargs):
            data = clients.shared.read_json(home/'.opencodex/config.json')
            data['providers']['strata'] = kwargs['body']['provider']
            self.write('.opencodex/config.json', data)
            return {'success': True}, None
        with patch.object(clients, 'runtime_metadata', return_value=runtime) as snapshot, \
                patch.object(clients.shared, 'management_json', side_effect=editor) as send:
            result = clients.sync_runtime(self.home)
            self.assertFalse(clients.sync_runtime(self.home)['changed'])
        self.assertEqual(snapshot.call_count, 2)  # once per explicit operation
        self.assertEqual(send.call_count, 1)      # no repeated provider write
        self.assertEqual(result['model'], 'strata/new/model')
        self.assertEqual(result['max_output_tokens'], 6000)
        self.assertNotIn('new-private-fixture', json.dumps(result))
        saved = clients.shared.read_json(self.home/'.claude/settings.json')
        self.assertEqual(saved['model'], 'strata/new/model')
        self.assertEqual(saved['env']['ANTHROPIC_MODEL'], 'strata/new/model')
        self.assertEqual(saved['env']['ANTHROPIC_DEFAULT_SONNET_MODEL'], 'another/model')
        self.assertEqual(saved['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '65536')
        self.assertNotIn('CLAUDE_CODE_AUTO_COMPACT_WINDOW', saved['env'])
        self.assertEqual(saved['autoCompactWindow'], 'auto')
        state = clients.shared.read_json(self.home/'.claude'/clients.shared.STATE)
        self.assertEqual(state['model'], 'strata/new/model')
        self.assertTrue(state['keep'])
        data = clients.shared.read_json(self.home/'.opencodex/config.json')
        self.assertEqual(data['providers']['keep'], {'adapter': 'keep'})
        provider = data['providers']['strata']
        self.assertEqual(provider['models'], ['new/model', 'other-model'])
        self.assertEqual(provider['modelCapabilities']['new/model']['inputModalities'], ['text'])
        self.assertEqual(provider['baseUrl'], runtime['base_url'])
        self.assertEqual(provider['apiKey'], runtime['api_key'])

    def test_runtime_metadata_uses_bounded_authenticated_reads_and_refuses_redirect_or_change(self):
        fixture = {'model': 'new-model', 'context': 524288, 'redirect': False, 'mismatch': False}
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                calls.append((self.path, self.headers.get('Authorization')))
                if fixture['redirect'] and self.path == '/health':
                    self.send_response(302)
                    self.send_header('Location', '/not-followed')
                    self.end_headers()
                    return
                data = {'/healthz': {'status': 'ok', 'service': 'opencodex'},
                    '/health': {'status': 'ok', 'loaded': True, 'service': 'strata', 'images': True,
                                'model': fixture['model'], 'max_context': fixture['context']},
                    '/props': {'model_alias': fixture['model'], 'default_generation_settings': {
                        'n_ctx': 4096 if fixture['mismatch'] else fixture['context'], 'params': {'n_predict': 12000}}}}[self.path]
                raw = json.dumps(data).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        key = self.home/'server-key'; key.write_text('fixture-new-key')
        kwargs = dict(server_url=base, api_key_file=key, expected_model='new-model')
        with patch.object(clients.shared, 'gateway', return_value=(base, 'strata/test')):
            result = clients.runtime_metadata(self.home, **kwargs)
            self.assertEqual(result['context'], 524288)
            self.assertEqual(result['max_output_tokens'], 12000)
            self.assertEqual(calls, [('/healthz', 'Bearer opencodex-proxy'),
                                    ('/health', 'Bearer fixture-new-key'), ('/props', 'Bearer fixture-new-key')])
            fixture['mismatch'] = True
            with self.assertRaisesRegex(ValueError, '조회 중 서버'):
                clients.runtime_metadata(self.home, **kwargs)
            fixture['mismatch'] = False; fixture['redirect'] = True
            with self.assertRaises(clients.shared.HTTPError):
                clients.runtime_metadata(self.home, **kwargs)
            self.assertFalse(any(path == '/not-followed' for path, _ in calls))
            kwargs['server_url'] = 'https://example.com'
            before = len(calls)
            with self.assertRaisesRegex(ValueError, '로컬 주소'):
                clients.runtime_metadata(self.home, **kwargs)
            self.assertEqual(len(calls), before)

    def test_runtime_provider_can_refresh_while_another_claude_model_stays_selected(self):
        self.settings.update(model='other/model', effortLevel='xhigh')
        self.write('.claude/settings.json', self.settings)
        before = (self.home/'.claude/settings.json').read_bytes()
        runtime = {'model': 'next-model', 'context': 131072, 'max_output_tokens': 24000,
                   'base_url': self.provider['baseUrl'], 'images': True}
        def editor(home, base, route, **kwargs):
            self.write('.opencodex/config.json', {'providers': {'strata': kwargs['body']['provider']}})
            return {'success': True}, None
        with patch.object(clients.shared, 'management_json', side_effect=editor):
            result = clients.sync_context(self.home, runtime=runtime)
        self.assertEqual((self.home/'.claude/settings.json').read_bytes(), before)
        self.assertEqual(result['claude_selection'], 'another_model_preserved')
        self.assertEqual(result['model'], 'strata/next-model')
        self.assertEqual(result['default_effort'], 'medium')

    def test_context_switch_preflights_global_override_without_writes(self):
        path = self.home/'.codex/config.toml'
        path.parent.mkdir()
        original = (self.home/'.claude/settings.json').read_bytes()
        catalog_line = 'model_catalog_json='+json.dumps(str(self.home/'catalog.json'))+'\n'
        for override in ['model_context_window=196000', 'model_auto_compact_token_limit=170000']:
            with self.subTest(override=override):
                path.write_text(catalog_line+override+'\n', encoding='utf-8')
                with patch.object(clients.shared, 'health', return_value=1048576), \
                        patch.object(clients.shared, 'management_json') as send:
                    with self.assertRaisesRegex(ValueError, '전역 컨텍스트/압축'):
                        clients.sync_context(self.home)
                send.assert_not_called()
                self.assertEqual((self.home/'.claude/settings.json').read_bytes(), original)
                self.assertEqual(path.read_text(), catalog_line+override+'\n')

    def test_uncertain_context_write_preserves_local_files_and_is_not_replayed(self):
        self.write('.claude/'+clients.shared.STATE, {'context': 262144, 'keep': True})
        before = {p: p.read_bytes() for p in [self.home/'.claude/settings.json',
                                             self.home/'.claude'/clients.shared.STATE]}
        def uncertain_editor(home, base, route, **kwargs):
            # The provider accepted the write, but its response was lost.
            self.write('.opencodex/config.json', {'providers': {'strata': kwargs['body']['provider']}})
            self.assertEqual(kwargs['timeout'], clients.CONTEXT_SYNC_CALL_TIMEOUT_SECONDS)
            return None, 'management_api_unavailable'
        with patch.object(clients.shared, 'health', return_value=1048576), \
                patch.object(clients.shared, 'management_json', side_effect=uncertain_editor) as send:
            with self.assertRaisesRegex(ValueError, 'phase=provider'):
                clients.sync_context(self.home)
        self.assertEqual(send.call_count, 1)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        provider = clients.shared.read_json(self.home/'.opencodex/config.json')['providers']['strata']
        self.assertEqual(provider['modelContextWindows']['test'], 1048576)

    def test_desktop_failure_or_catalog_mismatch_does_not_advance_claude(self):
        original = (self.home/'.claude/settings.json').read_bytes()
        def editor(home, base, route, **kwargs):
            self.write('.opencodex/config.json', {'providers': {'strata': kwargs['body']['provider']}})
            return {'success': True}, None
        with patch.object(clients.shared, 'health', return_value=1048576), \
                patch.object(clients.shared, 'management_json', side_effect=editor), \
                patch.object(clients, 'sync_desktop_context', side_effect=ValueError('fixture desktop refused')):
            with self.assertRaisesRegex(ValueError, 'phase=desktop'):
                clients.sync_context(self.home)
        self.assertEqual((self.home/'.claude/settings.json').read_bytes(), original)
        config = self.home/'.codex/config.toml'
        config.parent.mkdir()
        catalog = self.home/'catalog.json'
        config.write_text('model_catalog_json='+json.dumps(str(catalog))+'\n', encoding='utf-8')
        self.write('catalog.json', {'models': [{'slug': 'strata/test', 'context_window': 1048576,
                                               'auto_compact_token_limit': 1048576}]})
        with patch.object(clients.shared, 'health', return_value=1048576), \
                patch.object(clients, 'sync_desktop_context') as desktop:
            with self.assertRaisesRegex(ValueError, 'phase=codex_catalog'):
                clients.sync_context(self.home)
        desktop.assert_not_called()
        self.assertEqual((self.home/'.claude/settings.json').read_bytes(), original)

    def test_mismatched_model_and_invalid_limits_fail_before_publish(self):
        for settings, context in [({**self.settings, 'model': 'other/model'}, 262144),
                ({**self.settings, 'env': {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '262144'}}, 262144),
                (self.settings, True)]:
            with self.assertRaises(ValueError):
                clients.model_projection(self.provider, settings, context)

    def test_desktop_context_refresh_uses_existing_profile_owner_once_per_switch(self):
        library = self.home/'library'
        library.mkdir()
        selected = '57dfacd4-1c7c-4c8f-b9e0-ab6d2f229ab6'
        path = library/(selected+'.json')
        (library/'_meta.json').write_text(json.dumps({'appliedId': selected}))
        profile = {'inferenceProvider': 'gateway', 'inferenceGatewayBaseUrl': 'http://127.0.0.1:10100',
                   'inferenceModels': [{'name': 'wire-test'}, {'name': 'other', 'supports1m': True}]}
        path.write_text(json.dumps(profile))
        desired = True
        def editor(home, base, route, **kwargs):
            if route == '/api/claude-desktop':
                return {'rendered': [{'route': 'strata/test', 'name': 'wire-test', 'supports1m': desired}]}, None
            self.assertEqual(route, '/api/claude-desktop/apply')
            self.assertEqual(kwargs['body'], {'mode': 'static'})
            profile['inferenceModels'][0].update(supports1m=desired, prefer1m=desired)
            path.write_text(json.dumps(profile))
            return {'applied': True}, None
        with patch.object(clients.shared, 'desktop_config_library', return_value=library), \
                patch.object(clients.shared, 'management_json', side_effect=editor) as send:
            self.assertTrue(clients.sync_desktop_context(self.home, 'http://127.0.0.1:10100', 'strata/test')['changed'])
            self.assertFalse(clients.sync_desktop_context(self.home, 'http://127.0.0.1:10100', 'strata/test')['changed'])
            desired = False
            self.assertTrue(clients.sync_desktop_context(self.home, 'http://127.0.0.1:10100', 'strata/test')['changed'])
        self.assertEqual(sum(c.args[2].endswith('/apply') for c in send.call_args_list), 2)
        self.assertEqual(json.loads(path.read_text())['inferenceModels'][1], {'name': 'other', 'supports1m': True})

    def test_new_non_1m_desktop_model_is_applied_even_without_changed_1m_flags(self):
        library = self.home/'library'; library.mkdir()
        selected = '57dfacd4-1c7c-4c8f-b9e0-ab6d2f229ab6'
        self.write('library/_meta.json', {'appliedId': selected})
        profile = {'inferenceProvider': 'gateway', 'inferenceGatewayBaseUrl': 'http://127.0.0.1:10100',
                   'inferenceModels': [{'name': 'old-wire-model'}]}
        self.write('library/'+selected+'.json', profile)
        def editor(home, base, route, **kwargs):
            if route == '/api/claude-desktop':
                return {'rendered': [{'route': 'strata/new', 'name': 'new-wire-model', 'supports1m': False}]}, None
            profile['inferenceModels'].append({'name': 'new-wire-model'})
            self.write('library/'+selected+'.json', profile)
            return {'applied': True}, None
        with patch.object(clients.shared, 'desktop_config_library', return_value=library), \
                patch.object(clients.shared, 'management_json', side_effect=editor) as send:
            result = clients.sync_desktop_context(self.home, 'http://127.0.0.1:10100', 'strata/new')
        self.assertTrue(result['changed'])
        self.assertEqual(send.call_count, 2)

    def test_provider_editor_changes_only_the_strata_provider(self):
        path = self.home/'.opencodex/config.json'
        self.write('.opencodex/config.json', {'providers': {'strata': self.provider,
            'unrelated': {'adapter': 'keep'}}, 'model': 'unrelated/model'})
        def editor(home, base, route, **kwargs):
            self.assertEqual(route, '/api/providers')
            self.assertEqual(set(kwargs['body']), {'name', 'provider'})
            data = json.loads(path.read_text(encoding='utf-8'))
            data['providers']['strata'] = kwargs['body']['provider']
            path.write_text(json.dumps(data), encoding='utf-8')
            return {'success': True}, None
        with patch.object(clients.shared, 'health', return_value=262144), \
                patch.object(clients.shared, 'management_json', side_effect=editor) as send:
            result = clients.sync_model(self.home)
            self.assertTrue(result['changed'])
            self.assertEqual(result['max_output_tokens'], 32000)
            self.assertFalse(clients.sync_model(self.home)['changed'])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(json.loads(path.read_text())['providers']['unrelated'], {'adapter': 'keep'})

    def test_uncertain_provider_write_is_not_retried(self):
        with patch.object(clients.shared, 'health', return_value=262144), \
                patch.object(clients.shared, 'management_json', return_value=(None, 'management_api_unavailable')) as send:
            with self.assertRaisesRegex(ValueError, '자동 재전송하지'):
                clients.sync_model(self.home)
        self.assertEqual(send.call_count, 1)

    def test_codex_merge_retains_selection_permissions_and_user_mcp(self):
        path = self.home/'.codex/config.toml'
        path.parent.mkdir()
        original = 'model = "other/model"\nmodel_reasoning_effort = "xhigh"\napproval_policy = "on-request"\n[mcp_servers.custom]\ncommand = "keep"\n'
        path.write_text(original, encoding='utf-8')
        (path.parent/'AGENTS.md').write_text('사용자 지침\n', encoding='utf-8')
        result = clients.sync_codex(self.home)
        self.assertGreater(result['changed_files'], 0)
        text = path.read_text(encoding='utf-8')
        self.assertTrue(text.startswith(original))
        data = tomllib.loads(text)
        self.assertEqual(data['mcp_servers']['agent-tools']['env']['KEY'], 'fixture')
        self.assertEqual(data['mcp_servers']['agent-tools']['tool_timeout_sec'], 660)
        self.assertNotIn('strata-maintenance', data['mcp_servers'])
        self.assertNotIn('model_context_window', data)
        self.assertEqual(clients.sync_codex(self.home)['changed_files'], 0)
        self.assertTrue((path.parent/'AGENTS.md').read_text(encoding='utf-8').startswith('사용자 지침\n'))

    def test_user_edits_and_conflicting_mcp_are_preserved(self):
        clients.sync_codex(self.home)
        path = self.home/'.codex/config.toml'
        text = path.read_text(encoding='utf-8').replace('dispatcher path.py', 'user replacement.py')
        path.write_text(text, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '사용자가 수정'):
            clients.sync_codex(self.home)
        self.assertEqual(path.read_text(encoding='utf-8'), text)
        path.write_text('[mcp_servers.agent-tools]\ncommand="user"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '덮어쓰지'):
            clients.sync_codex(self.home)

    def test_maintenance_stays_project_local(self):
        project = self.home/'project'
        self.write('.claude/'+clients.shared.STATE, {'maintenance_mcp': {'project': str(project)}})
        native = clients.shared.read_json(self.home/'.claude.json')
        native['projects'] = {str(project): {'mcpServers': {'strata-maintenance': {
            'type': 'stdio', 'command': 'python', 'args': ['maintenance.py']}}}}
        self.write('.claude.json', native)
        clients.sync_codex(self.home)
        config = tomllib.loads((project/'.codex/config.toml').read_text(encoding='utf-8'))
        self.assertEqual(config['mcp_servers']['strata-maintenance']['args'], ['maintenance.py'])
        self.assertNotIn('strata-maintenance', tomllib.loads((self.home/'.codex/config.toml').read_text())['mcp_servers'])

    def test_disabled_maintenance_does_not_become_enabled_in_codex(self):
        project = self.home/'project'
        self.write('.claude/'+clients.shared.STATE, {'maintenance_mcp': {'project': str(project)}})
        native = clients.shared.read_json(self.home/'.claude.json')
        native['projects'] = {str(project): {'disabledMcpServers': ['strata-maintenance'],
            'mcpServers': {'strata-maintenance': {'type': 'stdio', 'command': 'python'}}}}
        self.write('.claude.json', native)
        clients.sync_codex(self.home)
        config = tomllib.loads((project/'.codex/config.toml').read_text(encoding='utf-8'))
        self.assertFalse(config['mcp_servers']['strata-maintenance']['enabled'])

    def test_audit_detects_context_override_and_keeps_synthetic_efforts_distinct(self):
        self.provider = clients.model_projection(self.provider, self.settings, 262144)
        self.write('.opencodex/config.json', {'providers': {'strata': self.provider}})
        catalog = self.home/'catalog.json'
        self.write('catalog.json', {'models': [{'slug': 'strata/test', 'context_window': 262144,
            'auto_compact_token_limit': 235929, 'supported_reasoning_levels': [
                {'effort': v} for v in ['low', 'medium', 'high', 'max', 'ultra']]}]})
        path = self.home/'.codex/config.toml'
        path.parent.mkdir()
        path.write_text('model_catalog_json = '+json.dumps(str(catalog))+'\nmodel_context_window=196000\n', encoding='utf-8')
        result = clients.audit(self.home)
        self.assertFalse(result['checks']['codex_context'])
        self.assertEqual(result['codex_gateway_only_efforts'], ['max', 'ultra'])
        self.assertEqual(result['runtime_status'], 'not_verified')

    def test_external_client_projection_does_not_edit_or_probe_model_gateway(self):
        with patch.object(Path, 'home', return_value=self.home), \
                patch.object(clients, 'sync_model') as gateway, \
                patch.object(clients, 'sync_codex', return_value={'changed_files': 0}) as local, \
                patch('sys.stdout', new_callable=StringIO):
            self.assertEqual(clients.main(['--codex-only']), 0)
        gateway.assert_not_called()
        local.assert_called_once_with(self.home)


if __name__ == '__main__':
    unittest.main()
