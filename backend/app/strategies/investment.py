from __future__ import annotations

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

    candidates = [
        {
            "variant": "先补现金安全垫",
            "plan_name": "cash_reserve_first",
            "risk_level": "conservative",
            "description": "现金账户低于安全垫时压低定投，先把家庭风险缓冲补齐。",
            "monthly_investment": round(max(0.0, min(monthly_surplus, monthly_surplus * 0.2 if reserve_gap > 0 else base_investable)) / 100) * 100,
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
        },
        {
            "variant": "稳健定投",
            "plan_name": "balanced_monthly_investment",
            "risk_level": "balanced",
            "description": "现金安全垫达标后维持中等定投，兼顾买房买车前的流动性。",
            "monthly_investment": round(max(0.0, min(monthly_surplus, base_investable)) / 100) * 100,
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
        },
        {
            "variant": "提高长期收益",
            "plan_name": "growth_monthly_investment",
            "risk_level": "growth",
            "description": "在现金垫充足时提高权益比例，适合目标事件还比较远的月份。",
            "monthly_investment": round(max(0.0, min(monthly_surplus, base_investable * 1.25)) / 100) * 100,
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
        },
    ]
    recommendations: list[InvestmentPlanRecommendation] = []
    for item in candidates:
        score = round(
            max(
                0,
                min(
                    100,
                    68
                    + (16 if reserve_gap > 0 and item["plan_name"] == "cash_reserve_first" else 0)
                    + (10 if reserve_gap <= 0 and item["plan_name"] != "cash_reserve_first" else 0)
                    + (8 if monthly_surplus > 0 else -16)
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
