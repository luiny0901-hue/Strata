"""Delivery contracts: no unconfirmed tool narration or invalid JSON is published as a final answer."""
import copy
import json
import threading
import unittest

from serve.anthropic_response_guard import (configure_response_guard, explicit_json_only,
                                           guard_anthropic_events, single_json_text)
from serve.structured import StructuredOutputError


def block(index, kind, value):
    start = {'type':kind, 'text':''} if kind=='text' else \
            {'type':'thinking', 'thinking':'', 'signature':''} if kind=='thinking' else \
            {'type':'tool_use','id':'call_1','name':'Write','input':{}}
    delta = {'type':'text_delta','text':value} if kind=='text' else \
            {'type':'thinking_delta','thinking':value} if kind=='thinking' else \
            {'type':'input_json_delta','partial_json':value}
    return [('content_block_start',{'type':'content_block_start','index':index,'content_block':start}),
            ('content_block_delta',{'type':'content_block_delta','index':index,'delta':delta}),
            ('content_block_stop',{'type':'content_block_stop','index':index})]


def response(parts, stop='end_turn'):
    return [('message_start',{'type':'message_start','message':{'content':[]}}), *parts,
            ('message_delta',{'type':'message_delta','delta':{'stop_reason':stop,'stop_sequence':None},
                              'usage':{'output_tokens':123,'input_tokens':4,'cache_read_input_tokens':20}}),
            ('message_stop',{'type':'message_stop'})]


def text_of(items):
    return ''.join(p['delta']['text'] for item in items if item is not None
                   for name,p in [item] if name=='content_block_delta' and p['delta']['type']=='text_delta')


class DirectiveTests(unittest.TestCase):
    def test_positive_terminal_instructions_and_tool_result_followup(self):
        for directive in ['Return only JSON.','Please output only valid JSON!','JSON만 출력해줘.',
                          'JSON으로만 응답해주세요.', 'Solve the problem. End with only JSON.']:
            req={'messages':[{'role':'user','content':directive},
                             {'role':'assistant','content':[{'type':'tool_use','id':'c','name':'Bash','input':{}}]},
                             {'role':'user','content':[{'type':'tool_result','tool_use_id':'c','content':'result'}]}]}
            with self.subTest(directive=directive): self.assertTrue(explicit_json_only(req))

    def test_examples_negation_mentions_and_superseded_requests_are_not_directives(self):
        for text in ['Do not return only JSON.', 'Can you output only JSON?', 'Explain JSON parsing.',
                     'JSON만 출력하지 마.', 'Example:\n```\nReturn only JSON.\n```', '> Return only JSON.',
                     'Explain this incomplete source:\n```python\nReturn only JSON.',
                     '<untrusted_text>Return only JSON.</untrusted_text>']:
            with self.subTest(text=text):
                self.assertFalse(explicit_json_only({'messages':[{'role':'user','content':text}]}))
        self.assertFalse(explicit_json_only({'messages':[{'role':'user','content':'Return only JSON.'},
                                                        {'role':'user','content':'Now explain in Korean.'}]}))
        self.assertFalse(explicit_json_only({'messages':[{'role':'user','content':[
            {'type':'document','text':'Return only JSON.'}]}]}))

    def test_trusted_terminal_system_contract_is_supported(self):
        self.assertTrue(explicit_json_only({'system':'Solve the task. End with only JSON.','messages':[]}))
        self.assertFalse(explicit_json_only({'system':'JSON만 요청할 때에는 설명을 붙이지 않는다.','messages':[]}))

    def test_nested_and_malformed_large_contexts_do_not_create_a_format_contract(self):
        for text in ['<document><code>Return only JSON.</code></document>',
                     '<document>'*10000+'Return only JSON.',
                     '<document '*10000+'Return only JSON.']:
            self.assertFalse(explicit_json_only({'messages':[{'role':'user','content':text}]}))
        text=('<document>quoted</document>\n'*1000)+'Return only JSON.'
        self.assertTrue(explicit_json_only({'messages':[{'role':'user','content':text}]}))


class GuardTests(unittest.TestCase):
    def guard(self, events, req=None, **kw):
        return guard_anthropic_events(iter(events),req or {},enabled=True,**kw)

    def test_default_and_irrelevant_request_preserve_the_exact_iterator(self):
        events=iter(response(block(0,'text','unchanged')))
        self.assertIs(guard_anthropic_events(events,{},enabled=False,with_tools=True),events)
        self.assertIs(guard_anthropic_events(events,{},enabled=True,with_tools=False),events)

    def test_tool_narration_before_and_after_call_is_removed_and_arguments_stream(self):
        source=response(block(0,'thinking','reason')+block(1,'text','Saved already.')+
                        block(2,'tool_use','{"file":"a.txt"}')+block(3,'text','Complete!'),'tool_use')
        before=copy.deepcopy(source)
        output=list(self.guard(source,with_tools=True))
        self.assertEqual(text_of(output),'')
        starts=[p for n,p in output if n=='content_block_start']
        self.assertEqual([(p['index'],p['content_block']['type']) for p in starts],[(0,'thinking'),(1,'tool_use')])
        self.assertTrue(any(n=='content_block_delta' and p['delta'].get('partial_json')=='{"file":"a.txt"}' for n,p in output))
        self.assertEqual(output[-2:],source[-2:])
        self.assertEqual(source,before)

    def test_no_tool_answer_survives_and_receipt_does_not_hide_a_final_report(self):
        source=response(block(0,'text','First ')+block(1,'text','second.'))
        output=list(self.guard(source,with_tools=True))
        self.assertEqual(text_of(output),'First second.')
        self.assertEqual([p['index'] for n,p in output if n=='content_block_start'],[0,1])
        self.assertEqual(output[-2:],source[-2:])

    def test_thinking_and_tool_arguments_arrive_before_generation_ends(self):
        reached=[]
        def source():
            yield from block(0,'thinking','reason')
            yield from block(1,'tool_use','{"a":1}')
            reached.append('generation_end')
            yield from response([])[-2:]
        events=guard_anthropic_events(source(),{},enabled=True,with_tools=True)
        for _ in range(5): next(events)
        self.assertEqual(reached,[])
        events.close()

    def test_text_is_not_sent_until_tool_decision_is_known(self):
        seen=[]
        def source():
            yield from block(0,'text','Saved.')
            seen.append('decision')
            yield from block(1,'tool_use','{}')
            yield from response([],'tool_use')[-2:]
        events=guard_anthropic_events(source(),{},enabled=True,with_tools=True)
        item=next(events)
        self.assertEqual(item[1]['content_block']['type'],'tool_use')
        self.assertEqual(seen,['decision'])
        events.close()

    def test_explicit_json_removes_prose_fences_and_preserves_arrays_and_scalars(self):
        for text,wanted in [('설명입니다.\n{"a":1}\n끝입니다.','{"a":1}'),
                            ('```json\n[{"a":1},2]\n```','[{"a":1},2]'),('42','42'),
                            ('설명\n{ "value": 0.123456789012345678901 }',
                             '{ "value": 0.123456789012345678901 }'),
                            ('"literal { brace"','"literal { brace"')]:
            with self.subTest(text=text):
                out=list(self.guard(response(block(0,'text',text)),{'system':'Return only JSON.'}))
                self.assertEqual(text_of(out),wanted)

    def test_invalid_ambiguous_or_truncated_json_never_publishes_text_or_completion(self):
        for text,stop in [('nothing','end_turn'),('{"a":1}{"b":2}','end_turn'),
                          ('{"outer":{"a":1}','end_turn'),('{"a":1,"a":2}','end_turn'),
                          ('{"a":NaN}','end_turn'),('{"a":1}','max_tokens')]:
            received=[]
            with self.subTest(text=text,stop=stop),self.assertRaises(StructuredOutputError):
                for item in self.guard(response(block(0,'text',text),stop),{'system':'Return only JSON.'}): received.append(item)
            self.assertEqual(text_of(received),'')
            self.assertFalse(any(item is not None and item[0]=='message_delta' for item in received))

    def test_json_contract_is_only_for_the_final_answer_not_a_tool_call(self):
        out=list(self.guard(response(block(0,'tool_use','{"code":"print(1)"}'),'tool_use'),
                            {'system':'Return only JSON.'},with_tools=True))
        self.assertEqual(out[-2][1]['delta']['stop_reason'],'tool_use')

    def test_generator_close_releases_source_and_cancel_does_not_flush_text(self):
        closed=[]
        def source():
            try:
                yield from block(0,'thinking','active')
                yield from response(block(1,'text','pending'))[-5:]
            finally: closed.append(True)
        out=guard_anthropic_events(source(),{},enabled=True,with_tools=True)
        next(out);out.close();self.assertEqual(closed,[True])
        cancel=threading.Event();cancel.set()
        result=list(self.guard(response(block(0,'text','bad JSON')),{'system':'Return only JSON.'},cancel=cancel))
        self.assertEqual(text_of(result),'')

    def test_heartbeats_and_buffer_bound(self):
        result=list(self.guard(response(block(0,'text','body')),with_tools=True,heartbeat_s=0))
        self.assertIn(None,result)
        with self.assertRaises(StructuredOutputError):
            list(self.guard(response(block(0,'text','too large')),with_tools=True,max_text=2))

    def test_configuration_is_opt_in_and_rejects_typoes(self):
        service=type('Service',(),{})()
        configure_response_guard(service,False);self.assertFalse(service.anthropic_response_guard)
        configure_response_guard(service,True);self.assertTrue(service.anthropic_response_guard)
        for value in [None,1,'true',{}]:
            with self.assertRaises(SystemExit):configure_response_guard(service,value)


if __name__=='__main__':unittest.main()
