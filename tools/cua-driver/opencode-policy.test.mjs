import assert from "node:assert/strict";
import test from "node:test";
import { isSafeCall } from "./opencode-policy.mjs";

const target = { target: { kind: "window", pid: 30216, window_id: 263942 } };

test("allows background actions for one exact window", () => {
  assert.equal(isSafeCall("click", { ...target, delivery_mode: "background" }), true);
});

test("allows foreground escalation for one exact window", () => {
  assert.equal(isSafeCall("hotkey", { ...target, keys: ["ctrl", "alt", "s"], delivery_mode: "foreground" }), true);
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
});

import { prepareCall } from "./opencode-policy.mjs";
test("1920 image budget preserves explicit requests and tree-only reads", () => {
  assert.equal(prepareCall("get_window_state", {pid: 1, window_id: 2}).max_image_dimension, 1920);
  assert.equal(prepareCall("get_window_state", {max_image_dimension: 0}).max_image_dimension, 0);
  assert.equal(prepareCall("get_window_state", {max_dimension: 1280}).max_image_dimension, undefined);
  assert.equal(prepareCall("get_window_state", {include_screenshot: false}).max_image_dimension, undefined);
});
