from __future__ import annotations

from datetime import date
from functools import lru_cache
from .domain.loans import (
    calculate_loan,
    commercial_prepayment_mode as _domain_commercial_prepayment_mode,
    phased_loan_state_detail_at as _phased_loan_state_detail_at,
    summarize_phased_loans,
)
from .domain.time import (
    add_months as _add_months,
    end_of_previous_month as _end_of_previous_month,
    month_distance as _month_distance,
    month_start_for_age as _month_start_for_age,
    month_tuple_to_date as _month_tuple_to_date,
    parse_year_month as _parse_year_month,
)
from .domain.tax import (
    clamp as _clamp,
)
from .domain.children import build_child_plan_strategies
from .domain.expenses import (
    MonthlyHouseholdExpenseBreakdown,
    base_living_expense_at as _base_living_expense_at,
    monthly_household_expense_at as _domain_monthly_household_expense_at,
    monthly_household_expense_breakdown_at as _domain_monthly_household_expense_breakdown_at,
    quarterly_rent_withdrawal_before_purchase_at as _domain_quarterly_rent_withdrawal_before_purchase_at,
    regular_debt_payment_at as _domain_regular_debt_payment_at,
    rent_withdrawal_before_purchase as _domain_rent_withdrawal_before_purchase,
)
from .domain.household import (
    evaluate_home_purchase_eligibility as _domain_evaluate_home_purchase_eligibility,
    household_with_member_derived_profile as _domain_household_with_member_derived_profile,
    household_with_property_goal as _domain_household_with_property_goal,
    property_goal_for_scenario as _domain_property_goal_for_scenario,
)
from .domain.housing import (
    minimum_down_payment_ratio as _policy_minimum_down_payment_ratio,
)
from .domain.investments import (
    InvestmentWithdrawalResult,
    investment_tax_estimate as _investment_tax_estimate,
    investment_withdrawal_at_purchase as _domain_investment_withdrawal_at_purchase,
    investment_withdrawal_mode as _domain_investment_withdrawal_mode,
    investment_withdrawal_mode_label as _domain_investment_withdrawal_mode_label,
)
from .domain.scoring import (
    clamp_score as _clamp_score,
)
from .events import build_plan_events_from_context
from .engine_config import parallel_worker_count as _parallel_worker_count
from .tax_engine import (
    build_tax_events,
    build_tax_monthly_points,
    build_tax_strategy_items,
    build_tax_strategy_timeline,
    calculate_household_tax,
    calculate_household_tax_for_year,
    household_monthly_income_profile_at,
)
from .result_assembly import AffordabilityResultInputs, build_affordability_result
from .planning_summary import affordability_status, home_loan_summaries
from .policies import get_policy
from .strategies.home import (
    family_down_payment_upfront_support as _strategy_family_down_payment_upfront_support,
)
from .strategies.home_provident_strategy import (
    is_beijing_pf_offset_month as _strategy_is_beijing_pf_offset_month,
    policy_default_pf_account_strategy as _strategy_policy_default_pf_account_strategy,
    semiannual_loan_offset_monthly_equivalent as _strategy_semiannual_loan_offset_monthly_equivalent,
)
from .strategies.stress import build_stress_tests as _strategy_build_stress_tests
from .projection.horizon import retirement_tail_months as _retirement_tail_months
from . import projection_facade as _projection_facade
from . import purchase_facade as _purchase_facade
from . import vehicle_facade as _vehicle_facade
from .strategy_pipeline import run_strategy_pipeline
from .calculation_context import (
    build_purchase_cash_context,
    build_vehicle_planning_context,
    prepare_household_context,
)
from .schemas import (
    AffordabilityResult,
    CalculationContextSnapshot,
    CarLoanSummary,
    CarPlanAnalysis,
    CarPlanData,
    HouseholdData,
    IncomeMember,
    LoanSummary,
    MarketSnapshotData,
    MonthlyCashflowPoint,
    PlanEventPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    StressResult,
    TaxMemberSummary,
    YieldSensitivityPoint,
)


VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


_visualization_horizon_months = _projection_facade.visualization_horizon_months


def monthly_household_expense_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
    rules: RulePackData | None = None,
    home_purchase_month: int | None = None,
) -> float:
    active_rules = rules or RulePackData()
    return _domain_monthly_household_expense_at(
        household,
        months_from_now,
        as_of=as_of,
        rules=active_rules,
        home_purchase_month=home_purchase_month,
    )


def monthly_household_expense_breakdown_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
    rules: RulePackData | None = None,
    home_purchase_month: int | None = None,
) -> MonthlyHouseholdExpenseBreakdown:
    active_rules = rules or RulePackData()
    return _domain_monthly_household_expense_breakdown_at(
        household,
        months_from_now,
        as_of=as_of,
        rules=active_rules,
        home_purchase_month=home_purchase_month,
    )


def _household_with_member_derived_profile(household: HouseholdData) -> HouseholdData:
    return _domain_household_with_member_derived_profile(household)


def calculate_car_loan(
    plan: CarPlanData,
    *,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    rules: RulePackData | None = None,
) -> CarLoanSummary:
    return _vehicle_facade.calculate_car_loan(
        plan,
        initial_cash=initial_cash,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        rules=rules,
    )


def _vehicle_loan_states(
    plan: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[VehicleLoanState]:
    return _vehicle_facade.vehicle_loan_states(
        plan,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
        rules=rules,
        calculation_context=calculation_context,
    )


def _aggregate_car_loan(
    plan: CarPlanData,
    *,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> CarLoanSummary:
    return _vehicle_facade.aggregate_car_loan(
        plan,
        car_loan_calculator=calculate_car_loan,
        initial_cash=initial_cash,
        monthly_cash_savings_before_car=monthly_cash_savings_before_car,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
        rules=rules,
        calculation_context=calculation_context,
    )


def _vehicle_update_month(plan: CarPlanData, purchase_month: int | None) -> int | None:
    return _vehicle_facade.vehicle_update_month(plan, purchase_month)


def _car_monthly_cash_cost_at(
    plan: CarPlanData,
    car_loan: CarLoanSummary,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> float:
    return _vehicle_facade.car_monthly_cash_cost_at(plan, month, vehicle_states=vehicle_states)


def _car_down_payment_at(
    plan: CarPlanData,
    car_loan: CarLoanSummary,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
) -> float:
    states = vehicle_states if vehicle_states is not None else _vehicle_loan_states(plan)
    return _vehicle_facade.car_down_payment_at(month, vehicle_states=states)


def build_car_plan_analyses(
    household: HouseholdData,
    *,
    net_monthly_income: float,
    annual_investment_return: float = 0.0,
    rules: RulePackData | None = None,
) -> list[CarPlanAnalysis]:
    rules = rules or RulePackData()
    current_monthly_expense = monthly_household_expense_at(household, rules=rules)
    return _vehicle_facade.build_car_plan_analyses(
        household,
        net_monthly_income=net_monthly_income,
        current_monthly_expense=current_monthly_expense,
        car_loan_calculator=calculate_car_loan,
        annual_investment_return=annual_investment_return,
        rules=rules,
    )


def _car_plan_with_selected_strategies(
    plan: CarPlanData,
    analyses: list[CarPlanAnalysis],
) -> CarPlanData:
    return _vehicle_facade.car_plan_with_selected_strategies(plan, analyses)

def _investment_withdrawal_at_purchase(
    *,
    scenario: ScenarioData,
    cash_before_transaction: float,
    investment_before_transaction: float,
    required_cash_after_pf: float,
    required_liquidity_reserve: float,
    sell_fee_rate: float,
    investment_enabled: bool,
) -> InvestmentWithdrawalResult:
    return _domain_investment_withdrawal_at_purchase(
        scenario=scenario,
        cash_before_transaction=cash_before_transaction,
        investment_before_transaction=investment_before_transaction,
        required_cash_after_pf=required_cash_after_pf,
        required_liquidity_reserve=required_liquidity_reserve,
        sell_fee_rate=sell_fee_rate,
        investment_enabled=investment_enabled,
    )


def _family_down_payment_upfront_support(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_month: int,
    remaining_upfront_cash_required: float,
) -> float:
    return _strategy_family_down_payment_upfront_support(
        household,
        scenario,
        purchase_month,
        remaining_upfront_cash_required,
    )


def _rent_withdrawal_before_purchase(household: HouseholdData) -> float:
    return _domain_rent_withdrawal_before_purchase(household)


def _quarterly_rent_withdrawal_before_purchase_at(household: HouseholdData, month: int) -> float:
    return _domain_quarterly_rent_withdrawal_before_purchase_at(household, month)


def _regular_debt_payment_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> float:
    return _domain_regular_debt_payment_at(household, months_from_now, as_of=as_of)


def _policy_default_pf_account_strategy(
    rules: RulePackData,
    household: HouseholdData | None = None,
    *,
    months_from_now: int = 0,
    as_of: date | None = None,
) -> str:
    return _strategy_policy_default_pf_account_strategy(
        rules,
        household,
        months_from_now=months_from_now,
        as_of=as_of,
    )


def _is_beijing_pf_offset_month(months_from_now: int, *, as_of: date | None = None) -> bool:
    return _strategy_is_beijing_pf_offset_month(months_from_now, as_of=as_of)


_beijing_pf_loan_offset_target = _projection_facade.beijing_pf_loan_offset_target


def _semiannual_loan_offset_monthly_equivalent(
    *,
    purchase_month: int,
    starting_pf_balance: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
    horizon_months: int = 12,
    as_of: date | None = None,
) -> float:
    return _strategy_semiannual_loan_offset_monthly_equivalent(
        purchase_month=purchase_month,
        starting_pf_balance=starting_pf_balance,
        monthly_pf_deposit=monthly_pf_deposit,
        provident_monthly_payment=provident_monthly_payment,
        rules=rules,
        horizon_months=horizon_months,
        as_of=as_of,
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
) -> list[PurchasePlanAnalysis]:
    return _purchase_facade.build_purchase_plan_analyses(
        household,
        scenario,
        rules,
        tax_summaries=tax_summaries,
        net_monthly_income=net_monthly_income,
        car_loan=car_loan,
        taxes_and_fees=taxes_and_fees,
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
) -> list[YieldSensitivityPoint]:
    return _purchase_facade.build_yield_sensitivity(
        household,
        scenario,
        rules,
        tax_summaries=tax_summaries,
        net_monthly_income=net_monthly_income,
        car_loan=car_loan,
        taxes_and_fees=taxes_and_fees,
        parallel_workers=parallel_workers,
    )


build_loan_visualization = _projection_facade.loan_visualization
_initial_provident_member_accounts = _projection_facade.initial_provident_member_accounts
_household_initial_provident_balance = _projection_facade.household_initial_provident_balance
build_social_security_visualization = _projection_facade.social_security_visualization
_apply_provident_member_outflow = _projection_facade.provident_member_outflow
build_provident_visualization = _projection_facade.provident_visualization
build_monthly_ledger = _projection_facade.monthly_ledger
build_monthly_cashflow_visualization = _projection_facade.monthly_cashflow_visualization


def build_plan_events(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    monthly_cashflow: list[MonthlyCashflowPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
) -> list[PlanEventPoint]:
    return build_plan_events_from_context(
        household,
        scenario,
        rules,
        purchase_plans,
        monthly_cashflow,
        provident_visualization,
        initial_provident_balance_provider=_household_initial_provident_balance,
        retirement_window_end_provider=lambda target_household, current_month: _retirement_tail_months(
            target_household,
            as_of=current_month,
            rules=rules,
        ),
        vehicle_loan_states_for_plan=lambda plan: _vehicle_loan_states(
            household.car_plan,
            scenario=scenario,
            home_purchase_month=plan.months_to_buy,
            rules=rules,
        ),
    )


def evaluate_eligibility(household: HouseholdData, rules: RulePackData) -> tuple[bool, list[str]]:
    return _domain_evaluate_home_purchase_eligibility(household, rules)


def _property_goal_for_scenario(household: HouseholdData, scenario: ScenarioData) -> tuple[int, str]:
    return _domain_property_goal_for_scenario(household, scenario)


def _household_with_property_goal(household: HouseholdData, scenario: ScenarioData) -> tuple[HouseholdData, str]:
    return _domain_household_with_property_goal(household, scenario)


def calculate_affordability(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    market_snapshot: MarketSnapshotData | None = None,
    stress_name: str | None = None,
    include_stress_tests: bool = False,
    calculation_context: CalculationContextSnapshot | None = None,
) -> AffordabilityResult:
    base_date = date.today()
    base_month = date(base_date.year, base_date.month, 1)
    parallel_workers = 1 if stress_name else _parallel_worker_count(rules, 4)
    risk_policy = get_policy(rules).affordability_risk_policy()
    min_down_payment_ratio = max(
        _policy_minimum_down_payment_ratio(household, False, rules),
        _policy_minimum_down_payment_ratio(household, True, rules),
    )
    household_context = prepare_household_context(
        household,
        scenario,
        rules,
        base_month=base_month,
    )
    household = household_context.household
    cashflow_household = household_context.cashflow_household
    vehicle_context = build_vehicle_planning_context(household_context, scenario, rules, calculation_context=calculation_context)
    cashflow_household = vehicle_context.cashflow_household
    strategy_household = vehicle_context.strategy_household
    purchase_cash_context = build_purchase_cash_context(
        strategy_household,
        scenario,
        rules,
        min_down_payment_ratio=min_down_payment_ratio,
        market_snapshot=market_snapshot,
    )
    eligible, eligibility_notes = (
        evaluate_eligibility(strategy_household, rules)
        if purchase_cash_context.has_purchase_target
        else (True, ["当前未启用购房目标，购房资格和贷款策略暂不进入基线测算。"])
    )
    strategy_pipeline = run_strategy_pipeline(
        strategy_household,
        scenario,
        rules,
        household_context=household_context,
        vehicle_context=vehicle_context,
        purchase_cash_context=purchase_cash_context,
        base_month=base_month,
        stress_name=stress_name,
        parallel_workers=parallel_workers,
        calculation_context=calculation_context,
        market_snapshot=market_snapshot,
    )
    purchase_plan_analyses = strategy_pipeline.purchase_plan_analyses
    yield_sensitivity = strategy_pipeline.yield_sensitivity
    projection_pipeline = strategy_pipeline.projection
    loan_visualization = projection_pipeline.loan_visualization
    provident_visualization = projection_pipeline.provident_visualization
    social_security_visualization = projection_pipeline.social_security_visualization
    monthly_cashflow_visualization = projection_pipeline.monthly_cashflow_visualization
    monthly_visualization_details = projection_pipeline.monthly_visualization_details
    account_snapshots = projection_pipeline.account_snapshots
    monthly_ledger = projection_pipeline.monthly_ledger
    annual_financial_summaries = projection_pipeline.annual_financial_summaries
    annual_visualization_details = projection_pipeline.annual_visualization_details
    account_concepts = projection_pipeline.account_concepts
    core_object_groups = projection_pipeline.core_object_groups
    strategy_explanations = projection_pipeline.strategy_explanations
    plan_events = projection_pipeline.plan_events
    selected_home_purchase_month = projection_pipeline.selected_home_purchase_month
    child_plan_strategies = projection_pipeline.child_plan_strategies
    tax_strategy_items = build_tax_strategy_items(
        household,
        scenario,
        rules,
        base_date=base_month,
        horizon_months=household_context.tax_horizon_months,
        selected_purchase_month=selected_home_purchase_month,
    )
    tax_strategy_timeline = build_tax_strategy_timeline(
        household,
        rules,
        tax_strategy_items,
        base_date=base_month,
        horizon_months=household_context.tax_horizon_months,
        tax_events=household_context.tax_events,
    )
    home_loan_context = home_loan_summaries(
        has_purchase_target=purchase_cash_context.has_purchase_target,
        household=strategy_household,
        scenario=scenario,
        rules=rules,
        market_snapshot=market_snapshot,
    )

    affordability = affordability_status(
        has_purchase_target=purchase_cash_context.has_purchase_target,
        eligible=eligible,
        household=cashflow_household,
        stated_down_payment=purchase_cash_context.stated_down_payment,
        taxes_and_fees=purchase_cash_context.taxes_and_fees,
        car_loan=vehicle_context.purchase_strategy_car_loan,
        vehicle_states=vehicle_context.pre_home_vehicle_states,
        commercial=home_loan_context.commercial,
        provident=home_loan_context.provident,
        net_monthly_income=household_context.net_monthly_income,
        current_monthly_expense=household_context.current_monthly_expense,
        recommended_emergency_months=risk_policy.recommended_emergency_months,
        caution_dti=risk_policy.caution_dti,
        danger_dti=risk_policy.danger_dti,
        car_down_payment_at=lambda plan, loan, month: _car_down_payment_at(
            plan,
            loan,
            month,
            vehicle_states=vehicle_context.pre_home_vehicle_states,
        ),
        car_monthly_cash_cost_at=lambda plan, loan, month: _car_monthly_cash_cost_at(
            plan,
            loan,
            month,
            vehicle_states=vehicle_context.pre_home_vehicle_states,
        ),
    )

    result = build_affordability_result(
        AffordabilityResultInputs(
            status=affordability.status,
            status_reason=affordability.status_reason,
            eligible=eligible,
            eligibility_notes=eligibility_notes,
            total_required_cash=affordability.total_required_cash,
            minimum_down_payment=purchase_cash_context.minimum_down_payment,
            stated_down_payment=purchase_cash_context.stated_down_payment,
            taxes_and_fees=purchase_cash_context.taxes_and_fees,
            funding_gap=affordability.funding_gap,
            remaining_cash=affordability.remaining_cash,
            gross_monthly_income=household_context.gross_monthly_income,
            net_monthly_income=household_context.net_monthly_income,
            annual_income_tax=household_context.annual_income_tax,
            phased_loan_monthly_payment=household_context.phased_loan_monthly_payment,
            effective_monthly_debt_payment=household_context.effective_monthly_debt_payment,
            phased_loan_summaries=household_context.phased_loan_summaries,
            car_loan=vehicle_context.car_loan,
            car_plan_analyses=vehicle_context.car_plan_analyses,
            monthly_payment=affordability.monthly_payment,
            post_purchase_cash_flow=affordability.post_purchase_cash_flow,
            debt_to_income_ratio=affordability.debt_to_income_ratio,
            emergency_months=affordability.emergency_months,
            commercial_loan=home_loan_context.commercial,
            provident_loan=home_loan_context.provident,
            tax_summaries=household_context.tax_summaries,
            tax_year_summaries=household_context.tax_year_summaries,
            tax_monthly_points=household_context.tax_monthly_points,
            tax_visualization_details=household_context.tax_visualization_details,
            tax_events=household_context.tax_events,
            tax_strategy_items=tax_strategy_items,
            tax_strategy_timeline=tax_strategy_timeline,
            career_shock_projection=household_context.career_shock_projection,
            investment_plan_recommendations=vehicle_context.investment_plan_recommendations,
            current_investment_allocation=vehicle_context.current_investment_allocation,
            child_plan_strategies=child_plan_strategies,
            annual_financial_summaries=annual_financial_summaries,
            purchase_plan_analyses=purchase_plan_analyses,
            yield_sensitivity=yield_sensitivity,
            monthly_cashflow_visualization=monthly_cashflow_visualization,
            monthly_visualization_details=monthly_visualization_details,
            annual_visualization_details=annual_visualization_details,
            account_snapshots=account_snapshots,
            monthly_ledger=monthly_ledger,
            loan_visualization=loan_visualization,
            provident_visualization=provident_visualization,
            social_security_visualization=social_security_visualization,
            account_concepts=account_concepts,
            core_object_groups=core_object_groups,
            strategy_explanations=strategy_explanations,
            plan_events=plan_events,
            property_goal_assumption=vehicle_context.property_goal_assumption,
            provident_year_reasons=home_loan_context.provident_year_reasons,
            scenario=scenario,
            base_month=base_month,
        )
    )

    if include_stress_tests and stress_name is None and purchase_cash_context.has_purchase_target:
        result.stress_tests = build_stress_tests(
            household,
            scenario,
            rules,
            market_snapshot=market_snapshot,
            parallel_workers=min(parallel_workers, 3),
        )
    return result


def build_stress_tests(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    market_snapshot: MarketSnapshotData | None = None,
    parallel_workers: int = 1,
) -> list[StressResult]:
    return _strategy_build_stress_tests(
        household,
        scenario,
        rules,
        affordability_calculator=lambda stress_household, stress_scenario, stress_rules, name: calculate_affordability(
            stress_household,
            stress_scenario,
            stress_rules,
            market_snapshot=market_snapshot,
            stress_name=name,
        ),
        parallel_workers=parallel_workers,
        market_snapshot=market_snapshot,
    )
