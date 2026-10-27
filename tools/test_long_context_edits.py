import unittest
from tools.benchmark_long_context_edits import verify


class ScopedCodeTests(unittest.TestCase):
    def test_function_docstring_preserves_functional_verification(self):
        code = '''def total(price, quantity):
    """Return the order total, including discounts and shipping."""
    if price < 0 or quantity < 0:
        return -1
    if quantity == 0:
        return 0
    subtotal = price * quantity
    if quantity >= 10:
        subtotal *= 0.9
    if subtotal < 100:
        subtotal += 5
    return subtotal
'''
        self.assertTrue(all(row['pass'] for row in verify(code, 2)))
        self.assertFalse(all(row['pass'] for row in verify(code.replace('subtotal *= 0.9', 'subtotal *= 0.8'), 2)))

    def test_docstrings_do_not_enable_other_expressions_or_execution(self):
        rejected = [
            'def total(price, quantity):\n    "doc"\n    price + quantity\n    return price * quantity\n',
            'def total(price, quantity):\n    "doc"\n    return eval("1")\n',
            'def total(price, quantity):\n    f"{price}"\n    return price * quantity\n',
            '"module doc"\ndef total(price, quantity):\n    return price * quantity\n',
            'def total(price, quantity):\n    "doc"\n    import os\n    return 0\n',
        ]
        for code in rejected:
            with self.subTest(code=code), self.assertRaises(ValueError):
                verify(code, 2)

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
