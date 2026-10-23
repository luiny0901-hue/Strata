"""Opt existing OpenCode ACP entries into thought-only display filtering."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from configure_opencode_session_recovery import _atomic_write, _backup


def install(acp):
    source = Path(__file__).parent / "opencode/acp_compact_display.py"
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    dest = Path.home() / ".config/opencode/strata-acp-display" / digest / source.name
    settings = json.loads(acp.read_text(encoding="utf-8-sig"))
    names = []
    for name, entry in settings.get("agent_servers", {}).items():
        if not isinstance(entry, dict):
            continue
        command = entry.get("command", "")
        args = entry.get("args", [])
        if not isinstance(command, str) or not isinstance(args, list):
            continue
        executable = command.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if args and str(args[0]).replace("\\", "/").endswith("/acp_compact_display.py"):
            # Upgrade an existing wrapper without wrapping it a second time.
            if len(args) < 4 or args[1] != "--":
                raise ValueError("Unexpected compact-display launcher arguments")
            original = args[2:]
        elif executable in ("opencode", "opencode.exe") and "acp" in args:
            original = [command, *args]
        else:
            continue
        entry["command"] = sys.executable
        entry["args"] = [str(dest), "--", *original]
        names.append(name)
    if not names:
        raise ValueError("No existing direct OpenCode ACP entries found")
    if dest.exists() and dest.read_bytes() != data:
        raise ValueError("Installed display asset differs from its content hash")
    if not dest.exists():
        _atomic_write(dest, data.decode("utf-8"))
    text = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    if acp.read_text(encoding="utf-8-sig") != text:
        _backup(acp)
        _atomic_write(acp, text)
    print("Compact thought display installed for: " + ", ".join(names))
    print("Reconnect the Rider ACP agent after its current task finishes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acp", type=Path, default=Path.home() / ".jetbrains/acp.json")
    install(parser.parse_args().acp)
