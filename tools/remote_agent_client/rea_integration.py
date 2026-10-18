"""Install and inspect the official REA OpenCode integration.

REA owns its MCP registration and workflow instructions. This module only
invokes its documented setup command; it never writes REA configuration files
itself or installs a native analysis provider.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass


REA_VERSION = "6.7.0"
REA_PACKAGE = f"rea-agents@{REA_VERSION}"
REA_CLIENT = "opencode"
REA_TOOL_GLOB = "rea_*"
REA_AGENT_NAME = "rea_analysis"
LEGACY_REA_AGENT = {
    "description": "Use REA to inspect authorized binaries, applications, or artifacts and return evidence.",
    "mode": "subagent",
    "tools": {REA_TOOL_GLOB: True},
}
REA_AGENT = {
    "description": (
        "Automatically select this subagent when the user asks to analyze, inspect, "
        "reverse engineer, compare, or investigate an authorized local executable, DLL, "
        "installer, APK, Electron/JavaScript application, ASAR, or other binary artifact. "
        "Use REA read-only and report evidence in Korean."
    ),
    "mode": "subagent",
    "tools": {REA_TOOL_GLOB: True},
    "prompt": (
        "Use REA only for artifacts the user is authorized to inspect. Never modify, execute, "
        "launch, install, upload, or delete the target. Select the narrowest suitable REA "
        "analysis route, distinguish evidence from inference, and report findings in Korean."
    ),
}


class ReaSetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReaSetupResult:
    command: tuple[str, ...]
    output: str


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def supported_node_version(value: str) -> bool:
    """Return whether REA's published Node version policy accepts *value*."""
    version = _version_tuple(value)
    if version is None:
        return False
    major, minor, _ = version
    return (major == 22 and minor >= 19) or (major == 24 and minor >= 11) or major >= 26


def rea_setup_command(npx: str) -> list[str]:
    return [npx, "-y", REA_PACKAGE, "setup", "--yes", "--client", REA_CLIENT]


def rea_doctor_command(npx: str) -> list[str]:
    return [npx, "-y", REA_PACKAGE, "doctor", "--client", REA_CLIENT, "--skill", "--format", "json"]


def _node_version(node: str) -> str:
    try:
        result = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReaSetupError(f"REA용 Node.js 버전을 확인하지 못했습니다: {exc}") from None
    value = (result.stdout or result.stderr).strip().splitlines()
    if result.returncode != 0 or not value or not supported_node_version(value[0]):
        received = value[0] if value else "확인 불가"
        raise ReaSetupError(
            "REA는 Node.js 22.19+, 24.11+ 또는 26+를 요구합니다. "
            f"현재 확인값: {received}"
        )
    return value[0]


def _require_runtime() -> tuple[str, str, str]:
    node = shutil.which("node")
    npx = shutil.which("npx")
    if not node or not npx:
        raise ReaSetupError("REA에는 PATH에서 찾을 수 있는 Node.js와 npx가 필요합니다.")
    return node, npx, _node_version(node)


def opencode_config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".config" / "opencode" / "opencode.json"


def apply_tool_scope(config_path: Path) -> bool:
    """Keep REA tools out of ordinary coding turns but enable a named subagent."""
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReaSetupError(f"REA 등록 뒤 OpenCode 설정을 읽지 못했습니다: {exc}") from None
    if not isinstance(document, dict):
        raise ReaSetupError("REA 등록 뒤 OpenCode 설정의 최상위 값이 객체가 아닙니다.")
    tools = document.setdefault("tools", {})
    agents = document.setdefault("agent", {})
    if not isinstance(tools, dict) or not isinstance(agents, dict):
        raise ReaSetupError("OpenCode의 tools 또는 agent 설정 형식이 예상과 다릅니다.")
    existing = agents.get(REA_AGENT_NAME)
    if existing is not None and existing not in (LEGACY_REA_AGENT, REA_AGENT):
        raise ReaSetupError(
            f"OpenCode agent '{REA_AGENT_NAME}'이 이미 다른 설정으로 존재합니다. 기존 설정을 보존했습니다."
        )
    changed = tools.get(REA_TOOL_GLOB) is not False or existing != REA_AGENT
    if not changed:
        return False
    tools[REA_TOOL_GLOB] = False
    agents[REA_AGENT_NAME] = REA_AGENT
    data = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    backup = config_path.with_name(config_path.name + ".strata-rea-tools.backup")
    try:
        shutil.copy2(config_path, backup)
        fd, temporary = tempfile.mkstemp(prefix="." + config_path.name + ".", suffix=".tmp", dir=config_path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, config_path)
    except OSError as exc:
        raise ReaSetupError(f"REA OpenCode 도구 범위를 안전하게 기록하지 못했습니다: {exc}") from None
    return True


def verify_tool_scope(config_path: Path) -> None:
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReaSetupError(f"REA 도구 범위 설정을 읽지 못했습니다: {exc}") from None
    if not isinstance(document, dict):
        raise ReaSetupError("REA 도구 범위 설정의 최상위 값이 객체가 아닙니다.")
    tools = document.get("tools")
    agents = document.get("agent")
    if not isinstance(tools, dict) or tools.get(REA_TOOL_GLOB) is not False:
        raise ReaSetupError("일반 OpenCode 세션의 REA 도구 차단 범위가 없습니다.")
    if not isinstance(agents, dict) or agents.get(REA_AGENT_NAME) != REA_AGENT:
        raise ReaSetupError("REA 전용 분석 subagent 범위가 없습니다.")


def configure_opencode() -> ReaSetupResult:
    """Run REA's official setup, then constrain its high-cardinality tool catalog."""
    _, npx, _ = _require_runtime()
    command = rea_setup_command(npx)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReaSetupError(f"REA OpenCode 등록을 실행하지 못했습니다: {exc}") from None
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        detail = output[-2000:] if output else "출력 없음"
        raise ReaSetupError(f"REA OpenCode 등록이 종료 코드 {result.returncode}로 실패했습니다: {detail}")
    apply_tool_scope(opencode_config_path())
    return ReaSetupResult(tuple(command), output)


def doctor_opencode() -> ReaSetupResult:
    """Run REA's scoped, read-only OpenCode and skill inspection."""
    _, npx, _ = _require_runtime()
    command = rea_doctor_command(npx)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReaSetupError(f"REA OpenCode 진단을 실행하지 못했습니다: {exc}") from None
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        detail = output[-2000:] if output else "출력 없음"
        raise ReaSetupError(f"REA OpenCode 진단이 종료 코드 {result.returncode}로 실패했습니다: {detail}")
    verify_tool_scope(opencode_config_path())
    return ReaSetupResult(tuple(command), output)
