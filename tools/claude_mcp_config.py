"""Validate the Claude-owned source for the local MCP dispatcher (CUA/REA plus toolset servers)."""
from __future__ import annotations

import json
import re
from pathlib import Path


MANAGED_SERVER_NAMES = ("cua-driver", "rea", "strata-maintenance")
TOOLSET_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def normalize_toolsets(raw_toolsets: object) -> dict:
    """Validate the optional toolsetServers block the dispatcher serves on demand."""
    if raw_toolsets is None:
        return {}
    if not isinstance(raw_toolsets, dict):
        raise ValueError("toolsetServers는 이름에서 서버 설정을 찾는 객체여야 합니다.")
    toolsets = {}
    for name, row in raw_toolsets.items():
        if (not isinstance(name, str) or not TOOLSET_NAME.match(name)
                or name in MANAGED_SERVER_NAMES or name == "agent-tools"):
            raise ValueError(f"toolset 서버 이름으로 올바르지 않습니다: {name!r}")
        if not isinstance(row, dict) or row.get("type") != "stdio":
            raise ValueError(f"toolset {name}은 stdio MCP 서버여야 합니다.")
        command, args, env, summary = row.get("command"), row.get("args", []), row.get("env", {}), row.get("summary")
        if (not isinstance(command, str) or not command.strip()
                or not isinstance(args, list) or not all(isinstance(item, str) for item in args)
                or not isinstance(env, dict)
                or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items())
                or not isinstance(summary, str) or not 1 <= len(summary) <= 120):
            raise ValueError(f"toolset {name}의 실행 명령·환경·summary 형식이 올바르지 않습니다.")
        entry = {"type": "stdio", "command": command, "args": list(args), "summary": summary}
        if env:
            entry["env"] = dict(env)
        toolsets[name] = entry
    return toolsets


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
    normalized = {"mcpServers": output}
    if "toolsetServers" in document:
        normalized["toolsetServers"] = normalize_toolsets(document["toolsetServers"])
    return normalized


def read(path: Path, *, require_gui_or_rea: bool = True) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Claude 전용 MCP 설정을 읽을 수 없습니다: {type(exc).__name__}") from None
    return normalize(document, require_gui_or_rea=require_gui_or_rea)
