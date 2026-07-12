from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from ..domain.housing import commercial_loan_rate
from ..policies import get_policy
from ..schemas import HouseholdData, MarketSnapshotData, RulePackData, ScenarioData, StressResult


class StressCalculationResultLike(Protocol):
    status: str
    monthly_payment: float
    post_purchase_cash_flow: float
    debt_to_income_ratio: float
    emergency_months: float
    purchase_plan_analyses: list


AffordabilityCalculator = Callable[[HouseholdData, ScenarioData, RulePackData, str], StressCalculationResultLike]


def build_stress_tests(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    affordability_calculator: AffordabilityCalculator,
    parallel_workers: int = 1,
    market_snapshot: MarketSnapshotData | None = None,
) -> list[StressResult]:
    policy = get_policy(rules)
    stress_policy = policy.stress_test_policy()
    rate_add = stress_policy.rate_add
    income_factor = stress_policy.income_factor
    price_factor = stress_policy.price_factor
    rate_rules = policy.stressed_interest_rate_rules(rate_add)
    rate_scenario = scenario.model_copy(update={"commercial_rate": commercial_loan_rate(scenario, market_snapshot) + rate_add})
    income_household = household.model_copy(update={"monthly_income": household.monthly_income * income_factor})
    if household.members:
        income_household = income_household.model_copy(
            update={
                "members": [
                    member.model_copy(
                        update={
                            "monthly_salary_gross": member.monthly_salary_gross * income_factor,
                            "income_stages": [
                                stage.model_copy(
                                    update={
                                        "monthly_salary_gross": stage.monthly_salary_gross * income_factor,
                                        "monthly_freelance_income": stage.monthly_freelance_income * income_factor,
                                        "other_annual_taxable_income": stage.other_annual_taxable_income * income_factor,
                                    }
                                )
                                for stage in member.income_stages
                            ],
                        }
                    )
                    for member in household.members
                ]
            }
        )
    price_scenario = scenario.model_copy(
        update={
            "total_price": scenario.total_price * price_factor,
            "down_payment_amount": scenario.down_payment_amount * price_factor,
            "commercial_loan_amount": scenario.commercial_loan_amount * price_factor,
            "provident_loan_amount": scenario.provident_loan_amount * price_factor,
        }
    )
    combined_rules = policy.combined_stress_rules(
        rate_add,
        stress_policy.property_annual_price_growth_rate,
    )
    combined_scenario = price_scenario.model_copy(
        update={
            "commercial_rate": commercial_loan_rate(scenario, market_snapshot) + rate_add,
            "annual_investment_return": max(0.0, scenario.annual_investment_return)
            * stress_policy.investment_return_factor,
        }
    )

    cases = [
        ("利率上行", household, rate_scenario, rate_rules),
        ("收入下降", income_household, scenario, rules),
        ("房价上行", household, price_scenario, rules),
        ("联合压力（收入、利率、房价、理财）", income_household, combined_scenario, combined_rules),
    ]

    def run_case(case: tuple[str, HouseholdData, ScenarioData, RulePackData]) -> StressResult:
        name, stress_household, stress_scenario, stress_rules = case
        result = affordability_calculator(stress_household, stress_scenario, stress_rules, name)
        recommended = next((plan for plan in result.purchase_plan_analyses if plan.is_recommended), None)
        candidates = [plan for plan in result.purchase_plan_analyses if plan.source != "baseline"]
        representative = recommended or min(
            candidates,
            key=lambda plan: (
                max(0.0, plan.cash_shortfall),
                0 if plan.insolvency_month is None else 1,
                0 if plan.liquid_assets_exhausted_month is None else 1,
                -plan.worst_cash_balance,
                plan.months_to_buy if plan.months_to_buy is not None else 10**9,
            ),
            default=None,
        )
        feasible = recommended is not None
        reason = (
            "压力情景下仍有方案通过现金安全与长期偿付能力门槛。"
            if feasible
            else "压力情景下无任何购房方案通过现金安全与长期偿付能力门槛。"
        )
        return StressResult(
            name=name,
            status=result.status,
            monthly_payment=result.monthly_payment,
            post_purchase_cash_flow=result.post_purchase_cash_flow,
            debt_to_income_ratio=result.debt_to_income_ratio,
            emergency_months=result.emergency_months,
            feasible=feasible,
            reason=reason,
            cash_shortfall=representative.cash_shortfall if representative else 0.0,
            worst_cash_balance=representative.worst_cash_balance if representative else 0.0,
            insolvency_month=representative.insolvency_month if representative else None,
            liquid_assets_exhausted_month=representative.liquid_assets_exhausted_month if representative else None,
        )

    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            return list(executor.map(run_case, cases))
    return [run_case(case) for case in cases]
