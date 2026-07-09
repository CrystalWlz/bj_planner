from __future__ import annotations

from ..policies import get_policy
from ..schemas import HouseholdData, MarketSnapshotData, RulePackData, ScenarioData
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


def _is_default_or_blank(value: object, default_value: float) -> bool:
    if value is None:
        return True
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return True
    return numeric <= 0 or abs(numeric - default_value) < 1e-12


def commercial_loan_rate(scenario: ScenarioData, market_snapshot: MarketSnapshotData | None = None) -> float:
    default_rate = float(ScenarioData.model_fields["commercial_rate"].default or 0.035)
    configured = getattr(scenario, "commercial_rate", None)
    if market_snapshot and market_snapshot.commercial_loan_rate is not None and _is_default_or_blank(configured, default_rate):
        return clamp(float(market_snapshot.commercial_loan_rate), 0.0, 0.2)
    return clamp(float(configured if configured is not None else default_rate), 0.0, 0.2)


def broker_fee_rate(
    scenario: ScenarioData,
    rules: RulePackData,
    market_snapshot: MarketSnapshotData | None = None,
) -> float:
    configured = getattr(scenario, "broker_fee_rate", None)
    default_rate = float(ScenarioData.model_fields["broker_fee_rate"].default or 0.022)
    if market_snapshot and market_snapshot.default_broker_fee_rate is not None and _is_default_or_blank(configured, default_rate):
        configured = market_snapshot.default_broker_fee_rate
    elif _is_default_or_blank(configured, default_rate):
        configured = get_policy(rules).default_broker_fee_rate()
    return clamp(
        float(configured),
        0.0,
        0.2,
    )


def housing_transaction_rate_amounts(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    market_snapshot: MarketSnapshotData | None = None,
) -> tuple[float, float, float, float]:
    deed_rate = deed_tax_rate(household, scenario, rules)
    broker_rate = broker_fee_rate(scenario, rules, market_snapshot)
    return deed_rate, broker_rate, scenario.total_price * deed_rate, scenario.total_price * broker_rate


def seller_tax_pass_through_amount(
    scenario: ScenarioData,
    rules: RulePackData,
    market_snapshot: MarketSnapshotData | None = None,
) -> float:
    if not scenario.seller_tax_pass_through_enabled:
        return 0.0
    configured = max(0.0, scenario.seller_tax_pass_through_amount)
    if configured > 0:
        return configured
    rate = scenario.seller_tax_pass_through_rate
    if rate <= 0 and market_snapshot and market_snapshot.seller_tax_pass_through_rate is not None:
        rate = market_snapshot.seller_tax_pass_through_rate
    if rate <= 0:
        rate = get_policy(rules).seller_tax_pass_through_default_rate()
    return max(0.0, scenario.total_price * clamp(float(rate), 0.0, 0.2))


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
    policy = get_policy(rules)
    cap, bonus = policy.provident_loan_policy_cap(household, scenario, purchase_months=purchase_months)
    payment_cap = policy.provident_repayment_capacity_payment_cap(
        monthly_income=monthly_income_for_capacity,
        borrower_count=borrower_count,
    )
    if payment_cap is not None:
        policy_loan_years = provident_loan_years(household, scenario, rules)[0]
        capacity_cap = loan_principal_for_payment_cap(
            payment_cap,
            provident_loan_rate(household, scenario, rules, policy_loan_years),
            policy_loan_years,
            provident_repayment_method(scenario),
        )
        cap = min(cap, capacity_cap)
    return cap, bonus
