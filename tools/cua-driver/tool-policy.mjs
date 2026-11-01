export const exposedTools = new Set([
  "list_apps", "list_windows", "get_window_state",
  "start_session", "end_session",
  "set_agent_cursor_enabled", "get_agent_cursor_state", "move_cursor",
  "click", "double_click", "right_click", "drag", "scroll",
  "type_text", "press_key", "hotkey", "set_value",
]);

const inputTools = new Set([
  "click", "double_click", "right_click", "drag", "scroll",
  "type_text", "press_key", "hotkey", "set_value",
]);

export function prepareCall(name, args) {
  if (inputTools.has(name)) return { ...args, delivery_mode: "background" };
  // Reproduce the selected client image budget without overwriting driver-wide settings.
  if (name === "get_window_state" && args.include_screenshot !== false
      && args.max_image_dimension === undefined && args.max_dimension === undefined) {
    return { ...args, max_image_dimension: 1920 };
  }
  return args;
}

export function exactWindow(args) {
  if (args.scope === "desktop") return false;
  if (args.target !== undefined) {
    return args.target?.kind === "window"
      && Number.isInteger(args.target.pid) && args.target.pid > 0
      && Number.isInteger(args.target.window_id) && args.target.window_id > 0
      && (args.pid === undefined || args.pid === args.target.pid)
      && (args.window_id === undefined || args.window_id === args.target.window_id);
  }
  if (typeof args.element_token === "string"
      && /^s[0-9a-f]{8}:[0-9]+$/.test(args.element_token)) return true;
  return (args.scope === undefined || args.scope === "window")
    && Number.isInteger(args.pid) && args.pid > 0
    && Number.isInteger(args.window_id) && args.window_id > 0;
}

export function isSafeCall(name, args) {
  if (!exposedTools.has(name) || !args || typeof args !== "object" || Array.isArray(args)) return false;
  if (name === "get_window_state") {
    return Number.isInteger(args.pid) && args.pid > 0
      && Number.isInteger(args.window_id) && args.window_id > 0
      && args.screenshot_out_file === undefined;
  }
  if (name === "move_cursor") return exactWindow(args);
  if (inputTools.has(name)) {
    const supportedDelivery = args.delivery_mode === undefined
      || args.delivery_mode === "background";
    return supportedDelivery && exactWindow(args);
  }
  if (name === "set_agent_cursor_enabled") {
    return typeof args.session === "string" && args.session.length > 0 && typeof args.enabled === "boolean";
  }
  return true;
}

// Native drivers may suggest SendInput when PostMessage cannot be verified.
// Preserve the actual effect/route; never advertise a forbidden recovery path.
export function restrictActionResult(name, result) {
  const meta = result?.structuredContent;
  if (!inputTools.has(name) || meta?.escalation?.target !== "foreground") return result;
  const { escalation, ...preserved } = meta;
  const summary = "BACKGROUND_ESCALATION_BLOCKED: the driver requested foreground fallback, which requires separate human approval through approved_foreground_action. "
    + "The input may already have occurred; delivery is not completion proof. Inspect a fresh target-window screenshot. "
    + "If unchanged, request human permission with approved_foreground_action or report BACKGROUND_ONLY_UNSUPPORTED. Do not replay input or use foreground/global/SendInput. "
    + `Driver effect=${String(meta.effect ?? "unknown")}, route=${String(meta.route ?? "unknown")}.`;
  return {
    ...result,
    content: [...(result.content ?? []).filter(item => item.type !== "text"), { type: "text", text: summary }],
    structuredContent: { ...preserved, summary, code: "background_escalation_blocked" },
  };
}

const windowFields = {
  pid: "Exact window's process ID; may be omitted with an element_token.",
  window_id: "Window ID from list_windows; may be omitted with an element_token.",
  scope: "Window scope only. Desktop input is unavailable through this proxy.",
  target: "Exact window target: kind=window, pid and window_id. Omit with an element_token.",
  session: "Stable public lifecycle label; reuse it across related calls. Omitted uses the transport's implicit session.",
  element_token: "Current <snapshot_id>:<row> from get_window_state. It binds the window. A new tree invalidates old tokens; do not combine with pixel coordinates.",
  capture_id: "ID from the latest get_window_state screenshot; use with its pixel coordinates.",
  x: "X in latest returned screenshot pixels; pair with y. No window offset or manual DPI scaling.",
  y: "Y in latest returned screenshot pixels; pair with x.",
};
const snapshotFields = {
  pid: "Required positive process ID from list_apps/list_windows.",
  window_id: "Required window ID belonging to pid, from list_windows.",
  capture_mode: "Deprecated and ignored; use include_accessibility_tree/include_screenshot.",
  display_only: "With tree disabled, display pixels without replacing registered pixel grounding. Default false.",
  full_output: "Return both tree forms and full metadata, up to 5000 elements/depth25. Default false.",
  include_accessibility_tree: "Return UIA tree by default. False skips the walk; then include_screenshot must be true.",
  include_screenshot: "Return screenshot by default. False keeps the UIA tree only; both cannot be false.",
  max_depth: "UIA walk depth cap; omitted uses the driver limit up to25.",
  max_dimension: "Legacy cap on screenshot long edge; cannot increase the configured limit. Prefer max_image_dimension.",
  max_elements: "UIA node budget; default250. Truncation is reported. Raise or narrow query/depth when needed.",
  max_image_dimension: "Screenshot long-edge override preserving aspect ratio. Proxy defaults1920; 0 requests native resolution.",
  query: "Case-insensitive tree substring; returns matches and ancestors with original element indices.",
  since: "Earlier snapshot_id (or latest) for this window: return changes only. Always use the NEW snapshot_id for tokens. Expired/other-window/different-scope IDs fall back to full read with since_status; reindexed warns of changed row indices.",
  timeout_ms: "UIA walk budget in milliseconds, default1000, range100..120000. A budget-limited walk may return a partial tree; inspect truncation flags.",
  tree_format: "markdown(default) gives [row] tokens; elements gives structured rows; both returns both at higher cost.",
  verbose: "Include diagnostic note and full background-input capability metadata. Default false.",
};

function windowCatalogSchema(schema, descriptions) {
  const properties = schema?.properties;
  if (!properties) return;
  for (const [name, description] of Object.entries(descriptions)) {
    if (properties[name]) properties[name].description = description;
  }
  if (properties.scope?.enum?.includes("window")) properties.scope.enum = ["window"];
  for (const key of ["pid", "window_id"]) {
    if (properties[key]?.type === "integer") properties[key].minimum = Math.max(1, properties[key].minimum ?? 1);
  }
  const target = properties.target;
  if (target?.properties?.kind?.enum?.includes("window")) {
    target.properties.kind.enum = ["window"];
    target.properties.kind.description = "Exact window target.";
    delete target.properties.display_id;
    target.required = [...new Set([...(target.required ?? []), "kind", "pid", "window_id"])];
    for (const key of ["pid", "window_id"]) {
      if (target.properties[key]?.type === "integer") target.properties[key].minimum = Math.max(1, target.properties[key].minimum ?? 1);
    }
  }
  // These forms are already rejected by isSafeCall/WindowGrounding.
  delete properties.from_zoom;
  delete properties.screenshot_out_file;
}

// Keep the supported window contract concise; never advertise rejected routes.
export function restrictCatalog(tools) {
  return tools.map((tool) => {
    if (tool.name === "get_window_state") {
      const copy = structuredClone(tool);
      copy.description = "Read one exact pid/window_id: bounded UIA tree and grounding screenshot. Default markdown rows [N] give element_token=<snapshot_id>:N. Cross-check pixels and tree. Each new tree invalidates older tokens; screenshot-only reads preserve tokens. Inspect truncation flags; query/depth/budget or since can narrow reads. The driver never substitutes another window. Window capture may omit browser-owned overlays: report the coverage gap; do not switch to desktop input. No input is performed.";
      windowCatalogSchema(copy.inputSchema, {...windowFields, ...snapshotFields});
      return copy;
    }
    if (tool.name === "move_cursor") {
      const copy = structuredClone(tool);
      copy.description = "Move only the AI overlay. In this proxy x,y are pixels in the latest get_window_state screenshot, exactly like click. The proxy converts them to driver screen coordinates. Do NOT add window origin or DPI scaling. A fresh screenshot and exact window target are required. This does not move the user's mouse and is not required before clicking.";
      windowCatalogSchema(copy.inputSchema, windowFields);
      return copy;
    }
    if (!inputTools.has(tool.name)) return tool;
    const copy = structuredClone(tool);
    copy.description = `${tool.name}: background input on one exact window/current element_token; never use the user's mouse or global input. Pixel actions use latest screenshot coordinates, no offsets/scaling/guesses; re-read after input. Delivery is not success. If ineffective, obtain HUMAN task approval via approved_foreground_action or report BACKGROUND_ONLY_UNSUPPORTED. No shell/native bypass or automated approval; continue only independent authorized work.`;
    windowCatalogSchema(copy.inputSchema, windowFields);
    const delivery = copy.inputSchema?.properties?.delivery_mode;
    if (delivery) {
      delivery.enum = ["background"];
      delivery.default = "background";
      delivery.description = "Only background delivery is permitted. Foreground SendInput and the user's pointer are forbidden.";
    }
    return copy;
  });
}
