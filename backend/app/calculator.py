from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from math import ceil
from typing import Callable, Literal

from .policies import get_policy
from .schemas import (
    AccountSnapshotPoint,
    AnnualFinancialSummary,
    AffordabilityResult,
    BonusTaxMethod,
    CarLoanSummary,
    CarPlanAnalysis,
    CarPlanData,
    CareerShockProjection,
    CareerShockMemberProjection,
    ElderlyDependentData,
    HouseholdData,
    IncomeMember,
    IncomeStageData,
    InvestmentAllocationSummary,
    InvestmentPlanRecommendation,
    ExistingLoanVisualizationDetail,
    LoanSummary,
    LoanVisualizationPoint,
    AccountConceptSummary,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    PlanEventPoint,
    ProvidentMemberAccountPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    StrategyExplanationPoint,
    StressResult,
    PhasedLoanData,
    PhasedLoanSummary,
    TaxMemberSummary,
    TaxMemberMonthlyPoint,
    TaxMonthlyPoint,
    TaxEventPoint,
    TaxYearSummary,
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
class LoanMonthProjection:
    balance_start: float
    interest: float
    contract_payment: float
    extra_principal_payment: float
    total_payment: float
    balance_end: float


@dataclass(frozen=True)
class LoanProjection:
    points: tuple[LoanMonthProjection, ...]
    total_interest: float
    actual_payoff_months: int
    interest_saved_by_prepayment: float


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
class MemberSalaryTaxState:
    previous_tax: float
    current_tax: float
    cumulative_taxable_income: float


@dataclass(frozen=True)
class PurchaseCandidate:
    purchase_month: int
    mix: tuple[float, float, float, float, float, float, float]
    pf_upfront_extractable: float
    family_pf_upfront_extractable: float
    pf_post_transaction_extractable: float
    cash_account_before_purchase: float
    investment_balance_before_purchase: float
    investment_sell_gross_at_purchase: float
    investment_sell_proceeds_at_purchase: float
    investment_balance_after_purchase: float
    cash_after_transaction: float
    cash_after_purchase: float
    pf_after_extract: float
    minimum_cash_balance: float
    minimum_cash_balance_month: int | None
    cash_stress_ok: bool
    cash_stress_shortfall: float


@dataclass(frozen=True)
class InvestmentWithdrawalResult:
    mode: str
    mode_label: str
    cash_before_transaction: float
    investment_before_transaction: float
    gross_sell: float
    sell_fee: float
    sell_proceeds: float
    investment_after_transaction: float
    cash_after_transaction: float


VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


@dataclass(frozen=True)
class VehicleMonthProjection:
    total_cash_cost: float
    first_down_payment: float
    extra_down_payment: float
    total_down_payment: float
    no_car_commute_cost: float
    components_by_index: dict[int, dict[str, float]]
    first_asset_value: float
    extra_asset_value: float
    total_asset_value: float


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


def _loan_projection_with_prepayment(
    principal: float,
    annual_rate: float,
    total_months: int,
    method: str,
    *,
    prepayment_monthly_amount: float = 0.0,
    prepayment_start_month: int = 1,
) -> LoanProjection:
    if principal <= 0 or total_months <= 0:
        return LoanProjection((), 0.0, 0, 0.0)

    monthly_rate = annual_rate / 12
    extra_monthly = max(0.0, prepayment_monthly_amount)
    start_month = max(1, int(prepayment_start_month))
    fixed_payment = 0.0
    baseline_interest = 0.0
    principal_per_month = principal / total_months
    if method != "equal_principal":
        if monthly_rate <= 0:
            fixed_payment = principal / total_months
        else:
            factor = (1 + monthly_rate) ** total_months
            fixed_payment = principal * monthly_rate * factor / (factor - 1)
            baseline_interest = fixed_payment * total_months - principal
    elif monthly_rate > 0:
        baseline_interest = monthly_rate * principal_per_month * total_months * (total_months + 1) / 2

    balance = principal
    total_interest = 0.0
    points: list[LoanMonthProjection] = []
    for month_index in range(1, total_months + 1):
        if balance <= 0:
            break
        balance_start = balance
        interest = max(0.0, balance_start * monthly_rate)
        if method == "equal_principal":
            scheduled_principal = min(balance_start, principal_per_month)
            contract_payment = scheduled_principal + interest
        else:
            contract_payment = min(balance_start + interest, fixed_payment)
            scheduled_principal = max(0.0, min(balance_start, contract_payment - interest))
        balance_after_contract = max(0.0, balance_start - scheduled_principal)
        extra_principal = min(
            balance_after_contract,
            extra_monthly if month_index >= start_month else 0.0,
        )
        balance = max(0.0, balance_after_contract - extra_principal)
        total_interest += interest
        points.append(
            LoanMonthProjection(
                balance_start=balance_start,
                interest=interest,
                contract_payment=contract_payment,
                extra_principal_payment=extra_principal,
                total_payment=contract_payment + extra_principal,
                balance_end=balance,
            )
        )

    interest_saved = max(0.0, baseline_interest - total_interest) if extra_monthly > 0 else 0.0
    return LoanProjection(
        points=tuple(points),
        total_interest=total_interest,
        actual_payoff_months=len(points),
        interest_saved_by_prepayment=interest_saved,
    )


def _loan_projection_point_after_payments(
    principal: float,
    annual_rate: float,
    total_months: int,
    method: str,
    elapsed_payments: int,
    *,
    prepayment_monthly_amount: float = 0.0,
    prepayment_start_month: int = 1,
) -> tuple[float, float, float]:
    if principal <= 0 or total_months <= 0:
        return 0.0, 0.0, 0.0
    paid_months = max(0, int(elapsed_payments))
    projection = _loan_projection_with_prepayment(
        principal,
        annual_rate,
        total_months,
        method,
        prepayment_monthly_amount=prepayment_monthly_amount,
        prepayment_start_month=prepayment_start_month,
    )
    if paid_months <= 0:
        first_point = projection.points[0] if projection.points else None
        return principal, first_point.contract_payment if first_point else 0.0, first_point.extra_principal_payment if first_point else 0.0
    if paid_months > len(projection.points):
        return 0.0, 0.0, 0.0
    previous = projection.points[paid_months - 1]
    return previous.balance_end, previous.contract_payment, previous.extra_principal_payment


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


def _vehicle_loan_projection(
    principal: float,
    total_months: int,
    interest_free_months: int,
    later_annual_rate: float,
    *,
    prepayment_monthly_amount: float = 0.0,
    prepayment_start_month: int = 1,
) -> LoanProjection:
    if principal <= 0 or total_months <= 0:
        return LoanProjection((), 0.0, 0, 0.0)
    interest_free_months = max(0, min(interest_free_months, total_months))
    later_months = max(0, total_months - interest_free_months)
    principal_per_month = principal / total_months
    standard_remaining_principal = max(0.0, principal - principal_per_month * interest_free_months)
    later_monthly = 0.0
    monthly_rate = later_annual_rate / 12
    if later_months > 0:
        if monthly_rate <= 0:
            later_monthly = standard_remaining_principal / later_months
        else:
            factor = (1 + monthly_rate) ** later_months
            later_monthly = standard_remaining_principal * monthly_rate * factor / (factor - 1)
    baseline_interest = max(0.0, later_monthly * later_months - standard_remaining_principal)

    balance = principal
    total_interest = 0.0
    extra_monthly = max(0.0, prepayment_monthly_amount)
    start_month = max(1, int(prepayment_start_month))
    points: list[LoanMonthProjection] = []
    for month_index in range(1, total_months + 1):
        if balance <= 0:
            break
        balance_start = balance
        if month_index <= interest_free_months:
            interest = 0.0
            contract_payment = min(balance_start, principal_per_month)
        else:
            interest = max(0.0, balance_start * monthly_rate)
            contract_payment = min(balance_start + interest, later_monthly)
        scheduled_principal = max(0.0, min(balance_start, contract_payment - interest))
        balance_after_contract = max(0.0, balance_start - scheduled_principal)
        extra_principal = min(
            balance_after_contract,
            extra_monthly if month_index >= start_month else 0.0,
        )
        balance = max(0.0, balance_after_contract - extra_principal)
        total_interest += interest
        points.append(
            LoanMonthProjection(
                balance_start=balance_start,
                interest=interest,
                contract_payment=contract_payment,
                extra_principal_payment=extra_principal,
                total_payment=contract_payment + extra_principal,
                balance_end=balance,
            )
        )

    return LoanProjection(
        points=tuple(points),
        total_interest=total_interest,
        actual_payoff_months=len(points),
        interest_saved_by_prepayment=max(0.0, baseline_interest - total_interest) if extra_monthly > 0 else 0.0,
    )


def _vehicle_loan_point_after_payments(loan: CarLoanSummary, elapsed_payments: int) -> tuple[float, float, float]:
    if loan.loan_principal <= 0 or loan.total_months <= 0:
        return 0.0, 0.0, 0.0
    projection = _vehicle_loan_projection(
        loan.loan_principal,
        loan.total_months,
        loan.interest_free_months,
        loan.later_annual_rate,
        prepayment_monthly_amount=loan.prepayment_monthly_amount if loan.prepayment_enabled else 0.0,
        prepayment_start_month=loan.prepayment_start_month,
    )
    paid_months = max(0, int(elapsed_payments))
    if paid_months <= 0:
        first_point = projection.points[0] if projection.points else None
        return loan.loan_principal, first_point.contract_payment if first_point else 0.0, first_point.extra_principal_payment if first_point else 0.0
    if paid_months > len(projection.points):
        return 0.0, 0.0, 0.0
    previous = projection.points[paid_months - 1]
    return previous.balance_end, previous.contract_payment, previous.extra_principal_payment


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
        return (
            max(0.0, member.monthly_social_insurance),
            max(0.0, member.monthly_housing_fund),
            0.0,
            0.0,
        )
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


@lru_cache(maxsize=512)
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
    settings = _career_shock_settings_by_member(household)
    for index, member in enumerate(household.members):
        setting = settings.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        targets.append(
            max(
                0,
                _months_between_months(
                    current_month,
                    _month_start_for_birth_month_or_age(
                        current_month,
                        effective_birth_month,
                        effective_current_age,
                        setting.retirement_age if setting else _policy_retirement_age_for_member(member, index),
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
    vehicle_states: list[VehicleLoanState] | None = None,
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
    vehicle_horizons = [
        (purchase_month or 0) + loan.total_months + 24
        for _, _, loan, purchase_month in (vehicle_states if vehicle_states is not None else _vehicle_loan_states(household.car_plan))
        if loan.enabled
    ]
    if not vehicle_horizons and car_loan.enabled:
        first_vehicle_start = car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else car_loan.purchase_delay_months
        vehicle_horizons.append(first_vehicle_start + car_loan.total_months + 24)
    if second_loan and second_loan.enabled:
        second_vehicle_start = second_loan.months_to_down_payment if second_loan.months_to_down_payment is not None else second_loan.purchase_delay_months
        vehicle_horizons.append(second_vehicle_start + second_loan.total_months + 24)
    return min(840, max(180, _retirement_tail_months(household), *plan_horizons, *vehicle_horizons))


def _zero_cash_stage(template: IncomeStageData, name: str, start: date, end: date | None = None) -> IncomeStageData:
    return template.model_copy(
        update={
            "name": name,
            "stage_kind": "manual",
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else None,
            "monthly_salary_gross": 0,
            "annual_bonus": 0,
            "annual_bonus_payout_month": template.annual_bonus_payout_month,
            "monthly_freelance_income": 0,
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


def _default_retirement_age_for_member(index: int) -> int:
    return 63 if index == 0 else 58


def _policy_retirement_age_for_member(member, index: int) -> int:
    category = getattr(member, "retirement_category", None)
    if category == "female_50":
        return 55
    if category == "female_55":
        return 58
    if category == "male_60":
        return 63
    return _default_retirement_age_for_member(index)


def _career_shock_settings_by_member(household: HouseholdData):
    shock = household.career_shock
    settings_by_name = {item.member_name: item for item in shock.member_settings}
    return {
        member.name: settings_by_name.get(member.name)
        for member in household.members
    }


def _member_retirement_months_by_index(
    household: HouseholdData,
    *,
    as_of: date | None = None,
) -> dict[int, int]:
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    settings_by_member = _career_shock_settings_by_member(household)
    retirement_months: dict[int, int] = {}
    for index, member in enumerate(household.members):
        setting = settings_by_member.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = _policy_retirement_age_for_member(member, index)
        retirement_start = _month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        retirement_months[index] = max(0, _months_between_months(current_month, retirement_start))
    return retirement_months


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


def _career_shock_flexible_housing_fund_monthly(shock: "CareerShockData", rules: RulePackData) -> float:
    if not shock.auto_flexible_housing_fund:
        return max(0.0, shock.self_housing_fund_monthly)
    params = rules.params
    if not bool(params.get("flexible_employment_housing_fund_enabled", True)):
        return 0.0
    raw_base = float(params.get("flexible_employment_housing_fund_base", params.get("beijing_housing_fund_base_floor", 2540)))
    floor = float(params.get("beijing_housing_fund_base_floor", 2540))
    ceiling = float(params.get("beijing_housing_fund_base_ceiling", 35811))
    base = _clamp(raw_base, floor, ceiling)
    rate = _clamp(float(params.get("flexible_employment_housing_fund_rate", 0.12)), 0.0, 0.24)
    return round(base * rate, 2)


def _estimate_auto_pension_monthly(
    member: IncomeMember,
    setting: "CareerShockMemberSetting",
    rules: RulePackData,
    retirement_start: date,
    as_of: date,
) -> float:
    params = rules.params
    manual_value = max(0.0, setting.pension_monthly)
    if not setting.auto_pension_monthly:
        return manual_value

    current_month = date(as_of.year, as_of.month, 1)
    months_to_retirement = max(0, _months_between_months(current_month, retirement_start))
    stages = sorted(
        member.income_stages or [],
        key=lambda stage: _parse_iso_date(stage.start_date, date(1900, 1, 1)),
    )
    current_stage = stages[-1] if stages else IncomeStageData(
        monthly_salary_gross=member.monthly_salary_gross,
        annual_bonus=member.annual_bonus,
    )
    current_salary = max(member.monthly_salary_gross, current_stage.monthly_salary_gross)
    social_floor = float(params.get("beijing_social_base_floor", 7162))
    social_ceiling = float(params.get("beijing_social_base_ceiling", 35811))
    contribution_base = _clamp(current_salary if current_salary > 0 else social_floor, social_floor, social_ceiling)
    flexible_base = _clamp(
        float(params.get("flexible_employment_social_base", social_floor)),
        social_floor,
        social_ceiling,
    )
    avg_salary_now = max(
        social_floor,
        min(
            social_ceiling,
            float(params.get("pension_reference_average_salary", params.get("beijing_social_base_ceiling", 35811))),
        ),
    )
    salary_growth = _clamp(float(params.get("pension_average_salary_growth_rate", 0.03)), 0.0, 0.10)
    projected_avg_salary = avg_salary_now * ((1 + salary_growth) ** (months_to_retirement / 12))
    existing_paid_years = max(
        float(params.get("pension_default_paid_years", 15)),
        max(0, member.current_age - 22),
    )
    future_paid_years = months_to_retirement / 12
    total_paid_years = max(15.0, existing_paid_years + future_paid_years)
    indexed_base = (contribution_base + flexible_base) / 2
    basic_pension = projected_avg_salary * (1 + indexed_base / projected_avg_salary) / 2 * total_paid_years * 0.01
    employee_rate = float(params.get("employee_pension_rate", 0.08))
    flexible_rate = float(params.get("flexible_employment_pension_rate", 0.20))
    account_return = _clamp(float(params.get("pension_personal_account_annual_return", 0.025)), 0.0, 0.08)
    existing_account = contribution_base * employee_rate * 12 * existing_paid_years
    future_account = 0.0
    for month in range(max(0, months_to_retirement)):
        future_account = (future_account + flexible_base * flexible_rate * 0.40) * ((1 + account_return) ** (1 / 12))
    account_months = max(1.0, float(params.get("pension_personal_account_months", 139)))
    personal_account_pension = (existing_account + future_account) / account_months
    raw_pension = basic_pension + personal_account_pension
    floor_rate = _clamp(float(params.get("pension_replacement_rate_floor", 0.20)), 0.0, 1.0)
    ceiling_rate = _clamp(float(params.get("pension_replacement_rate_ceiling", 0.65)), floor_rate, 1.2)
    floor_value = projected_avg_salary * floor_rate
    ceiling_value = projected_avg_salary * ceiling_rate
    return round(_clamp(raw_pension, floor_value, ceiling_value), 2)


def _household_with_career_income_stages(
    household: HouseholdData,
    rules: RulePackData | None = None,
    *,
    as_of: date | None = None,
) -> HouseholdData:
    shock = household.career_shock
    if household.career_shock_applied or not household.members:
        return household
    active_rules = rules or RulePackData()

    current = as_of or date.today()
    synthetic_prefix = "自动情景："
    updated_members: list[IncomeMember] = []
    settings_by_member = _career_shock_settings_by_member(household)
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
                    stage_kind="salary",
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
        setting = settings_by_member.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = _policy_retirement_age_for_member(member, index)
        retirement_start = _month_start_for_birth_month_or_age(
            current,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        pension_monthly = (
            _estimate_auto_pension_monthly(member, setting, active_rules, retirement_start, current)
            if setting
            else 0
        )

        if shock.enabled and setting and setting.enabled:
            layoff_start = _month_start_for_birth_month_or_age(
                current,
                effective_birth_month,
                effective_current_age,
                setting.layoff_age,
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
                        f"{synthetic_prefix}{setting.layoff_age}岁被裁员-失业金期",
                        layoff_start,
                        first_end,
                    )
                    stages.append(
                        first_stage.model_copy(
                            update={
                                "stage_kind": "unemployment",
                                "monthly_freelance_income": 0,
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
                                f"{synthetic_prefix}{setting.layoff_age}岁被裁员-失业金后续期",
                                later_start,
                                later_end,
                            )
                            stages.append(
                                later_stage.model_copy(
                                    update={
                                        "stage_kind": "unemployment",
                                        "monthly_freelance_income": 0,
                                        "monthly_non_taxable_income": float(
                                            active_rules.params.get("beijing_unemployment_benefit_after_12_months", 2129)
                                        )
                                    }
                                )
                            )
                else:
                    unemployment_end = _add_months(layoff_start, unemployment_months - 1)
                    end = min(unemployment_end, _end_of_previous_month(retirement_start))
                    unemployment_stage = _zero_cash_stage(template, f"{synthetic_prefix}{setting.layoff_age}岁被裁员-失业金期", layoff_start, end)
                    stages.append(
                        unemployment_stage.model_copy(
                            update={
                                "stage_kind": "unemployment",
                                "monthly_freelance_income": 0,
                                "monthly_non_taxable_income": shock.unemployment_benefit_monthly,
                            }
                        )
                    )
            self_social_start = _add_months(layoff_start, unemployment_months)
            if self_social_start < retirement_start:
                flexible_housing_fund = _career_shock_flexible_housing_fund_monthly(shock, active_rules)
                stages.append(
                    _zero_cash_stage(
                        template,
                        f"{synthetic_prefix}{setting.layoff_age}岁被裁员-灵活就业自缴社保期",
                        self_social_start,
                        _end_of_previous_month(retirement_start),
                    ).model_copy(
                        update={
                            "stage_kind": "freelance",
                            "monthly_freelance_income": 0,
                            "monthly_social_insurance": _career_shock_self_social_monthly(shock, active_rules),
                            "monthly_housing_fund": flexible_housing_fund,
                            "housing_fund_personal_rate": 0,
                            "housing_fund_employer_rate": 0,
                            "payroll_contributions_enabled": False,
                        }
                    )
                )

        if pension_monthly > 0:
            stages.append(
                _zero_cash_stage(template, f"{synthetic_prefix}{retirement_age}岁退休-养老金", retirement_start).model_copy(
                    update={"stage_kind": "pension", "monthly_non_taxable_income": pension_monthly}
                )
            )

        updated_members.append(member.model_copy(update={"income_stages": stages}))

    return household.model_copy(update={"members": updated_members, "career_shock_applied": True})


def _format_month(value: date | None) -> str | None:
    if value is None:
        return None
    return f"{value.year:04d}-{value.month:02d}"


def build_career_shock_projection(
    household: HouseholdData,
    rules: RulePackData,
    *,
    as_of: date | None = None,
) -> CareerShockProjection:
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    shock = household.career_shock
    effective_household = _household_with_career_income_stages(household, rules, as_of=current_month)
    unemployment_months = _career_shock_unemployment_months(household, shock)
    first_unemployment = (
        _unemployment_benefit_monthly_from_service(household.social_security_months, rules)
        if shock.auto_unemployment_benefit
        else max(0.0, shock.unemployment_benefit_monthly)
    )
    later_unemployment = float(rules.params.get("beijing_unemployment_benefit_after_12_months", 2129))
    self_social = _career_shock_self_social_monthly(shock, rules)
    flexible_housing = _career_shock_flexible_housing_fund_monthly(shock, rules)
    settings_by_member = _career_shock_settings_by_member(household)
    member_projections: list[CareerShockMemberProjection] = []
    synthetic_prefix = "自动情景："

    for index, member in enumerate(household.members):
        setting = settings_by_member.get(member.name)
        effective_member = effective_household.members[index] if index < len(effective_household.members) else member
        generated_stages = [
            stage
            for stage in (effective_member.income_stages or [])
            if stage.name.startswith(synthetic_prefix)
        ]
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = _policy_retirement_age_for_member(member, index)
        retirement_start = _month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        layoff_age = setting.layoff_age if setting else 35
        layoff_start = (
            _month_start_for_birth_month_or_age(
                current_month,
                effective_birth_month,
                effective_current_age,
                layoff_age,
            )
            if setting
            else None
        )
        pension_monthly = (
            _estimate_auto_pension_monthly(member, setting, rules, retirement_start, current_month)
            if setting
            else 0.0
        )
        notes = [
            "收入阶段由后端按职业冲击规则生成，前端只展示生成结果。",
            f"退休年龄按成员退休身份和规则包取 {retirement_age} 岁。",
        ]
        if setting and setting.enabled:
            notes.append(
                f"裁员后最多 {unemployment_months} 个月按失业金阶段测算，之后进入灵活就业自缴阶段直到退休。"
            )
        else:
            notes.append("该成员未启用职业冲击，只生成退休养老金阶段。")

        member_projections.append(
            CareerShockMemberProjection(
                member_name=member.name,
                enabled=bool(setting.enabled) if setting else False,
                layoff_age=layoff_age,
                retirement_age=retirement_age,
                layoff_month=_format_month(layoff_start),
                retirement_month=_format_month(retirement_start),
                unemployment_benefit_months=unemployment_months if setting and setting.enabled else 0,
                unemployment_benefit_monthly=round(first_unemployment, 2) if setting and setting.enabled else 0.0,
                later_unemployment_benefit_monthly=round(later_unemployment, 2) if setting and setting.enabled else 0.0,
                self_social_insurance_monthly=round(self_social, 2) if setting and setting.enabled else 0.0,
                flexible_housing_fund_monthly=round(flexible_housing, 2) if setting and setting.enabled else 0.0,
                pension_monthly=round(pension_monthly, 2),
                generated_stages=generated_stages,
                notes=notes,
            )
        )

    return CareerShockProjection(
        enabled=bool(shock.enabled),
        unemployment_benefit_months=unemployment_months,
        unemployment_benefit_monthly=round(first_unemployment, 2),
        later_unemployment_benefit_monthly=round(later_unemployment, 2),
        self_social_insurance_monthly=round(self_social, 2),
        flexible_housing_fund_monthly=round(flexible_housing, 2),
        effective_members=effective_household.members,
        member_projections=member_projections,
        notes=[
            "职业冲击、失业金、自缴社保、自缴公积金和养老金估算均由后端计算。",
            "前端手动参数只改变输入配置，保存后由后端重新生成收入阶段和现金流。",
        ],
    )

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
    salary_taxable = max(
        0.0,
        stage.monthly_salary_gross * 12
        + stage.monthly_freelance_income * 12
        + stage.other_annual_taxable_income
        - common_deductions,
    )
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
                selected_bonus_method = _stage_selected_bonus_method(stage, rules)
                selected_method_cache[stage_key] = selected_bonus_method
            active_months += 1
            cumulative_income += stage.monthly_salary_gross
            cumulative_income += stage.monthly_freelance_income
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
    selected_bonus_method = _stage_selected_bonus_method(stage, rules)
    previous_cumulative_tax, cumulative_tax = _member_cumulative_salary_tax_pair(
        member,
        rules,
        target_month.year,
        target_month.month,
        household,
    )
    salary_tax = max(0.0, cumulative_tax - previous_cumulative_tax)
    bonus_payout = _stage_bonus_payout_amount(stage, target_month.year, target_month.month)
    bonus_tax_due = 0.0
    if selected_bonus_method == "separate":
        bonus_brackets = list(rules.params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
        bonus_tax_due = _bonus_tax(bonus_payout, bonus_brackets) if bonus_payout > 0 else 0.0

    taxable_cash_income = (
        stage.monthly_salary_gross
        + stage.monthly_freelance_income
        + bonus_payout
        + stage.other_annual_taxable_income / 12
    )
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
        salary_annual += stage.monthly_freelance_income * stage_months
        bonus_annual += sum(
            _stage_bonus_payout_amount(stage, projection_year, month)
            for month in range(1, 13)
        )
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


def calculate_household_tax_for_year(household: HouseholdData, rules: RulePackData, year: int) -> TaxYearSummary:
    household = _household_with_career_income_stages(household, rules)
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
    selected_bonus_method = _stage_selected_bonus_method(stage, rules)
    tax_state = _member_cumulative_salary_tax_state(
        member,
        rules,
        target_month.year,
        target_month.month,
        household,
    )
    salary_tax = max(0.0, tax_state.current_tax - tax_state.previous_tax)
    bonus_income = _stage_bonus_payout_amount(stage, target_month.year, target_month.month)
    bonus_tax_due = 0.0
    if selected_bonus_method == "separate" and bonus_income > 0:
        bonus_brackets = list(rules.params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_BONUS_BRACKETS)
        bonus_tax_due = _bonus_tax(bonus_income, bonus_brackets)

    other_taxable_income = stage.monthly_freelance_income + stage.other_annual_taxable_income / 12
    elderly_care_deduction = _elderly_care_deduction_for_member_at(household, member.name, target_month)
    other_deduction = stage.other_annual_deductions / 12
    total_tax = salary_tax + bonus_tax_due
    gross_income = stage.monthly_salary_gross + bonus_income + other_taxable_income + stage.monthly_non_taxable_income
    net_income = gross_income - personal_social - personal_housing_fund - total_tax - stage.monthly_extra_cash_expense

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
        personal_social=round(personal_social, 2),
        personal_housing_fund=round(personal_housing_fund, 2),
        employer_social=round(employer_social, 2),
        employer_housing_fund=round(employer_housing_fund, 2),
        special_additional_deduction=round(stage.monthly_special_additional_deduction, 2),
        elderly_care_deduction=round(elderly_care_deduction, 2),
        other_deduction=round(other_deduction, 2),
        cumulative_taxable_income=round(tax_state.cumulative_taxable_income, 2),
        salary_tax=round(salary_tax, 2),
        bonus_tax=round(bonus_tax_due, 2),
        total_income_tax=round(total_tax, 2),
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
    household = _household_with_career_income_stages(household, rules, as_of=base_date)
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
                extra_cash_expense=round(sum(max(0.0, item.gross_salary + item.bonus_income + item.other_taxable_income + item.non_taxable_income - item.personal_social - item.personal_housing_fund - item.total_income_tax - item.net_income) for item in member_points), 2),
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
    household = _household_with_career_income_stages(household, rules, as_of=base_date)
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


def _phased_loan_phase_at(
    loan: PhasedLoanData,
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> str:
    current = as_of or date.today()
    target_month = _month_after(current, max(0, months_from_now))
    start_month = _parse_month(loan.interest_start_month)
    interest_only_until = _parse_month(loan.interest_only_until)
    if start_month is None or interest_only_until is None or loan.principal <= 0:
        return "配置待校验"
    if _month_distance(target_month, start_month) > 0:
        return "未开始计息"
    if _month_distance(target_month, interest_only_until) >= 0:
        return "只还利息"
    balance, payment = _phased_loan_state_at(loan, months_from_now, as_of=as_of)
    if balance <= 0 and payment <= 0:
        return "已结清"
    return "等额本金" if loan.repayment_method == "equal_principal" else "等额本息"


def _existing_loan_details_at(
    loans: list[PhasedLoanData],
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> list[ExistingLoanVisualizationDetail]:
    details: list[ExistingLoanVisualizationDetail] = []
    for index, loan in enumerate(loans, start=1):
        balance, payment = _phased_loan_state_at(loan, months_from_now, as_of=as_of)
        if balance <= 0 and payment <= 0:
            continue
        details.append(
            ExistingLoanVisualizationDetail(
                name=loan.name or f"已有贷款 {index}",
                borrower=loan.borrower,
                loan_type=loan.loan_type or "other",
                phase=_phased_loan_phase_at(loan, months_from_now, as_of=as_of),
                balance=round(balance, 2),
                monthly_payment=round(payment, 2),
            )
        )
    return details


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
            prepayment_enabled=False,
            prepayment_start_month=max(1, plan.loan_prepayment_start_month, plan.loan_prepayment_allowed_after_month),
            prepayment_allowed_after_month=max(1, plan.loan_prepayment_allowed_after_month),
            prepayment_monthly_amount=0,
            actual_payoff_months=0,
            interest_saved_by_prepayment=0,
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

    prepayment_monthly_amount = (
        max(0.0, plan.loan_prepayment_monthly_amount)
        if plan.loan_prepayment_enabled
        else 0.0
    )
    prepayment_allowed_after_month = max(1, min(total_months, plan.loan_prepayment_allowed_after_month))
    prepayment_start_month = max(
        prepayment_allowed_after_month,
        max(1, min(total_months, plan.loan_prepayment_start_month)),
    )
    loan_projection = _vehicle_loan_projection(
        principal,
        total_months,
        interest_free_months,
        plan.later_annual_rate,
        prepayment_monthly_amount=prepayment_monthly_amount,
        prepayment_start_month=prepayment_start_month,
    )

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
        prepayment_enabled=prepayment_monthly_amount > 0,
        prepayment_start_month=prepayment_start_month,
        prepayment_allowed_after_month=prepayment_allowed_after_month,
        prepayment_monthly_amount=round(prepayment_monthly_amount, 2),
        actual_payoff_months=loan_projection.actual_payoff_months,
        interest_saved_by_prepayment=round(loan_projection.interest_saved_by_prepayment, 2),
        total_interest=round(loan_projection.total_interest if prepayment_monthly_amount > 0 else later_total_interest, 2),
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


def _scenario_purchase_sequence(scenario: ScenarioData | None) -> int:
    return max(1, scenario.purchase_sequence if scenario else 1)


def _vehicle_is_before_or_parallel_home(vehicle: CarPlanData, scenario: ScenarioData | None) -> bool:
    if scenario is None or vehicle.purchase_timing_mode in {"parallel", "manual_month"}:
        return True
    return max(1, vehicle.planning_sequence) <= _scenario_purchase_sequence(scenario)


def _vehicle_base_purchase_month(
    vehicle: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
) -> int:
    if vehicle.purchase_timing_mode == "manual_month":
        return max(0, vehicle.manual_purchase_delay_months)
    if (
        scenario is not None
        and home_purchase_month is not None
        and vehicle.purchase_timing_mode == "auto_sequence"
        and vehicle.planning_sequence > _scenario_purchase_sequence(scenario)
    ):
        return max(0, home_purchase_month + vehicle.after_previous_event_delay_months)
    return max(0, vehicle.purchase_delay_months)


def _vehicle_plans(
    plan: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
) -> list[CarPlanData]:
    plans: list[CarPlanData] = []
    raw_vehicle_plans = sorted(
        enumerate(plan.vehicle_plans),
        key=lambda item: (max(1, item[1].planning_sequence), item[0]),
    )
    previous_sequence_month: int | None = None
    for index, vehicle in raw_vehicle_plans:
        if not vehicle.enabled or vehicle.total_price <= 0:
            continue
        if not include_after_home and not _vehicle_is_before_or_parallel_home(vehicle, scenario):
            continue
        base_purchase_month = _vehicle_base_purchase_month(
            vehicle,
            scenario=scenario,
            home_purchase_month=home_purchase_month,
        )
        effective_purchase_month = base_purchase_month
        if vehicle.purchase_timing_mode == "auto_sequence" and previous_sequence_month is not None:
            effective_purchase_month = max(
                effective_purchase_month,
                previous_sequence_month + vehicle.after_previous_event_delay_months,
            )
        plans.append(
            plan.model_copy(
                update={
                    **vehicle.model_dump(),
                    "enabled": True,
                    "name": vehicle.name or f"车辆 {index + 1}",
                    "purchase_delay_months": effective_purchase_month,
                    "vehicle_plans": [],
                    "second_car_enabled": False,
                }
            )
        )
        previous_sequence_month = effective_purchase_month
    if plans:
        return plans
    if plan.enabled and plan.total_price > 0 and (include_after_home or _vehicle_is_before_or_parallel_home(plan, scenario)):
        plans.append(plan.model_copy(update={"vehicle_plans": [], "second_car_enabled": False}))
    second_plan = _second_car_plan(plan)
    if second_plan.enabled and include_after_home:
        plans.append(second_plan)
    return plans


def _vehicle_loan_states(
    plan: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
) -> list[VehicleLoanState]:
    states: list[VehicleLoanState] = []
    for index, vehicle_plan in enumerate(
        _vehicle_plans(
            plan,
            scenario=scenario,
            home_purchase_month=home_purchase_month,
            include_after_home=include_after_home,
        )
    ):
        loan = calculate_car_loan(vehicle_plan)
        purchase_month = (
            loan.months_to_down_payment
            if loan.months_to_down_payment is not None
            else vehicle_plan.purchase_delay_months
        ) if loan.enabled else None
        states.append((index, vehicle_plan, loan, purchase_month))
    return states


def _vehicle_candidate_plans(plan: CarPlanData) -> list[tuple[int | None, CarPlanData]]:
    raw_candidates = [
        candidate if isinstance(candidate, CarPlanData) else CarPlanData.model_validate(candidate)
        for candidate in plan.candidate_vehicles
        if isinstance(candidate, (CarPlanData, dict))
    ]
    candidates = [
        candidate
        for candidate in raw_candidates
        if candidate.enabled and candidate.total_price > 0
    ]
    if not candidates:
        return [(None, plan.model_copy(update={"candidate_vehicles": []}))]

    options: list[tuple[int | None, CarPlanData]] = []
    for index, candidate in enumerate(candidates):
        candidate_data = candidate.model_dump()
        candidate_data["candidate_vehicles"] = []
        candidate_data["planning_sequence"] = plan.planning_sequence
        candidate_data["purchase_timing_mode"] = plan.purchase_timing_mode
        candidate_data["after_previous_event_delay_months"] = plan.after_previous_event_delay_months
        candidate_data["manual_purchase_delay_months"] = plan.manual_purchase_delay_months
        candidate_data["enabled"] = True
        candidate_data["selected_strategy_variant"] = plan.selected_strategy_variant
        options.append((index, plan.model_copy(update=candidate_data)))
    return options


def _aggregate_car_loan(
    plan: CarPlanData,
    *,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
) -> CarLoanSummary:
    vehicle_plans = _vehicle_plans(
        plan,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
    )
    if not vehicle_plans:
        return calculate_car_loan(plan.model_copy(update={"enabled": False, "total_price": 0}), initial_cash=initial_cash, monthly_cash_savings_before_car=monthly_cash_savings_before_car)
    loans = [
        calculate_car_loan(vehicle_plan, initial_cash=initial_cash, monthly_cash_savings_before_car=monthly_cash_savings_before_car)
        for vehicle_plan in vehicle_plans
    ]
    first = loans[0]
    return first.model_copy(
        update={
            "enabled": any(loan.enabled for loan in loans),
            "total_price": round(sum(loan.total_price for loan in loans), 2),
            "down_payment": round(sum(loan.down_payment for loan in loans), 2),
            "loan_principal": round(sum(loan.loan_principal for loan in loans), 2),
            "current_monthly_payment": round(sum(loan.current_monthly_payment for loan in loans), 2),
            "total_interest": round(sum(loan.total_interest for loan in loans), 2),
            "monthly_energy_cost": round(sum(loan.monthly_energy_cost for loan in loans), 2),
            "monthly_insurance_cost": round(sum(loan.monthly_insurance_cost for loan in loans), 2),
            "monthly_maintenance_cost": round(sum(loan.monthly_maintenance_cost for loan in loans), 2),
            "monthly_parking_cost": round(sum(loan.monthly_parking_cost for loan in loans), 2),
            "monthly_cash_operating_cost": round(sum(loan.monthly_cash_operating_cost for loan in loans), 2),
            "monthly_depreciation_cost": round(sum(loan.monthly_depreciation_cost for loan in loans), 2),
            "monthly_total_ownership_cost": round(sum(loan.monthly_total_ownership_cost for loan in loans), 2),
            "months_to_down_payment": min(
                (loan.months_to_down_payment for loan in loans if loan.months_to_down_payment is not None),
                default=None,
            ),
        }
    )


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


def _car_monthly_cash_cost_at(
    plan: CarPlanData,
    car_loan: CarLoanSummary,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> float:
    no_car_commute = _no_car_commute_cost(plan)
    vehicle_states = vehicle_states if vehicle_states is not None else _vehicle_loan_states(plan)
    if not vehicle_states:
        return no_car_commute
    first_purchase_month = min((purchase_month for _, _, _, purchase_month in vehicle_states if purchase_month is not None), default=None)
    total = no_car_commute if first_purchase_month is None or month < first_purchase_month else 0.0
    for _, vehicle_plan, loan, purchase_month in vehicle_states:
        if purchase_month is None or month < purchase_month:
            continue
        month_after_car = month - purchase_month
        payment = 0.0
        if month_after_car > 0:
            _, contract_payment, extra_payment = _vehicle_loan_point_after_payments(loan, month_after_car)
            payment = contract_payment + extra_payment
        annual_cost = (
            _car_annual_cash_cost_at(loan, vehicle_plan, month, purchase_month)
            if _is_car_annual_cost_month(month, purchase_month)
            else 0.0
        )
        total += payment + _car_monthly_cash_cost_without_annual(loan) + annual_cost
    return total


def _car_down_payment_at(
    plan: CarPlanData,
    car_loan: CarLoanSummary,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> float:
    total = 0.0
    vehicle_states = vehicle_states if vehicle_states is not None else _vehicle_loan_states(plan)
    for _, _, loan, purchase_month in vehicle_states:
        if loan.enabled and purchase_month == month:
            total += loan.down_payment
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
    if elapsed > 0:
        _, contract_payment, extra_payment = _vehicle_loan_point_after_payments(loan, elapsed)
        payment = contract_payment + extra_payment
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


def _car_down_payment_components_at(
    plan: CarPlanData,
    car_loan: CarLoanSummary,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> tuple[float, float]:
    first = 0.0
    extra = 0.0
    vehicle_states = vehicle_states if vehicle_states is not None else _vehicle_loan_states(plan)
    for index, _, loan, purchase_month in vehicle_states:
        if not loan.enabled or purchase_month != month:
            continue
        if index == 0:
            first += loan.down_payment
        else:
            extra += loan.down_payment
    return first, extra


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


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return max(0.0, value)
    return max(0.0, (value // step) * step)


def _choose_auto_vehicle_prepayment(
    plan: CarPlanData,
    *,
    down_payment_ratio: float,
    purchase_delay_months: int,
    total_months: int,
    interest_free_months: int,
    later_annual_rate: float,
    initial_cash: float,
    monthly_savings_before_car: float,
    monthly_savings_before_transport: float,
    current_monthly_expense: float,
    required_reserve: float,
) -> tuple[bool, int, int, float]:
    total_months = max(1, total_months)
    interest_free_months = max(0, min(interest_free_months, total_months))
    allowed_after = max(
        1,
        min(
            total_months,
            plan.loan_prepayment_allowed_after_month if plan.loan_prepayment_enabled else 12,
        ),
    )
    preferred_start = (
        plan.loan_prepayment_start_month
        if plan.loan_prepayment_enabled
        else max(allowed_after, interest_free_months + 1)
    )
    start_candidates = sorted({
        max(allowed_after, min(total_months, preferred_start)),
        max(allowed_after, min(total_months, interest_free_months + 1)),
        max(allowed_after, min(total_months, 25)),
    })
    base_plan = plan.model_copy(
        update={
            "enabled": True,
            "down_payment_ratio": down_payment_ratio,
            "down_payment": plan.total_price * down_payment_ratio,
            "purchase_delay_months": purchase_delay_months,
            "total_months": total_months,
            "interest_free_months": interest_free_months,
            "later_annual_rate": later_annual_rate,
            "loan_prepayment_enabled": False,
            "loan_prepayment_monthly_amount": 0.0,
        }
    )
    down_payment = max(0.0, base_plan.total_price * down_payment_ratio)
    principal = max(0.0, base_plan.total_price - down_payment)
    if principal <= 0:
        return False, allowed_after, allowed_after, 0.0
    principal_per_month = principal / total_months
    first_phase_monthly = principal_per_month if interest_free_months > 0 else 0.0
    remaining_principal = max(0.0, principal - principal_per_month * interest_free_months)
    later_months = max(0, total_months - interest_free_months)
    if later_months > 0:
        monthly_rate = later_annual_rate / 12
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
    operating_cost = _estimate_car_operating_cost(base_plan)

    regular_payment = (
        first_phase_monthly
        if interest_free_months > 0
        else later_monthly
    )
    monthly_room_after_regular_car = (
        monthly_savings_before_transport
        - regular_payment
        - operating_cost["monthly_cash_operating_cost"]
    )
    cashflow_buffer = max(500.0, current_monthly_expense * 0.08)
    auto_monthly_cap = max(0.0, monthly_room_after_regular_car - cashflow_buffer)
    manual_cap = max(0.0, plan.loan_prepayment_monthly_amount) if plan.loan_prepayment_enabled else 0.0
    strategy_cap = min(
        auto_monthly_cap,
        manual_cap if manual_cap > 0 else min(8000.0, max(1000.0, principal * 0.04)),
    )
    amount_candidates = {0.0}
    if strategy_cap >= 500:
        for ratio in (0.25, 0.5, 0.75, 1.0):
            rounded = _round_down_to_step(strategy_cap * ratio, 500)
            if rounded >= 500:
                amount_candidates.add(rounded)
    if manual_cap > 0 and auto_monthly_cap >= 500:
        amount_candidates.add(_round_down_to_step(min(manual_cap, auto_monthly_cap), 500))

    best: tuple[float, bool, int, int, float] | None = None
    for amount in sorted(amount_candidates):
        starts = start_candidates if amount > 0 else [allowed_after]
        for start_month in starts:
            projection = _vehicle_loan_projection(
                principal,
                total_months,
                interest_free_months,
                later_annual_rate,
                prepayment_monthly_amount=amount,
                prepayment_start_month=start_month,
            )
            required_cash = down_payment + required_reserve
            cash_ready_month = _months_until_cash_target(initial_cash, monthly_savings_before_car, required_cash)
            if cash_ready_month is None:
                months_to_buy = None
                cash_after_purchase = initial_cash - down_payment
            else:
                months_to_buy = max(purchase_delay_months, cash_ready_month)
                cash_after_purchase = initial_cash + monthly_savings_before_car * months_to_buy - down_payment
            expected_payment = first_phase_monthly if interest_free_months > 0 else later_monthly
            monthly_after_car = monthly_savings_before_transport - expected_payment - amount - operating_cost["monthly_cash_operating_cost"]
            interest_score = _clamp_score(projection.interest_saved_by_prepayment / max(later_total_interest, 1.0) * 10)
            payoff_score = _clamp_score((total_months - projection.actual_payoff_months) / max(total_months, 1) * 10)
            score = (
                _cash_flow_score(monthly_after_car, current_monthly_expense) * 0.32
                + _ratio_score(cash_after_purchase, required_reserve) * 0.22
                + _wait_score(months_to_buy, 24) * 0.16
                + interest_score * 0.18
                + payoff_score * 0.12
            )
            if monthly_after_car < 0:
                score -= 4.0
            if cash_after_purchase < required_reserve:
                score -= 2.0
            if amount > 0 and later_annual_rate <= 0.02 and start_month <= interest_free_months:
                score -= 1.0
            candidate = (score, amount > 0, start_month, allowed_after, amount)
            if best is None or candidate > best:
                best = candidate

    if best is None:
        return False, allowed_after, allowed_after, 0.0
    _, enabled, start_month, allowed_after, amount = best
    return enabled, start_month, allowed_after, amount


def _commercial_prepayment_mode(scenario: ScenarioData) -> str:
    mode = getattr(scenario, "commercial_prepayment_mode", "auto") or "auto"
    if mode in {"auto", "manual", "none"}:
        return mode
    return "manual" if scenario.commercial_prepayment_enabled else "auto"


def _choose_auto_commercial_prepayment(
    scenario: ScenarioData,
    *,
    commercial_loan: float,
    regular_payment: LoanSummary,
    post_purchase_cash_flow_with_pf: float,
    post_purchase_monthly_expense: float,
    required_liquidity_reserve: float,
    cash_after_purchase: float,
    minimum_cash_balance: float,
) -> tuple[bool, int, int, float]:
    total_months = max(1, scenario.loan_years * 12)
    allowed_after = max(1, min(total_months, scenario.commercial_prepayment_allowed_after_month))
    preferred_start = max(allowed_after, min(total_months, scenario.commercial_prepayment_start_month))
    if commercial_loan <= 0 or regular_payment.total_interest <= 0:
        return False, preferred_start, allowed_after, 0.0
    if cash_after_purchase < required_liquidity_reserve or minimum_cash_balance < required_liquidity_reserve * 0.35:
        return False, preferred_start, allowed_after, 0.0

    cashflow_buffer = max(1000.0, post_purchase_monthly_expense * 0.12)
    monthly_room = max(0.0, post_purchase_cash_flow_with_pf - cashflow_buffer)
    if monthly_room < 1000:
        return False, preferred_start, allowed_after, 0.0

    manual_cap = max(0.0, scenario.commercial_prepayment_monthly_amount)
    default_cap = min(20000.0, max(1000.0, commercial_loan * 0.012))
    strategy_cap = min(monthly_room * 0.70, manual_cap if manual_cap > 0 else default_cap)
    amount_candidates = {0.0}
    if strategy_cap >= 1000:
        for ratio in (0.25, 0.5, 0.75, 1.0):
            amount = _round_down_to_step(strategy_cap * ratio, 1000)
            if amount >= 1000:
                amount_candidates.add(amount)

    start_candidates = sorted({
        preferred_start,
        max(allowed_after, min(total_months, 12)),
        max(allowed_after, min(total_months, 24)),
    })
    best: tuple[float, bool, int, int, float] | None = None
    for amount in sorted(amount_candidates):
        starts = start_candidates if amount > 0 else [preferred_start]
        for start_month in starts:
            projection = _loan_projection_with_prepayment(
                commercial_loan,
                scenario.commercial_rate,
                total_months,
                _commercial_repayment_method(scenario),
                prepayment_monthly_amount=amount,
                prepayment_start_month=start_month,
            )
            monthly_after_extra = post_purchase_cash_flow_with_pf - amount
            interest_score = _clamp_score(projection.interest_saved_by_prepayment / max(regular_payment.total_interest, 1.0) * 10)
            payoff_score = _clamp_score((total_months - projection.actual_payoff_months) / max(total_months, 1) * 10)
            cashflow_score = _cash_flow_score(monthly_after_extra, post_purchase_monthly_expense)
            liquidity_score = _ratio_score(min(cash_after_purchase, minimum_cash_balance), required_liquidity_reserve)
            score = cashflow_score * 0.34 + liquidity_score * 0.20 + interest_score * 0.28 + payoff_score * 0.18
            if monthly_after_extra < cashflow_buffer:
                score -= 2.5
            if amount > 0 and scenario.commercial_rate <= max(0.0, scenario.annual_investment_return) + 0.004:
                score -= 1.2
            candidate = (score, amount > 0, start_month, allowed_after, amount)
            if best is None or candidate > best:
                best = candidate

    if best is None:
        return False, preferred_start, allowed_after, 0.0
    _, enabled, start_month, allowed_after, amount = best
    return enabled, start_month, allowed_after, amount


def build_car_plan_analyses(
    household: HouseholdData,
    *,
    net_monthly_income: float,
) -> list[CarPlanAnalysis]:
    vehicle_plans = _vehicle_plans(household.car_plan)
    if not vehicle_plans:
        return []

    initial_cash = household.cash_account_balance + household.investments
    current_monthly_expense = monthly_household_expense_at(household)
    monthly_savings_before_transport = max(
        0,
        net_monthly_income - current_monthly_expense - household.monthly_debt_payment,
    )
    no_car_commute = _no_car_commute_cost(household.car_plan)
    monthly_savings_before_car = max(0, monthly_savings_before_transport - no_car_commute)
    required_reserve = current_monthly_expense * household.required_liquidity_months

    analyses: list[CarPlanAnalysis] = []
    for vehicle_index, vehicle_plan in enumerate(vehicle_plans):
        candidate_options = _vehicle_candidate_plans(vehicle_plan)
        for candidate_index, plan in candidate_options:
            candidate_name = plan.name or vehicle_plan.name
            variant_prefix = candidate_name if len(vehicle_plans) > 1 or len(candidate_options) > 1 else ""
            high_down_ratio = min(1.0, max(plan.down_payment_ratio, 0.50))
            low_down_ratio = min(1.0, min(plan.down_payment_ratio, 0.15))
            delayed_down_ratio = min(1.0, max(plan.down_payment_ratio, 0.20))
            delay_months = max(plan.purchase_delay_months, 12)
            accelerated_prepayment = _choose_auto_vehicle_prepayment(
                plan,
                down_payment_ratio=max(plan.down_payment_ratio, 0.30),
                purchase_delay_months=plan.purchase_delay_months,
                total_months=60,
                interest_free_months=12,
                later_annual_rate=plan.later_annual_rate,
                initial_cash=initial_cash,
                monthly_savings_before_car=monthly_savings_before_car,
                monthly_savings_before_transport=monthly_savings_before_transport,
                current_monthly_expense=current_monthly_expense,
                required_reserve=required_reserve,
            )
            specs = [
                ("target", "Calculate from this vehicle source and the current manual loan settings.", plan.down_payment_ratio, plan.purchase_delay_months, plan.total_months, plan.interest_free_months, plan.later_annual_rate, plan.loan_prepayment_enabled, plan.loan_prepayment_start_month, plan.loan_prepayment_allowed_after_month, plan.loan_prepayment_monthly_amount),
                ("cash", "Pay in full to avoid auto debt, with the highest purchase-month cash pressure.", 1.0, plan.purchase_delay_months, 1, 0, 0.0, False, 1, 1, 0.0),
                ("high_down_low_loan", "Use a mainstream EV-style high-down-payment, short-term low-rate loan.", high_down_ratio, plan.purchase_delay_months, 36, 24, min(plan.later_annual_rate, 0.0199), False, 1, 12, 0.0),
                ("low_down_keep_cash", "Use a low down payment and longer term to preserve liquidity.", low_down_ratio, plan.purchase_delay_months, 60, 24, plan.later_annual_rate, False, 1, 12, 0.0),
                ("accelerated_principal", "Use a regular auto loan, then let the backend choose a principal prepayment pace after weighing cash pressure and home-purchase speed.", max(plan.down_payment_ratio, 0.30), plan.purchase_delay_months, 60, 12, plan.later_annual_rate, *accelerated_prepayment),
                ("delay_purchase", "Delay the purchase and keep cash for home purchase and emergency reserve first.", delayed_down_ratio, delay_months, 60, 24, plan.later_annual_rate, False, 1, 12, 0.0),
            ]
            for strategy_key, description, down_ratio, purchase_delay, total_months, interest_free_months, later_rate, prepay_enabled, prepay_start, prepay_allowed_after, prepay_monthly in specs:
                strategy_plan = plan.model_copy(
                    update={
                        "enabled": True,
                        "down_payment_ratio": down_ratio,
                        "down_payment": plan.total_price * down_ratio,
                        "purchase_delay_months": purchase_delay,
                        "total_months": total_months,
                        "interest_free_months": min(interest_free_months, total_months),
                        "later_annual_rate": later_rate,
                        "loan_prepayment_enabled": prepay_enabled,
                        "loan_prepayment_start_month": min(total_months, max(1, prepay_start)),
                        "loan_prepayment_allowed_after_month": min(total_months, max(1, prepay_allowed_after)),
                        "loan_prepayment_monthly_amount": max(0.0, prepay_monthly),
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
                expected_total_payment = expected_payment + (loan.prepayment_monthly_amount if loan.prepayment_enabled else 0.0)
                monthly_after_car = monthly_savings_before_transport - expected_total_payment - loan.monthly_cash_operating_cost
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
                    f"vehicle_goal:{vehicle_plan.name}",
                    f"vehicle_source:{candidate_name}",
                    f"down_payment_ratio:{down_ratio:.0%}",
                    f"cash_operating_cost_monthly:{round(loan.monthly_cash_operating_cost)}",
                    f"total_ownership_cost_monthly:{round(loan.monthly_total_ownership_cost)}",
                    "no_auto_loan" if loan.loan_principal == 0 else f"loan_principal:{round(loan.loan_principal)}",
                    (
                        f"auto_extra_principal:{round(loan.prepayment_monthly_amount)} from month {loan.prepayment_start_month}, "
                        f"payoff_months:{loan.actual_payoff_months}, interest_saved:{round(loan.interest_saved_by_prepayment)}"
                    )
                    if loan.prepayment_enabled and strategy_key == "accelerated_principal"
                    else (
                        f"extra_principal:{round(loan.prepayment_monthly_amount)} from month {loan.prepayment_start_month}, "
                        f"payoff_months:{loan.actual_payoff_months}, interest_saved:{round(loan.interest_saved_by_prepayment)}"
                    )
                    if loan.prepayment_enabled
                    else "no_extra_principal",
                    "manual_target" if strategy_key == "target" else "preserve_home_purchase_cash" if strategy_key in {"low_down_keep_cash", "delay_purchase"} else "reduce_long_term_auto_debt_pressure",
                ]
                analyses.append(
                    CarPlanAnalysis(
                        variant=f"{variant_prefix} | {strategy_key}" if variant_prefix else strategy_key,
                        description=description,
                        vehicle_index=vehicle_index,
                        vehicle_name=vehicle_plan.name,
                        vehicle_candidate_index=candidate_index,
                        vehicle_candidate_name=candidate_name,
                        strategy_key=strategy_key,
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
                        expected_monthly_payment_after_purchase=round(expected_total_payment, 2),
                        prepayment_enabled=loan.prepayment_enabled,
                        prepayment_start_month=loan.prepayment_start_month,
                        prepayment_allowed_after_month=loan.prepayment_allowed_after_month,
                        prepayment_monthly_amount=loan.prepayment_monthly_amount,
                        actual_payoff_months=loan.actual_payoff_months,
                        interest_saved_by_prepayment=loan.interest_saved_by_prepayment,
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


def _investment_withdrawal_mode_label(mode: str) -> str:
    labels = {
        "auto": "自动优化提取",
        "full_liquidation": "清空投资账户",
        "manual_reserve": "手动保留投资余额",
    }
    return labels.get(mode, "自动优化提取")


def _investment_withdrawal_mode(scenario: ScenarioData) -> str:
    mode = str(getattr(scenario, "investment_withdrawal_mode", "auto") or "auto")
    return mode if mode in {"auto", "full_liquidation", "manual_reserve"} else "auto"


def _investment_withdrawal_at_purchase(
    *,
    scenario: ScenarioData,
    cash_before_transaction: float,
    investment_before_transaction: float,
    required_cash_after_pf: float,
    required_liquidity_reserve: float,
    sell_fee_rate: float,
    investment_enabled: bool,
) -> InvestmentWithdrawalResult:
    mode = _investment_withdrawal_mode(scenario)
    cash_before = max(0.0, cash_before_transaction)
    investment_before = max(0.0, investment_before_transaction if investment_enabled else 0.0)
    fee_rate = _clamp(sell_fee_rate, 0.0, 0.05)
    if investment_before <= 0:
        return InvestmentWithdrawalResult(
            mode=mode,
            mode_label=_investment_withdrawal_mode_label(mode),
            cash_before_transaction=round(cash_before, 2),
            investment_before_transaction=0.0,
            gross_sell=0.0,
            sell_fee=0.0,
            sell_proceeds=0.0,
            investment_after_transaction=0.0,
            cash_after_transaction=round(cash_before - required_cash_after_pf, 2),
        )

    if mode == "full_liquidation":
        target_gross_sell = investment_before
    else:
        minimum_investment_balance = (
            max(0.0, scenario.investment_min_balance_after_purchase)
            if mode == "manual_reserve"
            else 0.0
        )
        required_net_from_investment = max(
            0.0,
            required_cash_after_pf + max(0.0, required_liquidity_reserve) - cash_before,
        )
        target_gross_sell = min(
            max(0.0, investment_before - minimum_investment_balance),
            required_net_from_investment / max(0.01, 1 - fee_rate),
        )

    gross_sell = max(0.0, min(investment_before, target_gross_sell))
    sell_fee = gross_sell * fee_rate
    sell_proceeds = max(0.0, gross_sell - sell_fee)
    return InvestmentWithdrawalResult(
        mode=mode,
        mode_label=_investment_withdrawal_mode_label(mode),
        cash_before_transaction=round(cash_before, 2),
        investment_before_transaction=round(investment_before, 2),
        gross_sell=round(gross_sell, 2),
        sell_fee=round(sell_fee, 2),
        sell_proceeds=round(sell_proceeds, 2),
        investment_after_transaction=round(max(0.0, investment_before - gross_sell), 2),
        cash_after_transaction=round(cash_before + sell_proceeds - required_cash_after_pf, 2),
    )


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
    investment_value_by_month: list[float] | None = None,
    pf_value_by_month: list[float] | None = None,
) -> tuple[float, float, float, float, float, float, float, float, float, float, float]:
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
    investment_value = (
        investment_value_by_month[month]
        if investment_value_by_month is not None and month < len(investment_value_by_month)
        else 0.0
    )
    if pf_value_by_month is not None and month < len(pf_value_by_month):
        pf_available = pf_value_by_month[month]
    else:
        pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
        initial_pf_balance = _household_initial_provident_balance(household, rules)
        pf_available = (
            _future_pf_value_with_schedule(
                initial_pf_balance,
                pf_interest_rate,
                month,
                monthly_pf_net_growth_at,
            )
            if monthly_pf_net_growth_at is not None
            else _future_pf_value(
                initial_pf_balance,
                monthly_pf_net_growth,
                pf_interest_rate,
                month,
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
    withdrawal = _investment_withdrawal_at_purchase(
        scenario=scenario,
        cash_before_transaction=cash_value,
        investment_before_transaction=investment_value,
        required_cash_after_pf=required_cash_after_pf,
        required_liquidity_reserve=monthly_household_expense_at(household, month) * household.required_liquidity_months,
        sell_fee_rate=sell_fee_rate,
        investment_enabled=household.investment_plan_name != "cash_only",
    )
    cash_after_transaction = withdrawal.cash_after_transaction
    pf_after_upfront_extract = max(0, pf_available - pf_upfront_extractable)
    pf_post_transaction_extractable = min(pf_after_upfront_extract, property_price * post_transaction_extract_ratio)
    return (
        round(pf_upfront_extractable, 2),
        round(family_pf_upfront_extractable, 2),
        round(pf_post_transaction_extractable, 2),
        round(withdrawal.cash_before_transaction, 2),
        round(withdrawal.investment_before_transaction, 2),
        round(withdrawal.gross_sell, 2),
        round(withdrawal.sell_proceeds, 2),
        round(withdrawal.investment_after_transaction, 2),
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


def _beijing_pf_loan_offset_target(
    *,
    available_balance: float,
    agreed_payment: float,
    remaining_loan_balance: float,
) -> float:
    available = max(0.0, available_balance)
    remaining = max(0.0, remaining_loan_balance)
    if available <= 0 or remaining <= 0:
        return 0.0

    minimum_offset = min(max(0.0, agreed_payment), remaining)
    if minimum_offset > 0 and available < minimum_offset:
        return 0.0
    return min(available, remaining)


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
    cash_relief, _ = _semiannual_loan_offset_projection(
        purchase_month=purchase_month,
        starting_pf_balance=starting_pf_balance,
        monthly_pf_deposit=monthly_pf_deposit,
        provident_monthly_payment=provident_monthly_payment,
        rules=rules,
        horizon_months=horizon_months,
        as_of=as_of,
    )
    return cash_relief


def _semiannual_loan_offset_projection(
    *,
    purchase_month: int,
    starting_pf_balance: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
    horizon_months: int = 12,
    as_of: date | None = None,
) -> tuple[float, float]:
    if monthly_pf_deposit <= 0 or provident_monthly_payment <= 0:
        return 0.0, 0.0
    pf_balance = max(0.0, starting_pf_balance)
    retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_rate = max(0.0, pf_interest_rate) / 12
    total_cash_relief = 0.0
    total_offset_payment = 0.0
    for offset in range(1, horizon_months + 1):
        absolute_month = purchase_month + offset
        pf_balance += pf_balance * pf_monthly_rate + monthly_pf_deposit
        if not _is_beijing_pf_offset_month(absolute_month, as_of=as_of):
            continue
        available = max(0.0, pf_balance - retained_balance)
        if available <= 0:
            continue
        offset_payment = _beijing_pf_loan_offset_target(
            available_balance=available,
            agreed_payment=provident_monthly_payment,
            remaining_loan_balance=max(available, provident_monthly_payment),
        )
        if offset_payment <= 0:
            continue
        pf_balance -= offset_payment
        total_cash_relief += min(offset_payment, provident_monthly_payment)
        total_offset_payment += offset_payment
    months = max(1, horizon_months)
    return total_cash_relief / months, total_offset_payment / months


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
    loan_offset_improvement, loan_offset_principal_effect = _semiannual_loan_offset_projection(
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
        material_principal_effect = loan_offset_principal_effect >= max(500.0, provident_monthly_payment * 0.5)
        if free_cash_flow < 0 or (near_cash_tension and material_payment_share) or pressure_ratio > 0.55 or material_principal_effect:
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
    car_down_payment_at: Callable[[int], float] | None = None,
    extra_monthly_payment: float = 0.0,
    extra_payment_start_month: int = 1,
    horizon_months: int = 120,
) -> tuple[float, int | None, bool]:
    cash_balance = starting_cash
    pf_balance = max(0.0, starting_pf_balance)
    minimum_cash = cash_balance
    minimum_month: int | None = purchase_month
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_rate = max(0.0, pf_interest_rate) / 12
    extra_monthly_payment = max(0.0, extra_monthly_payment)
    extra_payment_start_month = max(1, extra_payment_start_month)

    for absolute_month in range(purchase_month + 1, purchase_month + horizon_months + 1):
        repayment_month = max(1, absolute_month - purchase_month)
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
                available
                if _is_beijing_pf_offset_month(absolute_month) and available > 0
                else 0.0
            )
        else:
            pf_withdrawal = min(pf_balance, monthly_pf_withdrawal)
        pf_balance -= pf_withdrawal
        monthly_cash_delta = free_cash_flow + min(pf_withdrawal, provident_monthly_payment)
        if extra_monthly_payment > 0 and repayment_month >= extra_payment_start_month:
            monthly_cash_delta -= extra_monthly_payment
        monthly_cash_delta -= (
            car_down_payment_at(absolute_month)
            if car_down_payment_at is not None
            else _car_down_payment_at(household.car_plan, car_loan, absolute_month)
        )
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
    vehicle_states = _vehicle_loan_states(
        household.car_plan,
        scenario=scenario,
        include_after_home=False,
    )
    car_cost_cache: dict[int, float] = {}
    car_down_payment_cache: dict[int, float] = {}

    def car_monthly_cash_cost_at(month: int) -> float:
        if month not in car_cost_cache:
            car_cost_cache[month] = _car_monthly_cash_cost_at(
                household.car_plan,
                car_loan,
                month,
                vehicle_states=vehicle_states,
            )
        return car_cost_cache[month]

    def car_down_payment_at(month: int) -> float:
        if month not in car_down_payment_cache:
            car_down_payment_cache[month] = _car_down_payment_at(
                household.car_plan,
                car_loan,
                month,
                vehicle_states=vehicle_states,
            )
        return car_down_payment_cache[month]

    initial_car_down_payment = car_down_payment_at(0)
    initial_cash = max(0, household.cash_account_balance - initial_car_down_payment)
    initial_investment = max(0.0, household.investments)

    def monthly_pf_net_growth_at(month: int) -> float:
        return income_at_month(month).monthly_pf_deposit - _quarterly_rent_withdrawal_before_purchase_at(household, month)

    def monthly_cash_savings_at(month: int) -> float:
        savings = (
            income_at_month(month).net_income
            + _quarterly_rent_withdrawal_before_purchase_at(household, month)
            - expense_at_month(month)
            - household.monthly_debt_payment
            - car_monthly_cash_cost_at(month)
        )
        if month > 0:
            savings -= car_down_payment_at(month)
        return savings

    monthly_cash_savings = monthly_cash_savings_at(0)
    buy_fee_rate = _clamp(household.investment_buy_fee_rate, 0.0, 0.05)
    sell_fee_rate = _clamp(household.investment_sell_fee_rate, 0.0, 0.05)
    monthly_return = scenario.annual_investment_return / 12
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_return = max(0.0, pf_interest_rate) / 12
    cash_value_by_month = [initial_cash]
    investment_value_by_month = [initial_investment]
    pf_value_by_month = [max(0.0, _household_initial_provident_balance(household, rules))]
    investment_enabled = household.investment_plan_name != "cash_only"
    for month_index in range(1, 361):
        monthly_savings = monthly_cash_savings_at(month_index)
        cash_value = cash_value_by_month[-1]
        investment_value = investment_value_by_month[-1]
        if investment_enabled:
            investment_value = max(0.0, investment_value * (1 + monthly_return))
        reserve_target = max(0.0, expense_at_month(month_index) * household.investment_cash_reserve_months)
        projected_cash_before_investment = cash_value + monthly_savings
        if (
            investment_enabled
            and household.investment_auto_rebalance
            and projected_cash_before_investment < reserve_target
            and investment_value > 0
        ):
            liquidity_need = max(0.0, reserve_target - projected_cash_before_investment)
            gross_sell = min(investment_value, liquidity_need / max(0.01, 1 - sell_fee_rate))
            cash_value += max(0.0, gross_sell * (1 - sell_fee_rate))
            investment_value = max(0.0, investment_value - gross_sell)
        investment_contribution = 0.0
        if investment_enabled:
            base_contribution, sweep_contribution = _investment_allocation_for_month(
                monthly_surplus=monthly_savings,
                cash_balance=cash_value,
                reserve_target=reserve_target,
                household=household,
            )
            investment_contribution = base_contribution + sweep_contribution
        buy_fee = investment_contribution * buy_fee_rate
        cash_value = max(0.0, cash_value + monthly_savings - investment_contribution)
        investment_value = max(0.0, investment_value + max(0.0, investment_contribution - buy_fee))
        cash_value_by_month.append(cash_value)
        investment_value_by_month.append(investment_value)
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

    scenario_commercial_prepayment_mode = _commercial_prepayment_mode(scenario)

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
        cash_account_before_purchase = 0.0
        investment_balance_before_purchase = 0.0
        investment_sell_gross_at_purchase = 0.0
        investment_sell_proceeds_at_purchase = 0.0
        investment_balance_after_purchase = 0.0
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
        ) -> tuple[float, float, float, float, float, float, float, float, float, float, float]:
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
                investment_value_by_month=investment_value_by_month,
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
            candidate_commercial_prepayment_allowed_after_month = max(
                1,
                min(scenario.loan_years * 12, scenario.commercial_prepayment_allowed_after_month),
            )
            candidate_commercial_prepayment_start_month = max(
                candidate_commercial_prepayment_allowed_after_month,
                max(1, min(scenario.loan_years * 12, scenario.commercial_prepayment_start_month)),
            )
            candidate_commercial_prepayment = (
                max(0.0, scenario.commercial_prepayment_monthly_amount)
                if scenario_commercial_prepayment_mode == "manual"
                and mix[4] > 0
                else 0.0
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
                car_down_payment_at=car_down_payment_at,
                extra_monthly_payment=candidate_commercial_prepayment,
                extra_payment_start_month=candidate_commercial_prepayment_start_month,
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
                    candidate_cash_before_purchase,
                    candidate_investment_before_purchase,
                    candidate_investment_sell_gross,
                    candidate_investment_sell_proceeds,
                    candidate_investment_after_purchase,
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
                    cash_account_before_purchase=candidate_cash_before_purchase,
                    investment_balance_before_purchase=candidate_investment_before_purchase,
                    investment_sell_gross_at_purchase=candidate_investment_sell_gross,
                    investment_sell_proceeds_at_purchase=candidate_investment_sell_proceeds,
                    investment_balance_after_purchase=candidate_investment_after_purchase,
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
            cash_account_before_purchase = candidate_result.cash_account_before_purchase
            investment_balance_before_purchase = candidate_result.investment_balance_before_purchase
            investment_sell_gross_at_purchase = candidate_result.investment_sell_gross_at_purchase
            investment_sell_proceeds_at_purchase = candidate_result.investment_sell_proceeds_at_purchase
            investment_balance_after_purchase = candidate_result.investment_balance_after_purchase
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
                cash_account_before_purchase = best_failed_result.cash_account_before_purchase
                investment_balance_before_purchase = best_failed_result.investment_balance_before_purchase
                investment_sell_gross_at_purchase = best_failed_result.investment_sell_gross_at_purchase
                investment_sell_proceeds_at_purchase = best_failed_result.investment_sell_proceeds_at_purchase
                investment_balance_after_purchase = best_failed_result.investment_balance_after_purchase
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
                    cash_account_before_purchase,
                    investment_balance_before_purchase,
                    investment_sell_gross_at_purchase,
                    investment_sell_proceeds_at_purchase,
                    investment_balance_after_purchase,
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
        commercial_prepayment_mode = scenario_commercial_prepayment_mode
        commercial_prepayment_allowed_after_month = max(1, min(scenario.loan_years * 12, scenario.commercial_prepayment_allowed_after_month))
        commercial_prepayment_start_month = max(
            commercial_prepayment_allowed_after_month,
            max(1, min(scenario.loan_years * 12, scenario.commercial_prepayment_start_month)),
        )
        commercial_prepayment_monthly = (
            max(0.0, scenario.commercial_prepayment_monthly_amount)
            if commercial_prepayment_mode == "manual" and commercial_loan > 0
            else 0.0
        )
        immediate_commercial_prepayment = commercial_prepayment_monthly if commercial_prepayment_start_month <= 1 else 0.0
        commercial_projection = _loan_projection_with_prepayment(
            commercial_loan,
            scenario.commercial_rate,
            scenario.loan_years * 12,
            _commercial_repayment_method(scenario),
            prepayment_monthly_amount=commercial_prepayment_monthly,
            prepayment_start_month=commercial_prepayment_start_month,
        )
        commercial_interest = (
            commercial_projection.total_interest
            if commercial_prepayment_monthly > 0
            else commercial_payment.total_interest
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
                - immediate_commercial_prepayment
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
            - immediate_commercial_prepayment
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
        if commercial_prepayment_mode == "auto" and commercial_loan > 0:
            (
                commercial_auto_prepayment_enabled,
                commercial_prepayment_start_month,
                commercial_prepayment_allowed_after_month,
                commercial_prepayment_monthly,
            ) = _choose_auto_commercial_prepayment(
                scenario,
                commercial_loan=commercial_loan,
                regular_payment=commercial_payment,
                post_purchase_cash_flow_with_pf=post_purchase_cash_flow_with_pf,
                post_purchase_monthly_expense=post_purchase_monthly_expense,
                required_liquidity_reserve=required_liquidity_reserve,
                cash_after_purchase=cash_after_purchase,
                minimum_cash_balance=minimum_cash_balance,
            )
            if not commercial_auto_prepayment_enabled:
                commercial_prepayment_monthly = 0.0
            immediate_commercial_prepayment = commercial_prepayment_monthly if commercial_prepayment_start_month <= 1 else 0.0
            commercial_projection = _loan_projection_with_prepayment(
                commercial_loan,
                scenario.commercial_rate,
                scenario.loan_years * 12,
                _commercial_repayment_method(scenario),
                prepayment_monthly_amount=commercial_prepayment_monthly,
                prepayment_start_month=commercial_prepayment_start_month,
            )
            commercial_interest = (
                commercial_projection.total_interest
                if commercial_prepayment_monthly > 0
                else commercial_payment.total_interest
            )
            if commercial_prepayment_monthly > 0 and months is not None:
                minimum_cash_balance, minimum_cash_balance_month, cash_stress_ok = _post_purchase_cash_stress(
                    household=household,
                    rules=rules,
                    purchase_month=post_purchase_month,
                    starting_cash=cash_after_purchase,
                    starting_pf_balance=pf_after_extract,
                    total_monthly_payment=total_monthly_payment,
                    provident_monthly_payment=provident_payment.first_month_payment,
                    car_loan=car_loan,
                    expense_at_month=expense_at_month,
                    income_at_month=income_at_month,
                    car_monthly_cash_cost_at=car_monthly_cash_cost_at,
                    car_down_payment_at=car_down_payment_at,
                    extra_monthly_payment=commercial_prepayment_monthly,
                    extra_payment_start_month=commercial_prepayment_start_month,
                )
                cash_stress_shortfall = max(
                    0.0,
                    required_liquidity_reserve - cash_after_transaction,
                    -minimum_cash_balance,
                )
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
        payment_pressure_score = _clamp_score(10 - (total_monthly_payment + commercial_prepayment_monthly) / max(post_purchase_income.net_income, 1) / 0.45 * 10)
        commercial_pressure_score = _clamp_score(10 - commercial_loan / max(price, 1) / 0.65 * 10)
        interest_score = _clamp_score(10 - (commercial_interest + provident_payment.total_interest) / max(price, 1) / 0.55 * 10)
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
            - immediate_commercial_prepayment
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
                "note": f"商贷 {round(commercial_loan)}，总利息 {round(commercial_interest + provident_payment.total_interest)}。",
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
                commercial_prepayment_mode=commercial_prepayment_mode,  # type: ignore[arg-type]
                commercial_prepayment_enabled=commercial_prepayment_monthly > 0,
                commercial_prepayment_start_month=commercial_prepayment_start_month,
                commercial_prepayment_allowed_after_month=commercial_prepayment_allowed_after_month,
                commercial_prepayment_monthly_amount=round(commercial_prepayment_monthly, 2),
                commercial_actual_payoff_months=commercial_projection.actual_payoff_months if commercial_loan > 0 else 0,
                commercial_interest_saved_by_prepayment=round(commercial_projection.interest_saved_by_prepayment, 2),
                total_monthly_payment=round(total_monthly_payment, 2),
                total_interest=round(commercial_interest + provident_payment.total_interest, 2),
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
                investment_withdrawal_mode=_investment_withdrawal_mode(scenario),  # type: ignore[arg-type]
                investment_withdrawal_mode_label=_investment_withdrawal_mode_label(_investment_withdrawal_mode(scenario)),
                cash_account_before_purchase=round(cash_account_before_purchase, 2),
                investment_balance_before_purchase=round(investment_balance_before_purchase, 2),
                investment_sell_gross_at_purchase=round(investment_sell_gross_at_purchase, 2),
                investment_sell_proceeds_at_purchase=round(investment_sell_proceeds_at_purchase, 2),
                investment_balance_after_purchase=round(investment_balance_after_purchase, 2),
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
    vehicle_states: list[VehicleLoanState] | None = None,
) -> list[LoanVisualizationPoint]:
    base_vehicle_states = vehicle_states if vehicle_states is not None else _vehicle_loan_states(household.car_plan, scenario=scenario)
    base_existing_payment = max(0.0, base_monthly_debt_payment if base_monthly_debt_payment is not None else household.monthly_debt_payment)
    provident_offset_by_plan_month = {
        (row.plan_variant, row.month): row.loan_offset_payment
        for row in (provident_visualization or [])
    }
    visualization_horizon = _visualization_horizon_months(
        household,
        purchase_plans,
        car_loan,
        vehicle_states=base_vehicle_states,
    )
    existing_loan_by_month: dict[int, tuple[float, float, list[ExistingLoanVisualizationDetail]]] = {}
    for month in range(visualization_horizon + 1):
        existing_loan_details = _existing_loan_details_at(household.phased_loans, month)
        existing_loan_by_month[month] = (
            sum(detail.balance for detail in existing_loan_details),
            base_existing_payment + sum(detail.monthly_payment for detail in existing_loan_details),
            existing_loan_details,
        )
    rows: list[LoanVisualizationPoint] = []
    for plan in purchase_plans:
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 360
        horizon_months = visualization_horizon
        plan_vehicle_states = (
            vehicle_states
            if vehicle_states is not None
            else _vehicle_loan_states(household.car_plan, scenario=scenario, home_purchase_month=plan.months_to_buy)
        )
        cumulative_extra_provident_offset = 0.0
        for month in range(horizon_months + 1):
            vehicle_balance = 0.0
            vehicle_payment = 0.0
            vehicle_extra_principal_payment = 0.0
            for _, _, vehicle_loan, vehicle_purchase_month in plan_vehicle_states:
                if vehicle_purchase_month is None or month < vehicle_purchase_month:
                    continue
                vehicle_elapsed = max(0, month - vehicle_purchase_month)
                if vehicle_elapsed <= 0:
                    vehicle_balance += vehicle_loan.loan_principal
                    continue
                vehicle_balance_at_month, vehicle_contract_payment, vehicle_extra_payment = _vehicle_loan_point_after_payments(
                    vehicle_loan,
                    vehicle_elapsed,
                )
                vehicle_balance += vehicle_balance_at_month
                vehicle_payment += vehicle_contract_payment + vehicle_extra_payment
                vehicle_extra_principal_payment += vehicle_extra_payment
            home_elapsed = max(0, month - purchase_month) if plan.months_to_buy is not None and month >= purchase_month else 0
            commercial_payment = 0.0
            commercial_extra_principal_payment = 0.0
            if plan.months_to_buy is not None and month >= purchase_month:
                (
                    commercial_balance,
                    commercial_payment,
                    commercial_extra_principal_payment,
                ) = _loan_projection_point_after_payments(
                    plan.commercial_loan_amount,
                    scenario.commercial_rate,
                    plan.commercial_loan_years * 12,
                    plan.commercial_repayment_method,
                    home_elapsed,
                    prepayment_monthly_amount=plan.commercial_prepayment_monthly_amount
                    if plan.commercial_prepayment_enabled
                    else 0.0,
                    prepayment_start_month=plan.commercial_prepayment_start_month,
                )
            else:
                commercial_balance = 0.0
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
            provident_offset_payment = max(0.0, provident_offset_by_plan_month.get((plan.variant, month), 0.0))
            provident_cash_relief = min(provident_balance, plan.provident_monthly_payment, provident_offset_payment)
            extra_provident_offset = max(0.0, provident_offset_payment - provident_cash_relief)
            cumulative_extra_provident_offset += extra_provident_offset
            provident_balance = max(0.0, provident_balance - cumulative_extra_provident_offset)
            provident_payment = plan.provident_monthly_payment if provident_balance > 0 else 0.0
            home_payment = commercial_payment + provident_payment
            existing_loan_balance, existing_payment, existing_loan_details = existing_loan_by_month[month]
            total_payment = home_payment + commercial_extra_principal_payment + vehicle_payment + existing_payment
            cash_payment = max(0.0, total_payment - provident_cash_relief)
            rows.append(
                LoanVisualizationPoint(
                    plan_variant=plan.variant,
                    month=month,
                    commercial_loan_balance=round(commercial_balance, 2),
                    provident_loan_balance=round(provident_balance, 2),
                    home_loan_balance=round(commercial_balance + provident_balance, 2),
                    vehicle_loan_balance=round(vehicle_balance, 2),
                    existing_loan_balance=round(existing_loan_balance, 2),
                    total_loan_balance=round(
                        commercial_balance + provident_balance + vehicle_balance + existing_loan_balance,
                        2,
                    ),
                    commercial_monthly_payment=round(commercial_payment, 2),
                    provident_monthly_payment=round(provident_payment, 2),
                    home_monthly_payment=round(home_payment, 2),
                    vehicle_monthly_payment=round(vehicle_payment, 2),
                    commercial_extra_principal_payment=round(commercial_extra_principal_payment, 2),
                    vehicle_extra_principal_payment=round(vehicle_extra_principal_payment, 2),
                    existing_monthly_payment=round(existing_payment, 2),
                    existing_loan_details=existing_loan_details,
                    total_monthly_payment=round(total_payment, 2),
                    cash_monthly_payment=round(cash_payment, 2),
                    provident_offset_payment=round(provident_offset_payment, 2),
                    provident_monthly_payment_relief=round(provident_cash_relief, 2),
                )
            )
    return rows


def _member_income_profiles_at(
    household: HouseholdData,
    rules: RulePackData,
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> list[tuple[int, str, MonthlyIncomeProfile]]:
    household = _household_with_career_income_stages(household, rules, as_of=as_of)
    current = as_of or date.today()
    year, month = _month_after(current, max(0, months_from_now))
    target_month = date(year, month, 1)
    return [
        (index, member.name, _member_monthly_income_profile(member, rules, target_month, household))
        for index, member in enumerate(household.members)
    ]


def _initial_provident_member_accounts(household: HouseholdData, rules: RulePackData) -> list[dict[str, float | int | str]]:
    members = household.members
    if not members:
        return [
            {
                "member_index": 0,
                "member_name": "家庭公积金账户",
                "balance": max(0.0, household.provident_fund_balance),
            }
        ]

    explicit_balances = [max(0.0, getattr(member, "provident_fund_balance", 0.0)) for member in members]
    explicit_total = sum(explicit_balances)
    if explicit_total > 0:
        balances = explicit_balances
    else:
        profiles = _member_income_profiles_at(household, rules, 1)
        deposit_weights = [max(0.0, profile.monthly_pf_deposit) for _, _, profile in profiles]
        total_weight = sum(deposit_weights)
        if total_weight <= 0:
            deposit_weights = [1.0 for _ in members]
            total_weight = float(len(members))
        balances = [
            max(0.0, household.provident_fund_balance) * weight / total_weight
            for weight in deposit_weights
        ]

    return [
        {
            "member_index": index,
            "member_name": member.name,
            "balance": balances[index] if index < len(balances) else 0.0,
        }
        for index, member in enumerate(members)
    ]


def _household_initial_provident_balance(household: HouseholdData, rules: RulePackData) -> float:
    return sum(float(account["balance"]) for account in _initial_provident_member_accounts(household, rules))


def _apply_provident_member_outflow(
    account_rows: list[dict[str, float | int | str | bool]],
    amount: float,
    field: str,
    *,
    retained_balance: float = 0.0,
    priority_member_index: int | None = None,
) -> float:
    target = max(0.0, amount)
    if target <= 0:
        return 0.0
    available_by_index = [max(0.0, float(row["balance_end"]) - retained_balance) for row in account_rows]
    total_available = sum(available_by_index)
    actual = min(target, total_available)
    if actual <= 0:
        return 0.0

    if priority_member_index is not None:
        remaining = actual
        ordered_indexes = sorted(
            range(len(account_rows)),
            key=lambda index: 0 if int(account_rows[index]["member_index"]) == priority_member_index else 1,
        )
        for index in ordered_indexes:
            account_available = max(0.0, float(account_rows[index]["balance_end"]) - retained_balance)
            if account_available <= 0:
                continue
            outflow = min(account_available, remaining)
            account_rows[index][field] = float(account_rows[index].get(field, 0.0)) + outflow
            account_rows[index]["balance_end"] = max(0.0, float(account_rows[index]["balance_end"]) - outflow)
            remaining -= outflow
            if remaining <= 0:
                break
        return actual - max(0.0, remaining)

    remaining = actual
    remaining_available = total_available
    for index, row in enumerate(account_rows):
        account_available = available_by_index[index]
        if account_available <= 0:
            continue
        share = remaining if index == len(account_rows) - 1 else actual * account_available / total_available
        outflow = min(account_available, share, remaining)
        row[field] = float(row.get(field, 0.0)) + outflow
        row["balance_end"] = max(0.0, float(row["balance_end"]) - outflow)
        remaining -= outflow
        remaining_available -= account_available
        if remaining <= 0:
            break

    if remaining > 0 and remaining_available > 0:
        for row in account_rows:
            account_available = max(0.0, float(row["balance_end"]) - retained_balance)
            outflow = min(account_available, remaining)
            row[field] = float(row.get(field, 0.0)) + outflow
            row["balance_end"] = max(0.0, float(row["balance_end"]) - outflow)
            remaining -= outflow
            if remaining <= 0:
                break
    return actual - max(0.0, remaining)


def _provident_member_points(account_rows: list[dict[str, float | int | str | bool]]) -> list[ProvidentMemberAccountPoint]:
    points: list[ProvidentMemberAccountPoint] = []
    for row in account_rows:
        total_deposit = float(row["personal_deposit"]) + float(row["employer_deposit"])
        total_inflow = total_deposit + float(row["interest"])
        total_outflow = (
            float(row["rent_withdrawal"])
            + float(row["upfront_withdrawal"])
            + float(row["post_transaction_withdrawal"])
            + float(row["agreed_withdrawal"])
            + float(row["loan_offset_payment"])
            + float(row["retirement_withdrawal"])
        )
        points.append(
            ProvidentMemberAccountPoint(
                member_index=int(row["member_index"]),
                member_name=str(row["member_name"]),
                balance_start=round(float(row["balance_start"]), 2),
                personal_deposit=round(float(row["personal_deposit"]), 2),
                employer_deposit=round(float(row["employer_deposit"]), 2),
                total_deposit=round(total_deposit, 2),
                interest=round(float(row["interest"]), 2),
                rent_withdrawal=round(float(row["rent_withdrawal"]), 2),
                upfront_withdrawal=round(float(row["upfront_withdrawal"]), 2),
                post_transaction_withdrawal=round(float(row["post_transaction_withdrawal"]), 2),
                agreed_withdrawal=round(float(row["agreed_withdrawal"]), 2),
                loan_offset_payment=round(float(row["loan_offset_payment"]), 2),
                retirement_withdrawal=round(float(row["retirement_withdrawal"]), 2),
                account_closed_by_retirement=bool(row["account_closed_by_retirement"]),
                total_inflow=round(total_inflow, 2),
                total_outflow=round(total_outflow, 2),
                balance_end=round(float(row["balance_end"]), 2),
            )
        )
    return points


def build_provident_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> list[ProvidentVisualizationPoint]:
    pf_interest_rate = max(0.0, float(rules.params.get("provident_balance_annual_interest_rate", 0.015))) / 12
    retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
    visualization_horizon = _visualization_horizon_months(
        household,
        purchase_plans,
        car_loan,
        vehicle_states=vehicle_states,
    )
    rows: list[ProvidentVisualizationPoint] = []
    monthly_member_income_cache: dict[int, list[tuple[int, str, MonthlyIncomeProfile]]] = {}
    retirement_months_by_member = _member_retirement_months_by_index(household)

    def member_income_at_month(month: int) -> list[tuple[int, str, MonthlyIncomeProfile]]:
        if month not in monthly_member_income_cache:
            monthly_member_income_cache[month] = _member_income_profiles_at(household, rules, month)
        return monthly_member_income_cache[month]

    for plan in purchase_plans:
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 360
        horizon_months = visualization_horizon
        account_states = _initial_provident_member_accounts(household, rules)
        remaining_offsetable_loan = max(0.0, plan.provident_loan_amount)
        for month in range(horizon_months + 1):
            member_profiles = {index: profile for index, _, profile in member_income_at_month(month)}
            account_rows: list[dict[str, float | int | str | bool]] = []
            for account in account_states:
                member_index = int(account["member_index"])
                profile = member_profiles.get(member_index)
                retirement_month = retirement_months_by_member.get(member_index, 999999)
                is_retired_account_month = month >= retirement_month
                closes_this_month = month == retirement_month
                balance_start = float(account["balance"])
                personal_deposit = profile.personal_housing_fund if profile and month > 0 and not is_retired_account_month else 0.0
                employer_deposit = profile.employer_housing_fund if profile and month > 0 and not is_retired_account_month else 0.0
                interest = balance_start * pf_interest_rate if month > 0 and not is_retired_account_month else 0.0
                balance_end = balance_start + personal_deposit + employer_deposit + interest
                retirement_withdrawal = balance_end if closes_this_month and balance_end > 0 else 0.0
                if retirement_withdrawal:
                    balance_end = 0.0
                account_rows.append(
                    {
                        "member_index": member_index,
                        "member_name": account["member_name"],
                        "balance_start": balance_start,
                        "personal_deposit": personal_deposit,
                        "employer_deposit": employer_deposit,
                        "interest": interest,
                        "rent_withdrawal": 0.0,
                        "upfront_withdrawal": 0.0,
                        "post_transaction_withdrawal": 0.0,
                        "agreed_withdrawal": 0.0,
                        "loan_offset_payment": 0.0,
                        "retirement_withdrawal": retirement_withdrawal,
                        "account_closed_by_retirement": is_retired_account_month,
                        "balance_end": balance_end,
                    }
                )

            rent_withdrawal = 0.0
            upfront_withdrawal = 0.0
            post_transaction_withdrawal = 0.0
            agreed_withdrawal = 0.0
            loan_offset_payment = 0.0
            retirement_withdrawal = sum(float(row["retirement_withdrawal"]) for row in account_rows)

            is_purchase_month = plan.months_to_buy is not None and month == purchase_month
            is_after_purchase = plan.months_to_buy is not None and month > purchase_month
            if month > 0 and not is_purchase_month and not is_after_purchase:
                rent_withdrawal = _apply_provident_member_outflow(
                    account_rows,
                    _quarterly_rent_withdrawal_before_purchase_at(household, month),
                    "rent_withdrawal",
                )

            if is_purchase_month:
                upfront_withdrawal = _apply_provident_member_outflow(
                    account_rows,
                    plan.provident_upfront_extractable,
                    "upfront_withdrawal",
                )
                post_transaction_withdrawal = _apply_provident_member_outflow(
                    account_rows,
                    plan.provident_post_transaction_extractable,
                    "post_transaction_withdrawal",
                )
            elif is_after_purchase:
                strategy = plan.post_purchase_pf_strategy or ""
                if "loan_offset" in strategy:
                    available = sum(max(0.0, float(row["balance_end"]) - retained_balance) for row in account_rows)
                    loan_offset_payment = (
                        _beijing_pf_loan_offset_target(
                            available_balance=available,
                            agreed_payment=plan.provident_monthly_payment,
                            remaining_loan_balance=remaining_offsetable_loan,
                        )
                        if _is_beijing_pf_offset_month(month) and available > 0
                        else 0.0
                    )
                    loan_offset_payment = _apply_provident_member_outflow(
                        account_rows,
                        loan_offset_payment,
                        "loan_offset_payment",
                        retained_balance=retained_balance,
                        priority_member_index=household.borrower_member_index,
                    )
                    remaining_offsetable_loan = max(0.0, remaining_offsetable_loan - loan_offset_payment)
                elif "purchase_agreed" in strategy:
                    agreed_withdrawal = _apply_provident_member_outflow(
                        account_rows,
                        plan.monthly_post_purchase_pf_withdrawal,
                        "agreed_withdrawal",
                    )

            for index, account in enumerate(account_states):
                account["balance"] = float(account_rows[index]["balance_end"])

            member_accounts = _provident_member_points(account_rows)
            balance_start = sum(item.balance_start for item in member_accounts)
            personal_deposit = sum(item.personal_deposit for item in member_accounts)
            employer_deposit = sum(item.employer_deposit for item in member_accounts)
            total_deposit = sum(item.total_deposit for item in member_accounts)
            interest = sum(item.interest for item in member_accounts)
            total_inflow = total_deposit + interest
            total_outflow = (
                rent_withdrawal
                + upfront_withdrawal
                + post_transaction_withdrawal
                + agreed_withdrawal
                + loan_offset_payment
                + retirement_withdrawal
            )
            balance_end = sum(item.balance_end for item in member_accounts)
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
                    retirement_withdrawal=round(retirement_withdrawal, 2),
                    total_inflow=round(total_inflow, 2),
                    total_outflow=round(total_outflow, 2),
                    balance_end=round(max(0.0, balance_end), 2),
                    strategy_label=plan.post_purchase_pf_strategy_label,
                    member_accounts=member_accounts,
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


INVESTMENT_RISK_LABELS = {
    "cash": "现金保守",
    "conservative": "稳健",
    "balanced": "均衡",
    "growth": "进取",
}


def build_investment_allocation_summary(
    household: HouseholdData,
    *,
    monthly_surplus: float,
    current_monthly_expense: float,
) -> InvestmentAllocationSummary:
    reserve_months = household.investment_cash_reserve_months or household.required_liquidity_months or 6
    reserve_target = max(0.0, current_monthly_expense * reserve_months)
    monthly_setting = 0.0 if household.investment_plan_name == "cash_only" else max(0.0, household.monthly_investment_amount)
    allocation_household = household.model_copy(update={"monthly_investment_amount": monthly_setting})
    base, sweep = _investment_allocation_for_month(
        monthly_surplus=monthly_surplus,
        cash_balance=household.cash_account_balance,
        reserve_target=reserve_target,
        household=allocation_household,
    )
    total = max(0.0, base + sweep)
    buy_fee = total * max(0.0, household.investment_buy_fee_rate)
    return InvestmentAllocationSummary(
        monthly_surplus=round(max(0.0, monthly_surplus), 2),
        reserve_target=round(reserve_target, 2),
        reserve_gap=round(max(0.0, reserve_target - household.cash_account_balance), 2),
        base_investment=round(base, 2),
        cash_sweep_investment=round(sweep, 2),
        total_investment=round(total, 2),
        buy_fee=round(buy_fee, 2),
        net_investment=round(max(0.0, total - buy_fee), 2),
    )


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
    total_liquid_assets = max(1.0, household.cash_account_balance + household.investments)
    current_investment_ratio = max(0.0, household.investments) / total_liquid_assets
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


def build_monthly_cashflow_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> tuple[list[MonthlyCashflowPoint], list[AccountSnapshotPoint], list[MonthlyLedgerEntry]]:
    base_vehicle_states = vehicle_states if vehicle_states is not None else _vehicle_loan_states(household.car_plan, scenario=scenario)
    horizon = _visualization_horizon_months(
        household,
        purchase_plans,
        car_loan,
        vehicle_states=base_vehicle_states,
    )
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
    initial_provident_balance = _household_initial_provident_balance(household, rules)
    monthly_income_cache: dict[int, MonthlyIncomeProfile] = {}
    monthly_expense_cache: dict[int, float] = {}

    def income_at_month(month: int) -> MonthlyIncomeProfile:
        if month not in monthly_income_cache:
            monthly_income_cache[month] = household_monthly_income_profile_at(household, rules, month)
        return monthly_income_cache[month]

    def expense_at_month(month: int) -> float:
        if month not in monthly_expense_cache:
            monthly_expense_cache[month] = monthly_household_expense_at(household, month)
        return monthly_expense_cache[month]

    for plan in purchase_plans:
        plan_vehicle_states = (
            vehicle_states
            if vehicle_states is not None
            else _vehicle_loan_states(household.car_plan, scenario=scenario, home_purchase_month=plan.months_to_buy)
        )
        first_car_purchase_month = min(
            (purchase_month for _, _, _, purchase_month in plan_vehicle_states if purchase_month is not None),
            default=None,
        )
        vehicle_monthly_cache: dict[int, VehicleMonthProjection] = {}

        def vehicle_projection_at(month: int) -> VehicleMonthProjection:
            if month not in vehicle_monthly_cache:
                vehicle_total = _car_monthly_cash_cost_at(
                    household.car_plan,
                    car_loan,
                    month,
                    vehicle_states=plan_vehicle_states,
                )
                components_by_index = {
                    vehicle_index: _vehicle_cash_components_at(vehicle_loan, vehicle_plan, month, vehicle_purchase_month)
                    for vehicle_index, vehicle_plan, vehicle_loan, vehicle_purchase_month in plan_vehicle_states
                }
                first_down, second_down = _car_down_payment_components_at(
                    household.car_plan,
                    car_loan,
                    month,
                    vehicle_states=plan_vehicle_states,
                )
                first_asset = 0.0
                second_asset = 0.0
                for vehicle_index, vehicle_plan, vehicle_loan, vehicle_purchase_month in plan_vehicle_states:
                    asset_value = _vehicle_asset_value_at(
                        vehicle_loan.total_price if vehicle_loan.enabled else 0.0,
                        vehicle_plan.depreciation_years,
                        vehicle_purchase_month,
                        month,
                    )
                    if vehicle_index == 0:
                        first_asset += asset_value
                    else:
                        second_asset += asset_value
                no_car_commute = (
                    _no_car_commute_cost(household.car_plan)
                    if vehicle_total > 0 and first_car_purchase_month is not None and month < first_car_purchase_month
                    else 0.0
                )
                vehicle_monthly_cache[month] = VehicleMonthProjection(
                    total_cash_cost=vehicle_total,
                    first_down_payment=first_down,
                    extra_down_payment=second_down,
                    total_down_payment=first_down + second_down,
                    no_car_commute_cost=no_car_commute,
                    components_by_index=components_by_index,
                    first_asset_value=first_asset,
                    extra_asset_value=second_asset,
                    total_asset_value=first_asset + second_asset,
                )
            return vehicle_monthly_cache[month]

        cash_balance = max(0.0, household.cash_account_balance)
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
            provident_balance = provident_point.balance_end if provident_point else max(0.0, initial_provident_balance)
            provident_deposit = provident_point.total_deposit if provident_point else 0.0
            provident_cash_receipt = (
                provident_point.rent_withdrawal
                + provident_point.post_transaction_withdrawal
                + provident_point.agreed_withdrawal
                + provident_point.retirement_withdrawal
                if provident_point
                else 0.0
            )
            provident_house_offset_payment = provident_point.loan_offset_payment if provident_point else 0.0
            provident_house_payment_relief = 0.0

            if month == 0 and provident_cash_receipt:
                cash_balance = max(0.0, cash_balance + provident_cash_receipt)

            if month > 0:
                profile = income_at_month(month)
                cash_income = profile.net_income
                total_expense = expense_at_month(month)
                investment_reserve_target = max(0.0, total_expense * household.investment_cash_reserve_months)
                living_expense = household.monthly_expense
                scheduled_expense = max(0.0, total_expense - household.monthly_expense)
                regular_debt_payment = base_regular_debt_payment
                debt_payment = loan_point.existing_monthly_payment if loan_point else regular_debt_payment
                phased_loan_payment = max(0.0, debt_payment - regular_debt_payment)
                vehicle_projection = vehicle_projection_at(month)
                vehicle_total = vehicle_projection.total_cash_cost
                loan_vehicle_payment = loan_point.vehicle_monthly_payment if loan_point else 0.0
                vehicle_payment = min(vehicle_total, loan_vehicle_payment)
                vehicle_operating_cost = max(0.0, vehicle_total - vehicle_payment)
                for vehicle_index, components in vehicle_projection.components_by_index.items():
                    if vehicle_index == 0:
                        first_vehicle_payment += components["payment"]
                        first_vehicle_energy_cost += components["energy"]
                        first_vehicle_insurance_cost += components["insurance"]
                        first_vehicle_maintenance_cost += components["maintenance"]
                        first_vehicle_parking_cost += components["parking"]
                    else:
                        second_vehicle_payment += components["payment"]
                        second_vehicle_energy_cost += components["energy"]
                        second_vehicle_insurance_cost += components["insurance"]
                        second_vehicle_maintenance_cost += components["maintenance"]
                        second_vehicle_parking_cost += components["parking"]
                no_car_commute_cost = vehicle_projection.no_car_commute_cost
                first_vehicle_down_payment = vehicle_projection.first_down_payment
                second_vehicle_down_payment = vehicle_projection.extra_down_payment
                vehicle_down_payment = vehicle_projection.total_down_payment
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
                    monthly_surplus = (
                        cash_income
                        - total_expense
                        - debt_payment
                        - vehicle_total
                        + provident_cash_receipt
                    )
                    investment_return = investment_balance * monthly_return if investment_enabled else 0.0
                    if investment_return:
                        investment_balance = max(0.0, investment_balance + investment_return)
                    withdrawal = _investment_withdrawal_at_purchase(
                        scenario=scenario,
                        cash_before_transaction=cash_balance + monthly_surplus,
                        investment_before_transaction=investment_balance,
                        required_cash_after_pf=plan.required_cash_after_pf_extract,
                        required_liquidity_reserve=plan.required_liquidity_reserve,
                        sell_fee_rate=sell_fee_rate,
                        investment_enabled=investment_enabled,
                    )
                    investment_sell_fee = withdrawal.sell_fee
                    investment_sell_proceeds = withdrawal.sell_proceeds
                    investment_fee += investment_sell_fee
                    transaction_cash_in += investment_sell_proceeds
                    transaction_cash_out += plan.required_cash_after_pf_extract
                    cash_balance = max(
                        0.0,
                        withdrawal.cash_after_transaction
                        - vehicle_down_payment,
                    )
                    investment_balance = max(0.0, withdrawal.investment_after_transaction)
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
                        commercial_house_payment = loan_point.commercial_monthly_payment if loan_point else plan.commercial_monthly_payment
                        commercial_extra_principal_payment = loan_point.commercial_extra_principal_payment if loan_point else 0.0
                        provident_house_contract_payment = loan_point.provident_monthly_payment if loan_point else plan.provident_monthly_payment
                        provident_current_payment_relief = min(
                            provident_house_contract_payment,
                            provident_house_offset_payment,
                        )
                        provident_house_payment_relief = provident_current_payment_relief
                        house_payment = commercial_house_payment + commercial_extra_principal_payment + max(
                            0.0,
                            provident_house_contract_payment - provident_current_payment_relief,
                        )
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
                    if investment_return:
                        investment_balance = max(0.0, investment_balance + investment_return)
                    projected_cash_before_investment = cash_balance + investable_surplus
                    liquidity_sell_proceeds = 0.0
                    if (
                        investment_enabled
                        and household.investment_auto_rebalance
                        and projected_cash_before_investment < investment_reserve_target
                        and investment_balance > 0
                    ):
                        liquidity_need = max(0.0, investment_reserve_target - projected_cash_before_investment)
                        gross_sell = min(
                            investment_balance,
                            liquidity_need / max(0.01, 1 - sell_fee_rate),
                        )
                        investment_sell_fee = gross_sell * sell_fee_rate
                        liquidity_sell_proceeds = max(0.0, gross_sell - investment_sell_fee)
                        investment_sell_proceeds += liquidity_sell_proceeds
                        investment_fee += investment_sell_fee
                        investment_balance = max(0.0, investment_balance - gross_sell)
                        cash_balance += liquidity_sell_proceeds
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
                    investment_fee += investment_buy_fee
                    net_investment = max(0.0, investment_contribution - investment_buy_fee)
                    cash_balance = max(0.0, cash_balance + monthly_surplus - investment_contribution - vehicle_down_payment)
                    investment_balance = max(0.0, investment_balance + net_investment)
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
                    if liquidity_sell_proceeds:
                        entries.append(
                            _ledger_entry(
                                plan_variant=plan.variant,
                                month=month,
                                account="investment",
                                category="liquidity_redemption",
                                label="现金安全垫赎回",
                                amount=liquidity_sell_proceeds,
                                direction="transfer",
                            )
                        )

            if provident_cash_receipt:
                entries.append(
                    _ledger_entry(
                        plan_variant=plan.variant,
                        month=month,
                        account="cash",
                        category="provident_withdrawal",
                        label="公积金提取现金到账",
                        amount=provident_cash_receipt,
                        direction="inflow",
                    )
                )

            property_asset_value = scenario.total_price if month >= purchase_month else 0.0
            vehicle_projection = vehicle_projection_at(month)
            first_vehicle_asset_value = vehicle_projection.first_asset_value
            second_vehicle_asset_value = vehicle_projection.extra_asset_value
            vehicle_asset_value = vehicle_projection.total_asset_value
            fixed_asset_value = property_asset_value + vehicle_asset_value
            total_loan_balance = loan_point.total_loan_balance if loan_point else 0.0
            liquid_asset_value = cash_balance + investment_balance
            total_asset_value = cash_balance + investment_balance + provident_balance + fixed_asset_value
            net_worth = total_asset_value - total_loan_balance
            monthly_cash_delta = (
                cash_income
                + provident_cash_receipt
                + (investment_sell_proceeds if month != purchase_month else 0.0)
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
                    liquid_asset_value=round(liquid_asset_value, 2),
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
                    provident_house_payment_relief=round(provident_house_payment_relief, 2),
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
                    liquid_asset_value=round(liquid_asset_value, 2),
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


def build_annual_financial_summaries(
    monthly_cashflow: list[MonthlyCashflowPoint],
    account_snapshots: list[AccountSnapshotPoint],
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    *,
    base_date: date | None = None,
) -> list[AnnualFinancialSummary]:
    if not monthly_cashflow:
        return []

    start = base_date or date.today()
    base_month = date(start.year, start.month, 1)
    snapshots_by_plan_month = {(row.plan_variant, row.month): row for row in account_snapshots}
    loans_by_plan_month = {(row.plan_variant, row.month): row for row in loan_visualization}
    provident_by_plan_month = {(row.plan_variant, row.month): row for row in provident_visualization}
    groups: dict[tuple[str, int], dict[str, float | int | str]] = {}

    cashflow_sum_fields = [
        "cash_income",
        "living_expense",
        "scheduled_expense",
        "debt_payment",
        "house_payment",
        "vehicle_payment",
        "vehicle_operating_cost",
        "investment_contribution",
        "investment_return",
        "investment_fee",
        "investment_sell_proceeds",
        "provident_deposit",
        "provident_withdrawal",
        "transaction_cash_out",
        "transaction_cash_in",
        "monthly_cash_delta",
    ]
    loan_sum_map = {
        "commercial_payment": "commercial_monthly_payment",
        "provident_payment": "provident_monthly_payment",
        "vehicle_loan_payment": "vehicle_monthly_payment",
        "existing_loan_payment": "existing_monthly_payment",
        "commercial_extra_principal_payment": "commercial_extra_principal_payment",
        "vehicle_extra_principal_payment": "vehicle_extra_principal_payment",
        "provident_offset_payment": "provident_offset_payment",
        "cash_monthly_payment": "cash_monthly_payment",
    }

    for row in sorted(monthly_cashflow, key=lambda item: (item.plan_variant, item.month)):
        year, _ = _month_after(base_month, row.month)
        key = (row.plan_variant, year)
        group = groups.setdefault(
            key,
            {
                "plan_variant": row.plan_variant,
                "year": year,
                "months": 0,
                "last_month": -1,
                **{field: 0.0 for field in cashflow_sum_fields},
                **{field: 0.0 for field in loan_sum_map},
            },
        )
        group["months"] = int(group["months"]) + 1
        for field in cashflow_sum_fields:
            group[field] = float(group[field]) + float(getattr(row, field, 0.0))

        loan_row = loans_by_plan_month.get((row.plan_variant, row.month))
        if loan_row:
            for summary_field, loan_field in loan_sum_map.items():
                group[summary_field] = float(group[summary_field]) + float(getattr(loan_row, loan_field, 0.0))

        if row.month >= int(group["last_month"]):
            group["last_month"] = row.month
            snapshot = snapshots_by_plan_month.get((row.plan_variant, row.month))
            loan_snapshot = loan_row
            provident_snapshot = provident_by_plan_month.get((row.plan_variant, row.month))
            group.update(
                {
                    "cash_balance_end": snapshot.cash_balance if snapshot else row.cash_balance,
                    "investment_balance_end": snapshot.investment_balance if snapshot else row.investment_balance,
                    "liquid_asset_value_end": snapshot.liquid_asset_value if snapshot else row.liquid_asset_value,
                    "provident_balance_end": (
                        provident_snapshot.balance_end
                        if provident_snapshot
                        else snapshot.provident_balance if snapshot else row.provident_balance
                    ),
                    "fixed_asset_value_end": snapshot.fixed_asset_value if snapshot else row.fixed_asset_value,
                    "total_asset_value_end": snapshot.total_asset_value if snapshot else row.total_asset_value,
                    "total_loan_balance_end": (
                        loan_snapshot.total_loan_balance
                        if loan_snapshot
                        else snapshot.total_loan_balance if snapshot else row.total_loan_balance
                    ),
                    "net_worth_end": snapshot.net_worth if snapshot else row.net_worth,
                    "commercial_loan_balance_end": loan_snapshot.commercial_loan_balance if loan_snapshot else 0.0,
                    "provident_loan_balance_end": loan_snapshot.provident_loan_balance if loan_snapshot else 0.0,
                    "vehicle_loan_balance_end": loan_snapshot.vehicle_loan_balance if loan_snapshot else 0.0,
                    "existing_loan_balance_end": loan_snapshot.existing_loan_balance if loan_snapshot else 0.0,
                }
            )

    summaries: list[AnnualFinancialSummary] = []
    for group in sorted(groups.values(), key=lambda item: (str(item["plan_variant"]), int(item["year"]))):
        payload = {key: value for key, value in group.items() if key != "last_month"}
        for key, value in list(payload.items()):
            if isinstance(value, float):
                payload[key] = round(value, 2)
        summaries.append(AnnualFinancialSummary(**payload))
    return summaries


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
            code="liquid_asset_account",
            name="流动资产",
            category="account",
            description="现金账户和投资账户的合计，用于观察可较快动用的资产规模；不包含公积金账户、固定资产和贷款。",
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
            description="统一管理商业房贷、公积金贷款、车贷和已有贷款余额及月供；前端只展示后端返回的逐月余额和还款现金流。",
            managed_by="backend",
        ),
        AccountConceptSummary(
            code="net_worth",
            name="净资产",
            category="account",
            description="总资产扣除贷款余额后的家庭净值。账户余额、固定资产估值和贷款余额本身不会为负，但净资产可能因为负债高于资产而为负。",
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


def _income_stage_event_detail(stage: IncomeStageData) -> str:
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
        if stage.monthly_extra_cash_expense > 0:
            parts.append(f"额外现金支出约 {_money_text(stage.monthly_extra_cash_expense)}/月。")
    return "；".join(parts) if parts else "该收入阶段改变工资、社保、公积金或现金流口径。"


def _append_retirement_account_events(
    events: list[PlanEventPoint],
    *,
    plan_variant: str,
    provident_rows: list[ProvidentVisualizationPoint],
) -> None:
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
        _append_event(
            events,
            plan_variant=plan_variant,
            month=row.month,
            category="provident",
            title=title,
            detail=detail,
            amount=sum(account.retirement_withdrawal for account in retired_accounts),
            severity="success",
        )


def build_plan_events(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    monthly_cashflow: list[MonthlyCashflowPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
) -> list[PlanEventPoint]:
    current_month = date(date.today().year, date.today().month, 1)
    monthly_by_plan_month = {(row.plan_variant, row.month): row for row in monthly_cashflow}
    provident_by_plan = {
        plan.variant: [row for row in provident_visualization if row.plan_variant == plan.variant]
        for plan in purchase_plans
    }
    retirement_window_end = _retirement_tail_months(household, as_of=current_month)
    events: list[PlanEventPoint] = []
    for plan in purchase_plans:
        vehicle_states = _vehicle_loan_states(
            household.car_plan,
            scenario=scenario,
            home_purchase_month=plan.months_to_buy,
        )
        _append_event(
            events,
            plan_variant=plan.variant,
            month=0,
            category="account",
            title="当前账户快照",
            detail=(
                f"现金账户 {_money_text(household.cash_account_balance)}，投资账户 {_money_text(household.investments)}，"
                f"公积金账户 {_money_text(_household_initial_provident_balance(household, rules))}。这些余额后续由后端账户引擎逐月推演。"
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
        if not vehicle_states:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=0,
                category="vehicle",
                title="不买车模式",
                detail=f"当前不规划购车，通勤按无车成本 {_money_text(household.car_plan.no_car_monthly_commute_cost)}/月计入现金流。",
            )
        else:
            for vehicle_index, vehicle_plan, vehicle_loan, _ in vehicle_states:
                _vehicle_events_for_plan(
                    events,
                    plan_variant=plan.variant,
                    title_prefix="车辆" if len(vehicle_states) == 1 else vehicle_plan.name or f"车辆 {vehicle_index + 1}",
                    car_plan=vehicle_plan,
                    car_loan=vehicle_loan,
                )

        for member in household.members:
            for stage in member.income_stages:
                if not stage.name.startswith("自动情景："):
                    continue
                start = _parse_iso_date(stage.start_date, current_month)
                month = max(0, _months_between_months(current_month, date(start.year, start.month, 1)))
                _append_event(
                    events,
                    plan_variant=plan.variant,
                    month=month,
                    category="income",
                    title=f"{member.name}{stage.name.replace('自动情景：', '')}",
                    detail=_income_stage_event_detail(stage),
                    severity="success" if stage.stage_kind == "pension" else "warning",
                )
        _append_retirement_account_events(
            events,
            plan_variant=plan.variant,
            provident_rows=provident_by_plan.get(plan.variant, []),
        )
        if retirement_window_end > 0:
            _append_event(
                events,
                plan_variant=plan.variant,
                month=retirement_window_end,
                category="income",
                title="退休后长期观察窗口",
                detail="后端账户曲线至少延伸到最晚退休后 10 年，用于观察养老金、公积金销户、贷款余额、现金账户和投资账户在退休后的变化。",
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


def _property_goal_for_scenario(household: HouseholdData, scenario: ScenarioData) -> tuple[int, str]:
    enabled_goals = [goal for goal in household.property_goals if goal.enabled]
    if not enabled_goals:
        return max(1, scenario.purchase_sequence), scenario.name
    matched = [
        goal for goal in enabled_goals
        if goal.scenario_id and goal.scenario_id == scenario.name
    ] or [
        goal for goal in enabled_goals
        if not goal.scenario_id and (goal.name == scenario.name or len(enabled_goals) == 1)
    ]
    if not matched:
        return 1, ""
    goal = sorted(matched, key=lambda item: item.priority)[0]
    return max(1, goal.priority), goal.name


def _household_with_property_goal(household: HouseholdData, scenario: ScenarioData) -> tuple[HouseholdData, str]:
    priority, goal_name = _property_goal_for_scenario(household, scenario)
    if scenario.purchase_planning_mode == "parallel":
        label = goal_name or f"第 {priority} 套购房需求"
        note = (
            f"已按「{label}」作为可并行考虑的第 {priority} 套购房目标处理：策略生成不默认等待前一套成交，"
            "但仍会使用当前既有住房、既有房贷和规则包资格条件测算。"
        )
        return household, note
    prior_purchase_count = max(0, priority - 1)
    if prior_purchase_count <= 0:
        return household, ""
    adjusted = household.model_copy(
        update={
            "existing_home_count": min(10, household.existing_home_count + prior_purchase_count),
            "existing_mortgage_count": min(10, household.existing_mortgage_count + prior_purchase_count),
        }
    )
    label = goal_name or f"第 {priority} 套购房需求"
    note = (
        f"已按「{label}」作为第 {priority} 套购房目标处理：策略生成时把前置 {prior_purchase_count} 套购房需求"
        "计入既有住房和既有房贷口径，首付比例、公积金资格和贷款压力按更保守口径测算。"
    )
    return adjusted, note


def calculate_affordability(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    stress_name: str | None = None,
) -> AffordabilityResult:
    raw_household = household
    base_date = date.today()
    base_month = date(base_date.year, base_date.month, 1)
    career_shock_projection = build_career_shock_projection(raw_household, rules, as_of=base_month)
    household = raw_household.model_copy(
        update={
            "members": career_shock_projection.effective_members,
            "career_shock_applied": True,
        }
    )
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
    tax_year_summaries = build_tax_year_summaries(
        household,
        rules,
        start_year=min(base_month.year, household.income_projection_year),
        horizon_years=80,
    )
    tax_horizon_months = min(840, max(180, _retirement_tail_months(household, as_of=base_month)))
    tax_monthly_points = build_tax_monthly_points(
        household,
        rules,
        base_date=base_month,
        horizon_months=tax_horizon_months,
    )
    tax_events = build_tax_events(
        household,
        rules,
        base_date=base_month,
        horizon_months=tax_horizon_months,
    )
    phased_loan_summaries = summarize_phased_loans(household.phased_loans)
    phased_loan_monthly_payment = sum(item.current_monthly_payment for item in phased_loan_summaries)
    effective_monthly_debt_payment = household.monthly_debt_payment + phased_loan_monthly_payment
    cashflow_household = household.model_copy(
        update={"monthly_debt_payment": effective_monthly_debt_payment}
    )
    current_monthly_expense = monthly_household_expense_at(cashflow_household)
    current_income_profile = household_monthly_income_profile_at(cashflow_household, rules, 0)
    has_purchase_target = bool(scenario.enabled and scenario.total_price > 0)
    strategy_household, property_goal_assumption = _household_with_property_goal(cashflow_household, scenario)
    car_loan = _aggregate_car_loan(
        cashflow_household.car_plan,
        initial_cash=cashflow_household.cash_account_balance + cashflow_household.investments,
        monthly_cash_savings_before_car=max(
            0,
            current_income_profile.net_income - current_monthly_expense - cashflow_household.monthly_debt_payment,
        ),
    )
    purchase_strategy_car_loan = _aggregate_car_loan(
        cashflow_household.car_plan,
        initial_cash=cashflow_household.cash_account_balance + cashflow_household.investments,
        monthly_cash_savings_before_car=max(
            0,
            current_income_profile.net_income - current_monthly_expense - cashflow_household.monthly_debt_payment,
        ),
        scenario=scenario,
        include_after_home=False,
    )
    pre_home_vehicle_states = _vehicle_loan_states(
        cashflow_household.car_plan,
        scenario=scenario,
        include_after_home=False,
    )
    vehicle_states = _vehicle_loan_states(cashflow_household.car_plan, scenario=scenario)
    car_plan_analyses = build_car_plan_analyses(
        cashflow_household,
        net_monthly_income=net_monthly_income,
    )
    investment_plan_recommendations = build_investment_plan_recommendations(
        cashflow_household,
        scenario,
        net_monthly_income=net_monthly_income,
        current_monthly_expense=current_monthly_expense,
        effective_monthly_debt_payment=effective_monthly_debt_payment,
        car_loan=car_loan,
    )
    current_investment_allocation = build_investment_allocation_summary(
        cashflow_household,
        monthly_surplus=max(
            0.0,
            net_monthly_income
            - current_monthly_expense
            - effective_monthly_debt_payment
            - _car_monthly_cash_cost_at(
                cashflow_household.car_plan,
                car_loan,
                0,
                vehicle_states=pre_home_vehicle_states,
            ),
        ),
        current_monthly_expense=current_monthly_expense,
    )

    eligible, eligibility_notes = (
        evaluate_eligibility(strategy_household, rules)
        if has_purchase_target
        else (True, ["当前未启用购房目标，购房资格和贷款策略暂不进入基线测算。"])
    )
    minimum_down_payment = scenario.total_price * min_down_payment_ratio if has_purchase_target else 0.0
    stated_down_payment = max(scenario.down_payment_amount, minimum_down_payment) if has_purchase_target else 0.0
    deed_tax = scenario.total_price * scenario.deed_tax_rate if has_purchase_target else 0.0
    broker_fee = scenario.total_price * scenario.broker_fee_rate if has_purchase_target else 0.0
    upfront_renovation_cost = (
        scenario.renovation_cost if has_purchase_target and scenario.renovation_funding_mode == "upfront_cash" else 0
    )
    taxes_and_fees = deed_tax + broker_fee + (scenario.moving_and_misc_cost if has_purchase_target else 0) + upfront_renovation_cost
    if stress_name is None and has_purchase_target:
        purchase_plan_analyses = build_purchase_plan_analyses(
            strategy_household,
            scenario,
            rules,
            tax_summaries=tax_summaries,
            net_monthly_income=net_monthly_income,
            car_loan=purchase_strategy_car_loan,
            taxes_and_fees=taxes_and_fees,
        )
        if parallel_workers > 1:
            with ThreadPoolExecutor(max_workers=min(2, parallel_workers)) as executor:
                yield_future = executor.submit(
                    build_yield_sensitivity,
                    strategy_household,
                    scenario,
                    rules,
                    tax_summaries=tax_summaries,
                    net_monthly_income=net_monthly_income,
                    car_loan=purchase_strategy_car_loan,
                    taxes_and_fees=taxes_and_fees,
                    parallel_workers=max(1, parallel_workers - 1),
                )
                provident_future = executor.submit(
                    build_provident_visualization,
                    strategy_household,
                    scenario,
                    rules,
                    purchase_plan_analyses,
                    car_loan,
                    vehicle_states=vehicle_states,
                )
                yield_sensitivity = yield_future.result()
                provident_visualization = provident_future.result()
        else:
            yield_sensitivity = build_yield_sensitivity(
                strategy_household,
                scenario,
                rules,
                tax_summaries=tax_summaries,
                net_monthly_income=net_monthly_income,
                car_loan=purchase_strategy_car_loan,
                taxes_and_fees=taxes_and_fees,
                parallel_workers=1,
            )
            provident_visualization = build_provident_visualization(
                strategy_household,
                scenario,
                rules,
                purchase_plan_analyses,
                car_loan,
                vehicle_states=vehicle_states,
            )
        loan_visualization = build_loan_visualization(
            strategy_household,
            scenario,
            purchase_plan_analyses,
            car_loan,
            base_monthly_debt_payment=household.monthly_debt_payment,
            provident_visualization=provident_visualization,
        )
        monthly_cashflow_visualization, account_snapshots, monthly_ledger = build_monthly_cashflow_visualization(
            strategy_household,
            scenario,
            rules,
            purchase_plan_analyses,
            car_loan,
            loan_visualization,
            provident_visualization,
        )
        annual_financial_summaries = build_annual_financial_summaries(
            monthly_cashflow_visualization,
            account_snapshots,
            loan_visualization,
            provident_visualization,
            base_date=base_month,
        )
        account_concepts = build_account_concepts()
        strategy_explanations = build_strategy_explanations(purchase_plan_analyses)
        plan_events = build_plan_events(
            strategy_household,
            scenario,
            rules,
            purchase_plan_analyses,
            car_loan,
            monthly_cashflow_visualization,
            provident_visualization,
        )
    else:
        purchase_plan_analyses = []
        yield_sensitivity = []
        provident_visualization = []
        loan_visualization = []
        monthly_cashflow_visualization = []
        account_snapshots = []
        monthly_ledger = []
        annual_financial_summaries = []
        account_concepts = []
        strategy_explanations = []
        plan_events = []
    total_required_cash = stated_down_payment + taxes_and_fees + _car_down_payment_at(
        cashflow_household.car_plan,
        purchase_strategy_car_loan,
        0,
        vehicle_states=pre_home_vehicle_states,
    )
    remaining_cash = cashflow_household.cash_account_balance - total_required_cash
    funding_gap = max(0, -remaining_cash)

    commercial = (
        _loan_summary(
            scenario.commercial_loan_amount,
            scenario.commercial_rate,
            scenario.loan_years,
            _commercial_repayment_method(scenario),
        )
        if has_purchase_target
        else None
    )
    if has_purchase_target:
        provident_loan_years, provident_year_reasons = _provident_loan_years(strategy_household, scenario, rules)
        provident = _loan_summary(
            scenario.provident_loan_amount,
            scenario.provident_rate,
            provident_loan_years,
            _provident_repayment_method(scenario),
        )
    else:
        provident_year_reasons = ["当前未启用购房目标，暂不计算公积金贷款期限。"]
        provident = None

    monthly_payment = 0.0
    if commercial:
        monthly_payment += commercial.first_month_payment
    if provident:
        monthly_payment += provident.first_month_payment

    current_transport_cost = _car_monthly_cash_cost_at(
        cashflow_household.car_plan,
        purchase_strategy_car_loan,
        0,
        vehicle_states=pre_home_vehicle_states,
    )
    current_car_payment = sum(
        loan.current_monthly_payment
        for _, _, loan, purchase_month in pre_home_vehicle_states
        if loan.enabled and purchase_month is not None and purchase_month <= 0
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

    if not has_purchase_target:
        status = "不买房基线"
        status_reason = "当前没有启用目标房源，系统只测算家庭现状、理财、车辆和已有贷款现金流。"
    elif not eligible:
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
        tax_year_summaries=tax_year_summaries,
        tax_monthly_points=tax_monthly_points,
        tax_events=tax_events,
        career_shock_projection=career_shock_projection,
        investment_plan_recommendations=investment_plan_recommendations,
        current_investment_allocation=current_investment_allocation,
        annual_financial_summaries=annual_financial_summaries,
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
            *([property_goal_assumption] if property_goal_assumption else []),
            "北京公积金贷款额度按当前规则包的每缴存年额度估算；夫妻分别缴存时，现阶段用家庭录入的社保/个税月数近似代表较长缴存年限。",
            f"北京公积金贷款期限按设定年限、30 年上限、借款人年龄和二手房房龄/土地剩余年限取短；当前测算：{'；'.join(provident_year_reasons)}。",
            "公积金提取区分交易前现金、交易后购房提取和购后账户留存：默认不把买房后的月缴存公积金计入自由现金流。",
            "已有贷款在只还利息阶段按本金乘年利率除以 12 计入有效月债务，到期后按剩余期数转为等额本息或等额本金估算。",
            "等额本金场景使用首月月供评估现金流压力。",
            "工资薪金和全年一次性奖金按规则包税率表估算，未覆盖劳务报酬、经营所得等复杂申报情形。",
            "家庭支出按基础月支出叠加定时月支出测算；不符合税收养老条件的家庭支持支出只进入现金流，不进入个税专项附加扣除。",
        ],
    )

    if stress_name is None and has_purchase_target:
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
                                        "monthly_freelance_income": stage.monthly_freelance_income * income_factor,
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
