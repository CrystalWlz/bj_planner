from __future__ import annotations

from dataclasses import dataclass

from ..domain.housing import commercial_loan_rate
from ..domain.loans import (
    LoanComputation,
    LoanProjection,
    calculate_loan,
    loan_projection_with_prepayment,
    prepayment_investment_hurdle_rate,
)
from ..domain.scoring import cash_flow_score, clamp_score, prepayment_rate_spread_score, ratio_score
from ..schemas import LoanSummary, MarketSnapshotData, ScenarioData


@dataclass(frozen=True)
class CommercialPrepaymentPlan:
    regular_payment: LoanComputation
    mode: str
    allowed_after_month: int
    start_month: int
    monthly_amount: float
    immediate_monthly_amount: float
    projection: LoanProjection
    interest: float


def round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return max(0.0, value)
    return max(0.0, (value // step) * step)


def choose_auto_commercial_prepayment(
    scenario: ScenarioData,
    *,
    commercial_loan: float,
    regular_payment: LoanSummary,
    post_purchase_cash_flow_with_pf: float,
    post_purchase_monthly_expense: float,
    required_liquidity_reserve: float,
    cash_after_purchase: float,
    minimum_cash_balance: float,
    commercial_repayment_method: str,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
    market_snapshot: MarketSnapshotData | None = None,
) -> tuple[bool, int, int, float]:
    total_months = max(1, scenario.loan_years * 12)
    allowed_after = max(1, min(total_months, scenario.commercial_prepayment_allowed_after_month))
    preferred_start = max(allowed_after, min(total_months, scenario.commercial_prepayment_start_month))
    if commercial_loan <= 0 or regular_payment.total_interest <= 0:
        return False, preferred_start, allowed_after, 0.0
    if cash_after_purchase < required_liquidity_reserve or minimum_cash_balance < required_liquidity_reserve * 0.35:
        return False, preferred_start, allowed_after, 0.0

    hurdle_rate = prepayment_investment_hurdle_rate(
        scenario.annual_investment_return,
        buy_fee_rate=investment_buy_fee_rate,
        sell_fee_rate=investment_sell_fee_rate,
    )
    effective_commercial_rate = commercial_loan_rate(scenario, market_snapshot)
    if effective_commercial_rate <= hurdle_rate:
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
            amount = round_down_to_step(strategy_cap * ratio, 1000)
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
            projection = loan_projection_with_prepayment(
                commercial_loan,
                effective_commercial_rate,
                total_months,
                commercial_repayment_method,
                prepayment_monthly_amount=amount,
                prepayment_start_month=start_month,
            )
            monthly_after_extra = post_purchase_cash_flow_with_pf - amount
            interest_score = clamp_score(projection.interest_saved_by_prepayment / max(regular_payment.total_interest, 1.0) * 10)
            opportunity_score = prepayment_rate_spread_score(effective_commercial_rate, hurdle_rate)
            payoff_score = clamp_score((total_months - projection.actual_payoff_months) / max(total_months, 1) * 10)
            cashflow_score = cash_flow_score(monthly_after_extra, post_purchase_monthly_expense)
            liquidity_score = ratio_score(min(cash_after_purchase, minimum_cash_balance), required_liquidity_reserve)
            score = cashflow_score * 0.32 + liquidity_score * 0.20 + interest_score * 0.18 + payoff_score * 0.14 + opportunity_score * 0.16
            if monthly_after_extra < cashflow_buffer:
                score -= 2.5
            candidate = (score, amount > 0, start_month, allowed_after, amount)
            if best is None or candidate > best:
                best = candidate

    if best is None:
        return False, preferred_start, allowed_after, 0.0
    _, enabled, start_month, allowed_after, amount = best
    return enabled, start_month, allowed_after, amount


def build_commercial_prepayment_plan(
    scenario: ScenarioData,
    *,
    commercial_loan: float,
    commercial_repayment_method: str,
    commercial_prepayment_mode: str,
    prepayment_monthly_amount: float | None = None,
    prepayment_start_month: int | None = None,
    prepayment_allowed_after_month: int | None = None,
    market_snapshot: MarketSnapshotData | None = None,
) -> CommercialPrepaymentPlan:
    regular_payment = calculate_loan(
        commercial_loan,
        commercial_loan_rate(scenario, market_snapshot),
        scenario.loan_years,
        commercial_repayment_method,
    )
    total_months = max(1, scenario.loan_years * 12)
    allowed_after = max(
        1,
        min(total_months, prepayment_allowed_after_month or scenario.commercial_prepayment_allowed_after_month),
    )
    start_month = max(
        allowed_after,
        max(1, min(total_months, prepayment_start_month or scenario.commercial_prepayment_start_month)),
    )
    if commercial_loan <= 0:
        monthly_amount = 0.0
    elif prepayment_monthly_amount is not None:
        monthly_amount = max(0.0, prepayment_monthly_amount)
    else:
        monthly_amount = (
            max(0.0, scenario.commercial_prepayment_monthly_amount)
            if commercial_prepayment_mode == "manual"
            else 0.0
        )
    projection = loan_projection_with_prepayment(
        commercial_loan,
        commercial_loan_rate(scenario, market_snapshot),
        total_months,
        commercial_repayment_method,
        prepayment_monthly_amount=monthly_amount,
        prepayment_start_month=start_month,
    )
    return CommercialPrepaymentPlan(
        regular_payment=regular_payment,
        mode=commercial_prepayment_mode,
        allowed_after_month=allowed_after,
        start_month=start_month,
        monthly_amount=monthly_amount,
        immediate_monthly_amount=monthly_amount if start_month <= 1 else 0.0,
        projection=projection,
        interest=projection.total_interest if monthly_amount > 0 else regular_payment.total_interest,
    )


