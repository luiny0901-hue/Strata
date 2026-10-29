"""Apply the maintained Anthropic effort-budget hook to the downloaded NVFP4 server copy.

The fork checkout is intentionally git-ignored. Keep the behavior in tools/strata_anthropic_effort.py and this
small, version-tolerant integration patch in the tracked Strata checkout. Launchers fail closed if the upstream
source no longer matches the known integration points.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys


MARKER = "# STRATA_ANTHROPIC_EFFORT_BUDGETS_PATCH_V1"
IMPORT = (
    "from strata_anthropic_effort import (clean_anthropic_effort_budgets, "
    "request_with_anthropic_effort_budget)  # STRATA_ANTHROPIC_EFFORT_BUDGETS_PATCH_V1"
)
ATTR = "        self.anthropic_effort_budgets: dict[str, int] = {}  # STRATA_ANTHROPIC_EFFORT_BUDGETS_PATCH_V1"
METHODS = '''    def set_anthropic_effort_budgets(self, value) -> None:
        """Load the optional native Anthropic effort-to-budget map from the run config."""
        self.anthropic_effort_budgets = clean_anthropic_effort_budgets(value)

    def budget_anthropic_request(self, req: dict, *, codex_budget_labels: bool = False) -> dict:
        """Add the configured cap for a selected Anthropic effort without changing explicit request controls."""
        return request_with_anthropic_effort_budget(req, self.anthropic_effort_budgets, codex_budget_labels=codex_budget_labels)

'''
CODEX_WIRE_ARGUMENT = ', codex_budget_labels=self.headers.get("x-strata-effort-wire") == "opencodex-low-medium-high-v1"'
REQUEST = "            req = svc.budget_anthropic_request(req" + CODEX_WIRE_ARGUMENT + ")  # STRATA_ANTHROPIC_EFFORT_BUDGETS_PATCH_V1"
LEGACY_REQUEST = REQUEST.replace(CODEX_WIRE_ARGUMENT, "")
LEGACY_METHODS = METHODS.replace(", *, codex_budget_labels: bool = False", "").replace(", codex_budget_labels=codex_budget_labels", "")
CONFIG = '''    try:
        svc.set_anthropic_effort_budgets(cfg.get("anthropic_effort_budgets"))
    except ValueError as e:
        raise SystemExit(f"[strata] config {e}")
    if svc.anthropic_effort_budgets:
        budgets = ", ".join(f"{level}={tokens}" for level, tokens in svc.anthropic_effort_budgets.items())
        print(f"[strata] Anthropic reasoning budgets: {budgets} tokens", flush=True)  # STRATA_ANTHROPIC_EFFORT_BUDGETS_PATCH_V1
'''


class PatchError(ValueError):
    pass


def patch_source(source: str) -> tuple[str, bool]:
    """Return patched source and whether it changed. Never partially patch unknown source."""
    if MARKER in source:
        required = (IMPORT, ATTR, "def set_anthropic_effort_budgets(",
                    'svc.set_anthropic_effort_budgets(cfg.get("anthropic_effort_budgets"))')
        if not all(item in source for item in required):
            raise PatchError("the NVFP4 server contains a partial effort-budget patch; inspect it before editing")
        if METHODS in source and REQUEST in source:
            return source, False
        if source.count(LEGACY_METHODS) == 1 and source.count(LEGACY_REQUEST) == 1:
            return source.replace(LEGACY_METHODS, METHODS, 1).replace(LEGACY_REQUEST, REQUEST, 1), True
        raise PatchError("unknown or partial Codex effort-wire integration; inspect it before editing")

    changes = (
        ("from serve.responses import ResponsesError, error_body as responses_error_body  # noqa: E402",
         "from serve.responses import ResponsesError, error_body as responses_error_body  # noqa: E402\n" + IMPORT),
        ("        self.reasoning_budget_tokens = 0                 # #123: the config's default thinking budget (0: none)",
         "        self.reasoning_budget_tokens = 0                 # #123: the config's default thinking budget (0: none)\n" + ATTR),
        ("    def _vision_down(self) -> bool:", METHODS + "    def _vision_down(self) -> bool:"),
        ("        def _anthropic(self, req):\n"
         "            svc.load()\n"
         "            req = svc.with_shared(req, \"anthropic\")",
         "        def _anthropic(self, req):\n"
         "            svc.load()\n"
         "            req = svc.with_shared(req, \"anthropic\")\n" + REQUEST),
        ('    recovery = cfg.get("reasoning_loop_recovery", False)',
         CONFIG + '    recovery = cfg.get("reasoning_loop_recovery", False)'),
    )
    counts = [source.count(old) for old, _ in changes]
    if counts != [1] * len(changes):
        raise PatchError(f"unsupported NVFP4 server layout: expected one of each integration anchor, found {counts}")
    patched = source
    for old, new in changes:
        patched = patched.replace(old, new, 1)
    if patched.count(MARKER) != 4:
        raise PatchError("internal patch marker check failed")
    return patched, True


def apply_patch(server_path: Path) -> bool:
    server_path = server_path.expanduser().resolve()
    original = server_path.read_bytes()
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    body = original[len(bom):].decode("utf-8")
    newline = "\r\n" if "\r\n" in body else "\n"
    normalized = body.replace("\r\n", "\n")
    patched, changed = patch_source(normalized)
    if not changed:
        return False
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = server_path.with_name(f"{server_path.name}.before-effort-budgets-{stamp}.bak")
    if backup.exists():
        raise PatchError(f"refusing to overwrite an existing backup: {backup.name}")
    shutil.copy2(server_path, backup)
    encoded = bom + patched.replace("\n", newline).encode("utf-8")
    temporary = server_path.with_suffix(server_path.suffix + ".tmp")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, server_path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", type=Path, help="NVFP4 fork serve/server.py")
    args = parser.parse_args(argv)
    try:
        changed = apply_patch(args.server)
    except (OSError, UnicodeError, PatchError) as exc:
        print(f"[strata] cannot prepare Anthropic effort budgets: {exc}", file=sys.stderr)
        return 2
    print("[strata] NVFP4 Anthropic effort-budget integration " + ("installed" if changed else "already installed"),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
