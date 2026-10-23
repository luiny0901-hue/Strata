"""Offline bootstrap checks; never execute package managers, installers or engines."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import linux_nvfp4_server as linux
from tools.remote_agent_client import setup_client as client

ROOT = Path(__file__).resolve().parents[1]
BASH = (r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash"))


class LinuxProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="strata offline ")
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *args):
        with patch.object(linux.sys, "platform", "linux"), \
             patch.object(linux.os, "getuid", return_value=0 if os.name == "nt" else os.getuid(), create=True), \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.home)}), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return linux.main(list(args))

    def test_prepare_both_modes_preserves_key_and_literal_paths(self):
        data = self.home / "data with spaces"
        for mode in ("on", "off"):
            self.assertEqual(self.call("prepare", "--mode", mode, "--data-root", str(data), "--gpu", "2"), 0)
            key = (self.home / "strata/STRATA_API_KEY").read_bytes()
            if mode == "on":
                original = key
            self.assertEqual(key, original)
            profile = json.loads((self.home / f"strata/profiles/{linux.PROFILE_STEM}-{mode}-linux.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["uncensored"], mode == "on")
            self.assertEqual(profile["gpu"], 2)
            self.assertEqual(profile["vision"]["max_tokens"], 1024)
            self.assertFalse(profile["vision"]["gpu"])
            self.assertEqual(profile["args"][profile["args"].index("--pack") + 1], str(data / "packs/unsloth-ud-iq4_xs"))
            self.assertEqual(Path(profile["exe"]).name, "strata")

    def test_malformed_key_is_not_replaced(self):
        path = self.home / "strata/STRATA_API_KEY"
        path.parent.mkdir()
        path.write_text("invalid", encoding="utf-8")
        with self.assertRaises(SystemExit) as error:
            self.call("prepare")
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(path.read_text(), "invalid")

    def test_key_directory_is_rejected_without_reading(self):
        (self.home / "strata/STRATA_API_KEY").mkdir(parents=True)
        with self.assertRaises(SystemExit):
            self.call("prepare")

    def test_missing_artifacts_never_start_server(self):
        with patch.object(linux.os, "execve", side_effect=AssertionError("No server allowed")) as launch:
            with self.assertRaises(SystemExit):
                self.call("run", "--data-root", str(self.home / "absent"))
            launch.assert_not_called()

    def test_invalid_gpu_creates_nothing(self):
        with self.assertRaises(SystemExit):
            self.call("prepare", "--gpu", "-1")
        self.assertEqual(list(self.home.iterdir()), [])


class BootstrapSyntaxTests(unittest.TestCase):
    def bash_path(self, path):
        if os.name != "nt":
            return str(path)
        return subprocess.check_output([BASH, "-c", 'cygpath -u "$1"', "sh", str(path)], text=True).strip()

    def fake(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + content + "\n", encoding="utf-8", newline="\n")
        path.chmod(0o755)

    @unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash not installed")
    def test_macos_run_never_bootstraps_and_preserves_exit(self):
        with tempfile.TemporaryDirectory(prefix="bootstrap offline ") as temporary:
            home = Path(temporary)
            fakebin = home / "fakebin"
            self.fake(fakebin / "python3", 'printf "%s\\n" "$@" >> "$BOOT_LOG"; exit 9')
            for name in ("brew", "npm", "curl"):
                self.fake(fakebin / name, 'echo INSTALLER_CALLED >> "$BOOT_LOG"; exit 99')
            result = subprocess.run([BASH, "-c", 'PATH="$1:$PATH"; export PATH; exec sh "$2" run -- --version',
                                     "sh", self.bash_path(fakebin), self.bash_path(ROOT / "tools/remote_agent_client/setup-macos.sh")],
                                    env={**os.environ, "HOME": self.bash_path(home), "BOOT_LOG": self.bash_path(home / "calls")},
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 9, result.stderr)
            calls = (home / "calls").read_text()
            self.assertNotIn("INSTALLER_CALLED", calls)
            self.assertIn("--version", calls)

    @unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash not installed")
    def test_linux_custom_python_receives_dependency_install(self):
        with tempfile.TemporaryDirectory(prefix="bootstrap offline ") as temporary:
            home = Path(temporary)
            repo = home / "repo"
            (repo / "tools").mkdir(parents=True)
            shutil.copyfile(ROOT / "tools/bootstrap-linux-server.sh", repo / "tools/bootstrap-linux-server.sh")
            fakebin = home / "fakebin"
            self.fake(fakebin / "uname", "echo Linux")
            self.fake(fakebin / "python3", "exit 0")
            selected = home / "custom environment/python"
            self.fake(selected, 'printf "%s\\n" "$@" >> "$BOOT_LOG"; exit 0')
            result = subprocess.run([BASH, "-c", 'PATH="$1:$PATH"; export PATH; exec sh "$2" --python "$3" --mode off',
                                     "sh", self.bash_path(fakebin), self.bash_path(repo / "tools/bootstrap-linux-server.sh"), self.bash_path(selected)],
                                    env={**os.environ, "BOOT_LOG": self.bash_path(home / "calls")}, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (home / "calls").read_text()
            self.assertIn("pip\ninstall\n-r", calls)
            self.assertIn("prepare\n--python", calls)
            self.assertFalse((repo / ".venv").exists())

    @unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash not installed")
    def test_macos_existing_prerequisites_are_reused(self):
        with tempfile.TemporaryDirectory(prefix="bootstrap offline ") as temporary:
            home = Path(temporary)
            fakebin = home / "fakebin"
            self.fake(fakebin / "uname", 'case "$1" in -s) echo Darwin;; -m) echo arm64;; esac')
            self.fake(fakebin / "brew", 'if [ "$1" = shellenv ]; then exit 0; fi; echo INSTALLER_CALLED >> "$BOOT_LOG"; exit 99')
            self.fake(fakebin / "python3", 'if [ "$1" = -c ]; then exit 0; fi; printf "%s\\n" "$@" >> "$BOOT_LOG"; exit 0')
            for name in ("node", "gtimeout", "opencode"):
                self.fake(fakebin / name, "exit 0")
            for name in ("npm", "curl"):
                self.fake(fakebin / name, 'echo INSTALLER_CALLED >> "$BOOT_LOG"; exit 99')
            result = subprocess.run([BASH, "-c", 'PATH="$1:$PATH"; export PATH; exec sh "$2" setup',
                                     "sh", self.bash_path(fakebin), self.bash_path(ROOT / "tools/remote_agent_client/setup-macos.sh")],
                                    env={**os.environ, "HOME": self.bash_path(home), "BOOT_LOG": self.bash_path(home / "calls")},
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (home / "calls").read_text()
            self.assertIn("setup", calls)
            self.assertNotIn("INSTALLER_CALLED", calls)

    @unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash not installed")
    def test_each_shell_file_parses_separately(self):
        # bash -n with multiple filenames only parses the first file.
        for name in ("START-AGENT.command", "setup-opencode.sh", "SETUP-LINUX-SERVER.sh",
                     "tools/bootstrap-linux-server.sh", "tools/remote_agent_client/setup-macos.sh",
                     "run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh",
                     "run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.sh"):
            with self.subTest(name=name):
                result = subprocess.run([BASH, "-n", str(ROOT / name)], capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_menu_can_exit_without_installing(self):
        script = ROOT / "tools/remote_agent_client/bootstrap-windows.ps1"
        # Menu zero runs no setup commands and changes no operational settings.
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(script)], input=b"0\n",
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_parser_and_utf8_bom(self):
        script = ROOT / "tools/remote_agent_client/bootstrap-windows.ps1"
        self.assertTrue(script.read_bytes().startswith(b"\xef\xbb\xbf"))
        command = "$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile($env:STRATA_PARSE_FILE,[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e|Out-String|Write-Error;exit 1}"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                env={**os.environ, "STRATA_PARSE_FILE": str(script)}, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_run_without_setup_is_bounded_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(ROOT / "tools/remote_agent_client/bootstrap-windows.ps1"),
                                     "run", "--home", temporary], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(b"setup", result.stdout + result.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_macos_rider_wrapper_has_local_runtime_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch.object(client.os, "name", "posix"):
                wrapper, _, _, content, _ = client.build_launcher(home, home / "opencode")
            self.assertIn(b"/opt/homebrew/opt/node@24/bin", content)
            self.assertIn(b"$HOME/.local/bin", content)
            self.assertEqual(wrapper.name, "opencode-strata")


if __name__ == "__main__":
    unittest.main()
