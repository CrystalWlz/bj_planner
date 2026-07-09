import { useCallback, useEffect, useRef } from "react";
import type {
  CalculationContextGoalSnapshot,
  CarPlanAnalysis,
  ChildPlanData,
  PlanningGoalRecord,
  PlanningGoalType,
  PlanningGoalData,
  PlanningTimingMode,
  ResolvedPlanningGoal,
  ScenarioData,
  VehiclePlanData
} from "./types";

const HOME_TARGET_CONTROL_KEYS = [
  "planning_goal_id",
  "purchase_sequence",
  "purchase_planning_mode",
  "depends_on_goal_id",
  "after_previous_purchase_delay_months",
  "manual_purchase_delay_months",
  "planning_window_start_month",
  "planning_window_end_month",
  "selected_purchase_plan_variant",
  "provident_rate",
  "deed_tax_rate",
  "provident_account_repayment_strategy",
  "provident_account_repayment_switch_enabled",
  "provident_account_repayment_switch_after_month",
  "provident_account_repayment_switch_to_strategy"
];

const VEHICLE_TARGET_CONTROL_KEYS = [
  "planning_goal_id",
  "planning_sequence",
  "purchase_timing_mode",
  "depends_on_goal_id",
  "after_previous_event_delay_months",
  "manual_purchase_delay_months",
  "planning_window_start_month",
  "planning_window_end_month",
  "selected_strategy_variant"
];

const CHILD_TARGET_CONTROL_KEYS = [
  "planning_goal_id",
  "planning_sequence",
  "timing_mode",
  "planned_birth_month",
  "planned_birth_start_month",
  "planned_birth_end_month"
];

function withoutPlanningControlFields<T extends Record<string, unknown>>(value: T, keys: string[]): Record<string, unknown> {
  const controlKeys = new Set(keys);
  return Object.fromEntries(Object.entries(value).filter(([key]) => !controlKeys.has(key)));
}

export function useDebouncedPlanningGoalSave<T>(options: {
  buildGoalData: (data: T) => PlanningGoalData;
  saveGoal: (goalId: string, goalData: PlanningGoalData) => Promise<void>;
  onError: (error: unknown) => void;
  onSaved?: () => void;
  ignoreGoalIds?: Set<string>;
}) {
  const timers = useRef<Record<string, number>>({});
  const { buildGoalData, saveGoal, onError, onSaved, ignoreGoalIds } = options;

  useEffect(() => () => {
    Object.values(timers.current).forEach((timer) => window.clearTimeout(timer));
  }, []);

  return useCallback((goalId: string, data: T, delayMs = 700) => {
    if (!goalId || ignoreGoalIds?.has(goalId)) return;
    const existingTimer = timers.current[goalId];
    if (existingTimer) window.clearTimeout(existingTimer);
    timers.current[goalId] = window.setTimeout(() => {
      delete timers.current[goalId];
      void saveGoal(goalId, buildGoalData(data))
        .then(() => onSaved?.())
        .catch(onError);
    }, delayMs);
  }, [buildGoalData, ignoreGoalIds, onError, onSaved, saveGoal]);
}

export function planningTimingModeFromChildPlan(child: ChildPlanData): PlanningGoalData["timing_mode"] {
  if (child.timing_mode === "manual_month") return "manual_month";
  if (child.timing_mode === "not_planned") return "not_planned";
  return "after_goal";
}

export const PLANNING_GOAL_AUTO_DEPENDENCY_LABEL = "按顺序自动选择上一目标";

export const HOME_PLANNING_TIMING_OPTIONS: Array<{
  value: ScenarioData["purchase_planning_mode"];
  label: string;
}> = [
  { value: "after_previous_purchase", label: "按规划顺序排队" },
  { value: "parallel", label: "可并行考虑" },
];

export const VEHICLE_PLANNING_TIMING_OPTIONS: Array<{
  value: VehiclePlanData["purchase_timing_mode"];
  label: string;
}> = [
  { value: "auto_sequence", label: "按消费顺序自动排" },
  { value: "parallel", label: "可并行考虑" },
  { value: "manual_month", label: "手动指定月份" },
  { value: "not_planned", label: "暂不纳入规划" },
];

export const CHILD_PLANNING_TIMING_OPTIONS: Array<{
  value: ChildPlanData["timing_mode"];
  label: string;
}> = [
  { value: "after_first_home", label: "买房后开始计划" },
  { value: "manual_month", label: "指定出生年月" },
  { value: "not_planned", label: "暂不纳入规划" },
];

export function childPlanningTimingLabel(child: Pick<ChildPlanData, "timing_mode">) {
  if (child.timing_mode === "after_first_home") return "买房后开始";
  if (child.timing_mode === "manual_month") return "指定年月";
  return "暂不纳入";
}

export function childPlanHasPlanningTiming(child: Pick<ChildPlanData, "timing_mode">) {
  return child.timing_mode !== "not_planned";
}

export function childPlanIsIncludedInPlanning(child: Pick<ChildPlanData, "enabled" | "timing_mode">) {
  return child.enabled && childPlanHasPlanningTiming(child);
}

export function childPlanningTimingPatch(timingMode: ChildPlanData["timing_mode"]) {
  return {
    timing_mode: timingMode,
    enabled: timingMode !== "not_planned",
  } satisfies Partial<ChildPlanData>;
}

export interface YearMonthValue {
  year: number;
  month: number;
}

function parsePlanningMonthValue(value: string | null | undefined): YearMonthValue | null {
  if (!value) return null;
  const [yearPart, monthPart] = value.split("-");
  const year = Number(yearPart);
  const month = Number(monthPart);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
  return { year, month };
}

function comparePlanningMonth(left: YearMonthValue, right: YearMonthValue) {
  return (left.year - right.year) * 12 + left.month - right.month;
}

export function resolveChildBirthMonth(child: ChildPlanData): YearMonthValue | null {
  if (child.birth_month) return parsePlanningMonthValue(child.birth_month);
  if (child.planned_birth_start_month) return parsePlanningMonthValue(child.planned_birth_start_month);
  if (child.planned_birth_end_month) return parsePlanningMonthValue(child.planned_birth_end_month);
  if (child.timing_mode === "manual_month" && child.planned_birth_month) return parsePlanningMonthValue(child.planned_birth_month);
  if (child.timing_mode === "after_first_home" && child.planned_birth_month) return parsePlanningMonthValue(child.planned_birth_month);
  if (child.timing_mode === "after_first_home") return null;
  return parsePlanningMonthValue(child.planned_birth_month);
}

export function childEducationStageLabel(child: ChildPlanData, today = new Date()) {
  const birth = resolveChildBirthMonth(child);
  if (!birth) return child.timing_mode === "not_planned" ? "暂不规划" : "出生时间待定";
  const current = { year: today.getFullYear(), month: today.getMonth() + 1 };
  const ageMonths = comparePlanningMonth(current, birth);
  if (ageMonths < 0) return "未出生";
  const educationStart = parsePlanningMonthValue(child.education_start_month);
  if (educationStart && comparePlanningMonth(current, educationStart) >= 0) {
    if (ageMonths < 15 * 12) return "中小学阶段";
    return "高等教育阶段";
  }
  if (ageMonths < 36) return "婴幼儿阶段";
  return "幼儿园阶段";
}

export function childMonthlyCostAt(child: ChildPlanData, today = new Date()) {
  if (!childPlanIsIncludedInPlanning(child)) return 0;
  const stage = childEducationStageLabel(child, today);
  if (stage === "婴幼儿阶段") return child.monthly_childcare_cost_before_kindergarten;
  if (stage === "幼儿园阶段") return child.monthly_kindergarten_cost;
  if (stage === "中小学阶段") return child.monthly_primary_secondary_cost;
  if (stage === "高等教育阶段") return child.monthly_higher_education_cost;
  return 0;
}

export function planningInclusionStatusLabel(
  includedInPlanning: boolean,
  enabled: boolean,
  options: {
    includedLabel?: string;
    pausedLabel?: string;
    disabledLabel?: string;
  } = {}
) {
  if (includedInPlanning) return options.includedLabel ?? "纳入规划";
  return enabled ? options.pausedLabel ?? "暂不纳入" : options.disabledLabel ?? "已停用";
}

export function planningGoalTypeLabel(type: PlanningGoalType) {
  if (type === "home") return "购房";
  if (type === "vehicle") return "购车";
  if (type === "child") return "养娃";
  if (type === "renovation") return "装修";
  return "目标";
}

export const GENERIC_PLANNING_GOAL_TIMING_OPTIONS: Array<{
  value: PlanningGoalData["timing_mode"];
  label: string;
}> = [
  { value: "auto_sequence", label: "按规划顺序排队" },
  { value: "parallel", label: "可并行考虑" },
  { value: "manual_month", label: "手动指定月份" },
  { value: "after_goal", label: "排在某目标之后" },
  { value: "not_planned", label: "暂不纳入规划" },
];

export function genericPlanningGoalDefaultData(
  goalType: Extract<PlanningGoalType, "renovation" | "other">,
  index: number
): PlanningGoalData {
  const isRenovation = goalType === "renovation";
  const defaultBudget = isRenovation ? 250000 : 100000;
  const name = isRenovation ? `装修目标 ${index + 1}` : `其它目标 ${index + 1}`;
  return {
    schema_version: 34,
    goal_type: goalType,
    name,
    enabled: true,
    priority: index + 50,
    timing_mode: "auto_sequence",
    earliest_purchase_month: "",
    earliest_purchase_delay_months: 0,
    planning_window_start_month: "",
    planning_window_end_month: "",
    depends_on_goal_id: "",
    delay_after_dependency_months: 0,
    allow_parallel: false,
    selected_strategy_id: "",
    target_params: {
      name,
      estimated_cost: defaultBudget,
      category: isRenovation ? "renovation" : "other_major_goal"
    },
    financing_preferences: {
      funding_mode: "cash_or_investment"
    },
    holding_cost_params: {},
    metadata: {},
    notes: ""
  };
}

export function genericPlanningGoalDuplicateData(goal: PlanningGoalRecord, index: number): PlanningGoalData {
  const nextName = `${goal.data.name || planningGoalTypeLabel(goal.goal_type)} 复制`;
  return {
    ...goal.data,
    name: nextName,
    enabled: true,
    priority: index + 50,
    target_params: {
      ...goal.data.target_params,
      name: nextName,
    },
    metadata: {
      ...goal.data.metadata,
      duplicated_from_goal_id: goal.id,
    }
  };
}

export type PlanningGoalOptionSource = Pick<
  ResolvedPlanningGoal | CalculationContextGoalSnapshot,
  "id" | "name" | "goal_type" | "enabled" | "normalized_timing_mode"
>;

export interface PlanningGoalDependencyOption {
  id: string;
  label: string;
}

export function planningGoalDependencyOptions(
  goals: PlanningGoalOptionSource[] = [],
  excludedIds = new Set<string>()
): PlanningGoalDependencyOption[] {
  return goals
    .filter((goal) => goal.enabled && goal.normalized_timing_mode !== "not_planned" && !excludedIds.has(goal.id))
    .map((goal) => ({
      id: goal.id,
      label: `${goal.name}（${planningGoalTypeLabel(goal.goal_type)}）`
    }));
}

export function planningGoalDependencyLabel(
  goalId: string,
  options: PlanningGoalDependencyOption[] = [],
  goals: PlanningGoalOptionSource[] = []
) {
  return options.find((goal) => goal.id === goalId)?.label ?? goals.find((goal) => goal.id === goalId)?.name ?? "";
}

export function planningGoalIsNotPlanned(goal: { normalized_timing_mode: PlanningTimingMode }) {
  return goal.normalized_timing_mode === "not_planned";
}

export function planningGoalTimingLabel(goal: {
  normalized_timing_mode: PlanningTimingMode;
  depends_on_goal_name?: string;
}) {
  if (planningGoalIsNotPlanned(goal)) return "暂不纳入规划";
  if (goal.normalized_timing_mode === "parallel") return "并行";
  if (goal.normalized_timing_mode === "manual_month") return "指定时间";
  if (goal.normalized_timing_mode === "after_goal") {
    return goal.depends_on_goal_name ? `跟随 ${goal.depends_on_goal_name}` : "跟随目标";
  }
  return "自动顺序";
}

export function planningGoalOrderLabel(goal: {
  normalized_timing_mode: PlanningTimingMode;
  sequence_index: number;
}) {
  if (planningGoalIsNotPlanned(goal)) return "暂不排序";
  if (goal.normalized_timing_mode === "parallel") return "并行";
  return goal.sequence_index <= 0 ? "暂不排序" : `第 ${goal.sequence_index} 项`;
}

export function planningGoalTimingSummary(goal: {
  normalized_timing_mode: PlanningTimingMode;
  depends_on_goal_name?: string;
  resolved_not_before_month: number;
}) {
  return planningGoalIsNotPlanned(goal)
    ? "不参与本次推演"
    : `${planningGoalTimingLabel(goal)} · 最早第 ${goal.resolved_not_before_month} 个月`;
}

export function scenarioPlanningTimingSummary(
  scenario: ScenarioData,
  dependencyLabel = "指定目标"
) {
  if (!scenario.enabled) return "暂不纳入规划";
  if (scenario.purchase_planning_mode === "parallel") return "允许并行考虑";
  if (scenario.depends_on_goal_id) {
    return `跟随「${dependencyLabel || "指定目标"}」后 ${scenario.after_previous_purchase_delay_months || 0} 个月`;
  }
  return scenario.purchase_sequence <= 1
    ? "自动安排"
    : `排在第 ${scenario.purchase_sequence - 1} 个目标之后 ${scenario.after_previous_purchase_delay_months || 0} 个月`;
}

export function homePurchasePlanningModeForSequence(sequence: number): ScenarioData["purchase_planning_mode"] {
  return sequence <= 1 ? "parallel" : "after_previous_purchase";
}

export function homePlanningTimingPatch(
  scenario: Pick<ScenarioData, "depends_on_goal_id">,
  planningMode: ScenarioData["purchase_planning_mode"]
) {
  return {
    purchase_planning_mode: planningMode,
    depends_on_goal_id: planningMode === "parallel" ? "" : scenario.depends_on_goal_id
  } satisfies Partial<ScenarioData>;
}

export function homePlanIsIncludedInPlanning(
  scenario: Pick<ScenarioData, "enabled">,
  normalizedTimingMode: PlanningTimingMode | "" = ""
) {
  return scenario.enabled && normalizedTimingMode !== "not_planned";
}

export function homeDemandIsIncludedInPlanning(
  scenarios: Array<Pick<ScenarioData, "enabled">>,
  normalizedTimingMode: PlanningTimingMode | "" = ""
) {
  return normalizedTimingMode !== "not_planned" && scenarios.some((scenario) => scenario.enabled);
}

export function vehiclePlanningTimingSummary(
  vehicle: VehiclePlanData,
  dependencyLabel = "指定目标"
) {
  if (!vehicle.enabled || vehicle.purchase_timing_mode === "not_planned") return "暂不纳入规划";
  if (vehicle.purchase_timing_mode === "parallel") return "允许并行考虑";
  if (vehicle.purchase_timing_mode === "manual_month") {
    return `不早于 ${vehicle.manual_purchase_delay_months || vehicle.purchase_delay_months || 0} 个月后`;
  }
  if (vehicle.depends_on_goal_id) {
    return `跟随「${dependencyLabel || "指定目标"}」后 ${vehicle.after_previous_event_delay_months || 0} 个月`;
  }
  return `按消费顺序自动排，前一事件后 ${vehicle.after_previous_event_delay_months || 0} 个月`;
}

export function vehiclePlanningControlDefaults(
  index: number,
  base?: Partial<VehiclePlanData>
) {
  return {
    planning_goal_id: base?.planning_goal_id ?? "",
    planning_sequence: base?.planning_sequence ?? index + 1,
    purchase_timing_mode: base?.purchase_timing_mode ?? "auto_sequence",
    depends_on_goal_id: base?.depends_on_goal_id ?? "",
    after_previous_event_delay_months: base?.after_previous_event_delay_months ?? 0,
    manual_purchase_delay_months: base?.manual_purchase_delay_months ?? base?.purchase_delay_months ?? 0,
    planning_window_start_month: base?.planning_window_start_month ?? "",
    planning_window_end_month: base?.planning_window_end_month ?? "",
  } satisfies Pick<
    VehiclePlanData,
    | "planning_goal_id"
    | "planning_sequence"
    | "purchase_timing_mode"
    | "depends_on_goal_id"
    | "after_previous_event_delay_months"
    | "manual_purchase_delay_months"
    | "planning_window_start_month"
    | "planning_window_end_month"
  >;
}

export function vehiclePlanHasPlanningTiming(vehicle: Pick<VehiclePlanData, "purchase_timing_mode">) {
  return vehicle.purchase_timing_mode !== "not_planned";
}

export function vehiclePlanIsIncludedInPlanning(vehicle: Pick<VehiclePlanData, "enabled" | "purchase_timing_mode">) {
  return vehicle.enabled && vehiclePlanHasPlanningTiming(vehicle);
}

export function vehiclePlanUsesDependencySelector(vehicle: Pick<VehiclePlanData, "purchase_timing_mode">) {
  return vehicle.purchase_timing_mode === "auto_sequence";
}

export function vehiclePlanningTimingModeValue(vehicle: Pick<VehiclePlanData, "purchase_timing_mode">) {
  return vehicle.purchase_timing_mode || "auto_sequence";
}

export function vehiclePlanningEnabledPatch(
  vehicle: Pick<VehiclePlanData, "purchase_timing_mode">,
  enabled: boolean
) {
  return {
    enabled,
    purchase_timing_mode: enabled && vehicle.purchase_timing_mode === "not_planned" ? "auto_sequence" : vehicle.purchase_timing_mode,
  } satisfies Partial<VehiclePlanData>;
}

export function vehiclePlanningTimingPatch(
  vehicle: Pick<VehiclePlanData, "depends_on_goal_id">,
  timingMode: VehiclePlanData["purchase_timing_mode"]
) {
  return {
    purchase_timing_mode: timingMode,
    enabled: timingMode !== "not_planned",
    depends_on_goal_id: timingMode === "auto_sequence" ? vehicle.depends_on_goal_id : "",
  } satisfies Partial<VehiclePlanData>;
}

export function vehiclePrepaymentModeLabel(strategy: Pick<
  CarPlanAnalysis,
  "prepayment_allowed" | "prepayment_enabled" | "prepayment_strategy_type"
>) {
  if (!strategy.prepayment_allowed) return "合同不允许提前还本";
  if (!strategy.prepayment_enabled) return "不提前还本";
  if (strategy.prepayment_strategy_type === "lump_sum") return "一次性提前还本";
  if (strategy.prepayment_strategy_type === "monthly") return "分月提前还本";
  if (strategy.prepayment_strategy_type === "hybrid") return "一次性 + 分月组合";
  return "手动提前还本";
}

export function childPlanningGoalData(child: ChildPlanData, index: number, firstHomeGoalId = ""): PlanningGoalData {
  const targetParams = withoutPlanningControlFields({ ...child }, CHILD_TARGET_CONTROL_KEYS);
  const timingMode = planningTimingModeFromChildPlan(child);
  return {
    schema_version: 34,
    goal_type: "child",
    name: child.name || `子女计划 ${index + 1}`,
    enabled: child.enabled,
    priority: index + 30,
    timing_mode: timingMode,
    earliest_purchase_month: child.timing_mode === "manual_month" ? child.planned_birth_month || child.planned_birth_start_month : "",
    earliest_purchase_delay_months: 0,
    planning_window_start_month: child.planned_birth_start_month,
    planning_window_end_month: child.planned_birth_end_month,
    depends_on_goal_id: child.timing_mode === "after_first_home" ? firstHomeGoalId : "",
    delay_after_dependency_months: 0,
    allow_parallel: false,
    selected_strategy_id: "",
    target_params: targetParams,
    financing_preferences: {},
    holding_cost_params: {
      expense_strategy_mode: child.expense_strategy_mode,
      monthly_childcare_cost_before_kindergarten: child.monthly_childcare_cost_before_kindergarten,
      monthly_kindergarten_cost: child.monthly_kindergarten_cost,
      monthly_primary_secondary_cost: child.monthly_primary_secondary_cost,
      monthly_higher_education_cost: child.monthly_higher_education_cost
    },
    metadata: {
      child_timing_mode: child.timing_mode,
      planned_birth_month: child.planned_birth_month
    },
    notes: child.notes
  };
}

export function planningTimingModeFromVehiclePlan(vehicle: VehiclePlanData): PlanningGoalData["timing_mode"] {
  if (!vehicle.enabled || vehicle.purchase_timing_mode === "not_planned") return "not_planned";
  if (vehicle.purchase_timing_mode === "manual_month") return "manual_month";
  if (vehicle.purchase_timing_mode === "parallel") return "parallel";
  if (vehicle.depends_on_goal_id) return "after_goal";
  return "auto_sequence";
}

export function vehiclePlanningGoalData(vehicle: VehiclePlanData, index: number): PlanningGoalData {
  const targetParams = withoutPlanningControlFields({ ...vehicle }, VEHICLE_TARGET_CONTROL_KEYS);
  const timingMode = planningTimingModeFromVehiclePlan(vehicle);
  return {
    schema_version: 34,
    goal_type: "vehicle",
    name: vehicle.name || `用车需求 ${index + 1}`,
    enabled: vehicle.enabled,
    priority: Math.max(1, vehicle.planning_sequence || index + 1),
    timing_mode: timingMode,
    earliest_purchase_month: "",
    earliest_purchase_delay_months: Math.max(0, vehicle.manual_purchase_delay_months ?? vehicle.purchase_delay_months ?? 0),
    planning_window_start_month: vehicle.planning_window_start_month,
    planning_window_end_month: vehicle.planning_window_end_month,
    depends_on_goal_id: timingMode === "after_goal" ? vehicle.depends_on_goal_id : "",
    delay_after_dependency_months: Math.max(0, vehicle.after_previous_event_delay_months ?? 0),
    allow_parallel: timingMode === "parallel",
    selected_strategy_id: vehicle.selected_strategy_variant || "target",
    target_params: targetParams,
    financing_preferences: {
      financing_options: vehicle.financing_options,
      loan_prepayment_enabled: vehicle.loan_prepayment_enabled,
      loan_prepayment_strategy_type: vehicle.loan_prepayment_strategy_type
    },
    holding_cost_params: {
      annual_mileage_km: vehicle.annual_mileage_km,
      monthly_parking_cost: vehicle.monthly_parking_cost,
      annual_maintenance_cost: vehicle.annual_maintenance_cost,
      annual_insurance_rate: vehicle.annual_insurance_rate
    },
    metadata: {},
    notes: vehicle.notes
  };
}

export function planningTimingModeFromScenario(scenario: ScenarioData): PlanningGoalData["timing_mode"] {
  if (scenario.purchase_planning_mode === "parallel") return "parallel";
  if (scenario.depends_on_goal_id) return "after_goal";
  return "auto_sequence";
}

export function homePlanningGoalData(scenario: ScenarioData): PlanningGoalData {
  const targetParams = withoutPlanningControlFields({ ...scenario }, HOME_TARGET_CONTROL_KEYS);
  const timingMode = planningTimingModeFromScenario(scenario);
  return {
    schema_version: 34,
    goal_type: "home",
    name: scenario.name || "购房目标",
    enabled: scenario.enabled,
    priority: Math.max(1, scenario.purchase_sequence || 1),
    timing_mode: timingMode,
    earliest_purchase_month: "",
    earliest_purchase_delay_months: Math.max(0, scenario.manual_purchase_delay_months ?? 0),
    planning_window_start_month: scenario.planning_window_start_month,
    planning_window_end_month: scenario.planning_window_end_month,
    depends_on_goal_id: timingMode === "after_goal" ? scenario.depends_on_goal_id : "",
    delay_after_dependency_months: Math.max(0, scenario.after_previous_purchase_delay_months ?? 0),
    allow_parallel: scenario.purchase_planning_mode === "parallel",
    selected_strategy_id: scenario.selected_purchase_plan_variant || "",
    target_params: targetParams,
    financing_preferences: {
      commercial_repayment_method: scenario.commercial_repayment_method,
      provident_repayment_method: scenario.provident_repayment_method,
      commercial_prepayment_mode: scenario.commercial_prepayment_mode,
      provident_account_repayment_strategy: scenario.provident_account_repayment_strategy,
      provident_account_repayment_switch_enabled: scenario.provident_account_repayment_switch_enabled,
      provident_account_repayment_switch_after_month: scenario.provident_account_repayment_switch_after_month,
      provident_account_repayment_switch_to_strategy: scenario.provident_account_repayment_switch_to_strategy,
      investment_withdrawal_mode: scenario.investment_withdrawal_mode
    },
    holding_cost_params: {},
    metadata: {},
    notes: ""
  };
}
