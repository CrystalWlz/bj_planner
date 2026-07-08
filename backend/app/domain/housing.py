from __future__ import annotations

from math import ceil

from ..policies import get_policy
from ..schemas import HouseholdData, RulePackData, ScenarioData
from .loans import loan_principal_for_payment_cap
from .tax import clamp


def minimum_down_payment_ratio(household: HouseholdData, uses_provident_loan: bool, rules: RulePackData) -> float:
    return get_policy(rules).minimum_down_payment_ratio(household, uses_provident_loan=uses_provident_loan)


def provident_policy_bonus(scenario: ScenarioData, rules: RulePackData) -> float:
    return get_policy(rules).provident_policy_bonus(scenario)


def provident_loan_rate(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    loan_years: int,
) -> float:
    return get_policy(rules).provident_loan_rate(household, scenario, loan_years)


def deed_tax_rate(household: HouseholdData, scenario: ScenarioData, rules: RulePackData) -> float:
    return get_policy(rules).deed_tax_rate(household, scenario)


def broker_fee_rate(scenario: ScenarioData, rules: RulePackData) -> float:
    return clamp(
        float(getattr(scenario, "broker_fee_rate", rules.params.get("default_broker_fee_rate", 0.022))),
        0.0,
        0.2,
    )


def housing_transaction_rate_amounts(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
) -> tuple[float, float, float, float]:
    deed_rate = deed_tax_rate(household, scenario, rules)
    broker_rate = broker_fee_rate(scenario, rules)
    return deed_rate, broker_rate, scenario.total_price * deed_rate, scenario.total_price * broker_rate


def seller_tax_pass_through_amount(scenario: ScenarioData) -> float:
    if not scenario.seller_tax_pass_through_enabled:
        return 0.0
    configured = max(0.0, scenario.seller_tax_pass_through_amount)
    if configured > 0:
        return configured
    return max(0.0, scenario.total_price * scenario.seller_tax_pass_through_rate)


def is_second_hand_property(scenario: ScenarioData) -> bool:
    return "二手" in scenario.property_type


def is_new_home_property(scenario: ScenarioData) -> bool:
    return "新房" in scenario.property_type


def provident_loan_years(household: HouseholdData, scenario: ScenarioData, rules: RulePackData) -> tuple[int, list[str]]:
    return get_policy(rules).provident_loan_years(household, scenario)


def provident_repayment_method(scenario: ScenarioData) -> str:
    return scenario.provident_repayment_method or scenario.repayment_method


def provident_loan_cap(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    purchase_months: int = 0,
    monthly_income_for_capacity: float = 0.0,
    borrower_count: int = 1,
) -> tuple[float, float]:
    amount_per_year = float(rules.params.get("provident_loan_amount_per_deposit_year", 150_000))
    effective_deposit_months = household.social_security_months + max(0, purchase_months)
    deposit_years = ceil(effective_deposit_months / 12) if effective_deposit_months > 0 else 0
    policy_year_cap = amount_per_year * deposit_years
    if household.existing_home_count == 0:
        base_maximum_cap = float(rules.params.get("provident_first_home_loan_cap", 1_200_000))
    else:
        base_maximum_cap = float(rules.params.get("provident_second_home_loan_cap", 1_000_000))
    bonus = provident_policy_bonus(scenario, rules)
    cap = min(base_maximum_cap + bonus, policy_year_cap + bonus)
    if bool(rules.params.get("provident_repayment_capacity_enabled", True)) and monthly_income_for_capacity > 0:
        income_ratio = clamp(float(rules.params.get("provident_repayment_income_ratio", 0.60)), 0.0, 1.0)
        basic_living_cost = max(0.0, float(rules.params.get("provident_basic_living_cost_per_person", 1778)))
        family_living_floor = basic_living_cost * max(1, borrower_count)
        payment_cap = min(
            monthly_income_for_capacity * income_ratio,
            max(0.0, monthly_income_for_capacity - family_living_floor),
        )
        policy_loan_years = provident_loan_years(household, scenario, rules)[0]
        capacity_cap = loan_principal_for_payment_cap(
            payment_cap,
            provident_loan_rate(household, scenario, rules, policy_loan_years),
            policy_loan_years,
            provident_repayment_method(scenario),
        )
        cap = min(cap, capacity_cap)
    return cap, bonus
