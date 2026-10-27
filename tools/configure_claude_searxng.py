"""Enable or disable the loopback SearXNG search endpoint in Claude MCP settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

if __package__:
    from .claude_mcp.searxng_search import normalize_base_url
else:
    from claude_mcp.searxng_search import normalize_base_url


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Claude 설정 파일을 찾을 수 없습니다: {path}") from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError(f"Claude 설정 파일을 읽을 수 없습니다: {path}") from None
    if not isinstance(value, dict):
        raise ValueError(f"Claude 설정 파일의 최상위 값이 객체가 아닙니다: {path}")
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


def configure(home: Path, *, enabled: bool, base_url: str = "http://127.0.0.1:8888") -> dict:
    settings_path = home / ".claude" / "settings.json"
    native_path = home / ".claude.json"
    settings = _read(settings_path)
    native = _read(native_path)
    servers = native.get("mcpServers")
    agent_tools = servers.get("agent-tools") if isinstance(servers, dict) else None
    args = agent_tools.get("args") if isinstance(agent_tools, dict) else None
    if (not isinstance(agent_tools, dict) or not isinstance(args, list)
            or not any(isinstance(arg, str) and arg.replace("\\", "/").lower().endswith("/lazy_dispatcher.py")
                       for arg in args)):
        raise ValueError("agent-tools MCP가 이 저장소의 lazy_dispatcher.py를 사용하지 않아 변경하지 않았습니다.")

    settings_env = settings.setdefault("env", {})
    mcp_env = agent_tools.setdefault("env", {})
    if not isinstance(settings_env, dict) or not isinstance(mcp_env, dict):
        raise ValueError("Claude env 설정이 객체가 아니어서 덮어쓰지 않았습니다.")
    if enabled:
        endpoint = normalize_base_url(base_url)
        settings_env["SEARXNG_URL"] = endpoint
        mcp_env["SEARXNG_URL"] = endpoint
    else:
        settings_env.pop("SEARXNG_URL", None)
        mcp_env.pop("SEARXNG_URL", None)
        if not mcp_env:
            agent_tools.pop("env", None)

    # Validate and serialize both documents before either write, so malformed config is never partly applied.
    settings_bytes = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    native_bytes = json.dumps(native, ensure_ascii=False, indent=2) + "\n"
    json.loads(settings_bytes)
    json.loads(native_bytes)
    _write(settings_path, settings)
    _write(native_path, native)
    return {"enabled": enabled, "url": base_url if enabled else None,
            "settings": str(settings_path), "mcp_config": str(native_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable"))
    parser.add_argument("--url", default="http://127.0.0.1:8888")
    args = parser.parse_args(argv)
    try:
        result = configure(Path.home(), enabled=args.action == "enable", base_url=args.url)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Claude SearXNG 설정: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
