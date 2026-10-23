import { approvedForeground, foregroundTool } from "./opencode-foreground.mjs";
import {TaskApproval} from './opencode-task-approval.mjs';
import { spawn } from "node:child_process";
import readline from "node:readline";
import { exposedTools, isSafeCall, prepareCall, restrictCatalog, restrictActionResult } from "./opencode-policy.mjs";

import { readCatalog } from "./opencode-catalog.mjs";
import { WindowGrounding, GroundingError } from "./opencode-grounding.mjs";
import { RequestDeadlines } from "./opencode-request-lifecycle.mjs";

const driver = process.env.CUA_DRIVER_EXE;
const policy = process.env.CUA_DRIVER_POLICY_FILE;
if (!driver || !policy) {
  console.error("CUA_DRIVER_EXE and CUA_DRIVER_POLICY_FILE must be set.");
  process.exit(2);
}

function jsonLine(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function validEnvelope(msg) {
  if (!msg || typeof msg !== 'object' || Array.isArray(msg) || msg.jsonrpc !== '2.0') return false;
  const id = msg.id;
  if (id !== undefined && !(typeof id === 'string' || (typeof id === 'number' && Number.isFinite(id)))) return false;
  if (typeof msg.method === 'string' && msg.method.length > 0) return true;
  return id !== undefined && (Object.hasOwn(msg, 'result') !== Object.hasOwn(msg, 'error'));
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
let closing = false;
let consent;
let chatElicitation=false;
const chatApprovals=new Map();
let chatSerial=0;
function confirmInChat(preview,signal) {
  if(!chatElicitation)throw new Error('This client does not support chat approval. Reconnect through the updated Rider ACP launcher or a form-capable OpenCode client. No input dispatched.');
  const id=`strata-cua-chat-${++chatSerial}`;
  return new Promise(resolve=>{
    const finish=value=>{clearTimeout(timer);signal.removeEventListener('abort',abort);chatApprovals.delete(id);resolve(value);};
    const abort=()=>finish(false);
    const timer=setTimeout(abort,120000);
    chatApprovals.set(id,finish);
    signal.addEventListener('abort',abort,{once:true});
    if(signal.aborted){abort();return;}
    jsonLine({jsonrpc:'2.0',id,method:'elicitation/create',params:{mode:'form',message:preview,
      requestedSchema:{type:'object',properties:{allow:{type:'boolean',title:'이번 동작을 허용합니다',default:false}},required:['allow']}}});
  });
}
const taskApprovals=new TaskApproval(process.env.STRATA_CUA_TASK_STATE);
const pending = new RequestDeadlines({onTimeout: () => driverFailed('CUA Driver deadline exceeded; input side effects are unknown', 'driver_timeout')});
function releaseCalls() {
  for (const ticket of calls.values()) grounding.response(ticket, {isError:true});
  calls.clear();
  initializeIds.clear();
}
function stopDriver() {
  taskApprovals.close();
  consent?.controller.abort();
  pending.close();
  releaseCalls();
  action.stdin.end();
  const timer = setTimeout(() => action.kill(), 3000);
  timer.unref();
  action.once('exit', () => clearTimeout(timer));
}
function driverFailed(message, code = 'driver_unavailable') {
  if (closing) return;
  closing = true;
  for (const id of pending.ids()) errorResult(id, code, `${message}. Do not replay an input automatically; inspect the window before recovery.`);
  stopDriver();
  parentLines.close();
  process.stdin.destroy();
  process.exitCode = 1;
}
action.on("error", () => driverFailed("CUA Driver could not start"));
action.stdin.on("error", () => driverFailed("CUA Driver input pipe closed"));
actionLines.on("line", (line) => {
  if (closing) return; // Never deliver a late successful result after timeout/EOF.
  try {
    const msg = JSON.parse(line);
    if (!validEnvelope(msg)) throw new Error('Invalid driver JSON-RPC envelope');
    if (msg.id !== undefined) pending.complete(msg.id);
    if (msg.id !== undefined && calls.has(msg.id)) {
      const ticket = calls.get(msg.id);
      calls.delete(msg.id);
      grounding.response(ticket, msg.result);
      msg.result = restrictActionResult(ticket.name, msg.result);
    }
    if (msg.id !== undefined && initializeIds.has(String(msg.id)) && msg.result) {
      initializeIds.delete(String(msg.id));
      msg.result.instructions = [
        "GUI가 필요한 작업에서 CUA Driver를 자동으로 사용합니다. 작업 시작 때 list_windows로 정확한 창의 PID/HWND를 한 번 찾고, 같은 작업 중에는 재사용하세요. 앱 재시작, 새 창 생성, ID 오류나 불일치가 있을 때만 다시 목록을 읽으세요.",
        "첫 동작 전 get_window_state로 화면을 확인하세요. 표준 컨트롤은 좌표보다 element_token을 우선 사용하고, 캔버스나 접근성 정보가 없는 표면에서만 좌표를 사용하세요.",
        "각 동작 뒤 상태 확인이 필요하면 직전 snapshot_id를 since에 전달하고 include_screenshot:false로 변경된 접근성 트리만 읽으세요. 다음 동작은 새 snapshot의 토큰을 사용하세요. 픽셀 변화 확인, 캔버스 조작, 불확실한 결과에서만 스크린샷을 요청하세요. 기본 tree_format은 markdown이며 both/full_output은 필요한 경우에만 사용하세요.",
        "입력은 정확한 같은 창에 background만 사용합니다. 승인 없는 foreground, SendInput, 사용자 마우스 및 전역 입력은 금지합니다. 필요한 전경 입력은 approved_foreground_action으로 사용자가 채팅 승인 선택창에서 현재 작업 전체를 한 번 승인하면 같은 ACP 요청 완료·취소·연결 종료까지 재사용합니다. 갱신된 ACP 실행기가 없는 연결은 동작 1회만 허용합니다. 이 승인 선택창을 자동 조작하지 마세요. background_unavailable 또는 확인된 무동작이면 BACKGROUND_ONLY_UNSUPPORTED로 해당 GUI 단계와 의존 작업을 보류하세요. 다른 입력 경로로 전환하지 마세요. 이미 허가된 독립 코드 작업만 이어가고 차단된 완료 조건은 따로 보고하세요.",
        "데스크톱 전체 대상은 금지합니다. 조작 결과가 불명확하거나 권한이 거부되면 멈추고 보고하세요. 전역/네이티브 입력 또는 셸로 우회하지 않습니다. 에이전트 커서는 물리 포인터와 별도입니다.",
      ].join(" ");
      process.stdout.write(`${JSON.stringify(msg)}\n`);
    } else {
      process.stdout.write(`${JSON.stringify(msg)}\n`);
    }
  } catch {
    driverFailed('CUA Driver returned an invalid response; no unvalidated result was forwarded', 'driver_protocol_error');
  }
});

parentLines.on("line", async (line) => {
  let msg;
  try { msg = JSON.parse(line); }
  catch { jsonLine({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Invalid JSON" } }); return; }
  if(validEnvelope(msg)&&typeof msg.method!=='string'&&chatApprovals.has(msg.id)) {
    chatApprovals.get(msg.id)(msg.result?.action==='accept'&&msg.result?.content?.allow===true);return;
  }
  if(msg.method==='initialize')chatElicitation=Boolean(msg.params?.capabilities?.elicitation?.form);
  if (!validEnvelope(msg) || typeof msg.method !== 'string' || (msg.method === 'tools/call' && msg.id === undefined)) {
    jsonLine({jsonrpc:'2.0',id:null,error:{code:-32600,message:'Invalid request. Tool calls require a request ID; nothing was dispatched.'}});
    return;
  }
  if (closing) { if(msg.id !== undefined) errorResult(msg.id,'driver_unavailable','Driver connection closed. No request was dispatched.'); return; }
  if (msg.id !== undefined && pending.has(msg.id)) {
    driverFailed('Duplicate request ID: connection closed without dispatching another operation', 'driver_protocol_error');
    return;
  }
  if (pending.atCapacity && msg.id !== undefined) {
    errorResult(msg.id,'driver_busy','Request was NOT dispatched: too many outstanding requests.');
    return;
  }

  if (msg.method === "tools/list" && msg.id !== undefined) {
    jsonLine({ jsonrpc: "2.0", id: msg.id, result: { tools: [...tools, foregroundTool] } });
    return;
  }
  if (msg.method === "notifications/cancelled" && consent?.id === msg.params?.requestId) {
    consent.controller.abort(); return;
  }
  if (msg.method === "tools/call" && consent) {
    errorResult(msg.id, "approval_pending", "A human approval is pending. Do not automate its dialog or send overlapping input."); return;
  }
  if (msg.method === "tools/call" && msg.params?.name === foregroundTool.name) {
    if (calls.size) { errorResult(msg.id,"driver_busy","Wait for outstanding CUA requests before approval."); return; }
    const name=msg.params?.arguments?.action;
    const args=msg.params?.arguments?.arguments;
    const controller=new AbortController();
    consent={id:msg.id,controller};
    let ticket,taskScope;
    try {
      if (!isSafeCall(name,args)) throw new Error("Action must pass the exact-window background policy first.");
      taskScope=taskApprovals.bind(msg.params?._meta?.['ai.opencode/sessionID'],controller);
      const key=`${args.pid}:${args.window_id}`;
      const existing=grounding.frames.get(key);
      const frame=existing ? {...existing,png:grounding.approvalImage?.key===key ? grounding.approvalImage.data : undefined} : undefined;
      ticket=grounding.request(name,prepareCall(name,args));
      const result=await approvedForeground({driver,name,args:ticket.args.delivery_mode === "background" ? Object.fromEntries(Object.entries(ticket.args).filter(([key])=>key!=="delivery_mode")) : args,frame,captureTools:grounding.captureTools,signal:controller.signal,authorize:taskScope.authorize,confirmHuman:confirmInChat,assertOwned:taskScope.assertOwned});
      if (!closing && !controller.signal.aborted) jsonLine({jsonrpc:"2.0",id:msg.id,result});
      else if (!closing) errorResult(msg.id,"approval_cancelled","Cancelled; inspect the window before further input.");
    } catch(error) {
      if (!closing) errorResult(msg.id,"foreground_not_completed",error.message);
    } finally {
      if(ticket) grounding.response(ticket,{isError:true});
      taskScope?.close();
      consent=undefined;
    }
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
  if (msg.id !== undefined) pending.watch(msg.id, msg.method);
  action.stdin.write(`${JSON.stringify(msg)}\n`);
});

parentLines.on("close", () => { if (!closing) { closing = true; stopDriver(); } });
process.on("SIGINT", () => { consent?.controller.abort(); action.kill(); process.exit(130); });
process.on("SIGTERM", () => { consent?.controller.abort(); action.kill(); process.exit(143); });
action.on("exit", (code) => {
  if (!closing) driverFailed(`CUA Driver exited (${code})`);
});
