"""Opt-in delivery guard for Messages tool narration and explicit JSON-only replies.

The client executes tools after receiving tool_use. Text in that same response cannot
confirm the tool's success. Defer text until the response's tool decision is known;
keep thinking, tool arguments and heartbeats streaming. No model retry is added.
"""
from __future__ import annotations

import json
import re
import time

from serve.structured import StructuredOutputError, validated_json


def configure_response_guard(service, value):
    if not isinstance(value, bool):
        raise SystemExit('[strata] config "anthropic_response_guard" must be true or false')
    service.anthropic_response_guard = value


_ENGLISH = re.compile(
    r'(?:^|[.!?]\s+)(?:please\s+)?(?:return|output|respond(?:\s+with)?|end\s+with)\s+'
    r'(?:only(?:\s+valid)?|nothing\s+but)\s+json(?:\s+(?:object|array))?[.!\s]*$', re.I)
_KOREAN = re.compile(
    r'(?:^|[.!?]\s+)(?:(?:반드시|오직)\s*)?JSON(?:으로)?만\s*'
    r'(?:출력|응답|답변)(?:해(?:줘|주세요)?|해주세요|하세요|하라|한다)[.!\s]*$', re.I)
_BOUNDARY = re.compile(
    r'```|</?(system-reminder|tool_result|tool_response|untrusted_text|document|attachment|code)\b', re.I)


def _visible_text(text):
    # One forward scan: unmatched/nested context tags must not cause regex backtracking
    # over a long coding prompt. Excessive nesting is ambiguous, so infer no format.
    pieces, contexts, fenced, pos = [], [], False, 0
    while True:
        match = _BOUNDARY.search(text, pos)
        if match is None:
            if not fenced and not contexts:
                pieces.append(text[pos:])
            break
        if not fenced and not contexts:
            pieces.append(text[pos:match.start()])
        token = match.group(0)
        if token == '```':
            if not contexts:
                fenced = not fenced
            pos = match.end()
            continue
        if fenced:
            pos = match.end()
            continue
        end = text.find('>', match.end())
        if end < 0:
            break
        name = match.group(1).lower()
        if token.startswith('</'):
            if name in contexts:
                del contexts[len(contexts) - 1 - contexts[::-1].index(name):]
        elif text[end - 1:end] != '/':
            contexts.append(name)
            if len(contexts) > 64:
                return ''
        pos = end + 1
    return '\n'.join(pieces)


def _instruction_text(content):
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = '\n'.join(b.get('text', '') for b in content
                         if isinstance(b, dict) and b.get('type') == 'text' and isinstance(b.get('text'), str))
    else:
        return ''
    # Examples, attached source and tool results are not output-format instructions.
    text = _visible_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('>')]
    return lines[-1] if lines else ''


def explicit_json_only(req):
    """Recognize an affirmative terminal directive, not mentions of JSON or a new task's old history."""
    latest = ''
    for message in reversed(req.get('messages') or []):
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        latest = _instruction_text(message.get('content'))
        if latest:
            break
    system = _instruction_text(req.get('system'))
    return any(_ENGLISH.search(text) or _KOREAN.search(text) for text in (latest, system))


def single_json_text(text):
    """Extract one complete container; reject ambiguity and malformed/truncated outer JSON.

    Scalars must be the whole answer (optionally fenced). Never pick an inner object
    out of a broken outer value or choose the first of several JSON answers.
    """
    text = text.strip()
    if text.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', text, re.I | re.S)
        if match:
            text = match.group(1).strip()
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(text)
        if not text[end:].strip():
            return text
    except ValueError:
        pass
    starts = [i for mark in ('{', '[') if (i := text.find(mark)) >= 0]
    if not starts:
        raise ValueError('no single complete JSON value')
    start = min(starts)
    _, end = decoder.raw_decode(text, start)
    if any(mark in text[end:] for mark in ('{', '[')):
        raise ValueError('more than one JSON container or a malformed trailing value')
    return text[start:end]


class _JSONValue:
    def iter_errors(self, value):
        return iter(())


def guard_anthropic_events(events, req, *, enabled=False, with_tools=False, cancel=None,
                           heartbeat_s=5.0, max_text=8 << 20):
    json_only = explicit_json_only(req) if enabled else False
    if not enabled or not (with_tools or json_only):
        return events
    return _guard(events, json_only=json_only, cancel=cancel,
                  heartbeat_s=heartbeat_s, max_text=max_text)


def _guard(events, *, json_only, cancel, heartbeat_s, max_text):
    mapped, text_indices, pending = {}, set(), []
    next_index, text_size, used_tool = 0, 0, False
    last_sent = time.monotonic()

    def reindex(packet):
        return {**packet, 'index': mapped[packet['index']]}

    try:
        for item in events:
            now = time.monotonic()
            if item is None:
                last_sent = now
                yield None
                continue
            name, packet = item
            suppressed = False
            if name == 'content_block_start':
                index = packet['index']
                block = packet['content_block']
                if block['type'] == 'text':
                    text_indices.add(index)
                    if not used_tool:
                        value = block.get('text', '')
                        text_size += len(value)
                        pending.append([index, [value]])
                    suppressed = True
                else:
                    if block['type'] == 'tool_use':
                        used_tool = True
                        pending.clear()
                        text_size = 0
                    mapped[index] = next_index
                    next_index += 1
                    yield name, reindex(packet)
            elif name == 'content_block_delta' and packet['index'] in text_indices:
                if not used_tool:
                    value = packet['delta'].get('text', '')
                    text_size += len(value)
                    pending[-1][1].append(value)
                suppressed = True
            elif name == 'content_block_stop' and packet['index'] in text_indices:
                suppressed = True
            elif name in ('content_block_delta', 'content_block_stop'):
                yield name, reindex(packet)
            elif name == 'message_delta':
                cancelled = cancel is not None and cancel.is_set()
                if not used_tool and not cancelled:
                    texts = [''.join(parts) for _, parts in pending]
                    if json_only:
                        stop = packet['delta'].get('stop_reason')
                        finish = 'stop' if stop in ('end_turn', 'stop_sequence') else str(stop)
                        extracted = []
                        def extract_value(text):
                            value = single_json_text(text)
                            extracted.append(value)
                            return value
                        validated_json(''.join(texts), _JSONValue(), finish, extractor=extract_value)
                        # Validation must not round numeric literals or rewrite the user's JSON strings.
                        texts = extracted
                    for value in texts:
                        yield 'content_block_start', {'type':'content_block_start', 'index':next_index,
                            'content_block':{'type':'text', 'text':''}}
                        yield 'content_block_delta', {'type':'content_block_delta', 'index':next_index,
                            'delta':{'type':'text_delta', 'text':value}}
                        yield 'content_block_stop', {'type':'content_block_stop', 'index':next_index}
                        next_index += 1
                pending.clear()
                text_size = 0
                yield name, packet
            else:
                yield name, packet
            if text_size > max_text:
                raise StructuredOutputError('deferred Messages text exceeded the delivery buffer limit')
            if suppressed:
                if now - last_sent >= heartbeat_s:
                    last_sent = now
                    yield None
            else:
                last_sent = now
    finally:
        close = getattr(events, 'close', None)
        if close is not None:
            close()
