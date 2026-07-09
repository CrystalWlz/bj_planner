from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

from .calculation_context import PreparedHouseholdContext, PurchaseCashContext, VehiclePlanningContext
from .planning_pipeline import (
    StrategyProjectionPipelineResult,
    build_strategy_projection_pipeline,
    empty_strategy_projection_pipeline,
)
from .purchase_facade import (
    build_purchase_plan_analyses,
    build_yield_sensitivity,
)
from .schemas import (
    CalculationContextSnapshot,
    HouseholdData,
    MarketSnapshotData,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    YieldSensitivityPoint,
)


@dataclass
class StrategyPipelineResult:
    purchase_plan_analyses: list[PurchasePlanAnalysis] = field(default_factory=list)
    yield_sensitivity: list[YieldSensitivityPoint] = field(default_factory=list)
    projection: StrategyProjectionPipelineResult = field(default_factory=StrategyProjectionPipelineResult)


def run_strategy_pipeline(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    household_context: PreparedHouseholdContext,
    vehicle_context: VehiclePlanningContext,
    purchase_cash_context: PurchaseCashContext,
    base_month: date,
    stress_name: str | None,
    parallel_workers: int,
    calculation_context: CalculationContextSnapshot | None = None,
    market_snapshot: MarketSnapshotData | None = None,
) -> StrategyPipelineResult:
    if stress_name is not None or not purchase_cash_context.has_purchase_target:
        return StrategyPipelineResult(
            projection=empty_strategy_projection_pipeline(
                household,
                rules,
                base_month=base_month,
                calculation_context=calculation_context,
            )
        )

    purchase_plans = build_purchase_plan_analyses(
        household,
        scenario,
        rules,
        tax_summaries=household_context.tax_summaries,
        net_monthly_income=household_context.net_monthly_income,
        car_loan=vehicle_context.purchase_strategy_car_loan,
        taxes_and_fees=purchase_cash_context.taxes_and_fees,
        calculation_context=calculation_context,
        market_snapshot=market_snapshot,
    )
    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=min(2, parallel_workers)) as executor:
            yield_future = executor.submit(
                build_yield_sensitivity,
                household,
                scenario,
                rules,
                tax_summaries=household_context.tax_summaries,
                net_monthly_income=household_context.net_monthly_income,
                car_loan=vehicle_context.purchase_strategy_car_loan,
                taxes_and_fees=purchase_cash_context.taxes_and_fees,
                parallel_workers=max(1, parallel_workers - 1),
                market_snapshot=market_snapshot,
            )
            yield_sensitivity = yield_future.result()
    else:
        yield_sensitivity = build_yield_sensitivity(
            household,
            scenario,
            rules,
            tax_summaries=household_context.tax_summaries,
            net_monthly_income=household_context.net_monthly_income,
            car_loan=vehicle_context.purchase_strategy_car_loan,
        taxes_and_fees=purchase_cash_context.taxes_and_fees,
        parallel_workers=1,
        market_snapshot=market_snapshot,
    )
    return StrategyPipelineResult(
        purchase_plan_analyses=purchase_plans,
        yield_sensitivity=yield_sensitivity,
        projection=build_strategy_projection_pipeline(
            household,
            scenario,
            rules,
            purchase_plans,
            vehicle_context.car_loan,
            base_monthly_debt_payment=household_context.household.monthly_debt_payment,
            base_month=base_month,
            vehicle_states=vehicle_context.vehicle_states,
            calculation_context=calculation_context,
            market_snapshot=market_snapshot,
        ),
    )
