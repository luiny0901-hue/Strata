"""Read-back evidence must follow a real mutation; tool counts alone are not proof."""
import unittest
from tools.benchmark_live_acp_io import verified_readback


def event(time, name, status='completed', text=''):
    return {'seconds':time,'event':{'params':{'update':{'sessionUpdate':'tool_call_update','toolCallId':str(time),
            'title':name,'status':status,'locations':[{'path':'fixture/result.txt'}],
            'content':[{'type':'content','content':{'type':'text','text':text}}]}}}}


class Readback(unittest.TestCase):
    def test_edit_then_one_read_is_sufficient(self):
        self.assertTrue(verified_readback([event(1,'edit'),event(2,'read',text='1: TOTAL=43')],'TOTAL=43\n')[0])

    def test_old_reads_or_reports_cannot_replace_mutation(self):
        self.assertFalse(verified_readback([event(1,'read',text='1: TOTAL=42'),event(2,'read',text='1: TOTAL=42')],'TOTAL=43\n')[0])
        self.assertFalse(verified_readback([event(1,'read',text='1: TOTAL=43'),event(2,'edit')],'TOTAL=43\n')[0])

    def test_failed_mutation_is_not_verified(self):
        self.assertFalse(verified_readback([event(1,'edit','failed'),event(2,'read',text='1: TOTAL=43')],'TOTAL=43\n')[0])


if __name__ == '__main__':
    unittest.main()
