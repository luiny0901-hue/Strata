"""Anthropic client-owned tool search must not render the deferred catalog."""
import copy
import unittest

from serve.frontend import anthropic_to_messages, openai_to_messages


class DeferredToolsTests(unittest.TestCase):
    def setUp(self):
        self.request = {
            'messages': [{'role': 'user', 'content': 'Use a tool when needed.'}],
            'tools': [
                {'name': 'ToolSearch', 'description': 'Find available tools.', 'input_schema': {'type': 'object'}},
                {'name': 'mcp__rea__analyze', 'description': 'Large analysis schema.',
                 'input_schema': {'type': 'object'}, 'defer_loading': True},
                {'name': 'Read', 'input_schema': {'type': 'object'}, 'defer_loading': False},
            ],
        }

    def test_deferred_catalog_is_not_visible_but_search_and_loaded_tools_remain(self):
        original = copy.deepcopy(self.request)
        _, tools, _ = anthropic_to_messages(self.request)
        self.assertEqual({tool['name'] for tool in tools}, {'Read', 'ToolSearch'})
        self.assertEqual(self.request, original)

    def test_searched_tool_is_available_on_the_following_request(self):
        self.request['messages'].append({'role':'user', 'content':[
            {'type':'tool_result', 'tool_use_id':'search-1', 'content':[
                {'type':'tool_reference', 'tool_name':'mcp__rea__analyze'}]}]})
        _, tools, _ = anthropic_to_messages(self.request)
        self.assertIn('mcp__rea__analyze', {tool['name'] for tool in tools})

    def test_prior_tool_use_remains_available_without_original_search_result(self):
        self.request['messages'].append({'role':'assistant', 'content':[
            {'type':'tool_use', 'id':'call-1', 'name':'mcp__rea__analyze', 'input':{}}]})
        _, tools, _ = anthropic_to_messages(self.request)
        self.assertIn('mcp__rea__analyze', {tool['name'] for tool in tools})

    def test_a_quoted_name_does_not_activate_a_deferred_definition(self):
        self.request['messages'][0]['content'] = 'mcp__rea__analyze'
        _, tools, _ = anthropic_to_messages(self.request)
        self.assertNotIn('mcp__rea__analyze', {tool['name'] for tool in tools})

    def test_only_explicit_true_defers_and_invalid_deferred_schemas_are_validated(self):
        self.request['tools'][1]['defer_loading'] = False
        _, tools, _ = anthropic_to_messages(self.request)
        self.assertEqual(len(tools), 3)
        self.request['tools'][1].update(defer_loading=True, input_schema='invalid')
        with self.assertRaisesRegex(ValueError, 'input_schema'):
            anthropic_to_messages(self.request)

    def test_requests_without_deferral_have_identical_conversion(self):
        for tool in self.request['tools']:
            tool.pop('defer_loading', None)
        expected = anthropic_to_messages(self.request)
        for tool in self.request['tools']:
            tool['defer_loading'] = False
        self.assertEqual(anthropic_to_messages(self.request), expected)

    def test_openai_tool_conversion_is_unchanged(self):
        tools = [{'type': 'function', 'function': {'name': 'Read', 'parameters': {'type': 'object'}},
                  'defer_loading': True}]
        _, converted, _ = openai_to_messages({'messages': self.request['messages'], 'tools': tools})
        self.assertEqual([tool['name'] for tool in converted], ['Read'])


if __name__ == '__main__':
    unittest.main()
