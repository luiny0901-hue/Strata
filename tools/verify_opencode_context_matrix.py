#!/usr/bin/env python3
"""Run the isolated OpenCode compaction workflow at representative context lengths.

This is a CPU/loopback integration verifier. It never contacts Strata or starts
an inference server. Each context receives a fresh OpenCode CLI process, fake
OpenAI-compatible provider, session, initial file edit, and follow-up edit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

CONTEXTS = (8_192, 32_768, 65_536, 131_072, 262_144)
WORKFLOW = Path(__file__).with_name("verify_opencode_262k_workflow.py")


def receipt_from(output: str) -> dict[str, Any]:
    """Read the final JSON receipt without accepting unrelated OpenCode output."""
    for line in reversed(output.splitlines()):
        try:
            receipt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(receipt, dict) and "result" in receipt:
            return receipt
    raise ValueError("workflow verifier did not produce a JSON receipt")


def verify_receipt(receipt: dict[str, Any], context: int) -> dict[str, Any]:
    if receipt.get("result") != "PASS":
        raise ValueError(f"context {context}: workflow result was {receipt.get('result')!r}")
    compaction = receipt.get("compaction")
    if not isinstance(compaction, dict):
        raise ValueError(f"context {context}: receipt did not contain compaction settings")
    expected = {"keep": min(12_000, context // 8), "buffer": min(65_536, context // 4)}
    expected["trigger"] = context - expected["buffer"]
    if receipt.get("model_context") != context or any(compaction.get(key) != value for key, value in expected.items()):
        raise ValueError(f"context {context}: receipt policy did not match {expected!r}: {receipt!r}")
    if receipt.get("compacted_checkpoint_requests", 0) < 1:
        raise ValueError(f"context {context}: no conversation checkpoint was observed")
    if receipt.get("workflow_file") != "revised by follow-up\n":
        raise ValueError(f"context {context}: follow-up edit did not complete")
    return {
        "context": context,
        "keep": expected["keep"],
        "buffer": expected["buffer"],
        "trigger": expected["trigger"],
        "requests": receipt.get("model_requests"),
        "checkpoints": receipt.get("compacted_checkpoint_requests"),
    }


def main() -> int:
    results: list[dict[str, Any]] = []
    for context in CONTEXTS:
        completed = subprocess.run(
            [sys.executable, str(WORKFLOW), "--context", str(context)],
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2_000:]
            print(f"FAILED: context {context} workflow exited {completed.returncode}: {detail}", file=sys.stderr)
            return completed.returncode or 1
        try:
            results.append(verify_receipt(receipt_from(completed.stdout), context))
        except ValueError as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
    print(json.dumps({"result": "PASS", "contexts": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
