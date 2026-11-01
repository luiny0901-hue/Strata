# OpenCode shutdown and long-project follow-up

## Scope

This change records a narrowly scoped fix for the NVFP4 fork vision encoder's
Python pipe cleanup and makes the local OpenCode long-project settings
re-applicable after a Windows reinstall. It does not include fork binaries,
model files, API keys, or the user's global config file.

## Shutdown diagnosis and patch

- A controlled startup and Ctrl+C shutdown reproduced `OSError: [Errno 22] Invalid argument` during Python file finalization. The traceback reached `Vision.shutdown()` at `serve/server.py:2606`.
- The vision encoder is launched with `stdin=PIPE` and `stdout=PIPE`. `Vision.close()` waited for or killed the child but did not explicitly close both text wrappers. A CPU-only child-pipe fixture reproduced the finalizer failure; closing both streams in cleanup made that fixture exit without the error.
- The pre-patch `server.py` SHA-256 was `A9D6BD95557EAE37F36D7F452463CE08451561887A5F85802A8E58DB90029D58`; the patched file was `647F3AFF8DE6197523395AC8177DD2AEFB4105EBFA5BC457C0F6053446019543`.
- `tools/apply_nvfp4_vision_pipe_fix.ps1` targets only the NVFP4 fork release `0.1.44.1-nvfp4.2`. It checks the exact preimage and postimage hashes, refuses other versions, and is idempotent after the fix is applied.
- The first hand-written diff hunk was rejected during `git apply --check`; rather than retain a fragile patch file, it was replaced with the SHA-guarded script. PowerShell parsed the script with zero syntax errors. On a pristine copy of the pre-patch source it applied the fix, produced the expected SHA-256, and a second run reported the fix already applied without changing the hash.
- After patching, the local NVFP4 server reached ready, `/v1/models` returned the expected model, and Ctrl+C shutdown printed `stopped` without the OSError. Port 8080 and the Strata child-process check were clear afterward.
- The terminal wrapper returned status 1 for Ctrl+C even for a minimal Python control script that explicitly exits 0. The actual server child exit code was therefore not independently verified.

## OpenCode settings recorded for reuse

The secret-free provider example now includes the local settings that were
validated with `opencode debug config`:

- `agents.build.steps`: 100.
- Automatic compaction, keeping 20,000 recent tokens with a 32,768-token buffer.
- An explicit home-relative global Korean instructions path.
- Watcher ignores for common Unreal/Unity generated folders.

The local model, 262,144 context setting, output limit, API key, and permission
rules were preserved. The global API key and personalized settings were not
copied into this repository. The committed instructions example adds
long-project checkpoints, scoped discovery, loop stopping, and Korean replies.

## Validation and limits

- The local `opencode.json` parsed successfully and `opencode debug config`
  reported the expected settings.
- The earlier isolated multi-file OpenCode receipts recorded 17 passing tests
  for uncensored ON and 18 for OFF, with no failures or skips in those final
  runs. Those runs did not exercise the full 262,144-token context ceiling.
- A fresh long-duration task with these updated settings, the Rider plugin UI,
  image input, and actual Strata protocol behavior were not re-tested.
- The model was loaded for the startup/shutdown diagnostic, but no inference
  request was sent. No model assets, operational profile, or GPU power setting
  was modified.

See [the setup instructions](../IQ4XS_NVFP4_OPENCODE_SETUP.md) for the
re-installation flow. The detailed prior run log remains at
`C:\Users\luiny\AppData\Local\Strata\validation\opencode-multifile-ab-20261017\RESULTS.md`
on the original PC and is not required for reinstalling the documented setup.
