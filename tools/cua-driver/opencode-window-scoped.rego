package cua.policy

import rego.v1

read_tools := {"list_apps", "list_windows", "get_agent_cursor_state"}
window_action_tools := {"click", "double_click", "right_click", "drag", "scroll", "type_text", "press_key", "hotkey", "set_value"}

# Input and screenshots must identify one exact window. Desktop-wide control is denied.
window_target(args) if {
  args.target.kind == "window"
  args.target.pid > 0
  args.target.window_id > 0
  not args.scope == "desktop"
}

window_target(args) if {
  regex.match("^s[0-9a-f]{8}:[0-9]+$", args.element_token)
  not args.scope == "desktop"
  not args.target.kind == "desktop"
}

window_target(args) if {
  args.scope == "window"
  args.pid > 0
  args.window_id > 0
  not args.target.kind == "desktop"
}

window_delivery(args) if { args.delivery_mode == "background" }

allow if { input.tool in read_tools }

allow if {
  input.tool == "get_window_state"
  input.arguments.pid > 0
  input.arguments.window_id > 0
  not input.arguments.screenshot_out_file
}

allow if {
  input.tool in {"start_session", "end_session"}
  not input.arguments.capture_scope == "desktop"
}

allow if {
  input.tool == "set_agent_cursor_enabled"
  input.arguments.session != ""
}

allow if {
  input.tool == "move_cursor"
  window_target(input.arguments)
}

allow if {
  input.tool in window_action_tools
  window_target(input.arguments)
  window_delivery(input.arguments)
}

# App launch remains available; process termination is not exposed by this proxy.
allow if { input.tool == "launch_app" }

default allow := false
