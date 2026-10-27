"""Messages HTTP contracts with a CPU MockEngine; no GPU/service restart."""
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from serve.frontend import ChatTemplate
from serve.server import ByteTokenizer,MockEngine,Service,serve

TOOL={'name':'save_file','input_schema':{'type':'object','properties':{'content':{'type':'string'}},'required':['content']}}
CALL='<tool_call>\n<function=save_file>\n<parameter=content>\nhello\n</parameter>\n</function>\n</tool_call>'


class MessagesGuardHTTP(unittest.TestCase):
    def setUp(self):
        self.tok=ByteTokenizer()
        self.svc=Service(MockEngine(self.tok,'answer',max_context=16384),self.tok,
                         ChatTemplate(Path(__file__).parent/'chat_template.jinja'))
        self.svc.anthropic_response_guard=True
        self.httpd=serve(self.svc,port=0)
        self.base='http://127.0.0.1:'+str(self.httpd.server_address[1])

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close()

    def post(self,script,**extra):
        self.svc.engine=MockEngine(self.tok,script,max_context=16384)
        body={'model':'test','messages':[{'role':'user','content':'task'}],
              'thinking':{'type':'disabled'},'max_tokens':2048,**extra}
        try: response=urlopen(Request(self.base+'/v1/messages',data=json.dumps(body).encode(),
                                      headers={'Content-Type':'application/json'}),timeout=10)
        except HTTPError as error: response=error
        with response:
            raw=response.read().decode()
            return response.status,raw if extra.get('stream') else json.loads(raw)

    def test_tool_request_suppresses_narration_in_both_delivery_modes(self):
        for stream in (False,True):
            with self.subTest(stream=stream):
                code,body=self.post('Saved.\n'+CALL+'\nFinished.',tools=[TOOL],stream=stream)
                self.assertEqual(code,200)
                if stream:
                    packets=[json.loads(l[6:]) for l in body.splitlines() if l.startswith('data: ')]
                    self.assertFalse([p for p in packets if p.get('delta',{}).get('type')=='text_delta'])
                    self.assertTrue(any(p.get('content_block',{}).get('type')=='tool_use' for p in packets))
                    self.assertEqual(packets[-2]['delta']['stop_reason'],'tool_use')
                else:
                    self.assertEqual([b['type'] for b in body['content']],['tool_use'])
                    self.assertEqual(body['content'][0]['input'],{'content':'hello'})
                    self.assertEqual(body['stop_reason'],'tool_use')

    def test_disabled_mode_preserves_text_and_no_tool_final_reports_are_retained(self):
        self.svc.anthropic_response_guard=False
        _,reply=self.post('Saved.\n'+CALL,tools=[TOOL])
        self.assertTrue(any(b['type']=='text' and 'Saved.' in b['text'] for b in reply['content']))
        self.svc.anthropic_response_guard=True
        for text in ['파일을 저장했습니다.','도구가 거부되어 미완료입니다.','설명만 제공합니다.']:
            _,reply=self.post(text,tools=[TOOL])
            self.assertEqual(''.join(b.get('text','') for b in reply['content']),text)

    def test_json_excludes_prose_in_stream_and_nonstream_replies(self):
        for stream in (False,True):
            code,reply=self.post('설명입니다.\n{"modules":["core"],"cost":4}',system='Return only JSON.',stream=stream)
            self.assertEqual(code,200)
            if stream:
                packets=[json.loads(l[6:]) for l in reply.splitlines() if l.startswith('data: ')]
                text=''.join(p.get('delta',{}).get('text','') for p in packets)
            else: text=''.join(b.get('text','') for b in reply['content'])
            self.assertEqual(json.loads(text),{'modules':['core'],'cost':4})
            self.assertNotIn('설명',text)

    def test_bad_json_is_an_error_never_a_successful_final_text(self):
        code,reply=self.post('{"a":1}{"b":2}',system='Return only JSON.')
        self.assertEqual(code,502)
        self.assertEqual(reply['error']['code'],'structured_output_failed')
        code,raw=self.post('not JSON',system='Return only JSON.',stream=True)
        self.assertEqual(code,200)
        self.assertIn('event: error',raw)
        self.assertNotIn('"text_delta"',raw)
        self.assertNotIn('event: message_stop',raw)

    def test_native_compaction_does_not_inherit_an_old_user_json_directive(self):
        from serve.test_anthropic_compaction import request
        req=request();req['messages'][0]['content']='Return only JSON.'
        req['thinking']={'type':'disabled'};req['max_tokens']=2048
        self.svc.anthropic_compact_summary=True
        code,reply=self.post('<summary>Current state and remaining work.</summary>',**req)
        self.assertEqual(code,200)
        self.assertEqual(''.join(b.get('text','') for b in reply['content']),
                         '<summary>Current state and remaining work.</summary>')


if __name__=='__main__':unittest.main()
