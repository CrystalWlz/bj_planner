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
RenovationFundingMode = Literal["after_purchase_saving", "upfront_cash"]
InvestmentWithdrawalMode = Literal["auto", "full_liquidation", "manual_reserve"]
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
ExistingLoanPrepaymentMode = Literal["none", "manual", "auto"]
PlanningGoalType = Literal["home", "vehicle", "renovation", "other"]
PlanningTimingMode = Literal["auto_sequence", "parallel", "manual_month", "after_goal", "not_planned"]
ScheduledExpenseFrequency = Literal["monthly", "annual_once", "one_time"]
ScheduledExpenseTimingMode = Literal["fixed_month", "flexible_range"]
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
TaxStrategyStatus = Literal["auto_enabled", "manual_enabled", "available", "not_applicable", "conflict"]
TaxStrategySource = Literal["backend_auto", "manual", "event"]


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
    personal_pension_account_enabled: bool = True
    personal_pension_account_balance: float = Field(0, ge=0)
    personal_pension_open_mode: PersonalPensionOpenMode = "auto_tax_optimal"
    personal_pension_account_open_month: str = ""
    personal_pension_contribution_mode: PersonalPensionContributionMode = "auto_tax_optimal"
    personal_pension_monthly_contribution: float = Field(0, ge=0)
    personal_pension_annual_contribution_target: float = Field(0, ge=0)
    personal_pension_contribution_month: int = Field(12, ge=1, le=12)
    personal_pension_contribution_start_month: str = ""
    personal_pension_contribution_end_month: str | None = None
    personal_pension_annual_return: float = Field(0.025, ge=-0.5, le=0.5)
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
                "monthly_extra_cash_expense": data.get("monthly_extra_cash_expense", 0),
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
    annual_bonus: float = Field(0, ge=0)
    annual_bonus_payout_mode: AnnualBonusPayoutMode = "lump_sum"
    annual_bonus_payout_month: int = Field(4, ge=1, le=12)
    annual_bonus_earning_start_month: str = ""
    annual_bonus_earning_end_month: str = ""
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
        "not_eligible",
    ] = "unknown"
    beijing_indicator_expected_delay_months: int = Field(0, ge=0, le=240)
    vehicle_vessel_tax_annual_override: float | None = Field(None, ge=0)
    planning_sequence: int = Field(1, ge=1, le=50)
    purchase_timing_mode: Literal["auto_sequence", "parallel", "manual_month"] = "auto_sequence"
    after_previous_event_delay_months: int = Field(0, ge=0, le=240)
    manual_purchase_delay_months: int = Field(0, ge=0, le=600)
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
    vehicle_service_years: int = Field(15, ge=1, le=30)
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
    after_previous_purchase_delay_months: int = Field(0, ge=0, le=240)
    earliest_purchase_delay_months: int = Field(0, ge=0, le=600)
    notes: str = ""


class PlanningGoalData(BaseModel):
    schema_version: int = Field(34, ge=1)
    goal_type: PlanningGoalType = "home"
    name: str = "规划目标"
    enabled: bool = True
    priority: int = Field(1, ge=1, le=100)
    timing_mode: PlanningTimingMode = "auto_sequence"
    earliest_purchase_month: str = ""
    earliest_purchase_delay_months: int = Field(0, ge=0, le=600)
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
    tax_deductible_elderly_care: bool = False
    notes: str = ""


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
    monthly_preparation_cost: float = Field(1000, ge=0)
    monthly_pregnancy_cost: float = Field(2000, ge=0)
    birth_medical_cost: float = Field(20000, ge=0)
    postpartum_recovery_cost: float = Field(30000, ge=0)
    initial_baby_supplies_cost: float = Field(15000, ge=0)
    monthly_childcare_cost_before_kindergarten: float = Field(0, ge=0)
    monthly_kindergarten_cost: float = Field(0, ge=0)
    monthly_primary_secondary_cost: float = Field(0, ge=0)
    monthly_higher_education_cost: float = Field(0, ge=0)
    kindergarten_entry_cost: float = Field(0, ge=0)
    primary_school_entry_cost: float = Field(0, ge=0)
    higher_education_entry_cost: float = Field(0, ge=0)
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


class HouseholdData(BaseModel):
    schema_version: int = Field(43, ge=1)
    name: str = "未命名家庭"
    monthly_income: float = Field(0, ge=0)
    monthly_expense: float = Field(0, ge=0)
    monthly_debt_payment: float = Field(0, ge=0)
    cash_account_balance: float = Field(0, ge=0)
    investments: float = Field(0, ge=0)
    income_projection_year: int = Field(2027, ge=2024, le=2050)
    monthly_rent_from_housing_fund: float = Field(0, ge=0)
    family_provident_support_enabled: bool = False
    family_provident_support_label: str = "亲属异地公积金首付支持"
    family_down_payment_support_mode: str = "provident"
    family_savings_support_amount: float = Field(0, ge=0)
    family_provident_initial_balance: float = Field(0, ge=0)
    family_provident_monthly_salary: float = Field(0, ge=0)
    family_provident_total_rate: float = Field(0.24, ge=0, le=0.5)
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
    existing_home_count: int = Field(0, ge=0, le=10)
    existing_mortgage_count: int = Field(0, ge=0, le=10)
    has_beijing_hukou: bool = True
    social_security_months: int = Field(0, ge=0)
    child_count: int = Field(0, ge=0, le=10)
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
    name: str = "示例房源（请修改）"
    enabled: bool = True
    purchase_sequence: int = Field(1, ge=1, le=20)
    purchase_planning_mode: Literal["after_previous_purchase", "parallel"] = "after_previous_purchase"
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
    micro_commercial_loan_ratio: float = Field(0, ge=0, le=1)
    commercial_rate: float = Field(0.035, ge=0, le=0.2)
    provident_rate: float = Field(0.026, ge=0, le=0.2)
    loan_years: int = Field(25, ge=1, le=30)
    repayment_method: RepaymentMethod = "equal_installment"
    commercial_repayment_method: RepaymentMethod = "equal_installment"
    provident_repayment_method: RepaymentMethod = "equal_installment"
    commercial_prepayment_mode: CommercialPrepaymentMode = "auto"
    commercial_prepayment_enabled: bool = False
    commercial_prepayment_start_month: int = Field(1, ge=1, le=360)
    commercial_prepayment_allowed_after_month: int = Field(12, ge=1, le=360)
    commercial_prepayment_monthly_amount: float = Field(0, ge=0)
    provident_account_repayment_strategy: ProvidentAccountRepaymentStrategy = "auto"
    deed_tax_rate: float = Field(0.015, ge=0, le=0.2)
    broker_fee_rate: float = Field(0.022, ge=0, le=0.2)
    seller_tax_pass_through_enabled: bool = False
    seller_tax_pass_through_rate: float = Field(0, ge=0, le=0.2)
    seller_tax_pass_through_amount: float = Field(0, ge=0)
    renovation_cost: float = Field(250000, ge=0)
    renovation_funding_mode: RenovationFundingMode = "after_purchase_saving"
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
            "vehicle_purchase_tax_rate": 0.10,
            "vehicle_purchase_tax_taxable_price_ratio": 1 / 1.13,
            "new_energy_vehicle_purchase_tax_exempt_until": "2025-12",
            "new_energy_vehicle_purchase_tax_exemption_cap": 30000,
            "new_energy_vehicle_purchase_tax_half_until": "2027-12",
            "new_energy_vehicle_purchase_tax_half_relief_cap": 15000,
            "new_energy_vehicle_types": ["pure_electric", "plug_in_hybrid", "range_extended", "fuel_cell"],
            "new_energy_vehicle_vessel_tax_exempt_types": ["pure_electric", "fuel_cell"],
            "plug_in_hybrid_vehicle_vessel_tax_annual": 0,
            "plug_in_hybrid_vehicle_vessel_tax_exempt_until": "2026-12",
            "fuel_vehicle_vessel_tax_annual_default": 420,
            "beijing_small_passenger_indicator_required": True,
            "beijing_new_energy_family_indicator_priority": True,
            "beijing_personal_new_energy_indicator_wait_risk_months": 60,
            "beijing_vehicle_policy_notes": [
                "车辆购置税按不含增值税计税价格乘 10% 估算；新能源车按国家延续优化政策在 2025 年底前免征、2026-2027 年减半并受单车减税上限约束。",
                "北京小客车上牌需要指标。家庭新能源指标优先于个人轮候，若未取得指标，购车策略应把预计等待月份纳入买车时间。",
                "纯电动乘用车因无排量通常不属于车船税征税范围；插混、增程和燃油车按规则包或用户覆盖值估算年度车船税。",
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


class MarketSnapshotData(BaseModel):
    schema_version: int = Field(34, ge=1)
    region: str = "北京"
    snapshot_date: str = "2026-06-29"
    source_name: str = "手动录入"
    source_url: str = "https://zjw.beijing.gov.cn/bjjs/fwgl/fdcjy/index.shtml"
    avg_unit_price: float | None = None
    transaction_count: int | None = None
    listing_count: int | None = None
    notes: str = ""


class MarketSnapshotRecord(BaseModel):
    id: str
    data: MarketSnapshotData
    created_at: datetime
    updated_at: datetime


class MarketSnapshotCreate(BaseModel):
    data: MarketSnapshotData


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
    months_to_buy: int | None
    years_to_buy: float | None
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
    pension_interest: float
    pension_balance_end: float
    medical_balance_start: float
    medical_contribution: float
    medical_retiree_transfer: float = 0.0
    medical_interest: float
    medical_outflow: float = 0.0
    medical_balance_end: float
    retired: bool = False


class SocialSecurityVisualizationPoint(BaseModel):
    plan_variant: str
    month: int
    pension_balance_start: float
    pension_contribution: float
    pension_interest: float
    pension_balance_end: float
    medical_balance_start: float
    medical_contribution: float
    medical_retiree_transfer: float = 0.0
    medical_interest: float
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
    monthly_cash_delta: float
    cash_income: float
    pension_income: float = 0.0
    living_expense: float
    scheduled_expense: float
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
    investment_contribution: float
    investment_contribution_base: float = 0.0
    investment_contribution_cash_sweep: float = 0.0
    investment_return: float
    investment_tax: float = 0.0
    investment_fee: float
    investment_buy_fee: float = 0.0
    investment_sell_fee: float = 0.0
    investment_sell_proceeds: float = 0.0
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


class AccountConceptSummary(BaseModel):
    code: str
    name: str
    category: Literal["account", "cash", "investment", "provident", "social_security", "fixed_asset", "loan", "policy"]
    description: str
    managed_by: Literal["backend", "user_input", "policy"]


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


class TaxStrategyItem(BaseModel):
    deduction_type: SpecialDeductionType
    title: str
    status: TaxStrategyStatus = "available"
    member_name: str = ""
    monthly_amount: float = 0.0
    annual_amount: float = 0.0
    start_month: str = ""
    end_month: str | None = None
    reason: str = ""
    conflicts_with: list[str] = Field(default_factory=list)
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
    cash_reserve_months: float = 0.0
    equity_ratio: float = 0.0
    bond_ratio: float = 0.0
    cash_ratio: float = 0.0
    score: int = Field(0, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class AnnualFinancialSummary(BaseModel):
    plan_variant: str
    year: int
    months: int
    cash_income: float = 0.0
    pension_income: float = 0.0
    living_expense: float = 0.0
    scheduled_expense: float = 0.0
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
    provident_deposit: float = 0.0
    provident_withdrawal: float = 0.0
    pension_account_contribution: float = 0.0
    pension_account_interest: float = 0.0
    pension_account_balance_end: float = 0.0
    medical_account_contribution: float = 0.0
    medical_account_retiree_transfer: float = 0.0
    medical_account_interest: float = 0.0
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


class StressResult(BaseModel):
    name: str
    status: str
    monthly_payment: float
    post_purchase_cash_flow: float
    debt_to_income_ratio: float
    emergency_months: float


class AffordabilityRequest(BaseModel):
    household: HouseholdData
    scenario: ScenarioData
    rule_pack: RulePackData
    include_stress_tests: bool = False


class AffordabilityResult(BaseModel):
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
    commercial_loan: LoanSummary | None
    provident_loan: LoanSummary | None
    tax_summaries: list[TaxMemberSummary]
    tax_year_summaries: list[TaxYearSummary] = []
    tax_monthly_points: list[TaxMonthlyPoint] = []
    tax_events: list[TaxEventPoint] = []
    tax_strategy_items: list[TaxStrategyItem] = []
    career_shock_projection: CareerShockProjection | None = None
    investment_plan_recommendations: list[InvestmentPlanRecommendation] = Field(default_factory=list)
    current_investment_allocation: InvestmentAllocationSummary | None = None
    child_plan_strategies: list[ChildPlanStrategyPoint] = Field(default_factory=list)
    annual_financial_summaries: list[AnnualFinancialSummary] = Field(default_factory=list)
    purchase_plan_analyses: list[PurchasePlanAnalysis]
    yield_sensitivity: list[YieldSensitivityPoint]
    monthly_cashflow_visualization: list[MonthlyCashflowPoint] = []
    account_snapshots: list[AccountSnapshotPoint] = []
    monthly_ledger: list[MonthlyLedgerEntry] = []
    loan_visualization: list[LoanVisualizationPoint] = []
    provident_visualization: list[ProvidentVisualizationPoint] = []
    social_security_visualization: list[SocialSecurityVisualizationPoint] = []
    account_concepts: list[AccountConceptSummary] = []
    strategy_explanations: list[StrategyExplanationPoint] = []
    plan_events: list[PlanEventPoint] = []
    stress_tests: list[StressResult]
    assumptions: list[str]
