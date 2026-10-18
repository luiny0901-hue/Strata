#!/usr/bin/env python3
"""Install bounded OpenCode session recovery defaults without replacing user settings."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode" / "opencode.json"
DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "docs" / "OPENCODE_SESSION_RECOVERY_KO.md"
INSTALLED_INSTRUCTIONS_NAME = "STRATA_SESSION_RECOVERY_KO.md"


def _mapping(parent: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = parent.get(key)
    if value is None:
        value = {}
        parent[key] = value
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object; no files were changed.")
    return value


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.before-session-recovery-{stamp}.bak")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.before-session-recovery-{stamp}-{suffix}.bak")
        suffix += 1
    shutil.copy2(path, candidate)
    return candidate


def _atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _reference_for(target: Path) -> str:
    resolved = target.resolve()
    try:
        relative = resolved.relative_to(Path.home().resolve())
    except ValueError:
        return str(resolved)
    return "~/" + relative.as_posix()


def apply_config(
    config_path: Path,
    source_instructions: Path = DEFAULT_SOURCE,
    instructions_dir: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path.expanduser()
    source_instructions = source_instructions.expanduser()
    if not source_instructions.is_file():
        raise ValueError(f"Instruction source was not found: {source_instructions}")

    try:
        source_text = source_instructions.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Could not read the instruction source: {error}") from error
    if not source_text.strip():
        raise ValueError("Instruction source is empty; no files were changed.")

    existed = config_path.exists()
    if existed:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"OpenCode config is unreadable JSON; no files were changed: {error}") from error
        if not isinstance(config, dict):
            raise ValueError("OpenCode config root must be a JSON object; no files were changed.")
    else:
        config = {}

    updated = copy.deepcopy(config)
    compaction = _mapping(updated, "compaction", "compaction")
    keep = _mapping(compaction, "keep", "compaction.keep")
    agents = _mapping(updated, "agents", "agents")
    build = _mapping(agents, "build", "agents.build")
    instructions = updated.get("instructions", [])
    if isinstance(instructions, str):
        instructions = [instructions]
    if not isinstance(instructions, list) or any(not isinstance(item, str) for item in instructions):
        raise ValueError("instructions must be a string or an array of strings; no files were changed.")

    install_dir = instructions_dir.expanduser() if instructions_dir else config_path.parent
    target = install_dir / INSTALLED_INSTRUCTIONS_NAME
    reference = _reference_for(target)
    if reference not in instructions:
        instructions.append(reference)

    compaction["auto"] = True
    keep["tokens"] = 12000
    compaction["buffer"] = 65536
    build["steps"] = 60
    updated["instructions"] = instructions

    config_changed = updated != config
    instruction_exists = target.exists()
    if instruction_exists:
        try:
            instruction_changed = target.read_text(encoding="utf-8") != source_text.rstrip() + "\n"
        except (OSError, UnicodeError) as error:
            raise ValueError(f"Installed instruction file cannot be read; no files were changed: {error}") from error
    else:
        instruction_changed = True

    config_backup = _backup(config_path) if config_changed and existed else None
    instruction_backup = _backup(target) if instruction_changed and instruction_exists else None

    if instruction_changed:
        mode = stat.S_IMODE(target.stat().st_mode) if instruction_exists else None
        _atomic_write(target, source_text.rstrip() + "\n", mode)
    if config_changed:
        mode = stat.S_IMODE(config_path.stat().st_mode) if existed else None
        serialized = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        _atomic_write(config_path, serialized, mode)

    return {
        "config_path": str(config_path.resolve()),
        "instructions_path": str(target.resolve()),
        "config_changed": config_changed,
        "instructions_changed": instruction_changed,
        "config_backup": str(config_backup) if config_backup else None,
        "instructions_backup": str(instruction_backup) if instruction_backup else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="OpenCode config path")
    parser.add_argument("--instructions-dir", type=Path, help="directory for the installed instruction file")
    parser.add_argument("--source-instructions", type=Path, default=DEFAULT_SOURCE, help="source Korean instructions")
    args = parser.parse_args()
    try:
        result = apply_config(args.config, args.source_instructions, args.instructions_dir)
    except ValueError as error:
        parser.error(str(error))
    print(f"Config: {result['config_path']}")
    print(f"Instructions: {result['instructions_path']}")
    print(f"Config changed: {result['config_changed']}")
    print(f"Instructions changed: {result['instructions_changed']}")
    if result["config_backup"]:
        print(f"Config backup: {result['config_backup']}")
    if result["instructions_backup"]:
        print(f"Instructions backup: {result['instructions_backup']}")
    print("Restart OpenCode before relying on the new global settings in an existing client.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
