"""CPU-only checks for the bounded OpenCode 262K workflow verifier."""

from __future__ import annotations

import unittest

from tools.verify_opencode_262k_workflow import (
    COMPACTION_BUFFER,
    COMPACTION_KEEP,
    COMPACTION_TRIGGER,
    CONTEXT_LIMIT,
    checkpoint_request_count,
    configure_context,
)
from tools.configure_opencode_session_recovery import compaction_policy


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

    def test_policy_scales_for_supported_context_lengths(self):
        self.assertEqual(compaction_policy(8_192), {"keep": 1_024, "buffer": 2_048, "trigger": 6_144})
        self.assertEqual(compaction_policy(32_768), {"keep": 4_096, "buffer": 8_192, "trigger": 24_576})
        self.assertEqual(compaction_policy(65_536), {"keep": 8_192, "buffer": 16_384, "trigger": 49_152})
        self.assertEqual(compaction_policy(131_072), {"keep": 12_000, "buffer": 32_768, "trigger": 98_304})
        self.assertEqual(compaction_policy(262_144), {"keep": 12_000, "buffer": 65_536, "trigger": 196_608})

    def test_fixture_context_rejects_an_unusable_context(self):
        with self.assertRaisesRegex(ValueError, "at least 4096"):
            configure_context(2_048)


if __name__ == "__main__":
    unittest.main()
