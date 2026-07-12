from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Protocol

from .domain.time import add_months, month_distance, parse_iso_date, parse_year_month
from .schemas import CarPlanData, HouseholdData, IncomeMember, RulePackData, ScenarioData, VehicleIndicatorApplicantData


DEFAULT_COMPREHENSIVE_TAX_BRACKETS = [
    {"threshold": 36000, "rate": 0.03, "quick_deduction": 0},
    {"threshold": 144000, "rate": 0.10, "quick_deduction": 2520},
    {"threshold": 300000, "rate": 0.20, "quick_deduction": 16920},
    {"threshold": 420000, "rate": 0.25, "quick_deduction": 31920},
    {"threshold": 660000, "rate": 0.30, "quick_deduction": 52920},
    {"threshold": 960000, "rate": 0.35, "quick_deduction": 85920},
    {"threshold": 999999999, "rate": 0.45, "quick_deduction": 181920},
]

DEFAULT_MONTHLY_CONVERTED_BONUS_TAX_BRACKETS = [
    {"threshold": 3000, "rate": 0.03, "quick_deduction": 0},
    {"threshold": 12000, "rate": 0.10, "quick_deduction": 210},
    {"threshold": 25000, "rate": 0.20, "quick_deduction": 1410},
    {"threshold": 35000, "rate": 0.25, "quick_deduction": 2660},
    {"threshold": 55000, "rate": 0.30, "quick_deduction": 4410},
    {"threshold": 80000, "rate": 0.35, "quick_deduction": 7160},
    {"threshold": 999999999, "rate": 0.45, "quick_deduction": 15160},
]


DEFAULT_PURCHASE_HAPPINESS_WEIGHTS = {
    "living_quality": 0.10,
    "commute": 0.08,
    "education": 0.07,
    "vehicle_convenience": 0.04,
    "vehicle_home_tradeoff": 0.04,
    "transaction_liquidity": 0.09,
    "post_purchase_liquidity": 0.08,
    "investment_continuity": 0.05,
    "monthly_cashflow": 0.12,
    "debt_to_income": 0.08,
    "monthly_payment_pressure": 0.08,
    "loan_interest_pressure": 0.06,
    "cash_shortfall": 0.06,
    "waiting_time": 0.04,
    "renovation_readiness": 0.04,
    "stress_resilience": 0.07,
}


@dataclass(frozen=True)
class BeijingFamilyIndicatorProjection:
    score: float
    annual_gain: float
    generation_multiplier: int
    wait_months: int | None
    notes: list[str]


@dataclass(frozen=True)
class PensionEstimatePolicy:
    social_base_floor: float
    social_base_ceiling: float
    flexible_employment_social_base: float
    reference_average_salary: float
    average_salary_growth_rate: float
    default_paid_years: float
    employee_pension_rate: float
    flexible_employment_pension_rate: float
    personal_account_annual_return: float
    personal_account_months: float
    replacement_rate_floor: float
    replacement_rate_ceiling: float


@dataclass(frozen=True)
class PayrollContributionPolicy:
    social_base_floor: float
    social_base_ceiling: float
    housing_fund_base_floor: float
    housing_fund_base_ceiling: float
    housing_fund_rate_floor: float
    housing_fund_rate_ceiling: float
    employee_pension_rate: float
    employee_medical_rate: float
    employee_medical_fixed: float
    employee_unemployment_rate: float
    employer_pension_rate: float
    employer_medical_maternity_rate: float
    employer_unemployment_rate: float
    employer_work_injury_rate: float


@dataclass(frozen=True)
class SocialSecurityAccountPolicy:
    pension_account_annual_return: float
    pension_account_interest_credit_month: int
    pension_account_annual_credit_rates: dict
    medical_account_annual_interest_rate: float
    medical_account_interest_credit_months: set[int]
    medical_account_employee_transfer_rate: float
    medical_account_retiree_monthly_transfer_under_70: float
    medical_account_retiree_monthly_transfer_70_plus: float
    medical_account_retiree_large_mutual_aid_monthly: float
    pension_account_months: int
    pension_account_months_by_retirement_category: dict

    def pension_account_months_for_category(self, category: str) -> int:
        default_by_category = {
            "female_50": 195,
            "female_55": 170,
            "male_60": 139,
        }
        configured = self.pension_account_months_by_retirement_category
        if isinstance(configured, dict):
            value = configured.get(category)
            if value is not None:
                try:
                    return max(1, int(value))
                except (TypeError, ValueError):
                    pass
        if category in default_by_category:
            return default_by_category[category]
        return max(1, int(self.pension_account_months))

    def pension_credit_rate_for_year(self, year: int) -> float:
        return _yearly_policy_rate(
            self.pension_account_annual_credit_rates,
            year,
            self.pension_account_annual_return,
        )

    def medical_credit_rate_for_year(self, year: int) -> float:
        return max(0.0, self.medical_account_annual_interest_rate)


@dataclass(frozen=True)
class TaxCalculationPolicy:
    comprehensive_brackets: list[dict]
    monthly_converted_bonus_brackets: list[dict]
    personal_standard_deduction_annual: float
    annual_bonus_policy_periods: list[dict]
    annual_bonus_separate_tax_default_continues: bool
    annual_bonus_separate_tax_valid_until: date

    def annual_bonus_separate_tax_available(self, target_year: int) -> bool:
        for period in self.annual_bonus_policy_periods:
            if not isinstance(period, dict):
                continue
            start = parse_iso_date(str(period.get("effective_from") or ""), date(1900, 1, 1))
            end = parse_iso_date(str(period.get("effective_to") or ""), date(9999, 12, 31))
            if start.year <= target_year <= end.year:
                return bool(period.get("separate_tax_enabled", True))
        if self.annual_bonus_separate_tax_default_continues:
            return True
        return target_year <= self.annual_bonus_separate_tax_valid_until.year


@dataclass(frozen=True)
class TaxBenefitPolicy:
    housing_rent_monthly: float
    first_home_mortgage_interest_monthly: float
    first_home_mortgage_interest_max_months: int
    child_education_monthly: float
    infant_care_monthly: float
    serious_illness_medical_threshold: float
    serious_illness_medical_cap: float
    personal_pension_deduction_annual_cap: float
    personal_pension_withdrawal_tax_rate: float
    rent_and_mortgage_mutually_exclusive: bool
    annual_tax_settlement_month: int


@dataclass(frozen=True)
class HomePurchaseEligibilityPolicy:
    required_social_security_months: int
    max_home_count: int


@dataclass(frozen=True)
class AffordabilityRiskPolicy:
    recommended_emergency_months: float
    caution_dti: float
    danger_dti: float


@dataclass(frozen=True)
class ProvidentPostPurchasePolicy:
    cashflow_enabled: bool
    monthly_withdrawal_enabled: bool
    strategy_mode: str
    withdrawal_mode: str


@dataclass(frozen=True)
class HomeStrategyPolicy:
    micro_commercial_loan_ratio: float
    micro_commercial_loan_ratio_min: float
    micro_commercial_loan_ratio_max: float
    default_auto_search_horizon_months: int


@dataclass(frozen=True)
class ChildPlanningPolicy:
    birth_after_home_delay_months: int
    advanced_maternal_age: float
    happiness_weights: dict[str, float]


@dataclass(frozen=True)
class StressTestPolicy:
    rate_add: float
    income_factor: float
    price_factor: float
    investment_return_factor: float
    property_annual_price_growth_rate: float


@dataclass(frozen=True)
class PropertyTerminalValuePolicy:
    """Long-horizon property value assumptions used for comparable net worth.

    The value is intentionally a net realisable value, rather than a headline
    listing price.  This keeps a self-occupied home from being treated as
    instantly liquid when strategies are compared on terminal net worth.
    """

    annual_price_growth_rate: float
    sale_cost_rate: float
    liquidity_discount_rate: float


@dataclass(frozen=True)
class PersonalPensionReturnPolicy:
    pre_retirement_annual_return: float
    post_retirement_annual_return: float
    snapshot_date: str
    source_count: int


class RegionalPolicy(Protocol):
    code: str

    def minimum_down_payment_ratio(self, household: HouseholdData, *, uses_provident_loan: bool) -> float:
        ...

    def home_strategy_policy(self) -> HomeStrategyPolicy:
        ...

    def affordability_risk_policy(self) -> AffordabilityRiskPolicy:
        ...

    def stress_test_policy(self) -> StressTestPolicy:
        ...

    def property_terminal_value_policy(self) -> PropertyTerminalValuePolicy:
        ...

    def personal_pension_return_policy(self) -> PersonalPensionReturnPolicy:
        ...

    def stressed_interest_rate_rules(self, rate_add: float) -> RulePackData:
        ...

    def combined_stress_rules(
        self,
        rate_add: float,
        property_annual_price_growth_rate: float,
    ) -> RulePackData:
        ...

    def purchase_happiness_weights(self) -> dict[str, float]:
        ...

    def home_purchase_eligibility_policy(self) -> HomePurchaseEligibilityPolicy:
        ...

    def provident_policy_bonus(self, scenario: ScenarioData) -> float:
        ...

    def provident_loan_policy_cap(self, household: HouseholdData, scenario: ScenarioData, *, purchase_months: int = 0) -> tuple[float, float]:
        ...

    def provident_loan_years(self, household: HouseholdData, scenario: ScenarioData) -> tuple[int, list[str]]:
        ...

    def provident_loan_rate(self, household: HouseholdData, scenario: ScenarioData, loan_years: int) -> float:
        ...

    def provident_repayment_capacity_payment_cap(
        self,
        *,
        monthly_income: float,
        borrower_count: int,
    ) -> float | None:
        ...

    def provident_account_balance_annual_interest_rate(self) -> float:
        ...

    def provident_loan_offset_retained_balance(self) -> float:
        ...

    def provident_upfront_purchase_extract_ratio(self, scenario: ScenarioData) -> float:
        ...

    def provident_post_transaction_extract_ratio(self, scenario: ScenarioData) -> float:
        ...

    def provident_post_purchase_policy(self) -> ProvidentPostPurchasePolicy:
        ...

    def deed_tax_rate(self, household: HouseholdData, scenario: ScenarioData) -> float:
        ...

    def default_broker_fee_rate(self) -> float:
        ...

    def seller_tax_pass_through_default_rate(self) -> float:
        ...

    def provident_account_management_center(self) -> str:
        ...

    def default_provident_account_repayment_strategy(self) -> str:
        ...

    def provident_monthly_repayment_withdrawal_supported(self, center: str | None = None) -> bool:
        ...

    def provident_semiannual_principal_offset_supported(self, center: str | None = None) -> bool:
        ...

    def is_new_energy_vehicle(self, plan: CarPlanData) -> bool:
        ...

    def vehicle_purchase_tax_rate(self) -> float:
        ...

    def vehicle_purchase_tax_and_relief(self, plan: CarPlanData, *, purchase_month: int = 0) -> tuple[float, float]:
        ...

    def vehicle_vessel_tax_annual_at(self, plan: CarPlanData, *, month: int = 0) -> float:
        ...

    def beijing_small_passenger_indicator_required(self) -> bool:
        ...

    def beijing_new_energy_indicator_eligible(self, plan: CarPlanData) -> bool:
        ...

    def beijing_tail_restriction_exempt(self, plan: CarPlanData) -> bool:
        ...

    def beijing_family_new_energy_reference_annual_quota(self) -> float:
        ...

    def beijing_family_new_energy_config_month(self) -> int:
        ...

    def beijing_family_new_energy_projection(self, plan: CarPlanData) -> BeijingFamilyIndicatorProjection:
        ...

    def retirement_age_for_member(self, member: IncomeMember, index: int) -> int:
        ...

    def unemployment_benefit_monthly_from_service(self, service_months: int) -> float:
        ...

    def later_unemployment_benefit_monthly(self) -> float:
        ...

    def flexible_employment_social_monthly(self) -> float:
        ...

    def flexible_employment_housing_fund_monthly(self) -> float:
        ...

    def pension_estimate_policy(self) -> PensionEstimatePolicy:
        ...

    def payroll_contribution_policy(self) -> PayrollContributionPolicy:
        ...

    def social_security_account_policy(self) -> SocialSecurityAccountPolicy:
        ...

    def tax_calculation_policy(self) -> TaxCalculationPolicy:
        ...

    def tax_benefit_policy(self) -> TaxBenefitPolicy:
        ...

    def child_planning_policy(self) -> ChildPlanningPolicy:
        ...


@dataclass(frozen=True)
class BeijingPolicy:
    rules: RulePackData
    code: str = "beijing"

    @property
    def params(self) -> dict:
        return self.rules.params

    def minimum_down_payment_ratio(self, household: HouseholdData, *, uses_provident_loan: bool) -> float:
        params = self.params
        if household.existing_home_count <= 0 and household.existing_mortgage_count <= 0:
            commercial_ratio = float(params.get("first_home_commercial_min_down_payment_ratio", 0.15))
            provident_ratio = float(params.get("first_home_provident_min_down_payment_ratio", 0.20))
        else:
            commercial_ratio = float(params.get("second_home_commercial_min_down_payment_ratio", 0.20))
            provident_ratio = float(params.get("second_home_provident_min_down_payment_ratio", 0.25))
        return max(commercial_ratio, provident_ratio if uses_provident_loan else 0.0)

    def home_strategy_policy(self) -> HomeStrategyPolicy:
        default_ratio = _clamp(float(self.params.get("micro_commercial_loan_ratio", 0.05)), 0.0, 1.0)
        min_ratio = _clamp(
            float(self.params.get("micro_commercial_loan_ratio_min", min(0.02, default_ratio))),
            0.0,
            1.0,
        )
        max_ratio = _clamp(
            float(self.params.get("micro_commercial_loan_ratio_max", max(0.12, default_ratio))),
            min_ratio,
            1.0,
        )
        return HomeStrategyPolicy(
            micro_commercial_loan_ratio=default_ratio,
            micro_commercial_loan_ratio_min=min_ratio,
            micro_commercial_loan_ratio_max=max_ratio,
            default_auto_search_horizon_months=max(
                12,
                min(360, int(self.params.get("home_default_auto_search_horizon_months", 120))),
            ),
        )

    def affordability_risk_policy(self) -> AffordabilityRiskPolicy:
        caution_dti = _clamp(float(self.params.get("caution_dti", 0.40)), 0.0, 1.0)
        danger_dti = _clamp(float(self.params.get("danger_dti", 0.50)), caution_dti, 1.0)
        return AffordabilityRiskPolicy(
            recommended_emergency_months=max(0.0, float(self.params.get("recommended_emergency_months", 6))),
            caution_dti=caution_dti,
            danger_dti=danger_dti,
        )

    def personal_pension_return_policy(self) -> PersonalPensionReturnPolicy:
        return PersonalPensionReturnPolicy(
            pre_retirement_annual_return=_clamp(
                float(self.params.get("personal_pension_auto_pre_retirement_return", 0.025)),
                -0.5,
                0.5,
            ),
            post_retirement_annual_return=_clamp(
                float(self.params.get("personal_pension_auto_post_retirement_return", 0.015)),
                -0.5,
                0.5,
            ),
            snapshot_date=str(self.params.get("personal_pension_return_snapshot_date", "") or ""),
            source_count=max(0, int(self.params.get("personal_pension_return_source_count", 0) or 0)),
        )

    def stress_test_policy(self) -> StressTestPolicy:
        return StressTestPolicy(
            rate_add=max(0.0, float(self.params.get("rate_stress_add", 0.005))),
            income_factor=_clamp(float(self.params.get("income_stress_factor", 0.90)), 0.0, 1.0),
            price_factor=max(0.0, float(self.params.get("price_stress_factor", 1.05))),
            investment_return_factor=_clamp(
                float(self.params.get("investment_return_stress_factor", 0.50)),
                0.0,
                1.0,
            ),
            property_annual_price_growth_rate=_clamp(
                float(self.params.get("property_stress_annual_price_growth_rate", -0.02)),
                -0.20,
                0.20,
            ),
        )

    def property_terminal_value_policy(self) -> PropertyTerminalValuePolicy:
        return PropertyTerminalValuePolicy(
            annual_price_growth_rate=_clamp(
                float(self.params.get("property_annual_price_growth_rate", 0.0)),
                -0.20,
                0.20,
            ),
            sale_cost_rate=_clamp(float(self.params.get("property_sale_cost_rate", 0.03)), 0.0, 0.20),
            liquidity_discount_rate=_clamp(
                float(self.params.get("property_liquidity_discount_rate", 0.02)),
                0.0,
                0.20,
            ),
        )

    def stressed_interest_rate_rules(self, rate_add: float) -> RulePackData:
        provident_rate_keys = (
            "provident_first_home_rate_1_to_5_years",
            "provident_first_home_rate_6_to_30_years",
            "provident_second_home_rate_1_to_5_years",
            "provident_second_home_rate_6_to_30_years",
        )
        stressed_rate_params = dict(self.params)
        default_params = RulePackData().params
        for key in provident_rate_keys:
            stressed_rate_params[key] = float(stressed_rate_params.get(key, default_params.get(key, 0.0))) + rate_add
        return self.rules.model_copy(update={"params": stressed_rate_params})

    def combined_stress_rules(
        self,
        rate_add: float,
        property_annual_price_growth_rate: float,
    ) -> RulePackData:
        rate_rules = self.stressed_interest_rate_rules(rate_add)
        return rate_rules.model_copy(
            update={
                "params": {
                    **rate_rules.params,
                    "property_annual_price_growth_rate": property_annual_price_growth_rate,
                }
            }
        )

    def purchase_happiness_weights(self) -> dict[str, float]:
        raw_weights = self.params.get("purchase_happiness_weights", {})
        weights: dict[str, float] = {}
        for key, default in DEFAULT_PURCHASE_HAPPINESS_WEIGHTS.items():
            raw_value = raw_weights.get(key, default) if isinstance(raw_weights, dict) else default
            try:
                weights[key] = max(0.0, float(raw_value))
            except (TypeError, ValueError):
                weights[key] = default
        if sum(weights.values()) <= 0:
            return DEFAULT_PURCHASE_HAPPINESS_WEIGHTS.copy()
        return weights

    def home_purchase_eligibility_policy(self) -> HomePurchaseEligibilityPolicy:
        params = self.params
        return HomePurchaseEligibilityPolicy(
            required_social_security_months=max(0, int(params.get("required_social_security_months", 36))),
            max_home_count=max(0, int(params.get("max_home_count", 2))),
        )

    def provident_policy_bonus(self, scenario: ScenarioData) -> float:
        if not _is_new_home_property(scenario):
            return 0.0

        params = self.params
        bonuses: list[float] = []
        if scenario.green_building_level == "two_star":
            bonuses.append(float(params.get("provident_green_two_star_bonus", 0)))
        elif scenario.green_building_level == "three_star":
            bonuses.append(float(params.get("provident_green_three_star_bonus", 0)))

        prefab_bonus = {
            "A": float(params.get("provident_prefab_a_bonus", 0)),
            "AA": float(params.get("provident_prefab_aa_bonus", 0)),
            "AAA": float(params.get("provident_prefab_aaa_bonus", 0)),
        }.get(scenario.prefab_building_level, 0.0)
        if prefab_bonus > 0:
            bonuses.append(prefab_bonus)

        if scenario.is_ultra_low_energy_building:
            bonuses.append(float(params.get("provident_ultra_low_energy_bonus", 0)))

        cap = float(params.get("provident_policy_bonus_cap", 400000))
        return min(sum(bonuses), cap)

    def provident_loan_policy_cap(self, household: HouseholdData, scenario: ScenarioData, *, purchase_months: int = 0) -> tuple[float, float]:
        params = self.params
        amount_per_year = float(params.get("provident_loan_amount_per_deposit_year", 150_000))
        has_future_provident_deposit = any(
            member.provident_account_enabled
            and (
                member.monthly_salary_gross > 0
                or member.monthly_housing_fund > 0
                or any(
                    stage.payroll_contributions_enabled
                    and (stage.monthly_salary_gross > 0 or stage.monthly_housing_fund > 0)
                    for stage in member.income_stages
                )
            )
            for member in household.members
        )
        effective_deposit_months = household.social_security_months + (
            max(0, purchase_months) if has_future_provident_deposit else 0
        )
        deposit_years = (effective_deposit_months + 11) // 12 if effective_deposit_months > 0 else 0
        cap_by_deposit_years = amount_per_year * deposit_years
        if household.existing_home_count == 0:
            base_cap = float(params.get("provident_first_home_loan_cap", 1_200_000))
        else:
            base_cap = float(params.get("provident_second_home_loan_cap", 1_000_000))
        bonus = self.provident_policy_bonus(scenario)
        return min(base_cap + bonus, cap_by_deposit_years + bonus), bonus

    def provident_loan_years(self, household: HouseholdData, scenario: ScenarioData) -> tuple[int, list[str]]:
        params = self.params
        requested_years = max(1, min(scenario.loan_years, 30))
        max_years = int(params.get("provident_max_loan_years", 30))
        borrower_age_limit = int(params.get("provident_max_borrower_age", 68))
        borrower_age_years = max(18, household.borrower_age)
        age_limited_years = max(1, borrower_age_limit - borrower_age_years)
        limits: list[tuple[int, str]] = [
            (requested_years, f"手动贷款年限 {requested_years} 年"),
            (max_years, f"北京公积金最长 {max_years} 年"),
            (age_limited_years, f"借款申请人年龄 {borrower_age_years} 岁，对应最长 {age_limited_years} 年"),
        ]

        if _is_second_hand_property(scenario):
            property_age = max(0, scenario.building_age_years)
            safety_deduction = int(params.get("provident_property_age_safety_deduction_years", 3))
            uses_renovated_land_limit = scenario.is_old_community_renovated and scenario.remaining_land_use_years is not None
            if uses_renovated_land_limit:
                land_limited_years = max(1, scenario.remaining_land_use_years - safety_deduction)
                limits.append((land_limited_years, f"剩余土地使用年限 {scenario.remaining_land_use_years} 年，扣减 {safety_deduction} 年后最长 {land_limited_years} 年"))
            else:
                if scenario.building_structure == "brick_mixed":
                    total_life = int(params.get("provident_brick_mixed_total_life_years", 50))
                    structure_label = "砖混结构"
                else:
                    total_life = int(params.get("provident_steel_concrete_total_life_years", 60))
                    structure_label = "钢混结构"
                structure_limited_years = max(1, total_life - property_age - safety_deduction)
                limits.append(
                    (
                        structure_limited_years,
                        f"二手房房龄 {property_age} 年，{structure_label} 最长 {structure_limited_years} 年",
                    )
                )
                if scenario.remaining_land_use_years is not None:
                    land_limited_years = max(1, scenario.remaining_land_use_years)
                    limits.append((land_limited_years, f"土地剩余年限 {land_limited_years} 年"))

        selected_years = min(years for years, _ in limits)
        reasons = [reason for years, reason in limits if years == selected_years]
        return selected_years, reasons

    def provident_loan_rate(self, household: HouseholdData, scenario: ScenarioData, loan_years: int) -> float:
        params = self.params
        first_home = household.existing_home_count <= 0 and household.existing_mortgage_count <= 0
        term_bucket = "1_to_5_years" if loan_years <= 5 else "6_to_30_years"
        key = f"provident_{'first' if first_home else 'second'}_home_rate_{term_bucket}"
        fallback = 0.021 if first_home and loan_years <= 5 else 0.026 if first_home else 0.02325 if loan_years <= 5 else 0.03075
        return max(0.0, float(params.get(key, fallback)))

    def provident_repayment_capacity_payment_cap(
        self,
        *,
        monthly_income: float,
        borrower_count: int,
    ) -> float | None:
        params = self.params
        if not bool(params.get("provident_repayment_capacity_enabled", True)):
            return None
        if monthly_income <= 0:
            return None
        income_ratio = _clamp(float(params.get("provident_repayment_income_ratio", 0.60)), 0.0, 1.0)
        basic_living_cost = max(0.0, float(params.get("provident_basic_living_cost_per_person", 1778)))
        family_living_floor = basic_living_cost * max(1, borrower_count)
        return max(
            0.0,
            min(
                monthly_income * income_ratio,
                monthly_income - family_living_floor,
            ),
        )

    def provident_account_balance_annual_interest_rate(self) -> float:
        return max(0.0, float(self.params.get("provident_balance_annual_interest_rate", 0.015)))

    def provident_loan_offset_retained_balance(self) -> float:
        return max(0.0, float(self.params.get("provident_loan_offset_retained_balance", 10.0)))

    def provident_upfront_purchase_extract_ratio(self, scenario: ScenarioData) -> float:
        params = self.params
        default_ratio = float(params.get("provident_upfront_purchase_extract_ratio", 0.0))
        if _is_second_hand_property(scenario):
            configured = params.get("provident_upfront_purchase_extract_ratio_second_hand", 0.0)
        elif _is_new_home_property(scenario):
            configured = params.get("provident_upfront_purchase_extract_ratio_new_home", 1.0)
        else:
            configured = params.get("provident_upfront_purchase_extract_ratio", default_ratio)
        return _clamp(float(configured), 0.0, 1.0)

    def provident_post_transaction_extract_ratio(self, scenario: ScenarioData) -> float:
        return _clamp(float(self.params.get("provident_post_transaction_extract_ratio", 1.0)), 0.0, 1.0)

    def provident_post_purchase_policy(self) -> ProvidentPostPurchasePolicy:
        return ProvidentPostPurchasePolicy(
            cashflow_enabled=bool(self.params.get("provident_post_purchase_cashflow_enabled", False)),
            monthly_withdrawal_enabled=bool(
                self.params.get("provident_monthly_withdrawal_after_purchase_enabled", False)
            ),
            strategy_mode=str(self.params.get("provident_post_purchase_strategy_mode", "auto")),
            withdrawal_mode=str(self.params.get("provident_post_purchase_withdrawal_mode", "monthly_repayment_withdrawal")),
        )

    def deed_tax_rate(self, household: HouseholdData, scenario: ScenarioData) -> float:
        params = self.params
        is_first_home = household.existing_home_count <= 0
        is_small_or_standard = scenario.area_sqm <= float(params.get("deed_tax_standard_area_sqm", 140))
        if is_first_home and is_small_or_standard:
            key, fallback = "deed_tax_first_home_standard_rate", 0.01
        elif is_first_home:
            key, fallback = "deed_tax_first_home_large_rate", 0.015
        elif is_small_or_standard:
            key, fallback = "deed_tax_second_home_standard_rate", 0.01
        else:
            key, fallback = "deed_tax_second_home_large_rate", 0.02
        return max(0.0, float(params.get(key, params.get("default_deed_tax_rate", fallback))))

    def default_broker_fee_rate(self) -> float:
        return _clamp(float(self.params.get("default_broker_fee_rate", 0.022)), 0.0, 0.2)

    def seller_tax_pass_through_default_rate(self) -> float:
        return _clamp(float(self.params.get("seller_tax_pass_through_default_rate", 0.0)), 0.0, 0.2)

    def provident_account_management_center(self) -> str:
        center = str(self.params.get("provident_account_management_center", "beijing_municipal")).strip().lower()
        if center in {"national", "central_state", "guoguan", "state"}:
            return "national"
        return "beijing_municipal"

    def default_provident_account_repayment_strategy(self) -> str:
        center = self.provident_account_management_center()
        if self.provident_monthly_repayment_withdrawal_supported(center):
            return "monthly_repayment_withdrawal"
        if self.provident_semiannual_principal_offset_supported(center):
            return "semiannual_principal_offset"
        return "keep_in_account"

    def provident_monthly_repayment_withdrawal_supported(self, center: str | None = None) -> bool:
        normalized = _normalized_provident_center(center) or self.provident_account_management_center()
        if normalized == "national":
            return bool(self.params.get("provident_national_monthly_direct_offset_supported", True))
        return bool(self.params.get("provident_municipal_monthly_repayment_withdrawal_supported", True))

    def provident_semiannual_principal_offset_supported(self, center: str | None = None) -> bool:
        normalized = _normalized_provident_center(center) or self.provident_account_management_center()
        if normalized == "national":
            return bool(self.params.get("provident_national_semiannual_principal_offset_supported", False))
        return bool(self.params.get("provident_municipal_semiannual_principal_offset_supported", True))

    def is_new_energy_vehicle(self, plan: CarPlanData) -> bool:
        eligible_types = _policy_string_set(
            self.params.get("new_energy_vehicle_types"),
            ["pure_electric", "plug_in_hybrid", "range_extended", "fuel_cell"],
        )
        return bool(plan.new_energy_catalog_eligible) and str(plan.energy_type) in eligible_types

    def vehicle_purchase_tax_rate(self) -> float:
        return max(0.0, float(self.params.get("vehicle_purchase_tax_rate", 0.10)))

    def vehicle_purchase_tax_and_relief(self, plan: CarPlanData, *, purchase_month: int = 0) -> tuple[float, float]:
        taxable_ratio = max(0.0, float(self.params.get("vehicle_purchase_tax_taxable_price_ratio", 1 / 1.13)))
        taxable_price = max(0.0, plan.total_price) * taxable_ratio
        gross_tax = taxable_price * self.vehicle_purchase_tax_rate()
        if not self.is_new_energy_vehicle(plan):
            return gross_tax, 0.0

        today = date.today()
        purchase_date = add_months(date(today.year, today.month, 1), max(0, purchase_month))
        target = (purchase_date.year, purchase_date.month)
        exempt_until = parse_year_month(str(self.params.get("new_energy_vehicle_purchase_tax_exempt_until", "2025-12")))
        if exempt_until is not None and month_distance(target, exempt_until) >= 0:
            relief = min(gross_tax, float(self.params.get("new_energy_vehicle_purchase_tax_exemption_cap", 30000)))
            return max(0.0, gross_tax - relief), relief

        half_until = parse_year_month(str(self.params.get("new_energy_vehicle_purchase_tax_half_until", "2027-12")))
        if half_until is not None and month_distance(target, half_until) >= 0:
            relief = min(gross_tax * 0.5, float(self.params.get("new_energy_vehicle_purchase_tax_half_relief_cap", 15000)))
            return max(0.0, gross_tax - relief), relief
        return gross_tax, 0.0

    def vehicle_vessel_tax_annual_at(self, plan: CarPlanData, *, month: int = 0) -> float:
        passenger_not_taxable_types = _policy_string_set(
            self.params.get("vehicle_vessel_tax_passenger_not_taxable_types"),
            ["pure_electric", "fuel_cell"],
        )
        if str(plan.energy_type) in passenger_not_taxable_types:
            return 0.0

        exempt_types = _policy_string_set(
            self.params.get("new_energy_vehicle_vessel_tax_exempt_types"),
            ["pure_electric", "fuel_cell"],
        )
        if str(plan.energy_type) in exempt_types:
            return 0.0

        if str(plan.energy_type) in {"plug_in_hybrid", "range_extended"}:
            today = date.today()
            target_date = add_months(date(today.year, today.month, 1), max(0, month))
            exempt_until = parse_year_month(str(self.params.get("plug_in_hybrid_vehicle_vessel_tax_exempt_until", "2026-12")))
            if exempt_until is not None and month_distance((target_date.year, target_date.month), exempt_until) >= 0:
                return 0.0
            return max(0.0, float(self.params.get("plug_in_hybrid_vehicle_vessel_tax_annual", 0)))

        return max(0.0, float(self.params.get("fuel_vehicle_vessel_tax_annual_default", 420)))

    def beijing_small_passenger_indicator_required(self) -> bool:
        return bool(self.params.get("beijing_small_passenger_indicator_required", True))

    def beijing_new_energy_indicator_eligible(self, plan: CarPlanData) -> bool:
        eligible_types = _policy_string_set(
            self.params.get("beijing_new_energy_indicator_vehicle_types"),
            ["pure_electric"],
        )
        return str(plan.energy_type) in eligible_types

    def beijing_tail_restriction_exempt(self, plan: CarPlanData) -> bool:
        exempt_types = _policy_string_set(
            self.params.get("beijing_tail_restriction_exempt_vehicle_types"),
            ["pure_electric"],
        )
        return str(plan.energy_type) in exempt_types

    def beijing_family_new_energy_reference_annual_quota(self) -> float:
        return max(1.0, float(self.params.get("beijing_family_new_energy_reference_annual_quota", 119200)))

    def beijing_family_new_energy_config_month(self) -> int:
        return max(1, min(12, int(self.params.get("beijing_family_new_energy_config_month", 5))))

    def beijing_family_new_energy_projection(self, plan: CarPlanData) -> BeijingFamilyIndicatorProjection:
        applicant_projection = _beijing_family_indicator_from_applicants(plan)
        if applicant_projection is None:
            generation_multiplier = max(1, plan.beijing_family_indicator_generations)
            application_years = max(0, plan.beijing_family_indicator_application_years)
            main_points = max(0.0, plan.beijing_family_indicator_main_points) + application_years
            spouse_points = (
                max(0.0, plan.beijing_family_indicator_spouse_points) + application_years
                if plan.beijing_family_indicator_has_spouse
                else 0.0
            )
            other_count = max(0, plan.beijing_family_indicator_other_applicant_count)
            other_points = max(0.0, plan.beijing_family_indicator_other_points_total) + other_count * application_years
            spouse_weight = 2 if plan.beijing_family_indicator_has_spouse else 1
            score = max(0.0, ((main_points + spouse_points) * spouse_weight + other_points) * generation_multiplier)
            annual_gain = ((1 + (1 if plan.beijing_family_indicator_has_spouse else 0)) * spouse_weight + other_count) * generation_multiplier
            detail_notes = ["当前未配置家庭指标申请人明细，使用简化积分参数估算。"]
        else:
            score, annual_gain, generation_multiplier, detail_notes = applicant_projection

        cutoff = max(0.0, plan.beijing_family_indicator_current_cutoff_score)
        cutoff_growth = plan.beijing_family_indicator_cutoff_score_annual_change
        annual_quota = max(1, plan.beijing_family_indicator_annual_quota)
        reference_quota = self.beijing_family_new_energy_reference_annual_quota()
        quota_wait_factor = _clamp(reference_quota / annual_quota, 0.5, 3.0)
        if score >= cutoff:
            wait_months: int | None = 0
        else:
            effective_gain = annual_gain - cutoff_growth
            if effective_gain <= 0:
                wait_months = None
            else:
                years_to_cross = ceil((cutoff - score) / effective_gain * quota_wait_factor)
                today = date.today()
                base_year = max(today.year, plan.beijing_family_indicator_last_config_year)
                target_year = base_year + years_to_cross
                target_month = self.beijing_family_new_energy_config_month()
                wait_months = max(0, (target_year - today.year) * 12 + target_month - today.month)

        notes = [
            f"家庭新能源指标估算分数约 {score:.2f} 分；按最近入围分数 {cutoff:.2f}、年度新能源家庭指标约 {annual_quota} 个估算。",
        ]
        notes.extend(detail_notes)
        if quota_wait_factor != 1:
            notes.append(f"年度指标量相对基准 {round(reference_quota)} 个做粗略校正，等待年限系数约 {quota_wait_factor:.2f}；实际仍以年度公告和家庭申请人分布为准。")
        if wait_months is None:
            notes.append("当前积分年增长不高于入围分年增长，无法可靠估计排到时间；请补充更准确的家庭积分或公告分数变化。")
        elif wait_months > 0:
            estimated_date = add_months(date.today().replace(day=1), wait_months)
            notes.append(f"按当前积分增长估计约 {wait_months} 个月后可能进入家庭新能源指标配置窗口，约为 {estimated_date.year} 年。")
        else:
            notes.append("当前估算分数已达到或超过最近入围分数，购车时间不额外等待家庭新能源指标。")
        return BeijingFamilyIndicatorProjection(
            score=score,
            annual_gain=annual_gain,
            generation_multiplier=generation_multiplier,
            wait_months=wait_months,
            notes=notes,
        )

    def retirement_age_for_member(self, member: IncomeMember, index: int) -> int:
        category = getattr(member, "retirement_category", None)
        if category == "female_50":
            return int(self.params.get("retirement_age_female_worker", 55))
        if category == "female_55":
            return int(self.params.get("retirement_age_female_cadre", 58))
        if category == "male_60":
            return int(self.params.get("retirement_age_male", 63))
        return int(self.params.get("retirement_age_default_first_member" if index == 0 else "retirement_age_default_other_member", 63 if index == 0 else 58))

    def unemployment_benefit_monthly_from_service(self, service_months: int) -> float:
        if service_months >= 240:
            return float(self.params.get("beijing_unemployment_benefit_20y_plus", 2286))
        if service_months >= 180:
            return float(self.params.get("beijing_unemployment_benefit_15_to_20y", 2215))
        if service_months >= 120:
            return float(self.params.get("beijing_unemployment_benefit_10_to_15y", 2188))
        if service_months >= 60:
            return float(self.params.get("beijing_unemployment_benefit_5_to_10y", 2156))
        if service_months >= 12:
            return float(self.params.get("beijing_unemployment_benefit_under_5y", 2129))
        return 0.0

    def later_unemployment_benefit_monthly(self) -> float:
        return max(0.0, float(self.params.get("beijing_unemployment_benefit_after_12_months", 2129)))

    def flexible_employment_social_monthly(self) -> float:
        social_floor = float(self.params.get("beijing_social_base_floor", 7162))
        social_ceiling = float(self.params.get("beijing_social_base_ceiling", 35811))
        base = _clamp(
            float(self.params.get("flexible_employment_social_base", social_floor)),
            social_floor,
            social_ceiling,
        )
        pension = base * float(self.params.get("flexible_employment_pension_rate", 0.20))
        unemployment = base * float(self.params.get("flexible_employment_unemployment_rate", 0.01))
        medical = float(self.params.get("flexible_employment_medical_monthly", 584.92))
        return round(max(0.0, pension + unemployment + medical), 2)

    def flexible_employment_housing_fund_monthly(self) -> float:
        if not bool(self.params.get("flexible_employment_housing_fund_enabled", True)):
            return 0.0
        floor = float(self.params.get("beijing_housing_fund_base_floor", 2540))
        ceiling = float(self.params.get("beijing_housing_fund_base_ceiling", 35811))
        base = _clamp(
            float(self.params.get("flexible_employment_housing_fund_base", floor)),
            floor,
            ceiling,
        )
        rate = _clamp(float(self.params.get("flexible_employment_housing_fund_rate", 0.12)), 0.0, 0.24)
        return round(base * rate, 2)

    def pension_estimate_policy(self) -> PensionEstimatePolicy:
        social_floor = float(self.params.get("beijing_social_base_floor", 7162))
        social_ceiling = float(self.params.get("beijing_social_base_ceiling", 35811))
        reference_average_salary = _clamp(
            float(self.params.get("pension_reference_average_salary", self.params.get("beijing_social_base_ceiling", 35811))),
            social_floor,
            social_ceiling,
        )
        flexible_base = _clamp(
            float(self.params.get("flexible_employment_social_base", social_floor)),
            social_floor,
            social_ceiling,
        )
        floor_rate = _clamp(float(self.params.get("pension_replacement_rate_floor", 0.20)), 0.0, 1.0)
        ceiling_rate = _clamp(float(self.params.get("pension_replacement_rate_ceiling", 0.65)), floor_rate, 1.2)
        return PensionEstimatePolicy(
            social_base_floor=social_floor,
            social_base_ceiling=social_ceiling,
            flexible_employment_social_base=flexible_base,
            reference_average_salary=reference_average_salary,
            average_salary_growth_rate=_clamp(float(self.params.get("pension_average_salary_growth_rate", 0.03)), 0.0, 0.10),
            default_paid_years=max(0.0, float(self.params.get("pension_default_paid_years", 15))),
            employee_pension_rate=max(0.0, float(self.params.get("employee_pension_rate", 0.08))),
            flexible_employment_pension_rate=max(0.0, float(self.params.get("flexible_employment_pension_rate", 0.20))),
            personal_account_annual_return=_clamp(float(self.params.get("pension_personal_account_annual_return", 0.025)), 0.0, 0.08),
            personal_account_months=max(1.0, float(self.params.get("pension_personal_account_months", 139))),
            replacement_rate_floor=floor_rate,
            replacement_rate_ceiling=ceiling_rate,
        )

    def payroll_contribution_policy(self) -> PayrollContributionPolicy:
        return PayrollContributionPolicy(
            social_base_floor=float(self.params.get("beijing_social_base_floor", 7162)),
            social_base_ceiling=float(self.params.get("beijing_social_base_ceiling", 35811)),
            housing_fund_base_floor=float(self.params.get("beijing_housing_fund_base_floor", 2540)),
            housing_fund_base_ceiling=float(self.params.get("beijing_housing_fund_base_ceiling", 35811)),
            housing_fund_rate_floor=float(self.params.get("housing_fund_min_rate", 0.05)),
            housing_fund_rate_ceiling=float(self.params.get("housing_fund_max_rate", 0.12)),
            employee_pension_rate=max(0.0, float(self.params.get("employee_pension_rate", 0.08))),
            employee_medical_rate=max(0.0, float(self.params.get("employee_medical_rate", 0.02))),
            employee_medical_fixed=max(0.0, float(self.params.get("employee_medical_fixed", 3))),
            employee_unemployment_rate=max(0.0, float(self.params.get("employee_unemployment_rate", 0.005))),
            employer_pension_rate=max(0.0, float(self.params.get("employer_pension_rate", 0.16))),
            employer_medical_maternity_rate=max(0.0, float(self.params.get("employer_medical_maternity_rate", 0.098))),
            employer_unemployment_rate=max(0.0, float(self.params.get("employer_unemployment_rate", 0.005))),
            employer_work_injury_rate=max(0.0, float(self.params.get("employer_work_injury_rate", 0.002))),
        )

    def social_security_account_policy(self) -> SocialSecurityAccountPolicy:
        raw_medical_credit_months = self.params.get("medical_account_interest_credit_months", [3, 6, 9, 12])
        medical_credit_months: set[int] = set()
        if isinstance(raw_medical_credit_months, list):
            for item in raw_medical_credit_months:
                try:
                    month = int(item)
                except (TypeError, ValueError):
                    continue
                if 1 <= month <= 12:
                    medical_credit_months.add(month)
        if not medical_credit_months:
            medical_credit_months = {3, 6, 9, 12}
        return SocialSecurityAccountPolicy(
            pension_account_annual_return=_clamp(float(self.params.get("pension_personal_account_annual_return", 0.025)), 0.0, 0.20),
            pension_account_interest_credit_month=max(
                1,
                min(12, int(self.params.get("pension_personal_account_interest_credit_month", 12) or 12)),
            ),
            pension_account_annual_credit_rates=dict(self.params.get("pension_personal_account_annual_credit_rates") or {}),
            medical_account_annual_interest_rate=max(0.0, float(self.params.get("medical_account_annual_interest_rate", 0.0035))),
            medical_account_interest_credit_months=medical_credit_months,
            medical_account_employee_transfer_rate=max(0.0, float(self.params.get("medical_account_employee_transfer_rate", 0.02))),
            medical_account_retiree_monthly_transfer_under_70=max(0.0, float(self.params.get("medical_account_retiree_monthly_transfer_under_70", 100))),
            medical_account_retiree_monthly_transfer_70_plus=max(0.0, float(self.params.get("medical_account_retiree_monthly_transfer_70_plus", 110))),
            medical_account_retiree_large_mutual_aid_monthly=max(0.0, float(self.params.get("medical_account_retiree_large_mutual_aid_monthly", 3))),
            pension_account_months=max(1, int(self.params.get("pension_personal_account_months", 139) or 139)),
            pension_account_months_by_retirement_category=dict(
                self.params.get("pension_personal_account_months_by_retirement_category") or {}
            ),
        )

    def tax_calculation_policy(self) -> TaxCalculationPolicy:
        periods = self.params.get("annual_bonus_policy_periods")
        return TaxCalculationPolicy(
            comprehensive_brackets=list(self.params.get("comprehensive_tax_brackets") or DEFAULT_COMPREHENSIVE_TAX_BRACKETS),
            monthly_converted_bonus_brackets=list(
                self.params.get("monthly_converted_bonus_tax_brackets") or DEFAULT_MONTHLY_CONVERTED_BONUS_TAX_BRACKETS
            ),
            personal_standard_deduction_annual=float(self.params.get("personal_standard_deduction_annual", 60000)),
            annual_bonus_policy_periods=list(periods) if isinstance(periods, list) else [],
            annual_bonus_separate_tax_default_continues=bool(self.params.get("annual_bonus_separate_tax_default_continues", True)),
            annual_bonus_separate_tax_valid_until=parse_iso_date(
                str(self.params.get("annual_bonus_separate_tax_valid_until") or ""),
                date(9999, 12, 31),
            ),
        )

    def tax_benefit_policy(self) -> TaxBenefitPolicy:
        return TaxBenefitPolicy(
            housing_rent_monthly=max(0.0, float(self.params.get("beijing_housing_rent_deduction_monthly", 1500))),
            first_home_mortgage_interest_monthly=max(
                0.0,
                float(self.params.get("first_home_mortgage_interest_deduction_monthly", 1000)),
            ),
            first_home_mortgage_interest_max_months=max(
                0,
                int(self.params.get("first_home_mortgage_interest_max_months", 240)),
            ),
            child_education_monthly=max(0.0, float(self.params.get("child_education_deduction_monthly", 2000))),
            infant_care_monthly=max(0.0, float(self.params.get("infant_care_deduction_monthly", 2000))),
            serious_illness_medical_threshold=max(0.0, float(self.params.get("serious_illness_medical_threshold", 15000))),
            serious_illness_medical_cap=max(0.0, float(self.params.get("serious_illness_medical_cap", 80000))),
            personal_pension_deduction_annual_cap=max(
                0.0,
                float(self.params.get("personal_pension_deduction_annual_cap", 12000)),
            ),
            personal_pension_withdrawal_tax_rate=max(
                0.0,
                float(self.params.get("personal_pension_withdrawal_tax_rate", 0.03)),
            ),
            rent_and_mortgage_mutually_exclusive=bool(self.params.get("rent_and_mortgage_deduction_mutually_exclusive", True)),
            annual_tax_settlement_month=max(1, min(12, int(self.params.get("annual_tax_settlement_month", 3) or 3))),
        )

    def child_planning_policy(self) -> ChildPlanningPolicy:
        raw_weights = self.params.get("child_happiness_weights", {})
        weights: dict[str, float] = {}
        if isinstance(raw_weights, dict):
            for key, value in raw_weights.items():
                try:
                    weights[str(key)] = max(0.0, float(value))
                except (TypeError, ValueError):
                    continue
        return ChildPlanningPolicy(
            birth_after_home_delay_months=max(
                0,
                int(self.params.get("child_plan_birth_after_home_delay_months", 12)),
            ),
            advanced_maternal_age=max(
                0.0,
                float(self.params.get("child_plan_advanced_maternal_age", 35)),
            ),
            happiness_weights=weights,
        )


def _is_second_hand_property(scenario: ScenarioData) -> bool:
    text = scenario.property_type.strip()
    return "二手" in text or "存量" in text


def _is_new_home_property(scenario: ScenarioData) -> bool:
    return "新房" in scenario.property_type.strip()


def _normalized_provident_center(value: str | None) -> str | None:
    center = str(value or "").strip().lower()
    if center in {"national", "central_state", "guoguan", "state"}:
        return "national"
    if center in {"beijing_municipal", "municipal", "shiguan", "city"}:
        return "beijing_municipal"
    return None


def _policy_string_set(value: object, fallback: list[str]) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    return set(fallback)


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _yearly_policy_rate(table: dict, year: int, fallback: float) -> float:
    if isinstance(table, dict):
        value = table.get(str(year), table.get(year))
        if value is not None:
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                pass
    return max(0.0, float(fallback))


def _whole_years_between(start_month: tuple[int, int] | None, end_month: tuple[int, int]) -> int:
    if start_month is None:
        return 0
    return max(0, month_distance(start_month, end_month) // 12)


def _indicator_applicant_label(value: str) -> str:
    return {
        "main": "主申请人",
        "spouse": "配偶",
        "child": "子女",
        "parent": "父母",
        "parent_in_law": "配偶父母",
        "other": "其他家庭申请人",
    }.get(value, "其他家庭申请人")


def _indicator_eligibility_label(value: str) -> str:
    return {
        "beijing_household": "北京户籍",
        "beijing_work_residence_permit": "北京工作居住证",
        "beijing_residence_permit_social_tax": "北京居住证+连续社保/个税",
        "active_military_or_police": "驻京现役军人/武警",
        "hongkong_macao_taiwan_foreign": "港澳台/外籍按规定居留",
        "unknown": "资格待确认",
    }.get(value, "资格待确认")


def _coerce_indicator_applicant(value: object) -> VehicleIndicatorApplicantData | None:
    if isinstance(value, VehicleIndicatorApplicantData):
        return value
    if isinstance(value, dict):
        try:
            return VehicleIndicatorApplicantData.model_validate(value)
        except Exception:
            return None
    return None


def _beijing_family_indicator_from_applicants(plan: CarPlanData) -> tuple[float, float, int, list[str]] | None:
    applicants: list[VehicleIndicatorApplicantData] = []
    for item in plan.beijing_family_indicator_applicants:
        applicant = _coerce_indicator_applicant(item)
        if applicant is not None and applicant.enabled:
            applicants.append(applicant)
    if not applicants:
        return None

    today = date.today()
    current_month = (today.year, today.month)
    default_start = parse_year_month(plan.beijing_family_indicator_application_start_month)
    weighted_points = 0.0
    weighted_annual_gain = 0.0
    generations = {item.generation for item in applicants}
    generation_multiplier = max(1, min(3, len(generations)))
    notes = [f"家庭指标按 {len(applicants)} 名申请人、{generation_multiplier} 代计算；仅参与指标算分的老人不会进入家庭现金流。"]

    for index, applicant in enumerate(applicants):
        relationship = str(applicant.relationship)
        is_main_or_spouse = relationship in {"main", "spouse"}
        weight = 2 if is_main_or_spouse else 1
        base_points = 2 if relationship == "main" else 1
        start_month = parse_year_month(applicant.family_application_start_month) or default_start
        family_years = _whole_years_between(start_month, current_month)
        history_points = 0.0
        if applicant.personal_history_points_override is not None:
            history_points = max(0.0, applicant.personal_history_points_override)
        else:
            if applicant.personal_indicator_history_type in {"ordinary_lottery", "both"}:
                history_points += max(0, applicant.ordinary_lottery_steps)
            if applicant.personal_indicator_history_type in {"new_energy_queue", "both"}:
                history_points += _whole_years_between(parse_year_month(applicant.new_energy_queue_start_month), start_month or current_month)
        subtotal = base_points + family_years + history_points
        weighted_points += subtotal * weight
        weighted_annual_gain += weight
        notes.append(
            f"{applicant.name or f'申请人{index + 1}'}（{_indicator_applicant_label(relationship)}，{_indicator_eligibility_label(str(applicant.eligibility_type))}）："
            f"基础 {base_points} 分、家庭申请满年 {family_years} 分、个人摇号/轮候历史 {history_points:.1f} 分，按权重 {weight} 计入。"
        )

    score = weighted_points * generation_multiplier
    annual_gain = weighted_annual_gain * generation_multiplier
    notes.append(f"当前家庭积分约 {score:.2f} 分；以后每满一年约增加 {annual_gain:.2f} 分。公式口径为：主申请人和配偶积分权重 2，其他申请人权重 1，再乘家庭代际数。")
    return score, annual_gain, generation_multiplier, notes


def get_policy(rules: RulePackData) -> RegionalPolicy:
    jurisdiction = rules.jurisdiction.strip().lower()
    if jurisdiction in {"北京", "beijing", "bj"}:
        return BeijingPolicy(rules)
    return BeijingPolicy(rules)


def with_personal_pension_return_snapshot(
    rules: RulePackData,
    *,
    pre_retirement_annual_return: float,
    post_retirement_annual_return: float,
    snapshot_date: str,
    source_count: int,
) -> RulePackData:
    """Apply a monitored return snapshot without exposing policy params to the API layer."""
    params = {
        **rules.params,
        "personal_pension_auto_pre_retirement_return": pre_retirement_annual_return,
        "personal_pension_auto_post_retirement_return": post_retirement_annual_return,
        "personal_pension_return_snapshot_date": snapshot_date,
        "personal_pension_return_source_count": source_count,
    }
    return rules.model_copy(update={"params": params})
