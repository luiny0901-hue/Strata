#!/usr/bin/env python3
"""Configure and diagnose a client PC that uses a remote Strata server.

This tool configures OpenCode and its JetBrains ACP entry. It never installs or
starts Strata, changes firewall rules, or installs a CUA Driver.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = REPO_ROOT / "examples" / "opencode"
PROFILE_FILE = EXAMPLE_DIR / "autonomous-agent-v2.fragment.json"
INSTRUCTIONS_FILE = EXAMPLE_DIR / "KOREAN_INSTRUCTIONS.md"
PROVIDER_ID = "strata"
MODEL_KEY = "server"
KEY_FILE_RELATIVE = ".config/opencode/strata-client/secrets/STRATA_API_KEY"
SCHEMA_URL = "https://opencode.ai/config.json"


class SetupError(RuntimeError):
    pass


def client_dir(home: Path) -> Path:
    return home / ".config" / "opencode" / "strata-client"


def overlay_path(home: Path) -> Path:
    return client_dir(home) / "opencode.jsonc"


def key_path(home: Path) -> Path:
    return home / KEY_FILE_RELATIVE


def state_path(home: Path) -> Path:
    return client_dir(home) / "setup-state.json"


def acp_path(home: Path) -> Path:
    return home / ".jetbrains" / "acp.json"


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        raise SetupError("Strata 서버 주소가 비어 있습니다.")
    if "://" not in value:
        value = "http://" + value
    try:
        parsed = urllib.parse.urlsplit(value)
        # Force validation of malformed or out-of-range ports.
        _ = parsed.port
    except ValueError:
        raise SetupError("서버 주소의 호스트 또는 포트 형식이 잘못되었습니다.") from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SetupError("주소는 http(s)://호스트:포트 형식이어야 합니다.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SetupError("주소에 사용자 정보, 쿼리 또는 fragment를 넣지 마세요.")
    if parsed.path not in ("", "/", "/v1"):
        raise SetupError("서버 주소에는 호스트만 입력하거나 마지막에 /v1을 붙이세요.")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/v1", "", ""))


def http_json(url: str, api_key: str, timeout: float = 8.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise SetupError("API 키가 거부되었습니다. 서버 키를 확인하세요.") from None
        raise SetupError(f"서버 응답 오류: HTTP {exc.code} ({url})") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", "연결 실패")
        raise SetupError(f"서버에 연결할 수 없습니다 ({url}): {reason}") from None
    except (TimeoutError, OSError) as exc:
        raise SetupError(f"서버에 연결할 수 없습니다 ({url}): {exc}") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SetupError(f"서버가 유효한 JSON을 반환하지 않았습니다 ({url}).") from None
    if not isinstance(payload, dict):
        raise SetupError(f"서버 응답 형식이 예상과 다릅니다 ({url}).")
    return payload


def fetch_server_profile(base_url: str, api_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = base_url[:-3]
    health = http_json(root + "/health", api_key)
    if health.get("status") != "ok":
        raise SetupError("Strata /health가 정상 상태를 반환하지 않았습니다.")
    inventory = http_json(base_url + "/models", api_key)
    raw_models = inventory.get("data")
    if not isinstance(raw_models, list):
        raise SetupError("/v1/models 응답에 data 목록이 없습니다.")
    models: list[dict[str, Any]] = []
    for model in raw_models:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            continue
        architecture = model.get("architecture") or {}
        outputs = architecture.get("output_modalities") if isinstance(architecture, dict) else None
        if outputs and "text" not in outputs:
            continue
        models.append(model)
    if not models:
        raise SetupError("사용 가능한 텍스트 모델이 없습니다. Strata 서버가 모델을 불러왔는지 확인하세요.")
    return health, models


def _tilde_path(path: Path, home: Path) -> str:
    try:
        relative = path.relative_to(home)
    except ValueError:
        return path.as_posix()
    return "~/" + relative.as_posix()


def build_overlay(
    base_url: str,
    model: dict[str, Any],
    health: dict[str, Any],
    home: Path,
) -> dict[str, Any]:
    try:
        config = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"저장소의 OpenCode 프로필을 읽을 수 없습니다: {exc}") from None
    if not isinstance(config, dict):
        raise SetupError("OpenCode 프로필의 최상위 값은 JSON 객체여야 합니다.")

    config["$schema"] = SCHEMA_URL
    config["instructions"] = [_tilde_path(client_dir(home) / "KOREAN_INSTRUCTIONS.md", home)]
    config["model"] = f"{PROVIDER_ID}/{MODEL_KEY}"

    context = health.get("max_context")
    limit: dict[str, int] = {}
    if isinstance(context, int) and not isinstance(context, bool) and context > 0:
        limit["context"] = context
    modalities = ["text"]
    if health.get("images") is True:
        modalities.append("image")
    model_config: dict[str, Any] = {
        "modelID": model["id"],
        "name": f"Strata — {model['id']}",
        "capabilities": {"tools": True, "input": modalities, "output": ["text"]},
        "variants": [
            {"id": level, "body": {"reasoning_effort": level}}
            for level in ("none", "low", "medium", "high")
        ],
    }
    if limit:
        model_config["limit"] = limit

    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise SetupError("프로필의 providers 항목은 객체여야 합니다.")
    providers[PROVIDER_ID] = {
        "name": "Strata",
        "package": "@opencode/ai/providers/openai-compatible",
        "settings": {
            "baseURL": base_url,
            "apiKey": "{file:~/.config/opencode/strata-client/secrets/STRATA_API_KEY}",
            "headerTimeout": 600000,
            "chunkTimeout": 600000,
        },
        "models": {MODEL_KEY: model_config},
    }
    return config


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000:06d}"


def backup_if_changed(path: Path, new_bytes: bytes) -> None:
    if not path.exists():
        return
    try:
        old_bytes = path.read_bytes()
    except OSError as exc:
        raise SetupError(f"기존 파일을 읽을 수 없습니다: {path}: {exc}") from None
    if old_bytes == new_bytes:
        return
    backup = path.with_name(path.name + ".backup-" + _stamp())
    try:
        shutil.copy2(path, backup)
    except OSError as exc:
        raise SetupError(f"기존 파일 백업에 실패해 변경을 중단했습니다: {path}: {exc}") from None
    print(f"기존 설정 백업: {backup}")


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_if_changed(path, data)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        if os.name != "nt":
            os.chmod(temporary, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, mode)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise SetupError(f"파일을 안전하게 기록하지 못했습니다: {path}: {exc}") from None


def secure_windows_directory(path: Path) -> None:
    whoami = subprocess.run(["whoami"], capture_output=True, text=True, check=False)
    if whoami.returncode != 0 or not whoami.stdout.strip():
        raise SetupError("현재 Windows 사용자 ACL을 확인할 수 없어 API 키 파일을 쓰지 않았습니다.")
    path.mkdir(parents=True, exist_ok=True)
    account = whoami.stdout.strip()
    result = subprocess.run(
        ["icacls", str(path), "/reset", "/inheritance:r", "/grant:r", f"{account}:(OI)(CI)F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SetupError("API 키 디렉터리 ACL을 현재 사용자 전용으로 설정하지 못했습니다.")


def write_secret(path: Path, secret: str) -> None:
    if not secret or "\n" in secret or "\r" in secret:
        raise SetupError("API 키가 비어 있거나 줄바꿈을 포함합니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        secure_windows_directory(path.parent)
    else:
        os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(secret.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise SetupError(f"API 키를 기록하지 못했습니다: {path}: {exc}") from None


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _shell_literal(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def locate_opencode(explicit: str | None) -> Path | None:
    candidate = explicit or shutil.which("opencode")
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        located = shutil.which(str(path))
        if not located:
            return None
        path = Path(located)
    if not path.exists():
        return None
    return path.resolve()


def opencode_version(executable: Path) -> str:
    try:
        command = [str(executable), "--version"]
        environment = os.environ.copy()
        if os.name == "nt" and executable.suffix.casefold() in (".cmd", ".bat"):
            powershell = shutil.which("powershell.exe") or shutil.which("powershell")
            if not powershell:
                raise SetupError("Windows PowerShell을 찾을 수 없어 OpenCode CLI를 확인하지 못했습니다.")
            environment["LUSTRA_OPENCODE_EXECUTABLE"] = str(executable)
            command = [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "& $env:LUSTRA_OPENCODE_EXECUTABLE --version",
            ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"OpenCode CLI 버전을 확인하지 못했습니다: {exc}") from None
    version = (result.stdout or result.stderr).strip().splitlines()
    if result.returncode != 0 or not version:
        raise SetupError("OpenCode --version 확인이 실패했습니다. 클라이언트 설정은 변경하지 않았습니다.")
    value = version[0].strip()
    if not re.match(r"^(?:opencode\s+)?v?2\.\d+(?:\.\d+)?(?:[-+].*)?$", value, re.IGNORECASE):
        raise SetupError(
            f"이 설정 프로필은 OpenCode V2용이지만 확인된 버전은 '{value}'입니다. "
            "V2 CLI를 설치한 뒤 다시 실행하세요. 기존 설정은 변경하지 않았습니다."
        )
    return value


def build_launcher(home: Path, opencode: Path) -> tuple[Path, str, list[str], bytes, int]:
    bin_dir = client_dir(home) / "bin"
    overlay = overlay_path(home).resolve()
    if os.name == "nt":
        wrapper = bin_dir / "opencode-strata.ps1"
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            fallback = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            powershell = str(fallback) if fallback.exists() else None
        if not powershell:
            raise SetupError("Windows PowerShell을 찾을 수 없어 Rider ACP를 구성하지 않았습니다.")
        content = (
            "$ErrorActionPreference = 'Stop'\n"
            f"$env:OPENCODE_CONFIG = {_powershell_literal(str(overlay))}\n"
            f"$opencode = {_powershell_literal(str(opencode))}\n"
            "& $opencode @args\n"
            "exit $LASTEXITCODE\n"
        )
        # Windows PowerShell 5.1 requires a BOM to reliably read non-ASCII paths.
        launcher_data = b"\xef\xbb\xbf" + content.encode("utf-8")
        args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(wrapper), "acp"]
        return wrapper, str(Path(powershell).resolve()), args, launcher_data, 0o600

    wrapper = bin_dir / "opencode-strata"
    content = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"export OPENCODE_CONFIG={_shell_literal(str(overlay))}\n"
        f"exec {_shell_literal(str(opencode))} \"$@\"\n"
    )
    return wrapper, str(wrapper), ["acp"], content.encode("utf-8"), 0o700


def load_acp(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(
            f"JetBrains ACP 파일을 읽지 못해 덮어쓰지 않았습니다: {path}: {exc}. "
            "acp.json은 표준 JSON으로 저장한 뒤 다시 실행하세요."
        ) from None
    if not isinstance(value, dict):
        raise SetupError(f"JetBrains ACP 설정 최상위 값은 객체여야 합니다: {path}")
    return value


def merge_acp(path: Path, command: str, args: list[str]) -> tuple[dict[str, Any], str]:
    value = load_acp(path)
    defaults = value.setdefault("default_mcp_settings", {})
    servers = value.setdefault("agent_servers", {})
    if not isinstance(defaults, dict) or not isinstance(servers, dict):
        raise SetupError("acp.json의 default_mcp_settings / agent_servers 형식이 예상과 다릅니다.")
    defaults["use_custom_mcp"] = True

    base_name = "OpenCode Strata"
    name = base_name
    number = 2
    while name in servers:
        existing = servers[name]
        if isinstance(existing, dict) and existing.get("command") == command and existing.get("args") == args:
            break
        name = f"{base_name} ({number})"
        number += 1
    servers[name] = {"command": command, "args": args}
    return value, name


def choose_model(models: list[dict[str, Any]]) -> dict[str, Any]:
    if len(models) == 1:
        return models[0]
    print("Strata에서 확인한 텍스트 모델:")
    def model_status(model: dict[str, Any]) -> str:
        status = model.get("status")
        return status.get("value", "상태 정보 없음") if isinstance(status, dict) else "상태 정보 없음"

    for index, model in enumerate(models, 1):
        status = model_status(model)
        print(f"  {index}. {model['id']} [{status}]")
    loaded = next((i for i, item in enumerate(models, 1) if model_status(item) == "loaded"), 1)
    while True:
        answer = input(f"사용할 모델 번호 [{loaded}]: ").strip()
        if not answer:
            return models[loaded - 1]
        if answer.isdigit() and 1 <= int(answer) <= len(models):
            return models[int(answer) - 1]
        print("목록에 있는 번호를 입력하세요.")


def write_setup(
    home: Path,
    base_url: str,
    key: str,
    health: dict[str, Any],
    model: dict[str, Any],
    opencode: Path,
    version: str,
) -> str:
    acp = acp_path(home)
    # Validate existing ACP before writing any local client configuration.
    load_acp(acp)
    config = build_overlay(base_url, model, health, home)
    encoded_overlay = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    # Validate all generated state before touching the credential or ACP file.
    instructions_dest = client_dir(home) / "KOREAN_INSTRUCTIONS.md"
    instructions_bytes = INSTRUCTIONS_FILE.read_bytes()
    wrapper, acp_command, acp_args, launcher_data, launcher_mode = build_launcher(home, opencode)
    acp_config, agent_name = merge_acp(acp, acp_command, acp_args)

    atomic_write(instructions_dest, instructions_bytes)
    atomic_write(overlay_path(home), encoded_overlay)
    write_secret(key_path(home), key)
    atomic_write(wrapper, launcher_data, mode=launcher_mode)
    if os.name != "nt":
        os.chmod(wrapper, launcher_mode)
    atomic_write(acp, (json.dumps(acp_config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    state = {
        "base_url": base_url,
        "model_id": model["id"],
        "opencode_version": version,
        "context": health.get("max_context"),
        "images": health.get("images") is True,
        "loaded_at_setup": health.get("loaded") is True,
        "opencode_executable": str(opencode),
        "opencode_config": str(overlay_path(home).resolve()),
        "key_file": str(key_path(home)),
        "acp_config": str(acp),
        "acp_agent": agent_name,
        "launcher": str(wrapper),
    }
    atomic_write(state_path(home), (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return agent_name


def do_setup(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser() if args.home else Path.home()
    opencode = locate_opencode(args.opencode)
    if opencode is None:
        entered = input("OpenCode 실행 파일 경로 (PATH에서 못 찾음): ").strip()
        opencode = locate_opencode(entered)
    if opencode is None:
        raise SetupError("OpenCode CLI가 필요합니다. 기존 앱을 제거하거나 변경하지 않고, 설치 후 다시 실행하세요.")
    version = opencode_version(opencode)

    previous_url = ""
    if overlay_path(home).exists():
        try:
            previous = json.loads(overlay_path(home).read_text(encoding="utf-8"))
            previous_url = previous.get("providers", {}).get(PROVIDER_ID, {}).get("settings", {}).get("baseURL", "")
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    prompt = f"Strata 서버 주소 (예: 192.168.1.20:8080) [{previous_url or 'http://127.0.0.1:8080'}]: "
    raw_url = input(prompt).strip() or previous_url or "http://127.0.0.1:8080"
    base_url = normalize_base_url(raw_url)

    existing_key = key_path(home)
    key = ""
    if existing_key.exists() and input("저장된 키를 재사용할까요? [Y/n]: ").strip().lower() not in ("n", "no"):
        try:
            key = existing_key.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SetupError(f"저장된 API 키를 읽을 수 없습니다: {existing_key}: {exc}") from None
    if not key:
        key = getpass.getpass("Strata API 키 (입력 내용은 화면에 표시되지 않음): ").strip()
    try:
        health, models = fetch_server_profile(base_url, key)
    except SetupError as exc:
        if "거부되었습니다" not in str(exc) or not existing_key.exists() or key != existing_key.read_text(encoding="utf-8").strip():
            raise
        key = getpass.getpass("저장된 키가 거부되었습니다. 새 Strata API 키: ").strip()
        health, models = fetch_server_profile(base_url, key)
    model = choose_model(models)
    agent = write_setup(home, base_url, key, health, model, opencode, version)

    loaded = "loaded" if health.get("loaded") is True else "모델 미로드 (서버는 응답함)"
    context = health.get("max_context") or "서버가 보고하지 않음"
    print("\n설정 완료")
    print(f"  OpenCode 모델: {PROVIDER_ID}/{MODEL_KEY} → {model['id']}")
    print(f"  OpenCode CLI: {version}")
    print(f"  서버: {base_url} ({loaded}, context={context})")
    print(f"  API 키: {key_path(home)} (내용은 출력하거나 설정 JSON에 저장하지 않음)")
    print(f"  OpenCode 실행: {client_dir(home) / 'bin' / ('opencode-strata.ps1' if os.name == 'nt' else 'opencode-strata')}")
    print(f"  Rider: IDE를 재시작하고 ACP agent '{agent}'를 선택하세요.")
    print("  CUA Driver: 기존 로컬 MCP를 자동 설치하지 않습니다. Rider의 custom MCP 공유는 켰습니다.")
    print("  macOS CUA 지원: 이 저장소에서 검증되지 않았습니다.")
    print("  Hermes: 별도 설정입니다. 'hermes model'에서 Custom endpoint를 선택하세요.")
    doctor_command = (
        f"& {_powershell_literal(str(REPO_ROOT / 'tools' / 'remote_agent_client' / 'setup-windows.bat'))} doctor"
        if os.name == "nt"
        else f"sh {_shell_literal(str(REPO_ROOT / 'tools' / 'remote_agent_client' / 'setup-macos.sh'))} doctor"
    )
    print(f"  다음 점검: {doctor_command}")
    return 0


def _check_posix_secret(path: Path) -> bool:
    try:
        file_mode = stat.S_IMODE(path.stat().st_mode)
        directory_mode = stat.S_IMODE(path.parent.stat().st_mode)
        return file_mode & 0o077 == 0 and directory_mode & 0o077 == 0
    except OSError:
        return False


def _check_windows_secret(path: Path) -> bool:
    account = subprocess.run(["whoami"], capture_output=True, text=True, check=False)
    acl = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=False)
    if account.returncode != 0 or acl.returncode != 0 or not account.stdout.strip():
        return False
    current = account.stdout.strip().casefold()
    entries = [line.strip().casefold() for line in acl.stdout.splitlines() if re.search(r"\([^)]*\)", line)]
    return len(entries) == 1 and current in entries[0] and "(f)" in entries[0]


def do_doctor(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser() if args.home else Path.home()
    state_file = state_path(home)
    if not state_file.exists():
        raise SetupError(f"설정 영수증이 없습니다. 먼저 setup을 실행하세요: {state_file}")
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        config = json.loads(overlay_path(home).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"클라이언트 설정을 읽을 수 없습니다: {exc}") from None
    if not isinstance(state, dict) or not isinstance(config, dict):
        raise SetupError("클라이언트 영수증과 OpenCode overlay의 최상위 값은 JSON 객체여야 합니다.")

    failures = 0
    key_file = Path(state.get("key_file", key_path(home)))
    if key_file.exists():
        if os.name == "nt":
            if _check_windows_secret(key_file):
                print("PASS API 키 파일 ACL이 현재 사용자 전용입니다 (값은 표시하지 않음).")
            else:
                print("FAIL API 키 파일 ACL을 현재 사용자 전용으로 확인하지 못했습니다.")
                failures += 1
        elif _check_posix_secret(key_file):
            print(f"PASS API 키 파일 권한 600 이하: {key_file}")
        else:
            print(f"FAIL API 키 파일 권한이 너무 넓습니다: {key_file}")
            failures += 1
    else:
        print(f"FAIL API 키 파일 없음: {key_file}")
        failures += 1

    expected_id = state.get("model_id")
    expected_url = state.get("base_url")
    executable = Path(state.get("opencode_executable", ""))
    if executable.exists():
        try:
            current_version = opencode_version(executable)
            print(f"PASS OpenCode CLI V2: {current_version}")
        except SetupError as exc:
            print(f"FAIL OpenCode CLI: {exc}")
            failures += 1
    else:
        print(f"FAIL OpenCode 실행 파일 없음: {executable}")
        failures += 1
    providers = config.get("providers")
    provider = providers.get(PROVIDER_ID, {}) if isinstance(providers, dict) else {}
    settings = provider.get("settings") if isinstance(provider, dict) else None
    models = provider.get("models") if isinstance(provider, dict) else None
    model_config = models.get(MODEL_KEY) if isinstance(models, dict) else None
    configured_url = settings.get("baseURL") if isinstance(settings, dict) else None
    configured_model = model_config.get("modelID") if isinstance(model_config, dict) else None
    if configured_url == expected_url and configured_model == expected_id:
        print(f"PASS OpenCode overlay model mapping: {PROVIDER_ID}/{MODEL_KEY} → {expected_id}")
    else:
        print("FAIL OpenCode overlay와 설정 영수증의 서버/모델이 다릅니다.")
        failures += 1

    if not key_file.exists():
        return 1
    try:
        key = key_file.read_text(encoding="utf-8").strip()
        health, models = fetch_server_profile(expected_url, key)
        available = any(item.get("id") == expected_id for item in models)
        if available:
            loaded = health.get("loaded") is True
            print(f"PASS Strata /health + /v1/models 인증 및 모델 확인 ({'loaded' if loaded else '모델 미로드'})")
        else:
            print(f"FAIL Strata /v1/models에 등록 모델이 없습니다: {expected_id}")
            failures += 1
    except SetupError as exc:
        print(f"FAIL Strata 연결: {exc}")
        failures += 1

    acp = acp_path(home)
    try:
        acp_config = load_acp(acp)
        servers = acp_config.get("agent_servers", {})
        entry = servers.get(state.get("acp_agent"), {}) if isinstance(servers, dict) else {}
        wrapper = Path(state.get("launcher", ""))
        defaults = acp_config.get("default_mcp_settings")
        custom_mcp = isinstance(defaults, dict) and defaults.get("use_custom_mcp") is True
        if isinstance(entry, dict) and entry.get("args") and wrapper.exists() and custom_mcp:
            print(f"PASS Rider ACP agent 등록: {state.get('acp_agent')}")
        else:
            print("FAIL Rider ACP agent 항목이 없습니다.")
            failures += 1
    except SetupError as exc:
        print(f"FAIL Rider ACP: {exc}")
        failures += 1

    print("UNVERIFIED CUA Driver: 이 도구는 설치/실행/시각 동작을 검사하지 않습니다.")
    print("UNVERIFIED macOS CUA support: 별도 CUA 공급자의 Apple Silicon 지원 증거가 필요합니다.")
    print("NOT_RUN Hermes ACP: Hermes는 OpenCode와 별도 설정입니다.")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="대화형 OpenCode + Rider 설정")
    setup.add_argument("--home", help=argparse.SUPPRESS)
    setup.add_argument("--opencode", help="OpenCode CLI 전체 경로")
    setup.set_defaults(run=do_setup)
    doctor = sub.add_parser("doctor", help="현재 클라이언트 연결을 점검")
    doctor.add_argument("--home", help=argparse.SUPPRESS)
    doctor.set_defaults(run=do_doctor)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except SetupError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n취소했습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
