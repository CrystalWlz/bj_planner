from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .domain.career import household_with_pension_income_stages as _household_with_pension_income_stages
from .domain.time import (
    month_after as _month_after,
    month_distance as _month_distance,
    parse_iso_date as _parse_iso_date,
    parse_year_month as _parse_year_month,
)
from .domain.tax import (
    DEFAULT_BONUS_BRACKETS,
    DEFAULT_COMPREHENSIVE_BRACKETS,
    active_months_in_period as _active_months_in_period,
    annual_bonus_separate_tax_available as _annual_bonus_separate_tax_available,
    beijing_contributions as _beijing_contributions,
    bonus_tax as _bonus_tax,
    income_stage_for_month as _income_stage_for_month,
    progressive_tax as _progressive_tax,
    stage_bonus_cash_amount as _stage_bonus_cash_amount,
    stage_bonus_payout_amount as _stage_bonus_payout_amount,
    stage_monthly_spread_bonus_amount as _stage_monthly_spread_bonus_amount,
    stage_selected_bonus_method as _stage_selected_bonus_method,
)
from .schemas import (
    BonusTaxMethod,
    ElderlyDependentData,
    HouseholdData,
    IncomeMember,
    RulePackData,
    ScenarioData,
    TaxEventPoint,
    TaxMemberMonthlyPoint,
    TaxMemberSummary,
    TaxMonthlyPoint,
    TaxStrategyItem,
    TaxStrategyTimelinePoint,
    TaxYearSummary,
)
from .strategies.tax import (
    build_tax_events as _strategy_build_tax_events,
    build_tax_strategy_items as _strategy_build_tax_strategy_items,
    build_tax_strategy_timeline as _strategy_build_tax_strategy_timeline,
)


@dataclass(frozen=True)
class MonthlyIncomeProfile:
    gross_income: float
    net_income: float
    personal_social: float
    personal_housing_fund: float
    employer_social: float
    employer_housing_fund: float
    income_tax: float
    monthly_pf_deposit: float
    non_taxable_income: float = 0.0
    pension_income: float = 0.0
    personal_pension_contribution: float = 0.0
    other_cash_outflow: float = 0.0

    @property
    def extra_cash_expense(self) -> float:
        return self.other_cash_outflow


@dataclass(frozen=True)
class MemberSalaryTaxState:
    previous_tax: float
    current_tax: float
    cumulative_taxable_income: float


def _elderly_dependent_start_month(dependent: ElderlyDependentData) -> tuple[int, int] | None:
    birth_month = _parse_year_month(dependent.birth_month)
    if birth_month is None:
        return None
    return birth_month[0] + 60, birth_month[1]


def _elderly_care_deduction_for_member_at(
    household: HouseholdData | None,
    member_name: str,
    target_month: date,
) -> float:
    if household is None:
        return 0.0
    target = (target_month.year, target_month.month)
    deduction = 0.0
    for dependent in household.elderly_dependents:
        if dependent.member_name != member_name:
            continue
        start_month = _elderly_dependent_start_month(dependent)
        if start_month is None or _month_distance(start_month, target) < 0:
            continue
        if dependent.is_only_child:
            deduction += 3000.0
        else:
            deduction += min(max(0.0, dependent.shared_monthly_deduction), 1500.0)
    return min(deduction, 3000.0)


def _deduction_item_active_in_month(item_start: str, item_end: str | None, target_month: date) -> bool:
    start = _parse_year_month(item_start)
    if start is None:
        return False
    target = (target_month.year, target_month.month)
    if _month_distance(start, target) < 0:
        return False
    end = _parse_year_month(item_end)
    return end is None or _month_distance(target, end) >= 0


def _child_plan_birth_month(child: object) -> tuple[int, int] | None:
    birth_month = _parse_year_month(getattr(child, "birth_month", ""))
    if birth_month is not None:
        return birth_month
    planned_start = _parse_year_month(getattr(child, "planned_birth_start_month", ""))
    planned_end = _parse_year_month(getattr(child, "planned_birth_end_month", ""))
    planned_single = _parse_year_month(getattr(child, "planned_birth_month", ""))
    if planned_start is not None and planned_end is not None:
        return planned_start if _month_distance(planned_start, planned_end) >= 0 else planned_end
    if planned_start is not None:
        return planned_start
    if planned_end is not None:
        return planned_end
    if planned_single is not None:
        return planned_single
    return _parse_year_month(getattr(child, "planned_birth_month", ""))


def _child_age_months(child: object, target_month: date) -> int | None:
    birth_month = _child_plan_birth_month(child)
    if birth_month is None:
        return None
    return _month_distance(birth_month, (target_month.year, target_month.month))


def _personal_pension_deduction_for_member_at(
    household: HouseholdData | None,
    member_name: str,
    target_month: date,
    rules: RulePackData,
) -> float:
    if household is None:
        return 0.0
    cap = max(0.0, float(rules.params.get("personal_pension_deduction_annual_cap", 12000)))
    member = next((item for item in household.members if item.name == member_name), None)
    if member is None or not bool(getattr(member, "personal_pension_account_enabled", False)):
        return 0.0
    open_mode = str(getattr(member, "personal_pension_open_mode", "auto_tax_optimal") or "auto_tax_optimal")
    if open_mode == "none":
        return 0.0
    open_month = _parse_year_month(getattr(member, "personal_pension_account_open_month", ""))
    target = (target_month.year, target_month.month)
    if open_mode == "manual" and open_month is not None and _month_distance(open_month, target) < 0:
        return 0.0
    mode = str(getattr(member, "personal_pension_contribution_mode", "none") or "none")
    if mode == "none":
        return 0.0
    start = _parse_year_month(getattr(member, "personal_pension_contribution_start_month", ""))
    end = _parse_year_month(getattr(member, "personal_pension_contribution_end_month", "") or "")
    if start is not None and _month_distance(start, target) < 0:
        return 0.0
    if end is not None and _month_distance(target, end) < 0:
        return 0.0
    if mode == "auto_tax_optimal":
        stage = _income_stage_for_month(member, target_month.year, target_month.month)
        if stage is None or stage.stage_kind in {"pension", "unemployment"}:
            return 0.0
        taxable_cash_income = (
            stage.monthly_salary_gross
            + stage.monthly_freelance_income
            + stage.other_annual_taxable_income / 12
            + _stage_bonus_cash_amount(stage, target_month.year, target_month.month)
        )
        if taxable_cash_income <= 0:
            return 0.0
        annual_target = cap
    elif mode == "fixed_monthly":
        annual_target = max(0.0, float(getattr(member, "personal_pension_monthly_contribution", 0.0))) * 12
    else:
        annual_target = max(0.0, float(getattr(member, "personal_pension_annual_contribution_target", 0.0)))
    return min(annual_target, cap) / 12 if cap else annual_target / 12


def _personal_pension_cash_contribution_for_member_at(
    member: IncomeMember,
    target_month: date,
    rules: RulePackData,
) -> float:
    if not bool(getattr(member, "personal_pension_account_enabled", False)):
        return 0.0
    open_mode = str(getattr(member, "personal_pension_open_mode", "auto_tax_optimal") or "auto_tax_optimal")
    if open_mode == "none":
        return 0.0
    open_month = _parse_year_month(getattr(member, "personal_pension_account_open_month", ""))
    target = (target_month.year, target_month.month)
    if open_mode == "manual" and open_month is not None and _month_distance(open_month, target) < 0:
        return 0.0
    mode = str(getattr(member, "personal_pension_contribution_mode", "none") or "none")
    if mode == "none":
        return 0.0
    start = _parse_year_month(getattr(member, "personal_pension_contribution_start_month", ""))
    end = _parse_year_month(getattr(member, "personal_pension_contribution_end_month", "") or "")
    if start is not None and _month_distance(start, target) < 0:
        return 0.0
    if end is not None and _month_distance(target, end) < 0:
        return 0.0
    cap = max(0.0, float(rules.params.get("personal_pension_deduction_annual_cap", 12000)))
    if mode == "auto_tax_optimal":
        stage = _income_stage_for_month(member, target_month.year, target_month.month)
        if stage is None or stage.stage_kind in {"pension", "unemployment"}:
            return 0.0
        taxable_cash_income = (
            stage.monthly_salary_gross
            + stage.monthly_freelance_income
            + stage.other_annual_taxable_income / 12
            + _stage_bonus_cash_amount(stage, target_month.year, target_month.month)
        )
        if taxable_cash_income <= 0:
            return 0.0
        return cap / 12 if cap else 0.0
    if mode == "fixed_monthly":
        return max(0.0, float(getattr(member, "personal_pension_monthly_contribution", 0.0)))
    if mode == "fixed_annual":
        contribution_month = max(1, min(12, int(getattr(member, "personal_pension_contribution_month", 12) or 12)))
        if target_month.month != contribution_month:
            return 0.0
        return max(0.0, float(getattr(member, "personal_pension_annual_contribution_target", 0.0)))
    return 0.0


def _weighted_personal_pension_monthly_return(
    members: Sequence[IncomeMember],
    current_balance: float,
) -> float:
    enabled_members = [
        member
        for member in members
        if bool(getattr(member, "personal_pension_account_enabled", False))
    ]
    if not enabled_members:
        return 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    for member in enabled_members:
        balance = max(0.0, float(getattr(member, "personal_pension_account_balance", 0.0)))
        weight = balance if balance > 0 else 1.0
        annual_return = float(getattr(member, "personal_pension_annual_return", 0.025) or 0.0)
        weighted_sum += annual_return * weight
        weight_total += weight
    annual = weighted_sum / weight_total if weight_total > 0 else 0.0
    return (1 + annual) ** (1 / 12) - 1 if annual > -1 else 0.0


def _auto_child_special_deduction_for_member_at(
    household: HouseholdData | None,
    member_name: str,
    target_month: date,
    rules: RulePackData,
) -> float:
    if household is None:
        return 0.0
    infant_monthly = float(rules.params.get("infant_care_deduction_monthly", 2000))
    education_monthly = float(rules.params.get("child_education_deduction_monthly", 2000))
    total = 0.0
    for child in household.child_plans:
        if not child.enabled or child.tax_deduction_owner != member_name:
            continue
        age_months = _child_age_months(child, target_month)
        if age_months is not None and 0 <= age_months < 36:
            total += infant_monthly
            continue
        education_start = _parse_year_month(child.education_start_month)
        if education_start is not None and _month_distance(education_start, (target_month.year, target_month.month)) >= 0:
            total += education_monthly
    return total


def _configured_special_deduction_for_member_at(
    household: HouseholdData | None,
    member_name: str,
    target_month: date,
    rules: RulePackData,
    *,
    include_annual_settlement: bool = False,
) -> float:
    if household is None:
        return 0.0
    params = rules.params
    monthly_total = 0.0
    rent_total = 0.0
    mortgage_total = 0.0
    annual_total = 0.0
    for item in household.special_deductions:
        if not item.enabled or item.member_name != member_name:
            continue
        if not _deduction_item_active_in_month(item.start_month, item.end_month, target_month):
            continue
        if item.settlement_mode == "annual_settlement":
            if include_annual_settlement:
                if item.deduction_type == "serious_illness":
                    threshold = float(params.get("serious_illness_medical_threshold", 15000))
                    cap = float(params.get("serious_illness_medical_cap", 80000))
                    annual_total += min(cap, max(0.0, item.annual_amount - threshold))
                else:
                    annual_total += max(0.0, item.annual_amount)
            continue
        if item.deduction_type == "housing_rent":
            rent_total += item.monthly_amount or float(params.get("beijing_housing_rent_deduction_monthly", 1500))
        elif item.deduction_type == "mortgage_interest":
            used = max(0, item.claimed_months_used)
            elapsed = _month_distance(_parse_year_month(item.start_month) or (target_month.year, target_month.month), (target_month.year, target_month.month))
            max_months = int(params.get("first_home_mortgage_interest_max_months", 240))
            if item.is_first_home_loan and used + elapsed < max_months:
                mortgage_total += item.monthly_amount or float(params.get("first_home_mortgage_interest_deduction_monthly", 1000))
        elif item.deduction_type == "child_education":
            monthly_total += item.monthly_amount or float(params.get("child_education_deduction_monthly", 2000))
        elif item.deduction_type == "infant_care":
            monthly_total += item.monthly_amount or float(params.get("infant_care_deduction_monthly", 2000))
        elif item.deduction_type == "personal_pension":
            monthly_total += min(item.annual_amount or item.monthly_amount * 12, float(params.get("personal_pension_deduction_annual_cap", 12000))) / 12
        else:
            monthly_total += max(0.0, item.monthly_amount)
    if bool(params.get("rent_and_mortgage_deduction_mutually_exclusive", True)):
        monthly_total += max(rent_total, mortgage_total)
    else:
        monthly_total += rent_total + mortgage_total
    return monthly_total + (annual_total if include_annual_settlement and target_month.month == 12 else 0.0)


def _auto_housing_special_deduction_for_member_at(
    household: HouseholdData | None,
    member_name: str,
    target_month: date,
    rules: RulePackData,
) -> float:
    if household is None or not household.members or household.members[0].name != member_name:
        return 0.0
    for item in household.special_deductions:
        if (
            item.enabled
            and item.member_name == member_name
            and item.deduction_type in {"housing_rent", "mortgage_interest"}
            and _deduction_item_active_in_month(item.start_month, item.end_month, target_month)
        ):
            return 0.0
    for stage in household.rent_expense_stages:
        if stage.rent_amount <= 0:
            continue
        start = _parse_iso_date(stage.start_month, date(1900, 1, 1))
        end = _parse_iso_date(stage.end_month, date(9999, 12, 31)) if stage.end_month else date(9999, 12, 31)
        if start <= target_month <= end:
            return float(rules.params.get("beijing_housing_rent_deduction_monthly", 1500))
    return 0.0


def _structured_special_deduction_for_member_at(
    household: HouseholdData | None,
    member_name: str,
    target_month: date,
    rules: RulePackData,
    *,
    include_annual_settlement: bool = False,
) -> float:
    return (
        _elderly_care_deduction_for_member_at(household, member_name, target_month)
        + _auto_child_special_deduction_for_member_at(household, member_name, target_month, rules)
        + _auto_housing_special_deduction_for_member_at(household, member_name, target_month, rules)
        + _personal_pension_deduction_for_member_at(household, member_name, target_month, rules)
        + _configured_special_deduction_for_member_at(
            household,
            member_name,
            target_month,
            rules,
            include_annual_settlement=include_annual_settlement,
        )
    )


def _member_cumulative_salary_tax(
    member: IncomeMember,
    rules: RulePackData,
    year: int,
    through_month: int,
    household: HouseholdData | None = None,
) -> float:
    return _member_cumulative_salary_tax_pair(member, rules, year, through_month, household)[1]


def _member_cumulative_salary_tax_pair(
    member: IncomeMember,
    rules: RulePackData,
    year: int,
    through_month: int,
    household: HouseholdData | None = None,
) -> tuple[float, float]:
    state = _member_cumulative_salary_tax_state(member, rules, year, through_month, household)
    return state.previous_tax, state.current_tax


def _member_cumulative_salary_tax_state(
    member: IncomeMember,
    rules: RulePackData,
    year: int,
    through_month: int,
    household: HouseholdData | None = None,
) -> MemberSalaryTaxState:
    if through_month <= 0:
        return MemberSalaryTaxState(0.0, 0.0, 0.0)

    params = rules.params
    annual_brackets = list(params.get("comprehensive_tax_brackets") or DEFAULT_COMPREHENSIVE_BRACKETS)
    monthly_standard_deduction = float(params.get("personal_standard_deduction_annual", 60000)) / 12
    active_months = 0
    cumulative_income = 0.0
    cumulative_social_and_fund = 0.0
    cumulative_special_deduction = 0.0
    cumulative_other_deduction = 0.0
    previous_tax = 0.0
    current_tax = 0.0
    current_taxable_income = 0.0
    selected_method_cache: dict[int, BonusTaxMethod] = {}

    def cumulative_tax_value() -> tuple[float, float]:
        taxable = max(
            0.0,
            cumulative_income
            - monthly_standard_deduction * active_months
            - cumulative_social_and_fund
            - cumulative_special_deduction
            - cumulative_other_deduction,
        )
        return taxable, _progressive_tax(taxable, annual_brackets)

    for month in range(1, through_month + 1):
        target_date = date(year, month, 1)
        stage = _income_stage_for_month(member, year, month)
        if stage is not None:
            personal_social, personal_housing_fund, _, _ = _beijing_contributions(stage, rules)
            stage_key = id(stage)
            selected_bonus_method = selected_method_cache.get(stage_key)
            if selected_bonus_method is None:
                selected_bonus_method = _stage_selected_bonus_method(stage, rules, year)
                selected_method_cache[stage_key] = selected_bonus_method
            active_months += 1
            cumulative_income += stage.monthly_salary_gross
            cumulative_income += stage.monthly_freelance_income
            cumulative_income += stage.other_annual_taxable_income / 12
            cumulative_income += _stage_monthly_spread_bonus_amount(stage, year, month)
            if selected_bonus_method == "merged":
                cumulative_income += _stage_bonus_payout_amount(stage, year, month)
            cumulative_social_and_fund += personal_social + personal_housing_fund
            cumulative_special_deduction += stage.monthly_special_additional_deduction
            cumulative_special_deduction += _structured_special_deduction_for_member_at(
                household,
                member.name,
                target_date,
                rules,
            )
            cumulative_other_deduction += stage.other_annual_deductions / 12
        current_taxable_income, current_tax = cumulative_tax_value()
        if month == through_month - 1:
            previous_tax = current_tax

    return MemberSalaryTaxState(
        previous_tax=previous_tax,
        current_tax=current_tax,
        cumulative_taxable_income=current_taxable_income,
    )


def _member_monthly_income_profile(
    member: IncomeMember,
    rules: RulePackData,
    target_month: date,
    household: HouseholdData | None = None,
) -> MonthlyIncomeProfile:
    stage = _income_stage_for_month(member, target_month.year, target_month.month)
    if stage is None:
        return MonthlyIncomeProfile(0, 0, 0, 0, 0, 0, 0, 0)

    personal_social, personal_housing_fund, employer_social, employer_housing_fund = _beijing_contributions(stage, rules)
    selected_bonus_method = _stage_selected_bonus_method(stage, rules, target_month.year)
    previous_cumulative_tax, cumulative_tax = _member_cumulative_salary_tax_pair(
        member,
        rules,
        target_month.year,
        target_month.month,
        household,
    )
    salary_tax = max(0.0, cumulative_tax - previous_cumulative_tax)
    lump_sum_bonus_payout = _stage_bonus_payout_amount(stage, target_month.year, target_month.month)
    monthly_spread_bonus = _stage_monthly_spread_bonus_amount(stage, target_month.year, target_month.month)
    bonus_payout = lump_sum_bonus_payout + monthly_spread_bonus
    bonus_tax_due = 0.0
    if selected_bonus_method == "separate":
        bonus_brackets = list(rules.params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
        bonus_tax_due = _bonus_tax(lump_sum_bonus_payout, bonus_brackets) if lump_sum_bonus_payout > 0 else 0.0

    taxable_cash_income = (
        stage.monthly_salary_gross
        + stage.monthly_freelance_income
        + bonus_payout
        + stage.other_annual_taxable_income / 12
    )
    pension_income = stage.monthly_non_taxable_income if stage.stage_kind == "pension" else 0.0
    gross_income = taxable_cash_income + stage.monthly_non_taxable_income
    income_tax = salary_tax + bonus_tax_due
    personal_pension_contribution = _personal_pension_cash_contribution_for_member_at(member, target_month, rules)
    net_income = gross_income - personal_social - personal_housing_fund - income_tax
    return MonthlyIncomeProfile(
        gross_income=round(gross_income, 2),
        net_income=round(net_income, 2),
        personal_social=round(personal_social, 2),
        personal_housing_fund=round(personal_housing_fund, 2),
        employer_social=round(employer_social, 2),
        employer_housing_fund=round(employer_housing_fund, 2),
        income_tax=round(income_tax, 2),
        monthly_pf_deposit=round(personal_housing_fund + employer_housing_fund, 2),
        non_taxable_income=round(stage.monthly_non_taxable_income, 2),
        pension_income=round(pension_income, 2),
        personal_pension_contribution=round(personal_pension_contribution, 2),
        other_cash_outflow=0.0,
    )


def member_monthly_income_profiles_at(
    household: HouseholdData,
    rules: RulePackData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> list[tuple[int, str, MonthlyIncomeProfile]]:
    household = _household_with_pension_income_stages(household, rules, as_of=as_of)
    current = as_of or date.today()
    year, month = _month_after(current, max(0, months_from_now))
    target_month = date(year, month, 1)
    return [
        (index, member.name, _member_monthly_income_profile(member, rules, target_month, household))
        for index, member in enumerate(household.members)
    ]


def household_monthly_income_profile_at(
    household: HouseholdData,
    rules: RulePackData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> MonthlyIncomeProfile:
    household = _household_with_pension_income_stages(household, rules, as_of=as_of)
    current = as_of or date.today()
    if not household.members:
        return MonthlyIncomeProfile(
            gross_income=round(household.monthly_income, 2),
            net_income=round(household.monthly_income, 2),
            personal_social=0,
            personal_housing_fund=0,
            employer_social=0,
            employer_housing_fund=0,
            income_tax=0,
            monthly_pf_deposit=0,
        )

    member_profiles = [
        profile for _, _, profile in member_monthly_income_profiles_at(household, rules, months_from_now, as_of=current)
    ]
    return MonthlyIncomeProfile(
        gross_income=round(sum(item.gross_income for item in member_profiles), 2),
        net_income=round(sum(item.net_income for item in member_profiles), 2),
        personal_social=round(sum(item.personal_social for item in member_profiles), 2),
        personal_housing_fund=round(sum(item.personal_housing_fund for item in member_profiles), 2),
        employer_social=round(sum(item.employer_social for item in member_profiles), 2),
        employer_housing_fund=round(sum(item.employer_housing_fund for item in member_profiles), 2),
        income_tax=round(sum(item.income_tax for item in member_profiles), 2),
        monthly_pf_deposit=round(sum(item.monthly_pf_deposit for item in member_profiles), 2),
        non_taxable_income=round(sum(item.non_taxable_income for item in member_profiles), 2),
        pension_income=round(sum(item.pension_income for item in member_profiles), 2),
        personal_pension_contribution=round(sum(item.personal_pension_contribution for item in member_profiles), 2),
        other_cash_outflow=round(sum(item.other_cash_outflow for item in member_profiles), 2),
    )


def _member_tax_summary(
    member: IncomeMember,
    rules: RulePackData,
    household: HouseholdData | None = None,
) -> TaxMemberSummary:
    params = rules.params
    annual_brackets = list(params.get("comprehensive_tax_brackets") or DEFAULT_COMPREHENSIVE_BRACKETS)
    bonus_brackets = list(params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
    standard_deduction = float(params.get("personal_standard_deduction_annual", 60000))
    projection_year = int(params.get("_income_projection_year", 2027))
    stages = member.income_stages or []

    active_months = 0
    salary_annual = 0.0
    bonus_annual = 0.0
    other_taxable_income = 0.0
    other_deductions = 0.0
    social_and_fund = 0.0
    employer_social_total = 0.0
    employer_housing_fund_total = 0.0
    personal_social_total = 0.0
    personal_housing_fund_total = 0.0
    special_deductions = 0.0
    non_taxable_income = 0.0
    extra_cash_expense = 0.0

    for stage in stages:
        stage_months = _active_months_in_period(stage.start_date, stage.end_date, projection_year)
        if stage_months <= 0:
            continue
        personal_social, personal_housing_fund, employer_social, employer_housing_fund = _beijing_contributions(
            stage,
            rules,
        )
        stage_ratio = stage_months / 12
        active_months += stage_months
        salary_annual += stage.monthly_salary_gross * stage_months
        salary_annual += stage.monthly_freelance_income * stage_months
        stage_bonus_annual = sum(
            _stage_bonus_cash_amount(stage, projection_year, month)
            for month in range(1, 13)
        )
        if stage.annual_bonus_payout_mode == "monthly_spread":
            salary_annual += stage_bonus_annual
        else:
            bonus_annual += stage_bonus_annual
        non_taxable_income += stage.monthly_non_taxable_income * stage_months
        other_taxable_income += stage.other_annual_taxable_income * stage_ratio
        other_deductions += stage.other_annual_deductions * stage_ratio
        personal_social_total += personal_social * stage_months
        personal_housing_fund_total += personal_housing_fund * stage_months
        employer_social_total += employer_social * stage_months
        employer_housing_fund_total += employer_housing_fund * stage_months
        social_and_fund += (personal_social + personal_housing_fund) * stage_months
        special_deductions += stage.monthly_special_additional_deduction * stage_months
        for month in range(1, 13):
            if _income_stage_for_month(member, projection_year, month) != stage:
                continue
            special_deductions += _structured_special_deduction_for_member_at(
                household,
                member.name,
                date(projection_year, month, 1),
                rules,
                include_annual_settlement=True,
            )
            extra_cash_expense += _personal_pension_cash_contribution_for_member_at(
                member,
                date(projection_year, month, 1),
                rules,
            )

    common_deductions = standard_deduction + social_and_fund + special_deductions + other_deductions

    salary_taxable = max(0.0, salary_annual + other_taxable_income - common_deductions)
    separate_salary_tax = _progressive_tax(salary_taxable, annual_brackets)
    separate_available = _annual_bonus_separate_tax_available(rules, projection_year)
    separate_bonus_tax = _bonus_tax(bonus_annual, bonus_brackets) if separate_available else 0.0
    separate_total_tax = separate_salary_tax + separate_bonus_tax if separate_available else float("inf")

    merged_taxable = max(
        0.0,
        salary_annual
        + bonus_annual
        + other_taxable_income
        - common_deductions,
    )
    merged_total_tax = _progressive_tax(merged_taxable, annual_brackets)

    stage_methods = {
        _stage_selected_bonus_method(stage, rules, projection_year)
        for stage in stages
        if _active_months_in_period(stage.start_date, stage.end_date, projection_year) > 0
    }
    method = next(iter(stage_methods)) if len(stage_methods) == 1 else member.bonus_tax_method
    if not separate_available and method == "separate":
        method = "merged"
    if method == "merged":
        selected_method: BonusTaxMethod = "merged"
        taxable_income = merged_taxable
        salary_tax = merged_total_tax
        bonus_tax = 0.0
        total_tax = merged_total_tax
    elif method == "separate":
        selected_method = "separate"
        taxable_income = salary_taxable
        salary_tax = separate_salary_tax
        bonus_tax = separate_bonus_tax
        total_tax = separate_total_tax
    elif merged_total_tax < separate_total_tax:
        selected_method = "merged"
        taxable_income = merged_taxable
        salary_tax = merged_total_tax
        bonus_tax = 0.0
        total_tax = merged_total_tax
    else:
        selected_method = "separate"
        taxable_income = salary_taxable
        salary_tax = separate_salary_tax
        bonus_tax = separate_bonus_tax
        total_tax = separate_total_tax

    gross_income = salary_annual + bonus_annual + other_taxable_income + non_taxable_income
    social_and_fund = max(0.0, social_and_fund)
    net_annual = gross_income - social_and_fund - max(0.0, total_tax) - extra_cash_expense

    return TaxMemberSummary(
        member_name=member.name,
        active_months=active_months,
        monthly_personal_social_insurance=round(personal_social_total / 12, 2),
        monthly_personal_housing_fund=round(personal_housing_fund_total / 12, 2),
        monthly_employer_social_insurance=round(employer_social_total / 12, 2),
        monthly_employer_housing_fund=round(employer_housing_fund_total / 12, 2),
        gross_annual_income=round(gross_income, 2),
        taxable_income=round(taxable_income, 2),
        salary_tax=round(salary_tax, 2),
        bonus_tax=round(bonus_tax, 2),
        total_tax=round(total_tax, 2),
        net_annual_income=round(net_annual, 2),
        net_monthly_income=round(net_annual / 12, 2),
        selected_bonus_method=selected_method,
    )


def calculate_household_tax(household: HouseholdData, rules: RulePackData) -> tuple[list[TaxMemberSummary], float, float, float]:
    household = _household_with_pension_income_stages(household, rules)
    if not household.members:
        gross_monthly = household.monthly_income
        return [], gross_monthly, gross_monthly, 0.0

    projected_rules = rules.model_copy(
        update={
            "params": {
                **rules.params,
                "_income_projection_year": household.income_projection_year,
            }
        }
    )
    summaries = [_member_tax_summary(member, projected_rules, household) for member in household.members]
    gross_monthly = sum(item.gross_annual_income for item in summaries) / 12
    net_monthly = sum(item.net_annual_income for item in summaries) / 12
    annual_tax = sum(item.total_tax for item in summaries)
    return summaries, round(gross_monthly, 2), round(net_monthly, 2), round(annual_tax, 2)


def calculate_household_tax_for_year(household: HouseholdData, rules: RulePackData, year: int) -> TaxYearSummary:
    household = _household_with_pension_income_stages(household, rules)
    projected_rules = rules.model_copy(
        update={
            "params": {
                **rules.params,
                "_income_projection_year": year,
            }
        }
    )
    summaries = [_member_tax_summary(member, projected_rules, household) for member in household.members]
    return TaxYearSummary(
        year=year,
        summaries=summaries,
        gross_annual_income=round(sum(item.gross_annual_income for item in summaries), 2),
        taxable_income=round(sum(item.taxable_income for item in summaries), 2),
        salary_tax=round(sum(item.salary_tax for item in summaries), 2),
        bonus_tax=round(sum(item.bonus_tax for item in summaries), 2),
        total_tax=round(sum(item.total_tax for item in summaries), 2),
        net_annual_income=round(sum(item.net_annual_income for item in summaries), 2),
    )


def build_tax_year_summaries(
    household: HouseholdData,
    rules: RulePackData,
    *,
    start_year: int,
    horizon_years: int = 80,
) -> list[TaxYearSummary]:
    end_year = start_year + max(0, horizon_years)
    return [calculate_household_tax_for_year(household, rules, year) for year in range(start_year, end_year + 1)]


def _build_tax_member_monthly_point(
    member: IncomeMember,
    member_index: int,
    rules: RulePackData,
    household: HouseholdData,
    target_month: date,
    absolute_month: int,
) -> TaxMemberMonthlyPoint | None:
    stage = _income_stage_for_month(member, target_month.year, target_month.month)
    if stage is None:
        return None

    personal_social, personal_housing_fund, employer_social, employer_housing_fund = _beijing_contributions(stage, rules)
    selected_bonus_method = _stage_selected_bonus_method(stage, rules, target_month.year)
    tax_state = _member_cumulative_salary_tax_state(
        member,
        rules,
        target_month.year,
        target_month.month,
        household,
    )
    salary_tax = max(0.0, tax_state.current_tax - tax_state.previous_tax)
    lump_sum_bonus_income = _stage_bonus_payout_amount(stage, target_month.year, target_month.month)
    monthly_spread_bonus = _stage_monthly_spread_bonus_amount(stage, target_month.year, target_month.month)
    bonus_income = lump_sum_bonus_income + monthly_spread_bonus
    bonus_tax_due = 0.0
    if selected_bonus_method == "separate" and lump_sum_bonus_income > 0:
        bonus_brackets = list(rules.params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
        bonus_tax_due = _bonus_tax(lump_sum_bonus_income, bonus_brackets)

    other_taxable_income = stage.monthly_freelance_income + stage.other_annual_taxable_income / 12
    structured_deduction = _structured_special_deduction_for_member_at(
        household,
        member.name,
        target_month,
        rules,
    )
    other_deduction = stage.other_annual_deductions / 12
    total_tax = salary_tax + bonus_tax_due
    pension_income = stage.monthly_non_taxable_income if stage.stage_kind == "pension" else 0.0
    gross_income = stage.monthly_salary_gross + bonus_income + other_taxable_income + stage.monthly_non_taxable_income
    personal_pension_contribution = _personal_pension_cash_contribution_for_member_at(member, target_month, rules)
    net_income = gross_income - personal_social - personal_housing_fund - total_tax

    return TaxMemberMonthlyPoint(
        month=absolute_month,
        year=target_month.year,
        month_of_year=target_month.month,
        member_index=member_index,
        member_name=member.name,
        stage_name=stage.name,
        stage_kind=stage.stage_kind,
        gross_salary=round(stage.monthly_salary_gross, 2),
        bonus_income=round(bonus_income, 2),
        other_taxable_income=round(other_taxable_income, 2),
        non_taxable_income=round(stage.monthly_non_taxable_income, 2),
        pension_income=round(pension_income, 2),
        personal_social=round(personal_social, 2),
        personal_housing_fund=round(personal_housing_fund, 2),
        employer_social=round(employer_social, 2),
        employer_housing_fund=round(employer_housing_fund, 2),
        special_additional_deduction=round(stage.monthly_special_additional_deduction, 2),
        elderly_care_deduction=round(structured_deduction, 2),
        other_deduction=round(other_deduction, 2),
        cumulative_taxable_income=round(tax_state.cumulative_taxable_income, 2),
        salary_tax=round(salary_tax, 2),
        bonus_tax=round(bonus_tax_due, 2),
        total_income_tax=round(total_tax, 2),
        personal_pension_contribution=round(personal_pension_contribution, 2),
        net_income=round(net_income, 2),
        selected_bonus_method=selected_bonus_method,
    )


def build_tax_monthly_points(
    household: HouseholdData,
    rules: RulePackData,
    *,
    base_date: date | None = None,
    horizon_months: int = 840,
) -> list[TaxMonthlyPoint]:
    household = _household_with_pension_income_stages(household, rules, as_of=base_date)
    current = base_date or date.today()
    current_month = date(current.year, current.month, 1)
    rows: list[TaxMonthlyPoint] = []

    for absolute_month in range(max(0, horizon_months) + 1):
        year, month_of_year = _month_after(current_month, absolute_month)
        target_month = date(year, month_of_year, 1)
        member_points = [
            point
            for index, member in enumerate(household.members)
            if (
                point := _build_tax_member_monthly_point(
                    member,
                    index,
                    rules,
                    household,
                    target_month,
                    absolute_month,
                )
            )
            is not None
        ]
        rows.append(
            TaxMonthlyPoint(
                month=absolute_month,
                year=year,
                month_of_year=month_of_year,
                gross_income=round(sum(item.gross_salary + item.bonus_income + item.other_taxable_income + item.non_taxable_income for item in member_points), 2),
                net_income=round(sum(item.net_income for item in member_points), 2),
                income_tax=round(sum(item.total_income_tax for item in member_points), 2),
                salary_tax=round(sum(item.salary_tax for item in member_points), 2),
                bonus_tax=round(sum(item.bonus_tax for item in member_points), 2),
                personal_social=round(sum(item.personal_social for item in member_points), 2),
                personal_housing_fund=round(sum(item.personal_housing_fund for item in member_points), 2),
                employer_social=round(sum(item.employer_social for item in member_points), 2),
                employer_housing_fund=round(sum(item.employer_housing_fund for item in member_points), 2),
                monthly_pf_deposit=round(sum(item.personal_housing_fund + item.employer_housing_fund for item in member_points), 2),
                non_taxable_income=round(sum(item.non_taxable_income for item in member_points), 2),
                pension_income=round(sum(item.pension_income for item in member_points), 2),
                extra_cash_expense=round(sum(item.personal_pension_contribution for item in member_points), 2),
                member_points=member_points,
            )
        )

    return rows


def build_tax_events(
    household: HouseholdData,
    rules: RulePackData,
    *,
    base_date: date | None = None,
    horizon_months: int = 840,
) -> list[TaxEventPoint]:
    return _strategy_build_tax_events(
        household,
        rules,
        base_date=base_date,
        horizon_months=horizon_months,
    )


def _estimate_personal_pension_tax_saving(
    household: HouseholdData,
    member: IncomeMember,
    rules: RulePackData,
    projection_year: int,
) -> float:
    scoped_rules = rules.model_copy(update={"params": {**rules.params, "_income_projection_year": projection_year}})
    summary_with = _member_tax_summary(member, scoped_rules, household=household)
    member_without = member.model_copy(
        update={
            "personal_pension_account_enabled": False,
            "personal_pension_open_mode": "none",
            "personal_pension_contribution_mode": "none",
        }
    )
    household_without = household.model_copy(
        update={
            "members": [
                member_without if item.name == member.name else item
                for item in household.members
            ]
        }
    )
    summary_without = _member_tax_summary(member_without, scoped_rules, household=household_without)
    return max(0.0, summary_without.total_tax - summary_with.total_tax)


def build_tax_strategy_items(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    base_date: date | None = None,
    horizon_months: int = 840,
    selected_purchase_month: int | None = None,
) -> list[TaxStrategyItem]:
    return _strategy_build_tax_strategy_items(
        household,
        scenario,
        rules,
        base_date=base_date,
        horizon_months=horizon_months,
        selected_purchase_month=selected_purchase_month,
        personal_pension_tax_saving_estimator=_estimate_personal_pension_tax_saving,
    )


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
    timeline_events = tax_events if tax_events is not None else build_tax_events(
        household,
        rules,
        base_date=current_month,
        horizon_months=horizon_months,
    )
    return _strategy_build_tax_strategy_timeline(
        household,
        rules,
        strategy_items,
        base_date=current_month,
        horizon_months=horizon_months,
        tax_events=timeline_events,
    )
