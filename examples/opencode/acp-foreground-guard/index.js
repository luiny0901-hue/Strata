// OpenCode 2.0.22: background shell resumes outlive the ACP prompt subscription.
import {AsyncLocalStorage} from 'node:async_hooks';
import {mkdtemp, writeFile, unlink, rmdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';

export default {
  id: "strata.acp-foreground-guard",
  async setup(context) {
    if (process.env.OPENCODE_ACP_FOREGROUND_GUARD !== "1") return;
    const shellScope = new AsyncLocalStorage();
    if (process.env.OPENCODE_ACP_TERMINAL_GUARD === '1' && context.shell) await context.shell.hook('create.before', async invocation => {
      Object.assign(invocation.env, {CI:'true', NO_COLOR:'1', GIT_TERMINAL_PROMPT:'0', GCM_INTERACTIVE:'Never', PYTHONIOENCODING:'utf-8', PYTHONUNBUFFERED:'1'});
      if (process.platform !== 'win32' || !/^(pwsh|powershell)(\.exe)?$/i.test(path.basename(invocation.shell))) return;
      const scope = shellScope.getStore();
      if (!scope || !context.options?.bootstrapPath) throw new Error('ACP_TERMINAL_SETUP_REQUIRED: reinstall the ACP guard with its PowerShell bootstrap asset.');
      const directory = await mkdtemp(path.join(tmpdir(), 'opencode-command-'));
      const file = path.join(directory, 'command.ps1');
      scope.files.push({file, directory});
      await writeFile(file, '\ufeff' + invocation.command, {encoding:'utf8', mode:0o600});
      const quote = value => "'" + value.replaceAll("'", "''") + "'";
      invocation.command = `& ${quote(context.options.bootstrapPath)} -CommandFile ${quote(file)}; exit $LASTEXITCODE`;
    });
    await context.tool.transform((editor) => {
      for (const entry of editor.list()) {
        if (entry.name !== "shell" && entry.name !== "subagent") continue;
        editor.update(entry.id, (tool) => {
          const execute = tool.execute;
          tool.description += " ACP: all required work must settle inside the active request. Shell background=true is blocked. Subagents are awaited, including when background=true is requested. Never end with unfinished mandatory work or promise a later automatic report.";
          tool.execute = async (input, context) => {
            // Do not start a queued shell/child after the owning request was stopped.
            context.signal?.throwIfAborted();
            if (entry.name === "subagent") return execute({...input, background: false}, context);
            if (input.background !== true) {
              const scope = {files:[]};
              // Zero explicitly disables the core timeout. ACP must keep a finite deadline.
              const bounded = input.timeout === 0 ? {...input, timeout: 120000} : input;
              try { return await shellScope.run(scope, () => execute(bounded, context)); }
              finally {
                for (const {file, directory} of scope.files) {
                  await unlink(file).catch(()=>{});
                  await rmdir(directory).catch(()=>{});
                }
              }
            }
            const text = "ACP_BACKGROUND_BLOCKED: Command was NOT executed. This ACP client cannot receive a reliable final report after background shell auto-resume. For finite work, retry with background=false and a sufficient finite timeout (for 300 seconds of observation, use 420000 ms). For a persistent service, use an explicit detached launch with PID and health verification only when that service is requested. Do not claim this command succeeded or end with a promise to report later.";
            return {
              output: { output: text, exit: 1, truncated: false, status: "completed" },
              content: [{ type: "text", text }],
              metadata: { status: "completed", acpBackgroundBlocked: true },
            };
          };
        });
      }
    });
    // Separate opt-in: an existing process must not acquire a new turn gate on hot reload.
    if (process.env.OPENCODE_ACP_TURN_GUARD !== "1") return;
    const turns = new Map();
    await context.session.hook("prompt", event => {
      if (turns.size >= 512 && !turns.has(event.sessionID)) turns.delete(turns.keys().next().value);
      turns.set(event.sessionID, {armed: true, idle: undefined});
    });
    await context.session.hook("model.request", async event => {
      if (event.kind !== "primary") return;
      const state = turns.get(event.sessionID);
      if (!state) throw new Error("ACP_OUT_OF_TURN_BLOCKED: no new user/awaited-child prompt owns this inference. The prior ACP request may already be finished; automatic resume was stopped before contacting the model.");
      const info = await context.session.get({sessionID: event.sessionID});
      const idle = JSON.stringify(info.time?.idle ?? null);
      if (state.armed) {
        state.idle = idle;
        state.armed = false;
      } else if (idle !== state.idle) {
        throw new Error("ACP_OUT_OF_TURN_BLOCKED: the owning execution has already ended or was cancelled. Late automatic notifications cannot start hidden work. A new user prompt is required.");
      }
    });
    await context.session.hook("context", event => {
      event.system.push({type: "text", text: "ACP 요청이 끝나면 작업을 종료한다. 필수 자식 에이전트 결과와 도구 결과를 현재 요청 안에서 기다리고 완료 조건을 확인한 뒤 최종 답변한다. 백그라운드 완료 알림을 기다린다고 말하며 끝내지 않는다. 새 사용자 요청 없는 자동 재개는 차단된다. 외부에서 명시적으로 요청한 상시 서비스의 실행 상태는 최종 보고에 별도로 표시한다."});
      for (const name of ["shell", "subagent"]) {
        const background = event.tools[name]?.input?.properties?.background;
        if (background) { background.enum = [false]; background.default = false; background.description = "ACP requires foreground completion inside this request. Use false."; }
      }
      const timeout = event.tools.shell?.input?.properties?.timeout;
      if (timeout) {
        timeout.minimum = Math.max(timeout.minimum ?? 0, 1);
        timeout.description = "Finite timeout in milliseconds. Zero/unlimited is not allowed in ACP. Use an explicit task-appropriate deadline; do not rerun a timed-out command until its side effects are checked.";
      }
    });
    await context.session.hook("retry", event => {
      // Preserve core's permanent-error/cancellation decision and Retry-After minimum.
      // Refuse an excessive delay rather than retrying earlier than the server requested.
      if (event.decision.retry && (event.attempt > 4 || event.decision.delay > 30000)) {
        event.decision = {retry: false};
      }
    });
    await context.session.hook("compaction", event => {
      event.system.push({type: "text", text: "<!-- strata-summary-basic:v1 --> Internal checkpoint: keep required English headings, concise Korean contents, unfinished criteria, changed paths, verified results, blockers and next action. Do not reactivate completed work, call tools or invent verification."});
    });
  },
};
