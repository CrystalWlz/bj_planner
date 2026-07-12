from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from ..domain.children import child_plan_birth_month_for_strategy as _child_plan_birth_month_for_strategy
from ..domain.career import household_with_pension_income_stages as _household_with_pension_income_stages
from ..domain.investments import investment_effective_tax_rate, investment_tax_estimate
from ..domain.personal_pension import (
    personal_pension_annual_return_for_month,
    personal_pension_withdrawal_start_month,
)
from ..domain.tax import (
    income_stage_for_month as _income_stage_for_month,
    stage_bonus_cash_amount as _stage_bonus_cash_amount,
    stage_bonus_payout_amount as _stage_bonus_payout_amount,
    stage_bonus_payout_month as _stage_bonus_payout_month,
)
from ..domain.time import (
    format_year_month_tuple as _format_year_month_tuple,
    month_after as _month_after,
    months_between_months as _months_between_months,
    parse_iso_date as _parse_iso_date,
    parse_year_month as _parse_year_month,
)
from ..policy_explanations import market_assumption_note, policy_source_note, user_config_note
from ..policies import get_policy
from ..schemas import (
    HouseholdData,
    IncomeMember,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    TaxEventPoint,
    TaxStrategyItem,
    TaxStrategyTimelinePoint,
)


PersonalPensionTaxSavingEstimator = Callable[[HouseholdData, IncomeMember, RulePackData, int, float], float]


@dataclass(frozen=True)
class PersonalPensionAnnualOptimization:
    year: int
    annual_contribution: float
    estimated_tax_saving: float
    pension_net_value_at_withdrawal: float
    alternative_investment_value_at_withdrawal: float
    tax_saving_future_value: float
    net_advantage_at_withdrawal: float


@dataclass(frozen=True)
class PersonalPensionOptimizationDecision:
    member_index: int
    should_open: bool
    open_month: str = ""
    annual_schedule: dict[str, float] = field(default_factory=dict)
    annual_points: list[PersonalPensionAnnualOptimization] = field(default_factory=list)
    cumulative_contribution: float = 0.0
    cumulative_tax_saving: float = 0.0
    pension_net_value_at_withdrawal: float = 0.0
    alternative_investment_value_at_withdrawal: float = 0.0
    tax_saving_future_value: float = 0.0
    net_advantage_at_withdrawal: float = 0.0
    full_cap_annual_tax_saving: float = 0.0
    full_cap_net_advantage_at_withdrawal: float = 0.0


def _future_value_with_monthly_rate(amount: float, annual_return: float, months: int) -> float:
    if amount <= 0:
        return 0.0
    monthly_return = (1 + max(-0.95, annual_return)) ** (1 / 12) - 1
    return amount * ((1 + monthly_return) ** max(0, months))


def optimize_personal_pension_strategies(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    base_date: date,
    personal_pension_tax_saving_estimator: PersonalPensionTaxSavingEstimator,
) -> tuple[HouseholdData, dict[int, PersonalPensionOptimizationDecision]]:
    current_month = date(base_date.year, base_date.month, 1)
    annual_cap = max(0.0, get_policy(rules).tax_benefit_policy().personal_pension_deduction_annual_cap)
    withdrawal_tax_rate = get_policy(rules).tax_benefit_policy().personal_pension_withdrawal_tax_rate
    ordinary_return = max(-0.95, scenario.annual_investment_return * (1 - investment_effective_tax_rate(household)))
    buy_fee_rate = max(0.0, min(0.05, household.investment_buy_fee_rate))
    sell_fee_rate = max(0.0, min(0.05, household.investment_sell_fee_rate))
    candidate_step = max(500.0, annual_cap / 12) if annual_cap > 0 else 0.0
    candidate_amounts = (
        [0.0]
        if annual_cap <= 0
        else sorted({0.0, annual_cap, *[min(annual_cap, candidate_step * index) for index in range(1, 13)]})
    )
    decisions: dict[int, PersonalPensionOptimizationDecision] = {}
    optimized_members: list[IncomeMember] = []

    for member_index, member in enumerate(household.members):
        auto_managed = bool(
            member.personal_pension_account_enabled
            and member.personal_pension_participation_eligible
            and member.pension_account_enabled
            and member.personal_pension_open_mode == "auto_tax_optimal"
            and member.personal_pension_contribution_mode == "auto_tax_optimal"
        )
        if not auto_managed:
            optimized_members.append(member)
            continue
        withdrawal_month = personal_pension_withdrawal_start_month(
            member,
            member_index,
            rules,
            base_month=current_month,
        )
        withdrawal_offset = max(0, _months_between_months(current_month, withdrawal_month))
        annual_points: list[PersonalPensionAnnualOptimization] = []
        annual_schedule: dict[str, float] = {}
        first_full_cap_point: PersonalPensionAnnualOptimization | None = None
        for year in range(current_month.year, withdrawal_month.year + 1):
            contribution_month_number = max(current_month.month, 6) if year == current_month.year else 6
            contribution_month = date(year, contribution_month_number, 1)
            contribution_offset = _months_between_months(current_month, contribution_month)
            if contribution_offset < 0 or contribution_offset >= withdrawal_offset:
                continue
            months_to_withdrawal = withdrawal_offset - contribution_offset
            best_point = PersonalPensionAnnualOptimization(year, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            for amount in candidate_amounts[1:]:
                tax_saving = personal_pension_tax_saving_estimator(household, member, rules, year, amount)
                pension_value = amount
                for month_offset in range(contribution_offset, withdrawal_offset):
                    annual_return = personal_pension_annual_return_for_month(
                        member,
                        member_index,
                        rules,
                        base_month=current_month,
                        months_from_now=month_offset,
                    )
                    pension_value = _future_value_with_monthly_rate(pension_value, annual_return, 1)
                pension_net = pension_value * (1 - member.personal_pension_redemption_fee_rate) * (1 - withdrawal_tax_rate)
                alternative_value = _future_value_with_monthly_rate(
                    amount * (1 - buy_fee_rate),
                    ordinary_return,
                    months_to_withdrawal,
                ) * (1 - sell_fee_rate)
                tax_saving_future = _future_value_with_monthly_rate(
                    tax_saving * (1 - buy_fee_rate),
                    ordinary_return,
                    months_to_withdrawal,
                ) * (1 - sell_fee_rate)
                net_advantage = pension_net + tax_saving_future - alternative_value
                point = PersonalPensionAnnualOptimization(
                    year=year,
                    annual_contribution=round(amount, 2),
                    estimated_tax_saving=round(tax_saving, 2),
                    pension_net_value_at_withdrawal=round(pension_net, 2),
                    alternative_investment_value_at_withdrawal=round(alternative_value, 2),
                    tax_saving_future_value=round(tax_saving_future, 2),
                    net_advantage_at_withdrawal=round(net_advantage, 2),
                )
                if amount == annual_cap and first_full_cap_point is None:
                    first_full_cap_point = point
                if point.net_advantage_at_withdrawal > best_point.net_advantage_at_withdrawal:
                    best_point = point
            if best_point.net_advantage_at_withdrawal > max(100.0, best_point.annual_contribution * 0.005):
                annual_schedule[str(year)] = best_point.annual_contribution
                annual_points.append(best_point)

        should_open = bool(annual_schedule)
        first_open_year = min((int(year) for year in annual_schedule), default=0)
        first_open_month_number = 1
        if should_open:
            for month_number in range(current_month.month if first_open_year == current_month.year else 1, 13):
                stage = _income_stage_for_month(member, first_open_year, month_number)
                if stage is None or stage.stage_kind in {"pension", "unemployment"}:
                    continue
                taxable_income = (
                    stage.monthly_salary_gross
                    + stage.monthly_freelance_income
                    + stage.other_annual_taxable_income / 12
                    + _stage_bonus_cash_amount(stage, first_open_year, month_number)
                )
                if taxable_income > 0:
                    first_open_month_number = month_number
                    break
        open_month = (
            f"{first_open_year:04d}-{first_open_month_number:02d}"
            if should_open
            else ""
        )
        decision = PersonalPensionOptimizationDecision(
            member_index=member_index,
            should_open=should_open,
            open_month=open_month,
            annual_schedule=annual_schedule,
            annual_points=annual_points,
            cumulative_contribution=round(sum(point.annual_contribution for point in annual_points), 2),
            cumulative_tax_saving=round(sum(point.estimated_tax_saving for point in annual_points), 2),
            pension_net_value_at_withdrawal=round(sum(point.pension_net_value_at_withdrawal for point in annual_points), 2),
            alternative_investment_value_at_withdrawal=round(sum(point.alternative_investment_value_at_withdrawal for point in annual_points), 2),
            tax_saving_future_value=round(sum(point.tax_saving_future_value for point in annual_points), 2),
            net_advantage_at_withdrawal=round(sum(point.net_advantage_at_withdrawal for point in annual_points), 2),
            full_cap_annual_tax_saving=first_full_cap_point.estimated_tax_saving if first_full_cap_point else 0.0,
            full_cap_net_advantage_at_withdrawal=first_full_cap_point.net_advantage_at_withdrawal if first_full_cap_point else 0.0,
        )
        decisions[member_index] = decision
        if should_open:
            optimized_members.append(
                member.model_copy(
                    update={
                        "personal_pension_account_enabled": True,
                        "personal_pension_open_mode": "auto_tax_optimal",
                        "personal_pension_account_open_month": open_month,
                        "personal_pension_contribution_mode": "auto_tax_optimal",
                        "personal_pension_contribution_start_month": open_month,
                        "personal_pension_annual_contribution_target": annual_schedule.get(str(current_month.year), 0.0),
                        "personal_pension_auto_annual_contribution_schedule": annual_schedule,
                    }
                )
            )
        else:
            optimized_members.append(
                member.model_copy(
                    update={
                        "personal_pension_account_enabled": member.personal_pension_account_balance > 0,
                        "personal_pension_open_mode": "manual" if member.personal_pension_account_balance > 0 else "none",
                        "personal_pension_contribution_mode": "none",
                        "personal_pension_annual_contribution_target": 0.0,
                        "personal_pension_auto_annual_contribution_schedule": {},
                    }
                )
            )
    return household.model_copy(update={"members": optimized_members}), decisions


def _personal_pension_retirement_estimate(
    member: IncomeMember,
    member_index: int,
    rules: RulePackData,
    *,
    base_month: date,
    monthly_contribution: float,
) -> tuple[str, float, float]:
    withdrawal_month = personal_pension_withdrawal_start_month(
        member,
        member_index,
        rules,
        base_month=base_month,
    )
    redemption_delay = (
        0
        if member.personal_pension_product_liquidity_mode == "daily_liquid"
        else member.personal_pension_redemption_delay_months
    )
    if redemption_delay:
        withdrawal_year, withdrawal_month_number = _month_after(
            withdrawal_month,
            redemption_delay,
        )
        withdrawal_month = date(withdrawal_year, withdrawal_month_number, 1)
    months_to_withdrawal = max(0, _months_between_months(base_month, withdrawal_month))
    configured_end = _parse_year_month(member.personal_pension_contribution_end_month or "")
    configured_end_offset = (
        _months_between_months(base_month, date(configured_end[0], configured_end[1], 1))
        if configured_end
        else months_to_withdrawal - 1
    )
    balance = max(0.0, member.personal_pension_account_balance)
    for month in range(months_to_withdrawal + 1):
        contribution = monthly_contribution if month < months_to_withdrawal and month <= configured_end_offset else 0.0
        annual_return = personal_pension_annual_return_for_month(
            member,
            member_index,
            rules,
            base_month=base_month,
            months_from_now=month,
        )
        monthly_return = (1 + max(-0.95, annual_return)) ** (1 / 12) - 1
        balance = max(0.0, (balance + contribution) * (1 + monthly_return))
    mode = member.personal_pension_withdrawal_mode
    if mode == "lump_sum":
        gross_monthly = balance
    elif mode == "fixed_monthly":
        gross_monthly = min(balance, member.personal_pension_fixed_monthly_withdrawal)
    else:
        gross_monthly = balance / max(12, member.personal_pension_withdrawal_years * 12)
    redeemable_ratio = (
        1.0
        if member.personal_pension_product_liquidity_mode == "daily_liquid"
        else member.personal_pension_monthly_redeemable_ratio
    )
    gross_monthly = min(balance * redeemable_ratio, gross_monthly)
    withdrawal_tax_rate = get_policy(rules).tax_benefit_policy().personal_pension_withdrawal_tax_rate
    redemption_fee_rate = member.personal_pension_redemption_fee_rate
    return (
        f"{withdrawal_month.year:04d}-{withdrawal_month.month:02d}",
        balance,
        gross_monthly * (1 - redemption_fee_rate) * (1 - withdrawal_tax_rate),
    )


def _tax_source_labeled_detail(source: str, category: str, detail: str) -> str:
    if category == "investment_tax" and source != "manual":
        return market_assumption_note(detail)
    if source in {"manual", "event"}:
        return user_config_note(detail)
    return policy_source_note(detail)


def build_tax_events(
    household: HouseholdData,
    rules: RulePackData,
    *,
    base_date: date | None = None,
    horizon_months: int = 840,
) -> list[TaxEventPoint]:
    household = _household_with_pension_income_stages(household, rules, as_of=base_date)
    current = base_date or date.today()
    current_month = date(current.year, current.month, 1)
    end_year, end_month = _month_after(current_month, max(0, horizon_months))
    end_date = date(end_year, end_month, 1)
    events: list[TaxEventPoint] = []

    for member in household.members:
        for stage in member.income_stages:
            start = _parse_iso_date(stage.start_date, current_month)
            if current_month <= start <= end_date:
                absolute_month = _months_between_months(current_month, date(start.year, start.month, 1))
                events.append(
                    TaxEventPoint(
                        month=absolute_month,
                        year=start.year,
                        month_of_year=start.month,
                        member_name=member.name,
                        event_type="income_stage_start",
                        title=f"{member.name}收入阶段开始",
                        detail=f"{stage.name}从{start.year}年{start.month}月开始参与税务测算。",
                        amount=round(stage.monthly_salary_gross + stage.monthly_freelance_income + stage.monthly_non_taxable_income, 2),
                    )
                )

            if stage.end_date:
                end = _parse_iso_date(stage.end_date, end_date)
                if current_month <= end <= end_date:
                    absolute_month = _months_between_months(current_month, date(end.year, end.month, 1))
                    events.append(
                        TaxEventPoint(
                            month=absolute_month,
                            year=end.year,
                            month_of_year=end.month,
                            member_name=member.name,
                            event_type="income_stage_end",
                            title=f"{member.name}收入阶段结束",
                            detail=f"{stage.name}在{end.year}年{end.month}月结束，后续按下一段收入规则计算。",
                            amount=None,
                        )
                    )

            for year in range(current_month.year, end_date.year + 1):
                bonus_month = _stage_bonus_payout_month(stage, year)
                if bonus_month is None:
                    continue
                bonus_date = date(year, bonus_month, 1)
                if not current_month <= bonus_date <= end_date:
                    continue
                bonus_amount = _stage_bonus_payout_amount(stage, year, bonus_month)
                if bonus_amount <= 0:
                    continue
                absolute_month = _months_between_months(current_month, bonus_date)
                events.append(
                    TaxEventPoint(
                        month=absolute_month,
                        year=year,
                        month_of_year=bonus_month,
                        member_name=member.name,
                        event_type="bonus_payout",
                        title=f"{member.name}年终奖发放",
                        detail=f"{stage.name}按{bonus_month}月发放年终奖，金额按该阶段当年生效月份折算。",
                        amount=round(bonus_amount, 2),
                    )
                )

    return sorted(events, key=lambda item: (item.month, item.member_name, item.event_type))


def _active_rent_deduction_window(
    household: HouseholdData,
    *,
    base_date: date,
    horizon_months: int,
) -> tuple[str, str | None] | None:
    end_year, end_month = _month_after(base_date, max(0, horizon_months))
    horizon_end = date(end_year, end_month, 1)
    starts: list[date] = []
    ends: list[date] = []
    for stage in household.rent_expense_stages:
        if stage.rent_amount <= 0:
            continue
        start = _parse_iso_date(stage.start_month, base_date)
        end = _parse_iso_date(stage.end_month, horizon_end) if stage.end_month else horizon_end
        if end < base_date or start > horizon_end:
            continue
        starts.append(max(start, base_date))
        ends.append(min(end, horizon_end))
    if not starts:
        return None
    start = min(starts)
    end = max(ends) if ends else None
    return f"{start.year:04d}-{start.month:02d}", f"{end.year:04d}-{end.month:02d}" if end and end < horizon_end else None


def _first_personal_pension_tax_optimal_month(
    member: IncomeMember,
    *,
    base_date: date,
    horizon_months: int,
) -> str:
    for offset in range(max(0, horizon_months) + 1):
        year, month = _month_after(base_date, offset)
        stage = _income_stage_for_month(member, year, month)
        if stage is None or stage.stage_kind in {"pension", "unemployment"}:
            continue
        taxable_income = (
            stage.monthly_salary_gross
            + stage.monthly_freelance_income
            + stage.other_annual_taxable_income / 12
            + _stage_bonus_cash_amount(stage, year, month)
        )
        if taxable_income > 0:
            return f"{year:04d}-{month:02d}"
    return ""


def build_tax_strategy_items(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    base_date: date | None = None,
    horizon_months: int = 840,
    selected_purchase_month: int | None = None,
    selected_purchase_plan: PurchasePlanAnalysis | None = None,
    auto_suspended_personal_pension_member_indexes: set[int] | None = None,
    personal_pension_original_insolvency_month: int | None = None,
    personal_pension_optimization_decisions: dict[int, PersonalPensionOptimizationDecision] | None = None,
    personal_pension_tax_saving_estimator: PersonalPensionTaxSavingEstimator,
) -> list[TaxStrategyItem]:
    current = base_date or date.today()
    current_month = date(current.year, current.month, 1)
    tax_benefit = get_policy(rules).tax_benefit_policy()
    member_name = household.members[0].name if household.members else ""
    rent_monthly = tax_benefit.housing_rent_monthly
    mortgage_monthly = tax_benefit.first_home_mortgage_interest_monthly
    max_mortgage_months = tax_benefit.first_home_mortgage_interest_max_months
    rent_window = _active_rent_deduction_window(household, base_date=current_month, horizon_months=horizon_months)
    suspended_personal_pension_indexes = auto_suspended_personal_pension_member_indexes or set()
    pension_optimization_decisions = personal_pension_optimization_decisions or {}

    items: list[TaxStrategyItem] = []
    if rent_window:
        rent_status: Literal["auto_enabled", "available"] = "auto_enabled"
        rent_reason = "检测到家庭存在租房支出阶段，税务策略默认把北京住房租金专项附加扣除纳入月度预扣预缴。"
        if selected_purchase_month is not None and mortgage_monthly > rent_monthly:
            rent_status = "available"
            rent_reason = "购房后首套住房贷款利息扣除金额高于租金扣除；租房期仍可用，购房后由策略切换到房贷利息口径。"
        items.append(
            TaxStrategyItem(
                deduction_type="housing_rent",
                title="北京住房租金专项附加扣除",
                status=rent_status,
                member_name=member_name,
                monthly_amount=round(rent_monthly, 2),
                start_month=rent_window[0],
                end_month=rent_window[1],
                reason=rent_reason,
                conflicts_with=["mortgage_interest"],
                source="event",
            )
        )
    else:
        items.append(
            TaxStrategyItem(
                deduction_type="housing_rent",
                title="北京住房租金专项附加扣除",
                status="not_applicable",
                monthly_amount=round(rent_monthly, 2),
                reason="当前没有检测到租房支出阶段；不由用户手动打开，等租房事件存在时再自动纳入税务策略。",
                conflicts_with=["mortgage_interest"],
                source="backend_auto",
            )
        )

    has_home_target = bool(getattr(scenario, "enabled", False)) and selected_purchase_month is not None
    if has_home_target:
        purchase_year, purchase_month = _month_after(current_month, max(0, selected_purchase_month or 0))
        mortgage_status: Literal["auto_enabled", "available"] = "auto_enabled"
        mortgage_reason = "检测到已选购房策略形成首套住房贷款事件，税务策略从购房还贷月开始考虑首套住房贷款利息专项附加扣除。"
        if rent_window and rent_monthly >= mortgage_monthly:
            mortgage_status = "available"
            mortgage_reason = "同月住房租金扣除高于或等于首套房贷利息扣除，策略优先使用租金口径；房贷利息作为可切换备选保留。"
        items.append(
            TaxStrategyItem(
                deduction_type="mortgage_interest",
                title="首套住房贷款利息专项附加扣除",
                status=mortgage_status,
                member_name=member_name,
                monthly_amount=round(mortgage_monthly, 2),
                start_month=f"{purchase_year:04d}-{purchase_month:02d}",
                end_month=_format_year_month_tuple(_month_after(date(purchase_year, purchase_month, 1), max(0, max_mortgage_months - 1))) if max_mortgage_months > 0 else None,
                reason=mortgage_reason,
                conflicts_with=["housing_rent"],
                source="event",
            )
        )
    else:
        items.append(
            TaxStrategyItem(
                deduction_type="mortgage_interest",
                title="首套住房贷款利息专项附加扣除",
                status="not_applicable",
                monthly_amount=round(mortgage_monthly, 2),
                reason="当前选中规划没有形成购房还贷事件，首套住房贷款利息扣除暂不启用。",
                conflicts_with=["housing_rent"],
                source="backend_auto",
            )
        )

    child_monthly = tax_benefit.child_education_monthly
    infant_monthly = tax_benefit.infant_care_monthly
    for child in household.child_plans:
        if not child.enabled:
            continue
        birth_month = _child_plan_birth_month_for_strategy(child, as_of=current_month, home_purchase_month=selected_purchase_month, rules=rules)
        if birth_month:
            items.append(
                TaxStrategyItem(
                    deduction_type="infant_care",
                    title=f"{child.name}婴幼儿照护扣除",
                    status="auto_enabled" if child.tax_deduction_owner else "available",
                    member_name=child.tax_deduction_owner,
                    monthly_amount=round(infant_monthly, 2),
                    start_month=_format_year_month_tuple(birth_month),
                    end_month=_format_year_month_tuple(_month_after(date(birth_month[0], birth_month[1], 1), 35)),
                    reason=(
                        "子女出生节点由养娃计划生成；3岁以下婴幼儿照护扣除需在税务页指定申报成员后纳入。"
                        if not child.tax_deduction_owner
                        else "子女出生节点由养娃计划生成；3岁以下婴幼儿照护扣除已按税务页指定成员纳入。"
                    ),
                    source="event",
                )
            )
        education_start = _parse_year_month(child.education_start_month)
        if education_start:
            items.append(
                TaxStrategyItem(
                    deduction_type="child_education",
                    title=f"{child.name}子女教育扣除",
                    status="auto_enabled" if child.tax_deduction_owner else "available",
                    member_name=child.tax_deduction_owner,
                    monthly_amount=round(child_monthly, 2),
                    start_month=_format_year_month_tuple(education_start),
                    reason=(
                        "教育阶段开始月来自养娃计划；子女教育扣除需在税务页指定申报成员后纳入。"
                        if not child.tax_deduction_owner
                        else "教育阶段开始月来自养娃计划；子女教育扣除已按税务页指定成员纳入。"
                    ),
                    source="event",
                )
            )

    for member_index, member in enumerate(household.members):
        if bool(getattr(member, "personal_pension_account_enabled", False)):
            open_mode = str(getattr(member, "personal_pension_open_mode", "auto_tax_optimal") or "auto_tax_optimal")
            contribution_mode = str(getattr(member, "personal_pension_contribution_mode", "auto_tax_optimal") or "auto_tax_optimal")
            annual_cap = tax_benefit.personal_pension_deduction_annual_cap
            withdrawal_tax_rate = tax_benefit.personal_pension_withdrawal_tax_rate
            recommended_start = _first_personal_pension_tax_optimal_month(
                member,
                base_date=current_month,
                horizon_months=horizon_months,
            )
            configured_open_month = str(getattr(member, "personal_pension_account_open_month", "") or "")
            configured_contribution_start = str(getattr(member, "personal_pension_contribution_start_month", "") or "")
            strategy_start_month = (
                configured_open_month
                if open_mode == "manual" and configured_open_month
                else configured_contribution_start
                if configured_contribution_start
                else recommended_start
            )
            status = "auto_enabled" if open_mode == "auto_tax_optimal" and contribution_mode == "auto_tax_optimal" else "manual_enabled"
            eligible = bool(member.personal_pension_participation_eligible and member.pension_account_enabled)
            if open_mode == "none" or contribution_mode == "none" or not eligible:
                status = "not_applicable"
            counterfactual_suspended = member_index in suspended_personal_pension_indexes
            optimization_decision = pension_optimization_decisions.get(member_index)
            economic_not_worthwhile = bool(optimization_decision is not None and not optimization_decision.should_open)
            if counterfactual_suspended:
                status = "conflict"
            elif economic_not_worthwhile:
                status = "conflict"
            annual_cash_contribution = 0.0
            if status in {"auto_enabled", "manual_enabled"}:
                if contribution_mode == "fixed_monthly":
                    annual_cash_contribution = min(
                        annual_cap,
                        max(0.0, float(getattr(member, "personal_pension_monthly_contribution", 0.0))) * 12,
                    )
                elif contribution_mode == "fixed_annual":
                    annual_cash_contribution = min(
                        annual_cap,
                        max(0.0, float(getattr(member, "personal_pension_annual_contribution_target", 0.0))),
                    )
                else:
                    if optimization_decision is not None:
                        strategy_start_month = optimization_decision.open_month
                        first_planned_amount = next(iter(optimization_decision.annual_schedule.values()), 0.0)
                        annual_cash_contribution = optimization_decision.annual_schedule.get(
                            str(current_month.year),
                            first_planned_amount,
                        )
                        if strategy_start_month > f"{current_month.year:04d}-{current_month.month:02d}":
                            status = "available"
                    else:
                        annual_cash_contribution = annual_cap if recommended_start or strategy_start_month else 0.0
            deductible_amount = min(max(0.0, annual_cash_contribution), max(0.0, annual_cap))
            strategy_start_tuple = _parse_year_month(strategy_start_month)
            tax_saving_year = strategy_start_tuple[0] if strategy_start_tuple else current.year
            estimated_tax_saving = (
                personal_pension_tax_saving_estimator(
                    household,
                    member,
                    rules,
                    tax_saving_year,
                    deductible_amount,
                )
                if deductible_amount > 0
                else 0.0
            )
            if member.personal_pension_return_mode == "manual":
                account_return_rate = float(getattr(member, "personal_pension_annual_return", 0.025) or 0.0)
                post_retirement_return_rate = float(
                    getattr(member, "personal_pension_post_retirement_annual_return", 0.015) or 0.0
                )
            else:
                return_policy = get_policy(rules).personal_pension_return_policy()
                account_return_rate = return_policy.pre_retirement_annual_return
                post_retirement_return_rate = return_policy.post_retirement_annual_return
            withdrawal_mode = member.personal_pension_withdrawal_mode
            withdrawal_start_month, estimated_retirement_balance, estimated_monthly_withdrawal = (
                _personal_pension_retirement_estimate(
                    member,
                    member_index,
                    rules,
                    base_month=current_month,
                    monthly_contribution=annual_cash_contribution / 12,
                )
            )
            configured_end_month = getattr(member, "personal_pension_contribution_end_month", "") or None
            contribution_end_reason = (
                f"按手动设置缴至 {configured_end_month}；开始领取后自动停止缴费。"
                if configured_end_month
                else f"默认缴至 {withdrawal_start_month} 开始领取前；退休后不再继续锁定新增现金。"
            )
            cash_safety_rule = (
                f"现金低于约 {member.personal_pension_cash_reserve_months} 个月基础生活费时暂停缴费，并同步取消当期未实际缴费对应的节税。"
                if member.personal_pension_auto_suspend_for_cash_safety
                else "未启用现金安全自动暂停；长期方案会把个人养老金缴费持续计入现金压力。"
            )
            long_term_cash_risk_month = ""
            recommended_action = "按当前缴费配置执行，并由现金安全垫规则逐月复核。"
            risk_month_offset = (
                personal_pension_original_insolvency_month
                if counterfactual_suspended
                else selected_purchase_plan.insolvency_month
                if selected_purchase_plan is not None
                else None
            )
            if counterfactual_suspended and risk_month_offset is not None:
                risk_year, risk_month = _month_after(current_month, risk_month_offset)
                long_term_cash_risk_month = f"{risk_year:04d}-{risk_month:02d}"
                has_existing_balance = member.personal_pension_account_balance > 0
                contribution_end_reason = (
                    f"原整体方案预计在 {long_term_cash_risk_month} 发生现金穿底，且停缴反事实能够改善整体可行性；"
                    "自动策略已从本期起停止新增缴费。"
                )
                recommended_action = (
                    "保留已开户账户和既有余额，但暂停新增缴费；待降低大额目标压力、补足自由现金安全垫，"
                    "并确认完整账本不再穿底后，再按边际税率恢复缴费。"
                    if has_existing_balance
                    else "当前不建议为了税优专门开户并缴费；先让购房等整体方案恢复长期可行，再评估开户。"
                )
            elif economic_not_worthwhile:
                contribution_end_reason = "在当前税率、养老金收益、领取税和普通理财税后收益假设下，没有找到净收益为正的缴费金额。"
                recommended_action = (
                    "当前建议暂不开户和缴费。普通理财的预期税后终值高于个人养老金净领取加节税再投资终值；"
                    "收入税率、产品收益或普通理财收益假设变化后，系统会重新搜索开户年份和缴费额。"
                )
            elif (
                selected_purchase_plan is not None
                and selected_purchase_plan.insolvency_month is not None
                and selected_purchase_plan.insolvency_month
                < _months_between_months(current_month, personal_pension_withdrawal_start_month(
                    member,
                    member_index,
                    rules,
                    base_month=current_month,
                ))
            ):
                risk_year, risk_month = _month_after(current_month, selected_purchase_plan.insolvency_month)
                long_term_cash_risk_month = f"{risk_year:04d}-{risk_month:02d}"
                contribution_end_reason = (
                    f"当前整体方案预计在 {long_term_cash_risk_month} 发生现金穿底，早于 {withdrawal_start_month} 可领取月份；"
                    "但仅暂停个人养老金尚未被验证为足以修复整体风险。"
                )
                recommended_action = (
                    "应优先调整购房总价、买入时点和其他长期现金压力；个人养老金继续由逐月现金安全规则暂停，"
                    "不能把停缴本身误写成已经消除破产风险。"
                )
            withdrawal_mode_label = {
                "auto_safe": "现金安全优先动态领取",
                "monthly_annuity": "按计划年限动态均匀领取",
                "fixed_monthly": "固定月领",
                "lump_sum": "一次性领取",
            }.get(withdrawal_mode, withdrawal_mode)
            if status == "conflict" and counterfactual_suspended:
                reason = (
                    "个人养老金自动缴费与家庭长期现金安全冲突。系统已用停缴反事实重新推演：年度新增缴费和扣除均为 0；"
                    f"{contribution_end_reason}收益率假设仍用于既有余额，退休前为 {account_return_rate:.1%}、退休后为 {post_retirement_return_rate:.1%}，"
                    f"预计 {withdrawal_start_month} 起可领取，领取环节按 {withdrawal_tax_rate:.1%} 税率估算。{recommended_action}"
                )
            elif status == "conflict" and economic_not_worthwhile:
                reason = f"个人养老金当前经济性不足。{contribution_end_reason}{recommended_action}"
            elif status in {"auto_enabled", "available"}:
                reason = (
                    f"税务策略建议在 {strategy_start_month or '首次有应税工作收入时'} 开户并开始缴存，按年度 {annual_cap:.0f} 元扣除上限搜索最优金额；"
                    f"首个计划年度缴费约 {annual_cash_contribution:.0f} 元，可扣除约 {deductible_amount:.0f} 元，"
                    f"估算节税约 {estimated_tax_saving:.0f} 元。{contribution_end_reason}"
                    f"收益率在退休前十年由 {account_return_rate:.1%} 平滑降至 {post_retirement_return_rate:.1%}，"
                    f"预计领取起点余额约 {estimated_retirement_balance:.0f} 元，采用“{withdrawal_mode_label}”；"
                    f"领取环节按 {withdrawal_tax_rate:.1%} 税率估算。{cash_safety_rule}"
                )
            elif status == "manual_enabled":
                reason = (
                    "个人养老金开户或缴存由用户手动控制；后端按手动月份、缴存方式和年度扣除上限测算。"
                    f"当前年度现金缴费约 {annual_cash_contribution:.0f} 元，可扣除约 {deductible_amount:.0f} 元，估算节税约 {estimated_tax_saving:.0f} 元。"
                    f"{contribution_end_reason}预计 {withdrawal_start_month} 起采用“{withdrawal_mode_label}”，首月净领取约 {estimated_monthly_withdrawal:.0f} 元；"
                    f"领取环节按 {withdrawal_tax_rate:.1%} 税率估算。{cash_safety_rule}"
                )
            else:
                reason = (
                    "该成员没有启用个人养老金缴费策略，因此不产生个人养老金税前扣除、现金转出和账户收益。"
                    if eligible
                    else "该成员尚未确认参加基本养老保险并具备个人养老金参加资格，不能生成开户、缴费或税前扣除。"
                )
            if optimization_decision is not None and optimization_decision.should_open:
                reason += (
                    f" 全周期计划累计缴费约 {optimization_decision.cumulative_contribution:.0f} 元，名义节税约 {optimization_decision.cumulative_tax_saving:.0f} 元；"
                    f"到领取起点，养老金税费后价值约 {optimization_decision.pension_net_value_at_withdrawal:.0f} 元，"
                    f"同额普通理财约 {optimization_decision.alternative_investment_value_at_withdrawal:.0f} 元，"
                    f"节税再投资约 {optimization_decision.tax_saving_future_value:.0f} 元，综合净增益约 {optimization_decision.net_advantage_at_withdrawal:.0f} 元。"
                )
            elif optimization_decision is not None and not optimization_decision.should_open:
                reason += (
                    f" 若本年仍按 {annual_cap:.0f} 元上限缴费，预计当年节税约 {optimization_decision.full_cap_annual_tax_saving:.0f} 元，"
                    f"但到领取起点相对普通理财的净差额约 {optimization_decision.full_cap_net_advantage_at_withdrawal:.0f} 元。"
                )
            optimization_points = optimization_decision.annual_points if optimization_decision is not None else []
            items.append(
                TaxStrategyItem(
                    deduction_type="personal_pension",
                    title=f"{member.name}个人养老金税前扣除",
                    status=status,
                    member_name=member.name,
                    monthly_amount=round(deductible_amount / 12, 2),
                    annual_amount=round(deductible_amount, 2),
                    estimated_tax_saving=round(estimated_tax_saving, 2),
                    cash_contribution=round(annual_cash_contribution, 2),
                    account_return_rate=round(account_return_rate, 6),
                    post_retirement_return_rate=round(post_retirement_return_rate, 6),
                    withdrawal_tax_rate=round(withdrawal_tax_rate, 6),
                    withdrawal_mode=withdrawal_mode,
                    withdrawal_start_month=withdrawal_start_month,
                    withdrawal_years=member.personal_pension_withdrawal_years,
                    estimated_retirement_balance=round(estimated_retirement_balance, 2),
                    estimated_monthly_withdrawal=round(estimated_monthly_withdrawal, 2),
                    cumulative_contribution=round(optimization_decision.cumulative_contribution, 2) if optimization_decision else 0.0,
                    cumulative_estimated_tax_saving=round(optimization_decision.cumulative_tax_saving, 2) if optimization_decision else 0.0,
                    pension_net_value_at_withdrawal=round(optimization_decision.pension_net_value_at_withdrawal, 2) if optimization_decision else 0.0,
                    alternative_investment_value_at_withdrawal=round(optimization_decision.alternative_investment_value_at_withdrawal, 2) if optimization_decision else 0.0,
                    forgone_investment_earnings=round(max(0.0, optimization_decision.alternative_investment_value_at_withdrawal - optimization_decision.cumulative_contribution), 2) if optimization_decision else 0.0,
                    tax_saving_future_value=round(optimization_decision.tax_saving_future_value, 2) if optimization_decision else 0.0,
                    net_advantage_at_withdrawal=round(optimization_decision.net_advantage_at_withdrawal, 2) if optimization_decision else 0.0,
                    full_cap_annual_tax_saving=round(optimization_decision.full_cap_annual_tax_saving, 2) if optimization_decision else 0.0,
                    full_cap_net_advantage_at_withdrawal=round(optimization_decision.full_cap_net_advantage_at_withdrawal, 2) if optimization_decision else 0.0,
                    personal_pension_annual_plan=[
                        {
                            "year": point.year,
                            "annual_contribution": point.annual_contribution,
                            "estimated_tax_saving": point.estimated_tax_saving,
                            "pension_net_value_at_withdrawal": point.pension_net_value_at_withdrawal,
                            "alternative_investment_value_at_withdrawal": point.alternative_investment_value_at_withdrawal,
                            "tax_saving_future_value": point.tax_saving_future_value,
                            "net_advantage_at_withdrawal": point.net_advantage_at_withdrawal,
                        }
                        for point in optimization_points
                    ],
                    cash_safety_rule=cash_safety_rule,
                    contribution_end_reason=contribution_end_reason,
                    long_term_cash_risk_month=long_term_cash_risk_month,
                    recommended_action=recommended_action,
                    start_month="" if status == "conflict" else strategy_start_month,
                    end_month=configured_end_month,
                    reason=reason,
                    source="backend_auto",
                )
            )

    for item in household.special_deductions:
        if not item.enabled:
            continue
        items.append(
            TaxStrategyItem(
                deduction_type=item.deduction_type,
                title=item.name,
                status="manual_enabled",
                member_name=item.member_name,
                monthly_amount=round(item.monthly_amount, 2),
                annual_amount=round(item.annual_amount, 2),
                start_month=item.start_month,
                end_month=item.end_month,
                reason="这是用户手动覆盖项，会和自动税务策略一起交给后端税务计算；住房租金和首套房贷利息仍按互斥规则处理。",
                conflicts_with=["mortgage_interest"] if item.deduction_type == "housing_rent" else ["housing_rent"] if item.deduction_type == "mortgage_interest" else [],
                source="manual",
            )
        )

    order = {
        "housing_rent": 0,
        "mortgage_interest": 1,
        "child_education": 2,
        "infant_care": 3,
        "personal_pension": 4,
        "continuing_education": 5,
        "serious_illness": 6,
    }
    return sorted(items, key=lambda item: (order.get(item.deduction_type, 99), item.member_name, item.start_month))


def _tax_timeline_month_offset(start_month: date, month_text: str) -> tuple[int, int, int] | None:
    parsed = _parse_year_month(month_text)
    if not parsed:
        return None
    target = date(parsed[0], parsed[1], 1)
    return _months_between_months(start_month, target), parsed[0], parsed[1]


def build_tax_strategy_timeline(
    household: HouseholdData,
    rules: RulePackData,
    strategy_items: list[TaxStrategyItem],
    *,
    base_date: date | None = None,
    horizon_months: int = 840,
    tax_events: list[TaxEventPoint] | None = None,
) -> list[TaxStrategyTimelinePoint]:
    current = base_date or date.today()
    current_month = date(current.year, current.month, 1)
    end_year, end_month = _month_after(current_month, max(0, horizon_months))
    end_date = date(end_year, end_month, 1)
    points: list[TaxStrategyTimelinePoint] = []

    def add_point(
        *,
        month_text: str,
        category: str,
        title: str,
        action: str,
        member_name: str = "",
        deduction_type: str | None = None,
        status: str = "available",
        amount: float = 0.0,
        estimated_tax_saving: float = 0.0,
        detail: str = "",
        source: str = "backend_auto",
    ) -> None:
        month_info = _tax_timeline_month_offset(current_month, month_text)
        if month_info is None:
            return
        offset, year, month = month_info
        if offset < 0 or date(year, month, 1) > end_date:
            return
        points.append(
            TaxStrategyTimelinePoint(
                month=offset,
                year=year,
                month_of_year=month,
                category=category,  # type: ignore[arg-type]
                title=title,
                action=action,
                member_name=member_name,
                deduction_type=deduction_type,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                amount=round(amount, 2),
                estimated_tax_saving=round(estimated_tax_saving, 2),
                detail=_tax_source_labeled_detail(source, category, detail),
                source=source,  # type: ignore[arg-type]
            )
        )

    for item in strategy_items:
        start_month = item.start_month or f"{current_month.year:04d}-{current_month.month:02d}"
        if item.status == "not_applicable":
            continue
        if item.deduction_type == "personal_pension":
            if item.status == "conflict":
                add_point(
                    month_text=start_month,
                    category="personal_pension",
                    title=item.title,
                    action="暂不开户或暂停新增缴费",
                    member_name=item.member_name,
                    deduction_type=item.deduction_type,
                    status=item.status,
                    amount=0,
                    estimated_tax_saving=0,
                    detail=item.recommended_action or item.reason,
                    source=item.source,
                )
                continue
            add_point(
                month_text=start_month,
                category="personal_pension",
                title=item.title,
                action=(
                    "开启个人养老金税前扣除策略"
                    if item.status == "auto_enabled"
                    else "按最优月份计划开户并开始缴费"
                    if item.status == "available"
                    else "按手动设置执行个人养老金策略"
                ),
                member_name=item.member_name,
                deduction_type=item.deduction_type,
                status=item.status,
                amount=item.cash_contribution,
                estimated_tax_saving=item.estimated_tax_saving,
                detail=(
                    f"年度缴费约 {item.cash_contribution:.0f} 元，进入个人养老金账户；"
                    f"年度可扣除约 {item.annual_amount:.0f} 元，估算节税 {item.estimated_tax_saving:.0f} 元。"
                    "这笔钱会作为现金转出进入个人养老金账户，并在可视化账户曲线中继续产生收益。"
                ),
                source=item.source,
            )
            continue
        if item.source == "manual":
            add_point(
                month_text=start_month,
                category="manual_override",
                title=item.title,
                action="启用手动专项附加扣除覆盖",
                member_name=item.member_name,
                deduction_type=item.deduction_type,
                status=item.status,
                amount=item.annual_amount or item.monthly_amount * 12,
                estimated_tax_saving=item.estimated_tax_saving,
                detail=item.reason or "该扣除项由用户手动维护，后端按生效区间纳入税务测算。",
                source=item.source,
            )
            continue
        if item.deduction_type in {"housing_rent", "mortgage_interest"}:
            action = "采用住房租金扣除" if item.deduction_type == "housing_rent" else "切换到首套房贷利息扣除"
            category = "deduction_switch" if item.deduction_type == "mortgage_interest" else "deduction_assignment"
        else:
            action = "指定专项附加扣除申报成员" if item.member_name else "等待指定最优申报成员"
            category = "deduction_assignment"
        add_point(
            month_text=start_month,
            category=category,
            title=item.title,
            action=action,
            member_name=item.member_name,
            deduction_type=item.deduction_type,
            status=item.status,
            amount=item.annual_amount or item.monthly_amount * 12,
            estimated_tax_saving=item.estimated_tax_saving,
            detail=item.reason,
            source=item.source,
        )

    for event in tax_events or []:
        if event.event_type != "bonus_payout":
            continue
        add_point(
            month_text=f"{event.year:04d}-{event.month_of_year:02d}",
            category="bonus_tax",
            title=event.title,
            action="按收入阶段奖金规则计税",
            member_name=event.member_name,
            status="auto_enabled",
            amount=event.amount or 0.0,
            detail=f"{event.detail} 后端会按收入阶段设置选择单独计税、并入综合所得或择优计税。",
            source="event",
        )

    investment_estimate = investment_tax_estimate(household)
    effective_tax_rate = investment_estimate.effective_rate
    if effective_tax_rate > 0:
        plan_name = getattr(household, "investment_plan_name", "") or "当前理财策略"
        add_point(
            month_text=f"{current_month.year:04d}-{current_month.month:02d}",
            category="investment_tax",
            title="理财收益税后口径",
            action="将理财收益按税后收益纳入账户推演",
            status="auto_enabled",
            amount=effective_tax_rate,
            detail=(
                f"{plan_name} 的投资收益会先按约 {effective_tax_rate:.2%} 的有效税率扣减后再进入投资账户。"
                f"{investment_estimate.detail}"
                "这不是工资薪金个税，也不会进入月度生活支出；它直接影响理财计划、流动资产曲线和买房买车时点。"
            ),
            source=investment_estimate.source,
        )
    else:
        add_point(
            month_text=f"{current_month.year:04d}-{current_month.month:02d}",
            category="investment_tax",
            title="理财收益税后口径",
            action="当前按无额外理财收益税推演",
            status="available",
            amount=0.0,
            detail=(
                f"{investment_estimate.detail}"
                "如果未来手动配置分红、普通债券利息、境外资产等税负，或接入具体产品持仓数据，后端会自动更新投资账户曲线和策略比较。"
            ),
            source=investment_estimate.source,
        )

    annual_settlement_month = get_policy(rules).tax_benefit_policy().annual_tax_settlement_month
    for year in range(current_month.year + 1, min(end_date.year + 1, current_month.year + 6)):
        add_point(
            month_text=f"{year:04d}-{annual_settlement_month:02d}",
            category="annual_settlement",
            title=f"{year - 1}年度个税汇算",
            action="汇总年度专项扣除和税务策略",
            status="auto_enabled",
            detail="继续教育、大病医疗等年度汇算型扣除会在年度口径体现；工资、奖金、专项附加扣除和个人养老金会按成员分别汇总。",
            source="backend_auto",
        )

    category_order = {
        "investment_tax": 0,
        "deduction_assignment": 1,
        "deduction_switch": 2,
        "personal_pension": 3,
        "bonus_tax": 4,
        "annual_settlement": 5,
        "manual_override": 6,
    }
    return sorted(points, key=lambda point: (point.month, category_order.get(point.category, 99), point.member_name, point.title))
