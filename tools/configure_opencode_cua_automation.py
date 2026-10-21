#!/usr/bin/env python3
"""Install window-scoped background-only CUA input without the user's pointer."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode" / "opencode.json"
DEFAULT_CUA_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cua-driver"
DEFAULT_INSTRUCTIONS = DEFAULT_CONFIG.parent / "KOREAN_INSTRUCTIONS.md"
INSTRUCTIONS_NAME = "OPENCODE_CUA_AUTOMATION_KO.md"

OLD_DELIVERY_PREFIX = "- \uC785\uB825\uC740 \uC815\uD655\uD55C \uCC3D \uB300\uC0C1\uC73C\uB85C `delivery_mode: "
OLD_STOP_PREFIX = "- `background_unavailable`, 권한 거부, 창 식별 실패가 발생하면"
OLD_DISCOVERY_PREFIX = "- \uBA3C\uC800 `list_windows`\uB85C \uB300\uC0C1 \uC571\uC744 \uCC3E\uACE0"
OLD_IDENTITY_PREFIX = "- GUI \uC870\uC791 \uC804\uD6C4\uC5D0 \uC571\uACFC \uCC3D\uC758 \uC815\uCCB4\uC131\uC744 \uD655\uC778\uD558\uACE0"
OLD_STABILITY_PREFIX = "- \uAC01 \uD074\uB9AD\u00B7\uD1A0\uAE00\u00B7\uC120\uD0DD \uC785\uB825\uC740 \uAC00\uC7A5 \uCD5C\uADFC"
NEW_DISCOVERY_LINE = (
    "- 작업 시작 때 `list_windows`로 앱과 PID/HWND를 한 번 식별하고 같은 창을 다루는 동안 재사용한다. "
    "앱 재시작, 새 창 생성, ID 오류·불일치가 생긴 경우에만 목록을 다시 읽는다. 첫 입력 전에는 해당 창의 `get_window_state`를 읽는다."
)
PREVIOUS_DELIVERY_LINE = (
    '- 입력은 정확한 창 PID/HWND 대상으로 `background`부터 시도한다. '
    '드라이버의 `background_unavailable` 응답 또는 새 화면 상태에서 확인된 명백한 무동작 후에만 '
    '같은 동작을 같은 창에 `delivery_mode: "foreground"`로 한 번 재시도할 수 있다.'
)
PREVIOUS_STOP_LINE = (
    "- `foreground`는 대상 창을 잠시 활성화해 실제 입력을 전달한다. 사용자의 입력을 방해할 수 있거나 "
    "창 정체·결과가 불명확하면 사용하지 않는다. 데스크톱 전체 대상, 전역 입력, 셸/네이티브 입력 우회는 계속 금지하며, "
    "권한 거부나 확인되지 않은 결과에서는 멈춘다."
)
NEW_DELIVERY_LINE = '- 입력은 정확한 창 PID/HWND 대상으로 `delivery_mode:"background"`만 사용한다. AI 전용 커서는 cua-driver의 `move_cursor` 오버레이만 사용한다. 사용자 마우스·물리 포인터·foreground·SendInput은 금지한다.'
NEW_STOP_LINE = '- `background_unavailable` 또는 확인된 무동작이면 `BACKGROUND_ONLY_UNSUPPORTED`로 멈추고 보고한다. 사용자 마우스, 전역 입력, 셸/네이티브 입력으로 전환하지 않는다. 창 정체·결과가 불명확하거나 권한이 거부되면 멈춘다.'
NEW_IDENTITY_LINE = (
    "- 앱/창 정체성은 작업 시작과 결과 검증 때 확인한다. 동일 창에서 연속 작업 중에는 `list_windows`를 매번 반복하지 않는다. "
    "새 창 출현, 창 닫힘, PID/HWND 오류·불일치가 나타날 때만 목록을 다시 조회한다."
)
NEW_STABILITY_LINE = (
    "- 클릭·토글·선택은 가장 최근 `get_window_state`의 `element_token`을 사용한다. 각 동작 뒤 상태를 확인할 때 직전 `snapshot_id`를 "
    "`since`에 전달하고 `include_screenshot:false`로 변경된 트리만 읽어 새 토큰을 얻는다. 화면 픽셀 확인, 캔버스 조작, 불확실한 결과에서만 "
    "스크린샷을 요청한다. 큰 트리는 `query`·`max_depth`·`max_elements`로 제한하고 `both`·`full_output`은 필요한 경우에만 쓴다. "
    "`element_token is stale` 오류는 상태를 한 번 새로 읽어 최대 한 번만 재표적화한다."
)


def _object(parent: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = parent.get(key)
    if value is None:
        value = {}
        parent[key] = value
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object; no files were changed.")
    return value


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.before-cua-automation-{stamp}.bak")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.before-cua-automation-{stamp}-{suffix}.bak")
        suffix += 1
    shutil.copy2(path, candidate)
    return candidate


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _reference_for(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(Path.home().resolve())
    except ValueError:
        return str(resolved)
    return "~/" + relative.as_posix()


def _configured_cua_server(config: dict[str, Any]) -> dict[str, Any] | None:
    mcp = config.get("mcp")
    if not isinstance(mcp, dict):
        return None
    direct = mcp.get("cua-driver")
    if isinstance(direct, dict):
        return direct
    servers = mcp.get("servers")
    legacy = servers.get("cua-driver") if isinstance(servers, dict) else None
    return legacy if isinstance(legacy, dict) else None


def _read_text_preserving_newlines(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_bom


def _patch_gui_instructions(path: Path) -> bytes | None:
    if not path.exists():
        return None
    text, has_bom = _read_text_preserving_newlines(path)
    if "## OpenCode GUI 자동 사용" not in text and "CUA Driver 입력 안정화" not in text:
        # Unrelated personal instructions are not a legacy GUI policy.
        return None
    lines = text.splitlines(keepends=True)
    old_prefixes = (OLD_DISCOVERY_PREFIX, OLD_DELIVERY_PREFIX, OLD_STOP_PREFIX, OLD_IDENTITY_PREFIX, OLD_STABILITY_PREFIX)
    new_lines = (NEW_DISCOVERY_LINE, NEW_DELIVERY_LINE, NEW_STOP_LINE, NEW_IDENTITY_LINE, NEW_STABILITY_LINE)
    old_matches = [
        [i for i, line in enumerate(lines) if line.rstrip("\r\n").startswith(prefix)
         or (prefix == OLD_DELIVERY_PREFIX and line.rstrip("\r\n") == PREVIOUS_DELIVERY_LINE)
         or (prefix == OLD_STOP_PREFIX and line.rstrip("\r\n") == PREVIOUS_STOP_LINE)]
        for prefix in old_prefixes
    ]
    new_matches = [
        [i for i, line in enumerate(lines) if line.rstrip("\r\n") == replacement]
        for replacement in new_lines
    ]

    updates: list[tuple[int, str]] = []
    for old, new, replacement in zip(old_matches, new_matches, new_lines):
        if len(old) == 1 and not new:
            updates.append((old[0], replacement))
        elif not old and len(new) == 1:
            continue
        else:
            raise ValueError(
                f"Could not safely identify the old CUA policy in {path}; no files were changed. "
                "Review that instruction file manually before installation."
            )
    if not updates:
        return None

    for index, replacement in updates:
        ending = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
        lines[index] = replacement + ending
    body = "".join(lines).encode("utf-8")
    return (b"\xef\xbb\xbf" if has_bom else b"") + body


def _find_runtime_path(
    explicit: Path | None,
    env_name: str,
    executable_name: str,
    config: dict[str, Any],
    *,
    node: bool,
) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        explicit = explicit.expanduser()
        if not explicit.is_file():
            raise ValueError(f"Explicit runtime does not exist: {explicit}; no files were changed.")
        return explicit.resolve()
    configured = os.environ.get(env_name)
    if configured:
        candidates.append(Path(configured).expanduser())
    if node:
        server = _configured_cua_server(config)
        command = server.get("command") if isinstance(server, dict) else None
        if (isinstance(command, list) and command and isinstance(command[0], str)
                and Path(command[0]).stem.lower() == "node"):
            candidates.append(Path(command[0]).expanduser())
    else:
        server = _configured_cua_server(config)
        environment = server.get("environment") if isinstance(server, dict) else None
        configured_driver = environment.get("CUA_DRIVER_EXE") if isinstance(environment, dict) else None
        if isinstance(configured_driver, str) and configured_driver:
            candidates.append(Path(configured_driver).expanduser())
        installed = locate_cua_driver(Path.home())
        if installed:
            candidates.append(installed)
        if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Cua" / "cua-driver" / "bin" / "cua-driver.exe")

    found_on_path = shutil.which(executable_name)
    if found_on_path:
        candidates.append(Path(found_on_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError(
        f"Could not find {executable_name}. Install it separately or pass --{('node' if node else 'driver')} PATH; "
        "the installer does not install runtimes. No files were changed."
    )


def locate_cua_driver(home: Path) -> Path | None:
    """Resolve the installer's current pointer, never guess a release version."""
    name = "cua-driver.exe" if os.name == "nt" else "cua-driver"
    candidates = [home / ".cua-driver" / "packages" / "current" / name]
    for name in ("cua-driver", "cua-driver.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.extend([
        home / ".local" / "bin" / "cua-driver",
        Path("/Applications/CuaDriver.app/Contents/MacOS/cua-driver"),
    ])
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        candidates.extend(local / "Programs" / vendor / "bin/cua-driver.exe"
                          for vendor in ("Cua/cua-driver", "trycua/cua-driver-rs"))
    return next((path.resolve() for path in candidates if path.is_file()), None)


def prepare_configuration(
    config_path: Path = DEFAULT_CONFIG,
    cua_dir: Path = DEFAULT_CUA_DIR,
    instructions_path: Path = DEFAULT_INSTRUCTIONS,
    node_path: Path | None = None,
    driver_path: Path | None = None,
    source_root: Path = ROOT,
    config_document: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[Path, bytes]]:
    """Validate and render every file without writing (also used by remote setup)."""
    config_path = config_path.expanduser().resolve()
    cua_dir = cua_dir.expanduser().resolve()
    instructions_path = instructions_path.expanduser()
    source_root = source_root.resolve()

    if config_document is not None:
        config = config_document
    elif config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"OpenCode config is unreadable JSON; no files were changed: {error}") from error
        if not isinstance(config, dict):
            raise ValueError("OpenCode config root must be a JSON object; no files were changed.")
    else:
        config = {}

    resolved_node = _find_runtime_path(node_path, "CUA_NODE_EXE", "node", config, node=True)
    resolved_driver = _find_runtime_path(driver_path, "CUA_DRIVER_EXE", "cua-driver", config, node=False)

    try:
        updated = json.loads(json.dumps(config))
        mcp = _object(updated, "mcp", "mcp")
        servers = _object(mcp, "servers", "mcp.servers")
        # OpenCode V2 accepts V1 syntax but its migration drops V2-only fields
        # such as codemode. Normalize direct server entries before installing.
        for name, entry in list(mcp.items()):
            if name == "servers":
                continue
            if not isinstance(entry, dict) or entry.get("type") not in ("local", "remote"):
                raise ValueError(f"Unknown legacy mcp.{name}; no files were changed.")
            if name in servers and servers[name] != entry:
                raise ValueError(f"Conflicting mcp.{name} and mcp.servers.{name}; no files were changed.")
            servers[name] = entry
            del mcp[name]
        for entry in servers.values():
            if isinstance(entry, dict) and "enabled" in entry:
                if "disabled" in entry and entry["disabled"] != (not entry["enabled"]):
                    raise ValueError("Conflicting MCP enabled/disabled flags; no files were changed.")
                entry["disabled"] = not entry.pop("enabled")
        server = _object(servers, "cua-driver", "mcp.servers.cua-driver")
        environment = _object(server, "environment", "mcp.cua-driver.environment")
        instructions = updated.get("instructions", [])
        if isinstance(instructions, str):
            instructions = [instructions]
        if not isinstance(instructions, list) or any(not isinstance(item, str) for item in instructions):
            raise ValueError("OpenCode instructions must be a string or an array of strings; no files were changed.")
    except ValueError:
        raise

    installed_doc = config_path.parent / INSTRUCTIONS_NAME
    # Keep policy and wrapper beside the existing CUA driver's per-user config.
    policy_target = cua_dir / "opencode-window-scoped.rego"
    wrapper_target = cua_dir / "opencode-mcp.mjs"
    module_target = cua_dir / "opencode-policy.mjs"

    doc_source = source_root / "examples" / "opencode" / INSTRUCTIONS_NAME
    if not doc_source.is_file():
        raise ValueError(f"CUA instruction template missing: {doc_source}; no files were changed.")
    doc_content = doc_source.read_bytes()
    template_contents = {
        wrapper_target: (source_root / "tools" / "cua-driver" / "opencode-mcp.mjs").read_bytes(),
        cua_dir / "opencode-catalog.mjs": (source_root / "tools/cua-driver/opencode-catalog.mjs").read_bytes(),
        cua_dir / "opencode-grounding.mjs": (source_root / "tools/cua-driver/opencode-grounding.mjs").read_bytes(),
        module_target: (source_root / "tools" / "cua-driver" / "opencode-policy.mjs").read_bytes(),
        policy_target: (source_root / "tools" / "cua-driver" / "opencode-window-scoped.rego").read_bytes(),
        installed_doc: doc_content,
    }
    instructions_file_ref = _reference_for(installed_doc)
    if instructions_file_ref not in instructions:
        instructions.append(instructions_file_ref)

    server["type"] = "local"
    server["command"] = [str(resolved_node), str(wrapper_target)]
    server["disabled"] = False
    server["codemode"] = False
    server.pop("enabled", None)
    environment["CUA_DRIVER_EXE"] = str(resolved_driver)
    environment["CUA_DRIVER_POLICY_FILE"] = str(policy_target)
    environment["CUA_DRIVER_PERMISSION_MODE"] = "standard"
    updated["instructions"] = instructions

    korean_bytes = _patch_gui_instructions(instructions_path)
    if korean_bytes is not None:
        template_contents[instructions_path] = korean_bytes
    elif instructions_path.exists() and not any(
        line.rstrip("\r\n") == NEW_DELIVERY_LINE
        for line in _read_text_preserving_newlines(instructions_path)[0].splitlines(keepends=True)
    ):
        # A missing legacy block is safe only when the canonical supplement is already
        # the sole source of the GUI policy; _patch_gui_instructions rejects unknown
        # existing blocks to avoid leaving contradictory instructions behind.
        text, _ = _read_text_preserving_newlines(instructions_path)
        if "## OpenCode GUI 자동 사용" in text:
            raise ValueError(f"Could not safely update the existing GUI policy in {instructions_path}; no files were changed.")

    config_changed = updated != config
    if config_changed or config_document is not None:
        template_contents[config_path] = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    return {
        "config_path": str(config_path),
        "cua_policy_path": str(policy_target),
        "instructions_path": str(installed_doc),
        "config_changed": config_changed,
    }, template_contents


def apply_configuration(
    config_path: Path = DEFAULT_CONFIG,
    cua_dir: Path = DEFAULT_CUA_DIR,
    instructions_path: Path = DEFAULT_INSTRUCTIONS,
    node_path: Path | None = None,
    driver_path: Path | None = None,
    source_root: Path = ROOT,
) -> dict[str, Any]:
    result, template_contents = prepare_configuration(
        config_path, cua_dir, instructions_path, node_path, driver_path, source_root)
    changed_targets = [target for target, content in template_contents.items() if not target.exists() or target.read_bytes() != content]
    backups: list[str] = []
    for target in changed_targets:
        if target.exists():
            backups.append(str(_backup(target)))
    for target in changed_targets:
        _atomic_write(target, template_contents[target])

    result.update(changed_files=[str(path.resolve()) for path in changed_targets], backups=backups)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="OpenCode config path")
    parser.add_argument("--cua-config-dir", type=Path, default=DEFAULT_CUA_DIR, help="CUA Driver config directory")
    parser.add_argument("--instructions-file", type=Path, help="existing Korean instructions (default: beside --config)")
    parser.add_argument("--node", type=Path, help="Node.js executable (defaults to existing config or PATH)")
    parser.add_argument("--driver", type=Path, help="CUA Driver executable (defaults to existing config or PATH)")
    args = parser.parse_args()
    try:
        result = apply_configuration(
            args.config,
            args.cua_config_dir,
            args.instructions_file or args.config.parent / "KOREAN_INSTRUCTIONS.md",
            args.node,
            args.driver,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"OpenCode config: {result['config_path']}")
    print(f"CUA policy: {result['cua_policy_path']}")
    print(f"CUA instructions: {result['instructions_path']}")
    print(f"Config changed: {result['config_changed']}")
    print("Changed files:")
    for path in result["changed_files"]:
        print(f"  {path}")
    if result["backups"]:
        print("Backups:")
        for path in result["backups"]:
            print(f"  {path}")
    print("Restart the Rider OpenCode session at a safe point to reload the MCP proxy and policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
