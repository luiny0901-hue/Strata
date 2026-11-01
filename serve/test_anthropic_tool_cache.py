"""Prompt placement must retain tool capability, history, and API token accounting."""
import copy
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from serve.frontend import ChatTemplate, anthropic_to_messages, anthropic_tool_cache_prompt
from serve.server import ByteTokenizer, MockEngine, Service, serve

ROOT = Path(__file__).resolve().parents[1]
NAME = 'mcp__fixture__count'


def request():
    return {
        'system': 'Keep the original policy.',
        'messages': [
            {'role':'user','content':'KEEP_PREFIX_' * 100},
            {'role':'assistant','content':[{'type':'tool_use','id':'search-1','name':'ToolSearch','input':{}}]},
            {'role':'user','content':[{'type':'tool_result','tool_use_id':'search-1','content':[
                {'type':'text','text':'Search result.'},{'type':'tool_reference','tool_name':NAME}]}]},
        ],
        'tools': [
            {'name':'ToolSearch','input_schema':{'type':'object'}},
            {'name':NAME,'description':'Return a bounded count.','defer_loading':True,
             'input_schema':{'type':'object','properties':{'limit':{'type':'integer'}},'required':['limit']}},
            {'name':'mcp__fixture__unused','description':'UNSELECTED_CATALOG','defer_loading':True,
             'input_schema':{'type':'object'}},
        ],
        'thinking':{'type':'disabled'},'max_tokens':256,
    }


def project(req):
    messages, tools, kw = anthropic_to_messages(req)
    projected, shown = anthropic_tool_cache_prompt(req, messages, tools)
    return messages, tools, projected, shown, kw


class ToolCacheProjection(unittest.TestCase):
    def test_selected_schema_moves_but_callable_tools_and_original_input_are_preserved(self):
        req=request(); original=copy.deepcopy(req)
        messages,tools,projected,shown,_=project(req)
        self.assertEqual({t['name'] for t in tools},{'ToolSearch',NAME})
        self.assertEqual([t['name'] for t in shown],['ToolSearch'])
        self.assertNotIn(NAME,json.dumps(messages))
        self.assertIn(NAME,projected[-1]['content'])
        self.assertIn('Search result.',projected[-1]['content'])
        self.assertNotIn('UNSELECTED_CATALOG',json.dumps(projected))
        self.assertEqual(req,original)

    def test_long_prefix_is_identical_when_search_adds_a_definition(self):
        req=request()
        before=copy.deepcopy(req);before['messages']=before['messages'][:1]
        _,_,bm,bt,kw=project(before)
        _,_,am,at,_=project(req)
        template=ChatTemplate(ROOT/'serve/chat_template.jinja')
        prefix=template.render(bm,bt,**kw).split('<|im_start|>assistant')[0]
        self.assertTrue(template.render(am,at,**kw).startswith(prefix))

    def test_repeated_reference_does_not_repeat_definition(self):
        req=request()
        req['messages'].append(copy.deepcopy(req['messages'][-1]))
        _,_,messages,_,_=project(req)
        self.assertEqual(json.dumps(messages).count('Return a bounded count.'),1)

    def test_images_and_text_beside_references_are_preserved(self):
        req=request()
        req['messages'][-1]['content'][0]['content'].append(
            {'type':'image','source':{'type':'url','url':'https://example.test/image.png'}})
        messages,_,projected,_,_=project(req)
        before=next(m for m in messages if m['role']=='tool')['content']
        after=next(m for m in projected if m['role']=='tool')['content']
        self.assertEqual(after[:-1],before)
        self.assertIn(NAME,after[-1]['text'])

    def test_compaction_without_reference_keeps_prior_used_definition_in_header(self):
        req=request()
        req['messages']=req['messages'][:1]+[{'role':'assistant','content':[
            {'type':'tool_use','id':'call-1','name':NAME,'input':{'limit':2}}]}]
        messages,tools,projected,shown,_=project(req)
        self.assertIs(messages,projected)
        self.assertIs(tools,shown)
        self.assertIn(NAME,{t['name'] for t in shown})

    def test_updated_or_revoked_schema_is_not_retained_in_a_process_cache(self):
        req=request()
        req['tools'][1]['description']='UPDATED_SCHEMA'
        self.assertIn('UPDATED_SCHEMA',project(req)[2][-1]['content'])
        req['tools'].pop(1)
        _,tools,messages,shown,_=project(req)
        self.assertNotIn(NAME,json.dumps(messages)+json.dumps(shown)+json.dumps(tools))

    def test_eager_only_or_no_visible_reference_returns_original_objects(self):
        for mode in ['eager','no-reference','deferred-only']:
            req=request()
            if mode=='eager':
                req['tools'][1]['defer_loading']=False
            elif mode=='no-reference':
                req['messages']=req['messages'][:1]
            else:
                req['tools']=req['tools'][1:]
            messages,tools,projected,shown,_=project(req)
            self.assertIs(messages,projected)
            self.assertIs(tools,shown)

    def test_unknown_or_quoted_names_do_not_load_a_schema(self):
        req=request()
        req['messages'][-1]['content'][0]['content']=[{'type':'text','text':NAME},
            {'type':'tool_reference','tool_name':'not-in-catalog'}]
        _,_,messages,shown,_=project(req)
        self.assertEqual([t['name'] for t in shown],['ToolSearch'])
        self.assertNotIn('Return a bounded count.',json.dumps(messages))

    def test_no_offered_tools_never_injects_a_definition(self):
        req=request();messages,_,_=anthropic_to_messages(req)
        projected,shown=anthropic_tool_cache_prompt(req,messages,None)
        self.assertIs(projected,messages)
        self.assertIsNone(shown)

    def test_ambiguous_duplicate_names_keep_the_existing_prompt(self):
        req=request();req['tools'].append(copy.deepcopy(req['tools'][1]))
        messages,tools,projected,shown,_=project(req)
        self.assertIs(messages,projected)
        self.assertIs(tools,shown)


class ToolCacheHttp(unittest.TestCase):
    def setUp(self):
        self.tok=ByteTokenizer()
        reply='<tool_call>\n<function='+NAME+'>\n<parameter=limit>2</parameter>\n</function>\n</tool_call>'
        self.svc=Service(MockEngine(self.tok,reply,max_context=65536),self.tok,
                         ChatTemplate(ROOT/'serve/chat_template.jinja'))
        self.server=serve(self.svc,port=0)
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self,path,req):
        with urlopen(Request(self.base+path,data=json.dumps(req).encode(),
                     headers={'Content-Type':'application/json'}),timeout=10) as response:
            return json.load(response)

    def test_default_is_off_and_disabled_prompt_matches_existing_format(self):
        self.assertIs(self.svc.anthropic_tool_cache,False)
        req=request();messages,tools,kw=anthropic_to_messages(req)
        expected=len(self.svc.encode_prompt(messages,tools,kw))
        self.assertEqual(self.post('/v1/messages/count_tokens',req)['input_tokens'],expected)

    def test_count_and_generation_agree_and_parser_still_uses_integer_schema(self):
        self.svc.anthropic_tool_cache=True
        req=request()
        count=self.post('/v1/messages/count_tokens',req)['input_tokens']
        response=self.post('/v1/messages',req)
        self.assertEqual(response['usage']['input_tokens'],count)
        calls=[c for c in response['content'] if c['type']=='tool_use']
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['name'],NAME)
        self.assertEqual(calls[0]['input'],{'limit':2})
        self.assertIs(type(calls[0]['input']['limit']),int)

    def test_count_with_tool_choice_none_excludes_definitions(self):
        self.svc.anthropic_tool_cache=True
        req=request();req['tool_choice']={'type':'none'}
        messages,_,kw=anthropic_to_messages(req)
        expected=len(self.svc.encode_prompt(messages,None,kw))
        self.assertEqual(self.post('/v1/messages/count_tokens',req)['input_tokens'],expected)

    def test_forced_name_is_still_available_after_projection(self):
        self.svc.anthropic_tool_cache=True
        req=request();req['tool_choice']={'type':'tool','name':NAME}
        response=self.post('/v1/messages',req)
        self.assertTrue(any(c.get('name')==NAME for c in response['content']))

    def test_openai_prompt_is_unchanged_when_the_anthropic_option_is_enabled(self):
        native=request()
        req={'messages':[{'role':'user','content':'Use the count tool.'}], 'max_tokens':256,
             'chat_template_kwargs':{'enable_thinking':False},
             'tools':[{'type':'function','function':{'name':t['name'],'description':t.get('description',''),
                       'parameters':t['input_schema']}} for t in native['tools']]}
        before=self.post('/v1/chat/completions',req)
        self.svc.anthropic_tool_cache=True
        after=self.post('/v1/chat/completions',req)
        self.assertEqual(before['usage']['prompt_tokens'],after['usage']['prompt_tokens'])
        self.assertEqual(before['choices'][0]['message']['tool_calls'][0]['function'],
                         after['choices'][0]['message']['tool_calls'][0]['function'])


if __name__=='__main__':unittest.main()
