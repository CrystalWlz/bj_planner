from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .domain.children import build_child_plan_strategies
from .events import build_plan_events_from_context
from .projection.horizon import retirement_tail_months
from .projection_facade import (
    household_initial_provident_balance,
    loan_visualization as build_loan_visualization,
    monthly_ledger as build_monthly_ledger,
    provident_visualization as build_provident_visualization,
    social_security_visualization as build_social_security_visualization,
)
from .profiling import profile_span
from .reporting import (
    build_account_concepts,
    build_annual_financial_summaries_from_ledger,
    build_core_object_group_summaries,
    build_strategy_explanations,
)
from .schemas import (
    AccountConceptSummary,
    AccountSnapshotPoint,
    AnnualFinancialSummary,
    AnnualVisualizationDetail,
    CalculationContextSnapshot,
    CarLoanSummary,
    CarPlanData,
    ChildPlanStrategyPoint,
    CoreObjectGroupSummary,
    HouseholdData,
    LoanVisualizationPoint,
    MarketSnapshotData,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    MonthlyVisualizationDetail,
    PlanEventPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    SocialSecurityVisualizationPoint,
    StrategyExplanationPoint,
)
from .vehicle_facade import vehicle_loan_states
from .strategies.home_recommendations import (
    enrich_purchase_plans_with_projection_risk,
    with_purchase_plan_recommendations,
)
from .visualization import (
    build_annual_visualization_details,
    build_monthly_cashflow_points,
    build_monthly_visualization_details,
)

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


@dataclass
class StrategyProjectionPipelineResult:
    purchase_plan_analyses: list[PurchasePlanAnalysis] = field(default_factory=list)
    loan_visualization: list[LoanVisualizationPoint] = field(default_factory=list)
    provident_visualization: list[ProvidentVisualizationPoint] = field(default_factory=list)
    social_security_visualization: list[SocialSecurityVisualizationPoint] = field(default_factory=list)
    monthly_cashflow_visualization: list[MonthlyCashflowPoint] = field(default_factory=list)
    monthly_visualization_details: list[MonthlyVisualizationDetail] = field(default_factory=list)
    annual_visualization_details: list[AnnualVisualizationDetail] = field(default_factory=list)
    account_snapshots: list[AccountSnapshotPoint] = field(default_factory=list)
    monthly_ledger: list[MonthlyLedgerEntry] = field(default_factory=list)
    annual_financial_summaries: list[AnnualFinancialSummary] = field(default_factory=list)
    account_concepts: list[AccountConceptSummary] = field(default_factory=list)
    core_object_groups: list[CoreObjectGroupSummary] = field(default_factory=list)
    strategy_explanations: list[StrategyExplanationPoint] = field(default_factory=list)
    plan_events: list[PlanEventPoint] = field(default_factory=list)
    child_plan_strategies: list[ChildPlanStrategyPoint] = field(default_factory=list)
    selected_home_purchase_month: int | None = None


def selected_purchase_month(
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
) -> int | None:
    return next(
        (
            plan.months_to_buy
            for plan in purchase_plans
            if plan.variant == scenario.selected_purchase_plan_variant and plan.months_to_buy is not None
        ),
        next((plan.months_to_buy for plan in purchase_plans if plan.months_to_buy is not None), None),
    )


def build_strategy_projection_pipeline(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    base_month: date,
    base_monthly_debt_payment: float,
    vehicle_states: list[VehicleLoanState] | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
    market_snapshot: MarketSnapshotData | None = None,
) -> StrategyProjectionPipelineResult:
    with profile_span("selected_purchase_month"):
        selected_month = selected_purchase_month(scenario, purchase_plans)
    with profile_span("vehicle_states"):
        effective_vehicle_states = (
            vehicle_loan_states(
                household.car_plan,
                scenario=scenario,
                home_purchase_month=selected_month,
                rules=rules,
                calculation_context=calculation_context,
            )
            if selected_month is not None
            else (
                vehicle_states
                if vehicle_states is not None
                else vehicle_loan_states(household.car_plan, scenario=scenario, rules=rules, calculation_context=calculation_context)
            )
        )
    with profile_span("provident_projection"):
        provident_rows = build_provident_visualization(
            household,
            scenario,
            rules,
            purchase_plans,
            car_loan,
            vehicle_states=effective_vehicle_states,
        )
    with profile_span("social_security_projection"):
        social_security_rows = build_social_security_visualization(
            household,
            rules,
            purchase_plans,
            car_loan,
            vehicle_states=effective_vehicle_states,
        )
    with profile_span("loan_projection"):
        loan_rows = build_loan_visualization(
            household,
            scenario,
            purchase_plans,
            car_loan,
            base_monthly_debt_payment=base_monthly_debt_payment,
            provident_visualization=provident_rows,
            vehicle_states=effective_vehicle_states,
            rules=rules,
            calculation_context=calculation_context,
            market_snapshot=market_snapshot,
        )
    with profile_span("ledger_projection"):
        ledger_result = build_monthly_ledger(
            household,
            scenario,
            rules,
            purchase_plans,
            car_loan,
            loan_rows,
            provident_rows,
            social_security_rows,
            calculation_context=calculation_context,
        )
    with profile_span("monthly_visualization"):
        monthly_cashflow_rows = build_monthly_cashflow_points(
            ledger_result.projection_states,
            ledger_result.ledger_entries,
            risk_by_plan=ledger_result.risk_by_plan,
        )
    purchase_plans = with_purchase_plan_recommendations(
        enrich_purchase_plans_with_projection_risk(
            purchase_plans,
            ledger_result.risk_by_plan,
            household,
        ),
        scenario,
        household,
    )
    account_snapshots = ledger_result.account_snapshots
    monthly_ledger_entries = ledger_result.ledger_entries
    with profile_span("annual_reporting"):
        annual_summaries = build_annual_financial_summaries_from_ledger(
            monthly_ledger_entries,
            account_snapshots,
            loan_rows,
            provident_rows,
            social_security_rows,
            base_date=base_month,
        )
    with profile_span("account_concepts"):
        account_concepts = build_account_concepts(calculation_context)
        core_object_groups = build_core_object_group_summaries(account_concepts)
    with profile_span("events_and_strategy_explanations"):
        strategy_explanations = build_strategy_explanations(
            purchase_plans,
            account_concepts=account_concepts,
            core_object_groups=core_object_groups,
        )
        plan_events = build_plan_events_from_context(
            household,
            scenario,
            rules,
            purchase_plans,
            monthly_cashflow_rows,
            provident_rows,
            initial_provident_balance_provider=household_initial_provident_balance,
            retirement_window_end_provider=lambda target_household, current_month: retirement_tail_months(
                target_household,
                as_of=current_month,
                rules=rules,
            ),
            vehicle_loan_states_for_plan=lambda plan: vehicle_loan_states(
                household.car_plan,
                scenario=scenario,
                home_purchase_month=plan.months_to_buy,
                rules=rules,
                calculation_context=calculation_context,
            ),
            as_of=base_month,
            calculation_context=calculation_context,
            market_snapshot=market_snapshot,
        )
    with profile_span("child_plan_strategies"):
        lifecycle_plan = next(
            (plan for plan in purchase_plans if plan.is_recommended),
            next(
                (plan for plan in purchase_plans if plan.variant == scenario.selected_purchase_plan_variant),
                purchase_plans[0] if purchase_plans else None,
            ),
        )
        child_plan_strategies = build_child_plan_strategies(
            household,
            rules,
            home_purchase_month=selected_month,
            as_of=base_month,
            calculation_context=calculation_context,
            lifecycle_cash_shortfall=lifecycle_plan.cash_shortfall if lifecycle_plan else 0.0,
            lifecycle_insolvency_month=lifecycle_plan.insolvency_month if lifecycle_plan else None,
            annual_investment_return=scenario.annual_investment_return,
        )
    return StrategyProjectionPipelineResult(
        purchase_plan_analyses=purchase_plans,
        loan_visualization=loan_rows,
        provident_visualization=provident_rows,
        social_security_visualization=social_security_rows,
        monthly_cashflow_visualization=monthly_cashflow_rows,
        monthly_visualization_details=build_monthly_visualization_details(
            monthly_cashflow_rows,
            social_security_rows,
        ),
        annual_visualization_details=build_annual_visualization_details(annual_summaries),
        account_snapshots=account_snapshots,
        monthly_ledger=monthly_ledger_entries,
        annual_financial_summaries=annual_summaries,
        account_concepts=account_concepts,
        core_object_groups=core_object_groups,
        strategy_explanations=strategy_explanations,
        plan_events=plan_events,
        child_plan_strategies=child_plan_strategies,
        selected_home_purchase_month=selected_month,
    )


def empty_strategy_projection_pipeline(
    household: HouseholdData,
    rules: RulePackData,
    *,
    base_month: date,
    calculation_context: CalculationContextSnapshot | None = None,
) -> StrategyProjectionPipelineResult:
    return StrategyProjectionPipelineResult(
        purchase_plan_analyses=[],
        child_plan_strategies=build_child_plan_strategies(
            household,
            rules,
            home_purchase_month=None,
            as_of=base_month,
            calculation_context=calculation_context,
            annual_investment_return=0.025,
        )
    )
