// OpenCode 2.0.22: background shell resumes outlive the ACP prompt subscription.
export default {
  id: "strata.acp-foreground-guard",
  async setup(context) {
    if (process.env.OPENCODE_ACP_FOREGROUND_GUARD !== "1") return;
    await context.tool.transform((editor) => {
      for (const entry of editor.list()) {
        if (entry.name !== "shell") continue;
        editor.update(entry.id, (tool) => {
          const execute = tool.execute;
          tool.description += " ACP: background=true is blocked before execution. Run finite verification in foreground with an explicit timeout; do not promise a later automatic report.";
          tool.execute = async (input, context) => {
            if (input.background !== true) return execute(input, context);
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
  },
};
