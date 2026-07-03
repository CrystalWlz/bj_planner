from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Callable, Literal

from .policies import get_policy
from .schemas import (
    AccountSnapshotPoint,
    AffordabilityResult,
    BonusTaxMethod,
    CarLoanSummary,
    CarPlanAnalysis,
    CarPlanData,
    ElderlyDependentData,
    HouseholdData,
    IncomeMember,
    IncomeStageData,
    LoanSummary,
    LoanVisualizationPoint,
    AccountConceptSummary,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    PlanEventPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    StrategyExplanationPoint,
    StressResult,
    PhasedLoanData,
    PhasedLoanSummary,
    TaxMemberSummary,
    YieldSensitivityPoint,
)


DEFAULT_COMPREHENSIVE_BRACKETS = [
    {"threshold": 36000, "rate": 0.03, "quick_deduction": 0},
    {"threshold": 144000, "rate": 0.10, "quick_deduction": 2520},
    {"threshold": 300000, "rate": 0.20, "quick_deduction": 16920},
    {"threshold": 420000, "rate": 0.25, "quick_deduction": 31920},
    {"threshold": 660000, "rate": 0.30, "quick_deduction": 52920},
    {"threshold": 960000, "rate": 0.35, "quick_deduction": 85920},
    {"threshold": 999999999, "rate": 0.45, "quick_deduction": 181920},
]

DEFAULT_BONUS_BRACKETS = [
    {"threshold": 3000, "rate": 0.03, "quick_deduction": 0},
    {"threshold": 12000, "rate": 0.10, "quick_deduction": 210},
    {"threshold": 25000, "rate": 0.20, "quick_deduction": 1410},
    {"threshold": 35000, "rate": 0.25, "quick_deduction": 2660},
    {"threshold": 55000, "rate": 0.30, "quick_deduction": 4410},
    {"threshold": 80000, "rate": 0.35, "quick_deduction": 7160},
    {"threshold": 999999999, "rate": 0.45, "quick_deduction": 15160},
]


@dataclass(frozen=True)
class LoanComputation:
    first_month_payment: float
    average_month_payment: float
    total_interest: float


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
    extra_cash_expense: float = 0.0


@dataclass(frozen=True)
class PurchaseCandidate:
    purchase_month: int
    mix: tuple[float, float, float, float, float, float, float]
    pf_upfront_extractable: float
    family_pf_upfront_extractable: float
    pf_post_transaction_extractable: float
    cash_after_transaction: float
    cash_after_purchase: float
    pf_after_extract: float
    minimum_cash_balance: float
    minimum_cash_balance_month: int | None
    cash_stress_ok: bool
    cash_stress_shortfall: float


def _parallel_worker_count(rules: RulePackData, task_count: int) -> int:
    if task_count <= 1:
        return 1
    raw_value = rules.params.get("backend_parallel_workers", min(4, task_count))
    try:
        configured = int(raw_value)
    except (TypeError, ValueError):
        configured = min(4, task_count)
    return max(1, min(configured, task_count, 8))


def calculate_loan(principal: float, annual_rate: float, years: int, method: str) -> LoanComputation:
    if principal <= 0 or years <= 0:
        return LoanComputation(0, 0, 0)

    months = years * 12
    monthly_rate = annual_rate / 12

    if monthly_rate <= 0:
        monthly_payment = principal / months
        return LoanComputation(monthly_payment, monthly_payment, 0)

    if method == "equal_principal":
        principal_per_month = principal / months
        first_month_payment = principal_per_month + principal * monthly_rate
        total_interest = monthly_rate * principal_per_month * months * (months + 1) / 2
        average_month_payment = (principal + total_interest) / months
        return LoanComputation(first_month_payment, average_month_payment, total_interest)

    factor = (1 + monthly_rate) ** months
    monthly_payment = principal * monthly_rate * factor / (factor - 1)
    total_interest = monthly_payment * months - principal
    return LoanComputation(monthly_payment, monthly_payment, total_interest)


def _loan_principal_for_payment_cap(
    monthly_payment_cap: float,
    annual_rate: float,
    years: int,
    method: str,
) -> float:
    if monthly_payment_cap <= 0 or years <= 0:
        return 0.0
    months = years * 12
    monthly_rate = annual_rate / 12
    if method == "equal_principal" or monthly_rate <= 0:
        return monthly_payment_cap / (1 / months + monthly_rate)
    factor = (1 + monthly_rate) ** months
    return monthly_payment_cap * (factor - 1) / (monthly_rate * factor)


def _loan_balance_after_payments(
    principal: float,
    annual_rate: float,
    years: int,
    method: str,
    elapsed_payments: int,
) -> float:
    return _loan_balance_after_monthly_payments(
        principal,
        annual_rate,
        years * 12,
        method,
        elapsed_payments,
    )


def _loan_balance_after_monthly_payments(
    principal: float,
    annual_rate: float,
    total_months: int,
    method: str,
    elapsed_payments: int,
) -> float:
    if principal <= 0 or total_months <= 0:
        return 0.0
    paid_months = max(0, min(total_months, int(elapsed_payments)))
    if paid_months <= 0:
        return principal
    if paid_months >= total_months:
        return 0.0
    monthly_rate = annual_rate / 12
    if method == "equal_principal" or monthly_rate <= 0:
        return max(0.0, principal - (principal / total_months) * paid_months)
    factor = (1 + monthly_rate) ** total_months
    monthly_payment = principal * monthly_rate * factor / (factor - 1)
    return max(
        0.0,
        principal * (1 + monthly_rate) ** paid_months
        - monthly_payment * (((1 + monthly_rate) ** paid_months - 1) / monthly_rate),
    )


def _installment_balance_after_payments(principal: float, total_months: int, elapsed_payments: int) -> float:
    if principal <= 0 or total_months <= 0:
        return 0.0
    paid_months = max(0, min(total_months, int(elapsed_payments)))
    return max(0.0, principal - (principal / total_months) * paid_months)


def _pick_bracket(amount: float, brackets: list[dict]) -> tuple[float, float]:
    for bracket in brackets:
        if amount <= float(bracket["threshold"]):
            return float(bracket["rate"]), float(bracket["quick_deduction"])
    last = brackets[-1]
    return float(last["rate"]), float(last["quick_deduction"])


def _progressive_tax(taxable_income: float, brackets: list[dict]) -> float:
    if taxable_income <= 0:
        return 0.0
    if not brackets:
        brackets = DEFAULT_COMPREHENSIVE_BRACKETS
    rate, quick_deduction = _pick_bracket(taxable_income, brackets)
    return max(0.0, taxable_income * rate - quick_deduction)


def _bonus_tax(annual_bonus: float, brackets: list[dict]) -> float:
    if annual_bonus <= 0:
        return 0.0
    if not brackets:
        brackets = DEFAULT_BONUS_BRACKETS
    rate, quick_deduction = _pick_bracket(annual_bonus / 12, brackets)
    return max(0.0, annual_bonus * rate - quick_deduction)


def _active_months_in_year(start_date: str, projection_year: int) -> int:
    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        return 12
    if start.year > projection_year:
        return 0
    if start.year < projection_year:
        return 12
    return max(0, 13 - start.month)


def _active_months_in_period(start_date: str, end_date: str | None, projection_year: int) -> int:
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


def _stage_bonus_payout_month(stage: IncomeStageData, projection_year: int) -> int | None:
    if stage.annual_bonus <= 0:
        return None
    if _active_months_in_period(stage.start_date, stage.end_date, projection_year) <= 0:
        return None
    payout_month = max(1, min(12, stage.annual_bonus_payout_month))
    return payout_month if _stage_active_in_month(stage, projection_year, payout_month) else None


def _stage_bonus_payout_amount(stage: IncomeStageData, projection_year: int, month: int) -> float:
    if _stage_bonus_payout_month(stage, projection_year) != month:
        return 0.0
    active_months = _active_months_in_period(stage.start_date, stage.end_date, projection_year)
    return stage.annual_bonus * active_months / 12


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(value, ceiling))


def _beijing_contributions(member: IncomeMember | IncomeStageData, rules: RulePackData) -> tuple[float, float, float, float]:
    if isinstance(member, IncomeStageData) and not member.payroll_contributions_enabled:
        return 0.0, 0.0, 0.0, 0.0
    if member.monthly_salary_gross <= 0:
        return 0.0, 0.0, 0.0, 0.0
    params = rules.params
    social_base = _clamp(
        member.monthly_salary_gross,
        float(params.get("beijing_social_base_floor", 7162)),
        float(params.get("beijing_social_base_ceiling", 35811)),
    )
    fund_base = _clamp(
        member.monthly_salary_gross,
        float(params.get("beijing_housing_fund_base_floor", 2540)),
        float(params.get("beijing_housing_fund_base_ceiling", 35811)),
    )
    fund_rate_floor = float(params.get("housing_fund_min_rate", 0.05))
    fund_rate_ceiling = float(params.get("housing_fund_max_rate", 0.12))
    personal_fund_rate = _clamp(member.housing_fund_personal_rate, fund_rate_floor, fund_rate_ceiling)
    employer_fund_rate = _clamp(member.housing_fund_employer_rate, fund_rate_floor, fund_rate_ceiling)

    personal_social = (
        social_base * float(params.get("employee_pension_rate", 0.08))
        + social_base * float(params.get("employee_medical_rate", 0.02))
        + float(params.get("employee_medical_fixed", 3))
        + social_base * float(params.get("employee_unemployment_rate", 0.005))
    )
    employer_social = (
        social_base * float(params.get("employer_pension_rate", 0.16))
        + social_base * float(params.get("employer_medical_maternity_rate", 0.098))
        + social_base * float(params.get("employer_unemployment_rate", 0.005))
        + social_base * float(params.get("employer_work_injury_rate", 0.002))
    )
    personal_housing_fund = fund_base * personal_fund_rate
    employer_housing_fund = fund_base * employer_fund_rate
    return personal_social, personal_housing_fund, employer_social, employer_housing_fund


def _parse_iso_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def _add_months(base: date, months: int) -> date:
    zero_based_month = base.month - 1 + months
    return date(base.year + zero_based_month // 12, zero_based_month % 12 + 1, 1)


def _end_of_previous_month(month_start: date) -> date:
    if month_start.month == 1:
        return date(month_start.year - 1, 12, 31)
    return date(month_start.year, month_start.month - 1, 28)


def _month_start_for_age(as_of: date, current_age: int, target_age: int) -> date:
    months_until = max(0, (target_age - current_age) * 12)
    return _add_months(date(as_of.year, as_of.month, 1), months_until)


def _month_start_for_birth_month_or_age(
    as_of: date,
    birth_month_value: str | None,
    current_age: int,
    target_age: int,
) -> date:
    birth_month = _parse_year_month(birth_month_value)
    if birth_month is not None:
        target = date(birth_month[0] + target_age, birth_month[1], 1)
        return max(date(as_of.year, as_of.month, 1), target)
    return _month_start_for_age(as_of, current_age, target_age)


def _months_between_months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _retirement_tail_months(household: HouseholdData, *, as_of: date | None = None) -> int:
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    shock = household.career_shock
    targets: list[int] = []
    if household.members:
        targets.append(
            max(
                0,
                _months_between_months(
                    current_month,
                    _month_start_for_birth_month_or_age(
                        current_month,
                        shock.self_birth_month,
                        shock.self_current_age,
                        shock.self_retirement_age,
                    ),
                ),
            )
        )
    if len(household.members) >= 2:
        targets.append(
            max(
                0,
                _months_between_months(
                    current_month,
                    _month_start_for_birth_month_or_age(
                        current_month,
                        shock.spouse_birth_month,
                        shock.spouse_current_age,
                        shock.spouse_retirement_age,
                    ),
                ),
            )
        )
    return (max(targets) if targets else 0) + 120


def _visualization_horizon_months(
    household: HouseholdData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    second_loan: CarLoanSummary | None = None,
) -> int:
    plan_horizons = [
        (plan.months_to_buy or 0)
        + max(
            plan.commercial_loan_years * 12 if plan.commercial_loan_amount > 0 else 0,
            plan.provident_loan_years * 12 if plan.provident_loan_amount > 0 else 0,
        )
        + 12
        for plan in purchase_plans
    ]
    first_vehicle_start = (
        car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else car_loan.purchase_delay_months
    )
    second_vehicle_start = (
        second_loan.months_to_down_payment
        if second_loan and second_loan.months_to_down_payment is not None
        else second_loan.purchase_delay_months if second_loan else 0
    )
    vehicle_horizons = [
        first_vehicle_start + car_loan.total_months + 24 if car_loan.enabled else 0,
        second_vehicle_start + second_loan.total_months + 24 if second_loan and second_loan.enabled else 0,
    ]
    return min(840, max(180, _retirement_tail_months(household), *plan_horizons, *vehicle_horizons))


def _zero_cash_stage(template: IncomeStageData, name: str, start: date, end: date | None = None) -> IncomeStageData:
    return template.model_copy(
        update={
            "name": name,
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else None,
            "monthly_salary_gross": 0,
            "annual_bonus": 0,
            "annual_bonus_payout_month": template.annual_bonus_payout_month,
            "monthly_non_taxable_income": 0,
            "monthly_extra_cash_expense": 0,
            "monthly_social_insurance": 0,
            "monthly_housing_fund": 0,
            "housing_fund_personal_rate": 0,
            "housing_fund_employer_rate": 0,
            "monthly_special_additional_deduction": 0,
            "other_annual_deductions": 0,
            "other_annual_taxable_income": 0,
            "payroll_contributions_enabled": False,
        }
    )


def _unemployment_benefit_months_from_service(service_months: int) -> int:
    if service_months < 12:
        return 0
    if service_months < 60:
        return 12
    if service_months < 120:
        return 18
    return 24


def _unemployment_benefit_monthly_from_service(service_months: int, rules: RulePackData) -> float:
    params = rules.params
    if service_months >= 240:
        return float(params.get("beijing_unemployment_benefit_20y_plus", 2286))
    if service_months >= 180:
        return float(params.get("beijing_unemployment_benefit_15_to_20y", 2215))
    if service_months >= 120:
        return float(params.get("beijing_unemployment_benefit_10_to_15y", 2188))
    if service_months >= 60:
        return float(params.get("beijing_unemployment_benefit_5_to_10y", 2156))
    if service_months >= 12:
        return float(params.get("beijing_unemployment_benefit_under_5y", 2129))
    return 0.0


def _career_shock_unemployment_months(household: HouseholdData, shock: "CareerShockData") -> int:
    if not shock.auto_unemployment_benefit:
        return max(0, min(shock.unemployment_benefit_months, 24))
    return _unemployment_benefit_months_from_service(max(0, household.social_security_months))


def _career_shock_self_social_monthly(shock: "CareerShockData", rules: RulePackData) -> float:
    if not shock.auto_self_social_insurance:
        return max(0.0, shock.self_social_insurance_monthly)
    params = rules.params
    base = float(params.get("flexible_employment_social_base", params.get("beijing_social_base_floor", 7162)))
    floor = float(params.get("beijing_social_base_floor", 7162))
    ceiling = float(params.get("beijing_social_base_ceiling", 35811))
    base = _clamp(base, floor, ceiling)
    pension = base * float(params.get("flexible_employment_pension_rate", 0.20))
    unemployment = base * float(params.get("flexible_employment_unemployment_rate", 0.01))
    medical = float(params.get("flexible_employment_medical_monthly", 584.92))
    return round(max(0.0, pension + unemployment + medical), 2)


def _household_with_career_income_stages(
    household: HouseholdData,
    rules: RulePackData | None = None,
    *,
    as_of: date | None = None,
) -> HouseholdData:
    shock = household.career_shock
    if household.career_shock_applied or not shock.enabled or not household.members:
        return household
    active_rules = rules or RulePackData()

    current = as_of or date.today()
    synthetic_prefix = "自动情景："
    updated_members: list[IncomeMember] = []
    for index, member in enumerate(household.members):
        stages = [
            stage
            for stage in (member.income_stages or [])
            if not stage.name.startswith(synthetic_prefix)
        ]
        if not stages:
            stages = [
                IncomeStageData(
                    name="current",
                    start_date=member.employment_start_date,
                    monthly_salary_gross=member.monthly_salary_gross,
                    annual_bonus=member.annual_bonus,
                    annual_bonus_payout_month=4,
                    monthly_social_insurance=member.monthly_social_insurance,
                    monthly_housing_fund=member.monthly_housing_fund,
                    housing_fund_personal_rate=member.housing_fund_personal_rate,
                    housing_fund_employer_rate=member.housing_fund_employer_rate,
                    monthly_special_additional_deduction=member.monthly_special_additional_deduction,
                    other_annual_deductions=member.other_annual_deductions,
                    other_annual_taxable_income=member.other_annual_taxable_income,
                    bonus_tax_method=member.bonus_tax_method,
                )
            ]
        template = max(stages, key=lambda stage: _parse_iso_date(stage.start_date, date(1900, 1, 1)))
        member_current_age = shock.self_current_age if index == 0 else shock.spouse_current_age
        member_birth_month = shock.self_birth_month if index == 0 else shock.spouse_birth_month
        retirement_age = shock.self_retirement_age if index == 0 else shock.spouse_retirement_age
        pension_monthly = shock.self_pension_monthly if index == 0 else shock.spouse_pension_monthly
        retirement_start = _month_start_for_birth_month_or_age(
            current,
            member_birth_month,
            member_current_age,
            retirement_age,
        )

        if member.name == shock.layoff_member_name:
            layoff_start = _month_start_for_birth_month_or_age(
                current,
                shock.self_birth_month,
                shock.self_current_age,
                shock.layoff_age,
            )
            unemployment_months = _career_shock_unemployment_months(household, shock)
            if unemployment_months > 0 and layoff_start < retirement_start:
                if shock.auto_unemployment_benefit:
                    first_period_months = min(unemployment_months, 12)
                    first_end = min(
                        _add_months(layoff_start, first_period_months - 1),
                        _end_of_previous_month(retirement_start),
                    )
                    first_stage = _zero_cash_stage(
                        template,
                        f"{synthetic_prefix}{shock.layoff_age}岁被裁员-失业金期",
                        layoff_start,
                        first_end,
                    )
                    stages.append(
                        first_stage.model_copy(
                            update={
                                "monthly_non_taxable_income": _unemployment_benefit_monthly_from_service(
                                    household.social_security_months,
                                    active_rules,
                                )
                            }
                        )
                    )
                    if unemployment_months > 12:
                        later_start = _add_months(layoff_start, 12)
                        if later_start < retirement_start:
                            later_end = min(
                                _add_months(layoff_start, unemployment_months - 1),
                                _end_of_previous_month(retirement_start),
                            )
                            later_stage = _zero_cash_stage(
                                template,
                                f"{synthetic_prefix}{shock.layoff_age}岁被裁员-失业金后续期",
                                later_start,
                                later_end,
                            )
                            stages.append(
                                later_stage.model_copy(
                                    update={
                                        "monthly_non_taxable_income": float(
                                            active_rules.params.get("beijing_unemployment_benefit_after_12_months", 2129)
                                        )
                                    }
                                )
                            )
                else:
                    unemployment_end = _add_months(layoff_start, unemployment_months - 1)
                    end = min(unemployment_end, _end_of_previous_month(retirement_start))
                    unemployment_stage = _zero_cash_stage(template, f"{synthetic_prefix}{shock.layoff_age}岁被裁员-失业金期", layoff_start, end)
                    stages.append(
                        unemployment_stage.model_copy(
                            update={"monthly_non_taxable_income": shock.unemployment_benefit_monthly}
                        )
                    )
            self_social_start = _add_months(layoff_start, unemployment_months)
            if self_social_start < retirement_start:
                stages.append(
                    _zero_cash_stage(
                        template,
                        f"{synthetic_prefix}{shock.layoff_age}岁被裁员-灵活就业自缴社保期",
                        self_social_start,
                        _end_of_previous_month(retirement_start),
                    ).model_copy(update={"monthly_extra_cash_expense": _career_shock_self_social_monthly(shock, active_rules)})
                )

        if pension_monthly > 0:
            stages.append(
                _zero_cash_stage(template, f"{synthetic_prefix}{retirement_age}岁退休-养老金", retirement_start).model_copy(
                    update={"monthly_non_taxable_income": pension_monthly}
                )
            )

        updated_members.append(member.model_copy(update={"income_stages": stages}))

    return household.model_copy(update={"members": updated_members, "career_shock_applied": True})


def _parse_year_month(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (AttributeError, ValueError):
        return None
    if not 1 <= month <= 12:
        return None
    return year, month


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


def _stage_active_in_month(stage: IncomeStageData, year: int, month: int) -> bool:
    month_start = date(year, month, 1)
    start = _parse_iso_date(stage.start_date, date(1900, 1, 1))
    end = _parse_iso_date(stage.end_date, date(9999, 12, 31)) if stage.end_date else date(9999, 12, 31)
    return start <= month_start <= end


def _income_stage_for_month(member: IncomeMember, year: int, month: int) -> IncomeStageData | None:
    stages = member.income_stages or [
        IncomeStageData(
            name="current",
            start_date=member.employment_start_date,
            monthly_salary_gross=member.monthly_salary_gross,
            annual_bonus=member.annual_bonus,
            annual_bonus_payout_month=4,
            monthly_social_insurance=member.monthly_social_insurance,
            monthly_housing_fund=member.monthly_housing_fund,
            housing_fund_personal_rate=member.housing_fund_personal_rate,
            housing_fund_employer_rate=member.housing_fund_employer_rate,
            monthly_special_additional_deduction=member.monthly_special_additional_deduction,
            other_annual_deductions=member.other_annual_deductions,
            other_annual_taxable_income=member.other_annual_taxable_income,
            bonus_tax_method=member.bonus_tax_method,
        )
    ]
    active = [stage for stage in stages if _stage_active_in_month(stage, year, month)]
    if not active:
        return None
    return max(active, key=lambda stage: _parse_iso_date(stage.start_date, date(1900, 1, 1)))


def _stage_selected_bonus_method(stage: IncomeStageData, rules: RulePackData) -> BonusTaxMethod:
    method = stage.bonus_tax_method
    if method in {"merged", "separate"}:
        return method

    params = rules.params
    annual_brackets = list(params.get("comprehensive_tax_brackets") or DEFAULT_COMPREHENSIVE_BRACKETS)
    bonus_brackets = list(params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
    standard_deduction = float(params.get("personal_standard_deduction_annual", 60000))
    personal_social, personal_housing_fund, _, _ = _beijing_contributions(stage, rules)
    common_deductions = (
        standard_deduction
        + (personal_social + personal_housing_fund) * 12
        + stage.monthly_special_additional_deduction * 12
        + stage.other_annual_deductions
    )
    salary_taxable = max(0.0, stage.monthly_salary_gross * 12 + stage.other_annual_taxable_income - common_deductions)
    merged_taxable = max(0.0, salary_taxable + stage.annual_bonus)
    separate_total = _progressive_tax(salary_taxable, annual_brackets) + _bonus_tax(stage.annual_bonus, bonus_brackets)
    merged_total = _progressive_tax(merged_taxable, annual_brackets)
    return "merged" if merged_total < separate_total else "separate"


def _member_cumulative_salary_tax(
    member: IncomeMember,
    rules: RulePackData,
    year: int,
    through_month: int,
    household: HouseholdData | None = None,
) -> float:
    if through_month <= 0:
        return 0.0

    params = rules.params
    annual_brackets = list(params.get("comprehensive_tax_brackets") or DEFAULT_COMPREHENSIVE_BRACKETS)
    monthly_standard_deduction = float(params.get("personal_standard_deduction_annual", 60000)) / 12
    active_months = 0
    cumulative_income = 0.0
    cumulative_social_and_fund = 0.0
    cumulative_special_deduction = 0.0
    cumulative_other_deduction = 0.0

    for month in range(1, through_month + 1):
        target_date = date(year, month, 1)
        stage = _income_stage_for_month(member, year, month)
        if stage is None:
            continue
        personal_social, personal_housing_fund, _, _ = _beijing_contributions(stage, rules)
        selected_bonus_method = _stage_selected_bonus_method(stage, rules)
        active_months += 1
        cumulative_income += stage.monthly_salary_gross
        cumulative_income += stage.other_annual_taxable_income / 12
        if selected_bonus_method == "merged":
            cumulative_income += _stage_bonus_payout_amount(stage, year, month)
        cumulative_social_and_fund += personal_social + personal_housing_fund
        cumulative_special_deduction += stage.monthly_special_additional_deduction
        cumulative_special_deduction += _elderly_care_deduction_for_member_at(
            household,
            member.name,
            target_date,
        )
        cumulative_other_deduction += stage.other_annual_deductions / 12

    taxable = max(
        0.0,
        cumulative_income
        - monthly_standard_deduction * active_months
        - cumulative_social_and_fund
        - cumulative_special_deduction
        - cumulative_other_deduction,
    )
    return _progressive_tax(taxable, annual_brackets)


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
    selected_bonus_method = _stage_selected_bonus_method(stage, rules)
    cumulative_tax = _member_cumulative_salary_tax(
        member,
        rules,
        target_month.year,
        target_month.month,
        household,
    )
    previous_cumulative_tax = _member_cumulative_salary_tax(
        member,
        rules,
        target_month.year,
        target_month.month - 1,
        household,
    )
    salary_tax = max(0.0, cumulative_tax - previous_cumulative_tax)
    bonus_payout = _stage_bonus_payout_amount(stage, target_month.year, target_month.month)
    bonus_tax_due = 0.0
    if selected_bonus_method == "separate":
        bonus_brackets = list(rules.params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
        bonus_tax_due = _bonus_tax(bonus_payout, bonus_brackets) if bonus_payout > 0 else 0.0

    taxable_cash_income = stage.monthly_salary_gross + bonus_payout + stage.other_annual_taxable_income / 12
    gross_income = taxable_cash_income + stage.monthly_non_taxable_income
    income_tax = salary_tax + bonus_tax_due
    net_income = gross_income - personal_social - personal_housing_fund - income_tax - stage.monthly_extra_cash_expense
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
        extra_cash_expense=round(stage.monthly_extra_cash_expense, 2),
    )


def household_monthly_income_profile_at(
    household: HouseholdData,
    rules: RulePackData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> MonthlyIncomeProfile:
    household = _household_with_career_income_stages(household, rules, as_of=as_of)
    current = as_of or date.today()
    year, month = _month_after(current, max(0, months_from_now))
    target_month = date(year, month, 1)
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
        _member_monthly_income_profile(member, rules, target_month, household)
        for member in household.members
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
        extra_cash_expense=round(sum(item.extra_cash_expense for item in member_profiles), 2),
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
    stages = member.income_stages or [
        IncomeStageData(
            name="当前收入",
            start_date=member.employment_start_date,
            monthly_salary_gross=member.monthly_salary_gross,
            annual_bonus=member.annual_bonus,
            monthly_social_insurance=member.monthly_social_insurance,
            monthly_housing_fund=member.monthly_housing_fund,
            housing_fund_personal_rate=member.housing_fund_personal_rate,
            housing_fund_employer_rate=member.housing_fund_employer_rate,
            monthly_special_additional_deduction=member.monthly_special_additional_deduction,
            other_annual_deductions=member.other_annual_deductions,
            other_annual_taxable_income=member.other_annual_taxable_income,
            bonus_tax_method=member.bonus_tax_method,
        )
    ]

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
        bonus_annual += stage.annual_bonus * stage_ratio
        non_taxable_income += stage.monthly_non_taxable_income * stage_months
        extra_cash_expense += stage.monthly_extra_cash_expense * stage_months
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
            special_deductions += _elderly_care_deduction_for_member_at(
                household,
                member.name,
                date(projection_year, month, 1),
            )

    common_deductions = standard_deduction + social_and_fund + special_deductions + other_deductions

    salary_taxable = max(0.0, salary_annual + other_taxable_income - common_deductions)
    separate_salary_tax = _progressive_tax(salary_taxable, annual_brackets)
    separate_bonus_tax = _bonus_tax(bonus_annual, bonus_brackets)
    separate_total_tax = separate_salary_tax + separate_bonus_tax

    merged_taxable = max(
        0.0,
        salary_annual
        + bonus_annual
        + other_taxable_income
        - common_deductions,
    )
    merged_total_tax = _progressive_tax(merged_taxable, annual_brackets)

    method = member.bonus_tax_method
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
    household = _household_with_career_income_stages(household, rules)
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


def _loan_summary(principal: float, rate: float, years: int, method: str) -> LoanSummary | None:
    if principal <= 0:
        return None
    computed = calculate_loan(principal, rate, years, method)
    return LoanSummary(
        principal=round(principal, 2),
        annual_rate=rate,
        years=years,
        repayment_method=method,  # type: ignore[arg-type]
        first_month_payment=round(computed.first_month_payment, 2),
        average_month_payment=round(computed.average_month_payment, 2),
        total_interest=round(computed.total_interest, 2),
    )


def _parse_month(value: str) -> tuple[int, int] | None:
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (ValueError, AttributeError):
        return None
    if not 1 <= month <= 12:
        return None
    return year, month


def _month_distance(start: tuple[int, int], end: tuple[int, int]) -> int:
    return (end[0] - start[0]) * 12 + end[1] - start[1]


def _month_after(base: date, months_from_now: int) -> tuple[int, int]:
    zero_based_month = base.month - 1 + months_from_now
    return base.year + zero_based_month // 12, zero_based_month % 12 + 1


def monthly_household_expense_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> float:
    current = as_of or date.today()
    target_month = _month_after(current, max(0, months_from_now))
    scheduled_total = 0.0
    for item in household.scheduled_expenses:
        start_month = _parse_month(item.start_month)
        end_month = _parse_month(item.end_month) if item.end_month else None
        if start_month is None or _month_distance(start_month, target_month) < 0:
            continue
        if end_month is not None and _month_distance(target_month, end_month) < 0:
            continue
        scheduled_total += item.monthly_amount
    return max(0.0, household.monthly_expense + scheduled_total)


def _equal_installment_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate <= 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def _amortized_monthly_payment(principal: float, annual_rate: float, months: int, method: str) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if method == "equal_principal":
        return principal / months + principal * monthly_rate
    return _equal_installment_monthly_payment(principal, annual_rate, months)


def _commercial_repayment_method(scenario: ScenarioData) -> str:
    return scenario.commercial_repayment_method or scenario.repayment_method


def _provident_repayment_method(scenario: ScenarioData) -> str:
    return scenario.provident_repayment_method or scenario.repayment_method


def summarize_phased_loans(
    loans: list[PhasedLoanData],
    *,
    as_of: date | None = None,
) -> list[PhasedLoanSummary]:
    current = as_of or date.today()
    current_month = (current.year, current.month)
    summaries: list[PhasedLoanSummary] = []

    for loan in loans:
        start_month = _parse_month(loan.interest_start_month)
        interest_only_until = _parse_month(loan.interest_only_until)
        if start_month is None or interest_only_until is None or loan.principal <= 0:
            phase = "配置待校验"
            current_payment = 0.0
        elif _month_distance(current_month, start_month) > 0:
            phase = "未开始计息"
            current_payment = 0.0
        elif _month_distance(current_month, interest_only_until) >= 0:
            phase = "只还利息"
            current_payment = loan.principal * loan.annual_rate / 12
        else:
            elapsed_months = max(0, _month_distance(start_month, current_month))
            remaining_months = max(1, loan.remaining_months - elapsed_months)
            phase = "等额本金" if loan.repayment_method == "equal_principal" else "等额本息"
            current_payment = _amortized_monthly_payment(
                loan.principal,
                loan.annual_rate,
                remaining_months,
                loan.repayment_method,
            )

        summaries.append(
            PhasedLoanSummary(
                borrower=loan.borrower,
                name=loan.name,
                principal=round(loan.principal, 2),
                annual_rate=loan.annual_rate,
                repayment_method=loan.repayment_method,
                remaining_months=loan.remaining_months,
                interest_start_month=loan.interest_start_month,
                interest_only_until=loan.interest_only_until,
                phase=phase,
                current_monthly_payment=round(current_payment, 2),
            )
        )
    return summaries


def _phased_loan_state_at(
    loan: PhasedLoanData,
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> tuple[float, float]:
    if loan.principal <= 0:
        return 0.0, 0.0

    current = as_of or date.today()
    target_month = _month_after(current, max(0, months_from_now))
    start_month = _parse_month(loan.interest_start_month)
    interest_only_until = _parse_month(loan.interest_only_until)
    if start_month is None or interest_only_until is None:
        return loan.principal, 0.0

    if _month_distance(target_month, start_month) > 0:
        return loan.principal, 0.0

    monthly_rate = loan.annual_rate / 12
    if _month_distance(target_month, interest_only_until) >= 0:
        return loan.principal, loan.principal * monthly_rate

    interest_only_months = max(0, _month_distance(start_month, interest_only_until))
    amortization_months = max(1, loan.remaining_months - interest_only_months)
    elapsed_payments = max(0, _month_distance(interest_only_until, target_month))
    balance = _loan_balance_after_monthly_payments(
        loan.principal,
        loan.annual_rate,
        amortization_months,
        loan.repayment_method,
        elapsed_payments,
    )
    if balance <= 0:
        return 0.0, 0.0

    if loan.repayment_method == "equal_principal":
        payment = loan.principal / amortization_months + balance * monthly_rate
    else:
        payment = _equal_installment_monthly_payment(loan.principal, loan.annual_rate, amortization_months)
    return balance, payment


def calculate_car_loan(
    plan: CarPlanData,
    *,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
) -> CarLoanSummary:
    down_payment = max(0, plan.total_price * plan.down_payment_ratio)
    months_to_down: int | None
    if not plan.enabled or down_payment <= 0:
        months_to_down = 0
    elif initial_cash >= down_payment:
        months_to_down = 0
    elif monthly_cash_savings_before_car <= 0:
        months_to_down = None
    else:
        months_to_down = int((down_payment - initial_cash + monthly_cash_savings_before_car - 1) // monthly_cash_savings_before_car)
    if months_to_down is not None:
        months_to_down = max(plan.purchase_delay_months, months_to_down)

    if not plan.enabled or plan.total_price <= 0:
        operating_cost = _estimate_car_operating_cost(plan)
        return CarLoanSummary(
            enabled=False,
            total_price=round(plan.total_price, 2),
            down_payment_ratio=plan.down_payment_ratio,
            down_payment=round(down_payment, 2),
            purchase_delay_months=plan.purchase_delay_months,
            loan_principal=0,
            months_to_down_payment=months_to_down,
            years_to_down_payment=round(months_to_down / 12, 1) if months_to_down is not None else None,
            first_phase_monthly_payment=0,
            later_phase_monthly_payment=0,
            current_monthly_payment=0,
            total_interest=0,
            total_months=plan.total_months,
            interest_free_months=plan.interest_free_months,
            later_annual_rate=plan.later_annual_rate,
            **operating_cost,
        )

    total_months = max(1, plan.total_months)
    interest_free_months = max(0, min(plan.interest_free_months, total_months))
    later_months = max(0, total_months - interest_free_months)
    principal = max(0, plan.total_price - down_payment)
    principal_per_month = principal / total_months
    first_phase_monthly = principal_per_month if interest_free_months > 0 else 0
    remaining_principal = max(0, principal - principal_per_month * interest_free_months)

    if later_months > 0:
        monthly_rate = plan.later_annual_rate / 12
        if monthly_rate <= 0:
            later_monthly = remaining_principal / later_months
            later_total_interest = 0.0
        else:
            factor = (1 + monthly_rate) ** later_months
            later_monthly = remaining_principal * monthly_rate * factor / (factor - 1)
            later_total_interest = later_monthly * later_months - remaining_principal
    else:
        later_monthly = 0.0
        later_total_interest = 0.0

    current_month = max(1, min(plan.current_month_index, total_months))
    if plan.purchase_delay_months > 0:
        current_monthly = 0.0
    else:
        current_monthly = first_phase_monthly if current_month <= interest_free_months else later_monthly

    operating_cost = _estimate_car_operating_cost(plan)
    return CarLoanSummary(
        enabled=True,
        total_price=round(plan.total_price, 2),
        down_payment_ratio=plan.down_payment_ratio,
        down_payment=round(down_payment, 2),
        purchase_delay_months=plan.purchase_delay_months,
        loan_principal=round(principal, 2),
        months_to_down_payment=months_to_down,
        years_to_down_payment=round(months_to_down / 12, 1) if months_to_down is not None else None,
        first_phase_monthly_payment=round(first_phase_monthly, 2),
        later_phase_monthly_payment=round(later_monthly, 2),
        current_monthly_payment=round(current_monthly, 2),
        total_interest=round(later_total_interest, 2),
        total_months=total_months,
        interest_free_months=interest_free_months,
        later_annual_rate=plan.later_annual_rate,
        **operating_cost,
    )


def _estimate_car_operating_cost(plan: CarPlanData) -> dict[str, float]:
    monthly_energy = plan.annual_mileage_km / 100 * plan.electricity_kwh_per_100km * plan.electricity_price_per_kwh / 12
    annual_insurance = max(plan.annual_insurance_min, plan.total_price * plan.annual_insurance_rate)
    monthly_insurance = annual_insurance / 12
    monthly_maintenance = plan.annual_maintenance_cost / 12
    monthly_parking = plan.monthly_parking_cost
    monthly_cash = monthly_energy + monthly_insurance + monthly_maintenance + monthly_parking
    monthly_depreciation = plan.total_price / max(plan.depreciation_years, 1) / 12
    return {
        "monthly_energy_cost": round(monthly_energy, 2),
        "monthly_insurance_cost": round(monthly_insurance, 2),
        "monthly_maintenance_cost": round(monthly_maintenance, 2),
        "monthly_parking_cost": round(monthly_parking, 2),
        "monthly_cash_operating_cost": round(monthly_cash, 2),
        "monthly_depreciation_cost": round(monthly_depreciation, 2),
        "monthly_total_ownership_cost": round(monthly_cash + monthly_depreciation, 2),
    }


def _no_car_commute_cost(plan: CarPlanData) -> float:
    return max(0.0, plan.no_car_monthly_commute_cost)


def _second_car_plan(plan: CarPlanData) -> CarPlanData:
    return plan.model_copy(
        update={
            "enabled": plan.second_car_enabled and plan.second_car_total_price > 0,
            "name": "second_car",
            "selected_strategy_variant": "第二辆车",
            "total_price": plan.second_car_total_price,
            "down_payment_ratio": plan.second_car_down_payment_ratio,
            "down_payment": plan.second_car_total_price * plan.second_car_down_payment_ratio,
            "purchase_delay_months": plan.second_car_purchase_delay_months,
            "total_months": plan.second_car_total_months,
            "interest_free_months": min(plan.second_car_interest_free_months, plan.second_car_total_months),
            "later_annual_rate": plan.second_car_later_annual_rate,
            "annual_mileage_km": plan.second_car_annual_mileage_km,
            "monthly_parking_cost": plan.second_car_monthly_parking_cost,
        }
    )


def _car_monthly_cash_cost_without_annual(loan: CarLoanSummary) -> float:
    return max(0.0, loan.monthly_energy_cost + loan.monthly_parking_cost)


def _car_annual_cash_cost_at(
    loan: CarLoanSummary,
    plan: CarPlanData,
    month: int,
    purchase_month: int | None,
) -> float:
    if purchase_month is None:
        return 0.0
    owning_year = max(0, (month - purchase_month) // 12)
    insurance_growth = (1 + max(0.0, plan.annual_insurance_growth_rate)) ** owning_year
    maintenance_growth = (1 + max(0.0, plan.annual_maintenance_growth_rate)) ** owning_year
    annual_insurance = max(0.0, loan.monthly_insurance_cost * 12) * insurance_growth
    annual_maintenance = max(0.0, loan.monthly_maintenance_cost * 12) * maintenance_growth
    return annual_insurance + annual_maintenance


def _is_car_annual_cost_month(month: int, purchase_month: int | None) -> bool:
    if purchase_month is None or month < purchase_month:
        return False
    return (month - purchase_month) % 12 == 0


def _car_monthly_cash_cost_at(plan: CarPlanData, car_loan: CarLoanSummary, month: int) -> float:
    no_car_commute = _no_car_commute_cost(plan)
    first_purchase_month = (
        (car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else plan.purchase_delay_months)
        if plan.enabled and car_loan.enabled
        else None
    )
    if first_purchase_month is None:
        base_cost = no_car_commute
    elif month < first_purchase_month:
        base_cost = no_car_commute
    else:
        month_after_car = month - first_purchase_month
        payment = 0.0
        if 0 < month_after_car <= car_loan.total_months:
            payment = (
                car_loan.first_phase_monthly_payment
                if month_after_car <= car_loan.interest_free_months
                else car_loan.later_phase_monthly_payment
            )
        annual_cost = (
            _car_annual_cash_cost_at(car_loan, plan, month, first_purchase_month)
            if _is_car_annual_cost_month(month, first_purchase_month)
            else 0.0
        )
        base_cost = payment + _car_monthly_cash_cost_without_annual(car_loan) + annual_cost

    second_plan = _second_car_plan(plan)
    if not second_plan.enabled:
        return base_cost
    second_loan = calculate_car_loan(second_plan)
    second_purchase_month = (
        second_loan.months_to_down_payment if second_loan.months_to_down_payment is not None else second_plan.purchase_delay_months
    ) if second_loan.enabled else None
    if second_purchase_month is None or month < second_purchase_month:
        return base_cost
    month_after_second = month - second_purchase_month
    second_payment = 0.0
    if 0 < month_after_second <= second_loan.total_months:
        second_payment = (
            second_loan.first_phase_monthly_payment
            if month_after_second <= second_loan.interest_free_months
            else second_loan.later_phase_monthly_payment
        )
    second_annual_cost = (
        _car_annual_cash_cost_at(second_loan, second_plan, month, second_purchase_month)
        if _is_car_annual_cost_month(month, second_purchase_month)
        else 0.0
    )
    return base_cost + second_payment + _car_monthly_cash_cost_without_annual(second_loan) + second_annual_cost


def _car_down_payment_at(plan: CarPlanData, car_loan: CarLoanSummary, month: int) -> float:
    total = 0.0
    first_purchase_month = car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else plan.purchase_delay_months
    if plan.enabled and car_loan.enabled and first_purchase_month == month:
        total += car_loan.down_payment
    second_plan = _second_car_plan(plan)
    if second_plan.enabled:
        second_loan = calculate_car_loan(second_plan)
        second_purchase_month = (
            second_loan.months_to_down_payment
            if second_loan.months_to_down_payment is not None
            else second_plan.purchase_delay_months
        )
        if second_loan.enabled and second_purchase_month == month:
            total += second_loan.down_payment
    return total


def _vehicle_asset_value_at(price: float, depreciation_years: int, purchase_month: int | None, month: int) -> float:
    if purchase_month is None or month < purchase_month or price <= 0:
        return 0.0
    depreciation_months = max(12, depreciation_years * 12)
    age_months = max(0, month - purchase_month)
    return max(0.0, price * (1 - age_months / depreciation_months))


def _vehicle_cash_components_at(
    loan: CarLoanSummary,
    plan: CarPlanData,
    month: int,
    purchase_month: int | None,
) -> dict[str, float]:
    if purchase_month is None or month < purchase_month:
        return {
            "payment": 0.0,
            "energy": 0.0,
            "insurance": 0.0,
            "maintenance": 0.0,
            "parking": 0.0,
        }
    elapsed = month - purchase_month
    payment = 0.0
    if 0 < elapsed <= loan.total_months:
        payment = (
            loan.first_phase_monthly_payment
            if elapsed <= loan.interest_free_months
            else loan.later_phase_monthly_payment
        )
    annual_cost = (
        _car_annual_cash_cost_at(loan, plan, month, purchase_month)
        if _is_car_annual_cost_month(month, purchase_month)
        else 0.0
    )
    base_annual = max(0.0, loan.monthly_insurance_cost * 12) + max(0.0, loan.monthly_maintenance_cost * 12)
    insurance = 0.0
    maintenance = 0.0
    if annual_cost > 0 and base_annual > 0:
        insurance = annual_cost * max(0.0, loan.monthly_insurance_cost * 12) / base_annual
        maintenance = annual_cost - insurance
    return {
        "payment": payment,
        "energy": loan.monthly_energy_cost,
        "insurance": insurance,
        "maintenance": maintenance,
        "parking": loan.monthly_parking_cost,
    }


def _car_down_payment_components_at(plan: CarPlanData, car_loan: CarLoanSummary, month: int) -> tuple[float, float]:
    first = 0.0
    second = 0.0
    first_purchase_month = car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else plan.purchase_delay_months
    if plan.enabled and car_loan.enabled and first_purchase_month == month:
        first = car_loan.down_payment
    second_plan = _second_car_plan(plan)
    if second_plan.enabled:
        second_loan = calculate_car_loan(second_plan)
        second_purchase_month = (
            second_loan.months_to_down_payment
            if second_loan.months_to_down_payment is not None
            else second_plan.purchase_delay_months
        )
        if second_loan.enabled and second_purchase_month == month:
            second = second_loan.down_payment
    return first, second


def _months_until_cash_target(initial_cash: float, monthly_savings: float, target_cash: float, max_months: int = 120) -> int | None:
    if target_cash <= initial_cash:
        return 0
    if monthly_savings <= 0:
        return None
    months = int((target_cash - initial_cash + monthly_savings - 1) // monthly_savings)
    return months if months <= max_months else None


def _clamp_score(value: float, low: float = 0, high: float = 10) -> float:
    return max(low, min(high, value))


def _ratio_score(value: float, target: float) -> float:
    if target <= 0:
        return 10
    return _clamp_score(value / target * 10)


def _cash_flow_score(monthly_cash_flow: float, monthly_expense: float) -> float:
    if monthly_expense <= 0:
        return 10 if monthly_cash_flow >= 0 else 0
    return _clamp_score(5 + monthly_cash_flow / monthly_expense * 5)


def _dti_score(debt_to_income_ratio: float) -> float:
    if debt_to_income_ratio <= 0.35:
        return 10
    if debt_to_income_ratio >= 0.65:
        return 0
    return _clamp_score(10 - (debt_to_income_ratio - 0.35) / 0.30 * 10)


def _wait_score(months: int | None, max_comfort_months: int) -> float:
    if months is None:
        return 0
    if months <= 0:
        return 10
    return _clamp_score(10 - months / max(max_comfort_months, 1) * 10)


def build_car_plan_analyses(
    household: HouseholdData,
    *,
    net_monthly_income: float,
) -> list[CarPlanAnalysis]:
    plan = household.car_plan
    if not plan.enabled or plan.total_price <= 0:
        return []

    initial_cash = household.liquid_assets + household.investments
    current_monthly_expense = monthly_household_expense_at(household)
    monthly_savings_before_transport = max(
        0,
        net_monthly_income - current_monthly_expense - household.monthly_debt_payment,
    )
    no_car_commute = _no_car_commute_cost(plan)
    monthly_savings_before_car = max(0, monthly_savings_before_transport - no_car_commute)
    required_reserve = current_monthly_expense * household.required_liquidity_months
    high_down_ratio = min(1.0, max(plan.down_payment_ratio, 0.50))
    low_down_ratio = min(1.0, min(plan.down_payment_ratio, 0.15))
    delayed_down_ratio = min(1.0, max(plan.down_payment_ratio, 0.20))
    delay_months = max(plan.purchase_delay_months, 12)
    specs = [
        ("按目标设置", "完全按上方买车目标测算，用来直接观察手动修改后的效果。", plan.down_payment_ratio, plan.purchase_delay_months, plan.total_months, plan.interest_free_months, plan.later_annual_rate),
        ("全款", "不背车贷，现金压力最大，但买后月现金流最干净。", 1.0, plan.purchase_delay_months, 1, 0, 0.0),
        ("高首付低贷", "按主流电车 50% 左右首付、短周期低息方案测算，降低车贷月供。", high_down_ratio, plan.purchase_delay_months, 36, 24, min(plan.later_annual_rate, 0.0199)),
        ("低首付保现金", "按 15%-20% 低首付、60 期方案测算，把现金优先留给购房安全垫。", low_down_ratio, plan.purchase_delay_months, 60, 24, plan.later_annual_rate),
        ("延后买车", "先把现金留给购房，至少延后一年再执行低首付长贷方案。", delayed_down_ratio, delay_months, 60, 24, plan.later_annual_rate),
    ]

    analyses: list[CarPlanAnalysis] = []
    for variant, description, down_ratio, purchase_delay, total_months, interest_free_months, later_rate in specs:
        strategy_plan = plan.model_copy(
            update={
                "enabled": True,
                "down_payment_ratio": down_ratio,
                "down_payment": plan.total_price * down_ratio,
                "purchase_delay_months": purchase_delay,
                "total_months": total_months,
                "interest_free_months": min(interest_free_months, total_months),
                "later_annual_rate": later_rate,
            }
        )
        loan = calculate_car_loan(
            strategy_plan,
            initial_cash=initial_cash,
            monthly_cash_savings_before_car=monthly_savings_before_car,
        )
        required_cash = loan.down_payment + required_reserve
        cash_ready_month = _months_until_cash_target(initial_cash, monthly_savings_before_car, required_cash)
        if cash_ready_month is None:
            months_to_buy = None
            cash_after_purchase = initial_cash - loan.down_payment
        else:
            months_to_buy = max(purchase_delay, cash_ready_month)
            cash_after_purchase = initial_cash + monthly_savings_before_car * months_to_buy - loan.down_payment
        expected_payment = loan.first_phase_monthly_payment if loan.interest_free_months > 0 else loan.later_phase_monthly_payment
        monthly_after_car = monthly_savings_before_transport - expected_payment - loan.monthly_cash_operating_cost
        debt_burden_score = _clamp_score(10 - expected_payment / max(net_monthly_income, 1) / 0.18 * 10)
        total_cost_score = _clamp_score(10 - loan.monthly_total_ownership_cost / max(net_monthly_income, 1) / 0.16 * 10)
        happiness_score = (
            plan.happiness_score * 0.28
            + _ratio_score(cash_after_purchase, required_reserve) * 0.22
            + _cash_flow_score(monthly_after_car, current_monthly_expense) * 0.20
            + debt_burden_score * 0.12
            + total_cost_score * 0.08
            + _wait_score(months_to_buy, 24) * 0.10
        )
        notes = [
            f"首付比例 {down_ratio:.0%}",
            f"现金养车约 {round(loan.monthly_cash_operating_cost)} 元/月",
            f"含折旧总成本约 {round(loan.monthly_total_ownership_cost)} 元/月",
            "全款无贷款" if loan.loan_principal == 0 else f"{loan.interest_free_months} 期 0 息 / 共 {loan.total_months} 期",
            "买车后无车贷月供" if loan.loan_principal == 0 else f"贷款本金 {round(loan.loan_principal)}",
            "手动目标反馈" if variant == "按目标设置" else "保留购房现金优先" if variant in {"低首付保现金", "延后买车"} else "降低长期车贷压力",
        ]
        analyses.append(
            CarPlanAnalysis(
                variant=variant,
                description=description,
                purchase_delay_months=purchase_delay,
                months_to_buy=months_to_buy,
                years_to_buy=round(months_to_buy / 12, 1) if months_to_buy is not None else None,
                total_price=round(plan.total_price, 2),
                down_payment_ratio=down_ratio,
                down_payment=loan.down_payment,
                loan_principal=loan.loan_principal,
                total_months=loan.total_months,
                interest_free_months=loan.interest_free_months,
                later_annual_rate=loan.later_annual_rate,
                first_phase_monthly_payment=loan.first_phase_monthly_payment,
                later_phase_monthly_payment=loan.later_phase_monthly_payment,
                expected_monthly_payment_after_purchase=round(expected_payment, 2),
                total_interest=loan.total_interest,
                required_cash_at_purchase=round(required_cash, 2),
                cash_after_purchase=round(cash_after_purchase, 2),
                monthly_cash_flow_after_car=round(monthly_after_car, 2),
                operating_cost=loan.monthly_cash_operating_cost,
                monthly_energy_cost=loan.monthly_energy_cost,
                monthly_insurance_cost=loan.monthly_insurance_cost,
                monthly_maintenance_cost=loan.monthly_maintenance_cost,
                monthly_parking_cost=loan.monthly_parking_cost,
                monthly_cash_operating_cost=loan.monthly_cash_operating_cost,
                monthly_depreciation_cost=loan.monthly_depreciation_cost,
                monthly_total_ownership_cost=loan.monthly_total_ownership_cost,
                happiness_score=round(_clamp_score(happiness_score), 2),
                notes=notes,
            )
        )
    return analyses


def _future_cash_value(initial_cash: float, monthly_savings: float, annual_return: float, months: int) -> float:
    monthly_return = annual_return / 12
    value = initial_cash
    for _ in range(months):
        value = value * (1 + monthly_return) + monthly_savings
    return value


def _future_cash_value_with_schedule(
    initial_cash: float,
    annual_return: float,
    months: int,
    monthly_savings_at: Callable[[int], float],
    buy_fee_rate: float = 0.0,
) -> float:
    monthly_return = annual_return / 12
    value = initial_cash
    fee_rate = _clamp(buy_fee_rate, 0.0, 0.05)
    for month in range(1, months + 1):
        monthly_savings = monthly_savings_at(month)
        net_savings = monthly_savings * (1 - fee_rate) if monthly_savings > 0 else monthly_savings
        value = value * (1 + monthly_return) + net_savings
    return value


def _future_pf_value(initial_balance: float, monthly_net_growth: float, annual_interest_rate: float, months: int) -> float:
    monthly_rate = max(0, annual_interest_rate) / 12
    value = max(0, initial_balance)
    for _ in range(months):
        value = value * (1 + monthly_rate) + monthly_net_growth
    return max(0, value)


def _future_pf_value_with_schedule(
    initial_balance: float,
    annual_interest_rate: float,
    months: int,
    monthly_net_growth_at: Callable[[int], float],
) -> float:
    monthly_rate = max(0, annual_interest_rate) / 12
    value = max(0, initial_balance)
    for month in range(1, months + 1):
        value = max(0, value * (1 + monthly_rate) + monthly_net_growth_at(month))
    return max(0, value)


def _min_down_payment_ratio(household: HouseholdData, uses_provident_loan: bool, rules: RulePackData) -> float:
    return get_policy(rules).minimum_down_payment_ratio(household, uses_provident_loan=uses_provident_loan)


def _provident_policy_bonus(scenario: ScenarioData, rules: RulePackData) -> float:
    return get_policy(rules).provident_policy_bonus(scenario)


def _provident_loan_cap(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    purchase_months: int = 0,
    monthly_income_for_capacity: float = 0.0,
    borrower_count: int = 1,
) -> tuple[float, float]:
    amount_per_year = float(rules.params.get("provident_loan_amount_per_deposit_year", 150_000))
    effective_deposit_months = household.social_security_months + max(0, purchase_months)
    deposit_years = ceil(effective_deposit_months / 12) if effective_deposit_months > 0 else 0
    policy_year_cap = amount_per_year * deposit_years
    if household.existing_home_count == 0:
        base_maximum_cap = float(rules.params.get("provident_first_home_loan_cap", 1_200_000))
    else:
        base_maximum_cap = float(rules.params.get("provident_second_home_loan_cap", 1_000_000))
    bonus = _provident_policy_bonus(scenario, rules)
    cap = min(base_maximum_cap + bonus, policy_year_cap + bonus)
    if bool(rules.params.get("provident_repayment_capacity_enabled", True)) and monthly_income_for_capacity > 0:
        income_ratio = _clamp(float(rules.params.get("provident_repayment_income_ratio", 0.60)), 0.0, 1.0)
        basic_living_cost = max(0.0, float(rules.params.get("provident_basic_living_cost_per_person", 1778)))
        family_living_floor = basic_living_cost * max(1, borrower_count)
        payment_cap = min(
            monthly_income_for_capacity * income_ratio,
            max(0.0, monthly_income_for_capacity - family_living_floor),
        )
        capacity_cap = _loan_principal_for_payment_cap(
            payment_cap,
            scenario.provident_rate,
            _provident_loan_years(household, scenario, rules)[0],
            _provident_repayment_method(scenario),
        )
        cap = min(cap, capacity_cap)
    return cap, bonus


def _is_second_hand_property(scenario: ScenarioData) -> bool:
    return "二手" in scenario.property_type


def _is_new_home_property(scenario: ScenarioData) -> bool:
    return "新房" in scenario.property_type


def _provident_loan_years(household: HouseholdData, scenario: ScenarioData, rules: RulePackData) -> tuple[int, list[str]]:
    return get_policy(rules).provident_loan_years(household, scenario)


def _months_until_purchase(
    *,
    upfront_cash_required: float,
    planned_down_payment: float,
    household: HouseholdData,
    initial_cash: float,
    monthly_cash_savings: float,
    monthly_pf_net_growth: float,
    annual_return: float,
    required_liquidity_reserve: float,
    max_months: int = 360,
) -> tuple[int | None, float, float, float]:
    for months in range(max_months + 1):
        cash_value = _future_cash_value(initial_cash, monthly_cash_savings, annual_return, months)
        pf_available = max(
            0,
            household.provident_fund_balance + monthly_pf_net_growth * months,
        )
        pf_extractable = min(pf_available, planned_down_payment)
        required_cash_after_pf = max(0, upfront_cash_required - pf_extractable)
        if cash_value >= required_cash_after_pf + required_liquidity_reserve:
            return (
                months,
                round(pf_extractable, 2),
                round(cash_value - required_cash_after_pf, 2),
                round(pf_available - pf_extractable, 2),
            )
    final_cash = _future_cash_value(initial_cash, monthly_cash_savings, annual_return, max_months)
    final_pf = max(0, household.provident_fund_balance + monthly_pf_net_growth * max_months)
    final_extract = min(final_pf, planned_down_payment)
    return None, round(final_extract, 2), round(final_cash - max(0, upfront_cash_required - final_extract), 2), round(final_pf - final_extract, 2)


def _purchase_cash_state_at_month(
    *,
    month: int,
    upfront_cash_required: float,
    planned_down_payment: float,
    household: HouseholdData,
    rules: RulePackData,
    initial_cash: float,
    monthly_cash_savings: float,
    monthly_cash_savings_at: Callable[[int], float] | None = None,
    monthly_pf_net_growth: float,
    monthly_pf_net_growth_at: Callable[[int], float] | None = None,
    annual_return: float,
    property_price: float,
    scenario: ScenarioData,
    cash_value_by_month: list[float] | None = None,
    pf_value_by_month: list[float] | None = None,
) -> tuple[float, float, float, float, float, float]:
    buy_fee_rate = _clamp(household.investment_buy_fee_rate, 0.0, 0.05)
    sell_fee_rate = _clamp(household.investment_sell_fee_rate, 0.0, 0.05)
    cash_value = (
        cash_value_by_month[month]
        if cash_value_by_month is not None and month < len(cash_value_by_month)
        else (
            _future_cash_value_with_schedule(initial_cash, annual_return, month, monthly_cash_savings_at, buy_fee_rate)
            if monthly_cash_savings_at is not None
            else _future_cash_value(initial_cash, monthly_cash_savings, annual_return, month)
        )
    )
    if cash_value > 0 and household.investment_plan_name != "cash_only":
        cash_value *= 1 - sell_fee_rate
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_available = (
        pf_value_by_month[month]
        if pf_value_by_month is not None and month < len(pf_value_by_month)
        else (
            _future_pf_value_with_schedule(
                household.provident_fund_balance,
                pf_interest_rate,
                month,
                monthly_pf_net_growth_at,
            )
            if monthly_pf_net_growth_at is not None
            else _future_pf_value(
                household.provident_fund_balance,
                monthly_pf_net_growth,
                pf_interest_rate,
                month,
            )
        )
    )
    default_upfront_ratio = float(rules.params.get("provident_upfront_purchase_extract_ratio", 0.0))
    if _is_second_hand_property(scenario):
        upfront_ratio_key = "provident_upfront_purchase_extract_ratio_second_hand"
        ratio_fallback = 0.0
    elif _is_new_home_property(scenario):
        upfront_ratio_key = "provident_upfront_purchase_extract_ratio_new_home"
        ratio_fallback = 1.0
    else:
        upfront_ratio_key = "provident_upfront_purchase_extract_ratio"
        ratio_fallback = default_upfront_ratio
    upfront_extract_ratio = max(
        0,
        min(1, float(rules.params.get(upfront_ratio_key, ratio_fallback))),
    )
    post_transaction_extract_ratio = max(
        0,
        min(1, float(rules.params.get("provident_post_transaction_extract_ratio", 1.0))),
    )
    pf_upfront_extractable = min(pf_available, planned_down_payment * upfront_extract_ratio)
    family_pf_upfront_extractable = _family_down_payment_upfront_support(
        household,
        scenario,
        month,
        max(0.0, upfront_cash_required - pf_upfront_extractable),
    )
    required_cash_after_pf = max(0, upfront_cash_required - pf_upfront_extractable - family_pf_upfront_extractable)
    cash_after_transaction = cash_value - required_cash_after_pf
    pf_after_upfront_extract = max(0, pf_available - pf_upfront_extractable)
    pf_post_transaction_extractable = min(pf_after_upfront_extract, property_price * post_transaction_extract_ratio)
    return (
        round(pf_upfront_extractable, 2),
        round(family_pf_upfront_extractable, 2),
        round(pf_post_transaction_extractable, 2),
        round(cash_after_transaction, 2),
        round(cash_after_transaction + pf_post_transaction_extractable, 2),
        round(pf_after_upfront_extract - pf_post_transaction_extractable, 2),
    )


def _family_down_payment_support_mode(household: HouseholdData) -> str:
    mode = str(getattr(household, "family_down_payment_support_mode", "provident") or "provident")
    return mode if mode in {"provident", "savings"} else "provident"


def _family_down_payment_support_label(household: HouseholdData) -> str:
    if not household.family_provident_support_enabled:
        return ""
    configured = (household.family_provident_support_label or "").strip()
    if configured:
        return configured
    return "亲属积蓄首付支持" if _family_down_payment_support_mode(household) == "savings" else "亲属异地公积金首付支持"


def _family_down_payment_upfront_support(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_month: int,
    remaining_upfront_cash_required: float,
) -> float:
    if not household.family_provident_support_enabled:
        return 0.0
    if remaining_upfront_cash_required <= 0:
        return 0.0
    if _family_down_payment_support_mode(household) == "savings":
        return round(min(max(0.0, household.family_savings_support_amount), remaining_upfront_cash_required), 2)
    if not _is_new_home_property(scenario):
        return 0.0
    monthly_deposit = max(0.0, household.family_provident_monthly_salary * household.family_provident_total_rate)
    available_balance = max(0.0, household.family_provident_initial_balance + monthly_deposit * max(0, purchase_month))
    return round(min(available_balance, remaining_upfront_cash_required), 2)


def _rent_withdrawal_before_purchase(household: HouseholdData) -> float:
    if household.existing_home_count > 0:
        return 0.0
    return max(0.0, household.monthly_rent_from_housing_fund)


def _quarterly_rent_withdrawal_before_purchase_at(household: HouseholdData, month: int) -> float:
    monthly_withdrawal = _rent_withdrawal_before_purchase(household)
    if monthly_withdrawal <= 0 or month <= 0 or month % 3 != 0:
        return 0.0
    return monthly_withdrawal * 3


def _post_purchase_monthly_pf_withdrawal(
    *,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
) -> tuple[float, str]:
    if not bool(rules.params.get("provident_post_purchase_cashflow_enabled", False)):
        return 0.0, "kept_in_account"
    if not bool(rules.params.get("provident_monthly_withdrawal_after_purchase_enabled", False)):
        return 0.0, "kept_in_account"
    mode = str(rules.params.get("provident_post_purchase_withdrawal_mode", "purchase_agreed"))
    if mode == "loan_offset":
        return min(monthly_pf_deposit, provident_monthly_payment), mode
    return monthly_pf_deposit, "purchase_agreed"


def _is_beijing_pf_offset_month(months_from_now: int, *, as_of: date | None = None) -> bool:
    current = as_of or date.today()
    target = _add_months(date(current.year, current.month, 1), max(0, months_from_now))
    return target.month in {1, 7}


def _semiannual_loan_offset_monthly_equivalent(
    *,
    purchase_month: int,
    starting_pf_balance: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
    horizon_months: int = 12,
    as_of: date | None = None,
) -> float:
    if monthly_pf_deposit <= 0 or provident_monthly_payment <= 0:
        return 0.0
    pf_balance = max(0.0, starting_pf_balance)
    retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_rate = max(0.0, pf_interest_rate) / 12
    total_cash_relief = 0.0
    for offset in range(1, horizon_months + 1):
        absolute_month = purchase_month + offset
        pf_balance += pf_balance * pf_monthly_rate + monthly_pf_deposit
        if not _is_beijing_pf_offset_month(absolute_month, as_of=as_of):
            continue
        available = max(0.0, pf_balance - retained_balance)
        if available < provident_monthly_payment:
            continue
        cash_relief = min(available, provident_monthly_payment)
        pf_balance -= cash_relief
        total_cash_relief += cash_relief
    return total_cash_relief / max(1, horizon_months)


def _post_purchase_pf_strategy(
    *,
    purchase_month: int,
    starting_pf_balance: float,
    free_cash_flow: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    total_monthly_payment: float,
    post_purchase_monthly_expense: float,
    rules: RulePackData,
) -> tuple[float, str]:
    strategy_mode = str(rules.params.get("provident_post_purchase_strategy_mode", "auto"))
    manual_enabled = bool(rules.params.get("provident_post_purchase_cashflow_enabled", False)) and bool(
        rules.params.get("provident_monthly_withdrawal_after_purchase_enabled", False)
    )
    if strategy_mode == "manual":
        return _post_purchase_monthly_pf_withdrawal(
            monthly_pf_deposit=monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            rules=rules,
        )
    if strategy_mode == "keep_in_account":
        return 0.0, "kept_in_account"
    if strategy_mode == "loan_offset":
        monthly_equivalent = _semiannual_loan_offset_monthly_equivalent(
            purchase_month=purchase_month,
            starting_pf_balance=starting_pf_balance,
            monthly_pf_deposit=monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            rules=rules,
        )
        if monthly_equivalent <= 0:
            return 0.0, "kept_in_account"
        return monthly_equivalent, "loan_offset_semiannual"
    if strategy_mode == "purchase_agreed":
        if monthly_pf_deposit <= 0:
            return 0.0, "kept_in_account"
        return monthly_pf_deposit, "purchase_agreed"

    # Auto mode: compare the default account-retention strategy with policy-sensitive
    # post-purchase options. Prefer loan offset only when it materially improves the
    # household cash-pressure picture; keep deposits in the account when cash flow is
    # already comfortable or there is no provident loan to offset.
    loan_offset_improvement = _semiannual_loan_offset_monthly_equivalent(
        purchase_month=purchase_month,
        starting_pf_balance=starting_pf_balance,
        monthly_pf_deposit=monthly_pf_deposit,
        provident_monthly_payment=provident_monthly_payment,
        rules=rules,
    )
    if provident_monthly_payment > 0 and loan_offset_improvement > 0:
        pressure_ratio = total_monthly_payment / max(1.0, total_monthly_payment + post_purchase_monthly_expense)
        near_cash_tension = free_cash_flow < post_purchase_monthly_expense * 0.25
        material_payment_share = loan_offset_improvement >= max(500.0, total_monthly_payment * 0.08)
        if free_cash_flow < 0 or (near_cash_tension and material_payment_share) or pressure_ratio > 0.55:
            return loan_offset_improvement, "loan_offset_semiannual_auto"

    if manual_enabled:
        return _post_purchase_monthly_pf_withdrawal(
            monthly_pf_deposit=monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            rules=rules,
        )
    return 0.0, "kept_in_account"


def _post_purchase_pf_withdrawal_label(mode: str) -> str:
    labels = {
        "kept_in_account": "默认留存在公积金账户",
        "purchase_agreed": "显式开启后按购房约定提取估算",
        "loan_offset": "显式开启后按公积金贷款冲还贷估算",
        "loan_offset_semiannual": "显式开启后按北京半年度冲还贷估算",
        "loan_offset_semiannual_auto": "自动选择北京半年度公积金贷款冲还贷",
    }
    return labels.get(mode, "默认留存在公积金账户")


def _post_purchase_cash_stress(
    *,
    household: HouseholdData,
    rules: RulePackData,
    purchase_month: int,
    starting_cash: float,
    starting_pf_balance: float,
    total_monthly_payment: float,
    provident_monthly_payment: float,
    car_loan: CarLoanSummary,
    expense_at_month: Callable[[int], float],
    income_at_month: Callable[[int], MonthlyIncomeProfile],
    car_monthly_cash_cost_at: Callable[[int], float],
    horizon_months: int = 120,
) -> tuple[float, int | None, bool]:
    cash_balance = starting_cash
    pf_balance = max(0.0, starting_pf_balance)
    minimum_cash = cash_balance
    minimum_month: int | None = purchase_month
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_rate = max(0.0, pf_interest_rate) / 12

    for absolute_month in range(purchase_month + 1, purchase_month + horizon_months + 1):
        income = income_at_month(absolute_month)
        pf_balance += pf_balance * pf_monthly_rate + income.monthly_pf_deposit
        free_cash_flow = (
            income.net_income
            - expense_at_month(absolute_month)
            - household.monthly_debt_payment
            - car_monthly_cash_cost_at(absolute_month)
            - total_monthly_payment
        )
        monthly_pf_withdrawal, pf_strategy_mode = _post_purchase_pf_strategy(
            purchase_month=purchase_month,
            starting_pf_balance=starting_pf_balance,
            free_cash_flow=free_cash_flow,
            monthly_pf_deposit=income.monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            total_monthly_payment=total_monthly_payment,
            post_purchase_monthly_expense=expense_at_month(absolute_month),
            rules=rules,
        )
        if "loan_offset" in pf_strategy_mode:
            retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
            available = max(0.0, pf_balance - retained_balance)
            pf_withdrawal = (
                min(available, provident_monthly_payment)
                if _is_beijing_pf_offset_month(absolute_month) and available >= provident_monthly_payment
                else 0.0
            )
        else:
            pf_withdrawal = min(pf_balance, monthly_pf_withdrawal)
        pf_balance -= pf_withdrawal
        monthly_cash_delta = free_cash_flow + pf_withdrawal
        monthly_cash_delta -= _car_down_payment_at(household.car_plan, car_loan, absolute_month)
        cash_balance += monthly_cash_delta
        if cash_balance < minimum_cash:
            minimum_cash = cash_balance
            minimum_month = absolute_month
        if cash_balance < 0:
            return round(minimum_cash, 2), minimum_month, False

    return round(minimum_cash, 2), minimum_month, minimum_cash >= 0


def build_purchase_plan_analyses(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    tax_summaries: list[TaxMemberSummary],
    net_monthly_income: float,
    car_loan: CarLoanSummary,
    taxes_and_fees: float,
) -> list[PurchasePlanAnalysis]:
    price = scenario.total_price
    provident_loan_years, provident_year_reasons = _provident_loan_years(household, scenario, rules)
    micro_default_ratio = _clamp(float(rules.params.get("micro_commercial_loan_ratio", 0.05)), 0, 1)
    micro_min_ratio = _clamp(
        float(rules.params.get("micro_commercial_loan_ratio_min", min(0.02, micro_default_ratio))),
        0,
        1,
    )
    micro_max_ratio = _clamp(
        float(rules.params.get("micro_commercial_loan_ratio_max", max(0.12, micro_default_ratio))),
        micro_min_ratio,
        1,
    )
    manual_micro_ratio = _clamp(scenario.micro_commercial_loan_ratio, 0, 1)
    if manual_micro_ratio > 0:
        micro_ratio_candidates = [manual_micro_ratio]
    else:
        ratio_steps = max(1, int(round((micro_max_ratio - micro_min_ratio) / 0.01)))
        micro_ratio_candidates = sorted(
            {
                round(micro_min_ratio + (micro_max_ratio - micro_min_ratio) * index / ratio_steps, 4)
                for index in range(ratio_steps + 1)
            }
            | {micro_min_ratio, micro_default_ratio, micro_max_ratio}
        )
    current_monthly_expense = monthly_household_expense_at(household)
    monthly_expense_cache = {0: current_monthly_expense}
    monthly_income_cache: dict[int, MonthlyIncomeProfile] = {}

    def expense_at_month(month: int) -> float:
        if month not in monthly_expense_cache:
            monthly_expense_cache[month] = monthly_household_expense_at(household, month)
        return monthly_expense_cache[month]

    def income_at_month(month: int) -> MonthlyIncomeProfile:
        if month not in monthly_income_cache:
            monthly_income_cache[month] = household_monthly_income_profile_at(household, rules, month)
        return monthly_income_cache[month]

    required_liquidity_reserve = max(0, current_monthly_expense * household.required_liquidity_months)
    monthly_pf_deposit = income_at_month(0).monthly_pf_deposit or sum(
        item.monthly_personal_housing_fund + item.monthly_employer_housing_fund
        for item in tax_summaries
    )
    monthly_pf_net_growth = monthly_pf_deposit - _rent_withdrawal_before_purchase(household)
    car_purchase_month = car_loan.months_to_down_payment if household.car_plan.enabled and car_loan.enabled else None
    initial_car_down_payment = _car_down_payment_at(household.car_plan, car_loan, 0)
    initial_cash = max(0, household.liquid_assets + household.investments - initial_car_down_payment)

    def monthly_pf_net_growth_at(month: int) -> float:
        return income_at_month(month).monthly_pf_deposit - _quarterly_rent_withdrawal_before_purchase_at(household, month)

    def car_monthly_cash_cost_at(month: int) -> float:
        return _car_monthly_cash_cost_at(household.car_plan, car_loan, month)

    def monthly_cash_savings_at(month: int) -> float:
        savings = (
            income_at_month(month).net_income
            + _quarterly_rent_withdrawal_before_purchase_at(household, month)
            - expense_at_month(month)
            - household.monthly_debt_payment
            - car_monthly_cash_cost_at(month)
        )
        if month > 0:
            savings -= _car_down_payment_at(household.car_plan, car_loan, month)
        return savings

    monthly_cash_savings = monthly_cash_savings_at(0)
    buy_fee_rate = _clamp(household.investment_buy_fee_rate, 0.0, 0.05)
    monthly_return = scenario.annual_investment_return / 12
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_return = max(0.0, pf_interest_rate) / 12
    cash_value_by_month = [initial_cash]
    pf_value_by_month = [max(0.0, household.provident_fund_balance)]
    for month_index in range(1, 361):
        monthly_savings = monthly_cash_savings_at(month_index)
        net_savings = monthly_savings * (1 - buy_fee_rate) if monthly_savings > 0 else monthly_savings
        cash_value_by_month.append(cash_value_by_month[-1] * (1 + monthly_return) + net_savings)
        pf_value_by_month.append(
            max(0.0, pf_value_by_month[-1] * (1 + pf_monthly_return) + monthly_pf_net_growth_at(month_index))
        )

    variant_specs = [
        ("手动指定", "按当前目标里手动填写的首付、商贷和公积金贷生成，超出政策或价格约束时自动校正。", 0.0, False, True, False),
        ("0商贷", "公积金贷优先，目标把商贷压到 0。", 0.0, False, False, False),
        (
            "微量商贷",
            "以加快买房速度为目标，在微量商贷比例范围内自动选择最少商贷；若房源目标填写了手动比例，则按手动比例测算。",
            price * micro_default_ratio,
            False,
            False,
            True,
        ),
        ("较多商贷", "按北京最低首付测算，剩余贷款优先公积金后商贷。", 0.0, True, False, False),
    ]

    analyses: list[PurchasePlanAnalysis] = []
    for name, description, target_commercial, use_min_down, use_manual_mix, use_micro_strategy in variant_specs:
        provident_cap = 0.0
        provident_policy_bonus = 0.0
        min_down_payment = 0.0
        planned_down = 0.0
        commercial_loan = 0.0
        provident_loan = 0.0
        upfront_cash = 0.0
        months: int | None = 0
        minimum_cash_balance = 0.0
        minimum_cash_balance_month: int | None = 0
        cash_stress_ok = True
        cash_stress_shortfall = 0.0
        pf_upfront_extractable = 0.0
        family_pf_upfront_extractable = 0.0
        pf_post_transaction_extractable = 0.0
        pf_extractable = 0.0
        cash_after_transaction = 0.0
        cash_after_purchase = 0.0
        pf_after_extract = 0.0

        def compute_mix(
            purchase_months: int,
            commercial_target: float = target_commercial,
        ) -> tuple[float, float, float, float, float, float, float]:
            cap, bonus = _provident_loan_cap(
                household,
                scenario,
                rules,
                purchase_months=purchase_months,
                monthly_income_for_capacity=income_at_month(purchase_months).gross_income,
                borrower_count=max(1, len(household.members)),
            )
            max_pf_loan = min(cap, price)
            min_down_ratio = _min_down_payment_ratio(household, max_pf_loan > 0, rules)
            minimum_down = price * min_down_ratio
            if use_manual_mix:
                commercial = _clamp(scenario.commercial_loan_amount, 0, max(0, price - minimum_down))
                pf_loan = min(
                    max(0, scenario.provident_loan_amount),
                    max_pf_loan,
                    max(0, price - minimum_down - commercial),
                )
                down = max(minimum_down, scenario.down_payment_amount, price - commercial - pf_loan)
                excess = max(0, down + commercial + pf_loan - price)
                if excess > 0:
                    pf_reduction = min(pf_loan, excess)
                    pf_loan -= pf_reduction
                    excess -= pf_reduction
                if excess > 0:
                    commercial = max(0, commercial - excess)
            else:
                pf_loan = min(max_pf_loan, max(0, price - minimum_down))
            if use_min_down:
                down = minimum_down
                commercial = max(0, price - down - pf_loan)
            elif not use_manual_mix:
                commercial = min(commercial_target, max(0, price - pf_loan - minimum_down))
                down = max(minimum_down, price - pf_loan - commercial)
            return cap, bonus, minimum_down, down, commercial, pf_loan, down + taxes_and_fees

        def purchase_state_for_mix(
            candidate_month: int,
            mix: tuple[float, float, float, float, float, float, float],
        ) -> tuple[float, float, float, float, float, float]:
            return _purchase_cash_state_at_month(
                month=candidate_month,
                upfront_cash_required=mix[6],
                planned_down_payment=mix[3],
                household=household,
                rules=rules,
                initial_cash=initial_cash,
                monthly_cash_savings=monthly_cash_savings,
                monthly_cash_savings_at=monthly_cash_savings_at,
                monthly_pf_net_growth=monthly_pf_net_growth,
                monthly_pf_net_growth_at=monthly_pf_net_growth_at,
                annual_return=scenario.annual_investment_return,
                property_price=price,
                scenario=scenario,
                cash_value_by_month=cash_value_by_month,
                pf_value_by_month=pf_value_by_month,
            )

        def cash_stress_for_mix(
            candidate_month: int,
            mix: tuple[float, float, float, float, float, float, float],
            candidate_cash_after_purchase: float,
            candidate_pf_after_extract: float,
        ) -> tuple[float, int | None, bool]:
            candidate_commercial_payment = calculate_loan(
                mix[4],
                scenario.commercial_rate,
                scenario.loan_years,
                _commercial_repayment_method(scenario),
            )
            candidate_provident_payment = calculate_loan(
                mix[5],
                scenario.provident_rate,
                provident_loan_years,
                _provident_repayment_method(scenario),
            )
            return _post_purchase_cash_stress(
                household=household,
                rules=rules,
                purchase_month=candidate_month,
                starting_cash=candidate_cash_after_purchase,
                starting_pf_balance=candidate_pf_after_extract,
                total_monthly_payment=candidate_commercial_payment.first_month_payment
                + candidate_provident_payment.first_month_payment,
                provident_monthly_payment=candidate_provident_payment.first_month_payment,
                car_loan=car_loan,
                expense_at_month=expense_at_month,
                income_at_month=income_at_month,
                car_monthly_cash_cost_at=car_monthly_cash_cost_at,
            )

        best_failed_result: PurchaseCandidate | None = None
        best_failed_rank: tuple[float, int, float] | None = None
        search_start_month = min(360, max(0, scenario.manual_purchase_delay_months)) if use_manual_mix else 0

        for candidate_month in range(search_start_month, 361):
            candidate_monthly_expense = expense_at_month(candidate_month)
            required_liquidity_reserve = max(0, candidate_monthly_expense * household.required_liquidity_months)
            candidate_mixes = (
                [compute_mix(candidate_month, price * ratio) for ratio in micro_ratio_candidates]
                if use_micro_strategy
                else [compute_mix(candidate_month)]
            )
            candidate_result: PurchaseCandidate | None = None
            for candidate_mix in candidate_mixes:
                (
                    candidate_pf_upfront,
                    candidate_family_pf_upfront,
                    candidate_pf_post,
                    candidate_cash_after_transaction,
                    candidate_cash_after_purchase,
                    candidate_pf_after_extract,
                ) = purchase_state_for_mix(candidate_month, candidate_mix)
                transaction_shortfall = max(0.0, required_liquidity_reserve - candidate_cash_after_transaction)
                if transaction_shortfall > 0:
                    candidate_minimum_cash_balance = min(candidate_cash_after_transaction, candidate_cash_after_purchase)
                    candidate_minimum_cash_balance_month = candidate_month
                    candidate_cash_stress_ok = False
                else:
                    (
                        candidate_minimum_cash_balance,
                        candidate_minimum_cash_balance_month,
                        candidate_cash_stress_ok,
                    ) = cash_stress_for_mix(
                        candidate_month,
                        candidate_mix,
                        candidate_cash_after_purchase,
                        candidate_pf_after_extract,
                    )
                candidate = PurchaseCandidate(
                    purchase_month=candidate_month,
                    mix=candidate_mix,
                    pf_upfront_extractable=candidate_pf_upfront,
                    family_pf_upfront_extractable=candidate_family_pf_upfront,
                    pf_post_transaction_extractable=candidate_pf_post,
                    cash_after_transaction=candidate_cash_after_transaction,
                    cash_after_purchase=candidate_cash_after_purchase,
                    pf_after_extract=candidate_pf_after_extract,
                    minimum_cash_balance=candidate_minimum_cash_balance,
                    minimum_cash_balance_month=candidate_minimum_cash_balance_month,
                    cash_stress_ok=candidate_cash_stress_ok and transaction_shortfall <= 0,
                    cash_stress_shortfall=max(transaction_shortfall, -candidate_minimum_cash_balance, 0.0),
                )
                if candidate.cash_stress_ok:
                    candidate_result = candidate
                    break
                candidate_rank = (
                    candidate.cash_stress_shortfall,
                    candidate_month,
                    candidate.mix[4],
                )
                if best_failed_rank is None or candidate_rank < best_failed_rank:
                    best_failed_rank = candidate_rank
                    best_failed_result = candidate
            if candidate_result is None:
                continue
            (
                provident_cap,
                provident_policy_bonus,
                min_down_payment,
                planned_down,
                commercial_loan,
                provident_loan,
                upfront_cash,
            ) = candidate_result.mix
            pf_upfront_extractable = candidate_result.pf_upfront_extractable
            family_pf_upfront_extractable = candidate_result.family_pf_upfront_extractable
            pf_post_transaction_extractable = candidate_result.pf_post_transaction_extractable
            cash_after_transaction = candidate_result.cash_after_transaction
            cash_after_purchase = candidate_result.cash_after_purchase
            pf_after_extract = candidate_result.pf_after_extract
            minimum_cash_balance = candidate_result.minimum_cash_balance
            minimum_cash_balance_month = candidate_result.minimum_cash_balance_month
            cash_stress_ok = candidate_result.cash_stress_ok
            cash_stress_shortfall = candidate_result.cash_stress_shortfall
            pf_extractable = pf_upfront_extractable + family_pf_upfront_extractable + pf_post_transaction_extractable
            months = candidate_month
            break
        else:
            months = None
            if best_failed_result is not None:
                (
                    provident_cap,
                    provident_policy_bonus,
                    min_down_payment,
                    planned_down,
                    commercial_loan,
                    provident_loan,
                    upfront_cash,
                ) = best_failed_result.mix
                pf_upfront_extractable = best_failed_result.pf_upfront_extractable
                family_pf_upfront_extractable = best_failed_result.family_pf_upfront_extractable
                pf_post_transaction_extractable = best_failed_result.pf_post_transaction_extractable
                cash_after_transaction = best_failed_result.cash_after_transaction
                cash_after_purchase = best_failed_result.cash_after_purchase
                pf_after_extract = best_failed_result.pf_after_extract
                minimum_cash_balance = best_failed_result.minimum_cash_balance
                minimum_cash_balance_month = best_failed_result.minimum_cash_balance_month
                cash_stress_ok = False
                cash_stress_shortfall = best_failed_result.cash_stress_shortfall
                required_liquidity_reserve = max(
                    0,
                    expense_at_month(best_failed_result.purchase_month) * household.required_liquidity_months,
                )
            else:
                fallback_target = price * micro_ratio_candidates[-1] if use_micro_strategy else target_commercial
                (
                    provident_cap,
                    provident_policy_bonus,
                    min_down_payment,
                    planned_down,
                    commercial_loan,
                    provident_loan,
                    upfront_cash,
                ) = compute_mix(360, fallback_target)
                required_liquidity_reserve = max(0, expense_at_month(360) * household.required_liquidity_months)
                (
                    pf_upfront_extractable,
                    family_pf_upfront_extractable,
                    pf_post_transaction_extractable,
                    cash_after_transaction,
                    cash_after_purchase,
                    pf_after_extract,
                ) = purchase_state_for_mix(
                    360,
                    (
                        provident_cap,
                        provident_policy_bonus,
                        min_down_payment,
                        planned_down,
                        commercial_loan,
                        provident_loan,
                        upfront_cash,
                    ),
                )
                minimum_cash_balance, minimum_cash_balance_month, cash_stress_ok = cash_stress_for_mix(
                    360,
                    (
                        provident_cap,
                        provident_policy_bonus,
                        min_down_payment,
                        planned_down,
                        commercial_loan,
                        provident_loan,
                        upfront_cash,
                    ),
                    cash_after_purchase,
                    pf_after_extract,
                )
                cash_stress_shortfall = max(
                    0.0,
                    required_liquidity_reserve - cash_after_transaction,
                    -minimum_cash_balance,
                )
                cash_stress_ok = False
            pf_extractable = pf_upfront_extractable + family_pf_upfront_extractable + pf_post_transaction_extractable

        commercial_payment = calculate_loan(
            commercial_loan,
            scenario.commercial_rate,
            scenario.loan_years,
            _commercial_repayment_method(scenario),
        )
        provident_equal_installment_payment = calculate_loan(
            provident_loan,
            scenario.provident_rate,
            provident_loan_years,
            "equal_installment",
        )
        provident_equal_principal_payment = calculate_loan(
            provident_loan,
            scenario.provident_rate,
            provident_loan_years,
            "equal_principal",
        )
        selected_provident_repayment_method = _provident_repayment_method(scenario)
        post_purchase_month = months if months is not None else 360
        post_purchase_monthly_expense = expense_at_month(post_purchase_month)
        post_purchase_income = income_at_month(post_purchase_month)
        post_purchase_car_cost = car_monthly_cash_cost_at(post_purchase_month)
        if (
            provident_loan > 0
            and not use_manual_mix
            and selected_provident_repayment_method != "equal_principal"
            and provident_equal_principal_payment.first_month_payment > 0
        ):
            equal_principal_total_payment = commercial_payment.first_month_payment + provident_equal_principal_payment.first_month_payment
            equal_principal_free_cash_flow = (
                post_purchase_income.net_income
                - post_purchase_monthly_expense
                - household.monthly_debt_payment
                - post_purchase_car_cost
                - equal_principal_total_payment
            )
            equal_principal_pf_relief, _ = _post_purchase_pf_strategy(
                purchase_month=post_purchase_month,
                starting_pf_balance=pf_after_extract,
                free_cash_flow=equal_principal_free_cash_flow,
                monthly_pf_deposit=post_purchase_income.monthly_pf_deposit,
                provident_monthly_payment=provident_equal_principal_payment.first_month_payment,
                total_monthly_payment=equal_principal_total_payment,
                post_purchase_monthly_expense=post_purchase_monthly_expense,
                rules=rules,
            )
            pf_income_covers_material_share = post_purchase_income.monthly_pf_deposit >= provident_equal_principal_payment.first_month_payment * 0.55
            if equal_principal_free_cash_flow + equal_principal_pf_relief >= 0 and pf_income_covers_material_share:
                selected_provident_repayment_method = "equal_principal"
        provident_payment = (
            provident_equal_principal_payment
            if selected_provident_repayment_method == "equal_principal"
            else provident_equal_installment_payment
        )
        total_monthly_payment = commercial_payment.first_month_payment + provident_payment.first_month_payment
        post_purchase_cash_flow = (
            post_purchase_income.net_income
            - post_purchase_monthly_expense
            - household.monthly_debt_payment
            - post_purchase_car_cost
            - total_monthly_payment
        )
        monthly_pf_withdrawal, monthly_pf_withdrawal_mode = _post_purchase_pf_strategy(
            purchase_month=post_purchase_month,
            starting_pf_balance=pf_after_extract,
            free_cash_flow=post_purchase_cash_flow,
            monthly_pf_deposit=post_purchase_income.monthly_pf_deposit,
            provident_monthly_payment=provident_payment.first_month_payment,
            total_monthly_payment=total_monthly_payment,
            post_purchase_monthly_expense=post_purchase_monthly_expense,
            rules=rules,
        )
        post_purchase_cash_flow_with_pf = post_purchase_cash_flow + monthly_pf_withdrawal
        renovation_included_upfront = scenario.renovation_funding_mode == "upfront_cash"
        renovation_saving_months: int | None = 0
        post_purchase_renovation_monthly_saving = 0.0
        if not renovation_included_upfront and scenario.renovation_cost > 0:
            post_purchase_renovation_monthly_saving = max(0.0, post_purchase_cash_flow)
            immediate_renovation_cash = max(0.0, cash_after_purchase - required_liquidity_reserve)
            renovation_remaining = max(0.0, scenario.renovation_cost - immediate_renovation_cash)
            if renovation_remaining <= 0:
                renovation_saving_months = 0
            elif post_purchase_renovation_monthly_saving > 0:
                renovation_saving_months = ceil(renovation_remaining / post_purchase_renovation_monthly_saving)
            else:
                renovation_saving_months = None
        dti = (
            household.monthly_debt_payment
            + post_purchase_car_cost
            + total_monthly_payment
        ) / max(post_purchase_income.net_income, 1)
        wait_score = _wait_score(months, 120)
        stress_liquidity_floor = min(required_liquidity_reserve, max(1.0, post_purchase_monthly_expense * 3))
        liquidity_score = _ratio_score(min(cash_after_transaction, minimum_cash_balance), stress_liquidity_floor)
        post_extract_liquidity_score = _ratio_score(cash_after_purchase, required_liquidity_reserve)
        flow_score = _cash_flow_score(post_purchase_cash_flow_with_pf, post_purchase_monthly_expense)
        dti_score = _dti_score(dti)
        payment_pressure_score = _clamp_score(10 - total_monthly_payment / max(post_purchase_income.net_income, 1) / 0.45 * 10)
        commercial_pressure_score = _clamp_score(10 - commercial_loan / max(price, 1) / 0.65 * 10)
        interest_score = _clamp_score(10 - (commercial_payment.total_interest + provident_payment.total_interest) / max(price, 1) / 0.55 * 10)
        provident_interest_saving_if_equal_principal = max(
            0.0,
            provident_equal_installment_payment.total_interest - provident_equal_principal_payment.total_interest,
        )
        equal_principal_extra_first_payment = max(
            0.0,
            provident_equal_principal_payment.first_month_payment - provident_equal_installment_payment.first_month_payment,
        )
        equal_principal_cash_flow = (
            post_purchase_income.net_income
            - post_purchase_monthly_expense
            - household.monthly_debt_payment
            - post_purchase_car_cost
            - commercial_payment.first_month_payment
            - provident_equal_principal_payment.first_month_payment
            + monthly_pf_withdrawal
        )
        if provident_loan <= 0:
            provident_repayment_advice = "本方案不使用公积金贷款，无需比较公积金还款方式。"
        elif selected_provident_repayment_method == "equal_principal":
            provident_repayment_advice = (
                f"当前已采用等额本金；相比等额本息首月多付约 {round(equal_principal_extra_first_payment)}，"
                f"但公积金贷款总利息少约 {round(provident_interest_saving_if_equal_principal)}，本金下降更快。"
            )
        elif equal_principal_cash_flow >= 0:
            provident_repayment_advice = (
                f"若切换公积金贷为等额本金，首月现金压力约增加 {round(equal_principal_extra_first_payment)}，"
                f"但总利息可少约 {round(provident_interest_saving_if_equal_principal)}，本金下降更快；当前策略后现金流可覆盖，可作为优先比较项。"
            )
        else:
            provident_repayment_advice = (
                f"等额本金可少付公积金利息约 {round(provident_interest_saving_if_equal_principal)}，"
                f"但首月现金压力增加约 {round(equal_principal_extra_first_payment)}，当前现金流不宜自动切换。"
            )
        life_quality_score = (
            scenario.happiness_score * 0.28
            + scenario.commute_score * 0.21
            + scenario.school_score * 0.18
            + household.car_plan.happiness_score * 0.08
            + wait_score * 0.11
            + commercial_pressure_score * 0.06
            + liquidity_score * 0.08
        )
        financial_score = (
            liquidity_score * 0.22
            + post_extract_liquidity_score * 0.12
            + flow_score * 0.24
            + dti_score * 0.18
            + wait_score * 0.08
            + payment_pressure_score * 0.08
            + commercial_pressure_score * 0.05
            + interest_score * 0.03
        )
        liquidity_weight = _clamp_score(scenario.liquidity_priority_score) / 10
        happiness_score = (
            life_quality_score * (0.70 - liquidity_weight * 0.15)
            + financial_score * (0.30 + liquidity_weight * 0.15)
        )
        happiness_breakdown = [
            {
                "name": "居住体验",
                "score": round(scenario.happiness_score, 2),
                "weight": 0.18,
                "note": "目标房源的户型、社区、主观居住满意度。",
            },
            {
                "name": "通勤",
                "score": round(scenario.commute_score, 2),
                "weight": 0.14,
                "note": "通勤便利度和日常时间成本。",
            },
            {
                "name": "教育",
                "score": round(scenario.school_score, 2),
                "weight": 0.12,
                "note": "教育资源与家庭长期确定性。",
            },
            {
                "name": "交易当下现金安全",
                "score": round(liquidity_score, 2),
                "weight": 0.16,
                "note": f"交易当下现金 {round(cash_after_transaction)}，安全垫 {round(required_liquidity_reserve)}。",
            },
            {
                "name": "买后现金流",
                "score": round(flow_score, 2),
                "weight": 0.16,
                "note": f"买后自由现金月结余 {round(post_purchase_cash_flow)}；贷后公积金策略为{_post_purchase_pf_withdrawal_label(monthly_pf_withdrawal_mode)}，策略后现金压力约 {round(post_purchase_cash_flow_with_pf)}。",
            },
            {
                "name": "负债压力",
                "score": round(dti_score, 2),
                "weight": 0.10,
                "note": f"负债收入比 {round(dti * 100, 1)}%。",
            },
            {
                "name": "商贷与利息压力",
                "score": round((commercial_pressure_score * 0.65 + interest_score * 0.35), 2),
                "weight": 0.08,
                "note": f"商贷 {round(commercial_loan)}，总利息 {round(commercial_payment.total_interest + provident_payment.total_interest)}。",
            },
            {
                "name": "等待时间",
                "score": round(wait_score, 2),
                "weight": 0.06,
                "note": "越早可执行，对家庭确定性和机会成本越友好。",
            },
        ]
        analyses.append(
            PurchasePlanAnalysis(
                variant=name,
                description=description,
                months_to_buy=months,
                years_to_buy=round(months / 12, 1) if months is not None else None,
                minimum_down_payment=round(min_down_payment, 2),
                planned_down_payment=round(planned_down, 2),
                provident_fund_extractable=pf_extractable,
                provident_upfront_extractable=round(pf_upfront_extractable, 2),
                family_provident_upfront_extractable=round(family_pf_upfront_extractable, 2),
                family_down_payment_support_amount=round(family_pf_upfront_extractable, 2),
                family_down_payment_support_mode=(
                    _family_down_payment_support_mode(household)
                    if family_pf_upfront_extractable > 0
                    else "none"
                ),
                family_down_payment_support_label=(
                    _family_down_payment_support_label(household)
                    if family_pf_upfront_extractable > 0
                    else ""
                ),
                provident_post_transaction_extractable=round(pf_post_transaction_extractable, 2),
                required_cash_after_pf_extract=round(max(0, upfront_cash - pf_upfront_extractable - family_pf_upfront_extractable), 2),
                upfront_cash_required=round(upfront_cash, 2),
                commercial_loan_amount=round(commercial_loan, 2),
                provident_loan_amount=round(provident_loan, 2),
                provident_policy_bonus=round(provident_policy_bonus, 2),
                provident_policy_cap=round(provident_cap, 2),
                commercial_loan_years=scenario.loan_years,
                provident_loan_years=provident_loan_years,
                provident_loan_year_limit_reasons=provident_year_reasons,
                commercial_repayment_method=_commercial_repayment_method(scenario),  # type: ignore[arg-type]
                provident_repayment_method=selected_provident_repayment_method,  # type: ignore[arg-type]
                commercial_monthly_payment=round(commercial_payment.first_month_payment, 2),
                provident_monthly_payment=round(provident_payment.first_month_payment, 2),
                total_monthly_payment=round(total_monthly_payment, 2),
                total_interest=round(commercial_payment.total_interest + provident_payment.total_interest, 2),
                provident_contract_months=provident_loan_years * 12 if provident_loan > 0 else 0,
                provident_interest_saving_if_equal_principal=round(provident_interest_saving_if_equal_principal, 2),
                provident_equal_principal_first_payment=round(provident_equal_principal_payment.first_month_payment, 2),
                provident_equal_installment_payment=round(provident_equal_installment_payment.first_month_payment, 2),
                provident_repayment_advice=provident_repayment_advice,
                renovation_cost=round(scenario.renovation_cost, 2),
                renovation_funding_mode=scenario.renovation_funding_mode,
                renovation_included_in_upfront_cash=renovation_included_upfront,
                months_to_renovation=renovation_saving_months,
                years_to_renovation=round(renovation_saving_months / 12, 1)
                if renovation_saving_months is not None
                else None,
                post_purchase_renovation_monthly_saving=round(post_purchase_renovation_monthly_saving, 2),
                cash_after_transaction=round(cash_after_transaction, 2),
                cash_after_purchase=round(cash_after_purchase, 2),
                provident_balance_after_extract=round(pf_after_extract, 2),
                required_liquidity_reserve=round(required_liquidity_reserve, 2),
                liquidity_ok=cash_after_transaction >= required_liquidity_reserve and cash_stress_ok,
                minimum_cash_balance=round(max(0.0, minimum_cash_balance), 2),
                minimum_cash_balance_month=minimum_cash_balance_month,
                cash_stress_ok=cash_stress_ok,
                cash_stress_shortfall=round(max(0.0, cash_stress_shortfall, -minimum_cash_balance), 2),
                post_purchase_cash_flow=round(post_purchase_cash_flow, 2),
                post_purchase_pf_strategy=monthly_pf_withdrawal_mode,
                post_purchase_pf_strategy_label=_post_purchase_pf_withdrawal_label(monthly_pf_withdrawal_mode),
                monthly_post_purchase_pf_withdrawal=round(monthly_pf_withdrawal, 2),
                post_purchase_cash_flow_with_pf_withdrawal=round(post_purchase_cash_flow_with_pf, 2),
                debt_to_income_ratio=round(dti, 4),
                happiness_score=round(_clamp_score(happiness_score), 2),
                provident_extraction_notes=[
                    "交易前仅按规则包中的可提前提取比例计入首付现金；默认 0%，避免把审核后到账资金误当作交易前现金。",
                    "交易后购房提取按购房价款额度内、账户可用余额估算，审核通过后回流到银行卡。",
                    "买房后家庭在京住房性质发生变化，租房提取不再作为后续公积金现金流来源。",
                    "买房后月度公积金缴存默认不作为工资类收入；自动策略会在现金压力偏高且存在公积金贷款时优先考虑冲还贷。",
                    "冲还贷属于用公积金账户资金抵扣贷款，体现为降低贷款现金支出，不是自由现金收入；生效时原有购房、租房提取事项及已办理约定提取会同步终止，且冲还贷期间不再受理新的住房公积金提取业务。",
                    f"当前购后公积金处理：{_post_purchase_pf_withdrawal_label(monthly_pf_withdrawal_mode)}。",
                ],
                happiness_breakdown=happiness_breakdown,
            )
        )
    return analyses


def build_yield_sensitivity(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    tax_summaries: list[TaxMemberSummary],
    net_monthly_income: float,
    car_loan: CarLoanSummary,
    taxes_and_fees: float,
    parallel_workers: int = 1,
) -> list[YieldSensitivityPoint]:
    annual_returns = [0.015, 0.025, 0.035]

    def point_for_return(annual_return: float) -> YieldSensitivityPoint:
        adjusted = scenario.model_copy(update={"annual_investment_return": annual_return})
        analyses = build_purchase_plan_analyses(
            household,
            adjusted,
            rules,
            tax_summaries=tax_summaries,
            net_monthly_income=net_monthly_income,
            car_loan=car_loan,
            taxes_and_fees=taxes_and_fees,
        )
        fastest = min(
            analyses,
            key=lambda item: item.months_to_buy if item.months_to_buy is not None else 999999,
        )
        return YieldSensitivityPoint(
            annual_return=annual_return,
            months_to_buy=fastest.months_to_buy,
            years_to_buy=fastest.years_to_buy,
            cash_after_purchase=fastest.cash_after_purchase,
        )

    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            return list(executor.map(point_for_return, annual_returns))
    return [point_for_return(annual_return) for annual_return in annual_returns]


def build_loan_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    base_monthly_debt_payment: float | None = None,
    provident_visualization: list[ProvidentVisualizationPoint] | None = None,
) -> list[LoanVisualizationPoint]:
    second_plan = _second_car_plan(household.car_plan)
    second_loan = calculate_car_loan(second_plan) if second_plan.enabled else None
    first_car_purchase_month = (
        car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else household.car_plan.purchase_delay_months
    ) if household.car_plan.enabled and car_loan.enabled else None
    second_car_purchase_month = (
        second_loan.months_to_down_payment if second_loan and second_loan.months_to_down_payment is not None else second_plan.purchase_delay_months
    ) if second_loan and second_loan.enabled else None
    base_existing_payment = max(0.0, base_monthly_debt_payment if base_monthly_debt_payment is not None else household.monthly_debt_payment)
    provident_offset_by_plan_month = {
        (row.plan_variant, row.month): row.loan_offset_payment
        for row in (provident_visualization or [])
    }
    visualization_horizon = _visualization_horizon_months(household, purchase_plans, car_loan, second_loan=second_loan)
    rows: list[LoanVisualizationPoint] = []
    for plan in purchase_plans:
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 360
        horizon_months = visualization_horizon
        for month in range(horizon_months + 1):
            home_elapsed = max(0, month - purchase_month) if plan.months_to_buy is not None and month >= purchase_month else 0
            commercial_balance = (
                _loan_balance_after_payments(
                    plan.commercial_loan_amount,
                    scenario.commercial_rate,
                    plan.commercial_loan_years,
                    plan.commercial_repayment_method,
                    home_elapsed,
                )
                if plan.months_to_buy is not None and month >= purchase_month
                else 0.0
            )
            provident_balance = (
                _loan_balance_after_payments(
                    plan.provident_loan_amount,
                    scenario.provident_rate,
                    plan.provident_loan_years,
                    plan.provident_repayment_method,
                    home_elapsed,
                )
                if plan.months_to_buy is not None and month >= purchase_month
                else 0.0
            )
            first_vehicle_balance = 0.0
            first_vehicle_payment = 0.0
            if car_loan.enabled and first_car_purchase_month is not None and month >= first_car_purchase_month:
                vehicle_elapsed = max(0, month - first_car_purchase_month)
                first_vehicle_balance = _installment_balance_after_payments(
                    car_loan.loan_principal,
                    car_loan.total_months,
                    vehicle_elapsed,
                )
                if 0 < vehicle_elapsed <= car_loan.total_months:
                    first_vehicle_payment = (
                        car_loan.first_phase_monthly_payment
                        if vehicle_elapsed <= car_loan.interest_free_months
                        else car_loan.later_phase_monthly_payment
                    )
            second_vehicle_balance = 0.0
            second_vehicle_payment = 0.0
            if second_loan and second_car_purchase_month is not None and month >= second_car_purchase_month:
                second_elapsed = max(0, month - second_car_purchase_month)
                second_vehicle_balance = _installment_balance_after_payments(
                    second_loan.loan_principal,
                    second_loan.total_months,
                    second_elapsed,
                )
                if 0 < second_elapsed <= second_loan.total_months:
                    second_vehicle_payment = (
                        second_loan.first_phase_monthly_payment
                        if second_elapsed <= second_loan.interest_free_months
                        else second_loan.later_phase_monthly_payment
                    )
            commercial_payment = plan.commercial_monthly_payment if commercial_balance > 0 else 0.0
            provident_payment = plan.provident_monthly_payment if provident_balance > 0 else 0.0
            home_payment = commercial_payment + provident_payment
            vehicle_payment = first_vehicle_payment + second_vehicle_payment
            phased_loan_states = [_phased_loan_state_at(loan, month) for loan in household.phased_loans]
            existing_loan_balance = sum(balance for balance, _ in phased_loan_states)
            existing_payment = base_existing_payment + sum(payment for _, payment in phased_loan_states)
            total_payment = home_payment + vehicle_payment + existing_payment
            provident_offset_payment = min(
                provident_payment,
                max(0.0, provident_offset_by_plan_month.get((plan.variant, month), 0.0)),
            )
            cash_payment = max(0.0, total_payment - provident_offset_payment)
            rows.append(
                LoanVisualizationPoint(
                    plan_variant=plan.variant,
                    month=month,
                    commercial_loan_balance=round(commercial_balance, 2),
                    provident_loan_balance=round(provident_balance, 2),
                    home_loan_balance=round(commercial_balance + provident_balance, 2),
                    vehicle_loan_balance=round(first_vehicle_balance + second_vehicle_balance, 2),
                    existing_loan_balance=round(existing_loan_balance, 2),
                    total_loan_balance=round(
                        commercial_balance + provident_balance + first_vehicle_balance + second_vehicle_balance + existing_loan_balance,
                        2,
                    ),
                    commercial_monthly_payment=round(commercial_payment, 2),
                    provident_monthly_payment=round(provident_payment, 2),
                    home_monthly_payment=round(home_payment, 2),
                    vehicle_monthly_payment=round(vehicle_payment, 2),
                    existing_monthly_payment=round(existing_payment, 2),
                    total_monthly_payment=round(total_payment, 2),
                    cash_monthly_payment=round(cash_payment, 2),
                    provident_offset_payment=round(provident_offset_payment, 2),
                )
            )
    return rows


def build_provident_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
) -> list[ProvidentVisualizationPoint]:
    second_plan = _second_car_plan(household.car_plan)
    second_loan = calculate_car_loan(second_plan) if second_plan.enabled else None
    first_car_purchase_month = (
        car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else household.car_plan.purchase_delay_months
    ) if household.car_plan.enabled and car_loan.enabled else None
    second_car_purchase_month = (
        second_loan.months_to_down_payment if second_loan and second_loan.months_to_down_payment is not None else second_plan.purchase_delay_months
    ) if second_loan and second_loan.enabled else None
    pf_interest_rate = max(0.0, float(rules.params.get("provident_balance_annual_interest_rate", 0.015))) / 12
    retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
    visualization_horizon = _visualization_horizon_months(household, purchase_plans, car_loan, second_loan=second_loan)
    rows: list[ProvidentVisualizationPoint] = []

    for plan in purchase_plans:
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 360
        horizon_months = visualization_horizon
        balance = max(0.0, household.provident_fund_balance)
        for month in range(horizon_months + 1):
            balance_start = balance
            income = household_monthly_income_profile_at(household, rules, month)
            personal_deposit = income.personal_housing_fund if month > 0 else 0.0
            employer_deposit = income.employer_housing_fund if month > 0 else 0.0
            total_deposit = personal_deposit + employer_deposit
            interest = balance * pf_interest_rate if month > 0 else 0.0
            balance += total_deposit + interest

            rent_withdrawal = 0.0
            upfront_withdrawal = 0.0
            post_transaction_withdrawal = 0.0
            agreed_withdrawal = 0.0
            loan_offset_payment = 0.0

            is_purchase_month = plan.months_to_buy is not None and month == purchase_month
            is_after_purchase = plan.months_to_buy is not None and month > purchase_month
            if month > 0 and not is_purchase_month and not is_after_purchase:
                rent_withdrawal = min(balance, _quarterly_rent_withdrawal_before_purchase_at(household, month))
                balance -= rent_withdrawal

            if is_purchase_month:
                upfront_withdrawal = min(balance, plan.provident_upfront_extractable)
                balance -= upfront_withdrawal
                post_transaction_withdrawal = min(balance, plan.provident_post_transaction_extractable)
                balance -= post_transaction_withdrawal
            elif is_after_purchase:
                strategy = plan.post_purchase_pf_strategy or ""
                if "loan_offset" in strategy:
                    available = max(0.0, balance - retained_balance)
                    loan_offset_payment = (
                        min(available, plan.provident_monthly_payment)
                        if _is_beijing_pf_offset_month(month) and available >= plan.provident_monthly_payment
                        else 0.0
                    )
                    balance -= loan_offset_payment
                elif "purchase_agreed" in strategy:
                    agreed_withdrawal = min(balance, plan.monthly_post_purchase_pf_withdrawal)
                    balance -= agreed_withdrawal

            total_inflow = total_deposit + interest
            total_outflow = (
                rent_withdrawal
                + upfront_withdrawal
                + post_transaction_withdrawal
                + agreed_withdrawal
                + loan_offset_payment
            )
            rows.append(
                ProvidentVisualizationPoint(
                    plan_variant=plan.variant,
                    month=month,
                    balance_start=round(balance_start, 2),
                    personal_deposit=round(personal_deposit, 2),
                    employer_deposit=round(employer_deposit, 2),
                    total_deposit=round(total_deposit, 2),
                    interest=round(interest, 2),
                    rent_withdrawal=round(rent_withdrawal, 2),
                    upfront_withdrawal=round(upfront_withdrawal, 2),
                    post_transaction_withdrawal=round(post_transaction_withdrawal, 2),
                    agreed_withdrawal=round(agreed_withdrawal, 2),
                    loan_offset_payment=round(loan_offset_payment, 2),
                    total_inflow=round(total_inflow, 2),
                    total_outflow=round(total_outflow, 2),
                    balance_end=round(max(0.0, balance), 2),
                    strategy_label=plan.post_purchase_pf_strategy_label,
                )
            )
    return rows


def _ledger_entry(
    *,
    plan_variant: str,
    month: int,
    account: str,
    category: str,
    label: str,
    amount: float,
    direction: Literal["inflow", "outflow", "transfer", "valuation"],
) -> MonthlyLedgerEntry:
    return MonthlyLedgerEntry(
        plan_variant=plan_variant,
        month=month,
        account=account,
        category=category,
        label=label,
        amount=round(amount, 2),
        direction=direction,
    )


def _investment_allocation_for_month(
    *,
    monthly_surplus: float,
    cash_balance: float,
    reserve_target: float,
    household: HouseholdData,
) -> tuple[float, float]:
    setting = max(0.0, household.monthly_investment_amount)
    if setting <= 0:
        return 0.0, 0.0
    if not household.investment_auto_rebalance:
        return min(setting, max(0.0, monthly_surplus)), 0.0

    projected_cash_before_investment = cash_balance + monthly_surplus
    available_above_reserve = max(0.0, projected_cash_before_investment - reserve_target)
    if available_above_reserve <= 0:
        return 0.0, 0.0

    base = min(setting, max(0.0, monthly_surplus), available_above_reserve)
    excess_cash = max(0.0, cash_balance - reserve_target)
    sweep = min(excess_cash / 12, max(0.0, available_above_reserve - base))
    return max(0.0, base), max(0.0, sweep)


def build_monthly_cashflow_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
) -> tuple[list[MonthlyCashflowPoint], list[AccountSnapshotPoint], list[MonthlyLedgerEntry]]:
    second_plan = _second_car_plan(household.car_plan)
    second_loan = calculate_car_loan(second_plan) if second_plan.enabled else None
    first_car_purchase_month = (
        car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else household.car_plan.purchase_delay_months
    ) if household.car_plan.enabled and car_loan.enabled else None
    second_car_purchase_month = (
        second_loan.months_to_down_payment if second_loan and second_loan.months_to_down_payment is not None else second_plan.purchase_delay_months
    ) if second_loan and second_loan.enabled else None
    horizon = _visualization_horizon_months(household, purchase_plans, car_loan, second_loan=second_loan)
    loan_by_plan_month = {(row.plan_variant, row.month): row for row in loan_visualization}
    provident_by_plan_month = {(row.plan_variant, row.month): row for row in provident_visualization}
    monthly_return = scenario.annual_investment_return / 12
    buy_fee_rate = max(0.0, household.investment_buy_fee_rate)
    sell_fee_rate = max(0.0, household.investment_sell_fee_rate)
    investment_enabled = household.investment_plan_name != "cash_only"
    current_phased_payment = sum(payment for _, payment in (_phased_loan_state_at(loan, 0) for loan in household.phased_loans))
    base_regular_debt_payment = max(0.0, household.monthly_debt_payment - current_phased_payment)
    rows: list[MonthlyCashflowPoint] = []
    snapshots: list[AccountSnapshotPoint] = []
    ledger: list[MonthlyLedgerEntry] = []

    for plan in purchase_plans:
        cash_balance = max(0.0, household.liquid_assets)
        investment_balance = max(0.0, household.investments)
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 999999
        for month in range(0, horizon + 1):
            entries: list[MonthlyLedgerEntry] = []
            cash_income = 0.0
            living_expense = 0.0
            scheduled_expense = 0.0
            debt_payment = 0.0
            regular_debt_payment = 0.0
            phased_loan_payment = 0.0
            house_payment = 0.0
            house_contract_payment = 0.0
            provident_house_offset_payment = 0.0
            vehicle_payment = 0.0
            first_vehicle_payment = 0.0
            second_vehicle_payment = 0.0
            vehicle_operating_cost = 0.0
            first_vehicle_energy_cost = 0.0
            first_vehicle_insurance_cost = 0.0
            first_vehicle_maintenance_cost = 0.0
            first_vehicle_parking_cost = 0.0
            second_vehicle_energy_cost = 0.0
            second_vehicle_insurance_cost = 0.0
            second_vehicle_maintenance_cost = 0.0
            second_vehicle_parking_cost = 0.0
            no_car_commute_cost = 0.0
            vehicle_down_payment = 0.0
            first_vehicle_down_payment = 0.0
            second_vehicle_down_payment = 0.0
            investment_contribution = 0.0
            investment_contribution_base = 0.0
            investment_contribution_cash_sweep = 0.0
            investment_return = 0.0
            investment_fee = 0.0
            investment_buy_fee = 0.0
            investment_sell_fee = 0.0
            investment_sell_proceeds = 0.0
            transaction_cash_out = 0.0
            transaction_cash_in = 0.0
            phase = "购房前"

            provident_point = provident_by_plan_month.get((plan.variant, month))
            loan_point = loan_by_plan_month.get((plan.variant, month))
            provident_balance = provident_point.balance_end if provident_point else max(0.0, household.provident_fund_balance)
            provident_deposit = provident_point.total_deposit if provident_point else 0.0
            provident_cash_receipt = (
                provident_point.rent_withdrawal
                + provident_point.post_transaction_withdrawal
                + provident_point.agreed_withdrawal
                if provident_point
                else 0.0
            )
            provident_house_offset_payment = provident_point.loan_offset_payment if provident_point else 0.0

            if month > 0:
                profile = household_monthly_income_profile_at(household, rules, month)
                cash_income = profile.net_income
                total_expense = monthly_household_expense_at(household, month)
                investment_reserve_target = max(0.0, total_expense * household.investment_cash_reserve_months)
                living_expense = household.monthly_expense
                scheduled_expense = max(0.0, total_expense - household.monthly_expense)
                regular_debt_payment = base_regular_debt_payment
                debt_payment = loan_point.existing_monthly_payment if loan_point else regular_debt_payment
                phased_loan_payment = max(0.0, debt_payment - regular_debt_payment)
                vehicle_total = _car_monthly_cash_cost_at(household.car_plan, car_loan, month)
                loan_vehicle_payment = loan_point.vehicle_monthly_payment if loan_point else 0.0
                vehicle_payment = min(vehicle_total, loan_vehicle_payment)
                vehicle_operating_cost = max(0.0, vehicle_total - vehicle_payment)
                first_components = _vehicle_cash_components_at(car_loan, household.car_plan, month, first_car_purchase_month)
                second_components = (
                    _vehicle_cash_components_at(second_loan, second_plan, month, second_car_purchase_month)
                    if second_loan
                    else {"payment": 0.0, "energy": 0.0, "insurance": 0.0, "maintenance": 0.0, "parking": 0.0}
                )
                first_vehicle_payment = first_components["payment"]
                second_vehicle_payment = second_components["payment"]
                first_vehicle_energy_cost = first_components["energy"]
                first_vehicle_insurance_cost = first_components["insurance"]
                first_vehicle_maintenance_cost = first_components["maintenance"]
                first_vehicle_parking_cost = first_components["parking"]
                second_vehicle_energy_cost = second_components["energy"]
                second_vehicle_insurance_cost = second_components["insurance"]
                second_vehicle_maintenance_cost = second_components["maintenance"]
                second_vehicle_parking_cost = second_components["parking"]
                if vehicle_total > 0 and first_car_purchase_month is not None and month < first_car_purchase_month:
                    no_car_commute_cost = _no_car_commute_cost(household.car_plan)
                first_vehicle_down_payment, second_vehicle_down_payment = _car_down_payment_components_at(
                    household.car_plan,
                    car_loan,
                    month,
                )
                vehicle_down_payment = first_vehicle_down_payment + second_vehicle_down_payment
                if vehicle_down_payment:
                    transaction_cash_out += vehicle_down_payment
                    entries.append(
                        _ledger_entry(
                            plan_variant=plan.variant,
                            month=month,
                            account="cash",
                            category="vehicle_down_payment",
                            label="车辆首付现金支出",
                            amount=-vehicle_down_payment,
                            direction="outflow",
                        )
                    )

                if month == purchase_month:
                    phase = "交易月"
                    investment_sell_fee = investment_balance * sell_fee_rate if investment_enabled else 0.0
                    investment_sell_proceeds = max(0.0, investment_balance - investment_sell_fee)
                    investment_fee += investment_sell_fee
                    transaction_cash_in += investment_sell_proceeds + plan.provident_post_transaction_extractable
                    transaction_cash_out += plan.required_cash_after_pf_extract
                    cash_balance = max(
                        0.0,
                        cash_balance
                        + investment_sell_proceeds
                        - plan.required_cash_after_pf_extract
                        + plan.provident_post_transaction_extractable
                        - vehicle_down_payment,
                    )
                    investment_balance = 0.0
                    entries.extend(
                        [
                            _ledger_entry(
                                plan_variant=plan.variant,
                                month=month,
                                account="investment",
                                category="sell",
                                label="交易月理财变现",
                                amount=investment_sell_proceeds,
                                direction="transfer",
                            ),
                            _ledger_entry(
                                plan_variant=plan.variant,
                                month=month,
                                account="cash",
                                category="home_purchase",
                                label="购房交易现金支出",
                                amount=-plan.required_cash_after_pf_extract,
                                direction="outflow",
                            ),
                        ]
                    )
                else:
                    if month > purchase_month:
                        phase = "购房后"
                        house_contract_payment = loan_point.home_monthly_payment if loan_point else plan.total_monthly_payment
                        house_payment = max(0.0, house_contract_payment - provident_house_offset_payment)
                    monthly_surplus = (
                        cash_income
                        - total_expense
                        - debt_payment
                        - house_payment
                        - vehicle_total
                        + provident_cash_receipt
                    )
                    investable_surplus = monthly_surplus - vehicle_down_payment
                    investment_return = investment_balance * monthly_return if investment_enabled else 0.0
                    if investment_enabled:
                        investment_contribution_base, investment_contribution_cash_sweep = _investment_allocation_for_month(
                            monthly_surplus=investable_surplus,
                            cash_balance=cash_balance,
                            reserve_target=investment_reserve_target,
                            household=household,
                        )
                    investment_contribution = (
                        investment_contribution_base + investment_contribution_cash_sweep
                    )
                    investment_buy_fee = investment_contribution * buy_fee_rate
                    investment_fee = investment_buy_fee
                    net_investment = max(0.0, investment_contribution - investment_fee)
                    cash_balance = max(0.0, cash_balance + monthly_surplus - investment_contribution - vehicle_down_payment)
                    investment_balance = max(0.0, investment_balance + net_investment + investment_return)
                    if cash_income:
                        entries.append(
                            _ledger_entry(
                                plan_variant=plan.variant,
                                month=month,
                                account="cash",
                                category="income",
                                label="家庭税后现金收入",
                                amount=cash_income,
                                direction="inflow",
                            )
                        )
                    if total_expense:
                        entries.append(
                            _ledger_entry(
                                plan_variant=plan.variant,
                                month=month,
                                account="cash",
                                category="living_expense",
                                label="家庭生活与定时支出",
                                amount=-total_expense,
                                direction="outflow",
                            )
                        )
                    if investment_contribution:
                        entries.append(
                            _ledger_entry(
                                plan_variant=plan.variant,
                                month=month,
                                account="investment",
                                category="contribution",
                                label="理财定投买入",
                                amount=investment_contribution,
                                direction="transfer",
                            )
                        )

            property_asset_value = scenario.total_price if month >= purchase_month else 0.0
            first_vehicle_asset_value = _vehicle_asset_value_at(
                car_loan.total_price if car_loan.enabled else 0.0,
                household.car_plan.depreciation_years,
                first_car_purchase_month,
                month,
            )
            second_vehicle_asset_value = _vehicle_asset_value_at(
                second_loan.total_price if second_loan and second_loan.enabled else 0.0,
                second_plan.depreciation_years,
                second_car_purchase_month,
                month,
            )
            vehicle_asset_value = first_vehicle_asset_value + second_vehicle_asset_value
            fixed_asset_value = property_asset_value + vehicle_asset_value
            total_loan_balance = loan_point.total_loan_balance if loan_point else 0.0
            total_asset_value = cash_balance + investment_balance + provident_balance + fixed_asset_value
            net_worth = total_asset_value - total_loan_balance
            monthly_cash_delta = (
                cash_income
                + provident_cash_receipt
                + transaction_cash_in
                - living_expense
                - scheduled_expense
                - debt_payment
                - house_payment
                - vehicle_payment
                - vehicle_operating_cost
                - investment_contribution
                - transaction_cash_out
            )
            ledger.extend(entries)
            rows.append(
                MonthlyCashflowPoint(
                    plan_variant=plan.variant,
                    month=month,
                    cash_balance=round(cash_balance, 2),
                    investment_balance=round(investment_balance, 2),
                    provident_balance=round(provident_balance, 2),
                    fixed_asset_value=round(fixed_asset_value, 2),
                    total_asset_value=round(total_asset_value, 2),
                    total_loan_balance=round(total_loan_balance, 2),
                    net_worth=round(net_worth, 2),
                    monthly_cash_delta=round(monthly_cash_delta, 2),
                    cash_income=round(cash_income, 2),
                    living_expense=round(living_expense, 2),
                    scheduled_expense=round(scheduled_expense, 2),
                    debt_payment=round(debt_payment, 2),
                    regular_debt_payment=round(regular_debt_payment, 2),
                    phased_loan_payment=round(phased_loan_payment, 2),
                    house_payment=round(house_payment, 2),
                    house_contract_payment=round(house_contract_payment, 2),
                    provident_house_offset_payment=round(provident_house_offset_payment, 2),
                    vehicle_payment=round(vehicle_payment, 2),
                    first_vehicle_payment=round(first_vehicle_payment, 2),
                    second_vehicle_payment=round(second_vehicle_payment, 2),
                    vehicle_operating_cost=round(vehicle_operating_cost, 2),
                    first_vehicle_energy_cost=round(first_vehicle_energy_cost, 2),
                    first_vehicle_insurance_cost=round(first_vehicle_insurance_cost, 2),
                    first_vehicle_maintenance_cost=round(first_vehicle_maintenance_cost, 2),
                    first_vehicle_parking_cost=round(first_vehicle_parking_cost, 2),
                    second_vehicle_energy_cost=round(second_vehicle_energy_cost, 2),
                    second_vehicle_insurance_cost=round(second_vehicle_insurance_cost, 2),
                    second_vehicle_maintenance_cost=round(second_vehicle_maintenance_cost, 2),
                    second_vehicle_parking_cost=round(second_vehicle_parking_cost, 2),
                    no_car_commute_cost=round(no_car_commute_cost, 2),
                    first_vehicle_down_payment=round(first_vehicle_down_payment, 2),
                    second_vehicle_down_payment=round(second_vehicle_down_payment, 2),
                    vehicle_down_payment=round(vehicle_down_payment, 2),
                    investment_contribution=round(investment_contribution, 2),
                    investment_contribution_base=round(investment_contribution_base, 2),
                    investment_contribution_cash_sweep=round(investment_contribution_cash_sweep, 2),
                    investment_return=round(investment_return, 2),
                    investment_fee=round(investment_fee, 2),
                    investment_buy_fee=round(investment_buy_fee, 2),
                    investment_sell_fee=round(investment_sell_fee, 2),
                    investment_sell_proceeds=round(investment_sell_proceeds, 2),
                    provident_deposit=round(provident_deposit, 2),
                    provident_withdrawal=round(provident_cash_receipt, 2),
                    transaction_cash_out=round(transaction_cash_out, 2),
                    transaction_cash_in=round(transaction_cash_in, 2),
                    property_asset_value=round(property_asset_value, 2),
                    vehicle_asset_value=round(vehicle_asset_value, 2),
                    first_vehicle_asset_value=round(first_vehicle_asset_value, 2),
                    second_vehicle_asset_value=round(second_vehicle_asset_value, 2),
                    phase=phase,
                    ledger_entries=entries,
                )
            )
            snapshots.append(
                AccountSnapshotPoint(
                    plan_variant=plan.variant,
                    month=month,
                    cash_balance=round(cash_balance, 2),
                    investment_balance=round(investment_balance, 2),
                    provident_balance=round(provident_balance, 2),
                    property_asset_value=round(property_asset_value, 2),
                    vehicle_asset_value=round(vehicle_asset_value, 2),
                    first_vehicle_asset_value=round(first_vehicle_asset_value, 2),
                    second_vehicle_asset_value=round(second_vehicle_asset_value, 2),
                    fixed_asset_value=round(fixed_asset_value, 2),
                    total_asset_value=round(total_asset_value, 2),
                    total_loan_balance=round(total_loan_balance, 2),
                    net_worth=round(net_worth, 2),
                )
            )
    return rows, snapshots, ledger


def _money_text(amount: float) -> str:
    value = round(float(amount), 2)
    if abs(value) >= 10000:
        text = f"{value / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text} 万"
    text = f"{value:.0f}" if value == round(value) else f"{value:.2f}"
    return f"{text} 元"


def _repayment_method_label(method: str) -> str:
    return "等额本金" if method == "equal_principal" else "等额本息"


def build_account_concepts() -> list[AccountConceptSummary]:
    return [
        AccountConceptSummary(
            code="cash_account",
            name="现金账户",
            category="cash",
            description="由后端逐月推演的自由现金余额，只记录工资现金入账、日常支出、交易现金、车贷房贷现金还款、理财买卖资金等可以真实动用的现金。",
            managed_by="backend",
        ),
        AccountConceptSummary(
            code="investment_account",
            name="投资账户",
            category="investment",
            description="由后端根据定投策略、买入手续费、卖出手续费和月度收益复利推演，不直接等同于现金，交易月需要先变现再进入现金账户。",
            managed_by="backend",
        ),
        AccountConceptSummary(
            code="provident_account",
            name="公积金账户",
            category="provident",
            description="按政策口径单独管理，个人和单位缴存、账户利息、租房季度提取、购房相关提取、冲还贷支出都在后端逐月记账；默认不作为自由现金收入。",
            managed_by="backend",
        ),
        AccountConceptSummary(
            code="fixed_asset_account",
            name="固定资产",
            category="fixed_asset",
            description="记录房产和车辆等不动产/耐用品估值，用于看家庭资产结构，不作为首付或应急现金来源。",
            managed_by="backend",
        ),
        AccountConceptSummary(
            code="loan_account",
            name="贷款账户",
            category="loan",
            description="统一管理商业房贷、公积金贷款、车贷和阶段性既有贷款余额及月供；前端只展示后端返回的逐月余额和还款现金流。",
            managed_by="backend",
        ),
        AccountConceptSummary(
            code="policy_pack",
            name="政策规则包",
            category="policy",
            description="税、公积金、购房资格、贷款上限、贷款年限、冲还贷月份等由政策规则包控制；用户只调整真实可选参数和情景假设。",
            managed_by="policy",
        ),
    ]


def build_strategy_explanations(
    purchase_plans: list[PurchasePlanAnalysis],
) -> list[StrategyExplanationPoint]:
    rows: list[StrategyExplanationPoint] = []
    for plan in purchase_plans:
        if plan.months_to_buy is None:
            status_body = (
                f"当前方案在 30 年内没有找到现金安全的执行月份；压力情景短缺约 {_money_text(plan.cash_stress_shortfall)}。"
                "后端不会把现金账户推成负数来制造可行结果，需要延后、降低目标或调整贷款结构。"
            )
        else:
            status_body = (
                f"后端选择第 {plan.months_to_buy} 个月作为执行锚点；交易现金需覆盖 {_money_text(plan.required_cash_after_pf_extract)}，"
                f"交易当下现金约 {_money_text(plan.cash_after_transaction)}，购后现金约 {_money_text(plan.cash_after_purchase)}。"
            )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="summary",
                title="执行判断",
                body=status_body,
                priority=10,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="funding",
                title="资金结构",
                body=(
                    f"首付 {_money_text(plan.planned_down_payment)}，本人公积金可用于交易前抵扣 {_money_text(plan.provident_upfront_extractable)}，"
                    f"亲属首付支持 {_money_text(plan.family_down_payment_support_amount)}；后端按房源性质、政策上限和现金安全要求共同决定现金缺口。"
                ),
                priority=20,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="loan",
                title="贷款结构",
                body=(
                    f"公积金贷 {_money_text(plan.provident_loan_amount)}，{plan.provident_loan_years} 年，"
                    f"{_repayment_method_label(plan.provident_repayment_method)}；商贷 {_money_text(plan.commercial_loan_amount)}，"
                    f"{plan.commercial_loan_years} 年，{_repayment_method_label(plan.commercial_repayment_method)}。"
                    f"公积金政策上限 {_money_text(plan.provident_policy_cap)}，上浮 {_money_text(plan.provident_policy_bonus)}。"
                ),
                priority=30,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="provident",
                title="公积金策略",
                body=(
                    f"贷后公积金处理为“{plan.post_purchase_pf_strategy_label}”。"
                    + ("；".join(plan.provident_extraction_notes[:3]) if plan.provident_extraction_notes else "")
                ),
                priority=40,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="risk",
                title="现金与幸福度",
                body=(
                    f"买后自由现金月结余 {_money_text(plan.post_purchase_cash_flow)}，负债收入比 {plan.debt_to_income_ratio:.1%}，"
                    f"最低现金账户约 {_money_text(plan.minimum_cash_balance)}；幸福指数 {plan.happiness_score:.1f}/10。"
                ),
                priority=50,
            )
        )
    return sorted(rows, key=lambda item: (item.plan_variant, item.priority))


def _append_event(
    events: list[PlanEventPoint],
    *,
    plan_variant: str,
    month: int | None,
    category: Literal[
        "account",
        "income",
        "investment",
        "home_purchase",
        "loan",
        "provident",
        "vehicle",
        "renovation",
        "risk",
    ],
    title: str,
    detail: str,
    amount: float | None = None,
    severity: Literal["info", "success", "warning", "danger"] = "info",
) -> None:
    events.append(
        PlanEventPoint(
            plan_variant=plan_variant,
            month=max(0, int(month or 0)),
            category=category,
            title=title,
            detail=detail,
            amount=round(amount, 2) if amount is not None else None,
            severity=severity,
        )
    )


def _vehicle_update_month(plan: CarPlanData, purchase_month: int | None) -> int | None:
    if purchase_month is None:
        return None
    service_months = max(1, plan.vehicle_service_years) * 12
    mileage_months = ceil(max(1.0, plan.vehicle_retirement_mileage_km) / max(plan.annual_mileage_km, 1) * 12)
    return purchase_month + min(service_months, mileage_months)


def _vehicle_events_for_plan(
    events: list[PlanEventPoint],
    *,
    plan_variant: str,
    title_prefix: str,
    car_plan: CarPlanData,
    car_loan: CarLoanSummary,
) -> None:
    if not car_plan.enabled or not car_loan.enabled:
        return
    purchase_month = car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else car_plan.purchase_delay_months
    _append_event(
        events,
        plan_variant=plan_variant,
        month=purchase_month,
        category="vehicle",
        title=f"{title_prefix}购入",
        detail=(
            f"首付 {_money_text(car_loan.down_payment)}，车贷本金 {_money_text(car_loan.loan_principal)}，"
            f"现金养车月度成本约 {_money_text(car_loan.monthly_cash_operating_cost)}；保险和保养按年度发生月计入现金流。"
        ),
        amount=car_loan.down_payment,
        severity="success",
    )
    if car_loan.loan_principal > 0 and car_loan.interest_free_months > 0 and car_loan.interest_free_months < car_loan.total_months:
        _append_event(
            events,
            plan_variant=plan_variant,
            month=purchase_month + car_loan.interest_free_months,
            category="loan",
            title=f"{title_prefix}0 息期结束",
            detail=f"后段车贷月供约 {_money_text(car_loan.later_phase_monthly_payment)}，贷款余额继续由后端逐月推演。",
            amount=car_loan.later_phase_monthly_payment,
            severity="warning",
        )
    if car_loan.loan_principal > 0:
        _append_event(
            events,
            plan_variant=plan_variant,
            month=purchase_month + car_loan.total_months,
            category="loan",
            title=f"{title_prefix}贷款结清",
            detail="车贷结清后，现金流只保留电费、停车、年度保险和年度保养等持有成本。",
            severity="success",
        )
    update_month = _vehicle_update_month(car_plan, purchase_month)
    if update_month is not None:
        _append_event(
            events,
            plan_variant=plan_variant,
            month=update_month,
            category="vehicle",
            title=f"{title_prefix}更新/报废提醒",
            detail=(
                f"按 {car_plan.vehicle_service_years} 年使用年限和 {round(car_plan.vehicle_retirement_mileage_km)} 公里阈值估算，"
                "届时应重新评估置换预算和贷款策略。"
            ),
            severity="warning",
        )


def build_plan_events(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    monthly_cashflow: list[MonthlyCashflowPoint],
) -> list[PlanEventPoint]:
    current_month = date(date.today().year, date.today().month, 1)
    monthly_by_plan_month = {(row.plan_variant, row.month): row for row in monthly_cashflow}
    second_plan = _second_car_plan(household.car_plan)
    second_loan = calculate_car_loan(second_plan) if second_plan.enabled else None
    events: list[PlanEventPoint] = []
    for plan in purchase_plans:
        _append_event(
            events,
            plan_variant=plan.variant,
            month=0,
            category="account",
            title="当前账户快照",
            detail=(
                f"现金账户 {_money_text(household.liquid_assets)}，投资账户 {_money_text(household.investments)}，"
                f"公积金账户 {_money_text(household.provident_fund_balance)}。这些余额后续由后端账户引擎逐月推演。"
            ),
        )
        _append_event(
            events,
            plan_variant=plan.variant,
            month=0,
            category="investment",
            title="理财策略启动",
            detail=(
                f"目标月定投 {_money_text(household.monthly_investment_amount)}；后端会先保护现金安全垫，"
                "现金不足时减少或暂停定投，现金超额时按滚动节奏转入投资账户，投资收益留在投资账户复利。"
            ),
        )
        if not household.car_plan.enabled:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=0,
                category="vehicle",
                title="不买车模式",
                detail=f"当前不规划购车，通勤按无车成本 {_money_text(household.car_plan.no_car_monthly_commute_cost)}/月计入现金流。",
            )
        else:
            _vehicle_events_for_plan(
                events,
                plan_variant=plan.variant,
                title_prefix="车辆",
                car_plan=household.car_plan,
                car_loan=car_loan,
            )
        if second_plan.enabled and second_loan:
            _vehicle_events_for_plan(
                events,
                plan_variant=plan.variant,
                title_prefix="第二辆车",
                car_plan=second_plan,
                car_loan=second_loan,
            )

        for member in household.members:
            for stage in member.income_stages:
                if not stage.name.startswith("自动情景："):
                    continue
                start = _parse_iso_date(stage.start_date, current_month)
                month = max(0, _months_between_months(current_month, date(start.year, start.month, 1)))
                if stage.monthly_non_taxable_income > 0:
                    detail = f"非税现金收入约 {_money_text(stage.monthly_non_taxable_income)}/月。"
                elif stage.monthly_extra_cash_expense > 0:
                    detail = f"额外现金支出约 {_money_text(stage.monthly_extra_cash_expense)}/月。"
                else:
                    detail = "该收入阶段改变工资、社保、公积金或现金流口径。"
                _append_event(
                    events,
                    plan_variant=plan.variant,
                    month=month,
                    category="income",
                    title=f"{member.name}{stage.name.replace('自动情景：', '')}",
                    detail=detail,
                    severity="warning",
                )

        if plan.months_to_buy is None:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=360,
                category="risk",
                title="购房策略暂不可执行",
                detail=(
                    f"后端没有在 30 年内找到现金账户不穿底的执行点；压力短缺约 {_money_text(plan.cash_stress_shortfall)}。"
                ),
                amount=plan.cash_stress_shortfall,
                severity="danger",
            )
            continue

        purchase_month = plan.months_to_buy
        purchase_point = monthly_by_plan_month.get((plan.variant, purchase_month))
        _append_event(
            events,
            plan_variant=plan.variant,
            month=purchase_month,
            category="home_purchase",
            title="购房交易",
            detail=(
                f"交易现金需覆盖 {_money_text(plan.required_cash_after_pf_extract)}，交易当下现金约 {_money_text(plan.cash_after_transaction)}；"
                f"交易后现金约 {_money_text(plan.cash_after_purchase)}。"
            ),
            amount=plan.required_cash_after_pf_extract,
            severity="success" if plan.cash_stress_ok else "warning",
        )
        _append_event(
            events,
            plan_variant=plan.variant,
            month=purchase_month,
            category="provident",
            title="首付与公积金提取",
            detail=(
                f"本人公积金交易前抵扣 {_money_text(plan.provident_upfront_extractable)}，亲属首付支持 {_money_text(plan.family_down_payment_support_amount)}；"
                f"交易后预计到账 {_money_text(plan.provident_post_transaction_extractable)}，购后策略为“{plan.post_purchase_pf_strategy_label}”。"
            ),
            amount=plan.provident_upfront_extractable + plan.family_down_payment_support_amount,
        )
        if purchase_point and purchase_point.transaction_cash_in > 0:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=purchase_month,
                category="investment",
                title="投资账户变现",
                detail=(
                    f"交易月投资账户变现和其他交易流入合计 {_money_text(purchase_point.transaction_cash_in)}；"
                    f"卖出手续费计入当月投资费用，后续投资账户重新从定投策略推演。"
                ),
                amount=purchase_point.transaction_cash_in,
            )
        _append_event(
            events,
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
            amount=plan.provident_loan_amount + plan.commercial_loan_amount,
        )
        if plan.provident_loan_year_limit_reasons:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=purchase_month,
                category="provident",
                title="公积金贷款年限依据",
                detail="；".join(plan.provident_loan_year_limit_reasons),
            )
        if not plan.cash_stress_ok:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=plan.minimum_cash_balance_month,
                category="risk",
                title="压力现金缺口",
                detail=(
                    f"后端压力推演最低现金约 {_money_text(plan.minimum_cash_balance)}，短缺约 {_money_text(plan.cash_stress_shortfall)}；"
                    "现金账户不能为负，应延后或调整策略。"
                ),
                amount=plan.cash_stress_shortfall,
                severity="danger",
            )
        if scenario.renovation_cost > 0:
            renovation_month = (
                purchase_month
                if plan.renovation_included_in_upfront_cash
                else purchase_month + plan.months_to_renovation
                if plan.months_to_renovation is not None
                else purchase_month
            )
            _append_event(
                events,
                plan_variant=plan.variant,
                month=renovation_month,
                category="renovation",
                title="装修资金",
                detail=(
                    f"装修预算 {_money_text(scenario.renovation_cost)}。"
                    if plan.renovation_included_in_upfront_cash
                    else f"装修预算 {_money_text(scenario.renovation_cost)} 买后慢慢攒；后端按买后月结余 {_money_text(plan.post_purchase_renovation_monthly_saving)} 估算启动时间。"
                ),
                amount=scenario.renovation_cost,
                severity="success" if plan.months_to_renovation is not None else "warning",
            )

    category_order = {
        "account": 0,
        "income": 1,
        "investment": 2,
        "vehicle": 3,
        "home_purchase": 4,
        "loan": 5,
        "provident": 6,
        "renovation": 7,
        "risk": 8,
    }
    plan_order = {plan.variant: index for index, plan in enumerate(purchase_plans)}
    return sorted(events, key=lambda item: (plan_order.get(item.plan_variant, 999), item.month, category_order[item.category], item.title))


def evaluate_eligibility(household: HouseholdData, rules: RulePackData) -> tuple[bool, list[str]]:
    params = rules.params
    required_months = int(params.get("required_social_security_months", 36))
    max_home_count = int(params.get("max_home_count", 2))

    notes: list[str] = []
    has_local_qualification = household.has_beijing_hukou or household.social_security_months >= required_months
    if has_local_qualification:
        notes.append("已满足北京户籍或社保/个税年限的规则包条件。")
    else:
        notes.append(f"社保/个税年限低于当前规则包要求的 {required_months} 个月。")

    within_home_count = household.existing_home_count < max_home_count
    if within_home_count:
        notes.append("现有住房套数低于规则包上限。")
    else:
        notes.append(f"现有住房套数已达到规则包上限 {max_home_count} 套。")

    return has_local_qualification and within_home_count, notes


def calculate_affordability(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    stress_name: str | None = None,
) -> AffordabilityResult:
    household = _household_with_career_income_stages(household, rules)
    parallel_workers = 1 if stress_name else _parallel_worker_count(rules, 4)
    params = rules.params
    min_down_payment_ratio = float(params.get("minimum_down_payment_ratio", 0.30))
    recommended_emergency_months = float(params.get("recommended_emergency_months", 6))
    caution_dti = float(params.get("caution_dti", 0.40))
    danger_dti = float(params.get("danger_dti", 0.50))
    tax_summaries, gross_monthly_income, net_monthly_income, annual_income_tax = calculate_household_tax(
        household,
        rules,
    )
    phased_loan_summaries = summarize_phased_loans(household.phased_loans)
    phased_loan_monthly_payment = sum(item.current_monthly_payment for item in phased_loan_summaries)
    effective_monthly_debt_payment = household.monthly_debt_payment + phased_loan_monthly_payment
    cashflow_household = household.model_copy(
        update={"monthly_debt_payment": effective_monthly_debt_payment}
    )
    current_monthly_expense = monthly_household_expense_at(cashflow_household)
    current_income_profile = household_monthly_income_profile_at(cashflow_household, rules, 0)
    car_loan = calculate_car_loan(
        cashflow_household.car_plan,
        initial_cash=cashflow_household.liquid_assets + cashflow_household.investments,
        monthly_cash_savings_before_car=max(
            0,
            current_income_profile.net_income - current_monthly_expense - cashflow_household.monthly_debt_payment,
        ),
    )
    car_plan_analyses = build_car_plan_analyses(
        cashflow_household,
        net_monthly_income=net_monthly_income,
    )

    eligible, eligibility_notes = evaluate_eligibility(cashflow_household, rules)
    minimum_down_payment = scenario.total_price * min_down_payment_ratio
    stated_down_payment = max(scenario.down_payment_amount, minimum_down_payment)
    deed_tax = scenario.total_price * scenario.deed_tax_rate
    broker_fee = scenario.total_price * scenario.broker_fee_rate
    upfront_renovation_cost = (
        scenario.renovation_cost if scenario.renovation_funding_mode == "upfront_cash" else 0
    )
    taxes_and_fees = deed_tax + broker_fee + scenario.moving_and_misc_cost + upfront_renovation_cost
    purchase_plan_analyses = build_purchase_plan_analyses(
        cashflow_household,
        scenario,
        rules,
        tax_summaries=tax_summaries,
        net_monthly_income=net_monthly_income,
        car_loan=car_loan,
        taxes_and_fees=taxes_and_fees,
    )
    yield_sensitivity = build_yield_sensitivity(
        cashflow_household,
        scenario,
        rules,
        tax_summaries=tax_summaries,
        net_monthly_income=net_monthly_income,
        car_loan=car_loan,
        taxes_and_fees=taxes_and_fees,
        parallel_workers=min(parallel_workers, 3),
    )
    provident_visualization = build_provident_visualization(
        cashflow_household,
        scenario,
        rules,
        purchase_plan_analyses,
        car_loan,
    )
    loan_visualization = build_loan_visualization(
        cashflow_household,
        scenario,
        purchase_plan_analyses,
        car_loan,
        base_monthly_debt_payment=household.monthly_debt_payment,
        provident_visualization=provident_visualization,
    )
    monthly_cashflow_visualization, account_snapshots, monthly_ledger = build_monthly_cashflow_visualization(
        cashflow_household,
        scenario,
        rules,
        purchase_plan_analyses,
        car_loan,
        loan_visualization,
        provident_visualization,
    )
    account_concepts = build_account_concepts()
    strategy_explanations = build_strategy_explanations(purchase_plan_analyses)
    plan_events = build_plan_events(
        cashflow_household,
        scenario,
        purchase_plan_analyses,
        car_loan,
        monthly_cashflow_visualization,
    )
    total_required_cash = stated_down_payment + taxes_and_fees + _car_down_payment_at(cashflow_household.car_plan, car_loan, 0)
    remaining_cash = cashflow_household.liquid_assets - total_required_cash
    funding_gap = max(0, -remaining_cash)

    commercial = _loan_summary(
        scenario.commercial_loan_amount,
        scenario.commercial_rate,
        scenario.loan_years,
        _commercial_repayment_method(scenario),
    )
    provident_loan_years, provident_year_reasons = _provident_loan_years(cashflow_household, scenario, rules)
    provident = _loan_summary(
        scenario.provident_loan_amount,
        scenario.provident_rate,
        provident_loan_years,
        _provident_repayment_method(scenario),
    )

    monthly_payment = 0.0
    if commercial:
        monthly_payment += commercial.first_month_payment
    if provident:
        monthly_payment += provident.first_month_payment

    car_purchased_now = cashflow_household.car_plan.enabled and car_loan.enabled and car_loan.purchase_delay_months <= 0
    second_plan = _second_car_plan(cashflow_household.car_plan)
    second_loan = calculate_car_loan(second_plan) if second_plan.enabled else None
    second_car_purchased_now = bool(second_loan and second_loan.enabled and second_loan.purchase_delay_months <= 0)
    current_transport_cost = (
        car_loan.current_monthly_payment + car_loan.monthly_cash_operating_cost
        if car_purchased_now
        else _no_car_commute_cost(cashflow_household.car_plan)
    )
    if second_car_purchased_now and second_loan:
        current_transport_cost += second_loan.current_monthly_payment + second_loan.monthly_cash_operating_cost
    current_car_payment = (car_loan.current_monthly_payment if car_purchased_now else 0.0) + (
        second_loan.current_monthly_payment if second_car_purchased_now and second_loan else 0.0
    )
    monthly_income = max(net_monthly_income, 1)
    post_purchase_cash_flow = (
        net_monthly_income
        - current_monthly_expense
        - cashflow_household.monthly_debt_payment
        - current_transport_cost
        - monthly_payment
    )
    debt_to_income_ratio = (
        cashflow_household.monthly_debt_payment + current_car_payment + monthly_payment
    ) / monthly_income
    monthly_burn = max(
        current_monthly_expense
        + cashflow_household.monthly_debt_payment
        + current_transport_cost
        + monthly_payment,
        1,
    )
    emergency_months = max(0, remaining_cash) / monthly_burn

    if not eligible:
        status = "不可行"
        status_reason = "购房资格条件未通过当前规则包。"
    elif funding_gap > 0:
        status = "不可行"
        status_reason = "可动用现金不足以覆盖首付和一次性费用。"
    elif debt_to_income_ratio > danger_dti:
        status = "不可行"
        status_reason = "购后负债收入比超过高风险阈值。"
    elif debt_to_income_ratio > caution_dti or emergency_months < recommended_emergency_months:
        status = "谨慎可行"
        status_reason = "资金可覆盖购房，但现金流或应急金低于推荐安全垫。"
    else:
        status = "可行"
        status_reason = "资金、现金流和应急金均满足当前规则包阈值。"

    result = AffordabilityResult(
        status=status,
        status_reason=status_reason,
        eligible=eligible,
        eligibility_notes=eligibility_notes,
        total_required_cash=round(total_required_cash, 2),
        minimum_down_payment=round(minimum_down_payment, 2),
        stated_down_payment=round(stated_down_payment, 2),
        taxes_and_fees=round(taxes_and_fees, 2),
        funding_gap=round(funding_gap, 2),
        remaining_cash_after_purchase=round(remaining_cash, 2),
        household_gross_monthly_income=round(gross_monthly_income, 2),
        household_net_monthly_income=round(net_monthly_income, 2),
        annual_income_tax=round(annual_income_tax, 2),
        phased_loan_monthly_payment=round(phased_loan_monthly_payment, 2),
        effective_monthly_debt_payment=round(effective_monthly_debt_payment, 2),
        phased_loan_summaries=phased_loan_summaries,
        car_loan=car_loan,
        car_plan_analyses=car_plan_analyses,
        monthly_payment=round(monthly_payment, 2),
        post_purchase_cash_flow=round(post_purchase_cash_flow, 2),
        debt_to_income_ratio=round(debt_to_income_ratio, 4),
        emergency_months=round(emergency_months, 2),
        commercial_loan=commercial,
        provident_loan=provident,
        tax_summaries=tax_summaries,
        purchase_plan_analyses=purchase_plan_analyses,
        yield_sensitivity=yield_sensitivity,
        monthly_cashflow_visualization=monthly_cashflow_visualization,
        account_snapshots=account_snapshots,
        monthly_ledger=monthly_ledger,
        loan_visualization=loan_visualization,
        provident_visualization=provident_visualization,
        account_concepts=account_concepts,
        strategy_explanations=strategy_explanations,
        plan_events=plan_events,
        stress_tests=[],
        assumptions=[
            "测算结果仅用于家庭规划，不构成购房、税务、法律或银行审批意见。",
            "政策、税费、贷款额度和利率以规则包和用户手动录入为准。",
            "北京公积金贷款额度按当前规则包的每缴存年额度估算；夫妻分别缴存时，现阶段用家庭录入的社保/个税月数近似代表较长缴存年限。",
            f"北京公积金贷款期限按设定年限、30 年上限、借款人年龄和二手房房龄/土地剩余年限取短；当前测算：{'；'.join(provident_year_reasons)}。",
            "公积金提取区分交易前现金、交易后购房提取和购后账户留存：默认不把买房后的月缴存公积金计入自由现金流。",
            "目前贷款在只还利息阶段按本金乘年利率除以 12 计入有效月债务，到期后按剩余期数转为等额本息或等额本金估算。",
            "等额本金场景使用首月月供评估现金流压力。",
            "工资薪金和全年一次性奖金按规则包税率表估算，未覆盖劳务报酬、经营所得等复杂申报情形。",
            "家庭支出按基础月支出叠加定时月支出测算；不符合税收养老条件的家庭支持支出只进入现金流，不进入个税专项附加扣除。",
        ],
    )

    if stress_name is None:
        result.stress_tests = build_stress_tests(household, scenario, rules, parallel_workers=min(parallel_workers, 3))
    return result


def build_stress_tests(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    parallel_workers: int = 1,
) -> list[StressResult]:
    params = rules.params
    rate_add = float(params.get("rate_stress_add", 0.005))
    income_factor = float(params.get("income_stress_factor", 0.90))
    price_factor = float(params.get("price_stress_factor", 1.05))

    rate_scenario = scenario.model_copy(
        update={
            "commercial_rate": scenario.commercial_rate + rate_add,
            "provident_rate": scenario.provident_rate + rate_add,
        }
    )
    income_household = household.model_copy(update={"monthly_income": household.monthly_income * income_factor})
    if household.members:
        income_household = income_household.model_copy(
            update={
                "members": [
                    member.model_copy(
                        update={
                            "monthly_salary_gross": member.monthly_salary_gross * income_factor,
                            "income_stages": [
                                stage.model_copy(
                                    update={
                                        "monthly_salary_gross": stage.monthly_salary_gross * income_factor,
                                        "annual_bonus": stage.annual_bonus * income_factor,
                                        "other_annual_taxable_income": stage.other_annual_taxable_income * income_factor,
                                    }
                                )
                                for stage in member.income_stages
                            ],
                        }
                    )
                    for member in household.members
                ]
            }
        )
    price_scenario = scenario.model_copy(
        update={
            "total_price": scenario.total_price * price_factor,
            "down_payment_amount": scenario.down_payment_amount * price_factor,
            "commercial_loan_amount": scenario.commercial_loan_amount * price_factor,
            "provident_loan_amount": scenario.provident_loan_amount * price_factor,
        }
    )

    cases = [
        ("利率上行", household, rate_scenario),
        ("收入下降", income_household, scenario),
        ("房价上行", household, price_scenario),
    ]

    def run_case(case: tuple[str, HouseholdData, ScenarioData]) -> StressResult:
        name, stress_household, stress_scenario = case
        result = calculate_affordability(stress_household, stress_scenario, rules, stress_name=name)
        return StressResult(
            name=name,
            status=result.status,
            monthly_payment=result.monthly_payment,
            post_purchase_cash_flow=result.post_purchase_cash_flow,
            debt_to_income_ratio=result.debt_to_income_ratio,
            emergency_months=result.emergency_months,
        )

    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            return list(executor.map(run_case, cases))
    return [run_case(case) for case in cases]
