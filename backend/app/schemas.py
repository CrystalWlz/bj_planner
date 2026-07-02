from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


RepaymentMethod = Literal["equal_installment", "equal_principal"]
RuleStatus = Literal["draft", "active", "archived"]
BonusTaxMethod = Literal["separate", "merged", "best"]
GreenBuildingLevel = Literal["none", "two_star", "three_star"]
PrefabBuildingLevel = Literal["none", "A", "AA", "AAA"]
BuildingStructure = Literal["unknown", "brick_mixed", "steel_concrete"]
RenovationFundingMode = Literal["after_purchase_saving", "upfront_cash"]


class IncomeMember(BaseModel):
    name: str = "成员 1"
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

    @model_validator(mode="after")
    def ensure_default_income_stage(self) -> "IncomeMember":
        if not self.income_stages:
            self.income_stages = [
                IncomeStageData(
                    name="当前收入",
                    start_date=self.employment_start_date,
                    monthly_salary_gross=self.monthly_salary_gross,
                    annual_bonus=self.annual_bonus,
                    monthly_non_taxable_income=self.monthly_non_taxable_income,
                    monthly_extra_cash_expense=self.monthly_extra_cash_expense,
                    monthly_social_insurance=self.monthly_social_insurance,
                    monthly_housing_fund=self.monthly_housing_fund,
                    housing_fund_personal_rate=self.housing_fund_personal_rate,
                    housing_fund_employer_rate=self.housing_fund_employer_rate,
                    monthly_special_additional_deduction=self.monthly_special_additional_deduction,
                    other_annual_deductions=self.other_annual_deductions,
                    other_annual_taxable_income=self.other_annual_taxable_income,
                    bonus_tax_method=self.bonus_tax_method,
                )
            ]
        return self


class IncomeStageData(BaseModel):
    name: str = "当前收入"
    start_date: str = "2026-07-01"
    end_date: str | None = None
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
    bonus_tax_method: BonusTaxMethod = "best"
    payroll_contributions_enabled: bool = True


class CareerShockData(BaseModel):
    enabled: bool = False
    layoff_member_name: str = "成员 1"
    layoff_age: int = Field(35, ge=18, le=80)
    self_birth_month: str = ""
    spouse_birth_month: str = ""
    self_current_age: int = Field(30, ge=18, le=80)
    spouse_current_age: int = Field(30, ge=18, le=80)
    unemployment_benefit_months: int = Field(24, ge=0, le=24)
    unemployment_benefit_monthly: float = Field(0, ge=0)
    self_social_insurance_monthly: float = Field(0, ge=0)
    self_retirement_age: int = Field(63, ge=50, le=70)
    spouse_retirement_age: int = Field(58, ge=50, le=70)
    self_pension_monthly: float = Field(0, ge=0)
    spouse_pension_monthly: float = Field(0, ge=0)


class CarPlanData(BaseModel):
    enabled: bool = False
    name: str = "车辆计划"
    selected_strategy_variant: str = "手动设置"
    total_price: float = Field(0, ge=0)
    down_payment_ratio: float = Field(0.50, ge=0, le=1)
    down_payment: float = Field(0, ge=0)
    purchase_delay_months: int = Field(0, ge=0, le=120)
    total_months: int = Field(60, ge=1, le=120)
    interest_free_months: int = Field(24, ge=0, le=120)
    later_annual_rate: float = Field(0.0199, ge=0, le=0.5)
    current_month_index: int = Field(1, ge=1, le=120)
    saving_start_date: str = "2026-07-01"
    monthly_operating_cost: float = Field(0, ge=0)
    no_car_monthly_commute_cost: float = Field(0, ge=0)
    annual_mileage_km: float = Field(0, ge=0, le=100000)
    electricity_kwh_per_100km: float = Field(14, ge=0, le=50)
    electricity_price_per_kwh: float = Field(0.8, ge=0, le=5)
    monthly_parking_cost: float = Field(0, ge=0)
    annual_maintenance_cost: float = Field(0, ge=0)
    annual_insurance_rate: float = Field(0.018, ge=0, le=0.2)
    annual_insurance_min: float = Field(0, ge=0)
    depreciation_years: int = Field(8, ge=1, le=20)
    vehicle_service_years: int = Field(15, ge=1, le=30)
    vehicle_retirement_mileage_km: float = Field(600000, ge=0, le=1000000)
    second_car_enabled: bool = False
    second_car_total_price: float = Field(0, ge=0)
    second_car_down_payment_ratio: float = Field(0.40, ge=0, le=1)
    second_car_purchase_delay_months: int = Field(60, ge=0, le=240)
    second_car_total_months: int = Field(60, ge=1, le=120)
    second_car_interest_free_months: int = Field(24, ge=0, le=120)
    second_car_later_annual_rate: float = Field(0.0199, ge=0, le=0.5)
    second_car_annual_mileage_km: float = Field(0, ge=0, le=100000)
    second_car_monthly_parking_cost: float = Field(0, ge=0)
    happiness_score: float = Field(6.5, ge=0, le=10)
    notes: str = ""


class PhasedLoanData(BaseModel):
    borrower: str = "成员 1"
    name: str = "阶段性贷款"
    principal: float = Field(0, ge=0)
    annual_rate: float = Field(0.028, ge=0, le=0.2)
    repayment_method: RepaymentMethod = "equal_installment"
    remaining_months: int = Field(120, ge=1, le=360)
    interest_start_month: str = "2026-07"
    interest_only_until: str = "2028-07"


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


class ScheduledExpenseData(BaseModel):
    name: str = "定时支出"
    monthly_amount: float = Field(0, ge=0)
    start_month: str = "2026-07"
    end_month: str | None = None
    tax_deductible_elderly_care: bool = False
    notes: str = ""


class ElderlyDependentData(BaseModel):
    member_name: str = "成员 1"
    relationship_label: str = "直系亲属老人"
    birth_month: str = ""
    is_only_child: bool = False
    shared_monthly_deduction: float = Field(1500, ge=0, le=3000)


class HouseholdData(BaseModel):
    name: str = "未命名家庭"
    monthly_income: float = Field(0, ge=0)
    monthly_expense: float = Field(0, ge=0)
    monthly_debt_payment: float = Field(0, ge=0)
    liquid_assets: float = Field(0, ge=0)
    investments: float = Field(0, ge=0)
    income_projection_year: int = Field(2027, ge=2024, le=2050)
    monthly_rent_from_housing_fund: float = Field(0, ge=0)
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
    required_liquidity_months: float = Field(6, ge=0, le=36)
    borrower_age: int = Field(30, ge=18, le=68)
    career_shock: CareerShockData = Field(default_factory=CareerShockData)
    career_shock_applied: bool = False
    car_plan: CarPlanData = Field(default_factory=CarPlanData)
    phased_loans: list[PhasedLoanData] = Field(default_factory=list)
    scheduled_expenses: list[ScheduledExpenseData] = Field(default_factory=list)
    elderly_dependents: list[ElderlyDependentData] = Field(default_factory=list)
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
    name: str = "示例房源（请修改）"
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
    micro_commercial_loan_ratio: float = Field(0, ge=0, le=1)
    commercial_rate: float = Field(0.035, ge=0, le=0.2)
    provident_rate: float = Field(0.0285, ge=0, le=0.2)
    loan_years: int = Field(25, ge=1, le=30)
    repayment_method: RepaymentMethod = "equal_installment"
    commercial_repayment_method: RepaymentMethod = "equal_installment"
    provident_repayment_method: RepaymentMethod = "equal_installment"
    deed_tax_rate: float = Field(0.015, ge=0, le=0.2)
    broker_fee_rate: float = Field(0.022, ge=0, le=0.2)
    renovation_cost: float = Field(250000, ge=0)
    renovation_funding_mode: RenovationFundingMode = "after_purchase_saving"
    moving_and_misc_cost: float = Field(50000, ge=0)
    annual_investment_return: float = Field(0.025, ge=-0.5, le=0.5)
    happiness_score: float = Field(7.0, ge=0, le=10)
    commute_score: float = Field(7.0, ge=0, le=10)
    school_score: float = Field(6.0, ge=0, le=10)
    liquidity_priority_score: float = Field(7.0, ge=0, le=10)
    notes: str = ""
    selected_purchase_plan_variant: str = ""


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
            "provident_max_loan_years": 30,
            "provident_max_borrower_age": 68,
            "provident_brick_mixed_total_life_years": 50,
            "provident_steel_concrete_total_life_years": 60,
            "provident_property_age_safety_deduction_years": 3,
            "provident_upfront_purchase_extract_ratio": 0.0,
            "provident_upfront_purchase_extract_ratio_new_home": 1.0,
            "provident_upfront_purchase_extract_ratio_second_hand": 0.0,
            "provident_post_transaction_extract_ratio": 1.0,
            "provident_monthly_withdrawal_after_purchase_enabled": True,
            "provident_post_purchase_withdrawal_mode": "purchase_agreed",
            "provident_balance_annual_interest_rate": 0.015,
            "micro_commercial_loan_ratio": 0.05,
            "micro_commercial_loan_ratio_min": 0.02,
            "micro_commercial_loan_ratio_max": 0.12,
            "recommended_emergency_months": 6,
            "caution_dti": 0.40,
            "danger_dti": 0.50,
            "default_deed_tax_rate": 0.015,
            "default_broker_fee_rate": 0.022,
            "rate_stress_add": 0.005,
            "income_stress_factor": 0.90,
            "price_stress_factor": 1.05,
            "personal_standard_deduction_annual": 60000,
            "annual_bonus_separate_tax_valid_until": "2027-12-31",
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
    purchase_delay_months: int
    loan_principal: float
    months_to_down_payment: int | None
    years_to_down_payment: float | None
    first_phase_monthly_payment: float
    later_phase_monthly_payment: float
    current_monthly_payment: float
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


class CarPlanAnalysis(BaseModel):
    variant: str
    description: str
    purchase_delay_months: int
    months_to_buy: int | None
    years_to_buy: float | None
    total_price: float
    down_payment_ratio: float
    down_payment: float
    loan_principal: float
    total_months: int
    interest_free_months: int
    later_annual_rate: float
    first_phase_monthly_payment: float
    later_phase_monthly_payment: float
    expected_monthly_payment_after_purchase: float
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


class PurchasePlanAnalysis(BaseModel):
    variant: str
    description: str
    months_to_buy: int | None
    years_to_buy: float | None
    minimum_down_payment: float
    planned_down_payment: float
    provident_fund_extractable: float
    provident_upfront_extractable: float
    provident_post_transaction_extractable: float
    required_cash_after_pf_extract: float
    upfront_cash_required: float
    commercial_loan_amount: float
    provident_loan_amount: float
    provident_policy_bonus: float
    provident_policy_cap: float
    commercial_loan_years: int
    provident_loan_years: int
    provident_loan_year_limit_reasons: list[str]
    commercial_repayment_method: RepaymentMethod
    provident_repayment_method: RepaymentMethod
    commercial_monthly_payment: float
    provident_monthly_payment: float
    total_monthly_payment: float
    total_interest: float
    renovation_cost: float
    renovation_funding_mode: RenovationFundingMode
    renovation_included_in_upfront_cash: bool
    months_to_renovation: int | None
    years_to_renovation: float | None
    post_purchase_renovation_monthly_saving: float
    cash_after_transaction: float
    cash_after_purchase: float
    provident_balance_after_extract: float
    required_liquidity_reserve: float
    liquidity_ok: bool
    minimum_cash_balance: float = 0.0
    minimum_cash_balance_month: int | None = None
    cash_stress_ok: bool = True
    post_purchase_cash_flow: float
    monthly_post_purchase_pf_withdrawal: float
    post_purchase_cash_flow_with_pf_withdrawal: float
    debt_to_income_ratio: float
    happiness_score: float
    provident_extraction_notes: list[str]
    happiness_breakdown: list[dict[str, float | str]]


class YieldSensitivityPoint(BaseModel):
    annual_return: float
    months_to_buy: int | None
    years_to_buy: float | None
    cash_after_purchase: float


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
    purchase_plan_analyses: list[PurchasePlanAnalysis]
    yield_sensitivity: list[YieldSensitivityPoint]
    stress_tests: list[StressResult]
    assumptions: list[str]
