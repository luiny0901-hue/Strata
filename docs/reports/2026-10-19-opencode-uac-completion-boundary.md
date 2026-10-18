# OpenCode UAC and completion boundary — 2026-10-19

## Problem addressed

An unattended agent can become stuck when a shell command opens Windows UAC,
because that consent UI belongs to the secure desktop and is not a target that
CUA can safely approve. A separate behavior report described an agent making
additional calls after it had already reported the requested work complete.

## Applied boundary

- The global recovery installer appends five OpenCode V2 hard-deny policies for
  `Start-Process ... -Verb RunAs`, `runas`, `sudo`, and `gsudo` shell forms.
  The deny rules are appended after existing policies, and an invalid existing
  policy array aborts without changing the configuration.
- The installer appends the terminal OpenCode permission rule
  `action="*", resource="*", effect="allow"`. This lets the agent use normal
  user-account filesystem, shell, Git, external-directory, and MCP actions
  without an OpenCode approval dialog; the hard UAC policies still take
  precedence for elevation commands.
- The installed recovery instruction requires `BLOCKED_UAC` reporting instead
  of waiting, polling, retrying, or bypassing an elevation prompt. It tells the
  user the one required manual administrator action and resumes only after a
  new user request supplies its result.
- The recovery and CUA instructions define completion as an absorbing state:
  after all acceptance conditions are verified and any agent-owned CUA session
  is closed, the agent sends its final Korean response and does not start
  unrelated investigation, tool calls, or follow-up work.

## Validation

| Check | Result |
| --- | --- |
| Python OpenCode recovery/installer/remote setup tests | PASS — 28 tests |
| IQ4_XS profile and local OpenCode helper tests | PASS — 13 tests |
| Node CUA policy and catalogue tests | PASS — 11 tests |
| Profile JSON parsing | PASS |
| Current user OpenCode configuration | PASS — terminal wildcard allow rule, five UAC deny policies, and CUA direct-tool mode enabled |

No UAC prompt, Rider or Hermes session, real CUA input, Strata request, model,
or GPU process was started for this change. The policy prevents the known shell
elevation forms; it cannot prove that a model will obey every instruction or
that every third-party program uses one of those forms. A client must start a
new OpenCode session after the current task reaches a safe stopping point so
the new instructions are part of its conversation.
