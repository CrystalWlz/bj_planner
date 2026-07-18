# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


RepaymentMethod = Literal["equal_installment", "equal_principal"]
RuleStatus = Literal["draft", "active", "archived"]
BonusTaxMethod = Literal["separate", "merged", "best"]
AnnualBonusPayoutMode = Literal["lump_sum", "monthly_spread"]
IncomeStageKind = Literal["salary", "unemployment", "freelance", "pension", "manual"]
FreelanceTaxMode = Literal["labor_remuneration", "business_income", "other"]
GreenBuildingLevel = Literal["none", "two_star", "three_star"]
PrefabBuildingLevel = Literal["none", "A", "AA", "AAA"]
BuildingStructure = Literal["unknown", "brick_mixed", "steel_concrete"]
RenovationFundingMode = Literal[
    "cash_or_investment",
    "cash_only",
    "after_goal_saving",
    "after_purchase_saving",
    "upfront_cash",
]
InvestmentWithdrawalMode = Literal["auto", "full_liquidation", "manual_reserve"]
InvestmentInstrumentMarket = Literal["mainland_etf", "hong_kong_connect", "qdii_etf", "qdii_fund"]
InvestmentTradingMode = Literal["exchange", "fund_subscription"]
InvestmentAssetClass = Literal["equity", "defensive"]
InvestmentMarketDataStatus = Literal["complete", "partial", "empty"]
InvestmentOrderStatus = Literal["proposed", "simulated", "confirmed", "cancelled", "blocked"]
RetirementCategory = Literal["male_60", "female_55", "female_50"]
MemberSex = Literal["female", "male", "unspecified"]
ProvidentAccountManagementCenter = Literal["beijing_municipal", "national"]
CommercialPrepaymentMode = Literal["auto", "manual", "none"]
ProvidentAccountRepaymentStrategy = Literal[
    "auto",
    "monthly_repayment_withdrawal",
    "semiannual_principal_offset",
    "keep_in_account",
]
ProvidentAccountRepaymentSwitchTarget = Literal[
    "monthly_repayment_withdrawal",
    "semiannual_principal_offset",
]
ExistingLoanPrepaymentMode = Literal["none", "manual", "auto"]
AccountCalibrationTarget = Literal[
    "cash",
    "investment",
    "provident",
    "pension",
    "medical",
    "property_asset",
    "vehicle_asset",
    "fixed_asset",
    "total_loan",
]
AccountCalibrationScope = Literal["account", "concept", "major_event", "strategy_event"]
PlanningGoalType = Literal["home", "vehicle", "child", "renovation", "other"]
PlanningTimingMode = Literal["auto_sequence", "parallel", "manual_month", "after_goal", "not_planned"]
CoreObjectType = Literal["account", "loan", "asset", "adjustment"]
CoreObjectCategory = Literal[
    "cash",
    "investment",
    "provident",
    "pension",
    "medical",
    "personal_pension",
    "property_asset",
    "vehicle_asset",
    "child_goal",
    "planning_goal",
    "fixed_asset",
    "mortgage",
    "car_loan",
    "education",
    "consumer",
    "manual_adjustment",
    "other",
]
CoreObjectSource = Literal["household", "member", "loan", "goal", "manual"]
GeneratedStrategyType = Literal["purchase", "vehicle", "investment", "child_plan", "tax", "career_shock"]
VehiclePurchaseTimingMode = Literal["auto_sequence", "parallel", "manual_month", "not_planned"]
ScheduledExpenseFrequency = Literal["monthly", "annual_once", "one_time"]
ScheduledExpenseTimingMode = Literal["fixed_month", "flexible_range"]
ScheduledExpenseCategory = Literal["general", "medical"]
RentPaymentMode = Literal["cash", "provident"]
RentPaymentFrequency = Literal["monthly", "quarterly"]
ChildPlanTimingMode = Literal["after_first_home", "manual_month", "not_planned"]
ChildExpenseStrategyMode = Literal["balanced", "conservative", "quality", "manual"]
SpecialDeductionType = Literal[
    "child_education",
    "infant_care",
    "continuing_education",
    "serious_illness",
    "housing_rent",
    "mortgage_interest",
    "personal_pension",
]
SpecialDeductionSettlementMode = Literal["monthly_withholding", "annual_settlement"]
PersonalPensionContributionMode = Literal["none", "auto_tax_optimal", "fixed_monthly", "fixed_annual"]
PersonalPensionOpenMode = Literal["auto_tax_optimal", "manual", "none"]
PersonalPensionReturnMode = Literal["auto_lifecycle", "manual"]
PersonalPensionWithdrawalMode = Literal["auto_safe", "monthly_annuity", "fixed_monthly", "lump_sum"]
PersonalPensionTaxDeductionMode = Literal["monthly_withholding", "annual_settlement"]
PersonalPensionEarlyWithdrawalReason = Literal[
    "none",
    "total_disability",
    "settled_abroad",
    "major_medical_expense",
    "long_unemployment",
    "minimum_living_allowance",
]
PersonalPensionProductLiquidityMode = Literal["daily_liquid", "periodic", "locked_until_maturity"]
TaxStrategyStatus = Literal["auto_enabled", "manual_enabled", "available", "not_applicable", "conflict"]
TaxStrategySource = Literal["backend_auto", "strategy_auto", "manual", "event"]
TaxStrategyTimelineCategory = Literal[
    "deduction_assignment",
    "deduction_switch",
    "personal_pension",
    "bonus_tax",
    "investment_tax",
    "annual_settlement",
    "manual_override",
]


def default_retirement_category_for_sex(sex: str, fallback: RetirementCategory = "male_60") -> RetirementCategory:
    if sex == "male":
        return "male_60"
    if sex == "female":
        return "female_55"
    return fallback


def normalize_retirement_category_for_sex(
    category: str | None,
    sex: str | None,
    fallback: RetirementCategory = "male_60",
) -> RetirementCategory:
    if sex == "male":
        return "male_60"
    if sex == "female":
        return "female_50" if category == "female_50" else "female_55"
    if category in {"male_60", "female_55", "female_50"}:
        return category
    return fallback


class IncomeMember(BaseModel):
    name: str = "成员 1"
    sex: MemberSex = "unspecified"
    family_join_month: str = "2026-07"
    birth_month: str = ""
    current_age: int = Field(30, ge=0, le=120)
    retirement_category: RetirementCategory = "male_60"
    social_security_months: int = Field(0, ge=0)
    income_tax_months: int = Field(0, ge=0)
    existing_home_count: int = Field(0, ge=0, le=10)
    existing_mortgage_count: int = Field(0, ge=0, le=10)
    initial_cash_balance: float = Field(0, ge=0)
    initial_investments: float = Field(0, ge=0)
    initial_other_asset_value: float = Field(0, ge=0)
    initial_other_debt_balance: float = Field(0, ge=0)
    provident_fund_balance: float = Field(0, ge=0)
    provident_account_enabled: bool = True
    provident_account_open_month: str = ""
    pension_account_balance: float = Field(0, ge=0)
    pension_account_enabled: bool = True
    pension_account_open_month: str = ""
    medical_account_balance: float = Field(0, ge=0)
    medical_account_enabled: bool = True
    medical_account_open_month: str = ""
    personal_pension_account_enabled: bool = False
    personal_pension_participation_eligible: bool = False
    personal_pension_account_balance: float = Field(0, ge=0)
    personal_pension_open_mode: PersonalPensionOpenMode = "none"
    personal_pension_account_open_month: str = ""
    personal_pension_contribution_mode: PersonalPensionContributionMode = "none"
    personal_pension_tax_deduction_mode: PersonalPensionTaxDeductionMode = "monthly_withholding"
    personal_pension_monthly_contribution: float = Field(0, ge=0)
    personal_pension_annual_contribution_target: float = Field(0, ge=0)
    personal_pension_auto_annual_contribution_schedule: dict[str, float] = Field(default_factory=dict)
    personal_pension_contribution_month: int = Field(12, ge=1, le=12)
    personal_pension_contribution_start_month: str = ""
    personal_pension_contribution_end_month: str | None = None
    personal_pension_auto_suspend_for_cash_safety: bool = True
    personal_pension_cash_reserve_months: int = Field(6, ge=0, le=36)
    personal_pension_return_mode: PersonalPensionReturnMode = "auto_lifecycle"
    personal_pension_annual_return: float = Field(0.025, ge=-0.5, le=0.5)
    personal_pension_post_retirement_annual_return: float = Field(0.015, ge=-0.5, le=0.5)
    personal_pension_withdrawal_mode: PersonalPensionWithdrawalMode = "auto_safe"
    personal_pension_withdrawal_start_month: str = ""
    personal_pension_early_withdrawal_reason: PersonalPensionEarlyWithdrawalReason = "none"
    personal_pension_early_withdrawal_month: str = ""
    personal_pension_withdrawal_years: int = Field(20, ge=1, le=40)
    personal_pension_fixed_monthly_withdrawal: float = Field(0, ge=0)
    personal_pension_product_liquidity_mode: PersonalPensionProductLiquidityMode = "daily_liquid"
    personal_pension_redemption_delay_months: int = Field(0, ge=0, le=120)
    personal_pension_monthly_redeemable_ratio: float = Field(1, ge=0, le=1)
    personal_pension_redemption_fee_rate: float = Field(0, ge=0, le=0.5)
    monthly_salary_gross: float = Field(0, ge=0)
    annual_bonus: float = Field(0, ge=0)
    monthly_non_taxable_income: float = Field(0, ge=0)
    monthly_extra_cash_expense: float = Field(0, ge=0)
    monthly_social_insurance: float = Field(0, ge=0)
    monthly_housing_fund: float = Field(0, ge=0)
    housing_fund_personal_rate: float = Field(0.12, ge=0, le=0.12)
    housing_fund_employer_rate: float = Field(0.12, ge=0, le=0.12)
    monthly_special_additional_deduction: float = Field(0, ge=0)
    other_annual_deductions: float = Field(0, ge=0)
    other_annual_taxable_income: float = Field(0, ge=0)
    employment_start_date: str = "2026-07-01"
    bonus_tax_method: BonusTaxMethod = "best"
    income_stages: list["IncomeStageData"] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_default_income_stage_when_omitted(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        data["sex"] = data.get("sex") or "unspecified"
        data["retirement_category"] = normalize_retirement_category_for_sex(
            data.get("retirement_category"),
            data["sex"],
        )
        if data.get("income_stages") is not None:
            return data
        data["income_stages"] = [
            {
                "name": "当前收入",
                "stage_kind": "salary",
                "start_date": data.get("employment_start_date") or "2026-07-01",
                "monthly_salary_gross": data.get("monthly_salary_gross", 0),
                "annual_bonus": data.get("annual_bonus", 0),
                "annual_bonus_payout_mode": data.get("annual_bonus_payout_mode", "lump_sum"),
                "annual_bonus_payout_month": 4,
                "provident_account_management_center": "beijing_municipal",
                "monthly_freelance_income": 0,
                "monthly_non_taxable_income": data.get("monthly_non_taxable_income", 0),
                "monthly_extra_cash_expense": 0,
                "monthly_social_insurance": data.get("monthly_social_insurance", 0),
                "monthly_housing_fund": data.get("monthly_housing_fund", 0),
                "housing_fund_personal_rate": data.get("housing_fund_personal_rate", 0.12),
                "housing_fund_employer_rate": data.get("housing_fund_employer_rate", 0.12),
                "monthly_special_additional_deduction": data.get("monthly_special_additional_deduction", 0),
                "other_annual_deductions": data.get("other_annual_deductions", 0),
                "other_annual_taxable_income": data.get("other_annual_taxable_income", 0),
                "bonus_tax_method": data.get("bonus_tax_method", "best"),
                "payroll_contributions_enabled": True,
            }
        ]
        return data

class IncomeStageData(BaseModel):
    name: str = "当前收入"
    stage_kind: IncomeStageKind = "salary"
    start_date: str = "2026-07-01"
    end_date: str | None = None
    provident_account_management_center: ProvidentAccountManagementCenter = "beijing_municipal"
    monthly_salary_gross: float = Field(0, ge=0)
    annual_bonus_months: float = Field(0, ge=0, le=60)
    annual_bonus_payout_mode: AnnualBonusPayoutMode = "lump_sum"
    annual_bonus_payout_month: int = Field(4, ge=1, le=12)
    annual_bonus_earning_start_month: int | None = Field(None, ge=1, le=12)
    annual_bonus_earning_end_month: int | None = Field(None, ge=1, le=12)
    monthly_freelance_income: float = Field(0, ge=0)
    freelance_tax_mode: FreelanceTaxMode = "labor_remuneration"
    monthly_non_taxable_income: float = Field(0, ge=0)
    monthly_extra_cash_expense: float = Field(0, ge=0)
    monthly_social_insurance: float = Field(0, ge=0)
    monthly_housing_fund: float = Field(0, ge=0)
    housing_fund_personal_rate: float = Field(0.12, ge=0, le=0.12)
    housing_fund_employer_rate: float = Field(0.12, ge=0, le=0.12)
    monthly_special_additional_deduction: float = Field(0, ge=0)
    other_annual_deductions: float = Field(0, ge=0)
    other_annual_taxable_income: float = Field(0, ge=0)
    bonus_tax_method: BonusTaxMethod = "best"
    payroll_contributions_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_bonus_amount_to_salary_months(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if normalized.get("annual_bonus_months") is None:
            try:
                salary = max(0.0, float(normalized.get("monthly_salary_gross") or 0))
                amount = max(0.0, float(normalized.get("annual_bonus") or 0))
            except (TypeError, ValueError):
                salary = 0.0
                amount = 0.0
            normalized["annual_bonus_months"] = round(amount / salary, 1) if salary > 0 else 0.0
        else:
            try:
                normalized["annual_bonus_months"] = round(max(0.0, float(normalized["annual_bonus_months"])), 1)
            except (TypeError, ValueError):
                normalized["annual_bonus_months"] = 0.0
        normalized.pop("annual_bonus", None)
        return normalized

    @property
    def annual_bonus(self) -> float:
        return self.monthly_salary_gross * self.annual_bonus_months


class CareerShockMemberSetting(BaseModel):
    member_name: str = "成员 1"
    enabled: bool = False
    layoff_age: int = Field(35, ge=18, le=80)
    retirement_age: int = Field(63, ge=50, le=70)
    freelance_income_monthly: float = Field(0, ge=0)
    pension_monthly: float = Field(0, ge=0)
    auto_pension_monthly: bool = True
    birth_month: str = ""
    current_age: int = Field(30, ge=0, le=120)


class CareerShockData(BaseModel):
    enabled: bool = False
    member_settings: list[CareerShockMemberSetting] = Field(default_factory=list)
    auto_unemployment_benefit: bool = True
    auto_self_social_insurance: bool = True
    auto_flexible_housing_fund: bool = True
    unemployment_benefit_months: int = Field(24, ge=0, le=24)
    unemployment_benefit_monthly: float = Field(0, ge=0)
    self_social_insurance_monthly: float = Field(0, ge=0)
    self_housing_fund_monthly: float = Field(0, ge=0)


class VehicleFinancingOptionData(BaseModel):
    id: str = "three_year_two_year_subsidy"
    name: str = "三年前两年贴息"
    enabled: bool = True
    financing_type: Literal["dealer_subsidy", "standard", "bank_loan", "cash_only"] = "dealer_subsidy"
    total_months: int = Field(36, ge=1, le=120)
    interest_free_months: int = Field(24, ge=0, le=120)
    later_annual_rate: float = Field(0.0199, ge=0, le=0.5)
    min_down_payment_ratio: float = Field(0.30, ge=0, le=1)
    max_down_payment_ratio: float = Field(1.0, ge=0, le=1)
    prepayment_allowed: bool = True
    prepayment_allowed_after_month: int = Field(12, ge=1, le=120)
    prepayment_policy_note: str = "以合同为准；常见车贷需要满一定期数后才允许提前还本。"
    notes: str = ""

    @model_validator(mode="after")
    def validate_down_payment_bounds(self) -> "VehicleFinancingOptionData":
        if self.max_down_payment_ratio < self.min_down_payment_ratio:
            raise ValueError("max_down_payment_ratio must be greater than or equal to min_down_payment_ratio")
        return self


class VehicleIndicatorApplicantData(BaseModel):
    enabled: bool = True
    name: str = "家庭申请人"
    relationship: Literal["main", "spouse", "child", "parent", "parent_in_law", "other"] = "other"
    generation: Literal["self_generation", "child_generation", "parent_generation"] = "self_generation"
    eligibility_type: Literal[
        "beijing_household",
        "beijing_work_residence_permit",
        "beijing_residence_permit_social_tax",
        "active_military_or_police",
        "hongkong_macao_taiwan_foreign",
        "unknown",
    ] = "unknown"
    has_valid_driver_license: bool = False
    has_no_beijing_vehicle: bool = True
    family_application_start_month: str = ""
    personal_indicator_history_type: Literal["none", "ordinary_lottery", "new_energy_queue", "both"] = "none"
    ordinary_lottery_steps: int = Field(0, ge=0, le=200)
    new_energy_queue_start_month: str = ""
    personal_history_points_override: float | None = Field(None, ge=0)
    only_for_indicator_scoring: bool = True
    notes: str = ""


class VehiclePlanData(BaseModel):
    enabled: bool = False
    name: str = "车辆计划"
    selected_strategy_variant: str = "手动设置"
    candidate_vehicles: list["VehiclePlanData"] = Field(default_factory=list)
    financing_options: list[VehicleFinancingOptionData] = Field(default_factory=list)
    selected_financing_option_id: str = ""
    selected_financing_option_name: str = ""
    selected_financing_type: str = ""
    selected_financing_min_down_payment_ratio: float = Field(0.0, ge=0, le=1)
    selected_financing_max_down_payment_ratio: float = Field(1.0, ge=0, le=1)
    selected_financing_prepayment_allowed: bool = True
    selected_financing_prepayment_policy_note: str = ""
    energy_type: Literal["pure_electric", "plug_in_hybrid", "range_extended", "fuel_cell", "fuel"] = "pure_electric"
    new_energy_catalog_eligible: bool = True
    beijing_license_indicator_status: Literal[
        "unknown",
        "already_have",
        "family_new_energy_pending",
        "personal_new_energy_pending",
        "ordinary_indicator_pending",
        "not_eligible",
    ] = "unknown"
    beijing_indicator_expected_delay_months: int = Field(0, ge=0, le=240)
    license_plate_rental_enabled: bool = False
    license_plate_rental_upfront_fee: float = Field(20000, ge=0)
    license_plate_rental_term_months: int = Field(36, ge=1, le=120)
    license_plate_rental_renewal_fee: float = Field(20000, ge=0)
    license_plate_rental_renewal_term_months: int = Field(36, ge=1, le=120)
    license_plate_rental_after_term_mode: Literal["switch_to_own_indicator", "renew_until_own_indicator"] = "renew_until_own_indicator"
    beijing_family_indicator_score_enabled: bool = False
    beijing_family_indicator_application_start_month: str = ""
    beijing_family_indicator_applicants: list[VehicleIndicatorApplicantData] = Field(default_factory=list)
    beijing_family_indicator_generations: int = Field(1, ge=1, le=3)
    beijing_family_indicator_has_spouse: bool = True
    beijing_family_indicator_main_points: float = Field(2, ge=0)
    beijing_family_indicator_spouse_points: float = Field(1, ge=0)
    beijing_family_indicator_other_applicant_count: int = Field(0, ge=0, le=20)
    beijing_family_indicator_other_points_total: float = Field(0, ge=0)
    beijing_family_indicator_application_years: int = Field(0, ge=0, le=50)
    beijing_family_indicator_current_cutoff_score: float = Field(36, ge=0)
    beijing_family_indicator_cutoff_score_annual_change: float = Field(0, ge=-20, le=20)
    beijing_family_indicator_last_config_year: int = Field(2026, ge=2020, le=2100)
    beijing_family_indicator_annual_quota: int = Field(119200, ge=0)
    vehicle_vessel_tax_annual_override: float | None = Field(None, ge=0)
    planning_goal_id: str = ""
    planning_sequence: int = Field(1, ge=1, le=50)
    purchase_timing_mode: VehiclePurchaseTimingMode = "auto_sequence"
    depends_on_goal_id: str = ""
    after_previous_event_delay_months: int = Field(0, ge=0, le=240)
    manual_purchase_delay_months: int = Field(0, ge=0, le=600)
    planning_window_start_month: str = ""
    planning_window_end_month: str = ""
    total_price: float = Field(0, ge=0)
    down_payment_ratio: float = Field(0.50, ge=0, le=1)
    down_payment: float = Field(0, ge=0)
    purchase_delay_months: int = Field(0, ge=0, le=120)
    total_months: int = Field(60, ge=1, le=120)
    interest_free_months: int = Field(24, ge=0, le=120)
    later_annual_rate: float = Field(0.0199, ge=0, le=0.5)
    loan_prepayment_enabled: bool = False
    loan_prepayment_start_month: int = Field(1, ge=1, le=120)
    loan_prepayment_allowed_after_month: int = Field(12, ge=1, le=120)
    loan_prepayment_monthly_amount: float = Field(0, ge=0)
    loan_prepayment_strategy_type: str = "none"
    loan_prepayment_lump_sum_month: int = Field(0, ge=0, le=120)
    loan_prepayment_lump_sum_amount: float = Field(0, ge=0)
    current_month_index: int = Field(1, ge=1, le=120)
    saving_start_date: str = "2026-07-01"
    monthly_operating_cost: float = Field(0, ge=0)
    no_car_monthly_commute_cost: float = Field(0, ge=0)
    annual_mileage_km: float = Field(0, ge=0, le=100000)
    electricity_kwh_per_100km: float = Field(14, ge=0, le=50)
    electricity_price_per_kwh: float = Field(0.8, ge=0, le=5)
    monthly_parking_cost: float = Field(0, ge=0)
    annual_maintenance_cost: float = Field(0, ge=0)
    annual_maintenance_growth_rate: float = Field(0.03, ge=0, le=0.2)
    annual_insurance_rate: float = Field(0.018, ge=0, le=0.2)
    annual_insurance_min: float = Field(0, ge=0)
    annual_insurance_growth_rate: float = Field(0.02, ge=0, le=0.2)
    depreciation_years: int = Field(8, ge=1, le=20)
    vehicle_service_years: int = Field(10, ge=1, le=30)
    vehicle_retirement_mileage_km: float = Field(600000, ge=0, le=1000000)
    happiness_score: float = Field(6.5, ge=0, le=10)
    notes: str = ""


class CarPlanData(VehiclePlanData):
    vehicle_plans: list[VehiclePlanData] = Field(default_factory=list)


class PropertyPurchaseGoalData(BaseModel):
    name: str = "购房需求"
    scenario_id: str = ""
    priority: int = Field(1, ge=1, le=20)
    enabled: bool = True
    intended_use: Literal["self_use", "improvement", "investment", "other"] = "self_use"
    planning_mode: Literal["after_previous_purchase", "parallel"] = "after_previous_purchase"
    depends_on_goal_id: str = ""
    after_previous_purchase_delay_months: int = Field(0, ge=0, le=240)
    earliest_purchase_delay_months: int = Field(0, ge=0, le=600)
    planning_window_start_month: str = ""
    planning_window_end_month: str = ""
    notes: str = ""


class PlanningGoalData(BaseModel):
    schema_version: int = Field(55, ge=1)
    goal_type: PlanningGoalType = "home"
    name: str = "规划目标"
    enabled: bool = True
    priority: int = Field(1, ge=1, le=100)
    timing_mode: PlanningTimingMode = "auto_sequence"
    earliest_purchase_month: str = ""
    earliest_purchase_delay_months: int = Field(0, ge=0, le=600)
    planning_window_start_month: str = ""
    planning_window_end_month: str = ""
    depends_on_goal_id: str = ""
    delay_after_dependency_months: int = Field(0, ge=0, le=240)
    allow_parallel: bool = False
    selected_strategy_id: str = ""
    target_params: dict[str, Any] = Field(default_factory=dict)
    financing_preferences: dict[str, Any] = Field(default_factory=dict)
    holding_cost_params: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class PlanningGoalRecord(BaseModel):
    id: str
    household_id: str | None = None
    goal_type: PlanningGoalType
    data: PlanningGoalData
    created_at: datetime
    updated_at: datetime


class PlanningGoalCreate(BaseModel):
    household_id: str | None = None
    data: PlanningGoalData


class ResolvedPlanningGoal(BaseModel):
    id: str
    household_id: str | None = None
    goal_type: PlanningGoalType
    name: str
    planning_group_id: str = ""
    planning_group_name: str = ""
    planning_group_size: int = Field(1, ge=1)
    planning_group_member_ids: list[str] = Field(default_factory=list)
    target_amount: float = 0.0
    funding_mode: str = ""
    enabled: bool = True
    priority: int
    sequence_index: int
    timing_mode: PlanningTimingMode
    normalized_timing_mode: PlanningTimingMode
    depends_on_goal_id: str = ""
    depends_on_goal_name: str = ""
    delay_after_dependency_months: int = 0
    allow_parallel: bool = False
    earliest_purchase_month: str = ""
    earliest_purchase_delay_months: int = 0
    planning_window_start_month: str = ""
    planning_window_end_month: str = ""
    resolved_not_before_month: int = 0
    resolved_window_start_month: int = 0
    resolved_window_end_month: int | None = None
    dependency_warning: str = ""
    explanation: str = ""


class PlanningSequenceResult(BaseModel):
    base_month: str = ""
    goals: list[ResolvedPlanningGoal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CalculationContextGoalSnapshot(BaseModel):
    id: str
    goal_type: PlanningGoalType
    name: str
    planning_group_id: str = ""
    planning_group_name: str = ""
    planning_group_size: int = Field(1, ge=1)
    planning_group_member_ids: list[str] = Field(default_factory=list)
    target_amount: float = 0.0
    funding_mode: str = ""
    enabled: bool = True
    priority: int
    sequence_index: int
    normalized_timing_mode: PlanningTimingMode = "auto_sequence"
    depends_on_goal_id: str = ""
    depends_on_goal_name: str = ""
    delay_after_dependency_months: int = 0
    resolved_not_before_month: int = 0
    resolved_window_start_month: int = 0
    resolved_window_end_month: int | None = None
    explanation: str = ""
    dependency_warning: str = ""


class CalculationContextCoreObjectSnapshot(BaseModel):
    id: str
    object_type: CoreObjectType
    category: CoreObjectCategory
    name: str
    source: CoreObjectSource | Literal[""] = ""
    owner_key: str = ""
    reference_id: str = ""
    member_name: str = ""
    current_balance: float = 0.0
    monthly_flow: float = 0.0


class CalculationContextSnapshot(BaseModel):
    base_month: str = ""
    household_id: str = ""
    scenario_id: str = ""
    current_goal_id: str = ""
    current_goal_name: str = ""
    current_goal_resolved_not_before_month: int = 0
    current_goal_normalized_timing_mode: PlanningTimingMode | Literal[""] = ""
    planning_goal_ids: list[str] = Field(default_factory=list)
    planning_goals: list[CalculationContextGoalSnapshot] = Field(default_factory=list)
    core_object_ids: list[str] = Field(default_factory=list)
    core_objects: list[CalculationContextCoreObjectSnapshot] = Field(default_factory=list)
    planning_goal_fingerprint: str = ""
    core_object_fingerprint: str = ""
    resolved_goal_count: int = 0
    core_object_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class PhasedLoanData(BaseModel):
    borrower: str = "成员 1"
    name: str = "已有贷款"
    loan_type: Literal["mortgage", "car", "education", "consumer", "other"] = "other"
    principal: float = Field(0, ge=0)
    annual_rate: float = Field(0.028, ge=0, le=0.2)
    repayment_method: RepaymentMethod = "equal_installment"
    remaining_months: int = Field(120, ge=1, le=360)
    interest_start_month: str = "2026-07"
    interest_only_until: str = "2028-07"
    prepayment_mode: ExistingLoanPrepaymentMode = "none"
    prepayment_start_month: int = Field(1, ge=1, le=360)
    prepayment_allowed_after_month: int = Field(1, ge=1, le=360)
    prepayment_monthly_amount: float = Field(0, ge=0)


class PhasedLoanSummary(BaseModel):
    borrower: str
    name: str
    principal: float
    annual_rate: float
    repayment_method: RepaymentMethod
    remaining_months: int
    interest_start_month: str
    interest_only_until: str
    phase: str
    current_monthly_payment: float
    current_extra_principal_payment: float = 0.0
    prepayment_mode: ExistingLoanPrepaymentMode = "none"
    prepayment_start_month: int = 1
    prepayment_allowed_after_month: int = 1
    prepayment_monthly_amount: float = 0.0


class ExistingLoanVisualizationDetail(BaseModel):
    name: str
    borrower: str
    loan_type: Literal["mortgage", "car", "education", "consumer", "other"]
    phase: str
    balance: float
    monthly_payment: float
    extra_principal_payment: float = 0.0


class ScheduledExpenseData(BaseModel):
    name: str = "计划支出"
    monthly_amount: float = Field(0, ge=0)
    frequency: ScheduledExpenseFrequency = "monthly"
    one_time_timing_mode: ScheduledExpenseTimingMode = "fixed_month"
    annual_occurrence_month: int = Field(1, ge=1, le=12)
    start_month: str = "2026-07"
    end_month: str | None = None
    expense_category: ScheduledExpenseCategory = "general"
    medical_account_payable: bool = False
    tax_deductible_elderly_care: bool = False
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_medical_payment_scope(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        next_data = dict(data)
        category = next_data.get("expense_category")
        if category not in {"general", "medical"}:
            category = "medical" if bool(next_data.get("medical_account_payable", False)) else "general"
        next_data["expense_category"] = category
        if category != "medical":
            next_data["medical_account_payable"] = False
        return next_data


class DailyExpenseStageData(BaseModel):
    name: str = "日常支出阶段"
    start_month: str = "2026-07"
    end_month: str | None = None
    base_living_expense: float = Field(0, ge=0)


class RentExpenseStageData(BaseModel):
    name: str = "租房支出阶段"
    start_month: str = "2026-07"
    end_month: str | None = None
    rent_amount: float = Field(0, ge=0)
    broker_fee_months: float = Field(1, ge=0, le=12)
    broker_fee_amount: float | None = Field(default=None, ge=0)
    service_fee_first_year_rate: float = Field(0.09, ge=0, le=1)
    service_fee_later_year_rate: float = Field(0.06, ge=0, le=1)
    rent_payment_mode: RentPaymentMode = "cash"
    rent_payment_frequency: RentPaymentFrequency = "monthly"


class ElderlyDependentData(BaseModel):
    member_name: str = "成员 1"
    relationship_label: str = "直系亲属老人"
    birth_month: str = ""
    is_only_child: bool = False
    shared_monthly_deduction: float = Field(1500, ge=0, le=3000)


class ChildPlanData(BaseModel):
    planning_goal_id: str = ""
    name: str = "子女计划"
    enabled: bool = True
    timing_mode: ChildPlanTimingMode = "after_first_home"
    expense_strategy_mode: ChildExpenseStrategyMode = "balanced"
    planned_birth_month: str = ""
    planned_birth_start_month: str = ""
    planned_birth_end_month: str = ""
    birth_month: str = ""
    tax_deduction_owner: str = ""
    education_start_month: str = ""
    preparation_months_before_birth: int = Field(6, ge=0, le=24)
    pregnancy_months_before_birth: int = Field(9, ge=0, le=12)
    monthly_preparation_cost: float = Field(1500, ge=0)
    monthly_pregnancy_cost: float = Field(3000, ge=0)
    birth_medical_cost: float = Field(30000, ge=0)
    postpartum_recovery_cost: float = Field(40000, ge=0)
    initial_baby_supplies_cost: float = Field(20000, ge=0)
    monthly_childcare_cost_before_kindergarten: float = Field(4500, ge=0)
    monthly_kindergarten_cost: float = Field(5000, ge=0)
    monthly_primary_secondary_cost: float = Field(6000, ge=0)
    monthly_higher_education_cost: float = Field(8000, ge=0)
    kindergarten_entry_cost: float = Field(10000, ge=0)
    primary_school_entry_cost: float = Field(15000, ge=0)
    higher_education_entry_cost: float = Field(50000, ge=0)
    notes: str = ""


class SpecialDeductionItemData(BaseModel):
    deduction_type: SpecialDeductionType = "housing_rent"
    name: str = "专项附加扣除"
    enabled: bool = False
    member_name: str = ""
    spouse_member_name: str = ""
    child_name: str = ""
    start_month: str = "2026-07"
    end_month: str | None = None
    monthly_amount: float = Field(0, ge=0)
    annual_amount: float = Field(0, ge=0)
    settlement_mode: SpecialDeductionSettlementMode = "monthly_withholding"
    is_first_home_loan: bool = False
    claimed_months_used: int = Field(0, ge=0, le=240)
    notes: str = ""


class InvestmentTaxProfileData(BaseModel):
    deposit_interest_tax_rate: float = Field(0, ge=0, le=1)
    fund_dividend_tax_rate: float = Field(0, ge=0, le=1)
    stock_dividend_short_holding_tax_rate: float = Field(0.20, ge=0, le=1)
    stock_dividend_long_holding_tax_rate: float = Field(0, ge=0, le=1)
    bond_interest_tax_rate: float = Field(0, ge=0, le=1)
    overseas_asset_tax_rate: float = Field(0, ge=0, le=1)
    deposit_interest_ratio: float = Field(0, ge=0, le=1)
    fund_dividend_ratio: float = Field(0, ge=0, le=1)
    stock_dividend_short_ratio: float = Field(0, ge=0, le=1)
    stock_dividend_long_ratio: float = Field(0, ge=0, le=1)
    bond_interest_ratio: float = Field(0, ge=0, le=1)
    overseas_asset_ratio: float = Field(0, ge=0, le=1)


class AccountCalibrationData(BaseModel):
    enabled: bool = True
    month: str = "2026-07"
    calibration_scope: AccountCalibrationScope = "account"
    target: AccountCalibrationTarget = "cash"
    amount: float = Field(0, ge=0)
    member_name: str = ""
    reference_name: str = ""
    source_id: str = ""
    source_category: str = ""
    source_title: str = ""
    note: str = ""


class CoreObjectData(BaseModel):
    schema_version: int = Field(48, ge=1)
    object_type: CoreObjectType
    category: CoreObjectCategory
    name: str
    enabled: bool = True
    member_name: str = ""
    owner_key: str = ""
    reference_id: str = ""
    source: CoreObjectSource = "household"
    current_balance: float = 0.0
    monthly_flow: float = 0.0
    annual_rate: float = 0.0
    start_month: str = ""
    end_month: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoreObjectRecord(BaseModel):
    id: str
    household_id: str | None = None
    object_type: CoreObjectType
    category: CoreObjectCategory
    data: CoreObjectData
    created_at: datetime
    updated_at: datetime


class HouseholdData(BaseModel):
    schema_version: int = Field(46, ge=1)
    name: str = "未命名家庭"
    monthly_income: float = Field(0, ge=0)
    monthly_expense: float = Field(0, ge=0)
    monthly_debt_payment: float = Field(0, ge=0)
    cash_account_balance: float = Field(0, ge=0)
    investments: float = Field(0, ge=0)
    quant_investment_data_version: int = Field(0, ge=0)
    income_projection_year: int = Field(2027, ge=2024, le=2050)
    monthly_rent_from_housing_fund: float = Field(0, ge=0)
    family_provident_support_enabled: bool = False
    family_provident_support_label: str = "亲属异地公积金首付支持"
    family_down_payment_support_mode: str = "provident"
    family_savings_support_amount: float = Field(0, ge=0)
    family_provident_initial_balance: float = Field(0, ge=0)
    family_provident_monthly_salary: float = Field(0, ge=0)
    family_provident_total_rate: float = Field(0.24, ge=0, le=0.5)
    major_goal_tradeoff_mode: Literal["auto", "manual"] = "auto"
    major_goal_timing_preference: float = Field(0.5, ge=0, le=1)
    investment_plan_name: str = "conservative_monthly_investment"
    investment_risk_level: str = "conservative"
    monthly_investment_amount: float = Field(0, ge=0)
    investment_cash_reserve_months: float = Field(6, ge=0, le=36)
    investment_equity_ratio: float = Field(0.25, ge=0, le=1)
    investment_bond_ratio: float = Field(0.45, ge=0, le=1)
    investment_cash_ratio: float = Field(0.30, ge=0, le=1)
    investment_auto_rebalance: bool = True
    investment_buy_fee_rate: float = Field(0.0015, ge=0, le=0.05)
    investment_sell_fee_rate: float = Field(0.005, ge=0, le=0.05)
    investment_taxable_return_ratio: float = Field(0, ge=0, le=1)
    investment_return_tax_rate: float = Field(0, ge=0, le=1)
    investment_tax_profile: InvestmentTaxProfileData = Field(default_factory=InvestmentTaxProfileData)
    required_liquidity_months: float = Field(6, ge=0, le=36)
    borrower_age: int = Field(30, ge=18, le=68)
    borrower_member_index: int = Field(0, ge=0, le=20)
    career_shock: CareerShockData = Field(default_factory=CareerShockData)
    career_shock_applied: bool = False
    car_plan: CarPlanData = Field(default_factory=CarPlanData)
    property_goals: list[PropertyPurchaseGoalData] = Field(default_factory=list)
    phased_loans: list[PhasedLoanData] = Field(default_factory=list)
    scheduled_expenses: list[ScheduledExpenseData] = Field(default_factory=list)
    daily_expense_stages: list[DailyExpenseStageData] = Field(default_factory=list)
    rent_expense_stages: list[RentExpenseStageData] = Field(default_factory=list)
    elderly_dependents: list[ElderlyDependentData] = Field(default_factory=list)
    child_plans: list[ChildPlanData] = Field(default_factory=list)
    special_deductions: list[SpecialDeductionItemData] = Field(default_factory=list)
    account_calibrations: list[AccountCalibrationData] = Field(default_factory=list)
    existing_home_count: int = Field(0, ge=0, le=10)
    existing_mortgage_count: int = Field(0, ge=0, le=10)
    has_beijing_hukou: bool = True
    social_security_months: int = Field(0, ge=0)
    child_count: int = Field(
        0,
        ge=0,
        le=10,
        description="截至当前月份已经出生的子女数；未来养娃规划目标不计入当前家庭资格参数。",
    )
    provident_fund_balance: float = Field(0, ge=0)
    provident_fund_monthly_deposit: float = Field(0, ge=0)
    members: list[IncomeMember] = Field(
        default_factory=lambda: [
            IncomeMember(name="成员 1"),
        ]
    )
    notes: str = ""


class HouseholdRecord(BaseModel):
    id: str
    data: HouseholdData
    created_at: datetime
    updated_at: datetime


class HouseholdCreate(BaseModel):
    data: HouseholdData


class ScenarioData(BaseModel):
    schema_version: int = Field(39, ge=1)
    planning_goal_id: str = ""
    name: str = "示例房源（请修改）"
    enabled: bool = True
    purchase_sequence: int = Field(1, ge=1, le=20)
    purchase_planning_mode: Literal["after_previous_purchase", "parallel"] = "after_previous_purchase"
    depends_on_goal_id: str = ""
    after_previous_purchase_delay_months: int = Field(0, ge=0, le=240)
    district: str = "未设置"
    ring_area: str = "未设置"
    property_type: str = "二手房"
    green_building_level: GreenBuildingLevel = "none"
    prefab_building_level: PrefabBuildingLevel = "none"
    is_ultra_low_energy_building: bool = False
    building_age_years: int = Field(0, ge=0, le=100)
    building_structure: BuildingStructure = "unknown"
    is_old_community_renovated: bool = False
    remaining_land_use_years: int | None = Field(None, ge=0, le=70)
    total_price: float = Field(3000000, ge=0)
    area_sqm: float = Field(80, ge=0)
    down_payment_amount: float = Field(0, ge=0)
    commercial_loan_amount: float = Field(0, ge=0)
    provident_loan_amount: float = Field(0, ge=0)
    manual_purchase_delay_months: int = Field(0, ge=0, le=360)
    planning_window_start_month: str = ""
    planning_window_end_month: str = ""
    micro_commercial_loan_ratio: float = Field(0, ge=0, le=1)
    commercial_rate: float = Field(0.035, ge=0, le=0.2)
    loan_years: int = Field(25, ge=1, le=30)
    repayment_method: RepaymentMethod = "equal_installment"
    loan_repayment_strategy_mode: Literal["auto", "manual"] = "auto"
    commercial_repayment_method: RepaymentMethod = "equal_installment"
    provident_repayment_method: RepaymentMethod = "equal_installment"
    commercial_prepayment_mode: CommercialPrepaymentMode = "auto"
    commercial_prepayment_enabled: bool = False
    commercial_prepayment_start_month: int = Field(1, ge=1, le=360)
    commercial_prepayment_allowed_after_month: int = Field(12, ge=1, le=360)
    commercial_prepayment_monthly_amount: float = Field(0, ge=0)
    provident_account_repayment_strategy: ProvidentAccountRepaymentStrategy = "auto"
    provident_account_repayment_switch_enabled: bool = False
    provident_account_repayment_switch_after_month: int = Field(12, ge=1, le=360)
    provident_account_repayment_switch_to_strategy: ProvidentAccountRepaymentSwitchTarget = "semiannual_principal_offset"
    broker_fee_rate: float = Field(0.022, ge=0, le=0.2)
    seller_tax_pass_through_enabled: bool = False
    seller_tax_pass_through_rate: float = Field(0, ge=0, le=0.2)
    seller_tax_pass_through_amount: float = Field(0, ge=0)
    renovation_cost: float = Field(
        0,
        ge=0,
        exclude=True,
        description="由装修规划目标投影的计算期内部字段，不属于房源持久化数据",
    )
    renovation_funding_mode: RenovationFundingMode = Field(
        "after_goal_saving",
        exclude=True,
        description="由装修规划目标投影的计算期内部字段",
    )
    renovation_goal_id: str = Field("", exclude=True)
    renovation_delay_after_purchase_months: int = Field(0, ge=0, le=240, exclude=True)
    moving_and_misc_cost: float = Field(50000, ge=0)
    annual_investment_return: float = Field(0.025, ge=-0.5, le=0.5)
    investment_withdrawal_mode: InvestmentWithdrawalMode = "auto"
    investment_min_balance_after_purchase: float = Field(0, ge=0)
    happiness_score: float = Field(7.0, ge=0, le=10)
    commute_score: float = Field(7.0, ge=0, le=10)
    school_score: float = Field(6.0, ge=0, le=10)
    liquidity_priority_score: float = Field(7.0, ge=0, le=10)
    notes: str = ""
    selected_purchase_plan_variant: str = ""
    valuation_monitoring_enabled: bool = False
    valuation_asset_status: Literal["planned", "owned"] = "planned"
    valuation_interval_months: int = Field(1, ge=1, le=24)
    valuation_reference_date: str = ""
    valuation_reference_value: float = Field(0, ge=0)
    valuation_comparable_unit_price: float = Field(0, ge=0)
    valuation_district_adjustment_rate: float = Field(0, ge=-0.3, le=0.3)

    @model_validator(mode="after")
    def normalize_property_specific_fields(self) -> "ScenarioData":
        property_type = self.property_type.strip()
        is_second_hand = "二手" in property_type or "存量" in property_type
        is_new_home = "新房" in property_type
        if not is_second_hand:
            self.building_age_years = 0
            self.building_structure = "unknown"
            self.is_old_community_renovated = False
            self.remaining_land_use_years = None
        if not is_new_home:
            self.green_building_level = "none"
            self.prefab_building_level = "none"
            self.is_ultra_low_energy_building = False
        staged_modes = {"monthly_repayment_withdrawal", "semiannual_principal_offset"}
        if (
            self.provident_account_repayment_strategy not in staged_modes
            or self.provident_account_repayment_switch_to_strategy == self.provident_account_repayment_strategy
        ):
            self.provident_account_repayment_switch_enabled = False
        return self


class ScenarioRecord(BaseModel):
    id: str
    household_id: str | None = None
    data: ScenarioData
    created_at: datetime
    updated_at: datetime


class ScenarioCreate(BaseModel):
    household_id: str | None = None
    data: ScenarioData


class RulePackData(BaseModel):
    schema_version: int = Field(39, ge=1)
    name: str = "北京基准规则 2026 手动版"
    jurisdiction: str = "北京"
    category: str = "purchase_affordability"
    effective_date: str = "2025-08-09"
    source_url: str = "https://gjj.beijing.gov.cn/web/zwgk61/2024zcwj/436433464/436433465/743726695/index.html"
    status: RuleStatus = "active"
    notes: str = "辅助测算参数，请按银行和政策实际口径手动校验。"
    params: dict[str, Any] = Field(
        default_factory=lambda: {
            "required_social_security_months": 36,
            "max_home_count": 2,
            "minimum_down_payment_ratio": 0.30,
            "first_home_commercial_min_down_payment_ratio": 0.15,
            "second_home_commercial_min_down_payment_ratio": 0.20,
            "first_home_provident_min_down_payment_ratio": 0.20,
            "second_home_provident_min_down_payment_ratio": 0.25,
            "provident_first_home_loan_cap": 1200000,
            "provident_second_home_loan_cap": 1000000,
            "provident_loan_amount_per_deposit_year": 150000,
            "provident_green_two_star_bonus": 200000,
            "provident_green_three_star_bonus": 300000,
            "provident_prefab_a_bonus": 100000,
            "provident_prefab_aa_bonus": 200000,
            "provident_prefab_aaa_bonus": 300000,
            "provident_ultra_low_energy_bonus": 400000,
            "provident_policy_bonus_cap": 400000,
            "provident_repayment_capacity_enabled": True,
            "provident_repayment_income_ratio": 0.60,
            "provident_basic_living_cost_per_person": 1778,
            "provident_first_home_rate_1_to_5_years": 0.021,
            "provident_first_home_rate_6_to_30_years": 0.026,
            "provident_second_home_rate_1_to_5_years": 0.02325,
            "provident_second_home_rate_6_to_30_years": 0.03075,
            "provident_max_loan_years": 30,
            "provident_max_borrower_age": 68,
            "provident_brick_mixed_total_life_years": 50,
            "provident_steel_concrete_total_life_years": 60,
            "provident_property_age_safety_deduction_years": 3,
            "provident_upfront_purchase_extract_ratio": 0.0,
            "provident_upfront_purchase_extract_ratio_new_home": 1.0,
            "provident_upfront_purchase_extract_ratio_second_hand": 0.0,
            "provident_post_transaction_extract_ratio": 1.0,
            "provident_monthly_withdrawal_after_purchase_enabled": False,
            "provident_post_purchase_cashflow_enabled": False,
            "provident_post_purchase_strategy_mode": "auto",
            "provident_post_purchase_withdrawal_mode": "monthly_repayment_withdrawal",
            "provident_account_management_center": "beijing_municipal",
            "provident_municipal_monthly_repayment_withdrawal_supported": True,
            "provident_municipal_semiannual_principal_offset_supported": True,
            "provident_national_monthly_direct_offset_supported": True,
            "provident_national_deduction_order": "borrower_spouse_bank_card",
            "provident_balance_annual_interest_rate": 0.015,
            "micro_commercial_loan_ratio": 0.05,
            "micro_commercial_loan_ratio_min": 0.02,
            "micro_commercial_loan_ratio_max": 0.12,
            "recommended_emergency_months": 6,
            "caution_dti": 0.40,
            "danger_dti": 0.50,
            "default_deed_tax_rate": 0.015,
            "deed_tax_standard_area_sqm": 140,
            "deed_tax_first_home_standard_rate": 0.01,
            "deed_tax_first_home_large_rate": 0.015,
            "deed_tax_second_home_standard_rate": 0.01,
            "deed_tax_second_home_large_rate": 0.02,
            "default_broker_fee_rate": 0.022,
            "seller_tax_pass_through_default_rate": 0.0,
            "property_annual_price_growth_rate": 0.0,
            "property_sale_cost_rate": 0.03,
            "property_liquidity_discount_rate": 0.02,
            "property_stress_annual_price_growth_rate": -0.02,
            "investment_return_stress_factor": 0.50,
            "vehicle_purchase_tax_rate": 0.10,
            "vehicle_purchase_tax_taxable_price_ratio": 1 / 1.13,
            "new_energy_vehicle_purchase_tax_exempt_until": "2025-12",
            "new_energy_vehicle_purchase_tax_exemption_cap": 30000,
            "new_energy_vehicle_purchase_tax_half_until": "2027-12",
            "new_energy_vehicle_purchase_tax_half_relief_cap": 15000,
            "new_energy_vehicle_types": ["pure_electric", "plug_in_hybrid", "range_extended", "fuel_cell"],
            "vehicle_vessel_tax_passenger_not_taxable_types": ["pure_electric", "fuel_cell"],
            "new_energy_vehicle_vessel_tax_exempt_types": ["pure_electric", "fuel_cell"],
            "beijing_new_energy_indicator_vehicle_types": ["pure_electric"],
            "beijing_tail_restriction_exempt_vehicle_types": ["pure_electric"],
            "plug_in_hybrid_vehicle_vessel_tax_annual": 420,
            "plug_in_hybrid_vehicle_vessel_tax_exempt_until": "2026-12",
            "fuel_vehicle_vessel_tax_annual_default": 420,
            "beijing_small_passenger_indicator_required": True,
            "beijing_new_energy_family_indicator_priority": True,
            "beijing_family_new_energy_config_month": 5,
            "beijing_family_new_energy_reference_annual_quota": 119200,
            "beijing_personal_new_energy_indicator_wait_risk_months": 60,
            "beijing_vehicle_policy_notes": [
                "车辆购置税按不含增值税计税价格乘 10% 估算；新能源车按国家延续优化政策在 2025 年底前免征、2026-2027 年减半并受单车减税上限约束。",
                "北京小客车上牌需要指标。北京新能源小客车指标默认只按纯电驱动车型处理；插混、增程、燃油车应按普通小客车指标或已获指标处理。家庭新能源等待时间按最近入围分数、年度指标量和家庭积分粗略估算。",
                "纯电动、燃料电池乘用车因无排量通常不属于车船税征税范围；插混、增程乘用车按规则包配置的优惠期和优惠后税额估算，2027 年起默认不再按免征处理。",
            ],
            "rate_stress_add": 0.005,
            "income_stress_factor": 0.90,
            "price_stress_factor": 1.05,
            "backend_parallel_workers": 4,
            "purchase_happiness_weights": {
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
            },
            "personal_standard_deduction_annual": 60000,
            "annual_bonus_separate_tax_valid_until": "2027-12-31",
            "annual_bonus_separate_tax_default_continues": True,
            "annual_bonus_policy_periods": [
                {"effective_from": "2024-01-01", "effective_to": "2027-12-31", "separate_tax_enabled": True},
            ],
            "child_education_deduction_monthly": 2000,
            "infant_care_deduction_monthly": 2000,
            "continuing_education_degree_monthly": 400,
            "continuing_education_professional_annual": 3600,
            "serious_illness_medical_threshold": 15000,
            "serious_illness_medical_cap": 80000,
            "beijing_housing_rent_deduction_monthly": 1500,
            "first_home_mortgage_interest_deduction_monthly": 1000,
            "first_home_mortgage_interest_max_months": 240,
            "personal_pension_deduction_annual_cap": 12000,
            "personal_pension_withdrawal_tax_rate": 0.03,
            "rent_and_mortgage_deduction_mutually_exclusive": True,
            "child_plan_advanced_maternal_age": 35,
            "child_plan_birth_after_home_delay_months": 12,
            "child_happiness_weights": {
                "timing": 0.22,
                "cashflow": 0.26,
                "liquidity": 0.20,
                "maternal_age": 0.18,
                "education_readiness": 0.14,
            },
            "freelance_labor_remuneration_expense_ratio": 0.20,
            "freelance_labor_remuneration_withholding_rate": 0.20,
            "business_income_tax_rate_estimate": 0.10,
            "beijing_social_base_floor": 7162,
            "beijing_social_base_ceiling": 35811,
            "beijing_housing_fund_base_floor": 2540,
            "beijing_housing_fund_base_ceiling": 35811,
            "housing_fund_min_rate": 0.05,
            "housing_fund_max_rate": 0.12,
            "employee_pension_rate": 0.08,
            "employee_medical_rate": 0.02,
            "employee_medical_fixed": 3,
            "employee_unemployment_rate": 0.005,
            "employer_pension_rate": 0.16,
            "employer_medical_maternity_rate": 0.098,
            "employer_unemployment_rate": 0.005,
            "employer_work_injury_rate": 0.002,
            "beijing_unemployment_benefit_under_5y": 2129,
            "beijing_unemployment_benefit_5_to_10y": 2156,
            "beijing_unemployment_benefit_10_to_15y": 2188,
            "beijing_unemployment_benefit_15_to_20y": 2215,
            "beijing_unemployment_benefit_20y_plus": 2286,
            "beijing_unemployment_benefit_after_12_months": 2129,
            "flexible_employment_social_base": 7162,
            "flexible_employment_pension_rate": 0.20,
            "flexible_employment_unemployment_rate": 0.01,
            "flexible_employment_medical_monthly": 584.92,
            "flexible_employment_housing_fund_enabled": True,
            "flexible_employment_housing_fund_base": 7162,
            "flexible_employment_housing_fund_rate": 0.12,
            "pension_average_salary_growth_rate": 0.03,
            "pension_personal_account_annual_return": 0.025,
            "pension_personal_account_interest_credit_month": 12,
            "pension_personal_account_annual_credit_rates": {},
            "medical_account_annual_interest_rate": 0.0035,
            "medical_account_interest_credit_frequency": "quarterly",
            "medical_account_interest_credit_months": [3, 6, 9, 12],
            "medical_account_employee_transfer_rate": 0.02,
            "medical_account_retiree_monthly_transfer_under_70": 100,
            "medical_account_retiree_monthly_transfer_70_plus": 110,
            "medical_account_retiree_large_mutual_aid_monthly": 3,
            "pension_personal_account_months": 139,
            "pension_default_paid_years": 15,
            "pension_replacement_rate_floor": 0.20,
            "pension_replacement_rate_ceiling": 0.65,
            "comprehensive_tax_brackets": [
                {"threshold": 36000, "rate": 0.03, "quick_deduction": 0},
                {"threshold": 144000, "rate": 0.10, "quick_deduction": 2520},
                {"threshold": 300000, "rate": 0.20, "quick_deduction": 16920},
                {"threshold": 420000, "rate": 0.25, "quick_deduction": 31920},
                {"threshold": 660000, "rate": 0.30, "quick_deduction": 52920},
                {"threshold": 960000, "rate": 0.35, "quick_deduction": 85920},
                {"threshold": 999999999, "rate": 0.45, "quick_deduction": 181920},
            ],
            "monthly_converted_bonus_tax_brackets": [
                {"threshold": 3000, "rate": 0.03, "quick_deduction": 0},
                {"threshold": 12000, "rate": 0.10, "quick_deduction": 210},
                {"threshold": 25000, "rate": 0.20, "quick_deduction": 1410},
                {"threshold": 35000, "rate": 0.25, "quick_deduction": 2660},
                {"threshold": 55000, "rate": 0.30, "quick_deduction": 4410},
                {"threshold": 80000, "rate": 0.35, "quick_deduction": 7160},
                {"threshold": 999999999, "rate": 0.45, "quick_deduction": 15160},
            ],
        }
    )


class RulePackRecord(BaseModel):
    id: str
    data: RulePackData
    created_at: datetime
    updated_at: datetime


class RulePackCreate(BaseModel):
    data: RulePackData


class HousingMarketEvidenceData(BaseModel):
    source_name: str = ""
    source_url: str = ""
    source_type: Literal["government", "research", "agency", "brokerage", "media", "other"] = "other"
    published_date: str = ""
    scope_type: Literal["city", "district", "community"] = "city"
    scope_name: str = "北京"
    ring_scope: Literal[
        "all",
        "二环内",
        "二至三环",
        "三至四环",
        "四至五环",
        "五至六环",
        "六环外",
    ] = "all"
    property_segment: Literal["all", "resale", "new_home"] = "all"
    price_mom: float | None = Field(default=None, ge=-0.2, le=0.2)
    price_yoy: float | None = Field(default=None, ge=-0.5, le=0.5)
    avg_unit_price: float | None = Field(default=None, ge=0)
    sample_size: int | None = Field(default=None, ge=0)
    credibility_score: float = Field(0.6, ge=0, le=1)
    notes: str = ""


class MarketSnapshotData(BaseModel):
    schema_version: int = Field(54, ge=1)
    region: str = "北京"
    snapshot_date: str = "2026-06-29"
    source_name: str = "手动录入"
    source_url: str = "https://zjw.beijing.gov.cn/bjjs/fwgl/fdcjy/index.shtml"
    source_type: Literal["government", "research", "agency", "brokerage", "media", "other"] = "government"
    commercial_loan_rate: float | None = Field(default=None, ge=0, le=0.2)
    default_broker_fee_rate: float | None = Field(default=None, ge=0, le=0.2)
    seller_tax_pass_through_rate: float | None = Field(default=None, ge=0, le=0.2)
    avg_unit_price: float | None = None
    transaction_count: int | None = None
    listing_count: int | None = None
    resale_price_mom: float | None = Field(default=None, ge=-0.2, le=0.2)
    resale_price_yoy: float | None = Field(default=None, ge=-0.5, le=0.5)
    new_home_price_mom: float | None = Field(default=None, ge=-0.2, le=0.2)
    new_home_price_yoy: float | None = Field(default=None, ge=-0.5, le=0.5)
    long_term_anchor_growth_rate: float = Field(0.015, ge=-0.05, le=0.08)
    housing_data_quality_score: float = Field(0.6, ge=0, le=1)
    housing_market_evidence: list[HousingMarketEvidenceData] = Field(default_factory=list, max_length=50)
    notes: str = ""


class MarketSnapshotRecord(BaseModel):
    id: str
    data: MarketSnapshotData
    created_at: datetime
    updated_at: datetime


class MarketSnapshotCreate(BaseModel):
    data: MarketSnapshotData


class PropertyValuationProjectionPoint(BaseModel):
    month: int = Field(ge=0, le=600)
    label: str
    estimated_value: float = Field(ge=0)
    lower_value: float = Field(ge=0)
    upper_value: float = Field(ge=0)


class PropertyValuationData(BaseModel):
    schema_version: int = Field(54, ge=1)
    property_name: str
    valuation_date: str
    reference_date: str
    reference_value: float = Field(ge=0)
    estimated_market_value: float = Field(ge=0)
    estimated_unit_price: float = Field(ge=0)
    lower_value: float = Field(ge=0)
    upper_value: float = Field(ge=0)
    net_realisable_value: float = Field(ge=0)
    confidence_score: float = Field(ge=0, le=1)
    market_signal_rate: float = Field(ge=-0.5, le=0.5)
    near_term_annual_rate: float = Field(ge=-0.5, le=0.5)
    long_term_annual_rate: float = Field(ge=-0.5, le=0.5)
    structural_rate_adjustment: float = Field(ge=-0.2, le=0.2)
    location_rate_adjustment: float = Field(0, ge=-0.2, le=0.2)
    building_age_rate_adjustment: float = Field(0, ge=-0.2, le=0.2)
    location_reference_unit_price: float = Field(0, ge=0)
    sale_cost_rate: float = Field(ge=0, le=0.5)
    liquidity_discount_rate: float = Field(ge=0, le=0.5)
    market_snapshot_date: str
    market_source_name: str
    market_source_names: list[str] = Field(default_factory=list)
    market_source_count: int = Field(0, ge=0)
    matched_location_name: str = ""
    matched_ring_area: str = ""
    next_due_date: str
    drivers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    projection: list[PropertyValuationProjectionPoint] = Field(default_factory=list)


class PropertyValuationRecord(BaseModel):
    id: str
    household_id: str
    planning_goal_id: str
    valuation_date: str
    market_snapshot_id: str = ""
    data: PropertyValuationData
    created_at: datetime
    updated_at: datetime


class PropertyValuationRefreshRequest(BaseModel):
    household_id: str
    planning_goal_id: str
    property_data: ScenarioData
    market_snapshot_id: str = ""
    market_snapshot: MarketSnapshotData
    force: bool = False


class PropertyValuationRefreshResponse(BaseModel):
    record: PropertyValuationRecord
    refreshed: bool


class PersonalPensionReturnSourceData(BaseModel):
    name: str
    url: HttpUrl
    source_type: Literal["government", "registry", "index_provider", "institution", "media", "other"] = "other"
    product_type: Literal["deposit", "wealth", "fund", "insurance", "mixed"] = "mixed"
    credibility_score: float = Field(0.7, ge=0, le=1)
    parser: Literal["html_context", "eastmoney_fof_rank"] = "html_context"


class PersonalPensionReturnEvidenceData(BaseModel):
    source_name: str
    source_url: str
    source_type: str
    product_type: str
    fetched_at: str
    observed_annual_return: float | None = Field(None, ge=-0.5, le=0.5)
    sample_count: int = Field(0, ge=0)
    status: Literal["parsed", "no_rate", "fetch_failed"] = "no_rate"
    note: str = ""


class PersonalPensionReturnSnapshotData(BaseModel):
    snapshot_date: str
    pre_retirement_annual_return: float = Field(0.025, ge=-0.5, le=0.5)
    post_retirement_annual_return: float = Field(0.015, ge=-0.5, le=0.5)
    conservative_annual_return: float = Field(0.01, ge=-0.5, le=0.5)
    optimistic_annual_return: float = Field(0.04, ge=-0.5, le=0.5)
    observed_market_return: float | None = Field(None, ge=-0.5, le=0.5)
    source_count: int = Field(0, ge=0)
    parsed_source_count: int = Field(0, ge=0)
    next_due_date: str
    evidence: list[PersonalPensionReturnEvidenceData] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PersonalPensionReturnSnapshotRecord(BaseModel):
    id: str
    snapshot_date: str
    data: PersonalPensionReturnSnapshotData
    created_at: datetime
    updated_at: datetime


class PersonalPensionReturnRefreshRequest(BaseModel):
    force: bool = False
    sources: list[PersonalPensionReturnSourceData] = Field(default_factory=list)


class PersonalPensionReturnRefreshResponse(BaseModel):
    record: PersonalPensionReturnSnapshotRecord
    refreshed: bool


class SourceFetchRequest(BaseModel):
    url: HttpUrl
    name: str | None = None


class SourceDocumentRecord(BaseModel):
    id: str
    name: str
    url: str
    fetched_at: datetime
    content_hash: str
    status: str
    summary: str
    changed_from_previous: bool


class LoanSummary(BaseModel):
    principal: float
    annual_rate: float
    years: int
    repayment_method: RepaymentMethod
    first_month_payment: float
    average_month_payment: float
    total_interest: float


class CarLoanSummary(BaseModel):
    enabled: bool
    total_price: float
    down_payment_ratio: float
    down_payment: float
    purchase_tax: float = 0.0
    purchase_tax_relief: float = 0.0
    annual_vehicle_vessel_tax: float = 0.0
    license_plate_rental_initial_fee: float = 0.0
    beijing_family_indicator_score: float = 0.0
    beijing_family_indicator_estimated_wait_months: int | None = None
    purchase_delay_months: int
    loan_principal: float
    months_to_down_payment: int | None
    years_to_down_payment: float | None
    first_phase_monthly_payment: float
    later_phase_monthly_payment: float
    contract_monthly_payment: float = 0.0
    first_phase_interest_subsidy: float = 0.0
    total_interest_subsidy: float = 0.0
    borrower_total_interest: float = 0.0
    current_monthly_payment: float
    prepayment_allowed: bool = True
    prepayment_enabled: bool = False
    prepayment_start_month: int = 1
    prepayment_allowed_after_month: int = 12
    prepayment_monthly_amount: float = 0.0
    prepayment_strategy_type: str = "none"
    prepayment_lump_sum_month: int = 0
    prepayment_lump_sum_amount: float = 0.0
    prepayment_total_extra_principal: float = 0.0
    prepayment_net_benefit: float = 0.0
    prepayment_explanation: str = ""
    actual_payoff_months: int = 0
    interest_saved_by_prepayment: float = 0.0
    total_interest: float
    total_months: int
    interest_free_months: int
    later_annual_rate: float
    monthly_energy_cost: float
    monthly_insurance_cost: float
    monthly_maintenance_cost: float
    monthly_parking_cost: float
    monthly_cash_operating_cost: float
    monthly_depreciation_cost: float
    monthly_total_ownership_cost: float
    policy_notes: list[str] = Field(default_factory=list)


class CarPlanAnalysis(BaseModel):
    variant: str
    description: str
    planning_goal_id: str = ""
    source: str = "car_plan"
    vehicle_index: int = 0
    vehicle_name: str = "车辆计划"
    vehicle_candidate_index: int | None = None
    vehicle_candidate_name: str = ""
    financing_option_id: str = ""
    financing_option_name: str = ""
    financing_type: str = ""
    strategy_key: str = ""
    purchase_delay_months: int
    months_to_buy: int | None
    years_to_buy: float | None
    total_price: float
    down_payment_ratio: float
    down_payment: float
    purchase_tax: float = 0.0
    purchase_tax_relief: float = 0.0
    annual_vehicle_vessel_tax: float = 0.0
    license_plate_rental_initial_fee: float = 0.0
    beijing_family_indicator_score: float = 0.0
    beijing_family_indicator_estimated_wait_months: int | None = None
    loan_principal: float
    total_months: int
    interest_free_months: int
    later_annual_rate: float
    first_phase_monthly_payment: float
    later_phase_monthly_payment: float
    contract_monthly_payment: float = 0.0
    first_phase_interest_subsidy: float = 0.0
    total_interest_subsidy: float = 0.0
    borrower_total_interest: float = 0.0
    expected_monthly_payment_after_purchase: float
    prepayment_allowed: bool = True
    prepayment_enabled: bool = False
    prepayment_start_month: int = 1
    prepayment_allowed_after_month: int = 12
    prepayment_monthly_amount: float = 0.0
    prepayment_strategy_type: str = "none"
    prepayment_lump_sum_month: int = 0
    prepayment_lump_sum_amount: float = 0.0
    prepayment_total_extra_principal: float = 0.0
    prepayment_net_benefit: float = 0.0
    prepayment_explanation: str = ""
    actual_payoff_months: int = 0
    interest_saved_by_prepayment: float = 0.0
    total_interest: float
    required_cash_at_purchase: float
    required_liquidity_reserve: float = 0.0
    cash_after_purchase: float
    monthly_cash_flow_after_car: float
    operating_cost: float
    monthly_energy_cost: float
    monthly_insurance_cost: float
    monthly_maintenance_cost: float
    monthly_parking_cost: float
    monthly_cash_operating_cost: float
    monthly_depreciation_cost: float
    monthly_total_ownership_cost: float
    lifecycle_cash_shortfall: float = 0.0
    lifecycle_insolvency_month: int | None = None
    lifecycle_worst_liquid_balance: float = 0.0
    lifecycle_terminal_liquid_balance: float = 0.0
    lifecycle_feasible: bool = True
    lifecycle_risk_note: str = ""
    happiness_score: float
    notes: list[str]


class HappinessBreakdownItem(BaseModel):
    key: str
    name: str
    category: Literal["life", "finance", "timing", "resilience"]
    score: float
    weight: float
    weighted_score: float
    note: str


class PurchasePlanAnalysis(BaseModel):
    variant: str
    description: str
    planning_goal_id: str = ""
    source: str = "scenario"
    months_to_buy: int | None
    years_to_buy: float | None
    original_target_price: float = 0.0
    projected_purchase_price: float = 0.0
    projected_purchase_price_lower: float = 0.0
    projected_purchase_price_upper: float = 0.0
    projected_price_change: float = 0.0
    property_price_forecast_applied: bool = False
    property_price_forecast_confidence: float = 0.0
    property_price_forecast_note: str = ""
    minimum_down_payment: float
    planned_down_payment: float
    provident_fund_extractable: float
    provident_upfront_extractable: float
    family_provident_upfront_extractable: float = 0.0
    family_down_payment_support_amount: float = 0.0
    family_down_payment_support_mode: str = "none"
    family_down_payment_support_label: str = ""
    provident_post_transaction_extractable: float
    required_cash_after_pf_extract: float
    upfront_cash_required: float
    commercial_loan_amount: float
    provident_loan_amount: float
    provident_policy_bonus: float
    provident_policy_cap: float
    commercial_rate: float = 0.0
    provident_rate: float = 0.0
    deed_tax_rate: float = 0.0
    broker_fee_rate: float = 0.0
    deed_tax_amount: float = 0.0
    broker_fee_amount: float = 0.0
    commercial_loan_years: int
    provident_loan_years: int
    provident_loan_year_limit_reasons: list[str]
    commercial_repayment_method: RepaymentMethod
    provident_repayment_method: RepaymentMethod
    commercial_monthly_payment: float
    provident_monthly_payment: float
    commercial_interest_saving_if_equal_principal: float = 0.0
    commercial_equal_principal_first_payment: float = 0.0
    commercial_equal_installment_payment: float = 0.0
    commercial_repayment_advice: str = ""
    commercial_prepayment_mode: CommercialPrepaymentMode = "none"
    commercial_prepayment_enabled: bool = False
    commercial_prepayment_start_month: int = 1
    commercial_prepayment_allowed_after_month: int = 12
    commercial_prepayment_monthly_amount: float = 0.0
    commercial_actual_payoff_months: int = 0
    commercial_interest_saved_by_prepayment: float = 0.0
    total_monthly_payment: float
    total_interest: float
    provident_contract_months: int = 0
    provident_interest_saving_if_equal_principal: float = 0.0
    provident_equal_principal_first_payment: float = 0.0
    provident_equal_installment_payment: float = 0.0
    provident_repayment_advice: str = ""
    renovation_cost: float
    renovation_funding_mode: RenovationFundingMode
    renovation_included_in_upfront_cash: bool
    months_to_renovation: int | None
    years_to_renovation: float | None
    post_purchase_renovation_monthly_saving: float
    investment_withdrawal_mode: InvestmentWithdrawalMode = "auto"
    investment_withdrawal_mode_label: str = "自动优化提取"
    cash_account_before_purchase: float = 0.0
    investment_balance_before_purchase: float = 0.0
    investment_reserve_target: float = 0.0
    investment_sell_gross_at_purchase: float = 0.0
    investment_sell_proceeds_at_purchase: float = 0.0
    investment_balance_after_purchase: float = 0.0
    cash_after_transaction: float
    cash_after_purchase: float
    provident_balance_after_extract: float
    required_liquidity_reserve: float
    liquidity_ok: bool
    minimum_cash_balance: float = 0.0
    minimum_cash_balance_month: int | None = None
    cash_stress_ok: bool = True
    cash_stress_shortfall: float = 0.0
    cash_shortfall: float = 0.0
    insolvency_month: int | None = None
    liquid_assets_exhausted_month: int | None = None
    worst_cash_balance: float = 0.0
    terminal_net_worth: float = 0.0
    emergency_reserve_coverage_months: float = 0.0
    pareto_efficient: bool = False
    feasibility_recommendation: str = ""
    post_purchase_cash_flow: float
    post_purchase_pf_strategy: str = "keep_in_account"
    post_purchase_pf_strategy_label: str = "留存在公积金账户"
    monthly_post_purchase_pf_withdrawal: float
    post_purchase_cash_flow_with_pf_withdrawal: float
    debt_to_income_ratio: float
    happiness_score: float
    recommendation_score: int = Field(0, ge=0, le=100)
    recommendation_reasons: list[str] = Field(default_factory=list)
    is_recommended: bool = False
    provident_extraction_notes: list[str]
    happiness_breakdown: list[HappinessBreakdownItem]


class YieldSensitivityPoint(BaseModel):
    annual_return: float
    months_to_buy: int | None
    years_to_buy: float | None
    cash_after_purchase: float


class LoanVisualizationPoint(BaseModel):
    plan_variant: str
    month: int
    commercial_loan_balance: float
    provident_loan_balance: float
    home_loan_balance: float
    vehicle_loan_balance: float
    existing_loan_balance: float
    total_loan_balance: float
    commercial_monthly_payment: float
    provident_monthly_payment: float
    home_monthly_payment: float
    vehicle_monthly_payment: float
    commercial_extra_principal_payment: float = 0.0
    vehicle_extra_principal_payment: float = 0.0
    existing_monthly_payment: float
    existing_loan_details: list[ExistingLoanVisualizationDetail] = Field(default_factory=list)
    total_monthly_payment: float
    cash_monthly_payment: float
    provident_offset_payment: float = 0.0
    provident_monthly_withdrawal_payment: float = 0.0
    provident_principal_offset_payment: float = 0.0
    provident_monthly_payment_relief: float = 0.0


class ProvidentMemberAccountPoint(BaseModel):
    member_index: int
    member_name: str
    balance_start: float
    personal_deposit: float
    employer_deposit: float
    total_deposit: float
    interest: float
    rent_withdrawal: float
    upfront_withdrawal: float
    post_transaction_withdrawal: float
    agreed_withdrawal: float
    monthly_repayment_withdrawal: float = 0.0
    loan_offset_payment: float
    retirement_withdrawal: float = 0.0
    account_closed_by_retirement: bool = False
    total_inflow: float
    total_outflow: float
    balance_end: float


class ProvidentVisualizationPoint(BaseModel):
    plan_variant: str
    month: int
    balance_start: float
    personal_deposit: float
    employer_deposit: float
    total_deposit: float
    interest: float
    rent_withdrawal: float
    upfront_withdrawal: float
    post_transaction_withdrawal: float
    agreed_withdrawal: float
    monthly_repayment_withdrawal: float = 0.0
    loan_offset_payment: float
    retirement_withdrawal: float = 0.0
    total_inflow: float
    total_outflow: float
    balance_end: float
    strategy_label: str
    member_accounts: list[ProvidentMemberAccountPoint] = Field(default_factory=list)


class SocialSecurityMemberAccountPoint(BaseModel):
    member_index: int
    member_name: str
    pension_balance_start: float
    pension_contribution: float
    pension_account_payout: float = 0.0
    pension_interest: float
    pension_balance_end: float
    medical_balance_start: float
    medical_contribution: float
    medical_retiree_transfer: float = 0.0
    medical_interest: float
    medical_healthcare_outflow: float = 0.0
    medical_mutual_aid_outflow: float = 0.0
    medical_outflow: float = 0.0
    medical_balance_end: float
    retired: bool = False


class SocialSecurityVisualizationPoint(BaseModel):
    plan_variant: str
    month: int
    pension_balance_start: float
    pension_contribution: float
    pension_account_payout: float = 0.0
    pension_interest: float
    pension_balance_end: float
    medical_balance_start: float
    medical_contribution: float
    medical_retiree_transfer: float = 0.0
    medical_interest: float
    medical_healthcare_outflow: float = 0.0
    medical_mutual_aid_outflow: float = 0.0
    medical_outflow: float = 0.0
    medical_balance_end: float
    total_balance_end: float
    member_accounts: list[SocialSecurityMemberAccountPoint] = Field(default_factory=list)


class MonthlyLedgerEntry(BaseModel):
    plan_variant: str
    month: int
    account: str
    category: str
    label: str
    amount: float
    direction: Literal["inflow", "outflow", "transfer", "valuation"]
    source: str = "backend"


class ChildPlanStrategyPoint(BaseModel):
    planning_goal_id: str = ""
    source: str = "child_plans"
    child_name: str
    enabled: bool = True
    timing_mode: ChildPlanTimingMode = "after_first_home"
    expense_strategy_mode: ChildExpenseStrategyMode = "balanced"
    birth_month_index: int | None = None
    birth_month_label: str = ""
    preparation_start_month_index: int | None = None
    pregnancy_start_month_index: int | None = None
    education_start_month_index: int | None = None
    mother_member_name: str = ""
    mother_age_at_birth: float | None = None
    happiness_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    monthly_cost_now: float = 0.0
    first_year_cash_need: float = 0.0
    total_to_age_18: float = 0.0
    lifecycle_cash_shortfall: float = 0.0
    lifecycle_insolvency_month: int | None = None
    lifecycle_feasible: bool = True
    recommended_budget_factor: float = 1.0
    recommended_delay_months: int = 0
    lifecycle_risk_note: str = ""
    stages: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str = ""


class AccountSnapshotPoint(BaseModel):
    plan_variant: str
    month: int
    cash_balance: float
    investment_balance: float
    liquid_asset_value: float = 0.0
    provident_balance: float
    pension_account_balance: float = 0.0
    medical_account_balance: float = 0.0
    social_security_account_balance: float = 0.0
    personal_pension_balance: float = 0.0
    property_asset_value: float = 0.0
    vehicle_asset_value: float = 0.0
    first_vehicle_asset_value: float = 0.0
    second_vehicle_asset_value: float = 0.0
    fixed_asset_value: float
    total_asset_value: float
    total_loan_balance: float
    net_worth: float


class MonthlyCashflowPoint(BaseModel):
    plan_variant: str
    month: int
    cash_balance: float
    investment_balance: float
    liquid_asset_value: float = 0.0
    provident_balance: float
    pension_account_balance: float = 0.0
    medical_account_balance: float = 0.0
    social_security_account_balance: float = 0.0
    fixed_asset_value: float
    total_asset_value: float
    total_loan_balance: float
    net_worth: float
    happiness_score: float = 0.0
    monthly_cash_delta: float
    cash_shortfall: float = 0.0
    insolvency_month: int | None = None
    liquid_assets_exhausted_month: int | None = None
    cash_income: float
    pension_income: float = 0.0
    living_expense: float
    scheduled_expense: float
    renovation_expense: float = 0.0
    child_expense: float = 0.0
    career_shock_self_payment: float = 0.0
    debt_payment: float
    regular_debt_payment: float = 0.0
    phased_loan_payment: float = 0.0
    house_payment: float
    house_contract_payment: float = 0.0
    provident_house_offset_payment: float = 0.0
    provident_house_payment_relief: float = 0.0
    vehicle_payment: float
    first_vehicle_payment: float = 0.0
    second_vehicle_payment: float = 0.0
    vehicle_operating_cost: float
    first_vehicle_energy_cost: float = 0.0
    first_vehicle_insurance_cost: float = 0.0
    first_vehicle_maintenance_cost: float = 0.0
    first_vehicle_parking_cost: float = 0.0
    second_vehicle_energy_cost: float = 0.0
    second_vehicle_insurance_cost: float = 0.0
    second_vehicle_maintenance_cost: float = 0.0
    second_vehicle_parking_cost: float = 0.0
    no_car_commute_cost: float = 0.0
    first_vehicle_down_payment: float = 0.0
    second_vehicle_down_payment: float = 0.0
    vehicle_down_payment: float = 0.0
    vehicle_plate_rental_payment: float = 0.0
    investment_contribution: float
    investment_contribution_base: float = 0.0
    investment_contribution_cash_sweep: float = 0.0
    investment_return: float
    investment_tax: float = 0.0
    investment_fee: float
    investment_buy_fee: float = 0.0
    investment_sell_fee: float = 0.0
    investment_sell_proceeds: float = 0.0
    personal_pension_contribution: float = 0.0
    personal_pension_return: float = 0.0
    personal_pension_withdrawal: float = 0.0
    personal_pension_redemption_fee: float = 0.0
    personal_pension_withdrawal_tax: float = 0.0
    personal_pension_suspended_contribution: float = 0.0
    personal_pension_balance: float = 0.0
    provident_deposit: float
    provident_withdrawal: float
    transaction_cash_out: float
    transaction_cash_in: float
    property_asset_value: float = 0.0
    vehicle_asset_value: float = 0.0
    first_vehicle_asset_value: float = 0.0
    second_vehicle_asset_value: float = 0.0
    phase: str
    ledger_entries: list[MonthlyLedgerEntry] = Field(default_factory=list)


class VisualizationBreakdownItem(BaseModel):
    name: str
    value: float = 0.0
    amount: float | None = None
    kind: Literal["income", "expense", "asset", "deduction", "result"] | None = None


class MonthlyVisualizationDetail(BaseModel):
    plan_variant: str
    month: int
    income_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    income_legend: list[VisualizationBreakdownItem] = Field(default_factory=list)
    expense_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    loan_payment_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    provident_inflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    provident_outflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    social_security_inflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    social_security_outflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    cash_flow_items: list[VisualizationBreakdownItem] = Field(default_factory=list)
    cash_flow_drivers: list[VisualizationBreakdownItem] = Field(default_factory=list)
    advisor_text: str = ""
    explanation_items: list[dict[str, str]] = Field(default_factory=list)


class VisualizationPieBlock(BaseModel):
    title: str
    period: str = ""
    data: list[VisualizationBreakdownItem] = Field(default_factory=list)
    empty_text: str = ""


class AnnualVisualizationDetail(BaseModel):
    plan_variant: str
    year: int
    cash_inflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    cash_outflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    liquid_asset_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    fixed_asset_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    loan_payment_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    loan_balance_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    provident_flow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    social_security_inflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    social_security_outflow_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    social_security_balance_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)


class TaxVisualizationDetail(BaseModel):
    year: int
    month: int | None = None
    monthly_tax_member_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    monthly_deduction_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    annual_tax_member_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)
    annual_tax_type_pie: list[VisualizationBreakdownItem] = Field(default_factory=list)


class AccountConceptSummary(BaseModel):
    code: str
    name: str
    category: Literal["account", "cash", "investment", "provident", "social_security", "fixed_asset", "loan", "policy"]
    description: str
    managed_by: Literal["backend", "user_input", "policy"]
    core_object_count: int = 0
    current_balance: float = 0.0
    monthly_flow: float = 0.0


class CoreObjectGroupSummary(BaseModel):
    code: str
    name: str
    category: Literal["liquid_asset", "restricted_account", "fixed_asset", "loan", "policy"]
    description: str
    concept_codes: list[str] = Field(default_factory=list)
    core_object_count: int = 0
    current_balance: float = 0.0
    monthly_flow: float = 0.0


class PlanningFoundationSummary(BaseModel):
    planning_goals: list[PlanningGoalRecord] = Field(default_factory=list)
    planning_sequence: PlanningSequenceResult | None = None
    core_objects: list[CoreObjectRecord] = Field(default_factory=list)
    account_concepts: list[AccountConceptSummary] = Field(default_factory=list)
    core_object_groups: list[CoreObjectGroupSummary] = Field(default_factory=list)


class StrategyExplanationPoint(BaseModel):
    plan_variant: str
    section: str
    title: str
    body: str
    priority: int = Field(100, ge=0)


class PlanEventPoint(BaseModel):
    plan_variant: str
    month: int
    category: Literal[
        "account",
        "income",
        "investment",
        "home_purchase",
        "property_market",
        "loan",
        "provident",
        "vehicle",
        "child",
        "renovation",
        "risk",
    ]
    title: str
    detail: str
    amount: float | None = None
    severity: Literal["info", "success", "warning", "danger"] = "info"
    source: str = "backend"
    calibration_source: str = ""


class TaxMemberSummary(BaseModel):
    member_name: str
    active_months: int
    monthly_personal_social_insurance: float
    monthly_personal_housing_fund: float
    monthly_employer_social_insurance: float
    monthly_employer_housing_fund: float
    gross_annual_income: float
    taxable_income: float
    salary_tax: float
    bonus_tax: float
    total_tax: float
    net_annual_income: float
    net_monthly_income: float
    selected_bonus_method: BonusTaxMethod


class TaxYearSummary(BaseModel):
    year: int
    summaries: list[TaxMemberSummary]
    gross_annual_income: float
    taxable_income: float
    salary_tax: float
    bonus_tax: float
    total_tax: float
    net_annual_income: float


class TaxMemberMonthlyPoint(BaseModel):
    month: int
    year: int
    month_of_year: int
    member_index: int
    member_name: str
    stage_name: str
    stage_kind: str
    gross_salary: float
    bonus_income: float
    other_taxable_income: float
    non_taxable_income: float
    pension_income: float = 0.0
    personal_social: float
    personal_housing_fund: float
    employer_social: float
    employer_housing_fund: float
    special_additional_deduction: float
    elderly_care_deduction: float
    other_deduction: float
    cumulative_taxable_income: float
    salary_tax: float
    bonus_tax: float
    total_income_tax: float
    personal_pension_contribution: float = 0.0
    net_income: float
    selected_bonus_method: BonusTaxMethod


class TaxMonthlyPoint(BaseModel):
    month: int
    year: int
    month_of_year: int
    gross_income: float
    net_income: float
    income_tax: float
    salary_tax: float
    bonus_tax: float
    personal_social: float
    personal_housing_fund: float
    employer_social: float
    employer_housing_fund: float
    monthly_pf_deposit: float
    non_taxable_income: float
    pension_income: float = 0.0
    extra_cash_expense: float
    member_points: list[TaxMemberMonthlyPoint] = Field(default_factory=list)


class TaxEventPoint(BaseModel):
    month: int
    year: int
    month_of_year: int
    member_name: str
    event_type: Literal[
        "income_stage_start",
        "income_stage_end",
        "bonus_payout",
        "tax_payment",
        "deduction_start",
        "non_taxable_income",
    ]
    title: str
    detail: str
    amount: float | None = None
    source: str = "backend"


class PersonalPensionAnnualOptimizationPoint(BaseModel):
    year: int
    annual_contribution: float = 0.0
    estimated_tax_saving: float = 0.0
    pension_net_value_at_withdrawal: float = 0.0
    alternative_investment_value_at_withdrawal: float = 0.0
    tax_saving_future_value: float = 0.0
    net_advantage_at_withdrawal: float = 0.0


class TaxStrategyItem(BaseModel):
    deduction_type: SpecialDeductionType
    title: str
    status: TaxStrategyStatus = "available"
    member_name: str = ""
    monthly_amount: float = 0.0
    annual_amount: float = 0.0
    estimated_tax_saving: float = 0.0
    cash_contribution: float = 0.0
    account_return_rate: float = 0.0
    post_retirement_return_rate: float = 0.0
    withdrawal_tax_rate: float = 0.0
    withdrawal_mode: PersonalPensionWithdrawalMode | None = None
    withdrawal_start_month: str = ""
    withdrawal_years: int = 0
    estimated_retirement_balance: float = 0.0
    estimated_monthly_withdrawal: float = 0.0
    cumulative_contribution: float = 0.0
    cumulative_estimated_tax_saving: float = 0.0
    pension_net_value_at_withdrawal: float = 0.0
    alternative_investment_value_at_withdrawal: float = 0.0
    forgone_investment_earnings: float = 0.0
    tax_saving_future_value: float = 0.0
    net_advantage_at_withdrawal: float = 0.0
    full_cap_annual_tax_saving: float = 0.0
    full_cap_net_advantage_at_withdrawal: float = 0.0
    personal_pension_annual_plan: list[PersonalPensionAnnualOptimizationPoint] = Field(default_factory=list)
    cash_safety_rule: str = ""
    contribution_end_reason: str = ""
    long_term_cash_risk_month: str = ""
    recommended_action: str = ""
    start_month: str = ""
    end_month: str | None = None
    reason: str = ""
    conflicts_with: list[str] = Field(default_factory=list)
    source: TaxStrategySource = "backend_auto"


class TaxStrategyTimelinePoint(BaseModel):
    month: int
    year: int
    month_of_year: int
    category: TaxStrategyTimelineCategory
    title: str
    action: str
    member_name: str = ""
    deduction_type: SpecialDeductionType | None = None
    status: TaxStrategyStatus = "available"
    amount: float = 0.0
    estimated_tax_saving: float = 0.0
    detail: str = ""
    source: TaxStrategySource = "backend_auto"


class CareerShockMemberProjection(BaseModel):
    member_name: str
    enabled: bool = False
    layoff_age: int = Field(35, ge=18, le=80)
    retirement_age: int = Field(63, ge=45, le=80)
    layoff_month: str | None = None
    retirement_month: str | None = None
    unemployment_benefit_months: int = Field(0, ge=0, le=24)
    unemployment_benefit_monthly: float = 0.0
    later_unemployment_benefit_monthly: float = 0.0
    self_social_insurance_monthly: float = 0.0
    flexible_housing_fund_monthly: float = 0.0
    self_payment_monthly: float = 0.0
    pension_monthly: float = 0.0
    generated_stages: list[IncomeStageData] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CareerShockProjection(BaseModel):
    enabled: bool = False
    unemployment_benefit_months: int = Field(0, ge=0, le=24)
    unemployment_benefit_monthly: float = 0.0
    later_unemployment_benefit_monthly: float = 0.0
    self_social_insurance_monthly: float = 0.0
    flexible_housing_fund_monthly: float = 0.0
    self_payment_monthly: float = 0.0
    effective_members: list[IncomeMember] = Field(default_factory=list)
    member_projections: list[CareerShockMemberProjection] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InvestmentAllocationSummary(BaseModel):
    monthly_surplus: float = 0.0
    reserve_target: float = 0.0
    reserve_gap: float = 0.0
    base_investment: float = 0.0
    cash_sweep_investment: float = 0.0
    total_investment: float = 0.0
    buy_fee: float = 0.0
    net_investment: float = 0.0


class InvestmentPlanRecommendation(BaseModel):
    variant: str
    plan_name: str
    risk_level: str
    risk_label: str
    description: str
    monthly_investment: float = 0.0
    annual_return: float = 0.0
    after_tax_annual_return: float = 0.0
    risk_adjusted_annual_return: float = 0.0
    cash_reserve_months: float = 0.0
    liquidity_horizon_months: int | None = None
    goal_liquidity_target: float = 0.0
    goal_liquidity_gap: float = 0.0
    monthly_goal_saving: float = 0.0
    equity_ratio: float = 0.0
    bond_ratio: float = 0.0
    cash_ratio: float = 0.0
    lifecycle_cash_shortfall: float = 0.0
    lifecycle_insolvency_month: int | None = None
    lifecycle_liquid_assets_exhausted_month: int | None = None
    lifecycle_required_monthly_relief: float = 0.0
    lifecycle_feasible: bool = True
    lifecycle_risk_note: str = ""
    score: int = Field(0, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class QuantInvestmentPolicyData(BaseModel):
    """家庭量化定投的风险边界；不包含任何券商或数据服务凭据。"""

    schema_version: int = Field(1, ge=1)
    name: str = "港股通 / QDII ETF 月度定投"
    enabled: bool = True
    frequency: Literal["monthly"] = "monthly"
    equity_cap: float = Field(0.35, ge=0, le=1)
    defensive_min: float = Field(0.65, ge=0, le=1)
    rebalance_threshold: float = Field(0.05, ge=0, le=0.5)
    drawdown_reduce_threshold: float = Field(0.08, ge=0, le=1)
    drawdown_pause_threshold: float = Field(0.12, ge=0, le=1)
    drawdown_freeze_threshold: float = Field(0.15, ge=0, le=1)
    drawdown_reduced_equity_cap: float = Field(0.20, ge=0, le=1)
    qdii_premium_threshold: float = Field(0.03, ge=0, le=0.2)
    qdii_nav_max_stale_days: int = Field(3, ge=0, le=20)
    default_monthly_budget: float = Field(0, ge=0)
    slippage_rate: float = Field(0.001, ge=0, le=0.05)
    notes: str = ""

    @model_validator(mode="after")
    def validate_risk_boundaries(self) -> "QuantInvestmentPolicyData":
        if self.equity_cap + self.defensive_min > 1.000001:
            raise ValueError("权益上限与防御资产下限之和不能超过 100%")
        if not (
            self.drawdown_reduce_threshold
            <= self.drawdown_pause_threshold
            <= self.drawdown_freeze_threshold
        ):
            raise ValueError("回撤阈值必须按降仓、暂停、冻结顺序递增")
        return self


class QuantInvestmentPolicyRecord(BaseModel):
    id: str
    household_id: str
    data: QuantInvestmentPolicyData
    created_at: datetime
    updated_at: datetime


class QuantInvestmentPolicyCreate(BaseModel):
    household_id: str
    data: QuantInvestmentPolicyData


class InvestmentInstrumentData(BaseModel):
    schema_version: int = Field(1, ge=1)
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    market: InvestmentInstrumentMarket
    trading_mode: InvestmentTradingMode = "exchange"
    asset_class: InvestmentAssetClass
    currency: Literal["CNY", "HKD", "USD"] = "CNY"
    enabled: bool = True
    hong_kong_connect_eligible: bool = False
    purchase_suspended: bool = False
    monthly_purchase_limit: float | None = Field(default=None, ge=0)
    buy_fee_rate: float = Field(0.0015, ge=0, le=0.05)
    sell_fee_rate: float = Field(0.005, ge=0, le=0.05)
    qdii_premium_threshold: float | None = Field(default=None, ge=0, le=0.2)
    notes: str = ""

    @model_validator(mode="after")
    def validate_trading_route(self) -> "InvestmentInstrumentData":
        if self.market == "qdii_fund" and self.trading_mode != "fund_subscription":
            raise ValueError("场外 QDII 只能使用基金申购方式")
        if self.market != "qdii_fund" and self.trading_mode != "exchange":
            raise ValueError("一期场内标的必须使用交易所交易方式")
        return self


class InvestmentInstrumentRecord(BaseModel):
    id: str
    household_id: str
    data: InvestmentInstrumentData
    created_at: datetime
    updated_at: datetime


class InvestmentInstrumentCreate(BaseModel):
    household_id: str
    data: InvestmentInstrumentData


class InvestmentMarketBarData(BaseModel):
    date: str
    close: float = Field(gt=0)
    adjusted_close: float | None = Field(default=None, gt=0)
    nav: float | None = Field(default=None, gt=0)
    nav_date: str = ""
    premium_rate: float | None = Field(default=None, ge=-1, le=1)
    is_trading: bool = True


class InvestmentMarketSnapshotData(BaseModel):
    schema_version: int = Field(1, ge=1)
    source: Literal["tushare_pro", "manual"] = "tushare_pro"
    snapshot_date: str
    status: InvestmentMarketDataStatus = "complete"
    bars: list[InvestmentMarketBarData] = Field(default_factory=list, max_length=5000)
    warning: str = ""


class InvestmentMarketSnapshotRecord(BaseModel):
    id: str
    instrument_id: str
    snapshot_date: str
    data: InvestmentMarketSnapshotData
    created_at: datetime
    updated_at: datetime


class QuantMarketRefreshRequest(BaseModel):
    household_id: str
    start_date: str = ""


class QuantMarketRefreshResponse(BaseModel):
    records: list[InvestmentMarketSnapshotRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InvestmentMarketSnapshotCreate(BaseModel):
    household_id: str
    instrument_id: str
    data: InvestmentMarketSnapshotData


class QuantInvestmentProposalData(BaseModel):
    schema_version: int = Field(1, ge=1)
    policy_id: str
    snapshot_ids: list[str] = Field(default_factory=list)
    as_of_date: str
    protected_cash: float = Field(ge=0)
    investable_cash: float = Field(ge=0)
    proposed_budget: float = Field(ge=0)
    effective_equity_cap: float = Field(ge=0, le=1)
    estimated_drawdown: float = Field(ge=0, le=1)
    risk_state: Literal["normal", "reduced", "paused", "frozen", "blocked"]
    reasons: list[str] = Field(default_factory=list)


class QuantInvestmentProposalRecord(BaseModel):
    id: str
    household_id: str
    data: QuantInvestmentProposalData
    created_at: datetime
    updated_at: datetime


class QuantInvestmentProposalRequest(BaseModel):
    household_id: str
    policy_id: str


class PaperOrderData(BaseModel):
    schema_version: int = Field(1, ge=1)
    proposal_id: str
    instrument_id: str
    side: Literal["buy", "sell"] = "buy"
    order_amount: float = Field(gt=0)
    estimated_price: float = Field(gt=0)
    estimated_quantity: float = Field(gt=0)
    estimated_fee: float = Field(ge=0)
    status: InvestmentOrderStatus = "proposed"
    reason: str = ""
    executed_date: str = ""
    executed_price: float | None = Field(default=None, gt=0)
    executed_quantity: float | None = Field(default=None, gt=0)


class PaperOrderRecord(BaseModel):
    id: str
    household_id: str
    data: PaperOrderData
    created_at: datetime
    updated_at: datetime


class PaperOrderCreate(BaseModel):
    household_id: str
    data: PaperOrderData


class PaperOrderSimulateRequest(BaseModel):
    household_id: str
    executed_date: str = ""
    executed_price: float | None = Field(default=None, gt=0)


class QuantBacktestRequest(BaseModel):
    household_id: str
    policy_id: str
    monthly_contribution: float = Field(1000, gt=0)


class QuantBacktestResult(BaseModel):
    policy_id: str
    start_date: str
    end_date: str
    months: int = Field(ge=0)
    strategy_terminal_value: float = Field(ge=0)
    static_terminal_value: float = Field(ge=0)
    strategy_max_drawdown: float = Field(ge=0, le=1)
    static_max_drawdown: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class PortfolioStrategyRecommendation(BaseModel):
    plan_name: str
    title: str
    status: Literal["feasible", "adjustment_required", "high_risk"]
    description: str
    actions: list[str] = Field(default_factory=list)
    cash_shortfall: float = 0.0
    insolvency_month: int | None = None
    liquid_assets_exhausted_month: int | None = None
    terminal_net_worth: float = 0.0
    required_monthly_relief: float = 0.0
    feasible: bool = False
    score: int = Field(0, ge=0, le=100)
    is_recommended: bool = False
    reasons: list[str] = Field(default_factory=list)


class AnnualFinancialSummary(BaseModel):
    plan_variant: str
    year: int
    months: int
    cash_income: float = 0.0
    pension_income: float = 0.0
    living_expense: float = 0.0
    scheduled_expense: float = 0.0
    renovation_expense: float = 0.0
    child_expense: float = 0.0
    career_shock_self_payment: float = 0.0
    debt_payment: float = 0.0
    house_payment: float = 0.0
    vehicle_payment: float = 0.0
    vehicle_operating_cost: float = 0.0
    investment_contribution: float = 0.0
    investment_return: float = 0.0
    investment_tax: float = 0.0
    investment_fee: float = 0.0
    investment_sell_proceeds: float = 0.0
    personal_pension_contribution: float = 0.0
    personal_pension_return: float = 0.0
    personal_pension_withdrawal: float = 0.0
    personal_pension_redemption_fee: float = 0.0
    personal_pension_withdrawal_tax: float = 0.0
    personal_pension_suspended_contribution: float = 0.0
    personal_pension_balance_end: float = 0.0
    provident_deposit: float = 0.0
    provident_withdrawal: float = 0.0
    pension_account_contribution: float = 0.0
    pension_account_payout: float = 0.0
    pension_account_interest: float = 0.0
    pension_account_balance_end: float = 0.0
    medical_account_contribution: float = 0.0
    medical_account_retiree_transfer: float = 0.0
    medical_account_interest: float = 0.0
    medical_account_healthcare_outflow: float = 0.0
    medical_account_mutual_aid_outflow: float = 0.0
    medical_account_outflow: float = 0.0
    medical_account_balance_end: float = 0.0
    social_security_account_balance_end: float = 0.0
    transaction_cash_out: float = 0.0
    transaction_cash_in: float = 0.0
    monthly_cash_delta: float = 0.0
    cash_balance_end: float = 0.0
    investment_balance_end: float = 0.0
    liquid_asset_value_end: float = 0.0
    provident_balance_end: float = 0.0
    fixed_asset_value_end: float = 0.0
    property_asset_value_end: float = 0.0
    vehicle_asset_value_end: float = 0.0
    first_vehicle_asset_value_end: float = 0.0
    second_vehicle_asset_value_end: float = 0.0
    total_asset_value_end: float = 0.0
    total_loan_balance_end: float = 0.0
    net_worth_end: float = 0.0
    commercial_payment: float = 0.0
    provident_payment: float = 0.0
    vehicle_loan_payment: float = 0.0
    existing_loan_payment: float = 0.0
    commercial_extra_principal_payment: float = 0.0
    vehicle_extra_principal_payment: float = 0.0
    provident_offset_payment: float = 0.0
    provident_monthly_withdrawal_payment: float = 0.0
    provident_principal_offset_payment: float = 0.0
    cash_monthly_payment: float = 0.0
    commercial_loan_balance_end: float = 0.0
    provident_loan_balance_end: float = 0.0
    vehicle_loan_balance_end: float = 0.0
    existing_loan_balance_end: float = 0.0


class ExportSheet(BaseModel):
    plan_variant: str = ""
    title: str
    headers: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class ExportTextDocument(BaseModel):
    plan_variant: str
    filename: str
    lines: list[str] = Field(default_factory=list)


class StressResult(BaseModel):
    name: str
    status: str
    monthly_payment: float
    post_purchase_cash_flow: float
    debt_to_income_ratio: float
    emergency_months: float
    feasible: bool = False
    reason: str = ""
    cash_shortfall: float = 0.0
    worst_cash_balance: float = 0.0
    insolvency_month: int | None = None
    liquid_assets_exhausted_month: int | None = None


class AffordabilityRequest(BaseModel):
    household_id: str = ""
    scenario_id: str = ""
    household: HouseholdData
    scenario: ScenarioData
    rule_pack: RulePackData
    market_snapshot: MarketSnapshotData | None = None
    include_stress_tests: bool = False
    calculation_context: CalculationContextSnapshot | None = None


class CacheLayerHashes(BaseModel):
    input: str = ""
    strategy: str = ""
    ledger: str = ""
    visualization: str = ""
    engine: str = ""


class GeneratedStrategyBatchRequest(BaseModel):
    cache_layers: list[CacheLayerHashes] = Field(default_factory=list)
    strategy_type: GeneratedStrategyType | None = None
    owner_key: str | None = None
    current_only: bool = True


class AffordabilityResult(BaseModel):
    cache_layers: CacheLayerHashes = Field(default_factory=CacheLayerHashes)
    calculation_context: CalculationContextSnapshot | None = None
    status: str
    status_reason: str
    eligible: bool
    eligibility_notes: list[str]
    total_required_cash: float
    minimum_down_payment: float
    stated_down_payment: float
    taxes_and_fees: float
    funding_gap: float
    remaining_cash_after_purchase: float
    household_gross_monthly_income: float
    household_net_monthly_income: float
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
    immediate_purchase_status: str = ""
    immediate_purchase_reason: str = ""
    recommended_plan_status: str = ""
    recommended_plan_reason: str = ""
    commercial_loan: LoanSummary | None
    provident_loan: LoanSummary | None
    tax_summaries: list[TaxMemberSummary]
    tax_year_summaries: list[TaxYearSummary] = []
    tax_monthly_points: list[TaxMonthlyPoint] = []
    tax_events: list[TaxEventPoint] = []
    tax_strategy_items: list[TaxStrategyItem] = []
    tax_strategy_timeline: list[TaxStrategyTimelinePoint] = []
    career_shock_projection: CareerShockProjection | None = None
    investment_plan_recommendations: list[InvestmentPlanRecommendation] = Field(default_factory=list)
    portfolio_strategy_recommendations: list[PortfolioStrategyRecommendation] = Field(default_factory=list)
    current_investment_allocation: InvestmentAllocationSummary | None = None
    child_plan_strategies: list[ChildPlanStrategyPoint] = Field(default_factory=list)
    annual_financial_summaries: list[AnnualFinancialSummary] = Field(default_factory=list)
    purchase_plan_analyses: list[PurchasePlanAnalysis]
    yield_sensitivity: list[YieldSensitivityPoint]
    monthly_cashflow_visualization: list[MonthlyCashflowPoint] = []
    monthly_visualization_details: list[MonthlyVisualizationDetail] = []
    annual_visualization_details: list[AnnualVisualizationDetail] = []
    tax_visualization_details: list[TaxVisualizationDetail] = []
    account_snapshots: list[AccountSnapshotPoint] = []
    monthly_ledger: list[MonthlyLedgerEntry] = []
    loan_visualization: list[LoanVisualizationPoint] = []
    provident_visualization: list[ProvidentVisualizationPoint] = []
    social_security_visualization: list[SocialSecurityVisualizationPoint] = []
    account_concepts: list[AccountConceptSummary] = []
    core_object_groups: list[CoreObjectGroupSummary] = []
    strategy_explanations: list[StrategyExplanationPoint] = []
    plan_events: list[PlanEventPoint] = []
    export_sheets: list[ExportSheet] = []
    export_texts: list[ExportTextDocument] = []
    stress_tests: list[StressResult]
    assumptions: list[str]
