from __future__ import annotations

from .domain.vehicles import vehicle_update_month
from .domain.expenses import monthly_household_expense_at
from .projection.planning import (
    build_vehicle_loan_states,
    calculate_car_loan as projection_calculate_car_loan,
)
from .projection.vehicles import (
    car_down_payment_at as projected_car_down_payment_at,
    car_monthly_cash_cost_at as projected_car_monthly_cash_cost_at,
)
from .schemas import (
    CarLoanSummary,
    CarPlanAnalysis,
    CarPlanData,
    HouseholdData,
    RulePackData,
    ScenarioData,
)
from .strategies.vehicle import (
    aggregate_car_loan as strategy_aggregate_car_loan,
    build_car_plan_analyses as strategy_build_car_plan_analyses,
    car_plan_with_selected_strategies,
)

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


def calculate_car_loan(
    plan: CarPlanData,
    *,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    rules: RulePackData | None = None,
) -> CarLoanSummary:
    return projection_calculate_car_loan(
        plan,
        initial_cash=initial_cash,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        rules=rules,
    )


def vehicle_loan_states(
    plan: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData | None = None,
) -> list[VehicleLoanState]:
    return build_vehicle_loan_states(
        plan,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
        rules=rules,
    )


def aggregate_car_loan(
    plan: CarPlanData,
    *,
    car_loan_calculator=calculate_car_loan,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData | None = None,
) -> CarLoanSummary:
    return strategy_aggregate_car_loan(
        plan,
        calculate_car_loan=car_loan_calculator,
        initial_cash=initial_cash,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
        rules=rules,
    )


def car_monthly_cash_cost_at(
    plan: CarPlanData,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> float:
    states = vehicle_states if vehicle_states is not None else vehicle_loan_states(plan)
    return projected_car_monthly_cash_cost_at(plan, month, vehicle_states=states)


def car_down_payment_at(
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> float:
    states = vehicle_states if vehicle_states is not None else []
    return projected_car_down_payment_at(month, vehicle_states=states)


def build_car_plan_analyses(
    household: HouseholdData,
    *,
    net_monthly_income: float,
    current_monthly_expense: float | None = None,
    car_loan_calculator=calculate_car_loan,
    annual_investment_return: float = 0.0,
    rules: RulePackData | None = None,
) -> list[CarPlanAnalysis]:
    effective_rules = rules or RulePackData()
    effective_monthly_expense = (
        monthly_household_expense_at(household, rules=effective_rules)
        if current_monthly_expense is None
        else current_monthly_expense
    )
    return strategy_build_car_plan_analyses(
        household,
        net_monthly_income=net_monthly_income,
        current_monthly_expense=effective_monthly_expense,
        calculate_car_loan=car_loan_calculator,
        annual_investment_return=annual_investment_return,
        rules=effective_rules,
    )
