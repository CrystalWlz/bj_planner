from __future__ import annotations

from ..schemas import (
    CarPlanAnalysis,
    ChildPlanStrategyPoint,
    InvestmentPlanRecommendation,
    PortfolioStrategyRecommendation,
    PurchasePlanAnalysis,
    ScenarioData,
    TaxStrategyItem,
)


def _money_text(amount: float) -> str:
    value = max(0.0, float(amount))
    if value >= 10_000:
        return f"{value / 10_000:.1f} 万"
    return f"{value:.0f} 元"


def _portfolio_plan(
    plans: list[PurchasePlanAnalysis],
    scenario: ScenarioData,
) -> PurchasePlanAnalysis | None:
    return next(
        (plan for plan in plans if plan.is_recommended),
        next(
            (plan for plan in plans if plan.variant == scenario.selected_purchase_plan_variant),
            min(
                plans,
                key=lambda plan: (
                    plan.cash_shortfall,
                    plan.insolvency_month is not None,
                    -(plan.terminal_net_worth or 0.0),
                ),
                default=None,
            ),
        ),
    )


def build_portfolio_strategy_recommendations(
    *,
    purchase_plans: list[PurchasePlanAnalysis],
    car_plans: list[CarPlanAnalysis],
    investment_plans: list[InvestmentPlanRecommendation],
    child_plans: list[ChildPlanStrategyPoint],
    tax_strategy_items: list[TaxStrategyItem],
    scenario: ScenarioData,
) -> list[PortfolioStrategyRecommendation]:
    plan = _portfolio_plan(purchase_plans, scenario)
    purchase_unreachable = bool(plan is not None and plan.source != "baseline" and plan.months_to_buy is None)
    cash_shortfall = max(
        0.0,
        plan.cash_shortfall if plan else 0.0,
        plan.cash_stress_shortfall if plan else 0.0,
    )
    insolvency_month = plan.insolvency_month if plan else None
    exhausted_month = plan.liquid_assets_exhausted_month if plan else None
    at_risk = (
        purchase_unreachable
        or cash_shortfall > 0
        or insolvency_month is not None
        or exhausted_month is not None
    )
    relief_horizon = max(12, insolvency_month or exhausted_month or 120)
    required_monthly_relief = cash_shortfall * 1.10 / relief_horizon if at_risk else 0.0

    current_reasons = [
        "以完整月度账本而不是单项策略分数判断组合是否可执行。",
        (
            (
                "当前购房目标在规划窗口和长期现金约束下没有可执行月份。"
                if purchase_unreachable and insolvency_month is None
                else f"当前组合长期现金缺口约 {_money_text(cash_shortfall)}，首次穿底约在第 {insolvency_month} 个月。"
            )
            if at_risk
            else "当前组合未出现现金穿底或流动资产耗尽。"
        ),
    ]
    current = PortfolioStrategyRecommendation(
        plan_name="current_combination",
        title="当前采用组合",
        status="high_risk" if at_risk else "feasible",
        description="汇总当前选中的购房、购车、理财、养娃和税务/个人养老金设置。",
        actions=[],
        cash_shortfall=round(cash_shortfall, 2),
        insolvency_month=insolvency_month,
        liquid_assets_exhausted_month=exhausted_month,
        terminal_net_worth=round(plan.terminal_net_worth if plan else 0.0, 2),
        required_monthly_relief=round(required_monthly_relief, 2),
        feasible=not at_risk,
        score=92 if not at_risk else 5,
        is_recommended=not at_risk,
        reasons=current_reasons,
    )
    if not at_risk:
        return [current]

    actions: list[str] = []
    if plan is not None and plan.source != "baseline":
        actions.append("购房：继续搜索更晚买入月份、较低总价和更低长期月供，直至完整账本不再穿底。")
    feasible_delayed_vehicle = next(
        (
            item
            for item in car_plans
            if item.strategy_key == "delay_purchase" and item.lifecycle_feasible
        ),
        None,
    )
    if feasible_delayed_vehicle is not None:
        actions.append(f"购车：采用延后约 {feasible_delayed_vehicle.purchase_delay_months} 个月的长期可行候选。")
    elif car_plans:
        actions.append("购车：当前车价和持有成本下没有长期可行候选，应降低预算或暂不购车。")
    recovery_investment = next(
        (item for item in investment_plans if item.plan_name == "lifecycle_cashflow_recovery"),
        None,
    )
    if recovery_investment is not None:
        actions.append("理财：暂停新增风险投资，先恢复现金安全垫；保留已有资产时也不得把波动资产当应急金。")
    if any(not item.lifecycle_feasible for item in child_plans if item.enabled):
        actions.append("养娃：先用保守预算重算；是否延后需同时考虑生育年龄，不能只按财务缺口机械后移。")
    if any(item.deduction_type == "personal_pension" for item in tax_strategy_items):
        actions.append("个人养老金：穿底早于可领取月份时暂停新增自愿缴费，不能用锁定账户掩盖自由现金不足。")
    actions.append(f"组合底线：至少形成约 {_money_text(required_monthly_relief)} 的持续月度改善，并重新跑完整生命周期账本。")

    recovery = PortfolioStrategyRecommendation(
        plan_name="lifecycle_cashflow_recovery",
        title="生命周期现金流修复组合",
        status="adjustment_required",
        description="按可调整性先处理房车时点与预算，再处理自愿投资和个人养老金缴费；基本生活和必要养育支出不作为第一削减项。",
        actions=actions,
        cash_shortfall=round(cash_shortfall, 2),
        insolvency_month=insolvency_month,
        liquid_assets_exhausted_month=exhausted_month,
        terminal_net_worth=round(plan.terminal_net_worth if plan else 0.0, 2),
        required_monthly_relief=round(required_monthly_relief, 2),
        feasible=False,
        score=95,
        is_recommended=True,
        reasons=[
            "该方案是主动调整搜索的起点，不把原有高风险组合包装成可行方案。",
            "只有调整后重新推演且现金缺口、穿底月份和流动资产耗尽均消失，才可转为执行方案。",
            "排序同时考虑长期净资产、自由现金安全和重大目标效用，而不是只追求最早买入或最高收益率。",
        ],
    )
    return [recovery, current]
