#!/usr/bin/env python3
"""Render portable Strata UD-IQ4_XS profiles and update OpenCode's model default."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


MODEL_ID = "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs"
MODEL_KEY = "qwen3.8-flash-next-unsloth-ud-iq4_xs"
MODEL_NAME = "Qwen3.8 Flash Next Unsloth UD-IQ4_XS (NVFP4 fork)"
PROFILE_STEM = "strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored"
FORK_RELATIVE = Path(
    "forks/sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2/strata-nvfp4"
)
MODEL_REVISION = "2c41bd2a0b3f51c503c11f1c7ed2e6bb34036beb"
SHARD_NAMES = (
    "Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf",
    "Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf",
    "Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf",
)
DEFAULT_MANIFEST = "docs/reports/2026-10-17-iq4xs-artifact-manifest.json"


def _template_path(repository_root: Path, mode: str) -> Path:
    return repository_root / "profiles" / f"{PROFILE_STEM}-{mode}.json.template"


def _replace_tokens(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_tokens(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_tokens(item, replacements) for item in value]
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value
    return value


def render_profile(
    repository_root: Path,
    mode: str,
    strata_root: Path,
    data_root: Path,
    output_path: Path,
) -> Path:
    if mode not in ("on", "off"):
        raise ValueError("mode must be 'on' or 'off'")
    repository_root = repository_root.resolve()
    strata_root = strata_root.resolve()
    data_root = data_root.resolve()
    fork_root = (strata_root / FORK_RELATIVE).resolve()
    model_root = data_root / "models" / "unsloth-UD-IQ4_XS"
    pack_root = data_root / "packs" / "unsloth-ud-iq4_xs"
    replacements = {
        "@FORK_ROOT@": str(fork_root),
        "@MODEL_ROOT@": str(model_root),
        "@PACK_ROOT@": str(pack_root),
        "@STRATA_DATA_ROOT@": str(data_root),
        "@STRATA_ROOT@": str(strata_root),
    }
    template = json.loads(_template_path(repository_root, mode).read_text(encoding="utf-8"))
    profile = _replace_tokens(template, replacements)
    serialized = json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    unresolved = (
        "@FORK_ROOT@",
        "@MODEL_ROOT@",
        "@PACK_ROOT@",
        "@STRATA_DATA_ROOT@",
        "@STRATA_ROOT@",
    )
    if any(token in serialized for token in unresolved):
        raise ValueError("profile still contains an unresolved path token")
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    os.replace(temporary, output_path)
    return output_path


def opencode_model_definition() -> dict[str, Any]:
    return {
        "name": MODEL_NAME,
        "capabilities": {
            "tools": True,
            "input": ["text", "image"],
            "output": ["text"],
        },
        "limit": {"context": 262144, "output": 32000},
        "variants": [
            {"id": effort, "body": {"reasoning_effort": effort}}
            for effort in ("low", "medium", "high", "xhigh")
        ],
    }


def configure_opencode_document(document: dict[str, Any]) -> bool:
    """Update only the default model and this model's provider entry."""
    providers = document.get("providers")
    provider = providers.get("strata") if isinstance(providers, dict) else None
    if not isinstance(provider, dict):
        raise ValueError("OpenCode config must already contain providers.strata")
    settings = provider.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("OpenCode config must already contain providers.strata.settings")
    if settings.get("baseURL") != "http://127.0.0.1:8080/v1":
        raise ValueError(
            "Strata provider baseURL must be http://127.0.0.1:8080/v1; "
            "configure the local provider first"
        )
    models = provider.get("models")
    if not isinstance(models, dict):
        raise ValueError("OpenCode config must already contain providers.strata.models")

    desired = opencode_model_definition()
    changed = document.get("model") != MODEL_ID or models.get(MODEL_KEY) != desired
    if changed:
        models[MODEL_KEY] = desired
        document["model"] = MODEL_ID
    return changed


def apply_opencode_default(config_path: Path) -> tuple[bool, Path | None]:
    config_path = config_path.expanduser().resolve()
    original = config_path.read_text(encoding="utf-8-sig")
    document = json.loads(original)
    if not isinstance(document, dict):
        raise ValueError("OpenCode config root must be a JSON object")

    updated = copy.deepcopy(document)
    changed = configure_opencode_document(updated)
    if not changed:
        return False, None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = config_path.with_name(f"{config_path.name}.pre-iq4xs-{stamp}.bak")
    suffix = 1
    while backup_path.exists():
        backup_path = config_path.with_name(f"{config_path.name}.pre-iq4xs-{stamp}-{suffix}.bak")
        suffix += 1
    shutil.copy2(config_path, backup_path)

    temporary = config_path.with_name(config_path.name + ".tmp")
    serialized = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    temporary.write_text(serialized, encoding="utf-8")
    os.replace(temporary, config_path)
    return True, backup_path


def validate_templates(repository_root: Path) -> list[str]:
    results: list[str] = []
    for mode, expected in (("on", True), ("off", False)):
        profile = json.loads(_template_path(repository_root, mode).read_text(encoding="utf-8"))
        args = profile.get("args", [])
        assert profile.get("uncensored") is expected, f"{mode}: incorrect uncensored default"
        assert profile.get("model_name") == MODEL_KEY, f"{mode}: wrong model id"
        assert profile.get("port") == 8080 and profile.get("gpu") == 1, f"{mode}: wrong endpoint/GPU"
        assert profile.get("sampling") == {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
        assert profile.get("reasoning_budget_tokens") == 8192
        assert "--max-context" in args, f"{mode}: missing context limit"
        assert args[args.index("--max-context") + 1] == "262144", f"{mode}: wrong context limit"
        assert "--ple-gguf" in args, f"{mode}: missing IQ4_XS PLE shard"
        assert args[args.index("--native") + 1].endswith(SHARD_NAMES[0])
        assert args[args.index("--ple-gguf") + 1].endswith(SHARD_NAMES[1])
        assert args[args.index("--pack") + 1] == "@PACK_ROOT@"
        assert args[args.index("--spec") + 1] == "4", f"{mode}: wrong MTP depth"
        assert args[args.index("--spec-min-p") + 1] == "0.5", f"{mode}: wrong MTP threshold"
        assert args[args.index("--vram-reserve-mib") + 1] == "1280"
        assert "--control-vector-scaled" in args, f"{mode}: missing control vector"
        assert args[args.index("--control-vector-layer-range") + 1 :][:2] == ["8", "33"]
        assert profile.get("vision", {}).get("gpu") is False, f"{mode}: vision should use CPU"
        assert profile.get("vision", {}).get("model", "").startswith("@MODEL_ROOT@")
        serialized = json.dumps(profile)
        for token in ("@STRATA_ROOT@", "@STRATA_DATA_ROOT@", "@FORK_ROOT@", "@MODEL_ROOT@", "@PACK_ROOT@"):
            assert token in serialized, f"{mode}: expected token missing: {token}"
        results.append(f"PASS template={mode} uncensored={str(expected).lower()} context=262144")
    return results


def verify_assets(
    repository_root: Path,
    data_root: Path,
    fork_root: Path,
) -> tuple[bool, list[str]]:
    manifest_path = repository_root / DEFAULT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model", {}).get("revision") != MODEL_REVISION:
        raise ValueError("artifact manifest does not match the pinned UD-IQ4_XS revision")
    roots = {
        "data": data_root,
        "model": data_root / "models" / "unsloth-UD-IQ4_XS",
        "pack": data_root / "packs" / "unsloth-ud-iq4_xs",
        "fork": fork_root,
        "strata": repository_root,
    }
    results: list[str] = []
    passed = True
    for artifact in manifest["files"]:
        base = roots[artifact["root"]]
        path = base / Path(artifact["path"])
        if not path.is_file():
            results.append(f"FAIL missing {artifact['root']}/{artifact['path']}")
            passed = False
            continue
        size = path.stat().st_size
        if size != artifact["size"]:
            results.append(
                f"FAIL size {artifact['root']}/{artifact['path']} "
                f"expected={artifact['size']} actual={size}"
            )
            passed = False
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        actual_hash = digest.hexdigest()
        if actual_hash != artifact["sha256"]:
            results.append(
                f"FAIL sha256 {artifact['root']}/{artifact['path']} "
                f"expected={artifact['sha256']} actual={actual_hash}"
            )
            passed = False
        else:
            results.append(f"PASS {artifact['root']}/{artifact['path']} sha256={actual_hash}")
    return passed, results


def _default_opencode_path() -> Path:
    return Path.home() / ".config" / "opencode" / "opencode.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render-profile", help="render one ON/OFF runtime profile")
    render.add_argument("--mode", choices=("on", "off"), required=True)
    render.add_argument("--strata-root", type=Path, required=True)
    render.add_argument("--data-root", type=Path, default=Path.home() / "Strata-data")
    render.add_argument("--output", type=Path, required=True)

    apply = commands.add_parser("apply-opencode", help="set the UD-IQ4_XS OpenCode default")
    apply.add_argument("--config", type=Path, default=_default_opencode_path())

    validate = commands.add_parser("validate-templates", help="check the portable ON/OFF templates")
    validate.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])

    verify = commands.add_parser("verify-assets", help="hash-check model, pack, and fork files")
    verify.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    verify.add_argument("--data-root", type=Path, default=Path.home() / "Strata-data")
    verify.add_argument(
        "--fork-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / FORK_RELATIVE,
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "render-profile":
            path = render_profile(
                args.strata_root.resolve(),
                args.mode,
                args.strata_root,
                args.data_root,
                args.output,
            )
            print(path)
        elif args.command == "apply-opencode":
            changed, backup = apply_opencode_default(args.config)
            if changed:
                print(f"Updated OpenCode default model to {MODEL_ID}")
                print(f"Backup: {backup}")
            else:
                print(f"Already configured: {MODEL_ID}")
        elif args.command == "validate-templates":
            for result in validate_templates(args.repository_root.resolve()):
                print(result)
        else:
            passed, results = verify_assets(
                args.repository_root.resolve(),
                args.data_root.resolve(),
                args.fork_root.resolve(),
            )
            for result in results:
                print(result)
            if not passed:
                return 1
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
