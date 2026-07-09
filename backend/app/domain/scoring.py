from __future__ import annotations

from ..policies import get_policy
from ..schemas import PurchasePlanAnalysis, RulePackData


PURCHASE_HAPPINESS_FINANCIAL_KEYS = {
    "transaction_liquidity",
    "post_purchase_liquidity",
    "monthly_cashflow",
    "debt_to_income",
    "monthly_payment_pressure",
    "loan_interest_pressure",
    "cash_shortfall",
    "investment_continuity",
    "stress_resilience",
}


def clamp_score(value: float, low: float = 0, high: float = 10) -> float:
    return max(low, min(high, value))


def ratio_score(value: float, target: float) -> float:
    if target <= 0:
        return 10
    return clamp_score(value / target * 10)


def cash_flow_score(monthly_cash_flow: float, monthly_expense: float) -> float:
    if monthly_expense <= 0:
        return 10 if monthly_cash_flow >= 0 else 0
    return clamp_score(5 + monthly_cash_flow / monthly_expense * 5)


def monthly_happiness_score(
    plan: PurchasePlanAnalysis,
    *,
    month: int,
    purchase_month: int | None,
    cash_balance: float,
    monthly_cash_delta: float,
    monthly_expense: float,
    cash_income: float,
    total_loan_balance: float,
    vehicle_asset_value: float,
    child_expense: float,
) -> float:
    target_score = clamp_score(plan.happiness_score)
    if purchase_month is None or purchase_month >= 999999:
        stage_anchor = max(0.0, target_score - 1.4)
    elif month < purchase_month:
        wait_pressure = clamp_score((purchase_month - month) / 48 * 2.0, 0, 2.0)
        stage_anchor = max(0.0, target_score - wait_pressure - 0.45)
    elif month == purchase_month:
        stage_anchor = max(0.0, target_score - 0.35)
    else:
        stage_anchor = target_score

    liquidity_score = ratio_score(cash_balance, max(1.0, plan.required_liquidity_reserve))
    flow_score = cash_flow_score(monthly_cash_delta, max(1.0, monthly_expense))
    annual_income = max(1.0, cash_income * 12)
    loan_pressure_score = clamp_score(10 - total_loan_balance / annual_income * 1.8)
    vehicle_bonus = 0.25 if vehicle_asset_value > 0 else 0.0
    child_pressure = min(0.45, child_expense / max(1.0, monthly_expense) * 0.35)
    score = (
        stage_anchor * 0.46
        + liquidity_score * 0.20
        + flow_score * 0.18
        + loan_pressure_score * 0.16
        + vehicle_bonus
        - child_pressure
    )
    return round(clamp_score(score), 2)


def dti_score(debt_to_income_ratio: float) -> float:
    if debt_to_income_ratio <= 0.35:
        return 10
    if debt_to_income_ratio >= 0.65:
        return 0
    return clamp_score(10 - (debt_to_income_ratio - 0.35) / 0.30 * 10)


def prepayment_rate_spread_score(loan_effective_rate: float, hurdle_rate: float) -> float:
    spread = loan_effective_rate - hurdle_rate
    if spread <= 0:
        return 0.0
    return clamp_score(spread / 0.03 * 10)


def wait_score(months: int | None, max_comfort_months: int) -> float:
    if months is None:
        return 0
    if months <= 0:
        return 10
    return clamp_score(10 - months / max(max_comfort_months, 1) * 10)


def purchase_happiness_weights(rules: RulePackData, liquidity_priority_score: float) -> dict[str, float]:
    weights = dict(get_policy(rules).purchase_happiness_weights())

    priority = (clamp_score(liquidity_priority_score) - 5.0) / 5.0
    for key in list(weights):
        if key in PURCHASE_HAPPINESS_FINANCIAL_KEYS:
            weights[key] *= 1.0 + priority * 0.28
        elif key in {"living_quality", "commute", "education", "vehicle_convenience"}:
            weights[key] *= 1.0 - priority * 0.12

    total = sum(weights.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in weights.items()}


def renovation_readiness_score(
    renovation_cost: float,
    renovation_included_upfront: bool,
    renovation_saving_months: int | None,
) -> float:
    if renovation_cost <= 0:
        return 10
    if renovation_included_upfront:
        return 8.5
    if renovation_saving_months is None:
        return 2.0
    return wait_score(renovation_saving_months, 36)


def stress_resilience_score(cash_stress_ok: bool, cash_stress_shortfall: float, required_liquidity_reserve: float) -> float:
    if cash_stress_ok:
        return 10
    if required_liquidity_reserve <= 0:
        return 0
    return clamp_score(10 - max(0.0, cash_stress_shortfall) / required_liquidity_reserve * 10)


def weighted_happiness_breakdown(items: list[dict[str, float | str]], weights: dict[str, float]) -> tuple[float, list[dict[str, float | str]]]:
    enriched: list[dict[str, float | str]] = []
    total_score = 0.0
    for item in items:
        key = str(item["key"])
        score = clamp_score(float(item["score"]))
        weight = weights.get(key, 0.0)
        weighted_score = score * weight
        total_score += weighted_score
        enriched.append(
            {
                **item,
                "score": round(score, 2),
                "weight": round(weight, 4),
                "weighted_score": round(weighted_score, 3),
            }
        )
    return total_score, enriched
