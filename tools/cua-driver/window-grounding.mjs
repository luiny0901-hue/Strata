import { createHash } from "node:crypto";
const actions = new Set(["click", "double_click", "right_click", "drag", "scroll", "type_text", "press_key", "hotkey", "set_value"]);
const points = new Set(["click", "double_click", "right_click", "drag", "scroll", "move_cursor"]);

function identity(args) {
  const pid = args.target?.pid ?? args.pid;
  const hwnd = args.target?.window_id ?? args.window_id;
  return Number.isInteger(pid) && Number.isInteger(hwnd) ? `${pid}:${hwnd}` : undefined;
}

function metadata(result) {
  if (result?.structuredContent) return result.structuredContent;
  for (const item of result?.content ?? []) {
    if (item.type !== "text") continue;
    try { const value = JSON.parse(item.text); if (value && typeof value === "object") return value; } catch {}
  }
  return {};
}

function pngSize(result) {
  for (const item of result?.content ?? []) {
    if (item.type !== "image" || item.mimeType !== "image/png" || typeof item.data !== 'string') continue;
    // PNG dimensions live in the first 24 bytes; avoid decoding a whole 4K/8K
    // image just to read its header. The original image is still returned intact.
    const bytes = Buffer.from(item.data.slice(0, 32), "base64");
    if (bytes.length >= 24 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
      return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
    }
  }
}

export class GroundingError extends Error {
  constructor(message) { super(message); this.code = "fresh_screenshot_required"; }
}

export class WindowGrounding {
  constructor({now = Date.now, maxAgeMs = 120000, captureTools = new Set()} = {}) {
    this.now = now;
    this.maxAgeMs = maxAgeMs;
    this.captureTools = captureTools;
    this.frames = new Map();
    this.epoch = 0;
    this.inflight = 0;
    this.captureSequence = 0;
    this.latestCaptures = new Map();
  }

  request(name, args) {
    const key = identity(args);
    const ticket = {name, args: {...args}, key, epoch: this.epoch};
    if (this.inflight && (actions.has(name) || name === "get_window_state" || name === "move_cursor")) throw new GroundingError("A prior input is still running. Wait for its result, then read the window; do not issue overlapping inputs.");
    if (name === "get_window_state" && key) {
      // A newer read may reveal a moved/resized/changed window. Never fall back
      // to its previous pixels if the fresh read fails or returns tree-only.
      this.frames.delete(key);
      ticket.captureSequence = ++this.captureSequence;
      this.latestCaptures.delete(key);
      if (this.latestCaptures.size >= 128) this.latestCaptures.delete(this.latestCaptures.keys().next().value);
      this.latestCaptures.set(key, ticket.captureSequence);
    }
    const pairs = name === "drag" ? [[args.from_x, args.from_y], [args.to_x, args.to_y]] : [[args.x, args.y]];
    const pixel = (points.has(name) || actions.has(name)) && !args.element_token && (name === "drag" || name === "move_cursor" || args.x !== undefined || args.y !== undefined);
    if (pixel) {
      const frame = this.frames.get(key);
      if (!frame || this.now() - frame.time > this.maxAgeMs) throw new GroundingError("Read get_window_state with include_screenshot:true for this exact window, inspect it, then choose screenshot-local pixels. Do not guess/replay coordinates.");
      if (args.from_zoom) throw new GroundingError("Zoom coordinates are not available through this proxy. Use the latest full-window screenshot pixels.");
      for (const [x, y] of pairs) {
        if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x >= frame.width || y >= frame.height) {
          throw new GroundingError(`Coordinates must be inside the returned ${frame.width}x${frame.height} screenshot. Do not use desktop coordinates, normalized coordinates or manual DPI scaling.`);
        }
      }
      if (args.capture_id !== undefined && args.capture_id !== frame.captureID) throw new GroundingError("capture_id does not match the latest screenshot; read the window again.");
      if (name === "move_cursor") {
        const b = frame.bounds;
        if (!b || ![b.x, b.y, b.width, b.height].every(Number.isFinite) || b.width <= 0 || b.height <= 0) throw new GroundingError("No reliable window bounds for overlay conversion. Skip move_cursor; use a grounded click directly.");
        ticket.args = {...args, scope: "window", x: b.x + args.x * b.width / frame.width, y: b.y + args.y * b.height / frame.height};
      } else if (frame.captureID && this.captureTools.has(name)) {
        ticket.args.capture_id = frame.captureID;
      }
    }
    if (actions.has(name)) {
      // Token-only calls can omit the window identity; conservatively invalidate all.
      this.frames.clear();
      this.epoch++;
      this.inflight++;
    }
    return ticket;
  }

  response(ticket, result) {
    if (actions.has(ticket.name)) { this.inflight = Math.max(0, this.inflight - 1); return; }
    if (ticket.name !== "get_window_state" || !ticket.key) return;
    if (ticket.epoch !== this.epoch || ticket.captureSequence !== this.latestCaptures.get(ticket.key)) {
      if (result) {
        result.isError = true;
        result.structuredContent = {code:'stale_capture'};
        result.content = [{type:'text',text:'STALE_CAPTURE: a newer read or input superseded this response. Inspect a fresh window state; do not use this image or tokens.'}];
      }
      return;
    }
    if (result?.isError) return;
    if (ticket.args.include_screenshot === false || ticket.args.display_only === true) return;
    const meta = metadata(result);
    const size = pngSize(result);
    if (!size || size[0] <= 0 || size[1] <= 0 || meta.screenshot_frame_valid === false) {
      this.frames.delete(ticket.key);
      return;
    }
    this.frames.delete(ticket.key);
    if (this.frames.size >= 32) this.frames.delete(this.frames.keys().next().value);
    this.approvalImage = {key: ticket.key, data: result.content.find(item => item.type === "image" && item.mimeType === "image/png").data};
    this.frames.set(ticket.key, {width: size[0], height: size[1], bounds: meta.window_bounds, captureID: meta.capture_id, time: this.now(), digest: createHash("sha256").update(result.content.find(item => item.type === "image" && item.mimeType === "image/png").data).digest("hex")});
    result.content ??= [];
    result.content.push({type: "text", text: `CUA_COORDINATES: window ${ticket.key}; returned PNG ${size[0]}x${size[1]}. For click/drag/scroll/move_cursor use pixels in THIS image, origin top-left, x=0..${size[0]-1}, y=0..${size[1]-1}. Do not use desktop/UIA-frame coordinates, add window origin, or scale by DPI/vision token budget. Prefer element_token for standard controls. One input consumes this grounding; inspect a new screenshot before the next pixel action. move_cursor is an optional AI overlay, not a prerequisite to click.`});
  }
}
