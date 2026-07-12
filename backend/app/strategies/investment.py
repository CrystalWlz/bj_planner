from __future__ import annotations

from ..domain.investments import investment_tax_estimate, risk_adjusted_investment_return
from ..schemas import (
    CarLoanSummary,
    HouseholdData,
    InvestmentPlanRecommendation,
    ScenarioData,
)


INVESTMENT_RISK_LABELS = {
    "cash": "现金保守",
    "conservative": "稳健",
    "balanced": "均衡",
    "growth": "进取",
}


def _money_text(amount: float) -> str:
    if abs(amount) >= 10000:
        return f"{amount / 10000:.1f} 万"
    return f"{amount:.0f} 元"


def build_investment_plan_recommendations(
    household: HouseholdData,
    scenario: ScenarioData,
    *,
    net_monthly_income: float,
    current_monthly_expense: float,
    effective_monthly_debt_payment: float,
    car_loan: CarLoanSummary,
    home_purchase_month: int | None = None,
    home_required_cash: float = 0.0,
    home_required_reserve: float = 0.0,
    vehicle_purchase_month: int | None = None,
    lifecycle_cash_shortfall: float = 0.0,
    lifecycle_insolvency_month: int | None = None,
    lifecycle_liquid_assets_exhausted_month: int | None = None,
    maximum_monthly_investment: float | None = None,
) -> list[InvestmentPlanRecommendation]:
    car_cost = (
        car_loan.current_monthly_payment + car_loan.monthly_cash_operating_cost
        if household.car_plan.enabled and car_loan.enabled and car_loan.purchase_delay_months <= 0
        else max(0.0, household.car_plan.no_car_monthly_commute_cost)
    )
    monthly_surplus = max(0.0, net_monthly_income - current_monthly_expense - effective_monthly_debt_payment - car_cost)
    current_cash = max(0.0, household.cash_account_balance)
    total_liquid_account_assets = max(1.0, household.cash_account_balance + household.investments)
    current_investment_ratio = max(0.0, household.investments) / total_liquid_account_assets
    configured_reserve_months = max(
        1.0,
        household.investment_cash_reserve_months or household.required_liquidity_months or 6,
    )
    reserve_target = current_monthly_expense * configured_reserve_months
    reserve_gap = max(0.0, reserve_target - current_cash)
    cash_sweep = max(0.0, current_cash - reserve_target) / 12
    base_investable = (
        max(0.0, monthly_surplus * 0.25)
        if reserve_gap > 0
        else max(0.0, monthly_surplus * 0.55 + cash_sweep)
    )
    scenario_return = scenario.annual_investment_return if scenario.annual_investment_return is not None else 0.025
    tax_estimate = investment_tax_estimate(household)
    after_tax_return = max(0.0, scenario_return) * (1 - tax_estimate.effective_rate)
    risk_adjusted_return = risk_adjusted_investment_return(household, scenario_return)
    net_liquid_assets = current_cash + max(0.0, household.investments) * (1 - max(0.0, household.investment_sell_fee_rate))
    vehicle_goal_cash = (
        max(0.0, car_loan.down_payment)
        if vehicle_purchase_month is not None and vehicle_purchase_month > 0
        else 0.0
    )
    goal_deadlines = sorted(
        (month, amount)
        for month, amount in (
            (home_purchase_month, max(0.0, home_required_cash) + max(0.0, home_required_reserve)),
            (vehicle_purchase_month, vehicle_goal_cash),
        )
        if month is not None and month >= 0 and amount > 0
    )
    urgent_goal_deadlines = [(month, amount) for month, amount in goal_deadlines if month <= 24]
    liquidity_horizon_months = min((month for month, _ in goal_deadlines), default=None)
    goal_liquidity_target = 0.0
    goal_liquidity_gap = 0.0
    monthly_goal_saving = 0.0
    cumulative_target = 0.0
    for deadline_month, amount in urgent_goal_deadlines:
        cumulative_target += amount
        deadline_gap = max(0.0, cumulative_target - net_liquid_assets)
        required_monthly_saving = deadline_gap / max(1, deadline_month)
        if required_monthly_saving > monthly_goal_saving:
            monthly_goal_saving = required_monthly_saving
            liquidity_horizon_months = deadline_month
            goal_liquidity_target = cumulative_target
            goal_liquidity_gap = deadline_gap
        elif goal_liquidity_target <= 0:
            goal_liquidity_target = cumulative_target
            goal_liquidity_gap = deadline_gap
    short_goal_horizon = (
        liquidity_horizon_months is not None
        and liquidity_horizon_months <= 12
        and goal_liquidity_gap > 0
    )
    medium_goal_horizon = (
        liquidity_horizon_months is not None
        and 12 < liquidity_horizon_months <= 24
        and goal_liquidity_gap > 0
    )
    goal_investable_surplus = max(0.0, monthly_surplus - monthly_goal_saving)
    if maximum_monthly_investment is not None:
        goal_investable_surplus = min(goal_investable_surplus, max(0.0, maximum_monthly_investment))
    lifecycle_at_risk = (
        lifecycle_cash_shortfall > 0
        or lifecycle_insolvency_month is not None
        or lifecycle_liquid_assets_exhausted_month is not None
    )
    relief_horizon = max(12, lifecycle_insolvency_month or lifecycle_liquid_assets_exhausted_month or 120)
    lifecycle_required_monthly_relief = (
        lifecycle_cash_shortfall * 1.10 / relief_horizon
        if lifecycle_at_risk
        else 0.0
    )

    common = {
        "after_tax_annual_return": round(after_tax_return, 6),
        "risk_adjusted_annual_return": round(risk_adjusted_return, 6),
        "liquidity_horizon_months": liquidity_horizon_months,
        "goal_liquidity_target": round(goal_liquidity_target, 2),
        "goal_liquidity_gap": round(goal_liquidity_gap, 2),
        "monthly_goal_saving": round(monthly_goal_saving, 2),
        "lifecycle_cash_shortfall": round(max(0.0, lifecycle_cash_shortfall), 2),
        "lifecycle_insolvency_month": lifecycle_insolvency_month,
        "lifecycle_liquid_assets_exhausted_month": lifecycle_liquid_assets_exhausted_month,
        "lifecycle_required_monthly_relief": round(lifecycle_required_monthly_relief, 2),
    }

    candidates = []
    if lifecycle_at_risk:
        candidates.append(
            {
                **common,
                "variant": "长期现金流修复",
                "plan_name": "lifecycle_cashflow_recovery",
                "risk_level": "cash",
                "description": "完整生命周期账本出现现金缺口时，暂停新增风险投资并优先积累可自由动用现金；待缺口消除后再恢复定投。",
                "monthly_investment": 0.0,
                "annual_return": max(0.005, scenario_return * 0.20),
                "cash_reserve_months": max(configured_reserve_months, 12),
                "equity_ratio": 0.0,
                "bond_ratio": 0.15,
                "cash_ratio": 0.85,
                "lifecycle_feasible": False,
                "lifecycle_risk_note": (
                    f"当前组合长期现金缺口约 {_money_text(lifecycle_cash_shortfall)}，"
                    f"至少需要形成约 {_money_text(lifecycle_required_monthly_relief)} 的月度改善，并同步调整重大目标。"
                ),
                "reasons": [
                    "完整账本已出现流动资产耗尽或现金穿底，先修复现金流而不是追求账面收益率",
                    f"建议至少形成每月 {_money_text(lifecycle_required_monthly_relief)} 的持续改善",
                    "理财暂停只能减少现金波动，仍需与延后购房购车、降低预算或暂停自愿缴费组合执行",
                ],
            }
        )
    candidates.extend([
        {
            **common,
            "variant": "重大目标资金优先",
            "plan_name": "goal_liquidity_first",
            "risk_level": "cash" if short_goal_horizon else "conservative",
            "description": "重大目标进入两年内时，优先把交易资金和应急金放在低波动、可随时动用的资金桶中，避免刚买入又被迫卖出。",
            "monthly_investment": round(
                max(0.0, min(goal_investable_surplus, goal_investable_surplus * (0.0 if short_goal_horizon else 0.25))) / 100
            ) * 100,
            "annual_return": max(0.01, scenario_return * (0.30 if short_goal_horizon else 0.55)),
            "cash_reserve_months": max(configured_reserve_months, 9 if short_goal_horizon else 7),
            "equity_ratio": 0.05 if short_goal_horizon else 0.15,
            "bond_ratio": 0.20 if short_goal_horizon else 0.40,
            "cash_ratio": 0.75 if short_goal_horizon else 0.45,
            "reasons": [
                "重大目标资金和应急金优先，不把风险资产当作现金安全垫",
                (
                    f"最近重大目标约 {liquidity_horizon_months} 个月后"
                    if liquidity_horizon_months is not None
                    else "当前没有已排期的重大目标"
                ),
                f"目标资金缺口约 {_money_text(goal_liquidity_gap)}，每月先留存约 {_money_text(monthly_goal_saving)}",
                f"税后测算年化约 {after_tax_return:.1%}，风险调整后约 {risk_adjusted_return:.1%}",
            ],
            "lifecycle_feasible": not lifecycle_at_risk,
            "lifecycle_risk_note": "" if not lifecycle_at_risk else "当前整体规划存在长期现金缺口，本方案须在重大目标调整后重新评估。",
        },
        {
            **common,
            "variant": "先补现金安全垫",
            "plan_name": "cash_reserve_first",
            "risk_level": "conservative",
            "description": "现金账户低于安全垫时压低定投，先把家庭风险缓冲补齐。",
            "monthly_investment": round(max(0.0, min(goal_investable_surplus, goal_investable_surplus * 0.2 if reserve_gap > 0 else base_investable)) / 100) * 100,
            "annual_return": max(0.015, scenario_return * 0.75),
            "cash_reserve_months": max(configured_reserve_months, 6),
            "equity_ratio": 0.20,
            "bond_ratio": 0.50,
            "cash_ratio": 0.30,
            "reasons": [
                "优先保护现金账户",
                f"目标现金安全垫 {_money_text(reserve_target)}",
                f"当前投资占流动资产 {current_investment_ratio:.1%}",
            ],
            "lifecycle_feasible": not lifecycle_at_risk,
            "lifecycle_risk_note": "" if not lifecycle_at_risk else "当前整体规划存在长期现金缺口，补安全垫仍不足以单独恢复可行性。",
        },
        {
            **common,
            "variant": "稳健定投",
            "plan_name": "balanced_monthly_investment",
            "risk_level": "balanced",
            "description": "现金安全垫达标后维持中等定投，兼顾买房买车前的流动性。",
            "monthly_investment": round(max(0.0, min(goal_investable_surplus, base_investable)) / 100) * 100,
            "annual_return": max(0.02, scenario_return),
            "cash_reserve_months": configured_reserve_months,
            "equity_ratio": 0.35,
            "bond_ratio": 0.45,
            "cash_ratio": 0.20,
            "reasons": [
                "按月结余动态定投",
                "现金超额会分 12 个月滚入投资",
                f"预期年化 {max(0.02, scenario_return):.1%}",
            ],
            "lifecycle_feasible": not lifecycle_at_risk,
            "lifecycle_risk_note": "" if not lifecycle_at_risk else "当前整体规划存在长期现金缺口，不应继续按常规定投强度执行。",
        },
        {
            **common,
            "variant": "提高长期收益",
            "plan_name": "growth_monthly_investment",
            "risk_level": "growth",
            "description": "在现金垫充足时提高权益比例，适合目标事件还比较远的月份。",
            "monthly_investment": round(max(0.0, min(goal_investable_surplus, base_investable * 1.25)) / 100) * 100,
            "annual_return": max(0.025, scenario_return * 1.15),
            "cash_reserve_months": max(3.0, configured_reserve_months - 1),
            "equity_ratio": 0.50,
            "bond_ratio": 0.35,
            "cash_ratio": 0.15,
            "reasons": [
                "现金垫达标后提高权益仓位",
                f"保留至少 {max(3.0, configured_reserve_months - 1):.0f} 个月支出",
                "收益继续留在投资账户复利",
            ],
            "lifecycle_feasible": not lifecycle_at_risk,
            "lifecycle_risk_note": "" if not lifecycle_at_risk else "完整账本存在长期现金缺口，进取仓位不进入当前推荐。",
        },
    ])
    recommendations: list[InvestmentPlanRecommendation] = []
    for item in candidates:
        score = round(
            max(
                0,
                min(
                    100,
                    68
                    + (24 if (short_goal_horizon or medium_goal_horizon) and item["plan_name"] == "goal_liquidity_first" else 0)
                    - (28 if short_goal_horizon and item["plan_name"] == "growth_monthly_investment" else 0)
                    - (14 if medium_goal_horizon and item["plan_name"] == "growth_monthly_investment" else 0)
                    + (16 if reserve_gap > 0 and item["plan_name"] == "cash_reserve_first" else 0)
                    + (10 if reserve_gap <= 0 and not (short_goal_horizon or medium_goal_horizon) and item["plan_name"] != "cash_reserve_first" else 0)
                    + (8 if monthly_surplus > 0 else -16)
                    + (26 if lifecycle_at_risk and item["plan_name"] == "lifecycle_cashflow_recovery" else 0)
                    - (45 if lifecycle_at_risk and item["plan_name"] == "growth_monthly_investment" else 0)
                    - (24 if lifecycle_at_risk and item["plan_name"] not in {"lifecycle_cashflow_recovery", "cash_reserve_first"} else 0)
                    - abs(float(item["cash_reserve_months"]) - configured_reserve_months) * 1.5,
                ),
            )
        )
        recommendations.append(
            InvestmentPlanRecommendation(
                **item,
                risk_label=INVESTMENT_RISK_LABELS.get(str(item["risk_level"]), "自定义"),
                score=score,
            )
        )
    return sorted(recommendations, key=lambda item: item.score, reverse=True)
