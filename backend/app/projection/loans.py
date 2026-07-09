from __future__ import annotations

from collections.abc import Callable, Sequence

from ..domain.housing import commercial_loan_rate
from ..domain.loans import (
    existing_loan_details_projection,
    loan_balance_after_payments,
    loan_projection_point_after_payments,
    vehicle_loan_projection_for_like,
    vehicle_loan_projection_point,
)
from ..schemas import (
    CarLoanSummary,
    CarPlanData,
    HouseholdData,
    LoanVisualizationPoint,
    MarketSnapshotData,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    ScenarioData,
)

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]
VehicleStatesProvider = Callable[[PurchasePlanAnalysis | None], Sequence[VehicleLoanState]]


def build_loan_projection(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    *,
    horizon_months: int,
    base_monthly_debt_payment: float | None = None,
    provident_projection: list[ProvidentVisualizationPoint] | None = None,
    base_vehicle_states: Sequence[VehicleLoanState] | None = None,
    vehicle_states_by_plan: dict[str, Sequence[VehicleLoanState]] | None = None,
    market_snapshot: MarketSnapshotData | None = None,
) -> list[LoanVisualizationPoint]:
    base_existing_payment = max(
        0.0,
        base_monthly_debt_payment if base_monthly_debt_payment is not None else household.monthly_debt_payment,
    )
    provident_monthly_withdrawal_by_plan_month = {
        (row.plan_variant, row.month): row.monthly_repayment_withdrawal
        for row in (provident_projection or [])
    }
    provident_principal_offset_by_plan_month = {
        (row.plan_variant, row.month): row.loan_offset_payment
        for row in (provident_projection or [])
    }
    existing_loan_projection = existing_loan_details_projection(
        household.phased_loans,
        horizon_months,
        annual_investment_return=scenario.annual_investment_return,
        investment_buy_fee_rate=household.investment_buy_fee_rate,
        investment_sell_fee_rate=household.investment_sell_fee_rate,
    )
    existing_loan_by_month = {
        month: (
            sum(detail.balance for detail in existing_loan_details),
            base_existing_payment + sum(detail.monthly_payment for detail in existing_loan_details),
            existing_loan_details,
        )
        for month, existing_loan_details in enumerate(existing_loan_projection)
    }

    rows: list[LoanVisualizationPoint] = []
    vehicle_states_by_plan = vehicle_states_by_plan or {}
    for plan in purchase_plans:
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 360
        plan_vehicle_states = tuple(vehicle_states_by_plan.get(plan.variant, base_vehicle_states or ()))
        vehicle_projection_by_index = {
            vehicle_index: vehicle_loan_projection_for_like(vehicle_loan)
            for vehicle_index, _, vehicle_loan, _ in plan_vehicle_states
        }
        cumulative_extra_provident_offset = 0.0
        for month in range(horizon_months + 1):
            vehicle_balance = 0.0
            vehicle_payment = 0.0
            vehicle_extra_principal_payment = 0.0
            for vehicle_index, _, vehicle_loan, vehicle_purchase_month in plan_vehicle_states:
                if vehicle_purchase_month is None or month < vehicle_purchase_month:
                    continue
                vehicle_elapsed = max(0, month - vehicle_purchase_month)
                if vehicle_elapsed <= 0:
                    vehicle_balance += vehicle_loan.loan_principal
                    continue
                vehicle_balance_at_month, vehicle_contract_payment, vehicle_extra_payment = vehicle_loan_projection_point(
                    vehicle_projection_by_index[vehicle_index],
                    vehicle_loan.loan_principal,
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
                ) = loan_projection_point_after_payments(
                    plan.commercial_loan_amount,
                    commercial_loan_rate(scenario, market_snapshot),
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
                loan_balance_after_payments(
                    plan.provident_loan_amount,
                    plan.provident_rate,
                    plan.provident_loan_years,
                    plan.provident_repayment_method,
                    home_elapsed,
                )
                if plan.months_to_buy is not None and month >= purchase_month
                else 0.0
            )
            provident_monthly_withdrawal_payment = max(
                0.0,
                provident_monthly_withdrawal_by_plan_month.get((plan.variant, month), 0.0),
            )
            provident_principal_offset_payment = max(
                0.0,
                provident_principal_offset_by_plan_month.get((plan.variant, month), 0.0),
            )
            provident_offset_payment = provident_monthly_withdrawal_payment + provident_principal_offset_payment
            provident_cash_relief = min(
                provident_balance,
                plan.provident_monthly_payment,
                provident_monthly_withdrawal_payment,
            )
            cumulative_extra_provident_offset += provident_principal_offset_payment
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
                    provident_monthly_withdrawal_payment=round(provident_monthly_withdrawal_payment, 2),
                    provident_principal_offset_payment=round(provident_principal_offset_payment, 2),
                    provident_monthly_payment_relief=round(provident_cash_relief, 2),
                )
            )
    return rows


def build_loan_projection_from_strategy_context(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    *,
    horizon_months: int,
    base_monthly_debt_payment: float | None = None,
    provident_projection: list[ProvidentVisualizationPoint] | None = None,
    selected_vehicle_states: Sequence[VehicleLoanState] | None = None,
    vehicle_states_provider: VehicleStatesProvider,
    market_snapshot: MarketSnapshotData | None = None,
) -> list[LoanVisualizationPoint]:
    base_vehicle_states = tuple(
        selected_vehicle_states if selected_vehicle_states is not None else vehicle_states_provider(None)
    )
    vehicle_states_by_plan = {
        plan.variant: tuple(vehicle_states_provider(plan))
        for plan in purchase_plans
    }
    return build_loan_projection(
        household,
        scenario,
        purchase_plans,
        horizon_months=horizon_months,
        base_monthly_debt_payment=base_monthly_debt_payment,
        provident_projection=provident_projection,
        base_vehicle_states=base_vehicle_states,
        vehicle_states_by_plan=vehicle_states_by_plan,
        market_snapshot=market_snapshot,
    )
