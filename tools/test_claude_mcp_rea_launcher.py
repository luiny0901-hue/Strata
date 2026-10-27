import unittest, tempfile, json
from pathlib import Path
from tools.claude_mcp.rea_launcher import cached_entry, launch_command, PACKAGE
class LauncherTests(unittest.TestCase):
 def test_version_matches_installer(self):
  self.assertEqual(PACKAGE,'rea-agents@6.7.0')
 def test_pinned_cache_and_fallback(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'cache/node_modules/rea-agents';(p/'scripts').mkdir(parents=True)
   (p/'scripts/rea.mjs').write_text('fixture');meta=p/'package.json'
   meta.write_text(json.dumps({'name':'rea-agents','version':'6.7.0'}))
   self.assertEqual(launch_command([root],'node','npx'),['node',str(p/'scripts/rea.mjs'),'mcp'])
   meta.write_text(json.dumps({'name':'rea-agents','version':'99.0.0'}))
   self.assertIsNone(cached_entry([root]));self.assertEqual(launch_command([root],'node','npx',True),['cmd.exe','/d','/c','npx','-y',PACKAGE,'mcp'])
if __name__=='__main__':unittest.main()
