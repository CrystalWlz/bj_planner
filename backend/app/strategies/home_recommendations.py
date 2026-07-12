from __future__ import annotations

from ..projection.ledger_models import ProjectionRiskSummary
from ..domain.goal_tradeoffs import resolve_goal_tradeoff_preference
from ..schemas import HouseholdData, PurchasePlanAnalysis, ScenarioData, StressResult


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


def enrich_purchase_plans_with_projection_risk(
    plans: list[PurchasePlanAnalysis],
    risk_by_plan: dict[str, ProjectionRiskSummary],
    household: HouseholdData,
) -> list[PurchasePlanAnalysis]:
    enriched: list[PurchasePlanAnalysis] = []
    for plan in plans:
        risk = risk_by_plan.get(plan.variant)
        if risk is None:
            enriched.append(plan)
            continue
        monthly_burn = max(
            1.0,
            household.monthly_expense + household.monthly_debt_payment + plan.total_monthly_payment,
        )
        enriched.append(
            plan.model_copy(
                update={
                    "cash_shortfall": risk.cash_shortfall,
                    "insolvency_month": risk.insolvency_month,
                    "liquid_assets_exhausted_month": risk.liquid_assets_exhausted_month,
                    "worst_cash_balance": risk.worst_cash_balance,
                    "terminal_net_worth": risk.terminal_net_worth,
                    "emergency_reserve_coverage_months": round(
                        max(0.0, plan.cash_after_transaction) / monthly_burn,
                        2,
                    ),
                }
            )
        )
    return enriched


def _is_feasible(plan: PurchasePlanAnalysis) -> bool:
    return (
        plan.source != "baseline"
        and plan.months_to_buy is not None
        and plan.liquidity_ok
        and plan.cash_stress_ok
        and plan.cash_shortfall <= 0
        and plan.insolvency_month is None
        and plan.liquid_assets_exhausted_month is None
        and plan.terminal_net_worth == plan.terminal_net_worth
        and plan.worst_cash_balance == plan.worst_cash_balance
    )


def _pareto_efficient(plans: list[PurchasePlanAnalysis]) -> set[str]:
    efficient: set[str] = set()
    for plan in plans:
        values = (
            plan.terminal_net_worth,
            plan.worst_cash_balance,
            plan.emergency_reserve_coverage_months,
            plan.happiness_score,
            -(plan.months_to_buy or 0),
        )
        dominated = False
        for other in plans:
            if other is plan:
                continue
            other_values = (
                other.terminal_net_worth,
                other.worst_cash_balance,
                other.emergency_reserve_coverage_months,
                other.happiness_score,
                -(other.months_to_buy or 0),
            )
            if all(a >= b for a, b in zip(other_values, values)) and any(
                a > b for a, b in zip(other_values, values)
            ):
                dominated = True
                break
        if not dominated:
            efficient.add(plan.variant)
    return efficient


def with_purchase_plan_recommendations(
    plans: list[PurchasePlanAnalysis],
    scenario: ScenarioData,
    household: HouseholdData,
) -> list[PurchasePlanAnalysis]:
    if not plans:
        return plans
    feasible_plans = [plan for plan in plans if _is_feasible(plan)]
    if not feasible_plans:
        message = "无可行购房方案：建议延后买入、降低房源总价，或继续采用不买房基线。"
        return [
            plan.model_copy(
                update={
                    "recommendation_score": 0,
                    "recommendation_reasons": [message],
                    "is_recommended": False,
                    "pareto_efficient": False,
                    "feasibility_recommendation": message,
                }
            )
            for plan in plans
        ]
    pareto_variants = _pareto_efficient(feasible_plans)
    finite_months = [plan.months_to_buy for plan in feasible_plans if plan.months_to_buy is not None]
    max_months = max(max(finite_months or [1]), 1)
    max_payment = max([plan.total_monthly_payment for plan in feasible_plans] or [1], default=1)
    max_cash_after_transaction = max([max(plan.cash_after_transaction, 0.0) for plan in feasible_plans] or [1], default=1)
    max_terminal_net_worth = max([plan.terminal_net_worth for plan in feasible_plans] or [1], default=1)
    max_payment = max(max_payment, 1.0)
    max_cash_after_transaction = max(max_cash_after_transaction, 1.0)
    liquidity_weight = _clamp(float(scenario.liquidity_priority_score or 7), 0, 10) / 10
    earliest_feasible_month = min(finite_months or [0])
    best_terminal_net_worth = max(plan.terminal_net_worth for plan in feasible_plans)
    tradeoff = resolve_goal_tradeoff_preference(
        household,
        expected_investment_return=scenario.annual_investment_return,
        urgency_months=earliest_feasible_month,
        priority=scenario.purchase_sequence,
        life_utility_score=sum(plan.happiness_score for plan in feasible_plans) / max(1, len(feasible_plans)),
        cash_reserve_gap=max(0.0, household.monthly_expense * household.required_liquidity_months - household.cash_account_balance),
    )

    scored: list[tuple[PurchasePlanAnalysis, float, list[str]]] = []
    for plan in feasible_plans:
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
        terminal_value_score = _clamp((plan.terminal_net_worth / max(max_terminal_net_worth, 1.0)) * 100, 0, 100)
        safety_score = (
            cash_score * (0.18 + liquidity_weight * 0.08)
            + flow_score * 0.22
            + debt_score * 0.18
            + liquidity_score * 0.16
            + payment_score * 0.10
            + happiness_score * (0.16 - liquidity_weight * 0.08)
        )
        tradeoff_score = speed_score * tradeoff.timing_weight + terminal_value_score * tradeoff.wealth_weight
        score = safety_score * 0.70 + tradeoff_score * 0.30
        opportunity_cost = max(0.0, best_terminal_net_worth - plan.terminal_net_worth)
        timing_delay = max(0, (plan.months_to_buy or earliest_feasible_month) - earliest_feasible_month)
        reasons = purchase_plan_recommendation_reason(plan) + [
            tradeoff.explanation,
            f"相对最早可行方案延后 {timing_delay} 个月；相对最高财富终值少约 {_money_text(opportunity_cost)}。",
        ]
        scored.append((plan, _clamp(score, 0, 100), reasons))

    best_variant = max(
        (item for item in scored if item[0].variant in pareto_variants),
        key=lambda item: item[1],
    )[0].variant
    scores_by_variant = {plan.variant: (score, reasons) for plan, score, reasons in scored}
    recommended: list[PurchasePlanAnalysis] = []
    for plan in plans:
        feasible = _is_feasible(plan)
        score, reasons = scores_by_variant.get(
            plan.variant,
            (0, ["该方案未通过现金安全和长期偿付能力门槛，不参与推荐。"]),
        )
        recommended.append(
            plan.model_copy(
                update={
                    "recommendation_score": int(round(score)),
                    "recommendation_reasons": reasons,
                    "is_recommended": feasible and plan.variant == best_variant,
                    "pareto_efficient": feasible and plan.variant in pareto_variants,
                    "feasibility_recommendation": ""
                    if feasible
                    else "先延后、降低总价或继续租住；该方案不进入推荐比较。",
                }
            )
        )
    return recommended


def with_stress_test_recommendation_gate(
    plans: list[PurchasePlanAnalysis],
    stress_tests: list[StressResult],
) -> list[PurchasePlanAnalysis]:
    """Keep an otherwise feasible nominal plan out of recommendations if stress fails."""
    failed = [item for item in stress_tests if not item.feasible]
    if not failed:
        return plans
    failed_names = "、".join(item.name for item in failed)
    message = f"压力测试未通过（{failed_names}）：建议延后买入、降低总价或继续租住，不推荐立即执行。"
    return [
        plan.model_copy(
            update={
                "is_recommended": False,
                "recommendation_score": 0,
                "recommendation_reasons": [message],
                "feasibility_recommendation": message,
            }
        )
        for plan in plans
    ]


