from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
    interest_subsidy: float = 0.0
    gross_contract_payment: float = 0.0


@dataclass(frozen=True)
class LoanProjection:
    points: tuple[LoanMonthProjection, ...]
    total_interest: float
    actual_payoff_months: int
    interest_saved_by_prepayment: float
    total_interest_subsidy: float = 0.0


class VehicleLoanLike(Protocol):
    loan_principal: float
    total_months: int
    interest_free_months: int
    later_annual_rate: float
    prepayment_enabled: bool
    prepayment_monthly_amount: float
    prepayment_start_month: int
    prepayment_lump_sum_amount: float
    prepayment_lump_sum_month: int


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


def loan_projection_with_prepayment(
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


def loan_projection_point_after_payments(
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
    projection = loan_projection_with_prepayment(
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


def loan_principal_for_payment_cap(
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


def loan_balance_after_payments(
    principal: float,
    annual_rate: float,
    years: int,
    method: str,
    elapsed_payments: int,
) -> float:
    return loan_balance_after_monthly_payments(
        principal,
        annual_rate,
        years * 12,
        method,
        elapsed_payments,
    )


def loan_balance_after_monthly_payments(
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


def installment_balance_after_payments(principal: float, total_months: int, elapsed_payments: int) -> float:
    if principal <= 0 or total_months <= 0:
        return 0.0
    paid_months = max(0, min(total_months, int(elapsed_payments)))
    return max(0.0, principal - (principal / total_months) * paid_months)


def vehicle_loan_projection(
    principal: float,
    total_months: int,
    interest_free_months: int,
    later_annual_rate: float,
    *,
    prepayment_monthly_amount: float = 0.0,
    prepayment_start_month: int = 1,
    prepayment_lump_sum_amount: float = 0.0,
    prepayment_lump_sum_month: int = 0,
) -> LoanProjection:
    if principal <= 0 or total_months <= 0:
        return LoanProjection((), 0.0, 0, 0.0)
    subsidy_months = max(0, min(interest_free_months, total_months))
    monthly_rate = later_annual_rate / 12
    if monthly_rate <= 0:
        gross_monthly_payment = principal / total_months
    else:
        factor = (1 + monthly_rate) ** total_months
        gross_monthly_payment = principal * monthly_rate * factor / (factor - 1)

    balance = principal
    total_borrower_interest = 0.0
    total_interest_subsidy = 0.0
    baseline_borrower_interest = 0.0
    extra_monthly = max(0.0, prepayment_monthly_amount)
    start_month = max(1, int(prepayment_start_month))
    lump_sum_amount = max(0.0, prepayment_lump_sum_amount)
    lump_sum_month = max(0, int(prepayment_lump_sum_month))
    points: list[LoanMonthProjection] = []
    for month_index in range(1, total_months + 1):
        if balance <= 0:
            break
        balance_start = balance
        interest = max(0.0, balance_start * monthly_rate)
        gross_contract_payment = min(balance_start + interest, gross_monthly_payment)
        interest_subsidy = min(interest, gross_contract_payment) if month_index <= subsidy_months else 0.0
        contract_payment = max(0.0, gross_contract_payment - interest_subsidy)
        borrower_interest = max(0.0, interest - interest_subsidy)
        scheduled_principal = max(0.0, min(balance_start, gross_contract_payment - interest))
        balance_after_contract = max(0.0, balance_start - scheduled_principal)
        scheduled_extra_principal = extra_monthly if month_index >= start_month else 0.0
        lump_sum_principal = lump_sum_amount if lump_sum_month > 0 and month_index == lump_sum_month else 0.0
        extra_principal = min(balance_after_contract, scheduled_extra_principal + lump_sum_principal)
        balance = max(0.0, balance_after_contract - extra_principal)
        total_borrower_interest += borrower_interest
        total_interest_subsidy += interest_subsidy
        points.append(
            LoanMonthProjection(
                balance_start=balance_start,
                interest=interest,
                contract_payment=contract_payment,
                extra_principal_payment=extra_principal,
                total_payment=contract_payment + extra_principal,
                balance_end=balance,
                interest_subsidy=interest_subsidy,
                gross_contract_payment=gross_contract_payment,
            )
        )
    if extra_monthly > 0 or lump_sum_amount > 0:
        baseline_projection = vehicle_loan_projection(
            principal,
            total_months,
            subsidy_months,
            later_annual_rate,
            prepayment_monthly_amount=0.0,
            prepayment_start_month=start_month,
            prepayment_lump_sum_amount=0.0,
            prepayment_lump_sum_month=0,
        )
        baseline_borrower_interest = baseline_projection.total_interest

    return LoanProjection(
        points=tuple(points),
        total_interest=total_borrower_interest,
        actual_payoff_months=len(points),
        interest_saved_by_prepayment=max(0.0, baseline_borrower_interest - total_borrower_interest) if extra_monthly > 0 or lump_sum_amount > 0 else 0.0,
        total_interest_subsidy=total_interest_subsidy,
    )


def vehicle_loan_point_after_payments(loan: VehicleLoanLike, elapsed_payments: int) -> tuple[float, float, float]:
    if loan.loan_principal <= 0 or loan.total_months <= 0:
        return 0.0, 0.0, 0.0
    projection = vehicle_loan_projection(
        loan.loan_principal,
        loan.total_months,
        loan.interest_free_months,
        loan.later_annual_rate,
        prepayment_monthly_amount=loan.prepayment_monthly_amount if loan.prepayment_enabled else 0.0,
        prepayment_start_month=loan.prepayment_start_month,
        prepayment_lump_sum_amount=loan.prepayment_lump_sum_amount if loan.prepayment_enabled else 0.0,
        prepayment_lump_sum_month=loan.prepayment_lump_sum_month if loan.prepayment_enabled else 0,
    )
    paid_months = max(0, int(elapsed_payments))
    if paid_months <= 0:
        first_point = projection.points[0] if projection.points else None
        return loan.loan_principal, first_point.contract_payment if first_point else 0.0, first_point.extra_principal_payment if first_point else 0.0
    if paid_months > len(projection.points):
        return 0.0, 0.0, 0.0
    previous = projection.points[paid_months - 1]
    return previous.balance_end, previous.contract_payment, previous.extra_principal_payment
