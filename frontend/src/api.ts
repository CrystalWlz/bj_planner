import type {
  AccountConceptSummary,
  AffordabilityResult,
  CoreObjectGroupSummary,
  CoreObjectRecord,
  CoreObjectCategory,
  CoreObjectType,
  GeneratedStrategyBatchRequest,
  GeneratedStrategyRecord,
  HouseholdData,
  MarketSnapshotData,
  PlanningGoalData,
  PlanningFoundationSummary,
  PlanningGoalRecord,
  PlanningGoalType,
  PlanningSequenceResult,
  RecordEnvelope,
  RulePackData,
  ScenarioData,
  SourceDocumentRecord
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const inFlightCalculationRequests = new Map<string, Promise<AffordabilityResult>>();

function assertCompleteAffordabilityResult(result: AffordabilityResult): AffordabilityResult {
  const layers = result.cache_layers;
  if (!layers?.engine || !layers.input || !layers.strategy || !layers.ledger || !layers.visualization) {
    throw new Error("后端计算响应缺少完整 cache_layers，请重启后端服务并让旧缓存按当前格式重建。");
  }
  return result;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function loadInitialData() {
  const [householdRecords, ruleRecords, marketSnapshotRecords] = await Promise.all([
    request<RecordEnvelope<HouseholdData>[]>("/api/households"),
    request<RecordEnvelope<RulePackData>[]>("/api/rule-packs"),
    request<RecordEnvelope<MarketSnapshotData>[]>("/api/market-snapshots")
  ]);
  const scenarioRecords = householdRecords[0]?.id ? await fetchScenarios(householdRecords[0].id) : [];
  return [householdRecords, scenarioRecords, ruleRecords, marketSnapshotRecords] as const;
}

export function fetchHouseholds() {
  return request<RecordEnvelope<HouseholdData>[]>("/api/households");
}

export function fetchScenarios(householdId: string) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  const query = params.toString();
  return request<RecordEnvelope<ScenarioData>[]>(`/api/scenarios${query ? `?${query}` : ""}`);
}

export function fetchMarketSnapshots() {
  return request<RecordEnvelope<MarketSnapshotData>[]>("/api/market-snapshots");
}

export function fetchPlanningGoalSequence(householdId: string, goalType?: PlanningGoalType) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  if (goalType) params.set("goal_type", goalType);
  const query = params.toString();
  return request<PlanningSequenceResult>(`/api/planning-goals/sequence${query ? `?${query}` : ""}`);
}

export function fetchPlanningGoals(householdId: string, goalType?: PlanningGoalType) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  if (goalType) params.set("goal_type", goalType);
  const query = params.toString();
  return request<PlanningGoalRecord[]>(`/api/planning-goals${query ? `?${query}` : ""}`);
}

export function createPlanningGoal(data: PlanningGoalData, householdId?: string | null) {
  return request<PlanningGoalRecord>("/api/planning-goals", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId ?? null, data })
  });
}

export function savePlanningGoal(id: string, data: PlanningGoalData, householdId?: string | null) {
  const payload: { data: PlanningGoalData; household_id?: string | null } = { data };
  if (householdId !== undefined) payload.household_id = householdId;
  return request<PlanningGoalRecord>(`/api/planning-goals/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function deletePlanningGoal(id: string) {
  return request<{ deleted: boolean }>(`/api/planning-goals/${id}`, {
    method: "DELETE"
  });
}

export function fetchCoreObjects(householdId: string, objectType?: CoreObjectType, category?: CoreObjectCategory, ownerKey?: string) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  if (objectType) params.set("object_type", objectType);
  if (category) params.set("category", category);
  if (ownerKey) params.set("owner_key", ownerKey);
  const query = params.toString();
  return request<CoreObjectRecord[]>(`/api/core-objects${query ? `?${query}` : ""}`);
}

export function fetchAccountConcepts(householdId: string) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  const query = params.toString();
  return request<AccountConceptSummary[]>(`/api/account-concepts${query ? `?${query}` : ""}`);
}

export function fetchCoreObjectGroups(householdId: string) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  const query = params.toString();
  return request<CoreObjectGroupSummary[]>(`/api/core-object-groups${query ? `?${query}` : ""}`);
}

export function fetchPlanningFoundation(householdId: string) {
  const params = new URLSearchParams();
  params.set("household_id", householdId);
  const query = params.toString();
  return request<PlanningFoundationSummary>(`/api/planning-foundation${query ? `?${query}` : ""}`);
}

export function fetchGeneratedStrategiesByCacheLayers(payload: GeneratedStrategyBatchRequest) {
  return request<GeneratedStrategyRecord[]>("/api/generated-strategies/by-cache-layers", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function calculateAffordability(
  householdId: string,
  scenarioId: string,
  household: HouseholdData,
  scenario: ScenarioData,
  rulePack: RulePackData,
  marketSnapshot?: MarketSnapshotData | null,
  includeStressTests = false
) {
  const body = JSON.stringify({
    household_id: householdId,
    scenario_id: scenarioId,
    household,
    scenario,
    rule_pack: rulePack,
    market_snapshot: marketSnapshot ?? null,
    include_stress_tests: includeStressTests
  });
  const cached = inFlightCalculationRequests.get(body);
  if (cached) return cached;
  const promise = request<AffordabilityResult>("/api/calculations/affordability", {
    method: "POST",
    body
  }).then(assertCompleteAffordabilityResult).finally(() => {
    inFlightCalculationRequests.delete(body);
  });
  inFlightCalculationRequests.set(body, promise);
  return promise;
}

export function saveHousehold(id: string, household: HouseholdData) {
  return request<RecordEnvelope<HouseholdData>>(`/api/households/${id}`, {
    method: "PUT",
    body: JSON.stringify({ data: household })
  });
}

export function saveScenario(id: string, scenario: ScenarioData) {
  return request<RecordEnvelope<ScenarioData>>(`/api/scenarios/${id}`, {
    method: "PUT",
    body: JSON.stringify({ data: scenario })
  });
}

export function createScenario(scenario: ScenarioData, householdId?: string | null) {
  return request<RecordEnvelope<ScenarioData>>("/api/scenarios", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId ?? null, data: scenario })
  });
}

export function deleteScenario(id: string) {
  return request<{ deleted: boolean }>(`/api/scenarios/${id}`, {
    method: "DELETE"
  });
}

export function saveRulePack(id: string, rulePack: RulePackData) {
  return request<RecordEnvelope<RulePackData>>(`/api/rule-packs/${id}`, {
    method: "PUT",
    body: JSON.stringify({ data: rulePack })
  });
}

export function fetchSourcePreview(url: string, name?: string) {
  return request<SourceDocumentRecord>("/api/sources/fetch-preview", {
    method: "POST",
    body: JSON.stringify({ url, name })
  });
}
