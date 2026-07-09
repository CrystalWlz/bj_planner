from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .domain.housing import (
    commercial_loan_rate,
    provident_loan_rate,
    provident_loan_years,
    provident_repayment_method,
)
from .domain.loans import commercial_repayment_method, loan_summary
from .schemas import CarLoanSummary, CarPlanData, HouseholdData, LoanSummary
from .schemas import MarketSnapshotData, RulePackData, ScenarioData

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


@dataclass(frozen=True)
class AffordabilityStatusSummary:
    status: str
    status_reason: str
    total_required_cash: float
    remaining_cash: float
    funding_gap: float
    monthly_payment: float
    post_purchase_cash_flow: float
    debt_to_income_ratio: float
    emergency_months: float


@dataclass(frozen=True)
class HomeLoanSummaryContext:
    commercial: LoanSummary | None
    provident: LoanSummary | None
    provident_year_reasons: list[str]


def home_loan_summaries(
    *,
    has_purchase_target: bool,
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    market_snapshot: MarketSnapshotData | None = None,
) -> HomeLoanSummaryContext:
    if not has_purchase_target:
        return HomeLoanSummaryContext(
            commercial=None,
            provident=None,
            provident_year_reasons=["当前未启用购房目标，暂不计算公积金贷款期限。"],
        )

    commercial = loan_summary(
        scenario.commercial_loan_amount,
        commercial_loan_rate(scenario, market_snapshot),
        scenario.loan_years,
        commercial_repayment_method(scenario),
    )
    provident_years, provident_year_reasons = provident_loan_years(household, scenario, rules)
    provident = loan_summary(
        scenario.provident_loan_amount,
        provident_loan_rate(household, scenario, rules, provident_years),
        provident_years,
        provident_repayment_method(scenario),
    )
    return HomeLoanSummaryContext(
        commercial=commercial,
        provident=provident,
        provident_year_reasons=provident_year_reasons,
    )


def home_monthly_payment(
    commercial: LoanSummary | None,
    provident: LoanSummary | None,
) -> float:
    monthly_payment = 0.0
    if commercial:
        monthly_payment += commercial.first_month_payment
    if provident:
        monthly_payment += provident.first_month_payment
    return monthly_payment


def current_vehicle_monthly_payment(vehicle_states: list[VehicleLoanState]) -> float:
    return sum(
        loan.current_monthly_payment
        for _, _, loan, purchase_month in vehicle_states
        if loan.enabled and purchase_month is not None and purchase_month <= 0
    )


def affordability_status(
    *,
    has_purchase_target: bool,
    eligible: bool,
    household: HouseholdData,
    stated_down_payment: float,
    taxes_and_fees: float,
    car_loan: CarLoanSummary,
    vehicle_states: list[VehicleLoanState],
    commercial: LoanSummary | None,
    provident: LoanSummary | None,
    net_monthly_income: float,
    current_monthly_expense: float,
    recommended_emergency_months: float,
    caution_dti: float,
    danger_dti: float,
    car_down_payment_at: Callable[[CarPlanData, CarLoanSummary, int], float],
    car_monthly_cash_cost_at: Callable[[CarPlanData, CarLoanSummary, int], float],
) -> AffordabilityStatusSummary:
    total_required_cash = stated_down_payment + taxes_and_fees + car_down_payment_at(
        household.car_plan,
        car_loan,
        0,
    )
    remaining_cash = household.cash_account_balance - total_required_cash
    funding_gap = max(0.0, -remaining_cash)
    monthly_payment = home_monthly_payment(commercial, provident)
    current_transport_cost = car_monthly_cash_cost_at(
        household.car_plan,
        car_loan,
        0,
    )
    current_car_payment = current_vehicle_monthly_payment(vehicle_states)
    monthly_income = max(net_monthly_income, 1)
    post_purchase_cash_flow = (
        net_monthly_income
        - current_monthly_expense
        - household.monthly_debt_payment
        - current_transport_cost
        - monthly_payment
    )
    debt_to_income_ratio = (
        household.monthly_debt_payment + current_car_payment + monthly_payment
    ) / monthly_income
    monthly_burn = max(
        current_monthly_expense
        + household.monthly_debt_payment
        + current_transport_cost
        + monthly_payment,
        1,
    )
    emergency_months = max(0.0, remaining_cash) / monthly_burn

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

    return AffordabilityStatusSummary(
        status=status,
        status_reason=status_reason,
        total_required_cash=total_required_cash,
        remaining_cash=remaining_cash,
        funding_gap=funding_gap,
        monthly_payment=monthly_payment,
        post_purchase_cash_flow=post_purchase_cash_flow,
        debt_to_income_ratio=debt_to_income_ratio,
        emergency_months=emergency_months,
    )
