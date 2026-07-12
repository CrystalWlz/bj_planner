import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import {
  AlertTriangle,
  Banknote,
  CalendarClock,
  Car,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  Copy,
  Database,
  Download,
  Gauge,
  Home,
  Loader2,
  Moon,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Target,
  Trash2,
  TrendingUp,
  WalletCards
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  CHILD_PLANNING_TIMING_OPTIONS,
  childEducationStageLabel,
  childMonthlyCostAt,
  childPlanHasPlanningTiming,
  childPlanIsIncludedInPlanning,
  childPlanningGoalData,
  childPlanningTimingLabel,
  childPlanningTimingPatch,
  GENERIC_PLANNING_GOAL_TIMING_OPTIONS,
  genericPlanningGoalDefaultData,
  genericPlanningGoalDuplicateData,
  HOME_PLANNING_TIMING_OPTIONS,
  homeDemandIsIncludedInPlanning,
  homePlanIsIncludedInPlanning,
  homePlanningTimingPatch,
  homePurchasePlanningModeForSequence,
  PLANNING_GOAL_AUTO_DEPENDENCY_LABEL,
  homePlanningGoalData,
  scenarioFromHomePlanningGoal,
  planningGoalDependencyLabel,
  planningGoalDependencyOptions,
  planningInclusionStatusLabel,
  planningGoalIsNotPlanned,
  planningGoalOrderLabel,
  planningGoalTimingLabel,
  planningGoalTimingSummary,
  planningGoalTypeLabel,
  planningTimingModeFromScenario,
  resolveChildBirthMonth,
  scenarioPlanningTimingSummary,
  useDebouncedPlanningGoalSave,
  VEHICLE_PLANNING_TIMING_OPTIONS,
  vehiclePlanningControlDefaults,
  vehiclePlanningEnabledPatch,
  vehiclePlanningTimingPatch,
  vehiclePlanIsIncludedInPlanning,
  vehiclePrepaymentModeLabel,
  vehiclePlanningTimingSummary,
  vehiclePlanningGoalData
} from "./planningGoals";
import {
  childPlanStrategyForChild,
  generatedCarPlanAnalyses,
  generatedChildPlanStrategies,
  generatedInvestmentRecommendations,
  generatedPurchasePlanAnalyses,
  generatedStrategySearchText,
  generatedTaxStrategyItems,
  generatedTaxStrategyTimeline,
  generatedStrategySummaryByOwner,
  generatedStrategyTypeLabel,
  generatedStrategyTypeSummary,
} from "./generatedStrategies";
import {
  ACCOUNT_CALIBRATION_TARGET_OPTIONS,
  ACCOUNT_CONCEPT_CODES,
  CORE_OBJECT_GROUP_CODES,
  accountConceptBalanceTextWithHouseholdFallback,
  accountConceptMap,
  calibrationDefaultAmountFromConcepts,
  calibrationFallbackAmountFromHousehold,
  coreObjectBalanceText,
  coreObjectCountText,
  coreObjectGroupMap,
  coreObjectOwnerKey,
  coreObjectOwnerSummaryByOwner,
  coreObjectOwnerSummaryText,
  dashboardAccountConcepts
} from "./coreObjects";
import {
  buildMonthlyChartSeries,
  emptyMonthlyChartPoint
} from "./visualizationSeries";
import {
  calculateAffordability,
  createPlanningGoal,
  deletePlanningGoal,
  fetchGeneratedStrategiesByCacheLayers,
  fetchHouseholds,
  fetchPlanningGoals,
  fetchPlanningFoundation,
  fetchPersonalPensionReturnSnapshots,
  fetchSourcePreview,
  loadInitialData,
  peekCompletedAffordabilityResult,
  peekCompletedGeneratedStrategies,
  savePlanningGoal,
  saveHousehold,
  saveRulePack,
  refreshPersonalPensionReturns,
} from "./api";
import { money, numberInput, percent } from "./format";
import { PropertyMonitorPage } from "./PropertyMonitorPage";
import type {
  AccountCalibrationData,
  AccountCalibrationScope,
  AccountCalibrationTarget,
  AccountConceptSummary,
  AffordabilityResult,
  BonusTaxMethod,
  CarPlanAnalysis,
  CarPlanData,
  CareerShockData,
  ChildPlanData,
  ChildPlanStrategyPoint,
  CacheLayerHashes,
  CommercialPrepaymentMode,
  CoreObjectGroupSummary,
  CoreObjectRecord,
  DailyExpenseStageData,
  ElderlyDependentData,
  GeneratedStrategyRecord,
  HouseholdData,
  IncomeMember,
  IncomeStageData,
  InvestmentTaxProfileData,
  InvestmentPlanRecommendation,
  PersonalPensionReturnSnapshotRecord,
  CalculationContextCoreObjectSnapshot,
  CalculationContextGoalSnapshot,
  MarketSnapshotData,
  ProvidentAccountRepaymentStrategy,
  ProvidentAccountRepaymentSwitchTarget,
  ProvidentMemberAccountPoint,
  PurchasePlanAnalysis,
  RecordEnvelope,
  RepaymentMethod,
  RentExpenseStageData,
  PlanningGoalData,
  PlanningGoalRecord,
  PlanningGoalType,
  PlanningSequenceResult,
  PlanningTimingMode,
  RulePackData,
  ScenarioData,
  ScheduledExpenseData,
  SpecialDeductionItemData,
  SourceDocumentRecord,
  PhasedLoanData,
  TaxStrategyItem,
  TaxStrategyTimelinePoint,
  VehicleIndicatorApplicantData,
  VehicleFinancingOptionData,
  VehiclePlanData,
  VisualizationBreakdownItem
} from "./types";

const visualColors = {
  cash: "var(--chart-cash)",
  investment: "var(--chart-investment)",
  provident: "var(--chart-provident)",
  debt: "var(--chart-debt)",
  expense: "var(--chart-expense)",
  deduction: "var(--chart-deduction)",
  property: "var(--chart-property)",
  vehicle: "var(--chart-vehicle)",
  fixedAsset: "var(--chart-fixed-asset)",
  totalAsset: "var(--chart-total-asset)",
  pension: "var(--chart-pension)",
  medical: "var(--chart-medical)",
  baseline: "var(--chart-baseline)",
  safe: "var(--chart-safe)",
  warning: "var(--chart-warning)",
  danger: "var(--chart-danger)"
};

function hashPieName(name: string) {
  const baseHash = Array.from(name).reduce((hash, char) => {
    const next = (hash * 33 + char.charCodeAt(0)) >>> 0;
    return next;
  }, 5381);
  let mixedHash = baseHash ^ (baseHash >>> 16);
  mixedHash = Math.imul(mixedHash, 0x7feb352d) >>> 0;
  mixedHash ^= mixedHash >>> 15;
  mixedHash = Math.imul(mixedHash, 0x846ca68b) >>> 0;
  mixedHash ^= mixedHash >>> 16;
  return mixedHash >>> 0;
}

function stablePieColor(name: string, offset = 0) {
  const hash = hashPieName(offset ? `${name}:${offset}` : name);
  const hue = hash % 360;
  const saturation = 58 + (hash % 18);
  const lightness = 44 + ((hash >>> 8) % 12);
  return `hsl(${hue}deg ${saturation}% ${lightness}%)`;
}

const bonusTaxMethodLabels: Record<BonusTaxMethod, string> = {
  best: "自动择优",
  separate: "单独计税",
  merged: "并入综合所得"
};

const sourceDefaults = [
  "https://gjj.beijing.gov.cn/web/zwgk61/2024zcwj/436433464/436433465/743726695/index.html",
  "https://gjj.beijing.gov.cn/web/zwgk61/2024zcjd/743726745/index.html",
  "https://gjj.beijing.gov.cn/web/zwgk61/2024zcwj/436433464/436433467/743889727/index.html",
  "https://zjw.beijing.gov.cn/bjjs/fwgl/fdcjy/index.shtml"
];

const defaultVehicleFinancingOptions = (): VehicleFinancingOptionData[] => [
  {
    id: "cash_only",
    name: "全款",
    enabled: true,
    financing_type: "cash_only",
    total_months: 1,
    interest_free_months: 0,
    later_annual_rate: 0,
    min_down_payment_ratio: 1,
    max_down_payment_ratio: 1,
    prepayment_allowed: false,
    prepayment_allowed_after_month: 1,
    prepayment_policy_note: "全款购车不形成车贷，也不存在提前还本。",
    notes: "交易当月一次性支付车价，后续只保留保险、保养、停车、电费等持有成本。"
  },
  {
    id: "three_year_two_year_subsidy",
    name: "三年前两年贴息",
    enabled: true,
    financing_type: "dealer_subsidy",
    total_months: 36,
    interest_free_months: 24,
    later_annual_rate: 0.0199,
    min_down_payment_ratio: 0.3,
    max_down_payment_ratio: 1,
    prepayment_allowed: true,
    prepayment_allowed_after_month: 12,
    prepayment_policy_note: "通常需满足合同约定期数后提前还本；贴息期内提前还本可能影响补贴资格。",
    notes: "合同仍按全期等额本息计息，前两年由厂家或经销商补贴部分利息。"
  },
  {
    id: "twenty_down_two_year_subsidy",
    name: "最低20%首付两年贴息",
    enabled: true,
    financing_type: "dealer_subsidy",
    total_months: 60,
    interest_free_months: 24,
    later_annual_rate: 0.0249,
    min_down_payment_ratio: 0.2,
    max_down_payment_ratio: 1,
    prepayment_allowed: true,
    prepayment_allowed_after_month: 12,
    prepayment_policy_note: "最低首付换来更高贷款本金，提前还本需按合同约定期数和违约金条款判断。",
    notes: "适合比较低首付保现金方案；贴息来自厂家或经销商补贴，不改变贷款余额推演。"
  },
  {
    id: "zero_down_five_year_low_rate",
    name: "0首付五年低息",
    enabled: true,
    financing_type: "bank_loan",
    total_months: 60,
    interest_free_months: 0,
    later_annual_rate: 0.029,
    min_down_payment_ratio: 0,
    max_down_payment_ratio: 1,
    prepayment_allowed: true,
    prepayment_allowed_after_month: 12,
    prepayment_policy_note: "低息方案是否允许提前还本、是否收违约金要以具体合同为准。",
    notes: "适合比较极低首付对买房现金池的影响；家庭承担合同全期利息。"
  }
];

const normalizeVehicleFinancingOption = (
  option: Partial<VehicleFinancingOptionData>,
  index: number,
  vehicle: Partial<VehiclePlanData> = {}
): VehicleFinancingOptionData => {
  const financingType = option.financing_type ?? ((option.interest_free_months ?? 0) > 0 ? "dealer_subsidy" : "standard");
  let totalMonths = Math.max(1, Math.min(120, option.total_months ?? vehicle.total_months ?? 60));
  let interestFreeMonths = financingType === "dealer_subsidy"
    ? Math.max(0, Math.min(totalMonths, option.interest_free_months ?? vehicle.interest_free_months ?? 0))
    : 0;
  let minDownPaymentRatio = Math.max(0, Math.min(1, option.min_down_payment_ratio ?? 0.1));
  let maxDownPaymentRatio = Math.max(minDownPaymentRatio, Math.min(1, option.max_down_payment_ratio ?? 1));
  let laterAnnualRate = Math.max(0, Math.min(0.5, option.later_annual_rate ?? vehicle.later_annual_rate ?? 0.0199));

  if (financingType === "cash_only") {
    totalMonths = 1;
    interestFreeMonths = 0;
    laterAnnualRate = 0;
    minDownPaymentRatio = 1;
    maxDownPaymentRatio = 1;
  }
  const prepaymentAllowed = financingType !== "cash_only" && (option.prepayment_allowed ?? true);

  return {
    id: option.id || `financing_${index + 1}`,
    name: option.name || `金融方案 ${index + 1}`,
    enabled: option.enabled ?? true,
    financing_type: financingType,
    total_months: totalMonths,
    interest_free_months: interestFreeMonths,
    later_annual_rate: laterAnnualRate,
    min_down_payment_ratio: minDownPaymentRatio,
    max_down_payment_ratio: maxDownPaymentRatio,
    prepayment_allowed: prepaymentAllowed,
    prepayment_allowed_after_month: prepaymentAllowed
      ? Math.max(1, Math.min(totalMonths, option.prepayment_allowed_after_month ?? 12))
      : 1,
    prepayment_policy_note: option.prepayment_policy_note ?? (prepaymentAllowed ? "提前还本规则以经销商或银行合同为准。" : "该金融方案不形成或不允许提前还本。"),
    notes: option.notes ?? ""
  };
};

const normalizeVehicleFinancingOptions = (vehicle: Partial<VehiclePlanData>): VehicleFinancingOptionData[] => {
  const options = vehicle.financing_options ?? [];
  if (options.length) {
    return options.map((option, index) => normalizeVehicleFinancingOption(option, index, vehicle));
  }
  return defaultVehicleFinancingOptions().map((option, index) => normalizeVehicleFinancingOption(option, index, vehicle));
};

const defaultVehicleIndicatorApplicant = (index: number, patch: Partial<VehicleIndicatorApplicantData> = {}): VehicleIndicatorApplicantData => ({
  enabled: true,
  name: `指标申请人 ${index + 1}`,
  relationship: index === 0 ? "main" : "other",
  generation: "self_generation",
  eligibility_type: "unknown",
  has_valid_driver_license: index === 0,
  has_no_beijing_vehicle: true,
  family_application_start_month: "",
  personal_indicator_history_type: "none",
  ordinary_lottery_steps: 0,
  new_energy_queue_start_month: "",
  personal_history_points_override: null,
  only_for_indicator_scoring: true,
  notes: "",
  ...patch
});

const normalizeVehicleIndicatorApplicants = (applicants?: Partial<VehicleIndicatorApplicantData>[]): VehicleIndicatorApplicantData[] =>
  (applicants ?? []).map((applicant, index) => defaultVehicleIndicatorApplicant(index, applicant));

function PlanningWindowFields({
  startMonth,
  endMonth,
  onChange,
  startLabel = "计划窗口开始",
  endLabel = "计划窗口最晚",
  hint = "不填则由系统按现金安全、政策限制和目标顺序自动选择；填写后，后端会在这个时间窗口内寻找更合适的具体月份。"
}: {
  startMonth: string;
  endMonth: string;
  onChange: (patch: { planning_window_start_month?: string; planning_window_end_month?: string }) => void;
  startLabel?: string;
  endLabel?: string;
  hint?: string;
}) {
  return (
    <>
      <Field label={startLabel}>
        <input type="month" value={startMonth} onChange={(event) => onChange({ planning_window_start_month: event.target.value })} />
      </Field>
      <Field label={endLabel}>
        <input type="month" value={endMonth} onChange={(event) => onChange({ planning_window_end_month: event.target.value })} />
      </Field>
      <p className="field-hint form-grid-note">{hint}</p>
    </>
  );
}

const defaultCarPlan: CarPlanData = {
  enabled: false,
  name: "车辆计划",
  selected_strategy_variant: "手动设置",
  candidate_vehicles: [],
  financing_options: defaultVehicleFinancingOptions(),
  selected_financing_option_id: "",
  selected_financing_option_name: "",
  selected_financing_type: "",
  selected_financing_min_down_payment_ratio: 0,
  selected_financing_max_down_payment_ratio: 1,
  selected_financing_prepayment_allowed: true,
  selected_financing_prepayment_policy_note: "",
  energy_type: "pure_electric",
  new_energy_catalog_eligible: true,
  beijing_license_indicator_status: "unknown",
  beijing_indicator_expected_delay_months: 0,
  license_plate_rental_enabled: false,
  license_plate_rental_upfront_fee: 20000,
  license_plate_rental_term_months: 36,
  license_plate_rental_renewal_fee: 20000,
  license_plate_rental_renewal_term_months: 36,
  license_plate_rental_after_term_mode: "renew_until_own_indicator",
  beijing_family_indicator_score_enabled: false,
  beijing_family_indicator_application_start_month: "",
  beijing_family_indicator_applicants: [],
  beijing_family_indicator_generations: 1,
  beijing_family_indicator_has_spouse: true,
  beijing_family_indicator_main_points: 2,
  beijing_family_indicator_spouse_points: 1,
  beijing_family_indicator_other_applicant_count: 0,
  beijing_family_indicator_other_points_total: 0,
  beijing_family_indicator_application_years: 0,
  beijing_family_indicator_current_cutoff_score: 36,
  beijing_family_indicator_cutoff_score_annual_change: 0,
  beijing_family_indicator_last_config_year: 2026,
  beijing_family_indicator_annual_quota: 119200,
  vehicle_vessel_tax_annual_override: null,
  purchase_tax: 0,
  purchase_tax_relief: 0,
  annual_vehicle_vessel_tax: 0,
  license_plate_rental_initial_fee: 0,
  beijing_family_indicator_score: 0,
  beijing_family_indicator_estimated_wait_months: null,
  vehicle_plans: [],
  ...vehiclePlanningControlDefaults(0),
  total_price: 0,
  down_payment_ratio: 0.5,
  down_payment: 0,
  purchase_delay_months: 0,
  total_months: 60,
  interest_free_months: 24,
  later_annual_rate: 0.0199,
  loan_prepayment_enabled: false,
  loan_prepayment_start_month: 1,
  loan_prepayment_allowed_after_month: 12,
  loan_prepayment_monthly_amount: 0,
  loan_prepayment_strategy_type: "none",
  loan_prepayment_lump_sum_month: 0,
  loan_prepayment_lump_sum_amount: 0,
  current_month_index: 1,
  saving_start_date: "2026-07-01",
  monthly_operating_cost: 0,
  no_car_monthly_commute_cost: 0,
  annual_mileage_km: 0,
  electricity_kwh_per_100km: 14,
  electricity_price_per_kwh: 0.8,
  monthly_parking_cost: 0,
  annual_maintenance_cost: 0,
  annual_maintenance_growth_rate: 0.03,
  annual_insurance_rate: 0.018,
  annual_insurance_min: 0,
  annual_insurance_growth_rate: 0.02,
  depreciation_years: 8,
  vehicle_service_years: 10,
  vehicle_retirement_mileage_km: 600000,
  happiness_score: 6.5,
  notes: ""
};

const carStrategyKeys = new Set(["target", "cash", "high_down_low_loan", "low_down_keep_cash", "accelerated_principal", "delay_purchase"]);

function normalizeCarStrategySelection(value?: string) {
  const selected = (value || "").trim();
  if (!selected || selected === "手动设置" || selected === "手动策略") return "target";
  if (selected.includes("|")) return selected;
  return carStrategyKeys.has(selected) ? selected : "target";
}

function carStrategyKeyFromSelection(value?: string) {
  const normalized = normalizeCarStrategySelection(value);
  return normalized.includes("|") ? normalized.split("|").pop()?.trim() || normalized : normalized;
}

const defaultCareerShock = {
  enabled: false,
  member_settings: [],
  auto_unemployment_benefit: true,
  auto_self_social_insurance: true,
  auto_flexible_housing_fund: true,
  unemployment_benefit_months: 24,
  unemployment_benefit_monthly: 0,
  self_social_insurance_monthly: 0,
  self_housing_fund_monthly: 0
};

const defaultScheduledExpenses: ScheduledExpenseData[] = [
  {
    name: "计划支出",
    monthly_amount: 0,
    frequency: "monthly",
    one_time_timing_mode: "fixed_month",
    annual_occurrence_month: 1,
    start_month: "2026-07",
    end_month: null,
    expense_category: "general",
    medical_account_payable: false,
    tax_deductible_elderly_care: false,
    notes: ""
  }
];

const defaultAnnualScheduledExpense: ScheduledExpenseData = {
  name: "数码产品支出",
  monthly_amount: 10000,
  frequency: "annual_once",
  one_time_timing_mode: "fixed_month",
  annual_occurrence_month: 6,
  start_month: "2026-06",
  end_month: null,
  expense_category: "general",
  medical_account_payable: false,
  tax_deductible_elderly_care: false,
  notes: "一年一次的大额家庭消费支出，只在指定月份进入现金流。"
};

const defaultOneTimeScheduledExpense: ScheduledExpenseData = {
  name: "一次性大额支出",
  monthly_amount: 10000,
  frequency: "one_time",
  one_time_timing_mode: "flexible_range",
  annual_occurrence_month: 1,
  start_month: "2027-01",
  end_month: "2027-06",
  expense_category: "general",
  medical_account_payable: false,
  tax_deductible_elderly_care: false,
  notes: "给出可接受时间范围后，后端策略会先按不挤占现金池的保守口径安排到范围内较晚月份。"
};

const RING_AREA_OPTIONS = ["未设置", "待定", "二环内", "二至三环", "三至四环", "四至五环", "五至六环", "六环外"] as const;

const defaultDailyExpenseStage: DailyExpenseStageData = {
  name: "日常支出阶段",
  start_month: "2026-07",
  end_month: null,
  base_living_expense: 0
};

const defaultRentExpenseStage: RentExpenseStageData = {
  name: "租房支出阶段",
  start_month: "2026-07",
  end_month: null,
  rent_amount: 0,
  broker_fee_months: 1,
  broker_fee_amount: null,
  service_fee_first_year_rate: 0.09,
  service_fee_later_year_rate: 0.06,
  rent_payment_mode: "cash",
  rent_payment_frequency: "monthly"
};

const defaultInvestmentTaxProfile: InvestmentTaxProfileData = {
  deposit_interest_tax_rate: 0,
  fund_dividend_tax_rate: 0,
  stock_dividend_short_holding_tax_rate: 0.2,
  stock_dividend_long_holding_tax_rate: 0,
  bond_interest_tax_rate: 0,
  overseas_asset_tax_rate: 0,
  deposit_interest_ratio: 0,
  fund_dividend_ratio: 0,
  stock_dividend_short_ratio: 0,
  stock_dividend_long_ratio: 0,
  bond_interest_ratio: 0,
  overseas_asset_ratio: 0
};

const defaultChildPlan: ChildPlanData = {
  planning_goal_id: "",
  name: "子女计划",
  enabled: true,
  timing_mode: "after_first_home",
  expense_strategy_mode: "balanced",
  planned_birth_month: "",
  planned_birth_start_month: "",
  planned_birth_end_month: "",
  birth_month: "",
  tax_deduction_owner: "",
  education_start_month: "",
  preparation_months_before_birth: 6,
  pregnancy_months_before_birth: 9,
  monthly_preparation_cost: 1500,
  monthly_pregnancy_cost: 3000,
  birth_medical_cost: 30000,
  postpartum_recovery_cost: 40000,
  initial_baby_supplies_cost: 20000,
  monthly_childcare_cost_before_kindergarten: 4500,
  monthly_kindergarten_cost: 5000,
  monthly_primary_secondary_cost: 6000,
  monthly_higher_education_cost: 8000,
  kindergarten_entry_cost: 10000,
  primary_school_entry_cost: 15000,
  higher_education_entry_cost: 50000,
  notes: ""
};

const childExpensePresets: Record<ChildPlanData["expense_strategy_mode"], Partial<ChildPlanData>> = {
  conservative: {
    monthly_preparation_cost: 800,
    monthly_pregnancy_cost: 1800,
    birth_medical_cost: 15000,
    postpartum_recovery_cost: 20000,
    initial_baby_supplies_cost: 10000,
    monthly_childcare_cost_before_kindergarten: 2500,
    monthly_kindergarten_cost: 2500,
    monthly_primary_secondary_cost: 3000,
    monthly_higher_education_cost: 5000,
    kindergarten_entry_cost: 5000,
    primary_school_entry_cost: 8000,
    higher_education_entry_cost: 30000,
  },
  balanced: {
    monthly_preparation_cost: 1500,
    monthly_pregnancy_cost: 3000,
    birth_medical_cost: 30000,
    postpartum_recovery_cost: 40000,
    initial_baby_supplies_cost: 20000,
    monthly_childcare_cost_before_kindergarten: 4500,
    monthly_kindergarten_cost: 5000,
    monthly_primary_secondary_cost: 6000,
    monthly_higher_education_cost: 8000,
    kindergarten_entry_cost: 10000,
    primary_school_entry_cost: 15000,
    higher_education_entry_cost: 50000,
  },
  quality: {
    monthly_preparation_cost: 3000,
    monthly_pregnancy_cost: 6000,
    birth_medical_cost: 60000,
    postpartum_recovery_cost: 80000,
    initial_baby_supplies_cost: 40000,
    monthly_childcare_cost_before_kindergarten: 8000,
    monthly_kindergarten_cost: 9000,
    monthly_primary_secondary_cost: 12000,
    monthly_higher_education_cost: 15000,
    kindergarten_entry_cost: 20000,
    primary_school_entry_cost: 30000,
    higher_education_entry_cost: 100000,
  },
  manual: {}
};

function childExpenseStrategySnapshot(child: ChildPlanData): Partial<ChildPlanData> {
  return {
    expense_strategy_mode: child.expense_strategy_mode,
    monthly_preparation_cost: child.monthly_preparation_cost,
    monthly_pregnancy_cost: child.monthly_pregnancy_cost,
    birth_medical_cost: child.birth_medical_cost,
    postpartum_recovery_cost: child.postpartum_recovery_cost,
    initial_baby_supplies_cost: child.initial_baby_supplies_cost,
    monthly_childcare_cost_before_kindergarten: child.monthly_childcare_cost_before_kindergarten,
    monthly_kindergarten_cost: child.monthly_kindergarten_cost,
    monthly_primary_secondary_cost: child.monthly_primary_secondary_cost,
    monthly_higher_education_cost: child.monthly_higher_education_cost,
    kindergarten_entry_cost: child.kindergarten_entry_cost,
    primary_school_entry_cost: child.primary_school_entry_cost,
    higher_education_entry_cost: child.higher_education_entry_cost
  };
}

const defaultSpecialDeduction: SpecialDeductionItemData = {
  deduction_type: "housing_rent",
  name: "住房租金专项附加扣除",
  enabled: false,
  member_name: "",
  spouse_member_name: "",
  child_name: "",
  start_month: "2026-07",
  end_month: null,
  monthly_amount: 1500,
  annual_amount: 0,
  settlement_mode: "monthly_withholding",
  is_first_home_loan: false,
  claimed_months_used: 0,
  notes: ""
};

function defaultRetirementCategoryForMember(index: number): IncomeMember["retirement_category"] {
  return index === 0 ? "male_60" : "female_55";
}

function defaultRetirementCategoryForSex(sex: IncomeMember["sex"], index: number): IncomeMember["retirement_category"] {
  if (sex === "male") return "male_60";
  if (sex === "female") return "female_55";
  return defaultRetirementCategoryForMember(index);
}

function normalizeRetirementCategoryForSex(
  category: IncomeMember["retirement_category"] | undefined,
  sex: IncomeMember["sex"] | undefined,
  index: number
): IncomeMember["retirement_category"] {
  if (sex === "male") return "male_60";
  if (sex === "female") return category === "female_50" ? "female_50" : "female_55";
  return category ?? defaultRetirementCategoryForMember(index);
}

function retirementCategoryOptionsForSex(sex: IncomeMember["sex"] | undefined) {
  if (sex === "male") return [["male_60", retirementCategoryLabels.male_60]] as const;
  if (sex === "female") {
    return [
      ["female_55", retirementCategoryLabels.female_55],
      ["female_50", retirementCategoryLabels.female_50]
    ] as const;
  }
  return Object.entries(retirementCategoryLabels);
}

const retirementCategoryLabels: Record<IncomeMember["retirement_category"], string> = {
  male_60: "男职工（延至63岁）",
  female_55: "女职工原55岁（延至58岁）",
  female_50: "女职工原50岁（延至55岁）"
};

const memberSexLabels: Record<IncomeMember["sex"], string> = {
  unspecified: "未指定",
  female: "女性",
  male: "男性"
};

function normalizeCareerShockForMembers(
  rawShock: Partial<CareerShockData> | Record<string, unknown> | undefined,
  members: IncomeMember[]
): CareerShockData {
  const shock = { ...defaultCareerShock, ...(rawShock ?? {}) } as CareerShockData;
  const existingSettings = Array.isArray(shock.member_settings) ? shock.member_settings : [];
  const existingByName = new Map(existingSettings.map((item) => [item.member_name, item]));
  const member_settings = members.map((member, index) => {
    const memberName = member.name || `成员 ${index + 1}`;
    const existing = existingByName.get(memberName) ?? existingSettings[index];
    return {
      member_name: memberName,
      enabled: existing?.enabled ?? false,
      layoff_age: existing?.layoff_age ?? 35,
      retirement_age: existing?.retirement_age ?? 63,
      freelance_income_monthly: existing?.freelance_income_monthly ?? 0,
      pension_monthly: existing?.pension_monthly ?? 0,
      auto_pension_monthly: existing?.auto_pension_monthly ?? true
    };
  });
  return {
    enabled: member_settings.some((item) => item.enabled),
    member_settings,
    auto_unemployment_benefit: shock.auto_unemployment_benefit ?? true,
    auto_self_social_insurance: shock.auto_self_social_insurance ?? true,
    auto_flexible_housing_fund: shock.auto_flexible_housing_fund ?? true,
    unemployment_benefit_months: shock.unemployment_benefit_months ?? 24,
    unemployment_benefit_monthly: shock.unemployment_benefit_monthly ?? 0,
    self_social_insurance_monthly: shock.self_social_insurance_monthly ?? 0,
    self_housing_fund_monthly: shock.self_housing_fund_monthly ?? 0
  };
}

function normalizeVehiclePlanData(vehicle: VehiclePlanData): VehiclePlanData {
  return {
    ...vehicle,
    financing_options: normalizeVehicleFinancingOptions(vehicle),
    selected_financing_option_id: vehicle.selected_financing_option_id ?? "",
    selected_financing_option_name: vehicle.selected_financing_option_name ?? "",
    selected_financing_type: vehicle.selected_financing_type ?? "",
    selected_financing_min_down_payment_ratio: vehicle.selected_financing_min_down_payment_ratio ?? 0,
    selected_financing_max_down_payment_ratio: vehicle.selected_financing_max_down_payment_ratio ?? 1,
    selected_financing_prepayment_allowed: vehicle.selected_financing_prepayment_allowed ?? true,
    selected_financing_prepayment_policy_note: vehicle.selected_financing_prepayment_policy_note ?? "",
    depends_on_goal_id: vehicle.depends_on_goal_id ?? "",
    planning_window_start_month: vehicle.planning_window_start_month ?? "",
    planning_window_end_month: vehicle.planning_window_end_month ?? "",
    loan_prepayment_enabled: vehicle.loan_prepayment_enabled ?? false,
    loan_prepayment_start_month: vehicle.loan_prepayment_start_month ?? 1,
    loan_prepayment_allowed_after_month: vehicle.loan_prepayment_allowed_after_month ?? 12,
    loan_prepayment_monthly_amount: vehicle.loan_prepayment_monthly_amount ?? 0,
    loan_prepayment_strategy_type: vehicle.loan_prepayment_strategy_type ?? "none",
    loan_prepayment_lump_sum_month: vehicle.loan_prepayment_lump_sum_month ?? 0,
    loan_prepayment_lump_sum_amount: vehicle.loan_prepayment_lump_sum_amount ?? 0,
    selected_strategy_variant: normalizeCarStrategySelection(vehicle.selected_strategy_variant),
    candidate_vehicles: (vehicle.candidate_vehicles ?? []).map((candidate) => ({
      ...normalizeVehiclePlanData(candidate),
      candidate_vehicles: []
    }))
  };
}

function completeHouseholdDefaults(record: RecordEnvelope<HouseholdData>): RecordEnvelope<HouseholdData> {
  const members = record.data.members.map((member, index) => {
    const birthMonth = member.birth_month ?? "";
    const sex = member.sex ?? "unspecified";
    const retirementCategory = normalizeRetirementCategoryForSex(member.retirement_category, sex, index);
    return {
      ...member,
      sex,
      family_join_month: member.family_join_month ?? "2026-07",
      birth_month: birthMonth,
      current_age: ageYearsFromBirthMonth(birthMonth) ?? member.current_age ?? 30,
      retirement_category: retirementCategory,
      social_security_months: member.social_security_months ?? 0,
      income_tax_months: member.income_tax_months ?? 0,
      existing_home_count: member.existing_home_count ?? 0,
      existing_mortgage_count: member.existing_mortgage_count ?? 0,
      initial_cash_balance: member.initial_cash_balance ?? 0,
      initial_investments: member.initial_investments ?? 0,
      initial_other_asset_value: member.initial_other_asset_value ?? 0,
      initial_other_debt_balance: member.initial_other_debt_balance ?? 0,
      provident_fund_balance: member.provident_fund_balance ?? 0,
      provident_account_enabled: member.provident_account_enabled ?? true,
      provident_account_open_month: member.provident_account_open_month ?? member.family_join_month ?? "2026-07",
      pension_account_balance: member.pension_account_balance ?? 0,
      pension_account_enabled: member.pension_account_enabled ?? true,
      pension_account_open_month: member.pension_account_open_month ?? member.family_join_month ?? "2026-07",
      medical_account_balance: member.medical_account_balance ?? 0,
      medical_account_enabled: member.medical_account_enabled ?? true,
      medical_account_open_month: member.medical_account_open_month ?? member.family_join_month ?? "2026-07",
      personal_pension_account_enabled: member.personal_pension_account_enabled ?? false,
      personal_pension_participation_eligible: member.personal_pension_participation_eligible ?? false,
      personal_pension_account_balance: member.personal_pension_account_balance ?? 0,
      personal_pension_open_mode: member.personal_pension_open_mode ?? "none",
      personal_pension_account_open_month: member.personal_pension_account_open_month ?? "",
      personal_pension_contribution_mode: member.personal_pension_contribution_mode ?? "none",
      personal_pension_tax_deduction_mode: member.personal_pension_tax_deduction_mode ?? "monthly_withholding",
      personal_pension_monthly_contribution: member.personal_pension_monthly_contribution ?? 0,
      personal_pension_annual_contribution_target: member.personal_pension_annual_contribution_target ?? 0,
      personal_pension_auto_annual_contribution_schedule: member.personal_pension_auto_annual_contribution_schedule ?? {},
      personal_pension_contribution_month: member.personal_pension_contribution_month ?? 12,
      personal_pension_contribution_start_month: member.personal_pension_contribution_start_month ?? "",
      personal_pension_contribution_end_month: member.personal_pension_contribution_end_month ?? null,
      personal_pension_auto_suspend_for_cash_safety: member.personal_pension_auto_suspend_for_cash_safety ?? true,
      personal_pension_cash_reserve_months: member.personal_pension_cash_reserve_months ?? 6,
      personal_pension_return_mode: member.personal_pension_return_mode ?? "auto_lifecycle",
      personal_pension_annual_return: member.personal_pension_annual_return ?? 0.025,
      personal_pension_post_retirement_annual_return: member.personal_pension_post_retirement_annual_return ?? 0.015,
      personal_pension_withdrawal_mode: member.personal_pension_withdrawal_mode ?? "auto_safe",
      personal_pension_withdrawal_start_month: member.personal_pension_withdrawal_start_month ?? "",
      personal_pension_early_withdrawal_reason: member.personal_pension_early_withdrawal_reason ?? "none",
      personal_pension_early_withdrawal_month: member.personal_pension_early_withdrawal_month ?? "",
      personal_pension_withdrawal_years: member.personal_pension_withdrawal_years ?? 20,
      personal_pension_fixed_monthly_withdrawal: member.personal_pension_fixed_monthly_withdrawal ?? 0,
      personal_pension_product_liquidity_mode: member.personal_pension_product_liquidity_mode ?? "daily_liquid",
      personal_pension_redemption_delay_months: member.personal_pension_redemption_delay_months ?? 0,
      personal_pension_monthly_redeemable_ratio: member.personal_pension_monthly_redeemable_ratio ?? 1,
      personal_pension_redemption_fee_rate: member.personal_pension_redemption_fee_rate ?? 0
    };
  });
  return {
    ...record,
    data: {
      ...record.data,
      members,
      career_shock: normalizeCareerShockForMembers(record.data.career_shock, members),
      car_plan: {
        ...defaultCarPlan,
        ...record.data.car_plan,
        financing_options: normalizeVehicleFinancingOptions(record.data.car_plan),
        candidate_vehicles: (record.data.car_plan.candidate_vehicles ?? []).map((candidate) => normalizeVehiclePlanData(candidate)),
        vehicle_plans: (record.data.car_plan.vehicle_plans ?? []).map((vehicle) => normalizeVehiclePlanData(vehicle)),
        no_car_monthly_commute_cost: record.data.car_plan.no_car_monthly_commute_cost ?? 0
      },
      property_goals: (record.data.property_goals ?? []).map((goal, index) => ({
        ...goal,
        priority: goal.priority ?? index + 1,
        planning_mode: goal.planning_mode ?? "after_previous_purchase",
        depends_on_goal_id: goal.depends_on_goal_id ?? "",
        after_previous_purchase_delay_months: goal.after_previous_purchase_delay_months ?? 0
      })),
      phased_loans: (record.data.phased_loans ?? []).map((loan) => ({
        ...loan,
        prepayment_mode: loan.prepayment_mode ?? "none",
        prepayment_start_month: loan.prepayment_start_month ?? 1,
        prepayment_allowed_after_month: loan.prepayment_allowed_after_month ?? 1,
        prepayment_monthly_amount: loan.prepayment_monthly_amount ?? 0
      })),
      scheduled_expenses: (record.data.scheduled_expenses ?? []).map((expense) => {
        const expenseCategory = expense.expense_category ?? (expense.medical_account_payable ? "medical" : "general");
        return {
          ...expense,
          frequency: expense.frequency ?? "monthly",
          one_time_timing_mode: expense.one_time_timing_mode ?? "fixed_month",
          annual_occurrence_month: expense.annual_occurrence_month ?? Number(expense.start_month?.slice(5, 7) || 1),
          expense_category: expenseCategory,
          medical_account_payable: expenseCategory === "medical" ? expense.medical_account_payable ?? false : false
        };
      }),
      daily_expense_stages: (record.data.daily_expense_stages?.length
        ? record.data.daily_expense_stages
        : [{
            ...defaultDailyExpenseStage,
            base_living_expense: record.data.monthly_expense ?? 0
          }]
      ).map((stage) => ({
        ...stage,
        base_living_expense: stage.base_living_expense ?? 0
      })),
      rent_expense_stages: (record.data.rent_expense_stages?.length
        ? record.data.rent_expense_stages
        : [{
            ...defaultRentExpenseStage,
            rent_amount: record.data.monthly_rent_from_housing_fund ?? 0,
            rent_payment_mode: (record.data.monthly_rent_from_housing_fund ?? 0) > 0 ? "provident" : "cash",
            rent_payment_frequency: "monthly"
          }]
      ).map((stage) => ({
        ...stage,
        broker_fee_months: stage.broker_fee_months ?? 1,
        broker_fee_amount: stage.broker_fee_amount ?? null,
        service_fee_first_year_rate: stage.service_fee_first_year_rate ?? 0.09,
        service_fee_later_year_rate: stage.service_fee_later_year_rate ?? 0.06,
        rent_payment_mode: (stage.rent_payment_mode === "provident" ? "provident" : "cash") as RentExpenseStageData["rent_payment_mode"],
        rent_payment_frequency: (stage.rent_payment_frequency === "quarterly" ? "quarterly" : "monthly") as RentExpenseStageData["rent_payment_frequency"]
      })),
      elderly_dependents: record.data.elderly_dependents ?? [],
      child_plans: (record.data.child_plans ?? []).map((child, index) => ({
        ...defaultChildPlan,
        ...child,
        name: child.name || `子女计划 ${index + 1}`
      })),
      special_deductions: (record.data.special_deductions ?? []).map((item) => ({
        ...defaultSpecialDeduction,
        ...item,
        end_month: item.end_month ?? null
      })),
      account_calibrations: (record.data.account_calibrations ?? []).map((item) => ({
        enabled: item.enabled ?? true,
        month: item.month || "2026-07",
        calibration_scope: item.calibration_scope ?? "account",
        target: item.target ?? "cash",
        amount: item.amount ?? 0,
        member_name: item.member_name ?? "",
        reference_name: item.reference_name ?? "",
        source_id: item.source_id ?? "",
        source_category: item.source_category ?? "",
        source_title: item.source_title ?? "",
        note: item.note ?? ""
      })),
      borrower_member_index: record.data.borrower_member_index ?? 0,
      family_provident_support_enabled: record.data.family_provident_support_enabled ?? false,
      family_provident_support_label: record.data.family_provident_support_label ?? "亲属异地公积金首付支持",
      family_down_payment_support_mode: record.data.family_down_payment_support_mode ?? "provident",
      family_savings_support_amount: record.data.family_savings_support_amount ?? 0,
      family_provident_initial_balance: record.data.family_provident_initial_balance ?? 0,
      family_provident_monthly_salary: record.data.family_provident_monthly_salary ?? 0,
      family_provident_total_rate: record.data.family_provident_total_rate ?? 0.24,
      major_goal_tradeoff_mode: record.data.major_goal_tradeoff_mode ?? "auto",
      major_goal_timing_preference: record.data.major_goal_timing_preference ?? 0.5,
      investment_buy_fee_rate: record.data.investment_buy_fee_rate ?? 0.0015,
      investment_sell_fee_rate: record.data.investment_sell_fee_rate ?? 0.005,
      investment_taxable_return_ratio: record.data.investment_taxable_return_ratio ?? 0,
      investment_return_tax_rate: record.data.investment_return_tax_rate ?? 0,
      investment_tax_profile: {
        ...defaultInvestmentTaxProfile,
        ...(record.data.investment_tax_profile ?? {})
      }
    }
  };
}

const pages = ["家庭财务", "规划目标", "购车计划", "购房计划", "房产监测", "理财计划", "养娃计划", "税务", "可视化", "记账校准", "政策规则", "导出方案"] as const;
type PageName = (typeof pages)[number];
type SaveState = "idle" | "dirty" | "saving" | "saved";
type ThemeMode = "light" | "dark";
type VisualizationTimelineState = {
  selectedMonthIndex: number;
  viewStartMonth: number;
  viewWindowMonths: number;
};
const DEFAULT_VISUALIZATION_TIMELINE_STATE: VisualizationTimelineState = {
  selectedMonthIndex: 1,
  viewStartMonth: 0,
  viewWindowMonths: 120
};
type CollapseProfile = "core" | "advanced" | "explanation" | "longList";
const COLLAPSE_DEFAULTS: Record<CollapseProfile, boolean> = {
  core: true,
  advanced: false,
  explanation: false,
  longList: false,
};
type ScenarioComparison = {
  scenario: RecordEnvelope<ScenarioData>;
  result: AffordabilityResult;
  recommendation: PurchasePlanAnalysis | null;
  selectedPlan: PurchasePlanAnalysis | null;
};

const noPurchaseScenarioId = "__no_purchase_baseline__";

function createTargetScenarioData(sequence: number): ScenarioData {
  return {
    planning_goal_id: "",
    name: sequence <= 1 ? "第一套购房需求 · 候选房源 1" : `第 ${sequence} 套购房需求 · 候选房源 1`,
    enabled: true,
    purchase_sequence: Math.max(1, sequence),
    purchase_planning_mode: homePurchasePlanningModeForSequence(sequence),
    depends_on_goal_id: "",
    after_previous_purchase_delay_months: 0,
    district: "未设置",
    ring_area: "未设置",
    property_type: "二手房",
    green_building_level: "none",
    prefab_building_level: "none",
    is_ultra_low_energy_building: false,
    building_age_years: 0,
    building_structure: "unknown",
    is_old_community_renovated: false,
    remaining_land_use_years: null,
    total_price: 3000000,
    area_sqm: 80,
    down_payment_amount: 0,
    commercial_loan_amount: 0,
    provident_loan_amount: 0,
    manual_purchase_delay_months: 0,
    planning_window_start_month: "",
    planning_window_end_month: "",
    micro_commercial_loan_ratio: 0,
    commercial_rate: 0.035,
    loan_years: 25,
    repayment_method: "equal_installment",
    loan_repayment_strategy_mode: "auto",
    commercial_repayment_method: "equal_installment",
    provident_repayment_method: "equal_installment",
    commercial_prepayment_mode: "auto",
    commercial_prepayment_enabled: false,
    commercial_prepayment_start_month: 1,
    commercial_prepayment_allowed_after_month: 12,
    commercial_prepayment_monthly_amount: 0,
    provident_account_repayment_strategy: "auto",
    provident_account_repayment_switch_enabled: false,
    provident_account_repayment_switch_after_month: 12,
    provident_account_repayment_switch_to_strategy: "semiannual_principal_offset",
    broker_fee_rate: 0.022,
    seller_tax_pass_through_enabled: false,
    seller_tax_pass_through_rate: 0,
    seller_tax_pass_through_amount: 0,
    moving_and_misc_cost: 50000,
    annual_investment_return: 0.025,
    investment_withdrawal_mode: "auto",
    investment_min_balance_after_purchase: 0,
    happiness_score: 7,
    commute_score: 7,
    school_score: 6,
    liquidity_priority_score: 7,
    notes: "",
    selected_purchase_plan_variant: "",
    valuation_monitoring_enabled: false,
    valuation_asset_status: "planned",
    valuation_interval_months: 1,
    valuation_reference_date: "",
    valuation_reference_value: 0,
    valuation_comparable_unit_price: 0,
    valuation_district_adjustment_rate: 0
  };
}

function completeScenarioDefaults(record: RecordEnvelope<ScenarioData>, index: number): RecordEnvelope<ScenarioData> {
  const commercialPrepaymentMode =
    record.data.commercial_prepayment_mode ?? (record.data.commercial_prepayment_enabled ? "manual" : "auto");
  return {
    ...record,
    data: {
      ...createTargetScenarioData(index + 1),
      ...record.data,
      enabled: record.data.enabled ?? true,
      purchase_sequence: record.data.purchase_sequence ?? index + 1,
      purchase_planning_mode: record.data.purchase_planning_mode ?? homePurchasePlanningModeForSequence(index + 1),
      depends_on_goal_id: record.data.depends_on_goal_id ?? "",
      after_previous_purchase_delay_months: record.data.after_previous_purchase_delay_months ?? 0,
      investment_withdrawal_mode: record.data.investment_withdrawal_mode ?? "auto",
      investment_min_balance_after_purchase: record.data.investment_min_balance_after_purchase ?? 0,
      commercial_prepayment_mode: commercialPrepaymentMode,
      commercial_prepayment_enabled: commercialPrepaymentMode === "manual",
      commercial_prepayment_start_month: record.data.commercial_prepayment_start_month ?? 1,
      commercial_prepayment_allowed_after_month: record.data.commercial_prepayment_allowed_after_month ?? 12,
      commercial_prepayment_monthly_amount: commercialPrepaymentMode === "none" ? 0 : record.data.commercial_prepayment_monthly_amount ?? 0,
      provident_account_repayment_strategy: record.data.provident_account_repayment_strategy ?? "auto",
      provident_account_repayment_switch_enabled: record.data.provident_account_repayment_switch_enabled ?? false,
      provident_account_repayment_switch_after_month: record.data.provident_account_repayment_switch_after_month ?? 12,
      provident_account_repayment_switch_to_strategy:
        record.data.provident_account_repayment_switch_to_strategy ?? "semiannual_principal_offset"
    }
  };
}

function scenarioRecordFromHomeGoal(goal: PlanningGoalRecord, index: number): RecordEnvelope<ScenarioData> {
  return completeScenarioDefaults(
    {
      id: goal.id,
      household_id: goal.household_id,
      data: scenarioFromHomePlanningGoal(goal),
      created_at: goal.created_at,
      updated_at: goal.updated_at
    },
    index
  );
}

const noPurchaseScenario: RecordEnvelope<ScenarioData> = {
  id: noPurchaseScenarioId,
  data: {
    ...createTargetScenarioData(1),
    name: "不买房基线",
    enabled: false,
    total_price: 0,
    moving_and_misc_cost: 0
  },
  created_at: "",
  updated_at: ""
};

function investmentStrategyDetails(variant: string): string[] {
  if (variant.includes("现金") || variant.includes("安全")) {
    return ["先保证现金账户安全垫", "现金不足时降低定投", "现金超额后再逐步追加投资"];
  }
  if (variant.includes("长期") || variant.includes("收益")) {
    return ["适合目标事件较远时使用", "提高权益资产比例", "收益继续留在投资账户复利"];
  }
  return ["按月结余动态确定定投", "兼顾现金账户和投资账户", "买房买车前保留必要流动性"];
}

function purchaseStrategyDetails(plan: PurchasePlanAnalysis): string[] {
  return [
    plan.months_to_buy === null ? "当前现金路径暂不可达" : `${formatMonthDate(new Date(), plan.months_to_buy)} 可执行`,
    plan.property_price_forecast_applied
      ? `买入月房价预测 ${money(plan.projected_purchase_price)}，已进入首付和贷款测算`
      : `按当前目标报价 ${money(plan.original_target_price)} 测算`,
    `公积金贷 ${money(plan.provident_loan_amount)}，商贷 ${money(plan.commercial_loan_amount)}`,
    plan.liquidity_ok ? "买后现金安全垫达标" : "买后现金安全垫偏紧"
  ];
}

const parameterExplanations: Record<string, string> = {
  家庭名称: "仅用于区分方案，不参与计算。建议写成便于识别的版本，例如“当前家庭基准版”。",
  亲属首付支持: "可选情景：亲属用积蓄或符合条件的异地公积金帮助首付。积蓄支持按可支持金额计入；公积金支持按新房场景和账户余额增长估算，启用前应按实际政策核验。",
  支持资金来源: "选择亲属支持来自普通积蓄还是公积金账户。普通积蓄不受新房/二手房性质限制；公积金支持会按当前规则更保守地只在符合条件的新房里计入。",
  可支持首付金额: "亲属愿意且能够在购房交易时拿出的积蓄金额，用来减少家庭自己需要覆盖的交易现金。",
  支持账户当前余额: "亲属公积金账户今天的余额。系统会按当前余额加上未来每月入账额，估算购房当月可用于首付的上限。",
  支持账户月工资: "用于估算亲属公积金每月入账额的工资基数。",
  支持账户双边比例: "亲属个人和单位合计公积金缴存比例。默认 24% 表示个人 12% + 单位 12%。",
  购后安全垫月数: "买房或买车后希望保留的生活费月数。数值越高，系统越倾向延后买入或提高现金留存。",
  理财计划: "选择当前理财策略。手动指定会使用你填写的定投、费率和资产比例；自动方案会推荐更合适的配置。",
  当前投资资产: "今天已经在基金、股票、债券、理财等账户里的资产。后续会按年化收益、定投和手续费滚动。",
  测算年化: "对投资资产使用的预期年化收益率，不是保证收益。风险越高，建议同时保留更厚现金垫。",
  预估年收益: "按当前投资资产和测算年化粗略估算的一年收益，用于直觉参考。",
  折合月收益: "把预估年收益平均到每个月，仅用于展示；真实收益会波动。",
  应税收益比例: "理财收益中需要纳税的比例。默认 0，表示暂不对投资收益扣税；如果某类产品收益需要纳税，可在这里设置。",
  理财收益税率: "对上方应税收益部分采用的估算税率。后端会从投资收益中扣除，不计入工资个税。",
  当前可动用现金: "今天可随时用于首付、应急和日常支出的现金，不包含已投入理财的资产。",
  基础月支出: "日常家庭支出的当前月额，不含租房、房贷、车贷、已有贷款和计划支出。",
  家庭支出阶段: "日常支出按阶段生效，用来模拟生活方式、成员加入或家庭支持变化。",
  日常月支出: "该阶段每月固定发生的生活消费，不含租房和贷款。",
  租金月额: "该阶段每月租金。现金支付会进入现金家庭支出；公积金余额支付会进入公积金租房提取。",
  中介费月数: "租房开始时一次性发生的中介费，默认按 1 个月租金估算；如果填写固定中介费金额，则优先使用固定金额。",
  固定中介费: "可选。填入后租房开始月直接按这个金额扣现金；留空则按中介费月数乘以月租金估算。",
  首年服务费率: "租房第一年每次付租金时额外发生的服务费比例，默认按月租金的 9% 估算。",
  后续服务费率: "租房满一年后每次付租金时额外发生的服务费比例，默认按月租金的 6% 估算。",
  租房支付方式: "现金付房租会直接消耗现金；公积金余额付房租按所选支付频率进入公积金账户租房提取，不作为工资现金收入。",
  租房支付频率: "月付表示每月发生一次；季付表示从阶段开始月起每 3 个月支付 3 个月租金。",
  当前实际月支出: "日常支出、现金租房和本月已经生效的计划支出合计，用于判断现金安全垫。",
  支出名称: "计划支出的名称，会直接显示在月现金流里，例如家庭支持支出、年度数码支出。",
  发生频率: "选择这项支出是每月发生、每年固定月份发生，还是一次性发生。",
  支出金额: "这项支出在对应频率下发生的金额。每月支出每月扣除；年度和一次性支出只在发生月扣除。",
  年度发生月份: "一年一次支出的发生月份，例如每年 6 月购买数码产品。",
  开始月份: "该项支出从哪个月份开始计入现金流。",
  结束月份: "可选；填了以后，结束月份之后不再计入现金流。",
  时间安排: "一次性支出可以指定某个月，也可以给出可接受时间范围，由策略安排具体发生月。",
  发生月份: "一次性支出的固定发生月份。",
  最晚月份: "给策略安排一次性支出时可接受的最晚月份。",
  归属成员: "老人专项扣除归属于哪位收入成员。按政策通常只能扣自己的父母，不能夫妻互转。",
  称谓: "用于界面识别老人来源，例如成员一方直系亲属老人。",
  出生月份: "用于判断老人满 60 周岁的月份；系统从满 60 周岁当月开始计算赡养老人专项附加扣除。",
  本人分摊扣除: "非独生子女时本人每月可申报的分摊额，个人上限通常为 1500 元/月。",
  成员名称: "收入成员名称。老人专项扣除、工资阶段和可视化明细会按这个名称关联。",
  加入家庭月份: "该成员从哪个月份进入当前家庭财务共同体；后续会用于区分加入前后的账户和资产负债状态。",
  社保月数: "该成员已累计的社保缴纳月数，用于购房资格、失业金待遇期限等政策判断。",
  个税月数: "该成员已累计的个税缴纳月数；家庭资格展示会和社保月数一起取更有利的有效月数。",
  已有住房套数: "该成员名下已有住房套数。家庭画像会按成员汇总展示，并影响购房资格、首套/二套和贷款策略。",
  已有房贷笔数: "该成员名下仍计入政策判断的房贷笔数。家庭画像会按成员汇总展示。",
  加入时现金: "成员加入家庭财务共同体时带入的现金账户余额。填写成员值后，后端会优先用成员合计作为家庭初始现金。",
  加入时投资资产: "成员加入时带入的投资账户余额。填写成员值后，后端会优先用成员合计作为家庭初始投资账户。",
  加入时公积金余额: "成员加入时的住房公积金账户余额。后端会按成员账户分别计算缴存、利息、提取和还贷。",
  加入时其他资产: "不属于现金、投资、公积金的其他资产备注性金额，例如已持有车辆或其他可估值资产。",
  加入时其他负债: "加入家庭时已有但未在“已有贷款”中细分建模的其他负债余额，仅用于画像和后续资产负债扩展。",
  阶段名称: "工资阶段的名称，例如当前收入、换工作后。用于识别不同收入时期。",
  阶段类型: "选择这一段收入的性质。工资就业会按工资薪金自动扣社保、公积金和个税；失业期、自由职业和养老金阶段会按你填写或系统生成的收入项测算。",
  开始日期: "该工资阶段从哪天开始生效；税费和公积金会按月份匹配阶段。",
  结束日期: "该工资阶段结束日期；留空表示一直持续。",
  月工资税前: "每月税前工资，是社保、公积金、个税预扣和现金流收入的基础。",
  自由职业收入: "打开后，这一收入阶段可以额外填写自由职业收入；阶段类型选为自由职业时会默认打开。",
  "自由职业收入/月": "这一阶段实际发生的自由职业月收入，会作为综合所得现金收入纳入税务和现金流测算。",
  年终奖年额: "预计全年年终奖金额。可以选择发放月一次性入账，也可以选择按月均摊发放；后端会按不同发放模式进入对应税务口径。",
  奖金发放方式: "一次性发放按全年一次性奖金或并入综合所得测算；按月均摊会作为工资薪金收入进入每月累计预扣，不再走年终奖单独计税。",
  发放月份: "仅适用于发放月一次性发放模式。不同成员、不同工作阶段可以不同；税率和单独计税有效期仍由政策规则控制。",
  奖金归属起始月份: "起始月份从该月1日开始计入。例如选择2月开始、次年1月结束，表示奖金周期为2月1日至次年1月31日；这里只选择月份，不需要填写年份。",
  奖金归属截止月份: "截止月份计算到该月最后一日。例如2月至次年1月表示截止到次年1月31日。系统会把这个周期与收入阶段实际在职月份取交集，再按在职月数折算奖金。",
  家庭指标开始月: "整个家庭开始按家庭单位参与北京小客车指标计算的月份。单个申请人有不同加入月份时，可在申请人卡片里单独覆盖。",
  申请人名称: "只用于购车指标算分说明，不会自动加入家庭成员、收入、支出或现金流。",
  家庭关系: "主申请人和配偶积分权重按 2 计，其他家庭申请人按 1 计。",
  所属代际: "用于计算家庭代际数。比如加入一位符合条件的老人可形成父母一代，提高代际乘数，但不代表老人进入家庭财务现金流。",
  资格口径: "北京家庭指标申请资格来源，例如北京户籍、北京工作居住证、北京居住证并满足连续社保/个税等。这里用于提示和说明，具体资格仍需按官方口径复核。",
  加入家庭指标月: "该申请人从什么时候开始参与家庭指标计算。留空时使用上方家庭指标开始月。",
  个人指标历史: "参与家庭指标前个人普通指标摇号阶梯或新能源轮候历史会影响基础分；如已有官方计算结果，也可用个人历史分覆盖。",
  普通摇号阶梯数: "参与普通指标摇号积累的阶梯数，用于粗略折算家庭积分中的个人历史部分。",
  新能源轮候开始月: "个人新能源指标轮候开始月份；后端按进入家庭申请前的满年数粗略折算历史积分。",
  个人历史分覆盖: "如果已有官方系统给出的个人历史积分，可直接填写覆盖值；填 0 表示不用覆盖，按阶梯数和轮候开始月估算。",
  仅参与指标算分: "开启后，这个人只作为北京家庭指标申请人参与积分说明，不进入家庭收入、支出、资产、贷款和现金流。",
  "非税收入/月": "每月进入现金流但不并入工资薪金计税的收入，例如失业金等；退休养老金会由后端按退休月份单独生成并在可视化中拆分展示。",
  记账校准: "当模型推演余额和真实账户余额不一致时，在记账校准页按月份校准现金、投资、公积金、贷款或固定资产。现金流偏差由账户余额校准吸收，不再在收入阶段里手动扣一笔现金流。",
  工资社保扣缴: "开启时按工资薪金自动估算北京社保、公积金和个税；失业金、养老金等阶段应关闭。",
  公积金中心口径: "该收入阶段对应工作单位的公积金管理口径。换工作后可在新阶段改为市管或国管，购房策略会按借款申请人在买房月份生效的阶段选择还贷规则。",
  个人公积金比例: "个人缴纳住房公积金比例，会减少税后现金但增加公积金账户余额。",
  单位公积金比例: "单位缴纳住房公积金比例，会进入公积金账户，但不是当月现金工资。",
  "专项附加/月": "除赡养老人外的每月专项附加扣除，例如子女教育、住房租金等。",
  其他年收入: "工资薪金以外但需要并入综合所得测算的年度收入。",
  年终奖计税: "选择年终奖按单独计税、并入工资或由系统自动择优。",
  裁员年龄: "压力情景触发年龄。达到该年龄当月起，系统自动切换到失业金和自缴社保收入阶段。",
  自动估算失业保险待遇: "开启后按家庭画像里的累计社保/个税月数估算待遇期限，并按规则包里的北京失业保险金标准分档生成现金流；关闭后使用手动月数和月额。",
  自动估算灵活就业自缴: "开启后按规则包里的灵活就业缴费基数、养老比例、失业比例和医保月额合计生成裁员后的自缴社保支出。",
  自动估算灵活就业公积金: "开启后按规则包里的灵活就业公积金基数和比例生成自缴公积金。它会进入成员公积金账户，不作为可随意动用的现金。",
  自动估算退休养老金: "开启后系统按基础养老金加个人账户养老金的简化公式估算退休后月收入；关闭后可逐个成员手动填写养老金。",
  估算失业金月数: "根据累计社保/个税月数估算：不足 12 个月为 0，1-5 年为 12 个月，5-10 年为 18 个月，10 年以上为 24 个月。",
  估算失业金月额: "按规则包里的北京失业保险金分档金额展示；如果超过 12 个月，斜杠后是第 13 个月起的后续期金额。",
  "估算自缴社保/月": "按规则包自动估算的灵活就业养老、失业和医保合计月支出。",
  "估算自缴公积金/月": "按规则包自动估算的灵活就业住房公积金月缴存额，会增加对应成员的公积金账户余额。",
  失业金月数: "手动覆盖失业保险待遇期限；自动估算关闭时才参与计算，最长按 24 个月建模。",
  失业金月额: "手动覆盖失业保险金月额；自动估算关闭时才参与计算，作为非税现金收入进入家庭现金流。",
  "自缴社保/月": "手动覆盖裁员后以灵活就业身份自行缴纳养老、医保等的月现金支出；自动估算关闭时才参与计算。",
  "自缴公积金/月": "手动覆盖灵活就业住房公积金月缴存额；自动估算关闭时才参与计算。",
  "冲击期自由职业收入/月": "职业冲击启用后，后端生成的失业金期和灵活就业自缴期会带入这笔自由职业月收入；默认 0，不会影响未启用职业冲击的成员。",
  自动估算养老金: "开启后按成员年龄、退休年龄、缴费基数和规则包里的养老金参数估算；关闭后使用手动养老金。",
  "预计养老金/月": "按当前规则估算的退休后非税现金收入，用于长期现金流，不代表社保机构最终核定金额。",
  借款人: "贷款归属人，只用于展示和汇总，不改变还款计算公式。",
  贷款名称: "用于区分多笔贷款，例如低息贷款 A、教育贷款 A 或亲友借款 A。",
  本金: "当前仍需偿还或进入测算的贷款本金。",
  年利率: "贷款年化利率。等额本息/本金会按该利率计算还款。",
  还款方式: "等额本息月供较稳定，等额本金前期压力更高但总利息更少。",
  剩余期数: "从当前开始还剩多少个月需要还款。",
  计息开始月: "从哪个月份开始产生利息。",
  只还利息至: "政策宽限期结束月份；此前只还利息，之后进入本金偿还。",
  每月定投: "计划每月投入理财的现金上限。现金安全垫不足时系统会自动减少或暂停。",
  现金安全垫月数: "理财策略要求保留的现金月数。月数越高，越保守。",
  权益比例: "投资组合中股票、偏股基金等权益资产占比。收益弹性更高，波动也更大。",
  固收比例: "债券、固收类基金等相对稳健资产占比。",
  现金比例: "投资组合中货币基金、活期、短债等低波动现金类资产占比。",
  买入手续费率: "每月定投买入时扣除的费用比例。定投现金支出不变，但进入投资资产的净额会减少。",
  卖出手续费率: "买房交易月卖出投资资产时扣除的费用比例。会减少可用于首付的现金。",
  规则包: "当前使用的政策和参数集合。修改规则会影响税费、公积金、贷款和可买时间。",
  当前采用: "当前正在用于计算和可视化的策略。",
  房源总价: "候选房源总价。直接决定首付、税费、贷款规模和可买时间。",
  建筑面积: "用于对比房源性价比和居住体验评分，不直接改变贷款本金。",
  手动首付: "手动指定的首付金额。自动策略会在政策最低首付和现金约束之间校正。",
  手动商贷: "手动指定商业贷款金额。用于模拟特定贷款结构。",
  手动公积金贷: "手动指定公积金贷款金额，仍会受到北京公积金政策上限约束。",
  微量商贷手动比例: "微量商贷策略下可手动指定商贷占房价比例；留空或为 0 时由系统自动选择。",
  商贷利率: "商业贷款年利率，用于计算月供和总利息。",
  政策公积金利率: "由政策规则包按首套/二套和公积金贷款年限计算，不在房源目标里手动填写。",
  贷款年限: "贷款总年限。公积金贷款还会额外受年龄、房龄、土地年限等政策约束。",
  商贷还款: "商业贷款还款方式。等额本息稳定，等额本金前高后低。",
  公积金还款: "公积金贷款还款方式。会影响首月月供、平均月供和现金流压力。",
  公积金账户还贷策略: "买房后如何使用公积金账户余额。按月约定提取用于抵扣当期公积金贷月供；半年度冲还贷在每年 1 月和 7 月约定日集中冲抵本金，不能与约定提取同时启用。",
  公积金还贷切换: "只在手动选择按月约定提取或半年度冲还贷时生效。切换前后仍保持同一时间只有一种公积金还贷模式。",
  商贷提前还本策略: "选择是否让后端自动生成商贷额外还本。自动模式会比较商贷利率、理财预期净收益、买卖手续费和现金安全垫：只有提前还本的确定性收益更划算时才安排；手动指定则按下方参数固定测算。",
  商贷提前还本上限: "自动模式下作为每月额外还本上限，填 0 表示由系统按商贷本金和现金流自动设定；手动模式下表示每月额外还本金额。",
  希望起始还本月: "从第几个商贷还款月开始额外还本金；若早于合同允许月份，后端会自动顺延。",
  合同允许最早月: "银行合同允许提前还本的最早还款月。不同银行可能有一年后、金额限制或违约金，建议按实际合同填写。",
  政策契税比例: "由政策规则包按首套/二套和房屋面积计算，计入买房交易现金需求。",
  政策契税金额: "按候选房源总价乘以后端政策契税比例得到。",
  中介费假设: "中介服务费属于市场交易成本假设，可按实际报价手动覆盖。",
  搬家杂费: "搬家、家电、维修、临时周转等一次性杂费，计入交易现金需求。",
  居住幸福度: "房源本身带来的居住体验评分，会进入幸福指数。",
  通勤评分: "通勤便利程度评分，会进入幸福指数。",
  教育评分: "教育资源匹配程度评分，会进入幸福指数。",
  流动性偏好: "越重视流动性，系统越倾向保留更多现金、降低买后压力。",
  房屋性质: "新房、二手房等性质会影响公积金提取、贷款年限和部分政策适用。",
  绿色建筑: "符合绿色建筑条件的新房可能提高公积金贷款上限。",
  装配式等级: "装配式建筑等级可能提高公积金贷款上限。",
  二手房房龄: "二手房房龄会影响公积金贷款年限。",
  建筑结构: "二手房结构影响房屋耐用年限口径，从而影响公积金贷款年限。",
  剩余土地年限: "老旧小区改造等情形下用于约束公积金贷款年限。",
  车辆总价: "目标车辆落地前的购车总价，用于生成首付和贷款方案。",
  首付比例: "买车首付占车价比例。比例越高，贷款越少但短期现金压力越大。",
  首付金额: "买车首付现金金额。可由首付比例自动估算，也可手动微调。",
  延后买车月数: "从现在起延后多少个月买车，用于保留现金或等待收入提升。",
  总期数: "车贷总还款月数。",
  贴息期数: "车贷合同仍按全期等额本息计息；贴息期内厂家或经销商补贴部分利息，家庭现金支出按贴息后净月供计算。",
  合同年利率: "车贷合同全期使用的年化利率。所谓前段免息按厂家/经销商贴息处理，不改变贷款余额的等额本息推演。",
  当前期数: "当前已经处在车贷第几期，用于计算当前月供。",
  计划额外还本起始期: "希望从车贷第几期开始在合同月供之外额外还本金；如果早于合同允许提前还本的期数，后端会自动顺延。",
  合同允许提前还本期: "车贷合同允许提前还本金的最早还款期数。很多车贷会要求满 12 期后才可提前还本，或提前还本会有违约金、金额限制，建议按真实合同填写。",
  "额外还本金/月": "启用车贷提前还本后，每月在合同月供之外额外偿还的本金金额。自动策略会综合现金压力、购房速度、贴息后实际贷款成本和理财预期净收益决定是否采用。",
  攒车首付开始: "从哪个月份开始为买车首付积累现金。",
  年行驶里程: "估算电费、保养和折旧时使用的年行驶里程。",
  百公里电耗: "车辆每 100 公里耗电量，用于估算每月电费。",
  充电单价: "每度电价格，用于估算电费。",
  月停车费: "每月固定停车成本。",
  无车通勤月成本: "不买车或延后买车期间的打车、公交、地铁、共享出行等月均成本，会计入日常现金流。",
  年保养杂费: "保险外的保养、洗车、小维修等年度成本。",
  保养年增长: "车辆使用年限增加后，保养、小维修和耗材成本可能逐年上升。系统只在年度保养付款月计入增长后的现金支出。",
  保险费率: "按车价估算年度保险费用的比例。",
  年保险下限: "保险估算的最低年度金额，防止新车保险被低估。",
  保险年增长: "用于估算后续年份车险价格变化。系统只在年度保险付款月计入增长后的现金支出。",
  折旧年限: "用于估算车辆折旧成本，不代表真实卖车价格。",
  车辆使用年限: "不是政策强制报废年限，而是家庭按性能衰减、维修经济性和用车体验设定的预计实际使用期；默认按 10 年估算。",
  "报废/更新里程": "按小微非营运载客汽车 60 万公里引导报废口径作为提示阈值，可按实际用车强度调整。",
  第二辆车: "启用后会在指定月份之后把第二辆车首付、车贷和养车成本叠加到购房现金流和可视化。",
  第二辆车总价: "第二辆车预算总价。",
  第二车首付比例: "第二辆车贷款方案的首付比例。",
  第二车延后月数: "从现在起第几个月购买第二辆车。",
  第二车总期数: "第二辆车贷款总期数。",
  第二车贴息期数: "第二辆车贷款中由厂家或经销商补贴利息的期数。",
  第二车合同利率: "第二辆车贷款合同全期使用的年化利率；贴息期只影响家庭实际现金支出，不改变合同余额推演。",
  第二车年里程: "第二辆车预计年行驶里程，用于估算电费和报废里程时间。",
  第二车月停车费: "第二辆车每月新增停车费。",
  买车幸福度: "车辆对家庭便利、舒适、时间节省的主观评分。",
  "社保/个税月数": "在京社保或个税累计月数，用于购房资格和公积金缴存年限相关测算。",
  借款申请人: "选择用于公积金贷款年限测算的家庭成员。借款申请人年龄会自动取该成员的出生年月或当前年龄。",
  借款申请人年龄: "自动取所选借款申请人的年龄，用于判断公积金可贷年限；年龄越大可贷年限可能越短。",
  当前已出生子女数: "只统计截至当前月份已经出生的子女，用于当前家庭状态与资格判断。未来养娃目标仍会进入策略、税务时间线和长期现金流，但不会提前计入这里。",
  现有住房套数: "影响购房资格、首付比例和贷款政策。",
  现有房贷笔数: "影响贷款认定和风险判断。",
  公积金账户余额: "当前成员本人的公积金账户余额；后端会按成员账户分别计息、缴存、提取、按月抵月供和半年度冲本金。",
  失业金1至5年: "累计缴费满 1 年不满 5 年时使用的北京失业保险金月标准。",
  失业金5至10年: "累计缴费满 5 年不满 10 年时使用的北京失业保险金月标准。",
  失业金10至15年: "累计缴费满 10 年不满 15 年时使用的北京失业保险金月标准。",
  失业金15至20年: "累计缴费满 15 年不满 20 年时使用的北京失业保险金月标准。",
  失业金20年以上: "累计缴费满 20 年以上时使用的北京失业保险金月标准。",
  失业金13月后: "失业保险待遇领取第 13 个月起使用的后续期月标准。",
  灵活就业基数: "自动估算自缴社保时使用的灵活就业缴费基数，系统会限制在社保基数上下限之间。",
  灵活养老比例: "灵活就业人员基本养老保险缴费比例。",
  灵活失业比例: "灵活就业人员失业保险缴费比例。",
  灵活医保月额: "灵活就业人员基本医疗保险月缴费额，按北京当期固定标准维护。",
  首套商贷首付: "首套房商业贷款最低首付比例。",
  首套公积金首付: "首套房使用公积金贷款时的最低首付比例。",
  首套公积金额度: "首套房公积金贷款基础额度上限，不含绿色建筑等上浮。",
  每缴存年可贷额度: "北京公积金按缴存年限累积的可贷额度口径。",
  微量商贷自动下限: "系统自动生成微量商贷策略时尝试的最低商贷比例。",
  微量商贷默认比例: "微量商贷策略的默认比例，用于平衡买房速度和负债压力。",
  微量商贷自动上限: "系统自动生成微量商贷策略时允许尝试的最高商贷比例。",
  "谨慎 DTI": "负债收入比较舒适的阈值，低于该值通常现金流压力较小。",
  "高风险 DTI": "负债收入比较高的阈值，超过该值会显著压低幸福指数和可行性。"
};

const repaymentMethodLabels: Record<RepaymentMethod, string> = {
  equal_installment: "等额本息",
  equal_principal: "等额本金"
};

const commercialPrepaymentModeLabels: Record<CommercialPrepaymentMode, string> = {
  auto: "策略自动生成",
  manual: "手动指定",
  none: "不提前还本"
};

const providentAccountRepaymentStrategyLabels: Record<ProvidentAccountRepaymentStrategy, string> = {
  auto: "按政策和现金压力自动选择",
  monthly_repayment_withdrawal: "按月约定提取抵月供",
  semiannual_principal_offset: "半年度冲本金缩期",
  keep_in_account: "留存在公积金账户"
};

const providentAccountRepaymentSwitchTargetLabels: Record<ProvidentAccountRepaymentSwitchTarget, string> = {
  monthly_repayment_withdrawal: "按月约定提取抵月供",
  semiannual_principal_offset: "半年度冲还贷"
};

const accountCalibrationScopeLabels: Record<AccountCalibrationScope, string> = {
  account: "账户余额",
  concept: "重要概念",
  major_event: "重大事件",
  strategy_event: "策略事件"
};

const existingLoanTypeLabels: Record<NonNullable<PhasedLoanData["loan_type"]>, string> = {
  mortgage: "房贷",
  car: "车贷",
  education: "教育贷款",
  consumer: "消费贷款",
  other: "其他贷款"
};

function compactMoneyTick(value: unknown) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "";
  const abs = Math.abs(amount);
  if (abs >= 100000000) {
    const text = (amount / 100000000).toFixed(abs >= 1000000000 ? 0 : 1).replace(/\.0$/, "");
    return `${text}亿`;
  }
  if (abs >= 10000) {
    const text = (amount / 10000).toFixed(abs >= 100000 ? 0 : 1).replace(/\.0$/, "");
    return `${text}万`;
  }
  if (abs >= 1000) {
    return `${Math.round(amount / 1000)}千`;
  }
  return `${Math.round(amount)}`;
}

function familySupportAmount(plan: PurchasePlanAnalysis) {
  return plan.family_down_payment_support_amount ?? plan.family_provident_upfront_extractable ?? 0;
}

function familySupportLabel(plan: PurchasePlanAnalysis) {
  if (familySupportAmount(plan) <= 0) return "";
  return plan.family_down_payment_support_label || (
    plan.family_down_payment_support_mode === "savings" ? "亲属积蓄首付支持" : "亲属公积金首付支持"
  );
}

function familySupportPhrase(plan: PurchasePlanAnalysis) {
  const amount = familySupportAmount(plan);
  const label = familySupportLabel(plan);
  return amount > 0 && label ? `，${label} ${money(amount)}` : "";
}

function providentStrategyLabel(plan: PurchasePlanAnalysis) {
  return plan.post_purchase_pf_strategy_label || "默认留存在公积金账户";
}

const greenBuildingLabels = {
  none: "不适用",
  two_star: "二星绿色建筑",
  three_star: "三星绿色建筑"
} as const;

const prefabBuildingLabels = {
  none: "不适用",
  A: "装配式 A",
  AA: "装配式 AA",
  AAA: "装配式 AAA"
} as const;

function addMonths(baseDate: Date, months: number) {
  return new Date(baseDate.getFullYear(), baseDate.getMonth() + months, 1);
}

function formatMonthDate(baseDate: Date, monthsFromNow: number) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  return `${targetDate.getFullYear()}年${targetDate.getMonth() + 1}月`;
}

function formatPurchaseTiming(baseDate: Date, monthsToBuy: number | null | undefined, yearsToBuy?: number | null) {
  if (monthsToBuy === null || monthsToBuy === undefined) return "暂不可达";
  const relativeYears = yearsToBuy ?? Math.round((Math.max(0, monthsToBuy) / 12) * 10) / 10;
  return `${formatMonthDate(baseDate, monthsToBuy)}（距今约 ${relativeYears} 年）`;
}

function formatMonthInputValue(baseDate: Date, monthsFromNow: number) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  return `${targetDate.getFullYear()}-${String(targetDate.getMonth() + 1).padStart(2, "0")}`;
}

function formatTodayDate(baseDate: Date) {
  return `${baseDate.getFullYear()}年${baseDate.getMonth() + 1}月${baseDate.getDate()}日`;
}

function parseMonthValue(value: string | null | undefined) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{1,2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
  return { year, month };
}

function formatMonthValue(year: number, month: number) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function childStrategyBirthMonthValue(strategy: ChildPlanStrategyPoint | null | undefined) {
  const label = strategy?.birth_month_label?.trim();
  if (!label) return "";
  const direct = parseMonthValue(label);
  if (direct) return formatMonthValue(direct.year, direct.month);
  const match = /(\d{4})\D{0,4}(\d{1,2})/.exec(label);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return "";
  return formatMonthValue(year, month);
}

function compareMonth(left: { year: number; month: number }, right: { year: number; month: number }) {
  return (left.year - right.year) * 12 + left.month - right.month;
}

function formatAgeFromBirthMonth(value: string | null | undefined, today = new Date()) {
  const birthMonth = parseMonthValue(value);
  if (!birthMonth) return "待填写";
  const ageInMonths = compareMonth(
    { year: today.getFullYear(), month: today.getMonth() + 1 },
    birthMonth
  );
  if (ageInMonths < 0) return "待填写";
  const years = Math.floor(ageInMonths / 12);
  const months = ageInMonths % 12;
  return months > 0 ? `${years}岁${months}个月` : `${years}岁`;
}

function ageYearsFromBirthMonth(value: string | null | undefined, today = new Date()) {
  const birthMonth = parseMonthValue(value);
  if (!birthMonth) return null;
  const ageInMonths = compareMonth(
    { year: today.getFullYear(), month: today.getMonth() + 1 },
    birthMonth
  );
  return ageInMonths >= 0 ? Math.floor(ageInMonths / 12) : null;
}

function birthMonthFromAge(age: number, today = new Date()) {
  const safeAge = Math.max(0, Math.floor(age));
  const birthYear = today.getFullYear() - safeAge;
  return `${birthYear}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function householdExpenseAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  const dailyStage = dailyExpenseStageAt(household, baseDate, monthsFromNow);
  const rentStage = rentExpenseStageAt(household, baseDate, monthsFromNow);
  const baseLivingExpense = dailyStage?.base_living_expense ?? household.monthly_expense;
  const rentCashExpense = rentStage ? rentStageCashCostAt(rentStage, baseDate, monthsFromNow) : 0;
  return Math.max(
    0,
    baseLivingExpense +
      rentCashExpense +
      scheduledExpenseRowsAt(household, baseDate, monthsFromNow).reduce((sum, item) => sum + item.amount, 0)
  );
}

function rentStagePaymentAt(stage: RentExpenseStageData, baseDate: Date, monthsFromNow = 0) {
  const monthlyRent = Math.max(0, stage.rent_amount ?? 0);
  if ((stage.rent_payment_frequency ?? "monthly") !== "quarterly") return monthlyRent;
  const start = parseMonthValue(stage.start_month);
  if (!start) return monthlyRent * 3;
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const elapsed = (targetMonth.year - start.year) * 12 + (targetMonth.month - start.month);
  return elapsed >= 0 && elapsed % 3 === 0 ? monthlyRent * 3 : 0;
}

function rentStageElapsedMonths(stage: RentExpenseStageData, baseDate: Date, monthsFromNow = 0) {
  const start = parseMonthValue(stage.start_month);
  if (!start) return null;
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  return compareMonth(targetMonth, start);
}

function rentStageServiceFeeAt(stage: RentExpenseStageData, baseDate: Date, monthsFromNow = 0) {
  const rentPayment = rentStagePaymentAt(stage, baseDate, monthsFromNow);
  const elapsed = rentStageElapsedMonths(stage, baseDate, monthsFromNow);
  if (rentPayment <= 0 || elapsed === null || elapsed < 0) return 0;
  const rate = elapsed < 12 ? (stage.service_fee_first_year_rate ?? 0.09) : (stage.service_fee_later_year_rate ?? 0.06);
  return Math.max(0, rentPayment * Math.max(0, rate));
}

function rentStageBrokerFeeAt(stage: RentExpenseStageData, baseDate: Date, monthsFromNow = 0) {
  const elapsed = rentStageElapsedMonths(stage, baseDate, monthsFromNow);
  if (elapsed !== 0) return 0;
  if (stage.broker_fee_amount !== null && stage.broker_fee_amount !== undefined) return Math.max(0, stage.broker_fee_amount);
  return Math.max(0, (stage.rent_amount ?? 0) * (stage.broker_fee_months ?? 1));
}

function rentStageCashCostAt(stage: RentExpenseStageData, baseDate: Date, monthsFromNow = 0) {
  const rentCashPayment = stage.rent_payment_mode === "cash" ? rentStagePaymentAt(stage, baseDate, monthsFromNow) : 0;
  return rentCashPayment + rentStageServiceFeeAt(stage, baseDate, monthsFromNow) + rentStageBrokerFeeAt(stage, baseDate, monthsFromNow);
}

function scheduledExpenseRowsAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  return (household.scheduled_expenses ?? []).flatMap((item) => {
    const start = parseMonthValue(item.start_month);
    const end = parseMonthValue(item.end_month);
    if (!start) return [];
    const frequency = item.frequency ?? "monthly";
    if (frequency === "one_time") {
      const resolvedMonth = item.one_time_timing_mode === "flexible_range" && end && compareMonth(end, start) >= 0 ? end : start;
      if (compareMonth(targetMonth, resolvedMonth) !== 0) return [];
    } else {
      if (compareMonth(targetMonth, start) < 0) return [];
      if (end && compareMonth(targetMonth, end) > 0) return [];
      if (frequency === "annual_once" && targetMonth.month !== (item.annual_occurrence_month ?? start.month)) return [];
    }
    const amount = Math.max(0, item.monthly_amount);
    return amount > 0 ? [{ name: item.name || "计划支出", amount }] : [];
  });
}

function stageAt<T extends { start_month: string; end_month: string | null }>(stages: T[], baseDate: Date, monthsFromNow = 0) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  return stages.find((stage) => {
    const start = parseMonthValue(stage.start_month);
    const end = parseMonthValue(stage.end_month);
    if (!start || compareMonth(targetMonth, start) < 0) return false;
    if (end && compareMonth(targetMonth, end) > 0) return false;
    return true;
  }) ?? null;
}

function dailyExpenseStageAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  return stageAt(household.daily_expense_stages ?? [], baseDate, monthsFromNow);
}

function rentExpenseStageAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  return stageAt(household.rent_expense_stages ?? [], baseDate, monthsFromNow);
}

function elderlyDeductionStartMonth(dependent: ElderlyDependentData) {
  const birthMonth = parseMonthValue(dependent.birth_month);
  if (!birthMonth) return null;
  return { year: birthMonth.year + 60, month: birthMonth.month };
}

function elderlyCareDeductionForMemberAt(household: HouseholdData, memberName: string, targetDate: Date) {
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const total = (household.elderly_dependents ?? []).reduce((sum, dependent) => {
    if (dependent.member_name !== memberName) return sum;
    const startMonth = elderlyDeductionStartMonth(dependent);
    if (!startMonth || compareMonth(targetMonth, startMonth) < 0) return sum;
    return sum + (dependent.is_only_child ? 3000 : Math.min(Math.max(0, dependent.shared_monthly_deduction ?? 1500), 1500));
  }, 0);
  return Math.min(total, 3000);
}

function elderlyDeductionPolicyStatus(
  elderlyDependents: ElderlyDependentData[],
  targetDate = new Date()
) {
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const items = elderlyDependents
    .map((dependent) => {
      const startMonth = elderlyDeductionStartMonth(dependent);
      const monthlyDeduction = dependent.is_only_child
        ? 3000
        : Math.min(Math.max(0, dependent.shared_monthly_deduction ?? 1500), 1500);
      return { dependent, startMonth, monthlyDeduction };
    })
    .filter((item) => item.startMonth && item.monthlyDeduction > 0);
  const activeItems = items.filter((item) => item.startMonth && compareMonth(targetMonth, item.startMonth) >= 0);
  const nextItem = items
    .filter((item) => item.startMonth && compareMonth(targetMonth, item.startMonth) < 0)
    .sort((left, right) => compareMonth(left.startMonth!, right.startMonth!))[0];

  if (activeItems.length > 0) {
    const total = Math.min(3000, activeItems.reduce((sum, item) => sum + item.monthlyDeduction, 0));
    return {
      active: true,
      tone: "good" as const,
      label: `当前可按老人专项扣除测算，月扣除约 ${money(total)}`,
      detail: activeItems
        .map((item) => `${item.dependent.relationship_label || "直系亲属老人"}已满60岁`)
        .join("；")
    };
  }
  if (nextItem?.startMonth) {
    return {
      active: false,
      tone: "warn" as const,
      label: `暂未生效，预计 ${nextItem.startMonth.year}年${nextItem.startMonth.month}月 起满足老人专项扣除年龄条件`,
      detail: "系统会按老人出生月份自动判断，不需要在家庭支持支出里手动勾选。"
    };
  }
  return {
    active: false,
    tone: "warn" as const,
    label: "待填写老人出生月份后自动判断是否满足专项扣除",
    detail: "家庭支持支出只影响现金流；税收扣除请在“赡养老人专项扣除”里维护老人信息。"
  };
}

function incomeStageFromMember(member: IncomeMember): IncomeStageData {
  return {
    name: "当前收入",
    stage_kind: "salary",
    start_date: member.employment_start_date || "2026-07-01",
    end_date: null,
    provident_account_management_center: "beijing_municipal",
    monthly_salary_gross: member.monthly_salary_gross,
    annual_bonus_months: member.monthly_salary_gross > 0 ? Math.round(member.annual_bonus / member.monthly_salary_gross * 10) / 10 : 0,
    annual_bonus_payout_mode: "lump_sum",
    annual_bonus_payout_month: 4,
    annual_bonus_earning_start_month: null,
    annual_bonus_earning_end_month: null,
    monthly_freelance_income: 0,
    freelance_tax_mode: "labor_remuneration",
    monthly_non_taxable_income: 0,
    monthly_extra_cash_expense: 0,
    monthly_social_insurance: member.monthly_social_insurance,
    monthly_housing_fund: member.monthly_housing_fund,
    housing_fund_personal_rate: member.housing_fund_personal_rate,
    housing_fund_employer_rate: member.housing_fund_employer_rate,
    monthly_special_additional_deduction: member.monthly_special_additional_deduction,
    other_annual_deductions: member.other_annual_deductions,
    other_annual_taxable_income: member.other_annual_taxable_income,
    bonus_tax_method: member.bonus_tax_method,
    payroll_contributions_enabled: true
  };
}

function incomeStagesForMember(member: IncomeMember) {
  const stages = member.income_stages ?? [];
  return stages.map((stage) => ({
    ...stage,
    stage_kind: stage.stage_kind ?? "salary",
    provident_account_management_center: stage.provident_account_management_center ?? "beijing_municipal",
    annual_bonus_months: stage.annual_bonus_months ?? 0,
    annual_bonus_payout_month: stage.annual_bonus_payout_month ?? 4,
    annual_bonus_payout_mode: stage.annual_bonus_payout_mode ?? "lump_sum",
    annual_bonus_earning_start_month: stage.annual_bonus_earning_start_month ?? null,
    annual_bonus_earning_end_month: stage.annual_bonus_earning_end_month ?? null,
    monthly_freelance_income: stage.monthly_freelance_income ?? 0,
    freelance_tax_mode: stage.freelance_tax_mode ?? "labor_remuneration",
    monthly_non_taxable_income: stage.monthly_non_taxable_income ?? 0,
    monthly_extra_cash_expense: 0,
    payroll_contributions_enabled: stage.payroll_contributions_enabled ?? true
  }));
}

function defaultIncomeStageFromMember(member: IncomeMember): IncomeStageData {
  return incomeStageFromMember(member);
}

function incomeStageAt(member: IncomeMember, baseDate: Date, monthsFromNow = 0) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const stages = incomeStagesForMember(member);
  return (
    stages.find((stage) => {
      const start = parseMonthValue(stage.start_date.slice(0, 7));
      const end = parseMonthValue(stage.end_date?.slice(0, 7));
      if (!start || compareMonth(targetMonth, start) < 0) return false;
      if (end && compareMonth(targetMonth, end) > 0) return false;
      return true;
    }) ?? stages[0]
  );
}

const investmentPlanOptions = [
  { value: "manual_investment", label: "手动指定" },
  { value: "cash_only", label: "只放现金" },
  { value: "conservative_monthly_investment", label: "稳健理财" },
  { value: "balanced_monthly_investment", label: "均衡投资" },
  { value: "growth_monthly_investment", label: "进取定投" }
] as const;

const investmentRiskLabels: Record<string, string> = {
  cash: "现金保守",
  conservative: "稳健",
  balanced: "均衡",
  growth: "进取"
};

const investmentPlanRecommendationAliases: Record<string, string> = {
  conservative_monthly_investment: "cash_reserve_first"
};

function recommendedPurchasePlan(plans: PurchasePlanAnalysis[]) {
  return plans.find((plan) => plan.is_recommended) ?? plans[0] ?? null;
}

function purchaseRecommendationByVariant(plans: PurchasePlanAnalysis[]) {
  return new Map(plans.map((plan) => [plan.variant, plan]));
}

function userFacingError(action: string, err: unknown) {
  const message = err instanceof Error ? err.message : String(err || "");
  if (message === "Failed to fetch" || message.includes("NetworkError") || message.includes("fetch")) {
    return `${action}失败：无法连接本地后端服务。请确认后端已启动，并检查 VITE_API_BASE 是否指向正确端口。`;
  }
  if (message.startsWith("{") || message.startsWith("<")) {
    return `${action}失败：后端返回了无法直接展示的错误，请查看后端日志定位具体原因。`;
  }
  return `${action}失败：${message || "未知错误"}`;
}

function PlanningFoundationStrip({
  sequence,
  contextGoals,
  contextCoreObjects,
  planningGoals,
  accountConcepts,
  coreObjectGroups,
  cacheLayers,
  coreObjects,
  generatedStrategies,
  marketSnapshot,
  selectedHomeGoalId,
  selectedPurchasePlan
}: {
  sequence: PlanningSequenceResult | null;
  contextGoals?: CalculationContextGoalSnapshot[];
  contextCoreObjects?: CalculationContextCoreObjectSnapshot[];
  planningGoals?: PlanningGoalRecord[];
  accountConcepts?: AccountConceptSummary[];
  coreObjectGroups?: CoreObjectGroupSummary[];
  cacheLayers?: CacheLayerHashes | null;
  coreObjects: CoreObjectRecord[];
  generatedStrategies?: GeneratedStrategyRecord[];
  marketSnapshot?: RecordEnvelope<MarketSnapshotData> | null;
  selectedHomeGoalId?: string;
  selectedPurchasePlan?: PurchasePlanAnalysis | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const contextGoalItems = contextGoals?.map((goal) => ({
    id: goal.id,
    goal_type: goal.goal_type,
    name: goal.name,
    sequence_index: goal.sequence_index,
    normalized_timing_mode: goal.normalized_timing_mode,
    depends_on_goal_name: goal.depends_on_goal_name,
    resolved_not_before_month: goal.resolved_not_before_month,
    explanation: goal.explanation,
    planning_group_id: goal.planning_group_id,
    planning_group_name: goal.planning_group_name,
    planning_group_size: goal.planning_group_size,
    planning_group_member_ids: goal.planning_group_member_ids,
    source: "calculation" as const
  })) ?? [];
  const planningGoalItems = planningGoals?.map((goal, index) => ({
    id: goal.id,
    goal_type: goal.goal_type,
    name: goal.data.name,
    sequence_index: index + 1,
    normalized_timing_mode: goal.data.timing_mode,
    depends_on_goal_name: "",
    resolved_not_before_month: 0,
    explanation: goal.data.notes,
    planning_group_id: goal.goal_type === "home" ? `home:${Math.max(1, goal.data.priority)}` : goal.id,
    planning_group_name: goal.goal_type === "home" ? (goal.data.priority === 1 ? "第一套购房需求" : `第 ${goal.data.priority} 套购房需求`) : goal.data.name,
    planning_group_size: 1,
    planning_group_member_ids: [goal.id],
    source: "record" as const
  })) ?? [];
  const sequenceGoalItems = sequence?.goals.map((goal) => ({
    id: goal.id,
    goal_type: goal.goal_type,
    name: goal.name,
    sequence_index: goal.sequence_index,
    normalized_timing_mode: goal.normalized_timing_mode,
    depends_on_goal_name: goal.depends_on_goal_name,
    resolved_not_before_month: goal.resolved_not_before_month,
    explanation: goal.explanation,
    planning_group_id: goal.planning_group_id,
    planning_group_name: goal.planning_group_name,
    planning_group_size: goal.planning_group_size,
    planning_group_member_ids: goal.planning_group_member_ids,
    source: "library" as const
  })) ?? [];
  const goalSource = contextGoalItems.length ? "calculation" : sequenceGoalItems.length ? "library" : "record";
  const rawGoals = contextGoalItems.length ? contextGoalItems : sequenceGoalItems.length ? sequenceGoalItems : planningGoalItems;
  const visibleGoals = rawGoals.filter((goal) => goal.goal_type !== "home" || goal.id === selectedHomeGoalId);
  const groupedGoals = Array.from(visibleGoals.reduce((groups, goal) => {
    const key = goal.goal_type === "home" ? goal.planning_group_id : goal.id;
    groups.set(key, [...(groups.get(key) ?? []), goal]);
    return groups;
  }, new Map<string, Array<(typeof rawGoals)[number]>>()), ([key, members]) => {
    const representative = members[0];
    return {
      ...representative,
      id: key,
      name: representative.goal_type === "home" ? `${representative.planning_group_name} · ${representative.name}` : representative.name,
      planning_group_size: representative.goal_type === "home" ? 1 : Math.max(representative.planning_group_size, members.length),
      planning_group_member_ids: representative.goal_type === "home"
        ? [representative.id]
        : Array.from(new Set(members.flatMap((item) => item.planning_group_member_ids.length ? item.planning_group_member_ids : [item.id]))),
      candidate_names: []
    };
  });
  const goals = groupedGoals.slice(0, 6);
  const contextObjectItems = contextCoreObjects ?? [];
  const coreItems = contextObjectItems.length ? contextObjectItems : coreObjects;
  const groupByCode = coreObjectGroupMap(coreObjectGroups ?? []);
  const liquidGroup = groupByCode.get(CORE_OBJECT_GROUP_CODES.liquidAssets);
  const fixedAssetGroup = groupByCode.get(CORE_OBJECT_GROUP_CODES.fixedAssets);
  const loanGroup = groupByCode.get(CORE_OBJECT_GROUP_CODES.loanAccounts);
  const restrictedGroup = groupByCode.get(CORE_OBJECT_GROUP_CODES.restrictedAccounts);
  const foundationGroupCount = (group: CoreObjectGroupSummary | undefined) =>
    coreObjectCountText(group);
  const foundationGroupBalance = (group: CoreObjectGroupSummary | undefined) =>
    coreObjectBalanceText(group, "后端分组生成后显示");
  if (!goals.length && !coreItems.length && !(accountConcepts?.length) && !(coreObjectGroups?.length)) return null;
  const shortHash = (value?: string) => value ? value.slice(0, 7) : "";
  const cacheLayerLabel = cacheLayers?.input
    ? `输入 ${shortHash(cacheLayers.input)} · 策略 ${shortHash(cacheLayers.strategy)} · 账本 ${shortHash(cacheLayers.ledger)} · 展示 ${shortHash(cacheLayers.visualization)}`
    : "";
  const generatedStrategySummary = generatedStrategyTypeSummary(generatedStrategies ?? []);
  const generatedStrategySummaryByGoal = generatedStrategySummaryByOwner(generatedStrategies ?? []);
  const generatedStrategySummaryForGoal = (goalIds: string[]) => goalIds
    .map((goalId) => generatedStrategySummaryByGoal.get(goalId) ?? "")
    .filter(Boolean)
    .join(" · ");
  const coreObjectSummaryByGoal = coreObjectOwnerSummaryByOwner(coreItems);
  const coreObjectSummaryForGoal = (goalIds: string[]) => goalIds
    .map((goalId) => coreObjectOwnerSummaryText(coreObjectSummaryByGoal.get(goalId)))
    .filter(Boolean)
    .join(" · ");
  return (
    <section className={expanded ? "planning-foundation-strip expanded" : "planning-foundation-strip"}>
      <div className="planning-foundation-bar">
        <button
          className="planning-foundation-toggle"
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          <Target size={17} />
          <span>
            <strong>规划底座</strong>
            <small>{sequence?.warnings.length ? `${sequence.warnings.length} 个顺序提示` : goalSource === "calculation" ? "当前计算上下文" : "统一目标与账户索引"}</small>
          </span>
        </button>
        <div className="foundation-summary-list">
          <article className="foundation-summary-card">
            <small>流动资产</small>
            <strong>{foundationGroupCount(liquidGroup)}</strong>
            <span>{foundationGroupBalance(liquidGroup)}</span>
          </article>
          <article className="foundation-summary-card restricted">
            <small>受限账户</small>
            <strong>{foundationGroupCount(restrictedGroup)}</strong>
            <span>{foundationGroupBalance(restrictedGroup)}</span>
          </article>
          <article className="foundation-summary-card asset">
            <small>目标/资产</small>
            <strong>{foundationGroupCount(fixedAssetGroup)}</strong>
            <span>{foundationGroupBalance(fixedAssetGroup)}</span>
          </article>
          <article className="foundation-summary-card loan">
            <small>贷款</small>
            <strong>{foundationGroupCount(loanGroup)}</strong>
            <span>{foundationGroupBalance(loanGroup)}</span>
          </article>
          <article className="foundation-summary-card market">
            <small>市场假设</small>
            <strong>{marketSnapshot?.data.region ?? "未选择"}</strong>
            <span>
              {marketSnapshot
                ? `商贷 ${marketSnapshot.data.commercial_loan_rate !== null ? percent(marketSnapshot.data.commercial_loan_rate) : "按房源"} · 中介 ${marketSnapshot.data.default_broker_fee_rate !== null ? percent(marketSnapshot.data.default_broker_fee_rate) : "按规则"} · 转嫁 ${marketSnapshot.data.seller_tax_pass_through_rate !== null ? percent(marketSnapshot.data.seller_tax_pass_through_rate) : "按规则"}`
                : "未纳入本次输入"}
            </span>
          </article>
        </div>
        <button
          className="foundation-expand-button"
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-label={expanded ? "收起规划底座详情" : "展开规划底座详情"}
          title={expanded ? "收起详情" : "展开详情"}
        >
          {expanded ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
        </button>
      </div>
      {expanded ? (
        <div className="planning-foundation-content">
          <div className="planning-foundation-meta">
            {cacheLayerLabel ? <span className="cache-layer-label">{cacheLayerLabel}</span> : null}
            {generatedStrategySummary ? <span className="cache-layer-label">策略实体 {generatedStrategySummary}</span> : null}
          </div>
        {goals.length ? (
          <div className="goal-sequence-list">
            {goals.map((goal) => (
              <article key={goal.id} className={`goal-sequence-card${planningGoalIsNotPlanned(goal) ? " muted" : ""}`}>
                <small>{planningGoalTypeLabel(goal.goal_type)} · {planningGoalOrderLabel(goal)}</small>
                <strong>{goal.name}</strong>
                {goal.goal_type === "home" && selectedPurchasePlan ? (
                  <span>
                    当前采用 {selectedPurchasePlan.variant} · 预计买入价 {money(selectedPurchasePlan.projected_purchase_price || selectedPurchasePlan.original_target_price)}
                  </span>
                ) : null}
                <span>{planningGoalTimingSummary(goal)}</span>
                {goal.source === "calculation" ? <em>{planningGoalIsNotPlanned(goal) ? "上下文可见" : "已进入本次计算"}</em> : null}
                {!planningGoalIsNotPlanned(goal) && generatedStrategySummaryForGoal(goal.planning_group_member_ids) ? (
                  <em className="strategy-entity-pill">{generatedStrategySummaryForGoal(goal.planning_group_member_ids)}</em>
                ) : null}
                {!planningGoalIsNotPlanned(goal) && coreObjectSummaryForGoal(goal.planning_group_member_ids) ? (
                  <em className="core-object-pill">{coreObjectSummaryForGoal(goal.planning_group_member_ids)}</em>
                ) : null}
              </article>
            ))}
          </div>
        ) : null}
        </div>
      ) : null}
    </section>
  );
}


export function App() {
  const [households, setHouseholds] = useState<RecordEnvelope<HouseholdData>[]>([]);
  const [scenarios, setScenarios] = useState<RecordEnvelope<ScenarioData>[]>([]);
  const [rulePacks, setRulePacks] = useState<RecordEnvelope<RulePackData>[]>([]);
  const [marketSnapshots, setMarketSnapshots] = useState<RecordEnvelope<MarketSnapshotData>[]>([]);
  const [personalPensionReturnSnapshot, setPersonalPensionReturnSnapshot] = useState<PersonalPensionReturnSnapshotRecord | null>(null);
  const [refreshingPersonalPensionReturns, setRefreshingPersonalPensionReturns] = useState(false);
  const [planningGoals, setPlanningGoals] = useState<PlanningGoalRecord[]>([]);
  const [planningSequence, setPlanningSequence] = useState<PlanningSequenceResult | null>(null);
  const [coreObjects, setCoreObjects] = useState<CoreObjectRecord[]>([]);
  const [accountConcepts, setAccountConcepts] = useState<AccountConceptSummary[]>([]);
  const [coreObjectGroups, setCoreObjectGroups] = useState<CoreObjectGroupSummary[]>([]);
  const [generatedStrategies, setGeneratedStrategies] = useState<GeneratedStrategyRecord[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(noPurchaseScenarioId);
  const [scenarioResults, setScenarioResults] = useState<Record<string, AffordabilityResult>>({});
  const [selectedPlanVariants, setSelectedPlanVariants] = useState<Record<string, string>>({});
  const [activePage, setActivePage] = useState<PageName>("家庭财务");
  const [visualizationTimelineState, setVisualizationTimelineState] = useState<VisualizationTimelineState>(
    DEFAULT_VISUALIZATION_TIMELINE_STATE
  );
  const [sourceUrl, setSourceUrl] = useState(sourceDefaults[0]);
  const [sourcePreview, setSourcePreview] = useState<SourceDocumentRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [calculationVersion, setCalculationVersion] = useState(0);
  const [calculatedVersion, setCalculatedVersion] = useState(-1);
  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "light";
    const stored = window.localStorage.getItem("planner-theme");
    if (stored === "dark" || stored === "light") return stored;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const calculationSeqRef = useRef(0);
  const dirtyVersionRef = useRef(0);
  const updateVisualizationTimelineState = useCallback((patch: Partial<VisualizationTimelineState>) => {
    setVisualizationTimelineState((current) => ({ ...current, ...patch }));
  }, []);

  const household = households[0];
  const selectedScenario = scenarios.find((item) => item.id === selectedScenarioId) ?? scenarios[0] ?? noPurchaseScenario;
  const activeRulePack = rulePacks.find((item) => item.data.status === "active") ?? rulePacks[0];
  const activeMarketSnapshot = marketSnapshots.at(-1) ?? null;
  const hasCurrentCalculation = calculatedVersion === calculationVersion && !isCalculating;
  const calculationPending = !hasCurrentCalculation;
  const displayScenarioResults = useMemo<Record<string, AffordabilityResult>>(() => {
    return Object.fromEntries(Object.entries(scenarioResults).map(([scenarioId, scenarioResult]) => {
      const scenario = scenarios.find((item) => item.id === scenarioId);
      const purchasePlans = generatedPurchasePlanAnalyses(generatedStrategies, scenario);
      return [
        scenarioId,
        purchasePlans.length
          ? { ...scenarioResult, purchase_plan_analyses: purchasePlans }
          : scenarioResult
      ];
    }));
  }, [generatedStrategies, scenarioResults, scenarios]);
  const result = selectedScenario ? displayScenarioResults[selectedScenario.id] ?? null : null;
  const selectedScenarioPurchasePlansFromEntities = selectedScenario
    ? generatedPurchasePlanAnalyses(generatedStrategies, selectedScenario)
    : [];
  const purchasePlanSourceLabel = selectedScenarioPurchasePlansFromEntities.length ? "策略库方案" : "本次计算结果";
  const planningContextGoals = result?.calculation_context?.planning_goals ?? [];
  const planningContextCoreObjects = result?.calculation_context?.core_objects ?? [];
  const incomeMembers = household?.data.members ?? [];
  const carPlan = household?.data.car_plan ?? defaultCarPlan;
  const vehiclePlans = carPlan.vehicle_plans ?? [];
  const carStrategiesFromEntities = useMemo(
    () => generatedCarPlanAnalyses(generatedStrategies, vehiclePlans, result?.cache_layers),
    [generatedStrategies, result?.cache_layers, vehiclePlans]
  );
  const carStrategiesForPage = carStrategiesFromEntities.length
    ? carStrategiesFromEntities
    : result?.car_plan_analyses ?? [];
  const carStrategySourceLabel = carStrategiesFromEntities.length ? "策略库方案" : "本次计算结果";
  const phasedLoans = household?.data.phased_loans ?? [];
  const scheduledExpenses = household?.data.scheduled_expenses ?? [];
  const dailyExpenseStages = household?.data.daily_expense_stages?.length
    ? household.data.daily_expense_stages
    : [defaultDailyExpenseStage];
  const rentExpenseStages = household?.data.rent_expense_stages?.length
    ? household.data.rent_expense_stages
    : [defaultRentExpenseStage];
  const elderlyDependents = household?.data.elderly_dependents ?? [];
  const childPlans = household?.data.child_plans ?? [];
  const childPlanStrategiesFromEntities = useMemo(
    () => generatedChildPlanStrategies(generatedStrategies, childPlans, result?.cache_layers),
    [childPlans, generatedStrategies, result?.cache_layers]
  );
  const childPlanStrategiesForPage = childPlanStrategiesFromEntities.length
    ? childPlanStrategiesFromEntities
    : result?.child_plan_strategies ?? [];
  const childPlanStrategySourceLabel = childPlanStrategiesFromEntities.length ? "策略库方案" : "本次计算结果";
  const investmentRecommendationsFromEntities = useMemo(
    () => generatedInvestmentRecommendations(generatedStrategies, result?.cache_layers),
    [generatedStrategies, result?.cache_layers]
  );
  const investmentRecommendationsForPage = investmentRecommendationsFromEntities.length
    ? investmentRecommendationsFromEntities
    : result?.investment_plan_recommendations ?? [];
  const investmentRecommendationSourceLabel = investmentRecommendationsFromEntities.length ? "策略库方案" : "本次计算结果";
  const taxStrategyItemsFromEntities = useMemo(
    () => generatedTaxStrategyItems(generatedStrategies),
    [generatedStrategies]
  );
  const taxStrategyTimelineFromEntities = useMemo(
    () => generatedTaxStrategyTimeline(generatedStrategies),
    [generatedStrategies]
  );
  const taxStrategyItemsForPage = taxStrategyItemsFromEntities.length
    ? taxStrategyItemsFromEntities
    : result?.tax_strategy_items ?? [];
  const taxStrategyTimelineForPage = taxStrategyTimelineFromEntities.length
    ? taxStrategyTimelineFromEntities
    : result?.tax_strategy_timeline ?? [];
  const taxStrategySourceLabel =
    taxStrategyTimelineFromEntities.length || taxStrategyItemsFromEntities.length
      ? "策略库方案"
      : "本次计算结果";
  const firstHomeGoalId = useMemo(() => planningGoals.find((goal) => goal.goal_type === "home")?.id ?? "", [planningGoals]);
  const specialDeductions = household?.data.special_deductions ?? [];
  const selectedPlanVariant = selectedScenario
    ? selectedScenario.data.selected_purchase_plan_variant || selectedPlanVariants[selectedScenario.id] || ""
    : "";
  const selectedScenarioPurchasePlans = selectedScenarioPurchasePlansFromEntities.length
    ? selectedScenarioPurchasePlansFromEntities
    : result?.purchase_plan_analyses ?? [];
  const selectedScenarioHomePurchasePlans = selectedScenarioPurchasePlans.filter((plan) => plan.source !== "baseline");
  const visualizationPlans = selectedScenarioHomePurchasePlans.length ? selectedScenarioHomePurchasePlans : selectedScenarioPurchasePlans;
  const currentRecommendation = useMemo(
    () => recommendedPurchasePlan(selectedScenarioHomePurchasePlans),
    [selectedScenarioHomePurchasePlans]
  );
  const selectedPlan =
    selectedScenarioPurchasePlans.find((plan) => plan.variant === selectedPlanVariant) ??
    currentRecommendation ??
    selectedScenarioPurchasePlans[0] ??
    null;
  const scenarioComparisons = useMemo<ScenarioComparison[]>(
    () => scenarios
      .filter((scenario) => scenario.data.enabled)
      .map((scenario): ScenarioComparison | null => {
        const scenarioResult = displayScenarioResults[scenario.id];
        if (!scenarioResult) return null;
        const homePurchasePlans = scenarioResult.purchase_plan_analyses.filter((plan) => plan.source !== "baseline");
        const recommendation = recommendedPurchasePlan(homePurchasePlans);
        const selectedVariant = scenario.data.selected_purchase_plan_variant || selectedPlanVariants[scenario.id];
        const selectedPlan =
          homePurchasePlans.find((plan) => plan.variant === selectedVariant) ??
          recommendation ??
          homePurchasePlans[0] ??
          null;
        return { scenario, result: scenarioResult, recommendation, selectedPlan };
      })
      .filter((item): item is ScenarioComparison => item !== null),
    [displayScenarioResults, scenarios, selectedPlanVariants]
  );
  const propertyMonitorPurchasePlans = useMemo(
    () => Object.values(displayScenarioResults).flatMap((scenarioResult) => scenarioResult.purchase_plan_analyses),
    [displayScenarioResults]
  );

  const markDirty = (affectsCalculation = true) => {
    dirtyVersionRef.current += 1;
    setSaveState("dirty");
    if (affectsCalculation) {
      setCalculationVersion((version) => version + 1);
    }
  };

  const updateHousehold = <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => {
    markDirty(key !== "name");
    setHouseholds((items) => items.map((item, index) => index === 0 ? { ...item, data: { ...item.data, [key]: value } } : item));
  };
  const updateHouseholdPatch = (patch: Partial<HouseholdData>) => {
    markDirty(!Object.keys(patch).every((key) => key === "name"));
    setHouseholds((items) => items.map((item, index) => index === 0 ? { ...item, data: { ...item.data, ...patch } } : item));
  };
  const applyPlanningFoundation = useCallback((foundation: Awaited<ReturnType<typeof fetchPlanningFoundation>>) => {
    setPlanningGoals(foundation.planning_goals);
    setPlanningSequence(foundation.planning_sequence);
    setCoreObjects(foundation.core_objects);
    setAccountConcepts(foundation.account_concepts);
    setCoreObjectGroups(foundation.core_object_groups);
  }, []);
  const refreshPlanningFoundation = useCallback(async (householdId: string, options: { clearGeneratedStrategies?: boolean } = {}) => {
    const [householdRecords, foundation] = await Promise.all([
      fetchHouseholds(),
      fetchPlanningFoundation(householdId)
    ]);
    setHouseholds(householdRecords.map(completeHouseholdDefaults));
    applyPlanningFoundation(foundation);
    if (options.clearGeneratedStrategies) setGeneratedStrategies([]);
    setCalculationVersion((version) => version + 1);
  }, [applyPlanningFoundation]);
  const refreshScenariosAndPlanningFoundation = useCallback(async (householdId: string, options: { clearGeneratedStrategies?: boolean } = {}) => {
    const [homeGoals] = await Promise.all([
      fetchPlanningGoals(householdId, "home"),
      refreshPlanningFoundation(householdId, options)
    ]);
    setScenarios(homeGoals.map(scenarioRecordFromHomeGoal));
  }, [refreshPlanningFoundation]);
  const saveHomePlanningGoal = useCallback(async (goalId: string, goalData: PlanningGoalData) => {
    await savePlanningGoal(goalId, goalData, household?.id ?? null);
  }, [household?.id]);
  const refreshHomePlanningGoal = useCallback(() => {
    if (household?.id) void refreshScenariosAndPlanningFoundation(household.id);
  }, [household?.id, refreshScenariosAndPlanningFoundation]);
  const scheduleHomeGoalSave = useDebouncedPlanningGoalSave<ScenarioData>({
    buildGoalData: homePlanningGoalData,
    saveGoal: saveHomePlanningGoal,
    onSaved: refreshHomePlanningGoal,
    onError: (err) => setError(userFacingError("保存购房目标", err)),
    ignoreGoalIds: new Set([noPurchaseScenarioId])
  });
  const saveChildPlanningGoal = useCallback(async (goalId: string, goalData: PlanningGoalData) => {
    await savePlanningGoal(goalId, goalData, household?.id ?? null);
  }, [household?.id]);
  const refreshChildPlanningGoal = useCallback(() => {
    if (household?.id) void refreshPlanningFoundation(household.id);
  }, [household?.id, refreshPlanningFoundation]);
  const scheduleChildGoalSave = useDebouncedPlanningGoalSave<{ child: ChildPlanData; index: number }>({
    buildGoalData: ({ child, index }) => childPlanningGoalData(child, index, firstHomeGoalId),
    saveGoal: saveChildPlanningGoal,
    onSaved: refreshChildPlanningGoal,
    onError: (err) => setError(userFacingError("保存子女目标", err))
  });
  const updateScenarioRecord = (id: string, patch: Partial<ScenarioData>) => {
    if (id === noPurchaseScenarioId) return;
    markDirty(!Object.keys(patch).every((key) => ["selected_purchase_plan_variant", "name", "district", "ring_area"].includes(key) || key.startsWith("valuation_")));
    setScenarios((items) => items.map((item) => {
      if (item.id !== id) return item;
      const nextScenario = { ...item.data, ...patch };
      scheduleHomeGoalSave(nextScenario.planning_goal_id || id, nextScenario);
      return { ...item, data: nextScenario };
    }));
  };
  const updateScenario = <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => {
    if (!selectedScenario || selectedScenario.id === noPurchaseScenarioId) return;
    updateScenarioRecord(selectedScenario.id, { [key]: value } as Partial<ScenarioData>);
  };
  const updateInvestmentAnnualReturn = (annualReturn: number) => {
    markDirty(true);
    setScenarios((items) => items.map((item) => ({
      ...item,
      data: { ...item.data, annual_investment_return: annualReturn }
    })));
  };
  const updateRulePack = <K extends keyof RulePackData>(key: K, value: RulePackData[K]) => {
    if (!activeRulePack) return;
    markDirty(true);
    setRulePacks((items) => items.map((item) => item.id === activeRulePack.id ? { ...item, data: { ...item.data, [key]: value } } : item));
  };
  const updateRuleParam = (key: string, value: number | string | boolean) => {
    if (!activeRulePack) return;
    markDirty(true);
    setRulePacks((items) => items.map((item) => item.id === activeRulePack.id ? { ...item, data: { ...item.data, params: { ...item.data.params, [key]: value } } } : item));
  };
  const ruleNumber = (key: string, fallback: number) => {
    const value = Number(activeRulePack?.data.params[key]);
    return Number.isFinite(value) ? value : fallback;
  };

  const updateIncomeMember = <K extends keyof IncomeMember>(index: number, key: K, value: IncomeMember[K]) => {
    if (!household) return;
    const memberPatch: Partial<IncomeMember> = {};
    if (key === "birth_month") {
      const age = ageYearsFromBirthMonth(String(value), new Date());
      if (age !== null) memberPatch.current_age = age;
    }
    if (key === "current_age") memberPatch.birth_month = birthMonthFromAge(Number(value), new Date());
    if (key === "sex") {
      memberPatch.retirement_category = normalizeRetirementCategoryForSex(
        incomeMembers[index]?.retirement_category,
        value as IncomeMember["sex"],
        index
      );
    }
    if (key === "personal_pension_account_enabled") {
      memberPatch.personal_pension_open_mode = value ? "auto_tax_optimal" : "none";
      memberPatch.personal_pension_contribution_mode = value && incomeMembers[index]?.personal_pension_participation_eligible ? "auto_tax_optimal" : "none";
    }
    if (key === "personal_pension_participation_eligible" && !value) {
      memberPatch.personal_pension_contribution_mode = "none";
    }
    if (key === "pension_account_enabled" && !value) {
      memberPatch.personal_pension_participation_eligible = false;
      memberPatch.personal_pension_contribution_mode = "none";
    }
    if (key === "personal_pension_contribution_mode" && value !== "none") {
      memberPatch.personal_pension_account_enabled = true;
    }
    const nextMembers = incomeMembers.map((member, memberIndex) => memberIndex === index ? { ...member, [key]: value, ...memberPatch } : member);
    updateHousehold("members", nextMembers);
    if (key === "name" || key === "sex" || key === "birth_month" || key === "current_age" || key === "retirement_category") {
      updateHousehold("career_shock", normalizeCareerShockForMembers(household.data.career_shock, nextMembers));
    }
  };
  const addIncomeMember = () => {
    if (!household) return;
    const defaultSex: IncomeMember["sex"] = "unspecified";
    const nextMember: IncomeMember = {
      name: `成员 ${incomeMembers.length + 1}`,
      sex: defaultSex,
      family_join_month: "2026-07",
      birth_month: "",
      current_age: 30,
      retirement_category: defaultRetirementCategoryForSex(defaultSex, incomeMembers.length),
      social_security_months: 0,
      income_tax_months: 0,
      existing_home_count: 0,
      existing_mortgage_count: 0,
      initial_cash_balance: 0,
      initial_investments: 0,
      initial_other_asset_value: 0,
      initial_other_debt_balance: 0,
      provident_fund_balance: 0,
      provident_account_enabled: true,
      provident_account_open_month: "2026-07",
      pension_account_balance: 0,
      pension_account_enabled: true,
      pension_account_open_month: "2026-07",
      medical_account_balance: 0,
      medical_account_enabled: true,
      medical_account_open_month: "2026-07",
      personal_pension_account_enabled: false,
      personal_pension_participation_eligible: false,
      personal_pension_account_balance: 0,
      personal_pension_open_mode: "none",
      personal_pension_account_open_month: "",
      personal_pension_contribution_mode: "none",
      personal_pension_tax_deduction_mode: "monthly_withholding",
      personal_pension_monthly_contribution: 0,
      personal_pension_annual_contribution_target: 0,
      personal_pension_contribution_month: 12,
      personal_pension_contribution_start_month: "",
      personal_pension_contribution_end_month: null,
      personal_pension_auto_suspend_for_cash_safety: true,
      personal_pension_cash_reserve_months: 6,
      personal_pension_return_mode: "auto_lifecycle",
      personal_pension_annual_return: 0.025,
      personal_pension_post_retirement_annual_return: 0.015,
      personal_pension_withdrawal_mode: "auto_safe",
      personal_pension_withdrawal_start_month: "",
      personal_pension_early_withdrawal_reason: "none",
      personal_pension_early_withdrawal_month: "",
      personal_pension_withdrawal_years: 20,
      personal_pension_fixed_monthly_withdrawal: 0,
      personal_pension_product_liquidity_mode: "daily_liquid",
      personal_pension_redemption_delay_months: 0,
      personal_pension_monthly_redeemable_ratio: 1,
      personal_pension_redemption_fee_rate: 0,
      monthly_salary_gross: 0,
      annual_bonus: 0,
      monthly_social_insurance: 0,
      monthly_housing_fund: 0,
      housing_fund_personal_rate: 0.12,
      housing_fund_employer_rate: 0.12,
      monthly_special_additional_deduction: 0,
      other_annual_deductions: 0,
      other_annual_taxable_income: 0,
      employment_start_date: "2027-01-01",
      bonus_tax_method: "best",
      income_stages: [incomeStageFromMember({
        name: `成员 ${incomeMembers.length + 1}`,
        sex: defaultSex,
        family_join_month: "2026-07",
        birth_month: "",
        current_age: 30,
        retirement_category: defaultRetirementCategoryForSex(defaultSex, incomeMembers.length),
        social_security_months: 0,
        income_tax_months: 0,
        existing_home_count: 0,
        existing_mortgage_count: 0,
        initial_cash_balance: 0,
        initial_investments: 0,
        initial_other_asset_value: 0,
        initial_other_debt_balance: 0,
        provident_fund_balance: 0,
        provident_account_enabled: true,
        provident_account_open_month: "2026-07",
        pension_account_balance: 0,
        pension_account_enabled: true,
        pension_account_open_month: "2026-07",
        medical_account_balance: 0,
        medical_account_enabled: true,
        medical_account_open_month: "2026-07",
        personal_pension_account_enabled: false,
        personal_pension_participation_eligible: false,
        personal_pension_account_balance: 0,
        personal_pension_open_mode: "none",
        personal_pension_account_open_month: "",
        personal_pension_contribution_mode: "none",
        personal_pension_tax_deduction_mode: "monthly_withholding",
        personal_pension_monthly_contribution: 0,
        personal_pension_annual_contribution_target: 0,
        personal_pension_contribution_month: 12,
        personal_pension_contribution_start_month: "",
        personal_pension_contribution_end_month: null,
        personal_pension_auto_suspend_for_cash_safety: true,
        personal_pension_cash_reserve_months: 6,
        personal_pension_return_mode: "auto_lifecycle",
        personal_pension_annual_return: 0.025,
        personal_pension_post_retirement_annual_return: 0.015,
        personal_pension_withdrawal_mode: "auto_safe",
        personal_pension_withdrawal_start_month: "",
        personal_pension_early_withdrawal_reason: "none",
        personal_pension_early_withdrawal_month: "",
        personal_pension_withdrawal_years: 20,
        personal_pension_fixed_monthly_withdrawal: 0,
        personal_pension_product_liquidity_mode: "daily_liquid",
        personal_pension_redemption_delay_months: 0,
        personal_pension_monthly_redeemable_ratio: 1,
        personal_pension_redemption_fee_rate: 0,
        monthly_salary_gross: 0,
        annual_bonus: 0,
        monthly_social_insurance: 0,
        monthly_housing_fund: 0,
        housing_fund_personal_rate: 0.12,
        housing_fund_employer_rate: 0.12,
        monthly_special_additional_deduction: 0,
        other_annual_deductions: 0,
        other_annual_taxable_income: 0,
        employment_start_date: "2027-01-01",
        bonus_tax_method: "best",
        income_stages: []
      })]
    };
    const nextMembers = [...incomeMembers, nextMember];
    updateHousehold("members", nextMembers);
    updateHousehold("career_shock", normalizeCareerShockForMembers(household.data.career_shock, nextMembers));
  };
  const removeIncomeMember = (index: number) => {
    if (!household || incomeMembers.length <= 1) return;
    const nextMembers = incomeMembers.filter((_, memberIndex) => memberIndex !== index);
    updateHousehold("members", nextMembers);
    updateHousehold("career_shock", normalizeCareerShockForMembers(household.data.career_shock, nextMembers));
  };
  const updateIncomeStage = <K extends keyof IncomeStageData>(memberIndex: number, stageIndex: number, key: K, value: IncomeStageData[K]) => {
    const nextMembers = incomeMembers.map((member, currentMemberIndex) => {
      if (currentMemberIndex !== memberIndex) return member;
      const stages = incomeStagesForMember(member).map((stage, currentStageIndex) => currentStageIndex === stageIndex ? { ...stage, [key]: value } : stage);
      const firstStage = stages[0];
      return stageIndex === 0 ? {
        ...member,
        income_stages: stages,
        monthly_salary_gross: firstStage.monthly_salary_gross,
        annual_bonus: firstStage.monthly_salary_gross * firstStage.annual_bonus_months,
        annual_bonus_payout_mode: firstStage.annual_bonus_payout_mode,
        monthly_social_insurance: firstStage.monthly_social_insurance,
        monthly_housing_fund: firstStage.monthly_housing_fund,
        housing_fund_personal_rate: firstStage.housing_fund_personal_rate,
        housing_fund_employer_rate: firstStage.housing_fund_employer_rate,
        monthly_special_additional_deduction: firstStage.monthly_special_additional_deduction,
        other_annual_deductions: firstStage.other_annual_deductions,
        other_annual_taxable_income: firstStage.other_annual_taxable_income,
        employment_start_date: firstStage.start_date,
        bonus_tax_method: firstStage.bonus_tax_method
      } : { ...member, income_stages: stages };
    });
    updateHousehold("members", nextMembers);
  };
  const updateIncomeStagePatch = (memberIndex: number, stageIndex: number, patch: Partial<IncomeStageData>) => {
    const nextMembers = incomeMembers.map((member, currentMemberIndex) => {
      if (currentMemberIndex !== memberIndex) return member;
      const stages = incomeStagesForMember(member).map((stage, currentStageIndex) => currentStageIndex === stageIndex ? { ...stage, ...patch } : stage);
      const firstStage = stages[0];
      return stageIndex === 0 ? {
        ...member,
        income_stages: stages,
        monthly_salary_gross: firstStage.monthly_salary_gross,
        annual_bonus: firstStage.monthly_salary_gross * firstStage.annual_bonus_months,
        annual_bonus_payout_mode: firstStage.annual_bonus_payout_mode,
        monthly_social_insurance: firstStage.monthly_social_insurance,
        monthly_housing_fund: firstStage.monthly_housing_fund,
        housing_fund_personal_rate: firstStage.housing_fund_personal_rate,
        housing_fund_employer_rate: firstStage.housing_fund_employer_rate,
        monthly_special_additional_deduction: firstStage.monthly_special_additional_deduction,
        other_annual_deductions: firstStage.other_annual_deductions,
        other_annual_taxable_income: firstStage.other_annual_taxable_income,
        employment_start_date: firstStage.start_date,
        bonus_tax_method: firstStage.bonus_tax_method
      } : { ...member, income_stages: stages };
    });
    updateHousehold("members", nextMembers);
  };
  const addIncomeStage = (memberIndex: number) => {
    const nextMembers = incomeMembers.map((member, index) => {
      if (index !== memberIndex) return member;
      const stages = incomeStagesForMember(member);
      const template = stages[stages.length - 1] ?? defaultIncomeStageFromMember(member);
      return { ...member, income_stages: [...stages, { ...template, name: `收入阶段 ${stages.length + 1}`, start_date: "2028-01-01", end_date: null }] };
    });
    updateHousehold("members", nextMembers);
  };
  const removeIncomeStage = (memberIndex: number, stageIndex: number) => {
    const nextMembers = incomeMembers.map((member, index) => index !== memberIndex ? member : { ...member, income_stages: incomeStagesForMember(member).filter((_, itemIndex) => itemIndex !== stageIndex) });
    updateHousehold("members", nextMembers);
  };

  const updateArrayItem = <T, K extends keyof T>(items: T[], index: number, key: K, value: T[K]) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item);
  const updatePhasedLoan = <K extends keyof PhasedLoanData>(index: number, key: K, value: PhasedLoanData[K]) => updateHousehold("phased_loans", updateArrayItem(phasedLoans, index, key, value));
  const addPhasedLoan = () => updateHousehold("phased_loans", [...phasedLoans, { borrower: incomeMembers[0]?.name ?? "成员 1", name: "已有贷款", loan_type: "other", principal: 0, annual_rate: 0.028, repayment_method: "equal_installment", remaining_months: 120, interest_start_month: "2026-07", interest_only_until: "2028-07", prepayment_mode: "none", prepayment_start_month: 1, prepayment_allowed_after_month: 1, prepayment_monthly_amount: 0 }]);
  const removePhasedLoan = (index: number) => updateHousehold("phased_loans", phasedLoans.filter((_, itemIndex) => itemIndex !== index));
  const updateScheduledExpense = <K extends keyof ScheduledExpenseData>(index: number, key: K, value: ScheduledExpenseData[K]) => updateHousehold("scheduled_expenses", updateArrayItem(scheduledExpenses, index, key, value));
  const addScheduledExpense = () => updateHousehold("scheduled_expenses", [...scheduledExpenses, ...defaultScheduledExpenses]);
  const addAnnualScheduledExpense = () => updateHousehold("scheduled_expenses", [...scheduledExpenses, defaultAnnualScheduledExpense]);
  const addOneTimeScheduledExpense = () => updateHousehold("scheduled_expenses", [...scheduledExpenses, defaultOneTimeScheduledExpense]);
  const removeScheduledExpense = (index: number) => updateHousehold("scheduled_expenses", scheduledExpenses.filter((_, itemIndex) => itemIndex !== index));
  const updateDailyExpenseStage = <K extends keyof DailyExpenseStageData>(index: number, key: K, value: DailyExpenseStageData[K]) => updateHousehold("daily_expense_stages", updateArrayItem(dailyExpenseStages, index, key, value));
  const addDailyExpenseStage = () => updateHousehold("daily_expense_stages", [...dailyExpenseStages, { ...defaultDailyExpenseStage, name: `日常支出阶段 ${dailyExpenseStages.length + 1}` }]);
  const removeDailyExpenseStage = (index: number) => updateHousehold("daily_expense_stages", dailyExpenseStages.filter((_, itemIndex) => itemIndex !== index));
  const updateRentExpenseStage = <K extends keyof RentExpenseStageData>(index: number, key: K, value: RentExpenseStageData[K]) => updateHousehold("rent_expense_stages", updateArrayItem(rentExpenseStages, index, key, value));
  const addRentExpenseStage = () => updateHousehold("rent_expense_stages", [...rentExpenseStages, { ...defaultRentExpenseStage, name: `租房支出阶段 ${rentExpenseStages.length + 1}` }]);
  const removeRentExpenseStage = (index: number) => updateHousehold("rent_expense_stages", rentExpenseStages.filter((_, itemIndex) => itemIndex !== index));
  const updateElderlyDependent = <K extends keyof ElderlyDependentData>(index: number, key: K, value: ElderlyDependentData[K]) => updateHousehold("elderly_dependents", updateArrayItem(elderlyDependents, index, key, value));
  const addElderlyDependent = () => updateHousehold("elderly_dependents", [...elderlyDependents, { member_name: incomeMembers[0]?.name ?? "成员 1", relationship_label: "直系亲属老人", birth_month: "", is_only_child: false, shared_monthly_deduction: 1500 }]);
  const removeElderlyDependent = (index: number) => updateHousehold("elderly_dependents", elderlyDependents.filter((_, itemIndex) => itemIndex !== index));
  const updateChildPlanPatch = (index: number, patch: Partial<ChildPlanData>) => {
    const currentChild = childPlans[index];
    if (!currentChild) return;
    const nextChild = { ...currentChild, ...patch };
    const nextChildPlans = childPlans.map((item, itemIndex) => itemIndex === index ? nextChild : item);
    updateHousehold("child_plans", nextChildPlans);
    if (nextChild?.planning_goal_id) {
      scheduleChildGoalSave(nextChild.planning_goal_id, { child: nextChild, index });
    }
  };
  const updateChildPlan = <K extends keyof ChildPlanData>(index: number, key: K, value: ChildPlanData[K]) => {
    updateChildPlanPatch(index, { [key]: value } as Partial<ChildPlanData>);
  };
  const applyChildStrategyPatch = (index: number, patch: Partial<ChildPlanData>) => {
    const currentChild = childPlans[index];
    if (!currentChild) return;
    const nextChild = { ...currentChild, ...patch };
    markDirty(false);
    setHouseholds((items) => items.map((item, householdIndex) => {
      if (householdIndex !== 0) return item;
      return {
        ...item,
        data: {
          ...item.data,
          child_plans: childPlans.map((child, childIndex) => childIndex === index ? nextChild : child)
        }
      };
    }));
    if (nextChild.planning_goal_id) {
      void savePlanningGoal(nextChild.planning_goal_id, childPlanningGoalData(nextChild, index, firstHomeGoalId), household?.id ?? null)
        .then(() => {
          setSaveState("saved");
          setCalculationVersion((version) => version + 1);
        })
        .catch((err) => setError(userFacingError("保存养娃策略", err)));
    } else {
      setCalculationVersion((version) => version + 1);
    }
  };
  const addChildPlan = async () => {
    if (!household) return;
    setSaving(true);
    setError(null);
    const child: ChildPlanData = {
      ...defaultChildPlan,
      ...childExpensePresets.balanced,
      name: `子女计划 ${childPlans.length + 1}`
    };
    try {
      await createPlanningGoal(childPlanningGoalData(child, childPlans.length, firstHomeGoalId), household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("添加子女目标", err));
    } finally {
      setSaving(false);
    }
  };
  const duplicateChildPlan = async (index: number) => {
    if (!household) return;
    const source = childPlans[index];
    if (!source) return;
    const child: ChildPlanData = {
      ...source,
      planning_goal_id: "",
      enabled: true,
      name: `${source.name || `子女目标 ${index + 1}`} 复制`
    };
    setSaving(true);
    setError(null);
    try {
      await createPlanningGoal(childPlanningGoalData(child, childPlans.length, firstHomeGoalId), household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("复制子女目标", err));
    } finally {
      setSaving(false);
    }
  };
  const removeChildPlan = async (index: number) => {
    if (!household) return;
    const child = childPlans[index];
    if (!child) return;
    const goalId = child.planning_goal_id;
    if (!goalId) {
      updateHouseholdPatch({
        child_plans: childPlans.filter((_, itemIndex) => itemIndex !== index)
      });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await deletePlanningGoal(goalId);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("删除子女目标", err));
    } finally {
      setSaving(false);
    }
  };
  const createVehiclePlanningGoal = useCallback(async (vehicle: VehiclePlanData, index: number): Promise<boolean> => {
    if (!household) return false;
    setSaving(true);
    setError(null);
    try {
      await createPlanningGoal(vehiclePlanningGoalData(vehicle, index), household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
      return true;
    } catch (err) {
      setError(userFacingError("添加车辆需求", err));
      return false;
    } finally {
      setSaving(false);
    }
  }, [household, refreshPlanningFoundation]);
  const deleteVehiclePlanningGoal = useCallback(async (goalId: string): Promise<boolean> => {
    if (!household) return false;
    setSaving(true);
    setError(null);
    try {
      await deletePlanningGoal(goalId);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
      return true;
    } catch (err) {
      setError(userFacingError("删除车辆需求", err));
      return false;
    } finally {
      setSaving(false);
    }
  }, [household, refreshPlanningFoundation]);
  const saveVehiclePlanningGoal = useCallback(async (goalId: string, vehicle: VehiclePlanData, index: number): Promise<boolean> => {
    if (!household) return false;
    setSaving(true);
    setError(null);
    try {
      await savePlanningGoal(goalId, vehiclePlanningGoalData(vehicle, index), household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id);
      return true;
    } catch (err) {
      setError(userFacingError("保存车辆需求", err));
      return false;
    } finally {
      setSaving(false);
    }
  }, [household, refreshPlanningFoundation]);
  const savePlanningGoalData = useCallback(async (goalId: string, goalData: PlanningGoalData): Promise<void> => {
    await savePlanningGoal(goalId, goalData, household?.id ?? null);
  }, [household?.id]);
  const refreshGenericPlanningGoals = useCallback(() => {
    if (household?.id) void refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
  }, [household?.id, refreshPlanningFoundation]);
  const createGenericPlanningGoal = useCallback(async (goalType: "renovation" | "other") => {
    if (!household) return;
    const genericGoals = planningGoals.filter((goal) => goal.goal_type === "renovation" || goal.goal_type === "other");
    setSaving(true);
    setError(null);
    try {
      await createPlanningGoal(genericPlanningGoalDefaultData(goalType, genericGoals.length), household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("添加规划目标", err));
    } finally {
      setSaving(false);
    }
  }, [household, planningGoals, refreshPlanningFoundation]);
  const duplicateGenericPlanningGoal = useCallback(async (goal: PlanningGoalRecord) => {
    if (!household) return;
    const genericGoals = planningGoals.filter((item) => item.goal_type === "renovation" || item.goal_type === "other");
    setSaving(true);
    setError(null);
    try {
      await createPlanningGoal(genericPlanningGoalDuplicateData(goal, genericGoals.length), household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("复制规划目标", err));
    } finally {
      setSaving(false);
    }
  }, [household, planningGoals, refreshPlanningFoundation]);
  const saveGenericPlanningGoal = useCallback(async (goalId: string, goalData: PlanningGoalData) => {
    if (!household) return;
    setSaving(true);
    setError(null);
    try {
      await savePlanningGoal(goalId, goalData, household.id);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("保存规划目标", err));
    } finally {
      setSaving(false);
    }
  }, [household, refreshPlanningFoundation]);
  const deleteGenericPlanningGoal = useCallback(async (goalId: string) => {
    if (!household) return;
    setSaving(true);
    setError(null);
    try {
      await deletePlanningGoal(goalId);
      setSaveState("saved");
      await refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true });
    } catch (err) {
      setError(userFacingError("删除规划目标", err));
    } finally {
      setSaving(false);
    }
  }, [household, refreshPlanningFoundation]);
  const updateSpecialDeduction = <K extends keyof SpecialDeductionItemData>(index: number, key: K, value: SpecialDeductionItemData[K]) => updateHousehold("special_deductions", updateArrayItem(specialDeductions, index, key, value));
  const addSpecialDeduction = (deductionType: SpecialDeductionItemData["deduction_type"] = "housing_rent") => {
    const labels: Record<SpecialDeductionItemData["deduction_type"], string> = {
      child_education: "子女教育专项附加扣除",
      infant_care: "婴幼儿照护专项附加扣除",
      continuing_education: "继续教育年度汇算扣除",
      serious_illness: "大病医疗年度汇算扣除",
      housing_rent: "住房租金专项附加扣除",
      mortgage_interest: "首套住房贷款利息专项附加扣除",
      personal_pension: "个人养老金扣除"
    };
    updateHousehold("special_deductions", [
      ...specialDeductions,
      {
        ...defaultSpecialDeduction,
        deduction_type: deductionType,
        name: labels[deductionType],
        member_name: incomeMembers[0]?.name ?? "",
        settlement_mode: deductionType === "continuing_education" || deductionType === "serious_illness" ? "annual_settlement" : "monthly_withholding",
        monthly_amount: deductionType === "mortgage_interest" ? 1000 : deductionType === "housing_rent" ? 1500 : deductionType === "child_education" || deductionType === "infant_care" ? 2000 : 0,
        annual_amount: deductionType === "continuing_education" ? 3600 : 0,
        is_first_home_loan: deductionType === "mortgage_interest"
      }
    ]);
  };
  const removeSpecialDeduction = (index: number) => updateHousehold("special_deductions", specialDeductions.filter((_, itemIndex) => itemIndex !== index));
  const updateCarPlan = <K extends keyof CarPlanData>(key: K, value: CarPlanData[K]) => updateHousehold("car_plan", { ...carPlan, [key]: value });
  const updateCarPlanPatch = (patch: Partial<CarPlanData>) => updateHousehold("car_plan", { ...carPlan, ...patch });
  const updateCarPlanSelection = (vehicleIndex: number, variant: string) => {
    markDirty(false);
    const selectedVehicle = carPlan.vehicle_plans?.[vehicleIndex];
    const nextVehicle = selectedVehicle ? { ...selectedVehicle, selected_strategy_variant: variant } : null;
    setHouseholds((items) => items.map((item, index) => {
      if (index !== 0) return item;
      const vehiclePlans = (item.data.car_plan.vehicle_plans ?? []).map((vehicle, currentIndex) => (
        currentIndex === vehicleIndex ? { ...vehicle, selected_strategy_variant: variant } : vehicle
      ));
      return {
        ...item,
        data: {
          ...item.data,
          car_plan: {
            ...item.data.car_plan,
            selected_strategy_variant: variant,
            vehicle_plans: vehiclePlans
          }
        }
      };
    }));
    if (nextVehicle?.planning_goal_id) {
      void savePlanningGoalData(nextVehicle.planning_goal_id, vehiclePlanningGoalData(nextVehicle, vehicleIndex))
        .then(() => {
          setSaveState("saved");
          setCalculationVersion((version) => version + 1);
        })
        .catch((err) => setError(userFacingError("保存车辆策略", err)));
    } else {
      setCalculationVersion((version) => version + 1);
    }
  };
  const setSelectedPlanVariant = (variant: string) => {
    if (!selectedScenario) return;
    setSelectedPlanVariants((items) => ({ ...items, [selectedScenario.id]: variant }));
    if (selectedScenario.id !== noPurchaseScenarioId) updateScenario("selected_purchase_plan_variant", variant);
  };

  const addScenario = async (patch: Partial<ScenarioData> = {}) => {
    if (!household) return;
    const sequence = Math.max(1, patch.purchase_sequence ?? scenarios.length + 1);
    const created = await createPlanningGoal(homePlanningGoalData({
      ...createTargetScenarioData(sequence),
      annual_investment_return: selectedScenario.data.annual_investment_return ?? 0.025,
      ...patch
    }), household.id);
    setSelectedScenarioId(created.id);
    await refreshScenariosAndPlanningFoundation(household.id, { clearGeneratedStrategies: true });
  };
  const removeScenario = async (id: string) => {
    if (!household) return;
    setScenarios((items) => {
      const nextScenarios = items.filter((item) => item.id !== id);
      if (selectedScenarioId === id) setSelectedScenarioId(nextScenarios[0]?.id ?? noPurchaseScenarioId);
      return nextScenarios;
    });
    await deletePlanningGoal(id);
    await refreshScenariosAndPlanningFoundation(household.id, { clearGeneratedStrategies: true });
  };
  const removeScenarios = async (ids: string[]) => {
    if (!household) return;
    const idSet = new Set(ids);
    setScenarios((items) => {
      const nextScenarios = items.filter((item) => !idSet.has(item.id));
      if (idSet.has(selectedScenarioId)) setSelectedScenarioId(nextScenarios[0]?.id ?? noPurchaseScenarioId);
      return nextScenarios;
    });
    await Promise.all(ids.map((id) => deletePlanningGoal(id)));
    await refreshScenariosAndPlanningFoundation(household.id, { clearGeneratedStrategies: true });
  };

  const runCalculation = useCallback(async () => {
    if (!household || !activeRulePack) return;
    const requestSeq = ++calculationSeqRef.current;
    const requestVersion = calculationVersion;
    setError(null);
    const scenariosForCalculation = scenarios.length > 0 ? scenarios : [noPurchaseScenario];
    const cachedCalculated = scenariosForCalculation
      .map((scenario) => {
        const cached = peekCompletedAffordabilityResult(
          household.id,
          scenario.id,
          household.data,
          scenario.data,
          activeRulePack.data,
          activeMarketSnapshot?.data ?? null
        );
        return cached ? [scenario.id, cached] as const : null;
      });
    const allCalculationsCached = cachedCalculated.every((item) => item !== null);
    setIsCalculating(!allCalculationsCached);
    try {
      const calculated = allCalculationsCached
        ? cachedCalculated.filter((item): item is readonly [string, AffordabilityResult] => item !== null)
        : await Promise.all(scenariosForCalculation.map(async (scenario) => [scenario.id, await calculateAffordability(household.id, scenario.id, household.data, scenario.data, activeRulePack.data, activeMarketSnapshot?.data ?? null)] as const));
      if (requestSeq !== calculationSeqRef.current) return;
      const cacheLayerGroups = Array.from(new Map(calculated.map(([, item]) => [
        `${item.cache_layers.engine}:${item.cache_layers.input}:${item.cache_layers.strategy}:${item.cache_layers.ledger}:${item.cache_layers.visualization}`,
        item.cache_layers
      ])).values());
      const generatedStrategyRequest = {
        cache_layers: cacheLayerGroups,
        current_only: true
      };
      const cachedGeneratedRows = peekCompletedGeneratedStrategies(generatedStrategyRequest);
      if (allCalculationsCached) {
        startTransition(() => {
          setScenarioResults(Object.fromEntries(calculated));
          if (cachedGeneratedRows) {
            setGeneratedStrategies(Array.from(new Map(cachedGeneratedRows.map((item) => [item.id, item])).values()));
          }
          setCalculatedVersion(requestVersion);
        });
        if (cachedGeneratedRows) return;
      }
      let generatedRows: GeneratedStrategyRecord[] | null = null;
      try {
        generatedRows = await fetchGeneratedStrategiesByCacheLayers(generatedStrategyRequest);
      } catch {
        generatedRows = null;
      }
      if (requestSeq !== calculationSeqRef.current) return;
      const generatedRowsById = new Map((generatedRows ?? []).map((item) => [item.id, item]));
      startTransition(() => {
        if (!allCalculationsCached) setScenarioResults(Object.fromEntries(calculated));
        setGeneratedStrategies(Array.from(generatedRowsById.values()));
        setCalculatedVersion(requestVersion);
      });
    } catch (err) {
      if (requestSeq === calculationSeqRef.current) setError(userFacingError("计算", err));
    } finally {
      if (requestSeq === calculationSeqRef.current) setIsCalculating(false);
    }
  }, [activeMarketSnapshot, activeRulePack, calculationVersion, household, scenarios]);

  const persistAll = useCallback(async () => {
    if (!household || !activeRulePack) return;
    const saveVersion = dirtyVersionRef.current;
    setSaving(true);
    setError(null);
    try {
      const scenarioRecordsToSave = scenarios.filter((scenario) => scenario.id !== noPurchaseScenarioId);
      const [savedHousehold, savedHomeGoals, savedRulePack] = await Promise.all([
        saveHousehold(household.id, household.data),
        Promise.all(scenarioRecordsToSave.map((scenario) => savePlanningGoal(
          scenario.data.planning_goal_id || scenario.id,
          homePlanningGoalData(scenario.data),
          household.id
        ))),
        saveRulePack(activeRulePack.id, activeRulePack.data)
      ]);
      if (dirtyVersionRef.current === saveVersion) {
        setHouseholds((items) => items.map((item) => item.id === savedHousehold.id ? completeHouseholdDefaults(savedHousehold) : item));
        if (savedHomeGoals.length) {
          setScenarios((items) => items.map((item, index) => {
            const savedGoal = savedHomeGoals.find((goal) => goal.id === item.id);
            if (!savedGoal) return item;
            return scenarioRecordFromHomeGoal(savedGoal, index);
          }));
        }
        applyPlanningFoundation(await fetchPlanningFoundation(savedHousehold.id));
        setRulePacks((items) => items.map((item) => item.id === savedRulePack.id ? savedRulePack : item));
        setSaveState("saved");
      } else {
        setSaveState("dirty");
      }
    } catch (err) {
      setError(userFacingError("保存", err));
    } finally {
      setSaving(false);
    }
  }, [activeRulePack, applyPlanningFoundation, household, scenarios]);
  const previewSource = async () => setSourcePreview(await fetchSourcePreview(sourceUrl));
  const refreshPersonalPensionReturnData = useCallback(async (force = false) => {
    setRefreshingPersonalPensionReturns(true);
    try {
      const response = await refreshPersonalPensionReturns(force);
      setPersonalPensionReturnSnapshot(response.record);
      setCalculationVersion((version) => version + 1);
    } catch (err) {
      setError(userFacingError("更新个人养老金收益率", err));
    } finally {
      setRefreshingPersonalPensionReturns(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    loadInitialData()
      .then(async ([householdRecords, homeGoals, ruleRecords, marketSnapshotRecords]) => {
        if (!active) return;
        setHouseholds(householdRecords.map(completeHouseholdDefaults));
        const scenarioRecords = homeGoals.map(scenarioRecordFromHomeGoal);
        setScenarios(scenarioRecords);
        setRulePacks(ruleRecords);
        setMarketSnapshots(marketSnapshotRecords);
        setSelectedScenarioId(scenarioRecords[0]?.id ?? noPurchaseScenarioId);
        const firstHouseholdId = householdRecords[0]?.id;
        if (firstHouseholdId) {
          const foundation = await fetchPlanningFoundation(firstHouseholdId);
          if (active) {
            applyPlanningFoundation(foundation);
          }
        }
      })
      .catch((err) => setError(userFacingError("加载", err)))
      .finally(() => { if (active) setLoading(false); });
    fetchPersonalPensionReturnSnapshots()
      .then((records) => {
        if (active && records[0]) setPersonalPensionReturnSnapshot(records[0]);
        if (active && (!records[0] || records[0].data.next_due_date <= new Date().toISOString().slice(0, 10))) {
          void refreshPersonalPensionReturnData(false);
        }
      })
      .catch((err) => { if (active) setError(userFacingError("加载个人养老金收益率", err)); });
    return () => { active = false; };
  }, [applyPlanningFoundation, refreshPersonalPensionReturnData]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("planner-theme", theme);
  }, [theme]);
  useEffect(() => {
    if (loading || saving || saveState !== "dirty") return undefined;
    const timer = window.setTimeout(() => { void persistAll(); }, 1200);
    return () => window.clearTimeout(timer);
  }, [loading, persistAll, saveState, saving]);
  useEffect(() => {
    if (loading) return undefined;
    const timer = window.setTimeout(() => { void runCalculation(); }, 350);
    return () => window.clearTimeout(timer);
  }, [calculationVersion, loading]);

  if (loading) return <div className="loading-screen"><Loader2 className="spin" size={18} /> 正在加载家庭财务模型</div>;
  if (!household || !activeRulePack) return <div className="loading-screen">初始化数据缺失</div>;

  const pageContent = (() => {
    if (activePage === "家庭财务") return <IncomePage household={household.data} personalPensionAnnualCap={ruleNumber("personal_pension_deduction_annual_cap", 12000)} personalPensionReturnSnapshot={personalPensionReturnSnapshot} refreshingPersonalPensionReturns={refreshingPersonalPensionReturns} refreshPersonalPensionReturns={refreshPersonalPensionReturnData} scenario={selectedScenario.data} incomeMembers={incomeMembers} phasedLoans={phasedLoans} scheduledExpenses={scheduledExpenses} dailyExpenseStages={dailyExpenseStages} rentExpenseStages={rentExpenseStages} elderlyDependents={elderlyDependents} result={result} accountConcepts={result?.account_concepts ?? accountConcepts} coreObjectGroups={result?.core_object_groups ?? coreObjectGroups} updateHousehold={updateHousehold} updateIncomeMember={updateIncomeMember} addIncomeMember={addIncomeMember} removeIncomeMember={removeIncomeMember} updateIncomeStage={updateIncomeStage} updateIncomeStagePatch={updateIncomeStagePatch} addIncomeStage={addIncomeStage} removeIncomeStage={removeIncomeStage} updatePhasedLoan={updatePhasedLoan} addPhasedLoan={addPhasedLoan} removePhasedLoan={removePhasedLoan} updateScheduledExpense={updateScheduledExpense} addScheduledExpense={addScheduledExpense} addAnnualScheduledExpense={addAnnualScheduledExpense} addOneTimeScheduledExpense={addOneTimeScheduledExpense} removeScheduledExpense={removeScheduledExpense} updateDailyExpenseStage={updateDailyExpenseStage} addDailyExpenseStage={addDailyExpenseStage} removeDailyExpenseStage={removeDailyExpenseStage} updateRentExpenseStage={updateRentExpenseStage} addRentExpenseStage={addRentExpenseStage} removeRentExpenseStage={removeRentExpenseStage} updateElderlyDependent={updateElderlyDependent} addElderlyDependent={addElderlyDependent} removeElderlyDependent={removeElderlyDependent} />;
    if (activePage === "规划目标") return <PlanningGoalCenterPage household={household.data} updateHouseholdPatch={updateHouseholdPatch} planningGoals={planningGoals} planningSequence={planningSequence} coreObjects={coreObjects} createGoal={createGenericPlanningGoal} duplicateGoal={duplicateGenericPlanningGoal} saveGoal={saveGenericPlanningGoal} deleteGoal={deleteGenericPlanningGoal} refreshGoals={refreshGenericPlanningGoals} openPage={setActivePage} saving={saving} />;
    if (activePage === "税务") return <TaxPage household={household.data} incomeMembers={incomeMembers} childPlans={childPlans} specialDeductions={specialDeductions} result={result} taxStrategyItems={taxStrategyItemsForPage} taxStrategyTimeline={taxStrategyTimelineForPage} taxStrategySourceLabel={taxStrategySourceLabel} updateHousehold={updateHousehold} updateChildPlan={updateChildPlan} updateSpecialDeduction={updateSpecialDeduction} addSpecialDeduction={addSpecialDeduction} removeSpecialDeduction={removeSpecialDeduction} />;
    if (activePage === "记账校准") return <AccountCalibrationPage household={household.data} result={result} planningGoals={planningGoals} planningSequence={planningSequence} accountConcepts={result?.account_concepts ?? accountConcepts} coreObjectGroups={result?.core_object_groups ?? coreObjectGroups} generatedStrategies={generatedStrategies} updateHousehold={updateHousehold} />;
    if (activePage === "养娃计划") return <ChildPlanPage incomeMembers={incomeMembers} childPlans={childPlans} childPlanStrategies={childPlanStrategiesForPage} childPlanStrategySourceLabel={childPlanStrategySourceLabel} updateChildPlan={updateChildPlan} updateChildPlanPatch={updateChildPlanPatch} applyChildStrategyPatch={applyChildStrategyPatch} addChildPlan={addChildPlan} duplicateChildPlan={duplicateChildPlan} removeChildPlan={removeChildPlan} openPlanningGoals={() => setActivePage("规划目标")} />;
    if (activePage === "理财计划") return <InvestmentPlanPage household={household.data} scenario={selectedScenario.data} result={result} accountConcepts={result?.account_concepts ?? accountConcepts} investmentRecommendations={investmentRecommendationsForPage} investmentRecommendationSourceLabel={investmentRecommendationSourceLabel} updateHousehold={updateHousehold} updateHouseholdPatch={updateHouseholdPatch} updateInvestmentAnnualReturn={updateInvestmentAnnualReturn} />;
    if (activePage === "购房计划") return <ScenarioPage scenarios={scenarios} hasPurchaseTargets={scenarios.length > 0} selectedScenario={selectedScenario} setSelectedScenarioId={setSelectedScenarioId} updateScenario={updateScenario} updateScenarioRecord={updateScenarioRecord} addScenario={addScenario} removeScenario={removeScenario} removeScenarios={removeScenarios} result={result} planningSequence={planningSequence} scenarioComparisons={scenarioComparisons} selectedPlanVariant={selectedPlanVariant} setSelectedPlanVariant={setSelectedPlanVariant} availablePlans={selectedScenarioHomePurchasePlans} purchasePlanSourceLabel={purchasePlanSourceLabel} calculationPending={calculationPending} openPlanningGoals={() => setActivePage("规划目标")} />;
    if (activePage === "房产监测") return <PropertyMonitorPage householdId={household.id} scenarios={scenarios} marketSnapshots={marketSnapshots} purchasePlans={propertyMonitorPurchasePlans} onUpdateScenario={updateScenarioRecord} onMarketSnapshotCreated={(snapshot) => setMarketSnapshots((items) => [...items, snapshot])} />;
    if (activePage === "购车计划") return <CarPlanPage carPlan={carPlan} result={result} planningSequence={planningSequence} carStrategies={carStrategiesForPage} carStrategySourceLabel={carStrategySourceLabel} updateCarPlan={updateCarPlan} updateCarPlanPatch={updateCarPlanPatch} updateCarPlanSelection={updateCarPlanSelection} createVehiclePlanningGoal={createVehiclePlanningGoal} saveVehiclePlanningGoal={saveVehiclePlanningGoal} deleteVehiclePlanningGoal={deleteVehiclePlanningGoal} savePlanningGoalData={savePlanningGoalData} calculationPending={calculationPending} openPlanningGoals={() => setActivePage("规划目标")} />;
    if (activePage === "政策规则") return <RulePage activeRulePack={activeRulePack.data} ruleNumber={ruleNumber} updateRulePack={updateRulePack} updateRuleParam={updateRuleParam} sourceUrl={sourceUrl} setSourceUrl={setSourceUrl} sourcePreview={sourcePreview} previewSource={() => void previewSource()} saving={saving} />;
    if (activePage === "可视化") return <VisualizationPage result={result} household={household.data} selectedScenario={selectedScenario} scenarioComparisons={scenarioComparisons} setSelectedScenarioId={setSelectedScenarioId} selectedPlan={selectedPlan} selectedPlanVariant={selectedPlanVariant} setSelectedPlanVariant={setSelectedPlanVariant} availablePlans={visualizationPlans} accountConcepts={result?.account_concepts ?? accountConcepts} coreObjectGroups={result?.core_object_groups ?? coreObjectGroups} activeRulePack={activeRulePack.data} calculationPending={calculationPending} timelineState={visualizationTimelineState} onTimelineStateChange={updateVisualizationTimelineState} />;
    return <ExportPage result={result} scenario={selectedScenario.data} selectedPlan={selectedPlan} selectedPlanVariant={selectedPlanVariant} setSelectedPlanVariant={setSelectedPlanVariant} availablePlans={selectedScenarioPurchasePlans} runCalculation={runCalculation} />;
  })();

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <strong>豪斯计划</strong>
          <p>{isCalculating ? "后端正在重新计算" : saveState === "dirty" ? "有未保存修改" : "本地模型已就绪"}</p>
        </div>
        <div className="topbar-actions">
          <button className="ghost-button" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} type="button">
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />} {theme === "dark" ? "浅色" : "深色"}
          </button>
          <button className="ghost-button" onClick={() => void runCalculation()} disabled={isCalculating} type="button">
            <RefreshCw size={16} /> 重新计算
          </button>
          <button className="primary-button" onClick={() => void persistAll()} disabled={saving} type="button">
            <Save size={16} /> 保存本地
          </button>
        </div>
        {error ? <div className="topbar-status error-text">{error}</div> : null}
      </header>
      <nav className="page-nav">
        {pages.map((page) => (
          <button key={page} className={page === activePage ? "page-tab active" : "page-tab"} onClick={() => setActivePage(page)} type="button">
            {page}
          </button>
        ))}
      </nav>
      <PlanningFoundationStrip
        sequence={planningSequence}
        contextGoals={planningContextGoals}
        contextCoreObjects={planningContextCoreObjects}
        planningGoals={planningGoals}
        accountConcepts={result?.account_concepts ?? accountConcepts}
        coreObjectGroups={result?.core_object_groups ?? coreObjectGroups}
        cacheLayers={result?.cache_layers ?? null}
        coreObjects={coreObjects}
        generatedStrategies={generatedStrategies}
        marketSnapshot={activeMarketSnapshot}
        selectedHomeGoalId={
          selectedScenario.id === noPurchaseScenarioId
            ? ""
            : selectedScenario.data.planning_goal_id || selectedScenario.id
        }
        selectedPurchasePlan={selectedPlan}
      />
      <main className="page-workspace">{pageContent}</main>
    </div>
  );
}

function IncomePage({
  household,
  personalPensionAnnualCap,
  personalPensionReturnSnapshot,
  refreshingPersonalPensionReturns,
  refreshPersonalPensionReturns,
  scenario,
  incomeMembers,
  phasedLoans,
  scheduledExpenses,
  dailyExpenseStages,
  rentExpenseStages,
  elderlyDependents,
  result,
  accountConcepts,
  coreObjectGroups,
  updateHousehold,
  updateIncomeMember,
  addIncomeMember,
  removeIncomeMember,
  updateIncomeStage,
  updateIncomeStagePatch,
  addIncomeStage,
  removeIncomeStage,
  updatePhasedLoan,
  addPhasedLoan,
  removePhasedLoan,
  updateScheduledExpense,
  addScheduledExpense,
  addAnnualScheduledExpense,
  addOneTimeScheduledExpense,
  removeScheduledExpense,
  updateDailyExpenseStage,
  addDailyExpenseStage,
  removeDailyExpenseStage,
  updateRentExpenseStage,
  addRentExpenseStage,
  removeRentExpenseStage,
  updateElderlyDependent,
  addElderlyDependent,
  removeElderlyDependent
}: {
  household: HouseholdData;
  personalPensionAnnualCap: number;
  personalPensionReturnSnapshot: PersonalPensionReturnSnapshotRecord | null;
  refreshingPersonalPensionReturns: boolean;
  refreshPersonalPensionReturns: (force?: boolean) => Promise<void>;
  scenario: ScenarioData;
  incomeMembers: IncomeMember[];
  phasedLoans: PhasedLoanData[];
  scheduledExpenses: ScheduledExpenseData[];
  dailyExpenseStages: DailyExpenseStageData[];
  rentExpenseStages: RentExpenseStageData[];
  elderlyDependents: ElderlyDependentData[];
  result: AffordabilityResult | null;
  accountConcepts: AccountConceptSummary[];
  coreObjectGroups: CoreObjectGroupSummary[];
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
  updateIncomeMember: <K extends keyof IncomeMember>(
    index: number,
    key: K,
    value: IncomeMember[K]
  ) => void;
  addIncomeMember: () => void;
  removeIncomeMember: (index: number) => void;
  updateIncomeStage: <K extends keyof IncomeStageData>(
    memberIndex: number,
    stageIndex: number,
    key: K,
    value: IncomeStageData[K]
  ) => void;
  updateIncomeStagePatch: (
    memberIndex: number,
    stageIndex: number,
    patch: Partial<IncomeStageData>
  ) => void;
  addIncomeStage: (memberIndex: number) => void;
  removeIncomeStage: (memberIndex: number, stageIndex: number) => void;
  updatePhasedLoan: <K extends keyof PhasedLoanData>(
    index: number,
    key: K,
    value: PhasedLoanData[K]
  ) => void;
  addPhasedLoan: () => void;
  removePhasedLoan: (index: number) => void;
  updateScheduledExpense: <K extends keyof ScheduledExpenseData>(
    index: number,
    key: K,
    value: ScheduledExpenseData[K]
  ) => void;
  addScheduledExpense: () => void;
  addAnnualScheduledExpense: () => void;
  addOneTimeScheduledExpense: () => void;
  removeScheduledExpense: (index: number) => void;
  updateDailyExpenseStage: <K extends keyof DailyExpenseStageData>(
    index: number,
    key: K,
    value: DailyExpenseStageData[K]
  ) => void;
  addDailyExpenseStage: () => void;
  removeDailyExpenseStage: (index: number) => void;
  updateRentExpenseStage: <K extends keyof RentExpenseStageData>(
    index: number,
    key: K,
    value: RentExpenseStageData[K]
  ) => void;
  addRentExpenseStage: () => void;
  removeRentExpenseStage: (index: number) => void;
  updateElderlyDependent: <K extends keyof ElderlyDependentData>(
    index: number,
    key: K,
    value: ElderlyDependentData[K]
  ) => void;
  addElderlyDependent: () => void;
  removeElderlyDependent: (index: number) => void;
}) {
  const today = new Date();
  const careerShock = normalizeCareerShockForMembers(household.career_shock, incomeMembers);
  const careerShockProjection = result?.career_shock_projection ?? null;
  const estimatedUnemploymentBenefitMonths = careerShockProjection?.unemployment_benefit_months ?? 0;
  const estimatedUnemploymentBenefitMonthly = careerShockProjection?.unemployment_benefit_monthly ?? 0;
  const estimatedLaterUnemploymentBenefitMonthly = careerShockProjection?.later_unemployment_benefit_monthly ?? 0;
  const estimatedSelfSocialInsuranceMonthly = careerShockProjection?.self_social_insurance_monthly ?? 0;
  const estimatedFlexibleHousingFundMonthly = careerShockProjection?.flexible_housing_fund_monthly ?? 0;
  const allMembersAutoPension = careerShock.member_settings.length > 0
    ? careerShock.member_settings.every((setting) => setting.auto_pension_monthly)
    : true;
  const elderlyPolicyStatus = elderlyDeductionPolicyStatus(elderlyDependents, new Date());
  const phasedLoanPhaseSummary = (result?.phased_loan_summaries ?? []).reduce<Record<string, number>>((summary, loan) => {
    summary[loan.phase] = (summary[loan.phase] ?? 0) + 1;
    return summary;
  }, {});
  const phasedLoanSummaryText = phasedLoans.length > 0
    ? Object.entries(phasedLoanPhaseSummary).map(([phase, count]) => `${phase} ${count} 笔`).join("，") || "等待计算"
    : "暂无已有贷款";
  const updateCareerShock = (patch: Partial<CareerShockData>) => {
    const merged = normalizeCareerShockForMembers({ ...careerShock, ...patch }, incomeMembers);
    updateHousehold("career_shock", merged);
  };
  const updateMemberCareerShockSetting = (
    memberIndex: number,
    patch: Partial<CareerShockData["member_settings"][number]>
  ) => {
    const memberSettings = careerShock.member_settings.map((setting, index) =>
      index === memberIndex ? { ...setting, ...patch, member_name: incomeMembers[index]?.name || setting.member_name } : setting
    );
    const merged = normalizeCareerShockForMembers({ ...careerShock, member_settings: memberSettings }, incomeMembers);
    updateHousehold("career_shock", merged);
  };
  const updateScheduledExpensePatch = (index: number, patch: Partial<ScheduledExpenseData>) => {
    updateHousehold(
      "scheduled_expenses",
      scheduledExpenses.map((expense, itemIndex) => (itemIndex === index ? { ...expense, ...patch } : expense))
    );
  };
  const currentRentStage = rentExpenseStageAt(household, today);
  const currentMonthlyExpense = householdExpenseAt(household, today, 0);
  const currentRentCashCost = currentRentStage ? rentStageCashCostAt(currentRentStage, today) : 0;
  const memberAges = incomeMembers.map((member) => ageYearsFromBirthMonth(member.birth_month, today) ?? member.current_age ?? 30);
  const normalizedBorrowerMemberIndex = Math.min(
    Math.max(0, household.borrower_member_index ?? 0),
    Math.max(0, incomeMembers.length - 1)
  );
  const borrowerMember = incomeMembers[normalizedBorrowerMemberIndex] ?? incomeMembers[0];
  const borrowerMemberName = borrowerMember?.name || `成员 ${normalizedBorrowerMemberIndex + 1}`;
  const borrowerDisplayAge = memberAges[normalizedBorrowerMemberIndex] ?? household.borrower_age ?? 30;
  const borrowerAgeForPolicy = Math.min(68, Math.max(18, Math.round(borrowerDisplayAge ?? household.borrower_age ?? 30)));
  const derivedSocialSecurityMonths = Math.max(
    household.social_security_months ?? 0,
    ...incomeMembers.map((member) => Math.max(member.social_security_months ?? 0, member.income_tax_months ?? 0))
  );
  const derivedExistingHomeCount = incomeMembers.reduce((sum, member) => sum + (member.existing_home_count ?? 0), 0) || household.existing_home_count || 0;
  const derivedExistingMortgageCount = incomeMembers.reduce((sum, member) => sum + (member.existing_mortgage_count ?? 0), 0) || household.existing_mortgage_count || 0;
  const derivedInitialCashBalance = incomeMembers.reduce((sum, member) => sum + (member.initial_cash_balance ?? 0), 0);
  const derivedInitialInvestments = incomeMembers.reduce((sum, member) => sum + (member.initial_investments ?? 0), 0);
  const conceptByCode = accountConceptMap(accountConcepts);
  const coreGroupByCode = coreObjectGroupMap(coreObjectGroups);
  const liquidAssetGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.liquidAssets);
  const restrictedAccountGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.restrictedAccounts);
  const fixedAssetGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.fixedAssets);
  const loanAccountGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.loanAccounts);
  const accountDashboardConcepts = dashboardAccountConcepts(accountConcepts);
  const coreGroupMetricValue = (group: CoreObjectGroupSummary | undefined) =>
    coreObjectBalanceText(group);
  const coreGroupCountText = (group: CoreObjectGroupSummary | undefined) =>
    coreObjectCountText(group);
  const conceptMetricValue = (code: string) => coreObjectBalanceText(conceptByCode.get(code));
  const investmentAccountBalanceText = accountConceptBalanceTextWithHouseholdFallback(
    accountConcepts,
    ACCOUNT_CONCEPT_CODES.investment,
    household
  );
  const accountSetupDone =
    Boolean(liquidAssetGroup || restrictedAccountGroup) &&
    ((liquidAssetGroup?.current_balance ?? 0) > 0 || (restrictedAccountGroup?.current_balance ?? 0) > 0);
  const memberCompositionText = incomeMembers.length > 0
    ? `${incomeMembers.length} 人：${incomeMembers.map((member) => member.name || "未命名成员").join("、")}`
    : "待添加成员";
  const memberAgeText = incomeMembers.length > 0
    ? incomeMembers
        .map((member, index) => `${member.name || `成员 ${index + 1}`} ${member.birth_month ? `${memberAges[index]} 岁` : "年龄待填"}`)
        .join("、")
    : "待填写";
  const activeCareerShockSettings = careerShock.member_settings.filter((setting) => setting.enabled);
  const careerShockSummaryText = activeCareerShockSettings.length > 0
    ? activeCareerShockSettings.map((setting) => `${setting.member_name} ${setting.layoff_age} 岁`).join("、")
    : "默认不启用";
  useEffect(() => {
    const nextMembers = incomeMembers.map((member, index) => {
      const age = ageYearsFromBirthMonth(member.birth_month, today);
      return age !== null && age !== member.current_age ? { ...member, current_age: age } : member;
    });
    if (nextMembers.some((member, index) => member.current_age !== incomeMembers[index]?.current_age)) {
      updateHousehold("members", nextMembers);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomeMembers.map((member) => member.birth_month).join("|")]);
  useEffect(() => {
    const normalizedShock = normalizeCareerShockForMembers(household.career_shock, incomeMembers);
    if (JSON.stringify(normalizedShock) !== JSON.stringify(household.career_shock)) {
      updateHousehold("career_shock", normalizedShock);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomeMembers.map((member) => member.name).join("|"), incomeMembers.length]);
  useEffect(() => {
    if ((household.borrower_member_index ?? 0) !== normalizedBorrowerMemberIndex) {
      updateHousehold("borrower_member_index", normalizedBorrowerMemberIndex);
      return;
    }
    if ((household.borrower_age ?? 30) !== borrowerAgeForPolicy) {
      updateHousehold("borrower_age", borrowerAgeForPolicy);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedBorrowerMemberIndex, borrowerAgeForPolicy]);
  const setupChecklist = [
    { label: "家庭成员与工资阶段", done: incomeMembers.some((member) => incomeStagesForMember(member).some((stage) => stage.monthly_salary_gross > 0 || stage.annual_bonus_months > 0)) },
    { label: "日常、租房与计划支出", done: dailyExpenseStages.some((stage) => stage.base_living_expense > 0) || rentExpenseStages.some((stage) => stage.rent_amount > 0) || scheduledExpenses.some((expense) => expense.monthly_amount > 0) },
    { label: "账户与安全垫核心对象", done: accountSetupDone },
    { label: "已有贷款、赡养扣除和职业冲击", done: phasedLoans.length > 0 || elderlyDependents.length > 0 || Boolean(household.career_shock?.enabled) },
  ];
  const memberIncomeSection = (
    <section className="form-panel">
      <div className="member-header">
        <PanelTitle icon={<Banknote size={18} />} title="成员工资与收入阶段" collapsible />
        <span className="section-subtle-note">成员增删、出生年月和年龄在家庭画像中维护</span>
      </div>
      <div className="member-list roomy">
        {incomeMembers.map((member, index) => {
          const shockSetting = careerShock.member_settings[index];
          const shockProjection = careerShockProjection?.member_projections.find((item) => item.member_name === member.name);
          return (
          <section className="member-card" key={`member-${index}`}>
            <div className="member-card-head income-member-head">
              <div>
                <strong>{member.name || `成员 ${index + 1}`}</strong>
                <small>{incomeStagesForMember(member).length} 个收入阶段</small>
              </div>
            </div>
            <div className="member-header compact-heading">
              <strong>收入阶段</strong>
              <button className="ghost-button" onClick={() => addIncomeStage(index)} type="button">
                <Plus size={15} /> 新增阶段
              </button>
            </div>
            <div className="stage-list">
              {incomeStagesForMember(member).length === 0 ? (
                <section className="stage-row empty-stage-row">
                  <div className="empty-state compact">
                    <strong>暂无收入阶段</strong>
                    <span>该成员暂时不会产生工资、奖金、社保公积金缴存或个税；需要模拟工作、自由职业或退休收入时再新增阶段。</span>
                    <button className="ghost-button" onClick={() => addIncomeStage(index)} type="button">
                      <Plus size={15} /> 新增收入阶段
                    </button>
                  </div>
                </section>
              ) : null}
              {incomeStagesForMember(member).map((stage, stageIndex) => {
                const stageKind = stage.stage_kind ?? "salary";
                const showsSalaryControls = stageKind === "salary" || stageKind === "manual";
                const showsPayrollSwitch = stageKind === "salary" || stageKind === "manual";
                const showsFreelanceSwitch = stageKind !== "freelance";
                const freelanceEnabled = stageKind === "freelance" || (stage.monthly_freelance_income ?? 0) > 0;
                return (
                <section className="stage-row" key={`member-${index}-stage-${stageIndex}`}>
                  <div className="member-card-head">
                    <Field label="阶段名称">
                      <input
                        value={stage.name}
                        onChange={(event) => updateIncomeStage(index, stageIndex, "name", event.target.value)}
                      />
                    </Field>
                    <Field label="阶段类型">
                      <select
                        value={stage.stage_kind ?? "salary"}
                        onChange={(event) => {
                          const nextKind = event.target.value as IncomeStageData["stage_kind"];
                          if (nextKind === "salary") {
                            updateIncomeStagePatch(index, stageIndex, {
                              stage_kind: nextKind,
                              payroll_contributions_enabled: true,
                              monthly_freelance_income: 0,
                            });
                          } else if (nextKind === "freelance") {
                            updateIncomeStagePatch(index, stageIndex, {
                              stage_kind: nextKind,
                              payroll_contributions_enabled: false,
                              monthly_freelance_income: (stage.monthly_freelance_income ?? 0) > 0
                                ? stage.monthly_freelance_income
                                : Math.max(0, stage.monthly_salary_gross || 0),
                            });
                          } else if (nextKind === "manual") {
                            updateIncomeStagePatch(index, stageIndex, {
                              stage_kind: nextKind,
                              payroll_contributions_enabled: stage.payroll_contributions_enabled ?? false,
                            });
                          } else {
                            updateIncomeStagePatch(index, stageIndex, {
                              stage_kind: nextKind,
                              payroll_contributions_enabled: false,
                              monthly_freelance_income: 0,
                            });
                          }
                        }}
                      >
                        <option value="salary">工资就业</option>
                        <option value="unemployment">失业期</option>
                        <option value="freelance">自由职业</option>
                        <option value="pension">退休养老金</option>
                        <option value="manual">手动阶段</option>
                      </select>
                    </Field>
                    <button
                      className="icon-button"
                      onClick={() => removeIncomeStage(index, stageIndex)}
                      aria-label="删除收入阶段"
                      title="删除收入阶段"
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                  {showsPayrollSwitch || showsFreelanceSwitch ? (
                    <div className="stage-switch-row">
                      {showsPayrollSwitch ? (
                        <SwitchField
                          label="工资社保扣缴"
                          checked={stage.payroll_contributions_enabled ?? (stageKind === "salary")}
                          onChange={(checked) => updateIncomeStage(index, stageIndex, "payroll_contributions_enabled", checked)}
                        />
                      ) : null}
                      {showsFreelanceSwitch ? (
                        <SwitchField
                          label="自由职业收入"
                          checked={freelanceEnabled}
                          onChange={(checked) => {
                            if (checked) {
                              updateIncomeStagePatch(index, stageIndex, {
                                monthly_freelance_income: (stage.monthly_freelance_income ?? 0) > 0
                                  ? stage.monthly_freelance_income
                                  : Math.max(0, stage.monthly_salary_gross || 0),
                              });
                              return;
                            }
                            updateIncomeStage(index, stageIndex, "monthly_freelance_income", 0);
                          }}
                        />
                      ) : null}
                    </div>
                  ) : null}
                  <div className="form-grid">
                    <Field label="开始日期">
                      <input
                        type="date"
                        value={stage.start_date}
                        onChange={(event) => updateIncomeStage(index, stageIndex, "start_date", event.target.value)}
                      />
                    </Field>
                    <Field label="结束日期">
                      <input
                        type="date"
                        value={stage.end_date ?? ""}
                        onChange={(event) => updateIncomeStage(index, stageIndex, "end_date", event.target.value || null)}
                      />
                    </Field>
                    <Field label="公积金中心口径">
                      <select
                        value={stage.provident_account_management_center ?? "beijing_municipal"}
                        onChange={(event) =>
                          updateIncomeStage(
                            index,
                            stageIndex,
                            "provident_account_management_center",
                            event.target.value as IncomeStageData["provident_account_management_center"]
                          )
                        }
                      >
                        <option value="beijing_municipal">北京市管</option>
                        <option value="national">中央国家机关/国管</option>
                      </select>
                    </Field>
                    {showsSalaryControls ? (
                      <>
                        <NumberField
                          label="月工资税前"
                          value={stage.monthly_salary_gross}
                          min={0}
                          step={100}
                          onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_salary_gross", value)}
                        />
                        <NumberField
                          label="年终奖月数"
                          value={stage.annual_bonus_months}
                          min={0}
                          max={60}
                          step={0.1}
                          onChange={(value) => updateIncomeStage(index, stageIndex, "annual_bonus_months", Math.round(value * 10) / 10)}
                          description="按当前收入阶段月工资的倍数设置，支持一位小数。例如3.0表示标准年终奖为3个月工资，实际发放额还会按奖金归属周期内的在职月数折算。"
                        />
                        <Field label="奖金发放方式">
                          <select
                            value={stage.annual_bonus_payout_mode ?? "lump_sum"}
                            onChange={(event) =>
                              updateIncomeStage(index, stageIndex, "annual_bonus_payout_mode", event.target.value as IncomeStageData["annual_bonus_payout_mode"])
                            }
                          >
                            <option value="lump_sum">发放月一次性发放</option>
                            <option value="monthly_spread">按月均摊发放</option>
                          </select>
                        </Field>
                        {stage.annual_bonus_payout_mode === "monthly_spread" ? (
                          <Field label="发放月份">
                            <div className="readonly-metric compact">按月均摊时不使用</div>
                          </Field>
                        ) : (
                          <NumberField
                            label="发放月份"
                            value={stage.annual_bonus_payout_month ?? 4}
                            min={1}
                            max={12}
                            step={1}
                            onChange={(value) => updateIncomeStage(index, stageIndex, "annual_bonus_payout_month", Math.round(value))}
                          />
                        )}
                        <Field label="奖金归属起始月份" description={parameterExplanations["奖金归属起始月份"]}>
                          <select
                            value={stage.annual_bonus_earning_start_month ?? ""}
                            onChange={(event) => updateIncomeStage(index, stageIndex, "annual_bonus_earning_start_month", event.target.value ? Number(event.target.value) : null)}
                          >
                            <option value="">自动按收入阶段</option>
                            {Array.from({ length: 12 }, (_, monthIndex) => monthIndex + 1).map((month) => <option key={`bonus-start-${month}`} value={month}>{month}月</option>)}
                          </select>
                        </Field>
                        <Field label="奖金归属截止月份" description={parameterExplanations["奖金归属截止月份"]}>
                          <select
                            value={stage.annual_bonus_earning_end_month ?? ""}
                            onChange={(event) => updateIncomeStage(index, stageIndex, "annual_bonus_earning_end_month", event.target.value ? Number(event.target.value) : null)}
                          >
                            <option value="">自动按收入阶段</option>
                            {Array.from({ length: 12 }, (_, monthIndex) => monthIndex + 1).map((month) => <option key={`bonus-end-${month}`} value={month}>{month}月</option>)}
                          </select>
                        </Field>
                      </>
                    ) : null}
                    {freelanceEnabled ? (
                      <>
                        <NumberField
                          label="自由职业收入/月"
                          value={stage.monthly_freelance_income ?? 0}
                          min={0}
                          step={100}
                          onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_freelance_income", value)}
                        />
                        <Field label="自由职业税务口径">
                          <select
                            value={stage.freelance_tax_mode ?? "labor_remuneration"}
                            onChange={(event) => updateIncomeStage(index, stageIndex, "freelance_tax_mode", event.target.value as IncomeStageData["freelance_tax_mode"])}
                          >
                            <option value="labor_remuneration">劳务报酬</option>
                            <option value="business_income">经营所得</option>
                            <option value="other">其它粗略口径</option>
                          </select>
                        </Field>
                      </>
                    ) : null}
                    <NumberField
                      label="非税收入/月"
                      value={stage.monthly_non_taxable_income ?? 0}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_non_taxable_income", value)}
                    />
                    <NumberField
                      label="个人公积金比例"
                      value={stage.housing_fund_personal_rate ?? 0.12}
                      step={0.01}
                      min={0}
                      max={0.12}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "housing_fund_personal_rate", value)}
                    />
                    <NumberField
                      label="单位公积金比例"
                      value={stage.housing_fund_employer_rate ?? 0.12}
                      step={0.01}
                      min={0}
                      max={0.12}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "housing_fund_employer_rate", value)}
                    />
                    <NumberField
                      label="专项附加/月"
                      value={stage.monthly_special_additional_deduction}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_special_additional_deduction", value)}
                    />
                    <NumberField
                      label="其他年收入"
                      value={stage.other_annual_taxable_income}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "other_annual_taxable_income", value)}
                    />
                    <Field label="年终奖计税">
                      <select
                        value={stage.bonus_tax_method}
                        onChange={(event) =>
                          updateIncomeStage(index, stageIndex, "bonus_tax_method", event.target.value as BonusTaxMethod)
                        }
                      >
                        <option value="best">自动择优</option>
                        <option value="separate">单独计税</option>
                        <option value="merged">并入综合所得</option>
                      </select>
                    </Field>
                  </div>
                </section>
                );
              })}
              <section className="stage-row synthetic-stage-row" key={`member-${index}-career-shock-stage`}>
                <div className="member-card-head">
                  <div>
                    <strong>职业冲击收入阶段</strong>
                    <small>{shockSetting?.enabled ? "后端会生成失业金期与灵活就业期" : "默认不纳入测算"}</small>
                  </div>
                  <SwitchField
                    label={shockSetting?.enabled ? "启用职业冲击" : "不启用职业冲击"}
                    checked={Boolean(shockSetting?.enabled)}
                    onChange={(checked) => updateMemberCareerShockSetting(index, { enabled: checked })}
                  />
                </div>
                {shockSetting?.enabled ? (
                  <>
                    <div className="form-grid">
                      <NumberField
                        label="裁员年龄"
                        value={shockSetting.layoff_age}
                        min={18}
                        max={80}
                        step={1}
                        onChange={(value) => updateMemberCareerShockSetting(index, { layoff_age: value })}
                      />
                      <NumberField
                        label="冲击期自由职业收入/月"
                        value={shockSetting.freelance_income_monthly ?? 0}
                        min={0}
                        step={100}
                        onChange={(value) => updateMemberCareerShockSetting(index, { freelance_income_monthly: value })}
                      />
                      <SwitchField
                        label="自动估算养老金"
                        checked={shockSetting.auto_pension_monthly ?? true}
                        onChange={(checked) => updateMemberCareerShockSetting(index, { auto_pension_monthly: checked })}
                      />
                      {!shockSetting.auto_pension_monthly ? (
                        <NumberField
                          label="手动养老金/月"
                          value={shockSetting.pension_monthly}
                          min={0}
                          step={500}
                          onChange={(value) => updateMemberCareerShockSetting(index, { pension_monthly: value })}
                        />
                      ) : null}
                    </div>
                    <div className="read-only-grid">
                      <Metric label="预计裁员月份" value={shockProjection?.layoff_month ?? "等待后端计算"} tone="warn" />
                      <Metric label="预计退休月份" value={shockProjection?.retirement_month ?? "等待后端计算"} />
                      <Metric label="预计养老金/月" value={money(shockProjection?.pension_monthly ?? 0)} />
                      <Metric label="自缴支出/月" value={money(shockProjection?.self_payment_monthly ?? 0)} tone={(shockProjection?.self_payment_monthly ?? 0) > 0 ? "warn" : undefined} />
                    </div>
                    <div className="career-generated-stage-list">
                      {shockProjection?.generated_stages?.length ? (
                        shockProjection.generated_stages.map((generatedStage, generatedIndex) => (
                          <div className="read-only-line" key={`generated-stage-${index}-${generatedIndex}`}>
                            <strong>{generatedStage.name}</strong>
                            <span>
                              {generatedStage.start_date}
                              {generatedStage.end_date ? ` 至 ${generatedStage.end_date}` : " 起"}
                              {generatedStage.monthly_non_taxable_income > 0 ? `，非税收入 ${money(generatedStage.monthly_non_taxable_income)}/月` : ""}
                              {generatedStage.monthly_freelance_income > 0 ? `，自由职业收入 ${money(generatedStage.monthly_freelance_income)}/月` : ""}
                            </span>
                          </div>
                        ))
                      ) : (
                        <p className="field-hint">等待后端生成失业金期、灵活就业期和退休养老金阶段。</p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="field-hint">不启用时不会生成失业金期、灵活就业自缴期或裁员压力测试阶段；退休养老金仍可在全局估算规则中查看。</p>
                )}
                <p className="field-hint">
                  职业冲击作为该成员收入阶段的一部分管理。失业金、养老金由后端生成收入阶段；自缴社保和自缴公积金作为家庭支出里的按人月度支出进入现金流。
                </p>
              </section>
            </div>
            <p className="field-hint">
              默认只有一段收入；新增阶段后，后端会按各阶段实际生效月份折算税费、年终奖和公积金。五险按北京社保基数、个人养老 8%、医疗 2%+3、失业 0.5% 自动计算。
            </p>
          </section>
          );
        })}
      </div>
    </section>
  );

  const assetCashSection = (
    <section className="form-panel income-workbench-card account-panel">
      <PanelTitle icon={<ShieldCheck size={18} />} title="账户与安全垫" collapsible />
      <div className="form-grid two">
        <NumberField
          label="当前可动用现金"
          value={household.cash_account_balance}
          min={0}
          step={1000}
          onChange={(value) => updateHousehold("cash_account_balance", value)}
        />
        <NumberField
          label="当前投资资产"
          value={household.investments}
          min={0}
          step={1000}
          onChange={(value) => updateHousehold("investments", value)}
        />
        <NumberField
          label="现金安全垫月数"
          value={household.required_liquidity_months ?? 6}
          step={1}
          min={0}
          max={36}
          onChange={(value) => updateHousehold("required_liquidity_months", value)}
        />
      </div>
      <div className="account-member-balances">
        <strong className="setting-group-title">后端核心对象摘要</strong>
        <div className="read-only-grid">
          <Metric
            label="流动资产"
            value={coreGroupMetricValue(liquidAssetGroup)}
          />
          <Metric
            label="政策受限账户"
            value={coreGroupMetricValue(restrictedAccountGroup)}
          />
          <Metric
            label="固定资产与目标"
            value={coreGroupMetricValue(fixedAssetGroup)}
          />
          <Metric
            label="贷款账户"
            value={coreGroupMetricValue(loanAccountGroup)}
          />
        </div>
        <div className="read-only-grid">
          <Metric
            label="现金账户"
            value={conceptMetricValue(ACCOUNT_CONCEPT_CODES.cash)}
          />
          <Metric
            label="投资账户"
            value={investmentAccountBalanceText}
          />
          <Metric
            label="公积金账户"
            value={conceptMetricValue(ACCOUNT_CONCEPT_CODES.provident)}
          />
          <Metric
            label="养老医保账户"
            value={coreObjectBalanceText(conceptByCode.get(ACCOUNT_CONCEPT_CODES.socialSecurity))}
          />
        </div>
        {accountDashboardConcepts.length ? (
          <div className="setup-steps concept-chip-row">
            {accountDashboardConcepts.map((concept) => (
              <span className="setup-step done" key={concept.code}>
                {concept.name} {coreObjectCountText(concept)}
              </span>
            ))}
          </div>
        ) : null}
        <p className="field-hint compact">
          核心对象数量：流动资产 {coreGroupCountText(liquidAssetGroup)}，受限账户 {coreGroupCountText(restrictedAccountGroup)}，固定资产/目标 {coreGroupCountText(fixedAssetGroup)}，贷款 {coreGroupCountText(loanAccountGroup)}。
        </p>
      </div>
      <p className="field-hint">
        可编辑输入仍按真实账户填写；上方只读摘要来自后端核心对象分组，和规划底座、导出表、可视化概念保持同一口径。实际账户余额和模型不一致时，请到“记账校准”页面按月份校准账户。
      </p>
    </section>
  );

  return (
    <PlannerPageShell
      icon={<ClipboardCheck size={20} />}
      title="家庭财务"
      summary={<p>按“家庭画像 → 成员与账户 → 收入阶段 → 支出阶段 → 已有贷款”的顺序维护基础数据；计算结果和账户校准不要混在画像字段里。</p>}
    >
      <section className="form-panel setup-guide">
        <PanelTitle icon={<Sparkles size={18} />} title="初始化指引" collapsible />
        <p className="field-hint">
          首次使用建议按下面顺序填写家庭画像、收入支出、资产负债和计划目标，完成后点击“保存本地”写入本机数据库。
        </p>
        <div className="setup-steps">
          {setupChecklist.map((item, index) => (
            <span className={item.done ? "setup-step done" : "setup-step"} key={item.label}>
              <CheckCircle2 size={15} />
              {index + 1}. {item.label}
            </span>
          ))}
        </div>
      </section>

      <div className="income-overview-grid profile-only">
        <section className="form-panel income-overview-panel household-profile-panel">
          <PanelTitle icon={<ClipboardCheck size={18} />} title="家庭画像" collapsible />
          <div className="profile-summary-grid">
            <Metric label="成员组成" value={memberCompositionText} />
            <Metric label="成员年龄" value={memberAgeText} />
            <Metric label="赡养老人对象" value={`${elderlyDependents.length} 人`} />
            <Metric label="借款申请人年龄" value={`${borrowerAgeForPolicy} 岁，按${borrowerMemberName}同步`} />
          </div>
          <div className="profile-config-block">
            <strong>家庭与资格参数</strong>
            <div className="form-grid income-profile-grid profile-config-grid">
              <Field label="家庭名称">
                <input
                  value={household.name}
                  onChange={(event) => updateHousehold("name", event.target.value)}
                />
              </Field>
              <Field label="借款申请人">
                <select
                  value={normalizedBorrowerMemberIndex}
                  onChange={(event) => updateHousehold("borrower_member_index", Number(event.target.value))}
                >
                  {incomeMembers.map((member, index) => (
                    <option key={`borrower-member-${index}`} value={index}>
                      {member.name || `成员 ${index + 1}`}
                    </option>
                  ))}
                </select>
              </Field>
              <NumberField
                label="当前已出生子女数"
                value={household.child_count}
                min={0}
                max={10}
                step={1}
                onChange={(value) => updateHousehold("child_count", value)}
              />
              <SwitchField
                label="北京户籍家庭"
                checked={household.has_beijing_hukou}
                onChange={(checked) => updateHousehold("has_beijing_hukou", checked)}
              />
              <Metric label="社保/个税月数" value={`${derivedSocialSecurityMonths} 个月`} />
              <Metric label="现有住房套数" value={`${derivedExistingHomeCount} 套`} />
              <Metric label="现有房贷笔数" value={`${derivedExistingMortgageCount} 笔`} />
            </div>
          </div>
          <div className="profile-config-block">
            <strong>亲属首付支持</strong>
            <div className="family-support-box profile-family-support-box">
              <SwitchField
                label="启用亲属首付支持"
                checked={household.family_provident_support_enabled ?? false}
                onChange={(checked) => updateHousehold("family_provident_support_enabled", checked)}
              />
              {household.family_provident_support_enabled ? (
                <div className="form-grid two">
                  <Field label="支持情景名称">
                    <input
                      value={household.family_provident_support_label ?? (household.family_down_payment_support_mode === "savings" ? "亲属积蓄首付支持" : "亲属异地公积金首付支持")}
                      onChange={(event) => updateHousehold("family_provident_support_label", event.target.value)}
                    />
                  </Field>
                  <Field label="支持资金来源">
                    <select
                      value={household.family_down_payment_support_mode ?? "provident"}
                      onChange={(event) => {
                        const mode = event.target.value as HouseholdData["family_down_payment_support_mode"];
                        updateHousehold("family_down_payment_support_mode", mode);
                        updateHousehold(
                          "family_provident_support_label",
                          mode === "savings" ? "亲属积蓄首付支持" : "亲属异地公积金首付支持"
                        );
                      }}
                    >
                      <option value="savings">亲属积蓄支持</option>
                      <option value="provident">亲属公积金支持</option>
                    </select>
                  </Field>
                  {household.family_down_payment_support_mode === "savings" ? (
                    <NumberField
                      label="可支持首付金额"
                      value={household.family_savings_support_amount ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateHousehold("family_savings_support_amount", value)}
                    />
                  ) : (
                    <>
                      <NumberField
                        label="支持账户当前余额"
                        value={household.family_provident_initial_balance ?? 0}
                        min={0}
                        step={1000}
                        onChange={(value) => updateHousehold("family_provident_initial_balance", value)}
                      />
                      <NumberField
                        label="支持账户月工资"
                        value={household.family_provident_monthly_salary ?? 0}
                        min={0}
                        step={100}
                        onChange={(value) => updateHousehold("family_provident_monthly_salary", value)}
                      />
                      <NumberField
                        label="支持账户双边比例"
                        value={household.family_provident_total_rate ?? 0.24}
                        min={0}
                        max={0.5}
                        step={0.01}
                        onChange={(value) => updateHousehold("family_provident_total_rate", value)}
                      />
                    </>
                  )}
                </div>
              ) : null}
            </div>
          </div>
          <div className="profile-config-block family-member-manager">
            <div className="member-header compact-heading">
              <strong>家庭成员管理</strong>
              <button className="ghost-button" onClick={addIncomeMember} type="button">
                <Plus size={15} /> 新增成员
              </button>
            </div>
            <div className="member-list compact-list profile-member-list">
              {incomeMembers.map((member, index) => (
                <section className="member-card loan-card" key={`profile-member-${index}`}>
                  <div className="member-card-head">
                    <strong>{member.name || `成员 ${index + 1}`}</strong>
                    <button
                      className="icon-button"
                      onClick={() => removeIncomeMember(index)}
                      disabled={incomeMembers.length <= 1}
                      aria-label="删除成员"
                      title="删除成员"
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                  <div className="profile-member-fields">
                    <Field label="成员名称">
                      <input
                        value={member.name}
                        onChange={(event) => updateIncomeMember(index, "name", event.target.value)}
                      />
                    </Field>
                    <Field label="性别">
                      <select
                        value={member.sex ?? "unspecified"}
                        onChange={(event) => updateIncomeMember(index, "sex", event.target.value as IncomeMember["sex"])}
                      >
                        {Object.entries(memberSexLabels).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="加入家庭月份">
                      <input
                        type="month"
                        value={member.family_join_month ?? "2026-07"}
                        onChange={(event) => updateIncomeMember(index, "family_join_month", event.target.value)}
                      />
                    </Field>
                    <Field label="出生年月">
                      <input
                        type="month"
                        value={member.birth_month ?? ""}
                        onChange={(event) => updateIncomeMember(index, "birth_month", event.target.value)}
                      />
                    </Field>
                    <Field label="退休身份">
                      <select
                        value={normalizeRetirementCategoryForSex(member.retirement_category, member.sex, index)}
                        onChange={(event) => updateIncomeMember(index, "retirement_category", event.target.value as IncomeMember["retirement_category"])}
                      >
                        {retirementCategoryOptionsForSex(member.sex).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                      <p className="field-hint">
                        {member.sex === "unspecified"
                          ? "先选择性别后，系统会自动收窄可选退休身份并同步退休年龄。"
                          : "退休年龄由性别、退休身份和政策规则共同决定。"}
                      </p>
                    </Field>
                    <div className="derived-field">
                      <span>当前年龄</span>
                      <strong>{member.birth_month ? `${memberAges[index] ?? member.current_age ?? 30} 岁` : "填写出生年月后自动计算"}</strong>
                    </div>
                    <NumberField
                      label="社保月数"
                      value={member.social_security_months ?? 0}
                      min={0}
                      step={1}
                      onChange={(value) => updateIncomeMember(index, "social_security_months", value)}
                    />
                    <NumberField
                      label="个税月数"
                      value={member.income_tax_months ?? 0}
                      min={0}
                      step={1}
                      onChange={(value) => updateIncomeMember(index, "income_tax_months", value)}
                    />
                    <NumberField
                      label="已有住房套数"
                      value={member.existing_home_count ?? 0}
                      min={0}
                      max={10}
                      step={1}
                      onChange={(value) => updateIncomeMember(index, "existing_home_count", value)}
                    />
                    <NumberField
                      label="已有房贷笔数"
                      value={member.existing_mortgage_count ?? 0}
                      min={0}
                      max={10}
                      step={1}
                      onChange={(value) => updateIncomeMember(index, "existing_mortgage_count", value)}
                    />
                    <NumberField
                      label="加入时现金"
                      value={member.initial_cash_balance ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateIncomeMember(index, "initial_cash_balance", value)}
                    />
                    <NumberField
                      label="加入时投资资产"
                      value={member.initial_investments ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateIncomeMember(index, "initial_investments", value)}
                    />
                    <NumberField
                      label="加入时公积金余额"
                      value={member.provident_fund_balance ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateIncomeMember(index, "provident_fund_balance", value)}
                    />
                    <NumberField
                      label="加入时其他资产"
                      value={member.initial_other_asset_value ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateIncomeMember(index, "initial_other_asset_value", value)}
                    />
                    <NumberField
                      label="加入时其他负债"
                      value={member.initial_other_debt_balance ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateIncomeMember(index, "initial_other_debt_balance", value)}
                    />
                  </div>
                  <div className="member-subsection policy-account-subsection">
                    <div className="member-header compact-heading">
                      <strong>成员政策账户</strong>
                    </div>
                    <div className="policy-account-grid">
                      <section className="member-card nested-account-card policy-account-card">
                        <div className="member-card-head">
                          <strong>住房公积金账户</strong>
                          <SwitchField label={member.provident_account_enabled ? "已开通" : "未开通"} checked={member.provident_account_enabled ?? true} onChange={(checked) => updateIncomeMember(index, "provident_account_enabled", checked)} />
                        </div>
                        <div className="form-grid three">
                          <Field label="开户月份">
                            <input type="month" value={member.provident_account_open_month || member.family_join_month || ""} onChange={(event) => updateIncomeMember(index, "provident_account_open_month", event.target.value)} />
                          </Field>
                          <NumberField label="当前余额" value={member.provident_fund_balance ?? 0} min={0} step={1000} onChange={(value) => updateIncomeMember(index, "provident_fund_balance", value)} />
                        </div>
                        <p className="field-hint">账户是否存在、开户月份和当前余额在这里管理；每月缴存额由收入阶段的工资、公积金比例和市管/国管规则计算。</p>
                      </section>
                      <section className="member-card nested-account-card policy-account-card">
                        <div className="member-card-head">
                          <strong>基本养老保险个人账户</strong>
                          <SwitchField label={member.pension_account_enabled ? "已开通" : "未开通"} checked={member.pension_account_enabled ?? true} onChange={(checked) => updateIncomeMember(index, "pension_account_enabled", checked)} />
                        </div>
                        <div className="form-grid three">
                          <Field label="开户月份">
                            <input type="month" value={member.pension_account_open_month || member.family_join_month || ""} onChange={(event) => updateIncomeMember(index, "pension_account_open_month", event.target.value)} />
                          </Field>
                          <NumberField label="当前余额" value={member.pension_account_balance ?? 0} min={0} step={1000} onChange={(value) => updateIncomeMember(index, "pension_account_balance", value)} />
                        </div>
                        <p className="field-hint">基本养老个人账户缴存来自收入阶段和社保政策；关闭后后端不会继续累计个人账户余额。</p>
                      </section>
                      <section className="member-card nested-account-card policy-account-card">
                        <div className="member-card-head">
                          <strong>基本医保个人账户</strong>
                          <SwitchField label={member.medical_account_enabled ? "已开通" : "未开通"} checked={member.medical_account_enabled ?? true} onChange={(checked) => updateIncomeMember(index, "medical_account_enabled", checked)} />
                        </div>
                        <div className="form-grid three">
                          <Field label="开户月份">
                            <input type="month" value={member.medical_account_open_month || member.family_join_month || ""} onChange={(event) => updateIncomeMember(index, "medical_account_open_month", event.target.value)} />
                          </Field>
                          <NumberField label="当前余额" value={member.medical_account_balance ?? 0} min={0} step={100} onChange={(value) => updateIncomeMember(index, "medical_account_balance", value)} />
                        </div>
                        <p className="field-hint">医保个人账户划入、退休划入和大额互助支出由后端按政策推演，不在这里手工填年度缴存。</p>
                      </section>
                      <section className="member-card nested-account-card policy-account-card">
                        <div className="member-card-head">
                          <strong>个人养老金账户</strong>
                          <SwitchField
                            label={member.personal_pension_account_enabled ? "纳入税务策略" : "不纳入税务策略"}
                            checked={member.personal_pension_account_enabled ?? false}
                            onChange={(checked) => updateIncomeMember(index, "personal_pension_account_enabled", checked)}
                          />
                        </div>
                        <div className="form-grid three">
                          <SwitchField
                            label="已参加基本养老保险且具备个人养老金资格"
                            checked={member.personal_pension_participation_eligible ?? false}
                            disabled={!member.personal_pension_account_enabled || !member.pension_account_enabled}
                            onChange={(checked) => updateIncomeMember(index, "personal_pension_participation_eligible", checked)}
                          />
                          <Field label="开户策略">
                            <select
                              value={member.personal_pension_open_mode ?? (member.personal_pension_account_enabled ? "auto_tax_optimal" : "none")}
                              disabled={!member.personal_pension_account_enabled || !member.personal_pension_participation_eligible}
                              onChange={(event) => {
                                const mode = event.target.value as IncomeMember["personal_pension_open_mode"];
                                updateIncomeMember(index, "personal_pension_open_mode", mode);
                                if (mode === "none") {
                                  updateIncomeMember(index, "personal_pension_contribution_mode", "none");
                                }
                              }}
                            >
                              <option value="auto_tax_optimal">税务策略推荐开户</option>
                              <option value="manual">手动指定开户月</option>
                              <option value="none">暂不开户</option>
                            </select>
                          </Field>
                          <Field label="开户月份">
                            <input
                              type="month"
                              value={member.personal_pension_account_open_month ?? ""}
                              disabled={!member.personal_pension_account_enabled || !member.personal_pension_participation_eligible || (member.personal_pension_open_mode ?? "none") !== "manual"}
                              onChange={(event) => updateIncomeMember(index, "personal_pension_account_open_month", event.target.value)}
                            />
                          </Field>
                          <NumberField label="当前余额" value={member.personal_pension_account_balance ?? 0} min={0} step={1000} onChange={(value) => updateIncomeMember(index, "personal_pension_account_balance", value)} />
                          <Field label="税务缴存策略">
                            <select
                              value={member.personal_pension_contribution_mode ?? "auto_tax_optimal"}
                              onChange={(event) => updateIncomeMember(index, "personal_pension_contribution_mode", event.target.value as IncomeMember["personal_pension_contribution_mode"])}
                              disabled={!member.personal_pension_account_enabled || !member.personal_pension_participation_eligible || (member.personal_pension_open_mode ?? "none") === "none"}
                            >
                              <option value="none">暂不缴存</option>
                              <option value="auto_tax_optimal">税务策略自动制定</option>
                              <option value="fixed_monthly">手动固定月缴存</option>
                              <option value="fixed_annual">手动年度目标</option>
                            </select>
                          </Field>
                          <Field label="开始月份">
                            <input type="month" value={member.personal_pension_contribution_start_month ?? ""} disabled={!member.personal_pension_account_enabled || !member.personal_pension_participation_eligible || member.personal_pension_contribution_mode === "none" || member.personal_pension_contribution_mode === "auto_tax_optimal"} onChange={(event) => updateIncomeMember(index, "personal_pension_contribution_start_month", event.target.value)} />
                          </Field>
                          <Field label="结束月份">
                            <input type="month" value={member.personal_pension_contribution_end_month ?? ""} disabled={!member.personal_pension_account_enabled || !member.personal_pension_participation_eligible || member.personal_pension_contribution_mode === "none"} onChange={(event) => updateIncomeMember(index, "personal_pension_contribution_end_month", event.target.value || null)} />
                          </Field>
                          <Field label="税前扣除申报方式">
                            <select value={member.personal_pension_tax_deduction_mode ?? "monthly_withholding"} disabled={!member.personal_pension_account_enabled || !member.personal_pension_participation_eligible} onChange={(event) => updateIncomeMember(index, "personal_pension_tax_deduction_mode", event.target.value as IncomeMember["personal_pension_tax_deduction_mode"])}>
                              <option value="monthly_withholding">随实际缴费当期预扣扣除</option>
                              <option value="annual_settlement">年度汇算扣除</option>
                            </select>
                          </Field>
                          <SwitchField label="现金不足时自动暂停缴费" checked={member.personal_pension_auto_suspend_for_cash_safety ?? true} onChange={(checked) => updateIncomeMember(index, "personal_pension_auto_suspend_for_cash_safety", checked)} />
                          <NumberField label="缴费现金安全垫月数" value={member.personal_pension_cash_reserve_months ?? 6} min={0} max={36} step={1} onChange={(value) => updateIncomeMember(index, "personal_pension_cash_reserve_months", Math.round(value))} />
                          {member.personal_pension_contribution_mode === "fixed_monthly" ? (
                            <NumberField label="固定月缴存" value={member.personal_pension_monthly_contribution ?? 0} min={0} max={personalPensionAnnualCap} step={100} onChange={(value) => updateIncomeMember(index, "personal_pension_monthly_contribution", Math.min(personalPensionAnnualCap, value))} />
                          ) : null}
                          {member.personal_pension_contribution_mode === "fixed_annual" ? (
                            <>
                              <NumberField label="年度目标金额" value={member.personal_pension_annual_contribution_target ?? 0} min={0} max={personalPensionAnnualCap} step={1000} onChange={(value) => updateIncomeMember(index, "personal_pension_annual_contribution_target", Math.min(personalPensionAnnualCap, value))} />
                              <NumberField label="集中缴存月份" value={member.personal_pension_contribution_month ?? 12} min={1} max={12} step={1} onChange={(value) => updateIncomeMember(index, "personal_pension_contribution_month", Math.round(value))} />
                            </>
                          ) : null}
                          <Field label="收益率策略">
                            <select value={member.personal_pension_return_mode ?? "auto_lifecycle"} onChange={(event) => updateIncomeMember(index, "personal_pension_return_mode", event.target.value as IncomeMember["personal_pension_return_mode"])}>
                              <option value="auto_lifecycle">生命周期自动降风险</option>
                              <option value="manual">全周期固定收益假设</option>
                            </select>
                          </Field>
                          {(member.personal_pension_return_mode ?? "auto_lifecycle") === "auto_lifecycle" ? (
                            <div className="form-panel compact-card income-span-full">
                              <div className="member-card-head">
                                <strong>个人养老金收益率监测</strong>
                                <button className="ghost-button" type="button" disabled={refreshingPersonalPensionReturns} onClick={() => void refreshPersonalPensionReturns(true)}>
                                  <RefreshCw size={15} className={refreshingPersonalPensionReturns ? "spin" : undefined} />
                                  {refreshingPersonalPensionReturns ? "正在更新" : "立即抓取并校正"}
                                </button>
                              </div>
                              <div className="read-only-grid">
                                <Metric label="退休前年化假设" value={percent(personalPensionReturnSnapshot?.data.pre_retirement_annual_return ?? 0.025)} />
                                <Metric label="退休后年化假设" value={percent(personalPensionReturnSnapshot?.data.post_retirement_annual_return ?? 0.015)} />
                                <Metric label="有效来源" value={`${personalPensionReturnSnapshot?.data.parsed_source_count ?? 0} / ${personalPensionReturnSnapshot?.data.source_count ?? 0}`} />
                                <Metric label="快照日期" value={personalPensionReturnSnapshot?.data.snapshot_date ?? "尚未抓取"} tone={personalPensionReturnSnapshot ? "good" : "warn"} />
                                <Metric label="下次检查" value={personalPensionReturnSnapshot?.data.next_due_date ?? "打开页面后检查"} />
                              </div>
                              <p className="field-hint">自动模式使用政策边界和多来源产品市场数据，单次修正幅度受限；网页短期涨跌不会直接外推为长期保证收益。</p>
                              {personalPensionReturnSnapshot?.data.evidence.length ? (
                                <div className="warning-list">
                                  {personalPensionReturnSnapshot.data.evidence.map((item) => (
                                    <span key={item.source_url}>
                                      <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_name}</a>
                                      ：{item.status === "parsed" && item.observed_annual_return !== null ? `识别到 ${percent(item.observed_annual_return)}（${item.sample_count} 个样本）` : item.status === "fetch_failed" ? "本次抓取失败，未参与校正" : "未发现可安全解析的收益率"}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ) : (
                            <>
                              <NumberField label="退休前产品年化" value={member.personal_pension_annual_return ?? 0.025} min={-0.5} max={0.5} step={0.005} onChange={(value) => updateIncomeMember(index, "personal_pension_annual_return", value)} />
                              <NumberField label="退休后产品年化" value={member.personal_pension_post_retirement_annual_return ?? 0.015} min={-0.5} max={0.5} step={0.005} onChange={(value) => updateIncomeMember(index, "personal_pension_post_retirement_annual_return", value)} />
                            </>
                          )}
                          <Field label="退休领取策略">
                            <select value={member.personal_pension_withdrawal_mode ?? "auto_safe"} onChange={(event) => updateIncomeMember(index, "personal_pension_withdrawal_mode", event.target.value as IncomeMember["personal_pension_withdrawal_mode"])}>
                              <option value="auto_safe">现金安全优先动态领取</option>
                              <option value="monthly_annuity">按年限均匀领取</option>
                              <option value="fixed_monthly">固定每月领取</option>
                              <option value="lump_sum">退休时一次性领取</option>
                            </select>
                          </Field>
                          <Field label="开始领取月份">
                            <input type="month" value={member.personal_pension_withdrawal_start_month ?? ""} onChange={(event) => updateIncomeMember(index, "personal_pension_withdrawal_start_month", event.target.value)} />
                          </Field>
                          <Field label="法定提前领取事由">
                            <select value={member.personal_pension_early_withdrawal_reason ?? "none"} onChange={(event) => updateIncomeMember(index, "personal_pension_early_withdrawal_reason", event.target.value as IncomeMember["personal_pension_early_withdrawal_reason"])}>
                              <option value="none">无，按退休条件领取</option>
                              <option value="total_disability">完全丧失劳动能力</option>
                              <option value="settled_abroad">出国（境）定居</option>
                              <option value="major_medical_expense">符合政策标准的重大医疗支出</option>
                              <option value="long_unemployment">两年内领取失业保险金累计满12个月</option>
                              <option value="minimum_living_allowance">正在领取城乡最低生活保障金</option>
                            </select>
                          </Field>
                          {member.personal_pension_early_withdrawal_reason !== "none" ? (
                            <Field label="预计满足提前领取条件月份">
                              <input type="month" value={member.personal_pension_early_withdrawal_month ?? ""} onChange={(event) => updateIncomeMember(index, "personal_pension_early_withdrawal_month", event.target.value)} />
                            </Field>
                          ) : null}
                          {(member.personal_pension_withdrawal_mode ?? "auto_safe") === "auto_safe" || member.personal_pension_withdrawal_mode === "monthly_annuity" ? (
                            <NumberField label="计划领取年数" value={member.personal_pension_withdrawal_years ?? 20} min={1} max={40} step={1} onChange={(value) => updateIncomeMember(index, "personal_pension_withdrawal_years", Math.round(value))} />
                          ) : null}
                          {member.personal_pension_withdrawal_mode === "fixed_monthly" ? (
                            <NumberField label="固定每月领取" value={member.personal_pension_fixed_monthly_withdrawal ?? 0} min={0} step={100} onChange={(value) => updateIncomeMember(index, "personal_pension_fixed_monthly_withdrawal", value)} />
                          ) : null}
                          <Field label="产品流动性">
                            <select value={member.personal_pension_product_liquidity_mode ?? "daily_liquid"} onChange={(event) => updateIncomeMember(index, "personal_pension_product_liquidity_mode", event.target.value as IncomeMember["personal_pension_product_liquidity_mode"])}>
                              <option value="daily_liquid">可按领取申请正常变现</option>
                              <option value="periodic">定期开放或存在赎回周期</option>
                              <option value="locked_until_maturity">到期前受限</option>
                            </select>
                          </Field>
                          <NumberField label="领取到账延迟月数" value={member.personal_pension_redemption_delay_months ?? 0} min={0} max={120} step={1} onChange={(value) => updateIncomeMember(index, "personal_pension_redemption_delay_months", Math.round(value))} />
                          <NumberField label="每月最多可变现比例" value={member.personal_pension_monthly_redeemable_ratio ?? 1} min={0} max={1} step={0.05} onChange={(value) => updateIncomeMember(index, "personal_pension_monthly_redeemable_ratio", value)} />
                          <NumberField label="赎回或退保费用率" value={member.personal_pension_redemption_fee_rate ?? 0} min={0} max={0.5} step={0.005} onChange={(value) => updateIncomeMember(index, "personal_pension_redemption_fee_rate", value)} />
                        </div>
                        <p className="field-hint">个人养老金为自愿参加且封闭运行的账户，只有参加基本养老保险并实际开户后才能缴费。全年实际缴费不得超过政策上限；集中缴费只在实际缴费月或年度汇算时产生扣除。提前领取必须选择法定事由，普通现金不足不能触发提前支取；实际到账还受所购产品期限、赎回比例和费用约束。收益率仅为规划假设，不代表保证收益。</p>
                      </section>
                    </div>
                  </div>
                </section>
              ))}
            </div>
          </div>
          <p className="field-hint">
            家庭画像先维护成员组成、出生年月、加入家庭时间以及加入时资产负债；家庭社保/个税月数、已有住房和已有房贷会从成员信息汇总显示。借款申请人年龄会自动跟随所选成员。
          </p>
        </section>
      </div>

      {memberIncomeSection}

      <div className="income-detail-grid">
      <section className="form-panel income-workbench-card expense-panel">
        <div className="member-header">
          <PanelTitle icon={<WalletCards size={18} />} title="家庭支出" collapsible />
          <div className="header-actions">
            <button className="ghost-button" onClick={addDailyExpenseStage}>
              <Plus size={16} /> 新增日常阶段
            </button>
            <button className="ghost-button" onClick={addRentExpenseStage}>
              <Plus size={16} /> 新增租房阶段
            </button>
            <button className="ghost-button" onClick={addScheduledExpense}>
              <Plus size={16} /> 新增计划支出
            </button>
            <button className="ghost-button" onClick={addAnnualScheduledExpense}>
              <Plus size={16} /> 新增年度支出
            </button>
            <button className="ghost-button" onClick={addOneTimeScheduledExpense}>
              <Plus size={16} /> 新增一次性支出
            </button>
          </div>
        </div>
        <div className="loan-summary-strip">
          <Metric label="当前日常月支出" value={money(dailyExpenseStageAt(household, today)?.base_living_expense ?? household.monthly_expense)} />
          <Metric label="当前租房现金支出" value={money(currentRentCashCost)} />
          <Metric label="当前实际月支出" value={money(currentMonthlyExpense)} />
          <Metric
            label="本月计划支出"
            value={money(scheduledExpenseRowsAt(household, today, 0).reduce((sum, item) => sum + item.amount, 0))}
          />
        </div>
        <div className="member-header compact-heading">
          <strong>日常家庭支出阶段</strong>
        </div>
        <div className="member-list compact-list">
          {dailyExpenseStages.map((stage, index) => (
            <section className="member-card loan-card" key={`daily-expense-stage-${index}`}>
              <div className="member-card-head">
                <strong>{stage.name || `日常支出阶段 ${index + 1}`}</strong>
                <button
                  className="icon-button"
                  onClick={() => removeDailyExpenseStage(index)}
                  disabled={dailyExpenseStages.length <= 1}
                  aria-label="删除日常支出阶段"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="form-grid">
                <Field label="阶段名称">
                  <input
                    value={stage.name}
                    onChange={(event) => updateDailyExpenseStage(index, "name", event.target.value)}
                  />
                </Field>
                <Field label="开始月份">
                  <input
                    type="month"
                    value={stage.start_month}
                    onChange={(event) => updateDailyExpenseStage(index, "start_month", event.target.value)}
                  />
                </Field>
                <Field label="结束月份">
                  <input
                    type="month"
                    value={stage.end_month ?? ""}
                    onChange={(event) => updateDailyExpenseStage(index, "end_month", event.target.value || null)}
                  />
                </Field>
                <NumberField
                  label="日常月支出"
                  value={stage.base_living_expense}
                  min={0}
                  step={100}
                  onChange={(value) => updateDailyExpenseStage(index, "base_living_expense", value)}
                />
              </div>
              <p className="expense-note-display">
                日常家庭支出用于生活消费、餐饮、交通、日用品等持续性现金支出；租房、已有贷款和年度/一次性大额支出在下面单独配置。
              </p>
            </section>
          ))}
        </div>
        <div className="member-header compact-heading">
          <strong>租房支出阶段</strong>
        </div>
        <div className="member-list compact-list">
          {rentExpenseStages.map((stage, index) => (
            <section className="member-card loan-card" key={`rent-expense-stage-${index}`}>
              <div className="member-card-head">
                <strong>{stage.name || `租房支出阶段 ${index + 1}`}</strong>
                <button
                  className="icon-button"
                  onClick={() => removeRentExpenseStage(index)}
                  disabled={rentExpenseStages.length <= 1}
                  aria-label="删除租房支出阶段"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="form-grid">
                <Field label="阶段名称">
                  <input
                    value={stage.name}
                    onChange={(event) => updateRentExpenseStage(index, "name", event.target.value)}
                  />
                </Field>
                <Field label="开始月份">
                  <input
                    type="month"
                    value={stage.start_month}
                    onChange={(event) => updateRentExpenseStage(index, "start_month", event.target.value)}
                  />
                </Field>
                <Field label="结束月份">
                  <input
                    type="month"
                    value={stage.end_month ?? ""}
                    onChange={(event) => updateRentExpenseStage(index, "end_month", event.target.value || null)}
                  />
                </Field>
                <NumberField
                  label="租金月额"
                  value={stage.rent_amount}
                  min={0}
                  step={100}
                  onChange={(value) => updateRentExpenseStage(index, "rent_amount", value)}
                />
                <NumberField
                  label="中介费月数"
                  value={stage.broker_fee_months ?? 1}
                  min={0}
                  max={12}
                  step={0.5}
                  onChange={(value) => updateRentExpenseStage(index, "broker_fee_months", value)}
                />
                <NumberField
                  label="固定中介费"
                  value={stage.broker_fee_amount ?? 0}
                  min={0}
                  step={100}
                  onChange={(value) => updateRentExpenseStage(index, "broker_fee_amount", value > 0 ? value : null)}
                />
                <NumberField
                  label="首年服务费率"
                  value={stage.service_fee_first_year_rate ?? 0.09}
                  min={0}
                  max={1}
                  step={0.01}
                  onChange={(value) => updateRentExpenseStage(index, "service_fee_first_year_rate", value)}
                />
                <NumberField
                  label="后续服务费率"
                  value={stage.service_fee_later_year_rate ?? 0.06}
                  min={0}
                  max={1}
                  step={0.01}
                  onChange={(value) => updateRentExpenseStage(index, "service_fee_later_year_rate", value)}
                />
                <Field label="租房支付方式">
                  <select
                    value={stage.rent_payment_mode}
                    onChange={(event) => updateRentExpenseStage(index, "rent_payment_mode", event.target.value as RentExpenseStageData["rent_payment_mode"])}
                  >
                    <option value="cash">现金付房租</option>
                    <option value="provident">公积金余额付房租</option>
                  </select>
                </Field>
                <Field label="租房支付频率">
                  <select
                    value={stage.rent_payment_frequency ?? "monthly"}
                    onChange={(event) => updateRentExpenseStage(index, "rent_payment_frequency", event.target.value as RentExpenseStageData["rent_payment_frequency"])}
                  >
                    <option value="monthly">月付</option>
                    <option value="quarterly">季付</option>
                  </select>
                </Field>
              </div>
              <p className="expense-note-display">
                {stage.rent_payment_mode === "provident"
                  ? `该阶段租金按公积金租房提取处理，后端按${stage.rent_payment_frequency === "quarterly" ? "季付" : "月付"}节奏进入公积金账户流水；中介费和服务费仍作为现金支出。`
                  : `该阶段租金按${stage.rent_payment_frequency === "quarterly" ? "季付" : "月付"}节奏进入现金家庭支出；开始月另计中介费，服务费第一年 ${percent(stage.service_fee_first_year_rate ?? 0.09)}、后续 ${percent(stage.service_fee_later_year_rate ?? 0.06)}。`}
              </p>
            </section>
          ))}
        </div>
        <div className="member-header compact-heading">
          <strong>阶段性、年度与一次性支出</strong>
        </div>
        <div className="member-list compact-list">
          {scheduledExpenses.map((expense, index) => {
            const scheduledExpenseCategory = expense.expense_category ?? (expense.medical_account_payable ? "medical" : "general");
            const scheduledExpenseMedicalPayable = scheduledExpenseCategory === "medical" && (expense.medical_account_payable ?? false);
            return (
            <section className="member-card loan-card" key={`scheduled-expense-${index}`}>
              <div className="member-card-head">
                <strong>{expense.name || "计划支出"}</strong>
                <button
                  className="icon-button"
                  onClick={() => removeScheduledExpense(index)}
                  aria-label="删除计划支出"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="form-grid">
                <Field label="支出名称">
                  <input
                    value={expense.name}
                    onChange={(event) => updateScheduledExpense(index, "name", event.target.value)}
                  />
                </Field>
                <Field label="发生频率">
                  <select
                    value={expense.frequency ?? "monthly"}
                    onChange={(event) => {
                      const frequency = event.target.value as ScheduledExpenseData["frequency"];
                      updateScheduledExpense(index, "frequency", frequency);
                    }}
                  >
                    <option value="monthly">每月发生</option>
                    <option value="annual_once">一年一次</option>
                    <option value="one_time">一次性支出</option>
                  </select>
                </Field>
                <NumberField
                  label={(expense.frequency ?? "monthly") === "monthly" ? "每月金额" : "单次金额"}
                  value={expense.monthly_amount}
                  min={0}
                  step={100}
                  onChange={(value) => updateScheduledExpense(index, "monthly_amount", value)}
                />
                {(expense.frequency ?? "monthly") === "annual_once" ? (
                  <NumberField
                    label="年度发生月份"
                    value={expense.annual_occurrence_month ?? Number(expense.start_month?.slice(5, 7) || 1)}
                    min={1}
                    max={12}
                    step={1}
                    onChange={(value) => updateScheduledExpense(index, "annual_occurrence_month", Math.max(1, Math.min(12, Math.round(value || 1))))}
                  />
                ) : null}
                {(expense.frequency ?? "monthly") === "one_time" ? (
                  <Field label="时间安排">
                    <select
                      value={expense.one_time_timing_mode ?? "fixed_month"}
                      onChange={(event) => updateScheduledExpense(index, "one_time_timing_mode", event.target.value as ScheduledExpenseData["one_time_timing_mode"])}
                    >
                      <option value="fixed_month">指定月份</option>
                      <option value="flexible_range">给时间范围由策略安排</option>
                    </select>
                  </Field>
                ) : null}
                <Field label={(expense.frequency ?? "monthly") === "one_time" && (expense.one_time_timing_mode ?? "fixed_month") === "fixed_month" ? "发生月份" : "开始月份"}>
                  <input
                    type="month"
                    value={expense.start_month}
                    onChange={(event) => updateScheduledExpense(index, "start_month", event.target.value)}
                  />
                </Field>
                <Field label={(expense.frequency ?? "monthly") === "one_time" && (expense.one_time_timing_mode ?? "fixed_month") === "flexible_range" ? "最晚月份" : "结束月份"}>
                  <input
                    type="month"
                    value={expense.end_month ?? ""}
                    disabled={(expense.frequency ?? "monthly") === "one_time" && (expense.one_time_timing_mode ?? "fixed_month") === "fixed_month"}
                    onChange={(event) => updateScheduledExpense(index, "end_month", event.target.value || null)}
                  />
                </Field>
                <Field label="支出口径">
                  <select
                    value={scheduledExpenseCategory}
                    onChange={(event) => {
                      const expenseCategory = event.target.value as ScheduledExpenseData["expense_category"];
                      updateScheduledExpensePatch(index, {
                        expense_category: expenseCategory,
                        medical_account_payable: expenseCategory === "medical" ? expense.medical_account_payable ?? false : false
                      });
                    }}
                  >
                    <option value="general">普通家庭支出</option>
                    <option value="medical">医疗支出</option>
                  </select>
                </Field>
                {scheduledExpenseCategory === "medical" ? (
                  <>
                    <SwitchField
                      label="使用医保个人账户支付"
                      checked={scheduledExpenseMedicalPayable}
                      onChange={(checked) => updateScheduledExpense(index, "medical_account_payable", checked)}
                    />
                    <p className="field-hint form-grid-note">
                      仅对明确属于医保个人账户可支付的医疗支出生效。关闭时整项医疗支出进入现金支出；开启后医保余额不足的部分仍进入现金支出。
                    </p>
                  </>
                ) : null}
              </div>
              <p className="expense-note-display">
                {expense.notes || ((expense.frequency ?? "monthly") === "one_time" && (expense.one_time_timing_mode ?? "fixed_month") === "flexible_range"
                  ? "一次性支出给出时间范围后，后端会先按保守策略安排到范围内较晚月份，减少对购房买车现金池的挤压。"
                  : scheduledExpenseMedicalPayable
                    ? "这项支出会先从医保个人账户余额支付，余额不足部分才进入现金账户支出；它不自动认定为个税专项扣除。"
                    : "这项支出只作为家庭现金支出，不自动认定为个税专项扣除。")}
              </p>
            </section>
            );
          })}
        </div>
        <p className="field-hint">
          日常家庭支出和租房支出分别按阶段生效。现金付房租会进入现金家庭支出；公积金余额付房租会按租房提取口径进入公积金账户流水。其它阶段性支出、每月固定支出、年度支出和一次性大额支出统一放在计划支出里，不会错误摊平到每个月。老人专项附加扣除由下方“赡养老人专项扣除”的出生月份、归属成员和分摊方式自动判断，{elderlyPolicyStatus.detail}
        </p>
      </section>

      {assetCashSection}

      <section className="form-panel income-workbench-card career-panel">
        <PanelTitle icon={<AlertTriangle size={18} />} title="职业冲击自缴支出规则" collapsible />
        <div className="loan-summary-strip">
          <Metric label="启用职业冲击成员" value={careerShockSummaryText} tone={activeCareerShockSettings.length > 0 ? "warn" : undefined} />
          <Metric label="失业金月数" value={`${estimatedUnemploymentBenefitMonths} 个月`} />
          <Metric label="自缴社保/月" value={money(estimatedSelfSocialInsuranceMonthly)} />
          <Metric label="自缴公积金/月" value={money(estimatedFlexibleHousingFundMonthly)} />
        </div>
        <CollapsibleSettingGroup title="后端自动估算口径">
          <div className="switch-grid">
            <SwitchField
              label="自动估算失业保险待遇"
              checked={careerShock.auto_unemployment_benefit}
              onChange={(checked) => updateCareerShock({ auto_unemployment_benefit: checked })}
            />
            <SwitchField
              label="自动估算灵活就业社保"
              checked={careerShock.auto_self_social_insurance}
              onChange={(checked) => updateCareerShock({ auto_self_social_insurance: checked })}
            />
            <SwitchField
              label="自动估算灵活就业公积金"
              checked={careerShock.auto_flexible_housing_fund}
              onChange={(checked) => updateCareerShock({ auto_flexible_housing_fund: checked })}
            />
          </div>
          {!careerShock.auto_unemployment_benefit || !careerShock.auto_self_social_insurance || !careerShock.auto_flexible_housing_fund ? (
            <div className="form-grid structured-settings">
              {!careerShock.auto_unemployment_benefit ? (
                <>
                  <NumberField label="失业金月数" value={careerShock.unemployment_benefit_months} min={0} max={24} step={1} onChange={(value) => updateCareerShock({ unemployment_benefit_months: value })} />
                  <NumberField label="失业金月额" value={careerShock.unemployment_benefit_monthly} min={0} step={100} onChange={(value) => updateCareerShock({ unemployment_benefit_monthly: value })} />
                </>
              ) : null}
              {!careerShock.auto_self_social_insurance ? (
                <NumberField label="自缴社保/月" value={careerShock.self_social_insurance_monthly} min={0} step={100} onChange={(value) => updateCareerShock({ self_social_insurance_monthly: value })} />
              ) : null}
              {!careerShock.auto_flexible_housing_fund ? (
                <NumberField label="自缴公积金/月" value={careerShock.self_housing_fund_monthly} min={0} step={100} onChange={(value) => updateCareerShock({ self_housing_fund_monthly: value })} />
              ) : null}
            </div>
          ) : null}
          <p className="field-hint">
            成员是否启用职业冲击、裁员年龄、冲击期自由职业收入和手动养老金，已经合并到上方“成员工资与收入阶段”的职业冲击收入阶段。这里仅配置无法由成员阶段表达的全局政策估算口径；自缴社保和自缴公积金会作为按人月度家庭支出进入后端现金流和可视化。
          </p>
        </CollapsibleSettingGroup>
      </section>

      <section className="form-panel income-workbench-card elderly-panel">
        <div className="member-header">
          <PanelTitle icon={<ShieldCheck size={18} />} title="赡养老人专项扣除" collapsible />
          <button className="ghost-button" onClick={addElderlyDependent}>
            <Plus size={16} /> 新增老人
          </button>
        </div>
        <div className="member-list compact-list">
          {elderlyDependents.map((dependent, index) => {
            const startMonth = elderlyDeductionStartMonth(dependent);
            const monthlyDeduction = dependent.is_only_child
              ? 3000
              : Math.min(Math.max(0, dependent.shared_monthly_deduction ?? 1500), 1500);
            return (
              <section className="member-card loan-card" key={`elderly-dependent-${index}`}>
                <div className="member-card-head">
                  <strong>{dependent.relationship_label || "直系亲属老人"}</strong>
                  <button
                    className="icon-button"
                    onClick={() => removeElderlyDependent(index)}
                    aria-label="删除老人"
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="form-grid">
                  <Field label="归属成员">
                    <select
                      value={dependent.member_name}
                      onChange={(event) => updateElderlyDependent(index, "member_name", event.target.value)}
                    >
                      {incomeMembers.map((member, memberIndex) => (
                        <option key={`elderly-owner-${memberIndex}`} value={member.name}>
                          {member.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="称谓">
                    <input
                      value={dependent.relationship_label}
                      onChange={(event) => updateElderlyDependent(index, "relationship_label", event.target.value)}
                    />
                  </Field>
                  <Field label="出生月份">
                    <input
                      type="month"
                      value={dependent.birth_month}
                      onChange={(event) => updateElderlyDependent(index, "birth_month", event.target.value)}
                    />
                  </Field>
                  <SwitchField
                    label="独生子女"
                    checked={dependent.is_only_child}
                    onChange={(checked) => updateElderlyDependent(index, "is_only_child", checked)}
                  />
                  <NumberField
                    label="本人分摊扣除"
                    value={dependent.shared_monthly_deduction ?? 1500}
                    min={0}
                    max={3000}
                    step={100}
                    onChange={(value) => updateElderlyDependent(index, "shared_monthly_deduction", value)}
                  />
                </div>
                <div className="read-only-grid">
                  <Metric label="当前年龄" value={formatAgeFromBirthMonth(dependent.birth_month)} />
                  <Metric
                    label="预计生效"
                    value={startMonth ? `${startMonth.year}年${startMonth.month}月` : "待填写"}
                    tone={startMonth ? "good" : "warn"}
                  />
                  <Metric label="月扣除额" value={money(monthlyDeduction)} />
                </div>
              </section>
            );
          })}
        </div>
        <p className="field-hint">
          老人从年满 60 周岁的当月开始满足赡养老人专项附加扣除条件。常见用法：独生子女由对应成员每月扣 3000；非独生子女在兄弟姐妹间分摊 3000，当前成员尽量按本人上限 1500 申报。扣除归属应按真实亲属关系和政策口径填写。
        </p>
      </section>

      <section className="form-panel income-workbench-card current-loans-panel income-span-full">
        <div className="member-header">
          <PanelTitle icon={<WalletCards size={18} />} title="已有贷款" collapsible />
          <button className="ghost-button" onClick={addPhasedLoan}>
            <Plus size={16} /> 新增贷款
          </button>
        </div>
        <div className="loan-summary-strip">
          <Metric label="已有贷款笔数" value={`${phasedLoans.length} 笔`} tone={phasedLoans.length > 0 ? "good" : undefined} />
          <Metric label="当前阶段分布" value={phasedLoanSummaryText} />
        </div>
        <div className="member-list compact-list">
          {phasedLoans.map((loan, index) => {
            const summary = result?.phased_loan_summaries?.[index];
            return (
              <section className="member-card loan-card" key={`phased-loan-${index}`}>
                <div className="member-card-head">
                  <strong>{index + 1}. {loan.name || "已有贷款"} · {existingLoanTypeLabels[loan.loan_type ?? "other"]} · {summary?.phase ?? "待计算"}</strong>
                  <button
                    className="icon-button"
                    onClick={() => removePhasedLoan(index)}
                    aria-label="删除已有贷款"
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="form-grid">
                  <Field label="借款人">
                    <input
                      value={loan.borrower}
                      onChange={(event) => updatePhasedLoan(index, "borrower", event.target.value)}
                    />
                  </Field>
                  <Field label="贷款名称">
                    <input
                      value={loan.name}
                      onChange={(event) => updatePhasedLoan(index, "name", event.target.value)}
                    />
                  </Field>
                  <Field label="贷款类型">
                    <select
                      value={loan.loan_type ?? "other"}
                      onChange={(event) =>
                        updatePhasedLoan(index, "loan_type", event.target.value as NonNullable<PhasedLoanData["loan_type"]>)
                      }
                    >
                      <option value="mortgage">房贷</option>
                      <option value="car">车贷</option>
                      <option value="education">教育贷款</option>
                      <option value="consumer">消费贷款</option>
                      <option value="other">其他贷款</option>
                    </select>
                  </Field>
                  <NumberField
                    label="本金"
                    value={loan.principal}
                    min={0}
                    step={1000}
                    onChange={(value) => updatePhasedLoan(index, "principal", value)}
                  />
                  <NumberField
                    label="年利率"
                    value={loan.annual_rate}
                    min={0}
                    max={0.2}
                    step={0.0005}
                    onChange={(value) => updatePhasedLoan(index, "annual_rate", value)}
                  />
                  <Field label="还款方式">
                    <select
                      value={loan.repayment_method ?? "equal_installment"}
                      onChange={(event) =>
                        updatePhasedLoan(index, "repayment_method", event.target.value as RepaymentMethod)
                      }
                    >
                      <option value="equal_installment">等额本息</option>
                      <option value="equal_principal">等额本金</option>
                    </select>
                  </Field>
                  <NumberField
                    label="剩余期数"
                    value={loan.remaining_months}
                    min={1}
                    max={360}
                    step={1}
                    onChange={(value) => updatePhasedLoan(index, "remaining_months", value)}
                  />
                  <Field label="计息开始月">
                    <input
                      value={loan.interest_start_month}
                      onChange={(event) => updatePhasedLoan(index, "interest_start_month", event.target.value)}
                      placeholder="2026-07"
                    />
                  </Field>
                  <Field label="只还利息至">
                    <input
                      value={loan.interest_only_until}
                      onChange={(event) => updatePhasedLoan(index, "interest_only_until", event.target.value)}
                      placeholder="2028-07"
                    />
                  </Field>
                  <Field label="提前还款模式">
                    <select
                      value={loan.prepayment_mode ?? "none"}
                      onChange={(event) =>
                        updatePhasedLoan(index, "prepayment_mode", event.target.value as PhasedLoanData["prepayment_mode"])
                      }
                    >
                      <option value="none">不提前还款</option>
                      <option value="auto">自动策略</option>
                      <option value="manual">手动设定</option>
                    </select>
                  </Field>
                  {(loan.prepayment_mode ?? "none") !== "none" ? (
                    <>
                      <NumberField
                        label="计划起始还本月"
                        value={loan.prepayment_start_month ?? 1}
                        min={1}
                        max={360}
                        step={1}
                        onChange={(value) => updatePhasedLoan(index, "prepayment_start_month", value)}
                      />
                      <NumberField
                        label="合同允许最早月"
                        value={loan.prepayment_allowed_after_month ?? 1}
                        min={1}
                        max={360}
                        step={1}
                        onChange={(value) => updatePhasedLoan(index, "prepayment_allowed_after_month", value)}
                      />
                      <NumberField
                        label={(loan.prepayment_mode ?? "none") === "manual" ? "每月额外还本" : "自动还本上限/月"}
                        value={loan.prepayment_monthly_amount ?? 0}
                        min={0}
                        step={500}
                        onChange={(value) => updatePhasedLoan(index, "prepayment_monthly_amount", value)}
                      />
                    </>
                  ) : null}
                </div>
                {(loan.prepayment_mode ?? "none") !== "none" ? (
                  <p className="field-hint">
                    已有贷款提前还本会进入后端贷款余额、月供和现金流推演；自动策略会比较贷款利率、理财预期净收益、手续费和现金安全垫，低息贷款不一定提前还，若拖慢买房买车时间也会在策略对比中体现。
                  </p>
                ) : null}
              </section>
            );
          })}
        </div>
        <p className="field-hint">
          “其他固定还款/月”适合没有本金、利率或还款阶段明细的普通月债务；已有贷款适合已发生的房贷、车贷、消费贷、教育贷款等可建模账户。若某笔贷款有“到某月前只还利息、之后等额本息/等额本金”的安排，可填写“计息开始月”和“只还利息至”，后端会按真实月份推演贷款余额、阶段还款和现金流。
        </p>
      </section>
      </div>
    </PlannerPageShell>
  );
}

function PlanningGoalCenterPage({
  household,
  updateHouseholdPatch,
  planningGoals,
  planningSequence,
  coreObjects,
  createGoal,
  duplicateGoal,
  saveGoal,
  deleteGoal,
  refreshGoals,
  openPage,
  saving
}: {
  household: HouseholdData;
  updateHouseholdPatch: (patch: Partial<HouseholdData>) => void;
  planningGoals: PlanningGoalRecord[];
  planningSequence: PlanningSequenceResult | null;
  coreObjects: CoreObjectRecord[];
  createGoal: (goalType: "renovation" | "other") => void;
  duplicateGoal: (goal: PlanningGoalRecord) => void;
  saveGoal: (goalId: string, goalData: PlanningGoalData) => void;
  deleteGoal: (goalId: string) => void;
  refreshGoals: () => void;
  openPage: (page: PageName) => void;
  saving: boolean;
}) {
  type GoalFilter = "all" | PlanningGoalType;
  const [filter, setFilter] = useState<GoalFilter>("all");
  const [activeGoalId, setActiveGoalId] = useState(planningGoals[0]?.id ?? "");
  const [draftGoal, setDraftGoal] = useState<PlanningGoalData | null>(planningGoals[0]?.data ?? null);
  const resolvedGoalById = useMemo(
    () => new Map((planningSequence?.goals ?? []).map((goal) => [goal.id, goal])),
    [planningSequence]
  );
  const planningGoalGroups = useMemo(() => {
    const groups = new Map<string, PlanningGoalRecord[]>();
    planningGoals.forEach((goal) => {
      const key = goal.goal_type === "home" ? `home:${Math.max(1, goal.data.priority)}` : goal.id;
      groups.set(key, [...(groups.get(key) ?? []), goal]);
    });
    return Array.from(groups.entries())
      .map(([key, goals]) => ({
        key,
        goals,
        representative: goals[0],
        resolvedSequence: Math.min(...goals.map((goal) => resolvedGoalById.get(goal.id)?.sequence_index ?? goal.data.priority))
      }))
      .sort((left, right) => left.resolvedSequence - right.resolvedSequence);
  }, [planningGoals, resolvedGoalById]);
  const visibleGoalGroups = useMemo(
    () => filter === "all" ? planningGoalGroups : planningGoalGroups.filter((group) => group.representative.goal_type === filter),
    [filter, planningGoalGroups]
  );
  const selectedGoal = planningGoals.find((goal) => goal.id === activeGoalId)
    ?? visibleGoalGroups[0]?.representative
    ?? planningGoals[0]
    ?? null;
  const selectedGoalGroup = selectedGoal
    ? planningGoalGroups.find((group) => group.goals.some((goal) => goal.id === selectedGoal.id)) ?? null
    : null;
  const selectedGoalGroupGoals = selectedGoalGroup?.goals ?? (selectedGoal ? [selectedGoal] : []);
  const selectedResolvedGoal = selectedGoal ? resolvedGoalById.get(selectedGoal.id) : null;
  const effectiveGoal = draftGoal ?? selectedGoal?.data ?? null;
  const includedGoals = planningGoalGroups.filter((group) => group.goals.some((goal) => goal.data.enabled && goal.data.timing_mode !== "not_planned")).length;
  const genericGoalCount = planningGoalGroups.filter((group) => group.representative.goal_type === "renovation" || group.representative.goal_type === "other").length;
  const selectedCoreObjects = useMemo(
    () => {
      const ownerIds = new Set(selectedGoalGroupGoals.map((goal) => goal.id));
      return coreObjects.filter((object) => ownerIds.has(coreObjectOwnerKey(object)));
    },
    [coreObjects, selectedGoalGroupGoals]
  );
  const selectedCoreObjectSummary = selectedCoreObjects.length
    ? coreObjectOwnerSummaryText(coreObjectOwnerSummaryByOwner(selectedCoreObjects).get(selectedGoal?.id ?? ""))
    : "保存后会进入账户、资产、贷款和目标的统一索引。";
  const dependencyOptions = planningGoalDependencyOptions(
    planningSequence?.goals ?? [],
    new Set(selectedGoalGroupGoals.map((goal) => goal.id))
  );
  const isGenericGoal = selectedGoal?.goal_type === "renovation" || selectedGoal?.goal_type === "other";
  const detailPage: Partial<Record<PlanningGoalType, PageName>> = {
    home: "购房计划",
    vehicle: "购车计划",
    child: "养娃计划"
  };
  const windowLabel = selectedGoal?.goal_type === "child" ? "出生时间段" : selectedGoal?.goal_type === "home" || selectedGoal?.goal_type === "vehicle" ? "需求时间段" : "目标时间段";
  const timingOptions = GENERIC_PLANNING_GOAL_TIMING_OPTIONS.filter((option) => {
    if (option.value === "not_planned") return false;
    if (selectedGoal?.goal_type !== "child") return true;
    return option.value === "auto_sequence" || option.value === "manual_month" || option.value === "after_goal";
  });
  const goalWindowSummary = (goal: PlanningGoalData) => {
    if (!goal.enabled || goal.timing_mode === "not_planned") return "暂不纳入规划";
    const start = goal.planning_window_start_month || "不限";
    const end = goal.planning_window_end_month || "不限";
    return `${start} 至 ${end}`;
  };
  const targetSummary = (goal: PlanningGoalRecord) => {
    const target = goal.data.target_params;
    const directAmount = Number(target.total_price ?? target.estimated_cost ?? target.budget ?? target.amount ?? 0);
    if (directAmount > 0) return money(directAmount);
    if (goal.goal_type === "child") return "阶段支出与税务联动";
    return "详细参数见专业页面";
  };
  const goalGroupTitle = (goals: PlanningGoalRecord[]) => {
    const representative = goals[0];
    if (representative?.goal_type !== "home") return representative?.data.name ?? "规划目标";
    const sequence = Math.max(1, representative.data.priority);
    return sequence === 1 ? "第一套购房需求" : `第 ${sequence} 套购房需求`;
  };
  const homeCandidateSummary = (goals: PlanningGoalRecord[]) =>
    goals.map((goal) => `${goal.data.name}（${targetSummary(goal)}）`).join("、");
  const unifiedTimingPatch = (goal: PlanningGoalData): Partial<PlanningGoalData> => ({
    enabled: goal.enabled,
    priority: goal.priority,
    timing_mode: goal.timing_mode,
    earliest_purchase_month: goal.earliest_purchase_month,
    earliest_purchase_delay_months: goal.earliest_purchase_delay_months,
    planning_window_start_month: goal.planning_window_start_month,
    planning_window_end_month: goal.planning_window_end_month,
    depends_on_goal_id: goal.depends_on_goal_id,
    delay_after_dependency_months: goal.delay_after_dependency_months,
    allow_parallel: goal.allow_parallel
  });
  const updateDraftGoal = (patch: Partial<PlanningGoalData>) => {
    setDraftGoal((current) => current ? { ...current, ...patch } : current);
  };
  const updateDraftTargetParams = (patch: Record<string, unknown>) => {
    setDraftGoal((current) => current ? {
      ...current,
      target_params: { ...current.target_params, ...patch }
    } : current);
  };
  const saveSelectedGoal = () => {
    if (!selectedGoal || !draftGoal) return;
    if (selectedGoal.goal_type !== "home") {
      saveGoal(selectedGoal.id, draftGoal);
      return;
    }
    const timingPatch = unifiedTimingPatch(draftGoal);
    selectedGoalGroupGoals.forEach((goal) => saveGoal(goal.id, { ...goal.data, ...timingPatch }));
  };
  const selectGoal = (goalId: string) => {
    setActiveGoalId(goalId);
    const goal = planningGoals.find((item) => item.id === goalId);
    setDraftGoal(goal?.data ?? null);
  };
  const setGoalIncluded = (goal: PlanningGoalRecord, included: boolean) => {
    const relatedGoals = goal.goal_type === "home"
      ? planningGoalGroups.find((group) => group.goals.some((item) => item.id === goal.id))?.goals ?? [goal]
      : [goal];
    relatedGoals.forEach((item) => saveGoal(item.id, {
      ...item.data,
      enabled: included,
      timing_mode: included && item.data.timing_mode === "not_planned" ? "auto_sequence" : item.data.timing_mode
    }));
  };

  useEffect(() => {
    if (!planningGoals.length) {
      setActiveGoalId("");
      setDraftGoal(null);
      return;
    }
    if (!planningGoals.some((goal) => goal.id === activeGoalId)) {
      selectGoal(planningGoalGroups[0]?.representative.id ?? planningGoals[0].id);
    }
  }, [activeGoalId, planningGoalGroups, planningGoals]);

  useEffect(() => {
    if (visibleGoalGroups.length && !visibleGoalGroups.some((group) => group.goals.some((goal) => goal.id === activeGoalId))) {
      selectGoal(visibleGoalGroups[0].representative.id);
    }
  }, [activeGoalId, visibleGoalGroups]);

  useEffect(() => {
    setDraftGoal(selectedGoal?.data ?? null);
  }, [selectedGoal]);

  return (
    <PlannerPageShell
      icon={<Target size={20} />}
      title="规划目标"
      action={
        <div className="topbar-actions compact-actions">
          <button className="secondary-button" type="button" onClick={() => createGoal("renovation")} disabled={saving}>
            <Plus size={15} /> 添加装修目标
          </button>
          <button className="ghost-button" type="button" onClick={() => createGoal("other")} disabled={saving}>
            <Plus size={15} /> 添加其它目标
          </button>
        </div>
      }
      summary={<p>这里统一安排所有重大目标的纳入状态、优先级、依赖关系和时间段；购房、购车、养娃页面只维护各自的专业参数并展示这里的排期。</p>}
    >
      <WorkflowSection
        icon={<CalendarClock size={18} />}
        title="总体排期"
        description="先确定目标之间的取舍和时间段，再进入各专业页面比较房源、车源、养娃支出或融资策略。"
      >
        <div className="metric-grid planning-center-metrics">
          <Metric label="全部目标" value={`${planningGoalGroups.length} 个`} />
          <Metric label="纳入本次规划" value={`${includedGoals} 个`} tone={includedGoals > 0 ? "good" : undefined} />
          <Metric label="专业目标" value={`${planningGoalGroups.length - genericGoalCount} 个`} />
          <Metric label="顺序提示" value={`${planningSequence?.warnings.length ?? 0} 条`} tone={planningSequence?.warnings.length ? "warn" : undefined} />
        </div>
        <div className="form-grid two planning-tradeoff-controls">
          <Field label="重大目标时间与财富取舍">
            <select
              value={household.major_goal_tradeoff_mode ?? "auto"}
              onChange={(event) => updateHouseholdPatch({ major_goal_tradeoff_mode: event.target.value as HouseholdData["major_goal_tradeoff_mode"] })}
            >
              <option value="auto">自动量化取舍</option>
              <option value="manual">手动设定倾向</option>
            </select>
          </Field>
          {(household.major_goal_tradeoff_mode ?? "auto") === "manual" ? (
            <NumberField
              label="偏向提前实现目标"
              value={household.major_goal_timing_preference ?? 0.5}
              min={0.05}
              max={0.95}
              step={0.05}
              onChange={(value) => updateHouseholdPatch({ major_goal_timing_preference: value })}
            />
          ) : (
            <ReadOnlyField label="自动权衡因素" value="现金安全、目标优先级、生活效用、母亲年龄、理财税后收益与财富终值" />
          )}
        </div>
        <p className="field-hint">该设置同时约束购房、购车和养娃。0.5 表示时间效用与财富终值均衡；数值越高越愿意为提前实现目标放弃部分投资收益。现金缺口、破产月份和流动资产耗尽始终是硬门槛，不受手动倾向覆盖。</p>
        <div className="planning-filter-row" role="group" aria-label="筛选目标类型">
          {(["all", "home", "vehicle", "child", "renovation", "other"] as GoalFilter[]).map((type) => {
            const count = type === "all"
              ? planningGoalGroups.length
              : planningGoalGroups.filter((group) => group.representative.goal_type === type).length;
            const label = type === "all" ? "全部" : planningGoalTypeLabel(type);
            return (
              <button className={filter === type ? "filter-button active" : "filter-button"} key={type} type="button" onClick={() => setFilter(type)}>
                {label} <span>{count}</span>
              </button>
            );
          })}
        </div>
        {planningSequence?.warnings.length ? (
          <div className="planning-warning-list">
            {planningSequence.warnings.map((warning, index) => <span key={`${warning}-${index}`}><AlertTriangle size={14} /> {warning}</span>)}
          </div>
        ) : null}
        <div className="planning-sequence-rail">
          {visibleGoalGroups.map((group) => {
            const goal = group.representative;
            const resolvedGoal = resolvedGoalById.get(goal.id);
            const active = group.goals.some((item) => item.id === selectedGoal?.id);
            return (
            <button className={active ? "planning-sequence-item active" : "planning-sequence-item"} key={group.key} type="button" onClick={() => selectGoal(goal.id)}>
              <span>{resolvedGoal ? planningGoalOrderLabel({ ...resolvedGoal, sequence_index: group.resolvedSequence }) : "待解析"}</span>
              <strong>{goalGroupTitle(group.goals)}</strong>
              <small>{planningGoalTypeLabel(goal.goal_type)}{goal.goal_type === "home" ? ` · ${group.goals.length} 个候选房源` : ""} · {goalWindowSummary(goal.data)}</small>
            </button>
            );
          })}
        </div>
      </WorkflowSection>

      <WorkflowSection
        icon={<Target size={18} />}
        title="目标列表"
        description="选择一个目标后，在下方只编辑统一排期；专业参数请转到对应计划页面。"
      >
        {visibleGoalGroups.length ? (
          <div className="planning-goal-grid horizontal-card-list planning-center-goal-grid">
            {visibleGoalGroups.map((group) => {
              const goal = group.representative;
              const resolvedGoal = resolvedGoalById.get(goal.id);
              const included = group.goals.some((item) => item.data.enabled && item.data.timing_mode !== "not_planned");
              const allIncluded = group.goals.every((item) => item.data.enabled && item.data.timing_mode !== "not_planned");
              const relatedPage = detailPage[goal.goal_type];
              const active = group.goals.some((item) => item.id === selectedGoal?.id);
              return (
                <article className={active ? "planning-goal-card active" : "planning-goal-card"} key={group.key}>
                  <button className="planning-goal-select compact-select" type="button" onClick={() => selectGoal(goal.id)}>
                    <span className={included ? "goal-status enabled" : "goal-status paused"}>{included && !allIncluded ? "部分纳入" : planningInclusionStatusLabel(included, goal.data.enabled)}</span>
                    <small>{planningGoalTypeLabel(goal.goal_type)} · {resolvedGoal ? planningGoalOrderLabel({ ...resolvedGoal, sequence_index: group.resolvedSequence }) : "待解析"}</small>
                    <strong>{goalGroupTitle(group.goals)}</strong>
                    <em>{goalWindowSummary(goal.data)}</em>
                    <small>{goal.goal_type === "home" ? `${group.goals.length} 个候选房源：${homeCandidateSummary(group.goals)}` : targetSummary(goal)}</small>
                  </button>
                  <div className="planning-goal-actions">
                    {relatedPage ? <button className="ghost-button small" type="button" onClick={() => openPage(relatedPage)}>专业参数</button> : null}
                    {goal.goal_type !== "home" ? <button className="ghost-button small" type="button" onClick={() => duplicateGoal(goal)} disabled={saving}><Copy size={14} /> 复制</button> : null}
                    <button className="ghost-button small" type="button" onClick={() => setGoalIncluded(goal, !included)} disabled={saving}>{included ? "暂不纳入" : "纳入规划"}</button>
                    {goal.goal_type !== "home" ? <button className="ghost-button small danger-action" type="button" onClick={() => deleteGoal(goal.id)} disabled={saving} aria-label={`删除${goal.data.name}`}><Trash2 size={14} /> 删除</button> : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="还没有这类规划目标"
            description="购房、购车和养娃目标请在对应专业页面添加；装修和其它目标可以直接在这里创建。"
            action={<div className="quick-action-row"><button className="ghost-button" type="button" onClick={() => openPage("购房计划")}>添加购房目标</button><button className="ghost-button" type="button" onClick={() => openPage("购车计划")}>添加用车需求</button><button className="ghost-button" type="button" onClick={() => openPage("养娃计划")}>添加子女目标</button></div>}
          />
        )}
      </WorkflowSection>

      {selectedGoal && effectiveGoal ? (
        <>
          <WorkflowSection
            icon={<SlidersHorizontal size={18} />}
            title="统一排期设置"
            description="这些字段是所有重大目标唯一的排期入口。保存后，后端会重新解析顺序并同步到各专业页面的展示。"
          >
            <div className="planning-center-editor">
              <div className="form-grid planning-center-form">
                {selectedGoal.goal_type === "home" && selectedGoalGroupGoals.length > 1 ? (
                  <div className="field-hint planning-group-hint">
                    当前是同一购房需求下的 {selectedGoalGroupGoals.length} 个候选房源；这里修改的纳入状态、优先级、排期规则和需求时间段会同步应用到全部候选房源。
                  </div>
                ) : null}
                <SwitchField
                  label={effectiveGoal.enabled && effectiveGoal.timing_mode !== "not_planned" ? "纳入当前规划" : "暂不纳入规划"}
                  checked={effectiveGoal.enabled && effectiveGoal.timing_mode !== "not_planned"}
                  onChange={(checked) => updateDraftGoal({ enabled: checked, timing_mode: checked && effectiveGoal.timing_mode === "not_planned" ? "auto_sequence" : effectiveGoal.timing_mode })}
                />
                <NumberField label="规划优先级" value={effectiveGoal.priority} min={1} max={999} step={1} onChange={(value) => updateDraftGoal({ priority: Math.round(value) })} />
                <Field label="排期规则">
                  <select
                    value={effectiveGoal.timing_mode === "not_planned" ? "auto_sequence" : effectiveGoal.timing_mode}
                    onChange={(event) => {
                      const timingMode = event.target.value as PlanningTimingMode;
                      updateDraftGoal({
                        timing_mode: timingMode,
                        enabled: true,
                        allow_parallel: timingMode === "parallel",
                        depends_on_goal_id: timingMode === "after_goal" ? effectiveGoal.depends_on_goal_id : "",
                        earliest_purchase_month: "",
                        earliest_purchase_delay_months: 0,
                        delay_after_dependency_months: 0
                      });
                    }}
                  >
                    {timingOptions.map((option) => <option key={option.value} value={option.value}>{option.value === "manual_month" ? `指定${windowLabel}` : option.label}</option>)}
                  </select>
                </Field>
                {effectiveGoal.timing_mode === "after_goal" ? (
                  <Field label="跟随目标">
                    <select value={effectiveGoal.depends_on_goal_id} onChange={(event) => updateDraftGoal({ depends_on_goal_id: event.target.value })}>
                      <option value="">{PLANNING_GOAL_AUTO_DEPENDENCY_LABEL}</option>
                      {dependencyOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                    </select>
                  </Field>
                ) : null}
                <PlanningWindowFields
                  startMonth={effectiveGoal.planning_window_start_month}
                  endMonth={effectiveGoal.planning_window_end_month}
                  onChange={(patch) => updateDraftGoal(patch)}
                  startLabel={`${windowLabel}开始`}
                  endLabel={`${windowLabel}结束`}
                  hint={`策略只会在${windowLabel}内安排具体月份；不填则由后端结合顺序、现金安全、政策和其它目标决定。`}
                />
                {isGenericGoal ? (
                  <>
                    <Field label="目标名称"><input value={effectiveGoal.name} onChange={(event) => updateDraftGoal({ name: event.target.value, target_params: { ...effectiveGoal.target_params, name: event.target.value } })} /></Field>
                    <Field label="目标类型">
                      <select value={effectiveGoal.goal_type} onChange={(event) => updateDraftGoal({ goal_type: event.target.value as "renovation" | "other" })}>
                        <option value="renovation">装修</option><option value="other">其它重大目标</option>
                      </select>
                    </Field>
                    <NumberField label="目标预算" value={Number(effectiveGoal.target_params.estimated_cost ?? effectiveGoal.target_params.budget ?? 0)} min={0} step={10000} onChange={(value) => updateDraftTargetParams({ estimated_cost: value, budget: value })} />
                  </>
                ) : null}
                {selectedGoal.goal_type === "renovation" ? (
                  <div className="field-hint planning-group-hint">
                    装修目标是装修预算、资金方式和排期的唯一真源；它会作为购房后的独立规划事件进入策略、账本和时间线。
                  </div>
                ) : null}
                <Field label="排期备注"><textarea value={effectiveGoal.notes} onChange={(event) => updateDraftGoal({ notes: event.target.value })} /></Field>
              </div>
              <aside className="planning-center-detail-note">
                <span>{planningGoalTypeLabel(selectedGoal.goal_type)}</span>
                <strong>{goalGroupTitle(selectedGoalGroupGoals)}</strong>
                <p>{selectedGoal.goal_type === "home" ? `${selectedGoalGroupGoals.length} 个候选房源：${homeCandidateSummary(selectedGoalGroupGoals)}` : selectedGoal.goal_type === "renovation" ? "这里维护装修事件的预算、资金方式和排期；购房候选只提供房源参数，不再保存装修需求。" : isGenericGoal ? "预算、资金方式和排期都可以在这里维护。" : "车源、出生后的阶段支出和融资偏好只在专业计划页面维护，避免与统一排期重复。"}</p>
                {detailPage[selectedGoal.goal_type] ? <button className="ghost-button small" type="button" onClick={() => openPage(detailPage[selectedGoal.goal_type]!)}>查看专业参数</button> : null}
              </aside>
            </div>
            <div className="planning-goal-actions">
              <button className="primary-button" type="button" onClick={saveSelectedGoal} disabled={saving}><Save size={15} /> {selectedGoal.goal_type === "home" && selectedGoalGroupGoals.length > 1 ? `保存全部 ${selectedGoalGroupGoals.length} 个候选的统一排期` : "保存统一排期"}</button>
              <button className="ghost-button" type="button" onClick={refreshGoals} disabled={saving}><RefreshCw size={15} /> 刷新目标库</button>
            </div>
          </WorkflowSection>

          <WorkflowSection icon={<Sparkles size={18} />} title="排期影响预览" description="这里显示后端解析后的顺序和对象归属；策略、账本和可视化共用同一套目标主数据。" profile="explanation">
            <div className="strategy-grid generic-goal-impact-grid">
              <article><span>解析后的顺序</span><strong>{selectedResolvedGoal ? planningGoalOrderLabel(selectedResolvedGoal) : "等待解析"}</strong><p>{selectedResolvedGoal?.explanation || "保存后会按统一规则重新解析。"}</p></article>
              <article><span>{windowLabel}</span><strong>{goalWindowSummary(effectiveGoal)}</strong><p>{selectedResolvedGoal?.dependency_warning || "没有额外依赖警告。"}</p></article>
              <article><span>核心对象</span><strong>{selectedCoreObjects.length ? `${selectedCoreObjects.length} 个对象` : "等待索引"}</strong><p>{selectedCoreObjectSummary}</p></article>
              <article><span>当前策略</span><strong>{effectiveGoal.selected_strategy_id || "策略待生成"}</strong><p>策略选择仍由后端生成；这里仅管理目标的排期和纳入范围。</p></article>
            </div>
          </WorkflowSection>
        </>
      ) : null}
    </PlannerPageShell>
  );
}

function GenericPlanningGoalPage({
  planningGoals,
  planningSequence,
  coreObjects,
  createGoal,
  duplicateGoal,
  saveGoal,
  deleteGoal,
  refreshGoals,
  saving
}: {
  planningGoals: PlanningGoalRecord[];
  planningSequence: PlanningSequenceResult | null;
  coreObjects: CoreObjectRecord[];
  createGoal: (goalType: "renovation" | "other") => void;
  duplicateGoal: (goal: PlanningGoalRecord) => void;
  saveGoal: (goalId: string, goalData: PlanningGoalData) => void;
  deleteGoal: (goalId: string) => void;
  refreshGoals: () => void;
  saving: boolean;
}) {
  const genericGoals = useMemo(
    () => planningGoals.filter((goal) => goal.goal_type === "renovation" || goal.goal_type === "other"),
    [planningGoals]
  );
  const [activeGoalId, setActiveGoalId] = useState(genericGoals[0]?.id ?? "");
  const selectedGoal = genericGoals.find((goal) => goal.id === activeGoalId) ?? genericGoals[0] ?? null;
  const [draftGoal, setDraftGoal] = useState<PlanningGoalData | null>(selectedGoal?.data ?? null);

  useEffect(() => {
    if (!genericGoals.length) {
      setActiveGoalId("");
      setDraftGoal(null);
      return;
    }
    if (!selectedGoal) {
      setActiveGoalId(genericGoals[0].id);
      return;
    }
    setDraftGoal(selectedGoal.data);
  }, [genericGoals, selectedGoal]);

  const resolvedGoalById = useMemo(
    () => new Map((planningSequence?.goals ?? []).map((goal) => [goal.id, goal])),
    [planningSequence]
  );
  const dependencyOptions = planningGoalDependencyOptions(
    planningSequence?.goals ?? [],
    selectedGoal ? new Set([selectedGoal.id]) : new Set()
  );
  const selectedResolvedGoal = selectedGoal ? resolvedGoalById.get(selectedGoal.id) : null;
  const selectedCoreObjects = useMemo(
    () => selectedGoal ? coreObjects.filter((object) => coreObjectOwnerKey(object) === selectedGoal.id) : [],
    [coreObjects, selectedGoal]
  );
  const selectedCoreObjectSummaryByOwner = useMemo(
    () => coreObjectOwnerSummaryByOwner(selectedCoreObjects),
    [selectedCoreObjects]
  );
  const selectedCoreObjectSummaryItem = selectedCoreObjectSummaryByOwner.get(selectedGoal?.id ?? "");
  const selectedCoreObjectSummary = selectedCoreObjects.length
    ? coreObjectOwnerSummaryText(selectedCoreObjectSummaryItem)
    : "保存后会进入后端核心对象索引，作为目标/资产口径参与校准、导出和可视化说明。";
  const effectiveGoal = draftGoal ?? selectedGoal?.data ?? null;
  const estimatedCost = Number(
    effectiveGoal?.target_params?.estimated_cost ??
    effectiveGoal?.target_params?.budget ??
    effectiveGoal?.target_params?.amount ??
    0
  );
  const includedGoals = genericGoals.filter((goal) => goal.data.enabled && goal.data.timing_mode !== "not_planned").length;
  const updateDraftGoal = (patch: Partial<PlanningGoalData>) => {
    setDraftGoal((current) => current ? { ...current, ...patch } : current);
  };
  const updateDraftTargetParams = (patch: Record<string, unknown>) => {
    setDraftGoal((current) => current ? {
      ...current,
      target_params: { ...current.target_params, ...patch }
    } : current);
  };
  const saveSelectedGoal = () => {
    if (selectedGoal && draftGoal) saveGoal(selectedGoal.id, draftGoal);
  };
  const saveImmediateGoal = (goal: PlanningGoalRecord, patch: Partial<PlanningGoalData>) => {
    saveGoal(goal.id, { ...goal.data, ...patch });
  };

  return (
    <PlannerPageShell
      icon={<Target size={20} />}
      title="规划目标"
      action={
        <div className="topbar-actions compact-actions">
          <button className="secondary-button" type="button" onClick={() => createGoal("renovation")} disabled={saving}>
            <Plus size={15} /> 添加装修目标
          </button>
          <button className="ghost-button" type="button" onClick={() => createGoal("other")} disabled={saving}>
            <Plus size={15} /> 添加其它目标
          </button>
        </div>
      }
      summary={
        <div className="metric-grid">
          <Metric label="装修/其它目标" value={`${genericGoals.length} 个`} />
          <Metric label="纳入规划" value={`${includedGoals} 个`} tone={includedGoals > 0 ? "good" : undefined} />
          <Metric label="顺序预览" value={selectedResolvedGoal ? planningGoalOrderLabel(selectedResolvedGoal) : "等待选择"} />
          <Metric label="预计预算" value={money(Math.max(0, estimatedCost || 0))} />
        </div>
      }
    >
      <WorkflowSection
        icon={<Target size={18} />}
        title="目标列表"
        description="装修和其它重大目标直接写入统一规划目标库；购房、购车和养娃仍在各自专业页面编辑。"
      >
        {genericGoals.length ? (
          <div className="planning-goal-grid horizontal-card-list generic-goal-grid">
            {genericGoals.map((goal) => {
              const resolvedGoal = resolvedGoalById.get(goal.id);
              const isIncluded = goal.data.enabled && goal.data.timing_mode !== "not_planned";
              return (
                <article className={goal.id === selectedGoal?.id ? "planning-goal-card active" : "planning-goal-card"} key={goal.id}>
                  <button className="planning-goal-select compact-select" type="button" onClick={() => setActiveGoalId(goal.id)}>
                    <small>{planningGoalTypeLabel(goal.goal_type)} · {resolvedGoal ? planningGoalOrderLabel(resolvedGoal) : "待排序"}</small>
                    <strong>{goal.data.name}</strong>
                    <em>{resolvedGoal ? planningGoalTimingSummary(resolvedGoal) : planningGoalTimingLabel({ normalized_timing_mode: goal.data.timing_mode })}</em>
                  </button>
                  <span className={`goal-status ${isIncluded ? "enabled" : "paused"}`}>
                    {planningInclusionStatusLabel(isIncluded, goal.data.enabled)}
                  </span>
                  <div className="planning-goal-actions">
                    <button className="ghost-button small" type="button" onClick={() => duplicateGoal(goal)} disabled={saving}>
                      <Copy size={14} /> 复制
                    </button>
                    <button
                      className="ghost-button small"
                      type="button"
                      onClick={() => saveImmediateGoal(goal, { enabled: !goal.data.enabled })}
                      disabled={saving}
                    >
                      {goal.data.enabled ? "停用" : "启用"}
                    </button>
                    <button className="ghost-button danger small" type="button" onClick={() => deleteGoal(goal.id)} disabled={saving}>
                      <Trash2 size={14} /> 删除
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="还没有装修或其它重大目标"
            description="添加后会进入统一规划顺序、核心对象索引、记账校准和导出表；不需要目标时可保持为空。"
            action={
              <div className="quick-action-row">
                <button className="secondary-button" type="button" onClick={() => createGoal("renovation")} disabled={saving}>
                  <Plus size={15} /> 添加装修目标
                </button>
                <button className="ghost-button" type="button" onClick={() => createGoal("other")} disabled={saving}>
                  <Plus size={15} /> 添加其它目标
                </button>
              </div>
            }
          />
        )}
      </WorkflowSection>

      {selectedGoal && effectiveGoal ? (
        <>
          <WorkflowSection
            icon={<SlidersHorizontal size={18} />}
            title="当前目标配置"
            description="这里编辑目标名称、预算、顺序和依赖；保存后由后端统一解析顺序。"
          >
            <div className="form-grid generic-goal-config-grid">
              <Field label="目标名称">
                <input
                  type="text"
                  value={effectiveGoal.name}
                  onChange={(event) => updateDraftGoal({ name: event.target.value, target_params: { ...effectiveGoal.target_params, name: event.target.value } })}
                />
              </Field>
              <Field label="目标类型">
                <select
                  value={effectiveGoal.goal_type}
                  onChange={(event) => updateDraftGoal({
                    goal_type: event.target.value as "renovation" | "other",
                    target_params: {
                      ...effectiveGoal.target_params,
                      category: event.target.value === "renovation" ? "renovation" : "other_major_goal"
                    }
                  })}
                >
                  <option value="renovation">装修</option>
                  <option value="other">其它重大目标</option>
                </select>
              </Field>
              <NumberField label="目标预算" value={Math.max(0, estimatedCost || 0)} min={0} step={10000} onChange={(value) => updateDraftTargetParams({ estimated_cost: value, budget: value })} />
              <NumberField label="目标优先级" value={effectiveGoal.priority} min={1} max={999} step={1} onChange={(value) => updateDraftGoal({ priority: Math.round(value) })} />
              <Field label="时间安排">
                <select
                  value={effectiveGoal.timing_mode}
                  onChange={(event) => {
                    const timingMode = event.target.value as PlanningTimingMode;
                    updateDraftGoal({
                      timing_mode: timingMode,
                      enabled: timingMode !== "not_planned",
                      allow_parallel: timingMode === "parallel",
                      depends_on_goal_id: timingMode === "after_goal" ? effectiveGoal.depends_on_goal_id : ""
                    });
                  }}
                >
                  {GENERIC_PLANNING_GOAL_TIMING_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </Field>
              {effectiveGoal.timing_mode === "after_goal" ? (
                <Field label="跟随目标">
                  <select value={effectiveGoal.depends_on_goal_id} onChange={(event) => updateDraftGoal({ depends_on_goal_id: event.target.value })}>
                    <option value="">{PLANNING_GOAL_AUTO_DEPENDENCY_LABEL}</option>
                    {dependencyOptions.map((option) => (
                      <option key={option.id} value={option.id}>{option.label}</option>
                    ))}
                  </select>
                </Field>
              ) : null}
              <NumberField label={effectiveGoal.timing_mode === "after_goal" ? "依赖目标后等待月数" : "前一目标后等待月数"} value={effectiveGoal.delay_after_dependency_months} min={0} max={360} step={1} onChange={(value) => updateDraftGoal({ delay_after_dependency_months: Math.round(value), earliest_purchase_delay_months: Math.round(value) })} />
              <Field label="手动月份">
                <input type="month" value={effectiveGoal.earliest_purchase_month} onChange={(event) => updateDraftGoal({ earliest_purchase_month: event.target.value })} />
              </Field>
              <Field label="窗口开始">
                <input type="month" value={effectiveGoal.planning_window_start_month} onChange={(event) => updateDraftGoal({ planning_window_start_month: event.target.value })} />
              </Field>
              <Field label="窗口结束">
                <input type="month" value={effectiveGoal.planning_window_end_month} onChange={(event) => updateDraftGoal({ planning_window_end_month: event.target.value })} />
              </Field>
              <Field label="资金策略">
                <select
                  value={String(effectiveGoal.financing_preferences.funding_mode ?? "cash_or_investment")}
                  onChange={(event) => updateDraftGoal({ financing_preferences: { ...effectiveGoal.financing_preferences, funding_mode: event.target.value } })}
                >
                  <option value="cash_or_investment">现金与投资账户统筹</option>
                  <option value="cash_only">仅现金账户</option>
                  <option value="after_goal_saving">目标后逐月储备</option>
                </select>
              </Field>
              <Field label="目标备注">
                <textarea value={effectiveGoal.notes} onChange={(event) => updateDraftGoal({ notes: event.target.value })} />
              </Field>
              {effectiveGoal.goal_type === "renovation" ? (
                <div className="field-hint planning-group-hint">
                  装修目标是装修预算、资金方式和排期的唯一真源；它会作为购房后的独立规划事件进入策略、账本和时间线。
                </div>
              ) : null}
            </div>
            <div className="planning-goal-actions">
              <button className="primary-button" type="button" onClick={saveSelectedGoal} disabled={saving}>
                <Save size={15} /> 保存目标
              </button>
              <button className="ghost-button" type="button" onClick={refreshGoals} disabled={saving}>
                <RefreshCw size={15} /> 刷新目标库
              </button>
            </div>
          </WorkflowSection>

          <WorkflowSection
            icon={<Sparkles size={18} />}
            title="策略说明与影响预览"
            description="当前阶段先展示统一目标、顺序和核心对象口径；专属策略生成后会继续落到同一目标。"
            profile="explanation"
          >
            <div className="strategy-grid generic-goal-impact-grid">
              <article>
                <span>规划顺序</span>
                <strong>{selectedResolvedGoal ? planningGoalTimingSummary(selectedResolvedGoal) : "等待后端解析"}</strong>
                <p>{selectedResolvedGoal?.explanation || "保存目标后，后端会按统一顺序规则解析自动排队、并行、手动时间和跟随目标。"}</p>
              </article>
              <article>
                <span>核心对象</span>
                <strong>{selectedCoreObjects.length ? `${selectedCoreObjects.length} 个对象` : "等待索引"}</strong>
                <p>{selectedCoreObjectSummary}</p>
              </article>
              <article>
                <span>当前策略</span>
                <strong>{effectiveGoal.selected_strategy_id || "手动目标参数"}</strong>
                <p>{effectiveGoal.goal_type === "renovation" ? "装修目标会按所选购房需求、等待时间和资金策略生成一次装修事件，并在执行月份进入现金账本。" : "其它目标先按目标预算、时间和资金偏好进入统一目标库；专属账本策略尚未启用。"}</p>
              </article>
            </div>
          </WorkflowSection>
        </>
      ) : null}
    </PlannerPageShell>
  );
}

function AccountCalibrationPage({
  household,
  result,
  planningGoals,
  planningSequence,
  accountConcepts,
  coreObjectGroups,
  generatedStrategies,
  updateHousehold
}: {
  household: HouseholdData;
  result: AffordabilityResult | null;
  planningGoals: PlanningGoalRecord[];
  planningSequence: PlanningSequenceResult | null;
  accountConcepts: AccountConceptSummary[];
  coreObjectGroups: CoreObjectGroupSummary[];
  generatedStrategies: GeneratedStrategyRecord[];
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
}) {
  const today = new Date();
  const accountCalibrations = household.account_calibrations ?? [];
  const currentMonthText = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const [selectedConceptCode, setSelectedConceptCode] = useState("");
  const [selectedEventKey, setSelectedEventKey] = useState("");
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [conceptSourceQuery, setConceptSourceQuery] = useState("");
  const [eventSourceQuery, setEventSourceQuery] = useState("");
  const [strategySourceQuery, setStrategySourceQuery] = useState("");
  const [sourceMode, setSourceMode] = useState<"concept" | "event" | "strategy">("concept");
  const coreGroupByCode = coreObjectGroupMap(coreObjectGroups);
  const liquidAssetGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.liquidAssets);
  const restrictedAccountGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.restrictedAccounts);
  const fixedAssetGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.fixedAssets);
  const loanAccountGroup = coreGroupByCode.get(CORE_OBJECT_GROUP_CODES.loanAccounts);
  const defaultCalibrationAmount = (target: AccountCalibrationTarget) => {
    return calibrationDefaultAmountFromConcepts(
      accountConcepts,
      coreObjectGroups,
      target,
      calibrationFallbackAmountFromHousehold(household, target)
    );
  };
  const monthValueFromIndex = (monthIndex: number) => {
    const targetDate = addMonths(today, Math.max(0, monthIndex));
    return `${targetDate.getFullYear()}-${String(targetDate.getMonth() + 1).padStart(2, "0")}`;
  };
  const targetForEventCategory = (category: string): AccountCalibrationTarget => {
    if (category === "loan") return "total_loan";
    if (category === "provident") return "provident";
    if (category === "investment") return "investment";
    if (category === "home_purchase") return "property_asset";
    if (category === "vehicle") return "vehicle_asset";
    if (category === "renovation") return "fixed_asset";
    return "cash";
  };
  const targetForGoalType = (goalType: PlanningGoalRecord["goal_type"]): AccountCalibrationTarget => {
    if (goalType === "home") return "property_asset";
    if (goalType === "vehicle") return "vehicle_asset";
    if (goalType === "renovation") return "fixed_asset";
    return "cash";
  };
  const targetForConceptCode = (code: string): AccountCalibrationTarget | null => {
    if (code === ACCOUNT_CONCEPT_CODES.cash) return "cash";
    if (code === ACCOUNT_CONCEPT_CODES.investment) return "investment";
    if (code === ACCOUNT_CONCEPT_CODES.provident) return "provident";
    if (code === ACCOUNT_CONCEPT_CODES.pension) return "pension";
    if (code === ACCOUNT_CONCEPT_CODES.medical) return "medical";
    if (code === ACCOUNT_CONCEPT_CODES.fixedAsset) return "fixed_asset";
    if (code === ACCOUNT_CONCEPT_CODES.loan) return "total_loan";
    return null;
  };
  const conceptCodeForTarget = (target: AccountCalibrationTarget): string | null => {
    if (target === "cash") return ACCOUNT_CONCEPT_CODES.cash;
    if (target === "investment") return ACCOUNT_CONCEPT_CODES.investment;
    if (target === "provident") return ACCOUNT_CONCEPT_CODES.provident;
    if (target === "pension") return ACCOUNT_CONCEPT_CODES.pension;
    if (target === "medical") return ACCOUNT_CONCEPT_CODES.medical;
    if (target === "fixed_asset" || target === "property_asset" || target === "vehicle_asset") return ACCOUNT_CONCEPT_CODES.fixedAsset;
    if (target === "total_loan") return ACCOUNT_CONCEPT_CODES.loan;
    return null;
  };
  const targetForStrategyType = (strategyType: GeneratedStrategyRecord["strategy_type"]): AccountCalibrationTarget => {
    if (strategyType === "purchase") return "property_asset";
    if (strategyType === "vehicle") return "vehicle_asset";
    if (strategyType === "investment") return "investment";
    if (strategyType === "tax" || strategyType === "career_shock") return "cash";
    return "fixed_asset";
  };
  const sourceMatchesQuery = (query: string, values: Array<string | number | undefined>) => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return true;
    return values.some((value) => String(value ?? "").toLowerCase().includes(normalizedQuery));
  };
  const updateAccountCalibration = <K extends keyof AccountCalibrationData>(
    index: number,
    key: K,
    value: AccountCalibrationData[K]
  ) => {
    updateHousehold("account_calibrations", accountCalibrations.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [key]: value } : item
    )));
  };
  const addAccountCalibration = (target: AccountCalibrationTarget = "cash", patch: Partial<AccountCalibrationData> = {}) => {
    updateHousehold("account_calibrations", [
      ...accountCalibrations,
      {
        enabled: true,
        month: currentMonthText,
        calibration_scope: "account",
        target,
        amount: defaultCalibrationAmount(target),
        member_name: "",
        reference_name: "",
        source_id: "",
        source_category: "",
        source_title: "",
        note: "",
        ...patch
      }
    ]);
  };
  const addConceptCalibration = (concept: {
    key: string;
    target: AccountCalibrationTarget;
    name: string;
    currentBalance: number;
    sourceId: string;
    sourceCategory: string;
    note: string;
  }) => {
    addAccountCalibration(concept.target, {
      calibration_scope: "concept",
      amount: concept.currentBalance,
      source_id: concept.sourceId,
      source_category: concept.sourceCategory,
      source_title: concept.name,
      reference_name: concept.name,
      note: concept.note
    });
  };
  const addMajorEventCalibration = (event: {
    target: AccountCalibrationTarget;
    month: number;
    amount: number;
    sourceId: string;
    sourceCategory: string;
    sourceTitle: string;
    note: string;
  }) => {
    const target = event.target;
    addAccountCalibration(target, {
      calibration_scope: "major_event",
      month: monthValueFromIndex(event.month),
      amount: Math.max(0, event.amount),
      source_id: event.sourceId,
      source_category: event.sourceCategory,
      source_title: event.sourceTitle,
      reference_name: event.sourceTitle,
      note: event.note
    });
  };
  const addStrategyCalibration = (strategy: GeneratedStrategyRecord) => {
    const target = targetForStrategyType(strategy.strategy_type);
    const strategyName = strategy.variant || "自动方案";
    const title = `${generatedStrategyTypeLabel(strategy.strategy_type)}策略：${strategyName}`;
    addAccountCalibration(target, {
      calibration_scope: "strategy_event",
      amount: defaultCalibrationAmount(target),
      source_id: strategy.id,
      source_category: strategy.strategy_type,
      source_title: title,
      reference_name: title,
      note: `来自策略库中的${generatedStrategyTypeLabel(strategy.strategy_type)}方案，可用于校准该策略影响后的账户、资产或贷款余额`
    });
  };
  const removeAccountCalibration = (index: number) => {
    updateHousehold("account_calibrations", accountCalibrations.filter((_, itemIndex) => itemIndex !== index));
  };
  const updateAccountCalibrationNote = (index: number, value: string) => {
    updateHousehold("account_calibrations", accountCalibrations.map((item, itemIndex) => (
      itemIndex === index ? { ...item, reference_name: value, note: value } : item
    )));
  };
  const enabledCount = accountCalibrations.filter((item) => item.enabled).length;
  const latestSnapshot = result?.account_snapshots?.[result.account_snapshots.length - 1];
  const coreGroupMetricValue = (group: CoreObjectGroupSummary | undefined) =>
    coreObjectBalanceText(group);
  const coreGroupCountText = (group: CoreObjectGroupSummary | undefined) =>
    coreObjectCountText(group, "个对象");
  const targetSummary = ACCOUNT_CALIBRATION_TARGET_OPTIONS.map((option) => ({
    ...option,
    count: accountCalibrations.filter((item) => item.target === option.value).length
  })).filter((item) => item.count > 0);
  const conceptByTarget = new Map<AccountCalibrationTarget, AccountConceptSummary>();
  for (const concept of accountConcepts) {
    const target = targetForConceptCode(concept.code);
    if (target && !conceptByTarget.has(target)) conceptByTarget.set(target, concept);
  }
  const conceptCalibrationOptions = ACCOUNT_CALIBRATION_TARGET_OPTIONS.map((option) => {
    const concept = conceptByTarget.get(option.value);
    const fallbackCode = conceptCodeForTarget(option.value) ?? option.value;
    return {
      key: option.value,
      target: option.value,
      name: concept?.name ?? option.label,
      currentBalance: concept?.current_balance ?? defaultCalibrationAmount(option.value),
      sourceId: concept?.code ?? `calibration:${fallbackCode}`,
      sourceCategory: concept?.category ?? option.value,
      note: concept
        ? `${concept.name}按账户概念摘要校准`
        : `${option.label}按统一校准概念目录校准，金额来自核心对象分组或本页账户输入`
    };
  });
  const planEventCalibrationOptions = (result?.plan_events ?? [])
    .filter((event) => event.category !== "account" && event.category !== "property_market")
    .map((event, index) => ({
      key: `${event.plan_variant}:${event.month}:${event.category}:${event.title}:${index}`,
      label: `${formatMonthDate(today, event.month)} · ${event.title}`,
      event: {
        target: targetForEventCategory(event.category),
        month: event.month,
        amount: event.amount ?? defaultCalibrationAmount(targetForEventCategory(event.category)),
        sourceId: `${event.plan_variant}:${event.month}:${event.title}`,
        sourceCategory: event.category,
        sourceTitle: event.title,
        note: event.detail
      }
    }));
  const sequenceGoalById = new Map((planningSequence?.goals ?? []).map((goal) => [goal.id, goal]));
  const planningGoalCalibrationOptions = planningGoals
    .filter((goal) => goal.data.enabled)
    .map((goal, index) => {
      const sequenceGoal = sequenceGoalById.get(goal.id);
      const target = targetForGoalType(goal.goal_type);
      const month = sequenceGoal?.resolved_not_before_month ?? 0;
      const title = sequenceGoal?.name || goal.data.name || `规划目标 ${index + 1}`;
      return {
        key: `planning_goal:${goal.id}`,
        label: `${formatMonthDate(today, month)} · ${title}`,
        event: {
          target,
          month,
          amount: defaultCalibrationAmount(target),
          sourceId: goal.id,
          sourceCategory: `planning_goal:${goal.goal_type}`,
          sourceTitle: title,
          note: sequenceGoal?.explanation || goal.data.notes || "来自统一规划目标库，尚未形成完整事件时间线"
        }
      };
    });
  const majorEventCalibrationOptions = planEventCalibrationOptions.length
    ? planEventCalibrationOptions
    : planningGoalCalibrationOptions;
  const strategyCalibrationOptions = generatedStrategies.map((strategy) => ({
    key: strategy.id,
    label: `${generatedStrategyTypeLabel(strategy.strategy_type)} · ${strategy.variant || "自动方案"}`,
    searchText: generatedStrategySearchText(strategy),
    strategy
  }));
  const filteredConceptCalibrationOptions = conceptCalibrationOptions.filter((concept) =>
    sourceMatchesQuery(conceptSourceQuery, [
      concept.name,
      concept.sourceCategory,
      concept.note,
      concept.currentBalance,
    ])
  );
  const filteredMajorEventCalibrationOptions = majorEventCalibrationOptions.filter((option) =>
    sourceMatchesQuery(eventSourceQuery, [
      option.label,
      option.event.sourceTitle,
      option.event.sourceCategory,
      option.event.note,
      option.event.amount,
    ])
  );
  const filteredStrategyCalibrationOptions = strategyCalibrationOptions.filter((option) =>
    sourceMatchesQuery(strategySourceQuery, [
      option.label,
      option.searchText,
    ])
  );
  const selectedConcept = filteredConceptCalibrationOptions.find((concept) => concept.key === selectedConceptCode) ?? filteredConceptCalibrationOptions[0];
  const selectedEvent = filteredMajorEventCalibrationOptions.find((option) => option.key === selectedEventKey) ?? filteredMajorEventCalibrationOptions[0];
  const selectedStrategy = filteredStrategyCalibrationOptions.find((option) => option.key === selectedStrategyId) ?? filteredStrategyCalibrationOptions[0];
  const calibrationWarnings = (() => {
    const warnings: string[] = [];
    const disabledCount = accountCalibrations.filter((item) => !item.enabled).length;
    if (disabledCount > 0) {
      warnings.push(`有 ${disabledCount} 条校准已停用，不会进入后端账本和事件线。`);
    }
    const enabledByMonthTarget = new Map<string, AccountCalibrationData[]>();
    const enabledBySource = new Map<string, AccountCalibrationData[]>();
    for (const calibration of accountCalibrations) {
      if (!calibration.enabled) continue;
      const monthTargetKey = `${calibration.month || "未设月份"}:${calibration.target}`;
      enabledByMonthTarget.set(monthTargetKey, [...(enabledByMonthTarget.get(monthTargetKey) ?? []), calibration]);
      const sourceKey = [
        calibration.calibration_scope ?? "account",
        calibration.source_id,
        calibration.source_category,
        calibration.source_title,
        calibration.reference_name,
        calibration.target,
        calibration.month
      ].join("|");
      enabledBySource.set(sourceKey, [...(enabledBySource.get(sourceKey) ?? []), calibration]);
    }
    for (const [key, items] of enabledByMonthTarget) {
      if (items.length <= 1) continue;
      const [month, target] = key.split(":");
      const targetLabel = ACCOUNT_CALIBRATION_TARGET_OPTIONS.find((option) => option.value === target)?.label ?? target;
      warnings.push(`${month} 的${targetLabel}有 ${items.length} 条启用校准；后端会按记录顺序逐条应用，建议只保留最终确认的一条。`);
    }
    for (const items of enabledBySource.values()) {
      if (items.length <= 1) continue;
      const title = items[0].source_title || items[0].reference_name || "同一来源";
      warnings.push(`${title} 出现 ${items.length} 条重复启用校准，请确认不是重复添加。`);
    }
    return Array.from(new Set(warnings));
  })();
  const latestCalibrationMonth = accountCalibrations.reduce(
    (latest, item) => item.month && item.month > latest ? item.month : latest,
    ""
  );
  const activeTargetCount = new Set(accountCalibrations.filter((item) => item.enabled).map((item) => item.target)).size;
  const sourceModeCount = sourceMode === "concept"
    ? filteredConceptCalibrationOptions.length
    : sourceMode === "event"
      ? filteredMajorEventCalibrationOptions.length
      : filteredStrategyCalibrationOptions.length;

  return (
    <PlannerPageShell
      icon={<ShieldCheck size={20} />}
      title="记账校准"
      action={(
        <button className="primary-button" type="button" onClick={() => addAccountCalibration("cash")}>
          <Plus size={16} /> 新建校准
        </button>
      )}
      summary={(
        <p>
          把某个月的模型余额校到真实账面值，差额会从该月起进入后续账本。收入、支出和贷款仍保留原始业务口径，校准只负责让账户状态重新对齐现实。
        </p>
      )}
    >
      <WorkflowSection
        icon={<Gauge size={18} />}
        title="校准状态"
        description="先确认当前覆盖范围和异常，再决定是否新增或调整记录。"
        className="calibration-overview-section"
      >
        <div className="calibration-status-grid">
          <article>
            <span>启用记录</span>
            <strong>{enabledCount}<small> / {accountCalibrations.length} 条</small></strong>
            <p>{enabledCount ? `覆盖 ${activeTargetCount} 类账户或资产` : "当前账本未应用手动校准"}</p>
          </article>
          <article className={calibrationWarnings.length ? "has-warning" : "is-clear"}>
            <span>待处理提示</span>
            <strong>{calibrationWarnings.length}<small> 项</small></strong>
            <p>{calibrationWarnings.length ? "存在重复、冲突或停用记录" : "未发现重复来源或同月冲突"}</p>
          </article>
          <article>
            <span>最近校准月份</span>
            <strong>{latestCalibrationMonth || "尚无"}</strong>
            <p>新增记录默认使用 {currentMonthText}</p>
          </article>
          <article>
            <span>测算末月状态</span>
            <strong>{latestSnapshot ? money(latestSnapshot.cash_balance) : "等待计算"}</strong>
            <p>{latestSnapshot ? `贷款余额 ${money(latestSnapshot.total_loan_balance)}` : "完成重算后显示现金与贷款"}</p>
          </article>
        </div>
        <div className="calibration-balance-rail" aria-label="核心对象余额摘要">
          {[
            { label: "流动资产", value: coreGroupMetricValue(liquidAssetGroup), count: coreGroupCountText(liquidAssetGroup), tone: "liquid" },
            { label: "政策受限账户", value: coreGroupMetricValue(restrictedAccountGroup), count: coreGroupCountText(restrictedAccountGroup), tone: "policy" },
            { label: "固定资产与目标", value: coreGroupMetricValue(fixedAssetGroup), count: coreGroupCountText(fixedAssetGroup), tone: "asset" },
            { label: "贷款账户", value: coreGroupMetricValue(loanAccountGroup), count: coreGroupCountText(loanAccountGroup), tone: "loan" }
          ].map((item) => (
            <article className={`calibration-balance-item ${item.tone}`} key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.count}</small>
            </article>
          ))}
        </div>
        {targetSummary.length ? (
          <div className="calibration-coverage-strip" aria-label="校准对象分布">
            <div>
              <strong>记录分布</strong>
              <span>按校准对象查看当前记录数量</span>
            </div>
            <div className="calibration-coverage-bars">
              {targetSummary.map((item) => (
                <span key={item.value} style={{ "--coverage": `${Math.max(16, item.count / Math.max(1, accountCalibrations.length) * 100)}%` } as CSSProperties}>
                  <i />
                  <b>{item.label}</b>
                  <em>{item.count}</em>
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </WorkflowSection>

      <WorkflowSection
        icon={<Database size={18} />}
        title="选择校准来源"
        description="可直接校准账户，也可以从重大事件或已生成策略带入来源信息。"
        className="calibration-source-section"
      >
        <div className="calibration-manual-strip">
          <div>
            <strong>直接按账户新增</strong>
            <span>适合已经拿到银行卡、券商、公积金或贷款的真实余额。</span>
          </div>
          <div className="calibration-target-actions">
            {ACCOUNT_CALIBRATION_TARGET_OPTIONS.map((option) => (
              <button className="ghost-button" type="button" key={option.value} onClick={() => addAccountCalibration(option.value)}>
                <Plus size={14} /> {option.label}
              </button>
            ))}
          </div>
        </div>
        <div className="calibration-source-switch" role="tablist" aria-label="校准来源类型">
          <button type="button" role="tab" aria-selected={sourceMode === "concept"} className={sourceMode === "concept" ? "active" : ""} onClick={() => setSourceMode("concept")}>
            <WalletCards size={16} /> 账户概念 <span>{conceptCalibrationOptions.length}</span>
          </button>
          <button type="button" role="tab" aria-selected={sourceMode === "event"} className={sourceMode === "event" ? "active" : ""} onClick={() => setSourceMode("event")}>
            <CalendarClock size={16} /> 重大事件 <span>{majorEventCalibrationOptions.length}</span>
          </button>
          <button type="button" role="tab" aria-selected={sourceMode === "strategy"} className={sourceMode === "strategy" ? "active" : ""} onClick={() => setSourceMode("strategy")}>
            <Sparkles size={16} /> 策略方案 <span>{strategyCalibrationOptions.length}</span>
          </button>
        </div>
        <div className="calibration-source-explorer">
          <div className="calibration-source-controls">
            {sourceMode === "concept" ? (
              <>
                <Field label="搜索账户概念">
                  <input type="search" value={conceptSourceQuery} placeholder="搜索现金、投资、公积金或贷款" onChange={(event) => setConceptSourceQuery(event.target.value)} />
                </Field>
                <Field label="选择来源">
                  <select value={selectedConcept?.key ?? ""} onChange={(event) => setSelectedConceptCode(event.target.value)}>
                    {filteredConceptCalibrationOptions.length ? filteredConceptCalibrationOptions.map((concept) => (
                      <option key={concept.key} value={concept.key}>{concept.name} · {money(concept.currentBalance)}</option>
                    )) : <option value="">没有匹配来源</option>}
                  </select>
                </Field>
              </>
            ) : sourceMode === "event" ? (
              <>
                <Field label="搜索重大事件">
                  <input type="search" value={eventSourceQuery} placeholder="搜索月份、目标或事件说明" onChange={(event) => setEventSourceQuery(event.target.value)} />
                </Field>
                <Field label="选择来源">
                  <select value={selectedEvent?.key ?? ""} onChange={(event) => setSelectedEventKey(event.target.value)}>
                    {filteredMajorEventCalibrationOptions.length ? filteredMajorEventCalibrationOptions.map((option) => (
                      <option key={option.key} value={option.key}>{option.label}</option>
                    )) : <option value="">没有匹配来源</option>}
                  </select>
                </Field>
              </>
            ) : (
              <>
                <Field label="搜索策略方案">
                  <input type="search" value={strategySourceQuery} placeholder="搜索策略类型、方案或归属目标" onChange={(event) => setStrategySourceQuery(event.target.value)} />
                </Field>
                <Field label="选择来源">
                  <select value={selectedStrategy?.key ?? ""} onChange={(event) => setSelectedStrategyId(event.target.value)}>
                    {filteredStrategyCalibrationOptions.length ? filteredStrategyCalibrationOptions.map((option) => (
                      <option key={option.key} value={option.key}>{option.label}</option>
                    )) : <option value="">没有匹配来源</option>}
                  </select>
                </Field>
              </>
            )}
            <small>当前匹配 {sourceModeCount} 个来源；添加后仍可在记录中修改月份、对象和真实余额。</small>
          </div>
          <div className="calibration-source-preview">
            {sourceMode === "concept" && selectedConcept ? (
              <>
                <span>账户概念</span>
                <strong>{selectedConcept.name}</strong>
                <b>{money(selectedConcept.currentBalance)}</b>
                <p>{selectedConcept.note}</p>
                <button className="primary-button" type="button" onClick={() => addConceptCalibration(selectedConcept)}><Plus size={15} /> 添加这条校准</button>
              </>
            ) : sourceMode === "event" && selectedEvent ? (
              <>
                <span>重大事件</span>
                <strong>{selectedEvent.label}</strong>
                <b>{money(selectedEvent.event.amount)}</b>
                <p>{selectedEvent.event.note}</p>
                <button className="primary-button" type="button" onClick={() => addMajorEventCalibration(selectedEvent.event)}><Plus size={15} /> 添加这条校准</button>
              </>
            ) : sourceMode === "strategy" && selectedStrategy ? (
              <>
                <span>策略方案</span>
                <strong>{selectedStrategy.label}</strong>
                <b>{money(defaultCalibrationAmount(targetForStrategyType(selectedStrategy.strategy.strategy_type)))}</b>
                <p>{selectedStrategy.searchText || "策略来源会随校准记录一起进入后端事件说明。"}</p>
                <button className="primary-button" type="button" onClick={() => addStrategyCalibration(selectedStrategy.strategy)}><Plus size={15} /> 添加这条校准</button>
              </>
            ) : (
              <EmptyState compact title="没有匹配来源" description="清空搜索条件，或直接从上方账户按钮新建校准。" />
            )}
          </div>
        </div>
      </WorkflowSection>

      <WorkflowSection
        icon={<ClipboardCheck size={18} />}
        title="校准记录"
        description="按记录顺序应用；同一月份、同一对象通常只保留最后确认的一条。"
        className="calibration-records-section"
      >
        {calibrationWarnings.length ? (
          <div className="warning-list calibration-warning-list">
            {calibrationWarnings.map((warning) => <span key={warning}>{warning}</span>)}
          </div>
        ) : accountCalibrations.length ? (
          <div className="calibration-clear-state"><CheckCircle2 size={16} /> 当前记录未发现重复来源或同月冲突。</div>
        ) : null}
        {accountCalibrations.length === 0 ? (
          <EmptyState
            title="尚未建立校准记录"
            description="先选择一个真实账户或事件来源。校准不会制造一笔虚构收入或支出，只会把指定月份的账户状态对齐真实账面。"
            action={<button className="primary-button" type="button" onClick={() => addAccountCalibration("cash")}><Plus size={16} /> 从现金账户开始</button>}
          />
        ) : (
          <div className="account-calibration-list">
            {accountCalibrations.map((calibration, index) => {
              const targetLabel = ACCOUNT_CALIBRATION_TARGET_OPTIONS.find((option) => option.value === calibration.target)?.label ?? calibration.target;
              const scopeLabel = accountCalibrationScopeLabels[calibration.calibration_scope ?? "account"];
              return (
                <article className={`calibration-record-card ${calibration.enabled ? "is-enabled" : "is-disabled"}`} key={`account-calibration-${index}`}>
                  <header>
                    <span className="calibration-record-index">{index + 1}</span>
                    <div>
                      <strong>{targetLabel}</strong>
                      <span>{calibration.month || "未设置月份"} · {scopeLabel}</span>
                    </div>
                    <SwitchField label={calibration.enabled ? "计入账本" : "暂不计入"} checked={calibration.enabled} onChange={(checked) => updateAccountCalibration(index, "enabled", checked)} />
                    <button className="icon-button danger" type="button" onClick={() => removeAccountCalibration(index)} aria-label={`删除第 ${index + 1} 条校准`}>
                      <Trash2 size={16} />
                    </button>
                  </header>
                  <div className="calibration-record-fields">
                    <Field label="校准月份">
                      <input type="month" value={calibration.month} onChange={(event) => updateAccountCalibration(index, "month", event.target.value)} />
                    </Field>
                    <Field label="校准范围">
                      <select value={calibration.calibration_scope ?? "account"} onChange={(event) => updateAccountCalibration(index, "calibration_scope", event.target.value as AccountCalibrationScope)}>
                        {Object.entries(accountCalibrationScopeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </Field>
                    <Field label="校准对象">
                      <select value={calibration.target} onChange={(event) => updateAccountCalibration(index, "target", event.target.value as AccountCalibrationTarget)}>
                        {ACCOUNT_CALIBRATION_TARGET_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </Field>
                    <NumberField label="真实余额/估值" value={calibration.amount} min={0} step={1000} onChange={(value) => updateAccountCalibration(index, "amount", value)} />
                    {(calibration.calibration_scope ?? "account") !== "account" ? (
                      <Field label="来源事件/策略">
                        <input value={calibration.source_title || calibration.reference_name} placeholder="如购房交易、购车策略、贷款切换" onChange={(event) => updateAccountCalibration(index, "source_title", event.target.value)} />
                      </Field>
                    ) : null}
                    <Field label="对象备注">
                      <input value={calibration.reference_name || calibration.note} placeholder="如某张银行卡、某只基金、某笔贷款" onChange={(event) => updateAccountCalibrationNote(index, event.target.value)} />
                    </Field>
                  </div>
                  <footer>
                    <span>{calibration.source_title || calibration.reference_name || "手动账户校准"}</span>
                    <strong>{calibration.month || currentMonthText} 起校到 {money(calibration.amount)}</strong>
                  </footer>
                </article>
              );
            })}
          </div>
        )}
        <p className="field-hint calibration-example-note">
          示例：某月模型现金为 8 万、真实现金为 7.2 万时，直接把该月现金账户校到 7.2 万；无需再添加一笔无法解释的手动支出。
        </p>
      </WorkflowSection>
    </PlannerPageShell>
  );
}

function ChildPlanPage({
  incomeMembers,
  childPlans,
  childPlanStrategies,
  childPlanStrategySourceLabel,
  updateChildPlan,
  updateChildPlanPatch,
  applyChildStrategyPatch,
  addChildPlan,
  duplicateChildPlan,
  removeChildPlan,
  openPlanningGoals
}: {
  incomeMembers: IncomeMember[];
  childPlans: ChildPlanData[];
  childPlanStrategies: ChildPlanStrategyPoint[];
  childPlanStrategySourceLabel: string;
  updateChildPlan: <K extends keyof ChildPlanData>(index: number, key: K, value: ChildPlanData[K]) => void;
  updateChildPlanPatch: (index: number, patch: Partial<ChildPlanData>) => void;
  applyChildStrategyPatch: (index: number, patch: Partial<ChildPlanData>) => void;
  addChildPlan: () => void;
  duplicateChildPlan: (index: number) => void;
  removeChildPlan: (index: number) => void;
  openPlanningGoals: () => void;
}) {
  const [selectedChildIndex, setSelectedChildIndex] = useState(0);
  const expenseStrategyParametersRef = useRef(new Map<string, Partial<ChildPlanData>>());
  childPlans.forEach((child, index) => {
    const ownerKey = child.planning_goal_id || `${child.name}:${index}`;
    expenseStrategyParametersRef.current.set(
      `${ownerKey}:${child.expense_strategy_mode}`,
      childExpenseStrategySnapshot(child)
    );
  });
  const expenseStrategyPatch = (
    child: ChildPlanData,
    index: number,
    mode: ChildPlanData["expense_strategy_mode"]
  ) => {
    const ownerKey = child.planning_goal_id || `${child.name}:${index}`;
    return expenseStrategyParametersRef.current.get(`${ownerKey}:${mode}`) ?? {
      expense_strategy_mode: mode,
      ...childExpensePresets[mode]
    };
  };
  const activeChildIndex = childPlans.length ? Math.min(selectedChildIndex, childPlans.length - 1) : 0;
  const activeChild = childPlans[activeChildIndex] ?? null;
  const today = useMemo(() => new Date(), []);
  const includedChildren = childPlans.filter(childPlanIsIncludedInPlanning).length;
  const plannedChildren = childPlans.filter(childPlanHasPlanningTiming).length;
  const totalCurrentMonthlyCost = childPlans
    .filter(childPlanIsIncludedInPlanning)
    .reduce((sum, child) => sum + childMonthlyCostAt(child, today), 0);
  const nextBirth = childPlans
    .map((child) => resolveChildBirthMonth(child))
    .filter((item): item is { year: number; month: number } => Boolean(item))
    .sort(compareMonth)[0];
  const strategyForChild = (child: ChildPlanData) => childPlanStrategyForChild(childPlanStrategies, child);
  const advisorText = childPlans.length === 0
    ? "当前没有子女目标。先添加计划，系统会把出生时间、教育阶段和养育支出放进家庭现金流。"
    : includedChildren === 0
      ? "已有子女目标都未纳入当前规划，现金流暂不受影响；需要测算时打开对应目标。"
      : `已有 ${includedChildren} 个子女目标进入测算，当前口径下月度养育支出约 ${money(totalCurrentMonthlyCost)}。`;

  return (
    <PlannerPageShell
      icon={<Sparkles size={20} />}
      title="养娃计划"
      summary={<p>先管理子女目标，再编辑当前选中目标的出生窗口、阶段支出和税务联动；策略说明会回答建议何时生、对买房和现金流有什么影响。</p>}
    >
      <section className="strategy-hero child-advisor-panel">
        <div className="strategy-hero-main">
          <div className="recommend-title">
            <h3>养娃策略</h3>
            <span>{includedChildren ? "测算中" : "待添加"}</span>
          </div>
          <p>{advisorText}</p>
          <div className="advisor-note-list child-advisor-notes">
            <p>养娃计划负责真实家庭事件和现金支出：备孕、孕期、生产、养育和教育阶段。专项附加扣除、扣除归属和互斥规则统一在“税务”页配置。</p>
            <p>如果没有设定计划出生时间段，后端会按“买房后开始计划”推定出生节点；如果有偏好的出生窗口，就填写起止月份，让策略在窗口内选择具体月份。</p>
          </div>
        </div>
        <div className="strategy-hero-side">
          <Metric label="纳入规划子女" value={`${includedChildren} 人`} />
          <Metric label="已有子女计划" value={`${childPlans.length} 项`} />
          <Metric label="计划中子女" value={`${plannedChildren} 项`} />
          <Metric label="策略来源" value={childPlanStrategySourceLabel} />
          <Metric label="当前月度养育支出" value={money(totalCurrentMonthlyCost)} />
          <Metric label="下一次出生节点" value={nextBirth ? `${nextBirth.year}年${nextBirth.month}月` : "未安排"} tone={nextBirth ? "good" : undefined} />
        </div>
      </section>

      <section className="strategy-layout child-workbench-layout">
      <WorkflowSection
        icon={<Target size={18} />}
        title="目标列表"
        description="子女目标用统一目标卡片比较和选择；详情区只编辑当前选中的子女目标。"
        className="strategy-main-panel child-goal-panel"
      >
        <div className="member-header compact-actions">
          <button className="ghost-button" type="button" onClick={addChildPlan}>
            <Plus size={16} /> 添加子女目标
          </button>
        </div>
        {childPlans.length === 0 ? (
          <EmptyState
            title="默认暂无养娃目标"
            description="添加子女目标后，页面会按出生时间、教育阶段和支出口径生成现金流影响说明。"
            action={<button className="ghost-button" type="button" onClick={addChildPlan}><Plus size={16} /> 添加子女目标</button>}
          />
        ) : (
          <div className="child-goal-grid horizontal-card-list">
            {childPlans.map((child, index) => {
              const strategy = strategyForChild(child);
              const birth = resolveChildBirthMonth(child);
              const ageText = child.birth_month ? formatAgeFromBirthMonth(child.birth_month, today) : (birth ? "计划中" : "待安排");
              const stageLabel = childEducationStageLabel(child, today);
              const monthlyCost = childMonthlyCostAt(child, today);
              const includedInPlanning = childPlanIsIncludedInPlanning(child);
              return (
                <article className={`planning-goal-card child-goal-card ${index === activeChildIndex ? "active" : ""}`} key={`child-goal-${index}`}>
                  <button className="planning-goal-select" type="button" onClick={() => setSelectedChildIndex(index)}>
                    <span className={includedInPlanning ? "goal-status enabled" : "goal-status paused"}>
                      {planningInclusionStatusLabel(includedInPlanning, child.enabled, { disabledLabel: "暂停测算" })}
                    </span>
                    <strong>{child.name || `子女目标 ${index + 1}`}</strong>
                    <small>{childPlanningTimingLabel(child)} · {strategy?.birth_month_label || (birth ? `${birth.year}年${birth.month}月` : "出生时间待定")}</small>
                    <em>{stageLabel} · 当前月支出 {money(monthlyCost)}</em>
                  </button>
                  <div className="child-mini-metrics">
                    <span><b>{ageText}</b><small>当前年龄</small></span>
                    <span><b>{strategy?.mother_age_at_birth ? `${strategy.mother_age_at_birth.toFixed(1)} 岁` : "待判断"}</b><small>母亲生产年龄</small></span>
                    <span><b>{strategy ? `${strategy.happiness_score}/10` : "待计算"}</b><small>养娃幸福指数</small></span>
                  </div>
                  <div className="planning-goal-actions">
                    <button className="ghost-button small" type="button" onClick={openPlanningGoals}>调整排期</button>
                    <button className="ghost-button small" type="button" onClick={() => duplicateChildPlan(index)} title="复制子女目标">
                      <Copy size={14} /> 复制
                    </button>
                    <button className="ghost-button small" type="button" onClick={() => removeChildPlan(index)} title="删除子女目标">
                      <Trash2 size={14} /> 删除
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </WorkflowSection>

      {activeChild ? (
        <WorkflowSection
          icon={<SlidersHorizontal size={18} />}
          title="当前目标配置"
          description="只展示当前选中子女目标的时间、支出和影响，避免多个完整表单纵向堆叠。"
          className="strategy-main-panel child-config-panel"
        >
          <div className="member-list roomy child-config-list">
            {(() => {
              const index = activeChildIndex;
              const child = activeChild;
              const strategy = strategyForChild(child);
              const strategyBirthMonth = childStrategyBirthMonthValue(strategy);
              const strategyBirthMonthAdopted = Boolean(
                strategyBirthMonth &&
                child.timing_mode === "manual_month" &&
                child.planned_birth_month === strategyBirthMonth &&
                child.planned_birth_start_month === strategyBirthMonth &&
                child.planned_birth_end_month === strategyBirthMonth
              );
              const birth = resolveChildBirthMonth(child);
              const stageLabel = childEducationStageLabel(child, today);
              const currentCost = childMonthlyCostAt(child, today);
              const annualCost = currentCost * 12;
              const includedInPlanning = childPlanIsIncludedInPlanning(child);
              return (
                <section className="member-card child-plan-card" key={`child-plan-editor-${index}`}>
                  <div className="member-card-head">
                    <div>
                      <strong>{child.name || `子女目标 ${index + 1}`}</strong>
                      <span>{stageLabel} · {birth ? `${birth.year}年${birth.month}月出生口径` : "出生节点待后端策略确定"}</span>
                    </div>
                    <span className={includedInPlanning ? "decision-pill good" : "decision-pill"}>{includedInPlanning ? "影响现金流" : "仅保留目标"}</span>
                  </div>
                  <div className="child-plan-layout">
                    <div className="child-plan-section">
                      <div className="subsection-title">
                        <CalendarClock size={15} />
                        <strong>策略与时间展示</strong>
                      </div>
                      {strategy ? (
                        <div className="child-strategy-card">
                          <div className="subsection-title">
                            <Sparkles size={15} />
                            <strong>策略建议</strong>
                          </div>
                          <div>
                            <span>策略建议出生月</span>
                            <strong>{strategy.birth_month_label || "等待购房策略或出生窗口"}</strong>
                          </div>
                          <div>
                            <span>母亲生产年龄</span>
                            <strong>{strategy.mother_age_at_birth ? `${strategy.mother_age_at_birth.toFixed(1)} 岁` : "无法自动判断"}</strong>
                          </div>
                          <div>
                            <span>幸福指数</span>
                            <strong>{strategy.happiness_score}/10</strong>
                          </div>
                          <p>{strategy.explanation}</p>
                          {strategy.warnings.length > 0 ? (
                            <ul>
                              {strategy.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                            </ul>
                          ) : null}
                          {strategyBirthMonth ? <p className="field-hint">如需采用这个出生月份，请到“规划目标”页将出生时间段设为 {strategyBirthMonth} 至 {strategyBirthMonth}。</p> : null}
                        </div>
                      ) : null}
                      <div className="form-grid compact-two">
                        <Field label="目标名称">
                          <input value={child.name} onChange={(event) => updateChildPlan(index, "name", event.target.value)} />
                        </Field>
                        <div className="planning-source-note compact-note">
                          <div><strong>统一排期</strong><span>{childPlanningTimingLabel(child)} · 出生时间段：{child.planned_birth_start_month || "不限"} 至 {child.planned_birth_end_month || "不限"}</span></div>
                          <button className="ghost-button small" type="button" onClick={openPlanningGoals}>到规划目标调整</button>
                        </div>
                        <Field label="实际出生年月">
                          <input type="month" value={child.birth_month} onChange={(event) => updateChildPlan(index, "birth_month", event.target.value)} />
                        </Field>
                        <Field label="教育阶段开始">
                          <input type="month" value={child.education_start_month} onChange={(event) => updateChildPlan(index, "education_start_month", event.target.value)} />
                        </Field>
                        <Field label="税务扣除归属">
                          <div className="readonly-metric compact">
                            {child.tax_deduction_owner || "到税务页指定"}
                          </div>
                        </Field>
                      </div>
                    </div>
                    <div className="child-plan-section">
                      <div className="subsection-title">
                        <CircleDollarSign size={15} />
                        <strong>支出口径</strong>
                      </div>
                      <div className="form-grid compact-two">
                        <Field label="费用策略">
                          <select
                            value={child.expense_strategy_mode}
                            onChange={(event) => {
                              const mode = event.target.value as ChildPlanData["expense_strategy_mode"];
                              applyChildStrategyPatch(index, expenseStrategyPatch(child, index, mode));
                            }}
                          >
                            <option value="balanced">均衡口径</option>
                            <option value="conservative">保守低支出口径</option>
                            <option value="quality">高投入口径</option>
                            <option value="manual">手动指定</option>
                          </select>
                        </Field>
                        <NumberField label="备孕提前月数" value={child.preparation_months_before_birth} min={0} max={24} step={1} onChange={(value) => updateChildPlan(index, "preparation_months_before_birth", value)} />
                        <NumberField label="孕期月数" value={child.pregnancy_months_before_birth} min={0} max={12} step={1} onChange={(value) => updateChildPlan(index, "pregnancy_months_before_birth", value)} />
                        <NumberField label="备孕月支出" value={child.monthly_preparation_cost} min={0} step={500} onChange={(value) => updateChildPlan(index, "monthly_preparation_cost", value)} />
                        <NumberField label="孕期月支出" value={child.monthly_pregnancy_cost} min={0} step={500} onChange={(value) => updateChildPlan(index, "monthly_pregnancy_cost", value)} />
                        <NumberField label="生产医疗一次性" value={child.birth_medical_cost} min={0} step={1000} onChange={(value) => updateChildPlan(index, "birth_medical_cost", value)} />
                        <NumberField label="产后恢复与照护" value={child.postpartum_recovery_cost} min={0} step={1000} onChange={(value) => updateChildPlan(index, "postpartum_recovery_cost", value)} />
                        <NumberField label="新生儿初始用品" value={child.initial_baby_supplies_cost} min={0} step={1000} onChange={(value) => updateChildPlan(index, "initial_baby_supplies_cost", value)} />
                      </div>
                      <div className="child-cost-grid">
                        <NumberField label="婴幼儿月支出" value={child.monthly_childcare_cost_before_kindergarten} min={0} step={500} onChange={(value) => updateChildPlan(index, "monthly_childcare_cost_before_kindergarten", value)} />
                        <NumberField label="幼儿园月支出" value={child.monthly_kindergarten_cost} min={0} step={500} onChange={(value) => updateChildPlan(index, "monthly_kindergarten_cost", value)} />
                        <NumberField label="中小学月支出" value={child.monthly_primary_secondary_cost} min={0} step={500} onChange={(value) => updateChildPlan(index, "monthly_primary_secondary_cost", value)} />
                        <NumberField label="高等教育月支出" value={child.monthly_higher_education_cost} min={0} step={500} onChange={(value) => updateChildPlan(index, "monthly_higher_education_cost", value)} />
                        <NumberField label="幼儿园入园一次性" value={child.kindergarten_entry_cost} min={0} step={1000} onChange={(value) => updateChildPlan(index, "kindergarten_entry_cost", value)} />
                        <NumberField label="中小学入学一次性" value={child.primary_school_entry_cost} min={0} step={1000} onChange={(value) => updateChildPlan(index, "primary_school_entry_cost", value)} />
                        <NumberField label="高等教育启动支出" value={child.higher_education_entry_cost} min={0} step={1000} onChange={(value) => updateChildPlan(index, "higher_education_entry_cost", value)} />
                      </div>
                      <div className="read-only-grid child-impact-grid">
                        <Metric label="当前阶段" value={stageLabel} />
                        <Metric label="当前月支出" value={money(currentCost)} />
                        <Metric label="当前年度口径" value={money(annualCost)} />
                      </div>
                      {strategy?.stages.length ? (
                        <div className="child-stage-list">
                          {strategy.stages.map((stage) => (
                            <span key={`${stage.name}-${stage.month_label}`}>
                              <b>{stage.name}</b>
                              <em>{stage.month_label || "待定"} · {stage.frequency}</em>
                              <strong>{money(stage.amount)}</strong>
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="child-impact-note">
                    <ShieldCheck size={15} />
                    <span>这部分金额会作为真实家庭支出进入现金流；子女教育、婴幼儿照护等专项附加扣除请在“税务”页按申报成员单独配置。</span>
                  </div>
                </section>
              );
            })()}
          </div>
        </WorkflowSection>
      ) : null}
      </section>
    </PlannerPageShell>
  );
}

function TaxPage({
  household,
  incomeMembers,
  childPlans,
  specialDeductions,
  result,
  taxStrategyItems,
  taxStrategyTimeline,
  taxStrategySourceLabel,
  updateHousehold,
  updateChildPlan,
  updateSpecialDeduction,
  addSpecialDeduction,
  removeSpecialDeduction
}: {
  household: HouseholdData;
  incomeMembers: IncomeMember[];
  childPlans: ChildPlanData[];
  specialDeductions: SpecialDeductionItemData[];
  result: AffordabilityResult | null;
  taxStrategyItems: TaxStrategyItem[];
  taxStrategyTimeline: TaxStrategyTimelinePoint[];
  taxStrategySourceLabel: string;
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
  updateChildPlan: <K extends keyof ChildPlanData>(index: number, key: K, value: ChildPlanData[K]) => void;
  updateSpecialDeduction: <K extends keyof SpecialDeductionItemData>(index: number, key: K, value: SpecialDeductionItemData[K]) => void;
  addSpecialDeduction: (deductionType?: SpecialDeductionItemData["deduction_type"]) => void;
  removeSpecialDeduction: (index: number) => void;
}) {
  const memberOptions = incomeMembers.length ? incomeMembers : [{ name: "成员 1" } as IncomeMember];
  const deductionLabels: Record<SpecialDeductionItemData["deduction_type"], string> = {
    child_education: "子女教育",
    infant_care: "婴幼儿照护",
    continuing_education: "继续教育",
    serious_illness: "大病医疗",
    housing_rent: "住房租金",
    mortgage_interest: "首套房贷利息",
    personal_pension: "个人养老金"
  };
  const profile = { ...defaultInvestmentTaxProfile, ...(household.investment_tax_profile ?? {}) };
  const updateInvestmentTaxProfile = <K extends keyof InvestmentTaxProfileData>(key: K, value: InvestmentTaxProfileData[K]) => {
    updateHousehold("investment_tax_profile", { ...profile, [key]: value });
  };
  const taxYearSummaries = result?.tax_year_summaries ?? [];
  const selectedYearSummary = taxYearSummaries[0];
  const taxMemberRows = selectedYearSummary?.summaries ?? result?.tax_summaries ?? [];
  const autoTaxStrategyItems = [...new Map(
    taxStrategyItems
      .filter((item) => item.source !== "manual")
      .map((item) => [[
        item.deduction_type,
        item.title,
        item.member_name,
        item.status,
        item.start_month,
        item.end_month ?? "",
        item.monthly_amount,
        item.annual_amount,
        item.cash_contribution
      ].join(":"), item] as const)
  ).values()];
  const manualTaxStrategyItems = taxStrategyItems.filter((item) => item.source === "manual");
  const displayTaxStrategyTimeline = [...new Map(
    taxStrategyTimeline.map((item) => [[
      item.month,
      item.category,
      item.title,
      item.action,
      item.member_name,
      item.status,
      item.amount,
      item.estimated_tax_saving
    ].join(":"), item] as const)
  ).values()];
  const childPlanIndexByName = new Map(childPlans.map((child, index) => [child.name, index]));
  const childTaxStrategyTarget = (item: TaxStrategyItem) => {
    if (item.deduction_type !== "infant_care" && item.deduction_type !== "child_education") return null;
    const childName = childPlans.find((child) => item.title.startsWith(child.name))?.name ?? "";
    const index = childName ? childPlanIndexByName.get(childName) : undefined;
    return typeof index === "number" ? { childName, index } : null;
  };
  const enabledMonthlyDeductions = specialDeductions.filter((item) => item.enabled && item.settlement_mode === "monthly_withholding");
  const enabledAnnualDeductions = specialDeductions.filter((item) => item.enabled && item.settlement_mode === "annual_settlement");
  const monthlyDeductionTotal = enabledMonthlyDeductions.reduce((sum, item) => sum + Math.max(0, item.monthly_amount), 0);
  const annualDeductionTotal = enabledAnnualDeductions.reduce((sum, item) => sum + Math.max(0, item.annual_amount), 0);
  const rentMortgageConflict = taxStrategyItems.some((item) => item.status === "auto_enabled" && item.deduction_type === "housing_rent") &&
    taxStrategyItems.some((item) => item.status === "auto_enabled" && item.deduction_type === "mortgage_interest");
  const taxStrategyStatusLabel: Record<string, string> = {
    auto_enabled: "策略启用",
    manual_enabled: "手动覆盖",
    available: "待指定",
    not_applicable: "暂不适用",
    conflict: "互斥"
  };
  const taxStrategyItemStatusLabel = (item: Pick<TaxStrategyItem, "deduction_type" | "status" | "long_term_cash_risk_month">) =>
    item.deduction_type === "personal_pension" && item.status === "conflict"
      ? item.long_term_cash_risk_month ? "现金安全停缴" : "暂不开户更优"
      : taxStrategyStatusLabel[item.status] ?? "策略项";
  const taxTimelineCategoryLabel: Record<TaxStrategyTimelinePoint["category"], string> = {
    deduction_assignment: "扣除归属",
    deduction_switch: "扣除切换",
    personal_pension: "个人养老金",
    bonus_tax: "奖金计税",
    investment_tax: "理财税务",
    annual_settlement: "年度汇算",
    manual_override: "手动覆盖"
  };
  const taxTimelineCategoryTone: Record<TaxStrategyTimelinePoint["category"], string> = {
    deduction_assignment: "deduction",
    deduction_switch: "deduction",
    personal_pension: "pension",
    bonus_tax: "tax",
    investment_tax: "investment",
    annual_settlement: "settlement",
    manual_override: "manual"
  };
  const timelineSavingTotal = displayTaxStrategyTimeline.reduce((sum, item) => sum + Math.max(0, item.estimated_tax_saving ?? 0), 0);
  const nextTimelinePoint = displayTaxStrategyTimeline.find((item) => item.month >= 0);
  const investmentTaxTimeline = displayTaxStrategyTimeline.find((item) => item.category === "investment_tax");
  const investmentTaxWeightedRate =
    profile.deposit_interest_ratio * profile.deposit_interest_tax_rate +
    profile.fund_dividend_ratio * profile.fund_dividend_tax_rate +
    profile.stock_dividend_short_ratio * profile.stock_dividend_short_holding_tax_rate +
    profile.stock_dividend_long_ratio * profile.stock_dividend_long_holding_tax_rate +
    profile.bond_interest_ratio * profile.bond_interest_tax_rate +
    profile.overseas_asset_ratio * profile.overseas_asset_tax_rate;
  const taxStrategyNotes = [
    "工资薪金按成员收入阶段逐月累计预扣预缴；年终奖支持发放月一次性入账或按月均摊发放，后端会按对应税务口径计算。",
    "住房租金会根据租房阶段自动进入后端税务计算；首套房贷利息会根据选中购房策略生成策略项，和租金互斥的选择由税务策略说明。",
    "个人养老金账户已经放在家庭财务的成员卡片里管理。自动策略只有在完整账本长期可行时才缴费；若领取前存在现金穿底且停缴能改善风险，系统会保留既有余额并停止新增缴费。",
    "理财税务不混入工资个税；它按投资收益的应税来源占比和税率扣减投资账户收益，用于比较税后理财策略。"
  ];

  return (
    <PlannerPageShell
      icon={<CircleDollarSign size={20} />}
      title="税务"
      summary={<p>税务页按“年度税务策略、专项附加扣除、工资年终奖口径、理财税务”组织；后端生成长期策略时间线和成员税负，前端只负责申报归属、手动覆盖和口径配置。</p>}
    >

      <WorkflowSection
        icon={<ShieldCheck size={18} />}
        title="自动策略"
        description="后端会把收入阶段、购房租房、养娃、个人养老金和理财收益税统一编排成长期税务动作，而不是只看某一个月份。"
        className="tax-timeline-panel"
      >
        <div className="metric-grid">
          <Metric label="下一次策略动作" value={nextTimelinePoint ? `${nextTimelinePoint.year}-${String(nextTimelinePoint.month_of_year).padStart(2, "0")}` : "等待后端生成"} />
          <Metric label="时间线节点" value={`${displayTaxStrategyTimeline.length} 个`} />
          <Metric label="策略来源" value={taxStrategySourceLabel} />
          <Metric label="已估算节税" value={money(timelineSavingTotal)} tone={timelineSavingTotal > 0 ? "good" : undefined} />
          <Metric label="理财有效税率" value={percent(investmentTaxTimeline?.amount ?? investmentTaxWeightedRate)} />
        </div>
        {displayTaxStrategyTimeline.length > 0 ? (
          <div className="tax-strategy-timeline">
            {displayTaxStrategyTimeline.slice(0, 16).map((item, index) => (
              <article className="tax-timeline-item" key={`${item.category}-${item.title}-${item.year}-${item.month_of_year}-${index}`}>
                <div className={`tax-timeline-dot ${taxTimelineCategoryTone[item.category]}`} />
                <div className="tax-timeline-date">
                  <strong>{item.year}-{String(item.month_of_year).padStart(2, "0")}</strong>
                  <span>{taxTimelineCategoryLabel[item.category]}</span>
                </div>
                <div className="tax-timeline-main">
                  <div className="tax-timeline-title">
                    <strong>{item.action}</strong>
                    <StrategyStatePill active={item.status === "auto_enabled" || item.status === "manual_enabled"} recommended={item.status === "available"} label={item.deduction_type === "personal_pension" && item.status === "conflict" ? "暂不开户/停缴" : taxStrategyStatusLabel[item.status] ?? "策略项"} />
                  </div>
                  <p>{item.title}{item.member_name ? ` · ${item.member_name}` : ""}</p>
                  <small>{item.detail}</small>
                </div>
                <div className="tax-timeline-value">
                  {item.amount > 0 ? <Metric label={item.category === "investment_tax" ? "有效税率" : "金额"} value={item.category === "investment_tax" ? percent(item.amount) : money(item.amount)} /> : null}
                  {item.estimated_tax_saving > 0 ? <Metric label="估算节税" value={money(item.estimated_tax_saving)} tone="good" /> : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="field-hint">等待后端生成税务策略时间线。配置收入阶段、租房/购房计划、子女计划或个人养老金后，这里会显示长期税务动作。</p>
        )}
        {displayTaxStrategyTimeline.length > 16 ? (
          <p className="field-hint">已展示最近 16 个税务动作；完整时间线仍由后端保留在计算结果中，后续可用于导出。</p>
        ) : null}
      </WorkflowSection>

      <WorkflowSection
        icon={<Gauge size={18} />}
        title="工资年终奖口径"
        description="这里说明工资薪金、年终奖和年度口径的计算方式，具体金额以后端成员明细为准。"
        className="tax-strategy-panel"
      >
        <div className="metric-grid">
          <Metric label="年度个税" value={money(selectedYearSummary?.total_tax ?? result?.annual_income_tax ?? 0)} />
          <Metric label="年度税前收入" value={money(selectedYearSummary?.gross_annual_income ?? ((result?.household_gross_monthly_income ?? 0) * 12))} />
          <Metric label="月度手动扣除" value={money(monthlyDeductionTotal)} />
          <Metric label="年度汇算扣除" value={money(annualDeductionTotal)} />
        </div>
        <div className="strategy-grid tax-strategy-grid">
          <article className="strategy-card active">
            <div className="strategy-card-head">
              <strong>年终奖择优计税</strong>
              <StrategyStatePill active label="后端自动" />
            </div>
            <p>每个收入阶段可以设置年终奖发放方式、发放月份和计税方式。一次性发放可在单独计税和并入综合所得之间择优；按月均摊发放会进入工资薪金累计预扣，不适用全年一次性奖金单独计税。</p>
          </article>
          <article className="strategy-card active">
            <div className="strategy-card-head">
              <strong>专项附加扣除最优使用</strong>
              <StrategyStatePill active label="可手动" />
            </div>
            <p>住房租金、首套房贷利息、子女教育、婴幼儿照护、继续教育、大病医疗、赡养老人和个人养老金分别建模。月度扣除影响预扣预缴，年度汇算型扣除只在年度口径体现。</p>
          </article>
          <article className="strategy-card active">
            <div className="strategy-card-head">
              <strong>理财税后收益口径</strong>
              <StrategyStatePill active label="独立于工资税" />
            </div>
            <p>投资收益税按理财账户收益扣减，不进入工资薪金个税，也不混入家庭消费支出。策略比较时应看税后收益、买卖手续费和现金安全垫。</p>
          </article>
        </div>
        {rentMortgageConflict ? (
          <p className="warning-text">已同时配置住房租金和首套房贷利息扣除。若规则包启用互斥，后端会按同月更优项处理；请确认真实申报口径。</p>
        ) : null}
      </WorkflowSection>

      <WorkflowSection
        icon={<CircleDollarSign size={18} />}
        title="专项附加扣除"
        description="住房租金、首套住房贷款利息、子女相关扣除和个人养老金默认由后端根据事件生成；只在真实申报口径不同的时候添加手动覆盖。"
      >
        <p className="field-hint">住房租金、首套住房贷款利息、子女相关扣除和个人养老金默认由后端根据租房、购房、养娃和收入事件生成税务策略；用户只在需要覆盖真实申报口径时添加手动项。</p>
        <div className="tax-auto-strategy-grid">
          {autoTaxStrategyItems.map((item, itemIndex) => {
            const childTarget = childTaxStrategyTarget(item);
            const assignedMember = childTarget ? childPlans[childTarget.index]?.tax_deduction_owner || "" : item.member_name;
            return (
              <article className={`tax-strategy-item ${item.status}`} key={`${item.deduction_type}-${item.title}-${item.start_month}-${itemIndex}`}>
                <div className="strategy-card-head">
                  <strong>{item.title}</strong>
                  <StrategyStatePill active={item.status === "auto_enabled"} recommended={item.status === "available"} label={taxStrategyItemStatusLabel(item)} />
                </div>
                <div className="tax-strategy-metrics">
                  {childTarget ? (
                    <Field label="申报成员">
                      <select value={assignedMember} onChange={(event) => updateChildPlan(childTarget.index, "tax_deduction_owner", event.target.value)}>
                        <option value="">选择成员后启用</option>
                        {memberOptions.map((member, memberIndex) => <option key={`child-tax-owner-${childTarget.index}-${memberIndex}`} value={member.name}>{member.name}</option>)}
                      </select>
                    </Field>
                  ) : (
                    <Metric label="申报成员" value={item.member_name || "后端策略生成"} />
                  )}
                  <Metric label="月扣除" value={money(item.monthly_amount)} />
                  <Metric label="年度扣除" value={money(item.annual_amount)} />
                  {item.deduction_type === "personal_pension" ? (
                    <>
                      <Metric label="首个计划年缴费" value={money(item.cash_contribution)} />
                      <Metric label="首个计划年节税" value={money(item.estimated_tax_saving)} />
                      <Metric label="本年按上限缴费节税" value={money(item.full_cap_annual_tax_saving)} />
                      <Metric label="累计计划缴费" value={money(item.cumulative_contribution)} />
                      <Metric label="累计名义节税" value={money(item.cumulative_estimated_tax_saving)} />
                      <Metric label="退休前年化" value={percent(item.account_return_rate)} />
                      <Metric label="退休后年化" value={percent(item.post_retirement_return_rate)} />
                      <Metric label="预计领取起点余额" value={money(item.estimated_retirement_balance)} />
                      <Metric label="预计首月净领取" value={money(item.estimated_monthly_withdrawal)} />
                      <Metric label="养老金净领取终值" value={money(item.pension_net_value_at_withdrawal)} />
                      <Metric label="改投普通理财终值" value={money(item.alternative_investment_value_at_withdrawal)} />
                      <Metric label="放弃的理财收益" value={money(item.forgone_investment_earnings)} />
                      <Metric label="节税再投资终值" value={money(item.tax_saving_future_value)} />
                      <Metric label="相对普通理财净增益" value={money(item.net_advantage_at_withdrawal)} tone={item.net_advantage_at_withdrawal > 0 ? "good" : item.full_cap_net_advantage_at_withdrawal < 0 ? "bad" : undefined} />
                      <Metric label="开始领取" value={item.withdrawal_start_month || "退休时"} />
                      <Metric label="领取税率" value={percent(item.withdrawal_tax_rate)} />
                      {item.long_term_cash_risk_month ? <Metric label="长期现金穿底" value={item.long_term_cash_risk_month} /> : null}
                    </>
                  ) : null}
                  <Metric label="生效区间" value={`${item.start_month || "待事件"}${item.end_month ? ` 至 ${item.end_month}` : ""}`} />
                </div>
                <p>{childTarget && !assignedMember ? "该扣除来自养娃计划。请选择申报成员，后端会在下一次计算中启用并进入对应成员个税。" : item.reason}</p>
                {item.deduction_type === "personal_pension" && item.personal_pension_annual_plan.length > 0 ? (
                  <details className="details-panel">
                    <summary>
                      <span>查看年度最优缴费计划</span>
                      <small>{item.personal_pension_annual_plan.length} 个缴费年度</small>
                    </summary>
                    <div className="compact-table personal-pension-plan-table">
                      <div className="compact-table-head"><span>年度</span><span>缴费</span><span>当年节税</span><span>相对理财净增益</span></div>
                      {item.personal_pension_annual_plan.map((point) => (
                        <div className="compact-table-row" key={`${item.member_name}-${point.year}`}>
                          <span>{point.year}</span>
                          <span>{money(point.annual_contribution)}</span>
                          <span>{money(point.estimated_tax_saving)}</span>
                          <span>{money(point.net_advantage_at_withdrawal)}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                ) : null}
                {item.deduction_type === "personal_pension" && item.recommended_action ? <p className="tax-conflict-note">{item.recommended_action}</p> : null}
                {item.conflicts_with.length ? (
                  <span className="tax-conflict-note">与 {item.conflicts_with.map((type) => deductionLabels[type]).join("、")} 同月互斥，后端按税务策略择优。</span>
                ) : null}
              </article>
            );
          })}
        </div>
        <details className="details-panel tax-manual-panel">
          <summary>
            <span>手动覆盖专项附加扣除</span>
            <small>{manualTaxStrategyItems.length ? `已有 ${manualTaxStrategyItems.length} 个启用覆盖项` : "默认不需要手动配置"}</small>
          </summary>
          <div className="tax-deduction-action-grid">
            {(["housing_rent", "mortgage_interest", "continuing_education", "serious_illness", "child_education", "infant_care", "personal_pension"] as SpecialDeductionItemData["deduction_type"][]).map((type) => (
              <button className="tax-deduction-action" type="button" key={type} onClick={() => addSpecialDeduction(type)}>
                <Plus size={15} />
                <span>{deductionLabels[type]}</span>
              </button>
            ))}
          </div>
          <p className="field-hint">住房租金和首套住房贷款利息不能同时享受；继续教育、大病医疗适合年度汇算口径。手动覆盖只用于真实申报与系统事件不一致的情况。</p>
          <div className="member-list roomy">
            {specialDeductions.length > 0 ? specialDeductions.map((item, index) => (
              <section className="member-card" key={`tax-deduction-${index}`}>
              <div className="member-card-head">
                <strong>{item.name || deductionLabels[item.deduction_type]}</strong>
                <button className="icon-button" type="button" onClick={() => removeSpecialDeduction(index)} aria-label="删除扣除项" title="删除扣除项">
                  <Trash2 size={15} />
                </button>
              </div>
              <div className="form-grid three">
                <SwitchField label="启用扣除" checked={item.enabled} onChange={(checked) => updateSpecialDeduction(index, "enabled", checked)} />
                <Field label="扣除名称">
                  <input value={item.name} onChange={(event) => updateSpecialDeduction(index, "name", event.target.value)} />
                </Field>
                <Field label="扣除类型">
                  <select value={item.deduction_type} onChange={(event) => updateSpecialDeduction(index, "deduction_type", event.target.value as SpecialDeductionItemData["deduction_type"])}>
                    {Object.entries(deductionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </Field>
                <Field label="申报成员">
                  <select value={item.member_name} onChange={(event) => updateSpecialDeduction(index, "member_name", event.target.value)}>
                    <option value="">暂不指定</option>
                    {memberOptions.map((member, memberIndex) => <option key={`tax-deduction-member-${memberIndex}`} value={member.name}>{member.name}</option>)}
                  </select>
                </Field>
                <Field label="开始年月">
                  <input type="month" value={item.start_month} onChange={(event) => updateSpecialDeduction(index, "start_month", event.target.value)} />
                </Field>
                <Field label="结束年月">
                  <input type="month" value={item.end_month ?? ""} onChange={(event) => updateSpecialDeduction(index, "end_month", event.target.value || null)} />
                </Field>
                <Field label="扣除口径">
                  <select value={item.settlement_mode} onChange={(event) => updateSpecialDeduction(index, "settlement_mode", event.target.value as SpecialDeductionItemData["settlement_mode"])}>
                    <option value="monthly_withholding">月度预扣预缴</option>
                    <option value="annual_settlement">年度汇算</option>
                  </select>
                </Field>
                <NumberField label="月扣除金额" value={item.monthly_amount} min={0} step={100} onChange={(value) => updateSpecialDeduction(index, "monthly_amount", value)} />
                <NumberField label="年度扣除金额" value={item.annual_amount} min={0} step={500} onChange={(value) => updateSpecialDeduction(index, "annual_amount", value)} />
                {item.deduction_type === "mortgage_interest" ? (
                  <>
                    <SwitchField label="首套住房贷款" checked={item.is_first_home_loan} onChange={(checked) => updateSpecialDeduction(index, "is_first_home_loan", checked)} />
                    <NumberField label="已享受月数" value={item.claimed_months_used} min={0} max={240} step={1} onChange={(value) => updateSpecialDeduction(index, "claimed_months_used", value)} />
                  </>
                ) : null}
              </div>
              </section>
            )) : (
              <p className="field-hint">当前没有手动覆盖项。租房、购房、养娃、个人养老金等常见扣除会先由后端税务策略根据事件自动生成。</p>
            )}
          </div>
        </details>
      </WorkflowSection>

      <WorkflowSection
        icon={<TrendingUp size={18} />}
        title="理财税务"
        description="理财收益税按投资账户收益扣减，不进入工资薪金个税，也不作为生活支出重复计算。"
      >
        <div className="advisor-note-list tax-note-list">
          <p>{investmentTaxTimeline?.detail ?? "当前理财收益税口径由后端按理财税参数折算有效税率，并直接扣减投资账户收益。它不进入工资薪金个税，也不作为生活支出重复计算。"}</p>
          <p>理财策略比较应使用税后收益、手续费、现金安全垫和买房买车时间的综合结果。修改理财税务参数后，后端会重新生成投资账户曲线和相关策略。</p>
        </div>
        <p className="field-hint">这些参数用于估算投资账户收益的税后效果。未手动填写来源占比时，后端会按当前理财策略的权益、固收、现金配置自动估算；手动填写后作为覆盖口径。</p>
        <div className="form-grid three">
          <NumberField label="存款利息占比" value={profile.deposit_interest_ratio} min={0} max={1} step={0.05} onChange={(value) => updateInvestmentTaxProfile("deposit_interest_ratio", value)} />
          <NumberField label="存款利息税率" value={profile.deposit_interest_tax_rate} min={0} max={1} step={0.01} onChange={(value) => updateInvestmentTaxProfile("deposit_interest_tax_rate", value)} />
          <NumberField label="基金分红占比" value={profile.fund_dividend_ratio} min={0} max={1} step={0.05} onChange={(value) => updateInvestmentTaxProfile("fund_dividend_ratio", value)} />
          <NumberField label="基金分红税率" value={profile.fund_dividend_tax_rate} min={0} max={1} step={0.01} onChange={(value) => updateInvestmentTaxProfile("fund_dividend_tax_rate", value)} />
          <NumberField label="股票短持分红占比" value={profile.stock_dividend_short_ratio} min={0} max={1} step={0.05} onChange={(value) => updateInvestmentTaxProfile("stock_dividend_short_ratio", value)} />
          <NumberField label="股票短持分红税率" value={profile.stock_dividend_short_holding_tax_rate} min={0} max={1} step={0.01} onChange={(value) => updateInvestmentTaxProfile("stock_dividend_short_holding_tax_rate", value)} />
          <NumberField label="股票长持分红占比" value={profile.stock_dividend_long_ratio} min={0} max={1} step={0.05} onChange={(value) => updateInvestmentTaxProfile("stock_dividend_long_ratio", value)} />
          <NumberField label="股票长持分红税率" value={profile.stock_dividend_long_holding_tax_rate} min={0} max={1} step={0.01} onChange={(value) => updateInvestmentTaxProfile("stock_dividend_long_holding_tax_rate", value)} />
          <NumberField label="债券利息占比" value={profile.bond_interest_ratio} min={0} max={1} step={0.05} onChange={(value) => updateInvestmentTaxProfile("bond_interest_ratio", value)} />
          <NumberField label="债券利息税率" value={profile.bond_interest_tax_rate} min={0} max={1} step={0.01} onChange={(value) => updateInvestmentTaxProfile("bond_interest_tax_rate", value)} />
          <NumberField label="境外资产占比" value={profile.overseas_asset_ratio} min={0} max={1} step={0.05} onChange={(value) => updateInvestmentTaxProfile("overseas_asset_ratio", value)} />
          <NumberField label="境外资产税率" value={profile.overseas_asset_tax_rate} min={0} max={1} step={0.01} onChange={(value) => updateInvestmentTaxProfile("overseas_asset_tax_rate", value)} />
          <NumberField label="简化应税收益比例" value={household.investment_taxable_return_ratio ?? 0} min={0} max={1} step={0.05} onChange={(value) => updateHousehold("investment_taxable_return_ratio", value)} />
          <NumberField label="简化理财收益税率" value={household.investment_return_tax_rate ?? 0} min={0} max={1} step={0.01} onChange={(value) => updateHousehold("investment_return_tax_rate", value)} />
        </div>
      </WorkflowSection>

      <WorkflowSection
        icon={<ClipboardCheck size={18} />}
        title="成员年度税负明细"
        description="成员年度结果由后端根据收入阶段、专项扣除、年终奖和税务策略生成。"
      >
        {taxMemberRows.length > 0 ? (
          <div className="tax-detail-table">
            <span>成员</span>
            <span>税前收入</span>
            <span>应税所得</span>
            <span>工资个税</span>
            <span>年终奖个税</span>
            <span>计税方式</span>
            {taxMemberRows.map((item) => (
              <div className="tax-detail-row" key={`${item.member_name}-${item.gross_annual_income}`}>
                <span>{item.member_name}</span>
                <span>{money(item.gross_annual_income)}</span>
                <span>{money(item.taxable_income)}</span>
                <span>{money(item.salary_tax)}</span>
                <span>{money(item.bonus_tax)}</span>
                <span>{bonusTaxMethodLabels[item.selected_bonus_method] ?? item.selected_bonus_method}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="field-hint">等待后端生成税务结果。填写收入阶段并完成计算后，这里会展示成员年度税务明细。</p>
        )}
      </WorkflowSection>
    </PlannerPageShell>
  );
}

function InvestmentPlanPage({
  household,
  scenario,
  result,
  accountConcepts,
  investmentRecommendations,
  investmentRecommendationSourceLabel,
  updateHousehold,
  updateHouseholdPatch,
  updateInvestmentAnnualReturn
}: {
  household: HouseholdData;
  scenario: ScenarioData;
  result: AffordabilityResult | null;
  accountConcepts: AccountConceptSummary[];
  investmentRecommendations: InvestmentPlanRecommendation[];
  investmentRecommendationSourceLabel: string;
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
  updateHouseholdPatch: (patch: Partial<HouseholdData>) => void;
  updateInvestmentAnnualReturn: (annualReturn: number) => void;
}) {
  const latestRecommendationsRef = useRef<InvestmentPlanRecommendation[]>([]);
  const investmentPlanParametersRef = useRef(new Map<string, InvestmentPlanRecommendation>());
  if (investmentRecommendations.length) {
    latestRecommendationsRef.current = investmentRecommendations;
  }
  const recommendations =
    investmentRecommendations.length
      ? investmentRecommendations
      : latestRecommendationsRef.current;
  const recommendedInvestment = recommendations[0];
  const currentInvestmentAllocation =
    result?.current_investment_allocation ?? {
      monthly_surplus: 0,
      reserve_target: 0,
      reserve_gap: 0,
      base_investment: 0,
      cash_sweep_investment: 0,
      total_investment: 0,
      buy_fee: 0,
      net_investment: 0
    };
  const manualRecommendation: InvestmentPlanRecommendation = {
    variant: "手动指定",
    plan_name: "manual_investment",
    risk_level: household.investment_risk_level ?? "conservative",
    risk_label: investmentRiskLabels[household.investment_risk_level ?? "conservative"] ?? "自定义",
    description: "按上方手动填写的月定投、现金安全垫、资产比例和年化收益测算。",
    monthly_investment: household.monthly_investment_amount ?? 0,
    annual_return: scenario.annual_investment_return ?? 0,
    after_tax_annual_return: 0,
    risk_adjusted_annual_return: 0,
    cash_reserve_months: household.investment_cash_reserve_months ?? 6,
    liquidity_horizon_months: null,
    goal_liquidity_target: 0,
    goal_liquidity_gap: 0,
    monthly_goal_saving: 0,
    equity_ratio: household.investment_equity_ratio ?? 0.25,
    bond_ratio: household.investment_bond_ratio ?? 0.45,
    cash_ratio: household.investment_cash_ratio ?? 0.3,
    score: 0,
    reasons: [
      `使用当前已设定投 ${money(household.monthly_investment_amount ?? 0)}/月`,
      `现金安全垫按 ${household.investment_cash_reserve_months ?? 6} 个月支出控制`,
      `目标配置：权益 ${percent(household.investment_equity_ratio ?? 0.25)}、固收 ${percent(household.investment_bond_ratio ?? 0.45)}、现金 ${percent(household.investment_cash_ratio ?? 0.3)}`
    ]
  };
  const displayedRecommendations = [manualRecommendation, ...recommendations];
  const activeInvestmentPlanName = household.investment_plan_name ?? "conservative_monthly_investment";
  const activeInvestmentRecommendationName =
    investmentPlanRecommendationAliases[activeInvestmentPlanName] ?? activeInvestmentPlanName;
  const activeRecommendation =
    displayedRecommendations.find((item) => item.plan_name === activeInvestmentPlanName) ??
    displayedRecommendations.find((item) => item.plan_name === activeInvestmentRecommendationName) ??
    manualRecommendation;
  for (const plan of displayedRecommendations) {
    investmentPlanParametersRef.current.set(plan.plan_name, plan);
  }
  const investmentReasonText =
    !result
      ? "等待后端计算理财推荐；推荐、月结余和安全垫都以后端返回为准。"
      : (recommendedInvestment?.monthly_investment ?? 0) > 0
        ? `系统建议先保留现金安全垫 ${money(currentInvestmentAllocation.reserve_target)}；${recommendedInvestment?.liquidity_horizon_months !== undefined && recommendedInvestment?.liquidity_horizon_months !== null ? `最近重大目标约 ${recommendedInvestment.liquidity_horizon_months} 个月后，目标资金每月优先留存 ${money(recommendedInvestment.monthly_goal_saving ?? 0)}；` : ""}现金垫不足时先补现金，现金垫超额时再按节奏追加定投。当前最高分方案建议 ${money(recommendedInvestment?.monthly_investment ?? 0)}/月。`
        : currentInvestmentAllocation.reserve_gap > 0
          ? `系统建议月定投为 0，是因为现金安全垫还差 ${money(currentInvestmentAllocation.reserve_gap)}，当前月结余会优先补足现金池和购房首付，不先进入波动资产。`
          : "系统建议月定投为 0，是因为当前最高分方案选择了“暂停定投保现金”；可在下方采用稳健/均衡/进取方案后再手动微调。";
  const allocationData = [
    { name: "权益", 比例: Math.round((household.investment_equity_ratio ?? 0.25) * 100) },
    { name: "固收", 比例: Math.round((household.investment_bond_ratio ?? 0.45) * 100) },
    { name: "现金", 比例: Math.round((household.investment_cash_ratio ?? 0.3) * 100) }
  ];
  const investmentAccountBalanceText = accountConceptBalanceTextWithHouseholdFallback(
    accountConcepts,
    ACCOUNT_CONCEPT_CODES.investment,
    household
  );
  const applyInvestmentPlan = (plan: InvestmentPlanRecommendation) => {
    const cachedPlan = investmentPlanParametersRef.current.get(plan.plan_name) ?? plan;
    updateHouseholdPatch({
      investment_plan_name: cachedPlan.plan_name,
      investment_risk_level: cachedPlan.risk_level,
      monthly_investment_amount: cachedPlan.monthly_investment,
      investment_cash_reserve_months: cachedPlan.cash_reserve_months,
      investment_equity_ratio: cachedPlan.equity_ratio,
      investment_bond_ratio: cachedPlan.bond_ratio,
      investment_cash_ratio: cachedPlan.cash_ratio,
      investment_auto_rebalance: true
    });
    updateInvestmentAnnualReturn(cachedPlan.annual_return);
  };
  const selectInvestmentPlan = (planName: string) => {
    const recommendationName = investmentPlanRecommendationAliases[planName] ?? planName;
    const plan = displayedRecommendations.find((item) => item.plan_name === recommendationName);
    if (plan) {
      applyInvestmentPlan(plan);
      return;
    }
    if (planName === "cash_only") {
      updateHouseholdPatch({
        investment_plan_name: planName,
        investment_risk_level: "cash",
        monthly_investment_amount: 0,
        investment_equity_ratio: 0,
        investment_bond_ratio: 0,
        investment_cash_ratio: 1,
        investment_auto_rebalance: false
      });
      updateInvestmentAnnualReturn(0);
      return;
    }
    updateHousehold("investment_plan_name", planName);
  };
  const updateManualInvestmentHousehold = <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => {
    updateHouseholdPatch({ investment_plan_name: "manual_investment", [key]: value } as Partial<HouseholdData>);
  };
  const updateManualInvestmentAnnualReturn = (value: number) => {
    updateHousehold("investment_plan_name", "manual_investment");
    updateInvestmentAnnualReturn(value);
  };
  const portfolioStrategy =
    result?.portfolio_strategy_recommendations?.find((item) => item.is_recommended) ??
    result?.portfolio_strategy_recommendations?.[0];

  return (
    <PlannerPageShell
      icon={<TrendingUp size={20} />}
      title="理财计划"
      summary={<p>先选择理财策略方案，再编辑当前策略的现金安全垫、定投规则、资产比例、手续费税务和再平衡规则；后端会把实际定投、收益复利、手续费和税后收益纳入账户曲线。</p>}
    >
      <section className="strategy-hero investment-dashboard">
        <div className="strategy-hero-main">
          <div className="recommend-title">
            <h3>{activeRecommendation?.variant ?? "理财策略"}</h3>
            <span>{recommendedInvestment ? "推荐" : "待算"}</span>
          </div>
          <p>{investmentReasonText}</p>
          <div className="recommend-reasons">
            <span>现金安全垫 {money(currentInvestmentAllocation.reserve_target)}</span>
            <span>本月预计投入 {money(currentInvestmentAllocation.total_investment)}</span>
            <span>测算年化 {percent(household.investment_plan_name === "cash_only" ? 0 : scenario.annual_investment_return ?? 0)}</span>
          </div>
        </div>
        <div className="strategy-hero-side">
          <Metric label="当前投资资产" value={investmentAccountBalanceText} />
          <Metric label="系统建议月定投" value={money(recommendedInvestment?.monthly_investment ?? 0)} />
          <Metric label="策略来源" value={investmentRecommendationSourceLabel} />
          <Metric label="当前月结余" value={money(currentInvestmentAllocation.monthly_surplus)} tone={currentInvestmentAllocation.monthly_surplus > 0 ? "good" : "bad"} />
          <Metric label="安全垫缺口" value={money(currentInvestmentAllocation.reserve_gap)} tone={currentInvestmentAllocation.reserve_gap > 0 ? "warn" : "good"} />
          <Metric label="最近目标窗口" value={recommendedInvestment?.liquidity_horizon_months !== undefined && recommendedInvestment?.liquidity_horizon_months !== null ? `${recommendedInvestment.liquidity_horizon_months} 个月` : "无近期目标"} />
        </div>
      </section>

      {portfolioStrategy ? (
        <section className="workflow-section portfolio-strategy-summary">
          <div className="workflow-section-head">
            <div>
              <span className="eyebrow">家庭组合策略</span>
              <h3>{portfolioStrategy.title}</h3>
              <p>{portfolioStrategy.description}</p>
            </div>
            <span className={`status-badge ${portfolioStrategy.feasible ? "success" : "warning"}`}>
              {portfolioStrategy.feasible ? "生命周期可行" : "需要调整后重算"}
            </span>
          </div>
          <div className="metric-grid">
            <Metric label="长期现金缺口" value={money(portfolioStrategy.cash_shortfall)} tone={portfolioStrategy.cash_shortfall > 0 ? "bad" : "good"} />
            <Metric label="首次现金穿底" value={portfolioStrategy.insolvency_month === null ? "未发生" : `第 ${portfolioStrategy.insolvency_month} 个月`} tone={portfolioStrategy.insolvency_month === null ? "good" : "bad"} />
            <Metric label="所需月度改善" value={money(portfolioStrategy.required_monthly_relief)} tone={portfolioStrategy.required_monthly_relief > 0 ? "warn" : "good"} />
            <Metric label="长期净资产" value={money(portfolioStrategy.terminal_net_worth)} />
          </div>
          {portfolioStrategy.actions.length ? (
            <div className="warning-list">
              {portfolioStrategy.actions.map((action) => <span key={action}>{action}</span>)}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="strategy-layout investment-workbench-layout">
        <WorkflowSection
          icon={<Target size={18} />}
          title="理财策略方案"
          description={`${displayedRecommendations.length} 个方案。卡片负责比较和采用，下面只编辑当前采用或手动策略。`}
          className="strategy-main-panel investment-strategy-panel"
        >
          <div className="metric-grid investment-side-metrics">
            <Metric label="当前已设定投" value={money(household.monthly_investment_amount ?? 0)} />
            <Metric label="现金安全垫目标" value={money(currentInvestmentAllocation.reserve_target)} />
            <Metric label="追加定投" value={money(currentInvestmentAllocation.cash_sweep_investment)} tone={currentInvestmentAllocation.cash_sweep_investment > 0 ? "good" : undefined} />
            <Metric label="测算年化" value={percent(household.investment_plan_name === "cash_only" ? 0 : scenario.annual_investment_return ?? 0)} />
          </div>
          <div className="strategy-grid investment-plan-grid horizontal-card-list">
            {displayedRecommendations.map((plan) => {
              const active = activeInvestmentPlanName === plan.plan_name || activeInvestmentRecommendationName === plan.plan_name;
              return (
                <article className={`strategy-card investment-card ${active ? "active" : ""}`} key={plan.plan_name}>
                  <div className="strategy-card-head">
                    <strong>{plan.variant}</strong>
                    <StrategyStatePill
                      active={active}
                      recommended={!active && plan.plan_name === recommendedInvestment?.plan_name}
                      label={!active && plan.plan_name !== recommendedInvestment?.plan_name ? `${plan.score} 分` : undefined}
                    />
                  </div>
                  <p>{plan.description}</p>
                  <ul className="strategy-explain-list">
                    {investmentStrategyDetails(plan.variant).map((item, itemIndex) => (
                      <li key={`${item}-${itemIndex}`}>{item}</li>
                    ))}
                  </ul>
                  <div className="strategy-metrics">
                    <Metric label="月定投" value={money(plan.monthly_investment)} />
                    <Metric label="测算年化" value={percent(plan.annual_return)} />
                    <Metric label="风险调整后" value={percent(plan.risk_adjusted_annual_return ?? plan.after_tax_annual_return ?? plan.annual_return)} />
                    <Metric label="风险类型" value={plan.risk_label} />
                    <Metric label="现金垫" value={`${plan.cash_reserve_months} 个月`} />
                    <Metric label="生命周期" value={plan.lifecycle_feasible === false ? "需先修复" : "可继续比较"} tone={plan.lifecycle_feasible === false ? "bad" : "good"} />
                  </div>
                  <div className="investment-ratio-row">
                    <span style={{ width: `${plan.equity_ratio * 100}%` }} />
                    <span style={{ width: `${plan.bond_ratio * 100}%` }} />
                    <span style={{ width: `${plan.cash_ratio * 100}%` }} />
                  </div>
                  <p className="strategy-note">{plan.reasons.join("；")}</p>
                  {plan.lifecycle_risk_note ? <p className="strategy-note">{plan.lifecycle_risk_note}</p> : null}
                  <AdoptStrategyButton active={active} onClick={() => applyInvestmentPlan(plan)} />
                </article>
              );
            })}
          </div>
        </WorkflowSection>
        <WorkflowSection
          icon={<SlidersHorizontal size={18} />}
          title="当前策略配置"
          description="采用方案或手动调整后会影响可视化里的资产曲线。"
          className="strategy-main-panel investment-config-panel"
        >
          <div className="investment-config-grid">
            <section className="investment-settings">
              <PanelTitle icon={<SlidersHorizontal size={18} />} title="手动参数" compact collapsible />
              <div className="form-grid two">
                <Field label="理财计划">
                  <select
                    value={activeInvestmentPlanName === "cash_reserve_first" ? "conservative_monthly_investment" : activeInvestmentPlanName}
                    onChange={(event) => selectInvestmentPlan(event.target.value)}
                  >
                    {investmentPlanOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="风险类型">
                  <select
                    value={household.investment_risk_level ?? "conservative"}
                    onChange={(event) => updateManualInvestmentHousehold("investment_risk_level", event.target.value)}
                  >
                    {Object.entries(investmentRiskLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <NumberField label="每月定投" value={household.monthly_investment_amount ?? 0} min={0} step={100} onChange={(value) => updateManualInvestmentHousehold("monthly_investment_amount", value)} />
                <NumberField label="现金安全垫月数" value={household.investment_cash_reserve_months ?? 6} min={0} max={36} step={1} onChange={(value) => updateManualInvestmentHousehold("investment_cash_reserve_months", value)} />
                <NumberField label="权益比例" value={household.investment_equity_ratio ?? 0.25} min={0} max={1} step={0.05} onChange={(value) => updateManualInvestmentHousehold("investment_equity_ratio", value)} />
                <NumberField label="固收比例" value={household.investment_bond_ratio ?? 0.45} min={0} max={1} step={0.05} onChange={(value) => updateManualInvestmentHousehold("investment_bond_ratio", value)} />
                <NumberField label="现金比例" value={household.investment_cash_ratio ?? 0.3} min={0} max={1} step={0.05} onChange={(value) => updateManualInvestmentHousehold("investment_cash_ratio", value)} />
                <NumberField label="测算年化" value={scenario.annual_investment_return ?? 0.025} min={-0.5} max={0.5} step={0.001} onChange={updateManualInvestmentAnnualReturn} />
                <NumberField label="买入手续费率" value={household.investment_buy_fee_rate ?? 0.0015} min={0} max={0.05} step={0.0005} onChange={(value) => updateManualInvestmentHousehold("investment_buy_fee_rate", value)} />
                <NumberField label="卖出手续费率" value={household.investment_sell_fee_rate ?? 0.005} min={0} max={0.05} step={0.0005} onChange={(value) => updateManualInvestmentHousehold("investment_sell_fee_rate", value)} />
              </div>
              <SwitchField
                label="自动再平衡"
                checked={household.investment_auto_rebalance ?? true}
                onChange={(checked) => updateManualInvestmentHousehold("investment_auto_rebalance", checked)}
                description="现金垫不足时暂停定投，现金垫达标后按目标比例恢复。"
                className="section-switch"
              />
              <p className="field-hint">
                达到现金安全垫后，系统会把超过安全垫的闲置现金按节奏追加到定投；理财税务口径统一在“税务”页配置。
              </p>
            </section>
            <section className="investment-allocation">
              <PanelTitle icon={<Gauge size={18} />} title="目标配置" compact collapsible />
              <ResponsiveContainer width="100%" height={210}>
                <BarChart data={allocationData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} width={42} />
                  <Tooltip formatter={(value) => `${Number(value).toFixed(0)}%`} />
                  <Bar dataKey="比例" fill={visualColors.cash} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="investment-rule-list">
                <Row label="安全垫规则" value={currentInvestmentAllocation.reserve_gap > 0 ? "先补现金" : "允许定投"} />
                <Row label="基础定投" value={money(currentInvestmentAllocation.base_investment)} />
                <Row label="超额现金追加" value={money(currentInvestmentAllocation.cash_sweep_investment)} />
                <Row label="实际本月定投" value={money(currentInvestmentAllocation.total_investment)} />
                <Row label="当前采用" value={activeRecommendation?.variant ?? "手动设置"} />
              </div>
            </section>
          </div>
          <div className="strategy-current-panel">
            <div>
              <span>当前理财策略</span>
              <strong>{activeRecommendation?.variant ?? "手动设置"}</strong>
              <p>
                系统按“先保现金安全垫，再把月结余和超额现金逐步转入投资账户”的规则执行。
                当前选中策略本月预计投入 {money(currentInvestmentAllocation.total_investment)}，其中基础定投 {money(currentInvestmentAllocation.base_investment)}、超额现金追加 {money(currentInvestmentAllocation.cash_sweep_investment)}。
              </p>
            </div>
            <div>
              <span>风险与费用口径</span>
              <strong>{activeRecommendation?.risk_label ?? investmentRiskLabels[household.investment_risk_level ?? "conservative"]}</strong>
              <p>
                收益留在投资账户内复利；买入手续费从当月投入中扣除，买房变现时由后端按卖出费率扣除后进入现金账户。策略比较使用税后收益再扣风险缓冲，不用税前年化直接压过确定的贷款成本。
              </p>
            </div>
          </div>
          <div className="investment-guide">
            <article>
              <strong>1. 先定现金安全垫</strong>
              <span>现金安全垫按家庭月支出折算。未达标时系统会优先补现金，避免为了收益率把日常流动性压得过低。</span>
            </article>
            <article>
              <strong>2. 再选风险和定投</strong>
              <span>自动方案会给出月定投、权益/固收/现金比例；你手动改参数后会进入手动方案，并同步影响可视化资产曲线。</span>
            </article>
            <article>
              <strong>3. 最后看买房前后影响</strong>
              <span>买入手续费、卖出手续费和可配置的理财收益税都由后端进入账户推演；默认税率为 0，不臆造具体产品税负。</span>
            </article>
          </div>
        </WorkflowSection>
      </section>
    </PlannerPageShell>
  );
}

function ScenarioPage({
  scenarios,
  hasPurchaseTargets,
  selectedScenario,
  setSelectedScenarioId,
  updateScenario,
  updateScenarioRecord,
  addScenario,
  removeScenario,
  removeScenarios,
  result,
  planningSequence,
  scenarioComparisons,
  selectedPlanVariant,
  setSelectedPlanVariant,
  availablePlans,
  purchasePlanSourceLabel,
  calculationPending,
  openPlanningGoals
}: {
  scenarios: RecordEnvelope<ScenarioData>[];
  hasPurchaseTargets: boolean;
  selectedScenario: RecordEnvelope<ScenarioData>;
  setSelectedScenarioId: (id: string) => void;
  updateScenario: <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => void;
  updateScenarioRecord: (id: string, patch: Partial<ScenarioData>) => void;
  addScenario: (patch?: Partial<ScenarioData>) => void;
  removeScenario: (id: string) => void;
  removeScenarios: (ids: string[]) => void;
  result: AffordabilityResult | null;
  planningSequence: PlanningSequenceResult | null;
  scenarioComparisons: ScenarioComparison[];
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  availablePlans: PurchasePlanAnalysis[];
  purchasePlanSourceLabel: string;
  calculationPending: boolean;
  openPlanningGoals: () => void;
}) {
  const generatedPlans = availablePlans;
  const recommended = useMemo(() => recommendedPurchasePlan(generatedPlans), [generatedPlans]);
  const selectedPlan =
    generatedPlans.find((plan) => plan.variant === selectedPlanVariant) ??
    recommended ??
    generatedPlans[0] ??
    null;
  const householdStrategy = selectedPlan
    ? result?.strategy_explanations.find(
      (item) => item.plan_variant === selectedPlan.variant && item.section === "household"
    )?.body ?? ""
    : "";
  const recommendationByVariant = useMemo(
    () => purchaseRecommendationByVariant(generatedPlans),
    [generatedPlans]
  );
  const selectedPropertyType = selectedScenario.data.property_type ?? "二手房";
  const isSecondHandProperty = selectedPropertyType.includes("二手");
  const selectedProvidentAccountStrategy = selectedScenario.data.provident_account_repayment_strategy ?? "auto";
  const canConfigureProvidentAccountSwitch =
    selectedProvidentAccountStrategy === "monthly_repayment_withdrawal" ||
    selectedProvidentAccountStrategy === "semiannual_principal_offset";
  const fallbackProvidentAccountSwitchTarget: ProvidentAccountRepaymentSwitchTarget =
    selectedProvidentAccountStrategy === "monthly_repayment_withdrawal"
      ? "semiannual_principal_offset"
      : "monthly_repayment_withdrawal";
  const selectedProvidentAccountSwitchTarget =
    selectedScenario.data.provident_account_repayment_switch_to_strategy === selectedProvidentAccountStrategy
      ? fallbackProvidentAccountSwitchTarget
      : selectedScenario.data.provident_account_repayment_switch_to_strategy ?? fallbackProvidentAccountSwitchTarget;
  const updateScenarioPropertyType = (propertyType: ScenarioData["property_type"]) => {
    const patch: Partial<ScenarioData> = { property_type: propertyType };
    if (!propertyType.includes("二手")) {
      patch.building_age_years = 0;
      patch.building_structure = "unknown";
      patch.is_old_community_renovated = false;
      patch.remaining_land_use_years = null;
    }
    updateScenarioRecord(selectedScenario.id, patch);
  };
  const updateProvidentAccountRepaymentStrategy = (strategy: ProvidentAccountRepaymentStrategy) => {
    const stagedModes: ProvidentAccountRepaymentSwitchTarget[] = [
      "monthly_repayment_withdrawal",
      "semiannual_principal_offset"
    ];
    const canSwitch = stagedModes.includes(strategy as ProvidentAccountRepaymentSwitchTarget);
    const currentTarget = selectedScenario.data.provident_account_repayment_switch_to_strategy ?? "semiannual_principal_offset";
    const fallbackTarget: ProvidentAccountRepaymentSwitchTarget =
      strategy === "monthly_repayment_withdrawal" ? "semiannual_principal_offset" : "monthly_repayment_withdrawal";
    updateScenarioRecord(selectedScenario.id, {
      provident_account_repayment_strategy: strategy,
      provident_account_repayment_switch_enabled:
        canSwitch && Boolean(selectedScenario.data.provident_account_repayment_switch_enabled),
      provident_account_repayment_switch_to_strategy:
        canSwitch && currentTarget !== strategy ? currentTarget : fallbackTarget
    });
  };
  const updateProvidentAccountRepaymentSwitchTarget = (target: ProvidentAccountRepaymentSwitchTarget) => {
    const fallbackTarget: ProvidentAccountRepaymentSwitchTarget =
      selectedProvidentAccountStrategy === "monthly_repayment_withdrawal"
        ? "semiannual_principal_offset"
        : "monthly_repayment_withdrawal";
    updateScenarioRecord(selectedScenario.id, {
      provident_account_repayment_switch_to_strategy:
        target === selectedProvidentAccountStrategy ? fallbackTarget : target
    });
  };
  const purchaseDemandGroups = useMemo(() => {
    const contextHomeGoals = (result?.calculation_context?.planning_goals ?? [])
      .filter((goal) => goal.goal_type === "home")
      .map((goal) => ({
        id: goal.id,
        sequence_index: goal.sequence_index,
        normalized_timing_mode: goal.normalized_timing_mode,
        resolved_not_before_month: goal.resolved_not_before_month,
        explanation: goal.explanation,
      }));
    const libraryHomeGoals = (planningSequence?.goals ?? [])
      .filter((goal) => goal.goal_type === "home")
      .map((goal) => ({
        id: goal.id,
        sequence_index: goal.sequence_index,
        normalized_timing_mode: goal.normalized_timing_mode,
        resolved_not_before_month: goal.resolved_not_before_month,
        explanation: goal.explanation,
      }));
    const homeGoalById = new Map(
      (contextHomeGoals.length ? contextHomeGoals : libraryHomeGoals)
        .map((goal) => [goal.id, goal])
    );
    const resolvedGoalForScenario = (scenario: RecordEnvelope<ScenarioData>) =>
      homeGoalById.get(scenario.data.planning_goal_id || "") ?? homeGoalById.get(scenario.id);
    const groups = new Map<number, {
      items: RecordEnvelope<ScenarioData>[];
      resolvedSequence: number | null;
      resolvedNotBeforeMonth: number;
      timingMode: PlanningTimingMode | "";
      explanation: string;
    }>();
    scenarios.forEach((scenario) => {
      const sequence = Math.max(1, scenario.data.purchase_sequence || 1);
      const resolvedGoal = resolvedGoalForScenario(scenario);
      const existing = groups.get(sequence) ?? {
        items: [],
        resolvedSequence: null,
        resolvedNotBeforeMonth: 0,
        timingMode: "",
        explanation: "",
      };
      groups.set(sequence, {
        items: [...existing.items, scenario],
        resolvedSequence: resolvedGoal?.sequence_index && resolvedGoal.sequence_index > 0
          ? Math.min(existing.resolvedSequence ?? resolvedGoal.sequence_index, resolvedGoal.sequence_index)
          : existing.resolvedSequence,
        resolvedNotBeforeMonth: Math.max(existing.resolvedNotBeforeMonth, resolvedGoal?.resolved_not_before_month ?? 0),
        timingMode: existing.timingMode || resolvedGoal?.normalized_timing_mode || "",
        explanation: existing.explanation || resolvedGoal?.explanation || "",
      });
    });
    return Array.from(groups.entries())
      .sort(([leftSequence, left], [rightSequence, right]) =>
        (left.resolvedSequence ?? leftSequence) - (right.resolvedSequence ?? rightSequence)
        || leftSequence - rightSequence
      )
      .map(([sequence, group]) => ({
        sequence,
        resolvedSequence: group.resolvedSequence,
        resolvedNotBeforeMonth: group.resolvedNotBeforeMonth,
        timingMode: group.timingMode,
        explanation: group.explanation,
        items: group.items.slice().sort((left, right) => left.created_at.localeCompare(right.created_at)),
      }));
  }, [planningSequence?.goals, result?.calculation_context?.planning_goals, scenarios]);
  const selectedDemand =
    purchaseDemandGroups.find((group) => group.sequence === selectedScenario.data.purchase_sequence) ??
    purchaseDemandGroups[0] ??
    { sequence: 1, items: [] };
  const selectedDemandScenarios = selectedDemand.items;
  const selectedDemandEnabled = selectedDemandScenarios.some((item) => item.data.enabled);
  const selectedDemandIncludedInPlanning = homeDemandIsIncludedInPlanning(
    selectedDemandScenarios.map((item) => item.data),
    selectedDemand.timingMode
  );
  const dependencyGoalOptions = useMemo(() => {
    const excludedIds = new Set(
      selectedDemandScenarios
        .map((item) => item.data.planning_goal_id || item.id)
        .filter(Boolean)
    );
    return planningGoalDependencyOptions(planningSequence?.goals ?? [], excludedIds);
  }, [planningSequence?.goals, selectedDemandScenarios]);
  const dependencyGoalLabel = (goalId: string) =>
    planningGoalDependencyLabel(goalId, dependencyGoalOptions, planningSequence?.goals ?? []);
  const demandLabel = (sequence: number) => sequence <= 1 ? "第一套购房需求" : `第 ${sequence} 套购房需求`;
  const candidateLabel = (index: number) => `候选房源 ${index + 1}`;
  const demandTimingLabel = (group: (typeof purchaseDemandGroups)[number]) => {
    const scenario = group.items[0]?.data ?? selectedScenario.data;
    return scenarioPlanningTimingSummary(
      scenario,
      scenario.depends_on_goal_id ? dependencyGoalLabel(scenario.depends_on_goal_id) : "指定目标"
    );
  };
  const demandOrderLabel = (group: (typeof purchaseDemandGroups)[number]) => {
    const normalizedMode: PlanningTimingMode =
      group.timingMode || planningTimingModeFromScenario(group.items[0]?.data ?? selectedScenario.data);
    return planningGoalOrderLabel({
      normalized_timing_mode: normalizedMode,
      sequence_index: group.resolvedSequence ?? group.sequence,
    });
  };
  const updateSelectedDemand = (patch: Partial<ScenarioData>) => {
    selectedDemandScenarios.forEach((scenario) => updateScenarioRecord(scenario.id, patch));
  };
  const addPurchaseDemand = () => {
    const nextSequence = Math.max(0, ...purchaseDemandGroups.map((group) => group.sequence)) + 1;
    addScenario({
      name: `${demandLabel(nextSequence)} · 候选房源 1`,
      purchase_sequence: nextSequence,
      purchase_planning_mode: homePurchasePlanningModeForSequence(nextSequence),
      depends_on_goal_id: "",
      after_previous_purchase_delay_months: 0,
      selected_purchase_plan_variant: "",
    });
  };
  const addPropertyCandidate = (sequence = selectedDemand.sequence) => {
    const base = selectedDemandScenarios[0]?.data ?? createTargetScenarioData(sequence);
    const nextCandidateIndex = selectedDemandScenarios.length + 1;
    addScenario({
      ...base,
      name: `${demandLabel(sequence)} · ${candidateLabel(nextCandidateIndex)}`,
      purchase_sequence: sequence,
      selected_purchase_plan_variant: "",
    });
  };
  const duplicatePropertyCandidate = (scenario: RecordEnvelope<ScenarioData>) => {
    addScenario({
      ...scenario.data,
      name: `${scenario.data.name || "候选房源"} 复制`,
      selected_purchase_plan_variant: "",
    });
  };
  const removePurchaseDemand = (sequence: number) => {
    const ids = purchaseDemandGroups.find((group) => group.sequence === sequence)?.items.map((item) => item.id) ?? [];
    if (ids.length) removeScenarios(ids);
  };

  if (!hasPurchaseTargets) {
    return (
      <PlannerPageShell
        className="home-plan-page"
        icon={<Target size={20} />}
        title="购房计划"
        action={
          <button className="ghost-button" onClick={addPurchaseDemand}>
            <Plus size={16} /> 添加购房需求
          </button>
        }
        summary={<p>按“购房需求、候选房源、当前策略、影响预览”的顺序管理房源目标；没有目标时只展示家庭基线。</p>}
      >
        <section className="strategy-hero">
          <div className="strategy-hero-main">
            <PanelTitle icon={<Sparkles size={18} />} title="默认不买房" compact />
            <div className="recommend-title">
              <h3>当前不设定购房目标</h3>
              <span>基线</span>
            </div>
            <p>系统先按现有家庭收入、支出、贷款、理财和购车计划测算现金流；需要买第一套房时，先添加购房需求，再在需求下添加候选房源并生成具体购房策略。</p>
            <button className="primary-button recommend-action" onClick={addPurchaseDemand}>
              <Plus size={16} /> 添加购房需求
            </button>
            <div className="recommend-reasons">
              <span>不会默认生成购房贷款和交易事件</span>
              <span>可视化展示的是不买房基线现金流</span>
              <span>添加需求和候选房源后再进行房源与策略对比</span>
            </div>
          </div>
          <div className="strategy-hero-side">
            <Metric label="购房目标" value="未添加" />
            <Metric label="当前模式" value={result?.status ?? "不买房基线"} tone="good" />
            <Metric label="下一步" value="手动添加第一套房" />
          </div>
        </section>
        <section className="result-panel">
          <PanelTitle icon={<Home size={18} />} title="购房需求与候选房源" compact collapsible />
          <div className="empty-state target-empty-state">
            <strong>默认不买房</strong>
            <span>当前没有购房需求，购房策略、房贷、公积金贷款和交易事件都不会进入计划。</span>
            <button className="primary-button" onClick={addPurchaseDemand}>
              <Plus size={16} /> 添加购房需求
            </button>
          </div>
        </section>
        <section className="result-panel">
          <PanelTitle icon={<ClipboardCheck size={18} />} title="多套房管理逻辑" compact collapsible />
          <div className="explanation-grid">
            <article>
              <strong>第一套房手动添加</strong>
              <span>公开版本和新家庭默认不创建任何购房需求，避免把“买房”当作默认前提。</span>
            </article>
            <article>
              <strong>上一套后再考虑</strong>
              <span>第二套及以后默认按上一套成交后再进入策略测算，并按更保守的既有住房和既有房贷口径判断。</span>
            </article>
            <article>
              <strong>可并行考虑</strong>
              <span>如果确实要同时比较多套房，可以把购房需求设为可并行考虑，后端会按当前既有住房口径独立测算。</span>
            </article>
          </div>
        </section>
      </PlannerPageShell>
    );
  }

  return (
    <PlannerPageShell
      className="home-plan-page"
      icon={<Target size={20} />}
      title="购房计划"
      action={
        <button className="ghost-button" onClick={addPurchaseDemand}>
          <Plus size={16} /> 新增购房需求
        </button>
      }
      summary={<p>先选购房需求和候选房源，再确认贷款、公积金、装修与投资动用策略，最后查看现金流、贷款和幸福指数影响。</p>}
    >

      <section className="strategy-hero">
        <div className="strategy-hero-main">
          <PanelTitle icon={<Sparkles size={18} />} title={hasPurchaseTargets ? "自动推荐" : "默认不买房"} compact />
          {!hasPurchaseTargets ? (
            <>
              <div className="recommend-title">
                <h3>当前不设定购房目标</h3>
                <span>基线</span>
              </div>
              <p>系统先按现有家庭收入、支出、贷款、理财和购车计划测算现金流；需要买第一套房时，先添加购房需求，再在需求下添加候选房源并生成具体购房策略。</p>
              <button className="primary-button recommend-action" onClick={addPurchaseDemand}>
                <Plus size={16} /> 添加购房需求
              </button>
              <div className="recommend-reasons">
                <span>不会默认生成购房贷款和交易事件</span>
                <span>可视化展示的是不买房基线现金流</span>
                <span>添加需求和候选房源后再进行房源与策略对比</span>
              </div>
            </>
          ) : recommended ? (
            <>
              <div className="recommend-title">
                <h3>{recommended.variant}</h3>
                <span>{recommended.recommendation_score} 分</span>
              </div>
              <p>{recommended.description}</p>
              <button
                className="primary-button recommend-action"
                onClick={() => setSelectedPlanVariant(recommended.variant)}
              >
                <Sparkles size={16} /> 查看推荐策略
              </button>
              <div className="recommend-reasons">
                {recommended.recommendation_reasons.slice(0, 3).map((reason) => (
                  <span key={reason}>{reason}</span>
                ))}
              </div>
            </>
          ) : (
            <p>{calculationPending ? "正在按最新条件重新生成推荐策略。" : result?.recommended_plan_reason || "当前没有可执行购房方案，建议延后买入、降低总价或保持不买房基线。"}</p>
          )}
        </div>
        <div className="strategy-hero-side">
          <Metric
            label={hasPurchaseTargets ? "房源总价" : "购房需求"}
            value={hasPurchaseTargets ? money(selectedScenario.data.total_price) : "未添加"}
          />
          <Metric
            label={hasPurchaseTargets ? "当前立即购入能力" : "当前模式"}
            value={hasPurchaseTargets ? result?.immediate_purchase_status ?? "待计算" : "不买房基线"}
            tone={result?.immediate_purchase_status === "可行" ? "good" : result?.immediate_purchase_status === "不可行" ? "bad" : "warn"}
          />
          <Metric
            label={hasPurchaseTargets ? "推荐方案可行性" : "下一步"}
            value={
              hasPurchaseTargets
                ? result?.recommended_plan_status ?? "待计算"
                : "手动添加第一套房"
            }
            tone={
              result?.recommended_plan_status === "可行"
                ? "good"
                : result?.recommended_plan_status === "不可行" || result?.recommended_plan_status === "无可行方案"
                  ? "bad"
                  : "warn"
            }
          />
          <Metric label="策略来源" value={purchasePlanSourceLabel} />
        </div>
      </section>

      <div className="strategy-layout">
        <aside className="strategy-side-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<Home size={18} />} title="购房需求与候选房源" compact collapsible />
          </div>
          <div className="planning-goal-grid horizontal-card-list purchase-demand-grid">
            {purchaseDemandGroups.map((group) => {
              const firstScenario = group.items[0];
              const active = group.sequence === selectedDemand.sequence;
              const demandEnabled = group.items.some((item) => item.data.enabled);
              const includedInPlanning = homeDemandIsIncludedInPlanning(
                group.items.map((item) => item.data),
                group.timingMode
              );
              return (
                <article className={active ? "planning-goal-card active" : "planning-goal-card"} key={`purchase-demand-${group.sequence}`}>
                  <button type="button" className="planning-goal-select" onClick={() => firstScenario && setSelectedScenarioId(firstScenario.id)}>
                    <span className={includedInPlanning ? "goal-status enabled" : "goal-status paused"}>
                      {planningInclusionStatusLabel(includedInPlanning, demandEnabled)}
                    </span>
                    <strong>{demandLabel(group.sequence)}</strong>
                    <small>
                      {group.items.length} 个候选房源 · {demandOrderLabel(group)}
                    </small>
                    <em>{demandTimingLabel(group)}</em>
                  </button>
                  <div className="planning-goal-actions">
                    <button className="ghost-button small" type="button" onClick={() => firstScenario && setSelectedScenarioId(firstScenario.id)}>
                      选择需求
                    </button>
                    <button className="ghost-button small" type="button" onClick={() => addPropertyCandidate(group.sequence)}>
                      <Plus size={14} /> 候选
                    </button>
                    <button className="ghost-button small" type="button" onClick={openPlanningGoals}>调整排期</button>
                    <button className="ghost-button small danger-action" type="button" onClick={() => removePurchaseDemand(group.sequence)} aria-label={`删除${demandLabel(group.sequence)}`} title="删除该购房需求下的全部候选房源">
                      <Trash2 size={14} /> 删除
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
          {calculationPending ? (
            <p className="goal-updating-note">购房需求已更新，正在重新生成候选房源对比与贷款策略。</p>
          ) : null}
          <div className="planning-source-note">
            <div>
              <strong>统一排期</strong>
              <span>{demandTimingLabel(selectedDemand)} · {demandOrderLabel(selectedDemand)}</span>
            </div>
            <button className="ghost-button small" type="button" onClick={openPlanningGoals}>到规划目标调整</button>
          </div>
          <div className="vehicle-source-toolbar property-source-toolbar">
            <strong>{demandLabel(selectedDemand.sequence)}的候选房源</strong>
            <button className="ghost-button small" type="button" onClick={() => addPropertyCandidate(selectedDemand.sequence)}>
              <Plus size={14} /> 添加候选房源
            </button>
          </div>
          <div className="vehicle-source-grid property-source-grid">
            {selectedDemandScenarios.map((item, candidateIndex) => {
              const includedInPlanning = homePlanIsIncludedInPlanning(item.data, selectedDemand.timingMode);
              return (
                <article className={item.id === selectedScenario.id ? "vehicle-source-card active" : "vehicle-source-card"} key={item.id}>
                  <div className="vehicle-source-head">
                    <button type="button" className="planning-goal-select compact-select" onClick={() => setSelectedScenarioId(item.id)}>
                      <span className={includedInPlanning ? "goal-status enabled" : "goal-status paused"}>
                        {planningInclusionStatusLabel(includedInPlanning, item.data.enabled)}
                      </span>
                      <strong>{item.data.name || candidateLabel(candidateIndex)}</strong>
                      <small>{money(item.data.total_price)} · {item.data.property_type}</small>
                    </button>
                    <button className="ghost-button small danger-action" type="button" onClick={() => void removeScenario(item.id)} aria-label={`删除候选房源 ${item.data.name}`}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <div className="planning-goal-actions">
                    <button className="ghost-button small" type="button" onClick={() => setSelectedScenarioId(item.id)}>
                      选择房源
                    </button>
                    <button className="ghost-button small" type="button" onClick={() => duplicatePropertyCandidate(item)}>
                      <Copy size={14} /> 复制
                    </button>
                    <span className="source-summary-pill">{includedInPlanning ? "纳入当前规划" : "暂不纳入规划"}</span>
                  </div>
                </article>
              );
            })}
          </div>
          {selectedDemandScenarios.length === 0 ? (
            <div className="empty-state compact-empty-state">
              <span>这个购房需求还没有候选房源。</span>
              <button className="primary-button" type="button" onClick={() => addPropertyCandidate(selectedDemand.sequence)}>
                <Plus size={16} /> 添加候选房源
              </button>
            </div>
          ) : null}
          <div className="side-form structured-settings">
            <CollapsibleSettingGroup title="候选房源身份">
              <div className="form-grid two">
                <ReadOnlyField label="统一排期状态" value={selectedDemandIncludedInPlanning ? "纳入当前规划（到规划目标页调整）" : "暂不纳入规划（到规划目标页调整）"} />
                <Field label="候选房源名称">
                  <input
                    value={selectedScenario.data.name}
                    onChange={(event) => updateScenario("name", event.target.value)}
                  />
                </Field>
                <Field label="区域">
                  <input
                    value={selectedScenario.data.district}
                    onChange={(event) => updateScenario("district", event.target.value)}
                  />
                </Field>
                <Field label="环线">
                  <select
                    value={selectedScenario.data.ring_area}
                    onChange={(event) => updateScenario("ring_area", event.target.value)}
                  >
                    {!RING_AREA_OPTIONS.some((item) => item === selectedScenario.data.ring_area) ? <option value={selectedScenario.data.ring_area}>{selectedScenario.data.ring_area}</option> : null}
                    {RING_AREA_OPTIONS.map((item) => <option value={item} key={item}>{item}</option>)}
                  </select>
                </Field>
                <Field label="房屋性质">
                  <select
                    value={selectedScenario.data.property_type}
                    onChange={(event) => updateScenarioPropertyType(event.target.value as ScenarioData["property_type"])}
                  >
                    <option value="二手房">二手房</option>
                    <option value="新房">新房</option>
                    <option value="共有产权房">共有产权房</option>
                    <option value="其他">其他</option>
                  </select>
                </Field>
              </div>
            </CollapsibleSettingGroup>

            <CollapsibleSettingGroup title="价格与贷款">
              <div className="form-grid two">
                <NumberField label="房源总价" value={selectedScenario.data.total_price} min={0} step={10000} onChange={(value) => updateScenario("total_price", value)} />
                <NumberField label="建筑面积" value={selectedScenario.data.area_sqm} min={0} step={1} onChange={(value) => updateScenario("area_sqm", value)} />
                <NumberField label="贷款年限" value={selectedScenario.data.loan_years} min={1} max={30} step={1} onChange={(value) => updateScenario("loan_years", value)} />
                <Field label="贷款还款方式策略">
                  <select
                    value={selectedScenario.data.loan_repayment_strategy_mode ?? "auto"}
                    onChange={(event) => updateScenario("loan_repayment_strategy_mode", event.target.value as ScenarioData["loan_repayment_strategy_mode"])}
                  >
                    <option value="auto">策略联合优化商贷与公积金贷</option>
                    <option value="manual">手动指定两类贷款</option>
                  </select>
                </Field>
                {(selectedScenario.data.loan_repayment_strategy_mode ?? "auto") === "manual" ? (
                  <>
                    <Field label="商贷还款">
                      <select
                        value={selectedScenario.data.commercial_repayment_method ?? selectedScenario.data.repayment_method}
                        onChange={(event) => updateScenario("commercial_repayment_method", event.target.value as RepaymentMethod)}
                      >
                        <option value="equal_installment">等额本息</option>
                        <option value="equal_principal">等额本金</option>
                      </select>
                    </Field>
                    <Field label="公积金还款">
                      <select
                        value={selectedScenario.data.provident_repayment_method ?? selectedScenario.data.repayment_method}
                        onChange={(event) => updateScenario("provident_repayment_method", event.target.value as RepaymentMethod)}
                      >
                        <option value="equal_installment">等额本息</option>
                        <option value="equal_principal">等额本金</option>
                      </select>
                    </Field>
                  </>
                ) : (
                  <ReadOnlyField label="自动比较范围" value="商贷/公积金贷各自比较等额本息与等额本金" />
                )}
                <Field label="公积金账户还贷策略" description={parameterExplanations["公积金账户还贷策略"]}>
                  <select
                    value={selectedProvidentAccountStrategy}
                    onChange={(event) =>
                      updateProvidentAccountRepaymentStrategy(event.target.value as ProvidentAccountRepaymentStrategy)
                    }
                  >
                    {Object.entries(providentAccountRepaymentStrategyLabels).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </Field>
                {canConfigureProvidentAccountSwitch ? (
                  <>
                    <SwitchField
                      label="公积金还贷切换"
                      checked={Boolean(selectedScenario.data.provident_account_repayment_switch_enabled)}
                      onChange={(checked) => updateScenario("provident_account_repayment_switch_enabled", checked)}
                      description={parameterExplanations["公积金还贷切换"]}
                    />
                    {selectedScenario.data.provident_account_repayment_switch_enabled ? (
                      <>
                        <NumberField
                          label="切换还款月"
                          value={selectedScenario.data.provident_account_repayment_switch_after_month ?? 12}
                          min={1}
                          max={360}
                          step={1}
                          onChange={(value) => updateScenario("provident_account_repayment_switch_after_month", value)}
                        />
                        <Field label="切换后模式">
                          <select
                            value={selectedProvidentAccountSwitchTarget}
                            onChange={(event) =>
                              updateProvidentAccountRepaymentSwitchTarget(event.target.value as ProvidentAccountRepaymentSwitchTarget)
                            }
                          >
                            {Object.entries(providentAccountRepaymentSwitchTargetLabels)
                              .filter(([value]) => value !== selectedProvidentAccountStrategy)
                              .map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                          </select>
                        </Field>
                      </>
                    ) : null}
                  </>
                ) : null}
              </div>
            </CollapsibleSettingGroup>

            <CollapsibleSettingGroup title="政策属性">
              <div className="form-grid two">
                {isSecondHandProperty ? (
                  <>
                    <NumberField
                      label="二手房房龄"
                      value={selectedScenario.data.building_age_years ?? 0}
                      min={0}
                      max={100}
                      step={1}
                      onChange={(value) => updateScenario("building_age_years", value)}
                    />
                    <Field label="建筑结构">
                      <select
                        value={selectedScenario.data.building_structure ?? "unknown"}
                        onChange={(event) => updateScenario("building_structure", event.target.value as ScenarioData["building_structure"])}
                      >
                        <option value="unknown">未知（按砖混保守测算）</option>
                        <option value="brick_mixed">砖混结构</option>
                        <option value="steel_concrete">钢混结构</option>
                      </select>
                    </Field>
                    <NumberField
                      label="剩余土地年限"
                      value={selectedScenario.data.remaining_land_use_years ?? 70}
                      min={0}
                      max={70}
                      step={1}
                      onChange={(value) => updateScenario("remaining_land_use_years", value)}
                    />
                  </>
                ) : null}
                <Field label="绿色建筑">
                  <select
                    value={selectedScenario.data.green_building_level ?? "none"}
                    onChange={(event) => updateScenario("green_building_level", event.target.value as ScenarioData["green_building_level"])}
                  >
                    <option value="none">不适用</option>
                    <option value="two_star">二星绿色建筑</option>
                    <option value="three_star">三星绿色建筑</option>
                  </select>
                </Field>
                <Field label="装配式等级">
                  <select
                    value={selectedScenario.data.prefab_building_level ?? "none"}
                    onChange={(event) => updateScenario("prefab_building_level", event.target.value as ScenarioData["prefab_building_level"])}
                  >
                    <option value="none">不适用</option>
                    <option value="A">A</option>
                    <option value="AA">AA</option>
                    <option value="AAA">AAA</option>
                  </select>
                </Field>
              </div>
              <div className="switch-grid">
                {isSecondHandProperty ? (
                  <SwitchField
                    label="已完成老旧小区改造"
                    checked={selectedScenario.data.is_old_community_renovated ?? false}
                    onChange={(checked) => updateScenario("is_old_community_renovated", checked)}
                  />
                ) : null}
                <SwitchField
                  label="超低能耗建筑"
                  checked={selectedScenario.data.is_ultra_low_energy_building ?? false}
                  onChange={(checked) => updateScenario("is_ultra_low_energy_building", checked)}
                />
              </div>
            </CollapsibleSettingGroup>
          </div>
        </aside>

        <section className="strategy-main-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="手动参数" compact collapsible />
            <span>修改后会自动重算推荐、贷款结构和现金流</span>
          </div>
          <div className="structured-settings strategy-settings-groups">
            <CollapsibleSettingGroup title="贷款结构与资金策略">
              <div className="form-grid">
                <NumberField label="手动首付" value={selectedScenario.data.down_payment_amount} min={0} step={10000} onChange={(value) => updateScenario("down_payment_amount", value)} />
                <NumberField label="手动公积金贷" value={selectedScenario.data.provident_loan_amount} min={0} step={10000} onChange={(value) => updateScenario("provident_loan_amount", value)} />
                <NumberField label="手动商贷" value={selectedScenario.data.commercial_loan_amount} min={0} step={10000} onChange={(value) => updateScenario("commercial_loan_amount", value)} />
                <NumberField label="微量商贷手动比例" value={selectedScenario.data.micro_commercial_loan_ratio ?? 0} min={0} max={1} step={0.01} onChange={(value) => updateScenario("micro_commercial_loan_ratio", value)} />
                <ReadOnlyField label="政策公积金利率" value={selectedPlan ? percent(selectedPlan.provident_rate) : "待生成"} />
                <NumberField label="商贷利率" value={selectedScenario.data.commercial_rate} min={0} max={0.2} step={0.0005} onChange={(value) => updateScenario("commercial_rate", value)} />
                <Field label="商贷提前还本策略">
                  <select
                    value={selectedScenario.data.commercial_prepayment_mode ?? "auto"}
                    onChange={(event) => {
                      const mode = event.target.value as CommercialPrepaymentMode;
                      updateScenario("commercial_prepayment_mode", mode);
                      updateScenario("commercial_prepayment_enabled", mode === "manual");
                    }}
                  >
                    <option value="auto">策略自动生成</option>
                    <option value="manual">手动指定</option>
                    <option value="none">不提前还本</option>
                  </select>
                </Field>
                {(selectedScenario.data.commercial_prepayment_mode ?? "auto") !== "none" ? (
                  <>
                    <NumberField label="希望起始还本月" value={selectedScenario.data.commercial_prepayment_start_month ?? 1} min={1} max={360} step={1} onChange={(value) => updateScenario("commercial_prepayment_start_month", value)} />
                    <NumberField label="合同允许最早月" value={selectedScenario.data.commercial_prepayment_allowed_after_month ?? 12} min={1} max={360} step={1} onChange={(value) => updateScenario("commercial_prepayment_allowed_after_month", value)} />
                    <NumberField
                      label={(selectedScenario.data.commercial_prepayment_mode ?? "auto") === "manual" ? "每月额外还本" : "商贷提前还本上限"}
                      value={selectedScenario.data.commercial_prepayment_monthly_amount ?? 0}
                      min={0}
                      step={1000}
                      onChange={(value) => updateScenario("commercial_prepayment_monthly_amount", value)}
                    />
                  </>
                ) : null}
              </div>
            </CollapsibleSettingGroup>

            <CollapsibleSettingGroup title="交易成本与装修">
              <div className="form-grid">
                <ReadOnlyField label="政策契税比例" value={selectedPlan ? percent(selectedPlan.deed_tax_rate) : "待生成"} />
                <ReadOnlyField label="政策契税金额" value={selectedPlan ? money(selectedPlan.deed_tax_amount) : "待生成"} />
                <NumberField label="中介费假设" value={selectedScenario.data.broker_fee_rate} min={0} max={0.2} step={0.001} onChange={(value) => updateScenario("broker_fee_rate", value)} />
                <SwitchField label="卖方税费转嫁" checked={selectedScenario.data.seller_tax_pass_through_enabled ?? false} onChange={(checked) => updateScenario("seller_tax_pass_through_enabled", checked)} />
                {selectedScenario.data.seller_tax_pass_through_enabled ? (
                  <>
                    <NumberField label="卖方税费转嫁比例" value={selectedScenario.data.seller_tax_pass_through_rate ?? 0} min={0} max={0.2} step={0.001} onChange={(value) => updateScenario("seller_tax_pass_through_rate", value)} />
                    <NumberField label="卖方税费转嫁金额" value={selectedScenario.data.seller_tax_pass_through_amount ?? 0} min={0} step={1000} onChange={(value) => updateScenario("seller_tax_pass_through_amount", value)} />
                  </>
                ) : null}
                <NumberField label="搬家杂费" value={selectedScenario.data.moving_and_misc_cost} min={0} step={1000} onChange={(value) => updateScenario("moving_and_misc_cost", value)} />
              </div>
            </CollapsibleSettingGroup>

            <CollapsibleSettingGroup title="投资动用与偏好评分">
              <div className="form-grid">
                <ReadOnlyField
                  label="理财计划年化"
                  value={percent(selectedScenario.data.annual_investment_return ?? 0.025)}
                  description="来自理财计划当前采用的策略；如需调整收益假设，请到理财计划修改。"
                />
                {(selectedScenario.data.investment_withdrawal_mode ?? "auto") === "manual_reserve" ? (
                  <NumberField
                    label="交易后投资保留"
                    value={selectedScenario.data.investment_min_balance_after_purchase ?? 0}
                    min={0}
                    step={1000}
                    onChange={(value) => updateScenario("investment_min_balance_after_purchase", value)}
                  />
                ) : null}
                <NumberField label="居住幸福度" value={selectedScenario.data.happiness_score ?? 7} min={0} max={10} step={0.5} onChange={(value) => updateScenario("happiness_score", value)} />
                <NumberField label="通勤评分" value={selectedScenario.data.commute_score ?? 7} min={0} max={10} step={0.5} onChange={(value) => updateScenario("commute_score", value)} />
                <NumberField label="教育评分" value={selectedScenario.data.school_score ?? 6} min={0} max={10} step={0.5} onChange={(value) => updateScenario("school_score", value)} />
                <NumberField label="流动性偏好" value={selectedScenario.data.liquidity_priority_score ?? 7} min={0} max={10} step={0.5} onChange={(value) => updateScenario("liquidity_priority_score", value)} />
                <Field label="买房动用投资">
                  <select
                    value={selectedScenario.data.investment_withdrawal_mode ?? "auto"}
                    onChange={(event) =>
                      updateScenario("investment_withdrawal_mode", event.target.value as ScenarioData["investment_withdrawal_mode"])
                    }
                  >
                    <option value="auto">自动优化提取</option>
                    <option value="full_liquidation">清空投资账户</option>
                    <option value="manual_reserve">手动保留余额</option>
                  </select>
                </Field>
              </div>
            </CollapsibleSettingGroup>
          </div>
          <p className="field-hint">
            需求时间段会约束所有购房策略的候选月份，系统会在时间段内校验现金安全、政策贷款和买后压力。微量商贷手动比例填 0 时由系统在政策规则上下限内自动寻找更合适且商贷尽量少的比例，填入比例后按该比例固定测算。理财年化、定投和手续费来自理财计划当前策略，购房页只决定交易时如何动用投资账户。商贷提前还本选择“策略自动生成”时，后端会在合同允许月份之后比较商贷成本、税后理财净收益、现金安全和买后结余，再决定是否额外还本；选择“手动指定”时按你填写的起始月和每月金额测算。买房动用投资选择“自动优化提取”时，后端会联合比较买入月份、融资和投资保留额；只有税后风险调整收益覆盖确定的商贷成本时，才会把保留投资作为候选，并仍须通过现金与长期账本门槛。选择“清空投资账户”才会在交易月全部变现；选择“手动保留余额”时按设定余额尽量保留长期投资。
          </p>
        </section>
      </div>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Home size={18} />} title="房源对比" compact />
          <span>按每个候选房源当前选中的策略比较</span>
        </div>
        {scenarioComparisons.length ? (
          <div className="comparison-table">
            <div className="comparison-row comparison-head">
              <span>房源</span>
              <span>当前策略</span>
              <span>可买时间</span>
              <span>交易现金</span>
              <span>买后自由月结余</span>
              <span>幸福指数</span>
            </div>
            {scenarioComparisons.map(({ scenario, selectedPlan: plan }) => {
              const stressShortfall = Math.max(0, plan?.cash_stress_shortfall ?? 0);
              return (
                <button
                  type="button"
                  className={scenario.id === selectedScenario.id ? "comparison-row active" : "comparison-row"}
                  key={scenario.id}
                  onClick={() => setSelectedScenarioId(scenario.id)}
                >
                  <span>
                    <strong>{scenario.data.name}</strong>
                    <small>
                      {scenario.data.property_type} · 当前报价 {money(scenario.data.total_price)}
                      {plan?.property_price_forecast_applied ? ` · 买入月预测 ${money(plan.projected_purchase_price)}` : ""}
                    </small>
                  </span>
                  <span>{plan?.variant ?? "待生成"}</span>
                  <span>{plan ? formatPurchaseTiming(new Date(), plan.months_to_buy, plan.years_to_buy) : "-"}</span>
                  <span>{plan ? (stressShortfall > 0 ? `缺口 ${money(stressShortfall)}` : money(plan.cash_after_transaction)) : "-"}</span>
                  <span>{plan ? money(plan.post_purchase_cash_flow) : "-"}</span>
                  <span>{plan ? `${plan.happiness_score.toFixed(1)} / 10` : "-"}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">{calculationPending ? "正在计算房源对比" : "等待计算房源对比"}</div>
        )}
      </section>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Gauge size={18} />} title="候选策略" compact />
          <span>系统生成，选择后作为当前策略，可到可视化页查看图表</span>
        </div>
        {generatedPlans.length ? (
          <div className="strategy-grid">
            {generatedPlans.map((plan) => {
              const recommendation = recommendationByVariant.get(plan.variant);
              const isRecommended = plan.is_recommended;
              const isSelected = plan.variant === selectedPlan?.variant;
              const planStressShortfall = Math.max(0, plan.cash_stress_shortfall ?? 0);
              const planFamilySupportAmount = familySupportAmount(plan);
              const planFamilySupportLabel = familySupportLabel(plan);
              return (
                <button
                  key={plan.variant}
                  className={isSelected ? "strategy-card active" : "strategy-card"}
                  onClick={() => setSelectedPlanVariant(plan.variant)}
                >
                  <div className="strategy-card-head">
                    <strong>{plan.variant}</strong>
                    <StrategyStatePill
                      active={isSelected}
                      recommended={!isSelected && isRecommended}
                      label={!isSelected && !isRecommended ? `${recommendation?.recommendation_score ?? 0} 分` : undefined}
                    />
                  </div>
                  <p>{plan.description}</p>
                  <ul className="strategy-explain-list">
                    {purchaseStrategyDetails(plan).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <div className="strategy-scorebar">
                    <i style={{ width: `${Math.max(6, recommendation?.recommendation_score ?? 0)}%` }} />
                  </div>
                  <div className="strategy-metrics">
                    <Metric label="可买时间" value={plan.years_to_buy === null ? "暂不可达" : `${plan.years_to_buy} 年`} />
                    <Metric
                      label={plan.property_price_forecast_applied ? "买入月预测房价" : "目标房价"}
                      value={money(plan.projected_purchase_price || plan.original_target_price)}
                      tone={plan.projected_price_change > 0 ? "warn" : "good"}
                    />
                    {plan.property_price_forecast_applied ? (
                      <Metric
                        label="房价预测区间"
                        value={`${money(plan.projected_purchase_price_lower)}—${money(plan.projected_purchase_price_upper)}`}
                      />
                    ) : null}
                    <Metric label="计划首付" value={money(plan.planned_down_payment)} />
                    <Metric label="公积金贷" value={money(plan.provident_loan_amount)} />
                    <Metric label="公积金上限" value={money(plan.provident_policy_cap)} />
                    <Metric label="政策上浮" value={money(plan.provident_policy_bonus)} />
                    <Metric label="商贷" value={money(plan.commercial_loan_amount)} />
                    <Metric label="公积金年限" value={`${plan.provident_loan_years} 年`} />
                    <Metric label="商贷年限" value={`${plan.commercial_loan_years} 年`} />
                    <Metric label="公积金还款" value={repaymentMethodLabels[plan.provident_repayment_method]} />
                    <Metric label="商贷还款" value={repaymentMethodLabels[plan.commercial_repayment_method]} />
                    {plan.commercial_prepayment_enabled ? (
                      <>
                        <Metric label="商贷还本策略" value={commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]} tone="good" />
                        <Metric label="额外还本/月" value={money(plan.commercial_prepayment_monthly_amount)} />
                        <Metric label="节省商贷利息" value={money(plan.commercial_interest_saved_by_prepayment)} />
                      </>
                    ) : null}
                    <Metric label="本人公积金首付抵扣" value={money(plan.provident_upfront_extractable)} />
                    {planFamilySupportAmount > 0 ? (
                      <Metric label={planFamilySupportLabel || "亲属首付支持"} value={money(planFamilySupportAmount)} tone="good" />
                    ) : null}
                    <Metric label="购房后预计提取到账" value={money(plan.provident_post_transaction_extractable)} />
                    <Metric label={planStressShortfall > 0 ? "压力现金缺口" : "交易当下现金"} value={planStressShortfall > 0 ? money(planStressShortfall) : money(plan.cash_after_transaction)} tone={planStressShortfall > 0 ? "bad" : plan.liquidity_ok ? "good" : "warn"} />
                    <Metric label="总月供" value={money(plan.total_monthly_payment)} />
                    <Metric label="买后自由月结余" value={money(plan.post_purchase_cash_flow)} tone={plan.post_purchase_cash_flow >= 0 ? "good" : "bad"} />
                  </div>
                  <p className="strategy-note">
                    首付现金：本人公积金可直接抵首付 {money(plan.provident_upfront_extractable)}
                    {planFamilySupportAmount > 0 ? `，${planFamilySupportLabel || "亲属首付支持"} ${money(planFamilySupportAmount)}` : ""}
                    ；购房后预计可提到银行卡 {money(plan.provident_post_transaction_extractable)}；年限：{plan.provident_loan_year_limit_reasons.join("；")}
                  </p>
                  <span className="strategy-adoption-row">
                    {isSelected ? <CheckCircle2 size={16} /> : <Sparkles size={16} />}
                    {isSelected ? "当前采用" : "点击采用此购房策略"}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">{calculationPending ? "正在计算生成购房策略" : "等待计算生成购房策略"}</div>
        )}
      </section>

      {selectedPlan ? (
        <StrategyNarrative
          plan={selectedPlan}
          scenario={selectedScenario.data}
          recommendation={recommendationByVariant.get(selectedPlan.variant)}
          isRecommended={selectedPlan.is_recommended}
          householdStrategy={householdStrategy}
        />
      ) : null}
    </PlannerPageShell>
  );
}

function StrategyNarrative({
  plan,
  scenario,
  recommendation,
  isRecommended,
  householdStrategy
}: {
  plan: PurchasePlanAnalysis;
  scenario: ScenarioData;
  recommendation?: PurchasePlanAnalysis;
  isRecommended: boolean;
  householdStrategy: string;
}) {
  const timelineBaseDate = useMemo(() => new Date(), []);
  const purchaseMonthText =
    plan.months_to_buy === null ? "暂未形成可执行日期" : formatMonthDate(timelineBaseDate, plan.months_to_buy);
  const propertyNatureText = [
    scenario.property_type,
    scenario.green_building_level !== "none" ? greenBuildingLabels[scenario.green_building_level] : "",
    scenario.prefab_building_level !== "none" ? prefabBuildingLabels[scenario.prefab_building_level] : "",
    scenario.is_ultra_low_energy_building ? "超低能耗建筑" : ""
  ].filter(Boolean).join(" / ");
  const timingText =
    plan.months_to_buy === null
      ? "按当前收入和资产路径，30 年内暂时无法满足买入所需现金。"
      : `预计 ${purchaseMonthText}、约 ${plan.years_to_buy} 年后可以执行买入；该日期用于同步计算届时公积金缴存年限、可贷额度和现金积累。`;
  const loanText = `执行时采用 ${money(plan.planned_down_payment)} 首付，贷款合计 ${money(plan.provident_loan_amount + plan.commercial_loan_amount)}：其中公积金贷 ${money(plan.provident_loan_amount)}，商贷 ${money(plan.commercial_loan_amount)}。首付、贷款和交易现金按 ${purchaseMonthText} 的资产路径测算。`;
  const policyBasisText = `政策依据采用北京住房公积金官方口径：首套/二套分别读取规则包中的商贷和公积金最低首付比例，系统取更严格者；公积金贷款按“每缴存一年可贷 15 万元”随 ${purchaseMonthText} 的缴存时间增长，并受首套 ${money(1200000)}、二套 ${money(1000000)} 的基础最高额度、购房月收入还款能力和基本生活费保留约束。当前房源性质为「${propertyNatureText || "未标注"}」，符合绿色建筑、装配式建筑或超低能耗建筑时按可叠加项目求和并受上浮封顶控制，本方案上浮 ${money(plan.provident_policy_bonus)}，最终政策上限 ${money(plan.provident_policy_cap)}。`;
  const termBasisText = `贷款年限依据同时看手动设定年限、北京公积金最长 30 年、借款申请人年龄上限，以及二手房/老旧小区房龄或土地剩余年限；本方案采用公积金 ${plan.provident_loan_years} 年，理由：${plan.provident_loan_year_limit_reasons.join("；")}。`;
  const commercialPrepaymentText = plan.commercial_prepayment_enabled
    ? ` 商贷提前还本采用「${commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]}」：合同按第 ${plan.commercial_prepayment_allowed_after_month} 个还款月后才允许提前还本估算，实际从第 ${plan.commercial_prepayment_start_month} 个还款月起每月额外还本金 ${money(plan.commercial_prepayment_monthly_amount)}；按合同月供不降、缩短期限估算，预计 ${plan.commercial_actual_payoff_months} 个月结清，节省商贷利息约 ${money(plan.commercial_interest_saved_by_prepayment)}。`
    : ` 商贷提前还本策略为「${commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]}」，当前方案未安排额外还本，按合同还款节奏测算。`;
  const repaymentDetailText = `买后还款按两笔贷款分开计算：公积金贷 ${money(plan.provident_loan_amount)}，${plan.provident_loan_years} 年，${repaymentMethodLabels[plan.provident_repayment_method]}，首月/月供约 ${money(plan.provident_monthly_payment)}；商贷 ${money(plan.commercial_loan_amount)}，${plan.commercial_loan_years} 年，${repaymentMethodLabels[plan.commercial_repayment_method]}，首月/月供约 ${money(plan.commercial_monthly_payment)}。两者合计合同月供约 ${money(plan.total_monthly_payment)}，全周期利息约 ${money(plan.total_interest)}。${commercialPrepaymentText}${plan.commercial_repayment_advice ? ` ${plan.commercial_repayment_advice}` : ""}${plan.provident_repayment_advice ? ` ${plan.provident_repayment_advice}` : ""}`;
  const extractionNotesText = plan.provident_extraction_notes
    .map((note) => note.replace(/[。；\s]+$/u, ""))
    .join("；");
  const familySupportText = familySupportAmount(plan) > 0
    ? `另有${familySupportLabel(plan) || "亲属首付支持"} ${money(familySupportAmount(plan))}，用于减少家庭自己需要覆盖的首付现金。`
    : "";
  const extractionDetailText = `公积金提取按房源性质处理：符合条件的新房可按规则把本人公积金中的 ${money(plan.provident_upfront_extractable)} 直接用于抵扣首付；二手房默认更保守，主要把购房完成后、审核通过后预计可提到银行卡的金额单独列出，本方案预计到账 ${money(plan.provident_post_transaction_extractable)}，不是交易当天可用首付现金。剩余公积金余额约 ${money(plan.provident_balance_after_extract)}。${familySupportText}${extractionNotesText}。`;
  const usesMonthlyProvidentRepayment = (plan.post_purchase_pf_strategy ?? "").includes("monthly_repayment_withdrawal");
  const cashText = plan.liquidity_ok
    ? `交易当下现金约 ${money(plan.cash_after_transaction)}，购房后公积金预计到账后约 ${money(plan.cash_after_purchase)}，覆盖 ${money(plan.required_liquidity_reserve)} 安全垫。`
    : `交易当下现金约 ${money(plan.cash_after_transaction)}，低于 ${money(plan.required_liquidity_reserve)} 安全垫要求。`;
  const flowText =
    plan.post_purchase_cash_flow >= 0
      ? `买后自由现金流约 ${money(plan.post_purchase_cash_flow)}；贷后公积金策略为「${providentStrategyLabel(plan)}」，策略后现金压力折算约 ${money(plan.post_purchase_cash_flow_with_pf_withdrawal)}/月。${usesMonthlyProvidentRepayment ? "按月抵扣只覆盖公积金贷月供，不作为工资类收入。" : "半年度冲本金只在约定月体现，不作为工资类收入。"}`
      : `买后自由现金流约 ${money(plan.post_purchase_cash_flow)}；贷后公积金策略为「${providentStrategyLabel(plan)}」，系统会在按月抵月供、半年度冲本金和留存账户之间评估现金压力，但不会把公积金当作自由现金收入。`;
  const renovationText =
    plan.renovation_cost <= 0
      ? "当前购房需求后没有启用装修规划事件。"
      : plan.months_to_renovation === null
        ? `装修事件预算 ${money(plan.renovation_cost)}；当前购房后可用资金与月结余不足，暂无法安排执行。`
        : `装修事件预算 ${money(plan.renovation_cost)}，不计入买房交易日现金；预计在 ${formatMonthDate(timelineBaseDate, (plan.months_to_buy ?? 0) + plan.months_to_renovation)} 执行。`;
  const risks = [
    plan.debt_to_income_ratio > 0.5 ? "负债收入比较高，需要压低总价或延后买入。" : "负债收入比处在可观察区间。",
    plan.liquidity_ok ? "现金留存满足当前安全垫设定。" : "现金留存偏薄，建议提高流动性偏好或增加等待时间。",
    plan.post_purchase_cash_flow >= 0 ? "买后自由现金流为正，日常压力相对可控。" : "买后自由现金流为负，需要重新调整目标或贷款结构。"
  ];

  return (
    <section className="result-panel strategy-narrative">
      <div className="strategy-panel-head">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="当前策略说明" compact />
        <span>{isRecommended ? "系统推荐策略" : `${recommendation?.recommendation_score ?? 0} 分候选策略`}</span>
      </div>
      <div className="narrative-grid">
        {householdStrategy ? (
          <article className="wide">
            <span>家庭总策略</span>
            <strong>所有重大目标采用同一长期账本与风险门槛，而不是分别追求局部最优。</strong>
            <p>{householdStrategy}</p>
          </article>
        ) : null}
        <article>
          <span>执行路径</span>
          <strong>{timingText}</strong>
          <p>{loanText}</p>
        </article>
        <article>
          <span>政策依据</span>
          <strong>按北京公积金贷款额度、房源上浮、最低首付和贷款年限规则计算。</strong>
          <p>{policyBasisText} {termBasisText}</p>
        </article>
        <article>
          <span>买后还款方案</span>
          <strong>公积金贷和商贷分开测算月供、期限、还款方式和总利息。</strong>
          <p>{repaymentDetailText} {flowText}</p>
        </article>
        <article>
          <span>公积金提取</span>
          <strong>按房源性质区分交易前首付提取、交易后购房提取；买房后的月缴公积金默认留存在账户。</strong>
          <p>{extractionDetailText}</p>
        </article>
        <article>
          <span>资金结论</span>
          <strong>{cashText}</strong>
          <p>{flowText}</p>
        </article>
        <article>
          <span>装修安排</span>
          <strong>{renovationText}</strong>
          <p>装修不再绑定候选房源，也不会计入买房交易日现金；后端按独立装修目标的依赖等待期和资金可达时间安排执行。</p>
        </article>
        <article>
          <span>推荐理由</span>
          <strong>{recommendation?.recommendation_reasons[0] ?? plan.description}</strong>
          <p>{recommendation?.recommendation_reasons.slice(1, 3).join("；") || plan.description}</p>
        </article>
      </div>
      <div className="narrative-list">
        {risks.map((risk) => (
          <div key={risk}>
            <CheckCircle2 size={16} />
            <span>{risk}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function CarPlanPage({
  carPlan,
  result,
  planningSequence,
  carStrategies,
  carStrategySourceLabel,
  updateCarPlan,
  updateCarPlanPatch,
  updateCarPlanSelection,
  createVehiclePlanningGoal,
  saveVehiclePlanningGoal,
  deleteVehiclePlanningGoal,
  savePlanningGoalData,
  calculationPending,
  openPlanningGoals
}: {
  carPlan: CarPlanData;
  result: AffordabilityResult | null;
  planningSequence: PlanningSequenceResult | null;
  carStrategies: CarPlanAnalysis[];
  carStrategySourceLabel: string;
  updateCarPlan: <K extends keyof CarPlanData>(key: K, value: CarPlanData[K]) => void;
  updateCarPlanPatch: (patch: Partial<CarPlanData>) => void;
  updateCarPlanSelection: (vehicleIndex: number, variant: string) => void;
  createVehiclePlanningGoal: (vehicle: VehiclePlanData, index: number) => Promise<boolean>;
  saveVehiclePlanningGoal: (goalId: string, vehicle: VehiclePlanData, index: number) => Promise<boolean>;
  deleteVehiclePlanningGoal: (goalId: string) => Promise<boolean>;
  savePlanningGoalData: (goalId: string, goalData: PlanningGoalData) => Promise<void>;
  calculationPending: boolean;
  openPlanningGoals: () => void;
}) {
  const vehiclePlans = carPlan.vehicle_plans ?? [];
  const [selectedVehicleIndex, setSelectedVehicleIndex] = useState(0);
  const activeVehicleGoalId = vehiclePlans[selectedVehicleIndex]?.planning_goal_id ?? "";
  const resolvedVehicleGoalById = useMemo(() => (
    new Map((planningSequence?.goals ?? []).filter((goal) => goal.goal_type === "vehicle").map((goal) => [goal.id, goal]))
  ), [planningSequence?.goals]);
  const vehicleDependencyOptions = useMemo(() => (
    planningGoalDependencyOptions(
      planningSequence?.goals ?? [],
      activeVehicleGoalId ? new Set([activeVehicleGoalId]) : new Set()
    )
  ), [activeVehicleGoalId, planningSequence?.goals]);
  const vehicleDependencyLabel = (goalId: string) =>
    planningGoalDependencyLabel(goalId, vehicleDependencyOptions, planningSequence?.goals ?? []);
  const scheduleVehicleGoalSave = useDebouncedPlanningGoalSave<{ vehicle: VehiclePlanData; index: number }>({
    buildGoalData: ({ vehicle, index }) => vehiclePlanningGoalData(vehicle, index),
    saveGoal: savePlanningGoalData,
    onError: (err) => console.error(userFacingError("保存车辆需求", err))
  });
  useEffect(() => {
    if (vehiclePlans.length === 0) {
      if (selectedVehicleIndex !== 0) setSelectedVehicleIndex(0);
      return;
    }
    if (selectedVehicleIndex >= vehiclePlans.length) setSelectedVehicleIndex(vehiclePlans.length - 1);
  }, [selectedVehicleIndex, vehiclePlans.length]);
  const strategyLabel = (strategyKey: string) => ({
    target: "手动策略",
    cash: "全款",
    high_down_low_loan: "高首付低贷",
    low_down_keep_cash: "低首付保现金",
    accelerated_principal: "提前还本降息",
    delay_purchase: "延后买车"
  }[strategyKey] ?? strategyKey);
  const strategyDecisionText = (strategy: CarPlanAnalysis) => {
    if (!strategy.lifecycle_feasible && strategy.lifecycle_risk_note) return strategy.lifecycle_risk_note;
    if (strategy.description) return strategy.description;
    if (strategy.strategy_key === "cash") return "一次性现金支出最高，但之后没有车贷月供，适合现金安全垫非常充足时。";
    if (strategy.strategy_key === "high_down_low_loan") return "用较高首付换较低贷款本金和较短还款期，家庭承担利息更容易控制。";
    if (strategy.strategy_key === "low_down_keep_cash") return "保留更多现金给购房和应急垫，但车贷本金、利息和买后月压力更高。";
    if (strategy.strategy_key === "accelerated_principal") return "合同允许后额外还本金，目标是缩短车贷期限并降低家庭承担利息。";
    if (strategy.strategy_key === "delay_purchase") return "先不买车，把现金留给购房窗口和安全垫，适合当前现金曲线偏紧时。";
    return "按这个车源的手动参数测算，适合细调首付、期数、利率和购车时间。";
  };
  const displayStrategyName = (strategy: CarPlanAnalysis) => {
    const sourceName = strategy.vehicle_candidate_name || strategy.vehicle_name;
    const financingName = strategy.financing_option_name ? ` · ${strategy.financing_option_name}` : "";
    return `${sourceName}${financingName} · ${strategyLabel(strategy.strategy_key)}`;
  };
  const carStrategyIdentity = (strategy: CarPlanAnalysis) => [
    strategy.planning_goal_id || `vehicle-${strategy.vehicle_index}`,
    strategy.vehicle_candidate_index ?? "manual",
    strategy.financing_option_id || strategy.financing_option_name || "financing",
    strategy.strategy_key,
    strategy.variant
  ].join(":");
  const strategiesByVehicle = vehiclePlans.map((_, vehicleIndex) => carStrategies.filter((strategy) => strategy.vehicle_index === vehicleIndex));
  const resolveActiveCarStrategy = (vehicle: VehiclePlanData, vehicleIndex: number) => {
    const strategies = strategiesByVehicle[vehicleIndex] ?? [];
    if (!strategies.length) return null;
    const selectedVariant = normalizeCarStrategySelection(vehicle.selected_strategy_variant);
    const exact = strategies.find((strategy) => strategy.variant === selectedVariant);
    if (exact) return exact;
    const selectedKey = carStrategyKeyFromSelection(selectedVariant);
    return strategies.find((strategy) => strategy.strategy_key === selectedKey) ?? null;
  };
  const activeVehicleStrategies = new Set(
    vehiclePlans
      .map((vehicle, index) => resolveActiveCarStrategy(vehicle, index))
      .filter((strategy): strategy is CarPlanAnalysis => strategy !== null)
      .map(carStrategyIdentity)
      .filter(Boolean)
  );
  const strategyDecisionTone = (strategy: CarPlanAnalysis) => {
    if (!strategy.lifecycle_feasible || strategy.lifecycle_cash_shortfall > 0 || strategy.lifecycle_insolvency_month !== null) return "bad";
    if (strategy.cash_after_purchase < (strategy.required_liquidity_reserve ?? 0) || strategy.monthly_cash_flow_after_car < 0) return "bad";
    if (strategy.strategy_key === "delay_purchase") return "warn";
    if (strategy.happiness_score >= 7 && strategy.total_interest <= Math.max(1, strategy.loan_principal) * 0.08) return "good";
    return "neutral";
  };
  const strategyDecisionLabel = (strategy: CarPlanAnalysis) => {
    if (!strategy.lifecycle_feasible || strategy.lifecycle_cash_shortfall > 0) return "长期现金不可行";
    if (strategy.cash_after_purchase < (strategy.required_liquidity_reserve ?? 0)) return "安全垫不足";
    if (strategy.monthly_cash_flow_after_car < 0) return "月压偏高";
    if (strategy.strategy_key === "delay_purchase") return "保留买房现金";
    if (strategy.strategy_key === "cash") return "无车贷压力";
    if (strategy.strategy_key === "high_down_low_loan") return "低月供低利息";
    if (strategy.strategy_key === "low_down_keep_cash") return "保现金";
    if (strategy.strategy_key === "accelerated_principal") return "降净利息";
    return "可手动细调";
  };
  const carStrategyComparisonRows = carStrategies
    .slice()
    .sort((left, right) => {
      if (left.vehicle_index !== right.vehicle_index) return left.vehicle_index - right.vehicle_index;
      const leftSource = left.vehicle_candidate_index ?? -1;
      const rightSource = right.vehicle_candidate_index ?? -1;
      if (leftSource !== rightSource) return leftSource - rightSource;
      return (right.happiness_score - left.happiness_score) || (left.monthly_total_ownership_cost - right.monthly_total_ownership_cost);
    });
  const carStrategyAnalysisItems = (() => {
    if (!carStrategies.length) return [];
    const reachable = carStrategies.filter((strategy) => strategy.months_to_buy !== null);
    const fastest = reachable.reduce<CarPlanAnalysis | null>(
      (best, item) => best === null || (item.months_to_buy ?? 9999) < (best.months_to_buy ?? 9999) ? item : best,
      null
    );
    const lowestInterest = carStrategies.reduce<CarPlanAnalysis | null>(
      (best, item) => best === null || item.total_interest < best.total_interest ? item : best,
      null
    );
    const safestCash = carStrategies.reduce<CarPlanAnalysis | null>(
      (best, item) => best === null || item.cash_after_purchase > best.cash_after_purchase ? item : best,
      null
    );
    const bestHappiness = carStrategies.reduce<CarPlanAnalysis | null>(
      (best, item) => best === null || item.happiness_score > best.happiness_score ? item : best,
      null
    );
    return [
      fastest ? { label: "最快可买", value: displayStrategyName(fastest), detail: fastest.years_to_buy === null ? "暂不可达" : `${fastest.years_to_buy} 年` } : null,
      lowestInterest ? { label: "最低利息", value: displayStrategyName(lowestInterest), detail: money(lowestInterest.total_interest) } : null,
      safestCash ? { label: "买后现金最稳", value: displayStrategyName(safestCash), detail: money(safestCash.cash_after_purchase) } : null,
      bestHappiness ? { label: "幸福指数最高", value: displayStrategyName(bestHappiness), detail: `${bestHappiness.happiness_score.toFixed(1)} / 10` } : null
    ].filter((item): item is { label: string; value: string; detail: string } => item !== null);
  })();
  const selectedCarStrategy = vehiclePlans.length
    ? vehiclePlans.map((vehicle, index) => {
      if (!vehiclePlanIsIncludedInPlanning(vehicle)) {
        return `${vehicle.name || `车辆 ${index + 1}`}：暂不纳入规划`;
      }
      const activeStrategy = resolveActiveCarStrategy(vehicle, index);
      if (activeStrategy) {
        return `${vehicle.name || `车辆 ${index + 1}`}：${displayStrategyName(activeStrategy)}`;
      }
      return `${vehicle.name || `车辆 ${index + 1}`}：尚未采用具体方案`;
    }).join("；")
    : "不买车模式";

  const buildVehicleSource = (vehicleIndex: number, candidateIndex: number, base?: Partial<VehiclePlanData>): VehiclePlanData => ({
    enabled: true,
    name: base?.name ?? `车源 ${candidateIndex + 1}`,
    selected_strategy_variant: "target",
    candidate_vehicles: [],
    financing_options: normalizeVehicleFinancingOptions(base ?? {}).length
      ? normalizeVehicleFinancingOptions(base ?? {})
      : defaultVehicleFinancingOptions(),
    selected_financing_option_id: "",
    selected_financing_option_name: "",
    selected_financing_type: "",
    selected_financing_min_down_payment_ratio: 0,
    selected_financing_max_down_payment_ratio: 1,
    selected_financing_prepayment_allowed: true,
    selected_financing_prepayment_policy_note: "",
    energy_type: base?.energy_type ?? "pure_electric",
    new_energy_catalog_eligible: base?.new_energy_catalog_eligible ?? true,
    beijing_license_indicator_status: base?.beijing_license_indicator_status ?? "unknown",
    beijing_indicator_expected_delay_months: base?.beijing_indicator_expected_delay_months ?? 0,
    license_plate_rental_enabled: base?.license_plate_rental_enabled ?? false,
    license_plate_rental_upfront_fee: base?.license_plate_rental_upfront_fee ?? 20000,
    license_plate_rental_term_months: base?.license_plate_rental_term_months ?? 36,
    license_plate_rental_renewal_fee: base?.license_plate_rental_renewal_fee ?? 20000,
    license_plate_rental_renewal_term_months: base?.license_plate_rental_renewal_term_months ?? 36,
    license_plate_rental_after_term_mode: base?.license_plate_rental_after_term_mode ?? "renew_until_own_indicator",
    beijing_family_indicator_score_enabled: base?.beijing_family_indicator_score_enabled ?? false,
    beijing_family_indicator_application_start_month: base?.beijing_family_indicator_application_start_month ?? "",
    beijing_family_indicator_applicants: normalizeVehicleIndicatorApplicants(base?.beijing_family_indicator_applicants),
    beijing_family_indicator_generations: base?.beijing_family_indicator_generations ?? 1,
    beijing_family_indicator_has_spouse: base?.beijing_family_indicator_has_spouse ?? true,
    beijing_family_indicator_main_points: base?.beijing_family_indicator_main_points ?? 2,
    beijing_family_indicator_spouse_points: base?.beijing_family_indicator_spouse_points ?? 1,
    beijing_family_indicator_other_applicant_count: base?.beijing_family_indicator_other_applicant_count ?? 0,
    beijing_family_indicator_other_points_total: base?.beijing_family_indicator_other_points_total ?? 0,
    beijing_family_indicator_application_years: base?.beijing_family_indicator_application_years ?? 0,
    beijing_family_indicator_current_cutoff_score: base?.beijing_family_indicator_current_cutoff_score ?? 36,
    beijing_family_indicator_cutoff_score_annual_change: base?.beijing_family_indicator_cutoff_score_annual_change ?? 0,
    beijing_family_indicator_last_config_year: base?.beijing_family_indicator_last_config_year ?? 2026,
    beijing_family_indicator_annual_quota: base?.beijing_family_indicator_annual_quota ?? 119200,
    vehicle_vessel_tax_annual_override: base?.vehicle_vessel_tax_annual_override ?? null,
    purchase_tax: base?.purchase_tax ?? 0,
    purchase_tax_relief: base?.purchase_tax_relief ?? 0,
    annual_vehicle_vessel_tax: base?.annual_vehicle_vessel_tax ?? 0,
    license_plate_rental_initial_fee: base?.license_plate_rental_initial_fee ?? 0,
    beijing_family_indicator_score: base?.beijing_family_indicator_score ?? 0,
    beijing_family_indicator_estimated_wait_months: base?.beijing_family_indicator_estimated_wait_months ?? null,
    ...vehiclePlanningControlDefaults(vehicleIndex, base),
    total_price: base?.total_price ?? 200000,
    down_payment_ratio: base?.down_payment_ratio ?? 0.3,
    down_payment: base?.down_payment ?? Math.round((base?.total_price ?? 200000) * (base?.down_payment_ratio ?? 0.3)),
    purchase_delay_months: base?.purchase_delay_months ?? 0,
    total_months: base?.total_months ?? 60,
    interest_free_months: base?.interest_free_months ?? 24,
    later_annual_rate: base?.later_annual_rate ?? 0.0199,
    loan_prepayment_enabled: base?.loan_prepayment_enabled ?? false,
    loan_prepayment_start_month: base?.loan_prepayment_start_month ?? 1,
    loan_prepayment_allowed_after_month: base?.loan_prepayment_allowed_after_month ?? 12,
    loan_prepayment_monthly_amount: base?.loan_prepayment_monthly_amount ?? 0,
    loan_prepayment_strategy_type: base?.loan_prepayment_strategy_type ?? "none",
    loan_prepayment_lump_sum_month: base?.loan_prepayment_lump_sum_month ?? 0,
    loan_prepayment_lump_sum_amount: base?.loan_prepayment_lump_sum_amount ?? 0,
    current_month_index: base?.current_month_index ?? 1,
    saving_start_date: base?.saving_start_date ?? "2026-07-01",
    monthly_operating_cost: base?.monthly_operating_cost ?? 0,
    no_car_monthly_commute_cost: base?.no_car_monthly_commute_cost ?? carPlan.no_car_monthly_commute_cost ?? 0,
    annual_mileage_km: base?.annual_mileage_km ?? 12000,
    electricity_kwh_per_100km: base?.electricity_kwh_per_100km ?? 14,
    electricity_price_per_kwh: base?.electricity_price_per_kwh ?? 0.8,
    monthly_parking_cost: base?.monthly_parking_cost ?? 0,
    annual_maintenance_cost: base?.annual_maintenance_cost ?? 2500,
    annual_maintenance_growth_rate: base?.annual_maintenance_growth_rate ?? 0.03,
    annual_insurance_rate: base?.annual_insurance_rate ?? 0.018,
    annual_insurance_min: base?.annual_insurance_min ?? 4500,
    annual_insurance_growth_rate: base?.annual_insurance_growth_rate ?? 0.02,
    depreciation_years: base?.depreciation_years ?? 8,
    vehicle_service_years: base?.vehicle_service_years ?? 10,
    vehicle_retirement_mileage_km: base?.vehicle_retirement_mileage_km ?? 600000,
    happiness_score: base?.happiness_score ?? 6.5,
    notes: base?.notes ?? ""
  });

  const buildVehiclePlan = (index: number): VehiclePlanData => {
    const source = buildVehicleSource(index, 0, { name: `车源 1` });
    return {
      ...source,
      name: `用车需求 ${index + 1}`,
      selected_strategy_variant: "target",
      ...vehiclePlanningControlDefaults(index, source),
      candidate_vehicles: [source]
    };
  };

  const updateVehiclePlans = (
    nextVehicles: VehiclePlanData[],
    selectedStrategy = "target",
    saveVehicleIndex: number | null = null,
    saveDelayMs = 700
  ) => {
    updateCarPlanPatch({
      enabled: nextVehicles.length > 0,
      vehicle_plans: nextVehicles,
      selected_strategy_variant: nextVehicles.length ? selectedStrategy : "no_car"
    });
    if (saveVehicleIndex !== null) {
      const vehicle = nextVehicles[saveVehicleIndex];
      if (vehicle?.planning_goal_id) {
        scheduleVehicleGoalSave(vehicle.planning_goal_id, { vehicle, index: saveVehicleIndex }, saveDelayMs);
      }
    }
  };

  const addVehicle = async () => {
    const vehicle = buildVehiclePlan(vehiclePlans.length);
    const created = await createVehiclePlanningGoal(vehicle, vehiclePlans.length);
    if (created) {
      setSelectedVehicleIndex(vehiclePlans.length);
    }
  };

  const duplicateVehicle = async (index: number) => {
    const source = vehiclePlans[index];
    if (!source) return;
    const nextVehicle: VehiclePlanData = {
      ...source,
      planning_goal_id: "",
      enabled: true,
      name: `${source.name || "用车需求"} 复制`,
      selected_strategy_variant: "target",
      planning_sequence: vehiclePlans.length + 1,
      candidate_vehicles: (source.candidate_vehicles ?? []).map((candidate, candidateIndex) => ({
        ...candidate,
        planning_goal_id: "",
        name: `${candidate.name || `车源 ${candidateIndex + 1}`} 复制`,
        selected_strategy_variant: "target",
        candidate_vehicles: []
      }))
    };
    const created = await createVehiclePlanningGoal(nextVehicle, vehiclePlans.length);
    if (created) {
      setSelectedVehicleIndex(vehiclePlans.length);
    }
  };

  const updateVehicle = async (index: number, patch: Partial<VehiclePlanData>) => {
    const currentVehicle = vehiclePlans[index];
    if (!currentVehicle) return;
    const nextVehicle = { ...currentVehicle, selected_strategy_variant: "target", ...patch };
    const nextVehicles = vehiclePlans.map((vehicle, vehicleIndex) => (
      vehicleIndex === index ? nextVehicle : vehicle
    ));
    updateVehiclePlans(nextVehicles);
    if (nextVehicle.planning_goal_id) {
      await saveVehiclePlanningGoal(nextVehicle.planning_goal_id, nextVehicle, index);
      return;
    }
  };
  const updateVehicleLocal = (index: number, patch: Partial<VehiclePlanData>) => {
    const nextVehicles = vehiclePlans.map((vehicle, vehicleIndex) => (
      vehicleIndex === index
        ? { ...vehicle, selected_strategy_variant: "target", ...patch }
        : vehicle
    ));
    updateVehiclePlans(nextVehicles);
  };
  const updateVehiclePolicy = (index: number, patch: Partial<VehiclePlanData>) => {
    const nextVehicles = vehiclePlans.map((vehicle, vehicleIndex) => (
      vehicleIndex === index
        ? { ...vehicle, selected_strategy_variant: "target", ...patch }
        : vehicle
    ));
    updateVehiclePlans(nextVehicles, "target", index, 250);
  };

  const removeVehicle = async (index: number) => {
    const vehicle = vehiclePlans[index];
    if (!vehicle) return;
    const goalId = vehicle.planning_goal_id;
    if (!goalId) {
      const nextVehicles = vehiclePlans.filter((_, vehicleIndex) => vehicleIndex !== index);
      updateVehiclePlans(nextVehicles);
      setSelectedVehicleIndex(Math.max(0, Math.min(index, nextVehicles.length - 1)));
      return;
    }
    const deleted = await deleteVehiclePlanningGoal(goalId);
    if (deleted) {
      setSelectedVehicleIndex(Math.max(0, Math.min(index, vehiclePlans.length - 2)));
    }
  };

  const addCandidate = (vehicleIndex: number) => {
    const nextVehicles = vehiclePlans.map((vehicle, index) => {
      if (index !== vehicleIndex) return vehicle;
      const candidates = vehicle.candidate_vehicles ?? [];
      return {
        ...vehicle,
        candidate_vehicles: [
          ...candidates,
          buildVehicleSource(vehicleIndex, candidates.length, {
            name: `车源 ${candidates.length + 1}`,
            planning_sequence: vehicle.planning_sequence,
            purchase_timing_mode: vehicle.purchase_timing_mode,
            depends_on_goal_id: vehicle.depends_on_goal_id,
            after_previous_event_delay_months: vehicle.after_previous_event_delay_months,
            manual_purchase_delay_months: vehicle.manual_purchase_delay_months,
            total_price: candidates[candidates.length - 1]?.total_price ?? vehicle.total_price ?? 200000,
            down_payment_ratio: candidates[candidates.length - 1]?.down_payment_ratio ?? vehicle.down_payment_ratio ?? 0.3,
            annual_mileage_km: candidates[candidates.length - 1]?.annual_mileage_km ?? vehicle.annual_mileage_km ?? 12000,
            monthly_parking_cost: candidates[candidates.length - 1]?.monthly_parking_cost ?? vehicle.monthly_parking_cost ?? 0
          })
        ]
      };
    });
    updateVehiclePlans(nextVehicles, "target", vehicleIndex);
  };

  const updateCandidate = (vehicleIndex: number, candidateIndex: number, patch: Partial<VehiclePlanData>) => {
    const nextVehicles = vehiclePlans.map((vehicle, index) => {
      if (index !== vehicleIndex) return vehicle;
      const candidates = (vehicle.candidate_vehicles ?? []).map((candidate, currentIndex) => {
        if (currentIndex !== candidateIndex) return candidate;
        const nextCandidate = { ...candidate, selected_strategy_variant: "target", ...patch, candidate_vehicles: [] };
        if (patch.total_price !== undefined && patch.down_payment_ratio === undefined && patch.down_payment === undefined) {
          nextCandidate.down_payment = Math.round(patch.total_price * (nextCandidate.down_payment_ratio ?? 0));
        }
        return nextCandidate;
      });
      return { ...vehicle, selected_strategy_variant: "target", candidate_vehicles: candidates };
    });
    updateVehiclePlans(nextVehicles, "target", vehicleIndex, 250);
  };

  const updateVehicleIndicatorApplicants = (
    vehicleIndex: number,
    updater: (applicants: VehicleIndicatorApplicantData[]) => VehicleIndicatorApplicantData[]
  ) => {
    const vehicle = vehiclePlans[vehicleIndex];
    const currentApplicants = normalizeVehicleIndicatorApplicants(vehicle?.beijing_family_indicator_applicants);
    updateVehiclePolicy(vehicleIndex, {
      beijing_family_indicator_applicants: updater(currentApplicants)
    });
  };

  const addVehicleIndicatorApplicant = (vehicleIndex: number, patch: Partial<VehicleIndicatorApplicantData> = {}) => {
    updateVehicleIndicatorApplicants(vehicleIndex, (applicants) => [
      ...applicants,
      defaultVehicleIndicatorApplicant(applicants.length, patch)
    ]);
  };

  const updateVehicleIndicatorApplicant = (
    vehicleIndex: number,
    applicantIndex: number,
    patch: Partial<VehicleIndicatorApplicantData>
  ) => {
    updateVehicleIndicatorApplicants(vehicleIndex, (applicants) =>
      applicants.map((applicant, index) => index === applicantIndex ? defaultVehicleIndicatorApplicant(index, { ...applicant, ...patch }) : applicant)
    );
  };

  const removeVehicleIndicatorApplicant = (vehicleIndex: number, applicantIndex: number) => {
    updateVehicleIndicatorApplicants(vehicleIndex, (applicants) => applicants.filter((_, index) => index !== applicantIndex));
  };

  const buildFinancingOption = (index: number, base?: Partial<VehicleFinancingOptionData>): VehicleFinancingOptionData =>
    normalizeVehicleFinancingOption(
      {
        id: base?.id ?? `financing_${Date.now()}_${index + 1}`,
        name: base?.name ?? `金融方案 ${index + 1}`,
        enabled: base?.enabled ?? true,
        financing_type: base?.financing_type ?? "dealer_subsidy",
        total_months: base?.total_months ?? 60,
        interest_free_months: base?.interest_free_months ?? 24,
        later_annual_rate: base?.later_annual_rate ?? 0.0199,
        min_down_payment_ratio: base?.min_down_payment_ratio ?? 0.1,
        max_down_payment_ratio: base?.max_down_payment_ratio ?? 1,
        prepayment_allowed: base?.prepayment_allowed ?? true,
        prepayment_allowed_after_month: base?.prepayment_allowed_after_month ?? 12,
        prepayment_policy_note: base?.prepayment_policy_note ?? "提前还本规则以经销商或银行合同为准。",
        notes: base?.notes ?? ""
      },
      index
    );

  const updateCandidateFinancingOptions = (
    vehicleIndex: number,
    candidateIndex: number,
    updater: (options: VehicleFinancingOptionData[]) => VehicleFinancingOptionData[]
  ) => {
    const nextVehicles = vehiclePlans.map((vehicle, index) => {
      if (index !== vehicleIndex) return vehicle;
      const candidates = (vehicle.candidate_vehicles ?? []).map((candidate, currentIndex) => {
        if (currentIndex !== candidateIndex) return candidate;
        const currentOptions = normalizeVehicleFinancingOptions(candidate);
        return {
          ...candidate,
          selected_strategy_variant: "target",
          financing_options: updater(currentOptions),
          candidate_vehicles: []
        };
      });
      return { ...vehicle, selected_strategy_variant: "target", candidate_vehicles: candidates };
    });
    updateVehiclePlans(nextVehicles, "target", vehicleIndex, 250);
  };

  const addFinancingOption = (vehicleIndex: number, candidateIndex: number) => {
    updateCandidateFinancingOptions(vehicleIndex, candidateIndex, (options) => [
      ...options,
      buildFinancingOption(options.length, {
        name: `金融方案 ${options.length + 1}`,
        financing_type: "standard",
        interest_free_months: 0,
        later_annual_rate: 0.039
      })
    ]);
  };

  const addFinancingTemplate = (vehicleIndex: number, candidateIndex: number, template: VehicleFinancingOptionData) => {
    updateCandidateFinancingOptions(vehicleIndex, candidateIndex, (options) => [
      ...options,
      buildFinancingOption(options.length, {
        ...template,
        id: `${template.id}_${Date.now()}`,
        name: options.some((option) => option.name === template.name) ? `${template.name} 复制` : template.name
      })
    ]);
  };

  const updateFinancingOption = (
    vehicleIndex: number,
    candidateIndex: number,
    optionIndex: number,
    patch: Partial<VehicleFinancingOptionData>
  ) => {
    updateCandidateFinancingOptions(vehicleIndex, candidateIndex, (options) =>
      options.map((option, index) => index === optionIndex ? normalizeVehicleFinancingOption({ ...option, ...patch }, index) : option)
    );
  };

  const duplicateFinancingOption = (vehicleIndex: number, candidateIndex: number, optionIndex: number) => {
    updateCandidateFinancingOptions(vehicleIndex, candidateIndex, (options) => {
      const source = options[optionIndex];
      if (!source) return options;
      return [
        ...options,
        {
          ...source,
          id: `${source.id || "financing"}_copy_${Date.now()}`,
          name: `${source.name || `金融方案 ${optionIndex + 1}`} 复制`
        }
      ];
    });
  };

  const removeFinancingOption = (vehicleIndex: number, candidateIndex: number, optionIndex: number) => {
    updateCandidateFinancingOptions(vehicleIndex, candidateIndex, (options) =>
      options.length <= 1 ? options : options.filter((_, index) => index !== optionIndex)
    );
  };

  const duplicateCandidate = (vehicleIndex: number, candidateIndex: number) => {
    const nextVehicles = vehiclePlans.map((vehicle, index) => {
      if (index !== vehicleIndex) return vehicle;
      const candidates = vehicle.candidate_vehicles ?? [];
      const source = candidates[candidateIndex];
      if (!source) return vehicle;
      return {
        ...vehicle,
        selected_strategy_variant: "target",
        candidate_vehicles: [
          ...candidates,
          {
            ...source,
            name: `${source.name || `车源 ${candidateIndex + 1}`} 复制`,
            selected_strategy_variant: "target",
            candidate_vehicles: []
          }
        ]
      };
    });
    updateVehiclePlans(nextVehicles, "target", vehicleIndex, 250);
  };

  const removeCandidate = (vehicleIndex: number, candidateIndex: number) => {
    const nextVehicles = vehiclePlans.map((vehicle, index) => {
      if (index !== vehicleIndex) return vehicle;
      const nextCandidates = (vehicle.candidate_vehicles ?? []).filter((_, currentIndex) => currentIndex !== candidateIndex);
      return {
        ...vehicle,
        selected_strategy_variant: "target",
        candidate_vehicles: nextCandidates
      };
    });
    updateVehiclePlans(nextVehicles, "target", vehicleIndex, 250);
  };

  const selectStrategy = (strategy: CarPlanAnalysis) => {
    setSelectedVehicleIndex(strategy.vehicle_index);
    updateCarPlanSelection(strategy.vehicle_index, strategy.variant);
  };
  const selectedStrategyDetails = vehiclePlans
    .map((vehicle, index) => resolveActiveCarStrategy(vehicle, index))
    .filter((strategy): strategy is CarPlanAnalysis => strategy !== null);
  const primarySelectedStrategy = selectedStrategyDetails[0] ?? carStrategyComparisonRows[0] ?? null;
  const carTimelineBaseDate = useMemo(() => new Date(), []);
  const financingTypeLabel = (type: string) => ({
    dealer_subsidy: "经销商贴息",
    standard: "普通贷款",
    bank_loan: "银行贷款",
    cash_only: "仅全款"
  }[type] ?? "金融方案");
  const carStrategyPurchaseText = (strategy: CarPlanAnalysis) =>
    strategy.months_to_buy === null
      ? "按当前现金和月结余路径，测算期内暂时无法稳妥购车。"
      : `预计 ${formatMonthDate(carTimelineBaseDate, strategy.months_to_buy)}、约 ${strategy.years_to_buy} 年后购车；这个月份会同步进入购房现金压力、贷款余额和事件时间线。`;
  const carStrategyReasonText = (strategy: CarPlanAnalysis) => {
    if (strategy.strategy_key === "cash") return "该策略用现金一次性买车，后续没有车贷月供，优先降低负债和月度压力。";
    if (strategy.strategy_key === "high_down_low_loan") return "该策略把更多现金放在首付上，压低车贷本金和月供，更适合希望买车后现金流稳定的家庭。";
    if (strategy.strategy_key === "low_down_keep_cash") return "该策略降低首付，把现金留给购房窗口和应急垫，但会换来更高车贷本金和利息。";
    if (strategy.strategy_key === "accelerated_principal") return "该策略在合同允许后比较提前还本节奏，把节省利息和理财机会成本一起考虑。";
    if (strategy.strategy_key === "delay_purchase") return "该策略把购车向后排，先保留现金给房源交易和家庭安全垫。";
    return "该策略按当前车源、金融方案和手动偏好测算，适合继续微调首付比例、购车时间或提前还本设置。";
  };
  const carStrategyFinancingText = (strategy: CarPlanAnalysis) => {
    const plateRentalText = strategy.license_plate_rental_initial_fee > 0
      ? `另外，上牌租牌首期现金支出为 ${money(strategy.license_plate_rental_initial_fee)}，这笔钱不计入车价、首付或贷款本金。`
      : "";
    if (strategy.loan_principal <= 0) {
      return `当前采用${financingTypeLabel(strategy.financing_type)}口径，但实际不形成车贷；交易当月需要覆盖 ${money(strategy.down_payment)} 车辆首付/车款。${plateRentalText}`;
    }
    return `采用「${strategy.financing_option_name || financingTypeLabel(strategy.financing_type)}」：合同 ${strategy.total_months} 期、年利率 ${percent(strategy.later_annual_rate)}，贴息 ${strategy.interest_free_months} 期。贴息不是贷款余额免息，而是厂家或经销商补贴部分利息；后端仍按合同等额本息推演余额。${plateRentalText}`;
  };
  const carStrategyPrepaymentText = (strategy: CarPlanAnalysis) => {
    if (!strategy.prepayment_allowed) {
      return "当前金融方案不允许提前还本，后端不会安排一次性或分月额外还本金；如果经销商提供可提前还本版本，需要在该车源下新增或修改金融方案。";
    }
    if (!strategy.prepayment_enabled) {
      return strategy.prepayment_explanation || "当前不安排提前还本，主要因为贴息后家庭实际资金成本不高，或现金更应该留给购房和应急垫。";
    }
    const lump = strategy.prepayment_lump_sum_amount > 0
      ? `第 ${strategy.prepayment_lump_sum_month} 期一次性还本 ${money(strategy.prepayment_lump_sum_amount)}`
      : "";
    const monthly = strategy.prepayment_monthly_amount > 0
      ? `从第 ${strategy.prepayment_start_month} 期起每月额外还本 ${money(strategy.prepayment_monthly_amount)}`
      : "";
    return `${strategy.prepayment_explanation || "后端按利息节省、理财收益和现金安全综合选择提前还本。"}${[lump, monthly].filter(Boolean).join("，")}；预计 ${strategy.actual_payoff_months} 个月结清，节省利息约 ${money(strategy.interest_saved_by_prepayment)}，净收益约 ${money(strategy.prepayment_net_benefit)}。`;
  };
  const carStrategyRiskItems = (strategy: CarPlanAnalysis) => [
    strategy.cash_after_purchase >= (strategy.required_liquidity_reserve ?? 0)
      ? `买后现金预计 ${money(strategy.cash_after_purchase)}，覆盖 ${money(strategy.required_liquidity_reserve ?? 0)} 的现金安全垫。`
      : `买后现金预计 ${money(strategy.cash_after_purchase)}，低于 ${money(strategy.required_liquidity_reserve ?? 0)} 的现金安全垫；需要降低车价、提高等待时间或改用延后购车策略。`,
    strategy.monthly_cash_flow_after_car >= 0
      ? `买后月结余预计 ${money(strategy.monthly_cash_flow_after_car)}，车贷和养车支出已纳入现金流。`
      : `买后月结余预计 ${money(strategy.monthly_cash_flow_after_car)}，不建议在不调整收入或支出的情况下采用。`,
    strategy.total_interest_subsidy > 0
      ? `经销商贴息预计覆盖 ${money(strategy.total_interest_subsidy)} 利息，但仍要确认合同是否限制提前还本或收取违约金。`
      : strategy.prepayment_allowed
        ? `当前金融方案没有明显贴息补贴，应重点比较车贷利率和理财预期收益。`
        : `当前金融方案不允许提前还本，策略只比较首付、购车时间和现金安全。`,
    strategy.beijing_family_indicator_estimated_wait_months !== null
      ? `家庭新能源指标估算分约 ${strategy.beijing_family_indicator_score.toFixed(2)}，预计等待 ${strategy.beijing_family_indicator_estimated_wait_months} 个月；启用租牌时购车时间不再被该等待直接推迟。`
      : "北京指标时间按指标状态、申请规则和购车需求时间段处理。",
    ...strategy.notes
      .filter((note) =>
        note.includes("家庭新能源指标") ||
        note.includes("家庭指标") ||
        note.includes("申请人") ||
        note.includes("每满一年") ||
        note.includes("代计算")
      )
      .slice(0, 8)
  ];

  const carLoan = result?.car_loan;
  const activeVehiclePlan = vehiclePlans[selectedVehicleIndex] ?? null;
  const activeVehicleCandidate = activeVehiclePlan?.candidate_vehicles?.[0] ?? activeVehiclePlan;
  const heroCarStrategy = primarySelectedStrategy;
  const householdStrategyPlan = result?.purchase_plan_analyses.find((plan) => plan.is_recommended)
    ?? result?.purchase_plan_analyses[0];
  const householdStrategy = householdStrategyPlan
    ? result?.strategy_explanations.find(
      (item) => item.plan_variant === householdStrategyPlan.variant && item.section === "household"
    )?.body ?? ""
    : "";

  return (
    <PlannerPageShell
      icon={<Car size={20} />}
      title="购车计划"
      action={
        <button className="ghost-button" type="button" onClick={addVehicle}>
          <Plus size={16} /> 添加用车需求
        </button>
      }
      summary={<p>按“用车需求、候选车源、车辆参数与策略、政策与上牌、影响预览”的顺序管理购车目标。</p>}
    >

      <section className="strategy-hero">
        <div className="strategy-hero-main">
          <PanelTitle icon={<Sparkles size={18} />} title={vehiclePlans.length ? "自动推荐" : "默认不购车"} compact />
          {vehiclePlans.length === 0 ? (
            <>
              <div className="recommend-title">
                <h3>当前不设定购车需求</h3>
                <span>基线</span>
              </div>
              <p>系统只把无车通勤月成本计入现金流；需要购车时，先添加用车需求，再在需求下添加候选车源并生成贷款策略。</p>
              <button className="primary-button recommend-action" type="button" onClick={addVehicle}>
                <Plus size={16} /> 添加用车需求
              </button>
              <div className="recommend-reasons">
                <span>不会默认生成车贷和购车事件</span>
                <span>可视化展示的是不购车基线现金流</span>
                <span>添加车源后再比较全款、贷款和延后策略</span>
              </div>
            </>
          ) : heroCarStrategy ? (
            <>
              <div className="recommend-title">
                <h3>{displayStrategyName(heroCarStrategy)}</h3>
                <span>{heroCarStrategy.happiness_score.toFixed(1)} 分</span>
              </div>
              <p>{strategyDecisionText(heroCarStrategy)}</p>
              <button className="primary-button recommend-action" type="button" onClick={() => selectStrategy(heroCarStrategy)}>
                <Sparkles size={16} /> 查看当前购车策略
              </button>
              <div className="recommend-reasons">
                <span>{heroCarStrategy.years_to_buy === null ? "暂不可达" : `${heroCarStrategy.years_to_buy} 年左右可购车`}</span>
                <span>买后现金 {money(heroCarStrategy.cash_after_purchase)}</span>
                <span>买后月结余 {money(heroCarStrategy.monthly_cash_flow_after_car)}</span>
              </div>
            </>
          ) : (
            <p>{calculationPending ? "正在按最新用车需求重新生成推荐策略。" : "添加候选车源后会自动生成推荐策略。"}</p>
          )}
        </div>
        <div className="strategy-hero-side">
          <Metric label="用车需求" value={vehiclePlans.length ? `${vehiclePlans.length} 个` : "未添加"} />
          <Metric
            label="候选车源"
            value={vehiclePlans.length ? `${vehiclePlans.reduce((sum, item) => sum + (item.candidate_vehicles?.length ?? 0), 0)} 个` : "未添加"}
          />
          <Metric
            label={vehiclePlans.length ? "选中策略" : "当前模式"}
            value={vehiclePlans.length ? heroCarStrategy ? strategyLabel(heroCarStrategy.strategy_key) : "待生成" : "不购车基线"}
            tone={heroCarStrategy ? strategyDecisionTone(heroCarStrategy) === "bad" ? "bad" : "good" : "warn"}
          />
          <Metric label="策略来源" value={carStrategySourceLabel} />
        </div>
      </section>

      <div className="strategy-layout">
        <aside className="strategy-side-panel car-planner-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<CircleDollarSign size={18} />} title="用车需求与候选车源" compact collapsible />
          <span>{selectedCarStrategy}</span>
        </div>
        <div className="planning-goal-grid horizontal-card-list vehicle-goal-grid">
          {vehiclePlans.map((vehicle, vehicleIndex) => {
            const firstCandidate = vehicle.candidate_vehicles?.[0] ?? vehicle;
            const resolvedGoal = resolvedVehicleGoalById.get(vehicle.planning_goal_id || "");
            const includedInPlanning = vehiclePlanIsIncludedInPlanning(vehicle);
            return (
              <article className={vehicleIndex === selectedVehicleIndex ? "planning-goal-card active" : "planning-goal-card"} key={`vehicle-goal-${vehicleIndex}`}>
                <button className="planning-goal-select" type="button" onClick={() => setSelectedVehicleIndex(vehicleIndex)}>
                  <span className={includedInPlanning ? "goal-status enabled" : "goal-status paused"}>
                    {planningInclusionStatusLabel(includedInPlanning, vehicle.enabled)}
                  </span>
                  <strong>{vehicle.name || `用车需求 ${vehicleIndex + 1}`}</strong>
                  <small>
                    {money(firstCandidate.total_price || vehicle.total_price)} · {resolvedGoal ? planningGoalOrderLabel(resolvedGoal) : `顺序 ${vehicle.planning_sequence}`}
                  </small>
                  <em>
                    {vehiclePlanningTimingSummary(vehicle, vehicleDependencyLabel(vehicle.depends_on_goal_id || ""))}
                  </em>
                </button>
                <div className="planning-goal-actions">
                  <button className="ghost-button small" type="button" onClick={() => setSelectedVehicleIndex(vehicleIndex)}>
                    编辑
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => duplicateVehicle(vehicleIndex)}>
                    <Copy size={14} /> 复制
                  </button>
                  <button className="ghost-button small" type="button" onClick={openPlanningGoals}>调整排期</button>
                  <button className="ghost-button small danger-action" type="button" onClick={() => removeVehicle(vehicleIndex)} aria-label="删除用车需求">
                    <Trash2 size={14} /> 删除
                  </button>
                </div>
              </article>
            );
          })}
        </div>
        {calculationPending ? (
          <p className="goal-updating-note">用车需求已更新，正在重新生成候选车源对比与贷款策略。</p>
        ) : null}
        <div className="form-grid two">
          <NumberField label="无车通勤月成本" value={carPlan.no_car_monthly_commute_cost ?? 0} min={0} step={100} onChange={(value) => updateCarPlan("no_car_monthly_commute_cost", value)} />
        </div>
        {activeVehiclePlan ? (
          <>
            <div className="vehicle-source-toolbar property-source-toolbar">
              <strong>{activeVehiclePlan.name || `用车需求 ${selectedVehicleIndex + 1}`}的候选车源</strong>
              <button className="ghost-button small" type="button" onClick={() => addCandidate(selectedVehicleIndex)}>
                <Plus size={14} /> 添加候选车源
              </button>
            </div>
            {(activeVehiclePlan.candidate_vehicles ?? []).length ? (
              <div className="vehicle-source-grid property-source-grid car-source-list">
                {(activeVehiclePlan.candidate_vehicles ?? []).map((candidate, candidateIndex) => (
                  <article className="vehicle-source-card" key={`vehicle-source-summary-${selectedVehicleIndex}-${candidateIndex}`}>
                    <div className="vehicle-source-head">
                      <button className="planning-goal-select compact-select" type="button">
                        <span className={candidate.enabled ? "goal-status enabled" : "goal-status paused"}>
                          {candidate.enabled ? "纳入策略" : "已停用"}
                        </span>
                        <strong>{candidate.name || `候选车源 ${candidateIndex + 1}`}</strong>
                        <small>{money(candidate.total_price)} · {candidate.annual_mileage_km ?? 0} 公里/年</small>
                      </button>
                      <button className="ghost-button small danger-action" type="button" onClick={() => removeCandidate(selectedVehicleIndex, candidateIndex)} aria-label="删除车源">
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="planning-goal-actions">
                      <button className="ghost-button small" type="button" onClick={() => duplicateCandidate(selectedVehicleIndex, candidateIndex)}>
                        <Copy size={14} /> 复制
                      </button>
                      <span className="source-summary-pill">
                        {normalizeVehicleFinancingOptions(candidate).length} 个金融方案
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state compact-empty-state">这个用车需求还没有候选车源。</div>
            )}
          </>
        ) : null}
        </aside>

        <section className="strategy-main-panel car-config-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="车辆参数与手动策略" compact collapsible />
            <span>修改后会自动重算购车策略、贷款结构和现金流</span>
          </div>
        <div className="member-list compact-list vehicle-plan-list">
          {vehiclePlans.filter((_, vehicleIndex) => vehicleIndex === selectedVehicleIndex).map((vehicle) => {
            const vehicleIndex = selectedVehicleIndex;
            const candidates = vehicle.candidate_vehicles ?? [];
            const includedInPlanning = vehiclePlanIsIncludedInPlanning(vehicle);
            return (
              <section className="member-card vehicle-plan-card" key={`vehicle-plan-${vehicleIndex}`}>
                <div className="member-card-head">
                  <Field label="用车需求名称">
                    <input
                      value={vehicle.name}
                      onChange={(event) => updateVehicleLocal(vehicleIndex, { name: event.target.value })}
                      onBlur={() => void updateVehicle(vehicleIndex, { name: vehiclePlans[vehicleIndex]?.name ?? vehicle.name })}
                    />
                  </Field>
                  <span className={includedInPlanning ? "decision-pill good" : "decision-pill"}>{includedInPlanning ? "纳入当前规划" : "暂不纳入规划"}</span>
                  <button className="ghost-button small danger-action" type="button" onClick={() => removeVehicle(vehicleIndex)} aria-label="删除用车需求">
                    <Trash2 size={14} /> 删除需求
                  </button>
                </div>
                <div className="planning-source-note">
                  <div>
                    <strong>统一排期</strong>
                    <span>{vehiclePlanningTimingSummary(vehicle, vehicleDependencyLabel(vehicle.depends_on_goal_id || ""))}</span>
                  </div>
                  <button className="ghost-button small" type="button" onClick={openPlanningGoals}>到规划目标调整</button>
                </div>
                <div className="vehicle-source-toolbar">
                  <span>候选车源会分别生成全款、高首付低贷、低首付保现金、延后购车等贷款策略。</span>
                  <button className="ghost-button small" type="button" onClick={() => addCandidate(vehicleIndex)}>
                    <Plus size={14} /> 添加车源
                  </button>
                </div>
                {candidates.length ? (
                  <div className="vehicle-source-grid">
                    {candidates.map((candidate, candidateIndex) => (
                      <article className="vehicle-source-card" key={`vehicle-${vehicleIndex}-candidate-${candidateIndex}`}>
                        <div className="vehicle-source-head">
                          <Field label="车源名称">
                            <input value={candidate.name} onChange={(event) => updateCandidate(vehicleIndex, candidateIndex, { name: event.target.value })} />
                          </Field>
                          <button className="ghost-button small" type="button" onClick={() => duplicateCandidate(vehicleIndex, candidateIndex)} aria-label="复制车源">
                            <Copy size={14} /> 复制车源
                          </button>
                          <button className="ghost-button small danger-action" type="button" onClick={() => removeCandidate(vehicleIndex, candidateIndex)} aria-label="删除车源">
                            <Trash2 size={14} /> 删除车源
                          </button>
                        </div>
                        <div className="vehicle-setting-stack">
                          <CollapsibleSettingGroup title="车辆属性" profile="core">
                            <div className="form-grid compact-fields">
                              <NumberField label="车辆总价" value={candidate.total_price} min={0} step={10000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { total_price: value })} />
                              <Field label="能源类型">
                                <select
                                  value={candidate.energy_type ?? "pure_electric"}
                                  onChange={(event) => updateCandidate(vehicleIndex, candidateIndex, { energy_type: event.target.value as VehiclePlanData["energy_type"] })}
                                >
                                  <option value="pure_electric">纯电动</option>
                                  <option value="plug_in_hybrid">插电混动</option>
                                  <option value="range_extended">增程式</option>
                                  <option value="fuel_cell">燃料电池</option>
                                  <option value="fuel">燃油车</option>
                                </select>
                              </Field>
                              <SwitchField
                                label="符合新能源购置税目录"
                                checked={candidate.new_energy_catalog_eligible ?? true}
                                onChange={(checked) => updateCandidate(vehicleIndex, candidateIndex, { new_energy_catalog_eligible: checked })}
                              />
                              <NumberField
                                label="车船税覆盖值/年"
                                value={candidate.vehicle_vessel_tax_annual_override ?? 0}
                                min={0}
                                max={10000}
                                step={10}
                                onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { vehicle_vessel_tax_annual_override: value > 0 ? value : null })}
                              />
                              <NumberField label="年行驶里程" value={candidate.annual_mileage_km ?? 12000} min={0} max={100000} step={1000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_mileage_km: value })} />
                              <NumberField label="百公里电耗" value={candidate.electricity_kwh_per_100km ?? 14} min={0} max={50} step={0.5} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { electricity_kwh_per_100km: value })} />
                              <NumberField label="充电单价" value={candidate.electricity_price_per_kwh ?? 0.8} min={0} max={5} step={0.05} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { electricity_price_per_kwh: value })} />
                              <NumberField label="月停车费" value={candidate.monthly_parking_cost ?? 0} min={0} step={100} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { monthly_parking_cost: value })} />
                              <NumberField label="年保养杂费" value={candidate.annual_maintenance_cost ?? 0} min={0} step={500} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_maintenance_cost: value })} />
                              <NumberField label="保险费率" value={candidate.annual_insurance_rate ?? 0.018} min={0} max={0.2} step={0.001} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_insurance_rate: value })} />
                              <NumberField label="年保险下限" value={candidate.annual_insurance_min ?? 0} min={0} step={500} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_insurance_min: value })} />
                              <NumberField label="折旧年限" value={candidate.depreciation_years ?? 8} min={1} max={20} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { depreciation_years: value })} />
                              <NumberField label="实际使用年限" value={candidate.vehicle_service_years ?? 10} min={1} max={30} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { vehicle_service_years: value })} />
                              <NumberField label="报废/更新里程" value={candidate.vehicle_retirement_mileage_km ?? 600000} min={0} max={1000000} step={10000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { vehicle_retirement_mileage_km: value })} />
                              <NumberField label="购车幸福度" value={candidate.happiness_score ?? 6.5} min={0} max={10} step={0.5} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { happiness_score: value })} />
                            </div>
                            <p className="field-hint">
                              车辆没有固定强制报废年限时，后端会按实际使用年限和报废/更新里程择早估算更新月份。实际使用年限默认 10 年，可按性能衰减、维修经济性和家庭体验手动调整；到该月后，车辆资产、电费、停车费、保险、保养和车船税停止计入，若车贷未结清，贷款余额和月供仍继续进入现金流。
                            </p>
                          </CollapsibleSettingGroup>

                          <CollapsibleSettingGroup
                            title="经销商金融方案"
                            className="vehicle-financing-group"
                            action={(
                              <button className="ghost-button small" type="button" onClick={() => addFinancingOption(vehicleIndex, candidateIndex)}>
                                <Plus size={14} /> 添加金融方案
                              </button>
                            )}
                          >
                            <p className="field-hint">金融方案是经销商或银行给出的可选政策，购车策略只能选择使用哪一种，再决定首付比例和提前还本节奏。</p>
                            <div className="template-chip-row">
                              {defaultVehicleFinancingOptions().map((template) => (
                                <button
                                  className="ghost-button small"
                                  key={template.id}
                                  type="button"
                                  onClick={() => addFinancingTemplate(vehicleIndex, candidateIndex, template)}
                                >
                                  <Plus size={14} /> {template.name}
                                </button>
                              ))}
                            </div>
                            <div className="vehicle-financing-grid">
                              {normalizeVehicleFinancingOptions(candidate).map((option, optionIndex) => (
                                <article className="vehicle-financing-card" key={`${candidateIndex}-${option.id}-${optionIndex}`}>
                                  <div className="vehicle-source-head">
                                    <Field label="方案名称">
                                      <input value={option.name} onChange={(event) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { name: event.target.value })} />
                                    </Field>
                                    <button className="ghost-button small" type="button" onClick={() => duplicateFinancingOption(vehicleIndex, candidateIndex, optionIndex)}>
                                      <Copy size={14} /> 复制
                                    </button>
                                    <button className="ghost-button small danger-action" type="button" onClick={() => removeFinancingOption(vehicleIndex, candidateIndex, optionIndex)} disabled={normalizeVehicleFinancingOptions(candidate).length <= 1}>
                                      <Trash2 size={14} /> 删除
                                    </button>
                                  </div>
                                  <div className="form-grid compact-fields">
                                    <SwitchField label={option.enabled ? "纳入策略生成" : "暂不纳入策略"} checked={option.enabled} onChange={(checked) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { enabled: checked })} />
                                    <Field label="金融类型">
                                      <select
                                        value={option.financing_type}
                                        onChange={(event) => {
                                          const financingType = event.target.value as VehicleFinancingOptionData["financing_type"];
                                          const presetByType: Partial<VehicleFinancingOptionData> =
                                            financingType === "cash_only"
                                              ? {
                                                  financing_type: financingType,
                                                  total_months: 1,
                                                  interest_free_months: 0,
                                                  later_annual_rate: 0,
                                                  min_down_payment_ratio: 1,
                                                  max_down_payment_ratio: 1,
                                                  prepayment_allowed: false,
                                                  prepayment_allowed_after_month: 1,
                                                  prepayment_policy_note: "全款购车不形成车贷，也不存在提前还本。"
                                                }
                                              : financingType === "dealer_subsidy"
                                                ? {
                                                    financing_type: financingType,
                                                    total_months: option.total_months > 1 ? option.total_months : 60,
                                                    interest_free_months: option.interest_free_months > 0 ? option.interest_free_months : 24,
                                                    later_annual_rate: option.later_annual_rate > 0 ? option.later_annual_rate : 0.0199,
                                                    min_down_payment_ratio: option.min_down_payment_ratio < 1 ? option.min_down_payment_ratio : 0.1,
                                                    max_down_payment_ratio: option.max_down_payment_ratio > option.min_down_payment_ratio ? option.max_down_payment_ratio : 1,
                                                    prepayment_allowed: true,
                                                    prepayment_allowed_after_month: option.prepayment_allowed_after_month > 1 ? option.prepayment_allowed_after_month : 12,
                                                    prepayment_policy_note: option.prepayment_policy_note || "贴息期内提前还本可能影响补贴资格，具体按合同执行。"
                                                  }
                                                : {
                                                    financing_type: financingType,
                                                    total_months: option.total_months > 1 ? option.total_months : 60,
                                                    interest_free_months: 0,
                                                    later_annual_rate: option.later_annual_rate > 0 ? option.later_annual_rate : 0.039,
                                                    min_down_payment_ratio: option.min_down_payment_ratio < 1 ? option.min_down_payment_ratio : 0.1,
                                                    max_down_payment_ratio: option.max_down_payment_ratio > option.min_down_payment_ratio ? option.max_down_payment_ratio : 1,
                                                    prepayment_allowed: true,
                                                    prepayment_allowed_after_month: option.prepayment_allowed_after_month > 1 ? option.prepayment_allowed_after_month : 12,
                                                    prepayment_policy_note: option.prepayment_policy_note || "普通贷款提前还本规则以银行或经销商合同为准。"
                                                  };
                                          updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, presetByType);
                                        }}
                                      >
                                        <option value="dealer_subsidy">经销商贴息</option>
                                        <option value="standard">普通贷款</option>
                                        <option value="bank_loan">银行贷款</option>
                                        <option value="cash_only">仅全款</option>
                                      </select>
                                    </Field>
                                    <NumberField label="贷款总期数" value={option.total_months} min={1} max={120} step={1} onChange={(value) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { total_months: value })} />
                                    <NumberField label="贴息期数" value={option.interest_free_months} min={0} max={120} step={1} onChange={(value) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { interest_free_months: value })} />
                                    <NumberField label="合同年利率" value={option.later_annual_rate} min={0} max={0.5} step={0.0001} onChange={(value) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { later_annual_rate: value })} />
                                    <NumberField label="最低首付比例" value={option.min_down_payment_ratio} min={0} max={1} step={0.05} onChange={(value) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { min_down_payment_ratio: value })} />
                                    <NumberField label="最高首付比例" value={option.max_down_payment_ratio} min={0} max={1} step={0.05} onChange={(value) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { max_down_payment_ratio: value })} />
                                    <SwitchField label={option.prepayment_allowed ? "合同允许提前还本" : "合同不允许提前还本"} checked={option.prepayment_allowed} onChange={(checked) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { prepayment_allowed: checked })} />
                                    {option.prepayment_allowed ? (
                                      <NumberField label="最早提前还本期" value={option.prepayment_allowed_after_month} min={1} max={120} step={1} onChange={(value) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { prepayment_allowed_after_month: value })} />
                                    ) : null}
                                    <Field label="提前还本规则说明">
                                      <input value={option.prepayment_policy_note} onChange={(event) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { prepayment_policy_note: event.target.value })} />
                                    </Field>
                                    <Field label="金融方案说明">
                                      <input value={option.notes} onChange={(event) => updateFinancingOption(vehicleIndex, candidateIndex, optionIndex, { notes: event.target.value })} />
                                    </Field>
                                  </div>
                                </article>
                              ))}
                            </div>
                          </CollapsibleSettingGroup>

                          <CollapsibleSettingGroup title="策略偏好">
                            <div className="form-grid compact-fields">
                              <NumberField label="目标首付比例" value={candidate.down_payment_ratio ?? 0.3} min={0} max={1} step={0.05} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { down_payment_ratio: value, down_payment: Math.round((candidate.total_price ?? 0) * value) })} />
                              <NumberField label="目标首付金额" value={candidate.down_payment ?? 0} min={0} step={1000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { down_payment: value, down_payment_ratio: candidate.total_price > 0 ? Math.min(1, Math.max(0, value / candidate.total_price)) : 0 })} />
                              <SwitchField
                                label="手动设置提前还本参数"
                                checked={candidate.loan_prepayment_enabled ?? false}
                                onChange={(checked) => updateCandidate(vehicleIndex, candidateIndex, { loan_prepayment_enabled: checked })}
                              />
                              {(candidate.loan_prepayment_enabled ?? false) ? (
                                <>
                                  <NumberField label="希望起始还本期" value={candidate.loan_prepayment_start_month ?? 1} min={1} max={120} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { loan_prepayment_start_month: value })} />
                                  <NumberField label="分月额外还本金/月" value={candidate.loan_prepayment_monthly_amount ?? 0} min={0} step={500} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { loan_prepayment_monthly_amount: value })} />
                                  <NumberField label="一次性还本期数" value={candidate.loan_prepayment_lump_sum_month ?? 0} min={0} max={120} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { loan_prepayment_lump_sum_month: value })} />
                                  <NumberField label="一次性还本金额" value={candidate.loan_prepayment_lump_sum_amount ?? 0} min={0} step={1000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { loan_prepayment_lump_sum_amount: value })} />
                                </>
                              ) : null}
                            </div>
                          </CollapsibleSettingGroup>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">这个用车需求还没有车源。添加车源后，后端会按每个车源分别生成贷款策略。</div>
                )}
              </section>
            );
          })}
          {vehiclePlans.length === 0 ? (
            <div className="empty-state target-empty-state">
              <strong>默认不购车</strong>
              <span>当前只把无车通勤月成本计入现金流；添加用车需求后，可以继续添加多个候选车源并比较贷款策略。</span>
              <button className="primary-button" type="button" onClick={addVehicle}>
                <Plus size={16} /> 添加用车需求
              </button>
            </div>
          ) : null}
        </div>
        {carLoan ? (
          <div className="car-cost-breakdown">
            {vehiclePlans.length ? (
              <>
                <Metric label="月均现金养车" value={money(carLoan.monthly_cash_operating_cost)} />
                <Metric label="年保险" value={money(carLoan.monthly_insurance_cost * 12)} />
                <Metric label="电费/月" value={money(carLoan.monthly_energy_cost)} />
                <Metric label="年保养" value={money(carLoan.monthly_maintenance_cost * 12)} />
                <Metric label="停车/月" value={money(carLoan.monthly_parking_cost)} />
                <Metric label="含折旧总成本" value={money(carLoan.monthly_total_ownership_cost)} />
              </>
            ) : (
              <>
                <Metric label="无车通勤月成本" value={money(carPlan.no_car_monthly_commute_cost ?? 0)} />
                <Metric label="当前方案" value="不购车" />
              </>
            )}
          </div>
        ) : null}
        </section>

        <section className="strategy-main-panel car-policy-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<ShieldCheck size={18} />} title="政策与上牌" compact collapsible />
            <span>按当前用车需求统一配置指标、租牌和家庭新能源指标口径</span>
          </div>
          {activeVehiclePlan ? (
            <div className="member-list compact-list vehicle-plan-list">
              <section className="member-card vehicle-plan-card">
                <CollapsibleSettingGroup title="北京指标与租牌">
                  <div className="form-grid compact-fields">
                    <Field label="北京小客车指标">
                      <select
                        value={activeVehiclePlan.beijing_license_indicator_status ?? "unknown"}
                        onChange={(event) => updateVehiclePolicy(selectedVehicleIndex, { beijing_license_indicator_status: event.target.value as VehiclePlanData["beijing_license_indicator_status"] })}
                      >
                        <option value="unknown">未确认指标状态</option>
                        <option value="already_have">已取得指标</option>
                        <option value="family_new_energy_pending">家庭新能源指标等待中</option>
                        <option value="personal_new_energy_pending">个人新能源指标等待中</option>
                        <option value="ordinary_indicator_pending">普通小客车指标等待中</option>
                        <option value="not_eligible">暂不具备申请资格</option>
                      </select>
                    </Field>
                    <NumberField
                      label="预计指标等待月数"
                      value={activeVehiclePlan.beijing_indicator_expected_delay_months ?? 0}
                      min={0}
                      max={240}
                      step={1}
                      onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_indicator_expected_delay_months: value })}
                    />
                    <SwitchField
                      label={activeVehiclePlan.license_plate_rental_enabled ? "启用租牌过渡" : "不租牌"}
                      checked={activeVehiclePlan.license_plate_rental_enabled ?? false}
                      onChange={(checked) => updateVehiclePolicy(selectedVehicleIndex, { license_plate_rental_enabled: checked })}
                    />
                    {activeVehiclePlan.license_plate_rental_enabled ? (
                      <>
                        <NumberField
                          label="首期租牌费"
                          value={activeVehiclePlan.license_plate_rental_upfront_fee ?? 20000}
                          min={0}
                          step={1000}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { license_plate_rental_upfront_fee: value })}
                        />
                        <NumberField
                          label="首期租牌周期"
                          value={activeVehiclePlan.license_plate_rental_term_months ?? 36}
                          min={1}
                          max={120}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { license_plate_rental_term_months: value })}
                        />
                        <Field label="到期处理">
                          <select
                            value={activeVehiclePlan.license_plate_rental_after_term_mode ?? "renew_until_own_indicator"}
                            onChange={(event) => updateVehiclePolicy(selectedVehicleIndex, { license_plate_rental_after_term_mode: event.target.value as VehiclePlanData["license_plate_rental_after_term_mode"] })}
                          >
                            <option value="renew_until_own_indicator">继续租到取得自有指标</option>
                            <option value="switch_to_own_indicator">到期改用自有指标</option>
                          </select>
                        </Field>
                        {activeVehiclePlan.license_plate_rental_after_term_mode !== "switch_to_own_indicator" ? (
                          <>
                            <NumberField
                              label="续租费用"
                              value={activeVehiclePlan.license_plate_rental_renewal_fee ?? 20000}
                              min={0}
                              step={1000}
                              onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { license_plate_rental_renewal_fee: value })}
                            />
                            <NumberField
                              label="续租周期"
                              value={activeVehiclePlan.license_plate_rental_renewal_term_months ?? 36}
                              min={1}
                              max={120}
                              step={1}
                              onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { license_plate_rental_renewal_term_months: value })}
                            />
                          </>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                  <p className="field-hint">
                    指标和租牌是用车需求级政策口径，会统一应用到该需求下的所有候选车源；车型自身的能源类型、购置税目录资格和车船税覆盖值仍在每个候选车源的“车辆属性”里配置。
                  </p>
                </CollapsibleSettingGroup>

                <CollapsibleSettingGroup title="家庭新能源指标算分">
                  <div className="form-grid compact-fields">
                    <SwitchField
                      label={activeVehiclePlan.beijing_family_indicator_score_enabled ? "估算家庭新能源积分" : "不估算家庭积分"}
                      checked={activeVehiclePlan.beijing_family_indicator_score_enabled ?? false}
                      onChange={(checked) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_score_enabled: checked })}
                    />
                    {activeVehiclePlan.beijing_family_indicator_score_enabled ? (
                      <>
                        <Field label="家庭指标开始月">
                          <input
                            type="month"
                            value={activeVehiclePlan.beijing_family_indicator_application_start_month ?? ""}
                            onChange={(event) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_application_start_month: event.target.value })}
                          />
                        </Field>
                        <NumberField
                          label="家庭代际数"
                          value={activeVehiclePlan.beijing_family_indicator_generations ?? 1}
                          min={1}
                          max={3}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_generations: value })}
                        />
                        <SwitchField
                          label={activeVehiclePlan.beijing_family_indicator_has_spouse ? "含配偶申请人" : "不含配偶"}
                          checked={activeVehiclePlan.beijing_family_indicator_has_spouse ?? true}
                          onChange={(checked) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_has_spouse: checked })}
                        />
                        <NumberField
                          label="主申请人积分"
                          value={activeVehiclePlan.beijing_family_indicator_main_points ?? 2}
                          min={0}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_main_points: value })}
                        />
                        {activeVehiclePlan.beijing_family_indicator_has_spouse ? (
                          <NumberField
                            label="配偶积分"
                            value={activeVehiclePlan.beijing_family_indicator_spouse_points ?? 1}
                            min={0}
                            step={1}
                            onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_spouse_points: value })}
                          />
                        ) : null}
                        <NumberField
                          label="其他申请人数"
                          value={activeVehiclePlan.beijing_family_indicator_other_applicant_count ?? 0}
                          min={0}
                          max={20}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_other_applicant_count: value })}
                        />
                        <NumberField
                          label="其他申请人积分合计"
                          value={activeVehiclePlan.beijing_family_indicator_other_points_total ?? 0}
                          min={0}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_other_points_total: value })}
                        />
                        <NumberField
                          label="共同申请年数"
                          value={activeVehiclePlan.beijing_family_indicator_application_years ?? 0}
                          min={0}
                          max={50}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_application_years: value })}
                        />
                        <NumberField
                          label="最近入围分"
                          value={activeVehiclePlan.beijing_family_indicator_current_cutoff_score ?? 36}
                          min={0}
                          step={0.01}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_current_cutoff_score: value })}
                        />
                        <NumberField
                          label="入围分年变化"
                          value={activeVehiclePlan.beijing_family_indicator_cutoff_score_annual_change ?? 0}
                          min={-20}
                          max={20}
                          step={0.1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_cutoff_score_annual_change: value })}
                        />
                        <NumberField
                          label="公告年份"
                          value={activeVehiclePlan.beijing_family_indicator_last_config_year ?? 2026}
                          min={2020}
                          max={2100}
                          step={1}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_last_config_year: value })}
                        />
                        <NumberField
                          label="家庭新能源指标量"
                          value={activeVehiclePlan.beijing_family_indicator_annual_quota ?? 119200}
                          min={0}
                          step={100}
                          onChange={(value) => updateVehiclePolicy(selectedVehicleIndex, { beijing_family_indicator_annual_quota: value })}
                        />
                      </>
                    ) : null}
                  </div>
                  {activeVehiclePlan.beijing_family_indicator_score_enabled ? (
                    <div className="indicator-applicant-panel">
                      <div className="vehicle-source-toolbar">
                        <strong>家庭指标申请人明细</strong>
                        <div className="template-chip-row">
                          <button className="ghost-button small" type="button" onClick={() => addVehicleIndicatorApplicant(selectedVehicleIndex, { relationship: "main", name: "主申请人", has_valid_driver_license: true })}>
                            <Plus size={14} /> 主申请人
                          </button>
                          <button className="ghost-button small" type="button" onClick={() => addVehicleIndicatorApplicant(selectedVehicleIndex, { relationship: "spouse", name: "配偶", generation: "self_generation" })}>
                            <Plus size={14} /> 配偶
                          </button>
                          <button className="ghost-button small" type="button" onClick={() => addVehicleIndicatorApplicant(selectedVehicleIndex, { relationship: "parent", name: "老人", generation: "parent_generation", eligibility_type: "beijing_residence_permit_social_tax", only_for_indicator_scoring: true })}>
                            <Plus size={14} /> 老人算分
                          </button>
                        </div>
                      </div>
                      <p className="field-hint">
                        这里的申请人只用于北京家庭指标算分，不会自动进入家庭现金流。主申请人、配偶权重按 2 计，其他家庭申请人权重按 1 计，再乘家庭代际数；个人摇号阶梯或新能源轮候历史会进入基础分。
                      </p>
                      <div className="indicator-applicant-grid">
                        {normalizeVehicleIndicatorApplicants(activeVehiclePlan.beijing_family_indicator_applicants).map((applicant, applicantIndex) => (
                          <article className="indicator-applicant-card" key={`vehicle-indicator-${selectedVehicleIndex}-${applicantIndex}`}>
                            <div className="vehicle-source-head">
                              <Field label="申请人名称">
                                <input value={applicant.name} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { name: event.target.value })} />
                              </Field>
                              <SwitchField
                                label={applicant.enabled ? "参与算分" : "不参与算分"}
                                checked={applicant.enabled}
                                onChange={(checked) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { enabled: checked })}
                              />
                              <button className="ghost-button small danger-action" type="button" onClick={() => removeVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex)}>
                                <Trash2 size={14} /> 删除
                              </button>
                            </div>
                            <div className="form-grid compact-fields">
                              <Field label="家庭关系">
                                <select value={applicant.relationship} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { relationship: event.target.value as VehicleIndicatorApplicantData["relationship"] })}>
                                  <option value="main">主申请人</option>
                                  <option value="spouse">配偶</option>
                                  <option value="child">子女</option>
                                  <option value="parent">父母</option>
                                  <option value="parent_in_law">配偶父母</option>
                                  <option value="other">其他</option>
                                </select>
                              </Field>
                              <Field label="所属代际">
                                <select value={applicant.generation} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { generation: event.target.value as VehicleIndicatorApplicantData["generation"] })}>
                                  <option value="self_generation">本人/配偶一代</option>
                                  <option value="child_generation">子女一代</option>
                                  <option value="parent_generation">父母一代</option>
                                </select>
                              </Field>
                              <Field label="资格口径">
                                <select value={applicant.eligibility_type} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { eligibility_type: event.target.value as VehicleIndicatorApplicantData["eligibility_type"] })}>
                                  <option value="unknown">待确认</option>
                                  <option value="beijing_household">北京户籍</option>
                                  <option value="beijing_work_residence_permit">北京工作居住证</option>
                                  <option value="beijing_residence_permit_social_tax">北京居住证+连续社保/个税</option>
                                  <option value="active_military_or_police">驻京现役军人/武警</option>
                                  <option value="hongkong_macao_taiwan_foreign">港澳台/外籍按规定居留</option>
                                </select>
                              </Field>
                              <Field label="加入家庭指标月">
                                <input type="month" value={applicant.family_application_start_month} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { family_application_start_month: event.target.value })} />
                              </Field>
                              <Field label="个人指标历史">
                                <select value={applicant.personal_indicator_history_type} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { personal_indicator_history_type: event.target.value as VehicleIndicatorApplicantData["personal_indicator_history_type"] })}>
                                  <option value="none">无个人历史</option>
                                  <option value="ordinary_lottery">普通指标摇号阶梯</option>
                                  <option value="new_energy_queue">新能源个人轮候</option>
                                  <option value="both">普通阶梯+新能源轮候</option>
                                </select>
                              </Field>
                              <NumberField label="普通摇号阶梯数" value={applicant.ordinary_lottery_steps} min={0} max={200} step={1} onChange={(value) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { ordinary_lottery_steps: value })} />
                              <Field label="新能源轮候开始月">
                                <input type="month" value={applicant.new_energy_queue_start_month} onChange={(event) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { new_energy_queue_start_month: event.target.value })} />
                              </Field>
                              <NumberField label="个人历史分覆盖" value={applicant.personal_history_points_override ?? 0} min={0} step={1} onChange={(value) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { personal_history_points_override: value > 0 ? value : null })} />
                              <SwitchField label="有驾驶证" checked={applicant.has_valid_driver_license} onChange={(checked) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { has_valid_driver_license: checked })} />
                              <SwitchField label="名下无京牌车" checked={applicant.has_no_beijing_vehicle} onChange={(checked) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { has_no_beijing_vehicle: checked })} />
                              <SwitchField label="仅参与指标算分" checked={applicant.only_for_indicator_scoring} onChange={(checked) => updateVehicleIndicatorApplicant(selectedVehicleIndex, applicantIndex, { only_for_indicator_scoring: checked })} />
                            </div>
                          </article>
                        ))}
                        {normalizeVehicleIndicatorApplicants(activeVehiclePlan.beijing_family_indicator_applicants).length === 0 ? (
                          <div className="empty-state compact-empty-state">还没有申请人明细；不添加时后端会使用上方简化积分参数估算。</div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </CollapsibleSettingGroup>
              </section>
            </div>
          ) : (
            <div className="empty-state">添加用车需求后，可以统一配置北京指标、租牌和家庭新能源指标算分。</div>
          )}
        </section>
      </div>

      <section className="result-panel car-comparison-result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Car size={18} />} title="车源对比" compact />
          <span>按每个候选车源当前选中的策略比较</span>
        </div>
        {carStrategies.length ? (
          <div className="car-source-decision-stack">
            <div className="car-strategy-analysis-strip">
              {carStrategyAnalysisItems.map((item) => (
                <span key={item.label}>
                  <small>{item.label}</small>
                  <strong>{item.value}</strong>
                  <em>{item.detail}</em>
                </span>
              ))}
            </div>
            <div className="car-strategy-comparison-table">
              <div className="car-strategy-comparison-row car-strategy-comparison-head">
                <span>车源与策略</span>
                <span>可买时间</span>
                <span>首付/贷款</span>
                <span>月供</span>
                <span>家庭承担利息</span>
                <span>买后现金</span>
                <span>买后月结余</span>
                <span>幸福指数</span>
                <span>判断</span>
              </div>
              {carStrategyComparisonRows.map((strategy, strategyIndex) => (
                <button
                  className={activeVehicleStrategies.has(carStrategyIdentity(strategy)) ? "car-strategy-comparison-row active" : "car-strategy-comparison-row"}
                  key={`car-decision-row-${carStrategyIdentity(strategy)}-${strategyIndex}`}
                  type="button"
                  onClick={() => selectStrategy(strategy)}
                >
                  <span>
                    <strong>{displayStrategyName(strategy)}</strong>
                    <small>{strategyDecisionText(strategy)}</small>
                  </span>
                  <span data-label="可买时间">{strategy.years_to_buy === null ? "暂不可达" : `${strategy.years_to_buy} 年`}</span>
                  <span data-label="首付 / 贷款">{money(strategy.down_payment)} / {money(strategy.loan_principal)}</span>
                  <span data-label="月供">{money(strategy.expected_monthly_payment_after_purchase)}</span>
                  <span data-label="家庭承担利息">{money(strategy.total_interest)}</span>
                  <span data-label="买后现金">{money(strategy.cash_after_purchase)}</span>
                  <span data-label="买后月结余">{money(strategy.monthly_cash_flow_after_car)}</span>
                  <span data-label="幸福指数">{strategy.happiness_score.toFixed(1)} / 10</span>
                  <span className={`decision-pill ${strategyDecisionTone(strategy)}`} data-label="判断">{strategyDecisionLabel(strategy)}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="empty-state">
            {calculationPending
              ? "正在计算车源对比"
              : vehiclePlans.length
                ? "等待生成车源对比"
                : "当前为不购车模式，添加用车需求和候选车源后再进行车源对比。"}
          </div>
        )}
      </section>

      <section className="result-panel car-strategy-result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Gauge size={18} />} title="候选策略" compact />
          <span>策略由后端按当前用车需求和候选车源生成；切换策略只查看已生成结果。</span>
        </div>
        {carStrategies.length ? (
          <div className="car-source-decision-stack">
            {vehiclePlans.map((vehicle, vehicleIndex) => {
              const strategies = strategiesByVehicle[vehicleIndex] ?? [];
              const grouped = new Map<string, CarPlanAnalysis[]>();
              strategies.forEach((strategy) => {
                const key = `${strategy.vehicle_candidate_index ?? "manual"}-${strategy.vehicle_candidate_name || strategy.vehicle_name}`;
                grouped.set(key, [...(grouped.get(key) ?? []), strategy]);
              });
              return (
                <section className="car-source-decision" key={`vehicle-strategy-${vehicleIndex}`}>
                  <div className="decision-section-head">
                    <strong>{vehicle.name || `用车需求 ${vehicleIndex + 1}`}</strong>
                    <span>{strategies.length} 个策略</span>
                  </div>
                  {[...grouped.entries()].map(([key, sourceStrategies]) => {
                    const sample = sourceStrategies[0];
                    const cheapest = sourceStrategies.reduce((best, item) => item.monthly_total_ownership_cost < best.monthly_total_ownership_cost ? item : best, sample);
                    const fastest = sourceStrategies.reduce((best, item) => (item.months_to_buy ?? 9999) < (best.months_to_buy ?? 9999) ? item : best, sample);
                    return (
                      <article className="car-source-strategy-group" key={key}>
                        <div className="source-comparison-row">
                          <div>
                            <strong>{sample.vehicle_candidate_name || sample.vehicle_name}</strong>
                            <small>车价 {money(sample.total_price)}，最快 {fastest.years_to_buy === null ? "暂不可达" : `${fastest.years_to_buy} 年`}，低成本策略 {displayStrategyName(cheapest)}</small>
                          </div>
                          <div className="source-comparison-metrics">
                            <Metric label="最低首付" value={money(Math.min(...sourceStrategies.map((item) => item.down_payment)))} />
                            <Metric label="最低月供" value={money(Math.min(...sourceStrategies.map((item) => item.expected_monthly_payment_after_purchase)))} />
                            <Metric label="最高幸福度" value={`${Math.max(...sourceStrategies.map((item) => item.happiness_score)).toFixed(1)} / 10`} />
                          </div>
                        </div>
                        <div className="strategy-panel-head compact-section-head">
                          <PanelTitle icon={<Gauge size={18} />} title="候选策略明细" compact />
                          <span>{sample.vehicle_candidate_name || sample.vehicle_name}</span>
                        </div>
                        <div className="strategy-grid car-source-strategy-grid">
                          {sourceStrategies.map((strategy, strategyIndex) => (
                            <article
                              className={activeVehicleStrategies.has(carStrategyIdentity(strategy)) ? "strategy-card car-strategy-card active" : "strategy-card car-strategy-card"}
                              key={`${carStrategyIdentity(strategy)}-${strategyIndex}`}
                            >
                              <div className="strategy-card-head">
                                <strong>{displayStrategyName(strategy)}</strong>
                                <StrategyStatePill
                                  active={activeVehicleStrategies.has(carStrategyIdentity(strategy))}
                                  label={strategy.years_to_buy === null ? "暂不可达" : `${strategy.years_to_buy} 年`}
                                />
                              </div>
                              <p>{strategyDecisionText(strategy)}</p>
                              <div className="strategy-metrics">
                                <Metric label="首付" value={money(strategy.down_payment)} />
                                <Metric label="金融方案" value={strategy.financing_option_name || "当前方案"} />
                                <Metric label="贷款本金" value={money(strategy.loan_principal)} />
                                <Metric label="贴息/全期期数" value={`${strategy.interest_free_months} / ${strategy.total_months} 期`} />
                                <Metric label="合同年利率" value={percent(strategy.later_annual_rate)} />
                                <Metric label="合同月供" value={money(strategy.contract_monthly_payment)} />
                                <Metric label="贴息后首月净供" value={money(strategy.first_phase_monthly_payment)} />
                                <Metric label="贴息总额" value={money(strategy.total_interest_subsidy)} />
                                <Metric label="评估现金月供" value={money(strategy.expected_monthly_payment_after_purchase)} />
                                {strategy.prepayment_enabled ? (
                                  <>
                                    <Metric label="额外还本金/月" value={money(strategy.prepayment_monthly_amount)} />
                                    <Metric label="一次性还本金" value={money(strategy.prepayment_lump_sum_amount)} />
                                    <Metric label="合同可提前还本" value={`第 ${strategy.prepayment_allowed_after_month} 期起`} />
                                    <Metric label="预计结清" value={`${strategy.actual_payoff_months} 个月`} />
                                    <Metric label="节省利息" value={money(strategy.interest_saved_by_prepayment)} />
                                  </>
                                ) : !strategy.prepayment_allowed ? (
                                  <Metric label="提前还本规则" value="合同不允许" />
                                ) : null}
                                <Metric label="月现金养车" value={money(strategy.monthly_cash_operating_cost)} />
                                <Metric label="含折旧总成本" value={money(strategy.monthly_total_ownership_cost)} />
                                <Metric label="买后现金" value={money(strategy.cash_after_purchase)} tone={strategy.cash_after_purchase >= 0 ? "good" : "warn"} />
                                <Metric label="买后月结余" value={money(strategy.monthly_cash_flow_after_car)} tone={strategy.monthly_cash_flow_after_car >= 0 ? "good" : "bad"} />
                                <Metric label="家庭承担利息" value={money(strategy.total_interest)} />
                                <Metric label="幸福指数" value={`${strategy.happiness_score.toFixed(1)} / 10`} tone={strategy.happiness_score >= 7 ? "good" : strategy.happiness_score >= 5 ? "warn" : "bad"} />
                              </div>
                              <AdoptStrategyButton
                                active={activeVehicleStrategies.has(carStrategyIdentity(strategy))}
                                onClick={() => selectStrategy(strategy)}
                                activeLabel="当前查看"
                                inactiveLabel="查看策略"
                              />
                            </article>
                          ))}
                        </div>
                      </article>
                    );
                  })}
                </section>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">
            {calculationPending
              ? "正在根据最新用车需求重新生成车源对比与贷款策略。"
              : vehiclePlans.length
                ? "当前用车需求还没有可用车源策略；请添加车源或检查车辆价格、购车时间和贷款参数。"
                : "当前为不购车模式：每月无车通勤成本会进入现金流；添加用车需求和车源后，会自动生成车源对比与贷款策略。"}
          </div>
        )}
      </section>

      {primarySelectedStrategy ? (
        <section className="result-panel selected-car-strategy-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<ClipboardCheck size={18} />} title="当前购车策略说明" compact />
            <span>{displayStrategyName(primarySelectedStrategy)}</span>
          </div>
          <div className="selected-car-narrative-grid">
            {householdStrategy ? (
              <article className="wide">
                <span>家庭总策略约束</span>
                <strong>车辆方案必须服从全家庭的长期现金安全与重大目标顺序。</strong>
                <p>{householdStrategy}</p>
              </article>
            ) : null}
            <article className="wide">
              <span>执行路径</span>
              <strong>{carStrategyPurchaseText(primarySelectedStrategy)}</strong>
              <p>{carStrategyReasonText(primarySelectedStrategy)}</p>
            </article>
            <article>
              <span>金融方案依据</span>
              <strong>{primarySelectedStrategy.financing_option_name || financingTypeLabel(primarySelectedStrategy.financing_type)}</strong>
              <p>{carStrategyFinancingText(primarySelectedStrategy)}</p>
            </article>
            <article>
              <span>还款动作</span>
              <strong>{vehiclePrepaymentModeLabel(primarySelectedStrategy)}</strong>
              <p>{carStrategyPrepaymentText(primarySelectedStrategy)}</p>
            </article>
            <article className="wide">
              <span>对买房和家庭现金流的影响</span>
              <strong>
                买后现金 {money(primarySelectedStrategy.cash_after_purchase)}，
                月结余 {money(primarySelectedStrategy.monthly_cash_flow_after_car)}
              </strong>
              <p>
                这辆车的首付、贷款、保险保养、停车和电费都会进入可视化现金流；如果购房窗口紧张，
                优先比较「低首付保现金」和「延后买车」对买房时间的影响。
              </p>
            </article>
          </div>
          <div className="selected-car-risk-list">
            {carStrategyRiskItems(primarySelectedStrategy).map((item) => (
              <div key={item}>
                <CheckCircle2 size={16} />
                <span>{item}</span>
              </div>
            ))}
          </div>
          <div className="selected-car-strategy-grid">
            <article>
              <span>购车资金安排</span>
              <strong>{money(primarySelectedStrategy.down_payment)} 首付，{money(primarySelectedStrategy.loan_principal)} 车贷</strong>
              <p>
                后端按现金安全垫、购房窗口和月供压力选择 {percent(primarySelectedStrategy.down_payment_ratio)} 首付；
                买后现金预计 {money(primarySelectedStrategy.cash_after_purchase)}，月结余预计 {money(primarySelectedStrategy.monthly_cash_flow_after_car)}。
              </p>
            </article>
            <article>
              <span>车贷结构</span>
              <strong>{primarySelectedStrategy.total_months} 期，贴息 {primarySelectedStrategy.interest_free_months} 期</strong>
              <p>
                合同月供 {money(primarySelectedStrategy.contract_monthly_payment)}，
                贴息后首月家庭实际承担 {money(primarySelectedStrategy.first_phase_monthly_payment)}，
                全期家庭承担利息 {money(primarySelectedStrategy.total_interest)}。
              </p>
            </article>
            <article>
              <span>提前还本策略</span>
              <strong>{vehiclePrepaymentModeLabel(primarySelectedStrategy)}</strong>
              <p>
                {primarySelectedStrategy.prepayment_enabled
                  ? `${primarySelectedStrategy.prepayment_explanation} 分月额外还本 ${money(primarySelectedStrategy.prepayment_monthly_amount)}，一次性还本 ${money(primarySelectedStrategy.prepayment_lump_sum_amount)}，预计 ${primarySelectedStrategy.actual_payoff_months} 个月结清。`
                  : primarySelectedStrategy.prepayment_explanation || "车贷贴息后的实际资金成本不高，或现金安全垫更应该留给购房与家庭应急，暂不安排提前还本。"}
              </p>
            </article>
            <article>
              <span>家庭影响</span>
              <strong>幸福指数 {primarySelectedStrategy.happiness_score.toFixed(1)} / 10</strong>
              <p>
                该分数综合车辆幸福度、买后现金安全、月现金流压力、债务负担、养车成本和等待时间；若购房窗口紧张，低首付保现金或延后购车通常会更稳。
              </p>
            </article>
          </div>
        </section>
      ) : null}
    </PlannerPageShell>
  );
}

function RulePage({
  activeRulePack,
  ruleNumber,
  updateRulePack,
  updateRuleParam,
  sourceUrl,
  setSourceUrl,
  sourcePreview,
  previewSource,
  saving
}: {
  activeRulePack: RulePackData;
  ruleNumber: (key: string, fallback: number) => number;
  updateRulePack: <K extends keyof RulePackData>(key: K, value: RulePackData[K]) => void;
  updateRuleParam: (key: string, value: number | string | boolean) => void;
  sourceUrl: string;
  setSourceUrl: (value: string) => void;
  sourcePreview: SourceDocumentRecord | null;
  previewSource: () => void;
  saving: boolean;
}) {
  type RuleParamConfig =
    | {
        kind: "number";
        key: string;
        label: string;
        fallback: number;
        min?: number;
        max?: number;
        step?: number;
        description: string;
      }
    | {
        kind: "switch";
        key: string;
        label: string;
        description: string;
        trueValue?: number | boolean;
        falseValue?: number | boolean;
      }
    | {
        kind: "select";
        key: string;
        label: string;
        description: string;
        fallback: string;
        options: Array<{ value: string; label: string }>;
      }
    | {
        kind: "text";
        key: string;
        label: string;
        description: string;
        fallback: string;
      };
  const ruleGroups: Array<{ title: string; description: string; params: RuleParamConfig[] }> = [
    {
      title: "购房资格与首付",
      description: "这些属于购房政策口径，不应放到房源或家庭手动参数里。系统会按首套/二套、商贷/公积金取更严格的首付要求。",
      params: [
        { kind: "number", key: "max_home_count", label: "家庭可购住房套数", fallback: 2, min: 0, max: 10, step: 1, description: "用于判断当前家庭住房套数是否还允许继续购房。" },
        { kind: "number", key: "minimum_down_payment_ratio", label: "兜底最低首付比例", fallback: 0.3, min: 0, max: 1, step: 0.01, description: "当细分政策缺失时的保守兜底，不应替代首套/二套具体规则。" },
        { kind: "number", key: "first_home_commercial_min_down_payment_ratio", label: "首套商贷最低首付", fallback: 0.15, min: 0, max: 1, step: 0.01, description: "首套住房使用商业贷款时的最低首付比例。" },
        { kind: "number", key: "second_home_commercial_min_down_payment_ratio", label: "二套商贷最低首付", fallback: 0.2, min: 0, max: 1, step: 0.01, description: "二套住房使用商业贷款时的最低首付比例。" },
        { kind: "number", key: "first_home_provident_min_down_payment_ratio", label: "首套公积金最低首付", fallback: 0.2, min: 0, max: 1, step: 0.01, description: "首套住房使用公积金贷款时的最低首付比例。" },
        { kind: "number", key: "second_home_provident_min_down_payment_ratio", label: "二套公积金最低首付", fallback: 0.25, min: 0, max: 1, step: 0.01, description: "二套住房使用公积金贷款时的最低首付比例。" }
      ]
    },
    {
      title: "公积金贷款额度与年限",
      description: "这些参数应由城市公积金政策包控制，前端只展示和校验；购房策略不应手写固定额度。",
      params: [
        { kind: "number", key: "provident_loan_amount_per_deposit_year", label: "每缴存年可贷额度", fallback: 150000, min: 0, step: 10000, description: "北京现行口径下每缴存一年增加的可贷额度；会随购房月份自动变化。" },
        { kind: "number", key: "provident_first_home_loan_cap", label: "首套公积金基础上限", fallback: 1200000, min: 0, step: 10000, description: "首套房未计入绿色建筑、装配式等上浮前的基础最高额度。" },
        { kind: "number", key: "provident_second_home_loan_cap", label: "二套公积金基础上限", fallback: 1000000, min: 0, step: 10000, description: "二套房公积金贷款基础最高额度。" },
        { kind: "number", key: "provident_first_home_rate_1_to_5_years", label: "首套公积金利率 1-5 年", fallback: 0.021, min: 0, max: 0.2, step: 0.0005, description: "首套房公积金贷款期限不超过 5 年时使用的年利率。" },
        { kind: "number", key: "provident_first_home_rate_6_to_30_years", label: "首套公积金利率 6-30 年", fallback: 0.026, min: 0, max: 0.2, step: 0.0005, description: "首套房公积金贷款期限超过 5 年时使用的年利率。" },
        { kind: "number", key: "provident_second_home_rate_1_to_5_years", label: "二套公积金利率 1-5 年", fallback: 0.02325, min: 0, max: 0.2, step: 0.0005, description: "二套房公积金贷款期限不超过 5 年时使用的年利率。" },
        { kind: "number", key: "provident_second_home_rate_6_to_30_years", label: "二套公积金利率 6-30 年", fallback: 0.03075, min: 0, max: 0.2, step: 0.0005, description: "二套房公积金贷款期限超过 5 年时使用的年利率。" },
        { kind: "number", key: "provident_repayment_income_ratio", label: "还款能力收入占比", fallback: 0.6, min: 0, max: 1, step: 0.01, description: "用于计算公积金贷款还款能力上限，避免月供挤占基本生活。" },
        { kind: "number", key: "provident_basic_living_cost_per_person", label: "基本生活费/人", fallback: 1778, min: 0, step: 50, description: "公积金还款能力测算中为家庭成员保留的基本生活费。" },
        { kind: "number", key: "provident_max_loan_years", label: "最长贷款年限", fallback: 30, min: 1, max: 30, step: 1, description: "公积金贷款最长年限；实际年限还受借款人年龄和房龄影响。" },
        { kind: "number", key: "provident_max_borrower_age", label: "借款人年龄上限", fallback: 68, min: 18, max: 80, step: 1, description: "按借款申请人年龄约束贷款年限。" },
        { kind: "number", key: "provident_brick_mixed_total_life_years", label: "砖混房屋总年限", fallback: 50, min: 1, max: 100, step: 1, description: "用于二手房房龄影响贷款年限的估算。" },
        { kind: "number", key: "provident_steel_concrete_total_life_years", label: "钢混房屋总年限", fallback: 60, min: 1, max: 100, step: 1, description: "用于钢混结构二手房贷款年限测算。" }
      ]
    },
    {
      title: "新房性质与公积金上浮",
      description: "房源是否绿色建筑、装配式或超低能耗由候选房源填写；这里配置政策给出的上浮额度和封顶。",
      params: [
        { kind: "number", key: "provident_green_two_star_bonus", label: "二星绿色建筑上浮", fallback: 200000, min: 0, step: 10000, description: "符合二星绿色建筑条件时的公积金贷款额度上浮。" },
        { kind: "number", key: "provident_green_three_star_bonus", label: "三星绿色建筑上浮", fallback: 300000, min: 0, step: 10000, description: "符合三星绿色建筑条件时的公积金贷款额度上浮。" },
        { kind: "number", key: "provident_prefab_a_bonus", label: "装配式 A 上浮", fallback: 100000, min: 0, step: 10000, description: "装配式建筑 A 等级对应上浮。" },
        { kind: "number", key: "provident_prefab_aa_bonus", label: "装配式 AA 上浮", fallback: 200000, min: 0, step: 10000, description: "装配式建筑 AA 等级对应上浮。" },
        { kind: "number", key: "provident_prefab_aaa_bonus", label: "装配式 AAA 上浮", fallback: 300000, min: 0, step: 10000, description: "装配式建筑 AAA 等级对应上浮。" },
        { kind: "number", key: "provident_ultra_low_energy_bonus", label: "超低能耗建筑上浮", fallback: 400000, min: 0, step: 10000, description: "超低能耗建筑对应上浮。" },
        { kind: "number", key: "provident_policy_bonus_cap", label: "上浮封顶", fallback: 400000, min: 0, step: 10000, description: "多项上浮同时满足时，系统按可叠加项目求和，但最终不超过该封顶额。" }
      ]
    },
    {
      title: "公积金提取与冲还贷",
      description: "公积金账户性质特殊，不能随意计入自由现金。这里控制交易前首付抵扣、交易后提取到账和购后冲还贷口径。",
      params: [
        { kind: "switch", key: "provident_upfront_purchase_extract_ratio_new_home", label: "符合条件新房交易前可提", trueValue: 1, falseValue: 0, description: "开启后，新房可按规则把本人公积金余额用于首付抵扣。" },
        { kind: "switch", key: "provident_upfront_purchase_extract_ratio_second_hand", label: "二手房交易前可提", trueValue: 1, falseValue: 0, description: "默认关闭；二手房通常更保守，避免把审核后到账资金误认为首付现金。" },
        { kind: "number", key: "provident_post_transaction_extract_ratio", label: "交易后提取到账比例", fallback: 1, min: 0, max: 1, step: 0.05, description: "购房完成后审核通过，公积金余额可回流银行卡的估算比例。" },
        { kind: "switch", key: "provident_post_purchase_cashflow_enabled", label: "购后公积金计入现金改善", description: "默认关闭；购后缴存仍进入公积金账户，不作为自由现金收入。" },
        { kind: "select", key: "provident_account_management_center", label: "默认公积金中心兜底", fallback: "beijing_municipal", description: "仅在收入阶段未设置公积金中心口径时兜底使用。真实收入阶段请优先在“成员工资与收入阶段”里分别设置市管或国管。", options: [{ value: "beijing_municipal", label: "北京市管" }, { value: "national", label: "中央国家机关/国管" }] },
        { kind: "select", key: "provident_post_purchase_withdrawal_mode", label: "手动购后处理模式", fallback: "monthly_repayment_withdrawal", description: "只在策略模式设为手动时使用。按月抵月供降低每月银行卡还款压力；半年度冲本金主要减少本金和期限。", options: [{ value: "monthly_repayment_withdrawal", label: "按月约定提取抵月供" }, { value: "semiannual_principal_offset", label: "半年度冲本金缩期" }, { value: "purchase_agreed", label: "普通购房约定提取" }] },
        { kind: "switch", key: "provident_municipal_monthly_repayment_withdrawal_supported", label: "市管支持按月抵月供", description: "北京市管公积金贷款可办理约定提取，按月提取偿还公积金贷款月供，不足部分由还款卡补扣。" },
        { kind: "switch", key: "provident_municipal_semiannual_principal_offset_supported", label: "市管支持半年度冲本金", description: "半年度冲还贷与约定提取互斥，系统按 1 月/7 月集中冲抵本金建模。" },
        { kind: "switch", key: "provident_national_monthly_direct_offset_supported", label: "国管支持按月直冲", description: "国管公积金按月冲还贷时，按主借款人账户、配偶账户、还款账户顺序扣划。" },
        { kind: "number", key: "provident_balance_annual_interest_rate", label: "公积金账户年利率", fallback: 0.015, min: 0, max: 0.1, step: 0.0005, description: "公积金账户余额留存时的年化利息估算。" }
      ]
    },
    {
      title: "交易税费与市场费用",
      description: "契税属于政策税费，按家庭套数和房屋面积自动测算；中介费属于市场费用假设，可作为默认值供房源目标覆盖。",
      params: [
        { kind: "number", key: "deed_tax_standard_area_sqm", label: "契税普通面积阈值", fallback: 140, min: 0, max: 1000, step: 1, description: "用于区分契税标准面积和大面积住房的面积阈值。" },
        { kind: "number", key: "deed_tax_first_home_standard_rate", label: "首套标准面积契税", fallback: 0.01, min: 0, max: 0.2, step: 0.001, description: "首套且面积不超过阈值时使用的契税比例。" },
        { kind: "number", key: "deed_tax_first_home_large_rate", label: "首套大面积契税", fallback: 0.015, min: 0, max: 0.2, step: 0.001, description: "首套且面积超过阈值时使用的契税比例。" },
        { kind: "number", key: "deed_tax_second_home_standard_rate", label: "二套标准面积契税", fallback: 0.01, min: 0, max: 0.2, step: 0.001, description: "二套且面积不超过阈值时使用的契税比例。" },
        { kind: "number", key: "deed_tax_second_home_large_rate", label: "二套大面积契税", fallback: 0.02, min: 0, max: 0.2, step: 0.001, description: "二套且面积超过阈值时使用的契税比例。" },
        { kind: "number", key: "default_broker_fee_rate", label: "默认中介费假设", fallback: 0.022, min: 0, max: 0.2, step: 0.001, description: "新建房源目标时可参考的市场交易费用假设；具体房源仍可手动覆盖。" },
        { kind: "number", key: "seller_tax_pass_through_default_rate", label: "卖方税费转嫁默认", fallback: 0, min: 0, max: 0.2, step: 0.001, description: "卖方个税、增值税等是否转嫁给买方属于成交口径假设，不等同于买方契税政策。" }
      ]
    },
    {
      title: "车辆税费与北京小客车指标",
      description: "国家新能源购置税、北京小客车指标和车船税是三套不同口径。纯电、插混、增程、燃油车在购置税、上牌指标、限行和车船税上的规则不能混用。",
      params: [
        { kind: "number", key: "vehicle_purchase_tax_rate", label: "车辆购置税税率", fallback: 0.1, min: 0, max: 1, step: 0.005, description: "按不含增值税计税价格乘税率估算。当前国家口径为 10%。" },
        { kind: "number", key: "vehicle_purchase_tax_taxable_price_ratio", label: "含税价转计税价比例", fallback: 1 / 1.13, min: 0, max: 1, step: 0.001, description: "车价通常含增值税，购置税按不含增值税价格估算；默认用 1/1.13 折算。" },
        { kind: "text", key: "new_energy_vehicle_purchase_tax_exempt_until", label: "新能源购置税免征至", fallback: "2025-12", description: "符合目录的新能源车在该月份前按免征处理，并受单车免税额上限约束。" },
        { kind: "number", key: "new_energy_vehicle_purchase_tax_exemption_cap", label: "免征期单车免税上限", fallback: 30000, min: 0, step: 1000, description: "2024-2025 年新能源车免征车辆购置税，每辆新能源乘用车免税额不超过该上限。" },
        { kind: "text", key: "new_energy_vehicle_purchase_tax_half_until", label: "新能源购置税减半至", fallback: "2027-12", description: "符合目录的新能源车在该月份前按减半征收处理，并受单车减税额上限约束。" },
        { kind: "number", key: "new_energy_vehicle_purchase_tax_half_relief_cap", label: "减半期单车减税上限", fallback: 15000, min: 0, step: 1000, description: "2026-2027 年新能源车减半征收车辆购置税，每辆新能源乘用车减税额不超过该上限。" },
        { kind: "switch", key: "beijing_small_passenger_indicator_required", label: "北京小客车需要指标", description: "开启后，购车策略会要求明确北京小客车指标状态，并把预计等待月份纳入购车时间。" },
        { kind: "text", key: "beijing_new_energy_indicator_vehicle_types", label: "北京新能源指标车型", fallback: "pure_electric", description: "逗号分隔。北京新能源小客车指标默认只按纯电驱动车型处理；插混和增程不要默认放进这里。" },
        { kind: "text", key: "beijing_tail_restriction_exempt_vehicle_types", label: "北京尾号限行豁免车型", fallback: "pure_electric", description: "逗号分隔。默认只有纯电小客车按不限行便利性处理，插混、增程、燃油车应按普通小客车复核。" },
        { kind: "text", key: "vehicle_vessel_tax_passenger_not_taxable_types", label: "乘用车不征车船税类型", fallback: "pure_electric,fuel_cell", description: "逗号分隔。纯电、燃料电池乘用车因无排量通常不进入车船税征税范围；这不同于“免征”优惠。" },
        { kind: "text", key: "new_energy_vehicle_vessel_tax_exempt_types", label: "新能源车船税免征类型", fallback: "pure_electric,fuel_cell", description: "逗号分隔。用于政策包中仍按免征处理的新能源车船类型；插混/增程乘用车当前单独按优惠期和优惠后税额处理。" },
        { kind: "number", key: "beijing_family_new_energy_config_month", label: "家庭新能源配置月份", fallback: 5, min: 1, max: 12, step: 1, description: "用于把家庭新能源积分达到入围线的年份换算成具体等待月份；默认按每年 5 月集中配置估算。" },
        { kind: "number", key: "beijing_family_new_energy_reference_annual_quota", label: "家庭新能源指标量基准", fallback: 119200, min: 1, step: 100, description: "用于根据年度公告指标量粗略校正等待时间；2026 年常规配置加增发家庭新能源指标合计约 119200 个。" },
        { kind: "number", key: "beijing_personal_new_energy_indicator_wait_risk_months", label: "个人新能源指标等待风险月", fallback: 60, min: 0, max: 240, step: 1, description: "当车辆目标没有填写预计等待月数时，可作为个人新能源指标长期等待风险的参考。" },
        { kind: "text", key: "plug_in_hybrid_vehicle_vessel_tax_exempt_until", label: "插混/增程车船税优惠至", fallback: "2026-12", description: "插混、增程等车型在优惠期内可按 0 估算；优惠期后按下方年度车船税估算。" },
        { kind: "number", key: "plug_in_hybrid_vehicle_vessel_tax_annual", label: "插混/增程优惠后车船税/年", fallback: 420, min: 0, step: 10, description: "优惠期结束后用于插混、增程车型的年度车船税估算。具体税额仍与车型、排量和地方执行口径有关。" },
        { kind: "number", key: "fuel_vehicle_vessel_tax_annual_default", label: "燃油车车船税/年", fallback: 420, min: 0, step: 10, description: "燃油车年度车船税默认估算；实际金额按排量档、车型和保险代收结果复核。" }
      ]
    },
    {
      title: "税务与社保公积金",
      description: "工资税、社保、公积金缴存基数和年终奖计税应由政策包控制；成员页面只填个人收入阶段。",
      params: [
        { kind: "number", key: "personal_standard_deduction_annual", label: "年度基本扣除", fallback: 60000, min: 0, step: 1000, description: "综合所得个税年度基本减除费用。" },
        { kind: "text", key: "annual_bonus_separate_tax_valid_until", label: "年终奖政策公告至", fallback: "2027-12-31", description: "当前公开公告期限。系统按政策分段建模；未明确取消或更改时默认沿用当前口径，不在 2028 年自动禁用。" },
        { kind: "switch", key: "annual_bonus_separate_tax_default_continues", label: "公告后默认沿用当前口径", description: "开启后，政策未明确变化的年份继续允许年终奖单独计税择优。" },
        { kind: "number", key: "child_education_deduction_monthly", label: "子女教育月扣除", fallback: 2000, min: 0, step: 100, description: "每名符合条件子女的子女教育专项附加扣除月额。" },
        { kind: "number", key: "infant_care_deduction_monthly", label: "婴幼儿照护月扣除", fallback: 2000, min: 0, step: 100, description: "每名 3 岁以下婴幼儿照护专项附加扣除月额。" },
        { kind: "number", key: "continuing_education_degree_monthly", label: "继续教育月扣除", fallback: 400, min: 0, step: 100, description: "学历继续教育按月扣除口径；年度汇算项可在养娃计划页单独配置。" },
        { kind: "number", key: "continuing_education_professional_annual", label: "职业资格年度扣除", fallback: 3600, min: 0, step: 100, description: "职业资格继续教育年度扣除口径。" },
        { kind: "number", key: "serious_illness_medical_threshold", label: "大病医疗起扣线", fallback: 15000, min: 0, step: 1000, description: "大病医疗年度汇算时先扣除的自付金额阈值。" },
        { kind: "number", key: "serious_illness_medical_cap", label: "大病医疗扣除上限", fallback: 80000, min: 0, step: 1000, description: "大病医疗年度汇算可扣除上限。" },
        { kind: "number", key: "beijing_housing_rent_deduction_monthly", label: "北京住房租金月扣除", fallback: 1500, min: 0, step: 100, description: "北京住房租金专项附加扣除月额；与首套房贷利息互斥。" },
        { kind: "number", key: "first_home_mortgage_interest_deduction_monthly", label: "首套房贷利息月扣除", fallback: 1000, min: 0, step: 100, description: "首套住房贷款利息专项附加扣除月额；与住房租金互斥。" },
        { kind: "number", key: "first_home_mortgage_interest_max_months", label: "房贷利息最长月数", fallback: 240, min: 0, max: 360, step: 1, description: "首套住房贷款利息专项附加扣除最长享受月数。" },
        { kind: "number", key: "personal_pension_deduction_annual_cap", label: "个人养老金年缴费及扣除上限", fallback: 12000, min: 0, step: 1000, description: "个人养老金资金账户全年实际缴费与税前扣除共同适用的政策上限。" },
        { kind: "number", key: "personal_pension_withdrawal_tax_rate", label: "养老金领取税率", fallback: 0.03, min: 0, max: 1, step: 0.005, description: "个人养老金领取环节税率，用于长期策略估算。" },
        { kind: "switch", key: "rent_and_mortgage_deduction_mutually_exclusive", label: "租金与房贷利息互斥", description: "开启后，同一纳税人在同月只取住房租金和首套房贷利息中更优的一项。" },
        { kind: "number", key: "beijing_social_base_floor", label: "社保基数下限", fallback: 7162, min: 0, step: 100, description: "北京社保缴费基数下限。" },
        { kind: "number", key: "beijing_social_base_ceiling", label: "社保基数上限", fallback: 35811, min: 0, step: 100, description: "北京社保缴费基数上限。" },
        { kind: "number", key: "beijing_housing_fund_base_floor", label: "公积金基数下限", fallback: 2540, min: 0, step: 100, description: "北京住房公积金缴存基数下限。" },
        { kind: "number", key: "beijing_housing_fund_base_ceiling", label: "公积金基数上限", fallback: 35811, min: 0, step: 100, description: "北京住房公积金缴存基数上限。" },
        { kind: "number", key: "housing_fund_min_rate", label: "公积金最低比例", fallback: 0.05, min: 0, max: 0.12, step: 0.005, description: "个人收入阶段填写比例会被政策上下限夹住。" },
        { kind: "number", key: "housing_fund_max_rate", label: "公积金最高比例", fallback: 0.12, min: 0, max: 0.12, step: 0.005, description: "单位和个人公积金比例的政策上限。" }
      ]
    },
    {
      title: "失业、灵活就业与退休",
      description: "职业冲击页面只表达是否启用和成员年龄，金额由规则包自动估算。",
      params: [
        { kind: "number", key: "beijing_unemployment_benefit_under_5y", label: "失业金 1-5 年", fallback: 2129, min: 0, step: 10, description: "累计缴费不满 5 年时的月失业金估算。" },
        { kind: "number", key: "beijing_unemployment_benefit_5_to_10y", label: "失业金 5-10 年", fallback: 2156, min: 0, step: 10, description: "累计缴费 5 至 10 年对应月额。" },
        { kind: "number", key: "beijing_unemployment_benefit_10_to_15y", label: "失业金 10-15 年", fallback: 2188, min: 0, step: 10, description: "累计缴费 10 至 15 年对应月额。" },
        { kind: "number", key: "beijing_unemployment_benefit_15_to_20y", label: "失业金 15-20 年", fallback: 2215, min: 0, step: 10, description: "累计缴费 15 至 20 年对应月额。" },
        { kind: "number", key: "beijing_unemployment_benefit_20y_plus", label: "失业金 20 年以上", fallback: 2286, min: 0, step: 10, description: "累计缴费 20 年以上对应月额。" },
        { kind: "number", key: "beijing_unemployment_benefit_after_12_months", label: "失业金第 13 月后", fallback: 2129, min: 0, step: 10, description: "领取超过 12 个月后的月额估算。" },
        { kind: "number", key: "flexible_employment_social_base", label: "灵活就业社保基数", fallback: 7162, min: 0, step: 100, description: "职业冲击后自缴社保使用的基数。" },
        { kind: "number", key: "flexible_employment_pension_rate", label: "灵活就业养老比例", fallback: 0.2, min: 0, max: 1, step: 0.01, description: "灵活就业人员养老缴费比例。" },
        { kind: "number", key: "flexible_employment_unemployment_rate", label: "灵活就业失业比例", fallback: 0.01, min: 0, max: 1, step: 0.001, description: "灵活就业人员失业保险缴费比例。" },
        { kind: "number", key: "flexible_employment_medical_monthly", label: "灵活就业医保月额", fallback: 584.92, min: 0, step: 10, description: "灵活就业人员医保月缴费估算。" },
        { kind: "number", key: "pension_average_salary_growth_rate", label: "养老金工资增长", fallback: 0.03, min: 0, max: 0.1, step: 0.005, description: "养老金估算中社会平均工资增长率。" },
        { kind: "number", key: "pension_personal_account_annual_return", label: "基本养老个人账户记账率", fallback: 0.025, min: 0, max: 0.08, step: 0.005, description: "企业职工基本养老保险个人账户记账利率由国家按年公布；这里作为未填年度利率表时的兜底估算，后端按年度结息，不按月复利。" },
        { kind: "number", key: "pension_personal_account_interest_credit_month", label: "养老账户结息月份", fallback: 12, min: 1, max: 12, step: 1, description: "基本养老保险个人账户按年度记账；默认在 12 月体现年度利息。" },
        { kind: "number", key: "medical_account_annual_interest_rate", label: "医保个人账户活期利率", fallback: 0.0035, min: 0, max: 0.05, step: 0.0005, description: "北京医保个人账户按同期居民活期存款利率计息，后端默认按季度结息。" },
        { kind: "number", key: "pension_personal_account_months", label: "养老金计发月数", fallback: 139, min: 1, max: 300, step: 1, description: "退休后个人账户养老金计发月数。" }
      ]
    },
    {
      title: "策略与压力测试",
      description: "这些不是政策本身，而是策略生成和压力测试参数。它们影响方案排序，不应写死在前端。",
      params: [
        { kind: "number", key: "recommended_emergency_months", label: "推荐应急月数", fallback: 6, min: 0, max: 36, step: 1, description: "安全垫建议月数，用于策略可行性和幸福指数。" },
        { kind: "number", key: "caution_dti", label: "谨慎 DTI", fallback: 0.4, min: 0, max: 2, step: 0.01, description: "负债收入比达到该水平时开始提示压力。" },
        { kind: "number", key: "danger_dti", label: "高风险 DTI", fallback: 0.5, min: 0, max: 2, step: 0.01, description: "负债收入比超过该水平会显著压低可行性和幸福指数。" },
        { kind: "number", key: "rate_stress_add", label: "利率压力上浮", fallback: 0.005, min: 0, max: 0.05, step: 0.0005, description: "压力测试中对贷款利率的上浮假设。" },
        { kind: "number", key: "income_stress_factor", label: "收入压力系数", fallback: 0.9, min: 0, max: 1, step: 0.01, description: "压力测试中收入按该比例折减。" },
        { kind: "number", key: "price_stress_factor", label: "房价压力系数", fallback: 1.05, min: 1, max: 2, step: 0.01, description: "压力测试中房价或交易成本上浮系数。" },
        { kind: "number", key: "micro_commercial_loan_ratio", label: "微量商贷默认比例", fallback: 0.05, min: 0, max: 1, step: 0.01, description: "未手动指定时，微量商贷策略的默认候选比例。" },
        { kind: "number", key: "micro_commercial_loan_ratio_min", label: "微量商贷自动下限", fallback: 0.02, min: 0, max: 1, step: 0.01, description: "后端自动寻找微量商贷比例时的下限。" },
        { kind: "number", key: "micro_commercial_loan_ratio_max", label: "微量商贷自动上限", fallback: 0.12, min: 0, max: 1, step: 0.01, description: "后端自动寻找微量商贷比例时的上限。" },
        { kind: "number", key: "backend_parallel_workers", label: "策略生成并行数", fallback: 4, min: 1, max: 16, step: 1, description: "策略生成可并行的工作线程数；这是性能参数，不属于政策口径。" }
      ]
    }
  ];
  const renderRuleControl = (param: RuleParamConfig) => {
    if (param.kind === "number") {
      return (
        <div className="rule-param-field" key={param.key}>
          <NumberField
            label={param.label}
            value={ruleNumber(param.key, param.fallback)}
            min={param.min}
            max={param.max}
            step={param.step ?? 1}
            onChange={(value) => updateRuleParam(param.key, value)}
          />
          <p className="field-hint">{param.description}</p>
        </div>
      );
    }
    if (param.kind === "switch") {
      const rawValue = activeRulePack.params[param.key];
      const trueValue = param.trueValue ?? true;
      const falseValue = param.falseValue ?? false;
      const checked = typeof trueValue === "number" ? Number(rawValue ?? falseValue) > 0 : Boolean(rawValue ?? falseValue);
      return (
        <div className="rule-param-field switch-rule-param" key={param.key}>
          <SwitchField
            label={param.label}
            checked={checked}
            onChange={(nextChecked) => updateRuleParam(param.key, nextChecked ? trueValue : falseValue)}
          />
          <p className="field-hint">{param.description}</p>
        </div>
      );
    }
    if (param.kind === "select") {
      return (
        <div className="rule-param-field" key={param.key}>
          <Field label={param.label}>
            <select
              value={String(activeRulePack.params[param.key] ?? param.fallback)}
              onChange={(event) => updateRuleParam(param.key, event.target.value)}
            >
              {param.options.map((option) => (
                <option value={option.value} key={option.value}>{option.label}</option>
              ))}
            </select>
          </Field>
          <p className="field-hint">{param.description}</p>
        </div>
      );
    }
    return (
      <div className="rule-param-field" key={param.key}>
        <Field label={param.label}>
          <input
            value={String(activeRulePack.params[param.key] ?? param.fallback)}
            onChange={(event) => updateRuleParam(param.key, event.target.value)}
          />
        </Field>
        <p className="field-hint">{param.description}</p>
      </div>
    );
  };
  return (
    <PlannerPageShell
      icon={<Database size={20} />}
      title="政策规则"
      summary={<p>政策页只维护规则包、城市口径和来源预览；核心规则默认展开，细分政策参数按类别收起。</p>}
    >
      <section className="rule-panel">
        <PanelTitle icon={<Database size={18} />} title="规则包与来源" collapsible />
        <div className="rule-grid rule-meta-grid">
          <Field label="规则包名称">
            <input
              value={activeRulePack.name}
              onChange={(event) => updateRulePack("name", event.target.value)}
            />
          </Field>
          <Field label="生效日期">
            <input
              value={activeRulePack.effective_date}
              onChange={(event) => updateRulePack("effective_date", event.target.value)}
            />
          </Field>
          <Field label="城市/地区">
            <input
              value={activeRulePack.jurisdiction}
              onChange={(event) => updateRulePack("jurisdiction", event.target.value)}
            />
          </Field>
        </div>
        <div className="rule-category-stack">
          {ruleGroups.map((group, groupIndex) => (
            <details className="rule-category-panel collapsible-rule-category" key={group.title} open={groupIndex === 0}>
              <summary className="strategy-panel-head">
                <div>
                  <strong>{group.title}</strong>
                  <span>{group.description}</span>
                </div>
                <ChevronDown size={17} aria-hidden="true" />
              </summary>
              <div className="rule-grid categorized-rule-grid">
                {group.params.map(renderRuleControl)}
              </div>
            </details>
          ))}
        </div>
        <div className="source-row">
          <select value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)}>
            {sourceDefaults.map((url) => (
              <option key={url} value={url}>
                {url}
              </option>
            ))}
          </select>
          <button className="ghost-button" onClick={previewSource} disabled={saving}>
            <RefreshCw size={16} /> 抓取预览
          </button>
        </div>
        {sourcePreview ? (
          <div className="source-preview">
            <strong>{sourcePreview.changed_from_previous ? "发现新内容或首次抓取" : "内容未变化"}</strong>
            <span>{sourcePreview.summary}</span>
          </div>
        ) : null}
      </section>
    </PlannerPageShell>
  );
}

function VisualizationPage({
  result,
  household,
  selectedScenario,
  scenarioComparisons,
  setSelectedScenarioId,
  selectedPlan,
  selectedPlanVariant,
  setSelectedPlanVariant,
  availablePlans,
  accountConcepts,
  coreObjectGroups,
  activeRulePack,
  calculationPending,
  timelineState,
  onTimelineStateChange
}: {
  result: AffordabilityResult | null;
  household: HouseholdData;
  selectedScenario: RecordEnvelope<ScenarioData>;
  scenarioComparisons: ScenarioComparison[];
  setSelectedScenarioId: (id: string) => void;
  selectedPlan: PurchasePlanAnalysis | null;
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  availablePlans: PurchasePlanAnalysis[];
  accountConcepts: AccountConceptSummary[];
  coreObjectGroups: CoreObjectGroupSummary[];
  activeRulePack: RulePackData;
  calculationPending: boolean;
  timelineState: VisualizationTimelineState;
  onTimelineStateChange: (patch: Partial<VisualizationTimelineState>) => void;
}) {
  const scenario = selectedScenario.data;
  const visualizationConceptByCode = accountConceptMap(accountConcepts);
  const visualizationGroupByCode = coreObjectGroupMap(coreObjectGroups);
  const visualizationCoreObjectSummary = [
    `流动资产 ${coreObjectBalanceText(visualizationGroupByCode.get(CORE_OBJECT_GROUP_CODES.liquidAssets))}`,
    `受限账户 ${coreObjectBalanceText(visualizationGroupByCode.get(CORE_OBJECT_GROUP_CODES.restrictedAccounts))}`,
    `固定资产 ${coreObjectBalanceText(visualizationGroupByCode.get(CORE_OBJECT_GROUP_CODES.fixedAssets))}`,
    `贷款账户 ${coreObjectBalanceText(visualizationGroupByCode.get(CORE_OBJECT_GROUP_CODES.loanAccounts))}`,
    `公积金 ${coreObjectBalanceText(visualizationConceptByCode.get(ACCOUNT_CONCEPT_CODES.provident))}`
  ].join(" · ");
  const isBaselinePlan = selectedPlan?.source === "baseline";
  const comparisonDecision = (plan: PurchasePlanAnalysis | null) => {
    if (!plan) return { label: "待生成", tone: "muted" };
    if (plan.months_to_buy === null) return { label: "暂不可达", tone: "bad" };
    if (plan.cash_stress_ok === false || (plan.cash_stress_shortfall ?? 0) > 0) return { label: "先修现金缺口", tone: "bad" };
    if (!plan.liquidity_ok) return { label: "现金垫偏紧", tone: "warn" };
    if (plan.post_purchase_cash_flow < 0) return { label: "月供压力高", tone: "warn" };
    if (plan.happiness_score >= 7 && plan.debt_to_income_ratio <= 0.45) return { label: "优先关注", tone: "good" };
    return { label: "可比较", tone: "neutral" };
  };

  return (
    <PlannerPageShell
      icon={<TrendingUp size={20} />}
      title="可视化"
      summary={<p>按“方案对比、当前策略故事线、账户曲线、月度明细、贷款与政策账户、事件时间线”的顺序查看完整推演。</p>}
    >
      <section className="result-panel decision-board">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Home size={18} />} title={scenarioComparisons.length ? "房源决策表" : "家庭基线"} compact />
          <span>
            {scenarioComparisons.length
              ? "先看哪套房、哪种策略更值得继续推演；点击一行后，下方故事线会切换到对应房源和策略。"
              : "当前没有启用购房目标，下方展示家庭现金流、账户、贷款、政策账户和事件时间线的基线推演。"}
          </span>
        </div>
        {scenarioComparisons.length ? (
          <div className="comparison-table">
            <div className="comparison-row comparison-head">
              <span>房源与策略</span>
              <span>可买时间</span>
              <span>交易后现金</span>
              <span>压力现金</span>
              <span>买后月结余</span>
              <span>贷款压力</span>
              <span>幸福指数</span>
              <span>判断</span>
            </div>
            {scenarioComparisons.map(({ scenario: comparedScenario, selectedPlan: plan }) => {
              const decision = comparisonDecision(plan);
              const minimumCash =
                plan?.minimum_cash_balance !== undefined && plan.minimum_cash_balance !== null
                  ? plan.minimum_cash_balance
                  : plan?.cash_after_transaction;
              const stressShortfall = Math.max(0, plan?.cash_stress_shortfall ?? 0);
              const isRecommended = Boolean(plan?.is_recommended);
              return (
                <button
                  type="button"
                  className={comparedScenario.id === selectedScenario.id ? "comparison-row active" : "comparison-row"}
                  key={comparedScenario.id}
                  onClick={() => setSelectedScenarioId(comparedScenario.id)}
                >
                  <span>
                    <strong>{comparedScenario.data.name}</strong>
                    <small>
                      {comparedScenario.data.property_type} · {money(comparedScenario.data.total_price)}
                      {plan ? ` · ${plan.variant}` : ""}
                      {isRecommended ? " · 系统推荐" : ""}
                    </small>
                  </span>
                  <span data-label="可买时间">{plan ? formatPurchaseTiming(new Date(), plan.months_to_buy, plan.years_to_buy) : "-"}</span>
                  <span data-label="交易后现金">{plan ? money(plan.cash_after_purchase) : "-"}</span>
                  <span data-label="压力现金">{plan && stressShortfall > 0 ? `缺口 ${money(stressShortfall)}` : plan && minimumCash !== undefined ? money(minimumCash) : "-"}</span>
                  <span data-label="买后月结余">{plan ? money(plan.post_purchase_cash_flow) : "-"}</span>
                  <span data-label="贷款压力">{plan ? `${percent(plan.debt_to_income_ratio)} · 息 ${money(plan.total_interest)}` : "-"}</span>
                  <span data-label="幸福指数">{plan ? `${plan.happiness_score.toFixed(1)} / 10` : "-"}</span>
                  <span className={`decision-pill ${decision.tone}`} data-label="判断">{decision.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">
            {calculationPending
              ? "正在计算家庭基线"
              : "未启用购房目标，因此没有房源对比表；可视化会继续展示家庭基线账本。"}
          </div>
        )}
        <p className="field-hint">核心对象口径：{visualizationCoreObjectSummary}。账户、资产和贷款解释与家庭财务、记账校准和导出表共用这套后端概念。</p>
      </section>
      <section className="result-panel visualization-story-panel">
        {result && selectedPlan ? (
          <>
            <div className="visual-header">
              <div>
                <PanelTitle icon={<TrendingUp size={18} />} title={isBaselinePlan ? "家庭基线" : "选中策略"} />
                <h3>{selectedPlan.variant}</h3>
                <div className="visual-summary-strip">
                  <span>
                    <small>{isBaselinePlan ? "测算口径" : "可买时间"}</small>
                    <strong>{isBaselinePlan ? "不触发购房交易" : formatPurchaseTiming(new Date(), selectedPlan.months_to_buy, selectedPlan.years_to_buy)}</strong>
                  </span>
                  <span>
                    <small>{isBaselinePlan ? "当前现金账户" : "交易后现金"}</small>
                    <strong>{money(selectedPlan.cash_after_purchase)}</strong>
                  </span>
                  <span>
                    <small>{isBaselinePlan ? "当前月结余" : "买后月结余"}</small>
                    <strong>{money(selectedPlan.post_purchase_cash_flow)}</strong>
                  </span>
                  <span>
                    <small>幸福指数</small>
                    <strong>{selectedPlan.happiness_score.toFixed(1)} / 10</strong>
                  </span>
                </div>
              </div>
              {availablePlans.length > 1 || !isBaselinePlan ? (
                <select
                  value={selectedPlanVariant}
                  onChange={(event) => setSelectedPlanVariant(event.target.value)}
                >
                  {availablePlans.map((plan) => (
                    <option key={plan.variant} value={plan.variant}>
                      {plan.variant}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>

            <SelectedPlanVisualization
              result={result}
              household={household}
              scenario={scenario}
              plan={selectedPlan}
              availablePlans={availablePlans}
              rulePack={activeRulePack}
              timelineState={timelineState}
              onTimelineStateChange={onTimelineStateChange}
            />
          </>
        ) : (
          <PanelTitle
            icon={<Loader2 className="spin" size={18} />}
            title={calculationPending ? "正在计算生成策略" : "等待计算生成策略"}
          />
        )}
      </section>
    </PlannerPageShell>
  );
}

function SelectedPlanVisualization({
  result,
  household,
  scenario,
  plan,
  availablePlans,
  rulePack,
  timelineState,
  onTimelineStateChange
}: {
  result: AffordabilityResult;
  household: HouseholdData;
  scenario: ScenarioData;
  plan: PurchasePlanAnalysis;
  availablePlans: PurchasePlanAnalysis[];
  rulePack: RulePackData;
  timelineState: VisualizationTimelineState;
  onTimelineStateChange: (patch: Partial<VisualizationTimelineState>) => void;
}) {
  const timelineBaseDate = useMemo(() => new Date(), []);
  const { selectedMonthIndex, viewStartMonth, viewWindowMonths } = timelineState;
  const timelineRailRef = useRef<HTMLDivElement | null>(null);
  const timelineDragRef = useRef<{
    mode: "select" | "move-window" | "resize-start" | "resize-end";
    startPointerMonth: number;
    startSelectedMonth: number;
    startClientX: number;
    hasMoved: boolean;
    startViewStart: number;
    startViewWindow: number;
  } | null>(null);
  const timelinePreviewRef = useRef<{
    selectedMonth: number;
    viewStartMonth: number;
    viewWindowMonths: number;
  } | null>(null);
  const [timelineMarkerPulseKey, setTimelineMarkerPulseKey] = useState(0);
  const [timelinePreview, setTimelinePreview] = useState<{
    selectedMonth: number;
    viewStartMonth: number;
    viewWindowMonths: number;
  } | null>(null);
  const [timelineHoverMonth, setTimelineHoverMonth] = useState<number | null>(null);
  const [isCompactChart, setIsCompactChart] = useState(() =>
    typeof window === "undefined" ? false : window.innerWidth < 640
  );
  const isBaselineVisualization = plan.source === "baseline";
  const usesMonthlyProvidentRepayment = (plan.post_purchase_pf_strategy ?? "").includes("monthly_repayment_withdrawal");
  useEffect(() => {
    const syncCompactChart = () => setIsCompactChart(window.innerWidth < 640);
    syncCompactChart();
    window.addEventListener("resize", syncCompactChart);
    return () => window.removeEventListener("resize", syncCompactChart);
  }, []);
  const visualizationPlanVariant = useMemo(() => {
    const variants = Array.from(
      new Set(
        (result.monthly_cashflow_visualization ?? [])
          .map((item) => item.plan_variant)
          .filter(Boolean)
      )
    );
    if (variants.includes(plan.variant)) return plan.variant;
    return variants[0] ?? plan.variant;
  }, [result.monthly_cashflow_visualization, plan.variant]);
  const visualizationVariantMismatch = visualizationPlanVariant !== plan.variant;
  const loanVisualizationSeries = useMemo(
    () => (result.loan_visualization ?? []).filter((item) => item.plan_variant === visualizationPlanVariant),
    [result.loan_visualization, visualizationPlanVariant]
  );
  const loanVisualizationByMonth = useMemo(
    () => new Map(loanVisualizationSeries.map((item) => [item.month, item])),
    [loanVisualizationSeries]
  );
  const providentVisualizationSeries = useMemo(
    () => (result.provident_visualization ?? []).filter((item) => item.plan_variant === visualizationPlanVariant),
    [result.provident_visualization, visualizationPlanVariant]
  );
  const providentVisualizationByMonth = useMemo(
    () => new Map(providentVisualizationSeries.map((item) => [item.month, item])),
    [providentVisualizationSeries]
  );
  const socialSecurityVisualizationSeries = useMemo(
    () => (result.social_security_visualization ?? []).filter((item) => item.plan_variant === visualizationPlanVariant),
    [result.social_security_visualization, visualizationPlanVariant]
  );
  const socialSecurityVisualizationByMonth = useMemo(
    () => new Map(socialSecurityVisualizationSeries.map((item) => [item.month, item])),
    [socialSecurityVisualizationSeries]
  );
  const backendCashflowSeries = useMemo(
    () => (result.monthly_cashflow_visualization ?? []).filter((item) => item.plan_variant === visualizationPlanVariant),
    [result.monthly_cashflow_visualization, visualizationPlanVariant]
  );
  const monthlyVisualizationDetailByMonth = useMemo(
    () =>
      new Map(
        (result.monthly_visualization_details ?? [])
          .filter((item) => item.plan_variant === visualizationPlanVariant)
          .map((item) => [item.month, item])
      ),
    [result.monthly_visualization_details, visualizationPlanVariant]
  );
  const annualVisualizationDetailByYear = useMemo(
    () =>
      new Map(
        (result.annual_visualization_details ?? [])
          .filter((item) => item.plan_variant === visualizationPlanVariant)
          .map((item) => [item.year, item])
      ),
    [result.annual_visualization_details, visualizationPlanVariant]
  );
  const taxVisualizationDetailByMonth = useMemo(
    () =>
      new Map(
        (result.tax_visualization_details ?? [])
          .filter((item) => item.month !== null)
          .map((item) => [item.month as number, item])
      ),
    [result.tax_visualization_details]
  );
  const taxVisualizationDetailByYear = useMemo(
    () =>
      new Map(
        (result.tax_visualization_details ?? [])
          .filter((item) => item.month === null)
          .map((item) => [item.year, item])
      ),
    [result.tax_visualization_details]
  );
  const taxMonthlySeries = result.tax_monthly_points ?? [];
  const taxMonthlyByMonth = useMemo(
    () => new Map(taxMonthlySeries.map((item) => [item.month, item])),
    [taxMonthlySeries]
  );
  const requiredCashAfterPf = plan.required_cash_after_pf_extract;
  const purchaseYearText = formatPurchaseTiming(timelineBaseDate, plan.months_to_buy, plan.years_to_buy);
  const annualReturn = scenario.annual_investment_return ?? 0;
  const investmentEnabled = household.investment_plan_name !== "cash_only";
  const investmentBuyFeeRate = Math.min(Math.max(0, household.investment_buy_fee_rate ?? 0.0015), 0.05);
  const investmentSellFeeRate = Math.min(Math.max(0, household.investment_sell_fee_rate ?? 0.005), 0.05);
  const monthlyInvestmentSetting = investmentEnabled ? Math.max(0, household.monthly_investment_amount ?? 0) : 0;
  const renovationTimingText =
    plan.renovation_cost <= 0
      ? "无装修预算"
      : plan.months_to_renovation === null
          ? "暂无法估算"
          : `买后 ${plan.months_to_renovation} 个月`;
  const taxMemberPointToIncomeRow = (
    member: NonNullable<(typeof taxMonthlySeries)[number]["member_points"]>[number],
    absoluteMonth: number
  ) => {
    const householdMember = household.members.find((item) => item.name === member.member_name);
    const activeStage = householdMember ? incomeStageAt(householdMember, timelineBaseDate, absoluteMonth) : null;
    const stageKind = activeStage?.stage_kind ?? "manual";
    const taxableCash = member.gross_salary + member.bonus_income + member.other_taxable_income;
    const pensionIncome = member.pension_income ?? 0;
    const otherNonTaxableIncome = Math.max(0, member.non_taxable_income - pensionIncome);
    const allocTax = (amount: number) => (taxableCash > 0 ? member.total_income_tax * (amount / taxableCash) : 0);
    return {
      name: member.member_name,
      stageName: member.stage_name,
      stageKind,
      grossMonthly: member.gross_salary,
      bonusMonthly: member.bonus_income,
      otherMonthly: member.other_taxable_income,
      nonTaxableMonthly: otherNonTaxableIncome,
      pensionMonthly: pensionIncome,
      salaryNetMonthly: Math.max(
        0,
        member.gross_salary - member.personal_social - member.personal_housing_fund - allocTax(member.gross_salary)
      ),
      bonusNetMonthly: Math.max(0, member.bonus_income - allocTax(member.bonus_income)),
      otherNetMonthly: Math.max(0, member.other_taxable_income - allocTax(member.other_taxable_income)),
      nonTaxableNetMonthly: otherNonTaxableIncome,
      pensionNetMonthly: pensionIncome,
      extraCashExpense: 0,
      netMonthly: member.net_income,
      personalSocial: member.personal_social,
      personalHousingFund: member.personal_housing_fund,
      employerHousingFund: member.employer_housing_fund,
      incomeTax: member.total_income_tax,
      salaryTax: member.salary_tax,
      bonusTax: member.bonus_tax,
      elderlyCareDeduction: member.elderly_care_deduction,
      specialDeduction: member.special_additional_deduction + member.elderly_care_deduction + member.other_deduction
    };
  };
  const getMemberIncomeRows = (absoluteMonth: number) =>
    taxMonthlyByMonth.get(absoluteMonth)?.member_points.map((member) => taxMemberPointToIncomeRow(member, absoluteMonth)) ??
    (household.members.length > 0
      ? []
      : [
          {
            name: "家庭",
            stageName: "当前收入",
            stageKind: "manual" as IncomeStageData["stage_kind"],
            grossMonthly: result.household_gross_monthly_income,
            bonusMonthly: 0,
            otherMonthly: 0,
            nonTaxableMonthly: 0,
            salaryNetMonthly: result.household_net_monthly_income,
            bonusNetMonthly: 0,
            otherNetMonthly: 0,
            nonTaxableNetMonthly: 0,
            pensionNetMonthly: 0,
            pensionMonthly: 0,
            extraCashExpense: 0,
            netMonthly: result.household_net_monthly_income,
            personalSocial: 0,
            personalHousingFund: 0,
            employerHousingFund: 0,
            incomeTax: 0,
            elderlyCareDeduction: 0,
            specialDeduction: 0
          }
        ]);
  const horizonMonths = Math.min(
    960,
    Math.max(
      180,
      backendCashflowSeries[backendCashflowSeries.length - 1]?.month ?? 0,
      loanVisualizationSeries[loanVisualizationSeries.length - 1]?.month ?? 0,
      providentVisualizationSeries[providentVisualizationSeries.length - 1]?.month ?? 0,
      socialSecurityVisualizationSeries[socialSecurityVisualizationSeries.length - 1]?.month ?? 0,
      taxMonthlySeries[taxMonthlySeries.length - 1]?.month ?? 0
    )
  );
  const chartMaxTicks = isCompactChart ? 4 : 8;
  const chartMonthTickInterval = Math.max(0, Math.ceil(Math.min(horizonMonths + 1, viewWindowMonths) / chartMaxTicks) - 1);
  const formatChartMonthTick = (value: unknown) => {
    const month = Number(value);
    if (!Number.isFinite(month)) return "";
    const targetDate = addMonths(timelineBaseDate, month);
    return `${targetDate.getFullYear()}.${targetDate.getMonth() + 1}`;
  };
  const chartXAxisProps = {
    dataKey: "month",
    tickLine: false,
    axisLine: false,
    interval: chartMonthTickInterval,
    minTickGap: isCompactChart ? 34 : 52,
    tickMargin: 10,
    height: 34,
    tickFormatter: formatChartMonthTick
  };
  const monthlySeries = buildMonthlyChartSeries({
    backendCashflowSeries,
    horizonMonths,
    requiredLiquidityReserve: plan.required_liquidity_reserve,
    loanVisualizationByMonth,
    providentVisualizationByMonth,
    socialSecurityVisualizationByMonth,
    formatMonthName: (month) => formatMonthDate(timelineBaseDate, month),
    scheduledExpenseRowsAt: (month) => scheduledExpenseRowsAt(household, timelineBaseDate, month)
  });
  const hasBackendMonthlySeries = monthlySeries.length > 0;
  const timelineEndMonth = Math.max(
    0,
    monthlySeries[monthlySeries.length - 1]?.month ?? monthlySeries.length - 1,
    loanVisualizationSeries[loanVisualizationSeries.length - 1]?.month ?? 0,
    providentVisualizationSeries[providentVisualizationSeries.length - 1]?.month ?? 0,
    socialSecurityVisualizationSeries[socialSecurityVisualizationSeries.length - 1]?.month ?? 0,
    taxMonthlySeries[taxMonthlySeries.length - 1]?.month ?? 0
  );
  const clampTimelineMonth = (month: number) => Math.max(0, Math.min(timelineEndMonth, Math.round(month)));
  const safeSelectedMonthIndex = clampTimelineMonth(selectedMonthIndex);
  const selectedMonth =
    monthlySeries.find((item) => item.month === safeSelectedMonthIndex) ??
    monthlySeries[Math.min(safeSelectedMonthIndex, monthlySeries.length - 1)] ??
    emptyMonthlyChartPoint(formatMonthDate(timelineBaseDate, 0), plan.required_liquidity_reserve);
  const selectedMonthDetail = monthlyVisualizationDetailByMonth.get(selectedMonth.month);
  const emptyMonthlyDetail = useMemo(() => {
    return {
      income_pie: [],
      income_legend: [],
      expense_pie: [],
      cash_flow_items: [],
      cash_flow_drivers: [],
      advisor_text:
        selectedMonthDetail === undefined
          ? `${selectedMonth.name} 的月度现金流明细还没有由后端生成。`
          : `${selectedMonth.name} 没有可展示的现金流项目。`,
      explanation_items: [
        {
          title: "等待后端明细",
          body: "月现金流逐项明细以后端月度账本为准；前端不再用本地公式补算，以免和账户、税务、贷款、投资策略口径不一致。"
        }
      ]
    };
  }, [selectedMonth.name, selectedMonthDetail]);
  const effectiveMonthlyDetail = {
    income_pie: selectedMonthDetail?.income_pie ?? emptyMonthlyDetail.income_pie,
    income_legend: selectedMonthDetail?.income_legend ?? emptyMonthlyDetail.income_legend,
    expense_pie: selectedMonthDetail?.expense_pie ?? emptyMonthlyDetail.expense_pie,
    loan_payment_pie: selectedMonthDetail?.loan_payment_pie ?? [],
    provident_inflow_pie: selectedMonthDetail?.provident_inflow_pie ?? [],
    provident_outflow_pie: selectedMonthDetail?.provident_outflow_pie ?? [],
    social_security_inflow_pie: selectedMonthDetail?.social_security_inflow_pie ?? [],
    social_security_outflow_pie: selectedMonthDetail?.social_security_outflow_pie ?? [],
    cash_flow_items: selectedMonthDetail?.cash_flow_items ?? emptyMonthlyDetail.cash_flow_items,
    cash_flow_drivers: selectedMonthDetail?.cash_flow_drivers ?? emptyMonthlyDetail.cash_flow_drivers,
    advisor_text: selectedMonthDetail?.advisor_text || emptyMonthlyDetail.advisor_text,
    explanation_items: selectedMonthDetail?.explanation_items?.length
      ? selectedMonthDetail.explanation_items
      : emptyMonthlyDetail.explanation_items
  };
  const plannedHomeLoanAmount = Math.max(0, plan.commercial_loan_amount + plan.provident_loan_amount);
  const plannedVehicleLoanAmount = Math.max(0, result.car_loan.loan_principal ?? 0);
  const selectedLoanPoint = loanVisualizationByMonth.get(safeSelectedMonthIndex);
  const selectedProvidentPoint = providentVisualizationByMonth.get(safeSelectedMonthIndex);
  const selectedTotalLoanBalance = selectedLoanPoint?.total_loan_balance ?? 0;
  const selectedExistingLoanDetails = selectedLoanPoint?.existing_loan_details ?? [];
  const selectedExistingLoanPaymentTotal = selectedExistingLoanDetails.reduce(
    (sum, item) => sum + Math.max(0, item.monthly_payment || 0),
    0
  );
  const selectedOtherFixedDebtPayment = Math.max(
    0,
    selectedLoanPoint
      ? selectedLoanPoint.existing_monthly_payment - selectedExistingLoanPaymentTotal
      : selectedMonth.regularDebtPayment
  );
  const selectedExistingLoanDescription = selectedExistingLoanDetails.length > 0
    ? selectedExistingLoanDetails.map((item) => `${item.name} ${money(item.monthly_payment)}`).join("、")
    : `已有贷款合计 ${money(selectedLoanPoint?.existing_monthly_payment ?? selectedMonth.phasedLoanPayment)}`;
  const selectedExistingLoanBalanceDescription = selectedExistingLoanDetails.length > 0
    ? selectedExistingLoanDetails.map((item) => `${item.name} ${money(item.balance)}`).join("、")
    : `已有贷款 ${money(selectedLoanPoint?.existing_loan_balance ?? 0)}`;
  const maxViewStartMonth = Math.max(0, timelineEndMonth - viewWindowMonths + 1);
  const viewEndMonth = Math.min(timelineEndMonth, viewStartMonth + viewWindowMonths - 1);
  const visibleMonthlySeries = useMemo(
    () => monthlySeries.filter((item) => item.month >= viewStartMonth && item.month <= viewEndMonth),
    [monthlySeries, viewEndMonth, viewStartMonth]
  );
  const previewSelectedMonthIndex = clampTimelineMonth(timelinePreview?.selectedMonth ?? safeSelectedMonthIndex);
  const previewViewWindowMonths = Math.max(1, timelinePreview?.viewWindowMonths ?? viewWindowMonths);
  const previewViewStartMonth = Math.max(
    0,
    Math.min(timelinePreview?.viewStartMonth ?? viewStartMonth, Math.max(0, timelineEndMonth - previewViewWindowMonths + 1))
  );
  const previewViewEndMonth = Math.min(timelineEndMonth, previewViewStartMonth + previewViewWindowMonths - 1);
  const selectedMonthInputValue = formatMonthInputValue(timelineBaseDate, safeSelectedMonthIndex);
  const timelineStartInputValue = formatMonthInputValue(timelineBaseDate, 0);
  const timelineEndInputValue = formatMonthInputValue(timelineBaseDate, timelineEndMonth);
  const currentViewLabel =
    previewViewStartMonth <= 0 && previewViewEndMonth >= timelineEndMonth
      ? "全生命周期"
      : `${formatMonthDate(timelineBaseDate, previewViewStartMonth)} - ${formatMonthDate(timelineBaseDate, previewViewEndMonth)}`;
  const viewStartForSelectedMonth = useCallback(
    (month: number, currentStart: number, windowMonths: number) => {
      const safeWindowMonths = Math.max(1, Math.min(timelineEndMonth + 1, Math.round(windowMonths)));
      const maxStart = Math.max(0, timelineEndMonth - safeWindowMonths + 1);
      const clampedStart = Math.max(0, Math.min(currentStart, maxStart));
      if (month < clampedStart) return Math.max(0, Math.min(month, maxStart));
      if (month > clampedStart + safeWindowMonths - 1) {
        return Math.max(0, Math.min(month - safeWindowMonths + 1, maxStart));
      }
      return clampedStart;
    },
    [timelineEndMonth]
  );
  const selectVisualMonth = (month: number) => {
    const nextMonth = clampTimelineMonth(month);
    const nextViewStart = viewStartForSelectedMonth(nextMonth, viewStartMonth, viewWindowMonths);
    startTransition(() => {
      onTimelineStateChange({
        selectedMonthIndex: nextMonth,
        viewStartMonth: nextViewStart
      });
    });
  };
  const timelineMonthToPercent = (month: number) =>
    timelineEndMonth <= 0 ? 0 : Math.max(0, Math.min(100, (month / timelineEndMonth) * 100));
  const timelineWindowStartPercent = timelineMonthToPercent(previewViewStartMonth);
  const timelineWindowEndPercent = timelineMonthToPercent(previewViewEndMonth);
  const timelineSelectedPercent = timelineMonthToPercent(previewSelectedMonthIndex);
  const timelineFocusMonth = timelinePreview?.selectedMonth ?? timelineHoverMonth;
  const timelineFocusPercent = timelineFocusMonth === null ? 0 : timelineMonthToPercent(timelineFocusMonth);
  const timelineFocusLabel = timelineFocusMonth === null ? "" : formatMonthDate(timelineBaseDate, timelineFocusMonth);
  const timelineWindowWidthPercent = Math.max(1.2, timelineWindowEndPercent - timelineWindowStartPercent);
  const timelineTickCount = isCompactChart ? 5 : 7;
  const timelineTicks = useMemo(() => {
    const count = Math.max(2, Math.min(timelineTickCount, timelineEndMonth + 1));
    return Array.from(
      new Set(
        Array.from({ length: count }, (_, index) =>
          Math.round((timelineEndMonth * index) / Math.max(1, count - 1))
        )
      )
    ).map((month) => ({
      month,
      left: timelineMonthToPercent(month),
      label: formatChartMonthTick(month)
    }));
  }, [formatChartMonthTick, timelineEndMonth, timelineTickCount]);
  const timelineMinorTicks = useMemo(() => {
    const step = timelineEndMonth > 360 ? 24 : 12;
    return Array.from({ length: Math.floor(timelineEndMonth / step) + 1 }, (_, index) => {
      const month = index * step;
      return { month, left: timelineMonthToPercent(month) };
    });
  }, [timelineEndMonth]);
  const monthFromTimelineClientX = useCallback(
    (clientX: number) => {
      const rect = timelineRailRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0) return 0;
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      return clampTimelineMonth(Math.round(ratio * timelineEndMonth));
    },
    [timelineEndMonth]
  );
  const clampViewWindow = useCallback(
    (months: number) => Math.max(Math.min(timelineEndMonth + 1, Math.round(months)), Math.min(12, timelineEndMonth + 1)),
    [timelineEndMonth]
  );
  const updateTimelinePreview = useCallback((next: { selectedMonth: number; viewStartMonth: number; viewWindowMonths: number }) => {
    timelinePreviewRef.current = next;
    setTimelinePreview(next);
  }, []);
  const applyTimelineDrag = useCallback(
    (clientX: number) => {
      const drag = timelineDragRef.current;
      if (!drag) return;
      const pointerMonth = monthFromTimelineClientX(clientX);
      if (drag.mode === "select") {
        const windowMonths = clampViewWindow(viewWindowMonths);
        updateTimelinePreview({
          selectedMonth: pointerMonth,
          viewStartMonth: viewStartForSelectedMonth(pointerMonth, viewStartMonth, windowMonths),
          viewWindowMonths: windowMonths
        });
        return;
      }
      const dragDistance = Math.abs(clientX - drag.startClientX);
      if (dragDistance >= 5) {
        drag.hasMoved = true;
      }
      if (drag.mode === "move-window") {
        if (!drag.hasMoved) {
          updateTimelinePreview({
            selectedMonth: pointerMonth,
            viewStartMonth,
            viewWindowMonths
          });
          return;
        }
        const delta = pointerMonth - drag.startPointerMonth;
        const windowMonths = clampViewWindow(drag.startViewWindow);
        const maxStart = Math.max(0, timelineEndMonth - windowMonths + 1);
        const nextViewStartMonth = Math.max(0, Math.min(maxStart, drag.startViewStart + delta));
        updateTimelinePreview({
          selectedMonth: clampTimelineMonth(drag.startSelectedMonth + delta),
          viewStartMonth: nextViewStartMonth,
          viewWindowMonths: windowMonths
        });
        return;
      }
      if (drag.mode === "resize-start") {
        const fixedEnd = drag.startViewStart + drag.startViewWindow - 1;
        const minWindow = Math.min(12, timelineEndMonth + 1);
        const nextStart = Math.max(0, Math.min(pointerMonth, fixedEnd - minWindow + 1));
        updateTimelinePreview({
          selectedMonth: safeSelectedMonthIndex,
          viewStartMonth: nextStart,
          viewWindowMonths: clampViewWindow(fixedEnd - nextStart + 1)
        });
        return;
      }
      const minWindow = Math.min(12, timelineEndMonth + 1);
      const nextEnd = Math.max(drag.startViewStart + minWindow - 1, Math.min(timelineEndMonth, pointerMonth));
      updateTimelinePreview({
        selectedMonth: safeSelectedMonthIndex,
        viewStartMonth: Math.max(0, Math.min(drag.startViewStart, Math.max(0, timelineEndMonth - minWindow + 1))),
        viewWindowMonths: clampViewWindow(nextEnd - drag.startViewStart + 1)
      });
    },
    [
      clampViewWindow,
      monthFromTimelineClientX,
      safeSelectedMonthIndex,
      timelineEndMonth,
      updateTimelinePreview,
      viewStartForSelectedMonth,
      viewStartMonth,
      viewWindowMonths
    ]
  );
  const startTimelineDrag = (
    mode: "select" | "move-window" | "resize-start" | "resize-end",
    event: ReactPointerEvent<HTMLElement>
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const startPointerMonth = monthFromTimelineClientX(event.clientX);
    timelineDragRef.current = {
      mode,
      startPointerMonth,
      startSelectedMonth: safeSelectedMonthIndex,
      startClientX: event.clientX,
      hasMoved: false,
      startViewStart: viewStartMonth,
      startViewWindow: viewWindowMonths
    };
    const initialWindowMonths = clampViewWindow(viewWindowMonths);
    const initialSelectedMonth = mode === "select" || mode === "move-window" ? startPointerMonth : safeSelectedMonthIndex;
    const initialPreview = {
      selectedMonth: initialSelectedMonth,
      viewStartMonth: mode === "select"
        ? viewStartForSelectedMonth(initialSelectedMonth, viewStartMonth, initialWindowMonths)
        : viewStartMonth,
      viewWindowMonths: initialWindowMonths
    };
    updateTimelinePreview(initialPreview);
    if (mode === "select") {
      return;
    }
  };
  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => applyTimelineDrag(event.clientX);
    const handlePointerUp = () => {
      const preview = timelinePreviewRef.current;
      const drag = timelineDragRef.current;
      if (drag && preview) {
        const shouldKeepSelectedMonth =
          drag.mode === "resize-start" || drag.mode === "resize-end";
        const nextSelectedMonth = clampTimelineMonth(shouldKeepSelectedMonth ? drag.startSelectedMonth : preview.selectedMonth);
        onTimelineStateChange({
          selectedMonthIndex: nextSelectedMonth,
          viewStartMonth: preview.viewStartMonth,
          viewWindowMonths: clampViewWindow(preview.viewWindowMonths)
        });
      }
      timelineDragRef.current = null;
      timelinePreviewRef.current = null;
      setTimelinePreview(null);
      setTimelineHoverMonth(null);
    };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [applyTimelineDrag, clampViewWindow, onTimelineStateChange]);

  const setMonthFromInput = (value: string) => {
    const parsed = parseMonthValue(value);
    if (!parsed) return;
    const base = { year: timelineBaseDate.getFullYear(), month: timelineBaseDate.getMonth() + 1 };
    selectVisualMonth(compareMonth(parsed, base));
  };
  useEffect(() => {
    const nextSelectedMonth = clampTimelineMonth(selectedMonthIndex);
    const nextWindowMonths = clampViewWindow(viewWindowMonths);
    const nextMaxViewStartMonth = Math.max(0, timelineEndMonth - nextWindowMonths + 1);
    let nextViewStartMonth = Math.max(0, Math.min(viewStartMonth, nextMaxViewStartMonth));
    if (nextSelectedMonth < nextViewStartMonth) {
      nextViewStartMonth = Math.max(0, Math.min(nextSelectedMonth, nextMaxViewStartMonth));
    } else if (nextSelectedMonth > nextViewStartMonth + nextWindowMonths - 1) {
      nextViewStartMonth = Math.max(
        0,
        Math.min(nextSelectedMonth - nextWindowMonths + 1, nextMaxViewStartMonth)
      );
    }
    if (
      nextSelectedMonth !== selectedMonthIndex
      || nextViewStartMonth !== viewStartMonth
      || nextWindowMonths !== viewWindowMonths
    ) {
      onTimelineStateChange({
        selectedMonthIndex: nextSelectedMonth,
        viewStartMonth: nextViewStartMonth,
        viewWindowMonths: nextWindowMonths
      });
    }
  }, [
    clampViewWindow,
    onTimelineStateChange,
    selectedMonthIndex,
    timelineEndMonth,
    viewStartMonth,
    viewWindowMonths
  ]);
  useEffect(() => {
    setTimelineMarkerPulseKey((current) => current + 1);
  }, [safeSelectedMonthIndex]);
  const loanChartData = useMemo(
    () =>
      loanVisualizationSeries
        .map((item) => ({
          month: item.month,
          总贷款余额: Math.round(item.total_loan_balance),
          房贷余额: Math.round(item.home_loan_balance),
          商贷余额: Math.round(item.commercial_loan_balance),
          公积金贷余额: Math.round(item.provident_loan_balance),
          车贷余额: Math.round(item.vehicle_loan_balance),
          已有贷款余额: Math.round(item.existing_loan_balance),
          当月贷款还款: Math.round(item.total_monthly_payment),
          商贷月供: Math.round(item.commercial_monthly_payment),
          商贷额外还本: Math.round(item.commercial_extra_principal_payment ?? 0),
          公积金贷月供: Math.round(item.provident_monthly_payment),
          车贷额外还本: Math.round(item.vehicle_extra_principal_payment ?? 0),
          公积金按月抵月供: Math.round(item.provident_monthly_withdrawal_payment ?? 0),
          公积金冲本金: Math.round(item.provident_principal_offset_payment ?? 0),
          当月现金还款: Math.round(item.cash_monthly_payment)
        })),
    [loanVisualizationSeries]
  );
  const visibleLoanChartData = useMemo(
    () => loanChartData.filter((item) => item.month >= viewStartMonth && item.month <= viewEndMonth),
    [loanChartData, viewEndMonth, viewStartMonth]
  );
  const hasLoanChartActivity = loanChartData.some(
    (item) =>
      item.总贷款余额 > 0 ||
      item.房贷余额 > 0 ||
      item.车贷余额 > 0 ||
      item.已有贷款余额 > 0 ||
      item.当月贷款还款 > 0 ||
      item.当月现金还款 > 0
  );
  const providentChartData = useMemo(
    () =>
      providentVisualizationSeries
        .map((item) => ({
          month: item.month,
          公积金余额: Math.round(item.balance_end),
          ...Object.fromEntries((item.member_accounts ?? []).map((account) => [`${account.member_name}公积金余额`, Math.round(account.balance_end)])),
          当月缴存: Math.round(item.total_deposit),
          当月利息: Math.round(item.interest),
          还款支出: Math.round((item.monthly_repayment_withdrawal ?? 0) + item.loan_offset_payment),
          提取支出: Math.round(item.rent_withdrawal + item.upfront_withdrawal + item.post_transaction_withdrawal + item.agreed_withdrawal + (item.retirement_withdrawal ?? 0))
        })),
    [providentVisualizationSeries]
  );
  const visibleProvidentChartData = useMemo(
    () => providentChartData.filter((item) => item.month >= viewStartMonth && item.month <= viewEndMonth),
    [providentChartData, viewEndMonth, viewStartMonth]
  );
  const providentMemberBalanceKeys = useMemo(
    () => {
      const availableKeys = new Set(
        providentVisualizationSeries.flatMap((item) =>
          (item.member_accounts ?? []).map((account) => `${account.member_name}公积金余额`)
        )
      );
      const orderedKeys = household.members
        .map((member) => `${member.name}公积金余额`)
        .filter((key) => availableKeys.has(key));
      const extraKeys = Array.from(availableKeys).filter((key) => !orderedKeys.includes(key));
      return [...orderedKeys, ...extraKeys];
    },
    [household.members, providentVisualizationSeries]
  );
  const sortProvidentMemberAccounts = useCallback((accounts: ProvidentMemberAccountPoint[] = []) => {
    const order = new Map(household.members.map((member, index) => [member.name, index]));
    return [...accounts].sort((left, right) => {
      const leftOrder = order.get(left.member_name) ?? left.member_index ?? Number.MAX_SAFE_INTEGER;
      const rightOrder = order.get(right.member_name) ?? right.member_index ?? Number.MAX_SAFE_INTEGER;
      return leftOrder - rightOrder;
    });
  }, [household.members]);
  const selectedProvidentMemberAccounts = useMemo(
    () => sortProvidentMemberAccounts(selectedProvidentPoint?.member_accounts ?? []),
    [selectedProvidentPoint?.member_accounts, sortProvidentMemberAccounts]
  );
  const nextProvidentOffsetPoint = useMemo(
    () =>
      providentVisualizationSeries.find(
        (item) => item.month >= safeSelectedMonthIndex && ((item.monthly_repayment_withdrawal ?? 0) + item.loan_offset_payment) > 0
      ) ?? null,
    [providentVisualizationSeries, safeSelectedMonthIndex]
  );
  const providentOutflowDisplayPoint = useMemo(() => {
    const outflowPoints = providentVisualizationSeries.filter((item) => item.total_outflow > 0);
    if (outflowPoints.length === 0) return null;
    const selectedOutflow = outflowPoints.find((item) => item.month === safeSelectedMonthIndex);
    if (selectedOutflow) return selectedOutflow;
    return outflowPoints.reduce((best, item) => {
      const currentDistance = Math.abs(item.month - safeSelectedMonthIndex);
      const bestDistance = Math.abs(best.month - safeSelectedMonthIndex);
      if (currentDistance !== bestDistance) {
        return currentDistance < bestDistance ? item : best;
      }
      return item.month > safeSelectedMonthIndex && best.month < safeSelectedMonthIndex ? item : best;
    });
  }, [providentVisualizationSeries, safeSelectedMonthIndex]);
  const providentOutflowMemberAccounts = useMemo(
    () => sortProvidentMemberAccounts(providentOutflowDisplayPoint?.member_accounts ?? []),
    [providentOutflowDisplayPoint?.member_accounts, sortProvidentMemberAccounts]
  );
  const providentOutflowDisplayLabel = providentOutflowDisplayPoint
    ? formatMonthDate(timelineBaseDate, providentOutflowDisplayPoint.month)
    : "";
  const selectedMemberIncomeRows = getMemberIncomeRows(safeSelectedMonthIndex);
  const selectedTaxYear = addMonths(timelineBaseDate, safeSelectedMonthIndex).getFullYear();
  const selectedYearTaxSummary = result.tax_year_summaries?.find((item) => item.year === selectedTaxYear);
  const taxSummaryRows = selectedYearTaxSummary?.summaries ?? [];
  const annualTaxTotal = selectedYearTaxSummary?.total_tax ?? 0;
  const annualTaxableIncome = selectedYearTaxSummary?.taxable_income ?? 0;
  const annualGrossIncome = selectedYearTaxSummary?.gross_annual_income ?? 0;
  const annualNetIncome = selectedYearTaxSummary?.net_annual_income ?? 0;
  const selectedMonthTax = selectedMemberIncomeRows.reduce((sum, member) => sum + member.incomeTax, 0);
  const selectedAnnualFinancialSummary = result.annual_financial_summaries?.find(
    (item) => item.plan_variant === visualizationPlanVariant && item.year === selectedTaxYear
  );
  const selectedAnnualVisualizationDetail = annualVisualizationDetailByYear.get(selectedTaxYear);
  const selectedTaxVisualizationDetail =
    taxVisualizationDetailByMonth.get(safeSelectedMonthIndex) ??
    taxVisualizationDetailByYear.get(selectedTaxYear);
  const annualLoanPayment = selectedAnnualFinancialSummary
    ? selectedAnnualFinancialSummary.commercial_payment +
      selectedAnnualFinancialSummary.provident_payment +
      selectedAnnualFinancialSummary.vehicle_loan_payment +
      selectedAnnualFinancialSummary.existing_loan_payment +
      selectedAnnualFinancialSummary.commercial_extra_principal_payment +
      selectedAnnualFinancialSummary.vehicle_extra_principal_payment
    : 0;
  const annualPieTotal = (items: Array<{ value: number }>) =>
    items.reduce((sum, item) => sum + item.value, 0);
  const annualCashInflowData = selectedAnnualVisualizationDetail?.cash_inflow_pie ?? [];
  const annualCashOutflowData = selectedAnnualVisualizationDetail?.cash_outflow_pie ?? [];
  const annualAssetCompositionData = selectedAnnualVisualizationDetail?.liquid_asset_pie ?? [];
  const annualFixedAssetCompositionData = selectedAnnualVisualizationDetail?.fixed_asset_pie ?? [];
  const annualLoanPaymentData = selectedAnnualVisualizationDetail?.loan_payment_pie ?? [];
  const annualLoanBalanceData = selectedAnnualVisualizationDetail?.loan_balance_pie ?? [];
  const annualProvidentFlowData = selectedAnnualVisualizationDetail?.provident_flow_pie ?? [];
  const annualSocialSecurityFlowData = selectedAnnualVisualizationDetail?.social_security_inflow_pie ?? [];
  const annualSocialSecurityOutflowData = selectedAnnualVisualizationDetail?.social_security_outflow_pie ?? [];
  const annualSocialSecurityBalanceData = selectedAnnualVisualizationDetail?.social_security_balance_pie ?? [];
  const socialSecurityChartData = useMemo(
    () =>
      socialSecurityVisualizationSeries.map((item) => {
        const point: Record<string, number | string> = {
          month: item.month,
          政策账户合计: Math.round(item.total_balance_end),
          个人养老金账户: Math.round(
            backendCashflowSeries.find((row) => row.month === item.month)?.personal_pension_balance ?? 0
          ),
          养老当月缴入: Math.round(item.pension_contribution),
          养老计发支出: Math.round(item.pension_account_payout ?? 0),
          医保当月划入: Math.round(item.medical_contribution + item.medical_retiree_transfer),
          医保账户支出: Math.round(item.medical_outflow ?? 0),
          个人养老金缴费: Math.round(
            backendCashflowSeries.find((row) => row.month === item.month)?.personal_pension_contribution ?? 0
          ),
          个人养老金收益: Math.round(
            backendCashflowSeries.find((row) => row.month === item.month)?.personal_pension_return ?? 0
          ),
          账户利息: Math.round(item.pension_interest + item.medical_interest)
        };
        item.member_accounts.forEach((account) => {
          point[`${account.member_name}养老账户`] = Math.round(account.pension_balance_end);
          point[`${account.member_name}医保账户`] = Math.round(account.medical_balance_end);
        });
        return point;
      }),
    [backendCashflowSeries, socialSecurityVisualizationSeries]
  );
  const socialSecurityMemberAccountKeys = useMemo(() => {
    const availableKeys = new Set(
      socialSecurityVisualizationSeries.flatMap((item) =>
        (item.member_accounts ?? []).flatMap((account) => [
          `${account.member_name}养老账户`,
          `${account.member_name}医保账户`
        ])
      )
    );
    const orderedKeys = household.members.flatMap((member) => [
      `${member.name}养老账户`,
      `${member.name}医保账户`
    ]).filter((key) => availableKeys.has(key));
    const extraKeys = Array.from(availableKeys).filter((key) => !orderedKeys.includes(key));
    return [...orderedKeys, ...extraKeys];
  }, [household.members, socialSecurityVisualizationSeries]);
  const visibleSocialSecurityChartData = useMemo(
    () => socialSecurityChartData.filter((item) => Number(item.month) >= viewStartMonth && Number(item.month) <= viewEndMonth),
    [socialSecurityChartData, viewEndMonth, viewStartMonth]
  );
  const selectedSocialSecurityPoint = socialSecurityVisualizationByMonth.get(safeSelectedMonthIndex);
  const selectedSocialSecurityMemberAccounts = useMemo(
    () =>
      [...(selectedSocialSecurityPoint?.member_accounts ?? [])].sort((left, right) => {
        const leftOrder = household.members.findIndex((member) => member.name === left.member_name);
        const rightOrder = household.members.findIndex((member) => member.name === right.member_name);
        return (leftOrder < 0 ? left.member_index : leftOrder) - (rightOrder < 0 ? right.member_index : rightOrder);
      }),
    [household.members, selectedSocialSecurityPoint?.member_accounts]
  );
  const socialSecurityInflowPieData = effectiveMonthlyDetail.social_security_inflow_pie;
  const socialSecurityInflowPieTotal = annualPieTotal(socialSecurityInflowPieData);
  const socialSecurityOutflowPieData = effectiveMonthlyDetail.social_security_outflow_pie;
  const socialSecurityOutflowPieTotal = annualPieTotal(socialSecurityOutflowPieData);
  const selectedMonthGrossIncome = selectedMemberIncomeRows.reduce(
    (sum, member) => sum + member.grossMonthly + member.bonusMonthly + member.otherMonthly,
    0
  );
  const selectedMonthNetIncome = selectedMemberIncomeRows.reduce((sum, member) => sum + member.netMonthly, 0);
  const selectedMonthPreTaxDeductions = selectedMemberIncomeRows.reduce(
    (sum, member) => sum + member.personalSocial + member.personalHousingFund,
    0
  );
  const selectedMonthSpecialDeduction = selectedMemberIncomeRows.reduce(
    (sum, member) => sum + (member.specialDeduction ?? member.elderlyCareDeduction ?? 0),
    0
  );
  const taxChartData = useMemo(
    () =>
      taxMonthlySeries.map((item) => {
        const memberRows = item.member_points.map(taxMemberPointToIncomeRow);
        const monthPoint: Record<string, number | string> = {
          month: item.month,
          税前收入: Math.round(
            memberRows.reduce((sum, member) => sum + member.grossMonthly + member.bonusMonthly + member.otherMonthly, 0)
          ),
          税后现金入账: Math.round(memberRows.reduce((sum, member) => sum + member.netMonthly, 0)),
          当月个税: Math.round(memberRows.reduce((sum, member) => sum + member.incomeTax, 0)),
          年终奖入账: Math.round(memberRows.reduce((sum, member) => sum + member.bonusMonthly, 0))
        };
        memberRows.forEach((member) => {
          monthPoint[`${member.name}个税`] = Math.round(member.incomeTax);
        });
        return monthPoint;
      }),
    [taxMonthlySeries]
  );
  const visibleTaxChartData = useMemo(
    () => taxChartData.filter((item) => Number(item.month) >= viewStartMonth && Number(item.month) <= viewEndMonth),
    [taxChartData, viewEndMonth, viewStartMonth]
  );
  const taxMemberLineKeys = useMemo(() => {
    const availableKeys = new Set(
      taxChartData.flatMap((item) =>
        Object.keys(item).filter((key) => key.endsWith("个税") && key !== "当月个税" && Number(item[key]) > 0)
      )
    );
    const orderedKeys = household.members
      .map((member) => `${member.name}个税`)
      .filter((key) => availableKeys.has(key));
    const extraKeys = Array.from(availableKeys).filter((key) => !orderedKeys.includes(key));
    return [...orderedKeys, ...extraKeys];
  }, [household.members, taxChartData]);
  const investmentSummaryEndMonth = plan.months_to_buy ?? monthlySeries[monthlySeries.length - 1]?.month ?? 0;
  const investmentSummaryRows = monthlySeries.filter((item) => item.month <= investmentSummaryEndMonth);
  const investmentSummaryPoint =
    monthlySeries.find((item) => item.month === investmentSummaryEndMonth) ??
    investmentSummaryRows[investmentSummaryRows.length - 1] ??
    monthlySeries[monthlySeries.length - 1];
  const displayedInvestmentContribution = investmentSummaryRows.reduce(
    (sum, item) => sum + item.monthlyInvestment,
    0
  );
  const displayedInvestmentReturn = investmentSummaryRows.reduce(
    (sum, item) => sum + item.investmentReturn,
    0
  );
  const displayedInvestmentFees = investmentSummaryRows.reduce(
    (sum, item) => sum + item.monthlyInvestmentBuyFee + item.investmentSellFee,
    0
  );
  const investmentEffectAtPurchase = investmentSummaryPoint?.投资资产 ?? 0;
  const purchaseInvestmentBefore = plan.investment_balance_before_purchase ?? investmentEffectAtPurchase;
  const purchaseInvestmentSellProceeds = plan.investment_sell_proceeds_at_purchase ?? 0;
  const purchaseInvestmentSellGross = plan.investment_sell_gross_at_purchase ?? purchaseInvestmentSellProceeds;
  const purchaseInvestmentAfter = plan.investment_balance_after_purchase ?? investmentEffectAtPurchase;
  const purchaseInvestmentModeLabel = plan.investment_withdrawal_mode_label ?? "自动优化提取";
  const visualMinimumCashPoint = monthlySeries.reduce(
    (lowest, item) => (item.现金池 < lowest.现金池 ? item : lowest),
    selectedMonth
  );
  const minimumCashBalance = plan.minimum_cash_balance ?? visualMinimumCashPoint.现金池;
  const minimumCashMonth =
    plan.minimum_cash_balance_month !== undefined && plan.minimum_cash_balance_month !== null
      ? formatMonthDate(timelineBaseDate, plan.minimum_cash_balance_month)
      : visualMinimumCashPoint.name;
  const stressCashShortfall = Math.max(0, plan.cash_stress_shortfall ?? 0, -minimumCashBalance);
  const cashStressOk = plan.cash_stress_ok ?? stressCashShortfall <= 0;
  const stressCashMetricLabel = cashStressOk ? "压力最低现金" : "压力现金缺口";
  const stressCashMetricValue = cashStressOk ? money(minimumCashBalance) : money(stressCashShortfall);
  const stressCashSummary = cashStressOk
    ? `压力情景下最低现金出现在 ${minimumCashMonth}，仍保留 ${money(minimumCashBalance)}。`
    : `压力情景下 ${minimumCashMonth} 会出现 ${money(stressCashShortfall)} 资金缺口；现金不能为负，这表示该方案需要延后买入、降低目标、增加可用现金或重新调整贷款结构。`;
  const purchaseTimelineText =
    plan.months_to_buy === null
      ? "暂无法达到购房现金要求"
      : cashStressOk
        ? `${purchaseYearText} 可执行购房`
        : `${purchaseYearText} 交易现金可达，但压力情景有 ${money(stressCashShortfall)} 现金缺口`;
  const investmentSummaryText =
    monthlyInvestmentSetting > 0
      ? `当前理财方案以 ${money(monthlyInvestmentSetting)}/月作为基础定投上限、${percent(annualReturn)} 年化测算；买入费率 ${percent(investmentBuyFeeRate)}，卖出费率 ${percent(investmentSellFeeRate)}。实际每月投入由后端按现金安全垫和当月结余动态执行，超过安全垫的存量现金会按滚动节奏转入投资账户，收益留在投资账户里继续复利。`
      : "当前理财方案未设置月定投或选择只放现金，因此曲线主要体现现有投资账户的收益假设。";
  const advisorTone = isBaselineVisualization
    ? (selectedMonth.monthlyCashDelta >= 0 && selectedMonth.现金池 >= plan.required_liquidity_reserve ? "good" : "warn")
    : cashStressOk && plan.liquidity_ok && plan.post_purchase_cash_flow >= 0
    ? "good"
    : !cashStressOk || plan.post_purchase_cash_flow < 0
      ? "bad"
      : "warn";
  const advisorTitle =
    isBaselineVisualization
      ? "当前展示家庭财务基线"
      : advisorTone === "good"
      ? "这套方案可以进入细化比较"
      : advisorTone === "bad"
        ? "这套方案需要先修现金安全"
        : "这套方案可执行但要留意压力点";
  const advisorSummary =
    isBaselineVisualization
      ? "当前没有启用购房目标，后端仍按统一账本推演家庭收入、支出、贷款、车辆、公积金、养老医保、理财和校准事件；这里先用于观察不买房基线下账户会怎样变化。"
      : plan.months_to_buy === null
      ? `按当前收入、资产、理财和贷款策略，30 年内仍不能覆盖 ${scenario.name} 的交易现金要求。优先动作是降低房源总价、延后装修或提高可动用现金。`
      : advisorTone === "good"
        ? `${scenario.name} 采用「${plan.variant}」时，预计 ${formatMonthDate(timelineBaseDate, plan.months_to_buy)} 可以买入；交易后现金和买后月结余都留在安全区，适合继续比较居住体验、通勤和房源本身。`
        : advisorTone === "bad"
          ? `${scenario.name} 采用「${plan.variant}」时，时间上可能接近目标，但现金账户在压力情景下不够稳。先不要只看可买时间，应优先调整首付、商贷量、买车节奏或理财变现。`
          : `${scenario.name} 采用「${plan.variant}」时能形成方案，但交易现金、月结余或债务收入比里至少有一项偏紧，适合作为备选而不是默认执行。`;
  const advisorActions = isBaselineVisualization ? [
    `当前查看 ${selectedMonth.name}，当月现金净变化 ${money(selectedMonth.monthlyCashDelta)}。`,
    `月末现金账户 ${money(selectedMonth.现金池)}，投资账户 ${money(selectedMonth.投资资产)}，流动资产 ${money(selectedMonth.流动资产)}。`,
    `贷款余额 ${money(selectedTotalLoanBalance)}，公积金账户 ${money(selectedMonth.公积金余额)}，政策账户 ${money(selectedMonth.socialSecurityAccountBalance)}。`
  ] : [
    plan.months_to_buy === null
      ? "把候选房源总价、装修现金或首付要求往下调，先让方案进入可达区间。"
      : `把 ${formatMonthDate(timelineBaseDate, plan.months_to_buy)} 当作当前计划锚点，观察这个月的现金流和资产构成。`,
    !cashStressOk
      ? `压力现金缺口约 ${money(stressCashShortfall)}，优先延后购房或减少同步买车支出。`
      : `压力最低现金仍有 ${money(minimumCashBalance)}，下一步主要比较等待时间和幸福指数。`,
    plan.post_purchase_cash_flow < 0
      ? `买后自由现金流为负 ${money(Math.abs(plan.post_purchase_cash_flow))}，需要减少月供、降低用车成本或提高收入阶段。`
      : `买后自由现金流结余约 ${money(plan.post_purchase_cash_flow)}，贷后公积金策略为「${providentStrategyLabel(plan)}」，可继续评估装修和车贷节奏。`
  ];
  const advisorEvidenceItems = isBaselineVisualization ? [
    {
      label: "测算范围",
      value: "未启用购房目标，不生成房贷和购房交易；家庭财务仍按统一账本生成月度现金流、账户快照和年度摘要。"
    },
    {
      label: "当前月份",
      value: `${selectedMonth.name} 现金净变化 ${money(selectedMonth.monthlyCashDelta)}，月末现金账户 ${money(selectedMonth.现金池)}。`
    },
    {
      label: "资产账户",
      value: `投资账户 ${money(selectedMonth.投资资产)}，固定资产 ${money(selectedMonth.固定资产)}，净资产 ${money(selectedMonth.净资产)}。`
    },
    {
      label: "债务和政策账户",
      value: `贷款余额 ${money(selectedTotalLoanBalance)}，公积金账户 ${money(selectedMonth.公积金余额)}，养老医保账户 ${money(selectedMonth.socialSecurityAccountBalance)}。`
    }
  ] : [
    {
      label: "买入时间",
      value: plan.months_to_buy === null
        ? `30 年内暂未覆盖 ${scenario.name} 的交易现金要求。`
        : `${formatMonthDate(timelineBaseDate, plan.months_to_buy)} 可进入交易，距今约 ${plan.years_to_buy ?? "超过30"} 年。`
    },
    {
      label: "交易现金",
      value: `当天自备资金 ${money(requiredCashAfterPf)}，交易后现金 ${money(plan.cash_after_transaction)}，安全垫目标 ${money(plan.required_liquidity_reserve)}。`
    },
    {
      label: "压力现金",
      value: stressCashSummary
    },
    {
      label: "月供压力",
      value: `买后自由现金流 ${money(plan.post_purchase_cash_flow)}，负债收入比 ${percent(plan.debt_to_income_ratio)}；当月贷款还款会继续按房贷、车贷和已有贷款拆分查看。`
    },
    {
      label: "资产与体验",
      value: `幸福指数 ${plan.happiness_score.toFixed(1)} / 10；理财按 ${percent(annualReturn)} 年化、买入费 ${percent(investmentBuyFeeRate)}、卖出费 ${percent(investmentSellFeeRate)} 推演，买房时投资账户保留约 ${money(purchaseInvestmentAfter)}。`
    }
  ];
  const selectedFamilySupportAmount = familySupportAmount(plan);
  const selectedFamilySupportLabel = familySupportLabel(plan);
  const transactionTaxAndFees = Math.max(0, plan.upfront_cash_required - plan.planned_down_payment);
  const transactionUseBreakdown = [
    { name: "首付", value: plan.planned_down_payment, color: visualColors.cash },
    { name: "交易税费与杂费", value: transactionTaxAndFees, color: visualColors.expense },
  ].filter((item) => item.value > 1);
  const transactionFundingBreakdown = [
    { name: "家庭现金与投资变现承担", value: requiredCashAfterPf, color: visualColors.cash },
    { name: "本人公积金首付抵扣", value: plan.provident_upfront_extractable, color: visualColors.provident },
    { name: selectedFamilySupportLabel || "亲属首付支持", value: selectedFamilySupportAmount, color: visualColors.safe }
  ].filter((item) => item.value > 1);
  const attributionPieBlocks = [
    { title: "买房当天现金用途", data: transactionUseBreakdown },
    { title: "买房当天资金来源", data: transactionFundingBreakdown }
  ];
  const purchaseMonthForImpact = plan.months_to_buy ?? null;
  const monthsBeforeHomePurchase = purchaseMonthForImpact === null
    ? monthlySeries
    : monthlySeries.filter((item) => item.month <= purchaseMonthForImpact);
  const vehicleCashBeforeHome = monthsBeforeHomePurchase.reduce(
    (sum, item) =>
      sum +
      Math.max(0, item.carDownPaymentCashOut) +
      Math.max(0, item.secondCarDownPaymentCashOut) +
      Math.max(0, item.firstCarLoanPayment) +
      Math.max(0, item.secondCarLoanPayment) +
      Math.max(0, item.firstCarEnergyCost) +
      Math.max(0, item.firstCarInsuranceCost) +
      Math.max(0, item.firstCarMaintenanceCost) +
      Math.max(0, item.firstCarParkingCost) +
      Math.max(0, item.vehiclePlateRentalPayment) +
      Math.max(0, item.noCarCommuteCost),
    0
  );
  const vehicleDownPaymentBeforeHome = monthsBeforeHomePurchase.reduce(
    (sum, item) => sum + Math.max(0, item.carDownPaymentCashOut) + Math.max(0, item.secondCarDownPaymentCashOut),
    0
  );
  const purchaseMonthLoanPoint = purchaseMonthForImpact === null ? null : loanVisualizationByMonth.get(purchaseMonthForImpact);
  const purchaseMonthVehicleLoanBalance = purchaseMonthLoanPoint?.vehicle_loan_balance ?? 0;
  const purchaseMonthVehiclePayment = purchaseMonthLoanPoint?.vehicle_monthly_payment ?? 0;
  const vehicleDemandCount = household.car_plan.vehicle_plans?.length ?? 0;
  const carHomeImpactItems = [
    {
      label: vehicleDemandCount > 0 ? "购房前买车现金占用" : "无车通勤现金消耗",
      value: money(vehicleCashBeforeHome),
      detail: vehicleDemandCount > 0
        ? `其中车辆首付 ${money(vehicleDownPaymentBeforeHome)}，其余为车贷、能源、保险、保养、停车和租牌等上牌现金支出。`
        : "未配置买车需求，购房前按无车通勤成本进入现金流。"
    },
    {
      label: "购房月车贷余额",
      value: money(purchaseMonthVehicleLoanBalance),
      detail: purchaseMonthForImpact === null ? "当前购房月暂不可达，先按完整测算期观察车辆债务。" : `${formatMonthDate(timelineBaseDate, purchaseMonthForImpact)} 的车贷余额。`
    },
    {
      label: "购房月车贷月供",
      value: money(purchaseMonthVehiclePayment),
      detail: "会和房贷、已有贷款一起压缩买后自由现金流。"
    },
    {
      label: "策略口径",
      value: vehicleDemandCount > 0 ? `${vehicleDemandCount} 个车辆需求` : "不买车模式",
      detail: vehicleDemandCount > 0 ? "已采用的买车策略会进入购房前现金池、贷款余额和事件时间线。" : "当前只考虑无车通勤成本，不形成车贷余额。"
    }
  ];
  const keyAttributionItems = [
    {
      title: "买车怎样影响买房",
      body: vehicleDemandCount > 0
        ? `已配置 ${vehicleDemandCount} 个车辆需求。购房前车辆相关现金占用约 ${money(vehicleCashBeforeHome)}，其中首付约 ${money(vehicleDownPaymentBeforeHome)}；购房月车贷余额约 ${money(purchaseMonthVehicleLoanBalance)}、车贷月供约 ${money(purchaseMonthVehiclePayment)}。这些会直接推迟现金池达标时间，并和房贷一起影响买后月结余。`
        : `当前是不买车模式。系统不会生成车贷余额，但会把无车通勤成本计入每月现金流；如果后续添加车辆需求，车源首付、车贷、保险保养和停车电费都会重新进入购房策略推演。`
    },
    {
      title: "买房当天需要准备什么钱",
      body: `买房当天先看现金用途：首付 ${money(plan.planned_down_payment)}、税费杂费约 ${money(transactionTaxAndFees)}；独立装修事件不计入当天现金。再看资金来源：本人公积金首付抵扣 ${money(plan.provident_upfront_extractable)}${familySupportPhrase(plan)}，剩余由家庭现金和投资变现承担。`
    },
    {
      title: "贷款扣款要按月份看",
      body: usesMonthlyProvidentRepayment
        ? `房贷、车贷和已有贷款都会进入“贷款余额与月供”。当前公积金策略为「${providentStrategyLabel(plan)}」，后端按月从公积金账户余额优先抵扣公积金贷月供，不足部分才进入银行卡现金还款；具体每个月的扣款结构已经移到贷款图下方的月度饼图。`
        : `房贷、车贷和已有贷款都会进入“贷款余额与月供”。当前公积金策略为「${providentStrategyLabel(plan)}」，半年度冲本金只在约定月份从公积金账户集中冲抵，非冲抵月仍按合同从银行卡扣公积金贷月供；具体每个月的扣款结构已经移到贷款图下方的月度饼图。`
    },
    {
      title: "还款方式怎样影响还清速度",
      body: [plan.commercial_repayment_advice, plan.provident_repayment_advice].filter(Boolean).join(" ") || "本方案没有形成需要比较的住房贷款。"
    },
    {
      title: "理财对买房时间的影响",
      body: `截至买房月，后端推演定投本金约 ${money(displayedInvestmentContribution)}、投资收益约 ${money(displayedInvestmentReturn)}。当前买房动用投资策略为“${purchaseInvestmentModeLabel}”：交易前投资账户约 ${money(purchaseInvestmentBefore)}，交易月卖出本金约 ${money(purchaseInvestmentSellGross)}、到账约 ${money(purchaseInvestmentSellProceeds)}，交易后保留投资约 ${money(purchaseInvestmentAfter)}${(plan.investment_reserve_target ?? 0) > 0 ? `（本候选保留目标 ${money(plan.investment_reserve_target ?? 0)}）` : ""}。保留的投资资产不等同于现金安全垫，仍需单独满足现金账户要求。`
    },
    {
      title: "幸福指数为什么不是只看钱",
      body: `幸福指数同时看居住、通勤、教育、买车对买房窗口的影响、交易当天现金、买后安全垫、投资连续性、月结余、负债压力、贷款利息、现金缺口、等待时间、装修和压力韧性；所以更快买入不一定更高分，现金更稳也不一定代表居住体验最好。`
    }
  ];
  const selectChartMonth = (state: unknown) => {
    const chartState = state as
      | {
          activeLabel?: unknown;
          activePayload?: Array<{ payload?: { month?: unknown } }>;
          activeTooltipIndex?: unknown;
        }
      | undefined;
    const payloadMonth = chartState?.activePayload?.find((item) => typeof item.payload?.month === "number")?.payload?.month;
    const labelMonth =
      typeof chartState?.activeLabel === "number"
        ? chartState.activeLabel
        : typeof chartState?.activeLabel === "string"
          ? Number(chartState.activeLabel)
          : null;
    const rawMonth =
      typeof payloadMonth === "number"
        ? payloadMonth
        : labelMonth !== null
          ? labelMonth
          : typeof chartState?.activeTooltipIndex === "number"
            ? viewStartMonth + chartState.activeTooltipIndex
            : null;

    if (typeof rawMonth === "number" && Number.isFinite(rawMonth)) {
      selectVisualMonth(rawMonth);
    }
  };
  const selectedMonthReferenceLine = (yAxisId?: string) => (
    <ReferenceLine
      x={safeSelectedMonthIndex}
      yAxisId={yAxisId}
      stroke="var(--chart-danger)"
      strokeWidth={1.7}
      strokeOpacity={0.78}
      strokeDasharray="5 5"
      ifOverflow="extendDomain"
    />
  );
  const cashFlowData = effectiveMonthlyDetail.cash_flow_items.map((item) => ({
    name: item.name,
    amount: Math.round(item.amount ?? item.value),
    kind: item.kind ?? "expense"
  }));
  const cashFlowChartHeight = Math.max(360, cashFlowData.length * 28);
  const cashFlowColor = (kind: string) => {
    if (kind === "income") return visualColors.cash;
    if (kind === "asset") return visualColors.investment;
    if (kind === "deduction") return visualColors.deduction;
    if (kind === "result") return selectedMonth.monthlyCashDelta >= 0 ? visualColors.safe : visualColors.danger;
    return visualColors.expense;
  };
  const selectedMonthDrivers = effectiveMonthlyDetail.cash_flow_drivers.map((item) => ({
    name: item.name,
    amount: Math.round(item.amount ?? item.value),
    kind: item.kind ?? "expense"
  }));
  const monthAdvisorText =
    effectiveMonthlyDetail.advisor_text ??
    (selectedMonth.monthlyCashDelta >= 0
      ? `${selectedMonth.name} 现金净流入 ${money(selectedMonth.monthlyCashDelta)}。`
      : `${selectedMonth.name} 现金净流出 ${money(Math.abs(selectedMonth.monthlyCashDelta))}。`);
  const incomeLegendData = effectiveMonthlyDetail.income_legend;
  const incomePieData = effectiveMonthlyDetail.income_pie;
  const expensePieData = effectiveMonthlyDetail.expense_pie;
  const selectedLoanPaymentPieData = effectiveMonthlyDetail.loan_payment_pie;
  const sumPieValues = (items: Array<{ value: number }>) =>
    items.reduce((sum, item) => sum + Math.max(0, Number(item.value) || 0), 0);
  const annualTaxMemberPieData =
    selectedTaxVisualizationDetail?.annual_tax_member_pie ??
    taxVisualizationDetailByYear.get(selectedTaxYear)?.annual_tax_member_pie ??
    [];
  const annualTaxTypePieData =
    selectedTaxVisualizationDetail?.annual_tax_type_pie ??
    taxVisualizationDetailByYear.get(selectedTaxYear)?.annual_tax_type_pie ??
    [];
  const currentMonthTaxPieData = selectedTaxVisualizationDetail?.monthly_tax_member_pie ?? [];
  const currentMonthDeductionPieData = selectedTaxVisualizationDetail?.monthly_deduction_pie ?? [];
  const taxPieBlocks = [
    {
      title: "当月个税成员构成",
      period: selectedMonth.name,
      data: currentMonthTaxPieData,
      total: sumPieValues(currentMonthTaxPieData),
      emptyText: "当前月份没有个税扣缴。"
    },
    {
      title: "当月税前扣除构成",
      period: selectedMonth.name,
      data: currentMonthDeductionPieData,
      total: sumPieValues(currentMonthDeductionPieData),
      emptyText: "当前月份没有社保、公积金或专项附加扣除。"
    },
    {
      title: "年度个税成员构成",
      period: "年度",
      data: annualTaxMemberPieData,
      total: sumPieValues(annualTaxMemberPieData),
      emptyText: "当前年度没有可展示的成员个税。"
    },
    {
      title: "年度个税税种构成",
      period: "年度",
      data: annualTaxTypePieData,
      total: sumPieValues(annualTaxTypePieData),
      emptyText: "当前年度没有可拆分的工资薪金或年终奖个税。"
    }
  ];
  const pieTooltipFormatter = (value: unknown) => money(Number(value));
  const renderAnnualPieBlock = (
    title: string,
    period: string,
    data: Array<{ name: string; value: number }>,
    emptyText: string,
    paletteOffset = 0
  ) => {
    const total = annualPieTotal(data);
    return (
      <div className="cash-flow-pie" key={title}>
        <div className="pie-heading">
          <strong>{title}</strong>
          <span>
            <small>{period}</small>
            <b>{money(total)}</b>
          </span>
        </div>
        {data.length > 0 ? (
          <div className="pie-layout">
            <ResponsiveContainer width="100%" height={190}>
              <PieChart>
                <Tooltip formatter={pieTooltipFormatter} />
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                  {data.map((item) => (
                    <Cell key={`${title}-${item.name}`} fill={stablePieColor(item.name)} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pie-legend">
              {data.map((item) => (
                <span key={`${title}-legend-${item.name}`}>
                  <i style={{ background: stablePieColor(item.name) }} />
                  <em>{item.name}</em>
                  <strong>{money(item.value)}</strong>
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="field-hint">{emptyText}</p>
        )}
      </div>
    );
  };
  const cashFlowTooltipFormatter = (value: unknown, _name: unknown, item: { payload?: { name?: string } }) => [
    money(Number(value)),
    item.payload?.name ?? "金额"
  ];
  const providentInflowPieData = effectiveMonthlyDetail.provident_inflow_pie;
  const providentOutflowPieData = effectiveMonthlyDetail.provident_outflow_pie;
  const incomePieTotal = sumPieValues(incomePieData);
  const expensePieTotal = sumPieValues(expensePieData);
  const selectedLoanPaymentPieTotal = sumPieValues(selectedLoanPaymentPieData);
  const providentInflowPieTotal = sumPieValues(providentInflowPieData);
  const providentOutflowPieTotal = sumPieValues(providentOutflowPieData);
  const cashFlowDetailGroups: Array<{
    title: string;
    items: VisualizationBreakdownItem[];
  }> = [
    {
      title: "现金流入",
      items: effectiveMonthlyDetail.cash_flow_items.filter((item) => item.kind === "income")
    },
    {
      title: "现金流出",
      items: effectiveMonthlyDetail.cash_flow_items.filter((item) => item.kind === "expense")
    },
    {
      title: "账户转移与收益",
      items: effectiveMonthlyDetail.cash_flow_items.filter((item) => item.kind === "asset" || item.kind === "deduction")
    }
  ].filter((group) => group.items.length > 0);
  const cashFlowResultItems = effectiveMonthlyDetail.cash_flow_items.filter((item) => item.kind === "result");
  const selectedMonthExplanationItems = effectiveMonthlyDetail.explanation_items;
  const happinessData = availablePlans.map((item) => ({
    name: item.variant,
    幸福指数: Number(item.happiness_score.toFixed(1)),
    selected: item.variant === plan.variant
  }));
  const happinessCurveData = monthlySeries.map((item) => ({
    month: item.month,
    name: item.name,
    幸福指数: Number((item.happinessScore ?? plan.happiness_score).toFixed(2))
  }));
  const timelineItems = (result.plan_events ?? [])
    .filter((item) => item.plan_variant === visualizationPlanVariant)
    .sort((left, right) => left.month - right.month || left.title.localeCompare(right.title, "zh-Hans-CN"))
    .map((item) => ({
      month: item.month,
      label: `${formatMonthDate(timelineBaseDate, item.month)} · ${item.title}`,
      value: item.detail,
      severity: item.severity,
      calibrationSource: item.calibration_source
    }));

  return (
    <>
      <section className={`advisor-panel ${advisorTone}`}>
        <div>
          <PanelTitle icon={<ShieldCheck size={18} />} title="顾问摘要" compact />
          <h3>{advisorTitle}</h3>
          <p className="advisor-lead">{advisorSummary}</p>
          <details className="details-panel advisor-details">
            <summary>
              <span>查看顾问判断依据</span>
              <small>展开后按时间、现金、月供、资产体验拆开看</small>
            </summary>
            <div className="advisor-evidence-list">
              {advisorEvidenceItems.map((item) => (
                <div className="advisor-evidence-item" key={item.label}>
                  <strong>{item.label}</strong>
                  <span>{item.value}</span>
                </div>
              ))}
            </div>
          </details>
        </div>
        <div className="advisor-actions">
          {advisorActions.map((action) => (
            <span key={action}>
              <CheckCircle2 size={15} />
              {action}
            </span>
          ))}
        </div>
      </section>

      {isBaselineVisualization ? (
        <div className="metric-grid visual-strategy-metrics">
          <Metric label="当前查看月份" value={selectedMonth.name} />
          <Metric label="月末现金账户" value={money(selectedMonth.现金池)} tone={selectedMonth.现金池 >= plan.required_liquidity_reserve ? "good" : "warn"} />
          <Metric label="月末投资账户" value={money(selectedMonth.投资资产)} />
          <Metric label="流动资产" value={money(selectedMonth.流动资产)} />
          <Metric label="固定资产" value={money(selectedMonth.固定资产)} />
          <Metric label="贷款余额" value={money(selectedTotalLoanBalance)} tone={selectedTotalLoanBalance > 0 ? "warn" : "good"} />
          <Metric label="当月现金净变化" value={money(selectedMonth.monthlyCashDelta)} tone={selectedMonth.monthlyCashDelta >= 0 ? "good" : "warn"} />
          <Metric label="现金安全垫目标" value={money(plan.required_liquidity_reserve)} />
        </div>
      ) : (
        <>
          <div className="metric-grid visual-strategy-metrics">
            <Metric label="计划买入月份" value={purchaseYearText} tone={plan.months_to_buy === null ? "bad" : "good"} />
            <Metric label="买房当天自备资金" value={money(requiredCashAfterPf)} />
            <Metric label="买房当天剩余现金" value={money(plan.cash_after_transaction)} tone={plan.liquidity_ok ? "good" : "warn"} />
            <Metric label="现金安全垫目标" value={money(plan.required_liquidity_reserve)} />
            <Metric label={stressCashMetricLabel} value={stressCashMetricValue} tone={cashStressOk ? "good" : "bad"} />
            <Metric label="买后月度自由结余" value={money(plan.post_purchase_cash_flow)} tone={plan.post_purchase_cash_flow >= 0 ? "good" : "bad"} />
            <Metric label="装修资金" value={renovationTimingText} tone={plan.months_to_renovation === null ? "warn" : "good"} />
            <Metric label="负债收入比" value={percent(plan.debt_to_income_ratio)} tone={plan.debt_to_income_ratio > 0.5 ? "bad" : "warn"} />
            <Metric label="幸福指数" value={`${plan.happiness_score.toFixed(1)} / 10`} tone={plan.happiness_score >= 7 ? "good" : plan.happiness_score >= 5 ? "warn" : "bad"} />
            <Metric label="截至买房月投入本金" value={money(displayedInvestmentContribution)} />
            <Metric label="截至买房月投资收益" value={money(displayedInvestmentReturn)} tone={displayedInvestmentReturn >= 0 ? "good" : "warn"} />
            <Metric label="交易手续费" value={money(displayedInvestmentFees)} tone={displayedInvestmentFees > 0 ? "warn" : undefined} />
          </div>
          <p className={cashStressOk ? "field-hint" : "field-hint danger-text"}>
            {stressCashSummary}
          </p>
        </>
      )}
      {visualizationVariantMismatch ? (
        <p className="field-hint">
          账户曲线正在使用本次计算生成的「{visualizationPlanVariant}」账本；当前策略方案「{plan.variant}」刷新完成后会自动对齐。
        </p>
      ) : null}

      {!isBaselineVisualization ? (
      <section className="visual-story-block key-attribution-block">
        <div className="strategy-panel-head">
          <PanelTitle icon={<WalletCards size={18} />} title="关键决策因素" compact />
          <span>先看资金结构和买车影响；文字解释默认收起，需要时再展开。</span>
        </div>
        <div className="key-attribution-layout">
          <article className="funding-structure-card">
            <div className="card-mini-head">
              <strong>购房资金结构</strong>
              <span>{money(scenario.total_price)}</span>
            </div>
            <div className="loan-stack" aria-label="购房资金结构">
              <span
                className="down-payment"
                style={{ width: `${Math.max(0, (plan.planned_down_payment / scenario.total_price) * 100)}%` }}
              />
              <span
                className="provident-loan"
                style={{ width: `${Math.max(0, (plan.provident_loan_amount / scenario.total_price) * 100)}%` }}
              />
              <span
                className="commercial-loan"
                style={{ width: `${Math.max(0, (plan.commercial_loan_amount / scenario.total_price) * 100)}%` }}
              />
            </div>
            <div className="loan-legend compact-loan-legend">
              <span><i className="down-payment" />首付 {money(plan.planned_down_payment)}</span>
              <span><i className="provident-loan" />公积金贷 {money(plan.provident_loan_amount)} · {plan.provident_loan_years} 年 · {repaymentMethodLabels[plan.provident_repayment_method]}</span>
              <span><i className="commercial-loan" />商贷 {money(plan.commercial_loan_amount)} · {plan.commercial_loan_years} 年 · {repaymentMethodLabels[plan.commercial_repayment_method]}</span>
            </div>
          </article>
          <article className="car-home-impact-card">
            <div className="card-mini-head">
              <strong>买车对买房的影响</strong>
              <span>{vehicleDemandCount > 0 ? "已纳入策略" : "不买车模式"}</span>
            </div>
            <div className="car-home-impact-grid">
              {carHomeImpactItems.map((item) => (
                <span key={item.label}>
                  <small>{item.label}</small>
                  <strong>{item.value}</strong>
                  <em>{item.detail}</em>
                </span>
              ))}
            </div>
          </article>
        </div>
        <div className="attribution-pies">
          {attributionPieBlocks.map((pie) => {
            const total = pie.data.reduce((sum, item) => sum + item.value, 0);
            return (
              <div className="cash-flow-pie attribution-pie" key={pie.title}>
                <div className="pie-heading">
                  <strong>{pie.title}</strong>
                  <span>
                    <small>总量</small>
                    <b>{money(total)}</b>
                  </span>
                </div>
                {pie.data.length > 0 ? (
                  <div className="pie-layout compact-pie-layout">
                    <ResponsiveContainer width="100%" height={180}>
                      <PieChart>
                        <Tooltip formatter={pieTooltipFormatter} />
                        <Pie data={pie.data} dataKey="value" nameKey="name" innerRadius={40} outerRadius={64} paddingAngle={2}>
                          {pie.data.map((item) => (
                            <Cell key={`${pie.title}-${item.name}`} fill={stablePieColor(item.name)} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pie-legend">
                      {pie.data.map((item) => (
                        <span key={`${pie.title}-legend-${item.name}`}>
                          <i style={{ background: stablePieColor(item.name) }} />
                          <em>{item.name}</em>
                          <strong>{money(item.value)}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="field-hint">当前方案没有可展示的{pie.title}。</p>
                )}
              </div>
            );
          })}
        </div>
        <details className="advisor-details attribution-details">
          <summary>
            <span>展开顾问文字解释</span>
            <small>包含买车、首付、贷款、理财和幸福指数的详细说明</small>
          </summary>
          <div className="attribution-grid">
            {keyAttributionItems.map((item) => (
              <article key={item.title}>
                <strong>{item.title}</strong>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </details>
      </section>
      ) : null}

      <section className="linked-month-panel">
        <div className="visual-control-header">
          <PanelTitle icon={<CalendarClock size={18} />} title="联动月份查看" compact />
          <p>{monthAdvisorText}</p>
        </div>
        <div className="month-control-grid visual-month-controls">
          <label className="month-picker selected-month-picker">
            <span>查看月份</span>
            <div className="month-picker-row">
              <input
                type="month"
                min={timelineStartInputValue}
                max={timelineEndInputValue}
                value={selectedMonthInputValue}
                aria-label={`查看月份 ${selectedMonth.name}`}
                onInput={(event) => setMonthFromInput(event.currentTarget.value)}
                onChange={(event) => setMonthFromInput(event.target.value)}
              />
            </div>
          </label>
          <div className="timeline-window-picker">
            <div className="timeline-window-meta">
              <span>拖动蓝色窗口调整曲线范围，拖两侧把手改变窗口大小；点击带刻度的时间轴切换查看月份。</span>
              <strong>{currentViewLabel}</strong>
            </div>
            <div className="timeline-scale" aria-hidden="true">
              {timelineTicks.map((tick) => (
                <span key={tick.month} style={{ left: `${tick.left}%` }}>
                  {tick.label}
                </span>
              ))}
            </div>
            <div
              className={`timeline-rail ${timelinePreview ? "is-dragging" : ""}`}
              ref={timelineRailRef}
              role="slider"
              tabIndex={0}
              aria-label="联动月份时间轴"
              aria-valuemin={0}
              aria-valuemax={timelineEndMonth}
              aria-valuenow={safeSelectedMonthIndex}
              onPointerDown={(event) => startTimelineDrag("select", event)}
              onPointerMove={(event) => {
                if (!timelineDragRef.current) {
                  setTimelineHoverMonth(monthFromTimelineClientX(event.clientX));
                }
              }}
              onPointerLeave={() => {
                if (!timelineDragRef.current) {
                  setTimelineHoverMonth(null);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") selectVisualMonth(safeSelectedMonthIndex - 1);
                if (event.key === "ArrowRight") selectVisualMonth(safeSelectedMonthIndex + 1);
                if (event.key === "Home") selectVisualMonth(0);
                if (event.key === "End") selectVisualMonth(timelineEndMonth);
              }}
            >
              <div className="timeline-tick-layer" aria-hidden="true">
                {timelineMinorTicks.map((tick) => (
                  <i className="minor" key={`minor-tick-${tick.month}`} style={{ left: `${tick.left}%` }} />
                ))}
                {timelineTicks.map((tick) => (
                  <i key={`tick-${tick.month}`} style={{ left: `${tick.left}%` }} />
                ))}
              </div>
              <div
                className="timeline-window-band"
                style={{ left: `${timelineWindowStartPercent}%`, width: `${timelineWindowWidthPercent}%` }}
                onPointerDown={(event) => startTimelineDrag("move-window", event)}
              >
                <button
                  type="button"
                  className="timeline-window-handle start"
                  aria-label="调整曲线窗口起点"
                  onPointerDown={(event) => startTimelineDrag("resize-start", event)}
                />
                <span className="timeline-window-fill" />
                <button
                  type="button"
                  className="timeline-window-handle end"
                  aria-label="调整曲线窗口终点"
                  onPointerDown={(event) => startTimelineDrag("resize-end", event)}
                />
              </div>
              <button
                type="button"
                className="timeline-selected-marker"
                style={{ left: `${timelineSelectedPercent}%` }}
                aria-label={`当前查看月份 ${selectedMonth.name}`}
                onPointerDown={(event) => startTimelineDrag("select", event)}
              >
                <span className="timeline-selected-marker-core" key={timelineMarkerPulseKey} />
              </button>
              {timelineFocusMonth !== null ? (
                <div
                  className="timeline-focus-label"
                  style={{ left: `${timelineFocusPercent}%` }}
                  aria-hidden="true"
                >
                  <strong>{timelineFocusLabel}</strong>
                  <span>{timelinePreview ? "拖动预览" : "准备查看"}</span>
                </div>
              ) : null}
            </div>
          </div>
        </div>
        <div className="month-driver-panel">
          <div className="month-driver-head">
            <strong>当月关键变化</strong>
            <span>随查看月份联动</span>
          </div>
          <div className="month-driver-list">
            {selectedMonthDrivers.map((item) => (
              <span className={item.amount >= 0 ? "positive" : "negative"} key={item.name}>
                <em>{item.name}</em>
                <strong>{money(item.amount)}</strong>
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="chart-block tax-visual-chart">
        <div className="strategy-panel-head">
          <PanelTitle icon={<CircleDollarSign size={18} />} title="税务与工资扣缴" compact />
          <span>把工资从税前到税后拆开看；个人社保、公积金和专项扣除只影响计税口径，不再混进家庭支出饼图。</span>
        </div>
        <div className="tax-kpi-grid">
          <Metric label={`${selectedMonth.name} 个税`} value={money(selectedMonthTax)} />
          <Metric label={`${selectedMonth.name} 税前收入`} value={money(selectedMonthGrossIncome)} />
          <Metric label={`${selectedMonth.name} 税后现金入账`} value={money(selectedMonthNetIncome)} />
          <Metric label={`${selectedMonth.name} 社保公积金个人扣缴`} value={money(selectedMonthPreTaxDeductions)} />
          <Metric label={`${selectedMonth.name} 专项附加扣除`} value={money(selectedMonthSpecialDeduction)} />
          <Metric label="年度个税合计" value={money(annualTaxTotal)} />
        </div>
        <div className="tax-chart-grid">
          <div className="tax-trend-panel">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart
                data={visibleTaxChartData}
                onClick={selectChartMonth}
                margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis {...chartXAxisProps} />
                <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
                <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
                <Legend verticalAlign="top" height={30} iconType="line" />
                {selectedMonthReferenceLine()}
                <Line type="monotone" dataKey="税前收入" stroke={visualColors.baseline} strokeWidth={2.2} dot={false} />
                <Line type="monotone" dataKey="税后现金入账" stroke={visualColors.cash} strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="当月个税" stroke={visualColors.deduction} strokeWidth={2.2} dot={false} />
                <Line type="monotone" dataKey="年终奖入账" stroke={visualColors.warning} strokeWidth={2} strokeDasharray="5 4" dot={false} />
                {taxMemberLineKeys.map((key, index) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={stablePieColor(key, index + 5)}
                    strokeWidth={1.7}
                    strokeDasharray="3 5"
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <p className="field-hint">
              税务曲线跟随上方月份窗口。年终奖一次性发放时会在发放月入账并触发对应税务；按月均摊发放时会进入每月工资薪金累计预扣，曲线会更平滑。
            </p>
          </div>
          <div className="tax-summary-panel">
            <div>
              <span>当前月扣缴后留存率</span>
              <strong>{selectedMonthGrossIncome > 0 ? percent(selectedMonthNetIncome / selectedMonthGrossIncome) : "-"}</strong>
            </div>
            <div>
              <span>年度税前收入</span>
              <strong>{money(annualGrossIncome)}</strong>
            </div>
            <div>
              <span>年度应税所得</span>
              <strong>{money(annualTaxableIncome)}</strong>
            </div>
            <div>
              <span>年度税后到手</span>
              <strong>{money(annualNetIncome)}</strong>
            </div>
          </div>
        </div>
        <div className="cash-flow-pies tax-pies">
          {taxPieBlocks.map((pie, pieIndex) => (
            <div className="cash-flow-pie" key={pie.title}>
              <div className="pie-heading">
                <strong>{pie.title}</strong>
                <span>
                  <small>{pie.period}</small>
                  <b>{money(pie.total)}</b>
                </span>
              </div>
              {pie.data.length > 0 ? (
                <div className="pie-layout">
                  <ResponsiveContainer width="100%" height={190}>
                    <PieChart>
                      <Tooltip formatter={pieTooltipFormatter} />
                      <Pie data={pie.data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                        {pie.data.map((item) => (
                          <Cell key={`${pie.title}-${item.name}`} fill={stablePieColor(item.name)} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pie-legend">
                    {pie.data.map((item) => (
                      <span key={`${pie.title}-legend-${item.name}`}>
                        <i style={{ background: stablePieColor(item.name) }} />
                        <em>{item.name}</em>
                        <strong>{money(item.value)}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="field-hint">{pie.emptyText}</p>
              )}
            </div>
          ))}
        </div>
        <details className="details-panel tax-detail-panel">
          <summary>
            <span>查看年度税务明细</span>
            <small>按成员展示工资薪金税、年终奖税和计税方式，方便解释税负从哪里来</small>
          </summary>
          <div className="tax-detail-table">
            <div className="tax-detail-row tax-detail-head">
              <span>成员</span>
              <span>税前收入</span>
              <span>应税所得</span>
              <span>工资个税</span>
              <span>年终奖个税</span>
              <span>年度到手</span>
              <span>年终奖口径</span>
            </div>
            {taxSummaryRows.length > 0 ? (
              taxSummaryRows.map((item) => (
                <div className="tax-detail-row" key={item.member_name}>
                  <span>{item.member_name}</span>
                  <span>{money(item.gross_annual_income)}</span>
                  <span>{money(item.taxable_income)}</span>
                  <span>{money(item.salary_tax)}</span>
                  <span>{money(item.bonus_tax)}</span>
                  <span>{money(item.net_annual_income)}</span>
                  <span>{bonusTaxMethodLabels[item.selected_bonus_method] ?? item.selected_bonus_method}</span>
                </div>
              ))
            ) : (
              <div className="tax-detail-empty">当前没有年度税务汇总。</div>
            )}
          </div>
          <p className="field-hint">
            这里的“税前扣除”是为了计算个税而展示的过程项，不等同于家庭消费支出；家庭支出仍只看生活、贷款、用车、交易、理财手续费等真实现金流出。
          </p>
        </details>
      </section>

      <div className="visual-grid">
        <section className="chart-block asset-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title="流动资产" compact />
          {hasBackendMonthlySeries ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                data={visibleMonthlySeries}
                onClick={selectChartMonth}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis {...chartXAxisProps} />
                <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
                <Tooltip formatter={(value) => money(Number(value))} />
                {selectedMonthReferenceLine()}
                <Line type="monotone" dataKey="现金池" name="现金账户" stroke={visualColors.cash} strokeWidth={2.3} dot={false} />
                <Line type="monotone" dataKey="投资资产" name="投资账户" stroke={visualColors.investment} strokeWidth={2.3} dot={false} />
                <Line type="monotone" dataKey="流动资产" name="流动资产" stroke={visualColors.totalAsset} strokeWidth={2.8} dot={false} />
                <Line type="monotone" dataKey="安全垫" stroke={visualColors.warning} strokeWidth={2.1} strokeDasharray="5 5" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty-state">
              <strong>等待后端生成账户曲线</strong>
              <span>现金、投资、公积金和贷款变化只展示后端推演结果；当前没有可用月度序列。</span>
            </div>
          )}
          <div className="month-inspector">
            <div>
              <span>当前选中月份</span>
              <strong>{selectedMonth.name}</strong>
              <small>{selectedMonth.period}</small>
            </div>
            <div>
              <span>现金账户</span>
              <strong>{money(selectedMonth.现金池)}</strong>
              <small>当月净流入 {money(selectedMonth.monthlyCashDelta)}，{stressCashSummary}</small>
            </div>
            <div>
              <span>投资账户</span>
              <strong>{money(selectedMonth.投资资产)}</strong>
              <small>定投 {money(selectedMonth.monthlyInvestment)}，买入净额 {money(selectedMonth.monthlyInvestmentNet)}，手续费 {money(selectedMonth.monthlyInvestmentBuyFee)}，复利收益 {money(selectedMonth.investmentReturn)}</small>
            </div>
            <div>
              <span>固定资产</span>
              <strong>{money(selectedMonth.固定资产)}</strong>
              <small>房产 {money(selectedMonth.房产估值)}，车辆 {money(selectedMonth.车辆估值)}</small>
            </div>
          </div>
          <div className="loan-legend investment-legend">
            <span><i className="cash-line" />现金账户：首付、安全垫和日常结余</span>
            <span><i className="investment-line" />投资账户：当前投资、定投净买入和复利收益</span>
            <span><i className="total-line" />流动资产：现金+投资账户，不含公积金账户</span>
          </div>
          <p className="field-hint">
            {investmentSummaryText} 到选中买房时点，后端按“{purchaseInvestmentModeLabel}”处理投资账户：交易前约 {money(purchaseInvestmentBefore)}，交易月到账约 {money(purchaseInvestmentSellProceeds)}，交易后保留约 {money(purchaseInvestmentAfter)}。
          </p>
          <div className="annual-inline-chart">
            <div className="strategy-panel-head">
              <PanelTitle icon={<WalletCards size={18} />} title="年度流动资产拆解" compact />
              <span>{selectedTaxYear} 年度流动资产 {money(selectedAnnualFinancialSummary?.liquid_asset_value_end ?? 0)}</span>
            </div>
            {selectedAnnualFinancialSummary ? (
              <div className="cash-flow-pies annual-pies">
                {renderAnnualPieBlock(
                  "年度流动资产构成",
                  `${selectedTaxYear} 年度`,
                  annualAssetCompositionData,
                  "当前年份没有可展示的流动资产余额。",
                  0
                )}
              </div>
            ) : (
              <p className="field-hint">等待后端生成年度资产汇总。</p>
            )}
          </div>
        </section>

        <section className="chart-block fixed-asset-chart">
          <PanelTitle icon={<Home size={18} />} title="固定资产" compact />
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={visibleMonthlySeries}
              onClick={selectChartMonth}
              margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis {...chartXAxisProps} />
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
              <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
              <Legend verticalAlign="top" height={28} iconType="line" />
              {selectedMonthReferenceLine()}
              <Line type="monotone" dataKey="房产估值" stroke={visualColors.property} strokeWidth={2.4} dot={false} />
              <Line type="monotone" dataKey="车辆估值" stroke={visualColors.vehicle} strokeWidth={2.2} dot={false} />
              <Line type="monotone" dataKey="固定资产" stroke={visualColors.fixedAsset} strokeWidth={2.8} dot={false} />
              <Line type="monotone" dataKey="流动固定资产合计" name="流动资产+固定资产" stroke={visualColors.totalAsset} strokeWidth={2.1} strokeDasharray="4 4" dot={false} />
              <Line type="monotone" dataKey="净资产" name="净资产" stroke={visualColors.danger} strokeWidth={2.1} strokeDasharray="6 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="month-inspector fixed-asset-inspector">
            <div>
              <span>房产估值</span>
              <strong>{money(selectedMonth.房产估值)}</strong>
              <small>{selectedMonth.房产估值 > 0 ? `${scenario.name} 已计入固定资产` : "购房前暂未计入房产资产"}</small>
            </div>
            <div>
              <span>车辆估值</span>
              <strong>{money(selectedMonth.车辆估值)}</strong>
              <small>主用车 {money(selectedMonth.第一辆车估值)}，新增车辆 {money(selectedMonth.第二辆车估值)}</small>
            </div>
            <div>
              <span>固定资产合计</span>
              <strong>{money(selectedMonth.固定资产)}</strong>
              <small>房产按房源总价、车辆按折旧年限线性估算</small>
            </div>
            <div>
              <span>净资产</span>
              <strong>{money(selectedMonth.净资产)}</strong>
              <small>总资产扣除贷款余额；负数表示负债高于资产</small>
            </div>
            <div>
              <span>流动资产+固定资产</span>
              <strong>{money(selectedMonth.流动固定资产合计)}</strong>
              <small>现金账户、投资账户和固定资产合计；公积金账户单独查看</small>
            </div>
          </div>
          <div className="loan-legend fixed-asset-legend">
            <span><i className="home-asset-line" />房产估值</span>
            <span><i className="car-asset-line" />车辆估值</span>
            <span><i className="fixed-asset-line" />固定资产合计</span>
            <span><i className="net-asset-line" />流动资产+固定资产</span>
            <span><i className="danger-line" />净资产</span>
          </div>
          <p className="field-hint">
            固定资产用于观察资产结构，不直接代表可用于首付或应急的现金。房产按候选房源总价入账；车辆从购车月起按折旧年限线性递减，未考虑市场溢价、房价涨跌或真实二手车成交价。
          </p>
          <div className="annual-inline-chart">
            <div className="strategy-panel-head">
              <PanelTitle icon={<Home size={18} />} title="年度固定资产拆解" compact />
              <span>{selectedTaxYear} 年度固定资产 {money(selectedAnnualFinancialSummary?.fixed_asset_value_end ?? 0)}</span>
            </div>
            {selectedAnnualFinancialSummary ? (
              <>
                <div className="tax-summary-panel annual-summary-panel">
                  <div>
                    <span>年度房产估值</span>
                    <strong>{money(selectedAnnualFinancialSummary.property_asset_value_end)}</strong>
                  </div>
                  <div>
                    <span>年度车辆估值</span>
                    <strong>{money(selectedAnnualFinancialSummary.vehicle_asset_value_end)}</strong>
                  </div>
                  <div>
                    <span>年度固定资产</span>
                    <strong>{money(selectedAnnualFinancialSummary.fixed_asset_value_end)}</strong>
                  </div>
                  <div>
                    <span>年度流动资产+固定资产</span>
                    <strong>
                      {money(
                        selectedAnnualFinancialSummary.liquid_asset_value_end +
                          selectedAnnualFinancialSummary.fixed_asset_value_end
                      )}
                    </strong>
                  </div>
                </div>
                <div className="cash-flow-pies annual-pies">
                  {renderAnnualPieBlock(
                    "年度固定资产构成",
                    `${selectedTaxYear} 年度`,
                    annualFixedAssetCompositionData,
                    "当前年份没有可展示的固定资产。",
                    6
                  )}
                </div>
              </>
            ) : (
              <p className="field-hint">等待后端生成年度固定资产汇总。</p>
            )}
          </div>
        </section>

        <section className="chart-block loan-balance-chart">
          <PanelTitle icon={<Banknote size={18} />} title="贷款余额与月供" compact />
          {hasLoanChartActivity ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart
                data={visibleLoanChartData}
                onClick={selectChartMonth}
                margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis {...chartXAxisProps} />
                <YAxis yAxisId="balance" tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
                <YAxis yAxisId="payment" orientation="right" tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
                <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
                {selectedMonthReferenceLine("balance")}
                <Line yAxisId="balance" type="monotone" dataKey="总贷款余额" stroke={visualColors.debt} strokeWidth={2.8} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="商贷余额" stroke={visualColors.property} strokeWidth={2.4} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="公积金贷余额" stroke={visualColors.provident} strokeWidth={2.4} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="车贷余额" stroke={visualColors.vehicle} strokeWidth={2.2} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="已有贷款余额" stroke={visualColors.expense} strokeWidth={2.1} strokeDasharray="4 4" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="当月贷款还款" stroke={visualColors.warning} strokeWidth={2.0} strokeDasharray="3 3" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="商贷额外还本" stroke={visualColors.property} strokeWidth={1.9} strokeDasharray="7 4" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="车贷额外还本" stroke={visualColors.vehicle} strokeWidth={1.9} strokeDasharray="7 4" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="公积金按月抵月供" stroke={visualColors.provident} strokeWidth={2.0} strokeDasharray="2 5" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="公积金冲本金" stroke={visualColors.debt} strokeWidth={1.9} strokeDasharray="6 4" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="当月现金还款" stroke={visualColors.totalAsset} strokeWidth={2.1} strokeDasharray="6 4" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty-state">
              <strong>当前方案没有贷款账户变化</strong>
              <span>
                当前已选策略没有商贷、公积金贷、车贷或可推演余额的已有贷款。
              </span>
            </div>
          )}
          <div className="month-inspector loan-balance-inspector">
            <div>
              <span>总贷款余额</span>
              <strong>{money(selectedLoanPoint?.total_loan_balance ?? 0)}</strong>
              <small>后端按已选购房方案、车贷和已有贷款逐月测算</small>
            </div>
            <div>
              <span>房贷余额</span>
              <strong>{money(selectedLoanPoint?.home_loan_balance ?? 0)}</strong>
              <small>商贷 {money(selectedLoanPoint?.commercial_loan_balance ?? 0)}，公积金贷 {money(selectedLoanPoint?.provident_loan_balance ?? 0)}；计划房贷 {money(plannedHomeLoanAmount)}</small>
            </div>
            <div>
              <span>车贷与已有贷款</span>
              <strong>{money((selectedLoanPoint?.vehicle_loan_balance ?? 0) + (selectedLoanPoint?.existing_loan_balance ?? 0))}</strong>
              <small>车贷 {money(selectedLoanPoint?.vehicle_loan_balance ?? 0)}，{selectedExistingLoanBalanceDescription}；计划车贷 {money(plannedVehicleLoanAmount)}</small>
            </div>
            <div>
              <span>当月还款压力</span>
              <strong>{money(selectedLoanPoint?.cash_monthly_payment ?? 0)}</strong>
              <small>贷款还款 {money(selectedLoanPoint?.total_monthly_payment ?? 0)}；按月抵月供 {money(selectedLoanPoint?.provident_monthly_withdrawal_payment ?? 0)}；半年度冲本金 {money(selectedLoanPoint?.provident_principal_offset_payment ?? 0)}</small>
            </div>
          </div>
          <div className="loan-payment-pie-panel">
            <div className="cash-flow-pie loan-payment-pie">
              <div className="pie-heading">
                <strong>{selectedMonth.name} 贷款扣款结构</strong>
                <span>
                  <small>总量</small>
                  <b>{money(selectedLoanPaymentPieTotal)}</b>
                </span>
              </div>
              <div className="pie-subtotal">
                <span>展示口径</span>
                <strong>跟随当前选中月份</strong>
              </div>
              {selectedLoanPaymentPieData.length > 0 ? (
                <div className="pie-layout loan-payment-pie-layout">
                  <ResponsiveContainer width="100%" height={190}>
                    <PieChart>
                      <Tooltip formatter={pieTooltipFormatter} />
                      <Pie data={selectedLoanPaymentPieData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                        {selectedLoanPaymentPieData.map((item) => (
                          <Cell key={`loan-payment-${item.name}`} fill={stablePieColor(item.name)} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pie-legend">
                    {selectedLoanPaymentPieData.map((item) => (
                      <span key={`loan-payment-legend-${item.name}`}>
                        <i style={{ background: stablePieColor(item.name) }} />
                        <em>{item.name}</em>
                        <strong>{money(item.value)}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="field-hint">当前月份没有贷款扣款；贷款发生后这里会展示商贷、公积金贷、车贷和已有贷款的当月扣款结构。</p>
              )}
            </div>
          </div>
          <div className="loan-legend loan-balance-legend">
            <span><i className="total-loan-line" />总贷款余额</span>
            <span><i className="home-loan-line" />商贷余额</span>
            <span><i className="provident-loan" />公积金贷余额</span>
            <span><i className="vehicle-loan-line" />车贷余额</span>
            <span><i className="existing-loan-line" />已有贷款余额</span>
            <span><i className="provident-payment-line" />公积金按月抵月供</span>
            <span><i className="provident-principal-offset-line" />公积金半年度冲本金</span>
            <span><i className="cash-payment-line" />当月现金还款</span>
          </div>
          <p className="field-hint">
            贷款余额由后端统一生成，前端只展示结果。已有贷款按“未开始计息、只还利息、进入等额还款”逐月推进；其他固定还款如果没有本金配置，只计入还款压力，不推导余额。
          </p>
          <div className="annual-inline-chart">
            <div className="strategy-panel-head">
              <PanelTitle icon={<WalletCards size={18} />} title="年度贷款拆解" compact />
              <span>{selectedTaxYear} 年贷款还款 {money(annualLoanPayment)}</span>
            </div>
            {selectedAnnualFinancialSummary ? (
              <div className="cash-flow-pies annual-pies">
                {renderAnnualPieBlock(
                  "年度贷款还款构成",
                  `${selectedTaxYear} 年`,
                  annualLoanPaymentData,
                  "当前年份没有贷款还款。",
                  3
                )}
                {renderAnnualPieBlock(
                  "年度贷款余额构成",
                  `${selectedTaxYear} 年度`,
                  annualLoanBalanceData,
                  "当前年份末没有贷款余额。",
                  5
                )}
              </div>
            ) : (
              <p className="field-hint">等待后端生成年度贷款汇总。</p>
            )}
          </div>
        </section>

        <section className="chart-block provident-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title="公积金账户变化" compact />
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={visibleProvidentChartData}
              onClick={selectChartMonth}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis {...chartXAxisProps} />
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
              <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
              {selectedMonthReferenceLine()}
              <Line type="monotone" dataKey="公积金余额" name="家庭公积金合计" stroke={visualColors.provident} strokeWidth={2.8} dot={false} />
              {providentMemberBalanceKeys.map((key, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={stablePieColor(key, index + 2)}
                  strokeWidth={1.8}
                  strokeDasharray={index % 2 === 0 ? "4 4" : "2 5"}
                  dot={false}
                />
              ))}
              <Line type="monotone" dataKey="当月缴存" stroke={visualColors.investment} strokeWidth={1.8} dot={false} />
              <Line type="monotone" dataKey="还款支出" stroke={visualColors.debt} strokeWidth={2.1} strokeDasharray="5 4" dot={false} />
              <Line type="monotone" dataKey="提取支出" stroke={visualColors.warning} strokeWidth={1.8} strokeDasharray="3 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="loan-legend provident-account-legend">
            <span><i style={{ background: visualColors.provident }} />家庭公积金合计</span>
            {providentMemberBalanceKeys.map((key, index) => (
              <span key={`legend-${key}`}>
                <i style={{ background: stablePieColor(key, index + 2) }} />
                {key}
              </span>
            ))}
            <span><i style={{ background: visualColors.investment }} />当月缴存</span>
            <span><i style={{ background: visualColors.debt }} />还款支出</span>
            <span><i style={{ background: visualColors.warning }} />提取支出</span>
          </div>
          <div className="policy-note provident-offset-note">
            <strong>{usesMonthlyProvidentRepayment ? "按月抵月供会每月出现支出" : "半年度冲本金不是每月支出"}</strong>
            <span>
              {usesMonthlyProvidentRepayment
                ? "当前策略按月从公积金账户余额抵扣公积金贷月供；余额不足时，未覆盖部分仍进入银行卡现金还款。"
                : "当前策略按 1 月和 7 月合同约定还款日集中冲抵本金；其他月份支出为 0 属于正常状态。"}
              {nextProvidentOffsetPoint
                ? ` 下一次预计在 ${formatMonthDate(timelineBaseDate, nextProvidentOffsetPoint.month)} 支出 ${money((nextProvidentOffsetPoint.monthly_repayment_withdrawal ?? 0) + nextProvidentOffsetPoint.loan_offset_payment)}。`
                : " 当前窗口内没有预计公积金还贷支出。"}
            </span>
          </div>
          <div className="provident-balance-summary">
            <div>
              <span>{selectedMonth.name} 家庭公积金余额</span>
              <strong>{money(selectedMonth.公积金余额)}</strong>
              <small>月初 {money(selectedProvidentPoint?.balance_start ?? 0)}，当月收入 {money(selectedProvidentPoint?.total_inflow ?? 0)}，当月支出 {money(selectedProvidentPoint?.total_outflow ?? 0)}</small>
            </div>
            {selectedProvidentMemberAccounts.map((account) => (
              <div key={`provident-balance-${account.member_index}`}>
                <span>{account.member_name}账户余额</span>
                <strong>{money(account.balance_end)}</strong>
                <small>月初 {money(account.balance_start)}，收入 {money(account.total_inflow)}，支出 {money(account.total_outflow)}</small>
              </div>
            ))}
          </div>
          <div className="cash-flow-pies provident-pies">
            {[
              {
                title: "公积金账户收入",
                data: providentInflowPieData,
                total: providentInflowPieTotal,
                period: selectedMonth.name,
                emptyText: `当前月份没有可展示的公积金账户收入。`
              },
              {
                title: "公积金账户支出",
                data: providentOutflowPieData,
                total: providentOutflowPieTotal,
                period: providentOutflowDisplayPoint
                  ? providentOutflowDisplayPoint.month === safeSelectedMonthIndex
                    ? selectedMonth.name
                    : `最近有支出：${providentOutflowDisplayLabel}`
                  : "测算期内暂无支出",
                emptyText: "当前方案测算期内没有可展示的公积金账户支出。"
              }
            ].map((pie) => (
              <div className="cash-flow-pie" key={pie.title}>
                <div className="pie-heading">
                  <strong>{pie.title}</strong>
                  <span>
                    <small>{pie.period}</small>
                    <b>{money(pie.total)}</b>
                  </span>
                </div>
                <div className="pie-subtotal">
                  <span>展示口径</span>
                  <strong>
                    {pie.title === "公积金账户支出" && providentOutflowDisplayPoint?.month !== safeSelectedMonthIndex
                      ? "自动切到最近发生支出的月份"
                      : "跟随当前选中月份"}
                  </strong>
                </div>
                {pie.data.length > 0 ? (
                  <div className="pie-layout">
                    <ResponsiveContainer width="100%" height={190}>
                      <PieChart>
                        <Tooltip formatter={pieTooltipFormatter} />
                        <Pie data={pie.data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                          {pie.data.map((item) => (
                            <Cell key={`${pie.title}-${item.name}`} fill={stablePieColor(item.name)} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pie-legend">
                      {pie.data.map((item) => (
                        <span key={`${pie.title}-legend-${item.name}`}>
                          <i style={{ background: stablePieColor(item.name) }} />
                          <em>{item.name}</em>
                          <strong>{money(item.value)}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="field-hint">{pie.emptyText}</p>
                )}
              </div>
            ))}
          </div>
          <p className="field-hint">
            {usesMonthlyProvidentRepayment
              ? "公积金账户变化由后端逐月计算。当前策略按月优先用公积金账户余额覆盖公积金贷月供，属于账户支出，不作为自由现金收入；不足部分由现金账户承担。"
              : "公积金账户变化由后端逐月计算。当前半年度冲本金策略按规则包口径在 1 月、7 月合同约定还款日优先冲抵公积金贷款，冲抵资金属于公积金账户支出，不作为自由现金收入。"}
          </p>
          <div className="annual-inline-chart">
            <div className="strategy-panel-head">
              <PanelTitle icon={<WalletCards size={18} />} title="年度公积金流水" compact />
              <span>{selectedTaxYear} 年度公积金余额 {money(selectedAnnualFinancialSummary?.provident_balance_end ?? 0)}</span>
            </div>
            {selectedAnnualFinancialSummary ? (
              <>
                <div className="tax-summary-panel annual-summary-panel">
                  <div>
                    <span>年度缴存</span>
                    <strong>{money(selectedAnnualFinancialSummary.provident_deposit)}</strong>
                  </div>
                  <div>
                    <span>年度现金提取</span>
                    <strong>{money(selectedAnnualFinancialSummary.provident_withdrawal)}</strong>
                  </div>
                  <div>
                    <span>年度公积金还贷</span>
                    <strong>{money(selectedAnnualFinancialSummary.provident_offset_payment)}</strong>
                  </div>
                  <div>
                    <span>年度账户余额</span>
                    <strong>{money(selectedAnnualFinancialSummary.provident_balance_end)}</strong>
                  </div>
                </div>
                <div className="cash-flow-pies annual-pies">
                  {renderAnnualPieBlock(
                    "年度公积金流水构成",
                    `${selectedTaxYear} 年`,
                    annualProvidentFlowData,
                    "当前年份没有公积金缴存、提取或公积金账户还贷流水。",
                    2
                  )}
                </div>
              </>
            ) : (
              <p className="field-hint">等待后端生成年度公积金汇总。</p>
            )}
          </div>
        </section>

        <section className="chart-block social-security-chart">
          <PanelTitle icon={<ShieldCheck size={18} />} title="养老与医保个人账户" compact />
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={visibleSocialSecurityChartData}
              onClick={selectChartMonth}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis {...chartXAxisProps} />
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={compactMoneyTick} />
              <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
              {selectedMonthReferenceLine()}
              <Line type="monotone" dataKey="政策账户合计" stroke={visualColors.totalAsset} strokeWidth={2.7} dot={false} />
              <Line type="monotone" dataKey="个人养老金账户" stroke={visualColors.investment} strokeWidth={2.4} strokeDasharray="6 3" dot={false} />
              {socialSecurityMemberAccountKeys.map((key) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={stablePieColor(key)}
                  strokeWidth={key.endsWith("养老账户") ? 2.35 : 2.05}
                  strokeDasharray={key.endsWith("医保账户") ? "5 4" : undefined}
                  dot={false}
                />
              ))}
              <Line type="monotone" dataKey="养老当月缴入" stroke={visualColors.pension} strokeWidth={1.8} strokeDasharray="4 4" dot={false} />
              <Line type="monotone" dataKey="养老计发支出" stroke={visualColors.expense} strokeWidth={1.8} strokeDasharray="5 3" dot={false} />
              <Line type="monotone" dataKey="医保当月划入" stroke={visualColors.medical} strokeWidth={1.8} strokeDasharray="4 4" dot={false} />
              <Line type="monotone" dataKey="医保账户支出" stroke={visualColors.warning} strokeWidth={1.8} strokeDasharray="5 3" dot={false} />
              <Line type="monotone" dataKey="个人养老金缴费" stroke={visualColors.investment} strokeWidth={1.8} strokeDasharray="2 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="loan-legend provident-account-legend">
            <span><i style={{ background: visualColors.totalAsset }} />政策账户合计</span>
            <span><i style={{ background: visualColors.investment }} />个人养老金账户</span>
            {socialSecurityMemberAccountKeys.map((key) => (
              <span key={`social-security-legend-${key}`}>
                <i style={{ background: stablePieColor(key) }} />
                {key}
              </span>
            ))}
            <span><i style={{ background: visualColors.pension }} />养老当月缴入</span>
            <span><i style={{ background: visualColors.expense }} />养老计发支出</span>
            <span><i style={{ background: visualColors.medical }} />医保当月划入</span>
            <span><i style={{ background: visualColors.warning }} />医保账户支出</span>
            <span><i style={{ background: visualColors.investment }} />个人养老金缴费</span>
          </div>
          <div className="provident-balance-summary">
            <div>
              <span>{selectedMonth.name} 养老与医保账户合计</span>
              <strong>{money(selectedSocialSecurityPoint?.total_balance_end ?? selectedMonth.socialSecurityAccountBalance ?? 0)}</strong>
              <small>养老 {money(selectedSocialSecurityPoint?.pension_balance_end ?? selectedMonth.pensionAccountBalance ?? 0)}，医保 {money(selectedSocialSecurityPoint?.medical_balance_end ?? selectedMonth.medicalAccountBalance ?? 0)}</small>
            </div>
            <div>
              <span>{selectedMonth.name} 个人养老金账户</span>
              <strong>{money(selectedMonth.personalPensionBalance ?? 0)}</strong>
              <small>当月缴费 {money(selectedMonth.personalPensionContribution ?? 0)}，账户收益 {money(selectedMonth.personalPensionReturn ?? 0)}</small>
            </div>
            {selectedSocialSecurityMemberAccounts.map((account) => (
              <div key={`social-security-balance-${account.member_index}`}>
                <span>{account.member_name}政策账户</span>
                <strong>{money(account.pension_balance_end + account.medical_balance_end)}</strong>
                <small>
                  养老 {money(account.pension_balance_end)}，医保 {money(account.medical_balance_end)}
                  {account.pension_account_payout > 0 ? `，养老计发 ${money(account.pension_account_payout)}` : ""}
                  {account.medical_outflow > 0 ? `，医保支出 ${money(account.medical_outflow)}` : ""}
                  {account.retired ? "，已按退休口径划入医保" : ""}
                </small>
              </div>
            ))}
          </div>
          <div className="cash-flow-pies provident-pies">
            <div className="cash-flow-pie">
              <div className="pie-heading">
                <strong>当月政策账户流入</strong>
                <span>
                  <small>{selectedMonth.name}</small>
                  <b>{money(socialSecurityInflowPieTotal)}</b>
                </span>
              </div>
              {socialSecurityInflowPieData.length > 0 ? (
                <div className="pie-layout">
                  <ResponsiveContainer width="100%" height={190}>
                    <PieChart>
                      <Tooltip formatter={pieTooltipFormatter} />
                      <Pie data={socialSecurityInflowPieData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                        {socialSecurityInflowPieData.map((item) => (
                          <Cell key={`social-security-${item.name}`} fill={stablePieColor(item.name)} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pie-legend">
                    {socialSecurityInflowPieData.map((item) => (
                      <span key={`social-security-legend-${item.name}`}>
                        <i style={{ background: stablePieColor(item.name) }} />
                        <em>{item.name}</em>
                        <strong>{money(item.value)}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="field-hint">当前月份没有养老或医保个人账户流入。</p>
              )}
            </div>
            <div className="cash-flow-pie">
              <div className="pie-heading">
                <strong>当月政策账户支出</strong>
                <span>
                  <small>{selectedMonth.name}</small>
                  <b>{money(socialSecurityOutflowPieTotal)}</b>
                </span>
              </div>
              {socialSecurityOutflowPieData.length > 0 ? (
                <div className="pie-layout">
                  <ResponsiveContainer width="100%" height={190}>
                    <PieChart>
                      <Tooltip formatter={pieTooltipFormatter} />
                      <Pie data={socialSecurityOutflowPieData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                        {socialSecurityOutflowPieData.map((item) => (
                          <Cell key={`social-security-outflow-${item.name}`} fill={stablePieColor(item.name)} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pie-legend">
                    {socialSecurityOutflowPieData.map((item) => (
                      <span key={`social-security-outflow-legend-${item.name}`}>
                        <i style={{ background: stablePieColor(item.name) }} />
                        <em>{item.name}</em>
                        <strong>{money(item.value)}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="field-hint">当前月份没有养老或医保个人账户支出。</p>
              )}
            </div>
          </div>
          <p className="field-hint">
            养老保险个人账户和医保个人账户由后端逐月计算。退休后养老个人账户会按计发月数形成账户支出，养老金现金领取仍在收入侧展示；北京医保个人账户退休后会按政策定额划入，同时扣缴大额互助并优先支付明确标记为医保账户可支付的医疗支出。两类账户都不作为自由现金或流动资产。
          </p>
          <div className="annual-inline-chart">
            <div className="strategy-panel-head">
              <PanelTitle icon={<ShieldCheck size={18} />} title="年度养老与医保账户" compact />
              <span>{selectedTaxYear} 年度账户余额 {money(selectedAnnualFinancialSummary?.social_security_account_balance_end ?? 0)}</span>
            </div>
            {selectedAnnualFinancialSummary ? (
              <div className="cash-flow-pies annual-pies">
                {renderAnnualPieBlock(
                  "年度政策账户流入",
                  `${selectedTaxYear} 年度`,
                  annualSocialSecurityFlowData,
                  "当前年份没有养老或医保个人账户流入。",
                  4
                )}
                {renderAnnualPieBlock(
                  "年度政策账户支出",
                  `${selectedTaxYear} 年度`,
                  annualSocialSecurityOutflowData,
                  "当前年份没有养老或医保个人账户支出。",
                  6
                )}
                {renderAnnualPieBlock(
                  "年度政策账户余额",
                  `${selectedTaxYear} 年度`,
                  annualSocialSecurityBalanceData,
                  "当前年份没有养老或医保个人账户余额。",
                  5
                )}
              </div>
            ) : (
              <p className="field-hint">等待后端生成年度养老与医保账户汇总。</p>
            )}
          </div>
        </section>

        <section className="chart-block cash-flow-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title={`${selectedMonth.name} 月现金流`} compact />
          <ResponsiveContainer width="100%" height={cashFlowChartHeight}>
            <BarChart data={cashFlowData} layout="vertical" margin={{ top: 4, right: 14, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={compactMoneyTick} />
              <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={isCompactChart ? 152 : 196} tick={{ fontSize: 11 }} />
              <Tooltip formatter={cashFlowTooltipFormatter} />
              <Bar dataKey="amount" radius={[4, 4, 4, 4]}>
                {cashFlowData.map((item) => (
                  <Cell key={item.name} fill={cashFlowColor(item.kind)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="cash-flow-pies">
            {[
              { title: "收入构成", data: incomePieData, legendData: incomeLegendData, total: incomePieTotal },
              { title: "支出构成", data: expensePieData, total: expensePieTotal }
            ].map((pie) => (
              <div className="cash-flow-pie" key={pie.title}>
                <div className="pie-heading">
                  <strong>{pie.title}</strong>
                  <span>
                    <small>总量</small>
                    <b>{money(pie.total)}</b>
                  </span>
                </div>
                {pie.data.length > 0 ? (
                  <div className="pie-layout">
                    <ResponsiveContainer width="100%" height={210}>
                      <PieChart>
                        <Tooltip formatter={pieTooltipFormatter} />
                        <Pie
                          data={pie.data}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={48}
                          outerRadius={78}
                          paddingAngle={2}
                        >
                          {pie.data.map((item) => (
                            <Cell key={`${pie.title}-${item.name}`} fill={stablePieColor(item.name)} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pie-legend">
                      {(pie.legendData ?? pie.data).map((item) => (
                        <span key={`${pie.title}-legend-${item.name}`}>
                          <i style={{ background: stablePieColor(item.name) }} />
                          <em>{item.name}</em>
                          <strong>{money(item.value)}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="field-hint">当前月份没有可展示的{pie.title}。</p>
                )}
              </div>
            ))}
          </div>
          <div className="month-detail-panel backend-cash-flow-detail">
            <div className="month-detail-heading">
              <strong>后端逐项现金流</strong>
              <span>{selectedMonth.name} 的明细来自后端月度账本</span>
            </div>
            {cashFlowDetailGroups.length > 0 || cashFlowResultItems.length > 0 ? (
              <div className="cash-flow-sections">
                {cashFlowDetailGroups.map((group) => (
                  <div className="cash-flow-section" key={group.title}>
                    <strong>{group.title}</strong>
                    {group.items.map((item) => (
                      <Row
                        key={`${group.title}-${item.name}`}
                        label={item.name}
                        value={money(Number(item.amount ?? item.value))}
                      />
                    ))}
                  </div>
                ))}
                {cashFlowResultItems.length > 0 ? (
                  <div className="cash-flow-section result-section">
                    <strong>月度结果</strong>
                    {cashFlowResultItems.map((item) => (
                      <Row
                        key={`result-${item.name}`}
                        label={item.name}
                        value={money(Number(item.amount ?? item.value))}
                      />
                    ))}
                    <Row label="月末现金账户" value={money(selectedMonth.现金池)} />
                    <Row label="月末投资账户" value={money(selectedMonth.投资资产)} />
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="field-hint">后端还没有返回本月逐项现金流。请先重新计算，或检查后端服务是否完成账户曲线生成。</p>
            )}
          </div>
          <details className="details-panel month-detail-panel">
            <summary>
              <span>查看本月财务解释</span>
              <small>用于追溯工资、贷款、公积金和定投为什么这样入账</small>
            </summary>
            <div className="explanation-grid month-explanation-grid">
              {selectedMonthExplanationItems.map((item) => (
                <article key={item.title}>
                  <strong>{item.title}</strong>
                  <p>{item.body}</p>
                </article>
              ))}
            </div>
            <p className="field-hint">
              投资账户收益留在投资账户继续复利；买入手续费从定投资金中扣除，卖出手续费在交易月变现时扣除。单位公积金缴存进入单独的公积金账户，不作为固定工资口径直接计入购房后月结余。
            </p>
          </details>
          <div className="annual-inline-chart">
            <div className="strategy-panel-head">
              <PanelTitle icon={<WalletCards size={18} />} title="年度现金流拆解" compact />
              <span>{selectedTaxYear} 年现金净变化 {money(selectedAnnualFinancialSummary?.monthly_cash_delta ?? 0)}</span>
            </div>
            {selectedAnnualFinancialSummary ? (
              <>
                <div className="tax-summary-panel annual-summary-panel">
                  <div>
                    <span>年度现金流入</span>
                    <strong>{money(annualPieTotal(annualCashInflowData))}</strong>
                  </div>
                  <div>
                    <span>年度现金流出</span>
                    <strong>{money(annualPieTotal(annualCashOutflowData))}</strong>
                  </div>
                  <div>
                    <span>年度现金净变化</span>
                    <strong>{money(selectedAnnualFinancialSummary.monthly_cash_delta)}</strong>
                  </div>
                  <div>
                    <span>年度现金账户</span>
                    <strong>{money(selectedAnnualFinancialSummary.cash_balance_end)}</strong>
                  </div>
                </div>
                <div className="cash-flow-pies annual-pies">
                  {renderAnnualPieBlock(
                    "年度现金流入构成",
                    `${selectedTaxYear} 年`,
                    annualCashInflowData,
                    "当前年份没有现金流入。",
                    0
                  )}
                  {renderAnnualPieBlock(
                    "年度现金流出构成",
                    `${selectedTaxYear} 年`,
                    annualCashOutflowData,
                    "当前年份没有现金流出。",
                    4
                  )}
                </div>
              </>
            ) : (
              <p className="field-hint">等待后端生成年度现金流汇总。</p>
            )}
          </div>
        </section>
      </div>

      <section className="chart-block happiness-chart">
        <PanelTitle icon={<TrendingUp size={18} />} title="幸福指数" compact />
        <div className="chart-subhead">
          <strong>{isBaselineVisualization ? "家庭基线逐月曲线" : "当前方案逐月曲线"}</strong>
          <span>
            {isBaselineVisualization
              ? "后端按现金安全、月现金流、贷款压力和家庭事件生成"
              : "后端按现金安全、月现金流、贷款压力、购房阶段和家庭事件生成"}
          </span>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={happinessCurveData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="month" tickFormatter={formatChartMonthTick} tickLine={false} axisLine={false} height={34} />
            <YAxis domain={[0, 10]} tickLine={false} axisLine={false} width={36} />
            <Tooltip
              labelFormatter={(value) => formatChartMonthTick(value)}
              formatter={(value) => `${Number(value).toFixed(2)} / 10`}
            />
            <Line type="monotone" dataKey="幸福指数" stroke={visualColors.safe} strokeWidth={2.4} dot={false} activeDot={{ r: 4 }} />
            {selectedMonthReferenceLine()}
          </LineChart>
        </ResponsiveContainer>
        {!isBaselineVisualization ? (
          <>
            <div className="chart-subhead">
              <strong>不同购房方案对比</strong>
              <span>横向比较最终方案评分</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={happinessData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 10]} tickLine={false} axisLine={false} width={36} />
                <Tooltip formatter={(value) => `${Number(value).toFixed(1)} / 10`} />
                <Bar dataKey="幸福指数" radius={[4, 4, 0, 0]}>
                  {happinessData.map((item) => (
                    <Cell key={item.name} fill={item.selected ? visualColors.safe : "var(--chart-muted-series)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </>
        ) : null}
        <p className="field-hint">
          {isBaselineVisualization
            ? "基线幸福指数不包含购房交易和房源体验，只用于观察现金安全、月现金流、贷款压力、用车、养娃和家庭事件对长期状态的影响。"
            : "幸福指数由后端按居住、通勤、教育、用车便利、买车对买房影响、交易现金、买后安全垫、投资连续性、月现金流、负债、月供、利息、现金缺口、等待、装修和压力韧性加权计算；流动性偏好越高，财务安全维度权重越高。"}
        </p>
        {plan.happiness_breakdown.length > 0 ? (
          <div className="happiness-breakdown">
            {plan.happiness_breakdown.map((item) => (
              <div className="happiness-breakdown-item" key={item.key || item.name}>
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    权重 {percent(item.weight)}，贡献 {item.weighted_score.toFixed(2)} 分。{item.note}
                  </small>
                </span>
                <b>{item.score.toFixed(1)}</b>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section className="timeline-panel">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="事件时间线" compact />
        <div className="timeline-list">
          {timelineItems.map((item, index) => (
            <div className="timeline-item" key={`${item.month}-${item.label}-${index}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              {item.calibrationSource ? <small>校准来源：{item.calibrationSource}</small> : null}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function ExportPage({
  result,
  scenario,
  selectedPlan,
  selectedPlanVariant,
  setSelectedPlanVariant,
  availablePlans,
  runCalculation
}: {
  result: AffordabilityResult | null;
  scenario: ScenarioData;
  selectedPlan: PurchasePlanAnalysis | null;
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  availablePlans: PurchasePlanAnalysis[];
  runCalculation: () => void;
}) {
  const exportTargets = [
    {
      key: "current_plan",
      title: "当前方案",
      description: "导出当前选中的购房方案说明、关键指标和顾问提示。",
      ready: Boolean(result && selectedPlan),
    },
    {
      key: "monthly_timeline",
      title: "月度账户时间线",
      description: "详细表格包含现金、投资、公积金、养老医保、固定资产、贷款和流水。",
      ready: Boolean(result && selectedPlan),
    },
    {
      key: "tax_year_detail",
      title: "税务年度明细",
      description: "跟随详细表格一起导出年度税务、成员税负和税务策略结果。",
      ready: Boolean(result?.tax_year_summaries?.length),
    },
  ];

  return (
    <PlannerPageShell
      icon={<Download size={20} />}
      title="导出方案"
      action={<button className="ghost-button" onClick={runCalculation}><RefreshCw size={16} /> 刷新结果</button>}
      summary={<p>先确认导出对象和当前选中方案，再导出文字说明或详细表格。表格列名保持中文，避免出现内部字段名。</p>}
    >
      <WorkflowSection
        icon={<Target size={18} />}
        title="导出对象"
        description="选择要导出的内容范围；当前按钮会按所选方案导出文字或完整明细表。"
        className="export-target-panel"
      >
        <div className="horizontal-card-list compact export-target-grid">
          {exportTargets.map((target, index) => (
            <article className={`strategy-card ${index === 0 ? "active" : ""}`} key={target.key}>
              <div className="strategy-card-head">
                <strong>{target.title}</strong>
                <StrategyStatePill active={target.ready} recommended={!target.ready} label={target.ready ? "可导出" : "等待数据"} />
              </div>
              <p>{target.description}</p>
            </article>
          ))}
        </div>
      </WorkflowSection>
      <WorkflowSection
        icon={<SlidersHorizontal size={18} />}
        title="当前选中项配置"
        description="选择本次导出的方案口径；文字和表格会跟随这里的方案切换。"
        className="export-panel"
      >
        {result && selectedPlan ? (
          <>
            <div className="visual-header">
              <div>
                <PanelTitle icon={<Download size={18} />} title="当前导出方案" />
                <h3>{selectedPlan.variant}</h3>
                <p>{selectedPlan.description}</p>
              </div>
              <select
                value={selectedPlanVariant}
                onChange={(event) => setSelectedPlanVariant(event.target.value)}
              >
                {availablePlans.map((plan) => (
                  <option key={plan.variant} value={plan.variant}>
                    {plan.variant}
                  </option>
                ))}
              </select>
            </div>
            <PlanStatus plan={selectedPlan} />
          </>
        ) : (
          <EmptyState
            title="等待计算结果"
            description="先刷新或完成一次计算，然后这里会显示可导出的当前方案和详细账户时间线。"
            action={<button className="ghost-button" onClick={runCalculation}><RefreshCw size={16} /> 刷新结果</button>}
          />
        )}
      </WorkflowSection>
      {result && selectedPlan ? (
        <>
          <WorkflowSection
            icon={<Sparkles size={18} />}
            title="策略说明"
            description="导出前先确认当前方案的顾问提示、资格说明和关键假设。"
            profile="explanation"
          >
            <section className="notes export-notes">
              <p>导出内容以当前选中的“{selectedPlan.variant}”为准；全局即时可行性仅作为背景参考。</p>
              {result.eligibility_notes.map((note) => (
                <p key={note}>{note}</p>
              ))}
              {result.assumptions.map((note) => (
                <p key={note}>{note}</p>
              ))}
            </section>
          </WorkflowSection>
          <WorkflowSection
            icon={<Gauge size={18} />}
            title="影响预览与导出"
            description="先扫关键指标，再下载文字说明或结构化表格。"
          >
            <div className="metric-grid">
              <Metric
                label="预计买入时间"
                value={formatPurchaseTiming(new Date(), selectedPlan.months_to_buy, selectedPlan.years_to_buy)}
                tone={selectedPlan.months_to_buy === null ? "bad" : "good"}
              />
              <Metric label="首付" value={money(selectedPlan.planned_down_payment)} />
              <Metric label="公积金贷" value={money(selectedPlan.provident_loan_amount)} />
              <Metric label="商贷" value={money(selectedPlan.commercial_loan_amount)} />
              <Metric
                label="买后自由月结余"
                value={money(selectedPlan.post_purchase_cash_flow)}
                tone={selectedPlan.post_purchase_cash_flow >= 0 ? "good" : "bad"}
              />
              <Metric
                label="装修资金"
                value={
                  selectedPlan.months_to_renovation === null
                      ? "暂无法估算"
                      : `买后 ${selectedPlan.months_to_renovation} 个月`
                }
                tone={selectedPlan.months_to_renovation === null ? "warn" : "good"}
              />
              <Metric label="幸福指数" value={`${selectedPlan.happiness_score.toFixed(1)} / 10`} />
            </div>
            <div className="export-actions">
              <button className="primary-button" onClick={() => exportText(result, scenario, selectedPlan)}>
                <Download size={16} /> 导出文字
              </button>
              <button className="ghost-button" onClick={() => exportCsv(result, scenario, selectedPlan)}>
                <Download size={16} /> 导出详细表格
              </button>
            </div>
          </WorkflowSection>
        </>
      ) : null}
    </PlannerPageShell>
  );
}

function getPlanStatus(plan: PurchasePlanAnalysis) {
  if (plan.insolvency_month !== undefined && plan.insolvency_month !== null) {
    return {
      status: "不可行",
      statusClass: "bad",
      reason: `长期账本在 ${formatMonthDate(new Date(), plan.insolvency_month)} 出现现金缺口 ${money(Math.max(0, plan.cash_shortfall ?? 0))}；该方案不会进入推荐。`
    };
  }
  if (plan.liquid_assets_exhausted_month !== undefined && plan.liquid_assets_exhausted_month !== null) {
    return {
      status: "不可行",
      statusClass: "bad",
      reason: `长期账本在 ${formatMonthDate(new Date(), plan.liquid_assets_exhausted_month)} 耗尽流动资产；该方案不会进入推荐。`
    };
  }
  if (plan.months_to_buy === null) {
    const shortfall = Math.max(0, plan.cash_stress_shortfall ?? 0);
    return {
      status: "不可行",
      statusClass: "bad",
      reason:
        shortfall > 0
          ? `系统已尝试延后买入和调整贷款结构，但 30 年内仍会留下约 ${money(shortfall)} 的压力现金缺口；这类方案不应直接执行。`
          : "当前收入、资产和现金流路径下，30 年内无法达到该方案的购房现金要求。"
    };
  }
  if (plan.cash_stress_ok === false) {
    const shortfall = Math.max(0, plan.cash_stress_shortfall ?? 0, -(plan.minimum_cash_balance ?? 0));
    return {
      status: "不可行",
      statusClass: "bad",
      reason: `${formatMonthDate(new Date(), plan.months_to_buy)} 虽然可达到交易现金要求，但压力情景下会出现 ${money(shortfall)} 现金缺口；现金不能为负，需要延后买入、降低目标或重新调整贷款结构。`
    };
  }
  const riskNotes = [
    !plan.liquidity_ok ? "交易当下现金低于安全垫" : "",
    plan.post_purchase_cash_flow < 0 ? "买后自由现金流为负" : "",
    plan.debt_to_income_ratio > 0.5 ? "负债收入比较高" : ""
  ].filter(Boolean);
  if (riskNotes.length > 0) {
    return {
      status: "谨慎可行",
      statusClass: "warn",
      reason: `${formatMonthDate(new Date(), plan.months_to_buy)} 可执行，但${riskNotes.join("、")}，建议保留为有条件方案。`
    };
  }
  return {
    status: "可行",
    statusClass: "good",
    reason: `${formatMonthDate(new Date(), plan.months_to_buy)} 可执行，交易当下现金安全垫和买后自由现金流均满足当前设定。`
  };
}

function PlanStatus({ plan }: { plan: PurchasePlanAnalysis }) {
  const planStatus = getPlanStatus(plan);

  return (
    <div className={`status-block ${planStatus.statusClass}`}>
      {planStatus.status === "不可行" ? <AlertTriangle size={22} /> : <CheckCircle2 size={22} />}
      <div>
        <strong>{plan.variant}：{planStatus.status}</strong>
        <span>{planStatus.reason}</span>
      </div>
    </div>
  );
}

function downloadFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function exportText(result: AffordabilityResult, _scenario: ScenarioData, plan: PurchasePlanAnalysis) {
  const document = (result.export_texts ?? []).find((item) => item.plan_variant === plan.variant);
  const lines = document?.lines ?? [
    `当前导出方案：${plan.variant}`,
    "本次计算尚未生成结构化文字导出，请先重新计算。"
  ];
  downloadFile(document?.filename ?? `house-plan-${plan.variant}.txt`, lines.join("\n"), "text/plain;charset=utf-8");
}

function csvCell(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function csvRow(values: unknown[]) {
  return values.map((value) => csvCell(typeof value === "boolean" ? (value ? "是" : "否") : value)).join(",");
}

function csvSection(title: string, headers: string[], rows: unknown[][]) {
  return [
    csvRow([title]),
    csvRow(headers),
    ...rows.map((row) => csvRow(row)),
    ""
  ];
}

function exportCsv(result: AffordabilityResult, _scenario: ScenarioData, plan: PurchasePlanAnalysis) {
  const exportSheets = (result.export_sheets ?? []).filter(
    (sheet) => !sheet.plan_variant || sheet.plan_variant === plan.variant
  );
  const sections =
    exportSheets.length > 0
      ? [
          "sep=,",
          ...exportSheets.flatMap((sheet) => csvSection(sheet.title, sheet.headers, sheet.rows))
        ]
      : [
          "sep=,",
          ...csvSection("导出说明", ["项目", "内容"], [
            ["导出方案", plan.variant],
            ["状态", "本次计算尚未生成结构化导出表格，请先重新计算。"]
          ])
        ];
  downloadFile(`house-plan-${plan.variant}-detailed.csv`, `\uFEFF${sections.join("\n")}`, "text/csv;charset=utf-8");
}

function SectionHeader({
  icon,
  title,
  action
}: {
  icon: ReactNode;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-header">
      <div>
        {icon}
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

function PlannerPageShell({
  icon,
  title,
  summary,
  action,
  className = "",
  children
}: {
  icon: ReactNode;
  title: string;
  summary?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`page-stack planner-page-shell ${className}`}>
      <section className="planner-page-intro">
        <SectionHeader icon={icon} title={title} action={action} />
        {summary ? <div className="planner-summary-band">{summary}</div> : null}
      </section>
      {children}
    </div>
  );
}

function WorkflowSection({
  icon,
  title,
  description,
  children,
  className = "",
  defaultOpen,
  profile = "core"
}: {
  icon: ReactNode;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
  profile?: CollapseProfile;
}) {
  const initialOpen = defaultOpen ?? COLLAPSE_DEFAULTS[profile];
  const [open, setOpen] = useState(initialOpen);
  return (
    <section className={`form-panel workflow-section ${className}`}>
      <div className="workflow-section-head">
        <button className="collapsible-title-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <PanelTitle icon={icon} title={title} compact />
          {open ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
        </button>
        {description ? <span className="workflow-section-description">{description}</span> : null}
      </div>
      {open ? children : null}
    </section>
  );
}

function CollapsiblePanel({
  icon,
  title,
  children,
  className = "",
  defaultOpen,
  profile = "core",
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
  profile?: CollapseProfile;
  action?: ReactNode;
}) {
  const initialOpen = defaultOpen ?? COLLAPSE_DEFAULTS[profile];
  const [open, setOpen] = useState(initialOpen);
  return (
    <section className={`form-panel collapsible-panel ${className}`}>
      <div className="collapsible-panel-head">
        <button className="collapsible-title-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <PanelTitle icon={icon} title={title} compact />
          {open ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
        </button>
        {action}
      </div>
      {open ? children : null}
    </section>
  );
}

function CollapsibleSettingGroup({
  title,
  children,
  className = "",
  defaultOpen,
  profile = "advanced",
  action,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
  profile?: CollapseProfile;
  action?: ReactNode;
}) {
  const initialOpen = defaultOpen ?? COLLAPSE_DEFAULTS[profile];
  const [open, setOpen] = useState(initialOpen);
  return (
    <section className={`setting-group collapsible-setting-group ${className}`}>
      <div className="setting-group-head">
        <button className="setting-group-toggle" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <strong className="setting-group-title">{title}</strong>
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {action ? <div className="setting-group-actions">{action}</div> : null}
      </div>
      {open ? children : null}
    </section>
  );
}

function EmptyState({
  title,
  description,
  action,
  compact = false
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "empty-state compact-empty-state" : "empty-state"}>
      <strong>{title}</strong>
      {description ? <span>{description}</span> : null}
      {action}
    </div>
  );
}

function PanelTitle({
  icon,
  title,
  compact = false,
  collapsible = false,
  defaultOpen = true,
}: {
  icon: ReactNode;
  title: string;
  compact?: boolean;
  collapsible?: boolean;
  defaultOpen?: boolean;
}) {
  const className = `${compact ? "panel-title compact" : "panel-title"}${collapsible ? " panel-title-collapsible" : ""}`;
  if (collapsible) {
    return (
      <label className={className}>
        <input className="panel-collapse-input" type="checkbox" defaultChecked={defaultOpen} />
        {icon}
        <h2>{title}</h2>
        <ChevronDown className="panel-collapse-chevron" size={17} aria-hidden="true" />
      </label>
    );
  }
  return (
    <div className={className}>
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function Field({ label, children, description }: { label: string; children: ReactNode; description?: string }) {
  const helpText = description ?? parameterExplanations[label];
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {helpText ? <small className="parameter-help">{helpText}</small> : null}
    </label>
  );
}

function SwitchField({
  label,
  checked,
  onChange,
  description,
  disabled = false,
  className = ""
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
  disabled?: boolean;
  className?: string;
}) {
  const helpText = description ?? parameterExplanations[label];
  return (
    <label className={`switch-field ${className}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch-control" aria-hidden="true" />
      <span className="switch-copy">
        <strong>{label}</strong>
        {helpText ? <small>{helpText}</small> : null}
      </span>
    </label>
  );
}

function ReadOnlyField({ label, value, description }: { label: string; value: string; description?: string }) {
  return (
    <Field label={label} description={description}>
      <input type="text" value={value} readOnly />
    </Field>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
  min,
  max,
  description
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  min?: number;
  max?: number;
  description?: string;
}) {
  const [draftValue, setDraftValue] = useState(numberInput(value));

  useEffect(() => {
    setDraftValue(numberInput(value));
  }, [value]);

  const clampValue = (nextValue: number) => {
    if (!Number.isFinite(nextValue)) return value;
    if (min !== undefined && nextValue < min) return min;
    if (max !== undefined && nextValue > max) return max;
    return nextValue;
  };

  const commitValue = (rawValue: string) => {
    const trimmed = rawValue.trim();
    if (trimmed === "" || trimmed === "-" || trimmed === "." || trimmed === "-.") {
      setDraftValue(numberInput(value));
      return;
    }
    const nextValue = clampValue(Number(trimmed));
    setDraftValue(numberInput(nextValue));
    if (nextValue !== value) {
      onChange(nextValue);
    }
  };

  return (
    <Field label={label} description={description}>
      <input
        type="text"
        inputMode={step % 1 === 0 ? "numeric" : "decimal"}
        value={draftValue}
        onFocus={(event) => event.currentTarget.select()}
        onMouseUp={(event) => event.preventDefault()}
        onChange={(event) => setDraftValue(event.target.value)}
        onBlur={(event) => commitValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
      />
    </Field>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StrategyStatePill({
  active,
  recommended,
  label
}: {
  active: boolean;
  recommended?: boolean;
  label?: string;
}) {
  const content = active ? label ?? "当前采用" : recommended ? "系统推荐" : "候选方案";
  return (
    <span className={`strategy-state-pill ${active ? "active" : recommended ? "recommended" : ""}`}>
      {active ? <CheckCircle2 size={13} /> : recommended ? <Sparkles size={13} /> : null}
      {content}
    </span>
  );
}

function AdoptStrategyButton({
  active,
  onClick,
  activeLabel = "当前采用",
  inactiveLabel = "采用方案"
}: {
  active: boolean;
  onClick: () => void;
  activeLabel?: string;
  inactiveLabel?: string;
}) {
  return (
    <button
      type="button"
      className={active ? "ghost-button adopted-button" : "primary-button adopt-button"}
      onClick={onClick}
    >
      {active ? <CheckCircle2 size={16} /> : <Sparkles size={16} />}
      {active ? activeLabel : inactiveLabel}
    </button>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
