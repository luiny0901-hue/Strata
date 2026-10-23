#!/usr/bin/env python3
"""Create a non-overwriting Unreal or Unity AGENTS.md at a project root."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "unreal": ROOT / "examples" / "opencode" / "game-engines" / "UNREAL_ENGINE_AGENTS.md",
    "unity": ROOT / "examples" / "opencode" / "game-engines" / "UNITY_AGENTS.md",
}


def install_guidance(project: Path, engine: str) -> Path:
    """Copy one engine template to a new project-root AGENTS.md without overwriting."""
    if engine not in TEMPLATES:
        raise ValueError(f"Unsupported engine: {engine}")
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    template = TEMPLATES[engine]
    if not template.is_file():
        raise ValueError(f"Engine template is missing: {template}")
    destination = project / "AGENTS.md"
    content = template.read_bytes()
    try:
        # Exclusive creation also protects a file created by another process
        # between our initial project inspection and this write.
        with destination.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        raise FileExistsError(
            f"Refusing to overwrite existing project guidance: {destination}. "
            "Merge the relevant template manually."
        ) from None
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, choices=sorted(TEMPLATES), help="game engine template")
    parser.add_argument("--project", required=True, type=Path, help="existing project root")
    args = parser.parse_args()
    try:
        destination = install_guidance(args.project, args.engine)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Created {destination}")
    print("Review engine version and project-specific commands, then commit AGENTS.md with the game project.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
