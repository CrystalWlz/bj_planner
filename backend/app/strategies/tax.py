from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Literal

from ..domain.children import child_plan_birth_month_for_strategy as _child_plan_birth_month_for_strategy
from ..domain.career import household_with_pension_income_stages as _household_with_pension_income_stages
from ..domain.investments import investment_tax_estimate
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
from ..schemas import (
    HouseholdData,
    IncomeMember,
    RulePackData,
    ScenarioData,
    TaxEventPoint,
    TaxStrategyItem,
    TaxStrategyTimelinePoint,
)


PersonalPensionTaxSavingEstimator = Callable[[HouseholdData, IncomeMember, RulePackData, int], float]


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
    personal_pension_tax_saving_estimator: PersonalPensionTaxSavingEstimator,
) -> list[TaxStrategyItem]:
    current = base_date or date.today()
    current_month = date(current.year, current.month, 1)
    params = rules.params
    member_name = household.members[0].name if household.members else ""
    rent_monthly = float(params.get("beijing_housing_rent_deduction_monthly", 1500))
    mortgage_monthly = float(params.get("first_home_mortgage_interest_deduction_monthly", 1000))
    max_mortgage_months = int(params.get("first_home_mortgage_interest_max_months", 240))
    rent_window = _active_rent_deduction_window(household, base_date=current_month, horizon_months=horizon_months)

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

    child_monthly = float(params.get("child_education_deduction_monthly", 2000))
    infant_monthly = float(params.get("infant_care_deduction_monthly", 2000))
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

    for member in household.members:
        if bool(getattr(member, "personal_pension_account_enabled", False)):
            open_mode = str(getattr(member, "personal_pension_open_mode", "auto_tax_optimal") or "auto_tax_optimal")
            contribution_mode = str(getattr(member, "personal_pension_contribution_mode", "auto_tax_optimal") or "auto_tax_optimal")
            annual_cap = float(params.get("personal_pension_deduction_annual_cap", 12000))
            withdrawal_tax_rate = float(params.get("personal_pension_withdrawal_tax_rate", 0.03))
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
            if open_mode == "none" or contribution_mode == "none":
                status = "not_applicable"
            annual_cash_contribution = 0.0
            if status != "not_applicable":
                if contribution_mode == "fixed_monthly":
                    annual_cash_contribution = max(0.0, float(getattr(member, "personal_pension_monthly_contribution", 0.0))) * 12
                elif contribution_mode == "fixed_annual":
                    annual_cash_contribution = max(0.0, float(getattr(member, "personal_pension_annual_contribution_target", 0.0)))
                else:
                    annual_cash_contribution = annual_cap if recommended_start or strategy_start_month else 0.0
            deductible_amount = min(max(0.0, annual_cash_contribution), max(0.0, annual_cap))
            strategy_start_tuple = _parse_year_month(strategy_start_month)
            tax_saving_year = strategy_start_tuple[0] if strategy_start_tuple else current.year
            estimated_tax_saving = (
                personal_pension_tax_saving_estimator(household, member, rules, tax_saving_year)
                if deductible_amount > 0
                else 0.0
            )
            account_return_rate = float(getattr(member, "personal_pension_annual_return", 0.025) or 0.0)
            reason = (
                f"税务策略建议在 {strategy_start_month or '首次有应税工作收入时'} 开户并开始缴存，按年度 {annual_cap:.0f} 元扣除上限测算；"
                f"当前策略年度现金缴费约 {annual_cash_contribution:.0f} 元，可扣除约 {deductible_amount:.0f} 元，"
                f"按当前年度估算节税约 {estimated_tax_saving:.0f} 元。个人养老金与基本养老保险个人账户不同，缴费环节税前扣除，投资环节暂不征税，领取环节按 {withdrawal_tax_rate:.1%} 税率估算。"
                if status == "auto_enabled"
                else (
                    f"个人养老金开户或缴存由用户手动控制；后端按手动月份、缴存方式和年度扣除上限测算。"
                    f"当前年度现金缴费约 {annual_cash_contribution:.0f} 元，可扣除约 {deductible_amount:.0f} 元，估算节税约 {estimated_tax_saving:.0f} 元；领取环节按 {withdrawal_tax_rate:.1%} 税率估算。"
                    if status == "manual_enabled"
                    else "该成员没有启用个人养老金缴费策略，因此不产生个人养老金税前扣除、现金转出和账户收益。"
                )
            )
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
                    withdrawal_tax_rate=round(withdrawal_tax_rate, 6),
                    start_month=strategy_start_month,
                    end_month=getattr(member, "personal_pension_contribution_end_month", "") or None,
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
                detail=detail,
                source=source,  # type: ignore[arg-type]
            )
        )

    for item in strategy_items:
        start_month = item.start_month or f"{current_month.year:04d}-{current_month.month:02d}"
        if item.status == "not_applicable":
            continue
        if item.deduction_type == "personal_pension":
            add_point(
                month_text=start_month,
                category="personal_pension",
                title=item.title,
                action="开启个人养老金税前扣除策略" if item.status == "auto_enabled" else "按手动设置执行个人养老金策略",
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

    annual_settlement_month = int(rules.params.get("annual_tax_settlement_month", 3) or 3)
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
