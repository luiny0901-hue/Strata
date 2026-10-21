import { spawn } from "node:child_process";
import readline from "node:readline";
import { exposedTools, isSafeCall, prepareCall, restrictCatalog } from "./opencode-policy.mjs";

import { readCatalog } from "./opencode-catalog.mjs";
import { WindowGrounding, GroundingError } from "./opencode-grounding.mjs";

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

let tools;
try { tools = await readCatalog(driver, ["mcp"], exposedTools); }
catch (error) { console.error(`CUA catalog unavailable: ${error.message}`); process.exit(3); }
if (tools.length !== exposedTools.size) {
  console.error(`Expected ${exposedTools.size} safe Cua tools, found ${tools.length}.`);
  process.exit(3);
}
tools = restrictCatalog(tools);
const grounding = new WindowGrounding({captureTools: new Set(tools.filter(tool => tool.inputSchema?.properties?.capture_id).map(tool => tool.name))});
const calls = new Map();

const action = spawn(driver, ["mcp"], { stdio: ["pipe", "pipe", "inherit"], env: process.env, windowsHide: true });
const actionLines = readline.createInterface({ input: action.stdout });
const parentLines = readline.createInterface({ input: process.stdin });
const initializeIds = new Set();
const pendingIds = new Set();
function driverFailed(message) {
  for (const id of pendingIds) errorResult(id, "driver_unavailable", `${message}. Do not replay an input automatically; inspect the window before recovery.`);
  pendingIds.clear();
  parentLines.close();
  process.stdin.destroy();
  action.stdin.destroy();
  process.exitCode = 1;
}
action.on("error", () => driverFailed("CUA Driver could not start"));
action.stdin.on("error", () => driverFailed("CUA Driver input pipe closed"));
actionLines.on("line", (line) => {
  try {
    const msg = JSON.parse(line);
    if (msg.id !== undefined) pendingIds.delete(msg.id);
    if (msg.id !== undefined && calls.has(msg.id)) {
      const ticket = calls.get(msg.id);
      calls.delete(msg.id);
      grounding.response(ticket, msg.result);
    }
    if (msg.id !== undefined && initializeIds.has(String(msg.id)) && msg.result) {
      initializeIds.delete(String(msg.id));
      msg.result.instructions = [
        "GUI가 필요한 작업에서 CUA Driver를 자동으로 사용합니다. 작업 시작 때 list_windows로 정확한 창의 PID/HWND를 한 번 찾고, 같은 작업 중에는 재사용하세요. 앱 재시작, 새 창 생성, ID 오류나 불일치가 있을 때만 다시 목록을 읽으세요.",
        "첫 동작 전 get_window_state로 화면을 확인하세요. 표준 컨트롤은 좌표보다 element_token을 우선 사용하고, 캔버스나 접근성 정보가 없는 표면에서만 좌표를 사용하세요.",
        "각 동작 뒤 상태 확인이 필요하면 직전 snapshot_id를 since에 전달하고 include_screenshot:false로 변경된 접근성 트리만 읽으세요. 다음 동작은 새 snapshot의 토큰을 사용하세요. 픽셀 변화 확인, 캔버스 조작, 불확실한 결과에서만 스크린샷을 요청하세요. 기본 tree_format은 markdown이며 both/full_output은 필요한 경우에만 사용하세요.",
        "입력은 정확한 같은 창에 background만 사용합니다. foreground, SendInput, 사용자 마우스 및 전역 입력은 금지합니다. background_unavailable 또는 확인된 무동작이면 BACKGROUND_ONLY_UNSUPPORTED로 해당 GUI 단계와 의존 작업을 보류하세요. 다른 입력 경로로 전환하지 마세요. 이미 허가된 독립 코드 작업만 이어가고 차단된 완료 조건은 따로 보고하세요.",
        "데스크톱 전체 대상은 금지합니다. 조작 결과가 불명확하거나 권한이 거부되면 멈추고 보고하세요. 전역/네이티브 입력 또는 셸로 우회하지 않습니다. 에이전트 커서는 물리 포인터와 별도입니다.",
      ].join(" ");
      process.stdout.write(`${JSON.stringify(msg)}\n`);
    } else {
      process.stdout.write(`${JSON.stringify(msg)}\n`);
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
      errorResult(msg.id, "permission_denied", `Cua policy refused '${name}': exact window and background delivery only. Foreground, global input and the user's mouse are forbidden. Do not bypass via shell/native input.`);
      return;
    }
    try {
      const ticket = grounding.request(name, prepareCall(name, args));
      calls.set(msg.id, ticket);
      msg.params.arguments = ticket.args;
    } catch (error) {
      if (!(error instanceof GroundingError)) throw error;
      errorResult(msg.id, error.code, error.message);
      return;
    }
  }
  if (msg.method === "initialize" && msg.id !== undefined) initializeIds.add(String(msg.id));

  if (action.exitCode !== null || action.stdin.destroyed) {
    if (msg.id !== undefined) jsonLine({ jsonrpc: "2.0", id: msg.id, error: { code: -32000, message: "Cua Driver process is unavailable" } });
    return;
  }
  if (msg.id !== undefined) pendingIds.add(msg.id);
  action.stdin.write(`${JSON.stringify(msg)}\n`);
});

parentLines.on("close", () => action.stdin.end());
process.on("SIGINT", () => { action.kill(); process.exit(130); });
process.on("SIGTERM", () => { action.kill(); process.exit(143); });
action.on("exit", (code) => {
  if (pendingIds.size || (code !== 0 && code !== null)) driverFailed(`CUA Driver exited (${code})`);
});
