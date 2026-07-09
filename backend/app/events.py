from __future__ import annotations

from collections.abc import Callable
from datetime import date

from .core_object_concepts import CALIBRATION_TARGET_LABELS
from .domain.children import build_child_plan_strategies
from .domain.time import month_distance, months_between_months, parse_iso_date, parse_year_month
from .schemas import (
    CarLoanSummary,
    CarPlanData,
    CalculationContextSnapshot,
    HouseholdData,
    IncomeStageData,
    MonthlyCashflowPoint,
    PlanEventPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
)
from .strategies.home_events import purchase_plan_events
from .strategies.vehicle import vehicle_events_for_plan

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


def _money_text(amount: float) -> str:
    value = round(float(amount), 2)
    if abs(value) >= 10000:
        text = f"{value / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text} 万"
    text = f"{value:.0f}" if value == round(value) else f"{value:.2f}"
    return f"{text} 元"


def account_plan_events(
    household: HouseholdData,
    *,
    plan_variant: str,
    current_month: date,
    initial_provident_balance: float,
) -> list[PlanEventPoint]:
    events = [
        PlanEventPoint(
            plan_variant=plan_variant,
            month=0,
            category="account",
            title="当前账户快照",
            detail=(
                f"现金账户 {_money_text(household.cash_account_balance)}，投资账户 {_money_text(household.investments)}，"
                f"公积金账户 {_money_text(initial_provident_balance)}。这些余额后续由后端账户引擎逐月推演。"
            ),
            amount=None,
            severity="info",
        ),
        PlanEventPoint(
            plan_variant=plan_variant,
            month=0,
            category="investment",
            title="理财策略启动",
            detail=(
                f"目标月定投 {_money_text(household.monthly_investment_amount)}；后端会先保护现金安全垫，"
                "现金不足时减少或暂停定投，现金超额时按滚动节奏转入投资账户，投资收益留在投资账户复利。"
            ),
            amount=None,
            severity="info",
        ),
    ]
    for calibration in household.account_calibrations:
        if not calibration.enabled:
            continue
        target_month = parse_year_month(calibration.month)
        if target_month is None:
            continue
        month_index = max(0, month_distance((current_month.year, current_month.month), target_month))
        target_label = CALIBRATION_TARGET_LABELS.get(calibration.target, "账户")
        source_title = calibration.source_title or calibration.reference_name
        source_text = f"；来源：{source_title}" if source_title else ""
        note = f"；备注：{calibration.note}" if calibration.note else ""
        events.append(
            PlanEventPoint(
                plan_variant=plan_variant,
                month=month_index,
                category="loan" if calibration.target == "total_loan" else "account",
                title=f"手动校准：{source_title or target_label}",
                detail=(
                    f"{calibration.month} 将{target_label}"
                    f"对齐为 {_money_text(calibration.amount)}。"
                    "现金账户、投资账户会直接改变后续推演基准；账户和资产类校准会以偏移量延续到之后月份。"
                    f"{source_text}"
                    f"{note}"
                ),
                amount=round(calibration.amount, 2),
                severity="info",
            )
        )
    return events


def income_stage_event_detail(stage: IncomeStageData) -> str:
    parts: list[str] = []
    if stage.stage_kind == "pension":
        parts.append(f"退休后养老金约 {_money_text(stage.monthly_non_taxable_income)}/月，作为非税现金收入进入长期现金流。")
    elif stage.stage_kind == "unemployment":
        if stage.monthly_non_taxable_income > 0:
            parts.append(f"失业保险待遇约 {_money_text(stage.monthly_non_taxable_income)}/月。")
        if stage.monthly_freelance_income > 0:
            parts.append(f"同期自由职业收入约 {_money_text(stage.monthly_freelance_income)}/月，会并入税务和现金流测算。")
    elif stage.stage_kind == "freelance":
        if stage.monthly_freelance_income > 0:
            parts.append(f"自由职业收入约 {_money_text(stage.monthly_freelance_income)}/月。")
        if stage.monthly_social_insurance > 0:
            parts.append(f"灵活就业自缴社保约 {_money_text(stage.monthly_social_insurance)}/月。")
        if stage.monthly_housing_fund > 0:
            parts.append(f"灵活就业自缴公积金约 {_money_text(stage.monthly_housing_fund)}/月，进入成员公积金账户。")
    else:
        if stage.monthly_non_taxable_income > 0:
            parts.append(f"非税现金收入约 {_money_text(stage.monthly_non_taxable_income)}/月。")
    return "；".join(parts) if parts else "该收入阶段改变工资、社保、公积金或现金流口径。"


def automatic_income_stage_events(
    household: HouseholdData,
    *,
    plan_variant: str,
    current_month: date,
) -> list[PlanEventPoint]:
    events: list[PlanEventPoint] = []
    for member in household.members:
        for stage in member.income_stages:
            if not stage.name.startswith("自动情景："):
                continue
            start = parse_iso_date(stage.start_date, current_month)
            month = max(0, months_between_months(current_month, date(start.year, start.month, 1)))
            events.append(
                PlanEventPoint(
                    plan_variant=plan_variant,
                    month=month,
                    category="income",
                    title=f"{member.name}{stage.name.replace('自动情景：', '')}",
                    detail=income_stage_event_detail(stage),
                    amount=None,
                    severity="success" if stage.stage_kind == "pension" else "warning",
                )
            )
    return events


def retirement_account_events(
    *,
    plan_variant: str,
    provident_rows: list[ProvidentVisualizationPoint],
) -> list[PlanEventPoint]:
    events: list[PlanEventPoint] = []
    for row in provident_rows:
        retired_accounts = [
            account
            for account in row.member_accounts
            if account.account_closed_by_retirement and account.retirement_withdrawal > 0
        ]
        if not retired_accounts:
            continue
        if len(retired_accounts) == 1:
            account = retired_accounts[0]
            title = f"{account.member_name}公积金退休销户"
            detail = (
                f"该成员达到退休月份，后端停止继续缴存公积金，并将账户余额 "
                f"{_money_text(account.retirement_withdrawal)} 作为退休销户提取进入现金账户。"
            )
        else:
            title = "家庭公积金退休销户"
            detail = (
                "、".join(f"{account.member_name} {_money_text(account.retirement_withdrawal)}" for account in retired_accounts)
                + "；后端从该月起停止对应成员公积金缴存，并把退休销户提取计入现金账户。"
            )
        events.append(
            PlanEventPoint(
                plan_variant=plan_variant,
                month=row.month,
                category="provident",
                title=title,
                detail=detail,
                amount=round(sum(account.retirement_withdrawal for account in retired_accounts), 2),
                severity="success",
            )
        )
    return events


def no_vehicle_plan_event(
    household: HouseholdData,
    *,
    plan_variant: str,
) -> PlanEventPoint:
    return PlanEventPoint(
        plan_variant=plan_variant,
        month=0,
        category="vehicle",
        title="不买车模式",
        detail=f"当前不规划购车，通勤按无车成本 {_money_text(household.car_plan.no_car_monthly_commute_cost)}/月计入现金流。",
        amount=None,
        severity="info",
    )


def retirement_observation_window_event(
    *,
    plan_variant: str,
    retirement_window_end: int,
) -> PlanEventPoint | None:
    if retirement_window_end <= 0:
        return None
    return PlanEventPoint(
        plan_variant=plan_variant,
        month=retirement_window_end,
        category="income",
        title="退休后长期观察窗口",
        detail="后端账户曲线至少延伸到最晚退休后 10 年，用于观察养老金、公积金销户、贷款余额、现金账户和投资账户在退休后的变化。",
        amount=None,
        severity="info",
    )


def child_plan_events(
    household: HouseholdData,
    rules: RulePackData,
    *,
    plan_variant: str,
    home_purchase_month: int | None,
    current_month: date,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[PlanEventPoint]:
    events: list[PlanEventPoint] = []
    for child_strategy in build_child_plan_strategies(
        household,
        rules,
        home_purchase_month=home_purchase_month,
        as_of=current_month,
        calculation_context=calculation_context,
    ):
        if not child_strategy.enabled:
            continue
        if child_strategy.preparation_start_month_index is not None and child_strategy.preparation_start_month_index >= 0:
            events.append(
                PlanEventPoint(
                    plan_variant=plan_variant,
                    month=child_strategy.preparation_start_month_index,
                    category="child",
                    title=f"{child_strategy.child_name}备孕准备",
                    detail="开始计入备孕准备支出；具体金额来自养娃计划支出口径。",
                    amount=None,
                    severity="info",
                )
            )
        if child_strategy.pregnancy_start_month_index is not None and child_strategy.pregnancy_start_month_index >= 0:
            events.append(
                PlanEventPoint(
                    plan_variant=plan_variant,
                    month=child_strategy.pregnancy_start_month_index,
                    category="child",
                    title=f"{child_strategy.child_name}孕期支出",
                    detail="孕期检查、营养和时间弹性开始进入现金流测算。",
                    amount=None,
                    severity="info",
                )
            )
        if child_strategy.birth_month_index is not None and child_strategy.birth_month_index >= 0:
            detail = child_strategy.explanation
            if child_strategy.warnings:
                detail += " 风险提示：" + "；".join(child_strategy.warnings)
            events.append(
                PlanEventPoint(
                    plan_variant=plan_variant,
                    month=child_strategy.birth_month_index,
                    category="child",
                    title=f"{child_strategy.child_name}出生节点",
                    detail=detail,
                    amount=round(child_strategy.first_year_cash_need, 2),
                    severity="warning" if child_strategy.warnings else "success",
                )
            )
        if child_strategy.education_start_month_index is not None and child_strategy.education_start_month_index >= 0:
            events.append(
                PlanEventPoint(
                    plan_variant=plan_variant,
                    month=child_strategy.education_start_month_index,
                    category="child",
                    title=f"{child_strategy.child_name}教育阶段启动",
                    detail="教育阶段月支出和入学节点支出开始按养娃计划口径进入现金流；专项附加扣除仍由税务模块统一计算。",
                    amount=None,
                    severity="info",
                )
            )
    return events


def planning_goal_constraint_events(
    calculation_context: CalculationContextSnapshot | None,
    *,
    plan_variant: str,
) -> list[PlanEventPoint]:
    if calculation_context is None or not calculation_context.planning_goals:
        return []
    category_by_type = {
        "home": "home_purchase",
        "vehicle": "vehicle",
        "child": "child",
        "renovation": "renovation",
        "other": "risk",
    }
    events: list[PlanEventPoint] = []
    for goal in calculation_context.planning_goals:
        if goal.normalized_timing_mode == "not_planned":
            month = 0
            severity = "info"
            detail = f"{goal.name} 已保留在目标库中，但当前未纳入策略排程和现金流测算。"
        else:
            month = max(0, goal.resolved_window_start_month or goal.resolved_not_before_month)
            severity = "warning" if goal.dependency_warning else "info"
            detail_parts = [goal.explanation or "该目标的时间约束来自统一规划目标表。"]
            if goal.resolved_window_end_month is not None:
                detail_parts.append(f"规划窗口约束为第 {goal.resolved_window_start_month} 到第 {goal.resolved_window_end_month} 个月。")
            elif goal.resolved_not_before_month > 0:
                detail_parts.append(f"最早从第 {goal.resolved_not_before_month} 个月开始纳入策略搜索。")
            if goal.dependency_warning:
                detail_parts.append(goal.dependency_warning)
            detail = " ".join(part for part in detail_parts if part)
        events.append(
            PlanEventPoint(
                plan_variant=plan_variant,
                month=month,
                category=category_by_type.get(goal.goal_type, "risk"),
                title=f"规划目标：{goal.name}",
                detail=detail,
                amount=None,
                severity=severity,
                source="planning_goals",
            )
        )
    return events


def build_plan_events(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    monthly_cashflow: list[MonthlyCashflowPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    *,
    current_month: date,
    initial_provident_balance: float,
    retirement_window_end: int,
    vehicle_loan_states_for_plan: Callable[[PurchasePlanAnalysis], list[VehicleLoanState]],
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[PlanEventPoint]:
    monthly_by_plan_month = {(row.plan_variant, row.month): row for row in monthly_cashflow}
    provident_by_plan = {
        plan.variant: [row for row in provident_visualization if row.plan_variant == plan.variant]
        for plan in purchase_plans
    }
    events: list[PlanEventPoint] = []
    for plan in purchase_plans:
        vehicle_states = vehicle_loan_states_for_plan(plan)
        events.extend(
            account_plan_events(
                household,
                plan_variant=plan.variant,
                current_month=current_month,
                initial_provident_balance=initial_provident_balance,
            )
        )
        if not vehicle_states:
            events.append(no_vehicle_plan_event(household, plan_variant=plan.variant))
        else:
            for vehicle_index, vehicle_plan, vehicle_loan, _ in vehicle_states:
                events.extend(
                    vehicle_events_for_plan(
                        plan_variant=plan.variant,
                        title_prefix="车辆" if len(vehicle_states) == 1 else vehicle_plan.name or f"车辆 {vehicle_index + 1}",
                        car_plan=vehicle_plan,
                        car_loan=vehicle_loan,
                    )
                )

        events.extend(
            automatic_income_stage_events(
                household,
                plan_variant=plan.variant,
                current_month=current_month,
            )
        )
        events.extend(
            retirement_account_events(
                plan_variant=plan.variant,
                provident_rows=provident_by_plan.get(plan.variant, []),
            )
        )
        events.extend(
            child_plan_events(
                household,
                rules,
                plan_variant=plan.variant,
                home_purchase_month=plan.months_to_buy,
                current_month=current_month,
            )
        )
        events.extend(
            planning_goal_constraint_events(
                calculation_context,
                plan_variant=plan.variant,
            )
        )
        retirement_event = retirement_observation_window_event(
            plan_variant=plan.variant,
            retirement_window_end=retirement_window_end,
        )
        if retirement_event is not None:
            events.append(retirement_event)

        purchase_point = (
            monthly_by_plan_month.get((plan.variant, plan.months_to_buy))
            if plan.months_to_buy is not None
            else None
        )
        events.extend(
            purchase_plan_events(
                plan,
                scenario,
                purchase_point=purchase_point,
            )
        )

    category_order = {
        "account": 0,
        "income": 1,
        "investment": 2,
        "vehicle": 3,
        "child": 4,
        "home_purchase": 5,
        "loan": 6,
        "provident": 7,
        "renovation": 8,
        "risk": 9,
    }
    plan_order = {plan.variant: index for index, plan in enumerate(purchase_plans)}
    return sorted(events, key=lambda item: (plan_order.get(item.plan_variant, 999), item.month, category_order[item.category], item.title))


def build_plan_events_from_context(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    monthly_cashflow: list[MonthlyCashflowPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    *,
    initial_provident_balance_provider: Callable[[HouseholdData, RulePackData], float],
    retirement_window_end_provider: Callable[[HouseholdData, date], int],
    vehicle_loan_states_for_plan: Callable[[PurchasePlanAnalysis], list[VehicleLoanState]],
    as_of: date | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[PlanEventPoint]:
    base = as_of or date.today()
    current_month = date(base.year, base.month, 1)
    return build_plan_events(
        household,
        scenario,
        rules,
        purchase_plans,
        monthly_cashflow,
        provident_visualization,
        current_month=current_month,
        initial_provident_balance=initial_provident_balance_provider(household, rules),
        retirement_window_end=retirement_window_end_provider(household, current_month),
        vehicle_loan_states_for_plan=vehicle_loan_states_for_plan,
        calculation_context=calculation_context,
    )
