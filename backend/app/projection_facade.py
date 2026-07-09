from __future__ import annotations

from datetime import date

from .projection.horizon import visualization_horizon_months as build_visualization_horizon
from .projection.planning import (
    apply_provident_member_outflow,
    build_household_initial_provident_balance,
    build_initial_provident_member_accounts,
    build_loan_projection,
    build_monthly_ledger_projection,
    build_provident_projection,
    build_social_security_projection,
)
from .projection.provident import beijing_pf_loan_offset_target
from .schemas import (
    AccountSnapshotPoint,
    CarLoanSummary,
    CarPlanData,
    CalculationContextSnapshot,
    HouseholdData,
    LoanVisualizationPoint,
    MarketSnapshotData,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    SocialSecurityVisualizationPoint,
)
from .visualization import build_monthly_cashflow_points

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


def visualization_horizon_months(
    household: HouseholdData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    second_loan: CarLoanSummary | None = None,
    vehicle_states: list[VehicleLoanState] | None = None,
    rules: RulePackData | None = None,
) -> int:
    active_rules = rules or RulePackData()
    return build_visualization_horizon(
        household,
        purchase_plans,
        car_loan,
        second_loan=second_loan,
        vehicle_states=vehicle_states,
        rules=active_rules,
    )


def loan_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    base_monthly_debt_payment: float | None = None,
    provident_visualization: list[ProvidentVisualizationPoint] | None = None,
    vehicle_states: list[VehicleLoanState] | None = None,
    rules: RulePackData | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
    market_snapshot: MarketSnapshotData | None = None,
) -> list[LoanVisualizationPoint]:
    active_rules = rules or RulePackData()
    return build_loan_projection(
        household,
        scenario,
        purchase_plans,
        car_loan,
        base_monthly_debt_payment=base_monthly_debt_payment,
        provident_projection=provident_visualization,
        vehicle_states=vehicle_states,
        rules=active_rules,
        calculation_context=calculation_context,
        market_snapshot=market_snapshot,
    )


def initial_provident_member_accounts(
    household: HouseholdData,
    rules: RulePackData,
) -> list[dict[str, float | int | str | bool]]:
    return build_initial_provident_member_accounts(household, rules)


def household_initial_provident_balance(household: HouseholdData, rules: RulePackData) -> float:
    return build_household_initial_provident_balance(household, rules)


def social_security_visualization(
    household: HouseholdData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary | None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    horizon_months: int | None = None,
    as_of: date | None = None,
) -> list[SocialSecurityVisualizationPoint]:
    return build_social_security_projection(
        household,
        rules,
        purchase_plans,
        car_loan,
        vehicle_states=vehicle_states,
        horizon_months=horizon_months,
        as_of=as_of,
    )


def provident_member_outflow(
    account_rows: list[dict[str, float | int | str | bool]],
    amount: float,
    field: str,
    *,
    retained_balance: float = 0.0,
    priority_member_index: int | None = None,
) -> float:
    return apply_provident_member_outflow(
        account_rows,
        amount,
        field,
        retained_balance=retained_balance,
        priority_member_index=priority_member_index,
    )


def provident_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> list[ProvidentVisualizationPoint]:
    return build_provident_projection(
        household,
        scenario,
        rules,
        purchase_plans,
        car_loan,
        vehicle_states=vehicle_states,
    )


def monthly_ledger(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
):
    return build_monthly_ledger_projection(
        household,
        scenario,
        rules,
        purchase_plans,
        car_loan,
        loan_visualization,
        provident_visualization,
        social_security_visualization,
        vehicle_states=vehicle_states,
        calculation_context=calculation_context,
    )


def monthly_cashflow_visualization(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> tuple[list[MonthlyCashflowPoint], list[AccountSnapshotPoint], list[MonthlyLedgerEntry]]:
    ledger_result = monthly_ledger(
        household,
        scenario,
        rules,
        purchase_plans,
        car_loan,
        loan_visualization,
        provident_visualization,
        social_security_visualization,
        vehicle_states=vehicle_states,
        calculation_context=calculation_context,
    )
    return (
        build_monthly_cashflow_points(ledger_result.projection_states, ledger_result.ledger_entries),
        ledger_result.account_snapshots,
        ledger_result.ledger_entries,
    )
