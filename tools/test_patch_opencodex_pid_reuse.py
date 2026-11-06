"""버전 경계·원본 보존·멱등 재적용을 확인하는 PID 재사용 스테일 판정 패치 검사."""
from pathlib import Path
import json
import tempfile
import unittest

from tools.patch_opencodex_pid_reuse import CHANGES, MARKER, STATE, FENCE, install, patch_file

FENCE_PATH = Path(FENCE)
STATE_PATH = Path(STATE)


def fixture(relative):
    pairs = CHANGES[relative]['pairs']
    return pairs[0][0] + '\n// unrelated line\n' + (pairs[1][0] + '\n' if relative == FENCE_PATH else pairs[1][0])


class PidReusePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root/'package.json'
        self.package.write_text(json.dumps({'name': '@bitkyc08/opencodex', 'version': '2.95.0'}), encoding='utf-8')
        for relative in CHANGES:
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(relative), encoding='utf-8')

    def test_both_files_apply_with_expected_markers_and_reapply_is_noop(self):
        for relative in CHANGES:
            with self.subTest(relative=str(relative)):
                patched = patch_file(relative, fixture(relative))
                self.assertEqual(patched.count(MARKER), CHANGES[relative]['marker'])
                self.assertEqual(patch_file(relative, patched), patched)
                if relative == STATE_PATH:
                    self.assertIn('export function pidReusedSincePidRecord(', patched)
                    self.assertIn('statSync', patched.splitlines()[0])
                else:
                    self.assertIn('pidReusedSincePidRecord, removePidIfValueIs', patched)
                    self.assertIn('&& !(owner.pidSnapshot !== null && pidReusedSincePidRecord(owner.pidSnapshot)))', patched)

    def test_partial_or_unknown_state_raises(self):
        fence = fixture(FENCE_PATH)
        first_new = CHANGES[FENCE_PATH]['pairs'][0][1]
        with self.assertRaisesRegex(ValueError, '일부만'):
            patch_file(FENCE_PATH, fence.replace(CHANGES[FENCE_PATH]['pairs'][0][0], first_new, 1))
        with self.assertRaisesRegex(ValueError, '중복'):
            patch_file(FENCE_PATH, fixture(FENCE_PATH) + CHANGES[FENCE_PATH]['pairs'][1][0] + '\n')
        with self.assertRaises(ValueError):
            patch_file(FENCE_PATH, 'unrecognized source\n')
        with self.assertRaises(ValueError):
            patch_file(Path('src/other.ts'), fixture(FENCE_PATH))

    def test_install_is_idempotent_and_keeps_bom_and_crlf(self):
        for relative in CHANGES:
            path = self.root/relative
            text = fixture(relative).replace('\n', '\r\n')
            path.write_bytes(b'\xef\xbb\xbf'+text.encode())
        first = install(self.root)
        self.assertEqual(first['changed_files'], 2)
        self.assertEqual(first['runtime_reflection'], 'next_startup')
        self.assertIsNotNone(first['backup'])
        for relative in CHANGES:
            raw = (self.root/relative).read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
            self.assertIn(b'\r\n', raw)
        state = (self.root/STATE_PATH).read_bytes().decode('utf-8-sig')
        self.assertIn('export function pidReusedSincePidRecord(', state)
        fence = (self.root/FENCE_PATH).read_bytes().decode('utf-8-sig')
        self.assertIn(MARKER, fence)
        self.assertIn('\r\n', fence)
        self.assertEqual(install(self.root)['changed_files'], 0)
        self.assertTrue((self.root/'.strata-pid-reuse').is_dir())

    def test_other_version_or_package_is_rejected_without_edit(self):
        for name, version in (('@bitkyc08/opencodex', '2.96.0'), ('other-package', '2.95.0')):
            with self.subTest(name=name, version=version):
                self.package.write_text(json.dumps({'name': name, 'version': version}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    install(self.root)
        for relative in CHANGES:
            self.assertEqual((self.root/relative).read_text(encoding='utf-8'), fixture(relative))


if __name__ == '__main__':
    unittest.main()
