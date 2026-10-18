# NVFP4 fork + Unsloth UD-IQ4_XS for OpenCode

> 현재 통합 설치/복원 진입점은 [OPENCODE_QUICKSTART_KO.md](OPENCODE_QUICKSTART_KO.md)입니다. 아래의 이전 수동 설정 예시보다 통합 설치기를 우선 사용하세요.

This opt-in Windows setup uses the user's NVFP4 fork build with Unsloth
UD-IQ4_XS as the OpenCode default. It does not change Strata's installer,
include model weights or fork binaries, or store an OpenCode API key.

To use this Windows host from another Windows PC or Apple Silicon Mac, follow
[REMOTE_WINDOWS_MAC_SETUP.md](REMOTE_WINDOWS_MAC_SETUP.md). It keeps the model
on the host, requires an API key, scopes Windows Firewall to a Private local
subnet, and installs CUA Driver locally on each OpenCode client.

## Restore after reinstalling Windows

1. Clone the account fork and check out this setup branch:

    ```powershell
    git clone https://github.com/luiny0901-hue/Strata.git
    Set-Location Strata
    git fetch origin feature/opencode-session-recovery
    git switch --track origin/feature/opencode-session-recovery
    ```

2. Install Strata and its Python environment using
   [AI_SETUP.md](AI_SETUP.md). Download the Windows archive for NVFP4 fork
   `0.1.44.1-nvfp4.2` from the
   [fork releases](https://github.com/sergqwer/strata-nvfp4/releases), then
   extract it under:

    ```text
    <Strata checkout>\forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4
    ```

   Keep `release-manifest.json`. The `verify-assets` command checks the engine,
   vision engine, control vector, and release manifest against the recorded
   hashes.

   Apply the repository's SHA-guarded vision-pipe shutdown fix to this exact
   release before starting it:

    ```powershell
    & .\tools\apply_nvfp4_vision_pipe_fix.ps1
    ```

   The script verifies both source hashes, is safe to rerun after the fix is
   already applied, and refuses an unreviewed fork version. It changes only
   `Vision.close()` to close the encoder's stdin/stdout wrappers after
   child shutdown. It was derived from the inspected release's `server.py`
   SHA-256 `A9D6BD95557EAE37F36D7F452463CE08451561887A5F85802A8E58DB90029D58`;
   the locally patched file hashed to
   `647F3AFF8DE6197523395AC8177DD2AEFB4105EBFA5BC457C0F6053446019543`.
   See the [shutdown and OpenCode receipt](reports/2026-10-17-opencode-shutdown-followup.md).

3. Install the Hugging Face download command inside Strata's virtual
   environment, sign in if repository access requires it, and download the
   three IQ4_XS shards at the pinned official revision:

    ```powershell
    $python = ".\.venv\Scripts\python.exe"
    & $python -m pip install huggingface_hub
    & .\.venv\Scripts\hf.exe auth login

    $revision = "2c41bd2a0b3f51c503c11f1c7ed2e6bb34036beb"
    $download = "$env:USERPROFILE\Strata-data\downloads\iq4xs"
    $model = "$env:USERPROFILE\Strata-data\models\unsloth-UD-IQ4_XS"
    New-Item -ItemType Directory -Force $download, $model | Out-Null
    & .\.venv\Scripts\hf.exe download unsloth/Qwen3.8-Flash-Next-GGUF `
      UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf `
      UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf `
      UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf `
      --revision $revision --local-dir $download
    Move-Item "$download\UD-IQ4_XS\*.gguf" $model
    ```

   The pinned revision and all three shard hashes are recorded in the
   [artifact manifest](reports/2026-10-17-iq4xs-artifact-manifest.json). Their
   combined size is 93,682,584,224 bytes. The hashes in the manifest came from
   the successful download markers and match the official file metadata at
   that revision. `verify-assets` performs a full local re-hash after setup.

4. Build the native Strata pack using the first shard. The recorded pack used
   the compat-bf16 conversion:

    ```powershell
    $python = ".\.venv\Scripts\python.exe"
    $shard1 = "$env:USERPROFILE\Strata-data\models\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf"
    & $python .\tools\iq_pack.py --gguf $shard1 `
      --out "$env:USERPROFILE\Strata-data\packs\unsloth-ud-iq4_xs" `
      --compat-bf16
    ```

   Prepare the MTP runtime using [ORCA.md](ORCA.md) if it is not present.
   The profile also needs the BF16 vision projector at
   `Strata-data\models\mmproj-Qwen3.8-Flash-Next-BF16.gguf` and the
   checkout's `data\expert-profile.bin`.

5. Verify all pinned model, pack, engine, vision, MTP, and control-vector files.
   This reads about 97 GB and can take several minutes:

    ```powershell
    & .\.venv\Scripts\python.exe .\tools\iq4xs_opencode_setup.py verify-assets
    ```

6. Configure OpenCode's `strata` provider to use
   `http://127.0.0.1:8080/v1`. A secret-free example is in
   [opencode-strata-provider.example.json](opencode-strata-provider.example.json).
   Merge it into OpenCode's local config and replace `REPLACE_LOCALLY` only on
   this PC if Strata requires an API key. Do not commit a filled-in config.
   Then set the UD-IQ4_XS entry as OpenCode's default:

    ```powershell
    & .\.venv\Scripts\python.exe .\tools\iq4xs_opencode_setup.py apply-opencode
    ```

   Before modifying the config, the script saves a timestamped backup. It
   preserves the existing key and other settings, updates the selected model
   entry and default, and explicitly selects PowerShell 7 (`pwsh`) for Windows
   terminal commands. It refuses a missing Strata provider or a different base
   URL. The command also installs the bounded Windows and Linux command runners
   under `~/.config/opencode/scripts/` without changing neighboring scripts.

   The example also carries the verified long-project defaults: a 60-step
   build-agent ceiling, automatic compaction retaining 12,000 recent tokens
   with a 65,536-token buffer, and watcher ignores for common Unreal/Unity
   generated directories. The ignore list affects file-watcher events; it is
   not an access-control rule. Merge these keys into the global config while
   preserving existing permissions and credentials. Compaction is lossy and
   the step ceiling is finite; keep durable project state in `AGENTS.md` or a
   task handoff. Copy or merge
   [opencode-korean-long-project-instructions.example.md](opencode-korean-long-project-instructions.example.md)
   to `~/.config/opencode/KOREAN_INSTRUCTIONS.md`; merge it with personal
   instructions rather than overwriting them. Restart Rider/OpenCode after
   changing the global config.

   To run tests in Ubuntu WSL from Windows OpenCode, install the shell runner
   into the Linux user's config directory. From this checkout in PowerShell:

    ```powershell
    $runner = (Resolve-Path .\tools\opencode\run_bounded_command.sh).Path
    $drive = $runner.Substring(0, 1).ToLowerInvariant()
    $relative = $runner.Substring(3).Replace('\', '/')
    $linuxRunner = "/mnt/$drive/$relative"
    $bashTemplate = @'
set -eu
source="__SOURCE__"
target="$HOME/.config/opencode/scripts/run_bounded_command.sh"
mkdir -p "$(dirname "$target")"
if [ -f "$target" ] && ! cmp -s "$source" "$target"; then
  backup="$target.pre-iq4xs-$(date -u +%Y%m%dT%H%M%SZ)-$$.bak"
  cp -p "$target" "$backup"
fi
install -m 0755 "$source" "$target"
cmp -s "$source" "$target"
'@
    $bashScript = $bashTemplate.Replace('__SOURCE__', $linuxRunner)
    $encodedScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($bashScript))
    wsl.exe -d Ubuntu -- bash -lc "printf %s $encodedScript | base64 -d | bash"
    ```

   The Windows BAT starts Strata on `127.0.0.1`. In WSL NAT mode, Linux
   OpenCode cannot use that Windows loopback endpoint, and this setup does not
   expose the Strata server to the WSL network. On this PC, `opencode` typed
   inside Ubuntu resolves to the Windows CLI shim; use Windows OpenCode and
   invoke Linux tests explicitly with `wsl.exe -d Ubuntu -- bash -lc ...`.
   Native WSL OpenCode and a Linux Node toolchain are not configured by this
   setup.

7. Start one mode by double-clicking its batch file. Each batch file renders
   its portable profile, checks required files, and refuses an occupied port
   without stopping the process that owns it. Stop the running server before
   switching modes:

   - `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat`
   - `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.bat`

   Reopen the Rider/OpenCode chat after switching server mode.

## Recorded IQ4_XS profile

Both launch profiles use the tested NVFP4 fork plus UD-IQ4_XS combination on
RTX 3090 Ti GPU 1. They set a 262,144 context ceiling, 32,000 OpenCode output
limit, MTP spec 4 with minimum probability 0.5, automatic expert cache and
prefill, int8 KV with a 32,768-token resident window, 1,280 MiB VRAM reserve,
CPU vision encoding, and an 8,192-token reasoning budget. Sampling is
`temperature=1.0`, `top_p=0.95`, `top_k=20`.

The measured OpenCode task reached 41,507 prompt tokens, not the full 262K
ceiling. It sent no image, so this is not a vision performance result. A full
262K stress test was not performed; treat 262K as an experimental cap on a
24 GB card.

The ON profile loads the NVFP4 fork's refusal projection and sets
`uncensored=true`; the OFF profile loads the same projection and sets
`uncensored=false`. The fork's bundled notes list Unsloth models as a supported
family, but explicitly say UD-IQ4_XS was not measured. Therefore the ON/OFF
configuration and parser acceptance are testable here; the output-quality
impact for UD-IQ4_XS remains unverified. Read the release's
`data/uncensor/README.md` before enabling it.

## Test and comparison receipts

- [262K OpenCode model comparison](reports/2026-10-17-iq4xs-opencode-comparison.md)
  records the earlier IQ4_XS task timings and independent project-test counts.
- [Setup verification receipt](reports/2026-10-17-iq4xs-setup-verification.json)
  records this turn's OpenCode config change, parser checks, attempts, and
  unverified items without including the API key.
- The [historical Q4_K_XL report](reports/2026-10-17-q4kxl-opencode-comparison.md)
  is retained as comparison evidence; it is not the configured default.
- [IQ4_XS asset manifest](reports/2026-10-17-iq4xs-artifact-manifest.json)
  records expected asset sizes and hashes. Model hashes are pinned to the
  official Hugging Face revision above.

The portable setup tests use Python's standard library only and need no model
or GPU:

    ```powershell
    & .\.venv\Scripts\python.exe .\tools\test_iq4xs_opencode_setup.py
    & .\.venv\Scripts\python.exe .\tools\iq4xs_opencode_setup.py validate-templates
    ```

A full `verify-assets` run reads the entire model; do not treat a skipped or
interrupted run as a successful verification.
