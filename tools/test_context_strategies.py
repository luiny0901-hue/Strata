"""CPU-only fixture/answer-validation tests; never contact a model server."""
import unittest
from tools.benchmark_context_strategies import fixture,extract,EXPECTED


class ContextFixtureTests(unittest.TestCase):
    def test_fixture_is_reproducible_and_preserves_distant_contracts(self):
        text=fixture(100)
        self.assertEqual(text,fixture(100))
        self.assertEqual(text.count('CONTRACT '),3)
        self.assertTrue(text.startswith('CONTRACT early=E17 retry_limit=3'))
        self.assertTrue(text.endswith('CONTRACT late=L43\n'))
        self.assertLess(text.index('early=E17'),text.index('middle=M29'))
        self.assertLess(text.index('middle=M29'),text.index('late=L43'))

    def test_validator_preserves_types_and_detects_missing_or_changed_values(self):
        import json
        self.assertEqual(extract('```json\n'+json.dumps(EXPECTED)+'\n```'),EXPECTED)
        self.assertNotEqual(extract(json.dumps({**EXPECTED,'retry_limit':'3'})),EXPECTED)
        self.assertNotEqual(extract(json.dumps({**EXPECTED,'middle':None})),EXPECTED)
        self.assertIsNone(extract('no structured answer'))


if __name__=='__main__':unittest.main()
