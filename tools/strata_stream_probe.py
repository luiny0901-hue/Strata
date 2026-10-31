"""Probe the OpenCodex gateway wires for intermediate-process stream events.

Checks whether thinking/reasoning and tool-call deltas actually reach a
streaming client on the two routes Claude and Codex use. Prints an event
shape summary only, no prompt or answer text.
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:10100"
TOKEN = "opencodex-proxy"
MODEL = "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs"


def stream_events(url: str, payload: dict, headers: dict) -> list[str]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {TOKEN}")
    for name, value in headers.items():
        request.add_header(name, value)
    shapes: list[str] = []
    with urllib.request.urlopen(request, timeout=300) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body or body == "[DONE]":
                shapes.append("[DONE]" if body == "[DONE]" else "")
                continue
            try:
                event = json.loads(body)
            except json.JSONDecodeError:
                shapes.append("unparsable")
                continue
            kind = event.get("type") or event.get("object") or "?"
            detail = event.get("delta_type") or ""
            if kind == "content_block_start":
                detail = str((event.get("content_block") or {}).get("type"))
            elif kind in ("content_block_delta",):
                detail = str(event.get("delta", {}).get("type"))
            elif kind == "response.output_item.added":
                detail = str((event.get("item") or {}).get("type"))
            elif "response." in str(kind):
                detail = ""
            elif kind == "chat.completion.chunk":
                delta = (event.get("choices") or [{}])[0].get("delta", {})
                keys = [k for k in delta if delta.get(k)]
                detail = ",".join(keys)
            shapes.append(f"{kind}:{detail}" if detail else str(kind))
    return shapes


def summarize(name: str, shapes: list[str]) -> None:
    counts: dict[str, int] = {}
    for shape in shapes:
        if shape:
            counts[shape] = counts.get(shape, 0) + 1
    print(f"== {name} ==")
    for shape, count in counts.items():
        print(f"  {shape}  x{count}")


def main() -> int:
    probes = {
        "anthropic-thinking": (
            f"{BASE}/v1/messages",
            {"model": MODEL, "max_tokens": 256, "stream": True,
             "thinking": {"type": "enabled", "budget_tokens": 1024},
             "messages": [{"role": "user", "content": "29의 소수를 찾으세요. 짧게."}]},
            {"anthropic-version": "2023-06-01"},
        ),
        "anthropic-tool": (
            f"{BASE}/v1/messages",
            {"model": MODEL, "max_tokens": 256, "stream": True,
             "tools": [{"name": "ping", "description": "Return pong.",
                        "input_schema": {"type": "object", "properties": {}, "required": []}}],
             "tool_choice": {"type": "tool", "name": "ping"},
             "messages": [{"role": "user", "content": "Call the tool."}]},
            {"anthropic-version": "2023-06-01"},
        ),
        "responses-thinking": (
            f"{BASE}/v1/responses",
            {"model": MODEL, "stream": True,
             "reasoning": {"effort": "high", "summary": "auto"},
             "input": [{"role": "user", "content": "29의 소수를 찾으세요. 짧게."}]},
            {},
        ),
        "responses-tool": (
            f"{BASE}/v1/responses",
            {"model": MODEL, "stream": True,
             "tools": [{"type": "function", "name": "ping", "description": "Return pong.",
                        "parameters": {"type": "object", "properties": {}, "required": []}}],
             "tool_choice": {"type": "function", "name": "ping"},
             "input": [{"role": "user", "content": "Call the tool."}]},
            {},
        ),
    }
    only = sys.argv[1:]
    for name, (url, payload, headers) in probes.items():
        if only and name not in only:
            continue
        try:
            summarize(name, stream_events(url, payload, headers))
        except Exception as exc:  # noqa: BLE001 - report, keep probing the rest
            print(f"== {name} ==\n  ERROR {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
