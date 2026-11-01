"""CPU-only fork deployment checks for the opt-in image source cache."""
from pathlib import Path
import tempfile
import unittest

from tools.patch_nvfp4_vision_source_cache import CHANGES, PatchError, install, patch_server

ROOT = Path(__file__).resolve().parents[1]


class VisionCachePatch(unittest.TestCase):
    def original_server(self):
        text = (ROOT/'serve/server.py').read_text(encoding='utf-8')
        for old, new in reversed(CHANGES):
            self.assertEqual(text.count(new), 1)
            text = text.replace(new, old, 1)
        return text

    def test_known_layout_roundtrip_preserves_unrelated_changes(self):
        original = self.original_server()+'\n# preserve another fork feature\n'
        patched = patch_server(original)
        self.assertEqual(patch_server(patched), patched)
        for old, new in reversed(CHANGES):
            patched = patched.replace(new, old, 1)
        self.assertEqual(patched, original)

    def test_unknown_and_partial_layouts_are_refused(self):
        with self.assertRaises(PatchError):
            patch_server('class Vision: pass')
        for old, new in CHANGES:
            with self.subTest(hook=old[:60]), self.assertRaises(PatchError):
                patch_server(self.original_server().replace(old, new, 1))

    def test_atomic_install_backup_and_noop_preserve_crlf_and_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory)/'server.py'
            original = b'\xef\xbb\xbf'+self.original_server().replace('\n', '\r\n').encode('utf-8')
            server.write_bytes(original)
            first = install(server)
            self.assertEqual(first['changed'], 1)
            self.assertEqual((Path(first['backup'])/'0-server.py').read_bytes(), original)
            patched = server.read_bytes()
            self.assertTrue(patched.startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\n', patched.replace(b'\r\n', b''))
            self.assertEqual(install(server)['changed'], 0)
            self.assertEqual(server.read_bytes(), patched)

    def test_refusal_leaves_unknown_file_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory)/'server.py'
            server.write_bytes(b'class Vision: pass\n')
            with self.assertRaises(PatchError):
                install(server)
            self.assertEqual(server.read_bytes(), b'class Vision: pass\n')
            self.assertFalse((server.parent/'.vision-source-cache').exists())


if __name__ == '__main__':
    unittest.main()
