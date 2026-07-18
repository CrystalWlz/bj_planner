export type RepaymentMethod = "equal_installment" | "equal_principal";
export type RuleStatus = "draft" | "active" | "archived";
export type BonusTaxMethod = "separate" | "merged" | "best";
export type AnnualBonusPayoutMode = "lump_sum" | "monthly_spread";
export type IncomeStageKind = "salary" | "unemployment" | "freelance" | "pension" | "manual";
export type FreelanceTaxMode = "labor_remuneration" | "business_income" | "other";
export type GreenBuildingLevel = "none" | "two_star" | "three_star";
export type PrefabBuildingLevel = "none" | "A" | "AA" | "AAA";
export type BuildingStructure = "unknown" | "brick_mixed" | "steel_concrete";
export type RenovationFundingMode =
  | "cash_or_investment"
  | "cash_only"
  | "after_goal_saving"
  | "after_purchase_saving"
  | "upfront_cash";
export type CommercialPrepaymentMode = "auto" | "manual" | "none";
export type ProvidentAccountRepaymentStrategy =
  | "auto"
  | "monthly_repayment_withdrawal"
  | "semiannual_principal_offset"
  | "keep_in_account";
export type ProvidentAccountRepaymentSwitchTarget =
  | "monthly_repayment_withdrawal"
  | "semiannual_principal_offset";
export type PersonalPensionContributionMode = "none" | "auto_tax_optimal" | "fixed_monthly" | "fixed_annual";
export type PersonalPensionOpenMode = "auto_tax_optimal" | "manual" | "none";
export type PersonalPensionReturnMode = "auto_lifecycle" | "manual";
export type PersonalPensionWithdrawalMode = "auto_safe" | "monthly_annuity" | "fixed_monthly" | "lump_sum";
export type PersonalPensionTaxDeductionMode = "monthly_withholding" | "annual_settlement";
export type PersonalPensionEarlyWithdrawalReason = "none" | "total_disability" | "settled_abroad" | "major_medical_expense" | "long_unemployment" | "minimum_living_allowance";
export type PersonalPensionProductLiquidityMode = "daily_liquid" | "periodic" | "locked_until_maturity";

export interface IncomeMember {
  name: string;
  sex: "female" | "male" | "unspecified";
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
  provident_account_enabled: boolean;
  provident_account_open_month: string;
  pension_account_balance: number;
  pension_account_enabled: boolean;
  pension_account_open_month: string;
  medical_account_balance: number;
  medical_account_enabled: boolean;
  medical_account_open_month: string;
  personal_pension_account_enabled: boolean;
  personal_pension_participation_eligible: boolean;
  personal_pension_account_balance: number;
  personal_pension_open_mode: PersonalPensionOpenMode;
  personal_pension_account_open_month: string;
  personal_pension_contribution_mode: PersonalPensionContributionMode;
  personal_pension_tax_deduction_mode: PersonalPensionTaxDeductionMode;
  personal_pension_monthly_contribution: number;
  personal_pension_annual_contribution_target: number;
  personal_pension_auto_annual_contribution_schedule?: Record<string, number>;
  personal_pension_contribution_month: number;
  personal_pension_contribution_start_month: string;
  personal_pension_contribution_end_month: string | null;
  personal_pension_auto_suspend_for_cash_safety: boolean;
  personal_pension_cash_reserve_months: number;
  personal_pension_return_mode: PersonalPensionReturnMode;
  personal_pension_annual_return: number;
  personal_pension_post_retirement_annual_return: number;
  personal_pension_withdrawal_mode: PersonalPensionWithdrawalMode;
  personal_pension_withdrawal_start_month: string;
  personal_pension_early_withdrawal_reason: PersonalPensionEarlyWithdrawalReason;
  personal_pension_early_withdrawal_month: string;
  personal_pension_withdrawal_years: number;
  personal_pension_fixed_monthly_withdrawal: number;
  personal_pension_product_liquidity_mode: PersonalPensionProductLiquidityMode;
  personal_pension_redemption_delay_months: number;
  personal_pension_monthly_redeemable_ratio: number;
  personal_pension_redemption_fee_rate: number;
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
  annual_bonus_months: number;
  annual_bonus_payout_mode: AnnualBonusPayoutMode;
  annual_bonus_payout_month: number;
  annual_bonus_earning_start_month: number | null;
  annual_bonus_earning_end_month: number | null;
  monthly_freelance_income: number;
  freelance_tax_mode: FreelanceTaxMode;
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
  self_payment_monthly: number;
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
  self_payment_monthly: number;
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
  after_tax_annual_return?: number;
  risk_adjusted_annual_return?: number;
  cash_reserve_months: number;
  liquidity_horizon_months?: number | null;
  goal_liquidity_target?: number;
  goal_liquidity_gap?: number;
  monthly_goal_saving?: number;
  equity_ratio: number;
  bond_ratio: number;
  cash_ratio: number;
  lifecycle_cash_shortfall?: number;
  lifecycle_insolvency_month?: number | null;
  lifecycle_liquid_assets_exhausted_month?: number | null;
  lifecycle_required_monthly_relief?: number;
  lifecycle_feasible?: boolean;
  lifecycle_risk_note?: string;
  score: number;
  reasons: string[];
}

export type InvestmentInstrumentMarket = "mainland_etf" | "hong_kong_connect" | "qdii_etf" | "qdii_fund";
export type InvestmentTradingMode = "exchange" | "fund_subscription";
export type InvestmentAssetClass = "equity" | "defensive";
export type InvestmentOrderStatus = "proposed" | "simulated" | "confirmed" | "cancelled" | "blocked";

export interface QuantInvestmentPolicyData {
  schema_version: number;
  name: string;
  enabled: boolean;
  frequency: "monthly";
  equity_cap: number;
  defensive_min: number;
  rebalance_threshold: number;
  rebalance_months: number[];
  drawdown_reduce_threshold: number;
  drawdown_pause_threshold: number;
  drawdown_freeze_threshold: number;
  drawdown_reduced_equity_cap: number;
  qdii_premium_threshold: number;
  qdii_nav_max_stale_days: number;
  default_monthly_budget: number;
  slippage_rate: number;
  max_single_instrument_ratio: number;
  max_single_market_ratio: number;
  max_order_amount: number;
  post_trade_price_deviation_limit: number;
  research_strategy: "disabled" | "min_variance";
  freeze_on_reconciliation_mismatch: boolean;
  notes: string;
}

export interface InvestmentInstrumentData {
  schema_version: number;
  symbol: string;
  name: string;
  market: InvestmentInstrumentMarket;
  trading_mode: InvestmentTradingMode;
  asset_class: InvestmentAssetClass;
  currency: "CNY" | "HKD" | "USD";
  enabled: boolean;
  hong_kong_connect_eligible: boolean;
  purchase_suspended: boolean;
  monthly_purchase_limit: number | null;
  buy_fee_rate: number;
  sell_fee_rate: number;
  lot_size: number;
  qdii_premium_threshold: number | null;
  notes: string;
}

export interface InvestmentMarketBarData {
  date: string;
  price_date: string;
  close: number;
  adjusted_close: number | null;
  nav: number | null;
  nav_date: string;
  nav_available_date: string;
  premium_rate: number | null;
  is_trading: boolean;
  is_suspended: boolean;
  purchase_limited: boolean;
}

export interface InvestmentMarketSnapshotData {
  schema_version: number;
  source: "tushare_pro" | "manual";
  api_name: string;
  fetched_at: string;
  snapshot_date: string;
  status: "complete" | "partial" | "empty";
  trading_calendar: string;
  calendar_source: "provider" | "observed_prices" | "manual";
  trading_days: string[];
  suspension_dates: string[];
  adjustment: "none" | "forward" | "backward" | "provider";
  data_version: string;
  dataset_hash: string;
  expected_bar_count: number | null;
  actual_bar_count: number;
  completeness_ratio: number;
  bars: InvestmentMarketBarData[];
  warning: string;
}

export interface QuantInvestmentProposalData {
  schema_version: number;
  policy_id: string;
  snapshot_ids: string[];
  as_of_date: string;
  protected_cash: number;
  investable_cash: number;
  proposed_budget: number;
  effective_equity_cap: number;
  estimated_drawdown: number;
  risk_state: "normal" | "reduced" | "paused" | "frozen" | "blocked";
  rebalance_triggered: boolean;
  current_equity_ratio: number;
  target_weights: Record<string, number>;
  strategy_versions: Record<string, string>;
  reasons: string[];
}

export interface PaperOrderData {
  schema_version: number;
  client_order_id: string;
  proposal_id: string;
  instrument_id: string;
  side: "buy" | "sell";
  funding_source: "external_contribution" | "paper_cash";
  is_rebalance: boolean;
  order_amount: number;
  estimated_price: number;
  estimated_quantity: number;
  estimated_fee: number;
  cash_contribution_amount: number;
  lot_size: number;
  expected_trade_date: string;
  status: InvestmentOrderStatus;
  reason: string;
  executed_date: string;
  executed_price: number | null;
  executed_quantity: number | null;
}

export interface PaperPositionData {
  instrument_id: string;
  symbol: string;
  name: string;
  market: InvestmentInstrumentMarket;
  asset_class: InvestmentAssetClass;
  currency: "CNY" | "HKD" | "USD";
  quantity: number;
  average_cost: number;
  total_cost: number;
  latest_price: number;
  latest_price_date: string;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_fees: number;
}

export interface PaperPortfolioSummary {
  household_id: string;
  net_contributions: number;
  cash_balance: number;
  market_value: number;
  total_equity: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_fees: number;
  fill_count: number;
  current_drawdown: number;
  max_drawdown: number;
  frozen: boolean;
  reconciliation_status: "not_required" | "matched" | "mismatch";
  positions: PaperPositionData[];
  ledger_entries: MonthlyLedgerEntry[];
  account_snapshots: AccountSnapshotPoint[];
  visualization_details: MonthlyVisualizationDetail[];
  warnings: string[];
}

export interface QuantBacktestResult {
  policy_id: string;
  start_date: string;
  end_date: string;
  months: number;
  strategy_terminal_value: number;
  static_terminal_value: number;
  strategy_max_drawdown: number;
  static_max_drawdown: number;
  strategy_cagr: number;
  static_cagr: number;
  strategy_annualized_volatility: number;
  static_annualized_volatility: number;
  strategy_turnover: number;
  static_turnover: number;
  strategy_total_fees: number;
  static_total_fees: number;
  strategy_min_cash_balance: number;
  static_min_cash_balance: number;
  trade_count: number;
  benchmarks: QuantBenchmarkResult[];
  walk_forward_folds: QuantWalkForwardFold[];
  warnings: string[];
}

export interface QuantBenchmarkResult {
  benchmark_id: string;
  name: string;
  terminal_value: number;
  cagr: number;
  annualized_volatility: number;
  max_drawdown: number;
  total_fees: number;
}

export interface QuantWalkForwardFold {
  fold_index: number;
  train_start_date: string;
  train_end_date: string;
  test_start_date: string;
  test_end_date: string;
  strategy_return: number;
  static_return: number;
  strategy_max_drawdown: number;
  static_max_drawdown: number;
  warnings: string[];
}

export interface QuantBacktestRunData {
  schema_version: number;
  engine_version: string;
  policy_id: string;
  snapshot_ids: string[];
  strategy_versions: Record<string, string>;
  universe_version: string;
  dataset_versions: Record<string, string>;
  data_fingerprint: string;
  monthly_contribution: number;
  start_date: string;
  end_date: string;
  cost_assumptions: Record<string, number>;
  parameters: Record<string, unknown>;
  policy_snapshot: QuantInvestmentPolicyData;
  result: QuantBacktestResult;
  warnings: string[];
}

export interface QuantBacktestRunRecord extends RecordEnvelope<QuantBacktestRunData> {
  household_id: string;
  policy_id: string;
  data_fingerprint: string;
}

export interface QuantInvestmentPolicyRecord extends RecordEnvelope<QuantInvestmentPolicyData> {
  household_id: string;
}

export interface InvestmentInstrumentRecord extends RecordEnvelope<InvestmentInstrumentData> {
  household_id: string;
}

export interface InvestmentMarketSnapshotRecord extends RecordEnvelope<InvestmentMarketSnapshotData> {
  instrument_id: string;
  snapshot_date: string;
}

export interface QuantInvestmentProposalRecord extends RecordEnvelope<QuantInvestmentProposalData> {
  household_id: string;
}

export interface PaperOrderRecord extends RecordEnvelope<PaperOrderData> {
  household_id: string;
  proposal_id: string;
  instrument_id: string;
}

export interface PortfolioStrategyRecommendation {
  plan_name: string;
  title: string;
  status: "feasible" | "adjustment_required" | "high_risk";
  description: string;
  actions: string[];
  cash_shortfall: number;
  insolvency_month: number | null;
  liquid_assets_exhausted_month: number | null;
  terminal_net_worth: number;
  required_monthly_relief: number;
  feasible: boolean;
  score: number;
  is_recommended: boolean;
  reasons: string[];
}

export interface VehicleIndicatorApplicantData {
  enabled: boolean;
  name: string;
  relationship: "main" | "spouse" | "child" | "parent" | "parent_in_law" | "other";
  generation: "self_generation" | "child_generation" | "parent_generation";
  eligibility_type:
    | "beijing_household"
    | "beijing_work_residence_permit"
    | "beijing_residence_permit_social_tax"
    | "active_military_or_police"
    | "hongkong_macao_taiwan_foreign"
    | "unknown";
  has_valid_driver_license: boolean;
  has_no_beijing_vehicle: boolean;
  family_application_start_month: string;
  personal_indicator_history_type: "none" | "ordinary_lottery" | "new_energy_queue" | "both";
  ordinary_lottery_steps: number;
  new_energy_queue_start_month: string;
  personal_history_points_override: number | null;
  only_for_indicator_scoring: boolean;
  notes: string;
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
  energy_type: "pure_electric" | "plug_in_hybrid" | "range_extended" | "fuel_cell" | "fuel";
  new_energy_catalog_eligible: boolean;
  beijing_license_indicator_status:
    | "unknown"
    | "already_have"
    | "family_new_energy_pending"
    | "personal_new_energy_pending"
    | "ordinary_indicator_pending"
    | "not_eligible";
  beijing_indicator_expected_delay_months: number;
  license_plate_rental_enabled: boolean;
  license_plate_rental_upfront_fee: number;
  license_plate_rental_term_months: number;
  license_plate_rental_renewal_fee: number;
  license_plate_rental_renewal_term_months: number;
  license_plate_rental_after_term_mode: "switch_to_own_indicator" | "renew_until_own_indicator";
  beijing_family_indicator_score_enabled: boolean;
  beijing_family_indicator_application_start_month: string;
  beijing_family_indicator_applicants: VehicleIndicatorApplicantData[];
  beijing_family_indicator_generations: number;
  beijing_family_indicator_has_spouse: boolean;
  beijing_family_indicator_main_points: number;
  beijing_family_indicator_spouse_points: number;
  beijing_family_indicator_other_applicant_count: number;
  beijing_family_indicator_other_points_total: number;
  beijing_family_indicator_application_years: number;
  beijing_family_indicator_current_cutoff_score: number;
  beijing_family_indicator_cutoff_score_annual_change: number;
  beijing_family_indicator_last_config_year: number;
  beijing_family_indicator_annual_quota: number;
  vehicle_vessel_tax_annual_override: number | null;
  planning_goal_id: string;
  planning_sequence: number;
  purchase_timing_mode: VehiclePurchaseTimingMode;
  depends_on_goal_id: string;
  after_previous_event_delay_months: number;
  manual_purchase_delay_months: number;
  planning_window_start_month: string;
  planning_window_end_month: string;
  total_price: number;
  down_payment_ratio: number;
  down_payment: number;
  purchase_tax: number;
  purchase_tax_relief: number;
  annual_vehicle_vessel_tax: number;
  license_plate_rental_initial_fee: number;
  beijing_family_indicator_score: number;
  beijing_family_indicator_estimated_wait_months: number | null;
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
  depends_on_goal_id: string;
  after_previous_purchase_delay_months: number;
  earliest_purchase_delay_months: number;
  planning_window_start_month: string;
  planning_window_end_month: string;
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
  frequency: "monthly" | "annual_once" | "one_time";
  one_time_timing_mode: "fixed_month" | "flexible_range";
  annual_occurrence_month: number;
  start_month: string;
  end_month: string | null;
  expense_category: "general" | "medical";
  medical_account_payable: boolean;
  tax_deductible_elderly_care: boolean;
  notes: string;
}

export interface DailyExpenseStageData {
  name: string;
  start_month: string;
  end_month: string | null;
  base_living_expense: number;
}

export interface RentExpenseStageData {
  name: string;
  start_month: string;
  end_month: string | null;
  rent_amount: number;
  broker_fee_months: number;
  broker_fee_amount: number | null;
  service_fee_first_year_rate: number;
  service_fee_later_year_rate: number;
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

export interface ChildPlanData {
  planning_goal_id: string;
  name: string;
  enabled: boolean;
  timing_mode: ChildPlanTimingMode;
  expense_strategy_mode: "balanced" | "conservative" | "quality" | "manual";
  planned_birth_month: string;
  planned_birth_start_month: string;
  planned_birth_end_month: string;
  birth_month: string;
  tax_deduction_owner: string;
  education_start_month: string;
  preparation_months_before_birth: number;
  pregnancy_months_before_birth: number;
  monthly_preparation_cost: number;
  monthly_pregnancy_cost: number;
  birth_medical_cost: number;
  postpartum_recovery_cost: number;
  initial_baby_supplies_cost: number;
  monthly_childcare_cost_before_kindergarten: number;
  monthly_kindergarten_cost: number;
  monthly_primary_secondary_cost: number;
  monthly_higher_education_cost: number;
  kindergarten_entry_cost: number;
  primary_school_entry_cost: number;
  higher_education_entry_cost: number;
  notes: string;
}

export interface SpecialDeductionItemData {
  deduction_type:
    | "child_education"
    | "infant_care"
    | "continuing_education"
    | "serious_illness"
    | "housing_rent"
    | "mortgage_interest"
    | "personal_pension";
  name: string;
  enabled: boolean;
  member_name: string;
  spouse_member_name: string;
  child_name: string;
  start_month: string;
  end_month: string | null;
  monthly_amount: number;
  annual_amount: number;
  settlement_mode: "monthly_withholding" | "annual_settlement";
  is_first_home_loan: boolean;
  claimed_months_used: number;
  notes: string;
}

export interface PersonalPensionAnnualOptimizationPoint {
  year: number;
  annual_contribution: number;
  estimated_tax_saving: number;
  pension_net_value_at_withdrawal: number;
  alternative_investment_value_at_withdrawal: number;
  tax_saving_future_value: number;
  net_advantage_at_withdrawal: number;
}

export interface TaxStrategyItem {
  deduction_type: SpecialDeductionItemData["deduction_type"];
  title: string;
  status: "auto_enabled" | "manual_enabled" | "available" | "not_applicable" | "conflict";
  member_name: string;
  monthly_amount: number;
  annual_amount: number;
  estimated_tax_saving: number;
  cash_contribution: number;
  account_return_rate: number;
  post_retirement_return_rate: number;
  withdrawal_tax_rate: number;
  withdrawal_mode: PersonalPensionWithdrawalMode | null;
  withdrawal_start_month: string;
  withdrawal_years: number;
  estimated_retirement_balance: number;
  estimated_monthly_withdrawal: number;
  cumulative_contribution: number;
  cumulative_estimated_tax_saving: number;
  pension_net_value_at_withdrawal: number;
  alternative_investment_value_at_withdrawal: number;
  forgone_investment_earnings: number;
  tax_saving_future_value: number;
  net_advantage_at_withdrawal: number;
  full_cap_annual_tax_saving: number;
  full_cap_net_advantage_at_withdrawal: number;
  personal_pension_annual_plan: PersonalPensionAnnualOptimizationPoint[];
  cash_safety_rule: string;
  contribution_end_reason: string;
  long_term_cash_risk_month: string;
  recommended_action: string;
  start_month: string;
  end_month: string | null;
  reason: string;
  conflicts_with: SpecialDeductionItemData["deduction_type"][];
  source: "backend_auto" | "strategy_auto" | "manual" | "event";
}

export interface TaxStrategyTimelinePoint {
  month: number;
  year: number;
  month_of_year: number;
  category: "deduction_assignment" | "deduction_switch" | "personal_pension" | "bonus_tax" | "investment_tax" | "annual_settlement" | "manual_override";
  title: string;
  action: string;
  member_name: string;
  deduction_type: SpecialDeductionItemData["deduction_type"] | null;
  status: "auto_enabled" | "manual_enabled" | "available" | "not_applicable" | "conflict";
  amount: number;
  estimated_tax_saving: number;
  detail: string;
  source: "backend_auto" | "strategy_auto" | "manual" | "event";
}

export interface InvestmentTaxProfileData {
  deposit_interest_tax_rate: number;
  fund_dividend_tax_rate: number;
  stock_dividend_short_holding_tax_rate: number;
  stock_dividend_long_holding_tax_rate: number;
  bond_interest_tax_rate: number;
  overseas_asset_tax_rate: number;
  deposit_interest_ratio: number;
  fund_dividend_ratio: number;
  stock_dividend_short_ratio: number;
  stock_dividend_long_ratio: number;
  bond_interest_ratio: number;
  overseas_asset_ratio: number;
}

export type AccountCalibrationTarget =
  | "cash"
  | "investment"
  | "provident"
  | "pension"
  | "medical"
  | "property_asset"
  | "vehicle_asset"
  | "fixed_asset"
  | "total_loan";
export type AccountCalibrationScope = "account" | "concept" | "major_event" | "strategy_event";

export interface AccountCalibrationData {
  enabled: boolean;
  month: string;
  calibration_scope: AccountCalibrationScope;
  target: AccountCalibrationTarget;
  amount: number;
  member_name: string;
  reference_name: string;
  source_id: string;
  source_category: string;
  source_title: string;
  note: string;
}

export interface HouseholdData {
  schema_version: number;
  name: string;
  monthly_income: number;
  monthly_expense: number;
  monthly_debt_payment: number;
  cash_account_balance: number;
  investments: number;
  quant_investment_data_version?: number;
  income_projection_year: number;
  monthly_rent_from_housing_fund: number;
  family_provident_support_enabled: boolean;
  family_provident_support_label: string;
  family_down_payment_support_mode: "provident" | "savings";
  family_savings_support_amount: number;
  family_provident_initial_balance: number;
  family_provident_monthly_salary: number;
  family_provident_total_rate: number;
  major_goal_tradeoff_mode: "auto" | "manual";
  major_goal_timing_preference: number;
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
  investment_tax_profile: InvestmentTaxProfileData;
  required_liquidity_months: number;
  borrower_age: number;
  borrower_member_index: number;
  career_shock: CareerShockData;
  career_shock_applied?: boolean;
  car_plan: CarPlanData;
  property_goals: PropertyPurchaseGoalData[];
  phased_loans: PhasedLoanData[];
  scheduled_expenses: ScheduledExpenseData[];
  daily_expense_stages: DailyExpenseStageData[];
  rent_expense_stages: RentExpenseStageData[];
  elderly_dependents: ElderlyDependentData[];
  child_plans: ChildPlanData[];
  special_deductions: SpecialDeductionItemData[];
  account_calibrations: AccountCalibrationData[];
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

export type PlanningGoalType = "home" | "vehicle" | "child" | "renovation" | "other";
export type PlanningTimingMode = "auto_sequence" | "parallel" | "manual_month" | "after_goal" | "not_planned";
export type VehiclePurchaseTimingMode = "auto_sequence" | "parallel" | "manual_month" | "not_planned";
export type ChildPlanTimingMode = "after_first_home" | "manual_month" | "not_planned";
export type CoreObjectType = "account" | "loan" | "asset" | "adjustment";
export type CoreObjectCategory =
  | "cash"
  | "investment"
  | "provident"
  | "pension"
  | "medical"
  | "personal_pension"
  | "property_asset"
  | "vehicle_asset"
  | "child_goal"
  | "planning_goal"
  | "fixed_asset"
  | "mortgage"
  | "car_loan"
  | "education"
  | "consumer"
  | "manual_adjustment"
  | "other";
export type CoreObjectSource = "household" | "member" | "loan" | "goal" | "manual";

export interface CoreObjectData {
  schema_version: number;
  object_type: CoreObjectType;
  category: CoreObjectCategory;
  name: string;
  enabled: boolean;
  member_name: string;
  owner_key: string;
  reference_id: string;
  source: CoreObjectSource;
  current_balance: number;
  monthly_flow: number;
  annual_rate: number;
  start_month: string;
  end_month: string;
  metadata: Record<string, unknown>;
}

export interface CoreObjectRecord {
  id: string;
  household_id: string | null;
  object_type: CoreObjectType;
  category: CoreObjectCategory;
  data: CoreObjectData;
  created_at: string;
  updated_at: string;
}

export interface PlanningGoalData {
  schema_version: number;
  goal_type: PlanningGoalType;
  name: string;
  enabled: boolean;
  priority: number;
  timing_mode: PlanningTimingMode;
  earliest_purchase_month: string;
  earliest_purchase_delay_months: number;
  planning_window_start_month: string;
  planning_window_end_month: string;
  depends_on_goal_id: string;
  delay_after_dependency_months: number;
  allow_parallel: boolean;
  selected_strategy_id: string;
  target_params: Record<string, unknown>;
  financing_preferences: Record<string, unknown>;
  holding_cost_params: Record<string, unknown>;
  metadata: Record<string, unknown>;
  notes: string;
}

export interface PlanningGoalRecord {
  id: string;
  household_id: string | null;
  goal_type: PlanningGoalType;
  data: PlanningGoalData;
  created_at: string;
  updated_at: string;
}

export interface ResolvedPlanningGoal {
  id: string;
  household_id: string | null;
  goal_type: PlanningGoalType;
  name: string;
  planning_group_id: string;
  planning_group_name: string;
  planning_group_size: number;
  planning_group_member_ids: string[];
  target_amount: number;
  funding_mode: string;
  enabled: boolean;
  priority: number;
  sequence_index: number;
  timing_mode: PlanningTimingMode;
  normalized_timing_mode: PlanningTimingMode;
  depends_on_goal_id: string;
  depends_on_goal_name: string;
  delay_after_dependency_months: number;
  allow_parallel: boolean;
  earliest_purchase_month: string;
  earliest_purchase_delay_months: number;
  planning_window_start_month: string;
  planning_window_end_month: string;
  resolved_not_before_month: number;
  resolved_window_start_month: number;
  resolved_window_end_month: number | null;
  dependency_warning: string;
  explanation: string;
}

export interface PlanningSequenceResult {
  base_month: string;
  goals: ResolvedPlanningGoal[];
  warnings: string[];
}

export interface CalculationContextGoalSnapshot {
  id: string;
  goal_type: PlanningGoalType;
  name: string;
  planning_group_id: string;
  planning_group_name: string;
  planning_group_size: number;
  planning_group_member_ids: string[];
  target_amount: number;
  funding_mode: string;
  enabled: boolean;
  priority: number;
  sequence_index: number;
  normalized_timing_mode: PlanningTimingMode;
  depends_on_goal_id: string;
  depends_on_goal_name: string;
  delay_after_dependency_months: number;
  resolved_not_before_month: number;
  resolved_window_start_month: number;
  resolved_window_end_month: number | null;
  explanation: string;
  dependency_warning: string;
}

export interface CalculationContextCoreObjectSnapshot {
  id: string;
  object_type: CoreObjectType;
  category: CoreObjectCategory;
  name: string;
  source: CoreObjectSource | "";
  owner_key: string;
  reference_id: string;
  member_name: string;
  current_balance: number;
  monthly_flow: number;
}

export interface CalculationContextSnapshot {
  base_month: string;
  household_id: string;
  scenario_id: string;
  current_goal_id: string;
  current_goal_name: string;
  current_goal_resolved_not_before_month: number;
  current_goal_normalized_timing_mode: PlanningTimingMode | "";
  planning_goal_ids: string[];
  planning_goals: CalculationContextGoalSnapshot[];
  core_object_ids: string[];
  core_objects: CalculationContextCoreObjectSnapshot[];
  planning_goal_fingerprint: string;
  core_object_fingerprint: string;
  resolved_goal_count: number;
  core_object_count: number;
  warnings: string[];
}

export interface ScenarioData {
  planning_goal_id: string;
  name: string;
  enabled: boolean;
  purchase_sequence: number;
  purchase_planning_mode: "after_previous_purchase" | "parallel";
  depends_on_goal_id: string;
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
  planning_window_start_month: string;
  planning_window_end_month: string;
  micro_commercial_loan_ratio: number;
  commercial_rate: number;
  provident_rate?: number;
  loan_years: number;
  repayment_method: RepaymentMethod;
  loan_repayment_strategy_mode: "auto" | "manual";
  commercial_repayment_method: RepaymentMethod;
  provident_repayment_method: RepaymentMethod;
  commercial_prepayment_mode: CommercialPrepaymentMode;
  commercial_prepayment_enabled: boolean;
  commercial_prepayment_start_month: number;
  commercial_prepayment_allowed_after_month: number;
  commercial_prepayment_monthly_amount: number;
  provident_account_repayment_strategy: ProvidentAccountRepaymentStrategy;
  provident_account_repayment_switch_enabled: boolean;
  provident_account_repayment_switch_after_month: number;
  provident_account_repayment_switch_to_strategy: ProvidentAccountRepaymentSwitchTarget;
  deed_tax_rate?: number;
  broker_fee_rate: number;
  seller_tax_pass_through_enabled: boolean;
  seller_tax_pass_through_rate: number;
  seller_tax_pass_through_amount: number;
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
  valuation_monitoring_enabled: boolean;
  valuation_asset_status: "planned" | "owned";
  valuation_interval_months: number;
  valuation_reference_date: string;
  valuation_reference_value: number;
  valuation_comparable_unit_price: number;
  valuation_district_adjustment_rate: number;
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

export interface MarketSnapshotData {
  schema_version: number;
  region: string;
  snapshot_date: string;
  source_name: string;
  source_url: string;
  source_type: "government" | "research" | "agency" | "brokerage" | "media" | "other";
  commercial_loan_rate: number | null;
  default_broker_fee_rate: number | null;
  seller_tax_pass_through_rate: number | null;
  avg_unit_price: number | null;
  transaction_count: number | null;
  listing_count: number | null;
  resale_price_mom: number | null;
  resale_price_yoy: number | null;
  new_home_price_mom: number | null;
  new_home_price_yoy: number | null;
  long_term_anchor_growth_rate: number;
  housing_data_quality_score: number;
  housing_market_evidence: HousingMarketEvidenceData[];
  notes: string;
}

export interface HousingMarketEvidenceData {
  source_name: string;
  source_url: string;
  source_type: "government" | "research" | "agency" | "brokerage" | "media" | "other";
  published_date: string;
  scope_type: "city" | "district" | "community";
  scope_name: string;
  ring_scope: "all" | "二环内" | "二至三环" | "三至四环" | "四至五环" | "五至六环" | "六环外";
  property_segment: "all" | "resale" | "new_home";
  price_mom: number | null;
  price_yoy: number | null;
  avg_unit_price: number | null;
  sample_size: number | null;
  credibility_score: number;
  notes: string;
}

export interface PropertyValuationProjectionPoint {
  month: number;
  label: string;
  estimated_value: number;
  lower_value: number;
  upper_value: number;
}

export interface PropertyValuationData {
  schema_version: number;
  property_name: string;
  valuation_date: string;
  reference_date: string;
  reference_value: number;
  estimated_market_value: number;
  estimated_unit_price: number;
  lower_value: number;
  upper_value: number;
  net_realisable_value: number;
  confidence_score: number;
  market_signal_rate: number;
  near_term_annual_rate: number;
  long_term_annual_rate: number;
  structural_rate_adjustment: number;
  location_rate_adjustment: number;
  building_age_rate_adjustment: number;
  location_reference_unit_price: number;
  sale_cost_rate: number;
  liquidity_discount_rate: number;
  market_snapshot_date: string;
  market_source_name: string;
  market_source_names: string[];
  market_source_count: number;
  matched_location_name: string;
  matched_ring_area: string;
  next_due_date: string;
  drivers: string[];
  warnings: string[];
  projection: PropertyValuationProjectionPoint[];
}

export interface PropertyValuationRecord {
  id: string;
  household_id: string;
  planning_goal_id: string;
  valuation_date: string;
  market_snapshot_id: string;
  data: PropertyValuationData;
  created_at: string;
  updated_at: string;
}

export interface PropertyValuationRefreshResponse {
  record: PropertyValuationRecord;
  refreshed: boolean;
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
  policy_notes: string[];
}

export interface CarPlanAnalysis {
  variant: string;
  description: string;
  planning_goal_id: string;
  source: string;
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
  purchase_tax: number;
  purchase_tax_relief: number;
  annual_vehicle_vessel_tax: number;
  license_plate_rental_initial_fee: number;
  beijing_family_indicator_score: number;
  beijing_family_indicator_estimated_wait_months: number | null;
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
  required_liquidity_reserve?: number;
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
  lifecycle_cash_shortfall: number;
  lifecycle_insolvency_month: number | null;
  lifecycle_worst_liquid_balance: number;
  lifecycle_terminal_liquid_balance: number;
  lifecycle_feasible: boolean;
  lifecycle_risk_note: string;
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
  feasible: boolean;
  reason: string;
  cash_shortfall: number;
  worst_cash_balance: number;
  insolvency_month: number | null;
  liquid_assets_exhausted_month: number | null;
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
  pension_income: number;
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
  pension_income: number;
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
  planning_goal_id: string;
  source: string;
  months_to_buy: number | null;
  years_to_buy: number | null;
  original_target_price: number;
  projected_purchase_price: number;
  projected_purchase_price_lower: number;
  projected_purchase_price_upper: number;
  projected_price_change: number;
  property_price_forecast_applied: boolean;
  property_price_forecast_confidence: number;
  property_price_forecast_note: string;
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
  commercial_interest_saving_if_equal_principal: number;
  commercial_equal_principal_first_payment: number;
  commercial_equal_installment_payment: number;
  commercial_repayment_advice: string;
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
  investment_reserve_target?: number;
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
  cash_shortfall?: number;
  insolvency_month?: number | null;
  liquid_assets_exhausted_month?: number | null;
  worst_cash_balance?: number;
  terminal_net_worth?: number;
  emergency_reserve_coverage_months?: number;
  pareto_efficient?: boolean;
  feasibility_recommendation?: string;
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

export interface SocialSecurityMemberAccountPoint {
  member_index: number;
  member_name: string;
  pension_balance_start: number;
  pension_contribution: number;
  pension_account_payout: number;
  pension_interest: number;
  pension_balance_end: number;
  medical_balance_start: number;
  medical_contribution: number;
  medical_retiree_transfer: number;
  medical_interest: number;
  medical_healthcare_outflow: number;
  medical_mutual_aid_outflow: number;
  medical_outflow: number;
  medical_balance_end: number;
  retired: boolean;
}

export interface SocialSecurityVisualizationPoint {
  plan_variant: string;
  month: number;
  pension_balance_start: number;
  pension_contribution: number;
  pension_account_payout: number;
  pension_interest: number;
  pension_balance_end: number;
  medical_balance_start: number;
  medical_contribution: number;
  medical_retiree_transfer: number;
  medical_interest: number;
  medical_healthcare_outflow: number;
  medical_mutual_aid_outflow: number;
  medical_outflow: number;
  medical_balance_end: number;
  total_balance_end: number;
  member_accounts: SocialSecurityMemberAccountPoint[];
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
  pension_account_balance: number;
  medical_account_balance: number;
  social_security_account_balance: number;
  personal_pension_balance: number;
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
  pension_account_balance: number;
  medical_account_balance: number;
  social_security_account_balance: number;
  fixed_asset_value: number;
  total_asset_value: number;
  total_loan_balance: number;
  net_worth: number;
  happiness_score: number;
  monthly_cash_delta: number;
  cash_shortfall: number;
  insolvency_month: number | null;
  liquid_assets_exhausted_month: number | null;
  cash_income: number;
  pension_income: number;
  living_expense: number;
  scheduled_expense: number;
  renovation_expense: number;
  child_expense: number;
  career_shock_self_payment: number;
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
  vehicle_plate_rental_payment: number;
  investment_contribution: number;
  investment_contribution_base: number;
  investment_contribution_cash_sweep: number;
  investment_return: number;
  investment_tax: number;
  investment_fee: number;
  investment_buy_fee: number;
  investment_sell_fee: number;
  investment_sell_proceeds: number;
  personal_pension_contribution: number;
  personal_pension_return: number;
  personal_pension_withdrawal: number;
  personal_pension_redemption_fee: number;
  personal_pension_withdrawal_tax: number;
  personal_pension_suspended_contribution: number;
  personal_pension_balance: number;
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

export interface VisualizationBreakdownItem {
  name: string;
  value: number;
  amount: number | null;
  kind: "income" | "expense" | "asset" | "deduction" | "result" | null;
}

export interface MonthlyVisualizationDetail {
  plan_variant: string;
  month: number;
  income_pie: VisualizationBreakdownItem[];
  income_legend: VisualizationBreakdownItem[];
  expense_pie: VisualizationBreakdownItem[];
  loan_payment_pie: VisualizationBreakdownItem[];
  provident_inflow_pie: VisualizationBreakdownItem[];
  provident_outflow_pie: VisualizationBreakdownItem[];
  social_security_inflow_pie: VisualizationBreakdownItem[];
  social_security_outflow_pie: VisualizationBreakdownItem[];
  cash_flow_items: VisualizationBreakdownItem[];
  cash_flow_drivers: VisualizationBreakdownItem[];
  advisor_text: string;
  explanation_items: Array<{ title: string; body: string }>;
}

export interface AnnualVisualizationDetail {
  plan_variant: string;
  year: number;
  cash_inflow_pie: VisualizationBreakdownItem[];
  cash_outflow_pie: VisualizationBreakdownItem[];
  liquid_asset_pie: VisualizationBreakdownItem[];
  fixed_asset_pie: VisualizationBreakdownItem[];
  loan_payment_pie: VisualizationBreakdownItem[];
  loan_balance_pie: VisualizationBreakdownItem[];
  provident_flow_pie: VisualizationBreakdownItem[];
  social_security_inflow_pie: VisualizationBreakdownItem[];
  social_security_outflow_pie: VisualizationBreakdownItem[];
  social_security_balance_pie: VisualizationBreakdownItem[];
}

export interface TaxVisualizationDetail {
  year: number;
  month: number | null;
  monthly_tax_member_pie: VisualizationBreakdownItem[];
  monthly_deduction_pie: VisualizationBreakdownItem[];
  annual_tax_member_pie: VisualizationBreakdownItem[];
  annual_tax_type_pie: VisualizationBreakdownItem[];
}

export interface ChildPlanStrategyPoint {
  planning_goal_id: string;
  source: string;
  child_name: string;
  enabled: boolean;
  timing_mode: ChildPlanTimingMode;
  expense_strategy_mode: "balanced" | "conservative" | "quality" | "manual";
  birth_month_index: number | null;
  birth_month_label: string;
  preparation_start_month_index: number | null;
  pregnancy_start_month_index: number | null;
  education_start_month_index: number | null;
  mother_member_name: string;
  mother_age_at_birth: number | null;
  happiness_score: number;
  warnings: string[];
  monthly_cost_now: number;
  first_year_cash_need: number;
  total_to_age_18: number;
  lifecycle_cash_shortfall: number;
  lifecycle_insolvency_month: number | null;
  lifecycle_feasible: boolean;
  recommended_budget_factor: number;
  recommended_delay_months: number;
  lifecycle_risk_note: string;
  stages: Array<{ name: string; month_index: number | null; month_label: string; amount: number; frequency: string }>;
  explanation: string;
}

export interface AccountConceptSummary {
  code: string;
  name: string;
  category: "account" | "cash" | "investment" | "provident" | "social_security" | "fixed_asset" | "loan" | "policy";
  description: string;
  managed_by: "backend" | "user_input" | "policy";
  core_object_count: number;
  current_balance: number;
  monthly_flow: number;
}

export interface CoreObjectGroupSummary {
  code: string;
  name: string;
  category: "liquid_asset" | "restricted_account" | "fixed_asset" | "loan" | "policy";
  description: string;
  concept_codes: string[];
  core_object_count: number;
  current_balance: number;
  monthly_flow: number;
}

export interface PlanningFoundationSummary {
  planning_goals: PlanningGoalRecord[];
  planning_sequence: PlanningSequenceResult | null;
  core_objects: CoreObjectRecord[];
  account_concepts: AccountConceptSummary[];
  core_object_groups: CoreObjectGroupSummary[];
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
    | "property_market"
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
  calibration_source: string;
}

export interface AnnualFinancialSummary {
  plan_variant: string;
  year: number;
  months: number;
  cash_income: number;
  pension_income: number;
  living_expense: number;
  scheduled_expense: number;
  renovation_expense: number;
  child_expense: number;
  career_shock_self_payment: number;
  debt_payment: number;
  house_payment: number;
  vehicle_payment: number;
  vehicle_operating_cost: number;
  investment_contribution: number;
  investment_return: number;
  investment_tax: number;
  investment_fee: number;
  investment_sell_proceeds: number;
  personal_pension_contribution: number;
  personal_pension_return: number;
  personal_pension_withdrawal: number;
  personal_pension_redemption_fee: number;
  personal_pension_withdrawal_tax: number;
  personal_pension_suspended_contribution: number;
  personal_pension_balance_end: number;
  provident_deposit: number;
  provident_withdrawal: number;
  pension_account_contribution: number;
  pension_account_payout: number;
  pension_account_interest: number;
  pension_account_balance_end: number;
  medical_account_contribution: number;
  medical_account_retiree_transfer: number;
  medical_account_interest: number;
  medical_account_healthcare_outflow: number;
  medical_account_mutual_aid_outflow: number;
  medical_account_outflow: number;
  medical_account_balance_end: number;
  social_security_account_balance_end: number;
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

export interface ExportSheet {
  plan_variant: string;
  title: string;
  headers: string[];
  rows: unknown[][];
}

export interface ExportTextDocument {
  plan_variant: string;
  filename: string;
  lines: string[];
}

export interface CacheLayerHashes {
  input: string;
  strategy: string;
  ledger: string;
  visualization: string;
  engine: string;
}

export interface GeneratedStrategyBatchRequest {
  cache_layers: CacheLayerHashes[];
  strategy_type?: GeneratedStrategyType | null;
  owner_key?: string | null;
  current_only?: boolean;
}

export type GeneratedStrategyType = "purchase" | "vehicle" | "investment" | "child_plan" | "tax" | "career_shock";

export interface GeneratedStrategyRecord<TData = Record<string, unknown>> {
  id: string;
  cache_key: string;
  engine_fingerprint: string;
  input_hash: string;
  strategy_hash: string;
  ledger_hash: string;
  visualization_hash: string;
  strategy_type: GeneratedStrategyType;
  owner_key: string;
  strategy_key: string;
  variant: string;
  data: TData;
  created_at: string;
  updated_at: string;
}

export interface AffordabilityResult {
  cache_layers: CacheLayerHashes;
  calculation_context: CalculationContextSnapshot | null;
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
  immediate_purchase_status: string;
  immediate_purchase_reason: string;
  recommended_plan_status: string;
  recommended_plan_reason: string;
  commercial_loan: LoanSummary | null;
  provident_loan: LoanSummary | null;
  tax_summaries: TaxMemberSummary[];
  tax_year_summaries: TaxYearSummary[];
  tax_monthly_points: TaxMonthlyPoint[];
  tax_events: TaxEventPoint[];
  tax_strategy_items: TaxStrategyItem[];
  tax_strategy_timeline: TaxStrategyTimelinePoint[];
  career_shock_projection: CareerShockProjection | null;
  investment_plan_recommendations: InvestmentPlanRecommendation[];
  portfolio_strategy_recommendations: PortfolioStrategyRecommendation[];
  current_investment_allocation: InvestmentAllocationSummary | null;
  child_plan_strategies: ChildPlanStrategyPoint[];
  annual_financial_summaries: AnnualFinancialSummary[];
  purchase_plan_analyses: PurchasePlanAnalysis[];
  yield_sensitivity: YieldSensitivityPoint[];
  monthly_cashflow_visualization: MonthlyCashflowPoint[];
  monthly_visualization_details: MonthlyVisualizationDetail[];
  annual_visualization_details: AnnualVisualizationDetail[];
  tax_visualization_details: TaxVisualizationDetail[];
  account_snapshots: AccountSnapshotPoint[];
  monthly_ledger: MonthlyLedgerEntry[];
  paper_portfolio: PaperPortfolioSummary | null;
  loan_visualization: LoanVisualizationPoint[];
  provident_visualization: ProvidentVisualizationPoint[];
  social_security_visualization: SocialSecurityVisualizationPoint[];
  account_concepts: AccountConceptSummary[];
  core_object_groups: CoreObjectGroupSummary[];
  strategy_explanations: StrategyExplanationPoint[];
  plan_events: PlanEventPoint[];
  export_sheets: ExportSheet[];
  export_texts: ExportTextDocument[];
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

export interface PersonalPensionReturnEvidenceData {
  source_name: string;
  source_url: string;
  source_type: string;
  product_type: string;
  fetched_at: string;
  observed_annual_return: number | null;
  sample_count: number;
  status: "parsed" | "no_rate" | "fetch_failed";
  note: string;
}

export interface PersonalPensionReturnSnapshotData {
  snapshot_date: string;
  pre_retirement_annual_return: number;
  post_retirement_annual_return: number;
  conservative_annual_return: number;
  optimistic_annual_return: number;
  observed_market_return: number | null;
  source_count: number;
  parsed_source_count: number;
  next_due_date: string;
  evidence: PersonalPensionReturnEvidenceData[];
  drivers: string[];
  warnings: string[];
}

export interface PersonalPensionReturnSnapshotRecord {
  id: string;
  snapshot_date: string;
  data: PersonalPensionReturnSnapshotData;
  created_at: string;
  updated_at: string;
}

export interface PersonalPensionReturnRefreshResponse {
  record: PersonalPensionReturnSnapshotRecord;
  refreshed: boolean;
}
