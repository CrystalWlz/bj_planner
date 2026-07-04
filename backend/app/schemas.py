from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


RepaymentMethod = Literal["equal_installment", "equal_principal"]
RuleStatus = Literal["draft", "active", "archived"]
BonusTaxMethod = Literal["separate", "merged", "best"]
IncomeStageKind = Literal["salary", "unemployment", "freelance", "pension", "manual"]
GreenBuildingLevel = Literal["none", "two_star", "three_star"]
PrefabBuildingLevel = Literal["none", "A", "AA", "AAA"]
BuildingStructure = Literal["unknown", "brick_mixed", "steel_concrete"]
RenovationFundingMode = Literal["after_purchase_saving", "upfront_cash"]
InvestmentWithdrawalMode = Literal["auto", "full_liquidation", "manual_reserve"]
RetirementCategory = Literal["male_60", "female_55", "female_50"]


class IncomeMember(BaseModel):
    name: str = "成员 1"
    birth_month: str = ""
    current_age: int = Field(30, ge=0, le=120)
    retirement_category: RetirementCategory = "male_60"
    provident_fund_balance: float = Field(0, ge=0)
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
                    stage_kind="salary",
                    start_date=self.employment_start_date,
                    monthly_salary_gross=self.monthly_salary_gross,
                    annual_bonus=self.annual_bonus,
                    annual_bonus_payout_month=4,
                    monthly_freelance_income=0,
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
    stage_kind: IncomeStageKind = "salary"
    start_date: str = "2026-07-01"
    end_date: str | None = None
    monthly_salary_gross: float = Field(0, ge=0)
    annual_bonus: float = Field(0, ge=0)
    annual_bonus_payout_month: int = Field(4, ge=1, le=12)
    monthly_freelance_income: float = Field(0, ge=0)
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
    auto_pension_income: bool = True
    unemployment_benefit_months: int = Field(24, ge=0, le=24)
    unemployment_benefit_monthly: float = Field(0, ge=0)
    self_social_insurance_monthly: float = Field(0, ge=0)
    self_housing_fund_monthly: float = Field(0, ge=0)

class VehiclePlanData(BaseModel):
    enabled: bool = False
    name: str = "车辆计划"
    selected_strategy_variant: str = "手动设置"
    candidate_vehicles: list["VehiclePlanData"] = Field(default_factory=list)
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
    second_car_enabled: bool = False
    second_car_total_price: float = Field(0, ge=0)
    second_car_down_payment_ratio: float = Field(0.40, ge=0, le=1)
    second_car_purchase_delay_months: int = Field(60, ge=0, le=240)
    second_car_total_months: int = Field(60, ge=1, le=120)
    second_car_interest_free_months: int = Field(24, ge=0, le=120)
    second_car_later_annual_rate: float = Field(0.0199, ge=0, le=0.5)
    second_car_annual_mileage_km: float = Field(0, ge=0, le=100000)
    second_car_monthly_parking_cost: float = Field(0, ge=0)


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


class PhasedLoanData(BaseModel):
    borrower: str = "成员 1"
    name: str = "目前贷款"
    loan_type: Literal["mortgage", "car", "education", "consumer", "other"] = "other"
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
    schema_version: int = Field(17, ge=1)
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
    required_liquidity_months: float = Field(6, ge=0, le=36)
    borrower_age: int = Field(30, ge=18, le=68)
    borrower_member_index: int = Field(0, ge=0, le=20)
    career_shock: CareerShockData = Field(default_factory=CareerShockData)
    career_shock_applied: bool = False
    car_plan: CarPlanData = Field(default_factory=CarPlanData)
    property_goals: list[PropertyPurchaseGoalData] = Field(default_factory=list)
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
    schema_version: int = Field(17, ge=1)
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
    commercial_prepayment_enabled: bool = False
    commercial_prepayment_start_month: int = Field(1, ge=1, le=360)
    commercial_prepayment_allowed_after_month: int = Field(12, ge=1, le=360)
    commercial_prepayment_monthly_amount: float = Field(0, ge=0)
    deed_tax_rate: float = Field(0.015, ge=0, le=0.2)
    broker_fee_rate: float = Field(0.022, ge=0, le=0.2)
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
    schema_version: int = Field(17, ge=1)
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
            "second_home_provident_min_down_payment_ratio": 0.30,
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
            "backend_parallel_workers": 4,
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
    schema_version: int = Field(17, ge=1)
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
    prepayment_enabled: bool = False
    prepayment_start_month: int = 1
    prepayment_allowed_after_month: int = 12
    prepayment_monthly_amount: float = 0.0
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


class CarPlanAnalysis(BaseModel):
    variant: str
    description: str
    vehicle_index: int = 0
    vehicle_name: str = "车辆计划"
    vehicle_candidate_index: int | None = None
    vehicle_candidate_name: str = ""
    strategy_key: str = ""
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
    prepayment_enabled: bool = False
    prepayment_start_month: int = 1
    prepayment_allowed_after_month: int = 12
    prepayment_monthly_amount: float = 0.0
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
    commercial_loan_years: int
    provident_loan_years: int
    provident_loan_year_limit_reasons: list[str]
    commercial_repayment_method: RepaymentMethod
    provident_repayment_method: RepaymentMethod
    commercial_monthly_payment: float
    provident_monthly_payment: float
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
    provident_extraction_notes: list[str]
    happiness_breakdown: list[dict[str, float | str]]


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
    total_monthly_payment: float
    cash_monthly_payment: float
    provident_offset_payment: float = 0.0
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
    loan_offset_payment: float
    retirement_withdrawal: float = 0.0
    total_inflow: float
    total_outflow: float
    balance_end: float
    strategy_label: str
    member_accounts: list[ProvidentMemberAccountPoint] = Field(default_factory=list)


class MonthlyLedgerEntry(BaseModel):
    plan_variant: str
    month: int
    account: str
    category: str
    label: str
    amount: float
    direction: Literal["inflow", "outflow", "transfer", "valuation"]
    source: str = "backend"


class AccountSnapshotPoint(BaseModel):
    plan_variant: str
    month: int
    cash_balance: float
    investment_balance: float
    liquid_asset_value: float = 0.0
    provident_balance: float
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
    fixed_asset_value: float
    total_asset_value: float
    total_loan_balance: float
    net_worth: float
    monthly_cash_delta: float
    cash_income: float
    living_expense: float
    scheduled_expense: float
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
    category: Literal["account", "cash", "investment", "provident", "fixed_asset", "loan", "policy"]
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
    monthly_cashflow_visualization: list[MonthlyCashflowPoint] = []
    account_snapshots: list[AccountSnapshotPoint] = []
    monthly_ledger: list[MonthlyLedgerEntry] = []
    loan_visualization: list[LoanVisualizationPoint] = []
    provident_visualization: list[ProvidentVisualizationPoint] = []
    account_concepts: list[AccountConceptSummary] = []
    strategy_explanations: list[StrategyExplanationPoint] = []
    plan_events: list[PlanEventPoint] = []
    stress_tests: list[StressResult]
    assumptions: list[str]
