"""Windows CMD dispatch only; fake manager, no server/model/GPU launch."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.configure_strata_managed_launchers import enable_managed_launchers

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name=='nt','Windows BAT dispatch')
class ManagedOptIn(unittest.TestCase):
    def test_both_launchers_keep_opt_in_and_owned_child_boundary(self):
        for mode in ('on','off'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);path=root/'launcher.bat';stub=root/'fake-python.cmd'
                stub.write_text('@echo off\necho MANAGED_ROUTE\nexit /b 0\n')
                source=(ROOT/f'run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-{mode}.bat').read_text()
                # Execute actual routing clauses, replacing only the interpreter and startup tail.
                head=source.split('if not exist "%API_KEY_FILE%"',1)[0]
                self.assertEqual(head.count('set "PYTHON='),1)
                head='\n'.join('set "PYTHON='+str(stub)+'"' if line.startswith('set "PYTHON=') else line for line in head.splitlines())
                path.write_text(head+'\necho NORMAL_ROUTE\nexit /b 0\n')
                env={**os.environ,'USERPROFILE':str(root)};env.pop('STRATA_SUPERVISOR_CHILD',None)
                def run(args=(),child=False):
                    result=subprocess.run(['cmd.exe','/d','/c',str(path),*args],env={**env,**({'STRATA_SUPERVISOR_CHILD':'1'} if child else {})},capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr);return result.stdout
                self.assertIn('NORMAL_ROUTE',run())
                self.assertIn('MANAGED_ROUTE',run(('--managed',)))
                flag=enable_managed_launchers(root);before=flag.read_bytes()
                self.assertIn('MANAGED_ROUTE',run())
                self.assertIn('NORMAL_ROUTE',run(child=True))
                self.assertIn('NORMAL_ROUTE',run(('--managed',),child=True))
                self.assertEqual(enable_managed_launchers(root).read_bytes(),before)


if __name__=='__main__':unittest.main()
