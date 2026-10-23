import unittest
from tools.benchmark_long_context_edits import verify


class ScopedCodeTests(unittest.TestCase):
    def test_three_stage_contract(self):
        base='def total(price, quantity):\n    if price < 0 or quantity < 0: return -1\n'
        codes=[base+'    return price * quantity\n',
               base+'    subtotal = price * quantity\n    if quantity >= 10: subtotal *= 0.9\n    return subtotal\n',
               base+'    if quantity == 0: return 0\n    subtotal = price * quantity\n    if quantity >= 10: subtotal *= 0.9\n    if subtotal < 100: subtotal += 5\n    return subtotal\n']
        for stage,code in enumerate(codes):
            self.assertTrue(all(c['pass'] for c in verify(code,stage)))

    def test_disallow_side_effects_and_unbounded_execution(self):
        for code in ['import os\ndef total(price, quantity): return 0',
                     'def total(price, quantity):\n    while True: pass',
                     'def total(price, quantity): return open("x")',
                     '@print\ndef total(price, quantity): return 0',
                     'def total(price, quantity=print()): return 0']:
            with self.assertRaises(ValueError):verify(code,0)


if __name__=='__main__':unittest.main()
