"""Configure Exa/Tavily keys only in this user's Claude agent-tools MCP entry."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import tempfile


KEY_NAMES = ("EXA_API_KEY", "TAVILY_API_KEY")


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Claude 설정 파일을 찾을 수 없습니다: {path}") from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError(f"Claude 설정 파일을 읽을 수 없습니다: {path}") from None
    if not isinstance(value, dict):
        raise ValueError("Claude 설정의 최상위 값은 객체여야 합니다.")
    return value


def _write(path: Path, value: dict) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _is_owned_dispatcher(server: object) -> bool:
    if not isinstance(server, dict):
        return False
    args = server.get("args")
    return isinstance(args, list) and any(
        isinstance(arg, str) and arg.replace("\\", "/").lower().endswith("/lazy_dispatcher.py")
        for arg in args
    )


def configure(home: Path, *, exa_api_key: str | None = None,
              tavily_api_key: str | None = None, clear: bool = False) -> dict:
    path = home / ".claude.json"
    document = _read(path)
    servers = document.get("mcpServers")
    server = servers.get("agent-tools") if isinstance(servers, dict) else None
    if not _is_owned_dispatcher(server):
        raise ValueError("agent-tools MCP가 이 저장소의 lazy_dispatcher.py를 쓰지 않아 변경하지 않았습니다.")
    env = server.setdefault("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ValueError("agent-tools MCP 환경 설정이 올바르지 않아 변경하지 않았습니다.")
    if clear:
        for name in KEY_NAMES:
            env.pop(name, None)
    else:
        for name, candidate in (("EXA_API_KEY", exa_api_key), ("TAVILY_API_KEY", tavily_api_key)):
            if candidate is not None and candidate.strip():
                env[name] = candidate.strip()
    if not env:
        server.pop("env", None)
    _write(path, document)
    return {"settings": str(path), "exa_configured": bool(env.get("EXA_API_KEY")),
            "tavily_configured": bool(env.get("TAVILY_API_KEY")), "cleared": clear}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "clear"))
    args = parser.parse_args(argv)
    try:
        if args.action == "clear":
            result = configure(Path.home(), clear=True)
        else:
            exa = getpass.getpass("Exa API key (빈 입력은 기존 설정 유지): ")
            tavily = getpass.getpass("Tavily API key (빈 입력은 기존 설정 유지): ")
            result = configure(Path.home(), exa_api_key=exa, tavily_api_key=tavily)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"검색 키 설정: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    print("키는 화면에 출력하지 않았습니다. 사용자 .claude.json에 저장되므로 이 파일을 공유하거나 저장소에 올리지 마세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
