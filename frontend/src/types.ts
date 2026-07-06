export type RepaymentMethod = "equal_installment" | "equal_principal";
export type RuleStatus = "draft" | "active" | "archived";
export type BonusTaxMethod = "separate" | "merged" | "best";
export type IncomeStageKind = "salary" | "unemployment" | "freelance" | "pension" | "manual";
export type GreenBuildingLevel = "none" | "two_star" | "three_star";
export type PrefabBuildingLevel = "none" | "A" | "AA" | "AAA";
export type BuildingStructure = "unknown" | "brick_mixed" | "steel_concrete";
export type RenovationFundingMode = "after_purchase_saving" | "upfront_cash";
export type CommercialPrepaymentMode = "auto" | "manual" | "none";
export type ProvidentAccountRepaymentStrategy =
  | "auto"
  | "monthly_repayment_withdrawal"
  | "semiannual_principal_offset"
  | "keep_in_account";

export interface IncomeMember {
  name: string;
  family_join_month: string;
  birth_month: string;
  current_age: number;
  retirement_category: "male_60" | "female_55" | "female_50";
  social_security_months: number;
  income_tax_months: number;
  existing_home_count: number;
  existing_mortgage_count: number;
  initial_cash_balance: number;
  initial_investments: number;
  initial_other_asset_value: number;
  initial_other_debt_balance: number;
  provident_fund_balance: number;
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
  stage_kind: IncomeStageKind;
  start_date: string;
  end_date: string | null;
  provident_account_management_center: "beijing_municipal" | "national";
  monthly_salary_gross: number;
  annual_bonus: number;
  annual_bonus_payout_month: number;
  monthly_freelance_income: number;
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

export interface CareerShockMemberSetting {
  member_name: string;
  enabled: boolean;
  layoff_age: number;
  retirement_age: number;
  freelance_income_monthly: number;
  pension_monthly: number;
  auto_pension_monthly: boolean;
}

export interface CareerShockData {
  enabled: boolean;
  member_settings: CareerShockMemberSetting[];
  auto_unemployment_benefit: boolean;
  auto_self_social_insurance: boolean;
  auto_flexible_housing_fund: boolean;
  unemployment_benefit_months: number;
  unemployment_benefit_monthly: number;
  self_social_insurance_monthly: number;
  self_housing_fund_monthly: number;
}

export interface CareerShockMemberProjection {
  member_name: string;
  enabled: boolean;
  layoff_age: number;
  retirement_age: number;
  layoff_month: string | null;
  retirement_month: string | null;
  unemployment_benefit_months: number;
  unemployment_benefit_monthly: number;
  later_unemployment_benefit_monthly: number;
  self_social_insurance_monthly: number;
  flexible_housing_fund_monthly: number;
  pension_monthly: number;
  generated_stages: IncomeStageData[];
  notes: string[];
}

export interface CareerShockProjection {
  enabled: boolean;
  unemployment_benefit_months: number;
  unemployment_benefit_monthly: number;
  later_unemployment_benefit_monthly: number;
  self_social_insurance_monthly: number;
  flexible_housing_fund_monthly: number;
  effective_members: IncomeMember[];
  member_projections: CareerShockMemberProjection[];
  notes: string[];
}

export interface InvestmentAllocationSummary {
  monthly_surplus: number;
  reserve_target: number;
  reserve_gap: number;
  base_investment: number;
  cash_sweep_investment: number;
  total_investment: number;
  buy_fee: number;
  net_investment: number;
}

export interface InvestmentPlanRecommendation {
  variant: string;
  plan_name: string;
  risk_level: string;
  risk_label: string;
  description: string;
  monthly_investment: number;
  annual_return: number;
  cash_reserve_months: number;
  equity_ratio: number;
  bond_ratio: number;
  cash_ratio: number;
  score: number;
  reasons: string[];
}

export interface VehiclePlanData {
  enabled: boolean;
  name: string;
  selected_strategy_variant: string;
  candidate_vehicles: VehiclePlanData[];
  financing_options: VehicleFinancingOptionData[];
  selected_financing_option_id: string;
  selected_financing_option_name: string;
  selected_financing_type: string;
  selected_financing_min_down_payment_ratio: number;
  selected_financing_max_down_payment_ratio: number;
  selected_financing_prepayment_allowed: boolean;
  selected_financing_prepayment_policy_note: string;
  planning_sequence: number;
  purchase_timing_mode: "auto_sequence" | "parallel" | "manual_month";
  after_previous_event_delay_months: number;
  manual_purchase_delay_months: number;
  total_price: number;
  down_payment_ratio: number;
  down_payment: number;
  purchase_delay_months: number;
  total_months: number;
  interest_free_months: number;
  later_annual_rate: number;
  loan_prepayment_enabled: boolean;
  loan_prepayment_start_month: number;
  loan_prepayment_allowed_after_month: number;
  loan_prepayment_monthly_amount: number;
  loan_prepayment_strategy_type: string;
  loan_prepayment_lump_sum_month: number;
  loan_prepayment_lump_sum_amount: number;
  current_month_index: number;
  saving_start_date: string;
  monthly_operating_cost: number;
  no_car_monthly_commute_cost: number;
  annual_mileage_km: number;
  electricity_kwh_per_100km: number;
  electricity_price_per_kwh: number;
  monthly_parking_cost: number;
  annual_maintenance_cost: number;
  annual_maintenance_growth_rate: number;
  annual_insurance_rate: number;
  annual_insurance_min: number;
  annual_insurance_growth_rate: number;
  depreciation_years: number;
  vehicle_service_years: number;
  vehicle_retirement_mileage_km: number;
  happiness_score: number;
  notes: string;
}

export interface VehicleFinancingOptionData {
  id: string;
  name: string;
  enabled: boolean;
  financing_type: "dealer_subsidy" | "standard" | "bank_loan" | "cash_only";
  total_months: number;
  interest_free_months: number;
  later_annual_rate: number;
  min_down_payment_ratio: number;
  max_down_payment_ratio: number;
  prepayment_allowed: boolean;
  prepayment_allowed_after_month: number;
  prepayment_policy_note: string;
  notes: string;
}

export interface CarPlanData extends VehiclePlanData {
  vehicle_plans: VehiclePlanData[];
}

export interface PropertyPurchaseGoalData {
  name: string;
  scenario_id: string;
  priority: number;
  enabled: boolean;
  intended_use: "self_use" | "improvement" | "investment" | "other";
  planning_mode: "after_previous_purchase" | "parallel";
  after_previous_purchase_delay_months: number;
  earliest_purchase_delay_months: number;
  notes: string;
}

export interface PhasedLoanData {
  borrower: string;
  name: string;
  loan_type?: "mortgage" | "car" | "education" | "consumer" | "other";
  principal: number;
  annual_rate: number;
  repayment_method: RepaymentMethod;
  remaining_months: number;
  interest_start_month: string;
  interest_only_until: string;
  prepayment_mode: "none" | "manual" | "auto";
  prepayment_start_month: number;
  prepayment_allowed_after_month: number;
  prepayment_monthly_amount: number;
}

export interface ExistingLoanVisualizationDetail {
  name: string;
  borrower: string;
  loan_type: "mortgage" | "car" | "education" | "consumer" | "other";
  phase: string;
  balance: number;
  monthly_payment: number;
  extra_principal_payment: number;
}

export interface ScheduledExpenseData {
  name: string;
  monthly_amount: number;
  frequency: "monthly" | "annual_once";
  annual_occurrence_month: number;
  start_month: string;
  end_month: string | null;
  tax_deductible_elderly_care: boolean;
  notes: string;
}

export interface HouseholdExpenseStageData {
  name: string;
  start_month: string;
  end_month: string | null;
  base_living_expense: number;
  other_fixed_debt_payment: number;
  rent_amount: number;
  rent_payment_mode: "cash" | "provident";
  rent_payment_frequency: "monthly" | "quarterly";
}

export interface ElderlyDependentData {
  member_name: string;
  relationship_label: string;
  birth_month: string;
  is_only_child: boolean;
  shared_monthly_deduction: number;
}

export interface HouseholdData {
  schema_version: number;
  name: string;
  monthly_income: number;
  monthly_expense: number;
  monthly_debt_payment: number;
  cash_account_balance: number;
  investments: number;
  income_projection_year: number;
  monthly_rent_from_housing_fund: number;
  family_provident_support_enabled: boolean;
  family_provident_support_label: string;
  family_down_payment_support_mode: "provident" | "savings";
  family_savings_support_amount: number;
  family_provident_initial_balance: number;
  family_provident_monthly_salary: number;
  family_provident_total_rate: number;
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
  investment_taxable_return_ratio: number;
  investment_return_tax_rate: number;
  required_liquidity_months: number;
  borrower_age: number;
  borrower_member_index: number;
  career_shock: CareerShockData;
  career_shock_applied?: boolean;
  car_plan: CarPlanData;
  property_goals: PropertyPurchaseGoalData[];
  phased_loans: PhasedLoanData[];
  scheduled_expenses: ScheduledExpenseData[];
  household_expense_stages: HouseholdExpenseStageData[];
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
  enabled: boolean;
  purchase_sequence: number;
  purchase_planning_mode: "after_previous_purchase" | "parallel";
  after_previous_purchase_delay_months: number;
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
  manual_purchase_delay_months: number;
  micro_commercial_loan_ratio: number;
  commercial_rate: number;
  provident_rate: number;
  loan_years: number;
  repayment_method: RepaymentMethod;
  commercial_repayment_method: RepaymentMethod;
  provident_repayment_method: RepaymentMethod;
  commercial_prepayment_mode: CommercialPrepaymentMode;
  commercial_prepayment_enabled: boolean;
  commercial_prepayment_start_month: number;
  commercial_prepayment_allowed_after_month: number;
  commercial_prepayment_monthly_amount: number;
  provident_account_repayment_strategy: ProvidentAccountRepaymentStrategy;
  deed_tax_rate: number;
  broker_fee_rate: number;
  renovation_cost: number;
  renovation_funding_mode: RenovationFundingMode;
  moving_and_misc_cost: number;
  annual_investment_return: number;
  investment_withdrawal_mode: "auto" | "full_liquidation" | "manual_reserve";
  investment_min_balance_after_purchase: number;
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
  contract_monthly_payment: number;
  first_phase_interest_subsidy: number;
  total_interest_subsidy: number;
  borrower_total_interest: number;
  current_monthly_payment: number;
  prepayment_allowed: boolean;
  prepayment_enabled: boolean;
  prepayment_start_month: number;
  prepayment_allowed_after_month: number;
  prepayment_monthly_amount: number;
  prepayment_strategy_type: string;
  prepayment_lump_sum_month: number;
  prepayment_lump_sum_amount: number;
  prepayment_total_extra_principal: number;
  prepayment_net_benefit: number;
  prepayment_explanation: string;
  actual_payoff_months: number;
  interest_saved_by_prepayment: number;
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
  vehicle_index: number;
  vehicle_name: string;
  vehicle_candidate_index: number | null;
  vehicle_candidate_name: string;
  financing_option_id: string;
  financing_option_name: string;
  financing_type: string;
  strategy_key: string;
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
  contract_monthly_payment: number;
  first_phase_interest_subsidy: number;
  total_interest_subsidy: number;
  borrower_total_interest: number;
  expected_monthly_payment_after_purchase: number;
  prepayment_allowed: boolean;
  prepayment_enabled: boolean;
  prepayment_start_month: number;
  prepayment_allowed_after_month: number;
  prepayment_monthly_amount: number;
  prepayment_strategy_type: string;
  prepayment_lump_sum_month: number;
  prepayment_lump_sum_amount: number;
  prepayment_total_extra_principal: number;
  prepayment_net_benefit: number;
  prepayment_explanation: string;
  actual_payoff_months: number;
  interest_saved_by_prepayment: number;
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

export interface PhasedLoanSummary {
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
  current_extra_principal_payment: number;
  prepayment_mode: "none" | "manual" | "auto";
  prepayment_start_month: number;
  prepayment_allowed_after_month: number;
  prepayment_monthly_amount: number;
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

export interface TaxYearSummary {
  year: number;
  summaries: TaxMemberSummary[];
  gross_annual_income: number;
  taxable_income: number;
  salary_tax: number;
  bonus_tax: number;
  total_tax: number;
  net_annual_income: number;
}

export interface TaxMemberMonthlyPoint {
  month: number;
  year: number;
  month_of_year: number;
  member_index: number;
  member_name: string;
  stage_name: string;
  stage_kind: string;
  gross_salary: number;
  bonus_income: number;
  other_taxable_income: number;
  non_taxable_income: number;
  personal_social: number;
  personal_housing_fund: number;
  employer_social: number;
  employer_housing_fund: number;
  special_additional_deduction: number;
  elderly_care_deduction: number;
  other_deduction: number;
  cumulative_taxable_income: number;
  salary_tax: number;
  bonus_tax: number;
  total_income_tax: number;
  net_income: number;
  selected_bonus_method: BonusTaxMethod;
}

export interface TaxMonthlyPoint {
  month: number;
  year: number;
  month_of_year: number;
  gross_income: number;
  net_income: number;
  income_tax: number;
  salary_tax: number;
  bonus_tax: number;
  personal_social: number;
  personal_housing_fund: number;
  employer_social: number;
  employer_housing_fund: number;
  monthly_pf_deposit: number;
  non_taxable_income: number;
  extra_cash_expense: number;
  member_points: TaxMemberMonthlyPoint[];
}

export interface TaxEventPoint {
  month: number;
  year: number;
  month_of_year: number;
  member_name: string;
  event_type: "income_stage_start" | "income_stage_end" | "bonus_payout" | "tax_payment" | "deduction_start" | "non_taxable_income";
  title: string;
  detail: string;
  amount: number | null;
  source: string;
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
  family_provident_upfront_extractable?: number;
  family_down_payment_support_amount?: number;
  family_down_payment_support_mode?: "none" | "provident" | "savings";
  family_down_payment_support_label?: string;
  provident_post_transaction_extractable: number;
  required_cash_after_pf_extract: number;
  upfront_cash_required: number;
  commercial_loan_amount: number;
  provident_loan_amount: number;
  provident_policy_bonus: number;
  provident_policy_cap: number;
  commercial_rate: number;
  provident_rate: number;
  deed_tax_rate: number;
  broker_fee_rate: number;
  deed_tax_amount: number;
  broker_fee_amount: number;
  commercial_loan_years: number;
  provident_loan_years: number;
  provident_loan_year_limit_reasons: string[];
  commercial_repayment_method: RepaymentMethod;
  provident_repayment_method: RepaymentMethod;
  commercial_monthly_payment: number;
  provident_monthly_payment: number;
  commercial_prepayment_mode: CommercialPrepaymentMode;
  commercial_prepayment_enabled: boolean;
  commercial_prepayment_start_month: number;
  commercial_prepayment_allowed_after_month: number;
  commercial_prepayment_monthly_amount: number;
  commercial_actual_payoff_months: number;
  commercial_interest_saved_by_prepayment: number;
  total_monthly_payment: number;
  total_interest: number;
  provident_contract_months: number;
  provident_interest_saving_if_equal_principal: number;
  provident_equal_principal_first_payment: number;
  provident_equal_installment_payment: number;
  provident_repayment_advice: string;
  renovation_cost: number;
  renovation_funding_mode: RenovationFundingMode;
  renovation_included_in_upfront_cash: boolean;
  months_to_renovation: number | null;
  years_to_renovation: number | null;
  post_purchase_renovation_monthly_saving: number;
  investment_withdrawal_mode?: "auto" | "full_liquidation" | "manual_reserve";
  investment_withdrawal_mode_label?: string;
  cash_account_before_purchase?: number;
  investment_balance_before_purchase?: number;
  investment_sell_gross_at_purchase?: number;
  investment_sell_proceeds_at_purchase?: number;
  investment_balance_after_purchase?: number;
  cash_after_transaction: number;
  cash_after_purchase: number;
  provident_balance_after_extract: number;
  required_liquidity_reserve: number;
  liquidity_ok: boolean;
  minimum_cash_balance?: number;
  minimum_cash_balance_month?: number | null;
  cash_stress_ok?: boolean;
  cash_stress_shortfall?: number;
  post_purchase_cash_flow: number;
  post_purchase_pf_strategy: string;
  post_purchase_pf_strategy_label: string;
  monthly_post_purchase_pf_withdrawal: number;
  post_purchase_cash_flow_with_pf_withdrawal: number;
  debt_to_income_ratio: number;
  happiness_score: number;
  recommendation_score: number;
  recommendation_reasons: string[];
  is_recommended: boolean;
  provident_extraction_notes: string[];
  happiness_breakdown: Array<{
    key: string;
    name: string;
    category: "life" | "finance" | "timing" | "resilience";
    score: number;
    weight: number;
    weighted_score: number;
    note: string;
  }>;
}

export interface YieldSensitivityPoint {
  annual_return: number;
  months_to_buy: number | null;
  years_to_buy: number | null;
  cash_after_purchase: number;
}

export interface LoanVisualizationPoint {
  plan_variant: string;
  month: number;
  commercial_loan_balance: number;
  provident_loan_balance: number;
  home_loan_balance: number;
  vehicle_loan_balance: number;
  existing_loan_balance: number;
  total_loan_balance: number;
  commercial_monthly_payment: number;
  provident_monthly_payment: number;
  home_monthly_payment: number;
  vehicle_monthly_payment: number;
  commercial_extra_principal_payment: number;
  vehicle_extra_principal_payment: number;
  existing_monthly_payment: number;
  existing_loan_details: ExistingLoanVisualizationDetail[];
  total_monthly_payment: number;
  cash_monthly_payment: number;
  provident_offset_payment: number;
  provident_monthly_withdrawal_payment: number;
  provident_principal_offset_payment: number;
  provident_monthly_payment_relief: number;
}

export interface ProvidentMemberAccountPoint {
  member_index: number;
  member_name: string;
  balance_start: number;
  personal_deposit: number;
  employer_deposit: number;
  total_deposit: number;
  interest: number;
  rent_withdrawal: number;
  upfront_withdrawal: number;
  post_transaction_withdrawal: number;
  agreed_withdrawal: number;
  monthly_repayment_withdrawal: number;
  loan_offset_payment: number;
  retirement_withdrawal: number;
  account_closed_by_retirement: boolean;
  total_inflow: number;
  total_outflow: number;
  balance_end: number;
}

export interface ProvidentVisualizationPoint {
  plan_variant: string;
  month: number;
  balance_start: number;
  personal_deposit: number;
  employer_deposit: number;
  total_deposit: number;
  interest: number;
  rent_withdrawal: number;
  upfront_withdrawal: number;
  post_transaction_withdrawal: number;
  agreed_withdrawal: number;
  monthly_repayment_withdrawal: number;
  loan_offset_payment: number;
  retirement_withdrawal: number;
  total_inflow: number;
  total_outflow: number;
  balance_end: number;
  strategy_label: string;
  member_accounts: ProvidentMemberAccountPoint[];
}

export interface MonthlyLedgerEntry {
  plan_variant: string;
  month: number;
  account: string;
  category: string;
  label: string;
  amount: number;
  direction: "inflow" | "outflow" | "transfer" | "valuation";
  source: string;
}

export interface AccountSnapshotPoint {
  plan_variant: string;
  month: number;
  cash_balance: number;
  investment_balance: number;
  liquid_asset_value: number;
  provident_balance: number;
  property_asset_value: number;
  vehicle_asset_value: number;
  first_vehicle_asset_value: number;
  second_vehicle_asset_value: number;
  fixed_asset_value: number;
  total_asset_value: number;
  total_loan_balance: number;
  net_worth: number;
}

export interface MonthlyCashflowPoint {
  plan_variant: string;
  month: number;
  cash_balance: number;
  investment_balance: number;
  liquid_asset_value: number;
  provident_balance: number;
  fixed_asset_value: number;
  total_asset_value: number;
  total_loan_balance: number;
  net_worth: number;
  monthly_cash_delta: number;
  cash_income: number;
  living_expense: number;
  scheduled_expense: number;
  debt_payment: number;
  regular_debt_payment: number;
  phased_loan_payment: number;
  house_payment: number;
  house_contract_payment: number;
  provident_house_offset_payment: number;
  provident_house_payment_relief: number;
  vehicle_payment: number;
  first_vehicle_payment: number;
  second_vehicle_payment: number;
  vehicle_operating_cost: number;
  first_vehicle_energy_cost: number;
  first_vehicle_insurance_cost: number;
  first_vehicle_maintenance_cost: number;
  first_vehicle_parking_cost: number;
  second_vehicle_energy_cost: number;
  second_vehicle_insurance_cost: number;
  second_vehicle_maintenance_cost: number;
  second_vehicle_parking_cost: number;
  no_car_commute_cost: number;
  first_vehicle_down_payment: number;
  second_vehicle_down_payment: number;
  vehicle_down_payment: number;
  investment_contribution: number;
  investment_contribution_base: number;
  investment_contribution_cash_sweep: number;
  investment_return: number;
  investment_tax: number;
  investment_fee: number;
  investment_buy_fee: number;
  investment_sell_fee: number;
  investment_sell_proceeds: number;
  provident_deposit: number;
  provident_withdrawal: number;
  transaction_cash_out: number;
  transaction_cash_in: number;
  property_asset_value: number;
  vehicle_asset_value: number;
  first_vehicle_asset_value: number;
  second_vehicle_asset_value: number;
  phase: string;
  ledger_entries: MonthlyLedgerEntry[];
}

export interface AccountConceptSummary {
  code: string;
  name: string;
  category: "account" | "cash" | "investment" | "provident" | "fixed_asset" | "loan" | "policy";
  description: string;
  managed_by: "backend" | "user_input" | "policy";
}

export interface StrategyExplanationPoint {
  plan_variant: string;
  section: string;
  title: string;
  body: string;
  priority: number;
}

export interface PlanEventPoint {
  plan_variant: string;
  month: number;
  category:
    | "account"
    | "income"
    | "investment"
    | "home_purchase"
    | "loan"
    | "provident"
    | "vehicle"
    | "renovation"
    | "risk";
  title: string;
  detail: string;
  amount: number | null;
  severity: "info" | "success" | "warning" | "danger";
  source: string;
}

export interface AnnualFinancialSummary {
  plan_variant: string;
  year: number;
  months: number;
  cash_income: number;
  living_expense: number;
  scheduled_expense: number;
  debt_payment: number;
  house_payment: number;
  vehicle_payment: number;
  vehicle_operating_cost: number;
  investment_contribution: number;
  investment_return: number;
  investment_tax: number;
  investment_fee: number;
  investment_sell_proceeds: number;
  provident_deposit: number;
  provident_withdrawal: number;
  transaction_cash_out: number;
  transaction_cash_in: number;
  monthly_cash_delta: number;
  cash_balance_end: number;
  investment_balance_end: number;
  liquid_asset_value_end: number;
  provident_balance_end: number;
  fixed_asset_value_end: number;
  property_asset_value_end: number;
  vehicle_asset_value_end: number;
  first_vehicle_asset_value_end: number;
  second_vehicle_asset_value_end: number;
  total_asset_value_end: number;
  total_loan_balance_end: number;
  net_worth_end: number;
  commercial_payment: number;
  provident_payment: number;
  vehicle_loan_payment: number;
  existing_loan_payment: number;
  commercial_extra_principal_payment: number;
  vehicle_extra_principal_payment: number;
  provident_offset_payment: number;
  provident_monthly_withdrawal_payment: number;
  provident_principal_offset_payment: number;
  cash_monthly_payment: number;
  commercial_loan_balance_end: number;
  provident_loan_balance_end: number;
  vehicle_loan_balance_end: number;
  existing_loan_balance_end: number;
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
  phased_loan_monthly_payment: number;
  effective_monthly_debt_payment: number;
  phased_loan_summaries: PhasedLoanSummary[];
  car_loan: CarLoanSummary;
  car_plan_analyses: CarPlanAnalysis[];
  monthly_payment: number;
  post_purchase_cash_flow: number;
  debt_to_income_ratio: number;
  emergency_months: number;
  commercial_loan: LoanSummary | null;
  provident_loan: LoanSummary | null;
  tax_summaries: TaxMemberSummary[];
  tax_year_summaries: TaxYearSummary[];
  tax_monthly_points: TaxMonthlyPoint[];
  tax_events: TaxEventPoint[];
  career_shock_projection: CareerShockProjection | null;
  investment_plan_recommendations: InvestmentPlanRecommendation[];
  current_investment_allocation: InvestmentAllocationSummary | null;
  annual_financial_summaries: AnnualFinancialSummary[];
  purchase_plan_analyses: PurchasePlanAnalysis[];
  yield_sensitivity: YieldSensitivityPoint[];
  monthly_cashflow_visualization: MonthlyCashflowPoint[];
  account_snapshots: AccountSnapshotPoint[];
  monthly_ledger: MonthlyLedgerEntry[];
  loan_visualization: LoanVisualizationPoint[];
  provident_visualization: ProvidentVisualizationPoint[];
  account_concepts: AccountConceptSummary[];
  strategy_explanations: StrategyExplanationPoint[];
  plan_events: PlanEventPoint[];
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
