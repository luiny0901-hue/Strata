import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from io import StringIO

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

    def test_mismatched_model_and_invalid_limits_fail_before_publish(self):
        for settings, context in [({**self.settings, 'model': 'other/model'}, 262144),
                ({**self.settings, 'env': {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '262144'}}, 262144),
                (self.settings, True)]:
            with self.assertRaises(ValueError):
                clients.model_projection(self.provider, settings, context)

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
