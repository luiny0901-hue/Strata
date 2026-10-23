"""Portable shell smoke checks; Git Bash results are not native Linux process proof."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASH=r'C:\Program Files\Git\bin\bash.exe' if os.name=='nt' else shutil.which('bash')


@unittest.skipUnless(BASH and Path(BASH).is_file(), 'Bash unavailable')
class CommandCompletionTests(unittest.TestCase):
    def run_command(self, command, timeout='5', heartbeat='60'):
        with tempfile.TemporaryDirectory(prefix='runner smoke ') as directory:
            return subprocess.run([BASH,str(ROOT/'tools/opencode/run_bounded_command.sh'),
                                   '--timeout',timeout,'--heartbeat',heartbeat,'--log-dir',directory,
                                   '--','bash','-c',command],capture_output=True,timeout=8)

    def test_short_command_does_not_wait_for_heartbeat_and_preserves_output(self):
        result=self.run_command('printf IMMEDIATE_OK')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(b'IMMEDIATE_OK',result.stdout)
        self.assertNotIn(b'still running',result.stderr)

    def test_failure_does_not_wait_for_heartbeat_and_preserves_exit(self):
        result=self.run_command('exit 7')
        self.assertEqual(result.returncode,7,result.stderr)
        self.assertIn(b'EXIT_CODE=7',result.stdout)

    def test_longer_command_still_reports_progress(self):
        result=self.run_command('sleep 2; printf FINISHED',heartbeat='1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(b'still running',result.stderr)
        self.assertIn(b'FINISHED',result.stdout)

    def test_timeout_still_returns_124(self):
        result=self.run_command('sleep 3',timeout='1',heartbeat='60')
        self.assertEqual(result.returncode,124,result.stderr)
        self.assertIn(b'TIMEOUT_SECONDS=1',result.stderr)


if __name__=='__main__':
    unittest.main()
