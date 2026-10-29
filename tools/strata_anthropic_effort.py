"""Map Anthropic's selected effort to Strata's opt-in thinking token cap."""

from __future__ import annotations


EFFORT_LEVELS = ("low", "medium", "high")
MAX_EFFORT_BUDGET = 262144
CODEX_WIRE_EFFORTS = {4096: "low", 8192: "medium", 16384: "high"}
CODEX_DEFAULT_BUDGETS = {"low": 3072, "medium": 4096, "high": 8192}


def clean_anthropic_effort_budgets(value) -> dict[str, int]:
    """Validate the optional config map. Missing config preserves the legacy shared budget."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('anthropic_effort_budgets must be an object with low, medium and/or high keys')
    unknown = set(value) - set(EFFORT_LEVELS)
    if unknown:
        raise ValueError(f"anthropic_effort_budgets has unknown effort {sorted(unknown)[0]!r}")
    clean = {}
    for effort, budget in value.items():
        if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= MAX_EFFORT_BUDGET:
            raise ValueError(f"anthropic_effort_budgets.{effort} must be a whole number from 1 to "
                             f"{MAX_EFFORT_BUDGET}")
        clean[effort] = budget
    return clean


def request_with_anthropic_effort_budget(req: dict, budgets: dict[str, int], *, codex_budget_labels: bool = False) -> dict:
    """Apply a configured cap only to Anthropic effort requests that did not supply their own budget.

    Explicit reasoning_budget_tokens (including 0), disabled thinking, and legacy enabled thinking with its own
    budget retain precedence. Adaptive thinking is different: modern Claude requests use it together with
    output_config.effort, so the configured Strata cap must still follow that effort. The thinking object is preserved.
    The input request is never mutated. The optional Codex wire mode recognizes only its three known label budgets;
    other callers retain the legacy behavior. Without either opt-in, the request object is unchanged.
    """
    if not isinstance(req, dict) or req.get("reasoning_budget_tokens") is not None:
        return req
    thinking = req.get("thinking")
    output_config = req.get("output_config")
    # Opt-in OpenCodex compatibility: its generic Anthropic adapter encodes the
    # selected labels as budgets whose thresholds differ from Strata's frontend.
    # Native effort controls and explicit Strata caps keep their precedence.
    if (codex_budget_labels and isinstance(thinking, dict) and thinking.get("type") == "enabled"
            and (output_config is None or isinstance(output_config, dict))
            and not (output_config or {}).get("effort")):
        wire_budget = thinking.get("budget_tokens")
        effort = CODEX_WIRE_EFFORTS.get(wire_budget) if type(wire_budget) is int else None
        if effort is not None:
            return {**req, "output_config": {**(output_config or {}), "effort": effort},
                    "reasoning_budget_tokens": budgets.get(effort, CODEX_DEFAULT_BUDGETS[effort])}
    if not budgets:
        return req
    if isinstance(thinking, dict) and thinking.get("type") != "adaptive":
        return req
    if not isinstance(output_config, dict):
        return req
    effort = output_config.get("effort")
    budget = budgets.get(effort) if effort in EFFORT_LEVELS else None
    if budget is None:
        return req
    return {**req, "reasoning_budget_tokens": budget}
