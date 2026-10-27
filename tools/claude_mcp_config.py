"""Validate the Claude-owned source for the local CUA/REA dispatcher."""
from __future__ import annotations

import json
from pathlib import Path


MANAGED_SERVER_NAMES = ("cua-driver", "rea", "strata-maintenance")


def normalize(document: object, *, require_gui_or_rea: bool = True) -> dict:
    """Return only validated Claude stdio server entries owned by this integration."""
    if not isinstance(document, dict) or not isinstance(document.get("mcpServers"), dict):
        raise ValueError("Claude MCP 설정에는 mcpServers 객체가 필요합니다.")
    output = {}
    for name in MANAGED_SERVER_NAMES:
        row = document["mcpServers"].get(name)
        if row is None:
            continue
        if not isinstance(row, dict) or row.get("type") != "stdio":
            raise ValueError(f"{name}은 stdio MCP 서버여야 합니다.")
        command, args, env = row.get("command"), row.get("args", []), row.get("env", {})
        if (not isinstance(command, str) or not command.strip()
                or not isinstance(args, list) or not all(isinstance(item, str) for item in args)
                or not isinstance(env, dict)
                or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items())):
            raise ValueError(f"{name} MCP 실행 명령 또는 환경 설정 형식이 올바르지 않습니다.")
        normalized = {"type": "stdio", "command": command, "args": list(args)}
        if env:
            normalized["env"] = dict(env)
        output[name] = normalized
    if require_gui_or_rea and not ({"cua-driver", "rea"} & output.keys()):
        raise ValueError("Claude MCP 설정에 활성 CUA 또는 REA 서버가 없습니다.")
    return {"mcpServers": output}


def read(path: Path, *, require_gui_or_rea: bool = True) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Claude 전용 MCP 설정을 읽을 수 없습니다: {type(exc).__name__}") from None
    return normalize(document, require_gui_or_rea=require_gui_or_rea)
