from __future__ import annotations

from ..schemas import MonthlyCashflowPoint, PlanEventPoint, PurchasePlanAnalysis, ScenarioData


def _money_text(amount: float) -> str:
    value = round(float(amount), 2)
    if abs(value) >= 10000:
        text = f"{value / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text} 万"
    return f"{value:.0f} 元"


def _pf_strategy_switch_month(mode: str) -> int:
    if mode.startswith("monthly_then_semiannual_offset_after_"):
        try:
            return int(mode.rsplit("_", 1)[-1])
        except ValueError:
            return 12
    return 12


def _repayment_method_label(method: str) -> str:
    return "等额本金" if method == "equal_principal" else "等额本息"


def purchase_plan_events(
    plan: PurchasePlanAnalysis,
    scenario: ScenarioData,
    *,
    purchase_point: MonthlyCashflowPoint | None = None,
) -> list[PlanEventPoint]:
    if plan.months_to_buy is None:
        return [
            PlanEventPoint(
                plan_variant=plan.variant,
                month=360,
                category="risk",
                title="购房策略暂不可执行",
                detail=(
                    f"后端没有在 30 年内找到现金账户不穿底的执行点；压力短缺约 {_money_text(plan.cash_stress_shortfall)}。"
                ),
                amount=round(plan.cash_stress_shortfall, 2),
                severity="danger",
            )
        ]

    purchase_month = plan.months_to_buy
    events = [
        PlanEventPoint(
            plan_variant=plan.variant,
            month=purchase_month,
            category="home_purchase",
            title="购房交易",
            detail=(
                f"交易现金需覆盖 {_money_text(plan.required_cash_after_pf_extract)}，交易当下现金约 {_money_text(plan.cash_after_transaction)}；"
                f"交易后现金约 {_money_text(plan.cash_after_purchase)}。"
            ),
            amount=round(plan.required_cash_after_pf_extract, 2),
            severity="success" if plan.cash_stress_ok else "warning",
        ),
        PlanEventPoint(
            plan_variant=plan.variant,
            month=purchase_month,
            category="provident",
            title="首付与公积金提取",
            detail=(
                f"本人公积金交易前抵扣 {_money_text(plan.provident_upfront_extractable)}，亲属首付支持 {_money_text(plan.family_down_payment_support_amount)}；"
                f"交易后预计到账 {_money_text(plan.provident_post_transaction_extractable)}，购后策略为“{plan.post_purchase_pf_strategy_label}”。"
            ),
            amount=round(plan.provident_upfront_extractable + plan.family_down_payment_support_amount, 2),
            severity="info",
        ),
    ]

    if purchase_point and purchase_point.transaction_cash_in > 0:
        events.append(
            PlanEventPoint(
                plan_variant=plan.variant,
                month=purchase_month,
                category="investment",
                title="投资账户变现",
                detail=(
                    f"交易月投资账户变现和其他交易流入合计 {_money_text(purchase_point.transaction_cash_in)}；"
                    f"卖出手续费计入当月投资费用，后续投资账户重新从定投策略推演。"
                ),
                amount=round(purchase_point.transaction_cash_in, 2),
                severity="info",
            )
        )

    events.append(
        PlanEventPoint(
            plan_variant=plan.variant,
            month=purchase_month,
            category="loan",
            title="贷款结构生效",
            detail=(
                f"公积金贷 {_money_text(plan.provident_loan_amount)}（{plan.provident_loan_years} 年，"
                f"{_repayment_method_label(plan.provident_repayment_method)}），商贷 {_money_text(plan.commercial_loan_amount)}（"
                f"{plan.commercial_loan_years} 年，{_repayment_method_label(plan.commercial_repayment_method)}）。"
                f"{plan.provident_repayment_advice}"
            ),
            amount=round(plan.provident_loan_amount + plan.commercial_loan_amount, 2),
            severity="info",
        )
    )

    if plan.provident_loan_year_limit_reasons:
        events.append(
            PlanEventPoint(
                plan_variant=plan.variant,
                month=purchase_month,
                category="provident",
                title="公积金贷款年限依据",
                detail="；".join(plan.provident_loan_year_limit_reasons),
                amount=None,
                severity="info",
            )
        )

    if plan.post_purchase_pf_strategy.startswith("monthly_then_semiannual_offset"):
        switch_month = _pf_strategy_switch_month(plan.post_purchase_pf_strategy)
        events.append(
            PlanEventPoint(
                plan_variant=plan.variant,
                month=purchase_month + switch_month + 1,
                category="provident",
                title="公积金还贷方式切换",
                detail=(
                    f"前 {switch_month} 个还款月采用按月约定提取偿还公积金贷款，"
                    "本月起切换为北京半年度冲还贷：账户余额在每年 1 月/7 月合同约定日集中冲抵公积金贷款本金。"
                    "两种模式互斥，切换后按月约定提取终止，后续账户曲线按冲还贷规则推演。"
                ),
                amount=None,
                severity="success",
            )
        )

    if not plan.cash_stress_ok:
        events.append(
            PlanEventPoint(
                plan_variant=plan.variant,
                month=max(0, int(plan.minimum_cash_balance_month or purchase_month)),
                category="risk",
                title="压力现金缺口",
                detail=(
                    f"后端压力推演最低现金约 {_money_text(plan.minimum_cash_balance)}，短缺约 {_money_text(plan.cash_stress_shortfall)}；"
                    "现金账户不能为负，应延后或调整策略。"
                ),
                amount=round(plan.cash_stress_shortfall, 2),
                severity="danger",
            )
        )

    if scenario.renovation_cost > 0:
        renovation_month = (
            purchase_month
            if plan.renovation_included_in_upfront_cash
            else purchase_month + plan.months_to_renovation
            if plan.months_to_renovation is not None
            else purchase_month
        )
        events.append(
            PlanEventPoint(
                plan_variant=plan.variant,
                month=renovation_month,
                category="renovation",
                title="装修资金",
                detail=(
                    f"装修预算 {_money_text(scenario.renovation_cost)}。"
                    if plan.renovation_included_in_upfront_cash
                    else f"装修预算 {_money_text(scenario.renovation_cost)} 买后慢慢攒；后端按买后月结余 {_money_text(plan.post_purchase_renovation_monthly_saving)} 估算启动时间。"
                ),
                amount=round(scenario.renovation_cost, 2),
                severity="success" if plan.months_to_renovation is not None else "warning",
            )
        )
    return events
