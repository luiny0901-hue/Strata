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

    def run_runner(self, command: str, log_directory: Path, timeout: int = 10) -> subprocess.CompletedProcess[str]:
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
