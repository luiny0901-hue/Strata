"""Offline contracts for installer side effects, resume, and credential handling."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from tools import install_strata_agent as install
from tools import claude_opencodex_client as shared


class IntegratedInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='strata-install-test-')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def test_plan_never_probes_installs_or_writes_user_state(self):
        with patch.object(install, 'run', side_effect=AssertionError('No subprocess')), \
             patch.object(install, 'refresh_path', side_effect=AssertionError('No PATH mutation')), \
             patch.object(Path, 'home', side_effect=AssertionError('No user state')), \
             contextlib.redirect_stdout(StringIO()) as output:
            self.assertEqual(install.main(['--role', 'client', '--plan']), 0)
        self.assertFalse(json.loads(output.getvalue())['changes'])

    def test_existing_package_is_not_reinstalled(self):
        installer = install.Installer(self.home, 'client', 'win32')
        with patch.object(install, 'run', side_effect=AssertionError('No install')), \
             contextlib.redirect_stdout(StringIO()):
            installer.package('OpenJS.NodeJS.LTS', lambda: True)

    def test_unsupported_role_is_rejected_before_install_or_user_state(self):
        with patch.object(install.sys, 'platform', 'darwin'), \
             patch.object(install, 'run', side_effect=AssertionError('No install')), \
             patch.object(install, 'refresh_path', side_effect=AssertionError('No PATH mutation')), \
             patch.object(Path, 'home', side_effect=AssertionError('No user state')), \
             contextlib.redirect_stderr(StringIO()):
            self.assertEqual(install.main(['--role', 'server']), 2)

    def test_resume_reprobes_and_keeps_a_failed_step_incomplete(self):
        installer = install.Installer(self.home, 'client')
        with contextlib.redirect_stdout(StringIO()):
            installer.step('package', lambda: None)
            def unavailable():
                raise install.Pending('not ready')
            with self.assertRaises(install.Pending):
                installer.step('server', unavailable)
        resumed = install.Installer(self.home, 'client')
        self.assertEqual(resumed.state['status'], 'waiting')
        self.assertEqual(resumed.state['steps']['server'], 'incomplete')
        observed = []
        with contextlib.redirect_stdout(StringIO()):
            resumed.step('package', lambda: observed.append('rechecked'))
        self.assertEqual(observed, ['rechecked'])

    def test_another_installer_cannot_enter_the_same_user_lock(self):
        with install.install_lock(self.home):
            with self.assertRaises(install.Pending):
                with install.install_lock(self.home):
                    self.fail('A second installer entered')
        with install.install_lock(self.home):
            pass

    def test_uncertain_install_is_not_replayed_without_checking_prior_completion(self):
        installer = install.Installer(self.home, 'client', 'win32')
        with contextlib.redirect_stdout(StringIO()):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.fail_timeout(installer)
        resumed = install.Installer(self.home, 'client', 'win32')
        with patch.object(install.shutil, 'which', return_value='fixture-winget'), \
             patch('builtins.input', return_value=''), patch.object(install, 'run') as runner, \
             contextlib.redirect_stdout(StringIO()):
            with self.assertRaises(install.Pending):
                resumed.step('package', lambda: resumed.package('fixture-package', lambda: False))
        runner.assert_not_called()
        self.assertEqual(resumed.state['steps']['package'], 'uncertain')

    def fail_timeout(self, installer):
        def timeout():
            raise subprocess.TimeoutExpired('fixture-installer', 1)
        installer.step('package', timeout)

    def test_finished_package_after_timeout_is_reused_without_another_confirmation(self):
        installer = install.Installer(self.home, 'client', 'win32')
        installer.state['steps']['package'] = 'uncertain'
        installer.save()
        resumed = install.Installer(self.home, 'client', 'win32')
        with patch('builtins.input', side_effect=AssertionError('No repeat question')), \
             patch.object(install, 'run', side_effect=AssertionError('No reinstall')), \
             contextlib.redirect_stdout(StringIO()):
            resumed.step('package', lambda: resumed.package('fixture-package', lambda: True))
        self.assertEqual(resumed.state['steps']['package'], 'configured')

    def test_provider_preserves_existing_fields_and_never_journals_a_key(self):
        secret = 'fixture-credential-not-for-journal'
        for original_key in ('{file:credential-reference}', ''):
            with self.subTest(key_is_reference=bool(original_key)):
                config_path = self.home/'.opencodex/config.json'
                config_path.parent.mkdir(exist_ok=True)
                config_path.write_text(json.dumps({'providers': {'strata': {
                    'baseUrl': 'http://127.0.0.1:8080/v1', 'apiKey': original_key,
                    'modelAliases': {'keep': 'unchanged'}, 'custom': True}}}), encoding='utf-8')
                before = config_path.read_bytes()
                installer = install.Installer(self.home, 'client')
                installer.base = 'http://127.0.0.1:10100'
                headers = {'Authorization': 'Bearer '+secret} if original_key else {}
                with patch.object(shared, 'strata_upstream', return_value=('http://127.0.0.1:8080', headers)), \
                     patch.object(install.getpass, 'getpass', return_value=secret), \
                     patch.object(install, 'get_json', return_value={'status': 'ok', 'loaded': True,
                          'model': 'qwen-fixture', 'max_context': 262144}) as health, \
                     patch.object(shared, 'management_json', return_value=({'success': True}, None)) as save, \
                     patch.object(install, 'run', side_effect=AssertionError('No argv credential')):
                    installer.connect('local')
                provider = save.call_args.kwargs['body']['provider']
                self.assertEqual(provider['apiKey'], original_key or secret)
                self.assertEqual(provider['modelAliases'], {'keep': 'unchanged'})
                self.assertTrue(provider['custom'])
                self.assertNotIn(secret, installer.path.read_text(encoding='utf-8'))
                self.assertEqual(health.call_args.args[1]['Authorization'], 'Bearer '+secret)
                self.assertEqual(config_path.read_bytes(), before)  # only the management API may write config

    def test_unready_model_cannot_save_a_provider_or_finish_install(self):
        installer = install.Installer(self.home, 'client')
        installer.base = 'http://127.0.0.1:10100'
        with patch.object(install.getpass, 'getpass', return_value='fixture'), \
             patch.object(install, 'get_json', return_value={'status': 'ok', 'loaded': False}), \
             patch.object(shared, 'management_json') as save, \
             contextlib.redirect_stdout(StringIO()):
            with self.assertRaises(install.Pending):
                installer.step('server', lambda: installer.connect('local'))
        save.assert_not_called()
        self.assertEqual(installer.state['status'], 'waiting')

    def test_conflicting_proxy_owner_never_triggers_repair_or_restart(self):
        installer = install.Installer(self.home, 'client')
        with patch.object(install, 'ocx_command', return_value=['fixture-ocx']), \
             patch.object(install, 'run', return_value=json.dumps({'installed': True, 'conflict': True})) as runner:
            with self.assertRaises(install.Pending):
                installer.proxy()
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0][-3:], ['service', 'status', '--json'])

    def test_ready_existing_common_settings_are_not_regenerated(self):
        from tools import strata_client_settings as clients
        state = self.home/'.claude'/shared.STATE
        state.parent.mkdir(); state.write_text('{}', encoding='utf-8')
        installer = install.Installer(self.home, 'client')
        installer.model = 'fixture-model'
        with patch.object(shared, 'diagnose', return_value={'ready': True, 'desktop_ready': True}), \
             patch.object(shared, 'setup') as setup, patch.object(clients, 'sync_model'), \
             patch.object(install, 'ocx_command', return_value=['fixture-ocx']), \
             patch.object(install, 'run'), contextlib.redirect_stdout(StringIO()):
            installer.client_config()
        setup.assert_not_called()
        self.assertEqual(state.read_text(encoding='utf-8'), '{}')

    def test_ssh_options_and_shell_commands_are_rejected(self):
        for host in ('-oProxyCommand=bad', 'alice@host;whoami', 'host\ncommand', 'host name', 'alice:secret@host', ''):
            with self.subTest(host=host), self.assertRaises(ValueError):
                install.validate_ssh_host(host)
        install.validate_ssh_host('alice@server.example')

    def test_server_key_is_reused_and_invalid_existing_key_is_not_replaced(self):
        with patch.object(install, 'run', return_value='S-1-5-21-123'):
            install.ensure_server_key(self.home)
            path = self.home/'.config/strata/STRATA_API_KEY'
            original = path.read_bytes()
            self.assertEqual(len(original), 64)
            install.ensure_server_key(self.home)
            self.assertEqual(path.read_bytes(), original)
            path.write_text('invalid', encoding='utf-8')
            with self.assertRaises(install.Pending):
                install.ensure_server_key(self.home)
            self.assertEqual(path.read_text(encoding='utf-8'), 'invalid')

    def test_missing_exact_server_artifacts_never_launch_an_engine(self):
        class RestoreFixture(install.Installer):
            def step(self, name, operation):
                if name == '서버 Python 의존성':
                    return
                if name == 'GPU 드라이버·장치 선택':
                    self.state['gpu'] = 0
                    return
                return super().step(name, operation)
        installer = RestoreFixture(self.home, 'server', 'linux')
        with patch.object(install, 'ROOT', self.home/'empty-checkout'), \
             patch.object(install, 'run', side_effect=AssertionError('No engine')), \
             contextlib.redirect_stdout(StringIO()):
            with self.assertRaisesRegex(install.Pending, '동일 포크'):
                install.prepare_server(installer)
        self.assertEqual(installer.state['status'], 'waiting')


if __name__ == '__main__':
    unittest.main()
