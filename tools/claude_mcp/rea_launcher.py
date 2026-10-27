"""Pinned REA MCP launcher for the Claude MCP configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE = "rea-agents@6.7.0"

def cached_entry(roots):
    for root in roots:
        if not root.is_dir():
            continue
        try:
            directories = sorted(root.iterdir())
        except OSError:
            continue
        for directory in directories:
            package = directory / "node_modules/rea-agents"
            try:
                info = json.loads((package / "package.json").read_text(encoding="utf-8"))
                entry = package / "scripts/rea.mjs"
                if info.get("name") == "rea-agents" and info.get("version") == "6.7.0" and entry.is_file():
                    return entry
            except (OSError, ValueError):
                continue
    return None

def launch_command(roots, node, npx, windows=False):
    entry = cached_entry(roots)
    if entry and node:
        return [node, str(entry), "mcp"]
    if not npx:
        raise RuntimeError("REA cache missing and npx is unavailable; run client setup")
    args = [npx, "-y", PACKAGE, "mcp"]
    return ["cmd.exe", "/d", "/c", *args] if windows else args

def main():
    if sys.argv[1:] != [PACKAGE, "mcp"]:
        raise SystemExit("Only the pinned REA MCP command is supported")
    home = Path.home()
    roots = []
    if os.environ.get("npm_config_cache"):
        roots.append(Path(os.environ["npm_config_cache"]) / "_npx")
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "npm-cache/_npx")
    roots.extend([home / "AppData/Local/npm-cache/_npx", home / ".npm/_npx"])
    command = launch_command(roots, shutil.which("node"), shutil.which("npx"), os.name == "nt")
    child = subprocess.Popen(command)
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        return child.wait(timeout=5)

if __name__ == "__main__":
    raise SystemExit(main())
