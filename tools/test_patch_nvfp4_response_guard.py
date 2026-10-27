"""Known-layout patching, default behavior and atomic install contracts."""
from pathlib import Path
import tempfile
import unittest

from tools.patch_nvfp4_response_guard import CHANGES,MARKER,PatchError,install,patch_server,patch_structured

ROOT=Path(__file__).resolve().parents[1]


class ForkGuardPatch(unittest.TestCase):
    def original_server(self):
        text=(ROOT/'serve/server.py').read_text(encoding='utf-8')
        for old,new in reversed(CHANGES):text=text.replace(new,old,1)
        return text

    def test_complete_hook_is_idempotent(self):
        original=self.original_server();patched=patch_server(original)
        self.assertEqual(patched.count(MARKER),4)
        self.assertEqual(patch_server(patched),patched)
        # Only the documented four hooks changed; unrelated fork changes survive.
        for old,new in reversed(CHANGES):patched=patched.replace(new,old,1)
        self.assertEqual(patched,original)

    def test_unknown_or_partial_source_is_rejected(self):
        for source in ['class Service: pass',self.original_server()+'\n'+MARKER]:
            with self.assertRaises(PatchError):patch_server(source)
        with self.assertRaises(PatchError):patch_structured('def validated_json(text, validator, finish, *, extractor=None): pass')

    def test_install_is_atomic_and_second_install_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);server=root/'server.py';structured=root/'structured.py'
            server.write_text(self.original_server(),encoding='utf-8')
            structured.write_bytes((ROOT/'serve/structured.py').read_bytes())
            first=install(server);self.assertEqual(first['changed'],2)
            before={p.name:p.read_bytes() for p in root.glob('*.py')}
            second=install(server);self.assertEqual(second['changed'],0)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.glob('*.py')})
            self.assertIsNotNone(first['backup'])

    def test_bad_helper_or_module_leaves_every_source_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);server=root/'server.py';structured=root/'structured.py'
            server.write_text(self.original_server(),encoding='utf-8')
            structured.write_text('unknown helper',encoding='utf-8')
            before=server.read_bytes()
            with self.assertRaises(PatchError):install(server)
            self.assertEqual(server.read_bytes(),before)
            self.assertFalse((root/'anthropic_response_guard.py').exists())
            structured.write_bytes((ROOT/'serve/structured.py').read_bytes())
            bad=root/'bad.py';bad.write_text('def broken(',encoding='utf-8')
            with self.assertRaises(SyntaxError):install(server,bad)
            self.assertEqual(server.read_bytes(),before)
            self.assertFalse((root/'anthropic_response_guard.py').exists())


if __name__=='__main__':unittest.main()
