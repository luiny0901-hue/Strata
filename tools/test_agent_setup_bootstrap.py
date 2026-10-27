"""Offline Strata server bootstrap checks; never launch a model or install packages."""
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


class LinuxBootstrapTests(unittest.TestCase):
    def bash_path(self, path):
        if os.name != "nt":
            return str(path)
        return subprocess.check_output([BASH, "-c", 'cygpath -u "$1"', "sh", str(path)], text=True).strip()

    def fake(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + content + "\n", encoding="utf-8", newline="\n")
        path.chmod(0o755)

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
            self.fake(selected, 'printf "%s\n" "$@" >> "$BOOT_LOG"; exit 0')
            result = subprocess.run([BASH, "-c", 'PATH="$1:$PATH"; export PATH; exec sh "$2" --python "$3" --mode off',
                                     "sh", self.bash_path(fakebin), self.bash_path(repo / "tools/bootstrap-linux-server.sh"), self.bash_path(selected)],
                                    env={**os.environ, "BOOT_LOG": self.bash_path(home / "calls")}, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (home / "calls").read_text()
            self.assertIn("pip\ninstall\n-r", calls)
            self.assertIn("prepare\n--python", calls)
            self.assertFalse((repo / ".venv").exists())

    @unittest.skipUnless(BASH and Path(BASH).is_file(), "Bash not installed")
    def test_active_shell_launchers_parse(self):
        for relative in ("SETUP-LINUX-SERVER.sh", "tools/bootstrap-linux-server.sh",
                         "run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh",
                         "run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.sh",
                         "run-claude-opencodex.sh", "setup-claude-opencodex.sh"):
            with self.subTest(path=relative):
                result = subprocess.run([BASH, "-n", str(ROOT / relative)], capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
