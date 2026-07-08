from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from ..schemas import (
    CarLoanSummary,
    HouseholdData,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
    TaxMemberSummary,
    YieldSensitivityPoint,
)


PurchasePlanBuilder = Callable[..., list[PurchasePlanAnalysis]]


def build_yield_sensitivity(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    tax_summaries: list[TaxMemberSummary],
    net_monthly_income: float,
    car_loan: CarLoanSummary,
    taxes_and_fees: float,
    purchase_plan_builder: PurchasePlanBuilder,
    parallel_workers: int = 1,
) -> list[YieldSensitivityPoint]:
    annual_returns = [0.015, 0.025, 0.035]

    def point_for_return(annual_return: float) -> YieldSensitivityPoint:
        adjusted = scenario.model_copy(update={"annual_investment_return": annual_return})
        analyses = purchase_plan_builder(
            household,
            adjusted,
            rules,
            tax_summaries=tax_summaries,
            net_monthly_income=net_monthly_income,
            car_loan=car_loan,
            taxes_and_fees=taxes_and_fees,
        )
        fastest = min(
            analyses,
            key=lambda item: item.months_to_buy if item.months_to_buy is not None else 999999,
        )
        return YieldSensitivityPoint(
            annual_return=annual_return,
            months_to_buy=fastest.months_to_buy,
            years_to_buy=fastest.years_to_buy,
            cash_after_purchase=fastest.cash_after_purchase,
        )

    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            return list(executor.map(point_for_return, annual_returns))
    return [point_for_return(annual_return) for annual_return in annual_returns]
