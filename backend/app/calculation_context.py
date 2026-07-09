from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain.career import build_career_shock_projection
from .domain.expenses import (
    daily_expense_stage_at,
    monthly_household_expense_at,
    rent_expense_stage_at,
)
from .domain.housing import (
    housing_transaction_rate_amounts,
    seller_tax_pass_through_amount,
)
from .domain.investments import build_investment_allocation_summary
from .domain.loans import summarize_phased_loans
from .domain.household import household_with_member_derived_profile, household_with_property_goal
from .projection.horizon import retirement_tail_months
from .schemas import (
    CalculationContextSnapshot,
    CarLoanSummary,
    CarPlanAnalysis,
    CareerShockProjection,
    HouseholdData,
    InvestmentAllocationSummary,
    InvestmentPlanRecommendation,
    MarketSnapshotData,
    PhasedLoanSummary,
    RulePackData,
    ScenarioData,
    TaxEventPoint,
    TaxMemberSummary,
    TaxMonthlyPoint,
    TaxVisualizationDetail,
    TaxYearSummary,
)
from .strategies.investment import build_investment_plan_recommendations
from .tax_engine import (
    MonthlyIncomeProfile,
    build_tax_events,
    build_tax_monthly_points,
    build_tax_year_summaries,
    calculate_household_tax,
    household_monthly_income_profile_at,
)
from .vehicle_facade import (
    VehicleLoanState,
    aggregate_car_loan,
    build_car_plan_analyses,
    car_monthly_cash_cost_at,
    car_plan_with_selected_strategies,
    vehicle_loan_states,
)
from .visualization import build_tax_visualization_details


@dataclass(frozen=True)
class PreparedHouseholdContext:
    household: HouseholdData
    base_month: date
    career_shock_projection: CareerShockProjection
    tax_summaries: list[TaxMemberSummary]
    gross_monthly_income: float
    net_monthly_income: float
    annual_income_tax: float
    tax_year_summaries: list[TaxYearSummary]
    tax_monthly_points: list[TaxMonthlyPoint]
    tax_visualization_details: list[TaxVisualizationDetail]
    tax_events: list[TaxEventPoint]
    tax_horizon_months: int
    phased_loan_summaries: list[PhasedLoanSummary]
    phased_loan_monthly_payment: float
    effective_monthly_debt_payment: float
    cashflow_household: HouseholdData
    current_monthly_expense: float
    current_income_profile: MonthlyIncomeProfile


@dataclass(frozen=True)
class VehiclePlanningContext:
    cashflow_household: HouseholdData
    strategy_household: HouseholdData
    property_goal_assumption: str
    car_plan_analyses: list[CarPlanAnalysis]
    car_loan: CarLoanSummary
    purchase_strategy_car_loan: CarLoanSummary
    pre_home_vehicle_states: list[VehicleLoanState]
    vehicle_states: list[VehicleLoanState]
    investment_plan_recommendations: list[InvestmentPlanRecommendation]
    current_investment_allocation: InvestmentAllocationSummary


@dataclass(frozen=True)
class PurchaseCashContext:
    has_purchase_target: bool
    minimum_down_payment: float
    stated_down_payment: float
    deed_tax_rate: float
    broker_fee_rate: float
    deed_tax: float
    broker_fee: float
    seller_tax_pass_through: float
    upfront_renovation_cost: float
    taxes_and_fees: float


def prepare_household_context(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    base_month: date,
) -> PreparedHouseholdContext:
    raw_household = household_with_member_derived_profile(household)
    current_daily_expense_stage = daily_expense_stage_at(raw_household, as_of=base_month)
    current_rent_expense_stage = rent_expense_stage_at(raw_household, as_of=base_month)
    if current_daily_expense_stage or current_rent_expense_stage:
        raw_household = raw_household.model_copy(
            update={
                "monthly_expense": current_daily_expense_stage.base_living_expense
                if current_daily_expense_stage
                else raw_household.monthly_expense,
                "monthly_rent_from_housing_fund": current_rent_expense_stage.rent_amount
                if current_rent_expense_stage and current_rent_expense_stage.rent_payment_mode == "provident"
                else 0.0,
            }
        )
    career_shock_projection = build_career_shock_projection(raw_household, rules, as_of=base_month)
    effective_household = raw_household.model_copy(
        update={
            "members": career_shock_projection.effective_members,
            "career_shock_applied": True,
        }
    )
    tax_summaries, gross_monthly_income, net_monthly_income, annual_income_tax = calculate_household_tax(
        effective_household,
        rules,
    )
    tax_horizon_months = min(840, max(180, retirement_tail_months(effective_household, as_of=base_month, rules=rules)))
    tax_year_summaries = build_tax_year_summaries(
        effective_household,
        rules,
        start_year=min(base_month.year, effective_household.income_projection_year),
        horizon_years=80,
    )
    tax_monthly_points = build_tax_monthly_points(
        effective_household,
        rules,
        base_date=base_month,
        horizon_months=tax_horizon_months,
    )
    tax_events = build_tax_events(
        effective_household,
        rules,
        base_date=base_month,
        horizon_months=tax_horizon_months,
    )
    phased_loan_summaries = summarize_phased_loans(
        effective_household.phased_loans,
        annual_investment_return=scenario.annual_investment_return,
        investment_buy_fee_rate=effective_household.investment_buy_fee_rate,
        investment_sell_fee_rate=effective_household.investment_sell_fee_rate,
    )
    phased_loan_monthly_payment = sum(item.current_monthly_payment for item in phased_loan_summaries)
    effective_monthly_debt_payment = effective_household.monthly_debt_payment + phased_loan_monthly_payment
    cashflow_household = effective_household.model_copy(
        update={"monthly_debt_payment": effective_monthly_debt_payment}
    )
    return PreparedHouseholdContext(
        household=effective_household,
        base_month=base_month,
        career_shock_projection=career_shock_projection,
        tax_summaries=tax_summaries,
        gross_monthly_income=gross_monthly_income,
        net_monthly_income=net_monthly_income,
        annual_income_tax=annual_income_tax,
        tax_year_summaries=tax_year_summaries,
        tax_monthly_points=tax_monthly_points,
        tax_visualization_details=build_tax_visualization_details(tax_year_summaries, tax_monthly_points),
        tax_events=tax_events,
        tax_horizon_months=tax_horizon_months,
        phased_loan_summaries=phased_loan_summaries,
        phased_loan_monthly_payment=phased_loan_monthly_payment,
        effective_monthly_debt_payment=effective_monthly_debt_payment,
        cashflow_household=cashflow_household,
        current_monthly_expense=monthly_household_expense_at(cashflow_household, rules=rules),
        current_income_profile=household_monthly_income_profile_at(cashflow_household, rules, 0),
    )


def build_vehicle_planning_context(
    household_context: PreparedHouseholdContext,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    calculation_context: CalculationContextSnapshot | None = None,
) -> VehiclePlanningContext:
    cashflow_household = household_context.cashflow_household
    car_plan_analyses = build_car_plan_analyses(
        cashflow_household,
        net_monthly_income=household_context.net_monthly_income,
        annual_investment_return=scenario.annual_investment_return,
        rules=rules,
        calculation_context=calculation_context,
    )
    effective_car_plan = car_plan_with_selected_strategies(cashflow_household.car_plan, car_plan_analyses)
    cashflow_household = cashflow_household.model_copy(update={"car_plan": effective_car_plan})
    strategy_household, property_goal_assumption = household_with_property_goal(cashflow_household, scenario)
    monthly_cash_savings_before_car = max(
        0,
        household_context.current_income_profile.net_income
        - household_context.current_monthly_expense
        - cashflow_household.monthly_debt_payment,
    )
    car_loan = aggregate_car_loan(
        cashflow_household.car_plan,
        initial_cash=cashflow_household.cash_account_balance + cashflow_household.investments,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        rules=rules,
        calculation_context=calculation_context,
    )
    purchase_strategy_car_loan = aggregate_car_loan(
        cashflow_household.car_plan,
        initial_cash=cashflow_household.cash_account_balance + cashflow_household.investments,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        scenario=scenario,
        include_after_home=False,
        rules=rules,
        calculation_context=calculation_context,
    )
    pre_home_vehicle_states = vehicle_loan_states(
        cashflow_household.car_plan,
        scenario=scenario,
        include_after_home=False,
        rules=rules,
        calculation_context=calculation_context,
    )
    vehicle_states = vehicle_loan_states(cashflow_household.car_plan, scenario=scenario, rules=rules, calculation_context=calculation_context)
    car_monthly_cost = car_monthly_cash_cost_at(
        cashflow_household.car_plan,
        0,
        vehicle_states=pre_home_vehicle_states,
    )
    investment_plan_recommendations = build_investment_plan_recommendations(
        cashflow_household,
        scenario,
        net_monthly_income=household_context.net_monthly_income,
        current_monthly_expense=household_context.current_monthly_expense,
        effective_monthly_debt_payment=household_context.effective_monthly_debt_payment,
        car_loan=car_loan,
    )
    current_investment_allocation = build_investment_allocation_summary(
        cashflow_household,
        monthly_surplus=max(
            0.0,
            household_context.net_monthly_income
            - household_context.current_monthly_expense
            - household_context.effective_monthly_debt_payment
            - car_monthly_cost,
        ),
        current_monthly_expense=household_context.current_monthly_expense,
    )
    return VehiclePlanningContext(
        cashflow_household=cashflow_household,
        strategy_household=strategy_household,
        property_goal_assumption=property_goal_assumption,
        car_plan_analyses=car_plan_analyses,
        car_loan=car_loan,
        purchase_strategy_car_loan=purchase_strategy_car_loan,
        pre_home_vehicle_states=pre_home_vehicle_states,
        vehicle_states=vehicle_states,
        investment_plan_recommendations=investment_plan_recommendations,
        current_investment_allocation=current_investment_allocation,
    )


def build_purchase_cash_context(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    min_down_payment_ratio: float,
    market_snapshot: MarketSnapshotData | None = None,
) -> PurchaseCashContext:
    has_purchase_target = bool(scenario.enabled and scenario.total_price > 0)
    minimum_down_payment = scenario.total_price * min_down_payment_ratio if has_purchase_target else 0.0
    stated_down_payment = max(scenario.down_payment_amount, minimum_down_payment) if has_purchase_target else 0.0
    if has_purchase_target:
        deed_tax_rate, broker_fee_rate, deed_tax, broker_fee = housing_transaction_rate_amounts(
            household,
            scenario,
            rules,
            market_snapshot,
        )
    else:
        deed_tax_rate = broker_fee_rate = deed_tax = broker_fee = 0.0
    upfront_renovation_cost = (
        scenario.renovation_cost
        if has_purchase_target and scenario.renovation_funding_mode == "upfront_cash"
        else 0.0
    )
    seller_tax_pass_through = (
        seller_tax_pass_through_amount(scenario, rules, market_snapshot)
        if has_purchase_target
        else 0.0
    )
    taxes_and_fees = (
        deed_tax
        + broker_fee
        + seller_tax_pass_through
        + (scenario.moving_and_misc_cost if has_purchase_target else 0.0)
        + upfront_renovation_cost
    )
    return PurchaseCashContext(
        has_purchase_target=has_purchase_target,
        minimum_down_payment=minimum_down_payment,
        stated_down_payment=stated_down_payment,
        deed_tax_rate=deed_tax_rate,
        broker_fee_rate=broker_fee_rate,
        deed_tax=deed_tax,
        broker_fee=broker_fee,
        seller_tax_pass_through=seller_tax_pass_through,
        upfront_renovation_cost=upfront_renovation_cost,
        taxes_and_fees=taxes_and_fees,
    )
