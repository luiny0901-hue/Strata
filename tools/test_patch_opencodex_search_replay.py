"""버전 경계와 원본 보존을 확인하는 검색 이력·재시작 경로 패치 검사."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.patch_opencodex_search_replay import (
    ORIGINAL, PATCHED, RELATIVE_SOURCE, SERVICE_CHANGES, SERVICE_MARKER,
    install, patch_file, patch_source,
)

REPAIR = Path('src/service/repair.ts')
CLI = Path('src/service/cli.ts')

def fixture(relative):
    if relative == REPAIR:
        return ('  stopScheduler?: () => void;\n  startScheduler?: () => void;\n'
                '    try { (deps.stopScheduler ?? stopWindows)(); } catch { /* not running */ }\n'
                '    (deps.writeSchedulerAssets ?? writeWindowsSchedulerAssets)(runtime);\n')
    if relative == CLI:
        return ('import { stopTrackedProxyForServiceCommand, installServiceSafely } from "./orchestration";\n'
                '      await repairService({ verb, supervisionLatch });\n')
    raise AssertionError(relative)


class SearchReplayPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root/'package.json'
        self.package.write_text(json.dumps({'name': '@bitkyc08/opencodex', 'version': '2.95.0'}), encoding='utf-8')
        self.source = self.root/RELATIVE_SOURCE
        self.source.parent.mkdir(parents=True)
        for relative in (REPAIR, CLI):
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(relative), encoding='utf-8')

    def test_service_files_apply_both_edits_and_reapply_is_noop(self):
        for relative in (REPAIR, CLI):
            with self.subTest(relative=str(relative)):
                original = fixture(relative)
                patched = patch_file(relative, original)
                self.assertNotEqual(patched, original)
                for old, new in SERVICE_CHANGES[relative]:
                    self.assertIn(new, patched)
                if any(SERVICE_MARKER in new for old, new in SERVICE_CHANGES[relative]):
                    self.assertIn(SERVICE_MARKER, patched)
                self.assertEqual(patch_file(relative, patched), patched)
                for old, new in reversed(SERVICE_CHANGES[relative]):
                    patched = patched.replace(new, old, 1)
                self.assertEqual(patched, original)

    def test_mixed_service_state_raises_and_installs_nothing(self):
        self.source.write_text(ORIGINAL, encoding='utf-8')
        repair_text = fixture(REPAIR)
        old, new = SERVICE_CHANGES[REPAIR][0]
        (self.root/REPAIR).write_text(repair_text.replace(old, new, 1), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '일부만'):
            install(self.root)
        self.assertEqual((self.root/REPAIR).read_text(encoding='utf-8'), repair_text.replace(old, new, 1))
        self.assertEqual(self.source.read_text(encoding='utf-8'), ORIGINAL)

    def test_only_empty_string_rejection_changes_and_reapply_is_noop(self):
        source = 'before\n'+ORIGINAL+'\nafter\n'
        updated = patch_source(source)
        self.assertEqual(updated, 'before\n'+PATCHED+'\nafter\n')
        self.assertEqual(patch_source(updated), updated)
        self.assertIn('typeof value.signature !== "string"', updated)

    def test_unknown_duplicate_or_mixed_guard_preserves_source(self):
        for source in ('unrecognized source', ORIGINAL+'\n'+ORIGINAL, ORIGINAL+'\n'+PATCHED):
            with self.subTest(source=source), self.assertRaises(ValueError):
                patch_source(source)

    def test_install_preserves_bom_newlines_and_unrelated_content(self):
        raw = b'\xef\xbb\xbf'+('before\r\n'+ORIGINAL+'\r\nafter\r\n').encode()
        self.source.write_bytes(raw)
        first = install(self.root)
        self.assertEqual(first['changed_files'], 3)
        self.assertIsNotNone(first['backup'])
        self.assertEqual(self.source.read_bytes(), raw.replace(ORIGINAL.encode(), PATCHED.encode(), 1))
        self.assertEqual(install(self.root)['changed_files'], 0)

    def test_other_version_or_package_is_rejected_without_edit(self):
        self.source.write_text(ORIGINAL, encoding='utf-8')
        for name, version in (('@bitkyc08/opencodex', '2.96.0'), ('other-package', '2.95.0')):
            with self.subTest(name=name, version=version):
                self.package.write_text(json.dumps({'name': name, 'version': version}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    install(self.root)
                self.assertEqual(self.source.read_text(encoding='utf-8'), ORIGINAL)

    def test_unknown_source_install_leaves_bytes_unchanged(self):
        raw = b'unknown layout\n'
        self.source.write_bytes(raw)
        with self.assertRaises(ValueError):
            install(self.root)
        self.assertEqual(self.source.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
