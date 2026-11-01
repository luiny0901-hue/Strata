#!/usr/bin/env python3
"""Render and validate portable Strata UD-IQ4_XS runtime profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


MODEL_KEY = "qwen3.8-flash-next-unsloth-ud-iq4_xs"
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
CONTEXT_SIZES = (262144, 1048576)


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
    context: int = 262144,
) -> Path:
    if mode not in ("on", "off"):
        raise ValueError("mode must be 'on' or 'off'")
    if type(context) is not int or context not in CONTEXT_SIZES:
        raise ValueError("context must be 262144 or 1048576")
    repository_root = repository_root.resolve()
    strata_root = strata_root.resolve()
    data_root = data_root.resolve()
    if __package__:
        from .strata_fork_update import selected_fork
    else:
        from strata_fork_update import selected_fork
    fork_root = selected_fork(strata_root).resolve()
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
    if context != 262144:
        args = profile["args"]
        args[args.index("--max-context") + 1] = str(context)
        # Keep trained rotations for short dialogs and extend only when needed.
        args.extend(["--rope-scaling", "dynamic", "--rope-scale", "4"])
        profile["rope_auto"] = True
        profile["log"] = str(Path(profile["log"]).with_name(Path(profile["log"]).stem + "-1m.log"))
    gpu_override = os.environ.get("STRATA_SERVER_GPU")
    if gpu_override is not None:
        gpu = int(gpu_override)
        if gpu < 0:
            raise ValueError("STRATA_SERVER_GPU must be a nonnegative GPU index")
        profile["gpu"] = gpu
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


def validate_templates(repository_root: Path) -> list[str]:
    results: list[str] = []
    for mode, expected in (("on", True), ("off", False)):
        profile = json.loads(_template_path(repository_root, mode).read_text(encoding="utf-8"))
        args = profile.get("args", [])
        assert profile.get("uncensored") is expected, f"{mode}: incorrect uncensored default"
        assert bool(profile.get("ban_cjk_tokens")) is (mode == "on"), f"{mode}: wrong CJK ban default"
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
        # On the 3090 Ti box 448 left 357 MiB of VRAM free at load and prefill died
        # of an illegal memory access under WDDM paging (#2065). Free at load equals
        # 357 + (reserve - 448); a 2026-11-01 sweep crashed at 549 MiB free and
        # passed 2/2 at 679 (this value), accepting the engine's below-1024 note at
        # request start. Measured details: docs/STRATA_1M_CONTEXT_KO.md.
        assert args[args.index("--vram-reserve-mib") + 1] == "768"
        assert args[args.index("--prefill") + 1] == "auto:8192"
        for option, expected_cache in (
            ("--conversation-cache-mib", "8192"),
            ("--conversation-cache-slots", "2"),
            ("--conversation-cache-min-free-mib", "8192"),
            ("--conversation-cache-min-tokens", "16384"),
        ):
            if mode == "on":
                assert args.count(option) == 1 and args[args.index(option) + 1] == expected_cache, f"{mode}: wrong {option}"
            else:
                assert option not in args, f"{mode}: unmeasured conversation cache"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    selected = commands.add_parser("fork-root", help="resolve the shared active NVFP4 bundle")
    selected.add_argument("--strata-root", type=Path, required=True)

    render = commands.add_parser("render-profile", help="render one ON/OFF runtime profile")
    render.add_argument("--mode", choices=("on", "off"), required=True)
    render.add_argument("--strata-root", type=Path, required=True)
    render.add_argument("--data-root", type=Path, default=Path.home() / "Strata-data")
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--context", type=int, choices=CONTEXT_SIZES, default=262144)

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
        if args.command == "fork-root":
            if __package__:
                from .strata_fork_update import selected_fork
            else:
                from strata_fork_update import selected_fork
            print(selected_fork(args.strata_root.resolve()))
        elif args.command == "render-profile":
            path = render_profile(
                args.strata_root.resolve(),
                args.mode,
                args.strata_root,
                args.data_root,
                args.output,
                args.context,
            )
            print(path)
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
