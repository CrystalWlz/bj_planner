from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from calendar import monthrange
from typing import Any

from ..policies import (
    DEFAULT_COMPREHENSIVE_TAX_BRACKETS,
    DEFAULT_MONTHLY_CONVERTED_BONUS_TAX_BRACKETS,
    get_policy,
)
from ..schemas import BonusTaxMethod, IncomeMember, IncomeStageData, RulePackData
from .time import (
    parse_iso_date,
)


DEFAULT_COMPREHENSIVE_BRACKETS = DEFAULT_COMPREHENSIVE_TAX_BRACKETS
DEFAULT_BONUS_BRACKETS = DEFAULT_MONTHLY_CONVERTED_BONUS_TAX_BRACKETS


@dataclass(frozen=True)
class ContributionDetails:
    personal_social: float
    personal_housing_fund: float
    employer_social: float
    employer_housing_fund: float
    social_base: float
    employee_pension: float
    employee_medical: float
    employee_medical_fixed: float
    employee_unemployment: float


def clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(value, ceiling))


def pick_bracket(amount: float, brackets: list[dict[str, Any]]) -> tuple[float, float]:
    for bracket in brackets:
        if amount <= float(bracket["threshold"]):
            return float(bracket["rate"]), float(bracket["quick_deduction"])
    last = brackets[-1]
    return float(last["rate"]), float(last["quick_deduction"])


def progressive_tax(taxable_income: float, brackets: list[dict[str, Any]]) -> float:
    if taxable_income <= 0:
        return 0.0
    if not brackets:
        brackets = DEFAULT_COMPREHENSIVE_BRACKETS
    rate, quick_deduction = pick_bracket(taxable_income, brackets)
    return max(0.0, taxable_income * rate - quick_deduction)


def bonus_tax(annual_bonus: float, brackets: list[dict[str, Any]]) -> float:
    if annual_bonus <= 0:
        return 0.0
    if not brackets:
        brackets = DEFAULT_BONUS_BRACKETS
    rate, quick_deduction = pick_bracket(annual_bonus / 12, brackets)
    return max(0.0, annual_bonus * rate - quick_deduction)


def active_months_in_period(start_date: str, end_date: str | None, projection_year: int) -> int:
    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        start = date(projection_year, 1, 1)
    if end_date:
        try:
            end = date.fromisoformat(end_date)
        except ValueError:
            end = date(projection_year, 12, 31)
    else:
        end = date(projection_year, 12, 31)

    period_start = max(start, date(projection_year, 1, 1))
    period_end = min(end, date(projection_year, 12, 31))
    if period_start > period_end:
        return 0
    return (period_end.year - period_start.year) * 12 + period_end.month - period_start.month + 1


def stage_active_in_month(stage: IncomeStageData, year: int, month: int) -> bool:
    month_start = date(year, month, 1)
    start = parse_iso_date(stage.start_date, date(1900, 1, 1))
    end = parse_iso_date(stage.end_date, date(9999, 12, 31)) if stage.end_date else date(9999, 12, 31)
    return start <= month_start <= end


def income_stage_for_month(member: IncomeMember, year: int, month: int) -> IncomeStageData | None:
    stages = member.income_stages or []
    active = [stage for stage in stages if stage_active_in_month(stage, year, month)]
    if not active:
        return None
    return max(active, key=lambda stage: parse_iso_date(stage.start_date, date(1900, 1, 1)))


def stage_bonus_payout_month(stage: IncomeStageData, projection_year: int) -> int | None:
    if stage_annual_bonus_target_amount(stage) <= 0:
        return None
    if stage.annual_bonus_payout_mode == "monthly_spread":
        return None
    if active_months_in_period(stage.start_date, stage.end_date, projection_year) <= 0:
        return None
    payout_month = max(1, min(12, stage.annual_bonus_payout_month))
    return payout_month if stage_active_in_month(stage, projection_year, payout_month) else None


def stage_annual_bonus_target_amount(stage: IncomeStageData) -> float:
    return max(0.0, stage.monthly_salary_gross) * max(0.0, stage.annual_bonus_months)


def _bonus_earning_period(stage: IncomeStageData, projection_year: int) -> tuple[date, date] | None:
    earning_start = stage.annual_bonus_earning_start_month
    earning_end = stage.annual_bonus_earning_end_month
    if earning_start is None or earning_end is None:
        return None
    payout_month = max(1, min(12, stage.annual_bonus_payout_month))
    payout_period_end = date(projection_year, payout_month, monthrange(projection_year, payout_month)[1])
    earning_end_year = projection_year
    candidate_end = date(earning_end_year, earning_end, monthrange(earning_end_year, earning_end)[1])
    if candidate_end > payout_period_end:
        earning_end_year -= 1
    earning_start_year = earning_end_year if earning_start <= earning_end else earning_end_year - 1
    return (
        date(earning_start_year, earning_start, 1),
        date(earning_end_year, earning_end, monthrange(earning_end_year, earning_end)[1]),
    )


def stage_bonus_earning_months(stage: IncomeStageData, projection_year: int) -> float:
    earning_period = _bonus_earning_period(stage, projection_year)
    if earning_period is not None:
        earning_period_start, earning_period_end = earning_period
        month_cursor = earning_period_start
        active_months = 0
        while month_cursor <= earning_period_end:
            if stage_active_in_month(stage, month_cursor.year, month_cursor.month):
                active_months += 1
            if month_cursor.month == 12:
                month_cursor = date(month_cursor.year + 1, 1, 1)
            else:
                month_cursor = date(month_cursor.year, month_cursor.month + 1, 1)
        return float(active_months)
    return active_months_in_period(stage.start_date, stage.end_date, projection_year)


def stage_monthly_spread_bonus_amount(stage: IncomeStageData, projection_year: int, month: int) -> float:
    target_amount = stage_annual_bonus_target_amount(stage)
    if target_amount <= 0 or stage.annual_bonus_payout_mode != "monthly_spread":
        return 0.0
    if not stage_active_in_month(stage, projection_year, month):
        return 0.0
    earning_start = stage.annual_bonus_earning_start_month
    earning_end = stage.annual_bonus_earning_end_month
    if earning_start is not None and earning_end is not None:
        in_window = (
            earning_start <= month <= earning_end
            if earning_start <= earning_end
            else month >= earning_start or month <= earning_end
        )
        if not in_window:
            return 0.0
    return target_amount / 12


def stage_bonus_payout_amount(stage: IncomeStageData, projection_year: int, month: int) -> float:
    if stage_bonus_payout_month(stage, projection_year) != month:
        return 0.0
    return stage_annual_bonus_target_amount(stage) * min(12.0, stage_bonus_earning_months(stage, projection_year)) / 12


def stage_bonus_cash_amount(stage: IncomeStageData, projection_year: int, month: int) -> float:
    return stage_bonus_payout_amount(stage, projection_year, month) + stage_monthly_spread_bonus_amount(
        stage,
        projection_year,
        month,
    )


def beijing_contribution_details(member: IncomeMember | IncomeStageData, rules: RulePackData) -> ContributionDetails:
    if isinstance(member, IncomeStageData) and not member.payroll_contributions_enabled:
        return ContributionDetails(
            personal_social=max(0.0, member.monthly_social_insurance),
            personal_housing_fund=max(0.0, member.monthly_housing_fund),
            employer_social=0.0,
            employer_housing_fund=0.0,
            social_base=0.0,
            employee_pension=0.0,
            employee_medical=0.0,
            employee_medical_fixed=0.0,
            employee_unemployment=0.0,
        )
    if member.monthly_salary_gross <= 0:
        return ContributionDetails(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    payroll_policy = get_policy(rules).payroll_contribution_policy()
    social_base = clamp(
        member.monthly_salary_gross,
        payroll_policy.social_base_floor,
        payroll_policy.social_base_ceiling,
    )
    fund_base = clamp(
        member.monthly_salary_gross,
        payroll_policy.housing_fund_base_floor,
        payroll_policy.housing_fund_base_ceiling,
    )
    personal_fund_rate = clamp(
        member.housing_fund_personal_rate,
        payroll_policy.housing_fund_rate_floor,
        payroll_policy.housing_fund_rate_ceiling,
    )
    employer_fund_rate = clamp(
        member.housing_fund_employer_rate,
        payroll_policy.housing_fund_rate_floor,
        payroll_policy.housing_fund_rate_ceiling,
    )

    employee_pension = social_base * payroll_policy.employee_pension_rate
    employee_medical = social_base * payroll_policy.employee_medical_rate
    employee_medical_fixed = payroll_policy.employee_medical_fixed
    employee_unemployment = social_base * payroll_policy.employee_unemployment_rate
    personal_social = employee_pension + employee_medical + employee_medical_fixed + employee_unemployment
    employer_social = (
        social_base * payroll_policy.employer_pension_rate
        + social_base * payroll_policy.employer_medical_maternity_rate
        + social_base * payroll_policy.employer_unemployment_rate
        + social_base * payroll_policy.employer_work_injury_rate
    )
    personal_housing_fund = fund_base * personal_fund_rate
    employer_housing_fund = fund_base * employer_fund_rate
    return ContributionDetails(
        personal_social=personal_social,
        personal_housing_fund=personal_housing_fund,
        employer_social=employer_social,
        employer_housing_fund=employer_housing_fund,
        social_base=social_base,
        employee_pension=employee_pension,
        employee_medical=employee_medical,
        employee_medical_fixed=employee_medical_fixed,
        employee_unemployment=employee_unemployment,
    )


def beijing_contributions(member: IncomeMember | IncomeStageData, rules: RulePackData) -> tuple[float, float, float, float]:
    details = beijing_contribution_details(member, rules)
    return (
        details.personal_social,
        details.personal_housing_fund,
        details.employer_social,
        details.employer_housing_fund,
    )


def annual_bonus_separate_tax_available(rules: RulePackData, target_year: int) -> bool:
    return get_policy(rules).tax_calculation_policy().annual_bonus_separate_tax_available(target_year)


def stage_selected_bonus_method(stage: IncomeStageData, rules: RulePackData, target_year: int | None = None) -> BonusTaxMethod:
    if stage.annual_bonus_payout_mode == "monthly_spread":
        return "merged"
    if target_year is not None and not annual_bonus_separate_tax_available(rules, target_year):
        return "merged"
    method = stage.bonus_tax_method
    if method in {"merged", "separate"}:
        return method

    tax_policy = get_policy(rules).tax_calculation_policy()
    annual_brackets = tax_policy.comprehensive_brackets
    bonus_brackets = tax_policy.monthly_converted_bonus_brackets
    standard_deduction = tax_policy.personal_standard_deduction_annual
    personal_social, personal_housing_fund, _, _ = beijing_contributions(stage, rules)
    common_deductions = (
        standard_deduction
        + (personal_social + personal_housing_fund) * 12
        + stage.monthly_special_additional_deduction * 12
        + stage.other_annual_deductions
    )
    salary_taxable = max(
        0.0,
        stage.monthly_salary_gross * 12
        + stage.monthly_freelance_income * 12
        + stage.other_annual_taxable_income
        - common_deductions,
    )
    bonus_amount = stage_annual_bonus_target_amount(stage)
    if target_year is not None:
        payout_month = stage_bonus_payout_month(stage, target_year)
        if payout_month is not None:
            bonus_amount = stage_bonus_payout_amount(stage, target_year, payout_month)
    merged_taxable = max(0.0, salary_taxable + bonus_amount)
    separate_total = progressive_tax(salary_taxable, annual_brackets) + bonus_tax(bonus_amount, bonus_brackets)
    merged_total = progressive_tax(merged_taxable, annual_brackets)
    return "merged" if merged_total < separate_total else "separate"
