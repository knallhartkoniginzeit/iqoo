import pytest
from app.budget import (
    check_budget,
    get_budget_for_key,
    format_budget_error,
    BudgetDecision,
)


class TestBudgetChecking:
    def test_within_budget_allows(self):
        decision = check_budget(
            estimated_cost_usd=1.00,
            spent_today_usd=5.00,
            limit_usd=20.00,
        )
        assert decision.allow is True
        assert "within budget" in decision.reason.lower()
        assert decision.limit_usd == 20.00
        assert decision.spent_usd == 5.00
        assert decision.new_total_usd == 6.00

    def test_at_budget_limit_allows(self):
        decision = check_budget(
            estimated_cost_usd=5.00,
            spent_today_usd=15.00,
            limit_usd=20.00,
        )
        assert decision.allow is True
        assert decision.new_total_usd == 20.00

    def test_over_budget_blocks(self):
        decision = check_budget(
            estimated_cost_usd=10.00,
            spent_today_usd=15.00,
            limit_usd=20.00,
        )
        assert decision.allow is False
        assert "exceeds" in decision.reason.lower() or "would exceed" in decision.reason.lower()
        assert decision.limit_usd == 20.00
        assert decision.spent_usd == 15.00
        assert decision.new_total_usd == 25.00

    def test_single_request_over_limit_blocks(self):
        decision = check_budget(
            estimated_cost_usd=50.00,
            spent_today_usd=0.00,
            limit_usd=20.00,
        )
        assert decision.allow is False
        assert "exceeds daily limit" in decision.reason.lower()

    def test_zero_budget_blocks(self):
        decision = check_budget(
            estimated_cost_usd=0.01,
            spent_today_usd=0.00,
            limit_usd=0.00,
        )
        assert decision.allow is False

    def test_exact_zero_cost_allowed(self):
        decision = check_budget(
            estimated_cost_usd=0.00,
            spent_today_usd=0.00,
            limit_usd=20.00,
        )
        assert decision.allow is True


class TestBudgetForKey:
    def test_returns_default_when_no_match(self):
        budget = get_budget_for_key("nonexistentkeyhash123456789")
        assert "daily_limit_usd" in budget
        assert "hard_block" in budget
        assert budget["daily_limit_usd"] == 5.0

    def test_budget_format(self):
        budget = get_budget_for_key("somekey")
        assert isinstance(budget, dict)
        assert "daily_limit_usd" in budget
        assert isinstance(budget["daily_limit_usd"], (int, float))


class TestFormatBudgetError:
    def test_format_error_response(self):
        decision = BudgetDecision(
            allow=False,
            reason="Budget exceeded",
            limit_usd=20.00,
            spent_usd=19.50,
            new_total_usd=20.00,
        )
        error = format_budget_error(decision)
        assert error["error"] == "budget_exceeded"
        assert error["limit"] == 20.00
        assert error["spent"] == 19.50
        assert "estimated_cost" in error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
