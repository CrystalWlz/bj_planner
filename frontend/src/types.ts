export type RepaymentMethod = "equal_installment" | "equal_principal";
export type RuleStatus = "draft" | "active" | "archived";
export type BonusTaxMethod = "separate" | "merged" | "best";
export type GreenBuildingLevel = "none" | "two_star" | "three_star";
export type PrefabBuildingLevel = "none" | "A" | "AA" | "AAA";
export type BuildingStructure = "unknown" | "brick_mixed" | "steel_concrete";
export type RenovationFundingMode = "after_purchase_saving" | "upfront_cash";

export interface IncomeMember {
  name: string;
  monthly_salary_gross: number;
  annual_bonus: number;
  monthly_social_insurance: number;
  monthly_housing_fund: number;
  housing_fund_personal_rate: number;
  housing_fund_employer_rate: number;
  monthly_special_additional_deduction: number;
  other_annual_deductions: number;
  other_annual_taxable_income: number;
  employment_start_date: string;
  bonus_tax_method: BonusTaxMethod;
  income_stages: IncomeStageData[];
}

export interface IncomeStageData {
  name: string;
  start_date: string;
  end_date: string | null;
  monthly_salary_gross: number;
  annual_bonus: number;
  monthly_non_taxable_income: number;
  monthly_extra_cash_expense: number;
  monthly_social_insurance: number;
  monthly_housing_fund: number;
  housing_fund_personal_rate: number;
  housing_fund_employer_rate: number;
  monthly_special_additional_deduction: number;
  other_annual_deductions: number;
  other_annual_taxable_income: number;
  bonus_tax_method: BonusTaxMethod;
  payroll_contributions_enabled: boolean;
}

export interface CareerShockData {
  enabled: boolean;
  layoff_member_name: string;
  layoff_age: number;
  self_birth_month: string;
  spouse_birth_month: string;
  self_current_age: number;
  spouse_current_age: number;
  unemployment_benefit_months: number;
  unemployment_benefit_monthly: number;
  self_social_insurance_monthly: number;
  self_retirement_age: number;
  spouse_retirement_age: number;
  self_pension_monthly: number;
  spouse_pension_monthly: number;
}

export interface CarPlanData {
  enabled: boolean;
  name: string;
  selected_strategy_variant: string;
  total_price: number;
  down_payment_ratio: number;
  down_payment: number;
  purchase_delay_months: number;
  total_months: number;
  interest_free_months: number;
  later_annual_rate: number;
  current_month_index: number;
  saving_start_date: string;
  monthly_operating_cost: number;
  no_car_monthly_commute_cost: number;
  annual_mileage_km: number;
  electricity_kwh_per_100km: number;
  electricity_price_per_kwh: number;
  monthly_parking_cost: number;
  annual_maintenance_cost: number;
  annual_insurance_rate: number;
  annual_insurance_min: number;
  depreciation_years: number;
  vehicle_service_years: number;
  vehicle_retirement_mileage_km: number;
  second_car_enabled: boolean;
  second_car_total_price: number;
  second_car_down_payment_ratio: number;
  second_car_purchase_delay_months: number;
  second_car_total_months: number;
  second_car_interest_free_months: number;
  second_car_later_annual_rate: number;
  second_car_annual_mileage_km: number;
  second_car_monthly_parking_cost: number;
  happiness_score: number;
  notes: string;
}

export interface StudentLoanData {
  borrower: string;
  name: string;
  principal: number;
  annual_rate: number;
  repayment_method: RepaymentMethod;
  remaining_months: number;
  interest_start_month: string;
  interest_only_until: string;
}

export interface ScheduledExpenseData {
  name: string;
  monthly_amount: number;
  start_month: string;
  end_month: string | null;
  tax_deductible_elderly_care: boolean;
  notes: string;
}

export interface ElderlyDependentData {
  member_name: string;
  relationship_label: string;
  birth_month: string;
  is_only_child: boolean;
  shared_monthly_deduction: number;
}

export interface HouseholdData {
  name: string;
  monthly_income: number;
  monthly_expense: number;
  monthly_debt_payment: number;
  liquid_assets: number;
  investments: number;
  income_projection_year: number;
  monthly_rent_from_housing_fund: number;
  investment_plan_name: string;
  investment_risk_level: string;
  monthly_investment_amount: number;
  investment_cash_reserve_months: number;
  investment_equity_ratio: number;
  investment_bond_ratio: number;
  investment_cash_ratio: number;
  investment_auto_rebalance: boolean;
  investment_buy_fee_rate: number;
  investment_sell_fee_rate: number;
  required_liquidity_months: number;
  borrower_age: number;
  career_shock: CareerShockData;
  career_shock_applied?: boolean;
  car_plan: CarPlanData;
  student_loans: StudentLoanData[];
  scheduled_expenses: ScheduledExpenseData[];
  elderly_dependents: ElderlyDependentData[];
  existing_home_count: number;
  existing_mortgage_count: number;
  has_beijing_hukou: boolean;
  social_security_months: number;
  child_count: number;
  provident_fund_balance: number;
  provident_fund_monthly_deposit: number;
  members: IncomeMember[];
  notes: string;
}

export interface ScenarioData {
  name: string;
  district: string;
  ring_area: string;
  property_type: string;
  green_building_level: GreenBuildingLevel;
  prefab_building_level: PrefabBuildingLevel;
  is_ultra_low_energy_building: boolean;
  building_age_years: number;
  building_structure: BuildingStructure;
  is_old_community_renovated: boolean;
  remaining_land_use_years: number | null;
  total_price: number;
  area_sqm: number;
  down_payment_amount: number;
  commercial_loan_amount: number;
  provident_loan_amount: number;
  micro_commercial_loan_ratio: number;
  commercial_rate: number;
  provident_rate: number;
  loan_years: number;
  repayment_method: RepaymentMethod;
  commercial_repayment_method: RepaymentMethod;
  provident_repayment_method: RepaymentMethod;
  deed_tax_rate: number;
  broker_fee_rate: number;
  renovation_cost: number;
  renovation_funding_mode: RenovationFundingMode;
  moving_and_misc_cost: number;
  annual_investment_return: number;
  happiness_score: number;
  commute_score: number;
  school_score: number;
  liquidity_priority_score: number;
  notes: string;
  selected_purchase_plan_variant: string;
}

export interface RulePackData {
  name: string;
  jurisdiction: string;
  category: string;
  effective_date: string;
  source_url: string;
  status: RuleStatus;
  notes: string;
  params: Record<string, number | string | boolean | Array<Record<string, number>>>;
}

export interface RecordEnvelope<T> {
  id: string;
  data: T;
  created_at: string;
  updated_at: string;
  household_id?: string | null;
}

export interface LoanSummary {
  principal: number;
  annual_rate: number;
  years: number;
  repayment_method: RepaymentMethod;
  first_month_payment: number;
  average_month_payment: number;
  total_interest: number;
}

export interface CarLoanSummary {
  enabled: boolean;
  total_price: number;
  down_payment_ratio: number;
  down_payment: number;
  purchase_delay_months: number;
  loan_principal: number;
  months_to_down_payment: number | null;
  years_to_down_payment: number | null;
  first_phase_monthly_payment: number;
  later_phase_monthly_payment: number;
  current_monthly_payment: number;
  total_interest: number;
  total_months: number;
  interest_free_months: number;
  later_annual_rate: number;
  monthly_energy_cost: number;
  monthly_insurance_cost: number;
  monthly_maintenance_cost: number;
  monthly_parking_cost: number;
  monthly_cash_operating_cost: number;
  monthly_depreciation_cost: number;
  monthly_total_ownership_cost: number;
}

export interface CarPlanAnalysis {
  variant: string;
  description: string;
  purchase_delay_months: number;
  months_to_buy: number | null;
  years_to_buy: number | null;
  total_price: number;
  down_payment_ratio: number;
  down_payment: number;
  loan_principal: number;
  total_months: number;
  interest_free_months: number;
  later_annual_rate: number;
  first_phase_monthly_payment: number;
  later_phase_monthly_payment: number;
  expected_monthly_payment_after_purchase: number;
  total_interest: number;
  required_cash_at_purchase: number;
  cash_after_purchase: number;
  monthly_cash_flow_after_car: number;
  operating_cost: number;
  monthly_energy_cost: number;
  monthly_insurance_cost: number;
  monthly_maintenance_cost: number;
  monthly_parking_cost: number;
  monthly_cash_operating_cost: number;
  monthly_depreciation_cost: number;
  monthly_total_ownership_cost: number;
  happiness_score: number;
  notes: string[];
}

export interface StudentLoanSummary {
  borrower: string;
  name: string;
  principal: number;
  annual_rate: number;
  repayment_method: RepaymentMethod;
  remaining_months: number;
  interest_start_month: string;
  interest_only_until: string;
  phase: string;
  current_monthly_payment: number;
}

export interface StressResult {
  name: string;
  status: string;
  monthly_payment: number;
  post_purchase_cash_flow: number;
  debt_to_income_ratio: number;
  emergency_months: number;
}

export interface TaxMemberSummary {
  member_name: string;
  active_months: number;
  monthly_personal_social_insurance: number;
  monthly_personal_housing_fund: number;
  monthly_employer_social_insurance: number;
  monthly_employer_housing_fund: number;
  gross_annual_income: number;
  taxable_income: number;
  salary_tax: number;
  bonus_tax: number;
  total_tax: number;
  net_annual_income: number;
  net_monthly_income: number;
  selected_bonus_method: BonusTaxMethod;
}

export interface PurchasePlanAnalysis {
  variant: string;
  description: string;
  months_to_buy: number | null;
  years_to_buy: number | null;
  minimum_down_payment: number;
  planned_down_payment: number;
  provident_fund_extractable: number;
  provident_upfront_extractable: number;
  provident_post_transaction_extractable: number;
  required_cash_after_pf_extract: number;
  upfront_cash_required: number;
  commercial_loan_amount: number;
  provident_loan_amount: number;
  provident_policy_bonus: number;
  provident_policy_cap: number;
  commercial_loan_years: number;
  provident_loan_years: number;
  provident_loan_year_limit_reasons: string[];
  commercial_repayment_method: RepaymentMethod;
  provident_repayment_method: RepaymentMethod;
  commercial_monthly_payment: number;
  provident_monthly_payment: number;
  total_monthly_payment: number;
  total_interest: number;
  renovation_cost: number;
  renovation_funding_mode: RenovationFundingMode;
  renovation_included_in_upfront_cash: boolean;
  months_to_renovation: number | null;
  years_to_renovation: number | null;
  post_purchase_renovation_monthly_saving: number;
  cash_after_transaction: number;
  cash_after_purchase: number;
  provident_balance_after_extract: number;
  required_liquidity_reserve: number;
  liquidity_ok: boolean;
  minimum_cash_balance?: number;
  minimum_cash_balance_month?: number | null;
  cash_stress_ok?: boolean;
  post_purchase_cash_flow: number;
  monthly_post_purchase_pf_withdrawal: number;
  post_purchase_cash_flow_with_pf_withdrawal: number;
  debt_to_income_ratio: number;
  happiness_score: number;
  provident_extraction_notes: string[];
  happiness_breakdown: Array<{
    name: string;
    score: number;
    weight: number;
    note: string;
  }>;
}

export interface YieldSensitivityPoint {
  annual_return: number;
  months_to_buy: number | null;
  years_to_buy: number | null;
  cash_after_purchase: number;
}

export interface AffordabilityResult {
  status: string;
  status_reason: string;
  eligible: boolean;
  eligibility_notes: string[];
  total_required_cash: number;
  minimum_down_payment: number;
  stated_down_payment: number;
  taxes_and_fees: number;
  funding_gap: number;
  remaining_cash_after_purchase: number;
  household_gross_monthly_income: number;
  household_net_monthly_income: number;
  annual_income_tax: number;
  student_loan_monthly_payment: number;
  effective_monthly_debt_payment: number;
  student_loan_summaries: StudentLoanSummary[];
  car_loan: CarLoanSummary;
  car_plan_analyses: CarPlanAnalysis[];
  monthly_payment: number;
  post_purchase_cash_flow: number;
  debt_to_income_ratio: number;
  emergency_months: number;
  commercial_loan: LoanSummary | null;
  provident_loan: LoanSummary | null;
  tax_summaries: TaxMemberSummary[];
  purchase_plan_analyses: PurchasePlanAnalysis[];
  yield_sensitivity: YieldSensitivityPoint[];
  stress_tests: StressResult[];
  assumptions: string[];
}

export interface SourceDocumentRecord {
  id: string;
  name: string;
  url: string;
  fetched_at: string;
  content_hash: string;
  status: string;
  summary: string;
  changed_from_previous: boolean;
}
