from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Protocol

from ..schemas import ExistingLoanVisualizationDetail, LoanSummary, PhasedLoanData, PhasedLoanSummary, ScenarioData
from .time import month_after, month_distance, parse_month


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


def loan_summary(principal: float, annual_rate: float, years: int, method: str) -> LoanSummary | None:
    if principal <= 0:
        return None
    computed = calculate_loan(principal, annual_rate, years, method)
    return LoanSummary(
        principal=round(principal, 2),
        annual_rate=annual_rate,
        years=years,
        repayment_method=method,  # type: ignore[arg-type]
        first_month_payment=round(computed.first_month_payment, 2),
        average_month_payment=round(computed.average_month_payment, 2),
        total_interest=round(computed.total_interest, 2),
    )


def commercial_repayment_method(scenario: ScenarioData) -> str:
    return scenario.commercial_repayment_method or scenario.repayment_method


def commercial_prepayment_mode(scenario: ScenarioData) -> str:
    mode = getattr(scenario, "commercial_prepayment_mode", "auto") or "auto"
    if mode in {"auto", "manual", "none"}:
        return mode
    return "manual" if scenario.commercial_prepayment_enabled else "auto"


def equal_installment_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate <= 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def amortized_monthly_payment(principal: float, annual_rate: float, months: int, method: str) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if method == "equal_principal":
        return principal / months + principal * monthly_rate
    return equal_installment_monthly_payment(principal, annual_rate, months)


def prepayment_investment_hurdle_rate(
    annual_investment_return: float,
    *,
    effective_tax_rate: float = 0.0,
    buy_fee_rate: float = 0.0,
    sell_fee_rate: float = 0.0,
    risk_buffer: float = 0.003,
    fee_amortization_years: float = 3.0,
) -> float:
    fee_drag = (max(0.0, buy_fee_rate) + max(0.0, sell_fee_rate)) / max(1.0, fee_amortization_years)
    after_tax_return = max(0.0, annual_investment_return) * (1 - max(0.0, min(1.0, effective_tax_rate)))
    net_investment_return = max(0.0, after_tax_return - fee_drag)
    return max(0.0, net_investment_return + max(0.0, risk_buffer))


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
    projection = vehicle_loan_projection_for_like(loan)
    return vehicle_loan_projection_point(projection, loan.loan_principal, elapsed_payments)


def vehicle_loan_projection_for_like(loan: VehicleLoanLike) -> LoanProjection:
    if loan.loan_principal <= 0 or loan.total_months <= 0:
        return LoanProjection(points=(), total_interest=0.0, actual_payoff_months=0, interest_saved_by_prepayment=0.0)
    return _cached_vehicle_loan_projection(
        loan.loan_principal,
        int(loan.total_months),
        int(loan.interest_free_months),
        loan.later_annual_rate,
        loan.prepayment_monthly_amount if loan.prepayment_enabled else 0.0,
        int(loan.prepayment_start_month),
        loan.prepayment_lump_sum_amount if loan.prepayment_enabled else 0.0,
        int(loan.prepayment_lump_sum_month if loan.prepayment_enabled else 0),
    )


@lru_cache(maxsize=1024)
def _cached_vehicle_loan_projection(
    principal: float,
    total_months: int,
    interest_free_months: int,
    later_annual_rate: float,
    prepayment_monthly_amount: float,
    prepayment_start_month: int,
    prepayment_lump_sum_amount: float,
    prepayment_lump_sum_month: int,
) -> LoanProjection:
    return vehicle_loan_projection(
        principal,
        total_months,
        interest_free_months,
        later_annual_rate,
        prepayment_monthly_amount=prepayment_monthly_amount,
        prepayment_start_month=prepayment_start_month,
        prepayment_lump_sum_amount=prepayment_lump_sum_amount,
        prepayment_lump_sum_month=prepayment_lump_sum_month,
    )


def vehicle_loan_projection_point(
    projection: LoanProjection,
    principal: float,
    elapsed_payments: int,
) -> tuple[float, float, float]:
    if principal <= 0:
        return 0.0, 0.0, 0.0
    paid_months = max(0, int(elapsed_payments))
    if paid_months <= 0:
        first_point = projection.points[0] if projection.points else None
        return principal, first_point.contract_payment if first_point else 0.0, first_point.extra_principal_payment if first_point else 0.0
    if paid_months > len(projection.points):
        return 0.0, 0.0, 0.0
    previous = projection.points[paid_months - 1]
    return previous.balance_end, previous.contract_payment, previous.extra_principal_payment


def phased_loan_state_at(
    loan: PhasedLoanData,
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> tuple[float, float]:
    balance, payment, _ = phased_loan_state_detail_at(loan, months_from_now, as_of=as_of)
    return balance, payment


def phased_loan_prepayment_amount(
    loan: PhasedLoanData,
    payment_month_index: int,
    balance_after_contract: float,
    *,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> float:
    if balance_after_contract <= 0:
        return 0.0
    mode = getattr(loan, "prepayment_mode", "none") or "none"
    if mode == "none":
        return 0.0
    allowed_month = max(1, int(getattr(loan, "prepayment_allowed_after_month", 1) or 1))
    start_month = max(allowed_month, int(getattr(loan, "prepayment_start_month", 1) or 1))
    if payment_month_index < start_month:
        return 0.0
    configured_amount = max(0.0, float(getattr(loan, "prepayment_monthly_amount", 0.0) or 0.0))
    if mode == "manual":
        return min(balance_after_contract, configured_amount)
    hurdle_rate = prepayment_investment_hurdle_rate(
        annual_investment_return,
        buy_fee_rate=investment_buy_fee_rate,
        sell_fee_rate=investment_sell_fee_rate,
    )
    if loan.annual_rate <= hurdle_rate:
        return 0.0
    auto_amount = configured_amount if configured_amount > 0 else min(5000.0, max(500.0, loan.principal * 0.01))
    return min(balance_after_contract, auto_amount)


def phased_loan_state_detail_at(
    loan: PhasedLoanData,
    months_from_now: int,
    *,
    as_of: date | None = None,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> tuple[float, float, float]:
    if loan.principal <= 0:
        return 0.0, 0.0, 0.0

    current = as_of or date.today()
    target_month = month_after(current, max(0, months_from_now))
    start_month = parse_month(loan.interest_start_month)
    interest_only_until = parse_month(loan.interest_only_until)
    if start_month is None or interest_only_until is None:
        return loan.principal, 0.0, 0.0

    if month_distance(target_month, start_month) > 0:
        return loan.principal, 0.0, 0.0

    monthly_rate = loan.annual_rate / 12
    interest_only_months = max(0, month_distance(start_month, interest_only_until))
    amortization_months = max(1, loan.remaining_months - interest_only_months)
    fixed_installment_payment = equal_installment_monthly_payment(loan.principal, loan.annual_rate, amortization_months)
    balance = loan.principal
    payment_month_index = 0
    total_months = max(0, months_from_now)
    for offset in range(total_months + 1):
        month = month_after(current, offset)
        if month_distance(month, start_month) > 0:
            contract_payment = 0.0
            scheduled_principal = 0.0
            extra_principal = 0.0
        elif month_distance(month, interest_only_until) >= 0:
            payment_month_index += 1
            interest = balance * monthly_rate
            contract_payment = interest
            scheduled_principal = 0.0
            extra_principal = phased_loan_prepayment_amount(
                loan,
                payment_month_index,
                balance,
                annual_investment_return=annual_investment_return,
                investment_buy_fee_rate=investment_buy_fee_rate,
                investment_sell_fee_rate=investment_sell_fee_rate,
            )
        else:
            payment_month_index += 1
            interest = balance * monthly_rate
            if loan.repayment_method == "equal_principal":
                scheduled_principal = min(balance, loan.principal / amortization_months)
                contract_payment = scheduled_principal + interest
            else:
                contract_payment = min(balance + interest, fixed_installment_payment)
                scheduled_principal = max(0.0, min(balance, contract_payment - interest))
            extra_principal = phased_loan_prepayment_amount(
                loan,
                payment_month_index,
                max(0.0, balance - scheduled_principal),
                annual_investment_return=annual_investment_return,
                investment_buy_fee_rate=investment_buy_fee_rate,
                investment_sell_fee_rate=investment_sell_fee_rate,
            )

        if offset == total_months:
            if balance <= 0:
                return 0.0, 0.0, 0.0
            return balance, contract_payment + extra_principal, extra_principal
        balance = max(0.0, balance - scheduled_principal - extra_principal)
        if balance <= 0:
            return 0.0, 0.0, 0.0


def phased_loan_detail_projection(
    loan: PhasedLoanData,
    horizon_months: int,
    *,
    as_of: date | None = None,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> list[tuple[float, float, float, str]]:
    horizon = max(0, int(horizon_months))
    if loan.principal <= 0:
        return [(0.0, 0.0, 0.0, "已结清") for _ in range(horizon + 1)]

    current = as_of or date.today()
    start_month = parse_month(loan.interest_start_month)
    interest_only_until = parse_month(loan.interest_only_until)
    if start_month is None or interest_only_until is None:
        return [(loan.principal, 0.0, 0.0, "配置待校验") for _ in range(horizon + 1)]

    monthly_rate = loan.annual_rate / 12
    interest_only_months = max(0, month_distance(start_month, interest_only_until))
    amortization_months = max(1, loan.remaining_months - interest_only_months)
    fixed_installment_payment = equal_installment_monthly_payment(loan.principal, loan.annual_rate, amortization_months)
    balance = loan.principal
    payment_month_index = 0
    rows: list[tuple[float, float, float, str]] = []

    for offset in range(horizon + 1):
        month = month_after(current, offset)
        if balance <= 0:
            rows.append((0.0, 0.0, 0.0, "已结清"))
            continue

        if month_distance(month, start_month) > 0:
            contract_payment = 0.0
            scheduled_principal = 0.0
            extra_principal = 0.0
            phase = "未开始计息"
        elif month_distance(month, interest_only_until) >= 0:
            payment_month_index += 1
            interest = balance * monthly_rate
            contract_payment = interest
            scheduled_principal = 0.0
            extra_principal = phased_loan_prepayment_amount(
                loan,
                payment_month_index,
                balance,
                annual_investment_return=annual_investment_return,
                investment_buy_fee_rate=investment_buy_fee_rate,
                investment_sell_fee_rate=investment_sell_fee_rate,
            )
            phase = "只还利息"
        else:
            payment_month_index += 1
            interest = balance * monthly_rate
            if loan.repayment_method == "equal_principal":
                scheduled_principal = min(balance, loan.principal / amortization_months)
                contract_payment = scheduled_principal + interest
                phase = "等额本金"
            else:
                contract_payment = min(balance + interest, fixed_installment_payment)
                scheduled_principal = max(0.0, min(balance, contract_payment - interest))
                phase = "等额本息"
            extra_principal = phased_loan_prepayment_amount(
                loan,
                payment_month_index,
                max(0.0, balance - scheduled_principal),
                annual_investment_return=annual_investment_return,
                investment_buy_fee_rate=investment_buy_fee_rate,
                investment_sell_fee_rate=investment_sell_fee_rate,
            )

        rows.append((balance, contract_payment + extra_principal, extra_principal, phase))
        balance = max(0.0, balance - scheduled_principal - extra_principal)

    return rows


def existing_loan_details_projection(
    loans: list[PhasedLoanData],
    horizon_months: int,
    *,
    as_of: date | None = None,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> list[list[ExistingLoanVisualizationDetail]]:
    horizon = max(0, int(horizon_months))
    loan_projections = [
        (
            index,
            loan,
            phased_loan_detail_projection(
                loan,
                horizon,
                as_of=as_of,
                annual_investment_return=annual_investment_return,
                investment_buy_fee_rate=investment_buy_fee_rate,
                investment_sell_fee_rate=investment_sell_fee_rate,
            ),
        )
        for index, loan in enumerate(loans, start=1)
    ]
    rows: list[list[ExistingLoanVisualizationDetail]] = []
    for month in range(horizon + 1):
        details: list[ExistingLoanVisualizationDetail] = []
        for index, loan, projection in loan_projections:
            balance, payment, extra_principal_payment, phase = projection[month]
            if balance <= 0 and payment <= 0:
                continue
            details.append(
                ExistingLoanVisualizationDetail(
                    name=loan.name or f"已有贷款 {index}",
                    borrower=loan.borrower,
                    loan_type=loan.loan_type or "other",
                    phase=phase,
                    balance=round(balance, 2),
                    monthly_payment=round(payment, 2),
                    extra_principal_payment=round(extra_principal_payment, 2),
                )
            )
        rows.append(details)
    return rows


def phased_loan_phase_at(
    loan: PhasedLoanData,
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> str:
    current = as_of or date.today()
    target_month = month_after(current, max(0, months_from_now))
    start_month = parse_month(loan.interest_start_month)
    interest_only_until = parse_month(loan.interest_only_until)
    if start_month is None or interest_only_until is None or loan.principal <= 0:
        return "配置待校验"
    if month_distance(target_month, start_month) > 0:
        return "未开始计息"
    if month_distance(target_month, interest_only_until) >= 0:
        return "只还利息"
    balance, payment = phased_loan_state_at(loan, months_from_now, as_of=as_of)
    if balance <= 0 and payment <= 0:
        return "已结清"
    return "等额本金" if loan.repayment_method == "equal_principal" else "等额本息"


def existing_loan_details_at(
    loans: list[PhasedLoanData],
    months_from_now: int,
    *,
    as_of: date | None = None,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> list[ExistingLoanVisualizationDetail]:
    details: list[ExistingLoanVisualizationDetail] = []
    for index, loan in enumerate(loans, start=1):
        balance, payment, extra_principal_payment = phased_loan_state_detail_at(
            loan,
            months_from_now,
            as_of=as_of,
            annual_investment_return=annual_investment_return,
            investment_buy_fee_rate=investment_buy_fee_rate,
            investment_sell_fee_rate=investment_sell_fee_rate,
        )
        if balance <= 0 and payment <= 0:
            continue
        details.append(
            ExistingLoanVisualizationDetail(
                name=loan.name or f"已有贷款 {index}",
                borrower=loan.borrower,
                loan_type=loan.loan_type or "other",
                phase=phased_loan_phase_at(loan, months_from_now, as_of=as_of),
                balance=round(balance, 2),
                monthly_payment=round(payment, 2),
                extra_principal_payment=round(extra_principal_payment, 2),
            )
        )
    return details


def summarize_phased_loans(
    loans: list[PhasedLoanData],
    *,
    as_of: date | None = None,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> list[PhasedLoanSummary]:
    current = as_of or date.today()
    summaries: list[PhasedLoanSummary] = []

    for loan in loans:
        start_month = parse_month(loan.interest_start_month)
        interest_only_until = parse_month(loan.interest_only_until)
        if start_month is None or interest_only_until is None or loan.principal <= 0:
            phase = "配置待校验"
            current_payment = 0.0
            extra_payment = 0.0
        else:
            phase = phased_loan_phase_at(loan, 0, as_of=current)
            _, current_payment, extra_payment = phased_loan_state_detail_at(
                loan,
                0,
                as_of=current,
                annual_investment_return=annual_investment_return,
                investment_buy_fee_rate=investment_buy_fee_rate,
                investment_sell_fee_rate=investment_sell_fee_rate,
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
                current_extra_principal_payment=round(extra_payment, 2),
                prepayment_mode=loan.prepayment_mode,
                prepayment_start_month=loan.prepayment_start_month,
                prepayment_allowed_after_month=loan.prepayment_allowed_after_month,
                prepayment_monthly_amount=round(loan.prepayment_monthly_amount, 2),
            )
        )
    return summaries
