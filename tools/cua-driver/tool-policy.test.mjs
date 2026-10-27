import assert from "node:assert/strict";
import test from "node:test";
import { isSafeCall } from "./tool-policy.mjs";

const target = { target: { kind: "window", pid: 30216, window_id: 263942 } };

test("allows background actions for one exact window", () => {
  assert.equal(isSafeCall("click", { ...target, delivery_mode: "background" }), true);
});

test("rejects foreground for every input tool even with exact tokens or targets", () => {
  for (const name of ["click", "double_click", "right_click", "drag", "scroll", "type_text", "press_key", "hotkey", "set_value"]) {
    assert.equal(isSafeCall(name, { ...target, delivery_mode: "foreground" }), false);
    assert.equal(isSafeCall(name, { element_token: "s00000001:1", delivery_mode: "foreground" }), false);
  }
});

test("allows the driver's default delivery mode for one exact window", () => {
  assert.equal(isSafeCall("type_text", { ...target, text: "font" }), true);
});

test("rejects desktop-wide input even with foreground delivery", () => {
  assert.equal(isSafeCall("click", { target: { kind: "desktop", display_id: "primary" }, delivery_mode: "foreground", x: 100, y: 100 }), false);
  assert.equal(isSafeCall("hotkey", { scope: "desktop", keys: ["ctrl", "alt", "s"], delivery_mode: "foreground" }), false);
});

test("rejects unsupported delivery modes and malformed window targets", () => {
  assert.equal(isSafeCall("click", { ...target, delivery_mode: "automatic" }), false);
  assert.equal(isSafeCall("click", { target: { kind: "window", pid: 0, window_id: 263942 }, delivery_mode: "foreground" }), false);
});

test("does not expose process termination", () => {
  assert.equal(isSafeCall("kill_app", { pid: 30216 }), false);
  assert.equal(isSafeCall("launch_app", { path:'notepad.exe' }), false);
});

import { prepareCall } from "./tool-policy.mjs";
import { restrictCatalog } from "./tool-policy.mjs";

test("omitted delivery is pinned to background before forwarding", () => {
  assert.equal(prepareCall("click", target).delivery_mode, "background");
});

test("catalog removes driver escalation instructions and foreground enum", () => {
  const original = {name: "click", description: "retry foreground", inputSchema: {properties: {delivery_mode: {enum: ["background", "foreground"]}}}};
  const [safe] = restrictCatalog([original]);
  assert.deepEqual(safe.inputSchema.properties.delivery_mode.enum, ["background"]);
  assert.ok(safe.description.includes("BACKGROUND_ONLY_UNSUPPORTED"));
  assert.equal(original.description, "retry foreground");
});
test("1920 image budget preserves explicit requests and tree-only reads", () => {
  assert.equal(prepareCall("get_window_state", {pid: 1, window_id: 2}).max_image_dimension, 1920);
  assert.equal(prepareCall("get_window_state", {max_image_dimension: 0}).max_image_dimension, 0);
  assert.equal(prepareCall("get_window_state", {max_dimension: 1280}).max_image_dimension, undefined);
  assert.equal(prepareCall("get_window_state", {include_screenshot: false}).max_image_dimension, undefined);
});

test("catalog omits rejected desktop/zoom/file-output routes without changing native input handling", () => {
  const original = {name:'click', description:'native desktop escalation',inputSchema:{type:'object',properties:{
    scope:{type:'string',enum:['window','desktop']},from_zoom:{type:'boolean'},
    target:{type:'object',properties:{kind:{type:'string',enum:['window','desktop']},
      display_id:{type:'string'},pid:{type:'integer',minimum:0},window_id:{type:'integer',minimum:0}},required:['kind']},
    x:{type:'number',minimum:0},y:{type:'number'},element_token:{type:'string'},delivery_mode:{enum:['background','foreground']},
    custom:{type:'string',description:'Preserve future parameters verbatim',maxLength:42},
  }}};
  const before=structuredClone(original);
  const [actual]=restrictCatalog([original]);
  assert.deepEqual(actual.inputSchema.properties.scope.enum,['window']);
  assert.deepEqual(actual.inputSchema.properties.target.properties.kind.enum,['window']);
  assert.deepEqual(actual.inputSchema.properties.target.required,['kind','pid','window_id']);
  assert.equal(actual.inputSchema.properties.target.properties.pid.minimum,1);
  assert.equal(actual.inputSchema.properties.target.properties.display_id,undefined);
  assert.equal(actual.inputSchema.properties.from_zoom,undefined);
  assert.deepEqual(actual.inputSchema.properties.custom,original.inputSchema.properties.custom);
  assert.equal(actual.inputSchema.properties.x.minimum,0);
  assert.ok(actual.description.includes('HUMAN task approval'));
  assert.ok(actual.description.includes('re-read after input'));
  assert.deepEqual(original,before);
  assert.equal(isSafeCall('click',{scope:'desktop',pid:1,window_id:2,x:0,y:0}),false);
  assert.equal(isSafeCall('click',{element_token:'s00000001:1'}),true);
});

test("snapshot catalog preserves formats, diffs, bounds and explicit image budgets", () => {
  const original={name:'get_window_state',description:'escalate_session then get_desktop_state',inputSchema:{
    required:['pid','window_id'],properties:{pid:{type:'integer'},window_id:{type:'integer'},
      since:{type:'string'},query:{type:'string'},max_elements:{type:'integer',maximum:5000},
      max_image_dimension:{type:'integer',minimum:0},tree_format:{enum:['markdown','elements','both']},
      include_accessibility_tree:{type:'boolean'},include_screenshot:{type:'boolean'},screenshot_out_file:{type:'string'}}}};
  const [actual]=restrictCatalog([original]);
  assert.ok(!actual.description.includes('escalate_session'));
  assert.ok(!actual.description.includes('get_desktop_state'));
  assert.ok(actual.description.includes('invalidates older tokens'));
  assert.ok(actual.inputSchema.properties.since.description.includes('NEW snapshot_id'));
  assert.deepEqual(actual.inputSchema.properties.tree_format.enum,['markdown','elements','both']);
  assert.equal(actual.inputSchema.properties.max_elements.maximum,5000);
  assert.equal(actual.inputSchema.properties.max_image_dimension.minimum,0);
  assert.equal(actual.inputSchema.properties.screenshot_out_file,undefined);
  assert.equal(actual.inputSchema.properties.pid.description.includes('element_token'),false);
  assert.deepEqual(actual.inputSchema.required,['pid','window_id']);
  assert.deepEqual(actual,restrictCatalog([actual])[0]);
});

test("unknown tools and custom nested descriptions are not rewritten", () => {
  const tool={name:'future_tool',description:'Complete provider-specific contract',inputSchema:{properties:{x:{description:'Not screenshot coordinates'}}}};
  assert.equal(restrictCatalog([tool])[0],tool);
});
