from __future__ import annotations

from dataclasses import dataclass

from ..schemas import HouseholdData


@dataclass(frozen=True)
class GoalTradeoffPreference:
    timing_weight: float
    wealth_weight: float
    mode: str
    explanation: str


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def resolve_goal_tradeoff_preference(
    household: HouseholdData,
    *,
    expected_investment_return: float,
    urgency_months: int | None,
    priority: int = 1,
    life_utility_score: float = 7.0,
    cash_reserve_gap: float = 0.0,
) -> GoalTradeoffPreference:
    if household.major_goal_tradeoff_mode == "manual":
        timing_weight = _clamp(household.major_goal_timing_preference, 0.05, 0.95)
        return GoalTradeoffPreference(
            timing_weight=timing_weight,
            wealth_weight=1 - timing_weight,
            mode="manual",
            explanation=(
                f"使用手动取舍：时间效用 {timing_weight:.0%}，财富终值 {1 - timing_weight:.0%}。"
            ),
        )

    timing_weight = 0.48
    if urgency_months is not None:
        if urgency_months <= 12:
            timing_weight += 0.16
        elif urgency_months <= 24:
            timing_weight += 0.10
        elif urgency_months >= 60:
            timing_weight -= 0.08
    timing_weight += _clamp((6.5 - max(0.0, life_utility_score)) * -0.025, -0.08, 0.08)
    timing_weight += 0.06 if priority <= 1 else 0.03 if priority <= 3 else -0.02
    timing_weight -= _clamp((max(0.0, expected_investment_return) - 0.025) * 2.5, 0.0, 0.14)
    if cash_reserve_gap > 0:
        timing_weight -= 0.12
    timing_weight = _clamp(timing_weight, 0.20, 0.80)
    wealth_weight = 1 - timing_weight
    return GoalTradeoffPreference(
        timing_weight=timing_weight,
        wealth_weight=wealth_weight,
        mode="auto",
        explanation=(
            f"自动取舍根据目标紧迫度、优先级、生活效用、理财预期收益和现金安全，"
            f"得到时间效用 {timing_weight:.0%}、财富终值 {wealth_weight:.0%}。"
        ),
    )


__all__ = ["GoalTradeoffPreference", "resolve_goal_tradeoff_preference"]
