"""CPU-only tests for bounded OpenCode command execution on Windows and Linux."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_RUNNER = ROOT / "tools" / "opencode" / "run_bounded_command.ps1"
BASH_RUNNER = ROOT / "tools" / "opencode" / "run_bounded_command.sh"


class WindowsCommandRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.name != "nt":
            raise unittest.SkipTest("Windows runner tests require Windows")
        cls.pwsh = shutil.which("pwsh")
        if not cls.pwsh:
            raise unittest.SkipTest("PowerShell 7 (pwsh) is not installed")

    def run_runner(self, command: str, log_directory: Path, timeout: int = 10, extra_args=()) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.pwsh,
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(POWERSHELL_RUNNER),
                "-Command",
                command,
                "-WorkingDirectory",
                str(ROOT),
                "-TimeoutSeconds",
                str(timeout),
                "-HeartbeatSeconds",
                "1",
                "-LogDirectory",
                str(log_directory),
                *extra_args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )

    def test_success_preserves_output_and_zero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("cmd.exe /d /c echo RUNNER_OK", Path(temporary))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RUNNER_OK", result.stdout)
        self.assertIn("EXIT_CODE=0", result.stdout)

    def test_nonzero_exit_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("cmd.exe /d /c exit 7", Path(temporary))
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn("EXIT_CODE=7", result.stdout)

    def test_powershell_error_is_not_reported_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("Write-Error 'EXPECTED_CMDLET_FAILURE'", Path(temporary))
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_interactive_prompt_fails_without_waiting_or_false_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("Read-Host 'Do not prompt an agent'", Path(temporary))
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_uac_requests_are_refused_before_starting_anything(self) -> None:
        for command in ["Start-Process pwsh -Verb RunAs", "Start-Process pwsh -Verb:RunAs", "Start-Process pwsh -V RunAs", "saps pwsh -ver:RunAs", "runas /user:Administrator cmd", "$verb = 'RunAs'; Start-Process pwsh -Verb $verb"]:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temporary:
                result = self.run_runner(command, Path(temporary))
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertIn('BLOCKED_UAC', result.stderr)

    def test_quoted_elevation_word_is_not_a_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("Write-Output 'runas is a word here'", Path(temporary))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_required_admin_context_does_not_open_an_elevation_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("Write-Output ADMIN_CONTEXT_OK", Path(temporary), extra_args=['-RequireAdministrator'])
            self.assertIn(result.returncode, (0,77), result.stderr)
            if result.returncode == 77:
                self.assertNotIn('ADMIN_CONTEXT_OK', result.stdout)
                self.assertIn('BLOCKED_UAC', result.stderr)
            else:
                self.assertIn('ADMIN_CONTEXT_OK', result.stdout)

    def confirmation_fixture(self, base):
        script = base / 'gate.py'
        approval = base / 'approved'
        result = base / 'result'
        script.write_text('import pathlib,sys,time\na=pathlib.Path(sys.argv[1]);r=pathlib.Path(sys.argv[2])\nend=time.monotonic()+8\nwhile not a.exists() and time.monotonic()<end: time.sleep(.05)\nif a.exists(): r.write_text("approved")\nelse: raise SystemExit(1)\n', encoding='utf-8')
        quote = lambda x: "'" + str(x).replace("'", "''") + "'"
        command = '& ' + ' '.join(map(quote, (sys.executable, script, approval, result)))
        return command, approval, result

    def test_delayed_non_uac_confirmation_finishes_same_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            command, approval, output = self.confirmation_fixture(base)
            timer = threading.Timer(1.5, lambda: approval.write_text('yes'))
            timer.start()
            try:
                result = self.run_runner(command, base / 'logs', timeout=6)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(), 'approved')
            finally:
                timer.join()

    def test_late_confirmation_after_timeout_does_not_restart_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            command, approval, output = self.confirmation_fixture(base)
            result = self.run_runner(command, base / 'logs', timeout=1)
            self.assertEqual(result.returncode, 124, result.stderr)
            approval.write_text('too late')
            time.sleep(0.3)
            self.assertFalse(output.exists(), 'Timed-out confirmation process continued in the background')

    def test_large_output_goes_to_complete_logs_with_bounded_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner("[Console]::Write('x' * 200000)", Path(temporary))
            log = next(Path(temporary).glob('*.stdout.log'))
            self.assertEqual(log.stat().st_size, 200000)
            self.assertLess(len(result.stdout), 26000)
            self.assertFalse(list(Path(temporary).glob('*.command.ps1')))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_long_unicode_script_file_works_from_windows_powershell_51(self) -> None:
        ps51 = shutil.which('powershell.exe')
        if not ps51:
            self.skipTest('Windows PowerShell 5.1 unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / '한글 경로 with spaces'
            base.mkdir()
            script = base / '긴 스크립트.ps1'
            script.write_text('# long script\n' * 10000 + "Write-Output '한글 출력 성공'\n", encoding='utf-8')
            result = subprocess.run([ps51, '-NoProfile', '-NonInteractive', '-File', str(POWERSHELL_RUNNER), '-CommandFile', str(script), '-WorkingDirectory', str(base), '-LogDirectory', str(base / 'logs'), '-TimeoutSeconds', '10'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('한글 출력 성공', result.stdout)

    def test_timeout_kills_the_exact_command_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pid_file = base / "child.pid"
            encoded = base64.b64encode("Start-Sleep -Seconds 30".encode("utf-16le")).decode("ascii")
            escaped_pid_file = str(pid_file).replace("'", "''")
            command = (
                "$child = Start-Process -FilePath (Get-Command pwsh).Source "
                f"-ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand','{encoded}') -PassThru; "
                f"Set-Content -LiteralPath '{escaped_pid_file}' -Value $child.Id; "
                "Start-Sleep -Seconds 30"
            )
            started = time.monotonic()
            result = self.run_runner(command, base / "logs", timeout=1)
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn("PROCESS_TREE_TERMINATED=True", result.stderr)
            self.assertLess(elapsed, 20)
            self.assertTrue(pid_file.exists(), "child process did not start before timeout")
            child_pid = int(pid_file.read_text(encoding="utf-8").strip())
            check = subprocess.run(
                [
                    self.pwsh,
                    "-NoProfile",
                    "-Command",
                    f"if (Get-Process -Id {child_pid} -ErrorAction SilentlyContinue) {{ exit 1 }} else {{ exit 0 }}",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            self.assertEqual(check.returncode, 0, f"timed-out child {child_pid} remains alive")


class LinuxCommandRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if sys.platform != "linux":
            raise unittest.SkipTest("process-group and /proc fixtures require Linux")
        if not shutil.which("timeout"):
            raise unittest.SkipTest("GNU timeout is not installed")

    def run_runner(
        self,
        command: list[str],
        log_directory: Path,
        timeout_seconds: int = 10,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                str(BASH_RUNNER),
                "--timeout",
                str(timeout_seconds),
                "--heartbeat",
                "1",
                "--log-dir",
                str(log_directory),
                "--",
                *command,
            ],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )

    def test_success_preserves_output_and_zero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner(["bash", "-c", "printf RUNNER_OK"], Path(temporary))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RUNNER_OK", result.stdout)
        self.assertIn("EXIT_CODE=0", result.stdout)

    def test_nonzero_exit_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_runner(["bash", "-c", "exit 7"], Path(temporary))
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn("EXIT_CODE=7", result.stdout)

    def test_timeout_terminates_the_command_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pid_file = base / "child.pid"
            script = f"sleep 30 & echo $! > '{pid_file}'; wait"
            started = time.monotonic()
            result = self.run_runner(["bash", "-c", script], base / "logs", timeout_seconds=1)
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn("PROCESS_GROUP_TERMINATED=True", result.stderr)
            self.assertLess(elapsed, 20)
            self.assertTrue(pid_file.exists(), "child process did not start before timeout")
            child_pid = int(pid_file.read_text(encoding="utf-8").strip())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                proc_stat = Path(f"/proc/{child_pid}/stat")
                if not proc_stat.exists() or proc_stat.read_text(encoding="utf-8").split()[2] == "Z":
                    break
                time.sleep(0.1)
            else:
                self.fail(f"timed-out child {child_pid} remains alive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
