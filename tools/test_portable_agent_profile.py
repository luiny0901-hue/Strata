import unittest
from pathlib import Path
from tools.remote_agent_client.portable_profile import export_profile,apply_profile,validate

class PortableProfile(unittest.TestCase):
    def source(self):
        return {'model':'strata/local','agents':{'build':{'steps':512}},'compaction':{'auto':True,'keep':{'tokens':12000},'buffer':65536},
          'providers':{'strata':{'settings':{'apiKey':'DO-NOT-EXPORT','baseURL':'http://private'},'models':{'local':{'body':{'temperature':0.6,'apiKey':'NEVER'}}}}},
          'shell':'C:/old/pwsh.exe','tools':{'rea_*':False},'instructions':[]}
    def target(self,context=262144):
        return {'providers':{'strata':{'settings':{'baseURL':'http://new'},'models':{'server':{'limit':{'context':context,'output':min(32000,context//4)}}}}},'compaction':{'auto':True,'keep':{'tokens':12000},'buffer':1024}}
    def test_only_portable_values_export_and_restore(self):
        p=export_profile(self.source(),Path('/example'),'high');t=self.target();apply_profile(t,p)
        self.assertEqual(t['agents']['build']['steps'],512)
        self.assertEqual(t['providers']['strata']['models']['server']['body']['reasoning_effort'],'high')
        self.assertNotIn('DO-NOT-EXPORT',str(p));self.assertNotIn('NEVER',str(p));self.assertNotIn('C:/old',str(p))
        self.assertEqual(t['providers']['strata']['settings']['baseURL'],'http://new')
    def test_smaller_server_context_caps_restored_compaction(self):
        p=export_profile(self.source(),Path('/example'));t=self.target(8192);apply_profile(t,p)
        available=8192-2048
        self.assertLessEqual(t['compaction']['buffer']+t['compaction']['keep']['tokens'],available)
    def test_invalid_profile_fails_before_mutation(self):
        p=export_profile(self.source(),Path('/example'));p['body']['command']='bad';t=self.target();before=str(t)
        with self.assertRaises(ValueError):apply_profile(t,p)
        self.assertEqual(str(t),before)
    def test_disabled_compaction_and_tool_setting_survive(self):
        p=export_profile(self.source(),Path('/example'));p['compaction']['auto']=False;t=self.target();apply_profile(t,p)
        self.assertFalse(t['compaction']['auto']);self.assertFalse(t['tools']['rea_*'])

    def test_setup_restores_profile_with_new_pc_paths_and_receipt(self):
        import tempfile,json,shutil
        from unittest.mock import patch
        from tools.remote_agent_client import setup_client as client
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'package';home=Path(directory)/'new-user';root.mkdir();home.mkdir()
            bridge=root/'tools/opencode/acp_compact_display.py';bridge.parent.mkdir(parents=True)
            shutil.copy2(client.REPO_ROOT/'tools/opencode/acp_compact_display.py',bridge)
            (root/'portable-profile.json').write_text(json.dumps(export_profile(self.source(),home,'high')))
            node=home/'node.exe';driver=home/'cua-driver.exe';cli=home/'opencode.exe'
            for path in (node,driver,cli):path.write_bytes(b'fixture')
            with patch.object(client,'REPO_ROOT',root),patch.object(client,'secure_windows_directory'),patch.dict('os.environ',{'CUA_NODE_EXE':str(node)}):
                name=client.write_setup(home,'http://100.64.0.2:8080/v1','new-secret',{'max_context':262144,'images':True},{'id':'server-new'},cli,'2.0.22',driver,'existing','configured')
            config=json.loads(client.overlay_path(home).read_text(encoding='utf-8'))
            self.assertEqual(config['agents']['build']['steps'],512)
            self.assertEqual(config['providers']['strata']['models']['server']['body']['reasoning_effort'],'high')
            self.assertEqual(config['providers']['strata']['models']['server']['modelID'],'server-new')
            self.assertNotIn('DO-NOT-EXPORT',json.dumps(config))
            self.assertIn(name,json.loads(client.acp_path(home).read_text(encoding='utf-8'))['agent_servers'])
            self.assertEqual(client.check_assets(json.loads(client.state_path(home).read_text(encoding='utf-8'))),[])

if __name__=='__main__':unittest.main()
