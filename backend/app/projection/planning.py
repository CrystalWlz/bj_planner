from __future__ import annotations

from datetime import date

from ..domain.career import member_retirement_months_by_index
from ..domain.expenses import (
    monthly_household_expense_breakdown_at,
    quarterly_rent_withdrawal_before_purchase_at,
    regular_debt_payment_at,
)
from ..domain.investments import (
    investment_allocation_for_month,
    investment_effective_tax_rate,
    investment_withdrawal_at_purchase,
)
from ..domain.personal_pension import project_personal_pension_month
from ..domain.scoring import monthly_happiness_score
from ..domain.vehicles import calculate_car_loan_summary
from ..schemas import (
    CarLoanSummary,
    CarPlanData,
    CalculationContextSnapshot,
    HouseholdData,
    LoanVisualizationPoint,
    MarketSnapshotData,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    SocialSecurityVisualizationPoint,
)
from ..strategies.home_provident_strategy import (
    is_beijing_pf_offset_month,
    pf_strategy_active_mode,
)
from ..policies import get_policy
from ..strategies.vehicle import vehicle_loan_states
from ..tax_engine import (
    _weighted_personal_pension_monthly_return,
    household_monthly_income_profile_at,
    member_monthly_income_profiles_at,
)
from .accounts import (
    build_provident_account_projection,
    build_social_security_account_projection,
    household_initial_provident_balance,
    initial_provident_member_account_rows,
)
from .horizon import visualization_horizon_months
from .ledger import (
    MonthlyLedgerResult,
    build_projected_monthly_ledger_from_context,
)
from .loans import build_loan_projection_from_strategy_context
from .provident import (
    apply_provident_member_outflow,
    beijing_pf_loan_offset_target,
)
from .vehicles import build_vehicle_month_projection

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


def calculate_car_loan(plan: CarPlanData, *, initial_cash: float = 0, monthly_cash_savings_before_car: float = 0, rules: RulePackData) -> CarLoanSummary:
    return calculate_car_loan_summary(
        plan,
        initial_cash=initial_cash,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        rules=rules,
    )


def build_vehicle_loan_states(
    plan: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[VehicleLoanState]:
    return vehicle_loan_states(
        plan,
        calculate_car_loan=calculate_car_loan,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
        rules=rules,
        calculation_context=calculation_context,
    )


def build_visualization_horizon(
    household: HouseholdData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    second_loan: CarLoanSummary | None = None,
    vehicle_states: list[VehicleLoanState] | None = None,
    rules: RulePackData,
) -> int:
    effective_vehicle_states = vehicle_states if vehicle_states is not None else build_vehicle_loan_states(
        household.car_plan,
        rules=rules,
    )
    return visualization_horizon_months(
        household,
        purchase_plans,
        car_loan,
        second_loan=second_loan,
        vehicle_states=effective_vehicle_states,
        rules=rules,
    )


def build_loan_projection(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    base_monthly_debt_payment: float | None = None,
    provident_projection: list[ProvidentVisualizationPoint] | None = None,
    vehicle_states: list[VehicleLoanState] | None = None,
    rules: RulePackData,
    calculation_context: CalculationContextSnapshot | None = None,
    market_snapshot: MarketSnapshotData | None = None,
) -> list[LoanVisualizationPoint]:
    base_vehicle_states = vehicle_states if vehicle_states is not None else build_vehicle_loan_states(
        household.car_plan,
        scenario=scenario,
        rules=rules,
        calculation_context=calculation_context,
    )
    horizon = build_visualization_horizon(
        household,
        purchase_plans,
        car_loan,
        vehicle_states=base_vehicle_states,
        rules=rules,
    )
    return build_loan_projection_from_strategy_context(
        household,
        scenario,
        purchase_plans,
        horizon_months=horizon,
        base_monthly_debt_payment=base_monthly_debt_payment,
        provident_projection=provident_projection,
        selected_vehicle_states=vehicle_states,
        market_snapshot=market_snapshot,
        vehicle_states_provider=lambda plan: build_vehicle_loan_states(
            household.car_plan,
            scenario=scenario,
            home_purchase_month=plan.months_to_buy if plan is not None else None,
            rules=rules,
            calculation_context=calculation_context,
        ),
    )


def build_initial_provident_member_accounts(household: HouseholdData, rules: RulePackData) -> list[dict[str, float | int | str | bool]]:
    return initial_provident_member_account_rows(
        household,
        rules,
        income_rows_provider=member_monthly_income_profiles_at,
    )


def build_household_initial_provident_balance(household: HouseholdData, rules: RulePackData) -> float:
    return household_initial_provident_balance(
        household,
        rules,
        income_rows_provider=member_monthly_income_profiles_at,
    )


def build_social_security_projection(
    household: HouseholdData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary | None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    horizon_months: int | None = None,
    as_of: date | None = None,
) -> list[SocialSecurityVisualizationPoint]:
    horizon = (
        horizon_months
        if horizon_months is not None
        else build_visualization_horizon(
            household,
            purchase_plans,
            car_loan or calculate_car_loan(CarPlanData(), rules=rules),
            vehicle_states=vehicle_states,
            rules=rules,
        )
    )
    return build_social_security_account_projection(
        household,
        rules,
        purchase_plans,
        horizon_months=horizon,
        income_rows_provider=member_monthly_income_profiles_at,
        as_of=as_of,
    )


def build_provident_projection(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> list[ProvidentVisualizationPoint]:
    horizon = build_visualization_horizon(
        household,
        purchase_plans,
        car_loan,
        vehicle_states=vehicle_states,
        rules=rules,
    )
    return build_provident_account_projection(
        household,
        rules,
        purchase_plans,
        horizon_months=horizon,
        income_rows_provider=member_monthly_income_profiles_at,
        retirement_months_by_member=member_retirement_months_by_index(household, rules=rules),
        rent_withdrawal_at_month=quarterly_rent_withdrawal_before_purchase_at,
        is_offset_month=is_beijing_pf_offset_month,
        strategy_active_mode=lambda mode, purchase_month, current_month: pf_strategy_active_mode(
            mode,
            purchase_month=purchase_month,
            current_month=current_month,
        ),
    )


def build_monthly_ledger_projection(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_projection: list[LoanVisualizationPoint],
    provident_projection: list[ProvidentVisualizationPoint],
    social_security_projection: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> MonthlyLedgerResult:
    today = date.today()
    base_month = date(today.year, today.month, 1)
    base_vehicle_states = vehicle_states if vehicle_states is not None else build_vehicle_loan_states(
        household.car_plan,
        scenario=scenario,
        rules=rules,
        calculation_context=calculation_context,
    )
    horizon = build_visualization_horizon(
        household,
        purchase_plans,
        car_loan,
        vehicle_states=base_vehicle_states,
        rules=rules,
    )
    property_terminal_value_policy = get_policy(rules).property_terminal_value_policy()
    return build_projected_monthly_ledger_from_context(
        household,
        scenario,
        purchase_plans,
        car_loan,
        loan_projection,
        provident_projection,
        social_security_projection,
        vehicle_states=vehicle_states,
        base_month=base_month,
        horizon_months=horizon,
        initial_provident_balance=build_household_initial_provident_balance(household, rules),
        income_provider=lambda month: household_monthly_income_profile_at(household, rules, month, as_of=base_month),
        expense_provider=lambda month: monthly_household_expense_breakdown_at(
            household,
            month,
            as_of=base_month,
            rules=rules,
        ),
        vehicle_states_provider=lambda plan: build_vehicle_loan_states(
            household.car_plan,
            scenario=scenario,
            home_purchase_month=plan.months_to_buy,
            rules=rules,
            calculation_context=calculation_context,
        ),
        vehicle_month_projection_provider=lambda plan_vehicle_states, month: build_vehicle_month_projection(
            household.car_plan,
            month,
            vehicle_states=plan_vehicle_states,
        ),
        regular_debt_payment_at=regular_debt_payment_at,
        investment_effective_tax_rate=investment_effective_tax_rate(household),
        weighted_personal_pension_monthly_return=_weighted_personal_pension_monthly_return,
        member_income_profiles_at=lambda month: member_monthly_income_profiles_at(
            household,
            rules,
            month,
            as_of=base_month,
        ),
        personal_pension_month_at=lambda **kwargs: project_personal_pension_month(
            rules=rules,
            base_month=base_month,
            **kwargs,
        ),
        investment_withdrawal_at_purchase=investment_withdrawal_at_purchase,
        investment_allocation_for_month=investment_allocation_for_month,
        monthly_happiness_score=monthly_happiness_score,
        property_annual_price_growth_rate=property_terminal_value_policy.annual_price_growth_rate,
        property_sale_cost_rate=property_terminal_value_policy.sale_cost_rate,
        property_liquidity_discount_rate=property_terminal_value_policy.liquidity_discount_rate,
    )


__all__ = [
    "VehicleLoanState",
    "apply_provident_member_outflow",
    "beijing_pf_loan_offset_target",
    "build_household_initial_provident_balance",
    "build_initial_provident_member_accounts",
    "build_loan_projection",
    "build_monthly_ledger_projection",
    "build_provident_projection",
    "build_social_security_projection",
    "build_vehicle_loan_states",
    "build_visualization_horizon",
    "calculate_car_loan",
]
