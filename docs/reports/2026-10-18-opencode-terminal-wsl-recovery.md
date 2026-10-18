# OpenCode terminal and WSL execution recovery

Date: 2026-10-18 (KST)
Scope: OpenCode 2.0.22, Strata UD-IQ4_XS NVFP4 fork OFF/ON launchers, Windows and Ubuntu WSL command/test execution.

## Findings

- The global OpenCode config did not set `shell`; OpenCode was left to select a host shell automatically. The config now selects `pwsh` explicitly. OpenCode documents this property as applying to agent tool calls as well as the interactive terminal.
- Windows OpenCode could start WSL commands, but the Ubuntu environment is not a native OpenCode/Node setup on this PC: `opencode` resolves through the Windows CLI shim, `node` is missing in Ubuntu, and `npm` resolves to a Windows path. A Windows `npm` shim must not be reported as Linux Node testing.
- Strata binds to Windows loopback `127.0.0.1:8080`; in the observed WSL NAT configuration, Ubuntu could not reach that endpoint. The server was not exposed to the WSL network. Windows OpenCode can still invoke Linux-native tests explicitly through `wsl.exe`.
- Long or silent commands had no shared bounded runner contract. Two reusable runners now close stdin, record stdout/stderr per run, show elapsed-time heartbeats, enforce timeouts, preserve exit codes, and stop only the process tree created by that invocation.
- The indefinite hang reported by the user was not reproduced. The configuration and runner issues above were reproduced; long-project, GUI and production workloads remain unverified.

## Changes

- `tools/iq4xs_opencode_setup.py`: `apply-opencode` explicitly selects `pwsh` on Windows (or PowerShell fallback; `bash` on non-Windows), keeps existing config fields, creates a timestamped config backup, and installs both bounded runners idempotently under the OpenCode config directory.
- `tools/opencode/run_bounded_command.ps1` and `tools/opencode/run_bounded_command.sh`: reusable timeout, heartbeat, per-run logs and exit-code handling. Default timeout is 900 seconds; callers can set a smaller limit. The Windows runner uses PowerShell 7 when available; Linux uses GNU `timeout`.
- `tools/test_opencode_terminal_runners.py`: success, non-zero exit, timeout and owned child-tree cleanup checks for each host, with the opposite-host class explicitly skipped.
- `tools/test_iq4xs_opencode_setup.py`: shell selection, config preservation/idempotence and runner-install checks.
- `docs/opencode-strata-provider.example.json`, `docs/opencode-korean-long-project-instructions.example.md`, `docs/IQ4XS_NVFP4_OPENCODE_SETUP.md`: document the explicit shell, no-repeat policy, bounded execution and the WSL host/toolchain boundary.
- The Windows user config was backed up and updated to `shell: pwsh`; its existing provider API key and unrelated configuration were verified unchanged. The Korean global instructions were backed up and appended with the terminal/testing rules, preserving existing CUA guidance. The Windows runner was installed under `%USERPROFILE%\.config\opencode\scripts`; the Linux runner was installed under `~/.config/opencode/scripts` in Ubuntu with mode 0755.

## Verification

| Check | Result |
| --- | --- |
| Python compile for setup and test modules | PASS |
| Setup unit suite | PASS, 13 tests |
| Windows runner suite | PASS, 3 tests; 1 expected Linux-only class skip |
| Ubuntu WSL runner suite | PASS, 3 tests; 1 expected Windows-only class skip |
| Profile template validation | PASS, uncensored ON/OFF, context 262144 |
| Pre-fix disposable Node fixture | Expected failure, 0/2 tests passed; verified the test catches the defect |
| Pre-fix disposable WSL Python fixture | PASS, 2/2 |
| OFF BAT + OpenCode coding fixture before config update | PASS; Windows npm 2/2, WSL Python 2/2; task completed |
| ON BAT + OpenCode coding fixture before config update | PASS; Windows npm 2/2, WSL Python 2/2; task completed |
| OFF BAT + OpenCode after config update | PASS; OpenCode exit 0; Windows npm 1/1 and WSL Python 1/1; no test retry |
| `git diff --check` | PASS |

The final post-config task modified only `src/slug.js` in a disposable `%TEMP%` fixture. It ran the installed Windows runner and the installed Ubuntu runner once each. Node emitted a `MODULE_TYPELESS_PACKAGE_JSON` warning; the test passed. The WSL test confirms Linux Python invocation only, not JavaScript execution in Linux. All temporary Strata server processes launched for the audit were stopped; port 8080 was verified clear afterward.

## Attempt history

- A first OpenCode invocation used unsupported `--prompt`; it exited before starting a task. The prompt was passed positionally on subsequent calls.
- The first Windows runner test pass exposed a PowerShell `TextWriter` output-binding issue and a Windows console decoding issue in the Python harness. The runner and harness were corrected; a manual runner smoke test, then all 3 Windows tests passed.
- A first unit-test command imported `test_iq4xs_opencode_setup` from the wrong directory. Corrected to `unittest discover -s tools`; all 13 tests passed.
- A first template command used the missing WindowsApps `python.exe` alias. Corrected to the Strata virtual-environment Python; both templates passed validation.
- Initial WSL runner installation attempts lost Windows path separators/positional arguments. A later direct `bash -lc` install command also failed with `install: No such file`. No existing WSL file was overwritten in those attempts. The documented install path now derives `/mnt/<drive>/...` and pipes a base64-encoded script into Bash; the exact command was executed, and the resulting Linux file matched with mode 0755.
- One combined verification result exceeded the output limit, so each suite and template check was rerun separately and its result recorded above.
- A final git diff --check found an extra blank line at EOF in the setup guide after rewriting its WSL command example. The extra line was removed; the subsequent diff check passed.
- The user-reported indefinite loop did not occur in either BAT coding run or the post-config OFF run. These small CPU fixtures do not prove behavior for long-running builds, interactive installers, GPU tasks, or every Rider session.

## Remaining limitations

- Ubuntu Node.js is not installed. Linux JavaScript/Node tests are therefore NOT_RUN; install/use a Linux-native Node toolchain only when the user authorizes that environment change. Python tests ran under Linux.
- OpenCode is launched on Windows and reaches WSL by explicit `wsl.exe` calls. Native WSL OpenCode and Strata access from the WSL network were not enabled.
- The timeout runner can stop only descendants it created. Detached/escaped processes require separate ownership investigation; do not rerun a timed-out command automatically.
- Rider/OpenCode may need a restart to reload the global shell and instruction changes. The already-running application was not closed.
- No 262K long-context, large project, uncensored ON post-config, vision, production Strata, GPU, or GUI workload was tested as part of the terminal smoke.
