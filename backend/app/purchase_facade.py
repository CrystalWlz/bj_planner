from __future__ import annotations

from .domain.expenses import (
    monthly_household_expense_at,
    quarterly_rent_withdrawal_before_purchase_at,
    rent_withdrawal_before_purchase,
)
from .projection_facade import household_initial_provident_balance
from .schemas import (
    CarLoanSummary,
    CalculationContextSnapshot,
    HouseholdData,
    MarketSnapshotData,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    TaxMemberSummary,
    YieldSensitivityPoint,
)
from .strategies.home import (
    build_purchase_plan_analyses as strategy_build_purchase_plan_analyses,
    family_down_payment_upfront_support,
)
from .strategies.sensitivity import build_yield_sensitivity as strategy_build_yield_sensitivity
from .strategies.vehicle import planning_window_delay_months
from .tax_engine import household_monthly_income_profile_at
from .vehicle_facade import (
    VehicleLoanState,
    car_down_payment_at,
    car_monthly_cash_cost_at,
    vehicle_loan_states,
)


def build_purchase_plan_analyses(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    tax_summaries: list[TaxMemberSummary],
    net_monthly_income: float,
    car_loan: CarLoanSummary,
    taxes_and_fees: float,
    calculation_context: CalculationContextSnapshot | None = None,
    market_snapshot: MarketSnapshotData | None = None,
    variant_names: set[str] | None = None,
) -> list[PurchasePlanAnalysis]:
    return strategy_build_purchase_plan_analyses(
        household,
        scenario,
        rules,
        tax_summaries=tax_summaries,
        car_loan=car_loan,
        taxes_and_fees=taxes_and_fees,
        income_profile_provider=lambda month: household_monthly_income_profile_at(household, rules, month),
        expense_provider=lambda month, home_purchase_month=None: monthly_household_expense_at(
            household,
            month,
            rules=rules,
            home_purchase_month=home_purchase_month,
        ),
        rent_withdrawal_before_purchase=rent_withdrawal_before_purchase,
        quarterly_rent_withdrawal_before_purchase_at=quarterly_rent_withdrawal_before_purchase_at,
        vehicle_states_provider=lambda: vehicle_loan_states(
            household.car_plan,
            scenario=scenario,
            include_after_home=False,
            rules=rules,
        ),
        car_monthly_cash_cost_provider=lambda states, month: car_monthly_cash_cost_at(
            household.car_plan,
            month,
            vehicle_states=states,
        ),
        car_down_payment_provider=lambda states, month: car_down_payment_at(
            month,
            vehicle_states=states,
        ),
        family_down_payment_upfront_support_provider=lambda purchase_month, remaining: family_down_payment_upfront_support(
            household,
            scenario,
            purchase_month,
            remaining,
        ),
        initial_provident_balance=household_initial_provident_balance(household, rules),
        planning_window_delay_provider=planning_window_delay_months,
        calculation_context=calculation_context,
        market_snapshot=market_snapshot,
        variant_names=variant_names,
    )


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
    market_snapshot: MarketSnapshotData | None = None,
    baseline_analyses: list[PurchasePlanAnalysis] | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[YieldSensitivityPoint]:
    return strategy_build_yield_sensitivity(
        household,
        scenario,
        rules,
        tax_summaries=tax_summaries,
        net_monthly_income=net_monthly_income,
        car_loan=car_loan,
        taxes_and_fees=taxes_and_fees,
        purchase_plan_builder=build_purchase_plan_analyses,
        parallel_workers=parallel_workers,
        market_snapshot=market_snapshot,
        baseline_analyses=baseline_analyses,
        calculation_context=calculation_context,
    )


def pre_home_vehicle_states(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
) -> list[VehicleLoanState]:
    return vehicle_loan_states(
        household.car_plan,
        scenario=scenario,
        include_after_home=False,
        rules=rules,
    )
