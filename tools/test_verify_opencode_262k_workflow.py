"""CPU-only checks for the bounded OpenCode 262K workflow verifier."""

from __future__ import annotations

import unittest

from tools.verify_opencode_262k_workflow import (
    COMPACTION_BUFFER,
    COMPACTION_KEEP,
    COMPACTION_TRIGGER,
    CONTEXT_LIMIT,
    checkpoint_request_count,
)


class WorkflowVerifierTests(unittest.TestCase):
    def test_262k_policy_keeps_the_configured_summary_tail(self):
        self.assertEqual(CONTEXT_LIMIT, 262_144)
        self.assertEqual(COMPACTION_KEEP, 12_000)
        self.assertEqual(COMPACTION_BUFFER, 65_536)
        self.assertEqual(COMPACTION_TRIGGER, 196_608)

    def test_checkpoint_detector_requires_the_serialized_checkpoint_marker(self):
        requests = [
            {"messages": [{"role": "user", "content": "ordinary request"}]},
            {"messages": [{"role": "user", "content": "<conversation-checkpoint>summary</conversation-checkpoint>"}]},
        ]
        self.assertEqual(checkpoint_request_count(requests), 1)


if __name__ == "__main__":
    unittest.main()
