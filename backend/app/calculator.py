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
    months_between_months as _months_between_months,
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
from .domain.personal_pension import personal_pension_withdrawal_start_month
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
    optimize_personal_pension_strategies,
)
from .result_assembly import AffordabilityResultInputs, build_affordability_result
from .planning_summary import affordability_status, home_loan_summaries, recommended_plan_status
from .policies import get_policy
from .profiling import profile_span
from .strategies.home import (
    family_down_payment_upfront_support as _strategy_family_down_payment_upfront_support,
)
from .strategies.home_provident_strategy import (
    is_beijing_pf_offset_month as _strategy_is_beijing_pf_offset_month,
    policy_default_pf_account_strategy as _strategy_policy_default_pf_account_strategy,
    semiannual_loan_offset_monthly_equivalent as _strategy_semiannual_loan_offset_monthly_equivalent,
)
from .strategies.stress import build_stress_tests as _strategy_build_stress_tests
from .strategies.investment import build_investment_plan_recommendations
from .strategies.portfolio import build_portfolio_strategy_recommendations
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
    InvestmentPlanRecommendation,
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


def _selected_lifecycle_purchase_plan(
    purchase_plans: list[PurchasePlanAnalysis],
    scenario: ScenarioData,
) -> PurchasePlanAnalysis | None:
    recommended = next((plan for plan in purchase_plans if plan.is_recommended), None)
    if recommended is not None:
        return recommended
    selected = next(
        (plan for plan in purchase_plans if plan.variant == scenario.selected_purchase_plan_variant),
        None,
    )
    if selected is not None:
        return selected
    timed = min(
        (plan for plan in purchase_plans if plan.months_to_buy is not None),
        key=lambda plan: (
            plan.cash_shortfall,
            plan.insolvency_month is not None,
            plan.months_to_buy or 0,
        ),
        default=None,
    )
    return timed or next((plan for plan in purchase_plans if plan.source == "baseline"), None)


def _lifecycle_plan_is_feasible(plan: PurchasePlanAnalysis | None) -> bool:
    return bool(
        plan is not None
        and (plan.months_to_buy is not None or plan.source == "baseline")
        and plan.cash_shortfall <= 0
        and plan.cash_stress_shortfall <= 0
        and plan.insolvency_month is None
        and plan.liquid_assets_exhausted_month is None
        and plan.liquidity_ok
        and plan.cash_stress_ok
    )


def _auto_personal_pension_contribution_indexes(household: HouseholdData) -> set[int]:
    return {
        index
        for index, member in enumerate(household.members)
        if member.personal_pension_account_enabled
        and member.personal_pension_participation_eligible
        and member.pension_account_enabled
        and member.personal_pension_contribution_mode == "auto_tax_optimal"
        and member.personal_pension_auto_suspend_for_cash_safety
    }


def _personal_pension_risk_precedes_withdrawal(
    household: HouseholdData,
    rules: RulePackData,
    plan: PurchasePlanAnalysis | None,
    *,
    base_month: date,
    member_indexes: set[int],
) -> bool:
    if plan is None or plan.insolvency_month is None or not member_indexes:
        return False
    return any(
        plan.insolvency_month
        < _months_between_months(
            base_month,
            personal_pension_withdrawal_start_month(
                household.members[index],
                index,
                rules,
                base_month=base_month,
            ),
        )
        for index in member_indexes
    )


def _personal_pension_counterfactual_improves_risk(
    current_plan: PurchasePlanAnalysis | None,
    suspended_plan: PurchasePlanAnalysis | None,
) -> bool:
    if current_plan is None or suspended_plan is None or current_plan.insolvency_month is None:
        return False
    if suspended_plan.insolvency_month is None:
        return True
    current_shortfall = max(current_plan.cash_shortfall, current_plan.cash_stress_shortfall)
    suspended_shortfall = max(suspended_plan.cash_shortfall, suspended_plan.cash_stress_shortfall)
    return (
        suspended_plan.insolvency_month > current_plan.insolvency_month
        and suspended_shortfall + 1 < current_shortfall
    )


_AUTO_INVESTMENT_PLAN_ALIASES = {
    "balanced_monthly_investment": "balanced_monthly_investment",
    "growth_monthly_investment": "growth_monthly_investment",
    "goal_liquidity_first": "goal_liquidity_first",
    "cash_reserve_first": "cash_reserve_first",
    "lifecycle_cashflow_recovery": "lifecycle_cashflow_recovery",
}


def _household_with_selected_auto_investment_plan(
    household: HouseholdData,
    recommendations: list[InvestmentPlanRecommendation],
) -> HouseholdData | None:
    selected_plan_name = _AUTO_INVESTMENT_PLAN_ALIASES.get(household.investment_plan_name)
    if selected_plan_name is None:
        return None
    recommendation = next(
        (item for item in recommendations if item.plan_name == selected_plan_name),
        None,
    )
    if recommendation is None:
        return None
    update = {
        "investment_plan_name": recommendation.plan_name,
        "investment_risk_level": recommendation.risk_level,
        "monthly_investment_amount": recommendation.monthly_investment,
        "investment_cash_reserve_months": recommendation.cash_reserve_months,
        "investment_equity_ratio": recommendation.equity_ratio,
        "investment_bond_ratio": recommendation.bond_ratio,
        "investment_cash_ratio": recommendation.cash_ratio,
        "investment_auto_rebalance": True,
    }
    if all(getattr(household, key) == value for key, value in update.items()):
        return None
    return household.model_copy(update=update)


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
    configured_tax_strategy_household = household
    with profile_span("personal_pension_economic_optimization"):
        household, personal_pension_optimization_decisions = optimize_personal_pension_strategies(
            household,
            scenario,
            rules,
            base_date=base_month,
        )
    parallel_workers = 1 if stress_name else _parallel_worker_count(rules, 4)
    risk_policy = get_policy(rules).affordability_risk_policy()
    property_terminal_value_policy = get_policy(rules).property_terminal_value_policy()
    min_down_payment_ratio = max(
        _policy_minimum_down_payment_ratio(household, False, rules),
        _policy_minimum_down_payment_ratio(household, True, rules),
    )
    with profile_span("household_context"):
        household_context = prepare_household_context(
            household,
            scenario,
            rules,
            base_month=base_month,
        )
    household = household_context.household
    cashflow_household = household_context.cashflow_household
    with profile_span("vehicle_context"):
        vehicle_context = build_vehicle_planning_context(household_context, scenario, rules, calculation_context=calculation_context)
    cashflow_household = vehicle_context.cashflow_household
    strategy_household = vehicle_context.strategy_household
    with profile_span("purchase_cash_context"):
        purchase_cash_context = build_purchase_cash_context(
            strategy_household,
            scenario,
            rules,
            min_down_payment_ratio=min_down_payment_ratio,
            market_snapshot=market_snapshot,
        )
    with profile_span("eligibility"):
        eligible, eligibility_notes = (
            evaluate_eligibility(strategy_household, rules)
            if purchase_cash_context.has_purchase_target
            else (True, ["当前未启用购房目标，购房资格和贷款策略暂不进入基线测算。"])
        )
    with profile_span("strategy_pipeline"):
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
    auto_suspended_personal_pension_member_indexes: set[int] = set()
    personal_pension_original_insolvency_month: int | None = None
    auto_personal_pension_member_indexes = _auto_personal_pension_contribution_indexes(strategy_household)
    initial_selected_plan = _selected_lifecycle_purchase_plan(
        strategy_pipeline.purchase_plan_analyses,
        scenario,
    )
    if _personal_pension_risk_precedes_withdrawal(
        strategy_household,
        rules,
        initial_selected_plan,
        base_month=base_month,
        member_indexes=auto_personal_pension_member_indexes,
    ):
        with profile_span("personal_pension_counterfactual"):
            suspended_input_household = household.model_copy(
                update={
                    "members": [
                        member.model_copy(update={"personal_pension_contribution_mode": "none"})
                        if index in auto_personal_pension_member_indexes
                        else member
                        for index, member in enumerate(household.members)
                    ]
                }
            )
            suspended_household_context = prepare_household_context(
                suspended_input_household,
                scenario,
                rules,
                base_month=base_month,
            )
            suspended_vehicle_context = build_vehicle_planning_context(
                suspended_household_context,
                scenario,
                rules,
                calculation_context=calculation_context,
            )
            suspended_purchase_cash_context = build_purchase_cash_context(
                suspended_vehicle_context.strategy_household,
                scenario,
                rules,
                min_down_payment_ratio=min_down_payment_ratio,
                market_snapshot=market_snapshot,
            )
            suspended_strategy_pipeline = run_strategy_pipeline(
                suspended_vehicle_context.strategy_household,
                scenario,
                rules,
                household_context=suspended_household_context,
                vehicle_context=suspended_vehicle_context,
                purchase_cash_context=suspended_purchase_cash_context,
                base_month=base_month,
                stress_name=stress_name,
                parallel_workers=parallel_workers,
                calculation_context=calculation_context,
                market_snapshot=market_snapshot,
            )
            suspended_selected_plan = _selected_lifecycle_purchase_plan(
                suspended_strategy_pipeline.purchase_plan_analyses,
                scenario,
            )
        if _personal_pension_counterfactual_improves_risk(
            initial_selected_plan,
            suspended_selected_plan,
        ):
            auto_suspended_personal_pension_member_indexes = auto_personal_pension_member_indexes
            personal_pension_original_insolvency_month = initial_selected_plan.insolvency_month
            household_context = suspended_household_context
            household = suspended_household_context.household
            cashflow_household = suspended_vehicle_context.cashflow_household
            vehicle_context = suspended_vehicle_context
            strategy_household = suspended_vehicle_context.strategy_household
            purchase_cash_context = suspended_purchase_cash_context
            strategy_pipeline = suspended_strategy_pipeline

    initial_investment_selected_plan = _selected_lifecycle_purchase_plan(
        strategy_pipeline.purchase_plan_analyses,
        scenario,
    )
    initial_investment_home_month = (
        initial_investment_selected_plan.months_to_buy
        if initial_investment_selected_plan
        else (12 if purchase_cash_context.has_purchase_target else None)
    )
    initial_investment_vehicle_month = (
        vehicle_context.car_loan.purchase_delay_months
        if vehicle_context.car_loan.enabled and vehicle_context.car_loan.purchase_delay_months > 0
        else None
    )
    initial_investment_recommendations = build_investment_plan_recommendations(
        cashflow_household,
        scenario,
        net_monthly_income=household_context.net_monthly_income,
        current_monthly_expense=household_context.current_monthly_expense,
        effective_monthly_debt_payment=household_context.effective_monthly_debt_payment,
        car_loan=vehicle_context.car_loan,
        home_purchase_month=initial_investment_home_month,
        home_required_cash=(
            initial_investment_selected_plan.required_cash_after_pf_extract
            if initial_investment_selected_plan
            else purchase_cash_context.stated_down_payment + purchase_cash_context.taxes_and_fees
        ),
        home_required_reserve=(
            initial_investment_selected_plan.required_liquidity_reserve
            if initial_investment_selected_plan
            else household_context.current_monthly_expense * cashflow_household.required_liquidity_months
        ),
        vehicle_purchase_month=initial_investment_vehicle_month,
        lifecycle_cash_shortfall=(
            max(initial_investment_selected_plan.cash_shortfall, initial_investment_selected_plan.cash_stress_shortfall)
            if initial_investment_selected_plan
            else 0.0
        ),
        lifecycle_insolvency_month=(
            initial_investment_selected_plan.insolvency_month if initial_investment_selected_plan else None
        ),
        lifecycle_liquid_assets_exhausted_month=(
            initial_investment_selected_plan.liquid_assets_exhausted_month if initial_investment_selected_plan else None
        ),
    )
    auto_investment_household = _household_with_selected_auto_investment_plan(
        household,
        initial_investment_recommendations,
    )
    auto_investment_monthly_cap: float | None = None
    if auto_investment_household is not None:
        baseline_investment_state = (
            household_context,
            household,
            cashflow_household,
            vehicle_context,
            strategy_household,
            purchase_cash_context,
            strategy_pipeline,
        )

        def project_auto_investment_household(target_household: HouseholdData):
            target_household_context = prepare_household_context(
                target_household,
                scenario,
                rules,
                base_month=base_month,
            )
            target_vehicle_context = build_vehicle_planning_context(
                target_household_context,
                scenario,
                rules,
                calculation_context=calculation_context,
            )
            target_purchase_cash_context = build_purchase_cash_context(
                target_vehicle_context.strategy_household,
                scenario,
                rules,
                min_down_payment_ratio=min_down_payment_ratio,
                market_snapshot=market_snapshot,
            )
            target_strategy_pipeline = run_strategy_pipeline(
                target_vehicle_context.strategy_household,
                scenario,
                rules,
                household_context=target_household_context,
                vehicle_context=target_vehicle_context,
                purchase_cash_context=target_purchase_cash_context,
                base_month=base_month,
                stress_name=stress_name,
                parallel_workers=parallel_workers,
                calculation_context=calculation_context,
                market_snapshot=market_snapshot,
            )
            return (
                target_household_context,
                target_household_context.household,
                target_vehicle_context.cashflow_household,
                target_vehicle_context,
                target_vehicle_context.strategy_household,
                target_purchase_cash_context,
                target_strategy_pipeline,
            )

        with profile_span("auto_investment_strategy_projection"):
            full_investment_state = project_auto_investment_household(auto_investment_household)
        full_plan = _selected_lifecycle_purchase_plan(full_investment_state[-1].purchase_plan_analyses, scenario)
        selected_investment_state = full_investment_state
        selected_monthly_investment = auto_investment_household.monthly_investment_amount
        if not _lifecycle_plan_is_feasible(full_plan):
            baseline_plan = _selected_lifecycle_purchase_plan(
                baseline_investment_state[-1].purchase_plan_analyses,
                scenario,
            )
            selected_investment_state = baseline_investment_state
            selected_monthly_investment = 0.0
            lower = 0.0
            upper = auto_investment_household.monthly_investment_amount
            if _lifecycle_plan_is_feasible(baseline_plan) and upper > 0:
                with profile_span("auto_investment_safe_amount_search"):
                    for _ in range(3):
                        trial_amount = (lower + upper) / 2
                        trial_household = auto_investment_household.model_copy(
                            update={"monthly_investment_amount": trial_amount}
                        )
                        trial_state = project_auto_investment_household(trial_household)
                        trial_plan = _selected_lifecycle_purchase_plan(
                            trial_state[-1].purchase_plan_analyses,
                            scenario,
                        )
                        if _lifecycle_plan_is_feasible(trial_plan):
                            lower = trial_amount
                            selected_monthly_investment = trial_amount
                            selected_investment_state = trial_state
                        else:
                            upper = trial_amount
        auto_investment_monthly_cap = round(max(0.0, selected_monthly_investment), 2)
        (
            household_context,
            household,
            cashflow_household,
            vehicle_context,
            strategy_household,
            purchase_cash_context,
            strategy_pipeline,
        ) = selected_investment_state
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
    selected_purchase_plan = _selected_lifecycle_purchase_plan(purchase_plan_analyses, scenario)
    investment_home_month = (
        selected_purchase_plan.months_to_buy
        if selected_purchase_plan
        else (12 if purchase_cash_context.has_purchase_target else None)
    )
    investment_vehicle_month = (
        vehicle_context.car_loan.purchase_delay_months
        if vehicle_context.car_loan.enabled and vehicle_context.car_loan.purchase_delay_months > 0
        else None
    )
    current_investment_allocation = vehicle_context.current_investment_allocation
    investment_plan_recommendations = build_investment_plan_recommendations(
        cashflow_household,
        scenario,
        net_monthly_income=household_context.net_monthly_income,
        current_monthly_expense=household_context.current_monthly_expense,
        effective_monthly_debt_payment=household_context.effective_monthly_debt_payment,
        car_loan=vehicle_context.car_loan,
        home_purchase_month=investment_home_month,
        home_required_cash=selected_purchase_plan.required_cash_after_pf_extract if selected_purchase_plan else purchase_cash_context.stated_down_payment + purchase_cash_context.taxes_and_fees,
        home_required_reserve=selected_purchase_plan.required_liquidity_reserve if selected_purchase_plan else household_context.current_monthly_expense * cashflow_household.required_liquidity_months,
        vehicle_purchase_month=investment_vehicle_month,
        lifecycle_cash_shortfall=(
            max(selected_purchase_plan.cash_shortfall, selected_purchase_plan.cash_stress_shortfall)
            if selected_purchase_plan
            else 0.0
        ),
        lifecycle_insolvency_month=selected_purchase_plan.insolvency_month if selected_purchase_plan else None,
        lifecycle_liquid_assets_exhausted_month=(
            selected_purchase_plan.liquid_assets_exhausted_month if selected_purchase_plan else None
        ),
        maximum_monthly_investment=auto_investment_monthly_cap,
    )
    with profile_span("tax_strategy"):
        tax_strategy_items = build_tax_strategy_items(
            configured_tax_strategy_household,
            scenario,
            rules,
            base_date=base_month,
            horizon_months=household_context.tax_horizon_months,
            selected_purchase_month=selected_home_purchase_month,
            selected_purchase_plan=selected_purchase_plan,
            auto_suspended_personal_pension_member_indexes=auto_suspended_personal_pension_member_indexes,
            personal_pension_original_insolvency_month=personal_pension_original_insolvency_month,
            personal_pension_optimization_decisions=personal_pension_optimization_decisions,
        )
        tax_strategy_timeline = build_tax_strategy_timeline(
            configured_tax_strategy_household,
            rules,
            tax_strategy_items,
            base_date=base_month,
            horizon_months=household_context.tax_horizon_months,
            tax_events=household_context.tax_events,
        )
    with profile_span("portfolio_strategy"):
        portfolio_strategy_recommendations = build_portfolio_strategy_recommendations(
            purchase_plans=purchase_plan_analyses,
            car_plans=vehicle_context.car_plan_analyses,
            investment_plans=investment_plan_recommendations,
            child_plans=child_plan_strategies,
            tax_strategy_items=tax_strategy_items,
            scenario=scenario,
        )
    with profile_span("home_loan_summary"):
        home_loan_context = home_loan_summaries(
            has_purchase_target=purchase_cash_context.has_purchase_target,
            household=strategy_household,
            scenario=scenario,
            rules=rules,
            market_snapshot=market_snapshot,
        )

    with profile_span("affordability_status"):
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

    with profile_span("result_assembly"):
        recommended_status, recommended_reason = recommended_plan_status(purchase_plan_analyses)
        result = build_affordability_result(
        AffordabilityResultInputs(
            status=recommended_status if purchase_cash_context.has_purchase_target else affordability.status,
            status_reason=recommended_reason if purchase_cash_context.has_purchase_target else affordability.status_reason,
            immediate_purchase_status=affordability.status,
            immediate_purchase_reason=affordability.status_reason,
            recommended_plan_status=recommended_status if purchase_cash_context.has_purchase_target else affordability.status,
            recommended_plan_reason=recommended_reason if purchase_cash_context.has_purchase_target else affordability.status_reason,
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
            investment_plan_recommendations=investment_plan_recommendations,
            portfolio_strategy_recommendations=portfolio_strategy_recommendations,
            current_investment_allocation=current_investment_allocation,
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
            property_terminal_value_assumption=(
                "房产终值按可变现净值估算："
                f"年价格变化假设 {property_terminal_value_policy.annual_price_growth_rate:.1%}，"
                f"出售成本 {property_terminal_value_policy.sale_cost_rate:.1%}，"
                f"流动性折价 {property_terminal_value_policy.liquidity_discount_rate:.1%}；"
                "不把挂牌价或买入总价直接当作可立即动用的资产。"
            ),
            provident_year_reasons=home_loan_context.provident_year_reasons,
            scenario=scenario,
            base_month=base_month,
            calculation_context=calculation_context,
        )
    )

    if include_stress_tests and stress_name is None and purchase_cash_context.has_purchase_target:
        with profile_span("stress_tests"):
            result.stress_tests = build_stress_tests(
                household,
                scenario,
                rules,
                market_snapshot=market_snapshot,
                parallel_workers=min(parallel_workers, 3),
            )
        from .strategies.home_recommendations import with_stress_test_recommendation_gate

        result.purchase_plan_analyses = with_stress_test_recommendation_gate(
            result.purchase_plan_analyses,
            result.stress_tests,
        )
        failed_stress_names = [item.name for item in result.stress_tests if not item.feasible]
        if failed_stress_names:
            stress_reason = (
                f"压力测试未通过（{'、'.join(failed_stress_names)}）："
                "没有方案同时满足现金安全和长期偿付能力，不推荐立即执行。"
            )
            result.status = "无可行方案"
            result.status_reason = stress_reason
            result.recommended_plan_status = "无可行方案"
            result.recommended_plan_reason = stress_reason
        else:
            recommended_status, recommended_reason = recommended_plan_status(result.purchase_plan_analyses)
            result.status = recommended_status
            result.status_reason = recommended_reason
            result.recommended_plan_status = recommended_status
            result.recommended_plan_reason = recommended_reason
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
