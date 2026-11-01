"""Compaction formatting must not change normal requests or discard native policy."""
import copy
import json
from pathlib import Path
import unittest
from urllib.request import Request, urlopen

from serve.anthropic_compaction import HINT, concise_compaction_request
from serve.frontend import ChatTemplate, anthropic_to_messages
from serve.server import ByteTokenizer, MockEngine, Service, serve


def native_prompt():
    return ('Your task is to create a detailed summary of the conversation so far, paying close attention.\n'
            '1. Primary Request and Intent:\n3. Files and Code Sections:\n6. All user messages:\n'
            '9. Optional Next Step:\n<summary>state</summary>\n' + 'Native checklist. ' * 60 +
            '\nAdditional Instructions:\nKEEP: no publish; Windows build NOT_RUN.\n'
            'REMINDER: Do NOT call any tools. Respond with plain text only. '
            'Tool calls will be rejected and you will fail the task.')


def request():
    return {'system': 'Original system policy.',
            'messages': [{'role': 'user', 'content': 'Original task.'},
                         {'role': 'assistant', 'content': 'Completed state.'},
                         {'role': 'user', 'content': native_prompt()}],
            'model': 'fixture', 'max_tokens': 32000, 'thinking': {'type': 'adaptive'},
            'output_config': {'effort': 'high'},
            'tools': [{'name': 'Read', 'input_schema': {'type': 'object'}}]}


class CompactionFormatting(unittest.TestCase):
    def test_disabled_is_identical_even_for_native_request(self):
        req = request()
        for enabled in (False, None, 1, 'true'):
            self.assertIs(concise_compaction_request(req, enabled), req)

    def test_preserves_every_original_field_and_all_custom_instructions(self):
        req = request(); before = copy.deepcopy(req)
        changed = concise_compaction_request(req, True)
        self.assertEqual(req, before)
        self.assertEqual({k: v for k, v in changed.items() if k != 'messages'},
                         {k: v for k, v in req.items() if k != 'messages'})
        self.assertEqual(changed['messages'][:-1], req['messages'])
        self.assertEqual(changed['messages'][-1], {'role': 'system', 'content': HINT.strip()})
        self.assertIs(concise_compaction_request(changed, True), changed)

    def test_text_block_metadata_is_preserved(self):
        req = request()
        req['messages'][-1]['content'] = [{'type': 'text', 'text': native_prompt(),
                                         'cache_control': {'type': 'ephemeral'}}]
        changed = concise_compaction_request(req, True)
        self.assertEqual(changed['messages'][:-1], req['messages'])

    def test_multiple_text_blocks_and_large_transcript_prefix_are_preserved(self):
        req = request()
        prefix = {'type': 'text', 'text': 'Original transcript. ' * 10000,
                  'cache_control': {'type': 'ephemeral'}}
        req['messages'][-1]['content'] = [prefix, {'type': 'text', 'text': native_prompt()}]
        changed = concise_compaction_request(req, True)
        self.assertEqual(changed['messages'][:-1], req['messages'])

    def test_gateway_system_trailer_is_preserved_and_never_scans_past_assistant(self):
        req = request(); trailer = {'role': 'system', 'content': 'Existing gateway policy.'}
        req['messages'].append(trailer)
        changed = concise_compaction_request(req, True)
        self.assertEqual(changed['messages'][:-1], req['messages'])
        req['messages'].insert(-1, {'role': 'assistant', 'content': 'A later answer.'})
        self.assertIs(concise_compaction_request(req, True), req)

    def test_rendered_conversation_prefix_is_identical_before_summary_hint(self):
        req = request(); req['messages'].append({'role': 'system', 'content': 'Existing hook context.'})
        template = ChatTemplate(Path(__file__).parent/'chat_template.jinja')
        messages, tools, kw = anthropic_to_messages(req)
        before = template.render(messages, tools, **kw)
        changed, shown, options = anthropic_to_messages(concise_compaction_request(req, True))
        after = template.render(changed, shown, **options)
        self.assertTrue(after.startswith(before.rsplit('<|im_start|>assistant', 1)[0]))

    def test_summary_words_in_normal_task_or_old_history_do_not_match(self):
        req = request(); req['messages'].append({'role': 'user', 'content': 'Summarize the code.'})
        self.assertIs(concise_compaction_request(req, True), req)
        req['messages'][-1]['content'] = 'x' * 1200 + '9. Optional Next Step:'
        self.assertIs(concise_compaction_request(req, True), req)

    def test_changed_template_or_missing_guard_is_unchanged(self):
        for removed in ('Your task is to create a detailed summary', '6. All user messages:',
                        'Tool calls will be rejected', '<summary>'):
            req = request(); req['messages'][-1]['content'] = native_prompt().replace(removed, '')
            with self.subTest(removed=removed):
                self.assertIs(concise_compaction_request(req, True), req)

    def test_mixed_content_tool_result_assistant_and_oversized_prompt_are_unchanged(self):
        variants = [
            {'role': 'assistant', 'content': native_prompt()},
            {'role': 'user', 'content': [{'type': 'tool_result', 'content': native_prompt()}]},
            {'role': 'user', 'content': [{'type': 'text', 'text': native_prompt()}, {'type': 'image'}]},
            {'role': 'user', 'content': native_prompt() + 'x' * 30000},
        ]
        for last in variants:
            req = request(); req['messages'][-1] = last
            with self.subTest(kind=last['role']):
                self.assertIs(concise_compaction_request(req, True), req)


class CompactionHttp(unittest.TestCase):
    def setUp(self):
        tok = ByteTokenizer()
        self.svc = Service(MockEngine(tok, '<summary>fixture</summary>', max_context=65536), tok,
                           ChatTemplate(Path(__file__).parent/'chat_template.jinja'))
        self.server = serve(self.svc, port=0)
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, path, req):
        with urlopen(Request(self.base+path, data=json.dumps(req).encode(),
                             headers={'Content-Type': 'application/json'}), timeout=10) as response:
            return json.load(response)

    def test_count_matches_generation_with_option_enabled_and_normal_request_unchanged(self):
        req = request(); req.update(max_tokens=256, thinking={'type': 'disabled'})
        req.pop('output_config'); req.pop('tools')
        self.assertIs(self.svc.anthropic_compact_summary, False)
        before = self.post('/v1/messages/count_tokens', req)['input_tokens']
        self.svc.anthropic_compact_summary = True
        changed = concise_compaction_request(req, True)
        messages, tools, kw = anthropic_to_messages(changed)
        expected = len(self.svc.encode_prompt(messages, tools, kw))
        count = self.post('/v1/messages/count_tokens', req)['input_tokens']
        response = self.post('/v1/messages', req)
        self.assertGreater(count, before)
        self.assertEqual(count, expected)
        self.assertEqual(response['usage']['input_tokens'], count)
        req['messages'][-1]['content'] = 'Ordinary work.'
        after = self.post('/v1/messages/count_tokens', req)['input_tokens']
        self.svc.anthropic_compact_summary = False
        self.assertEqual(self.post('/v1/messages/count_tokens', req)['input_tokens'], after)


if __name__ == '__main__':
    unittest.main()
