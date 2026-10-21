"""CPU-only immutable runtime packaging tests; no live process or config touched."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import opencode_runtime_assets as assets


class RuntimeAssetTests(unittest.TestCase):
    def test_upgrade_preserves_old_files_options_and_single_registration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / 'strata-output-recovery'
            base.mkdir()
            old = base / 'index.js'
            old.write_bytes(b'old runtime')
            config = {'plugins':[{'package':str(base),'options':{'providerID':'custom'}}, 'unrelated']}
            files = assets.prepare_runtime_assets(config,root,names=('output',))
            for path, content in files.items():
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(content)
            entry = config['plugins'][0]
            self.assertEqual(entry['options'],{'providerID':'custom'})
            self.assertEqual(old.read_bytes(),b'old runtime')
            self.assertEqual(Path(entry['package']).parent,base/'versions')
            self.assertEqual(files,assets.prepare_runtime_assets(config,root,names=('output',)))
            self.assertEqual(len(config['plugins']),2)
            corrupt = Path(entry['package'])/'index.js'
            corrupt.write_bytes(b'changed externally')
            with self.assertRaisesRegex(ValueError,'Immutable runtime asset changed'):
                assets.prepare_runtime_assets(config,root,names=('output',))
            self.assertEqual(corrupt.read_bytes(),b'changed externally')

    def test_source_change_stages_new_version_and_pins_bootstrap(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'source'
            plugin=source/'examples/opencode/acp-foreground-guard'
            scripts=source/'tools/opencode'
            plugin.mkdir(parents=True)
            scripts.mkdir(parents=True)
            for name in ('index.js','package.json'):
                (plugin/name).write_bytes(b'fixture')
            for name in ('powershell-bootstrap.ps1','powershell-preflight.ps1'):
                (scripts/name).write_bytes(b'fixture')
            config={}
            with patch.object(assets,'ROOT',source):
                first=assets.prepare_runtime_assets(config,root/'installed',names=('acp',))
                old=config['plugins'][0]['package']
                (scripts/'powershell-preflight.ps1').write_bytes(b'new source')
                second=assets.prepare_runtime_assets(config,root/'installed',names=('acp',))
            entry=config['plugins'][0]
            self.assertNotEqual(old,entry['package'])
            self.assertFalse(set(first)&set(second))
            self.assertEqual(Path(entry['options']['bootstrapPath']).parent,Path(entry['package']))
            self.assertEqual(len(config['plugins']),1)


if __name__=='__main__':
    unittest.main()
