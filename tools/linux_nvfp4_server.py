"""Prepare/run the existing IQ4_XS fork profile on Linux; never download artifacts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile

if __package__:
    from .iq4xs_opencode_setup import FORK_RELATIVE, PROFILE_STEM, SHARD_NAMES
else:
    from iq4xs_opencode_setup import FORK_RELATIVE, PROFILE_STEM, SHARD_NAMES


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--mode", choices=("on", "off"), default="on")
    parser.add_argument("--data-root", type=Path, default=Path.home() / "Strata-data")
    parser.add_argument("--fork-root", type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        parser.error("This entry point requires Linux. Use the BAT launchers on Windows.")
    if args.gpu < 0 or not 1 <= args.port <= 65535:
        parser.error("GPU must be nonnegative and port must be 1..65535")
    root = Path(__file__).resolve().parents[1]
    fork = (args.fork_root or root / FORK_RELATIVE).expanduser().resolve()
    data = args.data_root.expanduser().resolve()
    python = (args.python or root / ".venv/bin/python").expanduser().resolve()
    pack = data / "packs/unsloth-ud-iq4_xs"
    model = data / "models/unsloth-UD-IQ4_XS"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    private = config_home / "strata"
    if private.is_symlink():
        parser.error("Strata config directory must not be a symlink")
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path = private / "STRATA_API_KEY"
    if not key_path.exists():
        # Exclusive create preserves a key already used by remote clients.
        with open(key_path, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            stream.write(secrets.token_hex(32))
    if key_path.is_symlink() or not stat.S_ISREG(key_path.stat().st_mode) or key_path.stat().st_uid != os.getuid():
        parser.error("API key must be a regular file owned by the current user")
    os.chmod(key_path, 0o600)
    key = key_path.read_text(encoding="utf-8")
    if len(key) != 64 or any(c not in "0123456789abcdefABCDEF" for c in key):
        parser.error("API key must contain exactly 64 hexadecimal characters")
    replacements = {"@FORK_ROOT@": str(fork), "@PACK_ROOT@": str(pack),
                    "@MODEL_ROOT@": str(model), "@STRATA_ROOT@": str(root),
                    "@STRATA_DATA_ROOT@": str(data)}

    def convert(value):
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, str):
            # Convert template separators before inserting literal Linux paths.
            value = value.replace("\\", "/")
            for token, replacement in replacements.items():
                value = value.replace(token, replacement)
            return value
        return value

    template = root / "profiles" / f"{PROFILE_STEM}-{args.mode}.json.template"
    profile = convert(json.loads(template.read_text(encoding="utf-8")))
    profile["exe"] = str(fork / "engine/strata")
    profile["vision"]["exe"] = str(fork / "engine/strata-vision")
    profile["vision"]["max_tokens"] = 1024
    profile["gpu"] = args.gpu
    profile["port"] = args.port
    profiles = private / "profiles"
    profiles.mkdir(exist_ok=True)
    output = profiles / f"{PROFILE_STEM}-{args.mode}-linux.json"
    fd, temporary = tempfile.mkstemp(dir=profiles, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(profile, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Profile: {output}\nAPI key file: {key_path} (contents hidden)", flush=True)
    if args.action == "prepare":
        print("Prepared only; no server, downloads, hardware checks or tests were run.")
        return 0
    required = [python, fork / "serve/server.py", fork / "release-manifest.json",
                pack / "index.txt", pack / "tokenizer/tokenizer.json",
                root / "data/expert-profile.bin",
                data / "models/mmproj-Qwen3.8-Flash-Next-BF16.gguf",
                fork / "data/uncensor/qwen-nvfp4-gptq-uncensored.gguf"]
    required += [model / name for name in SHARD_NAMES]
    required += [data / "mtp/rt" / name for name in ("dense.bin", "experts.bin", "draft_vocab.bin")]
    required += [Path(profile["exe"]), Path(profile["vision"]["exe"])]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        parser.error("Missing artifacts (nothing downloaded):\n" + "\n".join(missing))
    for binary in (python, Path(profile["exe"]), Path(profile["vision"]["exe"])):
        if not os.access(binary, os.X_OK):
            parser.error(f"Not executable: {binary}")
    (data / "logs").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["STRATA_API_KEY"] = key
    os.chdir(fork)
    print(f"Starting {args.host}:{args.port}, GPU {args.gpu}, CPU vision; Linux runtime UNVERIFIED.", flush=True)
    os.execve(str(python), [str(python), "-m", "serve.server", "--engine", "strata",
                           "--config", str(output), "--host", args.host, "--port", str(args.port),
                           "--image-max-tokens", "1024"], env)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Server setup stopped: {exc}. Existing artifacts were preserved.", file=sys.stderr)
        raise SystemExit(2)
