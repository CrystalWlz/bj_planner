from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .reporting import build_export_sheets, build_export_texts
from .schemas import (
    AccountConceptSummary,
    AccountSnapshotPoint,
    AffordabilityResult,
    AnnualFinancialSummary,
    AnnualVisualizationDetail,
    CarLoanSummary,
    CarPlanAnalysis,
    CareerShockProjection,
    ChildPlanStrategyPoint,
    CalculationContextSnapshot,
    CoreObjectGroupSummary,
    InvestmentAllocationSummary,
    InvestmentPlanRecommendation,
    PortfolioStrategyRecommendation,
    LoanSummary,
    LoanVisualizationPoint,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    MonthlyVisualizationDetail,
    PhasedLoanSummary,
    PlanEventPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    ScenarioData,
    SocialSecurityVisualizationPoint,
    StrategyExplanationPoint,
    TaxEventPoint,
    TaxMemberSummary,
    TaxMonthlyPoint,
    TaxStrategyItem,
    TaxStrategyTimelinePoint,
    TaxVisualizationDetail,
    TaxYearSummary,
    YieldSensitivityPoint,
)


@dataclass(frozen=True)
class AffordabilityResultInputs:
    status: str
    status_reason: str
    immediate_purchase_status: str
    immediate_purchase_reason: str
    recommended_plan_status: str
    recommended_plan_reason: str
    eligible: bool
    eligibility_notes: list[str]
    total_required_cash: float
    minimum_down_payment: float
    stated_down_payment: float
    taxes_and_fees: float
    funding_gap: float
    remaining_cash: float
    gross_monthly_income: float
    net_monthly_income: float
    annual_income_tax: float
    phased_loan_monthly_payment: float
    effective_monthly_debt_payment: float
    phased_loan_summaries: list[PhasedLoanSummary]
    car_loan: CarLoanSummary
    car_plan_analyses: list[CarPlanAnalysis]
    monthly_payment: float
    post_purchase_cash_flow: float
    debt_to_income_ratio: float
    emergency_months: float
    commercial_loan: LoanSummary | None
    provident_loan: LoanSummary | None
    tax_summaries: list[TaxMemberSummary]
    tax_year_summaries: list[TaxYearSummary]
    tax_monthly_points: list[TaxMonthlyPoint]
    tax_visualization_details: list[TaxVisualizationDetail]
    tax_events: list[TaxEventPoint]
    tax_strategy_items: list[TaxStrategyItem]
    tax_strategy_timeline: list[TaxStrategyTimelinePoint]
    career_shock_projection: CareerShockProjection | None
    investment_plan_recommendations: list[InvestmentPlanRecommendation]
    portfolio_strategy_recommendations: list[PortfolioStrategyRecommendation]
    current_investment_allocation: InvestmentAllocationSummary | None
    child_plan_strategies: list[ChildPlanStrategyPoint]
    annual_financial_summaries: list[AnnualFinancialSummary]
    purchase_plan_analyses: list[PurchasePlanAnalysis]
    yield_sensitivity: list[YieldSensitivityPoint]
    monthly_cashflow_visualization: list[MonthlyCashflowPoint]
    monthly_visualization_details: list[MonthlyVisualizationDetail]
    annual_visualization_details: list[AnnualVisualizationDetail]
    account_snapshots: list[AccountSnapshotPoint]
    monthly_ledger: list[MonthlyLedgerEntry]
    loan_visualization: list[LoanVisualizationPoint]
    provident_visualization: list[ProvidentVisualizationPoint]
    social_security_visualization: list[SocialSecurityVisualizationPoint]
    account_concepts: list[AccountConceptSummary]
    core_object_groups: list[CoreObjectGroupSummary]
    strategy_explanations: list[StrategyExplanationPoint]
    plan_events: list[PlanEventPoint]
    property_goal_assumption: str
    property_terminal_value_assumption: str
    provident_year_reasons: list[str]
    scenario: ScenarioData
    base_month: date
    calculation_context: CalculationContextSnapshot | None = None


def affordability_assumptions(
    *,
    property_goal_assumption: str,
    property_terminal_value_assumption: str,
    provident_year_reasons: list[str],
) -> list[str]:
    assumptions = [
        "测算结果仅用于家庭规划，不构成购房、税务、法律或银行审批意见。",
        "政策、税费、贷款额度和利率以规则包和用户手动录入为准。",
    ]
    if property_goal_assumption:
        assumptions.append(property_goal_assumption)
    if property_terminal_value_assumption:
        assumptions.append(property_terminal_value_assumption)
    assumptions.extend(
        [
            "北京公积金贷款额度按当前规则包的每缴存年额度估算；夫妻分别缴存时，现阶段用家庭录入的社保/个税月数近似代表较长缴存年限。",
            f"北京公积金贷款期限按设定年限、30 年上限、借款人年龄和二手房房龄/土地剩余年限取短；当前测算：{'；'.join(provident_year_reasons)}。",
            "公积金提取区分交易前现金、交易后购房提取和购后账户留存：默认不把买房后的月缴存公积金计入自由现金流。",
            "已有贷款在只还利息阶段按本金乘年利率除以 12 计入有效月债务，到期后按剩余期数转为等额本息或等额本金估算。",
            "等额本金场景使用首月月供评估现金流压力。",
            "工资薪金和全年一次性奖金按规则包税率表估算，未覆盖劳务报酬、经营所得等复杂申报情形。",
            "家庭支出按基础月支出叠加定时月支出测算；不符合税收养老条件的家庭支持支出只进入现金流，不进入个税专项附加扣除。",
        ]
    )
    return assumptions


def build_affordability_result(inputs: AffordabilityResultInputs) -> AffordabilityResult:
    result = AffordabilityResult(
        calculation_context=inputs.calculation_context,
        status=inputs.status,
        status_reason=inputs.status_reason,
        immediate_purchase_status=inputs.immediate_purchase_status,
        immediate_purchase_reason=inputs.immediate_purchase_reason,
        recommended_plan_status=inputs.recommended_plan_status,
        recommended_plan_reason=inputs.recommended_plan_reason,
        eligible=inputs.eligible,
        eligibility_notes=inputs.eligibility_notes,
        total_required_cash=round(inputs.total_required_cash, 2),
        minimum_down_payment=round(inputs.minimum_down_payment, 2),
        stated_down_payment=round(inputs.stated_down_payment, 2),
        taxes_and_fees=round(inputs.taxes_and_fees, 2),
        funding_gap=round(inputs.funding_gap, 2),
        remaining_cash_after_purchase=round(inputs.remaining_cash, 2),
        household_gross_monthly_income=round(inputs.gross_monthly_income, 2),
        household_net_monthly_income=round(inputs.net_monthly_income, 2),
        annual_income_tax=round(inputs.annual_income_tax, 2),
        phased_loan_monthly_payment=round(inputs.phased_loan_monthly_payment, 2),
        effective_monthly_debt_payment=round(inputs.effective_monthly_debt_payment, 2),
        phased_loan_summaries=inputs.phased_loan_summaries,
        car_loan=inputs.car_loan,
        car_plan_analyses=inputs.car_plan_analyses,
        monthly_payment=round(inputs.monthly_payment, 2),
        post_purchase_cash_flow=round(inputs.post_purchase_cash_flow, 2),
        debt_to_income_ratio=round(inputs.debt_to_income_ratio, 4),
        emergency_months=round(inputs.emergency_months, 2),
        commercial_loan=inputs.commercial_loan,
        provident_loan=inputs.provident_loan,
        tax_summaries=inputs.tax_summaries,
        tax_year_summaries=inputs.tax_year_summaries,
        tax_monthly_points=inputs.tax_monthly_points,
        tax_visualization_details=inputs.tax_visualization_details,
        tax_events=inputs.tax_events,
        tax_strategy_items=inputs.tax_strategy_items,
        tax_strategy_timeline=inputs.tax_strategy_timeline,
        career_shock_projection=inputs.career_shock_projection,
        investment_plan_recommendations=inputs.investment_plan_recommendations,
        portfolio_strategy_recommendations=inputs.portfolio_strategy_recommendations,
        current_investment_allocation=inputs.current_investment_allocation,
        child_plan_strategies=inputs.child_plan_strategies,
        annual_financial_summaries=inputs.annual_financial_summaries,
        purchase_plan_analyses=inputs.purchase_plan_analyses,
        yield_sensitivity=inputs.yield_sensitivity,
        monthly_cashflow_visualization=inputs.monthly_cashflow_visualization,
        monthly_visualization_details=inputs.monthly_visualization_details,
        annual_visualization_details=inputs.annual_visualization_details,
        account_snapshots=inputs.account_snapshots,
        monthly_ledger=inputs.monthly_ledger,
        loan_visualization=inputs.loan_visualization,
        provident_visualization=inputs.provident_visualization,
        social_security_visualization=inputs.social_security_visualization,
        account_concepts=inputs.account_concepts,
        core_object_groups=inputs.core_object_groups,
        strategy_explanations=inputs.strategy_explanations,
        plan_events=inputs.plan_events,
        stress_tests=[],
        assumptions=affordability_assumptions(
            property_goal_assumption=inputs.property_goal_assumption,
            property_terminal_value_assumption=inputs.property_terminal_value_assumption,
            provident_year_reasons=inputs.provident_year_reasons,
        ),
    )
    result.export_sheets = build_export_sheets(result, inputs.scenario, base_date=inputs.base_month)
    result.export_texts = build_export_texts(result, inputs.scenario, base_date=inputs.base_month)
    return result
