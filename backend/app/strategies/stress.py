from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from ..schemas import HouseholdData, RulePackData, ScenarioData, StressResult


class StressCalculationResultLike(Protocol):
    status: str
    monthly_payment: float
    post_purchase_cash_flow: float
    debt_to_income_ratio: float
    emergency_months: float


AffordabilityCalculator = Callable[[HouseholdData, ScenarioData, RulePackData, str], StressCalculationResultLike]


def build_stress_tests(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    affordability_calculator: AffordabilityCalculator,
    parallel_workers: int = 1,
) -> list[StressResult]:
    params = rules.params
    rate_add = float(params.get("rate_stress_add", 0.005))
    income_factor = float(params.get("income_stress_factor", 0.90))
    price_factor = float(params.get("price_stress_factor", 1.05))

    provident_rate_keys = (
        "provident_first_home_rate_1_to_5_years",
        "provident_first_home_rate_6_to_30_years",
        "provident_second_home_rate_1_to_5_years",
        "provident_second_home_rate_6_to_30_years",
    )
    stressed_rate_params = dict(rules.params)
    default_params = RulePackData().params
    for key in provident_rate_keys:
        stressed_rate_params[key] = float(stressed_rate_params.get(key, default_params.get(key, 0.0))) + rate_add
    rate_rules = rules.model_copy(update={"params": stressed_rate_params})
    rate_scenario = scenario.model_copy(update={"commercial_rate": scenario.commercial_rate + rate_add})
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
                                        "annual_bonus": stage.annual_bonus * income_factor,
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

    cases = [
        ("利率上行", household, rate_scenario, rate_rules),
        ("收入下降", income_household, scenario, rules),
        ("房价上行", household, price_scenario, rules),
    ]

    def run_case(case: tuple[str, HouseholdData, ScenarioData, RulePackData]) -> StressResult:
        name, stress_household, stress_scenario, stress_rules = case
        result = affordability_calculator(stress_household, stress_scenario, stress_rules, name)
        return StressResult(
            name=name,
            status=result.status,
            monthly_payment=result.monthly_payment,
            post_purchase_cash_flow=result.post_purchase_cash_flow,
            debt_to_income_ratio=result.debt_to_income_ratio,
            emergency_months=result.emergency_months,
        )

    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            return list(executor.map(run_case, cases))
    return [run_case(case) for case in cases]
