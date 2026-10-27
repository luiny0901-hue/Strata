"""CPU contracts for one policy-bound background conversation restoration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import claude_desktop_restore as ui

SID = '11111111-2222-4333-8444-555555555555'


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'session.json'
        self.row = {'sessionId': 'local_'+SID, 'cliSessionId': SID, 'title': 'Exact diagnostic', 'lastFocusedAt': 10}
        self.path.write_text(json.dumps(self.row))
        self.state = {'pid': 17, 'window_id': 28, 'truncated': False, 'elements_complete': True,
            'snapshot_id': 's12345678', 'elements': [{'role': 'Button', 'enabled': True,
            'label': self.row['title'], 'actions': ['invoke'], 'element_token': 's12345678:9'}]}

    def test_current_complete_unique_semantic_button(self):
        self.assertEqual(ui.exact_conversation_button(self.state, pid=17, window_id=28,
                                                     title=self.row['title']), 's12345678:9')

    def test_pruned_layout_nodes_require_explicit_drained_walk_and_counts(self):
        state = dict(self.state, elements_complete=False, nodes_pending=0, nodes_visited=3,
                     total_element_count=1, returned_element_count=1)
        self.assertEqual(ui.exact_conversation_button(state, pid=17, window_id=28,
                                                     title=self.row['title']), 's12345678:9')
        for change in ({'nodes_pending':1}, {'total_element_count':2}, {'returned_element_count':0}):
            with self.assertRaises(ValueError):
                ui.exact_conversation_button(dict(state, **change), pid=17, window_id=28, title=self.row['title'])

    def test_ambiguous_partial_stale_or_wrong_window_never_selects_a_button(self):
        variants = [dict(self.state, truncated=True), dict(self.state, elements_complete=False),
                    dict(self.state, pid=18), dict(self.state, elements=self.state['elements']*2),
                    dict(self.state, snapshot_id='s87654321')]
        for state in variants:
            with self.subTest(state=state), self.assertRaises(ValueError):
                ui.exact_conversation_button(state, pid=17, window_id=28, title=self.row['title'])

    def test_background_click_once_then_exact_focus_proof(self):
        calls = []; state = self.state; row = self.row; path = self.path
        class Server:
            def call(self, name, args, **kwargs):
                calls.append((name, args))
                if name == 'list_windows':
                    return {'structuredContent': {'windows': [{'pid':17,'window_id':28,'is_on_screen':True}]}}
                if name == 'get_window_state':
                    return {'structuredContent': state}
                path.write_text(json.dumps(dict(row, lastFocusedAt=11)))
                return {'structuredContent': {'effect':'confirmed', 'route':'accessibility', 'delivery':{'mode':'background'}}}
        class System:
            def matches(self, value): return True
        with patch.object(ui, 'search_catalog', side_effect=lambda server, name, *a, **k: [{'name':name}]):
            result = ui.restore(Server(), System(), {'pid':17}, path, SID, deadline=time.monotonic()+3)
        self.assertEqual(result['click_count'], 1)
        self.assertEqual(calls[-1], ('click', {'element_token':'s12345678:9','delivery_mode':'background'}))
        self.assertFalse(any('x' in args or 'y' in args for _, args in calls))

    def test_ambiguous_sidebar_performs_no_input(self):
        state = dict(self.state, elements=self.state['elements']*2); calls=[]
        class Server:
            def call(self, name, args, **kwargs):
                calls.append(name)
                if name == 'list_windows':
                    return {'structuredContent': {'windows':[{'pid':17,'window_id':28,'is_on_screen':True}]}}
                return {'structuredContent':state}
        with patch.object(ui, 'search_catalog', side_effect=lambda server, name, *a, **k:[{'name':name}]):
            with self.assertRaises(ValueError):
                ui.restore(Server(), None, {'pid':17}, self.path, SID, deadline=time.monotonic()+3)
        self.assertNotIn('click',calls)


if __name__ == '__main__':
    unittest.main()
