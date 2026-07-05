import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, ReactNode } from "react";
import {
  AlertTriangle,
  Banknote,
  CalendarClock,
  Car,
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
  calculateAffordability,
  createScenario,
  deleteScenario,
  fetchSourcePreview,
  loadInitialData,
  saveHousehold,
  saveRulePack,
  saveScenario
} from "./api";
import { money, numberInput, percent } from "./format";
import type {
  AffordabilityResult,
  BonusTaxMethod,
  CarPlanAnalysis,
  CarPlanData,
  CareerShockData,
  CommercialPrepaymentMode,
  ElderlyDependentData,
  HouseholdData,
  IncomeMember,
  IncomeStageData,
  InvestmentPlanRecommendation,
  ProvidentAccountRepaymentStrategy,
  ProvidentMemberAccountPoint,
  PurchasePlanAnalysis,
  RecordEnvelope,
  RepaymentMethod,
  RenovationFundingMode,
  RulePackData,
  ScenarioData,
  ScheduledExpenseData,
  SourceDocumentRecord,
  PhasedLoanData,
  VehicleFinancingOptionData,
  VehiclePlanData
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
  const legacyNames = new Set(["当前经销商金融方案", "当前普通贷款方案", "当前经销商贴息方案"]);
  const legacyOptions = options.length > 0 && options.every((option) => option.id === "legacy_current" || legacyNames.has(option.name));
  if (options.length && !legacyOptions) {
    return options.map((option, index) => normalizeVehicleFinancingOption(option, index, vehicle));
  }
  return defaultVehicleFinancingOptions().map((option, index) => normalizeVehicleFinancingOption(option, index, vehicle));
};

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
  vehicle_plans: [],
  planning_sequence: 1,
  purchase_timing_mode: "auto_sequence",
  after_previous_event_delay_months: 0,
  manual_purchase_delay_months: 0,
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
  vehicle_service_years: 15,
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
    name: "定时支出",
    monthly_amount: 0,
    start_month: "2026-07",
    end_month: null,
    tax_deductible_elderly_care: false,
    notes: ""
  }
];

function defaultRetirementCategoryForMember(index: number): IncomeMember["retirement_category"] {
  return index === 0 ? "male_60" : "female_55";
}

const retirementCategoryLabels: Record<IncomeMember["retirement_category"], string> = {
  male_60: "男职工（延至63岁）",
  female_55: "女职工原55岁（延至58岁）",
  female_50: "女职工原50岁（延至55岁）"
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
    const retirementCategory = member.retirement_category ?? defaultRetirementCategoryForMember(index);
    return {
      ...member,
      birth_month: birthMonth,
      current_age: ageYearsFromBirthMonth(birthMonth) ?? member.current_age ?? 30,
      retirement_category: retirementCategory,
      provident_account_management_center: member.provident_account_management_center ?? "beijing_municipal",
      provident_fund_balance: member.provident_fund_balance ?? 0
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
        after_previous_purchase_delay_months: goal.after_previous_purchase_delay_months ?? 0
      })),
      phased_loans: (record.data.phased_loans ?? []).map((loan) => ({
        ...loan,
        prepayment_mode: loan.prepayment_mode ?? "none",
        prepayment_start_month: loan.prepayment_start_month ?? 1,
        prepayment_allowed_after_month: loan.prepayment_allowed_after_month ?? 1,
        prepayment_monthly_amount: loan.prepayment_monthly_amount ?? 0
      })),
      scheduled_expenses: record.data.scheduled_expenses ?? [],
      elderly_dependents: record.data.elderly_dependents ?? [],
      borrower_member_index: record.data.borrower_member_index ?? 0,
      family_provident_support_enabled: record.data.family_provident_support_enabled ?? false,
      family_provident_support_label: record.data.family_provident_support_label ?? "亲属异地公积金首付支持",
      family_down_payment_support_mode: record.data.family_down_payment_support_mode ?? "provident",
      family_savings_support_amount: record.data.family_savings_support_amount ?? 0,
      family_provident_initial_balance: record.data.family_provident_initial_balance ?? 0,
      family_provident_monthly_salary: record.data.family_provident_monthly_salary ?? 0,
      family_provident_total_rate: record.data.family_provident_total_rate ?? 0.24,
      investment_buy_fee_rate: record.data.investment_buy_fee_rate ?? 0.0015,
      investment_sell_fee_rate: record.data.investment_sell_fee_rate ?? 0.005
    }
  };
}

const pages = ["家庭财务", "理财计划", "购房计划", "购车计划", "政策规则", "可视化", "导出方案"] as const;
type PageName = (typeof pages)[number];
type SaveState = "idle" | "dirty" | "saving" | "saved";
type ThemeMode = "light" | "dark";
type ScenarioComparison = {
  scenario: RecordEnvelope<ScenarioData>;
  result: AffordabilityResult;
  recommendation: PurchasePlanAnalysis | null;
  selectedPlan: PurchasePlanAnalysis | null;
};

const noPurchaseScenarioId = "__no_purchase_baseline__";

function createTargetScenarioData(sequence: number): ScenarioData {
  return {
    name: sequence <= 1 ? "第一套购房需求 · 候选房源 1" : `第 ${sequence} 套购房需求 · 候选房源 1`,
    enabled: true,
    purchase_sequence: Math.max(1, sequence),
    purchase_planning_mode: sequence <= 1 ? "parallel" : "after_previous_purchase",
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
    micro_commercial_loan_ratio: 0,
    commercial_rate: 0.035,
    provident_rate: 0.026,
    loan_years: 25,
    repayment_method: "equal_installment",
    commercial_repayment_method: "equal_installment",
    provident_repayment_method: "equal_installment",
    commercial_prepayment_mode: "auto",
    commercial_prepayment_enabled: false,
    commercial_prepayment_start_month: 1,
    commercial_prepayment_allowed_after_month: 12,
    commercial_prepayment_monthly_amount: 0,
    provident_account_repayment_strategy: "auto",
    deed_tax_rate: 0.015,
    broker_fee_rate: 0.022,
    renovation_cost: 250000,
    renovation_funding_mode: "after_purchase_saving",
    moving_and_misc_cost: 50000,
    annual_investment_return: 0.025,
    investment_withdrawal_mode: "auto",
    investment_min_balance_after_purchase: 0,
    happiness_score: 7,
    commute_score: 7,
    school_score: 6,
    liquidity_priority_score: 7,
    notes: "",
    selected_purchase_plan_variant: ""
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
      purchase_planning_mode: record.data.purchase_planning_mode ?? (index === 0 ? "parallel" : "after_previous_purchase"),
      after_previous_purchase_delay_months: record.data.after_previous_purchase_delay_months ?? 0,
      investment_withdrawal_mode: record.data.investment_withdrawal_mode ?? "auto",
      investment_min_balance_after_purchase: record.data.investment_min_balance_after_purchase ?? 0,
      commercial_prepayment_mode: commercialPrepaymentMode,
      commercial_prepayment_enabled: commercialPrepaymentMode === "manual",
      commercial_prepayment_start_month: record.data.commercial_prepayment_start_month ?? 1,
      commercial_prepayment_allowed_after_month: record.data.commercial_prepayment_allowed_after_month ?? 12,
      commercial_prepayment_monthly_amount: commercialPrepaymentMode === "none" ? 0 : record.data.commercial_prepayment_monthly_amount ?? 0,
      provident_account_repayment_strategy: record.data.provident_account_repayment_strategy ?? "auto"
    }
  };
}

const noPurchaseScenario: RecordEnvelope<ScenarioData> = {
  id: noPurchaseScenarioId,
  data: {
    ...createTargetScenarioData(1),
    name: "不买房基线",
    enabled: false,
    total_price: 0,
    renovation_cost: 0,
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
    `公积金贷 ${money(plan.provident_loan_amount)}，商贷 ${money(plan.commercial_loan_amount)}`,
    plan.liquidity_ok ? "买后现金安全垫达标" : "买后现金安全垫偏紧"
  ];
}

const parameterExplanations: Record<string, string> = {
  家庭名称: "仅用于区分方案，不参与计算。建议写成便于识别的版本，例如“当前家庭基准版”。",
  "租房提取公积金/月": "购房前按租房提取公积金的月均额度录入；现金流和可视化里按季度到账处理，不是工资公积金缴存额。",
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
  当前可动用现金: "今天可随时用于首付、应急和日常支出的现金，不包含已投入理财的资产。",
  基础月支出: "从现在起每月固定发生的生活支出，不含家庭支持支出、房贷、车贷和已有贷款等单独项目。",
  当前实际月支出: "基础月支出加上当前已经生效的定时支出，用于判断现金安全垫。",
  "其他固定还款/月": "除下方单独建模的已有贷款外，每月固定发生但暂不推导余额的还款；已有贷款会自动加进测算。",
  支出名称: "定时支出的名称，会直接显示在月现金流里，例如家庭支持支出。",
  定时月支出: "从开始月份起每月发生的额外家庭支出。用于现金流，不一定能抵扣个税。",
  开始月份: "该项支出从哪个月份开始计入现金流。",
  结束月份: "可选；填了以后，结束月份之后不再计入现金流。",
  归属成员: "老人专项扣除归属于哪位收入成员。按政策通常只能扣自己的父母，不能夫妻互转。",
  称谓: "用于界面识别老人来源，例如成员一方直系亲属老人。",
  出生月份: "用于判断老人满 60 周岁的月份；系统从满 60 周岁当月开始计算赡养老人专项附加扣除。",
  本人分摊扣除: "非独生子女时本人每月可申报的分摊额，个人上限通常为 1500 元/月。",
  成员名称: "收入成员名称。老人专项扣除、工资阶段和可视化明细会按这个名称关联。",
  阶段名称: "工资阶段的名称，例如当前收入、换工作后。用于识别不同收入时期。",
  阶段类型: "选择这一段收入的性质。工资就业会按工资薪金自动扣社保、公积金和个税；失业期、自由职业和养老金阶段会按你填写或系统生成的收入项测算。",
  开始日期: "该工资阶段从哪天开始生效；税费和公积金会按月份匹配阶段。",
  结束日期: "该工资阶段结束日期；留空表示一直持续。",
  月工资税前: "每月税前工资，是社保、公积金、个税预扣和现金流收入的基础。",
  自由职业收入: "打开后，这一收入阶段可以额外填写自由职业收入；阶段类型选为自由职业时会默认打开。",
  "自由职业收入/月": "这一阶段实际发生的自由职业月收入，会作为综合所得现金收入纳入税务和现金流测算。",
  年终奖年额: "预计全年年终奖金额。现金流按该收入阶段设置的发放月份一次性入账，不均摊到每个月；系统会按单独计税或并入综合所得择优测算。",
  发放月份: "该收入阶段年终奖实际入账月份。不同成员、不同工作阶段可以不同；税率和单独计税有效期仍由政策规则控制。",
  "非税收入/月": "每月进入现金流但不并入工资薪金计税的收入，例如失业金、基础养老金等估算项。",
  "额外现金支出/月": "该收入阶段每月额外发生、但不属于社保公积金扣缴的现金支出。灵活就业自缴社保和自缴公积金请使用专门字段，避免重复计算。",
  工资社保扣缴: "开启时按工资薪金自动估算北京社保、公积金和个税；失业金、养老金等阶段应关闭。",
  公积金中心口径: "该成员住房公积金账户归属口径。市管和国管贷后还款规则不同，购房策略会优先按借款申请人的口径自动选择按月抵月供或半年度冲本金。",
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
  公积金账户还贷策略: "买房后如何使用公积金账户余额。按月约定提取用于抵扣当期公积金贷月供；半年度冲本金在约定月集中冲抵本金，不能与约定提取同时启用。",
  商贷提前还本策略: "选择是否让后端自动生成商贷额外还本。自动模式会比较商贷利率、理财预期净收益、买卖手续费和现金安全垫：只有提前还本的确定性收益更划算时才安排；手动指定则按下方参数固定测算。",
  商贷提前还本上限: "自动模式下作为每月额外还本上限，填 0 表示由系统按商贷本金和现金流自动设定；手动模式下表示每月额外还本金额。",
  希望起始还本月: "从第几个商贷还款月开始额外还本金；若早于合同允许月份，后端会自动顺延。",
  合同允许最早月: "银行合同允许提前还本的最早还款月。不同银行可能有一年后、金额限制或违约金，建议按实际合同填写。",
  政策契税比例: "由政策规则包按首套/二套和房屋面积计算，计入买房交易现金需求。",
  政策契税金额: "按候选房源总价乘以后端政策契税比例得到。",
  中介费假设: "中介服务费属于市场交易成本假设，可按实际报价手动覆盖。",
  装修预算: "预计装修需要的总资金。可选择交易前准备或买房后慢慢攒。",
  装修资金: "决定装修预算是计入交易现金，还是买房后用月结余逐步积累。",
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
  车辆使用年限: "用于提示家庭何时考虑更新车辆。私家小微非营运车通常不是固定年限强制报废。",
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
  子女数: "用于家庭状态、幸福指数和部分政策判断，不能为负。",
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

const existingLoanTypeLabels: Record<NonNullable<PhasedLoanData["loan_type"]>, string> = {
  mortgage: "房贷",
  car: "车贷",
  education: "教育贷款",
  consumer: "消费贷款",
  other: "其他贷款"
};

const renovationFundingLabels: Record<RenovationFundingMode, string> = {
  after_purchase_saving: "买后攒钱装修",
  upfront_cash: "交易前准备装修款"
};

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
  return Math.max(
    0,
    household.monthly_expense +
      scheduledExpenseRowsAt(household, baseDate, monthsFromNow).reduce((sum, item) => sum + item.amount, 0)
  );
}

function scheduledExpenseRowsAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  return (household.scheduled_expenses ?? []).flatMap((item) => {
    const start = parseMonthValue(item.start_month);
    const end = parseMonthValue(item.end_month);
    if (!start || compareMonth(targetMonth, start) < 0) return [];
    if (end && compareMonth(targetMonth, end) > 0) return [];
    const amount = Math.max(0, item.monthly_amount);
    return amount > 0 ? [{ name: item.name || "定时支出", amount }] : [];
  });
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
    monthly_salary_gross: member.monthly_salary_gross,
    annual_bonus: member.annual_bonus,
    annual_bonus_payout_month: 4,
    monthly_freelance_income: 0,
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
  const stages = member.income_stages?.length ? member.income_stages : [incomeStageFromMember(member)];
  return stages.map((stage) => ({
    ...stage,
    stage_kind: stage.stage_kind ?? "salary",
    annual_bonus_payout_month: stage.annual_bonus_payout_month ?? 4,
    monthly_freelance_income: stage.monthly_freelance_income ?? 0,
    monthly_non_taxable_income: stage.monthly_non_taxable_income ?? 0,
    monthly_extra_cash_expense: stage.monthly_extra_cash_expense ?? 0,
    payroll_contributions_enabled: stage.payroll_contributions_enabled ?? true
  }));
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


export function App() {
  const [households, setHouseholds] = useState<RecordEnvelope<HouseholdData>[]>([]);
  const [scenarios, setScenarios] = useState<RecordEnvelope<ScenarioData>[]>([]);
  const [rulePacks, setRulePacks] = useState<RecordEnvelope<RulePackData>[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(noPurchaseScenarioId);
  const [scenarioResults, setScenarioResults] = useState<Record<string, AffordabilityResult>>({});
  const [selectedPlanVariants, setSelectedPlanVariants] = useState<Record<string, string>>({});
  const [activePage, setActivePage] = useState<PageName>("家庭财务");
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

  const household = households[0];
  const selectedScenario = scenarios.find((item) => item.id === selectedScenarioId) ?? scenarios[0] ?? noPurchaseScenario;
  const activeRulePack = rulePacks.find((item) => item.data.status === "active") ?? rulePacks[0];
  const hasCurrentCalculation = calculatedVersion === calculationVersion && !isCalculating;
  const calculationPending = !hasCurrentCalculation;
  const displayScenarioResults = hasCurrentCalculation ? scenarioResults : {};
  const result = selectedScenario ? displayScenarioResults[selectedScenario.id] ?? null : null;
  const incomeMembers = household?.data.members ?? [];
  const carPlan = household?.data.car_plan ?? defaultCarPlan;
  const phasedLoans = household?.data.phased_loans ?? [];
  const scheduledExpenses = household?.data.scheduled_expenses ?? [];
  const elderlyDependents = household?.data.elderly_dependents ?? [];
  const selectedPlanVariant = selectedScenario
    ? selectedScenario.data.selected_purchase_plan_variant || selectedPlanVariants[selectedScenario.id] || ""
    : "";
  const currentRecommendation = useMemo(
    () => result ? recommendedPurchasePlan(result.purchase_plan_analyses) : null,
    [result]
  );
  const selectedPlan =
    result?.purchase_plan_analyses.find((plan) => plan.variant === selectedPlanVariant) ??
    currentRecommendation ??
    result?.purchase_plan_analyses[0] ??
    null;
  const scenarioComparisons = useMemo<ScenarioComparison[]>(
    () => scenarios
      .filter((scenario) => scenario.data.enabled)
      .map((scenario): ScenarioComparison | null => {
        const scenarioResult = displayScenarioResults[scenario.id];
        if (!scenarioResult) return null;
        const recommendation = recommendedPurchasePlan(scenarioResult.purchase_plan_analyses);
        const selectedVariant = scenario.data.selected_purchase_plan_variant || selectedPlanVariants[scenario.id];
        const selectedPlan =
          scenarioResult.purchase_plan_analyses.find((plan) => plan.variant === selectedVariant) ??
          recommendation ??
          scenarioResult.purchase_plan_analyses[0] ??
          null;
        return { scenario, result: scenarioResult, recommendation, selectedPlan };
      })
      .filter((item): item is ScenarioComparison => item !== null),
    [displayScenarioResults, scenarios, selectedPlanVariants]
  );

  const markDirty = (affectsCalculation = true) => {
    dirtyVersionRef.current += 1;
    setSaveState("dirty");
    if (affectsCalculation) setCalculationVersion((version) => version + 1);
  };

  const updateHousehold = <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => {
    markDirty(key !== "name");
    setHouseholds((items) => items.map((item, index) => index === 0 ? { ...item, data: { ...item.data, [key]: value } } : item));
  };
  const updateHouseholdPatch = (patch: Partial<HouseholdData>) => {
    markDirty(!Object.keys(patch).every((key) => key === "name"));
    setHouseholds((items) => items.map((item, index) => index === 0 ? { ...item, data: { ...item.data, ...patch } } : item));
  };
  const updateScenario = <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => {
    if (!selectedScenario || selectedScenario.id === noPurchaseScenarioId) return;
    markDirty(!["selected_purchase_plan_variant", "name", "district", "ring_area"].includes(String(key)));
    setScenarios((items) => items.map((item) => item.id === selectedScenario.id ? { ...item, data: { ...item.data, [key]: value } } : item));
  };
  const updateScenarioRecord = (id: string, patch: Partial<ScenarioData>) => {
    if (id === noPurchaseScenarioId) return;
    markDirty(!Object.keys(patch).every((key) => ["selected_purchase_plan_variant", "name", "district", "ring_area"].includes(key)));
    setScenarios((items) => items.map((item) => item.id === id ? { ...item, data: { ...item.data, ...patch } } : item));
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
    const nextMembers = incomeMembers.map((member, memberIndex) => memberIndex === index ? { ...member, [key]: value, ...memberPatch } : member);
    updateHousehold("members", nextMembers);
    if (key === "name" || key === "birth_month" || key === "current_age" || key === "retirement_category") {
      updateHousehold("career_shock", normalizeCareerShockForMembers(household.data.career_shock, nextMembers));
    }
  };
  const addIncomeMember = () => {
    if (!household) return;
    const nextMember: IncomeMember = {
      name: `成员 ${incomeMembers.length + 1}`,
      birth_month: "",
      current_age: 30,
      retirement_category: defaultRetirementCategoryForMember(incomeMembers.length),
      provident_account_management_center: "beijing_municipal",
      provident_fund_balance: 0,
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
        birth_month: "",
        current_age: 30,
        retirement_category: defaultRetirementCategoryForMember(incomeMembers.length),
        provident_account_management_center: "beijing_municipal",
        provident_fund_balance: 0,
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
        annual_bonus: firstStage.annual_bonus,
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
        annual_bonus: firstStage.annual_bonus,
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
      return { ...member, income_stages: [...stages, { ...stages[stages.length - 1], name: `收入阶段 ${stages.length + 1}`, start_date: "2028-01-01", end_date: null }] };
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
  const removeScheduledExpense = (index: number) => updateHousehold("scheduled_expenses", scheduledExpenses.filter((_, itemIndex) => itemIndex !== index));
  const updateElderlyDependent = <K extends keyof ElderlyDependentData>(index: number, key: K, value: ElderlyDependentData[K]) => updateHousehold("elderly_dependents", updateArrayItem(elderlyDependents, index, key, value));
  const addElderlyDependent = () => updateHousehold("elderly_dependents", [...elderlyDependents, { member_name: incomeMembers[0]?.name ?? "成员 1", relationship_label: "直系亲属老人", birth_month: "", is_only_child: false, shared_monthly_deduction: 1500 }]);
  const removeElderlyDependent = (index: number) => updateHousehold("elderly_dependents", elderlyDependents.filter((_, itemIndex) => itemIndex !== index));

  const updateCarPlan = <K extends keyof CarPlanData>(key: K, value: CarPlanData[K]) => updateHousehold("car_plan", { ...carPlan, [key]: value });
  const updateCarPlanPatch = (patch: Partial<CarPlanData>) => updateHousehold("car_plan", { ...carPlan, ...patch });
  const updateCarPlanSelection = (vehicleIndex: number, variant: string) => {
    markDirty(false);
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
  };
  const setSelectedPlanVariant = (variant: string) => {
    if (!selectedScenario) return;
    setSelectedPlanVariants((items) => ({ ...items, [selectedScenario.id]: variant }));
    if (selectedScenario.id !== noPurchaseScenarioId) updateScenario("selected_purchase_plan_variant", variant);
  };

  const addScenario = async (patch: Partial<ScenarioData> = {}) => {
    const sequence = Math.max(1, patch.purchase_sequence ?? scenarios.length + 1);
    const created = await createScenario({
      ...createTargetScenarioData(sequence),
      annual_investment_return: selectedScenario.data.annual_investment_return ?? 0.025,
      ...patch
    });
    setScenarios((items) => [...items, completeScenarioDefaults(created, items.length)]);
    setSelectedScenarioId(created.id);
    markDirty(true);
  };
  const removeScenario = async (id: string) => {
    setScenarios((items) => {
      const nextScenarios = items.filter((item) => item.id !== id);
      if (selectedScenarioId === id) setSelectedScenarioId(nextScenarios[0]?.id ?? noPurchaseScenarioId);
      return nextScenarios;
    });
    markDirty(true);
    await deleteScenario(id);
  };
  const removeScenarios = async (ids: string[]) => {
    const idSet = new Set(ids);
    setScenarios((items) => {
      const nextScenarios = items.filter((item) => !idSet.has(item.id));
      if (idSet.has(selectedScenarioId)) setSelectedScenarioId(nextScenarios[0]?.id ?? noPurchaseScenarioId);
      return nextScenarios;
    });
    markDirty(true);
    await Promise.all(ids.map((id) => deleteScenario(id)));
  };

  const runCalculation = useCallback(async () => {
    if (!household || !activeRulePack) return;
    const requestSeq = ++calculationSeqRef.current;
    const requestVersion = calculationVersion;
    setIsCalculating(true);
    setError(null);
    try {
      const scenariosForCalculation = scenarios.length > 0 ? scenarios : [noPurchaseScenario];
      const calculated = await Promise.all(scenariosForCalculation.map(async (scenario) => [scenario.id, await calculateAffordability(household.data, scenario.data, activeRulePack.data)] as const));
      if (requestSeq !== calculationSeqRef.current) return;
      setScenarioResults(Object.fromEntries(calculated));
      setCalculatedVersion(requestVersion);
    } catch (err) {
      if (requestSeq === calculationSeqRef.current) setError(err instanceof Error ? err.message : "计算失败");
    } finally {
      if (requestSeq === calculationSeqRef.current) setIsCalculating(false);
    }
  }, [activeRulePack, calculationVersion, household, scenarios]);

  const persistAll = useCallback(async () => {
    if (!household || !activeRulePack) return;
    const saveVersion = dirtyVersionRef.current;
    setSaving(true);
    setError(null);
    try {
      const scenarioRecordsToSave = scenarios.filter((scenario) => scenario.id !== noPurchaseScenarioId);
      const [savedHousehold, savedScenarios, savedRulePack] = await Promise.all([
        saveHousehold(household.id, household.data),
        Promise.all(scenarioRecordsToSave.map((scenario) => saveScenario(scenario.id, scenario.data))),
        saveRulePack(activeRulePack.id, activeRulePack.data)
      ]);
      if (dirtyVersionRef.current === saveVersion) {
        setHouseholds((items) => items.map((item) => item.id === savedHousehold.id ? completeHouseholdDefaults(savedHousehold) : item));
        if (savedScenarios.length) {
          setScenarios((items) => items.map((item, index) => {
            const savedScenario = savedScenarios.find((scenario) => scenario.id === item.id);
            return savedScenario ? completeScenarioDefaults(savedScenario, index) : item;
          }));
        }
        setRulePacks((items) => items.map((item) => item.id === savedRulePack.id ? savedRulePack : item));
        setSaveState("saved");
      } else {
        setSaveState("dirty");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }, [activeRulePack, household, scenarios]);
  const previewSource = async () => setSourcePreview(await fetchSourcePreview(sourceUrl));

  useEffect(() => {
    let active = true;
    loadInitialData()
      .then(([householdRecords, scenarioRecords, ruleRecords]) => {
        if (!active) return;
        setHouseholds(householdRecords.map(completeHouseholdDefaults));
        setScenarios(scenarioRecords.map(completeScenarioDefaults));
        setRulePacks(ruleRecords);
        setSelectedScenarioId(scenarioRecords[0]?.id ?? noPurchaseScenarioId);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
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
    if (activePage === "家庭财务") return <IncomePage household={household.data} scenario={selectedScenario.data} incomeMembers={incomeMembers} phasedLoans={phasedLoans} scheduledExpenses={scheduledExpenses} elderlyDependents={elderlyDependents} result={result} updateHousehold={updateHousehold} updateIncomeMember={updateIncomeMember} addIncomeMember={addIncomeMember} removeIncomeMember={removeIncomeMember} updateIncomeStage={updateIncomeStage} updateIncomeStagePatch={updateIncomeStagePatch} addIncomeStage={addIncomeStage} removeIncomeStage={removeIncomeStage} updatePhasedLoan={updatePhasedLoan} addPhasedLoan={addPhasedLoan} removePhasedLoan={removePhasedLoan} updateScheduledExpense={updateScheduledExpense} addScheduledExpense={addScheduledExpense} removeScheduledExpense={removeScheduledExpense} updateElderlyDependent={updateElderlyDependent} addElderlyDependent={addElderlyDependent} removeElderlyDependent={removeElderlyDependent} />;
    if (activePage === "理财计划") return <InvestmentPlanPage household={household.data} scenario={selectedScenario.data} result={result} updateHousehold={updateHousehold} updateHouseholdPatch={updateHouseholdPatch} updateInvestmentAnnualReturn={updateInvestmentAnnualReturn} />;
    if (activePage === "购房计划") return <ScenarioPage scenarios={scenarios} hasPurchaseTargets={scenarios.length > 0} selectedScenario={selectedScenario} setSelectedScenarioId={setSelectedScenarioId} updateScenario={updateScenario} updateScenarioRecord={updateScenarioRecord} addScenario={addScenario} removeScenario={removeScenario} removeScenarios={removeScenarios} result={result} scenarioComparisons={scenarioComparisons} selectedPlanVariant={selectedPlanVariant} setSelectedPlanVariant={setSelectedPlanVariant} calculationPending={calculationPending} />;
    if (activePage === "购车计划") return <CarPlanPage carPlan={carPlan} result={result} updateCarPlan={updateCarPlan} updateCarPlanPatch={updateCarPlanPatch} updateCarPlanSelection={updateCarPlanSelection} calculationPending={calculationPending} />;
    if (activePage === "政策规则") return <RulePage activeRulePack={activeRulePack.data} ruleNumber={ruleNumber} updateRulePack={updateRulePack} updateRuleParam={updateRuleParam} sourceUrl={sourceUrl} setSourceUrl={setSourceUrl} sourcePreview={sourcePreview} previewSource={() => void previewSource()} saving={saving} />;
    if (activePage === "可视化") return <VisualizationPage result={result} household={household.data} selectedScenario={selectedScenario} scenarioComparisons={scenarioComparisons} setSelectedScenarioId={setSelectedScenarioId} selectedPlan={selectedPlan} selectedPlanVariant={selectedPlanVariant} setSelectedPlanVariant={setSelectedPlanVariant} activeRulePack={activeRulePack.data} calculationPending={calculationPending} />;
    return <ExportPage result={result} scenario={selectedScenario.data} selectedPlan={selectedPlan} selectedPlanVariant={selectedPlanVariant} setSelectedPlanVariant={setSelectedPlanVariant} runCalculation={runCalculation} />;
  })();

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <strong>豪斯计划</strong>
          <p>{isCalculating ? "后端正在重新计算" : saveState === "dirty" ? "有未保存修改" : "本地模型已就绪"}</p>
        </div>
        <div className="topbar-actions">
          {error ? <span className="error-text">{error}</span> : null}
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
      </header>
      <nav className="page-nav">
        {pages.map((page) => (
          <button key={page} className={page === activePage ? "page-tab active" : "page-tab"} onClick={() => setActivePage(page)} type="button">
            {page}
          </button>
        ))}
      </nav>
      <main className="page-workspace">{pageContent}</main>
    </div>
  );
}

function IncomePage({
  household,
  scenario,
  incomeMembers,
  phasedLoans,
  scheduledExpenses,
  elderlyDependents,
  result,
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
  removeScheduledExpense,
  updateElderlyDependent,
  addElderlyDependent,
  removeElderlyDependent
}: {
  household: HouseholdData;
  scenario: ScenarioData;
  incomeMembers: IncomeMember[];
  phasedLoans: PhasedLoanData[];
  scheduledExpenses: ScheduledExpenseData[];
  elderlyDependents: ElderlyDependentData[];
  result: AffordabilityResult | null;
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
  removeScheduledExpense: (index: number) => void;
  updateElderlyDependent: <K extends keyof ElderlyDependentData>(
    index: number,
    key: K,
    value: ElderlyDependentData[K]
  ) => void;
  addElderlyDependent: () => void;
  removeElderlyDependent: (index: number) => void;
}) {
  const currentMonthlyExpense = householdExpenseAt(household, new Date(), 0);
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
  const today = new Date();
  const memberAges = incomeMembers.map((member) => ageYearsFromBirthMonth(member.birth_month, today) ?? member.current_age ?? 30);
  const normalizedBorrowerMemberIndex = Math.min(
    Math.max(0, household.borrower_member_index ?? 0),
    Math.max(0, incomeMembers.length - 1)
  );
  const borrowerMember = incomeMembers[normalizedBorrowerMemberIndex] ?? incomeMembers[0];
  const borrowerMemberName = borrowerMember?.name || `成员 ${normalizedBorrowerMemberIndex + 1}`;
  const borrowerDisplayAge = memberAges[normalizedBorrowerMemberIndex] ?? household.borrower_age ?? 30;
  const borrowerAgeForPolicy = Math.min(68, Math.max(18, Math.round(borrowerDisplayAge ?? household.borrower_age ?? 30)));
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
    { label: "家庭成员与工资阶段", done: incomeMembers.some((member) => incomeStagesForMember(member).some((stage) => stage.monthly_salary_gross > 0 || stage.annual_bonus > 0)) },
    { label: "基础支出与定时支出", done: household.monthly_expense > 0 || scheduledExpenses.some((expense) => expense.monthly_amount > 0) },
    { label: "现金、投资和成员公积金账户", done: household.cash_account_balance > 0 || household.investments > 0 || incomeMembers.some((member) => (member.provident_fund_balance ?? 0) > 0) },
    { label: "已有贷款、赡养扣除和职业冲击", done: phasedLoans.length > 0 || elderlyDependents.length > 0 || Boolean(household.career_shock?.enabled) },
  ];
  const memberIncomeSection = (
    <section className="form-panel">
      <div className="member-header">
        <PanelTitle icon={<Banknote size={18} />} title="成员工资与收入阶段" />
        <span className="section-subtle-note">成员增删、出生年月和年龄在家庭画像中维护</span>
      </div>
      <div className="member-list roomy">
        {incomeMembers.map((member, index) => (
          <section className="member-card" key={`member-${index}`}>
            <div className="member-card-head income-member-head">
              <div>
                <strong>{member.name || `成员 ${index + 1}`}</strong>
                <small>{incomeStagesForMember(member).length} 个收入阶段</small>
              </div>
              <Field label="公积金中心口径">
                <select
                  value={member.provident_account_management_center ?? "beijing_municipal"}
                  onChange={(event) =>
                    updateIncomeMember(
                      index,
                      "provident_account_management_center",
                      event.target.value as IncomeMember["provident_account_management_center"]
                    )
                  }
                >
                  <option value="beijing_municipal">北京市管</option>
                  <option value="national">中央国家机关/国管</option>
                </select>
              </Field>
            </div>
            <div className="member-header compact-heading">
              <strong>收入阶段</strong>
              <button className="ghost-button" onClick={() => addIncomeStage(index)} type="button">
                <Plus size={15} /> 新增阶段
              </button>
            </div>
            <div className="stage-list">
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
                      disabled={incomeStagesForMember(member).length <= 1}
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
                          label="年终奖年额"
                          value={stage.annual_bonus}
                          min={0}
                          step={100}
                          onChange={(value) => updateIncomeStage(index, stageIndex, "annual_bonus", value)}
                        />
                        <NumberField
                          label="发放月份"
                          value={stage.annual_bonus_payout_month ?? 4}
                          min={1}
                          max={12}
                          step={1}
                          onChange={(value) => updateIncomeStage(index, stageIndex, "annual_bonus_payout_month", Math.round(value))}
                        />
                      </>
                    ) : null}
                    {freelanceEnabled ? (
                      <NumberField
                        label="自由职业收入/月"
                        value={stage.monthly_freelance_income ?? 0}
                        min={0}
                        step={100}
                        onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_freelance_income", value)}
                      />
                    ) : null}
                    <NumberField
                      label="非税收入/月"
                      value={stage.monthly_non_taxable_income ?? 0}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_non_taxable_income", value)}
                    />
                    <NumberField
                      label="额外现金支出/月"
                      value={stage.monthly_extra_cash_expense ?? 0}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_extra_cash_expense", value)}
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
            </div>
            <p className="field-hint">
              默认只有一段收入；新增阶段后，后端会按各阶段实际生效月份折算税费、年终奖和公积金。五险按北京社保基数、个人养老 8%、医疗 2%+3、失业 0.5% 自动计算。
            </p>
          </section>
        ))}
      </div>
    </section>
  );

  const assetCashSection = (
    <section className="form-panel income-workbench-card account-panel">
      <PanelTitle icon={<ShieldCheck size={18} />} title="账户与安全垫" />
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
          label="租房提取公积金/月"
          value={household.monthly_rent_from_housing_fund ?? 0}
          min={0}
          step={100}
          onChange={(value) => updateHousehold("monthly_rent_from_housing_fund", value)}
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
        <strong className="setting-group-title">成员公积金账户快照</strong>
        <div className="form-grid two">
          {incomeMembers.map((member, index) => (
            <NumberField
              key={`provident-balance-${index}`}
              label={`${member.name || `成员 ${index + 1}`}公积金余额`}
              value={member.provident_fund_balance ?? 0}
              min={0}
              step={1000}
              onChange={(value) => updateIncomeMember(index, "provident_fund_balance", value)}
            />
          ))}
        </div>
      </div>
      <p className="field-hint">
        当前可动用现金和当前投资资产是今天手动录入的资产快照；租房提取公积金按月均额度录入，但可视化和现金流按季度到账；现金安全垫月数 = 买房后希望至少保留的生活费月数。成员公积金余额在后端按成员账户分别计息、缴存、提取、按月抵月供和半年度冲本金。
      </p>
    </section>
  );

  return (
    <div className="page-stack income-page-stack">
      <SectionHeader icon={<ClipboardCheck size={20} />} title="家庭财务" />
      <section className="form-panel setup-guide">
        <PanelTitle icon={<Sparkles size={18} />} title="初始化指引" />
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
          <PanelTitle icon={<ClipboardCheck size={18} />} title="家庭画像" />
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
                label="子女数"
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
              <NumberField
                label="社保/个税月数"
                value={household.social_security_months}
                step={1}
                min={0}
                onChange={(value) => updateHousehold("social_security_months", value)}
              />
              <NumberField
                label="现有住房套数"
                value={household.existing_home_count}
                min={0}
                max={10}
                step={1}
                onChange={(value) => updateHousehold("existing_home_count", value)}
              />
              <NumberField
                label="现有房贷笔数"
                value={household.existing_mortgage_count}
                min={0}
                max={10}
                step={1}
                onChange={(value) => updateHousehold("existing_mortgage_count", value)}
              />
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
                    <Field label="出生年月">
                      <input
                        type="month"
                        value={member.birth_month ?? ""}
                        onChange={(event) => updateIncomeMember(index, "birth_month", event.target.value)}
                      />
                    </Field>
                    <Field label="退休身份">
                      <select
                        value={member.retirement_category ?? defaultRetirementCategoryForMember(index)}
                        onChange={(event) => updateIncomeMember(index, "retirement_category", event.target.value as IncomeMember["retirement_category"])}
                      >
                        {Object.entries(retirementCategoryLabels).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <div className="derived-field">
                      <span>当前年龄</span>
                      <strong>{member.birth_month ? `${memberAges[index] ?? member.current_age ?? 30} 岁` : "填写出生年月后自动计算"}</strong>
                    </div>
                  </div>
                </section>
              ))}
            </div>
          </div>
          <p className="field-hint">
            家庭画像先维护成员组成、出生年月和购房资格参数；收入、支出、账户和负债在下方按财务工作流分区维护。借款申请人年龄会自动跟随所选成员。
          </p>
        </section>
      </div>

      {memberIncomeSection}

      <div className="income-detail-grid">
      <section className="form-panel income-workbench-card expense-panel">
        <div className="member-header">
          <PanelTitle icon={<WalletCards size={18} />} title="家庭支出" />
          <button className="ghost-button" onClick={addScheduledExpense}>
            <Plus size={16} /> 新增定时支出
          </button>
        </div>
        <div className="loan-summary-strip">
          <Metric label="基础月支出" value={money(household.monthly_expense)} />
          <Metric label="当前实际月支出" value={money(currentMonthlyExpense)} />
          <Metric
            label="定时月支出"
            value={money(Math.max(0, currentMonthlyExpense - household.monthly_expense))}
          />
        </div>
        <div className="form-grid">
          <NumberField
            label="基础月支出"
            value={household.monthly_expense}
            min={0}
            step={100}
            onChange={(value) => updateHousehold("monthly_expense", value)}
          />
          <NumberField
            label="其他固定还款/月"
            value={household.monthly_debt_payment}
            min={0}
            step={100}
            onChange={(value) => updateHousehold("monthly_debt_payment", value)}
          />
        </div>
        <div className="member-list compact-list">
          {scheduledExpenses.map((expense, index) => (
            <section className="member-card loan-card" key={`scheduled-expense-${index}`}>
              <div className="member-card-head">
                <strong>{expense.name || "定时支出"}</strong>
                <button
                  className="icon-button"
                  onClick={() => removeScheduledExpense(index)}
                  aria-label="删除定时支出"
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
                <NumberField
                  label="每月金额"
                  value={expense.monthly_amount}
                  min={0}
                  step={100}
                  onChange={(value) => updateScheduledExpense(index, "monthly_amount", value)}
                />
                <Field label="开始月份">
                  <input
                    type="month"
                    value={expense.start_month}
                    onChange={(event) => updateScheduledExpense(index, "start_month", event.target.value)}
                  />
                </Field>
                <Field label="结束月份">
                  <input
                    type="month"
                    value={expense.end_month ?? ""}
                    onChange={(event) => updateScheduledExpense(index, "end_month", event.target.value || null)}
                  />
                </Field>
              </div>
              <p className="expense-note-display">
                {expense.notes || "这项支出只作为家庭现金支出，不自动认定为个税专项扣除。"}
              </p>
            </section>
          ))}
        </div>
        <p className="field-hint">
          基础月支出从现在起计入现金流；定时支出只在开始月份后计入。家庭支持支出本身只影响现金流；老人专项附加扣除由下方“赡养老人专项扣除”的出生月份、归属成员和分摊方式自动判断，{elderlyPolicyStatus.detail}
        </p>
      </section>

      {assetCashSection}

      <section className="form-panel income-workbench-card career-panel">
        <PanelTitle icon={<AlertTriangle size={18} />} title="职业冲击与退休养老金" />
        <div className="loan-summary-strip">
          <Metric label="当前启用成员" value={careerShockSummaryText} tone={activeCareerShockSettings.length > 0 ? "warn" : undefined} />
          <Metric label="估算失业金月数" value={`${estimatedUnemploymentBenefitMonths} 个月`} />
          <Metric label="估算自缴社保/月" value={money(estimatedSelfSocialInsuranceMonthly)} />
          <Metric label="估算自缴公积金/月" value={money(estimatedFlexibleHousingFundMonthly)} />
        </div>
        <div className="setting-group">
          <strong className="setting-group-title">全局估算规则</strong>
          <div className="switch-grid">
            <SwitchField
              label="自动估算失业保险待遇"
              checked={careerShock.auto_unemployment_benefit}
              onChange={(checked) => updateCareerShock({ auto_unemployment_benefit: checked })}
            />
            <SwitchField
              label="自动估算灵活就业自缴"
              checked={careerShock.auto_self_social_insurance}
              onChange={(checked) => updateCareerShock({ auto_self_social_insurance: checked })}
            />
            <SwitchField
              label="自动估算灵活就业公积金"
              checked={careerShock.auto_flexible_housing_fund}
              onChange={(checked) => updateCareerShock({ auto_flexible_housing_fund: checked })}
            />
            <SwitchField
              label="自动估算退休养老金"
              checked={allMembersAutoPension}
              onChange={(checked) => {
                const member_settings = careerShock.member_settings.map((setting) => ({ ...setting, auto_pension_monthly: checked }));
                updateCareerShock({ member_settings });
              }}
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
          <div className="read-only-grid">
            {careerShock.auto_unemployment_benefit ? (
              <Metric
                label="自动估算失业金月额"
                value={
                  estimatedUnemploymentBenefitMonths > 12
                    ? `${money(estimatedUnemploymentBenefitMonthly)} / ${money(estimatedLaterUnemploymentBenefitMonthly)}`
                    : money(estimatedUnemploymentBenefitMonthly)
                }
              />
            ) : null}
            {careerShock.auto_self_social_insurance ? (
              <Metric label="自动估算自缴社保/月" value={money(estimatedSelfSocialInsuranceMonthly)} />
            ) : null}
            {careerShock.auto_flexible_housing_fund ? (
              <Metric label="自动估算自缴公积金/月" value={money(estimatedFlexibleHousingFundMonthly)} />
            ) : null}
          </div>
        </div>
        <div className="member-list compact-list career-member-list">
          {incomeMembers.map((member, index) => {
            const projection = careerShockProjection?.member_projections.find((item) => item.member_name === member.name);
            const setting = careerShock.member_settings[index] ?? {
              member_name: member.name || `成员 ${index + 1}`,
              enabled: false,
              layoff_age: 35,
              retirement_age: projection?.retirement_age ?? 63,
              freelance_income_monthly: 0,
              pension_monthly: 0,
              auto_pension_monthly: true
            };
            const policyRetirementAge = projection?.retirement_age;
            const estimatedPensionMonthly = projection?.pension_monthly ?? 0;
            const layoffDate = projection?.layoff_month ?? "等待后端计算";
            const retirementDate = projection?.retirement_month ?? "等待后端计算";
            return (
              <section className="member-card loan-card career-member-card" key={`career-shock-${index}`}>
                <div className="member-card-head">
                  <strong>{member.name || `成员 ${index + 1}`}</strong>
                  <SwitchField
                    label={setting.enabled ? "启用职业冲击" : "不启用职业冲击"}
                    checked={setting.enabled}
                    onChange={(checked) => updateMemberCareerShockSetting(index, { enabled: checked })}
                  />
                </div>
                <div className="form-grid structured-settings career-member-settings">
                  {setting.enabled ? (
                    <>
                      <NumberField label="裁员年龄" value={setting.layoff_age} min={18} max={80} step={1} onChange={(value) => updateMemberCareerShockSetting(index, { layoff_age: value })} />
                      <NumberField
                        label="冲击期自由职业收入/月"
                        value={setting.freelance_income_monthly ?? 0}
                        min={0}
                        step={100}
                        onChange={(value) => updateMemberCareerShockSetting(index, { freelance_income_monthly: value })}
                      />
                    </>
                  ) : null}
                  <SwitchField
                    label="自动估算养老金"
                    checked={setting.auto_pension_monthly ?? true}
                    onChange={(checked) => updateMemberCareerShockSetting(index, { auto_pension_monthly: checked })}
                  />
                  {!setting.auto_pension_monthly ? (
                    <NumberField label="手动养老金/月" value={setting.pension_monthly} min={0} step={500} onChange={(value) => updateMemberCareerShockSetting(index, { pension_monthly: value })} />
                  ) : null}
                </div>
                <div className="read-only-grid">
                  <Metric label="当前年龄" value={member.birth_month ? `${memberAges[index]} 岁` : "待填写出生年月"} />
                  <Metric label="预计裁员月份" value={setting.enabled ? layoffDate : "未启用"} tone={setting.enabled ? "warn" : undefined} />
                  <Metric label="政策退休年龄" value={policyRetirementAge ? `${policyRetirementAge} 岁` : "等待后端计算"} />
                  <Metric label="预计退休月份" value={retirementDate} />
                  <Metric label="预计养老金/月" value={money(estimatedPensionMonthly)} />
                  {setting.enabled ? (
                    <Metric label="冲击期自由职业收入" value={money(setting.freelance_income_monthly ?? 0)} />
                  ) : null}
                </div>
                {projection?.generated_stages?.length ? (
                  <p className="field-hint">
                    后端生成阶段：{projection.generated_stages.map((stage) => stage.name).join("；")}
                  </p>
                ) : (
                  <p className="field-hint">等待后端生成职业冲击和退休阶段。</p>
                )}
              </section>
            );
          })}
        </div>
        <p className="field-hint">
          职业冲击默认对所有成员关闭；需要压力测试时，只打开对应成员。当前年龄由家庭画像里的出生年月推导；退休年龄按规则包默认口径进入测算。裁员后会由后端生成失业金期、灵活就业自缴期和退休养老金阶段；若启用“冲击期自由职业收入/月”，这笔收入会进入这些自动阶段，默认不产生。
        </p>
      </section>

      <section className="form-panel income-workbench-card elderly-panel">
        <div className="member-header">
          <PanelTitle icon={<ShieldCheck size={18} />} title="赡养老人专项扣除" />
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
          <PanelTitle icon={<WalletCards size={18} />} title="已有贷款" />
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
    </div>
  );
}

function InvestmentPlanPage({
  household,
  scenario,
  result,
  updateHousehold,
  updateHouseholdPatch,
  updateInvestmentAnnualReturn
}: {
  household: HouseholdData;
  scenario: ScenarioData;
  result: AffordabilityResult | null;
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
  updateHouseholdPatch: (patch: Partial<HouseholdData>) => void;
  updateInvestmentAnnualReturn: (annualReturn: number) => void;
}) {
  const latestRecommendationsRef = useRef<InvestmentPlanRecommendation[]>([]);
  if (result?.investment_plan_recommendations?.length) {
    latestRecommendationsRef.current = result.investment_plan_recommendations;
  }
  const recommendations =
    result?.investment_plan_recommendations?.length
      ? result.investment_plan_recommendations
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
    cash_reserve_months: household.investment_cash_reserve_months ?? 6,
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
  const investmentReasonText =
    !result
      ? "等待后端计算理财推荐；推荐、月结余和安全垫都以后端返回为准。"
      : (recommendedInvestment?.monthly_investment ?? 0) > 0
        ? `系统建议先保留现金安全垫 ${money(currentInvestmentAllocation.reserve_target)}；现金垫不足时先补现金，现金垫超额时按节奏追加定投。当前最高分方案建议 ${money(recommendedInvestment?.monthly_investment ?? 0)}/月。`
        : currentInvestmentAllocation.reserve_gap > 0
          ? `系统建议月定投为 0，是因为现金安全垫还差 ${money(currentInvestmentAllocation.reserve_gap)}，当前月结余会优先补足现金池和购房首付，不先进入波动资产。`
          : "系统建议月定投为 0，是因为当前最高分方案选择了“暂停定投保现金”；可在下方采用稳健/均衡/进取方案后再手动微调。";
  const allocationData = [
    { name: "权益", 比例: Math.round((household.investment_equity_ratio ?? 0.25) * 100) },
    { name: "固收", 比例: Math.round((household.investment_bond_ratio ?? 0.45) * 100) },
    { name: "现金", 比例: Math.round((household.investment_cash_ratio ?? 0.3) * 100) }
  ];
  const applyInvestmentPlan = (plan: InvestmentPlanRecommendation) => {
    updateHouseholdPatch({
      investment_plan_name: plan.plan_name,
      investment_risk_level: plan.risk_level,
      monthly_investment_amount: plan.monthly_investment,
      investment_cash_reserve_months: plan.cash_reserve_months,
      investment_equity_ratio: plan.equity_ratio,
      investment_bond_ratio: plan.bond_ratio,
      investment_cash_ratio: plan.cash_ratio,
      investment_auto_rebalance: true
    });
    updateInvestmentAnnualReturn(plan.annual_return);
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

  return (
    <div className="page-stack">
      <SectionHeader icon={<TrendingUp size={20} />} title="理财计划" />
      <section className="result-panel investment-dashboard">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Sparkles size={18} />} title="自动管理概览" compact />
          <span>用于购房测算的年化和资产增长口径，不代表具体产品建议</span>
        </div>
        <div className="metric-grid">
          <Metric label="当前投资资产" value={money(household.investments)} />
          <Metric label="系统建议月定投" value={money(recommendedInvestment?.monthly_investment ?? 0)} />
          <Metric label="当前已设定投" value={money(household.monthly_investment_amount ?? 0)} />
          <Metric label="当前月结余" value={money(currentInvestmentAllocation.monthly_surplus)} tone={currentInvestmentAllocation.monthly_surplus > 0 ? "good" : "bad"} />
          <Metric label="现金安全垫目标" value={money(currentInvestmentAllocation.reserve_target)} />
          <Metric label="安全垫缺口" value={money(currentInvestmentAllocation.reserve_gap)} tone={currentInvestmentAllocation.reserve_gap > 0 ? "warn" : "good"} />
          <Metric label="安全垫达标后追加定投" value={money(currentInvestmentAllocation.cash_sweep_investment)} tone={currentInvestmentAllocation.cash_sweep_investment > 0 ? "good" : undefined} />
          <Metric label="测算年化" value={percent(household.investment_plan_name === "cash_only" ? 0 : scenario.annual_investment_return ?? 0)} />
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
              收益留在投资账户内复利；买入手续费从当月投入中扣除，买房变现时由后端按卖出费率扣除后进入现金账户。
            </p>
          </div>
        </div>
        <p className="field-hint investment-explain">{investmentReasonText}</p>
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
            <span>买入手续费从定投资金扣除，收益留在投资账户复利；交易月需要变现时，后端再扣除卖出手续费。</span>
          </article>
        </div>
        <div className="investment-layout">
          <section className="investment-settings">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="手动参数" compact />
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
              达到现金安全垫后，系统会把超过安全垫的闲置现金按 12 个月节奏追加到定投；买入手续费从定投资金里扣除，理财收益留在投资资产里继续复利，买房变现时再扣卖出手续费。
            </p>
          </section>
          <section className="investment-allocation">
            <PanelTitle icon={<Gauge size={18} />} title="目标配置" compact />
            <ResponsiveContainer width="100%" height={220}>
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
              <Row label="安全垫达标后追加" value={money(currentInvestmentAllocation.cash_sweep_investment)} />
              <Row label="实际本月定投" value={money(currentInvestmentAllocation.total_investment)} />
              <Row label="买入手续费率" value={percent(household.investment_buy_fee_rate ?? 0.0015)} />
              <Row label="卖出手续费率" value={percent(household.investment_sell_fee_rate ?? 0.005)} />
              <Row label="月定投占结余" value={currentInvestmentAllocation.monthly_surplus > 0 ? percent(currentInvestmentAllocation.total_investment / currentInvestmentAllocation.monthly_surplus) : "0.0%"} />
              <Row label="当前采用" value={activeRecommendation?.variant ?? "手动设置"} />
            </div>
          </section>
        </div>
      </section>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Target size={18} />} title="理财策略方案" compact />
          <span>包含手动指定和自动生成方案，采用后会影响可视化里的资产曲线</span>
        </div>
        <div className="strategy-grid">
          {displayedRecommendations.map((plan) => {
            const active = activeInvestmentPlanName === plan.plan_name || activeInvestmentRecommendationName === plan.plan_name;
            return (
              <article className={`strategy-card investment-card ${active ? "active" : ""}`} key={plan.variant}>
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
                  {investmentStrategyDetails(plan.variant).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <div className="strategy-metrics">
                  <Metric label="月定投" value={money(plan.monthly_investment)} />
                  <Metric label="测算年化" value={percent(plan.annual_return)} />
                  <Metric label="风险类型" value={plan.risk_label} />
                  <Metric label="现金垫" value={`${plan.cash_reserve_months} 个月`} />
                </div>
                <div className="investment-ratio-row">
                  <span style={{ width: `${plan.equity_ratio * 100}%` }} />
                  <span style={{ width: `${plan.bond_ratio * 100}%` }} />
                  <span style={{ width: `${plan.cash_ratio * 100}%` }} />
                </div>
                <p className="strategy-note">{plan.reasons.join("；")}</p>
                <AdoptStrategyButton active={active} onClick={() => applyInvestmentPlan(plan)} />
              </article>
            );
          })}
        </div>
      </section>
    </div>
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
  scenarioComparisons,
  selectedPlanVariant,
  setSelectedPlanVariant,
  calculationPending
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
  scenarioComparisons: ScenarioComparison[];
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  calculationPending: boolean;
}) {
  const generatedPlans = result?.purchase_plan_analyses ?? [];
  const recommended = useMemo(() => recommendedPurchasePlan(generatedPlans), [generatedPlans]);
  const selectedPlan =
    generatedPlans.find((plan) => plan.variant === selectedPlanVariant) ??
    recommended ??
    generatedPlans[0] ??
    null;
  const recommendationByVariant = useMemo(
    () => purchaseRecommendationByVariant(generatedPlans),
    [generatedPlans]
  );
  const scenarioTimingLabel = (scenario: ScenarioData) => {
    if (!scenario.enabled) return "暂不纳入规划";
    if (scenario.purchase_planning_mode === "parallel") return "允许并行考虑";
    return scenario.purchase_sequence <= 1
      ? "自动安排"
      : `排在第 ${scenario.purchase_sequence - 1} 个目标之后 ${scenario.after_previous_purchase_delay_months || 0} 个月`;
  };
  const selectedPropertyType = selectedScenario.data.property_type ?? "二手房";
  const isSecondHandProperty = selectedPropertyType.includes("二手");
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
  const purchaseDemandGroups = useMemo(() => {
    const groups = new Map<number, RecordEnvelope<ScenarioData>[]>();
    scenarios.forEach((scenario) => {
      const sequence = Math.max(1, scenario.data.purchase_sequence || 1);
      groups.set(sequence, [...(groups.get(sequence) ?? []), scenario]);
    });
    return Array.from(groups.entries())
      .sort(([left], [right]) => left - right)
      .map(([sequence, items]) => ({
        sequence,
        items: items.slice().sort((left, right) => left.created_at.localeCompare(right.created_at)),
      }));
  }, [scenarios]);
  const selectedDemand =
    purchaseDemandGroups.find((group) => group.sequence === selectedScenario.data.purchase_sequence) ??
    purchaseDemandGroups[0] ??
    { sequence: 1, items: [] };
  const selectedDemandScenarios = selectedDemand.items;
  const demandLabel = (sequence: number) => sequence <= 1 ? "第一套购房需求" : `第 ${sequence} 套购房需求`;
  const candidateLabel = (index: number) => `候选房源 ${index + 1}`;
  const demandTimingLabel = (items: RecordEnvelope<ScenarioData>[]) => scenarioTimingLabel(items[0]?.data ?? selectedScenario.data);
  const updateSelectedDemand = (patch: Partial<ScenarioData>) => {
    selectedDemandScenarios.forEach((scenario) => updateScenarioRecord(scenario.id, patch));
  };
  const addPurchaseDemand = () => {
    const nextSequence = Math.max(0, ...purchaseDemandGroups.map((group) => group.sequence)) + 1;
    addScenario({
      name: `${demandLabel(nextSequence)} · 候选房源 1`,
      purchase_sequence: nextSequence,
      purchase_planning_mode: nextSequence <= 1 ? "parallel" : "after_previous_purchase",
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
      <div className="page-stack strategy-workbench">
        <SectionHeader
          icon={<Target size={20} />}
          title="购房计划"
          action={
            <button className="ghost-button" onClick={addPurchaseDemand}>
              <Plus size={16} /> 添加购房需求
            </button>
          }
        />
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
          <PanelTitle icon={<Home size={18} />} title="购房需求与候选房源" compact />
          <div className="empty-state target-empty-state">
            <strong>默认不买房</strong>
            <span>当前没有购房需求，购房策略、房贷、公积金贷款和交易事件都不会进入计划。</span>
            <button className="primary-button" onClick={addPurchaseDemand}>
              <Plus size={16} /> 添加购房需求
            </button>
          </div>
        </section>
        <section className="result-panel">
          <PanelTitle icon={<ClipboardCheck size={18} />} title="多套房管理逻辑" compact />
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
      </div>
    );
  }

  return (
    <div className="page-stack strategy-workbench">
      <SectionHeader
        icon={<Target size={20} />}
          title="购房计划"
          action={
          <button className="ghost-button" onClick={addPurchaseDemand}>
            <Plus size={16} /> 新增购房需求
          </button>
        }
      />

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
            <p>{calculationPending ? "正在按最新条件重新生成推荐策略。" : "调整购房目标后会自动生成推荐策略。"}</p>
          )}
        </div>
        <div className="strategy-hero-side">
          <Metric
            label={hasPurchaseTargets ? "房源总价" : "购房需求"}
            value={hasPurchaseTargets ? money(selectedScenario.data.total_price) : "未添加"}
          />
          <Metric
            label={hasPurchaseTargets ? "选中策略" : "当前模式"}
            value={hasPurchaseTargets ? selectedPlan?.variant ?? "待生成" : "不买房基线"}
            tone={selectedPlan?.liquidity_ok ? "good" : "warn"}
          />
          <Metric
            label={hasPurchaseTargets ? "预计买入" : "下一步"}
            value={
              hasPurchaseTargets
                ? selectedPlan?.years_to_buy === null ? "暂不可达" : `${selectedPlan?.years_to_buy ?? "-"} 年`
                : "手动添加第一套房"
            }
          />
        </div>
      </section>

      <div className="strategy-layout">
        <aside className="strategy-side-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<Home size={18} />} title="购房需求与候选房源" compact />
          </div>
          <div className="planning-goal-grid purchase-demand-grid">
            {purchaseDemandGroups.map((group) => {
              const firstScenario = group.items[0];
              const active = group.sequence === selectedDemand.sequence;
              const enabledCount = group.items.filter((item) => item.data.enabled).length;
              return (
                <article className={active ? "planning-goal-card active" : "planning-goal-card"} key={`purchase-demand-${group.sequence}`}>
                  <button type="button" className="planning-goal-select" onClick={() => firstScenario && setSelectedScenarioId(firstScenario.id)}>
                    <span className={enabledCount > 0 ? "goal-status enabled" : "goal-status paused"}>
                      {enabledCount > 0 ? "纳入规划" : "已停用"}
                    </span>
                    <strong>{demandLabel(group.sequence)}</strong>
                    <small>{group.items.length} 个候选房源 · 顺序 {group.sequence}</small>
                    <em>{demandTimingLabel(group.items)}</em>
                  </button>
                  <div className="planning-goal-actions">
                    <button className="ghost-button small" type="button" onClick={() => firstScenario && setSelectedScenarioId(firstScenario.id)}>
                      编辑
                    </button>
                    <button className="ghost-button small" type="button" onClick={() => addPropertyCandidate(group.sequence)}>
                      <Plus size={14} /> 候选
                    </button>
                    <button className="ghost-button small" type="button" onClick={() => active && updateSelectedDemand({ enabled: enabledCount <= 0 })} disabled={!active}>
                      {enabledCount > 0 ? "停用" : "启用"}
                    </button>
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
          <div className="vehicle-source-toolbar property-source-toolbar">
            <strong>{demandLabel(selectedDemand.sequence)}的候选房源</strong>
            <button className="ghost-button small" type="button" onClick={() => addPropertyCandidate(selectedDemand.sequence)}>
              <Plus size={14} /> 添加候选房源
            </button>
          </div>
          <div className="vehicle-source-grid property-source-grid">
            {selectedDemandScenarios.map((item, candidateIndex) => (
              <article className={item.id === selectedScenario.id ? "vehicle-source-card active" : "vehicle-source-card"} key={item.id}>
                <div className="vehicle-source-head">
                  <button type="button" className="planning-goal-select compact-select" onClick={() => setSelectedScenarioId(item.id)}>
                    <span className={item.data.enabled ? "goal-status enabled" : "goal-status paused"}>
                      {item.data.enabled ? "纳入规划" : "已停用"}
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
                    编辑
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => duplicatePropertyCandidate(item)}>
                    <Copy size={14} /> 复制
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => updateScenarioRecord(item.id, { enabled: !item.data.enabled })}>
                    {item.data.enabled ? "停用" : "启用"}
                  </button>
                </div>
              </article>
            ))}
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
            <section className="setting-group">
              <strong className="setting-group-title">购房需求</strong>
              <div className="form-grid two">
                <SwitchField
                  label={selectedDemandScenarios.some((item) => item.data.enabled) ? "纳入当前规划" : "暂不纳入规划"}
                  checked={selectedDemandScenarios.some((item) => item.data.enabled)}
                  onChange={(checked) => updateSelectedDemand({ enabled: checked })}
                />
                <NumberField
                  label="购房顺序"
                  value={selectedDemand.sequence}
                  min={1}
                  max={20}
                  step={1}
                  onChange={(value) => updateSelectedDemand({ purchase_sequence: Math.max(1, value || 1) })}
                />
                <NumberField
                  label="上一套后等待月数"
                  value={selectedScenario.data.after_previous_purchase_delay_months}
                  min={0}
                  max={240}
                  step={1}
                  onChange={(value) => updateSelectedDemand({ after_previous_purchase_delay_months: value })}
                />
                <Field label="购房时间规则">
                  <select
                    value={selectedScenario.data.purchase_planning_mode}
                    onChange={(event) =>
                      updateSelectedDemand({ purchase_planning_mode: event.target.value as ScenarioData["purchase_planning_mode"] })
                    }
                  >
                    <option value="after_previous_purchase">按规划顺序排队</option>
                    <option value="parallel">可并行考虑</option>
                  </select>
                </Field>
              </div>
            </section>

            <section className="setting-group">
              <strong className="setting-group-title">候选房源身份</strong>
              <div className="form-grid two">
                <SwitchField
                  label={selectedScenario.data.enabled ? "纳入当前规划" : "暂不纳入规划"}
                  checked={selectedScenario.data.enabled}
                  onChange={(checked) => updateScenario("enabled", checked)}
                />
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
                  <input
                    value={selectedScenario.data.ring_area}
                    onChange={(event) => updateScenario("ring_area", event.target.value)}
                  />
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
            </section>

            <section className="setting-group">
              <strong className="setting-group-title">价格与贷款</strong>
              <div className="form-grid two">
                <NumberField label="房源总价" value={selectedScenario.data.total_price} min={0} step={10000} onChange={(value) => updateScenario("total_price", value)} />
                <NumberField label="建筑面积" value={selectedScenario.data.area_sqm} min={0} step={1} onChange={(value) => updateScenario("area_sqm", value)} />
                <NumberField label="贷款年限" value={selectedScenario.data.loan_years} min={1} max={30} step={1} onChange={(value) => updateScenario("loan_years", value)} />
                <Field label="商贷还款">
                  <select
                    value={selectedScenario.data.commercial_repayment_method ?? selectedScenario.data.repayment_method}
                    onChange={(event) =>
                      updateScenario("commercial_repayment_method", event.target.value as RepaymentMethod)
                    }
                  >
                    <option value="equal_installment">等额本息</option>
                    <option value="equal_principal">等额本金</option>
                  </select>
                </Field>
                <Field label="公积金还款">
                  <select
                    value={selectedScenario.data.provident_repayment_method ?? selectedScenario.data.repayment_method}
                    onChange={(event) =>
                      updateScenario("provident_repayment_method", event.target.value as RepaymentMethod)
                    }
                  >
                    <option value="equal_installment">等额本息</option>
                    <option value="equal_principal">等额本金</option>
                  </select>
                </Field>
                <Field label="公积金账户还贷策略" description={parameterExplanations["公积金账户还贷策略"]}>
                  <select
                    value={selectedScenario.data.provident_account_repayment_strategy ?? "auto"}
                    onChange={(event) =>
                      updateScenario(
                        "provident_account_repayment_strategy",
                        event.target.value as ProvidentAccountRepaymentStrategy
                      )
                    }
                  >
                    {Object.entries(providentAccountRepaymentStrategyLabels).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </Field>
              </div>
            </section>

            <section className="setting-group">
              <strong className="setting-group-title">政策属性</strong>
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
            </section>
          </div>
        </aside>

        <section className="strategy-main-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="手动调整策略参数" compact />
            <span>修改后会自动重算推荐、贷款结构和现金流</span>
          </div>
          <div className="structured-settings strategy-settings-groups">
            <section className="setting-group">
              <strong className="setting-group-title">执行时间与贷款结构</strong>
              <div className="form-grid">
                <NumberField
                  label="手动买入延后月数"
                  value={selectedScenario.data.manual_purchase_delay_months ?? 0}
                  min={0}
                  max={360}
                  step={1}
                  onChange={(value) => updateScenario("manual_purchase_delay_months", value)}
                />
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
            </section>

            <section className="setting-group">
              <strong className="setting-group-title">交易成本与装修</strong>
              <div className="form-grid">
                <ReadOnlyField label="政策契税比例" value={selectedPlan ? percent(selectedPlan.deed_tax_rate) : "待生成"} />
                <ReadOnlyField label="政策契税金额" value={selectedPlan ? money(selectedPlan.deed_tax_amount) : "待生成"} />
                <NumberField label="中介费假设" value={selectedScenario.data.broker_fee_rate} min={0} max={0.2} step={0.001} onChange={(value) => updateScenario("broker_fee_rate", value)} />
                <NumberField label="装修预算" value={selectedScenario.data.renovation_cost} min={0} step={10000} onChange={(value) => updateScenario("renovation_cost", value)} />
                <NumberField label="搬家杂费" value={selectedScenario.data.moving_and_misc_cost} min={0} step={1000} onChange={(value) => updateScenario("moving_and_misc_cost", value)} />
                <Field label="装修资金">
                  <select
                    value={selectedScenario.data.renovation_funding_mode ?? "after_purchase_saving"}
                    onChange={(event) =>
                      updateScenario("renovation_funding_mode", event.target.value as RenovationFundingMode)
                    }
                  >
                    <option value="after_purchase_saving">买后攒钱装修</option>
                    <option value="upfront_cash">交易前准备装修款</option>
                  </select>
                </Field>
              </div>
            </section>

            <section className="setting-group">
              <strong className="setting-group-title">投资动用与偏好评分</strong>
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
            </section>
          </div>
          <p className="field-hint">
            手动买入延后月数只作用于“手动指定”策略，系统会从该月份开始校验现金安全；微量商贷手动比例填 0 时由系统在政策规则上下限内自动寻找更早可买且商贷尽量少的比例，填入比例后按该比例固定测算。理财年化、定投和手续费来自理财计划当前策略，购房页只决定交易时如何动用投资账户。商贷提前还本选择“策略自动生成”时，后端会在合同允许最早月之后比较商贷成本、理财预期净收益、现金安全和买后结余，再决定是否额外还本；选择“手动指定”时按你填写的起始月和每月金额测算。买房动用投资选择“自动优化提取”时，后端只卖出覆盖交易现金和安全垫所需的投资资产；选择“清空投资账户”才会在交易月全部变现；选择“手动保留余额”时按设定余额尽量保留长期投资。
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
                    <small>{scenario.data.property_type} · {money(scenario.data.total_price)}</small>
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
        />
      ) : null}
    </div>
  );
}

function StrategyNarrative({
  plan,
  scenario,
  recommendation,
  isRecommended
}: {
  plan: PurchasePlanAnalysis;
  scenario: ScenarioData;
  recommendation?: PurchasePlanAnalysis;
  isRecommended: boolean;
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
  const policyBasisText = `政策依据采用北京住房公积金官方口径：首套/二套分别读取规则包中的商贷和公积金最低首付比例，系统取更严格者；公积金贷款按“每缴存一年可贷 15 万元”随 ${purchaseMonthText} 的缴存时间增长，并受首套 ${money(1200000)}、二套 ${money(1000000)} 的基础最高额度、购房月收入还款能力和基本生活费保留约束。当前房源性质为「${propertyNatureText || "未标注"}」，符合绿色建筑、装配式建筑或超低能耗建筑时只取最高一项上浮，本方案上浮 ${money(plan.provident_policy_bonus)}，最终政策上限 ${money(plan.provident_policy_cap)}。`;
  const termBasisText = `贷款年限依据同时看手动设定年限、北京公积金最长 30 年、借款申请人年龄上限，以及二手房/老旧小区房龄或土地剩余年限；本方案采用公积金 ${plan.provident_loan_years} 年，理由：${plan.provident_loan_year_limit_reasons.join("；")}。`;
  const commercialPrepaymentText = plan.commercial_prepayment_enabled
    ? ` 商贷提前还本采用「${commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]}」：合同按第 ${plan.commercial_prepayment_allowed_after_month} 个还款月后才允许提前还本估算，实际从第 ${plan.commercial_prepayment_start_month} 个还款月起每月额外还本金 ${money(plan.commercial_prepayment_monthly_amount)}；按合同月供不降、缩短期限估算，预计 ${plan.commercial_actual_payoff_months} 个月结清，节省商贷利息约 ${money(plan.commercial_interest_saved_by_prepayment)}。`
    : ` 商贷提前还本策略为「${commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]}」，当前方案未安排额外还本，按合同还款节奏测算。`;
  const repaymentDetailText = `买后还款按两笔贷款分开计算：公积金贷 ${money(plan.provident_loan_amount)}，${plan.provident_loan_years} 年，${repaymentMethodLabels[plan.provident_repayment_method]}，首月/月供约 ${money(plan.provident_monthly_payment)}；商贷 ${money(plan.commercial_loan_amount)}，${plan.commercial_loan_years} 年，${repaymentMethodLabels[plan.commercial_repayment_method]}，首月/月供约 ${money(plan.commercial_monthly_payment)}。两者合计合同月供约 ${money(plan.total_monthly_payment)}，全周期利息约 ${money(plan.total_interest)}。${commercialPrepaymentText}${plan.provident_repayment_advice ? ` ${plan.provident_repayment_advice}` : ""}`;
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
    scenario.renovation_cost <= 0
      ? "当前房源未设置装修预算。"
      : plan.renovation_included_in_upfront_cash
        ? `装修预算 ${money(scenario.renovation_cost)} 已计入交易现金需求。`
        : plan.months_to_renovation === null
          ? `装修预算 ${money(scenario.renovation_cost)} 不计入交易现金；买后月结余不足，暂无法估算装修启动时间。`
          : plan.months_to_renovation === 0
            ? `装修预算 ${money(scenario.renovation_cost)} 不计入交易现金；买后回流现金已可覆盖装修。`
            : `装修预算 ${money(scenario.renovation_cost)} 不计入交易现金；买后按月结余约 ${money(plan.post_purchase_renovation_monthly_saving)} 攒钱，预计 ${formatMonthDate(timelineBaseDate, (plan.months_to_buy ?? 0) + plan.months_to_renovation)} 可启动装修。`;
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
          <p>{plan.renovation_included_in_upfront_cash ? "装修资金会随首付和税费一起占用交易前现金。" : "默认不把装修款硬塞进交易日现金需求，买后按真实月结余判断启动时间。"}</p>
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
  updateCarPlan,
  updateCarPlanPatch,
  updateCarPlanSelection,
  calculationPending
}: {
  carPlan: CarPlanData;
  result: AffordabilityResult | null;
  updateCarPlan: <K extends keyof CarPlanData>(key: K, value: CarPlanData[K]) => void;
  updateCarPlanPatch: (patch: Partial<CarPlanData>) => void;
  updateCarPlanSelection: (vehicleIndex: number, variant: string) => void;
  calculationPending: boolean;
}) {
  const carStrategies = result?.car_plan_analyses ?? [];
  const vehiclePlans = carPlan.vehicle_plans ?? [];
  const [selectedVehicleIndex, setSelectedVehicleIndex] = useState(0);
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
      .map((vehicle, index) => resolveActiveCarStrategy(vehicle, index)?.variant)
      .filter(Boolean)
  );
  const strategyDecisionTone = (strategy: CarPlanAnalysis) => {
    if (strategy.cash_after_purchase < 0 || strategy.monthly_cash_flow_after_car < 0) return "bad";
    if (strategy.strategy_key === "delay_purchase") return "warn";
    if (strategy.happiness_score >= 7 && strategy.total_interest <= Math.max(1, strategy.loan_principal) * 0.08) return "good";
    return "neutral";
  };
  const strategyDecisionLabel = (strategy: CarPlanAnalysis) => {
    if (strategy.cash_after_purchase < 0) return "现金不足";
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
    planning_sequence: base?.planning_sequence ?? vehicleIndex + 1,
    purchase_timing_mode: base?.purchase_timing_mode ?? "auto_sequence",
    after_previous_event_delay_months: base?.after_previous_event_delay_months ?? 0,
    manual_purchase_delay_months: base?.manual_purchase_delay_months ?? base?.purchase_delay_months ?? 0,
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
    vehicle_service_years: base?.vehicle_service_years ?? 15,
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
      planning_sequence: index + 1,
      purchase_timing_mode: "auto_sequence",
      after_previous_event_delay_months: 0,
      manual_purchase_delay_months: source.purchase_delay_months,
      candidate_vehicles: [source]
    };
  };

  const updateVehiclePlans = (nextVehicles: VehiclePlanData[], selectedStrategy = "target") => {
    updateCarPlanPatch({
      enabled: nextVehicles.length > 0,
      vehicle_plans: nextVehicles,
      selected_strategy_variant: nextVehicles.length ? selectedStrategy : "no_car"
    });
  };

  const addVehicle = () => {
    const nextVehicles = [...vehiclePlans, buildVehiclePlan(vehiclePlans.length)];
    updateVehiclePlans(nextVehicles, nextVehicles[nextVehicles.length - 1].selected_strategy_variant);
    setSelectedVehicleIndex(nextVehicles.length - 1);
  };

  const duplicateVehicle = (index: number) => {
    const source = vehiclePlans[index];
    if (!source) return;
    const nextVehicle: VehiclePlanData = {
      ...source,
      enabled: true,
      name: `${source.name || "用车需求"} 复制`,
      selected_strategy_variant: "target",
      planning_sequence: vehiclePlans.length + 1,
      candidate_vehicles: (source.candidate_vehicles ?? []).map((candidate, candidateIndex) => ({
        ...candidate,
        name: `${candidate.name || `车源 ${candidateIndex + 1}`} 复制`,
        selected_strategy_variant: "target",
        candidate_vehicles: []
      }))
    };
    const nextVehicles = [...vehiclePlans, nextVehicle];
    updateVehiclePlans(nextVehicles, "target");
    setSelectedVehicleIndex(nextVehicles.length - 1);
  };

  const updateVehicle = (index: number, patch: Partial<VehiclePlanData>) => {
    const nextVehicles = vehiclePlans.map((vehicle, vehicleIndex) => (
      vehicleIndex === index
        ? { ...vehicle, selected_strategy_variant: "target", ...patch }
        : vehicle
    ));
    updateVehiclePlans(nextVehicles);
  };

  const removeVehicle = (index: number) => {
    const nextVehicles = vehiclePlans.filter((_, vehicleIndex) => vehicleIndex !== index);
    updateVehiclePlans(nextVehicles);
    setSelectedVehicleIndex(Math.max(0, Math.min(index, nextVehicles.length - 1)));
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
    updateVehiclePlans(nextVehicles);
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
    updateVehiclePlans(nextVehicles);
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
    updateVehiclePlans(nextVehicles);
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
    updateVehiclePlans(nextVehicles);
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
    updateVehiclePlans(nextVehicles);
  };

  const selectStrategy = (strategy: CarPlanAnalysis) => {
    setSelectedVehicleIndex(strategy.vehicle_index);
    updateCarPlanSelection(strategy.vehicle_index, strategy.variant);
  };
  const selectedStrategyDetails = vehiclePlans
    .map((vehicle, index) => resolveActiveCarStrategy(vehicle, index))
    .filter((strategy): strategy is CarPlanAnalysis => strategy !== null);
  const primarySelectedStrategy = selectedStrategyDetails[0] ?? carStrategyComparisonRows[0] ?? null;
  const prepaymentModeLabel = (strategy: CarPlanAnalysis) => {
    if (!strategy.prepayment_allowed) return "合同不允许提前还本";
    if (!strategy.prepayment_enabled) return "不提前还本";
    if (strategy.prepayment_strategy_type === "lump_sum") return "一次性提前还本";
    if (strategy.prepayment_strategy_type === "monthly") return "分月提前还本";
    if (strategy.prepayment_strategy_type === "hybrid") return "一次性 + 分月组合";
    return "手动提前还本";
  };
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
    if (strategy.loan_principal <= 0) {
      return `当前采用${financingTypeLabel(strategy.financing_type)}口径，但实际不形成车贷；交易当月需要覆盖 ${money(strategy.down_payment)} 现金。`;
    }
    return `采用「${strategy.financing_option_name || financingTypeLabel(strategy.financing_type)}」：合同 ${strategy.total_months} 期、年利率 ${percent(strategy.later_annual_rate)}，贴息 ${strategy.interest_free_months} 期。贴息不是贷款余额免息，而是厂家或经销商补贴部分利息；后端仍按合同等额本息推演余额。`;
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
    strategy.cash_after_purchase >= 0
      ? `买后现金预计 ${money(strategy.cash_after_purchase)}，没有出现购车当月现金缺口。`
      : `买后现金预计 ${money(strategy.cash_after_purchase)}，需要降低车价、提高等待时间或改用延后购车策略。`,
    strategy.monthly_cash_flow_after_car >= 0
      ? `买后月结余预计 ${money(strategy.monthly_cash_flow_after_car)}，车贷和养车支出已纳入现金流。`
      : `买后月结余预计 ${money(strategy.monthly_cash_flow_after_car)}，不建议在不调整收入或支出的情况下采用。`,
    strategy.total_interest_subsidy > 0
      ? `经销商贴息预计覆盖 ${money(strategy.total_interest_subsidy)} 利息，但仍要确认合同是否限制提前还本或收取违约金。`
      : strategy.prepayment_allowed
        ? `当前金融方案没有明显贴息补贴，应重点比较车贷利率和理财预期收益。`
        : `当前金融方案不允许提前还本，策略只比较首付、购车时间和现金安全。`
  ];

  const carLoan = result?.car_loan;
  const activeVehiclePlan = vehiclePlans[selectedVehicleIndex] ?? null;
  const activeVehicleCandidate = activeVehiclePlan?.candidate_vehicles?.[0] ?? activeVehiclePlan;
  const heroCarStrategy = primarySelectedStrategy;

  return (
    <div className="page-stack strategy-workbench">
      <SectionHeader
        icon={<Car size={20} />}
        title="购车计划"
        action={
          <button className="ghost-button" type="button" onClick={addVehicle}>
            <Plus size={16} /> 添加用车需求
          </button>
        }
      />

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
        </div>
      </section>

      <div className="strategy-layout">
        <aside className="strategy-side-panel car-planner-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<CircleDollarSign size={18} />} title="用车需求与候选车源" compact />
          <span>{selectedCarStrategy}</span>
        </div>
        <div className="planning-goal-grid vehicle-goal-grid">
          {vehiclePlans.map((vehicle, vehicleIndex) => {
            const firstCandidate = vehicle.candidate_vehicles?.[0] ?? vehicle;
            return (
              <article className={vehicleIndex === selectedVehicleIndex ? "planning-goal-card active" : "planning-goal-card"} key={`vehicle-goal-${vehicleIndex}`}>
                <button className="planning-goal-select" type="button" onClick={() => setSelectedVehicleIndex(vehicleIndex)}>
                  <span className={vehicle.enabled ? "goal-status enabled" : "goal-status paused"}>
                    {vehicle.enabled ? "纳入规划" : "已停用"}
                  </span>
                  <strong>{vehicle.name || `用车需求 ${vehicleIndex + 1}`}</strong>
                  <small>{money(firstCandidate.total_price || vehicle.total_price)} · 顺序 {vehicle.planning_sequence}</small>
                  <em>
                    {vehicle.enabled
                      ? vehicle.purchase_timing_mode === "parallel"
                        ? "允许并行考虑"
                        : vehicle.purchase_timing_mode === "manual_month"
                          ? `不早于 ${vehicle.manual_purchase_delay_months || vehicle.purchase_delay_months || 0} 个月后`
                          : `按消费顺序自动排，前一事件后 ${vehicle.after_previous_event_delay_months || 0} 个月`
                      : "暂不纳入规划"}
                  </em>
                </button>
                <div className="planning-goal-actions">
                  <button className="ghost-button small" type="button" onClick={() => setSelectedVehicleIndex(vehicleIndex)}>
                    编辑
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => duplicateVehicle(vehicleIndex)}>
                    <Copy size={14} /> 复制
                  </button>
                  <button className="ghost-button small" type="button" onClick={() => updateVehicle(vehicleIndex, { enabled: !vehicle.enabled })}>
                    {vehicle.enabled ? "停用" : "启用"}
                  </button>
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
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="车辆参数与手动策略" compact />
            <span>修改后会自动重算购车策略、贷款结构和现金流</span>
          </div>
        <div className="member-list compact-list vehicle-plan-list">
          {vehiclePlans.filter((_, vehicleIndex) => vehicleIndex === selectedVehicleIndex).map((vehicle) => {
            const vehicleIndex = selectedVehicleIndex;
            const candidates = vehicle.candidate_vehicles ?? [];
            return (
              <section className="member-card vehicle-plan-card" key={`vehicle-plan-${vehicleIndex}`}>
                <div className="member-card-head">
                  <Field label="用车需求名称">
                    <input value={vehicle.name} onChange={(event) => updateVehicle(vehicleIndex, { name: event.target.value })} />
                  </Field>
                  <SwitchField
                    label={vehicle.enabled ? "纳入当前规划" : "暂不纳入规划"}
                    checked={vehicle.enabled}
                    onChange={(checked) => updateVehicle(vehicleIndex, { enabled: checked })}
                  />
                  <button className="ghost-button small danger-action" type="button" onClick={() => removeVehicle(vehicleIndex)} aria-label="删除用车需求">
                    <Trash2 size={14} /> 删除需求
                  </button>
                </div>
                <div className="vehicle-sequence-grid">
                  <NumberField
                    label="消费事件顺序"
                    value={vehicle.planning_sequence ?? vehicleIndex + 1}
                    min={1}
                    max={50}
                    step={1}
                    onChange={(value) => updateVehicle(vehicleIndex, { planning_sequence: value })}
                  />
                  <Field label="购车时间规则">
                    <select
                      value={vehicle.purchase_timing_mode ?? "auto_sequence"}
                      onChange={(event) => updateVehicle(vehicleIndex, { purchase_timing_mode: event.target.value as VehiclePlanData["purchase_timing_mode"] })}
                    >
                      <option value="auto_sequence">按消费顺序自动排</option>
                      <option value="parallel">可并行考虑</option>
                      <option value="manual_month">手动指定月份</option>
                    </select>
                  </Field>
                  <NumberField
                    label="前一事件后等待月数"
                    value={vehicle.after_previous_event_delay_months ?? 0}
                    min={0}
                    max={240}
                    step={1}
                    onChange={(value) => updateVehicle(vehicleIndex, { after_previous_event_delay_months: value })}
                  />
                  {vehicle.purchase_timing_mode === "manual_month" ? (
                    <NumberField
                      label="指定购车距今月数"
                      value={vehicle.manual_purchase_delay_months ?? vehicle.purchase_delay_months ?? 0}
                      min={0}
                      max={600}
                      step={1}
                      onChange={(value) => updateVehicle(vehicleIndex, { manual_purchase_delay_months: value, purchase_delay_months: value })}
                    />
                  ) : null}
                </div>
                <p className="field-hint">
                  消费事件顺序会和房源的购房顺序一起参与测算：排在当前房源之前或并行的车辆会计入购房前现金压力；排在当前房源之后的车辆会在选中购房方案成交后再进入现金流、贷款和事件时间线。
                </p>
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
                          <section className="setting-group">
                            <strong className="setting-group-title">车辆属性</strong>
                            <div className="form-grid compact-fields">
                              <NumberField label="车辆总价" value={candidate.total_price} min={0} step={10000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { total_price: value })} />
                              <NumberField label="年行驶里程" value={candidate.annual_mileage_km ?? 12000} min={0} max={100000} step={1000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_mileage_km: value })} />
                              <NumberField label="百公里电耗" value={candidate.electricity_kwh_per_100km ?? 14} min={0} max={50} step={0.5} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { electricity_kwh_per_100km: value })} />
                              <NumberField label="充电单价" value={candidate.electricity_price_per_kwh ?? 0.8} min={0} max={5} step={0.05} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { electricity_price_per_kwh: value })} />
                              <NumberField label="月停车费" value={candidate.monthly_parking_cost ?? 0} min={0} step={100} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { monthly_parking_cost: value })} />
                              <NumberField label="年保养杂费" value={candidate.annual_maintenance_cost ?? 0} min={0} step={500} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_maintenance_cost: value })} />
                              <NumberField label="保险费率" value={candidate.annual_insurance_rate ?? 0.018} min={0} max={0.2} step={0.001} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_insurance_rate: value })} />
                              <NumberField label="年保险下限" value={candidate.annual_insurance_min ?? 0} min={0} step={500} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { annual_insurance_min: value })} />
                              <NumberField label="折旧年限" value={candidate.depreciation_years ?? 8} min={1} max={20} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { depreciation_years: value })} />
                              <NumberField label="车辆使用年限" value={candidate.vehicle_service_years ?? 15} min={1} max={30} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { vehicle_service_years: value })} />
                              <NumberField label="报废/更新里程" value={candidate.vehicle_retirement_mileage_km ?? 600000} min={0} max={1000000} step={10000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { vehicle_retirement_mileage_km: value })} />
                              <NumberField label="购车幸福度" value={candidate.happiness_score ?? 6.5} min={0} max={10} step={0.5} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { happiness_score: value })} />
                            </div>
                          </section>

                          <section className="setting-group vehicle-financing-group">
                            <div className="vehicle-source-toolbar">
                              <strong className="setting-group-title">经销商金融方案</strong>
                              <button className="ghost-button small" type="button" onClick={() => addFinancingOption(vehicleIndex, candidateIndex)}>
                                <Plus size={14} /> 添加金融方案
                              </button>
                            </div>
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
                          </section>

                          <section className="setting-group">
                            <strong className="setting-group-title">策略偏好</strong>
                            <div className="form-grid compact-fields">
                              <NumberField label="目标首付比例" value={candidate.down_payment_ratio ?? 0.3} min={0} max={1} step={0.05} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { down_payment_ratio: value, down_payment: Math.round((candidate.total_price ?? 0) * value) })} />
                              <NumberField label="目标首付金额" value={candidate.down_payment ?? 0} min={0} step={1000} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { down_payment: value, down_payment_ratio: candidate.total_price > 0 ? Math.min(1, Math.max(0, value / candidate.total_price)) : 0 })} />
                              <NumberField label="最早购车月数" value={candidate.purchase_delay_months ?? 0} min={0} max={240} step={1} onChange={(value) => updateCandidate(vehicleIndex, candidateIndex, { purchase_delay_months: value })} />
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
                          </section>
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
              {carStrategyComparisonRows.map((strategy) => (
                <button
                  className={activeVehicleStrategies.has(strategy.variant) ? "car-strategy-comparison-row active" : "car-strategy-comparison-row"}
                  key={`car-decision-row-${strategy.variant}`}
                  type="button"
                  onClick={() => selectStrategy(strategy)}
                >
                  <span>
                    <strong>{displayStrategyName(strategy)}</strong>
                    <small>{strategyDecisionText(strategy)}</small>
                  </span>
                  <span>{strategy.years_to_buy === null ? "暂不可达" : `${strategy.years_to_buy} 年`}</span>
                  <span>{money(strategy.down_payment)} / {money(strategy.loan_principal)}</span>
                  <span>{money(strategy.expected_monthly_payment_after_purchase)}</span>
                  <span>{money(strategy.total_interest)}</span>
                  <span>{money(strategy.cash_after_purchase)}</span>
                  <span>{money(strategy.monthly_cash_flow_after_car)}</span>
                  <span>{strategy.happiness_score.toFixed(1)} / 10</span>
                  <span className={`decision-pill ${strategyDecisionTone(strategy)}`}>{strategyDecisionLabel(strategy)}</span>
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
                          {sourceStrategies.map((strategy) => (
                            <article className={activeVehicleStrategies.has(strategy.variant) ? "strategy-card car-strategy-card active" : "strategy-card car-strategy-card"} key={strategy.variant}>
                              <div className="strategy-card-head">
                                <strong>{displayStrategyName(strategy)}</strong>
                                <StrategyStatePill
                                  active={activeVehicleStrategies.has(strategy.variant)}
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
                                active={activeVehicleStrategies.has(strategy.variant)}
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
              <strong>{prepaymentModeLabel(primarySelectedStrategy)}</strong>
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
              <strong>{prepaymentModeLabel(primarySelectedStrategy)}</strong>
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
    </div>
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
        { kind: "number", key: "second_home_provident_min_down_payment_ratio", label: "二套公积金最低首付", fallback: 0.3, min: 0, max: 1, step: 0.01, description: "二套住房使用公积金贷款时的最低首付比例。" }
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
        { kind: "number", key: "provident_policy_bonus_cap", label: "上浮封顶", fallback: 400000, min: 0, step: 10000, description: "多项上浮同时满足时，系统只按政策封顶控制最终上浮额。" }
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
        { kind: "select", key: "provident_account_management_center", label: "默认公积金中心兜底", fallback: "beijing_municipal", description: "仅在成员未设置公积金中心口径时兜底使用。真实家庭成员请优先在“成员工资与收入阶段”里分别设置市管或国管。", options: [{ value: "beijing_municipal", label: "北京市管" }, { value: "national", label: "中央国家机关/国管" }] },
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
        { kind: "number", key: "default_broker_fee_rate", label: "默认中介费假设", fallback: 0.022, min: 0, max: 0.2, step: 0.001, description: "新建房源目标时可参考的市场交易费用假设；具体房源仍可手动覆盖。" }
      ]
    },
    {
      title: "税务与社保公积金",
      description: "工资税、社保、公积金缴存基数和年终奖计税应由政策包控制；成员页面只填个人收入阶段。",
      params: [
        { kind: "number", key: "personal_standard_deduction_annual", label: "年度基本扣除", fallback: 60000, min: 0, step: 1000, description: "综合所得个税年度基本减除费用。" },
        { kind: "text", key: "annual_bonus_separate_tax_valid_until", label: "年终奖单独计税有效至", fallback: "2027-12-31", description: "年终奖单独计税政策有效期；过期后系统会按合并计税比较。" },
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
        { kind: "number", key: "pension_personal_account_annual_return", label: "养老金账户收益", fallback: 0.025, min: 0, max: 0.08, step: 0.005, description: "个人养老金账户记账收益估算。" },
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
        { kind: "number", key: "backend_parallel_workers", label: "后端并行工作数", fallback: 4, min: 1, max: 16, step: 1, description: "策略生成可并行的工作线程数；这是性能参数，不属于政策口径。" }
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
    <div className="page-stack">
      <SectionHeader icon={<Database size={20} />} title="政策规则" />
      <section className="rule-panel">
        <PanelTitle icon={<Database size={18} />} title="规则包与来源" />
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
          {ruleGroups.map((group) => (
            <section className="rule-category-panel" key={group.title}>
              <div className="strategy-panel-head">
                <div>
                  <strong>{group.title}</strong>
                  <span>{group.description}</span>
                </div>
              </div>
              <div className="rule-grid categorized-rule-grid">
                {group.params.map(renderRuleControl)}
              </div>
            </section>
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
    </div>
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
  activeRulePack,
  calculationPending
}: {
  result: AffordabilityResult | null;
  household: HouseholdData;
  selectedScenario: RecordEnvelope<ScenarioData>;
  scenarioComparisons: ScenarioComparison[];
  setSelectedScenarioId: (id: string) => void;
  selectedPlan: PurchasePlanAnalysis | null;
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  activeRulePack: RulePackData;
  calculationPending: boolean;
}) {
  const availablePlans = result?.purchase_plan_analyses ?? [];
  const scenario = selectedScenario.data;
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
    <div className="page-stack visualization-page">
      <SectionHeader icon={<TrendingUp size={20} />} title="可视化" />
      <section className="result-panel decision-board">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Home size={18} />} title="房源决策表" compact />
          <span>先看哪套房、哪种策略更值得继续推演；点击一行后，下方故事线会切换到对应房源和策略。</span>
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
                  <span>{plan ? formatPurchaseTiming(new Date(), plan.months_to_buy, plan.years_to_buy) : "-"}</span>
                  <span>{plan ? money(plan.cash_after_purchase) : "-"}</span>
                  <span>{plan && stressShortfall > 0 ? `缺口 ${money(stressShortfall)}` : plan && minimumCash !== undefined ? money(minimumCash) : "-"}</span>
                  <span>{plan ? money(plan.post_purchase_cash_flow) : "-"}</span>
                  <span>{plan ? `${percent(plan.debt_to_income_ratio)} · 息 ${money(plan.total_interest)}` : "-"}</span>
                  <span>{plan ? `${plan.happiness_score.toFixed(1)} / 10` : "-"}</span>
                  <span className={`decision-pill ${decision.tone}`}>{decision.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">{calculationPending ? "正在计算房源对比" : "等待计算房源对比"}</div>
        )}
      </section>
      <section className="result-panel visualization-story-panel">
        {result && selectedPlan ? (
          <>
            <div className="visual-header">
              <div>
                <PanelTitle icon={<TrendingUp size={18} />} title="选中策略" />
                <h3>{selectedPlan.variant}</h3>
                <div className="visual-summary-strip">
                  <span>
                    <small>可买时间</small>
                    <strong>{formatPurchaseTiming(new Date(), selectedPlan.months_to_buy, selectedPlan.years_to_buy)}</strong>
                  </span>
                  <span>
                    <small>交易后现金</small>
                    <strong>{money(selectedPlan.cash_after_purchase)}</strong>
                  </span>
                  <span>
                    <small>买后月结余</small>
                    <strong>{money(selectedPlan.post_purchase_cash_flow)}</strong>
                  </span>
                  <span>
                    <small>幸福指数</small>
                    <strong>{selectedPlan.happiness_score.toFixed(1)} / 10</strong>
                  </span>
                </div>
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

            <SelectedPlanVisualization
              result={result}
              household={household}
              scenario={scenario}
              plan={selectedPlan}
              rulePack={activeRulePack}
            />
          </>
        ) : (
          <PanelTitle
            icon={<Loader2 className="spin" size={18} />}
            title={calculationPending ? "正在计算生成策略" : "等待计算生成策略"}
          />
        )}
      </section>
    </div>
  );
}

function SelectedPlanVisualization({
  result,
  household,
  scenario,
  plan,
  rulePack
}: {
  result: AffordabilityResult;
  household: HouseholdData;
  scenario: ScenarioData;
  plan: PurchasePlanAnalysis;
  rulePack: RulePackData;
}) {
  const timelineBaseDate = useMemo(() => new Date(), []);
  const [selectedMonthIndex, setSelectedMonthIndex] = useState(1);
  const [viewStartMonth, setViewStartMonth] = useState(0);
  const [viewWindowMonths, setViewWindowMonths] = useState(120);
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
  const usesMonthlyProvidentRepayment = (plan.post_purchase_pf_strategy ?? "").includes("monthly_repayment_withdrawal");
  useEffect(() => {
    const syncCompactChart = () => setIsCompactChart(window.innerWidth < 640);
    syncCompactChart();
    window.addEventListener("resize", syncCompactChart);
    return () => window.removeEventListener("resize", syncCompactChart);
  }, []);
  const loanVisualizationSeries = useMemo(
    () => (result.loan_visualization ?? []).filter((item) => item.plan_variant === plan.variant),
    [result.loan_visualization, plan.variant]
  );
  const loanVisualizationByMonth = useMemo(
    () => new Map(loanVisualizationSeries.map((item) => [item.month, item])),
    [loanVisualizationSeries]
  );
  const providentVisualizationSeries = useMemo(
    () => (result.provident_visualization ?? []).filter((item) => item.plan_variant === plan.variant),
    [result.provident_visualization, plan.variant]
  );
  const providentVisualizationByMonth = useMemo(
    () => new Map(providentVisualizationSeries.map((item) => [item.month, item])),
    [providentVisualizationSeries]
  );
  const backendCashflowSeries = useMemo(
    () => (result.monthly_cashflow_visualization ?? []).filter((item) => item.plan_variant === plan.variant),
    [result.monthly_cashflow_visualization, plan.variant]
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
    scenario.renovation_cost <= 0
      ? "无装修预算"
      : plan.renovation_included_in_upfront_cash
        ? "交易时已备"
        : plan.months_to_renovation === null
          ? "暂无法估算"
          : plan.months_to_renovation === 0
            ? "买后可启动"
            : `买后 ${plan.months_to_renovation} 个月`;
  const taxMemberPointToIncomeRow = (member: NonNullable<(typeof taxMonthlySeries)[number]["member_points"]>[number]) => {
    const taxableCash = member.gross_salary + member.bonus_income + member.other_taxable_income;
    const extraCashExpense = Math.max(
      0,
      member.gross_salary +
        member.bonus_income +
        member.other_taxable_income +
        member.non_taxable_income -
        member.personal_social -
        member.personal_housing_fund -
        member.total_income_tax -
        member.net_income
    );
    const allocTax = (amount: number) => (taxableCash > 0 ? member.total_income_tax * (amount / taxableCash) : 0);
    return {
      name: member.member_name,
      stageName: member.stage_name,
      grossMonthly: member.gross_salary,
      bonusMonthly: member.bonus_income,
      otherMonthly: member.other_taxable_income,
      nonTaxableMonthly: member.non_taxable_income,
      salaryNetMonthly: Math.max(
        0,
        member.gross_salary - member.personal_social - member.personal_housing_fund - allocTax(member.gross_salary)
      ),
      bonusNetMonthly: Math.max(0, member.bonus_income - allocTax(member.bonus_income)),
      otherNetMonthly: Math.max(0, member.other_taxable_income - allocTax(member.other_taxable_income)),
      nonTaxableNetMonthly: member.non_taxable_income,
      extraCashExpense,
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
    taxMonthlyByMonth.get(absoluteMonth)?.member_points.map(taxMemberPointToIncomeRow) ??
    (household.members.length > 0
      ? []
      : [
          {
            name: "家庭",
            stageName: "当前收入",
            grossMonthly: result.household_gross_monthly_income,
            bonusMonthly: 0,
            otherMonthly: 0,
            nonTaxableMonthly: 0,
            salaryNetMonthly: result.household_net_monthly_income,
            bonusNetMonthly: 0,
            otherNetMonthly: 0,
            nonTaxableNetMonthly: 0,
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
    840,
    Math.max(
      180,
      backendCashflowSeries[backendCashflowSeries.length - 1]?.month ?? 0,
      loanVisualizationSeries[loanVisualizationSeries.length - 1]?.month ?? 0,
      providentVisualizationSeries[providentVisualizationSeries.length - 1]?.month ?? 0,
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
  const monthlySeries =
    backendCashflowSeries
      .filter((item) => item.month <= horizonMonths)
      .map((item) => {
            const loanPoint = loanVisualizationByMonth.get(item.month);
            const providentPoint = providentVisualizationByMonth.get(item.month);
            const houseContractPayment = item.house_contract_payment ?? loanPoint?.home_monthly_payment ?? 0;
            const providentHouseOffsetPayment =
              item.provident_house_offset_payment ??
              loanPoint?.provident_offset_payment ??
              (providentPoint
                ? (providentPoint.monthly_repayment_withdrawal ?? 0) + (providentPoint.loan_offset_payment ?? 0)
                : 0);
            const providentHousePaymentRelief =
              item.provident_house_payment_relief ??
              loanPoint?.provident_monthly_payment_relief ??
              Math.min(loanPoint?.provident_monthly_payment ?? 0, providentHouseOffsetPayment);
            const housePayment = item.house_payment ?? Math.max(0, houseContractPayment - providentHousePaymentRelief);
            const vehiclePayment = item.vehicle_payment ?? loanPoint?.vehicle_monthly_payment ?? 0;
            const debtPayment = item.debt_payment ?? loanPoint?.existing_monthly_payment ?? 0;
            const vehicleOperatingCost = item.vehicle_operating_cost ?? 0;
            const propertyAssetValue = item.property_asset_value ?? 0;
            const vehicleAssetValue = item.vehicle_asset_value ?? Math.max(0, item.fixed_asset_value - propertyAssetValue);
            const firstVehicleAssetValue = item.first_vehicle_asset_value ?? vehicleAssetValue;
            const secondVehicleAssetValue = item.second_vehicle_asset_value ?? 0;
            const investmentBuyFee = item.investment_buy_fee ?? item.investment_fee ?? 0;
            const investmentSellFee = item.investment_sell_fee ?? 0;
            const investmentContribution = item.investment_contribution ?? 0;
            return {
              month: item.month,
              name: formatMonthDate(timelineBaseDate, item.month),
              period: item.phase,
              现金池: Math.round(item.cash_balance),
              投资资产: Math.round(item.investment_balance),
              固定资产: Math.round(item.fixed_asset_value),
              房产估值: Math.round(propertyAssetValue),
              车辆估值: Math.round(vehicleAssetValue),
              第一辆车估值: Math.round(firstVehicleAssetValue),
              第二辆车估值: Math.round(secondVehicleAssetValue),
              流动资产: Math.round(item.liquid_asset_value ?? item.cash_balance + item.investment_balance),
              流动固定资产合计: Math.round((item.liquid_asset_value ?? item.cash_balance + item.investment_balance) + item.fixed_asset_value),
              净资产: Math.round(item.net_worth),
              公积金余额: Math.round(item.provident_balance),
              安全垫: Math.round(plan.required_liquidity_reserve),
              cashIncome: item.cash_income,
              livingExpense: item.living_expense + item.scheduled_expense,
              baseLivingExpense: item.living_expense,
              scheduledLivingExpense: item.scheduled_expense,
              scheduledExpenseRows: scheduledExpenseRowsAt(household, timelineBaseDate, item.month),
              debtPayment,
              regularDebtPayment: item.regular_debt_payment ?? Math.max(0, debtPayment - (item.phased_loan_payment ?? 0)),
              phasedLoanPayment: item.phased_loan_payment ?? Math.max(0, debtPayment - household.monthly_debt_payment),
              carCost: vehiclePayment + vehicleOperatingCost,
              firstCarLoanPayment: item.first_vehicle_payment ?? vehiclePayment,
              firstCarEnergyCost: item.first_vehicle_energy_cost ?? 0,
              firstCarInsuranceCost: item.first_vehicle_insurance_cost ?? 0,
              firstCarMaintenanceCost: item.first_vehicle_maintenance_cost ?? 0,
              firstCarParkingCost: item.first_vehicle_parking_cost ?? 0,
              secondCarLoanPayment: item.second_vehicle_payment ?? 0,
              secondCarEnergyCost: item.second_vehicle_energy_cost ?? 0,
              secondCarInsuranceCost: item.second_vehicle_insurance_cost ?? 0,
              secondCarMaintenanceCost: item.second_vehicle_maintenance_cost ?? 0,
              secondCarParkingCost: item.second_vehicle_parking_cost ?? 0,
              noCarCommuteCost: item.no_car_commute_cost ?? 0,
              housePayment,
              houseContractPayment,
              providentHouseOffsetPayment,
              providentHousePaymentRelief,
              providentHousePayment: Math.max(
                0,
                (loanPoint?.provident_monthly_payment ?? 0) - providentHousePaymentRelief
              ),
              providentHouseContractPayment: loanPoint?.provident_monthly_payment ?? 0,
              commercialHousePayment: loanPoint?.commercial_monthly_payment ?? 0,
              commercialExtraPrincipalPayment: loanPoint?.commercial_extra_principal_payment ?? 0,
              vehicleExtraPrincipalPayment: loanPoint?.vehicle_extra_principal_payment ?? 0,
              monthlyInvestment: investmentContribution,
              monthlyInvestmentBase: item.investment_contribution_base ?? investmentContribution,
              monthlyInvestmentCashSweep: item.investment_contribution_cash_sweep ?? 0,
              monthlyInvestmentBuyFee: investmentBuyFee,
              monthlyInvestmentNet: Math.max(0, investmentContribution - investmentBuyFee),
              investmentReturn: item.investment_return,
              investmentSellFee,
              investmentSellProceeds: item.investment_sell_proceeds ?? 0,
              purchaseCashOut: item.transaction_cash_out,
              purchaseCashIn: item.transaction_cash_in,
              houseTransactionCashOut: Math.max(0, item.transaction_cash_out - (item.vehicle_down_payment ?? 0)),
              carDownPaymentCashOut: item.first_vehicle_down_payment ?? item.vehicle_down_payment ?? 0,
              secondCarDownPaymentCashOut: item.second_vehicle_down_payment ?? 0,
              monthlyCashDelta: item.monthly_cash_delta,
              providentInterest: providentPoint?.interest ?? 0,
              providentDeposit: item.provident_deposit,
              providentRentWithdrawal: providentPoint?.rent_withdrawal ?? 0,
              providentUpfrontWithdrawal: providentPoint?.upfront_withdrawal ?? 0,
              providentPostTransactionWithdrawal: providentPoint?.post_transaction_withdrawal ?? 0,
              providentAgreedWithdrawal: providentPoint?.agreed_withdrawal ?? 0,
              providentRetirementWithdrawal: providentPoint?.retirement_withdrawal ?? 0,
              providentLoanOffsetPayment: providentHouseOffsetPayment,
              providentMonthlyRepaymentWithdrawal: providentPoint?.monthly_repayment_withdrawal ?? 0,
              providentPrincipalOffsetPayment: providentPoint?.loan_offset_payment ?? 0,
              providentMonthlyWithdrawal: item.provident_withdrawal,
              backendLedgerEntries: item.ledger_entries
            };
          });
  const hasBackendMonthlySeries = monthlySeries.length > 0;
  const timelineEndMonth = Math.max(
    0,
    monthlySeries[monthlySeries.length - 1]?.month ?? monthlySeries.length - 1,
    loanVisualizationSeries[loanVisualizationSeries.length - 1]?.month ?? 0,
    providentVisualizationSeries[providentVisualizationSeries.length - 1]?.month ?? 0,
    taxMonthlySeries[taxMonthlySeries.length - 1]?.month ?? 0
  );
  const clampTimelineMonth = (month: number) => Math.max(0, Math.min(timelineEndMonth, Math.round(month)));
  const safeSelectedMonthIndex = clampTimelineMonth(selectedMonthIndex);
  const selectedMonth =
    monthlySeries.find((item) => item.month === safeSelectedMonthIndex) ??
    monthlySeries[Math.min(safeSelectedMonthIndex, monthlySeries.length - 1)] ??
    {
      month: 0,
      name: formatMonthDate(timelineBaseDate, 0),
      period: "等待后端计算",
      现金池: 0,
      投资资产: 0,
      固定资产: 0,
      房产估值: 0,
      车辆估值: 0,
      第一辆车估值: 0,
      第二辆车估值: 0,
      流动资产: 0,
      流动固定资产合计: 0,
      净资产: 0,
      公积金余额: 0,
      安全垫: Math.round(plan.required_liquidity_reserve),
      cashIncome: 0,
      livingExpense: 0,
      baseLivingExpense: 0,
      scheduledLivingExpense: 0,
      scheduledExpenseRows: [],
      debtPayment: 0,
      regularDebtPayment: 0,
      phasedLoanPayment: 0,
      carCost: 0,
      firstCarLoanPayment: 0,
      firstCarEnergyCost: 0,
      firstCarInsuranceCost: 0,
      firstCarMaintenanceCost: 0,
      firstCarParkingCost: 0,
      secondCarLoanPayment: 0,
      secondCarEnergyCost: 0,
      secondCarInsuranceCost: 0,
      secondCarMaintenanceCost: 0,
      secondCarParkingCost: 0,
      noCarCommuteCost: 0,
      housePayment: 0,
      houseContractPayment: 0,
      providentHouseOffsetPayment: 0,
      providentHousePayment: 0,
      providentHouseContractPayment: 0,
      commercialHousePayment: 0,
      monthlyInvestment: 0,
      monthlyInvestmentBase: 0,
      monthlyInvestmentCashSweep: 0,
      monthlyInvestmentBuyFee: 0,
      monthlyInvestmentNet: 0,
      investmentReturn: 0,
      investmentSellFee: 0,
      investmentSellProceeds: 0,
      purchaseCashOut: 0,
      purchaseCashIn: 0,
      houseTransactionCashOut: 0,
      carDownPaymentCashOut: 0,
      secondCarDownPaymentCashOut: 0,
      monthlyCashDelta: 0,
      providentInterest: 0,
      providentDeposit: 0,
      providentRentWithdrawal: 0,
      providentUpfrontWithdrawal: 0,
      providentPostTransactionWithdrawal: 0,
      providentAgreedWithdrawal: 0,
      providentRetirementWithdrawal: 0,
      providentLoanOffsetPayment: 0,
      providentMonthlyWithdrawal: 0,
      backendLedgerEntries: []
    };
  const plannedHomeLoanAmount = Math.max(0, plan.commercial_loan_amount + plan.provident_loan_amount);
  const plannedVehicleLoanAmount = Math.max(0, result.car_loan.loan_principal ?? 0);
  const selectedLoanPoint = loanVisualizationByMonth.get(safeSelectedMonthIndex);
  const selectedProvidentPoint = providentVisualizationByMonth.get(safeSelectedMonthIndex);
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
      setSelectedMonthIndex(nextMonth);
      setViewStartMonth(nextViewStart);
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
        setSelectedMonthIndex(nextSelectedMonth);
        setViewStartMonth(preview.viewStartMonth);
        setViewWindowMonths(clampViewWindow(preview.viewWindowMonths));
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
  }, [applyTimelineDrag, clampViewWindow, timelineEndMonth]);

  const setMonthFromInput = (value: string) => {
    const parsed = parseMonthValue(value);
    if (!parsed) return;
    const base = { year: timelineBaseDate.getFullYear(), month: timelineBaseDate.getMonth() + 1 };
    selectVisualMonth(compareMonth(parsed, base));
  };
  useEffect(() => {
    const nextSelectedMonth = clampTimelineMonth(selectedMonthIndex);
    if (nextSelectedMonth !== selectedMonthIndex) {
      setSelectedMonthIndex(nextSelectedMonth);
    }
  }, [selectedMonthIndex, timelineEndMonth]);
  useEffect(() => {
    setViewStartMonth((current) => Math.max(0, Math.min(current, maxViewStartMonth)));
  }, [maxViewStartMonth]);
  useEffect(() => {
    setViewStartMonth((current) => {
      const clampedCurrent = Math.max(0, Math.min(current, maxViewStartMonth));
      if (safeSelectedMonthIndex < clampedCurrent) {
        return Math.max(0, Math.min(safeSelectedMonthIndex, maxViewStartMonth));
      }
      if (safeSelectedMonthIndex > clampedCurrent + viewWindowMonths - 1) {
        return Math.max(0, Math.min(safeSelectedMonthIndex - viewWindowMonths + 1, maxViewStartMonth));
      }
      return clampedCurrent;
    });
  }, [maxViewStartMonth, safeSelectedMonthIndex, viewWindowMonths]);
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
    (item) => item.plan_variant === plan.variant && item.year === selectedTaxYear
  );
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
  const annualCashInflowData = selectedAnnualFinancialSummary
    ? [
        { name: "工资及其他现金收入", value: selectedAnnualFinancialSummary.cash_income },
        { name: "公积金现金提取", value: selectedAnnualFinancialSummary.provident_withdrawal },
        { name: "投资卖出到账", value: selectedAnnualFinancialSummary.investment_sell_proceeds },
        { name: "交易现金流入", value: selectedAnnualFinancialSummary.transaction_cash_in }
      ].filter((item) => item.value > 0)
    : [];
  const annualCashOutflowData = selectedAnnualFinancialSummary
    ? [
        { name: "基础生活支出", value: selectedAnnualFinancialSummary.living_expense },
        { name: "定时支出", value: selectedAnnualFinancialSummary.scheduled_expense },
        { name: "已有贷款还款", value: selectedAnnualFinancialSummary.debt_payment },
        { name: "房贷现金还款", value: selectedAnnualFinancialSummary.house_payment },
        { name: "车贷现金还款", value: selectedAnnualFinancialSummary.vehicle_payment },
        { name: "养车现金支出", value: selectedAnnualFinancialSummary.vehicle_operating_cost },
        { name: "理财买入", value: selectedAnnualFinancialSummary.investment_contribution },
        { name: "理财手续费", value: selectedAnnualFinancialSummary.investment_fee },
        { name: "交易现金流出", value: selectedAnnualFinancialSummary.transaction_cash_out }
      ].filter((item) => item.value > 0)
    : [];
  const annualAssetCompositionData = selectedAnnualFinancialSummary
    ? [
        { name: "现金账户", value: selectedAnnualFinancialSummary.cash_balance_end },
        { name: "投资账户", value: selectedAnnualFinancialSummary.investment_balance_end }
      ].filter((item) => item.value > 0)
    : [];
  const annualFixedAssetCompositionData = selectedAnnualFinancialSummary
    ? [
        { name: "房产估值", value: selectedAnnualFinancialSummary.property_asset_value_end },
        { name: "车辆估值", value: selectedAnnualFinancialSummary.vehicle_asset_value_end }
      ].filter((item) => item.value > 0)
    : [];
  const annualLoanPaymentData = selectedAnnualFinancialSummary
    ? [
        { name: "商贷合同还款", value: selectedAnnualFinancialSummary.commercial_payment },
        {
          name: "公积金贷银行卡还款",
          value: Math.max(
            0,
            selectedAnnualFinancialSummary.provident_payment -
              selectedAnnualFinancialSummary.provident_monthly_withdrawal_payment
          )
        },
        { name: "公积金按月抵月供", value: selectedAnnualFinancialSummary.provident_monthly_withdrawal_payment },
        { name: "公积金半年度冲本金", value: selectedAnnualFinancialSummary.provident_principal_offset_payment },
        { name: "车贷现金还款", value: selectedAnnualFinancialSummary.vehicle_loan_payment },
        { name: "已有贷款还款", value: selectedAnnualFinancialSummary.existing_loan_payment },
        { name: "商贷额外还本", value: selectedAnnualFinancialSummary.commercial_extra_principal_payment },
        { name: "车贷额外还本", value: selectedAnnualFinancialSummary.vehicle_extra_principal_payment }
      ].filter((item) => item.value > 0)
    : [];
  const annualLoanBalanceData = selectedAnnualFinancialSummary
    ? [
        { name: "商贷余额", value: selectedAnnualFinancialSummary.commercial_loan_balance_end },
        { name: "公积金贷余额", value: selectedAnnualFinancialSummary.provident_loan_balance_end },
        { name: "车贷余额", value: selectedAnnualFinancialSummary.vehicle_loan_balance_end },
        { name: "已有贷款余额", value: selectedAnnualFinancialSummary.existing_loan_balance_end }
      ].filter((item) => item.value > 0)
    : [];
  const annualProvidentFlowData = selectedAnnualFinancialSummary
    ? [
        { name: "公积金缴存", value: selectedAnnualFinancialSummary.provident_deposit },
        { name: "现金提取到账", value: selectedAnnualFinancialSummary.provident_withdrawal },
        { name: "按月抵月供", value: selectedAnnualFinancialSummary.provident_monthly_withdrawal_payment },
        { name: "半年度冲本金", value: selectedAnnualFinancialSummary.provident_principal_offset_payment }
      ].filter((item) => item.value > 0)
    : [];
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
  const advisorTone = cashStressOk && plan.liquidity_ok && plan.post_purchase_cash_flow >= 0
    ? "good"
    : !cashStressOk || plan.post_purchase_cash_flow < 0
      ? "bad"
      : "warn";
  const advisorTitle =
    advisorTone === "good"
      ? "这套方案可以进入细化比较"
      : advisorTone === "bad"
        ? "这套方案需要先修现金安全"
        : "这套方案可执行但要留意压力点";
  const advisorSummary =
    plan.months_to_buy === null
      ? `按当前收入、资产、理财和贷款策略，30 年内仍不能覆盖 ${scenario.name} 的交易现金要求。优先动作是降低房源总价、延后装修或提高可动用现金。`
      : advisorTone === "good"
        ? `${scenario.name} 采用「${plan.variant}」时，预计 ${formatMonthDate(timelineBaseDate, plan.months_to_buy)} 可以买入；交易后现金和买后月结余都留在安全区，适合继续比较居住体验、通勤和房源本身。`
        : advisorTone === "bad"
          ? `${scenario.name} 采用「${plan.variant}」时，时间上可能接近目标，但现金账户在压力情景下不够稳。先不要只看可买时间，应优先调整首付、商贷量、买车节奏或理财变现。`
          : `${scenario.name} 采用「${plan.variant}」时能形成方案，但交易现金、月结余或债务收入比里至少有一项偏紧，适合作为备选而不是默认执行。`;
  const advisorActions = [
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
  const advisorEvidenceItems = [
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
  const transactionTaxAndFees = Math.max(0, plan.upfront_cash_required - plan.planned_down_payment - plan.renovation_cost);
  const transactionUseBreakdown = [
    { name: "首付", value: plan.planned_down_payment, color: visualColors.cash },
    { name: "交易税费与杂费", value: transactionTaxAndFees, color: visualColors.expense },
    { name: "交易月装修现金", value: plan.renovation_included_in_upfront_cash ? plan.renovation_cost : 0, color: visualColors.property }
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
        ? `其中车辆首付 ${money(vehicleDownPaymentBeforeHome)}，其余为车贷、能源、保险、保养和停车。`
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
      body: `买房当天先看现金用途：首付 ${money(plan.planned_down_payment)}、税费杂费约 ${money(transactionTaxAndFees)}${plan.renovation_included_in_upfront_cash ? `、交易月装修 ${money(plan.renovation_cost)}` : "；装修按买后慢慢攒，不计入当天现金"}。再看资金来源：本人公积金首付抵扣 ${money(plan.provident_upfront_extractable)}${familySupportPhrase(plan)}，剩余由家庭现金和投资变现承担。`
    },
    {
      title: "贷款扣款要按月份看",
      body: usesMonthlyProvidentRepayment
        ? `房贷、车贷和已有贷款都会进入“贷款余额与月供”。当前公积金策略为「${providentStrategyLabel(plan)}」，后端按月从公积金账户余额优先抵扣公积金贷月供，不足部分才进入银行卡现金还款；具体每个月的扣款结构已经移到贷款图下方的月度饼图。`
        : `房贷、车贷和已有贷款都会进入“贷款余额与月供”。当前公积金策略为「${providentStrategyLabel(plan)}」，半年度冲本金只在约定月份从公积金账户集中冲抵，非冲抵月仍按合同从银行卡扣公积金贷月供；具体每个月的扣款结构已经移到贷款图下方的月度饼图。`
    },
    {
      title: "还款方式怎样影响还清速度",
      body: plan.provident_repayment_advice || "本方案没有可比较的公积金贷款还款方式。"
    },
    {
      title: "理财对买房时间的影响",
      body: `截至买房月，后端推演定投本金约 ${money(displayedInvestmentContribution)}、投资收益约 ${money(displayedInvestmentReturn)}。当前买房动用投资策略为“${purchaseInvestmentModeLabel}”：交易前投资账户约 ${money(purchaseInvestmentBefore)}，交易月卖出本金约 ${money(purchaseInvestmentSellGross)}、到账约 ${money(purchaseInvestmentSellProceeds)}，交易后保留投资约 ${money(purchaseInvestmentAfter)}。`
    },
    {
      title: "幸福指数为什么不是只看钱",
      body: `幸福指数同时看居住、通勤、教育、现金安全、月结余、负债压力、商贷利息和等待时间；所以更快买入不一定更高分，现金更稳也不一定代表居住体验最好。`
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
  const cashFlowData = [
    ...(selectedMonth.cashIncome > 0
      ? selectedMemberIncomeRows.flatMap((member) => [
          { name: `${member.name}工资净入账`, amount: Math.round(member.salaryNetMonthly), kind: "income" },
          ...(member.bonusMonthly > 0
            ? [{ name: `${member.name}奖金净入账`, amount: Math.round(member.bonusNetMonthly), kind: "income" }]
            : []),
          ...(member.otherMonthly > 0
            ? [{ name: `${member.name}其他净入账`, amount: Math.round(member.otherNetMonthly), kind: "income" }]
            : []),
          ...(member.nonTaxableMonthly > 0
            ? [{ name: `${member.name}非税收入`, amount: Math.round(member.nonTaxableNetMonthly), kind: "income" }]
            : [])
        ])
      : []),
    ...(selectedMonth.cashIncome > 0
      ? selectedMemberIncomeRows.flatMap((member) =>
          member.extraCashExpense > 0
            ? [{ name: `${member.name}收入阶段额外现金支出`, amount: -Math.round(member.extraCashExpense), kind: "expense" }]
            : []
        )
      : []),
    { name: "定投买入净额", amount: -Math.round(selectedMonth.monthlyInvestmentNet), kind: "asset" },
    { name: "理财买入手续费", amount: -Math.round(selectedMonth.monthlyInvestmentBuyFee), kind: "expense" },
    { name: "复利收益留存", amount: Math.round(selectedMonth.investmentReturn), kind: "asset" },
    { name: "投资卖出到账", amount: Math.round(selectedMonth.investmentSellProceeds), kind: "income" },
    { name: "投资卖出手续费", amount: -Math.round(selectedMonth.investmentSellFee), kind: "expense" },
    { name: "公积金现金到账", amount: Math.round(selectedMonth.providentRentWithdrawal + selectedMonth.providentPostTransactionWithdrawal + (selectedMonth.providentAgreedWithdrawal ?? 0) + (selectedMonth.providentRetirementWithdrawal ?? 0)), kind: "income" },
    { name: "公积金账户抵扣/冲本金", amount: Math.round(selectedMonth.providentLoanOffsetPayment ?? 0), kind: "asset" },
    { name: "基础生活支出", amount: -Math.round(selectedMonth.baseLivingExpense), kind: "expense" },
    ...selectedMonth.scheduledExpenseRows.map((item) => ({
      name: item.name,
      amount: -Math.round(item.amount),
      kind: "expense"
    })),
    { name: "债务还款", amount: -Math.round(selectedMonth.debtPayment), kind: "expense" },
    { name: "通勤/用车成本", amount: -Math.round(selectedMonth.carCost), kind: "expense" },
    { name: "房贷现金还款", amount: -Math.round(selectedMonth.housePayment), kind: "expense" },
    { name: "公积金账户代扣房贷", amount: Math.round(selectedMonth.providentHouseOffsetPayment ?? 0), kind: "asset" },
    { name: "交易现金", amount: Math.round(selectedMonth.purchaseCashIn - selectedMonth.purchaseCashOut), kind: "expense" },
    { name: "当月现金净流入", amount: Math.round(selectedMonth.monthlyCashDelta), kind: "result" }
  ].filter((item) => item.amount !== 0 || item.kind === "result");
  const cashFlowChartHeight = Math.max(360, cashFlowData.length * 28);
  const cashFlowColor = (kind: string) => {
    if (kind === "income") return visualColors.cash;
    if (kind === "asset") return visualColors.investment;
    if (kind === "deduction") return visualColors.deduction;
    if (kind === "result") return selectedMonth.monthlyCashDelta >= 0 ? visualColors.safe : visualColors.danger;
    return visualColors.expense;
  };
  const selectedMonthDrivers = cashFlowData
    .filter((item) => item.kind !== "result" && Math.abs(item.amount) > 0)
    .sort((left, right) => Math.abs(right.amount) - Math.abs(left.amount))
    .slice(0, 5);
  const monthAdvisorText =
    selectedMonth.monthlyCashDelta >= 0
      ? `${selectedMonth.name} 现金净流入 ${money(selectedMonth.monthlyCashDelta)}，这个月现金账户在变厚。主要正向项来自工资入账、公积金现金到账、公积金账户抵扣月供、投资卖出或收益留存；主要压力项见下方归因。`
      : `${selectedMonth.name} 现金净流出 ${money(Math.abs(selectedMonth.monthlyCashDelta))}，这个月需要确认是否是交易、定投、车贷、房贷或生活支出的阶段性压力。`;
  const incomeMemberLegendData = selectedMemberIncomeRows
    .flatMap((member) => [
      { name: `${member.name}工资净入账`, value: Math.max(0, member.salaryNetMonthly) },
      { name: `${member.name}奖金净入账`, value: Math.max(0, member.bonusNetMonthly) },
      { name: `${member.name}其他净入账`, value: Math.max(0, member.otherNetMonthly) },
      { name: `${member.name}非税收入`, value: Math.max(0, member.nonTaxableNetMonthly) },
    ])
    .filter((item) => item.value > 0);
  const incomeHouseholdFlowData = [
    { name: "复利收益", value: selectedMonth.investmentReturn },
    { name: "租房公积金提取", value: selectedMonth.providentRentWithdrawal },
    { name: "交易后公积金回流", value: selectedMonth.providentPostTransactionWithdrawal },
    { name: "退休公积金销户到账", value: selectedMonth.providentRetirementWithdrawal ?? 0 },
    { name: "投资卖出到账", value: selectedMonth.investmentSellProceeds },
    { name: "交易现金流入", value: Math.max(0, selectedMonth.purchaseCashIn - selectedMonth.investmentSellProceeds) }
  ];
  const incomeLegendData = [
    ...incomeMemberLegendData,
    ...incomeHouseholdFlowData.filter((item) => item.value > 0)
  ];
  const incomePieData = [
    ...incomeMemberLegendData,
    ...incomeHouseholdFlowData
  ].filter((item) => item.value > 0);
  const existingLoanExpensePieData = selectedExistingLoanDetails.length > 0
    ? selectedExistingLoanDetails.map((item, index) => ({
        name: item.name,
        value: item.monthly_payment,
        color: stablePieColor(item.name)
      }))
    : [{ name: "已有贷款月供", value: selectedMonth.phasedLoanPayment, color: visualColors.expense }];
  const expensePieData = [
    ...selectedMemberIncomeRows.flatMap((member) => [
      { name: `${member.name}收入阶段额外现金支出`, value: member.extraCashExpense }
    ]),
    { name: "基础生活支出", value: selectedMonth.baseLivingExpense },
    ...selectedMonth.scheduledExpenseRows.map((item) => ({ name: item.name, value: item.amount })),
    { name: "其他固定还款", value: selectedOtherFixedDebtPayment || selectedMonth.regularDebtPayment },
    ...existingLoanExpensePieData,
    { name: "无车通勤成本", value: selectedMonth.noCarCommuteCost },
    { name: "车辆车贷", value: selectedMonth.firstCarLoanPayment },
    { name: "车辆电费", value: selectedMonth.firstCarEnergyCost },
    { name: "车辆保险", value: selectedMonth.firstCarInsuranceCost },
    { name: "车辆保养", value: selectedMonth.firstCarMaintenanceCost },
    { name: "车辆停车", value: selectedMonth.firstCarParkingCost },
    { name: "第二辆车车贷", value: selectedMonth.secondCarLoanPayment },
    { name: "第二辆车电费", value: selectedMonth.secondCarEnergyCost },
    { name: "第二辆车保险", value: selectedMonth.secondCarInsuranceCost },
    { name: "第二辆车保养", value: selectedMonth.secondCarMaintenanceCost },
    { name: "第二辆车停车", value: selectedMonth.secondCarParkingCost },
    { name: "公积金贷银行卡月扣", value: selectedMonth.providentHousePayment },
    { name: "公积金账户按月抵月供", value: selectedMonth.providentMonthlyRepaymentWithdrawal ?? 0 },
    { name: "公积金账户半年度冲本金", value: selectedMonth.providentPrincipalOffsetPayment ?? 0 },
    { name: "商贷月供", value: selectedMonth.commercialHousePayment },
    { name: "商贷额外还本", value: selectedMonth.commercialExtraPrincipalPayment ?? 0 },
    { name: "理财买入净额", value: selectedMonth.monthlyInvestmentNet },
    { name: "理财手续费", value: selectedMonth.monthlyInvestmentBuyFee + selectedMonth.investmentSellFee },
    { name: "购房交易现金", value: selectedMonth.houseTransactionCashOut },
    { name: "车辆首付", value: selectedMonth.carDownPaymentCashOut },
    { name: "第二辆车首付", value: selectedMonth.secondCarDownPaymentCashOut }
  ].filter((item) => item.value > 0);
  const selectedLoanPaymentPieData = [
    { name: "商贷合同还款", value: selectedLoanPoint?.commercial_monthly_payment ?? 0, color: visualColors.property },
    { name: "商贷额外还本", value: selectedLoanPoint?.commercial_extra_principal_payment ?? 0, color: visualColors.baseline },
    {
      name: "公积金贷银行卡月扣",
      value: Math.max(
        0,
        (selectedLoanPoint?.provident_monthly_payment ?? 0) -
          (selectedLoanPoint?.provident_monthly_payment_relief ?? 0)
      ),
      color: visualColors.warning
    },
    {
      name: "公积金账户按月抵月供",
      value: selectedLoanPoint?.provident_monthly_withdrawal_payment ?? 0,
      color: visualColors.provident
    },
    {
      name: "公积金账户半年度冲本金",
      value: selectedLoanPoint?.provident_principal_offset_payment ?? 0,
      color: visualColors.provident
    },
    {
      name: "车贷现金还款",
      value: Math.max(0, (selectedLoanPoint?.vehicle_monthly_payment ?? 0) - (selectedLoanPoint?.vehicle_extra_principal_payment ?? 0)),
      color: visualColors.vehicle
    },
    { name: "车贷额外还本", value: selectedLoanPoint?.vehicle_extra_principal_payment ?? 0, color: "var(--gold)" },
    { name: "其他固定还款", value: selectedOtherFixedDebtPayment, color: visualColors.expense },
    ...selectedExistingLoanDetails.map((item, index) => ({
      name: item.name,
      value: item.monthly_payment,
      color: stablePieColor(item.name)
    }))
  ].filter((item) => item.value > 0);
  const sumPieValues = (items: Array<{ value: number }>) =>
    items.reduce((sum, item) => sum + Math.max(0, Number(item.value) || 0), 0);
  const annualTaxMemberPieData = taxSummaryRows
    .map((item) => ({ name: `${item.member_name}年度个税`, value: item.total_tax }))
    .filter((item) => item.value > 0);
  const annualTaxTypePieData = [
    { name: "工资薪金个税", value: taxSummaryRows.reduce((sum, item) => sum + item.salary_tax, 0) },
    { name: "年终奖个税", value: taxSummaryRows.reduce((sum, item) => sum + item.bonus_tax, 0) }
  ].filter((item) => item.value > 0);
  const currentMonthTaxPieData = selectedMemberIncomeRows
    .map((member) => ({ name: `${member.name}当月个税`, value: member.incomeTax }))
    .filter((item) => item.value > 0);
  const currentMonthDeductionPieData = selectedMemberIncomeRows
    .flatMap((member) => [
      { name: `${member.name}个人社保`, value: member.personalSocial },
      { name: `${member.name}个人公积金`, value: member.personalHousingFund },
      { name: `${member.name}专项附加扣除`, value: member.elderlyCareDeduction ?? 0 }
    ])
    .filter((item) => item.value > 0);
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
  const providentInflowPieData = [
    ...selectedProvidentMemberAccounts.flatMap((account) => [
      { name: `${account.member_name}个人缴存`, value: account.personal_deposit },
      { name: `${account.member_name}单位缴存`, value: account.employer_deposit },
      { name: `${account.member_name}利息`, value: account.interest }
    ])
  ].filter((item) => item.value > 0);
  const providentOutflowPieData = [
    ...providentOutflowMemberAccounts.flatMap((account) => [
      { name: `${account.member_name}租房提取`, value: account.rent_withdrawal },
      { name: `${account.member_name}交易前提取`, value: account.upfront_withdrawal },
      { name: `${account.member_name}交易后提取`, value: account.post_transaction_withdrawal },
      { name: `${account.member_name}购后约定提取`, value: account.agreed_withdrawal },
      { name: `${account.member_name}按月抵月供`, value: account.monthly_repayment_withdrawal ?? 0 },
      { name: `${account.member_name}半年度冲本金`, value: account.loan_offset_payment },
      { name: `${account.member_name}退休销户提取`, value: account.retirement_withdrawal ?? 0 }
    ])
  ].filter((item) => item.value > 0);
  const incomePieTotal = sumPieValues(incomePieData);
  const expensePieTotal = sumPieValues(expensePieData);
  const selectedLoanPaymentPieTotal = sumPieValues(selectedLoanPaymentPieData);
  const providentInflowPieTotal = sumPieValues(providentInflowPieData);
  const providentOutflowPieTotal = sumPieValues(providentOutflowPieData);
  const cashFlowGroups: Array<{ title: string; rows: Array<[string, number]> }> = [
    {
      title: "收入与入账",
      rows: [
        ...(selectedMonth.cashIncome > 0
          ? selectedMemberIncomeRows.flatMap((member): Array<[string, number]> => [
              [`${member.name}工资净入账`, member.salaryNetMonthly],
              ...(member.bonusMonthly > 0 ? [[`${member.name}奖金净入账`, member.bonusNetMonthly] as [string, number]] : []),
              ...(member.otherMonthly > 0 ? [[`${member.name}其他净入账`, member.otherNetMonthly] as [string, number]] : []),
              ...(member.nonTaxableMonthly > 0 ? [[`${member.name}非税收入`, member.nonTaxableNetMonthly] as [string, number]] : [])
            ])
          : []),
        ["复利收益留存", selectedMonth.investmentReturn],
        ["投资卖出到账", selectedMonth.investmentSellProceeds],
        ["当月公积金现金到账", selectedMonth.providentRentWithdrawal + selectedMonth.providentPostTransactionWithdrawal + (selectedMonth.providentAgreedWithdrawal ?? 0) + (selectedMonth.providentRetirementWithdrawal ?? 0)],
        ["公积金账户抵扣/冲本金（非收入）", selectedMonth.providentLoanOffsetPayment ?? 0]
      ]
    },
    {
      title: "购房后月支出",
      rows: [
        ...selectedMemberIncomeRows.flatMap((member): Array<[string, number]> =>
          member.extraCashExpense > 0
            ? [[`${member.name}收入阶段额外现金支出`, -member.extraCashExpense]]
            : []
        ),
        ["基础生活支出", -selectedMonth.baseLivingExpense],
        ...selectedMonth.scheduledExpenseRows.map((item): [string, number] => [item.name, -item.amount]),
        ["固定还款与已有贷款", -selectedMonth.debtPayment],
        ["通勤/用车", -selectedMonth.carCost],
        ["房贷现金还款", -selectedMonth.housePayment],
        ["公积金账户代扣房贷", selectedMonth.providentHouseOffsetPayment ?? 0],
        ["基础定投现金支出", -selectedMonth.monthlyInvestmentBase],
        ["安全垫达标后追加定投", -selectedMonth.monthlyInvestmentCashSweep],
        ["定投买入净额", -selectedMonth.monthlyInvestmentNet],
        ["理财买入手续费", -selectedMonth.monthlyInvestmentBuyFee],
        ["投资卖出手续费", -selectedMonth.investmentSellFee],
        ["交易现金净额", selectedMonth.purchaseCashIn - selectedMonth.purchaseCashOut]
      ]
    },
    {
      title: "月度结果",
      rows: [
        ["当月现金净流入", selectedMonth.monthlyCashDelta],
        ["月末现金账户", selectedMonth.现金池],
        ["月末投资账户", selectedMonth.投资资产],
        ["月末公积金余额", selectedMonth.公积金余额]
      ]
    }
  ];
  const selectedMonthExplanationItems = [
    {
      title: "收入为什么这样入账",
      body:
        selectedMonth.cashIncome > 0
          ? `工资按各家庭成员当前生效的收入阶段逐月入账；年终奖不均摊到 12 个月，只在发放月进入现金流，所以 ${selectedMonth.name} 会看到对应月份的跳升或回落。税后现金工资已经扣除了个人社保、个人公积金和当月累计预扣个税。`
          : `${selectedMonth.name} 没有工资现金入账，通常是收入阶段尚未开始、已进入失业/退休等自动情景，或该月是交易月只展示资产转换。`
    },
    {
      title: "年度/阶段性支出为什么不是均摊",
      body:
        selectedMonth.firstCarInsuranceCost + selectedMonth.firstCarMaintenanceCost + selectedMonth.secondCarInsuranceCost + selectedMonth.secondCarMaintenanceCost > 0
          ? `车辆保险和保养按实际发生月计入现金流，不做月度均摊；当前月出现 ${money(selectedMonth.firstCarInsuranceCost + selectedMonth.secondCarInsuranceCost)} 保险和 ${money(selectedMonth.firstCarMaintenanceCost + selectedMonth.secondCarMaintenanceCost)} 保养，并按设定年增长率随持有年份递增。`
          : `车辆保险、保养这类年度支出不会平均摊到每个月；只有到车辆购入后的年度节点才进入当月现金流，并会按设定年增长率随持有年份递增。平时只保留电费、停车、通勤等更接近月度发生的项目。`
    },
    {
      title: "贷款还款策略为什么这样",
      body:
        selectedLoanPoint && selectedLoanPoint.total_monthly_payment > 0
          ? `房贷、车贷和已有贷款都属于贷款。当前月贷款还款 ${money(selectedLoanPoint.total_monthly_payment)}，其中房贷 ${money(selectedLoanPoint.home_monthly_payment)}、车贷 ${money(selectedLoanPoint.vehicle_monthly_payment)}、${selectedExistingLoanDescription}；商贷和车贷额外还本会作为本金支出计入当月还款。公积金按月抵月供只降低银行卡还款压力，半年度冲本金才额外压降贷款本金，两者不会在同一阶段并行。`
          : `当前月还没有实际贷款还款进入现金流；如果计划中有房贷或车贷，它们会从买房/买车发生月起进入贷款余额与月供曲线。`
    },
    {
      title: "公积金账户为什么这样流动",
      body: `公积金账户由后端逐月计算：个人缴存和单位缴存进入账户，账户利息留在账户内；购房前租房提取按季度到账，买房后不再把租房提取当作后续来源。按月抵月供和半年度冲本金分开记账，半年度冲本金与约定提取互斥，属于账户支出，不属于自由现金收入。`
    },
    {
      title: "理财定投为什么这样执行",
      body:
        selectedMonth.monthlyInvestment > 0
          ? `本月定投 ${money(selectedMonth.monthlyInvestment)}，买入净额 ${money(selectedMonth.monthlyInvestmentNet)}，手续费 ${money(selectedMonth.monthlyInvestmentBuyFee)}。策略先保护现金安全垫：当月结余用于基础定投，安全垫以上的存量现金会分期追加到投资账户；若当月净流入为负，通常代表主动调仓而不是日常支出失控。`
          : `本月没有执行定投，通常是月结余不足、现金账户低于安全垫，或理财策略选择了现金保守模式。已有投资账户的收益仍留在投资账户中复利。`
    },
    {
      title: "当月净流入怎么看",
      body:
        selectedMonth.monthlyCashDelta >= 0
          ? `${selectedMonth.name} 现金净流入为 ${money(selectedMonth.monthlyCashDelta)}，说明工资、到账、冲抵或投资变现足以覆盖本月支出和定投。`
          : `${selectedMonth.name} 现金净流出为 ${money(Math.abs(selectedMonth.monthlyCashDelta))}。如果不是交易、买车首付、年度保险保养或装修等特殊时点，就应优先检查定投、用车、房贷和家庭支出是否需要调整。`
    }
  ];
  const happinessData = result.purchase_plan_analyses.map((item) => ({
    name: item.variant,
    幸福指数: Number(item.happiness_score.toFixed(1)),
    selected: item.variant === plan.variant
  }));
  const timelineItems = (result.plan_events ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month || left.title.localeCompare(right.title, "zh-Hans-CN"))
    .map((item) => ({
      month: item.month,
      label: `${formatMonthDate(timelineBaseDate, item.month)} · ${item.title}`,
      value: item.detail,
      severity: item.severity
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
                <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
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
              税务曲线跟随上方月份窗口。年终奖只在发放月入账和计税，所以奖金发放月会看到税前收入、税后现金和个税同时跳升；这比把年终奖均摊到每个月更贴近真实现金流。
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
                <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
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
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
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
                <YAxis yAxisId="balance" tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
                <YAxis yAxisId="payment" orientation="right" tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
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
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
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

        <section className="chart-block cash-flow-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title={`${selectedMonth.name} 月现金流`} compact />
          <ResponsiveContainer width="100%" height={cashFlowChartHeight}>
            <BarChart data={cashFlowData} layout="vertical" margin={{ top: 4, right: 14, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
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
          <details className="details-panel month-detail-panel">
            <summary>
              <span>查看收入、支出和账户明细</span>
              <small>{selectedMonth.name} 的逐项现金流默认收起，避免影响图表阅读</small>
            </summary>
            <div className="cash-flow-sections">
              {cashFlowGroups.map((group) => (
                <div className="cash-flow-section" key={group.title}>
                  <strong>{group.title}</strong>
                  {group.rows.map(([label, value]) => (
                    <Row key={label} label={label} value={money(Number(value))} />
                  ))}
                </div>
              ))}
            </div>
          </details>
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
        <PanelTitle icon={<TrendingUp size={18} />} title="幸福指数对比" compact />
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
        <p className="field-hint">
          幸福指数由后端按居住、通勤、教育、用车便利、现金安全、月度现金流、负债、月供、利息、等待、装修和压力韧性加权计算；流动性偏好越高，财务安全维度权重越高。
        </p>
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
      </section>

      <section className="timeline-panel">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="事件时间线" compact />
        <div className="timeline-list">
          {timelineItems.map((item, index) => (
            <div className="timeline-item" key={`${item.month}-${item.label}-${index}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
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
  runCalculation
}: {
  result: AffordabilityResult | null;
  scenario: ScenarioData;
  selectedPlan: PurchasePlanAnalysis | null;
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  runCalculation: () => void;
}) {
  const availablePlans = result?.purchase_plan_analyses ?? [];

  return (
    <div className="page-stack">
      <SectionHeader
        icon={<Download size={20} />}
        title="导出方案"
        action={
          <button className="ghost-button" onClick={runCalculation}>
            <RefreshCw size={16} /> 刷新结果
          </button>
        }
      />
      <section className="result-panel export-panel">
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
                  selectedPlan.renovation_included_in_upfront_cash
                    ? "交易时已备"
                    : selectedPlan.months_to_renovation === null
                      ? "暂无法估算"
                      : selectedPlan.months_to_renovation === 0
                        ? "买后可启动"
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
            <section className="notes">
              <p>导出内容以当前选中的“{selectedPlan.variant}”为准；全局即时可行性仅作为背景参考。</p>
              {result.eligibility_notes.map((note) => (
                <p key={note}>{note}</p>
              ))}
              {result.assumptions.map((note) => (
                <p key={note}>{note}</p>
              ))}
            </section>
          </>
        ) : (
          <PanelTitle icon={<Loader2 className="spin" size={18} />} title="等待计算" />
        )}
      </section>
    </div>
  );
}

function getPlanStatus(plan: PurchasePlanAnalysis) {
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

function exportText(result: AffordabilityResult, scenario: ScenarioData, plan: PurchasePlanAnalysis) {
  const planStatus = getPlanStatus(plan);
  const monthlyRows = selectedPlanCashflowRows(result, plan);
  const loanRows = selectedPlanLoanRows(result, plan);
  const providentRows = selectedPlanProvidentRows(result, plan);
  const eventRows = selectedPlanEventRows(result, plan);
  const strategyRows = selectedPlanStrategyRows(result, plan);
  const purchaseMonth = plan.months_to_buy ?? null;
  const purchaseCashflow = purchaseMonth === null ? null : monthlyRows.find((item) => item.month === purchaseMonth) ?? null;
  const finalCashflow = monthlyRows[monthlyRows.length - 1] ?? null;
  const renovationText =
    scenario.renovation_cost <= 0
      ? "装修预算：未设置"
      : plan.renovation_included_in_upfront_cash
        ? `装修预算：${money(scenario.renovation_cost)}，资金方式：${renovationFundingLabels[plan.renovation_funding_mode]}，已计入交易现金需求`
        : plan.months_to_renovation === null
          ? `装修预算：${money(scenario.renovation_cost)}，资金方式：${renovationFundingLabels[plan.renovation_funding_mode]}，买后月结余暂不足以估算装修启动时间`
          : `装修预算：${money(scenario.renovation_cost)}，资金方式：${renovationFundingLabels[plan.renovation_funding_mode]}，预计买后 ${plan.months_to_renovation} 个月可启动装修`;
  const lines = [
    `当前导出方案：${plan.variant}`,
    `方案结论：${planStatus.status}`,
    planStatus.reason,
    plan.description,
    "",
    `税后月收入：${money(result.household_net_monthly_income)}`,
    `年度个税：${money(result.annual_income_tax)}`,
    `已有贷款月供：${money(result.phased_loan_monthly_payment)}`,
    "",
    "当前方案购房路径：",
    `预计买入时间：${plan.months_to_buy === null ? "30 年内暂不可达" : formatMonthDate(new Date(), plan.months_to_buy)}（约 ${plan.years_to_buy ?? "超过30"} 年）`,
    `首付：${money(plan.planned_down_payment)}，本人公积金首付抵扣：${money(plan.provident_upfront_extractable)}${familySupportPhrase(plan)}，交易现金需覆盖：${money(plan.required_cash_after_pf_extract)}`,
    `购房后预计公积金提取到账：${money(plan.provident_post_transaction_extractable)}，剩余公积金余额：${money(plan.provident_balance_after_extract)}`,
    renovationText,
    `公积金贷：${money(plan.provident_loan_amount)}，${plan.provident_loan_years} 年，${repaymentMethodLabels[plan.provident_repayment_method]}，政策上限 ${money(plan.provident_policy_cap)}，政策上浮 ${money(plan.provident_policy_bonus)}`,
    `商贷：${money(plan.commercial_loan_amount)}，${plan.commercial_loan_years} 年，${repaymentMethodLabels[plan.commercial_repayment_method]}`,
    plan.commercial_prepayment_enabled
      ? `商贷提前还本：${commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]}，第 ${plan.commercial_prepayment_start_month} 个还款月起每月额外还本 ${money(plan.commercial_prepayment_monthly_amount)}，预计节省利息 ${money(plan.commercial_interest_saved_by_prepayment)}`
      : `商贷提前还本：${commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]}，当前方案不安排额外还本`,
    `合计月供：${money(plan.total_monthly_payment)}，交易当下现金：${money(plan.cash_after_transaction)}，购房后公积金到账后现金：${money(plan.cash_after_purchase)}`,
    `买后自由现金月结余：${money(plan.post_purchase_cash_flow)}，贷后公积金策略：${providentStrategyLabel(plan)}，按策略折算后的现金压力：${money(plan.post_purchase_cash_flow_with_pf_withdrawal)}/月`,
    `公积金还款方式建议：${plan.provident_repayment_advice || "无"}`,
    `负债收入比：${percent(plan.debt_to_income_ratio)}，幸福指数：${plan.happiness_score.toFixed(1)} / 10`,
    "幸福指数明细：",
    ...plan.happiness_breakdown.map((item) => `- ${item.name}：${item.score.toFixed(1)} 分，权重 ${percent(item.weight)}，贡献 ${item.weighted_score.toFixed(2)} 分。${item.note}`),
    `公积金年限依据：${plan.provident_loan_year_limit_reasons.join("；")}`,
    "",
    "关键事件时间线：",
    ...(eventRows.length > 0
      ? eventRows.map((item) => `- ${formatMonthDate(new Date(), item.month)}｜${item.title}｜${item.detail}${item.amount === null || item.amount === undefined ? "" : `｜金额 ${money(item.amount)}`}`)
      : ["- 当前方案暂无后端事件。"]),
    "",
    "账户与贷款快照：",
    purchaseCashflow
      ? `买入月 ${formatMonthDate(new Date(), purchaseCashflow.month)}：现金账户 ${money(purchaseCashflow.cash_balance)}，投资账户 ${money(purchaseCashflow.investment_balance)}，公积金账户 ${money(purchaseCashflow.provident_balance)}，固定资产 ${money(purchaseCashflow.fixed_asset_value)}，贷款余额 ${money(purchaseCashflow.total_loan_balance)}，净资产 ${money(purchaseCashflow.net_worth)}。`
      : "买入月：当前方案 30 年内暂不可达。",
    finalCashflow
      ? `测算末月 ${formatMonthDate(new Date(), finalCashflow.month)}：现金账户 ${money(finalCashflow.cash_balance)}，投资账户 ${money(finalCashflow.investment_balance)}，公积金账户 ${money(finalCashflow.provident_balance)}，固定资产 ${money(finalCashflow.fixed_asset_value)}，贷款余额 ${money(finalCashflow.total_loan_balance)}，净资产 ${money(finalCashflow.net_worth)}。`
      : "测算末月：暂无后端账户曲线。",
    loanRows.length > 0
      ? `贷款曲线：共 ${loanRows.length} 个月，最高总贷款余额 ${money(Math.max(...loanRows.map((item) => item.total_loan_balance)))}。`
      : "贷款曲线：当前方案暂无贷款曲线。",
    providentRows.length > 0
      ? `公积金账户曲线：共 ${providentRows.length} 个月，末月家庭公积金余额 ${money(providentRows[providentRows.length - 1].balance_end)}。`
      : "公积金账户曲线：当前方案暂无公积金曲线。",
    "",
    "策略解释：",
    ...(strategyRows.length > 0
      ? strategyRows.map((item) => `- ${item.title}：${item.body}`)
      : ["- 当前方案暂无后端策略解释。"]),
    "",
    "详细表格提示：导出表格会包含每个月的现金账户、投资账户、公积金账户、固定资产、贷款余额、月现金流、成员公积金账户和后端流水明细。",
    "",
    `全局即时评估：${result.status}。${result.status_reason}`
  ];
  downloadFile(`house-plan-${plan.variant}.txt`, lines.join("\n"), "text/plain;charset=utf-8");
}

function csvCell(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function csvRow(values: Array<string | number | boolean | null | undefined>) {
  return values.map((value) => csvCell(typeof value === "boolean" ? (value ? "是" : "否") : value)).join(",");
}

function csvSection(title: string, headers: string[], rows: Array<Array<string | number | boolean | null | undefined>>) {
  return [
    csvRow([title]),
    csvRow(headers),
    ...rows.map((row) => csvRow(row)),
    ""
  ];
}

function selectedPlanCashflowRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.monthly_cashflow_visualization ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month);
}

function selectedPlanSnapshotRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.account_snapshots ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month);
}

function selectedPlanLoanRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.loan_visualization ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month);
}

function selectedPlanProvidentRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.provident_visualization ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month);
}

function selectedPlanLedgerRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.monthly_ledger ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month || left.account.localeCompare(right.account) || left.label.localeCompare(right.label));
}

function selectedPlanEventRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.plan_events ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month || left.title.localeCompare(right.title));
}

function selectedPlanStrategyRows(result: AffordabilityResult, plan: PurchasePlanAnalysis) {
  return (result.strategy_explanations ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.priority - right.priority || left.section.localeCompare(right.section));
}

function exportCsv(result: AffordabilityResult, scenario: ScenarioData, plan: PurchasePlanAnalysis) {
  const planStatus = getPlanStatus(plan);
  const baseDate = new Date();
  const cashflowRows = selectedPlanCashflowRows(result, plan);
  const snapshotRows = selectedPlanSnapshotRows(result, plan);
  const loanRows = selectedPlanLoanRows(result, plan);
  const providentRows = selectedPlanProvidentRows(result, plan);
  const ledgerRows = selectedPlanLedgerRows(result, plan);
  const eventRows = selectedPlanEventRows(result, plan);
  const strategyRows = selectedPlanStrategyRows(result, plan);
  const cashflowByMonth = new Map(cashflowRows.map((item) => [item.month, item]));
  const sections = [
    "sep=,",
    ...csvSection("导出说明", ["项目", "内容"], [
      ["导出时间", new Date().toLocaleString("zh-CN")],
      ["导出方案", plan.variant],
      ["方案结论", planStatus.status],
      ["结论解释", planStatus.reason],
      ["时间口径", "所有月份为从当前月份开始推演的真实年月；金额单位为元。"],
      ["数据来源", "后端返回的已选方案、账户曲线、贷款曲线、公积金曲线、月度流水和事件时间线。"]
    ]),
    ...csvSection("方案摘要", ["项目", "内容"], [
      ["房源/场景", scenario.name],
      ["方案描述", plan.description],
      ["预计买入时间", plan.months_to_buy === null ? "30年内暂不可达" : formatPurchaseTiming(baseDate, plan.months_to_buy, plan.years_to_buy)],
      ["最低首付", plan.minimum_down_payment],
      ["计划首付", plan.planned_down_payment],
      ["交易现金总需求", plan.upfront_cash_required],
      ["本人公积金首付抵扣", plan.provident_upfront_extractable],
      ["亲属首付支持类型", familySupportLabel(plan)],
      ["亲属首付支持金额", familySupportAmount(plan)],
      ["交易现金需家庭覆盖", plan.required_cash_after_pf_extract],
      ["交易当下现金", plan.cash_after_transaction],
      ["购房后公积金到账后现金", plan.cash_after_purchase],
      ["现金安全垫要求", plan.required_liquidity_reserve],
      ["最低现金账户", plan.minimum_cash_balance ?? ""],
      ["最低现金月份", plan.minimum_cash_balance_month === null || plan.minimum_cash_balance_month === undefined ? "" : formatMonthDate(baseDate, plan.minimum_cash_balance_month)],
      ["压力现金缺口", plan.cash_stress_shortfall ?? 0],
      ["买后自由现金月结余", plan.post_purchase_cash_flow],
      ["贷后公积金策略", providentStrategyLabel(plan)],
      ["公积金账户还贷改善/月", plan.monthly_post_purchase_pf_withdrawal],
      ["策略后现金压力/月", plan.post_purchase_cash_flow_with_pf_withdrawal],
      ["负债收入比", percent(plan.debt_to_income_ratio)],
      ["幸福指数", plan.happiness_score.toFixed(1)]
    ]),
    ...csvSection("贷款与购房资金", ["项目", "内容"], [
      ["公积金贷款金额", plan.provident_loan_amount],
      ["公积金贷款政策上限", plan.provident_policy_cap],
      ["公积金政策上浮", plan.provident_policy_bonus],
      ["公积金贷款年限", plan.provident_loan_years],
      ["公积金合同期数", plan.provident_contract_months],
      ["公积金还款方式", repaymentMethodLabels[plan.provident_repayment_method]],
      ["公积金月供", plan.provident_monthly_payment],
      ["公积金等额本息月供", plan.provident_equal_installment_payment],
      ["公积金等额本金首月", plan.provident_equal_principal_first_payment],
      ["等额本金可节省利息", plan.provident_interest_saving_if_equal_principal],
      ["公积金还款建议", plan.provident_repayment_advice],
      ["公积金年限依据", plan.provident_loan_year_limit_reasons.join("；")],
      ["商贷金额", plan.commercial_loan_amount],
      ["商贷年限", plan.commercial_loan_years],
      ["商贷还款方式", repaymentMethodLabels[plan.commercial_repayment_method]],
      ["商贷月供", plan.commercial_monthly_payment],
      ["商贷提前还本策略", commercialPrepaymentModeLabels[plan.commercial_prepayment_mode ?? "none"]],
      ["商贷提前还本是否启用", plan.commercial_prepayment_enabled],
      ["商贷提前还本起始月", plan.commercial_prepayment_start_month],
      ["商贷每月额外还本", plan.commercial_prepayment_monthly_amount],
      ["商贷提前还本节省利息", plan.commercial_interest_saved_by_prepayment],
      ["合计月供", plan.total_monthly_payment],
      ["全周期利息", plan.total_interest],
      ["购房后预计公积金提取到账", plan.provident_post_transaction_extractable],
      ["提取后公积金余额", plan.provident_balance_after_extract]
    ]),
    ...csvSection("装修与幸福指数", ["项目", "内容"], [
      ["装修预算", plan.renovation_cost],
      ["装修资金方式", renovationFundingLabels[plan.renovation_funding_mode]],
      ["装修是否计入交易现金", plan.renovation_included_in_upfront_cash],
      ["预计装修等待月数", plan.months_to_renovation ?? "暂无法估算"],
      ["预计装修等待年数", plan.years_to_renovation ?? "暂无法估算"],
      ["买后每月装修储蓄", plan.post_purchase_renovation_monthly_saving]
    ]),
    ...csvSection("幸福指数明细", ["分类", "维度", "得分", "权重", "贡献", "解释"], plan.happiness_breakdown.map((item) => [
      item.category,
      item.name,
      item.score,
      item.weight,
      item.weighted_score,
      item.note
    ])),
    ...csvSection("关键事件时间线", ["月份序号", "真实年月", "类别", "标题", "详情", "金额", "等级", "来源"], eventRows.map((item) => [
      item.month,
      formatMonthDate(baseDate, item.month),
      item.category,
      item.title,
      item.detail,
      item.amount ?? "",
      item.severity,
      item.source
    ])),
    ...csvSection("账户月度快照", [
      "月份序号",
      "真实年月",
      "阶段",
      "现金账户",
      "投资账户",
      "流动资产",
      "公积金账户",
      "房产估值",
      "车辆估值",
      "主用车估值",
      "新增车辆估值",
      "固定资产",
      "总资产",
      "贷款余额",
      "净资产"
    ], snapshotRows.map((item) => {
      const cashflow = cashflowByMonth.get(item.month);
      return [
        item.month,
        formatMonthDate(baseDate, item.month),
        cashflow?.phase ?? "",
        item.cash_balance,
        item.investment_balance,
        item.liquid_asset_value,
        item.provident_balance,
        item.property_asset_value,
        item.vehicle_asset_value,
        item.first_vehicle_asset_value,
        item.second_vehicle_asset_value,
        item.fixed_asset_value,
        item.total_asset_value,
        item.total_loan_balance,
        item.net_worth
      ];
    })),
    ...csvSection("月现金流明细", [
      "月份序号",
      "真实年月",
      "阶段",
      "现金净流入",
      "现金收入",
      "基础生活支出",
      "定时支出",
      "普通固定还款",
      "已有贷款还款",
      "房贷现金还款",
      "房贷合同还款",
      "公积金账户代扣房贷",
      "车贷还款",
      "主用车贷款",
      "新增车辆贷款",
      "车辆运营成本",
      "主用车能耗",
      "主用车保险",
      "主用车保养",
      "主用车停车",
      "新增车辆能耗",
      "新增车辆保险",
      "新增车辆保养",
      "新增车辆停车",
      "无车通勤成本",
      "主用车首付",
      "新增车辆首付",
      "车辆首付合计",
      "定投买入",
      "基础定投",
      "安全垫达标后追加定投",
      "投资收益",
      "投资买入手续费",
      "投资卖出手续费",
      "投资卖出到账",
      "公积金缴存",
      "公积金现金提取",
      "交易现金支出",
      "交易现金流入",
      "月末现金账户",
      "月末投资账户",
      "月末流动资产",
      "月末公积金账户",
      "月末固定资产",
      "月末总资产",
      "月末贷款余额",
      "月末净资产"
    ], cashflowRows.map((item) => [
      item.month,
      formatMonthDate(baseDate, item.month),
      item.phase,
      item.monthly_cash_delta,
      item.cash_income,
      item.living_expense,
      item.scheduled_expense,
      item.regular_debt_payment,
      item.phased_loan_payment,
      item.house_payment,
      item.house_contract_payment,
      item.provident_house_offset_payment,
      item.vehicle_payment,
      item.first_vehicle_payment,
      item.second_vehicle_payment,
      item.vehicle_operating_cost,
      item.first_vehicle_energy_cost,
      item.first_vehicle_insurance_cost,
      item.first_vehicle_maintenance_cost,
      item.first_vehicle_parking_cost,
      item.second_vehicle_energy_cost,
      item.second_vehicle_insurance_cost,
      item.second_vehicle_maintenance_cost,
      item.second_vehicle_parking_cost,
      item.no_car_commute_cost,
      item.first_vehicle_down_payment,
      item.second_vehicle_down_payment,
      item.vehicle_down_payment,
      item.investment_contribution,
      item.investment_contribution_base,
      item.investment_contribution_cash_sweep,
      item.investment_return,
      item.investment_buy_fee,
      item.investment_sell_fee,
      item.investment_sell_proceeds,
      item.provident_deposit,
      item.provident_withdrawal,
      item.transaction_cash_out,
      item.transaction_cash_in,
      item.cash_balance,
      item.investment_balance,
      item.liquid_asset_value,
      item.provident_balance,
      item.fixed_asset_value,
      item.total_asset_value,
      item.total_loan_balance,
      item.net_worth
    ])),
    ...csvSection("贷款余额与月供", [
      "月份序号",
      "真实年月",
      "商贷余额",
      "公积金贷余额",
      "房贷余额",
      "车贷余额",
      "已有贷款余额",
      "总贷款余额",
      "商贷月供",
      "公积金贷合同月供",
      "房贷合同月供",
      "车贷月供",
      "已有贷款月供",
      "贷款还款合计",
      "现金还款",
      "公积金按月抵月供",
      "公积金半年度冲本金"
    ], loanRows.map((item) => [
      item.month,
      formatMonthDate(baseDate, item.month),
      item.commercial_loan_balance,
      item.provident_loan_balance,
      item.home_loan_balance,
      item.vehicle_loan_balance,
      item.existing_loan_balance,
      item.total_loan_balance,
      item.commercial_monthly_payment,
      item.provident_monthly_payment,
      item.home_monthly_payment,
      item.vehicle_monthly_payment,
      item.existing_monthly_payment,
      item.total_monthly_payment,
      item.cash_monthly_payment,
      item.provident_monthly_withdrawal_payment,
      item.provident_principal_offset_payment
    ])),
    ...csvSection("公积金家庭账户", [
      "月份序号",
      "真实年月",
      "月初余额",
      "个人缴存",
      "单位缴存",
      "缴存合计",
      "利息",
      "租房提取",
      "交易前提取",
      "交易后提取",
      "约定提取",
      "按月抵月供",
      "半年度冲本金",
      "退休销户提取",
      "收入合计",
      "支出合计",
      "月末余额",
      "策略"
    ], providentRows.map((item) => [
      item.month,
      formatMonthDate(baseDate, item.month),
      item.balance_start,
      item.personal_deposit,
      item.employer_deposit,
      item.total_deposit,
      item.interest,
      item.rent_withdrawal,
      item.upfront_withdrawal,
      item.post_transaction_withdrawal,
      item.agreed_withdrawal,
      item.monthly_repayment_withdrawal,
      item.loan_offset_payment,
      item.retirement_withdrawal,
      item.total_inflow,
      item.total_outflow,
      item.balance_end,
      item.strategy_label
    ])),
    ...csvSection("公积金成员账户", [
      "月份序号",
      "真实年月",
      "成员序号",
      "成员",
      "月初余额",
      "个人缴存",
      "单位缴存",
      "缴存合计",
      "利息",
      "租房提取",
      "交易前提取",
      "交易后提取",
      "约定提取",
      "按月抵月供",
      "半年度冲本金",
      "退休销户提取",
      "退休销户关闭",
      "收入合计",
      "支出合计",
      "月末余额"
    ], providentRows.flatMap((row) =>
      [...(row.member_accounts ?? [])]
        .sort((left, right) => left.member_index - right.member_index)
        .map((account) => [
          row.month,
          formatMonthDate(baseDate, row.month),
          account.member_index + 1,
          account.member_name,
          account.balance_start,
          account.personal_deposit,
          account.employer_deposit,
          account.total_deposit,
          account.interest,
          account.rent_withdrawal,
          account.upfront_withdrawal,
          account.post_transaction_withdrawal,
          account.agreed_withdrawal,
          account.monthly_repayment_withdrawal,
          account.loan_offset_payment,
          account.retirement_withdrawal,
          account.account_closed_by_retirement ? "是" : "否",
          account.total_inflow,
          account.total_outflow,
          account.balance_end
        ])
    )),
    ...csvSection("后端月度流水", ["月份序号", "真实年月", "账户", "类别", "项目", "金额", "方向", "来源"], ledgerRows.map((item) => [
      item.month,
      formatMonthDate(baseDate, item.month),
      item.account,
      item.category,
      item.label,
      item.amount,
      item.direction,
      item.source
    ])),
    ...csvSection("策略解释", ["分区", "标题", "解释", "优先级"], strategyRows.map((item) => [
      item.section,
      item.title,
      item.body,
      item.priority
    ])),
    ...csvSection("账户与概念说明", ["代码", "名称", "类别", "管理方", "说明"], (result.account_concepts ?? []).map((item) => [
      item.code,
      item.name,
      item.category,
      item.managed_by,
      item.description
    ])),
    ...csvSection("全局提示与假设", ["类型", "内容"], [
      ...result.eligibility_notes.map((note) => ["资格提示", note]),
      ...result.assumptions.map((note) => ["测算假设", note]),
      ...plan.provident_extraction_notes.map((note) => ["公积金提取提示", note])
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

function PanelTitle({ icon, title, compact = false }: { icon: ReactNode; title: string; compact?: boolean }) {
  return (
    <div className={compact ? "panel-title compact" : "panel-title"}>
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
  className = ""
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
  className?: string;
}) {
  const helpText = description ?? parameterExplanations[label];
  return (
    <label className={`switch-field ${className}`}>
      <input
        type="checkbox"
        checked={checked}
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
