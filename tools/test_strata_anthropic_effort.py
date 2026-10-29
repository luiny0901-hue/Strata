"""Contracts for Claude Messages effort budgets and the downloaded-fork source integration."""

import unittest

from tools.patch_nvfp4_server_effort import PatchError, patch_source
from tools.strata_anthropic_effort import (clean_anthropic_effort_budgets,
                                           request_with_anthropic_effort_budget)


class AnthropicEffortBudgetTests(unittest.TestCase):
    def test_opt_in_codex_labels_have_distinct_native_efforts_and_caps(self):
        for wire, effort, cap in ((4096,'low',3072),(8192,'medium',4096),(16384,'high',8192)):
            req={'thinking':{'type':'enabled','budget_tokens':wire},'output_config':{'format':{'type':'json_schema'}}}
            mapped=request_with_anthropic_effort_budget(req, {}, codex_budget_labels=True)
            self.assertEqual(mapped['output_config'],{'format':{'type':'json_schema'},'effort':effort})
            self.assertEqual(mapped['reasoning_budget_tokens'],cap)
            self.assertNotIn('reasoning_budget_tokens',req)
            self.assertIs(request_with_anthropic_effort_budget(req, {}),req)

    def test_codex_compatibility_preserves_explicit_controls(self):
        for req in (
            {'thinking':{'type':'enabled','budget_tokens':4096},'reasoning_budget_tokens':0},
            {'thinking':{'type':'enabled','budget_tokens':4096},'output_config':{'effort':'high'}},
            {'thinking':{'type':'disabled','budget_tokens':4096}},
            {'thinking':{'type':'enabled','budget_tokens':4097}},
            {'thinking':{'type':'enabled','budget_tokens':True}},
            {'thinking':{'type':'enabled','budget_tokens':4096},'output_config':[]},
        ):
            self.assertIs(request_with_anthropic_effort_budget(req, {}, codex_budget_labels=True),req)
        req={'thinking':{'type':'enabled','budget_tokens':4096}}
        self.assertEqual(request_with_anthropic_effort_budget(req, {'low':1024}, codex_budget_labels=True)['reasoning_budget_tokens'],1024)
    def test_config_is_optional_and_rejects_invalid_values(self):
        self.assertEqual(clean_anthropic_effort_budgets(None), {})
        self.assertEqual(clean_anthropic_effort_budgets({"low": 3072, "medium": 4096, "high": 8192}),
                         {"low": 3072, "medium": 4096, "high": 8192})
        for bad in ([], {"none": 1}, {"low": 0}, {"medium": True}, {"high": 262145}, {"low": "3072"}):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                clean_anthropic_effort_budgets(bad)

    def test_effort_mapping_preserves_explicit_budget_and_thinking(self):
        budgets = {"low": 3072, "medium": 4096, "high": 8192}
        for request in (
                {"output_config": {"effort": "high"}, "reasoning_budget_tokens": 0},
                {"output_config": {"effort": "high"}, "reasoning_budget_tokens": 123},
                {"output_config": {"effort": "high"}, "thinking": {"type": "disabled"}},
                {"output_config": {"effort": "high"}, "thinking": {"type": "enabled", "budget_tokens": 123}},
                {"output_config": {"effort": "high"}, "thinking": {"type": "enabled"}},
                {"thinking": {"type": "adaptive"}},
                {"output_config": {"effort": "xhigh"}},
                {"messages": []},
        ):
            with self.subTest(request=request):
                self.assertIs(request_with_anthropic_effort_budget(request, budgets), request)

    def test_adaptive_thinking_uses_effort_budget_and_keeps_the_standard_request(self):
        budgets = {"low": 3072, "medium": 4096, "high": 8192}
        for effort, budget in budgets.items():
            request = {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}, "messages": []}
            mapped = request_with_anthropic_effort_budget(request, budgets)
            with self.subTest(effort=effort):
                self.assertEqual(mapped, {**request, "reasoning_budget_tokens": budget})
                self.assertEqual(request, {"thinking": {"type": "adaptive"},
                                          "output_config": {"effort": effort}, "messages": []})

    def test_effort_mapping_copies_only_matching_native_anthropic_requests(self):
        request = {"output_config": {"effort": "medium"}, "messages": []}
        mapped = request_with_anthropic_effort_budget(request, {"medium": 4096})
        self.assertEqual(mapped, {**request, "reasoning_budget_tokens": 4096})
        self.assertIsNot(mapped, request)
        self.assertNotIn("reasoning_budget_tokens", request)


class ForkPatchTests(unittest.TestCase):
    SOURCE = '''from serve.responses import ResponsesError, error_body as responses_error_body  # noqa: E402

class Service:
        self.reasoning_budget_tokens = 0                 # #123: the config's default thinking budget (0: none)
    def _vision_down(self) -> bool:
        pass
        def _anthropic(self, req):
            svc.load()
            req = svc.with_shared(req, "anthropic")
            pass
    recovery = cfg.get("reasoning_loop_recovery", False)
'''

    def test_patch_is_complete_and_idempotent(self):
        patched, changed = patch_source(self.SOURCE)
        self.assertTrue(changed)
        self.assertEqual(patched.count("STRATA_ANTHROPIC_EFFORT_BUDGETS_PATCH_V1"), 4)
        self.assertIn("req = svc.budget_anthropic_request(req, codex_budget_labels=", patched)
        self.assertIn('self.headers.get("x-strata-effort-wire") == "opencodex-low-medium-high-v1"', patched)
        self.assertIn('svc.set_anthropic_effort_budgets(cfg.get("anthropic_effort_budgets"))', patched)
        self.assertEqual(patch_source(patched), (patched, False))

    def test_unknown_layout_is_rejected_without_partial_output(self):
        with self.assertRaises(PatchError):
            patch_source("class Service: pass\n")

    def test_known_legacy_patch_upgrades_once_and_unknown_partial_upgrade_is_rejected(self):
        from tools.patch_nvfp4_server_effort import METHODS,REQUEST,LEGACY_METHODS,LEGACY_REQUEST
        current,_=patch_source(self.SOURCE)
        legacy=current.replace(METHODS,LEGACY_METHODS).replace(REQUEST,LEGACY_REQUEST)
        self.assertEqual(patch_source(legacy),(current,True))
        self.assertEqual(patch_source(current),(current,False))
        with self.assertRaises(PatchError):
            patch_source(legacy.replace(LEGACY_REQUEST,REQUEST))


if __name__ == "__main__":
    unittest.main()
