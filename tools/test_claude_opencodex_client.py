import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.error import HTTPError

from tools import claude_opencodex_client as shared


class SharedClaudeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home/'claude-mcp.json'
        for name, data in [('.opencodex/config.json', {'port': 10100, 'providers': {'strata': {'defaultModel': 'qwen-test', 'adapter': 'anthropic'}},
                'protocols': {'rollout': {'managedMessagesNative': True}}}),
                ('.claude/settings.json', {'theme': 'light', 'env': {'USER_OPTION': 'keep'},
                    'hooks': {
                        'SessionStart': [{'hooks': [{'type': 'command', 'command': 'user-hook'}]}],
                        'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'user-prompt-hook'}]}],
                    }}),
                ('.claude.json', {'userID': 'keep', 'projects': {'sample': {'history': True}},
                    'mcpServers': {'custom': {'command': 'custom-tool'}}}),
                ('claude-mcp.json', {'mcpServers': {
                    'rea': {'type':'stdio', 'command':'python', 'args':['rea','mcp']},
                    'cua-driver': {'type':'stdio', 'command':'node', 'args':['cua.js']}}})]:
            path = self.home/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding='utf-8')

    def diagnose_shared(self):
        preview = {'status': 'preview', 'eligible': True, 'mode': 'native',
                   'feature_effects': [{'feature': 'request.tools', 'disposition': 'passthrough'}]}
        with patch.object(shared, 'health', return_value=262144), \
                patch.object(shared, 'messages_route_preview', return_value=preview):
            return shared.diagnose(self.home)

    def test_desktop_gateway_readiness_is_distinct_and_uses_the_configured_profile_path(self):
        profile_path=self.home/'desktop'/'configLibrary'
        with patch.dict(os.environ, {'CLAUDE_3P_CONFIG_LIBRARY':str(profile_path)}):
            self.setup_shared()
            missing=self.diagnose_shared()
            self.assertTrue(missing['ready'])
            self.assertFalse(missing['desktop_ready'])
            self.assertEqual(missing['desktop']['status'],'not_configured')

            profile_path.mkdir(parents=True)
            profile_id='4e5c9c35-8d38-4f06-88fa-9f28d0f70ad1'
            (profile_path/'_meta.json').write_text(json.dumps({'appliedId':profile_id}),encoding='utf-8')
            (profile_path/(profile_id+'.json')).write_text(json.dumps({
                'inferenceProvider':'gateway','inferenceGatewayBaseUrl':'http://127.0.0.1:10100',
                'inferenceModels':[{'name':'claude-fable-test','isFamilyDefault':True}]}),encoding='utf-8')
            open_config=shared.read_json(self.home/'.opencodex/config.json')
            open_config['claudeCode']={'desktopProfile':{'defaults':{'opus':'strata/qwen-test'}}}
            (self.home/'.opencodex/config.json').write_text(json.dumps(open_config),encoding='utf-8')
            ready=self.diagnose_shared()
            self.assertTrue(ready['desktop_ready'])
            self.assertEqual(ready['desktop']['status'],'ready')
            # CLI ENABLE_TOOL_SEARCH cannot prove Desktop's separate gateway setting.
            self.assertIsNone(ready['desktop']['tool_search']['configured'])
            self.assertFalse(ready['desktop']['tool_search']['enabled_in_profile'])
            profile_file=profile_path/(profile_id+'.json')
            profile=json.loads(profile_file.read_text(encoding='utf-8'))
            for enabled in (False, True):
                profile['toolSearchEnabled']=enabled
                profile_file.write_text(json.dumps(profile),encoding='utf-8')
                observed=self.diagnose_shared()
                self.assertTrue(observed['desktop_ready'])
                self.assertEqual(observed['desktop']['tool_search']['enabled_in_profile'],enabled)
                self.assertEqual(observed['desktop']['tool_search']['runtime_status'],'not_verified')

    def test_invalid_desktop_profile_is_reported_without_crashing_common_diagnosis(self):
        profile_path=self.home/'desktop'/'configLibrary'
        profile_path.mkdir(parents=True)
        (profile_path/'_meta.json').write_text('{invalid',encoding='utf-8')
        with patch.dict(os.environ, {'CLAUDE_3P_CONFIG_LIBRARY':str(profile_path)}):
            self.setup_shared()
            report=self.diagnose_shared()
        self.assertTrue(report['ready'])
        self.assertFalse(report['desktop_ready'])
        self.assertEqual(report['desktop']['status'],'invalid_profile')

    def test_setup_cli_accepts_a_claude_format_mcp_import(self):
        source = self.home/'claude-mcp.json'
        source.write_text(json.dumps({'mcpServers': {
            'cua-driver': {'type':'stdio','command':'node','args':['cua.js']}}}),encoding='utf-8')
        expected={'base_url':'http://127.0.0.1:10100','model':'strata/qwen-test','context':262144,
                  'profile':str(self.home/'.claude'),'mcp':['agent-tools'],'changed':1,'backup':'backup'}
        with patch.object(Path,'home',return_value=self.home), \
                patch.object(shared,'setup',return_value=expected) as setup, \
                patch('sys.stdout',new_callable=StringIO):
            self.assertEqual(shared.main(['setup','--mcp-config',str(source)]),0)
        setup.assert_called_once_with(self.home,mcp_config=source.resolve(),lazy_cua_rea=True)

    def test_setup_cli_forwards_the_explicit_lazy_cua_rea_option(self):
        expected={'base_url':'http://127.0.0.1:10100','model':'strata/qwen-test','context':262144,
                  'profile':str(self.home/'.claude'),'mcp':['agent-tools'],'changed':1,'backup':'backup'}
        with patch.object(Path,'home',return_value=self.home), \
                patch.object(shared,'setup',return_value=expected) as setup, \
                patch('sys.stdout',new_callable=StringIO):
            self.assertEqual(shared.main(['setup','--mcp-config',str(self.source),'--lazy-cua-rea']),0)
        setup.assert_called_once_with(self.home,mcp_config=self.source.resolve(),lazy_cua_rea=True)

    def test_setup_cli_can_explicitly_select_direct_cua_rea(self):
        expected={'base_url':'http://127.0.0.1:10100','model':'strata/qwen-test','context':262144,
                  'profile':str(self.home/'.claude'),'mcp':['cua-driver','rea'],'changed':1,'backup':'backup'}
        with patch.object(Path,'home',return_value=self.home), \
                patch.object(shared,'setup',return_value=expected) as setup, \
                patch('sys.stdout',new_callable=StringIO):
            self.assertEqual(shared.main(['setup','--mcp-config',str(self.source),'--direct-cua-rea']),0)
        setup.assert_called_once_with(self.home,mcp_config=self.source.resolve(),lazy_cua_rea=False)

    def setup_shared(self):
        return shared.setup(self.home, mcp_config=self.source, verify=False)

    def test_default_setup_preserves_user_fields_and_uses_on_demand_cua_rea(self):
        self.setup_shared()
        settings = shared.read_json(self.home/'.claude/settings.json')
        native = shared.read_json(self.home/'.claude.json')
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        self.assertEqual(settings['theme'], 'light')
        self.assertEqual(settings['env']['USER_OPTION'], 'keep')
        self.assertEqual(settings['env']['ANTHROPIC_BASE_URL'], 'http://127.0.0.1:10100')
        self.assertEqual(settings['env']['ENABLE_TOOL_SEARCH'], 'auto')
        self.assertEqual(settings['model'], 'strata/qwen-test')
        self.assertEqual(settings['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '262144')
        self.assertEqual(settings['env']['CLAUDE_CODE_AUTO_COMPACT_WINDOW'], '262144')
        self.assertEqual(settings['autoCompactWindow'], 262144)
        self.assertNotIn('CLAUDE_CONFIG_DIR', settings['env'])
        self.assertEqual(native['projects'], {'sample': {'history': True}})
        self.assertEqual(set(native['mcpServers']), {'custom', 'agent-tools'})
        self.assertEqual(state['mcp_source_config'], str((self.home/'.claude/strata-mcp.json').resolve()))
        self.assertNotIn('source_config', state)
        self.assertTrue(state['lazy_cua_rea'])
        self.assertIn('mcp__agent-tools__search_tools', settings['permissions']['allow'])
        self.assertNotIn('mcp__agent-tools__call_tool', settings['permissions']['allow'])
        self.assertEqual(len(settings['hooks']['SessionStart']), 2)
        self.assertEqual(settings['hooks']['UserPromptSubmit'], [
            {'hooks': [{'type': 'command', 'command': 'user-prompt-hook'}]}])
        self.assertEqual(self.setup_shared()['changed'], 0)

    def test_existing_profile_runs_from_claude_owned_mcp_config_after_legacy_source_is_removed(self):
        first = shared.setup(self.home, mcp_config=self.source, verify=False)
        mcp_source = self.home/'.claude/strata-mcp.json'
        self.assertTrue(mcp_source.is_file())
        self.source.unlink()
        second = shared.setup(self.home, verify=False)
        self.assertEqual(first['mcp_source_config'], str(mcp_source.resolve()))
        self.assertEqual(second['changed'], 0)
        native = shared.read_json(self.home/'.claude.json')
        args = native['mcpServers']['agent-tools']['args']
        self.assertEqual(args[-2:], ['--mcp-config', str(mcp_source.resolve())])

    def test_context_diagnosis_uses_saved_window_precedence_and_reports_reduced_windows(self):
        self.setup_shared()
        report = self.diagnose_shared()
        self.assertEqual(report['context_window_policy']['auto_compact_window_tokens'], 262144)
        self.assertEqual(report['context_window_policy']['status'], 'full_model_window')
        self.assertEqual(report['context_window_policy']['runtime_status'], 'not_verified')
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['autoCompactWindow'] = 196608
        path.write_text(json.dumps(settings), encoding='utf-8')
        self.assertEqual(self.diagnose_shared()['context_window_policy']['source'], 'environment')
        settings['env']['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] = '196608'
        path.write_text(json.dumps(settings), encoding='utf-8')
        reduced = self.diagnose_shared()
        self.assertEqual(reduced['server_context'], 262144)
        self.assertEqual(reduced['context_window_policy']['auto_compact_window_tokens'], 196608)
        self.assertEqual(reduced['context_window_policy']['status'], 'reduced_window')

    def test_saved_compaction_resolution_caps_the_model_and_ignores_invalid_env(self):
        settings = {'env': {'CLAUDE_CODE_AUTO_COMPACT_WINDOW': 'invalid'},
                    'modelSettings': {'strata/test': {'autoCompactWindow': 131072}},
                    'autoCompactWindow': 196608}
        self.assertEqual(shared.saved_compaction_window(settings, 'strata/test', 262144),
                         (131072, 'model_settings'))
        settings['env']['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] = '1M'
        self.assertEqual(shared.saved_compaction_window(settings, 'strata/test', 262144),
                         (262144, 'environment'))
        self.assertEqual(shared.saved_compaction_window(settings, 'strata/test', 65536),
                         (65536, 'environment'))

    def test_mcp_audit_reports_duplicate_direct_servers_without_removing_user_settings(self):
        self.setup_shared()
        path = self.home/'.claude.json'
        native = shared.read_json(path)
        native['mcpServers']['cua-driver'] = {'command': 'user-cua'}
        path.write_text(json.dumps(native), encoding='utf-8')
        report = self.diagnose_shared()['mcp_delivery']
        self.assertEqual(report['duplicate_direct_servers'], ['cua-driver'])
        self.assertEqual(report['additional_user_servers'], ['cua-driver', 'custom'])
        self.assertEqual(shared.read_json(path), native)

    def test_existing_claude_mcp_source_is_not_replaced_by_later_import(self):
        shared.setup(self.home, mcp_config=self.source, verify=False)
        mcp_source = self.home/'.claude/strata-mcp.json'
        before = mcp_source.read_bytes()
        alternate = self.home/'alternate-claude-mcp.json'
        alternate.write_text(json.dumps({'mcpServers': {'rea': {
            'type':'stdio','command':'other-rea','args':[]}}}),encoding='utf-8')
        shared.setup(self.home, mcp_config=alternate, verify=False)
        self.assertEqual(mcp_source.read_bytes(), before)

    def test_fresh_client_creates_guarded_mcp_without_copying_windows_settings(self):
        driver = self.home/'native-driver'; driver.write_bytes(b'fixture'); driver.chmod(0o755)
        def which(name):
            return str(driver) if name == 'cua-driver' else '/fixture/'+name
        with patch.object(shared.shutil, 'which', side_effect=which), \
             patch.dict(os.environ, {'STRATA_CUA_DRIVER_EXE': ''}):
            source, payload, path = shared.resolve_mcp_source(self.home)
        cua = source['mcpServers']['cua-driver']
        self.assertEqual(cua['env']['CUA_DRIVER_EXE'], str(driver.resolve()))
        self.assertEqual(cua['env']['CUA_DRIVER_PERMISSION_MODE'], 'standard')
        self.assertIn('window-scoped.rego', cua['env']['CUA_DRIVER_POLICY_FILE'])
        self.assertEqual(source['mcpServers']['rea']['args'][-2:], ['rea-agents@6.7.0', 'mcp'])
        self.assertEqual(json.loads(payload), source)
        self.assertFalse(path.exists())  # still a plan until the existing publisher commits

    def test_copied_windows_cua_paths_are_resolved_on_the_current_client(self):
        driver = self.home/'local-driver'; driver.write_bytes(b'fixture'); driver.chmod(0o755)
        original = {'mcpServers': {'cua-driver': {'type': 'stdio', 'command': r'Z:\old\node.exe',
            'args': [r'Z:\old\tools\cua-driver\mcp.mjs'], 'env': {
                'CUA_DRIVER_EXE': r'Z:\old\cua-driver.exe',
                'CUA_DRIVER_POLICY_FILE': r'Z:\old\window-scoped.rego'}}}}
        saved = json.dumps(original)
        with patch.object(shared.shutil, 'which', side_effect=lambda name: str(driver) if name == 'cua-driver' else '/fixture/node'), \
             patch.dict(os.environ, {'STRATA_CUA_DRIVER_EXE': ''}):
            source = shared._localize_cua_launcher(original)['mcpServers']['cua-driver']
        self.assertEqual(source['env']['CUA_DRIVER_EXE'], str(driver.resolve()))
        self.assertEqual(source['command'], str(Path('/fixture/node').resolve()))
        self.assertEqual(Path(source['args'][0]), shared.ROOT/'tools/cua-driver/mcp.mjs')
        self.assertEqual(json.dumps(original), saved)

    def test_invalid_explicit_cua_path_does_not_fall_back(self):
        with patch.dict(os.environ, {'STRATA_CUA_DRIVER_EXE': str(self.home/'missing-driver')}), \
             patch.object(shared.shutil, 'which') as locate:
            with self.assertRaisesRegex(ValueError, 'STRATA_CUA_DRIVER_EXE'):
                shared.local_cua_executable()
            locate.assert_not_called()

    def test_desktop_paths_follow_mac_linux_and_explicit_user_data(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=self.home):
            with patch.object(shared.sys, 'platform', 'darwin'):
                self.assertEqual(shared.desktop_config_library(self.home), self.home/'Library/Application Support/Claude-3p/configLibrary')
            with patch.object(shared.sys, 'platform', 'linux'):
                self.assertEqual(shared.desktop_config_library(self.home), self.home/'.config/Claude-3p/configLibrary')
            with patch.dict(os.environ, {'CLAUDE_USER_DATA_DIR': str(self.home/'custom')}):
                self.assertEqual(shared.desktop_config_library(self.home), self.home/'custom/configLibrary')
            with patch.dict(os.environ, {'OPENCODEX_CLAUDE_DESKTOP_CONFIG_DIR': str(self.home/'library')}):
                self.assertEqual(shared.desktop_config_library(self.home), self.home/'library')

    def test_claude_mcp_import_relocalizes_a_copied_rea_launcher(self):
        config = self.home/'copied-strata-mcp.json'
        config.write_text(json.dumps({'mcpServers': {'rea': {'type':'stdio',
            'command':'old-python', 'args':[r'Z:\old-checkout\tools\claude_mcp\rea_launcher.py',
                                            'rea-agents@6.7.0', 'mcp']}}}), encoding='utf-8')
        source, payload, path = shared.resolve_mcp_source(self.home, mcp_config=config)
        expected = str((shared.direct.ROOT/'tools/claude_mcp/rea_launcher.py').resolve())
        self.assertEqual(source['mcpServers']['rea']['args'][0], expected)
        selected_python = shared.resolve_runtime_python({})
        self.assertEqual(source['mcpServers']['rea']['command'], selected_python)
        self.assertEqual(json.loads(payload)['mcpServers']['rea']['command'], selected_python)
        self.assertEqual(json.loads(payload)['mcpServers']['rea']['args'][0], expected)
        self.assertEqual(path, self.home/'.claude/strata-mcp.json')

    def test_claude_projection_uses_the_selected_python_for_the_repository_rea_launcher(self):
        source = {'mcpServers': {'rea': {'type': 'stdio', 'command': 'old-python',
            'args': [str((shared.direct.ROOT/'tools/claude_mcp/rea_launcher.py').resolve()),
                     'rea-agents@6.7.0', 'mcp']}}}
        projected = shared.claude_mcp_projection(source, self.home/'.claude/strata-mcp.json',
            lazy_cua_rea=False, runtime_python='selected-python')
        self.assertEqual(projected['rea']['command'], 'selected-python')

    def test_setup_preserves_existing_runtime_python_across_generated_commands(self):
        selected = self.home/'installed-runtime'/'python.exe'
        selected.parent.mkdir(parents=True)
        selected.write_bytes(b'fixture executable')
        caller = self.home/'other-python.exe'
        caller.write_bytes(b'fixture executable')
        self.enable_maintenance_server()
        hook_path = self.home/'hook.py'
        hook = f'"{selected.resolve().as_posix()}" -X utf8 "{hook_path.as_posix()}" hook'
        (self.home/'.claude/strata-opencodex.json').write_text(json.dumps({
            'version': 1, 'hook_command': hook}), encoding='utf-8')
        settings_path = self.home/'.claude/settings.json'
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
        settings['hooks']['UserPromptSubmit'].append({'hooks': [
            {'type': 'command', 'command': hook, 'timeout': 3}]})
        settings_path.write_text(json.dumps(settings), encoding='utf-8')

        with patch.dict(os.environ, {'STRATA_CLAUDE_PYTHON': ''}), \
                patch.object(shared.sys, 'executable', str(caller)):
            shared.setup(self.home, mcp_config=self.source, verify=False)

        settings = shared.read_json(self.home/'.claude/settings.json')
        native = shared.read_json(self.home/'.claude.json')
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        expected = str(selected.resolve())
        self.assertEqual(state['runtime_python'], expected)
        self.assertEqual(native['mcpServers']['agent-tools']['command'], expected)
        maintenance_project = state['maintenance_mcp']['project']
        self.assertEqual(native['projects'][maintenance_project]['mcpServers']['strata-maintenance']['command'], expected)
        session_commands = [handler['command'] for row in settings['hooks']['SessionStart']
                            for handler in row['hooks']]
        prompt_commands = [handler['command'] for row in settings['hooks']['UserPromptSubmit']
                           for handler in row['hooks']]
        self.assertIn(state['hook_command'], session_commands)
        self.assertEqual(prompt_commands, ['user-prompt-hook'])

    def test_setup_uses_explicit_runtime_python_override_and_rejects_missing_path(self):
        selected = self.home/'selected-python.exe'
        selected.write_bytes(b'fixture executable')
        with patch.dict(os.environ, {'STRATA_CLAUDE_PYTHON': str(selected)}):
            self.assertEqual(shared.resolve_runtime_python({}), str(selected.resolve()))
        with patch.dict(os.environ, {'STRATA_CLAUDE_PYTHON': 'python'}), \
                patch('tools.claude_opencodex_client.shutil.which', return_value=str(selected)):
            self.assertEqual(shared.resolve_runtime_python({}), str(selected.resolve()))
        with patch.dict(os.environ, {'STRATA_CLAUDE_PYTHON': str(self.home/'missing-python.exe')}):
            with self.assertRaisesRegex(ValueError, 'STRATA_CLAUDE_PYTHON'):
                shared.resolve_runtime_python({})

    def test_runtime_python_can_be_recovered_from_legacy_managed_hook(self):
        selected = self.home/'legacy-python.exe'
        selected.write_bytes(b'fixture executable')
        hook_path = self.home/'hook.py'
        hook = f'"{selected.resolve().as_posix()}" -X utf8 "{hook_path.as_posix()}" hook'
        self.assertEqual(shared.resolve_runtime_python({'hook_command': hook}),
                         str(selected.resolve()))
        self.assertEqual(shared.resolve_runtime_python({
            'runtime_python': str(self.home/'missing-python.exe'), 'hook_command': hook}),
            str(selected.resolve()))

    def test_lazy_cua_rea_setup_replaces_only_managed_servers_and_can_be_reversed(self):
        report = shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        native = shared.read_json(self.home/'.claude.json')
        settings = shared.read_json(self.home/'.claude/settings.json')
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        self.assertEqual(set(native['mcpServers']), {'custom', 'agent-tools'})
        self.assertEqual(native['mcpServers']['custom'], {'command': 'custom-tool'})
        self.assertEqual(native['mcpServers']['agent-tools']['type'], 'stdio')
        args = native['mcpServers']['agent-tools']['args']
        self.assertEqual(args[-2:], ['--mcp-config', str((self.home/'.claude/strata-mcp.json').resolve())])
        self.assertTrue(Path(args[0]).is_file())
        self.assertEqual(state['managed_mcp_servers'], ['agent-tools'])
        self.assertEqual(state['managed_permission_rules'], ['mcp__agent-tools__search_tools'])
        self.assertTrue(state['lazy_cua_rea'])
        self.assertIn('mcp__agent-tools__search_tools', settings['permissions']['allow'])
        self.assertNotIn('mcp__agent-tools__call_tool', settings['permissions']['allow'])
        self.assertIn('agent-tools', report['mcp'])
        guide = (self.home/'.claude/CLAUDE.md').read_text(encoding='utf-8')
        self.assertIn('`agent-tools.search_tools`', guide)
        self.assertIn('`agent-tools.call_tool`', guide)
        self.assertNotIn('직접 연결된 `cua-driver` MCP', guide)

        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=False)
        restored = shared.read_json(self.home/'.claude.json')
        self.assertEqual(set(restored['mcpServers']), {'custom', 'rea', 'cua-driver'})
        self.assertEqual(restored['mcpServers']['custom'], {'command': 'custom-tool'})
        restored_guide = (self.home/'.claude/CLAUDE.md').read_text(encoding='utf-8')
        self.assertIn('직접 연결된 `cua-driver` MCP', restored_guide)
        self.assertNotIn('`agent-tools.search_tools`', restored_guide)
        restored_settings = shared.read_json(self.home/'.claude/settings.json')
        self.assertNotIn('mcp__agent-tools__search_tools', restored_settings['permissions']['allow'])

    def test_lazy_permission_is_idempotent_and_preserves_preexisting_allow_rules(self):
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions'] = {'allow': ['mcp__custom__read']}
        path.write_text(json.dumps(settings), encoding='utf-8')

        first = shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        after_first = shared.read_json(path)
        self.assertEqual(after_first['permissions']['allow'], [
            'mcp__custom__read', 'mcp__agent-tools__search_tools'])
        second = shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        self.assertEqual(second['changed'], 0)
        self.assertEqual(shared.read_json(path)['permissions']['allow'], after_first['permissions']['allow'])

        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=False)
        final = shared.read_json(path)
        self.assertEqual(final['permissions']['allow'], ['mcp__custom__read'])

    def enable_maintenance_server(self):
        token_file = self.home/'supervisor.token'
        token_file.write_text('a'*64, encoding='ascii')
        source = shared.read_json(self.source)
        source['mcpServers']['strata-maintenance'] = {
            'type': 'stdio', 'command': 'python',
            'args': [str(shared.ROOT/'tools/claude_maintenance.py'),
                     '--control-url', 'http://127.0.0.1:9876', '--token-file', str(token_file)]}
        self.source.write_text(json.dumps(source), encoding='utf-8')

    def test_setup_manages_only_exact_read_only_maintenance_permissions(self):
        self.enable_maintenance_server()
        report = self.setup_shared()
        settings = shared.read_json(self.home/'.claude/settings.json')
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        expected = {f'mcp__strata-maintenance__{name}'
                    for name in shared.READ_ONLY_MAINTENANCE_TOOLS}
        self.assertEqual(set(state['managed_permission_rules']),
            expected | {'mcp__agent-tools__search_tools'})
        self.assertTrue(expected.issubset(set(settings['permissions']['allow'])))
        self.assertNotIn('mcp__agent-tools__call_tool', settings['permissions']['allow'])
        for action in ('restart_strata', 'cancel_restart'):
            self.assertNotIn(f'mcp__strata-maintenance__{action}', settings['permissions']['allow'])
        self.assertNotIn('strata-maintenance', report['mcp'])
        self.assertEqual(report['maintenance_project'], shared.maintenance_project_path())
        self.assertEqual(self.setup_shared()['changed'], 0)

        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=False)
        direct = shared.read_json(self.home/'.claude/settings.json')
        self.assertIn('mcp__strata-maintenance__environment_status', direct['permissions']['allow'])
        self.assertNotIn('mcp__agent-tools__search_tools', direct['permissions']['allow'])

        source_path = self.home/'.claude/strata-mcp.json'
        source = shared.read_json(source_path)
        source['mcpServers'].pop('strata-maintenance')
        source_path.write_text(json.dumps(source), encoding='utf-8')
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=False)
        removed = shared.read_json(self.home/'.claude/settings.json')
        self.assertFalse(any(rule.startswith('mcp__strata-maintenance__')
                             for rule in removed['permissions']['allow']))
        native = shared.read_json(self.home/'.claude.json')
        self.assertNotIn('strata-maintenance',
                         native['projects'][shared.maintenance_project_path()]['mcpServers'])

    def test_maintenance_permissions_preserve_user_server_glob_and_require_server_anchor(self):
        self.enable_maintenance_server()
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions'] = {'allow': ['mcp__strata-maintenance__*']}
        path.write_text(json.dumps(settings), encoding='utf-8')

        shared.setup(self.home, mcp_config=self.source, verify=False)
        current = shared.read_json(path)
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        self.assertEqual(current['permissions']['allow'], [
            'mcp__strata-maintenance__*', 'mcp__agent-tools__search_tools'])
        self.assertEqual(state['managed_permission_rules'], ['mcp__agent-tools__search_tools'])
        self.assertTrue(shared.mcp_permission_matches(
            current['permissions']['allow'], 'mcp__strata-maintenance__restart_strata'))
        self.assertFalse(shared.mcp_permission_matches(['*'], 'mcp__strata-maintenance__environment_status'))
        self.assertFalse(shared.mcp_permission_matches(
            ['mcp__other-server__*'], 'mcp__strata-maintenance__environment_status'))

    def test_no_maintenance_permissions_are_added_without_projected_maintenance_server(self):
        self.setup_shared()
        settings = shared.read_json(self.home/'.claude/settings.json')
        self.assertFalse(any(rule.startswith('mcp__strata-maintenance__')
                             for rule in settings['permissions']['allow']))

    def test_lazy_setup_does_not_claim_or_remove_a_preexisting_search_permission(self):
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions'] = {'allow': ['mcp__agent-tools__search_tools']}
        path.write_text(json.dumps(settings), encoding='utf-8')

        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        self.assertEqual(state['managed_permission_rules'], [])
        shared.setup(self.home, mcp_config=self.source, verify=False)
        self.assertEqual(shared.read_json(path)['permissions']['allow'], [
            'mcp__agent-tools__search_tools'])

    def test_non_lazy_setup_does_not_add_agent_tools_permission(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=False)
        settings = shared.read_json(self.home/'.claude/settings.json')
        self.assertNotIn('mcp__agent-tools__search_tools', settings['permissions'].get('allow', []))

    def test_doctor_validates_legacy_managed_dispatcher_and_missing_permission_without_writing(self):
        self.setup_shared()
        state_path = self.home/'.claude/strata-opencodex.json'
        state = shared.read_json(state_path)
        state.pop('lazy_cua_rea', None)
        state.pop('mcp_source_config', None)
        state_path.write_text(json.dumps(state), encoding='utf-8')
        settings_path = self.home/'.claude/settings.json'
        settings = shared.read_json(settings_path)
        settings['permissions']['allow'].remove('mcp__agent-tools__search_tools')
        settings_path.write_text(json.dumps(settings), encoding='utf-8')
        before = {path: path.read_bytes() for path in (state_path, settings_path, self.home/'.claude.json')}

        report = self.diagnose_shared()

        self.assertEqual(report['mcp_delivery']['mode'], 'on_demand_cua_rea')
        self.assertTrue(report['mcp_delivery']['mode_inferred_from_managed_server'])
        self.assertEqual(report['mcp_delivery']['status'], 'configured')
        self.assertEqual(report['mcp_permissions']['status'], 'missing')
        self.assertFalse(report['checks']['managed_mcp_permission_configuration'])
        self.assertFalse(report['ready'])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_doctor_rejects_changed_legacy_dispatcher_identity(self):
        self.setup_shared()
        state_path = self.home/'.claude/strata-opencodex.json'
        state = shared.read_json(state_path)
        state.pop('lazy_cua_rea', None)
        state_path.write_text(json.dumps(state), encoding='utf-8')
        native_path = self.home/'.claude.json'
        native = shared.read_json(native_path)
        native['mcpServers']['agent-tools']['args'][0] = str(self.home/'other-dispatcher.py')
        native_path.write_text(json.dumps(native), encoding='utf-8')

        report = self.diagnose_shared()

        self.assertEqual(report['mcp_delivery']['mode'], 'on_demand_cua_rea')
        self.assertEqual(report['mcp_delivery']['status'], 'mismatch')
        self.assertFalse(report['checks']['managed_mcp_configuration'])
        self.assertFalse(report['ready'])

    def test_doctor_reports_lazy_mcp_configuration_without_claiming_runtime_validation(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        preview = {'status': 'preview', 'eligible': True, 'mode': 'native',
                   'feature_effects': [{'feature': 'request.tools', 'disposition': 'passthrough'}]}
        pacing = {'status': 'not_tracking', 'provider': 'strata', 'enabled': False,
                  'queued': 0, 'next_slot_in_ms': 0, 'in_flight': None,
                  'in_flight_reported': False, 'scope': 'pacing only'}
        with patch.object(shared, 'health', return_value=262144), \
                patch.object(shared, 'messages_route_preview', return_value=preview), \
                patch.object(shared, 'opencodex_request_pacing_activity', return_value=pacing):
            report = shared.diagnose(self.home)
        self.assertTrue(report['checks']['managed_mcp_configuration'])
        self.assertEqual(report['mcp_delivery']['mode'], 'on_demand_cua_rea')
        self.assertEqual(report['mcp_delivery']['status'], 'configured')
        self.assertEqual(report['mcp_delivery']['runtime_status'], 'not_verified')
        self.assertTrue(report['checks']['managed_mcp_permission_configuration'])
        self.assertEqual(report['mcp_permissions']['status'], 'configured')
        self.assertTrue(report['mcp_permissions']['search_tool_allowed_by_rules'])
        self.assertFalse(report['mcp_permissions']['call_tool_allowed_by_rules'])
        self.assertFalse(report['mcp_permissions']['maintenance_server_configured'])
        self.assertFalse(any(report['mcp_permissions']['maintenance_read_tools_allowed_by_rules'].values()))
        self.assertEqual(report['mcp_permissions']['runtime_status'], 'not_verified')
        self.assertTrue(report['checks']['desktop_permission_mode_configuration'])
        self.assertEqual(report['desktop_permission_mode']['default_mode'], 'bypassPermissions')
        self.assertEqual(report['desktop_permission_mode']['runtime_status'], 'not_verified')
        self.assertEqual(report['opencodex_request_pacing'], pacing)

    def test_doctor_reports_saved_effort_without_claiming_current_session_effort(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        report = self.diagnose_shared()
        self.assertEqual(report['effort_level']['saved_default'], 'medium')
        self.assertEqual(report['effort_level']['status'], 'configured')
        self.assertEqual(report['effort_level']['runtime_status'], 'not_verified')
        self.assertIn('current Desktop session', report['effort_level']['scope'])

        settings_path = self.home/'.claude/settings.json'
        settings = shared.read_json(settings_path)
        settings['effortLevel'] = 'high'
        settings_path.write_text(json.dumps(settings), encoding='utf-8')
        report = self.diagnose_shared()
        self.assertEqual(report['effort_level']['saved_default'], 'high')
        self.assertEqual(report['effort_level']['runtime_status'], 'not_verified')

    def test_doctor_marks_missing_or_invalid_saved_effort_without_failing_readiness(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        settings_path = self.home/'.claude/settings.json'
        settings = shared.read_json(settings_path)
        settings.pop('effortLevel', None)
        settings_path.write_text(json.dumps(settings), encoding='utf-8')
        missing = self.diagnose_shared()
        self.assertEqual(missing['effort_level']['status'], 'missing')
        self.assertIsNone(missing['effort_level']['saved_default'])
        self.assertTrue(missing['ready'])

        settings['effortLevel'] = 'xhigh'
        settings_path.write_text(json.dumps(settings), encoding='utf-8')
        invalid = self.diagnose_shared()
        self.assertEqual(invalid['effort_level']['status'], 'invalid')
        self.assertTrue(invalid['ready'])

    def test_doctor_rejects_cli_only_permission_mode_for_desktop(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions']['defaultMode'] = 'dontAsk'
        path.write_text(json.dumps(settings), encoding='utf-8')
        report = self.diagnose_shared()
        self.assertFalse(report['checks']['desktop_permission_mode_configuration'])
        self.assertFalse(report['ready'])
        self.assertEqual(report['desktop_permission_mode']['status'], 'unsupported_for_desktop')
        self.assertEqual(report['desktop_permission_mode']['runtime_status'], 'not_verified')

    def test_doctor_reports_malformed_desktop_permission_mode_without_crashing(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions']['defaultMode'] = []
        path.write_text(json.dumps(settings), encoding='utf-8')
        report = self.diagnose_shared()
        self.assertFalse(report['checks']['desktop_permission_mode_configuration'])
        self.assertFalse(report['ready'])
        self.assertEqual(report['desktop_permission_mode']['status'], 'invalid')

    def test_doctor_detects_a_missing_lazy_search_permission_without_claiming_runtime(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions']['allow'].remove('mcp__agent-tools__search_tools')
        path.write_text(json.dumps(settings), encoding='utf-8')
        report = self.diagnose_shared()
        self.assertFalse(report['checks']['managed_mcp_permission_configuration'])
        self.assertEqual(report['mcp_permissions']['status'], 'missing')
        self.assertFalse(report['mcp_permissions']['search_tool_allowed_by_rules'])
        self.assertEqual(report['mcp_permissions']['runtime_status'], 'not_verified')
        self.assertFalse(report['ready'])

    def test_lazy_setup_reuses_user_mcp_tool_glob_without_adding_redundant_exact_rule(self):
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions'] = {'allow': ['mcp__agent-tools__search_*']}
        path.write_text(json.dumps(settings), encoding='utf-8')

        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        current = shared.read_json(path)
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        self.assertEqual(current['permissions']['allow'], ['mcp__agent-tools__search_*'])
        self.assertEqual(state['managed_permission_rules'], [])
        report = self.diagnose_shared()
        self.assertTrue(report['checks']['managed_mcp_permission_configuration'])
        self.assertTrue(report['mcp_permissions']['search_tool_allowed_by_rules'])
        self.assertFalse(report['mcp_permissions']['call_tool_allowed_by_rules'])

    def test_lazy_doctor_does_not_treat_unanchored_wildcard_as_mcp_approval(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        path = self.home/'.claude/settings.json'
        settings = shared.read_json(path)
        settings['permissions']['allow'] = ['*']
        path.write_text(json.dumps(settings), encoding='utf-8')
        report = self.diagnose_shared()
        self.assertFalse(report['checks']['managed_mcp_permission_configuration'])
        self.assertEqual(report['mcp_permissions']['status'], 'missing')

    def test_lazy_doctor_reports_ask_and_deny_precedence_over_allow(self):
        shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=True)
        path = self.home/'.claude/settings.json'
        for rule_set, rule, expected in [
            ('ask', 'mcp__agent-tools__search_tools', 'requires_confirmation'),
            ('deny', 'mcp__agent-tools__search_*', 'blocked_by_deny'),
        ]:
            with self.subTest(rule_set=rule_set):
                settings = shared.read_json(path)
                settings['permissions'][rule_set] = [rule]
                path.write_text(json.dumps(settings), encoding='utf-8')
                report = self.diagnose_shared()
                self.assertEqual(report['mcp_permissions']['status'], expected)
                self.assertFalse(report['checks']['managed_mcp_permission_configuration'])

    def test_changed_managed_guidance_stops_before_settings_or_mcp_write(self):
        self.setup_shared()
        p = self.home/'.claude/CLAUDE.md'
        p.write_text('user edit', encoding='utf-8')
        before = (self.home/'.claude/settings.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '수동 변경'):
            self.setup_shared()
        self.assertEqual(before, (self.home/'.claude/settings.json').read_bytes())
        self.assertEqual(p.read_text(), 'user edit')

    def test_unowned_mcp_conflict_does_not_overwrite_any_configuration(self):
        path = self.home/'.claude.json'
        data = shared.read_json(path)
        data['mcpServers']['rea'] = {'command': 'user-rea'}
        path.write_text(json.dumps(data))
        before = (self.home/'.claude/settings.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '기존 사용자 MCP'):
            shared.setup(self.home, mcp_config=self.source, verify=False, lazy_cua_rea=False)
        self.assertEqual(before, (self.home/'.claude/settings.json').read_bytes())
        self.assertFalse((self.home/'.claude/CLAUDE.md').exists())

    def test_shared_effort_permission_and_explicit_prompt_choice_survive_setup(self):
        self.setup_shared()
        path = self.home/'.claude/settings.json'
        data = shared.read_json(path)
        data['env']['ENABLE_TOOL_SEARCH'] = 'false'
        data.update(effortLevel='high', permissions={'defaultMode': 'plan'})
        data['env']['CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT'] = '0'
        path.write_text(json.dumps(data))
        report = self.diagnose_shared()
        self.assertFalse(report['ready'])
        self.assertFalse(report['checks']['mcp_tool_search_route_preview'])
        self.setup_shared()
        current = shared.read_json(path)
        self.assertEqual(current['env']['ENABLE_TOOL_SEARCH'], 'auto')
        self.assertEqual(current['effortLevel'], 'high')
        self.assertEqual(current['permissions']['defaultMode'], 'plan')
        self.assertEqual(current['env']['CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT'], '0')
        self.assertTrue(self.diagnose_shared()['ready'])

    def test_tool_search_requires_native_route_and_tool_passthrough(self):
        self.setup_shared()
        base = {'status': 'preview', 'eligible': True, 'mode': 'native',
                'feature_effects': [{'feature': 'request.tools', 'disposition': 'passthrough'}]}
        for preview, expected in [
            (base, True),
            ({**base, 'eligible': False}, False),
            ({**base, 'mode': 'bridge'}, False),
            ({**base, 'feature_effects': []}, False),
        ]:
            with self.subTest(preview=preview), patch.object(shared, 'health', return_value=262144), \
                    patch.object(shared, 'messages_route_preview', return_value=preview):
                report = shared.diagnose(self.home)
                self.assertEqual(report['checks']['mcp_tool_search_route_preview'], expected)
                self.assertEqual(report['mcp_tool_search']['mode'], 'model_aware_threshold_deferred')
                self.assertEqual(report['mcp_tool_search']['runtime_status'], 'not_verified')

    def test_backup_has_original_bytes_and_absent_file_receipts(self):
        original = (self.home/'.claude.json').read_bytes()
        result = self.setup_shared()
        backup = Path(result['backup'])
        manifest = json.loads((backup/'files.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['state'], 'committed')
        receipt = manifest['files']
        row = next(row for row in receipt if row['path'] == str(self.home/'.claude.json'))
        self.assertEqual((backup/row['backup']).read_bytes(), original)
        self.assertTrue(any(row['backup'] is None for row in receipt))

    def test_live_gateway_context_is_used_and_bad_model_does_not_touch_settings(self):
        with patch.object(shared, 'health', return_value=65536):
            self.assertEqual(shared.setup(self.home, mcp_config=self.source)['context'], 65536)
        settings = shared.read_json(self.home/'.claude/settings.json')
        self.assertEqual(settings['env']['CLAUDE_CODE_MAX_OUTPUT_TOKENS'], '16384')
        self.assertNotIn('CLAUDE_CODE_AUTO_COMPACT_WINDOW', settings['env'])
        original = (self.home/'.claude/settings.json').read_bytes()
        with patch.object(shared, 'health', side_effect=ValueError('missing model')):
            with self.assertRaisesRegex(ValueError, 'missing model'):
                shared.setup(self.home, mcp_config=self.source)
        self.assertEqual((self.home/'.claude/settings.json').read_bytes(), original)

    def test_concurrent_configuration_edit_is_not_overwritten(self):
        path = self.home/'.claude/settings.json'
        before = {path: path.read_bytes()}
        path.write_text('{"user":"concurrent"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '다른 작업'):
            shared.publish_files({path: '{"setup":"new"}\n'}, self.home/'.claude', before)
        self.assertEqual(path.read_text(), '{"user":"concurrent"}')

    def test_partial_publish_restores_only_owned_configuration_bytes(self):
        a, b = self.home/'a.json', self.home/'b.json'
        a.write_bytes(b'original a'); b.write_bytes(b'original b')
        replace = shared.os.replace
        def injected(source, destination):
            if Path(destination) == b:
                raise OSError('fixture write failure')
            return replace(source, destination)
        with patch.object(shared.os, 'replace', side_effect=injected):
            with self.assertRaisesRegex(OSError, 'fixture'):
                shared.publish_files({a: 'new a', b: 'new b'}, self.home/'.claude', {a: b'original a', b: b'original b'})
        self.assertEqual(a.read_bytes(), b'original a')
        self.assertEqual(b.read_bytes(), b'original b')
        self.assertFalse(list(self.home.glob('.strata-setup-*')))

    def test_rollback_preserves_concurrent_post_publish_edit(self):
        a, b = self.home/'a.json', self.home/'b.json'
        a.write_bytes(b'original a'); b.write_bytes(b'original b')
        replace = shared.os.replace
        def injected(source, destination):
            if Path(destination) == b:
                a.write_bytes(b'other session changed a')
                raise OSError('fixture concurrent write')
            return replace(source, destination)
        with patch.object(shared.os, 'replace', side_effect=injected):
            with self.assertRaises(OSError):
                shared.publish_files({a: 'new a', b: 'new b'}, self.home/'.claude', {a: b'original a', b: b'original b'})
        self.assertEqual(a.read_bytes(), b'other session changed a')
        manifest = next((self.home/'.claude/backups').glob('*/files.json'))
        self.assertEqual(json.loads(manifest.read_text())['state'], 'rollback_conflict')

    def test_supervisor_bridge_registration_is_opt_in_and_preserves_other_mcp(self):
        self.enable_maintenance_server()
        self.setup_shared()
        native = shared.read_json(self.home/'.claude.json')
        self.assertNotIn('strata-maintenance', native['mcpServers'])
        project = native['projects'][shared.maintenance_project_path()]
        self.assertIn('strata-maintenance', project['mcpServers'])
        self.assertIn('custom', native['mcpServers'])
        self.assertNotIn('a'*64, json.dumps(native))

    def test_global_maintenance_migrates_without_affecting_normal_or_new_projects(self):
        self.enable_maintenance_server()
        self.setup_shared()
        native_path = self.home/'.claude.json'
        state_path = self.home/'.claude/strata-opencodex.json'
        native, state = shared.read_json(native_path), shared.read_json(state_path)
        project = state.pop('maintenance_mcp')['project']
        server = native['projects'][project]['mcpServers'].pop('strata-maintenance')
        native['mcpServers']['strata-maintenance'] = server
        normal = {'history': 'keep', 'disabledMcpServers': ['rea'],
                  'mcpServers': {'project-tool': {'command': 'keep'}}}
        native['projects']['normal-project'] = normal
        state['managed_mcp_servers'].append('strata-maintenance')
        native_path.write_text(json.dumps(native), encoding='utf-8')
        state_path.write_text(json.dumps(state), encoding='utf-8')

        self.setup_shared()
        migrated = shared.read_json(native_path)
        self.assertEqual(migrated['projects']['normal-project'], normal)
        self.assertEqual(migrated['projects']['sample'], {'history': True})
        self.assertEqual(set(migrated['mcpServers']), {'custom', 'agent-tools'})
        self.assertEqual(migrated['projects'][project]['mcpServers']['strata-maintenance'], server)
        self.assertNotIn('strata-maintenance', migrated.get('projects', {}).get('new-project', {}).get('mcpServers', {}))
        self.assertEqual(self.setup_shared()['changed'], 0)

    def test_worktree_scope_uses_primary_repository_and_non_git_folders_keep_their_path(self):
        primary = self.home/'primary-repository'
        (primary/'.git').mkdir(parents=True)
        linked = self.home/'linked-checkout'
        linked.mkdir()
        (linked/'.git').write_text('gitdir: fixture', encoding='utf-8')
        result = shared.subprocess.CompletedProcess(['git'], 0, stdout=str(primary/'.git')+'\n')
        with patch.object(shared, 'ROOT', linked), \
                patch.object(shared.subprocess, 'run', return_value=result):
            self.assertEqual(shared.maintenance_project_path(), primary.resolve().as_posix())
        with patch.object(shared, 'ROOT', self.home/'ordinary-folder'), \
                patch.object(shared.subprocess, 'run') as command:
            self.assertEqual(shared.maintenance_project_path(), (self.home/'ordinary-folder').as_posix())
            command.assert_not_called()

    def test_maintenance_project_toggle_is_preserved_and_reported(self):
        self.enable_maintenance_server()
        self.setup_shared()
        path = self.home/'.claude.json'
        native = shared.read_json(path)
        project = shared.maintenance_project_path()
        native['projects'][project]['disabledMcpServers'] = ['strata-maintenance', 'custom']
        path.write_bytes((json.dumps(native, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
        self.assertEqual(self.setup_shared()['changed'], 0)
        report = self.diagnose_shared()
        self.assertTrue(report['checks']['managed_mcp_configuration'])
        self.assertTrue(report['mcp_permissions']['maintenance_server_configured'])
        self.assertEqual(report['mcp_delivery']['maintenance'], {
            'scope': 'local', 'project': project, 'configured': True,
            'enabled_for_project': False, 'registered_for_all_projects': False})

    def test_user_project_maintenance_conflict_does_not_publish_other_changes(self):
        self.enable_maintenance_server()
        path = self.home/'.claude.json'
        native = shared.read_json(path)
        native['projects'][shared.maintenance_project_path()] = {
            'mcpServers': {'strata-maintenance': {'command': 'user-maintenance'}}}
        path.write_text(json.dumps(native), encoding='utf-8')
        before = {p: p.read_bytes() for p in self.home.rglob('*.json')}
        with self.assertRaisesRegex(ValueError, '기존 프로젝트 유지보수 MCP'):
            self.setup_shared()
        self.assertEqual({p: p.read_bytes() for p in self.home.rglob('*.json')}, before)

    def test_relocated_setup_moves_only_the_owned_maintenance_registration(self):
        self.enable_maintenance_server()
        self.setup_shared()
        native = shared.read_json(self.home/'.claude.json')
        state = shared.read_json(self.home/'.claude/strata-opencodex.json')
        server = native['projects'][state['maintenance_mcp']['project']]['mcpServers']['strata-maintenance']
        with patch.object(shared, 'ROOT', self.home/'relocated-checkout'):
            shared.scope_maintenance_mcp(native, server, state)
        old_project = native['projects'][shared.maintenance_project_path()]
        new_project = native['projects'][(self.home/'relocated-checkout').resolve().as_posix()]
        self.assertNotIn('strata-maintenance', old_project['mcpServers'])
        self.assertIn('strata-maintenance', new_project['mcpServers'])
        self.assertNotIn('strata-maintenance', native['mcpServers'])

    def test_new_managed_asset_can_be_added_without_a_parallel_fixed_file_list(self):
        assets = shared.direct.managed_guidance(self.home/'.claude')
        assets['guidance/new-topic.md'] = 'new owned topic\n'
        with patch.object(shared.direct, 'managed_guidance', return_value=assets):
            self.setup_shared()
        self.assertEqual((self.home/'.claude/guidance/new-topic.md').read_text(), 'new owned topic\n')

    def test_smaller_client_context_is_valid_but_exceeding_server_limit_is_not(self):
        self.setup_shared()
        path = self.home/'.claude/settings.json'
        data = shared.read_json(path)
        for configured, ready in [('65536', True), ('524288', False), ('auto', False)]:
            data['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'] = configured
            path.write_text(json.dumps(data))
            with self.subTest(configured=configured):
                self.assertEqual(self.diagnose_shared()['ready'], ready)

    def test_setup_preserves_proxy_transport_and_status_labels_configuration_only(self):
        path = self.home/'.opencodex/config.json'
        config = shared.read_json(path)
        config['providers']['strata']['adapter'] = 'anthropic'
        config['protocols'] = {'rollout': {'managedMessagesNative': True}}
        path.write_text(json.dumps(config))
        before = path.read_bytes()
        self.setup_shared()
        self.assertEqual(path.read_bytes(), before)
        report = self.diagnose_shared()
        self.assertTrue(report['ready'])
        self.assertTrue(report['transport']['native_messages_configured'])
        self.assertTrue(report['checks']['mcp_tool_search_route_preview'])
        self.assertTrue(report['mcp_tool_search']['route_preview_compatible'])
        self.assertEqual(report['mcp_tool_search']['mode'], 'model_aware_threshold_deferred')
        self.assertEqual(report['mcp_tool_search']['runtime_status'], 'not_verified')
        self.assertIn('route preview', report['transport']['scope'])
        config['protocols']['rollout']['managedMessagesNative'] = False
        path.write_text(json.dumps(config))
        report = self.diagnose_shared()
        self.assertFalse(report['ready'])
        self.assertFalse(report['transport']['native_messages_configured'])

    def test_host_memory_status_returns_a_validated_point_in_time_snapshot(self):
        gib = 1024**3
        with patch.object(shared, '_physical_memory_bytes', return_value=(128*gib, 24*gib)):
            result = shared.host_memory_status()
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['total_mib'], 131072)
        self.assertEqual(result['available_mib'], 24576)
        self.assertEqual(result['available_percent'], 18.8)
        self.assertIn('GPU', result['scope'])
        with patch.object(shared, '_physical_memory_bytes', return_value=(128*gib, 129*gib)):
            self.assertEqual(shared.host_memory_status()['reason'], 'invalid_memory_status')
        with patch.object(shared, '_physical_memory_bytes', side_effect=OSError):
            self.assertEqual(shared.host_memory_status()['reason'], 'host_memory_unavailable')

    def test_linux_meminfo_parser_uses_memavailable(self):
        from unittest.mock import mock_open
        meminfo = 'MemTotal:       4194304 kB\nMemAvailable:   1048576 kB\n'
        with patch.object(shared.os, 'name', 'posix'), patch.object(shared.sys, 'platform', 'linux'), \
                patch('builtins.open', mock_open(read_data=meminfo)):
            self.assertEqual(shared._physical_memory_bytes(), (4194304*1024, 1048576*1024))

    def test_posix_sysconf_fallback_is_bounded_and_portable(self):
        pages = {'SC_PAGE_SIZE': 4096, 'SC_PHYS_PAGES': 1000, 'SC_AVPHYS_PAGES': 250}
        with patch.object(shared.os, 'name', 'posix'), patch.object(shared.sys, 'platform', 'darwin'), \
                patch.object(shared.os, 'sysconf', side_effect=pages.__getitem__, create=True):
            self.assertEqual(shared._physical_memory_bytes(), (4096*1000, 4096*250))


class LiveReadinessFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name); (self.home/'.opencodex').mkdir()
        self.loaded = True; self.actual_model = 'qwen-test'; self.redirect = False
        self.activity_redirect = False
        self.slots = [{'id': 0, 'is_processing': False}]
        self.status_redirect = False
        self.status_too_large = False
        self.status = {'service': 'strata', 'loaded': True, 'cache_max_tokens': 262144,
            'concurrency': {'serving': 1, 'requested': 1},
            'activity': {'requests': 13, 'in_flight': 0, 'last_request_at': 1792964866,
                         'private': 'do-not-return'},
            'last_timings': {'prompt_n': 34098, 'prompt_per_second': 2681.1, 'prompt_ms': 12718.1,
                             'predicted_n': 37, 'predicted_per_second': 89.0, 'predicted_ms': 415.6,
                             'cache_n': 0, 'private_timing': 'do-not-return'},
            'machine': {'gpu': {'name': 'Fixture GPU', 'used_mib': 12000, 'total_mib': 24000,
                                'util_pct': 8, 'temp_c': 44, 'power_w': 90, 'serial': 'private'},
                        'gpus': [{'name': 'Fixture GPU 0', 'used_mib': 12000, 'total_mib': 24000,
                                  'index': 0, 'role': 'model', 'serial': 'private'},
                                 {'name': 'Fixture GPU 1', 'used_mib': 2, 'total_mib': 24000,
                                  'index': 1, 'role': 'unused'}],
                        'ram': {'used_gib': 103.5, 'total_gib': 127.9}},
            'vram': {'elastic': False, 'secret': 'private'}, 'api_key': 'private'}
        self.auth = []
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                fixture.auth.append((self.path, self.headers.get('Authorization')))
                if self.path == '/health' and fixture.redirect:
                    self.send_response(302);self.send_header('Location', '/should-not-follow');self.end_headers();return
                if self.path == '/slots' and fixture.activity_redirect:
                    self.send_response(302);self.send_header('Location', '/should-not-follow');self.end_headers();return
                if self.path == '/v1/status' and fixture.status_redirect:
                    self.send_response(302);self.send_header('Location', '/should-not-follow');self.end_headers();return
                if self.path == '/v1/status' and fixture.status_too_large:
                    raw = b' ' * (256*1024+1)
                    self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                data = {'/healthz': {'status': 'ok', 'service': 'opencodex'},
                    '/v1/models': {'data': [{'id': 'strata/qwen-test', 'context_window': 262144}]},
                    '/health': {'status': 'ok', 'loaded': fixture.loaded, 'model': fixture.actual_model, 'max_context': 65536},
                    '/v1/status': fixture.status,
                    '/slots': fixture.slots}[self.path]
                raw = json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
        config = {'providers': {'strata': {'baseUrl': self.base+'/v1', 'apiKey': 'fixture-provider-secret'}}}
        (self.home/'.opencodex/config.json').write_text(json.dumps(config))
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)

    def test_actual_smaller_context_and_credentials_stay_on_upstream_endpoint(self):
        self.assertEqual(shared.health(self.base,'strata/qwen-test',home=self.home),65536)
        self.assertEqual(self.auth[0][1], 'Bearer opencodex-proxy')
        self.assertEqual(self.auth[-1], ('/health','Bearer fixture-provider-secret'))

    def test_model_catalog_discovery_uses_timeout_for_measured_cold_refresh(self):
        original_urlopen = shared.urlopen
        observed = []

        def record_timeout(request, timeout):
            observed.append((request.full_url.rsplit('/', 1)[-1], timeout))
            return original_urlopen(request, timeout=timeout)

        with patch.object(shared, 'urlopen', side_effect=record_timeout):
            self.assertEqual(shared.health(self.base,'strata/qwen-test',home=self.home),65536)

        self.assertEqual(observed, [
            ('healthz', 5),
            ('models', shared.MODEL_CATALOG_TIMEOUT_SECONDS),
        ])
        self.assertEqual(shared.MODEL_CATALOG_TIMEOUT_SECONDS, 15)

    def test_cached_catalog_does_not_hide_unloaded_or_different_model(self):
        self.loaded = False
        with self.assertRaisesRegex(ValueError, '실제 Strata'):
            shared.health(self.base,'strata/qwen-test',home=self.home)
        self.loaded = True;self.actual_model = 'other'
        with self.assertRaisesRegex(ValueError, '실제 Strata'):
            shared.health(self.base,'strata/qwen-test',home=self.home)

    def test_upstream_redirect_is_not_followed_with_provider_credential(self):
        self.redirect = True
        with self.assertRaises(HTTPError):
            shared.health(self.base,'strata/qwen-test',home=self.home)
        self.assertFalse(any(path=='/should-not-follow' for path,_ in self.auth))

    def test_maintenance_health_does_not_refresh_unrelated_provider_catalogs(self):
        self.assertEqual(shared.health(self.base,'strata/qwen-test',home=self.home,discover=False),65536)
        self.assertEqual([path for path,_ in self.auth], ['/healthz','/health'])

    def test_strata_activity_reports_idle_and_busy_without_slot_details_or_credentials(self):
        idle = shared.strata_activity(self.home)
        self.assertEqual((idle['status'], idle['is_idle'], idle['in_flight']), ('idle', True, 0))
        self.status['activity']['in_flight'] = 2
        busy = shared.strata_activity(self.home)
        self.assertEqual((busy['status'], busy['is_idle'], busy['in_flight']), ('busy', False, 2))
        serialized = json.dumps(busy)
        self.assertNotIn('fixture-provider-secret', serialized)
        self.assertNotIn('is_processing', serialized)
        self.assertEqual(self.auth, [('/v1/status', 'Bearer fixture-provider-secret')]*2)
        self.assertIn('OpenCodex 대기열', busy['scope'])

    def test_strata_activity_fails_closed_for_bad_slots_or_redirects(self):
        self.status['activity']['in_flight'] = 'invalid'
        self.slots = [{'id': 0, 'busy': False}]
        result = shared.strata_activity(self.home)
        self.assertEqual((result['status'], result['is_idle'], result['reason']),
                         ('unknown', None, 'invalid_slot_response'))
        self.slots = [{'id': 0, 'is_processing': False}]
        self.activity_redirect = True
        result = shared.strata_activity(self.home)
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['is_idle'])
        self.assertFalse(any(path == '/should-not-follow' for path, _ in self.auth))

    def test_strata_runtime_status_returns_only_bounded_validated_telemetry(self):
        result = shared.strata_runtime_status(self.home)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['context_tokens'], 262144)
        self.assertEqual(result['concurrency'], {'serving': 1, 'requested': 1})
        self.assertEqual(result['activity'], {'status': 'idle', 'is_idle': True, 'in_flight': 0,
            'requests': 13, 'last_request_at': 1792964866})
        self.assertEqual(result['last_request_timings'], {'prompt_n':34098,'prompt_per_second':2681.1,
            'prompt_ms':12718.1,'predicted_n':37,'predicted_per_second':89.0,'predicted_ms':415.6,'cache_n':0})
        self.assertEqual(result['machine']['gpu']['used_mib'], 12000)
        self.assertEqual(result['machine']['gpus'][1]['role'], 'unused')
        self.assertEqual(result['machine']['ram']['used_gib'], 103.5)
        self.assertEqual(result['vram'], {'elastic': False})
        serialized = json.dumps(result)
        for secret in ('fixture-provider-secret', 'do-not-return', 'private', 'serial', 'api_key', 'private_timing'):
            self.assertNotIn(secret, serialized)
        self.assertIn('장치 전체', result['scope'])
        self.assertEqual(self.auth, [('/v1/status', 'Bearer fixture-provider-secret')])

    def test_strata_runtime_status_drops_out_of_range_values_and_fails_closed(self):
        self.status['machine']['gpu']['util_pct'] = 101
        self.status['machine']['gpu']['used_mib'] = 25000
        self.status['machine']['gpu']['total_mib'] = 24000
        self.status['activity']['in_flight'] = -1
        result = shared.strata_runtime_status(self.home)
        self.assertNotIn('util_pct', result['machine']['gpu'])
        self.assertNotIn('used_mib', result['machine']['gpu'])
        self.assertEqual(result['activity']['status'], 'unknown')
        self.status_redirect = True
        result = shared.strata_runtime_status(self.home)
        self.assertEqual(result['reason'], 'HTTPError')
        self.assertFalse(any(path == '/should-not-follow' for path, _ in self.auth))
        self.status_redirect = False
        self.status_too_large = True
        self.assertEqual(shared.strata_runtime_status(self.home)['reason'], 'response_too_large')

    def test_strata_activity_reuses_status_observation_and_falls_back_to_slots(self):
        status = shared.strata_runtime_status(self.home)
        activity = shared.strata_activity(self.home, runtime_status=status)
        self.assertEqual(activity['status'], 'idle')
        self.assertEqual(self.auth, [('/v1/status', 'Bearer fixture-provider-secret')])
        status['activity']['status'] = 'unknown'
        self.slots = [{'id': 0, 'is_processing': True}]
        activity = shared.strata_activity(self.home, runtime_status=status)
        self.assertEqual(activity['status'], 'busy')
        self.assertEqual([path for path, _ in self.auth], ['/v1/status', '/slots'])


class OpenCodexRequestPacingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home/'.opencodex').mkdir()
        (self.home/'.opencodex/config.json').write_text(json.dumps({
            'port': 10100, 'providers': {'strata': {'defaultModel': 'qwen-test'}}}), encoding='utf-8')

    def test_reports_paced_queue_and_inflight_counts_without_other_fields(self):
        status = {'provider':'strata','enabled':True,'queued':2,'nextSlotInMs':75,
                  'inFlight':1,'lastStartedAt':123,'lastModelId':'private-model',
                  'keys':[{'id':'private-key-id','inFlight':1}]}
        with patch.object(shared, 'management_json', return_value=(status, None)) as query:
            report = shared.opencodex_request_pacing_activity(self.home)
        self.assertEqual(report['status'], 'observed')
        self.assertEqual((report['queued'], report['next_slot_in_ms'], report['in_flight']), (2,75,1))
        self.assertTrue(report['in_flight_reported'])
        self.assertEqual(query.call_args.args, (self.home, 'http://127.0.0.1:10100',
            '/api/provider-request-pacing?name=strata'))
        self.assertEqual(query.call_args.kwargs, {'timeout':2})
        serialized = json.dumps(report)
        self.assertNotIn('private-model', serialized)
        self.assertNotIn('private-key-id', serialized)
        self.assertIn('전체 요청 유휴 상태를 증명하지 않습니다', report['scope'])

    def test_disabled_pacing_does_not_claim_no_inflight_requests(self):
        with patch.object(shared, 'management_json', return_value=(
                {'provider':'strata','enabled':False,'queued':0,'nextSlotInMs':0}, None)):
            report = shared.opencodex_request_pacing_activity(self.home)
        self.assertEqual(report['status'], 'not_tracking')
        self.assertEqual(report['queued'], 0)
        self.assertIsNone(report['in_flight'])
        self.assertFalse(report['in_flight_reported'])
        self.assertNotIn('is_idle', report)

    def test_missing_or_invalid_pacing_data_fails_closed(self):
        for value, error, reason in [
            (None, 'management_api_unavailable', 'management_api_unavailable'),
            ({'provider':'other','enabled':True,'queued':0,'nextSlotInMs':0}, None, 'invalid_pacing_status'),
            ({'provider':'strata','enabled':True,'queued':-1,'nextSlotInMs':0}, None, 'invalid_pacing_status'),
            ({'provider':'strata','enabled':True,'queued':0,'nextSlotInMs':0,'inFlight':-1}, None, 'invalid_pacing_status'),
        ]:
            with self.subTest(value=value, error=error), \
                    patch.object(shared, 'management_json', return_value=(value, error)):
                report = shared.opencodex_request_pacing_activity(self.home)
            self.assertEqual(report['status'], 'unknown')
            self.assertEqual(report['reason'], reason)


class MessagesRoutePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home/'.opencodex').mkdir()
        self.token = 'ocx_admin_'+'x'*43
        (self.home/'.opencodex/admin-api-token').write_text(self.token+'\n', encoding='utf-8')
        self.requests = []
        self.redirect_management = False
        self.extra_response_bytes = 0
        self.logs_rows = [
            {'timestamp': 1000, 'surface': 'claude', 'inboundProtocol': 'messages',
             'provider': 'strata', 'model': 'qwen-test', 'status': 200, 'durationMs': 100,
             'firstOutputMs': 10, 'usage': {'inputTokens': 100, 'cachedInputTokens': 80,
                 'outputTokens': 5}, 'protocolTrace': {'inbound':'messages','mode':'native',
                 'requestPath':['messages','messages'],'responsePath':['messages','messages'],
                 'reasonCodes':['same-wire-native'],'featureEffects':[{'feature':'request.tools',
                 'disposition':'passthrough'}]}, 'genStartMs':20,'lastOutputMs':90,
             'displayMetrics':{'decodeTokPerSecond':{'kind':'value','value':60.0,'estimated':True,
                 'timingBasis':'generation-window'}}, 'prompt':'must not be returned'},
            {'timestamp': 1500, 'surface': 'claude-desktop', 'inboundProtocol': 'messages',
             'provider': 'strata', 'model': 'qwen-test', 'status': 200, 'durationMs': 60,
             'firstOutputMs': 8, 'usage': {'inputTokens': 90, 'cachedInputTokens': 70,
                 'outputTokens': 4}, 'genStartMs':15,'lastOutputMs':45,
             'displayMetrics':{'decodeTokPerSecond':{'kind':'unavailable','reason':'decode_window_too_short'}},
             'protocolTrace': {'inbound':'messages','mode':'native'}},
            {'timestamp': 2000, 'surface': 'claude', 'inboundProtocol': 'messages',
             'provider': 'strata', 'model': 'qwen-test', 'status': 499, 'durationMs': 50,
             'firstOutputMs': 5, 'protocolTrace': {'mode':'native'}},
            {'timestamp': 2500, 'surface': 'claude', 'inboundProtocol': 'messages',
             'provider': 'strata', 'model': 'qwen-test', 'status': 200, 'durationMs': 120,
             'firstOutputMs': 14, 'usage': {'inputTokens': 120, 'cachedInputTokens': 60,
                 'outputTokens': 8}, 'protocolTrace': {'inbound':'messages','mode':'native',
                 'requestPath':['messages','messages'],'responsePath':['messages','messages'],
                 'reasonCodes':['same-wire-native'],'featureEffects':[]}, 'genStartMs':25,'lastOutputMs':100,
             'displayMetrics':{'decodeTokPerSecond':{'kind':'unavailable','reason':'decode_window_too_short'}}},
            {'timestamp': 3000, 'surface': 'claude', 'inboundProtocol': 'chat',
             'provider': 'strata', 'model': 'qwen-test', 'status': 200, 'durationMs': 999},
        ]
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                fixture.requests.append((self.path, self.headers.get('Authorization'), None))
                if fixture.redirect_management:
                    self.send_response(302);self.send_header('Location','/credential-should-not-follow');self.end_headers();return
                raw = json.dumps({'logs':fixture.logs_rows,'secret':'never-return-this',
                    'padding':'x'*fixture.extra_response_bytes}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                fixture.requests.append((self.path, self.headers.get('Authorization'),
                    json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))))
                if fixture.redirect_management:
                    self.send_response(302);self.send_header('Location','/credential-should-not-follow');self.end_headers();return
                plan = {'basis': 'preview', 'routeKind': 'provider', 'mode': 'native',
                    'candidates': [{'provider': 'strata', 'model': 'qwen-test', 'mode': 'native',
                        'requestPath': ['messages','messages'], 'responsePath': ['messages','messages'],
                        'fidelity': 'preserved', 'eligible': True, 'reasonCodes': ['same-wire-native'],
                        'featureEffects': [{'feature':'request.tools','disposition':'passthrough'}]}]}
                raw = json.dumps(plan).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)

    def test_preview_uses_management_plane_and_returns_only_sanitized_route_fields(self):
        result = shared.messages_route_preview(self.home,self.base,'strata/qwen-test')
        self.assertEqual(self.requests[0][0],'/api/protocols/plan')
        self.assertEqual(self.requests[0][1],'Bearer '+self.token)
        self.assertEqual(self.requests[0][2], {'model':'strata/qwen-test','inbound':'messages','features':[
            'request.tools','request.reasoning','request.thinking_budget','request.cache_control']})
        self.assertEqual(result['status'],'preview')
        self.assertEqual(result['mode'],'native')
        self.assertEqual(result['request_path'],['messages','messages'])
        self.assertNotIn(self.token,json.dumps(result))
        self.assertNotIn('candidates',result)

    def test_missing_admin_token_is_reported_without_failing_connection_diagnosis(self):
        (self.home/'.opencodex/admin-api-token').unlink()
        self.assertEqual(shared.messages_route_preview(self.home,self.base,'strata/qwen-test'),
            {'status':'unavailable','reason':'admin_token_file_unavailable'})
        self.assertEqual(self.requests,[])

    def test_observed_messages_trace_returns_only_bounded_latency_and_route_metadata(self):
        result = shared.observed_messages_route(self.home,self.base,'strata/qwen-test')
        self.assertEqual(self.requests[0][0],'/api/logs?provider=strata&model=qwen-test&limit=12')
        self.assertEqual(self.requests[0][1],'Bearer '+self.token)
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['sample_count'],4)
        self.assertEqual(result['successful_count'],3)
        self.assertEqual(result['non_success_statuses'],[499])
        self.assertEqual(result['median_duration_ms_successful'],100)
        self.assertEqual(result['median_first_response_chunk_ms_successful'],10)
        self.assertEqual(result['decode_rate_by_basis']['generation-window'],
                         {'median_tokens_per_second':60.0,'sample_count':1})
        self.assertEqual(result['median_request_output_tokens_per_second_successful'],66.7)
        self.assertEqual(result['by_surface']['claude'], {'sample_count':3,'successful_count':2,
            'median_duration_ms_successful':110,'median_first_response_chunk_ms_successful':12,
            'decode_rate_by_basis':{'generation-window':{'median_tokens_per_second':60.0,'sample_count':1}},
            'median_request_output_tokens_per_second_successful':58.4})
        self.assertEqual(result['by_surface']['claude-desktop'], {'sample_count':1,'successful_count':1,
            'median_duration_ms_successful':60,'median_first_response_chunk_ms_successful':8,
            'decode_rate_by_basis':{},'median_request_output_tokens_per_second_successful':66.7})
        self.assertEqual(result['latest']['surface'],'claude')
        self.assertEqual(result['latest']['cached_input_tokens'],60)
        self.assertEqual(result['latest']['decode_tokens_per_second'],
                         {'status':'unavailable','reason':'decode_window_too_short'})
        self.assertEqual(result['latest']['generation_window_ms'],75)
        self.assertEqual(result['latest']['request_output_tokens_per_second'],66.7)
        self.assertEqual(result['latest']['first_response_chunk_ms'],14)
        self.assertEqual(result['latest']['route']['request_path'],['messages','messages'])
        self.assertIn('not time to first generated',result['first_response_chunk_scope'])
        self.assertIn('legacy first-visible-output estimates remain unavailable',result['decode_rate_scope'])
        self.assertIn('not decode speed',result['request_rate_scope'])
        self.assertNotIn('must not be returned',json.dumps(result))
        self.assertNotIn(self.token,json.dumps(result))
        self.assertNotIn('secret',json.dumps(result))

    def test_decode_rate_uses_official_generation_window_and_rejects_failed_rows(self):
        latest = self.logs_rows[-2]
        latest.update(status=499, durationMs=120, firstOutputMs=14,
            usage={'inputTokens':120,'cachedInputTokens':60,'outputTokens':8})
        failed = shared.observed_messages_route(self.home,self.base,'strata/qwen-test')
        self.assertEqual(failed['latest']['output_tokens'],8)
        self.assertEqual(failed['latest']['decode_tokens_per_second'],
                         {'status':'unavailable','reason':'request_not_successful'})

        latest.update(status=200, durationMs=14, firstOutputMs=14)
        no_interval = shared.observed_messages_route(self.home,self.base,'strata/qwen-test')
        self.assertNotIn('generation_window_ms',no_interval['latest'])
        self.assertEqual(no_interval['latest']['decode_tokens_per_second'],
                         {'status':'unavailable','reason':'decode_window_too_short'})

        latest.update(durationMs=1200, firstOutputMs=10, genStartMs=None,lastOutputMs=None,
            displayMetrics={'decodeTokPerSecond':{'kind':'value','value':42.0,'estimated':True,
                'timingBasis':'legacy-post-visible-output'}})
        legacy = shared.observed_messages_route(self.home,self.base,'strata/qwen-test')
        self.assertEqual(legacy['latest']['decode_tokens_per_second'],
                         {'status':'unavailable','reason':'legacy_baseline_not_safe'})

    def test_context_usage_compares_recent_request_to_auto_compact_threshold(self):
        observed = {'status':'observed','latest':{'input_tokens':90,'cached_input_tokens':70}}
        result = shared.context_usage_observation(observed, 100)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['window_utilization_percent'], 90.0)
        self.assertEqual(result['remaining_tokens_to_auto_compact_window'], 10)
        self.assertEqual(result['cached_input_percent'], 77.8)
        self.assertIn('not the Claude Desktop context meter', result['scope'])

    def test_context_usage_is_unavailable_when_the_denominator_or_request_is_missing(self):
        self.assertEqual(shared.context_usage_observation({'status':'unavailable'}, 100),
            {'status':'unavailable','reason':'request_usage_or_compaction_window_unavailable'})
        self.assertEqual(shared.context_usage_observation({'status':'observed','latest':{}}, 100),
            {'status':'unavailable','reason':'latest_request_usage_unavailable'})

    def test_no_recent_observed_claude_messages_is_nonfatal(self):
        self.logs_rows = []
        self.assertEqual(shared.observed_messages_route(self.home,self.base,'strata/qwen-test'),
            {'status':'unavailable','reason':'no_recent_claude_messages'})

    def test_connection_refusal_history_is_visible_after_recovery_without_raw_error_data(self):
        self.logs_rows = [
            {'timestamp': 5000, 'surface': 'claude-desktop', 'inboundProtocol': 'messages',
             'provider': 'strata', 'model': 'qwen-test', 'status': 502, 'durationMs': 7,
             'upstreamError': 'ECONNREFUSED: Authorization: Bearer secret-must-not-leak'},
            {'timestamp': 6000, 'surface': 'claude-desktop', 'inboundProtocol': 'messages',
             'provider': 'strata', 'model': 'qwen-test', 'status': 200, 'durationMs': 100},
        ]
        result = shared.observed_messages_route(self.home, self.base, 'strata/qwen-test')
        self.assertEqual(result['latest']['status'], 200)
        self.assertEqual(result['failure_summary'], {
            'sample_count': 1, 'categories': {'upstream_connection_refused': 1},
            'latest': {'timestamp': 5000, 'status': 502, 'duration_ms': 7,
                       'category': 'upstream_connection_refused'}})
        self.assertNotIn('secret-must-not-leak', json.dumps(result))
        self.assertNotIn('Authorization', json.dumps(result))

    def test_unrecognized_or_structured_errors_stay_unclassified(self):
        for error in (None, {'message': 'ECONNREFUSED'}, ['ECONNREFUSED'], 123,
                      'unexpected private error', 'PREFIXECONNREFUSED'):
            with self.subTest(error=error):
                self.logs_rows = [{'timestamp': 5000, 'surface': 'claude-desktop',
                    'inboundProtocol': 'messages', 'provider': 'strata', 'model': 'qwen-test',
                    'status': 502, 'upstreamError': error}]
                result = shared.observed_messages_route(self.home, self.base, 'strata/qwen-test')
                self.assertEqual(result['failure_summary']['categories'], {'unclassified_http_error': 1})
                self.assertNotIn('upstreamError', json.dumps(result))

    def test_management_token_never_follows_redirect(self):
        self.redirect_management = True
        preview = shared.messages_route_preview(self.home,self.base,'strata/qwen-test')
        observed = shared.observed_messages_route(self.home,self.base,'strata/qwen-test')
        self.assertEqual(preview['reason'],'management_http_302')
        self.assertEqual(observed['reason'],'management_http_302')
        self.assertEqual(len(self.requests),2)
        self.assertTrue(all('/credential-should-not-follow' not in path for path,_,_ in self.requests))

    def test_oversized_management_log_response_is_bounded(self):
        self.extra_response_bytes = 300_000
        self.assertEqual(shared.observed_messages_route(self.home,self.base,'strata/qwen-test'),
            {'status':'unavailable','reason':'management_response_too_large'})


if __name__ == '__main__':
    unittest.main()
