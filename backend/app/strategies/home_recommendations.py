from __future__ import annotations

from ..schemas import PurchasePlanAnalysis, ScenarioData


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _money_text(amount: float) -> str:
    value = round(float(amount), 2)
    if abs(value) >= 10000:
        text = f"{value / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text} 万"
    return f"{value:.0f} 元"


def purchase_plan_recommendation_reason(plan: PurchasePlanAnalysis) -> list[str]:
    effective_cash_flow = plan.post_purchase_cash_flow_with_pf_withdrawal
    return [
        (
            "当前现金路径暂未达成买入条件"
            if plan.months_to_buy is None
            else f"{plan.years_to_buy} 年左右可执行买入"
        ),
        (
            f"买后仍覆盖 {_money_text(plan.required_liquidity_reserve)} 安全垫"
            if plan.liquidity_ok
            else "买后安全垫偏紧，需要提高现金留存"
        ),
        (
            f"策略后现金压力每月结余 {_money_text(effective_cash_flow)}"
            if effective_cash_flow >= 0
            else f"策略后现金压力每月缺口 {_money_text(abs(effective_cash_flow))}"
        ),
        (
            f"{plan.post_purchase_pf_strategy_label}，月均减少现金压力 {_money_text(plan.monthly_post_purchase_pf_withdrawal)}"
            if plan.monthly_post_purchase_pf_withdrawal > 0
            else "公积金继续留存在账户，不进入自由现金流"
        ),
        (
            "不使用商贷，利息压力最低"
            if plan.commercial_loan_amount == 0
            else f"商贷控制在 {_money_text(plan.commercial_loan_amount)}"
        ),
    ]


def with_purchase_plan_recommendations(
    plans: list[PurchasePlanAnalysis],
    scenario: ScenarioData,
) -> list[PurchasePlanAnalysis]:
    if not plans:
        return plans
    finite_months = [plan.months_to_buy for plan in plans if plan.months_to_buy is not None]
    max_months = max(max(finite_months or [1]), 1)
    max_payment = max([plan.total_monthly_payment for plan in plans] or [1], default=1)
    max_cash_after_transaction = max([max(plan.cash_after_transaction, 0.0) for plan in plans] or [1], default=1)
    max_payment = max(max_payment, 1.0)
    max_cash_after_transaction = max(max_cash_after_transaction, 1.0)
    liquidity_weight = _clamp(float(scenario.liquidity_priority_score or 7), 0, 10) / 10

    scored: list[tuple[PurchasePlanAnalysis, int, list[str]]] = []
    for plan in plans:
        speed_score = (
            0.0
            if plan.months_to_buy is None
            else max(0.0, 100 - (plan.months_to_buy / max_months) * 36)
        )
        cash_score = _clamp((max(plan.cash_after_transaction, 0.0) / max_cash_after_transaction) * 100, 0, 100)
        effective_cash_flow = plan.post_purchase_cash_flow_with_pf_withdrawal
        flow_score = 100.0 if effective_cash_flow >= 0 else max(0.0, 100 + effective_cash_flow / 1000)
        debt_score = max(0.0, 100 - plan.debt_to_income_ratio * 150)
        liquidity_score = 100.0 if plan.liquidity_ok else 45.0
        payment_score = max(0.0, 100 - (plan.total_monthly_payment / max_payment) * 42)
        happiness_score = _clamp(plan.happiness_score * 10, 0, 100)
        score = (
            speed_score * (0.2 + (1 - liquidity_weight) * 0.12)
            + cash_score * (0.16 + liquidity_weight * 0.14)
            + flow_score * 0.18
            + debt_score * 0.16
            + liquidity_score * 0.12
            + payment_score * 0.1
            + happiness_score * 0.08
        )
        scored.append((plan, int(round(_clamp(score, 0, 100))), purchase_plan_recommendation_reason(plan)))

    best_variant = max(scored, key=lambda item: item[1])[0].variant
    return [
        plan.model_copy(
            update={
                "recommendation_score": score,
                "recommendation_reasons": reasons,
                "is_recommended": plan.variant == best_variant,
            }
        )
        for plan, score, reasons in scored
    ]


