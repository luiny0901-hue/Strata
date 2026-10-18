import { spawn } from "node:child_process";
import readline from "node:readline";
import { exposedTools, isSafeCall } from "./opencode-policy.mjs";

const driver = process.env.CUA_DRIVER_EXE;
const policy = process.env.CUA_DRIVER_POLICY_FILE;
if (!driver || !policy) {
  console.error("CUA_DRIVER_EXE and CUA_DRIVER_POLICY_FILE must be set.");
  process.exit(2);
}

function jsonLine(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function errorResult(id, code, message) {
  jsonLine({
    jsonrpc: "2.0",
    id,
    result: {
      content: [{ type: "text", text: message }],
      isError: true,
      structuredContent: { code },
    },
  });
}

async function catalogTools() {
  const env = { ...process.env };
  delete env.CUA_DRIVER_POLICY_FILE;
  delete env.CUA_DRIVER_MANAGED_POLICY_FILE;
  delete env.CUA_DRIVER_PERMISSION_MODE;
  delete env.CUA_DRIVER_CAPABILITY_MANIFEST_FILE;
  delete env.CUA_DRIVER_CAPABILITY_MANIFEST_APPROVED;

  const child = spawn(driver, ["mcp"], { stdio: ["pipe", "pipe", "inherit"], env });
  const lines = readline.createInterface({ input: child.stdout });
  const pending = new Map();
  lines.on("line", (line) => {
    try {
      const msg = JSON.parse(line);
      if (msg.id !== undefined && pending.has(String(msg.id))) {
        pending.get(String(msg.id))(msg);
        pending.delete(String(msg.id));
      }
    } catch { /* ignore non-JSON diagnostics */ }
  });
  child.on("exit", (code) => {
    for (const reject of pending.values()) reject(new Error(`catalog process exited (${code})`));
    pending.clear();
  });
  let id = 1;
  const request = (method, params = {}) => new Promise((resolve, reject) => {
    const requestId = id++;
    const timer = setTimeout(() => {
      pending.delete(String(requestId));
      reject(new Error(`catalog ${method} timed out`));
    }, 20000);
    pending.set(String(requestId), (msg) => { clearTimeout(timer); resolve(msg); });
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: requestId, method, params })}\n`);
  });

  try {
    const init = await request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "opencode-cua-window-policy", version: "1.1" },
    });
    if (init.error || !init.result?.serverInfo) throw new Error("Cua catalog initialize failed");
    child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');
    const response = await request("tools/list");
    if (response.error || !Array.isArray(response.result?.tools)) throw new Error("Cua tool catalog unavailable");
    return response.result.tools.filter((tool) => exposedTools.has(tool.name));
  } finally {
    lines.close();
    child.stdin.end();
    await new Promise((resolve) => {
      if (child.exitCode !== null) resolve();
      else child.once("exit", resolve);
      setTimeout(() => { if (child.exitCode === null) child.kill(); resolve(); }, 3000).unref();
    });
  }
}

const tools = await catalogTools();
if (tools.length !== exposedTools.size) {
  console.error(`Expected ${exposedTools.size} safe Cua tools, found ${tools.length}.`);
  process.exit(3);
}

const action = spawn(driver, ["mcp"], { stdio: ["pipe", "pipe", "inherit"], env: process.env });
const actionLines = readline.createInterface({ input: action.stdout });
const parentLines = readline.createInterface({ input: process.stdin });
const initializeIds = new Set();
actionLines.on("line", (line) => {
  try {
    const msg = JSON.parse(line);
    if (msg.id !== undefined && initializeIds.has(String(msg.id)) && msg.result) {
      initializeIds.delete(String(msg.id));
      msg.result.instructions = "GUI가 필요한 작업에서 CUA Driver를 자동 사용합니다. 입력 전 정확한 창의 PID와 HWND 및 화면 상태를 확인하세요. 입력은 background부터 시도합니다. 드라이버가 background_unavailable을 반환하거나 새 화면 확인으로 동작이 실행되지 않았음이 명백한 경우에만, 동일 동작을 같은 정확한 창에 foreground로 한 번 재시도할 수 있습니다. foreground는 잠시 대상 창을 활성화하므로 사용자가 입력 중이면 사용하지 않습니다. 데스크톱 전체 대상은 금지합니다. 각 조작 뒤 화면을 다시 읽고 결과를 확인하며, 권한 거부나 대상이 불분명한 경우 멈춥니다. 전역/네이티브 입력 또는 셸로 우회하지 않습니다. 에이전트 커서는 물리 포인터와 별도입니다.";
      process.stdout.write(`${JSON.stringify(msg)}\n`);
    } else {
      process.stdout.write(`${line}\n`);
    }
  } catch {
    process.stdout.write(`${line}\n`);
  }
});

parentLines.on("line", (line) => {
  let msg;
  try { msg = JSON.parse(line); }
  catch { jsonLine({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Invalid JSON" } }); return; }

  if (msg.method === "tools/list" && msg.id !== undefined) {
    jsonLine({ jsonrpc: "2.0", id: msg.id, result: { tools } });
    return;
  }
  if (msg.method === "tools/call" && msg.id !== undefined) {
    const name = msg.params?.name;
    const args = msg.params?.arguments ?? {};
    if (!isSafeCall(name, args)) {
      errorResult(msg.id, "permission_denied", `Cua safety policy refused '${name}': a supported tool and exact window target are required; desktop-wide input remains disabled.`);
      return;
    }
  }
  if (msg.method === "initialize" && msg.id !== undefined) initializeIds.add(String(msg.id));

  if (action.exitCode !== null || action.stdin.destroyed) {
    if (msg.id !== undefined) jsonLine({ jsonrpc: "2.0", id: msg.id, error: { code: -32000, message: "Cua Driver process is unavailable" } });
    return;
  }
  action.stdin.write(`${JSON.stringify(msg)}\n`);
});

parentLines.on("close", () => action.stdin.end());
process.on("SIGINT", () => { action.kill(); process.exit(130); });
process.on("SIGTERM", () => { action.kill(); process.exit(143); });
action.on("exit", (code) => { if (code !== 0 && code !== null) process.exitCode = code; });
