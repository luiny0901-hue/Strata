"""CPU checks for the representative-context OpenCode integration verifier."""

from __future__ import annotations

import unittest

from tools.verify_opencode_context_matrix import receipt_from, verify_receipt


class ContextMatrixTests(unittest.TestCase):
    def test_receipt_requires_checkpoint_and_completed_follow_up(self):
        receipt = {
            "result": "PASS",
            "model_context": 8_192,
            "compaction": {"keep": 1_024, "buffer": 2_048, "trigger": 6_144},
            "compacted_checkpoint_requests": 1,
            "workflow_file": "revised by follow-up\n",
            "model_requests": 8,
        }
        self.assertEqual(verify_receipt(receipt, 8_192)["buffer"], 2_048)

    def test_receipt_rejects_missing_checkpoint(self):
        with self.assertRaisesRegex(ValueError, "no conversation checkpoint"):
            verify_receipt(
                {
                    "result": "PASS",
                    "model_context": 8_192,
                    "compaction": {"keep": 1_024, "buffer": 2_048, "trigger": 6_144},
                    "compacted_checkpoint_requests": 0,
                    "workflow_file": "revised by follow-up\n",
                },
                8_192,
            )

    def test_receipt_parser_uses_the_final_json_receipt(self):
        self.assertEqual(receipt_from("noise\n{\"result\": \"PASS\"}\n")["result"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
