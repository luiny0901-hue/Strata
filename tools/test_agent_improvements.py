import unittest
from tools.benchmark_agent_improvements import apply_exact,edit_fixture,verify_edit


class ModificationChecks(unittest.TestCase):
    def test_partial_and_whole_same_contract(self):
        source=edit_fixture()
        self.assertFalse(verify_edit(source))
        changed=apply_exact(source,'def value_050():\n    return 50','def value_050():\n    return 1050')
        self.assertTrue(verify_edit(changed))
        self.assertFalse(verify_edit(changed.replace('return 49','return 1049')))

    def test_ambiguous_edit_rejected(self):
        for old in ('', 'missing','return '):
            with self.assertRaises(ValueError):apply_exact(edit_fixture(),old,'changed')


if __name__=='__main__':unittest.main()
