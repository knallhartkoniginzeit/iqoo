from typing import Dict, Any, NamedTuple
from app.config import BUDGETS


class BudgetDecision(NamedTuple):
    allow: bool
    reason: str
    limit_usd: float
    spent_usd: float
    new_total_usd: float


def get_budget_for_key(key_hash: str) -> Dict[str, Any]:
    budgets = BUDGETS.get("budgets", [])
    defaults = BUDGETS.get("defaults", {})
    key_hash_prefix = key_hash[:8]
    for budget in budgets:
        if budget.get("key_hash") == key_hash:
            return budget
        if budget.get("key_hash_prefix") == key_hash_prefix:
            return budget
    return {"label": "default", "daily_limit_usd": defaults.get("daily_limit_usd", 5.0), "hard_block": defaults.get("hard_block", True)}


def check_budget(estimated_cost_usd: float, spent_today_usd: float, limit_usd: float) -> BudgetDecision:
    new_total = spent_today_usd + estimated_cost_usd
    if estimated_cost_usd > limit_usd:
        return BudgetDecision(allow=False, reason="Request cost exceeds daily limit", limit_usd=limit_usd,
                             spent_usd=spent_today_usd, new_total_usd=new_total)
    if new_total > limit_usd:
        return BudgetDecision(allow=False, reason="Total spend would exceed daily limit", limit_usd=limit_usd,
                             spent_usd=spent_today_usd, new_total_usd=new_total)
    return BudgetDecision(allow=True, reason="Request within budget", limit_usd=limit_usd,
                         spent_usd=spent_today_usd, new_total_usd=new_total)


def format_budget_error(decision: BudgetDecision) -> Dict[str, Any]:
    return {
        "error": "budget_exceeded",
        "limit": decision.limit_usd,
        "spent": decision.spent_usd,
        "estimated_cost": decision.new_total_usd - decision.spent_usd,
        "reason": decision.reason,
    }
