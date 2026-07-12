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
from .profiling import profile_span
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


def baseline_purchase_plan_analysis(
    household: HouseholdData,
    scenario: ScenarioData,
    *,
    net_monthly_income: float,
    current_monthly_expense: float,
    effective_monthly_debt_payment: float,
) -> PurchasePlanAnalysis:
    required_liquidity_reserve = max(
        0.0,
        (current_monthly_expense + effective_monthly_debt_payment) * max(0.0, household.required_liquidity_months),
    )
    baseline_cash_flow = net_monthly_income - current_monthly_expense - effective_monthly_debt_payment
    debt_to_income_ratio = (
        effective_monthly_debt_payment / net_monthly_income
        if net_monthly_income > 0
        else 0.0
    )
    cash_balance = max(0.0, household.cash_account_balance)
    return PurchasePlanAnalysis(
        variant="家庭基线",
        description="未启用购房目标时的家庭现金流、账户、贷款、政策账户和事件基线。",
        planning_goal_id="",
        source="baseline",
        months_to_buy=None,
        years_to_buy=None,
        minimum_down_payment=0.0,
        planned_down_payment=0.0,
        provident_fund_extractable=0.0,
        provident_upfront_extractable=0.0,
        family_provident_upfront_extractable=0.0,
        family_down_payment_support_amount=0.0,
        family_down_payment_support_mode="none",
        family_down_payment_support_label="",
        provident_post_transaction_extractable=0.0,
        required_cash_after_pf_extract=0.0,
        upfront_cash_required=0.0,
        commercial_loan_amount=0.0,
        provident_loan_amount=0.0,
        provident_policy_bonus=0.0,
        provident_policy_cap=0.0,
        commercial_rate=0.0,
        provident_rate=0.0,
        deed_tax_rate=0.0,
        broker_fee_rate=0.0,
        deed_tax_amount=0.0,
        broker_fee_amount=0.0,
        commercial_loan_years=0,
        provident_loan_years=0,
        provident_loan_year_limit_reasons=[],
        commercial_repayment_method=scenario.commercial_repayment_method,
        provident_repayment_method=scenario.provident_repayment_method,
        commercial_monthly_payment=0.0,
        provident_monthly_payment=0.0,
        commercial_prepayment_mode="none",
        commercial_prepayment_enabled=False,
        commercial_prepayment_start_month=1,
        commercial_prepayment_allowed_after_month=12,
        commercial_prepayment_monthly_amount=0.0,
        commercial_actual_payoff_months=0,
        commercial_interest_saved_by_prepayment=0.0,
        total_monthly_payment=0.0,
        total_interest=0.0,
        provident_contract_months=0,
        provident_interest_saving_if_equal_principal=0.0,
        provident_equal_principal_first_payment=0.0,
        provident_equal_installment_payment=0.0,
        provident_repayment_advice="未启用购房目标，当前只展示家庭基线账本，不生成房贷还款方式建议。",
        renovation_cost=0.0,
        renovation_funding_mode="after_goal_saving",
        renovation_included_in_upfront_cash=False,
        months_to_renovation=None,
        years_to_renovation=None,
        post_purchase_renovation_monthly_saving=0.0,
        investment_withdrawal_mode="auto",
        investment_withdrawal_mode_label="不触发购房变现",
        cash_account_before_purchase=cash_balance,
        investment_balance_before_purchase=max(0.0, household.investments),
        investment_sell_gross_at_purchase=0.0,
        investment_sell_proceeds_at_purchase=0.0,
        investment_balance_after_purchase=max(0.0, household.investments),
        cash_after_transaction=cash_balance,
        cash_after_purchase=cash_balance,
        provident_balance_after_extract=max(0.0, household.provident_fund_balance),
        required_liquidity_reserve=required_liquidity_reserve,
        liquidity_ok=cash_balance >= required_liquidity_reserve,
        minimum_cash_balance=cash_balance,
        minimum_cash_balance_month=0,
        cash_stress_ok=True,
        cash_stress_shortfall=0.0,
        post_purchase_cash_flow=baseline_cash_flow,
        post_purchase_pf_strategy="keep_in_account",
        post_purchase_pf_strategy_label="留存在公积金账户",
        monthly_post_purchase_pf_withdrawal=0.0,
        post_purchase_cash_flow_with_pf_withdrawal=baseline_cash_flow,
        debt_to_income_ratio=debt_to_income_ratio,
        happiness_score=scenario.happiness_score,
        recommendation_score=0,
        recommendation_reasons=["未启用购房目标时仅作为家庭财务基线，不参与房源推荐排序。"],
        is_recommended=False,
        provident_extraction_notes=["未启用购房目标，公积金账户只按缴存、租房提取、退休和校准事件推演。"],
        happiness_breakdown=[],
    )


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
    if stress_name is not None:
        return StrategyPipelineResult(
            projection=empty_strategy_projection_pipeline(
                household,
                rules,
                base_month=base_month,
                calculation_context=calculation_context,
            )
        )
    if not purchase_cash_context.has_purchase_target:
        baseline_plan = baseline_purchase_plan_analysis(
            household,
            scenario,
            net_monthly_income=household_context.net_monthly_income,
            current_monthly_expense=household_context.current_monthly_expense,
            effective_monthly_debt_payment=household_context.effective_monthly_debt_payment,
        )
        with profile_span("projection_pipeline"):
            projection = build_strategy_projection_pipeline(
                household,
                scenario,
                rules,
                [baseline_plan],
                vehicle_context.car_loan,
                base_monthly_debt_payment=household_context.household.monthly_debt_payment,
                base_month=base_month,
                vehicle_states=vehicle_context.vehicle_states,
                calculation_context=calculation_context,
                market_snapshot=market_snapshot,
            )
        return StrategyPipelineResult(
            purchase_plan_analyses=projection.purchase_plan_analyses,
            projection=projection,
        )

    with profile_span("purchase_strategy_generation"):
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
    with profile_span("yield_sensitivity"):
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
                    baseline_analyses=purchase_plans,
                    calculation_context=calculation_context,
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
                baseline_analyses=purchase_plans,
                calculation_context=calculation_context,
            )
    with profile_span("projection_pipeline"):
        projection = build_strategy_projection_pipeline(
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
        )
    return StrategyPipelineResult(
        purchase_plan_analyses=projection.purchase_plan_analyses,
        yield_sensitivity=yield_sensitivity,
        projection=projection,
    )
