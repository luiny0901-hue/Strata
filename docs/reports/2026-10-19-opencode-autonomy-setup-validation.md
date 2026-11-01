# OpenCode autonomous setup validation — 2026-10-19

## Scope

This record covers the portable OpenCode configuration, bounded terminal runners,
and local CUA Driver MCP wrapper used with the Unsloth UD-IQ4_XS NVFP4-fork
launchers. It does not validate Rider, Hermes, a real Strata inference request,
GPU performance, a model load, or a GUI action.

## Verified revision

The final Git commit and remote branch are recorded by the release commit that
adds this evidence file. The validation commands below were run from the same
working tree immediately before that commit.

## Windows results

| Check | Result |
| --- | --- |
| `tools/test_iq4xs_opencode_setup.py` | PASS — 13 tests |
| OpenCode/CUA/session/remote setup unittest suite | PASS — 25 tests |
| CUA policy and catalogue Node tests | PASS — 11 tests |
| PowerShell firewall helper tests | PASS — 11 cases |
| Windows terminal runner tests | PASS — 3 tests |
| Direct CUA MCP handshake and read-only tool catalogue | PASS — `cua-driver connected` |
| Profile rendering comparison against the current local profile pair | PASS — ON/OFF settings matched |

The first direct MCP validation attempt failed because its *validation command*
did not set the wrapper path environment variable. It did not start Strata or
send a CUA action. A second read-only run passed after that command error was
corrected. A second validation assumption also expected prefixed tool names;
the current driver reports standard MCP names such as `list_windows` and
`get_window_state`. The wrapper exposed those safe tools and did not expose
`kill_app`.

## WSL Ubuntu results

| Check | Result |
| --- | --- |
| OpenCode/CUA/session/remote setup unittest suite | PASS — 25 tests |
| IQ4_XS profile setup tests | PASS — 13 tests |
| `tools/opencode/run_bounded_command.sh` simple bounded command | PASS |
| Node-based CUA policy/catalogue tests | NOT_RUN — `node` was not installed in this WSL distribution |

No runtime, Node package, model, or GPU component was installed in WSL to turn
the last item into a pass.

## Operational boundary

The ON and OFF BAT files retain their existing runtime behavior. Their shared
OpenCode path uses CPU vision encoding and a 1024 image-token budget; no live
image request or performance benchmark was part of this validation.

For a fresh Windows installation, use `SETUP-OPENCODE.bat`. For macOS and
Linux clients, use `setup-opencode.sh` after the documented prerequisites are
available. The remote installers generate local credentials and policy assets;
they do not copy an existing secret. `doctor` verifies the installed wrapper
asset hashes before reporting the client ready.
