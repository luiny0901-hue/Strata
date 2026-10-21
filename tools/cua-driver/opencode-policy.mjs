export const exposedTools = new Set([
  "list_apps", "list_windows", "get_window_state",
  "start_session", "end_session",
  "set_agent_cursor_enabled", "get_agent_cursor_state", "move_cursor",
  "click", "double_click", "right_click", "drag", "scroll",
  "type_text", "press_key", "hotkey", "set_value", "launch_app",
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
      && Number.isInteger(args.target.window_id) && args.target.window_id > 0;
  }
  if (typeof args.element_token === "string"
      && /^s[0-9a-f]{8}:[0-9]+$/.test(args.element_token)) return true;
  return args.scope === "window"
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
  if (name === "launch_app") return true;
  return true;
}

// Driver descriptions advertise SendInput escalation; that route is forbidden here.
export function restrictCatalog(tools) {
  return tools.map((tool) => {
    if (!inputTools.has(tool.name)) return tool;
    const copy = structuredClone(tool);
    copy.description = `${tool.name}: use CUA Driver background delivery for one exact window only. Prefer a current element_token when supported; otherwise use coordinates from the latest window screenshot. Never use foreground/global input or the user's mouse. If background delivery is unavailable or ineffective, stop and report BACKGROUND_ONLY_UNSUPPORTED; do not retry through shell or native input.`;
    const delivery = copy.inputSchema?.properties?.delivery_mode;
    if (delivery) {
      delivery.enum = ["background"];
      delivery.default = "background";
      delivery.description = "Only background delivery is permitted. Foreground SendInput and the user's pointer are forbidden.";
    }
    return copy;
  });
}
