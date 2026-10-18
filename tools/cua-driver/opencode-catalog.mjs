import { spawn } from "node:child_process";
import readline from "node:readline";

// Catalog discovery is read-only. All actual actions use the policy-bound process.
export async function readCatalog(driver, args, allowed, { timeoutMs = 20000 } = {}) {
  const env = { ...process.env };
  for (const key of ["CUA_DRIVER_POLICY_FILE", "CUA_DRIVER_MANAGED_POLICY_FILE",
    "CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_CAPABILITY_MANIFEST_FILE",
    "CUA_DRIVER_CAPABILITY_MANIFEST_APPROVED"]) delete env[key];
  const child = spawn(driver, args, { stdio: ["pipe", "pipe", "inherit"], env, windowsHide: true });
  const lines = readline.createInterface({ input: child.stdout });
  const pending = new Map();
  let failure;
  const fail = (error) => {
    failure = error;
    for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(error); }
    pending.clear();
  };
  child.on("error", fail);
  child.stdin.on("error", fail);
  child.on("exit", (code) => fail(new Error(`catalog process exited (${code})`)));
  lines.on("line", (line) => {
    let msg;
    try { msg = JSON.parse(line); } catch { return; }
    const entry = pending.get(String(msg.id));
    if (!entry) return;
    pending.delete(String(msg.id));
    clearTimeout(entry.timer);
    entry.resolve(msg);
  });
  let id = 0;
  const request = (method, params = {}) => new Promise((resolve, reject) => {
    if (failure) { reject(failure); return; }
    const requestId = ++id;
    const timer = setTimeout(() => {
      pending.delete(String(requestId));
      reject(new Error(`catalog ${method} timed out`));
    }, timeoutMs);
    pending.set(String(requestId), { resolve, reject, timer });
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: requestId, method, params })}\n`);
  });
  try {
    const init = await request("initialize", {
      protocolVersion: "2024-11-05", capabilities: {},
      clientInfo: { name: "opencode-cua-window-policy", version: "1.2" },
    });
    if (init.error || !init.result?.serverInfo) throw new Error("Cua catalog initialize failed");
    child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');
    const response = await request("tools/list");
    if (response.error || !Array.isArray(response.result?.tools)) throw new Error("Cua tool catalog unavailable");
    return response.result.tools.filter((tool) => allowed.has(tool.name));
  } finally {
    fail(new Error("catalog closed"));
    lines.close();
    child.stdin.end();
    await new Promise((resolve) => {
      if (child.exitCode !== null || !child.pid) { resolve(); return; }
      const timer = setTimeout(() => { child.kill(); resolve(); }, 3000);
      child.once("exit", () => { clearTimeout(timer); resolve(); });
    });
  }
}
