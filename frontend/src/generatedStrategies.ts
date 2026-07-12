import type {
  CarPlanAnalysis,
  CacheLayerHashes,
  ChildPlanData,
  ChildPlanStrategyPoint,
  GeneratedStrategyRecord,
  GeneratedStrategyType,
  InvestmentPlanRecommendation,
  PurchasePlanAnalysis,
  RecordEnvelope,
  ScenarioData,
  TaxStrategyItem,
  TaxStrategyTimelinePoint,
  VehiclePlanData
} from "./types";

export const GENERATED_STRATEGY_TYPES = {
  purchase: "purchase",
  vehicle: "vehicle",
  investment: "investment",
  childPlan: "child_plan",
  tax: "tax",
  careerShock: "career_shock",
} as const;

export function generatedStrategiesByType(
  records: GeneratedStrategyRecord[],
  strategyType: GeneratedStrategyType
) {
  return records.filter((record) => record.strategy_type === strategyType);
}

export function generatedStrategyTypeLabel(type: GeneratedStrategyType) {
  if (type === GENERATED_STRATEGY_TYPES.purchase) return "购房";
  if (type === GENERATED_STRATEGY_TYPES.vehicle) return "购车";
  if (type === GENERATED_STRATEGY_TYPES.investment) return "理财";
  if (type === GENERATED_STRATEGY_TYPES.childPlan) return "养娃";
  if (type === GENERATED_STRATEGY_TYPES.tax) return "税务";
  if (type === GENERATED_STRATEGY_TYPES.careerShock) return "职业";
  return type;
}

export function generatedStrategySearchText(record: GeneratedStrategyRecord) {
  return [
    generatedStrategyTypeLabel(record.strategy_type),
    record.strategy_type,
    record.owner_key,
    record.strategy_key,
    record.variant,
  ].filter(Boolean).join(" ");
}

export function generatedStrategyTypeSummary(records: GeneratedStrategyRecord[]) {
  const counts = new Map<GeneratedStrategyType, number>();
  for (const record of records) {
    counts.set(record.strategy_type, (counts.get(record.strategy_type) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([type, count]) => `${generatedStrategyTypeLabel(type)} ${count}`)
    .join(" · ");
}

export function generatedStrategySummaryByOwner(records: GeneratedStrategyRecord[]) {
  const recordsByOwner = new Map<string, GeneratedStrategyRecord[]>();
  for (const record of records) {
    const ownerKey = record.owner_key || "household";
    recordsByOwner.set(ownerKey, [...(recordsByOwner.get(ownerKey) ?? []), record]);
  }
  return new Map(
    Array.from(recordsByOwner.entries()).map(([ownerKey, ownerRecords]) => [
      ownerKey,
      generatedStrategyTypeSummary(ownerRecords)
    ])
  );
}

export function childPlanStrategyOwnerKeys(childPlans: ChildPlanData[]) {
  const goalOwnerKeys = new Set<string>();
  for (const child of childPlans) {
    if (child.planning_goal_id) {
      goalOwnerKeys.add(child.planning_goal_id);
    }
  }
  return goalOwnerKeys;
}

export function matchesChildPlanStrategyOwner(record: GeneratedStrategyRecord, childPlans: ChildPlanData[]) {
  if (!childPlans.length) return true;
  return childPlanStrategyOwnerKeys(childPlans).has(record.owner_key);
}

export function vehicleStrategyOwnerKeys(vehiclePlans: VehiclePlanData[]) {
  const ownerKeys = new Set<string>();
  vehiclePlans.forEach((vehicle, vehicleIndex) => {
    if (vehicle.planning_goal_id) {
      ownerKeys.add(vehicle.planning_goal_id);
      return;
    }
    ownerKeys.add(`vehicle:${vehicleIndex}:candidate:target`);
    (vehicle.candidate_vehicles ?? []).forEach((_, candidateIndex) => {
      ownerKeys.add(`vehicle:${vehicleIndex}:candidate:${candidateIndex}`);
    });
  });
  return ownerKeys;
}

export function matchesVehicleStrategyOwner(record: GeneratedStrategyRecord, vehiclePlans: VehiclePlanData[]) {
  const ownerKeys = vehicleStrategyOwnerKeys(vehiclePlans);
  return ownerKeys.size === 0 || ownerKeys.has(record.owner_key);
}

export function purchaseStrategyOwnerKeys(scenario?: RecordEnvelope<ScenarioData> | null) {
  if (scenario?.data.planning_goal_id) return new Set([scenario.data.planning_goal_id]);
  if (scenario?.id) return new Set([scenario.id]);
  if (scenario?.data.name) return new Set([scenario.data.name]);
  return new Set<string>();
}

export function matchesPurchaseStrategyOwner(
  record: GeneratedStrategyRecord,
  scenario?: RecordEnvelope<ScenarioData> | null
) {
  const ownerKeys = purchaseStrategyOwnerKeys(scenario);
  return ownerKeys.size === 0 || ownerKeys.has(record.owner_key);
}

function taxStrategyItemFromGeneratedData(data: Record<string, unknown>): TaxStrategyItem | null {
  if (data.entity_kind !== "strategy_item") return null;
  if (typeof data.title !== "string" || typeof data.deduction_type !== "string" || typeof data.status !== "string") return null;
  return data as unknown as TaxStrategyItem;
}

function taxStrategyTimelineFromGeneratedData(data: Record<string, unknown>): TaxStrategyTimelinePoint | null {
  if (data.entity_kind !== "timeline_point") return null;
  if (typeof data.title !== "string" || typeof data.category !== "string" || typeof data.month !== "number") return null;
  return data as unknown as TaxStrategyTimelinePoint;
}

function childPlanStrategyFromGeneratedData(data: Record<string, unknown>): ChildPlanStrategyPoint | null {
  if (typeof data.child_name !== "string" || typeof data.happiness_score !== "number") return null;
  if (!Array.isArray(data.stages) || !Array.isArray(data.warnings)) return null;
  return data as unknown as ChildPlanStrategyPoint;
}

function investmentRecommendationFromGeneratedData(data: Record<string, unknown>): InvestmentPlanRecommendation | null {
  if (typeof data.variant !== "string" || typeof data.plan_name !== "string") return null;
  if (typeof data.monthly_investment !== "number" || typeof data.annual_return !== "number") return null;
  if (!Array.isArray(data.reasons)) return null;
  return data as unknown as InvestmentPlanRecommendation;
}

function carPlanAnalysisFromGeneratedData(data: Record<string, unknown>): CarPlanAnalysis | null {
  if (typeof data.variant !== "string" || typeof data.strategy_key !== "string") return null;
  if (typeof data.vehicle_index !== "number" || typeof data.happiness_score !== "number") return null;
  return data as unknown as CarPlanAnalysis;
}

function purchasePlanAnalysisFromGeneratedData(data: Record<string, unknown>): PurchasePlanAnalysis | null {
  if (typeof data.variant !== "string" || typeof data.description !== "string") return null;
  if (typeof data.happiness_score !== "number" || typeof data.planned_down_payment !== "number") return null;
  return data as unknown as PurchasePlanAnalysis;
}

export function generatedTaxStrategyItems(records: GeneratedStrategyRecord[]): TaxStrategyItem[] {
  return generatedStrategiesByType(records, GENERATED_STRATEGY_TYPES.tax)
    .map((record) => taxStrategyItemFromGeneratedData(record.data))
    .filter((item): item is TaxStrategyItem => item !== null);
}

export function generatedTaxStrategyTimeline(records: GeneratedStrategyRecord[]): TaxStrategyTimelinePoint[] {
  return [...generatedStrategiesByType(records, GENERATED_STRATEGY_TYPES.tax)
    .map((record) => taxStrategyTimelineFromGeneratedData(record.data))
    .filter((item): item is TaxStrategyTimelinePoint => item !== null)]
    .sort((a, b) => a.month - b.month || a.category.localeCompare(b.category) || a.title.localeCompare(b.title));
}

export function generatedChildPlanStrategies(
  records: GeneratedStrategyRecord[],
  childPlans: ChildPlanData[] = [],
  preferredCacheLayers?: CacheLayerHashes | null
): ChildPlanStrategyPoint[] {
  const childRecords = generatedStrategiesByType(records, GENERATED_STRATEGY_TYPES.childPlan)
    .filter((record) => matchesChildPlanStrategyOwner(record, childPlans));
  const preferredRecords = preferredCacheLayers
    ? childRecords.filter((record) => matchesCacheLayers(record, preferredCacheLayers))
    : [];
  return (preferredRecords.length ? preferredRecords : childRecords)
    .map((record) => childPlanStrategyFromGeneratedData(record.data))
    .filter((item): item is ChildPlanStrategyPoint => item !== null)
    .sort((a, b) => (a.birth_month_index ?? Number.MAX_SAFE_INTEGER) - (b.birth_month_index ?? Number.MAX_SAFE_INTEGER) || a.child_name.localeCompare(b.child_name));
}

export function childPlanStrategyForChild(
  strategies: ChildPlanStrategyPoint[],
  child: Pick<ChildPlanData, "planning_goal_id" | "name">
) {
  if (!child.planning_goal_id) return undefined;
  return strategies.find((item) => item.planning_goal_id === child.planning_goal_id);
}

function matchesCacheLayers(record: GeneratedStrategyRecord, cacheLayers: CacheLayerHashes) {
  return record.engine_fingerprint === cacheLayers.engine
    && record.input_hash === cacheLayers.input
    && record.strategy_hash === cacheLayers.strategy
    && record.ledger_hash === cacheLayers.ledger
    && record.visualization_hash === cacheLayers.visualization;
}

export function generatedInvestmentRecommendations(
  records: GeneratedStrategyRecord[],
  preferredCacheLayers?: CacheLayerHashes | null
): InvestmentPlanRecommendation[] {
  const investmentRecords = generatedStrategiesByType(records, GENERATED_STRATEGY_TYPES.investment);
  const preferredRecords = preferredCacheLayers
    ? investmentRecords.filter((record) => matchesCacheLayers(record, preferredCacheLayers))
    : [];
  const sourceRecords = preferredRecords.length ? preferredRecords : investmentRecords;
  const recommendationsByPlanName = new Map<string, InvestmentPlanRecommendation>();

  for (const record of sourceRecords) {
    const recommendation = investmentRecommendationFromGeneratedData(record.data);
    if (!recommendation) continue;
    const existing = recommendationsByPlanName.get(recommendation.plan_name);
    if (!existing || recommendation.score > existing.score) {
      recommendationsByPlanName.set(recommendation.plan_name, recommendation);
    }
  }

  return Array.from(recommendationsByPlanName.values())
    .sort((a, b) => b.score - a.score || a.plan_name.localeCompare(b.plan_name));
}

export function generatedCarPlanAnalyses(
  records: GeneratedStrategyRecord[],
  vehiclePlans: VehiclePlanData[] = [],
  preferredCacheLayers?: CacheLayerHashes | null
): CarPlanAnalysis[] {
  const vehicleRecords = generatedStrategiesByType(records, GENERATED_STRATEGY_TYPES.vehicle)
    .filter((record) => matchesVehicleStrategyOwner(record, vehiclePlans));
  const preferredRecords = preferredCacheLayers
    ? vehicleRecords.filter((record) => matchesCacheLayers(record, preferredCacheLayers))
    : [];
  return (preferredRecords.length ? preferredRecords : vehicleRecords)
    .map((record) => carPlanAnalysisFromGeneratedData(record.data))
    .filter((item): item is CarPlanAnalysis => item !== null)
    .sort((a, b) => {
      if (a.vehicle_index !== b.vehicle_index) return a.vehicle_index - b.vehicle_index;
      const leftCandidate = a.vehicle_candidate_index ?? -1;
      const rightCandidate = b.vehicle_candidate_index ?? -1;
      if (leftCandidate !== rightCandidate) return leftCandidate - rightCandidate;
      return b.happiness_score - a.happiness_score || a.variant.localeCompare(b.variant);
    });
}

export function generatedPurchasePlanAnalyses(records: GeneratedStrategyRecord[], scenario?: RecordEnvelope<ScenarioData> | null): PurchasePlanAnalysis[] {
  return generatedStrategiesByType(records, GENERATED_STRATEGY_TYPES.purchase)
    .filter((record) => matchesPurchaseStrategyOwner(record, scenario))
    .map((record) => purchasePlanAnalysisFromGeneratedData(record.data))
    .filter((item): item is PurchasePlanAnalysis => item !== null)
    .sort((a, b) => {
      if (a.is_recommended !== b.is_recommended) return a.is_recommended ? -1 : 1;
      return b.recommendation_score - a.recommendation_score || a.variant.localeCompare(b.variant);
    });
}
