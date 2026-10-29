"""CPU/mock release and existing supervisor integration; no downloads or GPU work."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from tools import strata_fork_update as u
from tools.strata_server_supervisor import Supervisor
from tools.strata_iq4xs_profiles import render_profile

ROOT = Path(__file__).resolve().parents[1]


def release(tag='v0.1.45.1-nvfp4.1'):
    name = f'strata-nvfp4-{tag}-windows-x64.zip'
    return {'tag_name': tag, 'assets': [{'name': name, 'size': 10,
            'digest': 'sha256:' + 'a' * 64,
            'browser_download_url': f'https://github.com/{u.REPO}/releases/download/{tag}/{name}'}]}


def bundle(path, v):
    path.mkdir(parents=True, exist_ok=True)
    (path/'serve').mkdir()
    (path/'serve/server.py').write_text('original = True\n')
    (path/'requirements-serve.txt').write_text('same\n')
    (path/'requirements-model.txt').write_text('same\n')
    files = {p.relative_to(path).as_posix(): u.digest(p) for p in path.rglob('*') if p.is_file()}
    u.write(path/'release-manifest.json', {'version': v, 'files': files})
    return path


class ForkUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.updates = u.ForkUpdates(self.root)
        self.old = bundle(self.root/u.DEFAULT_FORK, '0.1.44.1-nvfp4.2')
        u.write(self.updates.directory/'config.json', {'enabled': True})

    def pending(self):
        relative = 'forks/auto-nvfp4-0.1.45.1-nvfp4.1/strata-nvfp4'
        new = bundle(self.root/relative, '0.1.45.1-nvfp4.1')
        u.write(self.updates.directory/'pending.json', {'version': '0.1.45.1-nvfp4.1', 'path': relative,
                'previous_path': self.old.relative_to(self.root).as_posix(),
                'baseline': u.inventory(self.old), 'files': u.inventory(new)})
        return new

    def supervisor(self):
        supervisor = Supervisor(self.root, ['unused'], 'http://127.0.0.1:1', self.root/'key', 'fixture',
                                updates=self.updates)
        self.addCleanup(supervisor.log.close)
        supervisor.process = Mock()
        supervisor.port_open = Mock(return_value=False)
        supervisor.wait_ready = Mock()
        return supervisor

    def test_semantic_beta_filter_even_when_github_marks_final_and_numeric_order(self):
        beta = release('v0.2.0-beta-nvfp4.3')
        beta['prerelease'] = False
        draft = {**release('v9.0.0-nvfp4.1'), 'draft': True}
        a, b = release('v0.1.45.1-nvfp4.2'), release('v0.1.45.1-nvfp4.10')
        self.assertIs(u.latest_stable([beta, draft, a, b]), b)

    def test_asset_never_selects_upstream_or_missing_digest_or_other_host(self):
        rel = release()
        upstream = dict(rel['assets'][0], name='strata-windows-x64.zip')
        rel['assets'].insert(0, upstream)
        self.assertTrue(u.asset_for(rel)['name'].startswith('strata-nvfp4-'))
        for attr, value in [('digest', None), ('size', True), ('browser_download_url', 'https://other.invalid/x')]:
            bad = release(); bad['assets'][0][attr] = value
            with self.subTest(attr=attr), self.assertRaises(ValueError):
                u.asset_for(bad)

    def test_no_new_stable_means_no_download_and_daily_cache(self):
        current = release('v0.1.44.1-nvfp4.2')
        with patch.object(self.updates, 'prepare') as prepare, patch.object(u, 'fetch_releases') as fetch:
            result = self.updates.check(releases=[current, release('v0.2.0-beta-nvfp4.3')])
            self.assertEqual(result['status'], 'current')
            self.assertEqual(self.updates.check(), result)
        prepare.assert_not_called(); fetch.assert_not_called()

    def test_linux_never_downloads_windows_bundle(self):
        with patch.object(self.updates, 'prepare') as prepare:
            self.assertEqual(self.updates.check(releases=[release()], platform='linux')['status'], 'platform_unavailable')
        prepare.assert_not_called()

    def test_network_failure_preserves_current_and_retries_no_more_than_daily(self):
        with patch.object(u, 'fetch_releases', side_effect=OSError('offline')) as fetch:
            self.assertEqual(self.updates.check()['status'], 'deferred')
            self.updates.check()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(u.selected_fork(self.root), self.old)

    def test_archive_rejects_traversal_links_duplicates_and_windows_aliases(self):
        bad_names = ('strata-nvfp4/../../escape', 'strata-nvfp4/CON.txt',
                     'strata-nvfp4/file.', 'strata-nvfp4/C:/bad', 'strata-nvfp4/a\\b')
        for n, name in enumerate(bad_names):
            archive = self.root/f'{n}.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                info = zipfile.ZipInfo(name)
                info.filename = name  # Python normalizes backslashes when constructing ZipInfo on Windows.
                z.writestr(info, b'x')
            with self.subTest(name=name), self.assertRaises(ValueError):
                u.unpack(archive, self.root/f'extract{n}')
        for n, names in enumerate([['strata-nvfp4/A', 'strata-nvfp4/a'], ['strata-nvfp4/link']]):
            archive = self.root/f'other{n}.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for name in names:
                    info = zipfile.ZipInfo(name)
                    if name.endswith('link'): info.external_attr = 0o120777 << 16
                    z.writestr(info, b'x')
            with self.assertRaises(ValueError):
                u.unpack(archive, self.root/f'other{n}')
        self.assertFalse((self.root/'escape').exists())

    def test_download_hash_mismatch_and_cancel_never_publish_pending(self):
        for stopped in (False, True):
            with patch.object(u, 'urlopen', return_value=io.BytesIO(b'0123456789')):
                with self.assertRaises((ValueError, RuntimeError)):
                    u.download(release()['assets'][0], self.root/str(stopped), lambda: stopped)
        self.assertFalse((self.updates.directory/'pending.json').exists())

    def test_changed_custom_upstream_anchor_blocks_before_live_files_change(self):
        new = bundle(self.root/'candidate', '0.1.45.1-nvfp4.1')
        (self.old/'serve/server.py').write_text('local = True\n')
        (new/'serve/server.py').write_text('changed = True\n')
        m = u.read(new/'release-manifest.json'); m['files']['serve/server.py'] = u.digest(new/'serve/server.py')
        u.write(new/'release-manifest.json', m)
        with self.assertRaisesRegex(ValueError, 'local customization'):
            u.preserve_customizations(self.old, new)
        self.assertEqual((self.old/'serve/server.py').read_text(), 'local = True\n')

    def test_successful_activation_uses_one_start_and_preserves_previous_bundle(self):
        new = self.pending(); supervisor = self.supervisor()
        supervisor.start()
        self.assertEqual(u.selected_fork(self.root), new)
        self.assertEqual(supervisor.process.start.call_count, 1)
        self.assertEqual(u.read(self.updates.directory/'transaction.json')['state'], 'ready')
        self.assertTrue(self.old.is_dir())
        self.assertFalse((self.updates.directory/'pending.json').exists())

    def test_readiness_failure_drains_candidate_and_restores_once_without_replay(self):
        self.pending(); supervisor = self.supervisor()
        supervisor.wait_ready.side_effect = [RuntimeError('not ready'), None]
        supervisor.start()
        self.assertEqual(u.selected_fork(self.root), self.old)
        self.assertEqual(supervisor.process.start.call_count, 2)
        supervisor.process.stop.assert_called_once()
        self.assertEqual(u.read(self.updates.directory/'rejected.json')['version'], '0.1.45.1-nvfp4.1')
        with patch.object(self.updates, 'prepare') as prepare:
            self.assertEqual(self.updates.check(releases=[release()], platform='win32')['status'], 'rejected')
        prepare.assert_not_called()

    def test_busy_port_or_failed_drain_never_starts_replacement(self):
        self.pending(); supervisor = self.supervisor()
        supervisor.port_open.return_value = True
        with self.assertRaises(RuntimeError): supervisor.start()
        supervisor.process.start.assert_not_called()
        supervisor.port_open.return_value = False
        supervisor.wait_ready.side_effect = RuntimeError('failed')
        supervisor.process.stop.side_effect = RuntimeError('tree not drained')
        with self.assertRaisesRegex(RuntimeError, 'tree not drained'): supervisor.start()
        self.assertEqual(supervisor.process.start.call_count, 1)

    def test_interrupted_activation_restores_on_next_owner_start_even_disabled(self):
        self.pending(); supervisor = self.supervisor()
        self.updates.activate(supervisor)
        u.write(self.updates.directory/'config.json', {'enabled': False})
        self.assertIsNone(self.updates.activate(supervisor))
        self.assertEqual(u.selected_fork(self.root), self.old)

    def test_post_preparation_edit_defers_and_never_overwrites_local_work(self):
        self.pending(); supervisor = self.supervisor()
        (self.old/'serve/server.py').write_text('new edit\n')
        supervisor.start()
        self.assertEqual(u.selected_fork(self.root), self.old)
        self.assertEqual(u.read(self.updates.directory/'status.json')['status'], 'deferred')

    def test_missing_or_malformed_pending_never_blocks_previous_service(self):
        new = self.pending(); supervisor = self.supervisor()
        (new/'serve/server.py').unlink()
        supervisor.start()
        self.assertEqual(u.selected_fork(self.root), self.old)
        (self.updates.directory/'pending.json').write_text('{broken')
        supervisor.start()
        self.assertEqual(supervisor.process.start.call_count, 2)

    def test_verified_side_by_side_preparation_preserves_custom_module_without_activation(self):
        new = bundle(self.root/'bundle-source', '0.1.45.1-nvfp4.1')
        for name in ('serve/structured.py', 'engine/strata.exe', 'engine/strata-vision.exe',
                     'data/uncensor/qwen-nvfp4-gptq-uncensored.gguf'):
            p = new/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('pass\n')
        manifest = u.read(new/'release-manifest.json')
        manifest['files'] = {p.relative_to(new).as_posix(): u.digest(p) for p in new.rglob('*')
                             if p.is_file() and p.name != 'release-manifest.json'}
        u.write(new/'release-manifest.json', manifest)
        (self.old/'serve/local.py').write_text('custom = True\n')
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            for path in new.rglob('*'):
                if path.is_file(): z.writestr('strata-nvfp4/'+path.relative_to(new).as_posix(), path.read_bytes())
        raw = data.getvalue(); rel = release(); asset = rel['assets'][0]
        asset['size'] = len(raw); asset['digest'] = 'sha256:'+u.hashlib.sha256(raw).hexdigest()
        with patch.object(u, 'urlopen', return_value=io.BytesIO(raw)), \
             patch('tools.patch_nvfp4_server_effort.patch_source', side_effect=lambda s: (s, False)), \
             patch('tools.patch_nvfp4_vision_source_cache.patch_server', side_effect=lambda s: s), \
             patch('tools.patch_nvfp4_response_guard.patch_server', side_effect=lambda s: s), \
             patch('tools.patch_nvfp4_response_guard.patch_structured', side_effect=lambda s: s):
            self.updates.prepare(self.old, rel, lambda: False)
        pending = u.read(self.updates.directory/'pending.json')
        candidate = self.root/pending['path']
        self.assertEqual((candidate/'serve/local.py').read_text(), 'custom = True\n')
        self.assertEqual(u.selected_fork(self.root), self.old)
        self.assertEqual(u.inventory(candidate), pending['files'])

    def test_both_profiles_and_launcher_resolve_same_pointer(self):
        new = self.pending(); supervisor = self.supervisor(); supervisor.start()
        for mode in ('on', 'off'):
            output = self.root/f'{mode}.json'
            render_profile(ROOT, mode, self.root, self.root/'data', output)
            profile = u.read(output)
            self.assertEqual(Path(profile['exe'].replace('\\', '/')).parent.parent, new)
            self.assertIn('262144', profile['args'])
            self.assertIn('448', profile['args'])

    @unittest.skipUnless(os.name == 'nt', 'Windows CMD quoting')
    def test_actual_cmd_launcher_resolves_pointer_with_spaces_without_starting_server(self):
        new = self.pending(); supervisor = self.supervisor(); supervisor.start()
        (self.root/'tools').mkdir()
        for name in ('strata_iq4xs_profiles.py', 'strata_fork_update.py'):
            shutil.copy2(ROOT/'tools'/name, self.root/'tools'/name)
        for mode in ('on', 'off'):
            text = (ROOT/f'run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-{mode}.bat').read_text()
            head = text.split('if not exist "%API_KEY_FILE%"', 1)[0]
            head = '\n'.join('set "PYTHON='+sys.executable+'"' if line.startswith('set "PYTHON=') else line
                             for line in head.splitlines())
            path = self.root/f'with spaces {mode}.bat'
            path.write_text(head+'\necho SELECTED=%FORK_ROOT%\necho ENGINE=%ENGINE_DIR%\nexit /b 0\n')
            result = subprocess.run(['cmd.exe', '/d', '/c', str(path)],
                     env={**os.environ, 'STRATA_SUPERVISOR_CHILD': '1'}, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SELECTED='+str(new), result.stdout)
            self.assertIn('ENGINE='+str(new/'engine'), result.stdout)

    def test_watch_prepares_only_never_restarts_running_server(self):
        supervisor = self.supervisor()
        def checked(**kwargs):
            supervisor.stopping.set()
            return {'status': 'prepared'}
        with patch.object(self.updates, 'check', side_effect=checked):
            supervisor.watch_updates()
        supervisor.process.start.assert_not_called()
        supervisor.process.stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
