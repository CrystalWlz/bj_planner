import type {
  AccountConceptSummary,
  AffordabilityResult,
  BrokerOrderDispatchRecord,
  BrokerReconciliationRunRecord,
  CoreObjectGroupSummary,
  CoreObjectRecord,
  CoreObjectCategory,
  CoreObjectType,
  GeneratedStrategyBatchRequest,
  GeneratedStrategyRecord,
  HouseholdData,
  InvestmentInstrumentData,
  InvestmentInstrumentRecord,
  InvestmentMarketSnapshotData,
  InvestmentMarketSnapshotRecord,
  MarketSnapshotData,
  PropertyValuationRecord,
  PropertyValuationRefreshResponse,
  PersonalPensionReturnRefreshResponse,
  PersonalPensionReturnSnapshotRecord,
  PaperOrderData,
  PaperOrderRecord,
  PaperPortfolioSummary,
  PostTradeRiskReviewRecord,
  PlanningGoalData,
  PlanningFoundationSummary,
  PlanningGoalRecord,
  PlanningGoalType,
  PlanningSequenceResult,
  RecordEnvelope,
  RulePackData,
  QuantBacktestResult,
  QuantBacktestRunRecord,
  QuantInvestmentPolicyData,
  QuantInvestmentPolicyRecord,
  QuantInvestmentProposalRecord,
  ScenarioData,
  SourceDocumentRecord
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const inFlightCalculationRequests = new Map<string, Promise<AffordabilityResult>>();
const completedCalculationResults = new Map<string, AffordabilityResult>();
const inFlightGeneratedStrategyRequests = new Map<string, Promise<GeneratedStrategyRecord[]>>();
const completedGeneratedStrategyResults = new Map<string, GeneratedStrategyRecord[]>();
const MAX_COMPLETED_CALCULATION_RESULTS = 48;
const MAX_COMPLETED_GENERATED_STRATEGY_RESULTS = 48;

function rememberCalculationResult(key: string, result: AffordabilityResult) {
  completedCalculationResults.delete(key);
  completedCalculationResults.set(key, result);
  while (completedCalculationResults.size > MAX_COMPLETED_CALCULATION_RESULTS) {
    const oldestKey = completedCalculationResults.keys().next().value;
    if (typeof oldestKey !== "string") break;
    completedCalculationResults.delete(oldestKey);
  }
  return result;
}

function rememberGeneratedStrategyResult(key: string, result: GeneratedStrategyRecord[]) {
  completedGeneratedStrategyResults.delete(key);
  completedGeneratedStrategyResults.set(key, result);
  while (completedGeneratedStrategyResults.size > MAX_COMPLETED_GENERATED_STRATEGY_RESULTS) {
    const oldestKey = completedGeneratedStrategyResults.keys().next().value;
    if (typeof oldestKey !== "string") break;
    completedGeneratedStrategyResults.delete(oldestKey);
  }
  return result;
}

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
  const homeGoals = householdRecords[0]?.id ? await fetchPlanningGoals(householdRecords[0].id, "home") : [];
  return [householdRecords, homeGoals, ruleRecords, marketSnapshotRecords] as const;
}

export function fetchHouseholds() {
  return request<RecordEnvelope<HouseholdData>[]>("/api/households");
}

export function fetchMarketSnapshots() {
  return request<RecordEnvelope<MarketSnapshotData>[]>("/api/market-snapshots");
}

export function fetchQuantInvestmentPolicies(householdId: string) {
  return request<QuantInvestmentPolicyRecord[]>(`/api/quant-investment/policies?${new URLSearchParams({ household_id: householdId })}`);
}

export function createQuantInvestmentPolicy(householdId: string, data: QuantInvestmentPolicyData) {
  return request<QuantInvestmentPolicyRecord>("/api/quant-investment/policies", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, data })
  });
}

export function saveQuantInvestmentPolicy(id: string, householdId: string, data: QuantInvestmentPolicyData) {
  return request<QuantInvestmentPolicyRecord>(`/api/quant-investment/policies/${id}`, {
    method: "PUT",
    body: JSON.stringify({ household_id: householdId, data })
  });
}

export function fetchQuantInvestmentInstruments(householdId: string) {
  return request<InvestmentInstrumentRecord[]>(`/api/quant-investment/instruments?${new URLSearchParams({ household_id: householdId })}`);
}

export function createQuantInvestmentInstrument(householdId: string, data: InvestmentInstrumentData) {
  return request<InvestmentInstrumentRecord>("/api/quant-investment/instruments", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, data })
  });
}

export function saveQuantInvestmentInstrument(id: string, householdId: string, data: InvestmentInstrumentData) {
  return request<InvestmentInstrumentRecord>(`/api/quant-investment/instruments/${id}`, {
    method: "PUT",
    body: JSON.stringify({ household_id: householdId, data })
  });
}

export function fetchQuantMarketSnapshots(householdId: string) {
  return request<InvestmentMarketSnapshotRecord[]>(`/api/quant-investment/market-snapshots?${new URLSearchParams({ household_id: householdId })}`);
}

export function createQuantMarketSnapshot(householdId: string, instrumentId: string, data: InvestmentMarketSnapshotData) {
  return request<InvestmentMarketSnapshotRecord>("/api/quant-investment/market-snapshots", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, instrument_id: instrumentId, data })
  });
}

export function refreshQuantMarketData(householdId: string, startDate = "") {
  return request<{ records: InvestmentMarketSnapshotRecord[]; warnings: string[] }>("/api/quant-investment/market-data/refresh", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, start_date: startDate })
  });
}

export function fetchQuantInvestmentProposals(householdId: string) {
  return request<QuantInvestmentProposalRecord[]>(`/api/quant-investment/proposals?${new URLSearchParams({ household_id: householdId })}`);
}

export function createQuantInvestmentProposal(householdId: string, policyId: string) {
  return request<QuantInvestmentProposalRecord>("/api/quant-investment/proposals", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, policy_id: policyId })
  });
}

export function runQuantInvestmentBacktest(householdId: string, policyId: string, monthlyContribution: number) {
  return request<QuantBacktestResult>("/api/quant-investment/backtests", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, policy_id: policyId, monthly_contribution: monthlyContribution })
  });
}

export function fetchQuantBacktestRuns(householdId: string) {
  return request<QuantBacktestRunRecord[]>(`/api/quant-investment/backtest-runs?${new URLSearchParams({ household_id: householdId })}`);
}

export function fetchQuantPaperOrders(householdId: string) {
  return request<PaperOrderRecord[]>(`/api/quant-investment/paper-orders?${new URLSearchParams({ household_id: householdId })}`);
}

export function fetchQuantPaperPortfolio(householdId: string) {
  return request<PaperPortfolioSummary>(`/api/quant-investment/paper-portfolio?${new URLSearchParams({ household_id: householdId })}`);
}

export function fetchQuantPostTradeRiskReviews(householdId: string) {
  return request<PostTradeRiskReviewRecord[]>(`/api/quant-investment/post-trade-risk-reviews?${new URLSearchParams({ household_id: householdId })}`);
}

export function reviewQuantPostTradeRisk(householdId: string, riskStateHash: string, reviewNote: string) {
  return request<PostTradeRiskReviewRecord>("/api/quant-investment/post-trade-risk-reviews", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, risk_state_hash: riskStateHash, review_note: reviewNote })
  });
}

export function fetchQuantBrokerOrderDispatches(householdId: string) {
  return request<BrokerOrderDispatchRecord[]>(`/api/quant-investment/broker-order-dispatches?${new URLSearchParams({ household_id: householdId })}`);
}

export function retryQuantBrokerOrderDispatch(
  id: string,
  householdId: string,
  reconciliationId: string,
  reviewNote: string,
) {
  return request<BrokerOrderDispatchRecord>(`/api/quant-investment/broker-order-dispatches/${id}/retry`, {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, reconciliation_id: reconciliationId, review_note: reviewNote })
  });
}

export function fetchQuantBrokerReconciliations(householdId: string) {
  return request<BrokerReconciliationRunRecord[]>(`/api/quant-investment/broker-reconciliations?${new URLSearchParams({ household_id: householdId })}`);
}

export function reconcileQuantPaperBroker(householdId: string) {
  return request<BrokerReconciliationRunRecord>("/api/quant-investment/broker-reconciliations/paper", {
    method: "POST",
    body: JSON.stringify({ household_id: householdId })
  });
}

export function simulateQuantPaperOrder(id: string, householdId: string, executedPrice?: number) {
  return request<PaperOrderRecord>(`/api/quant-investment/paper-orders/${id}/simulate`, {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, executed_price: executedPrice ?? null })
  });
}

export function cancelQuantPaperOrder(id: string, householdId: string, reason = "用户人工取消模拟订单") {
  return request<PaperOrderRecord>(`/api/quant-investment/paper-orders/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ household_id: householdId, reason })
  });
}

export function createMarketSnapshot(data: MarketSnapshotData) {
  return request<RecordEnvelope<MarketSnapshotData>>("/api/market-snapshots", {
    method: "POST",
    body: JSON.stringify({ data })
  });
}

export function fetchPropertyValuations(householdId: string, planningGoalId?: string) {
  const params = new URLSearchParams({ household_id: householdId });
  if (planningGoalId) params.set("planning_goal_id", planningGoalId);
  return request<PropertyValuationRecord[]>(`/api/property-valuations?${params.toString()}`);
}

export function refreshPropertyValuation(payload: {
  household_id: string;
  planning_goal_id: string;
  property_data: ScenarioData;
  market_snapshot_id: string;
  market_snapshot: MarketSnapshotData;
  force?: boolean;
}) {
  return request<PropertyValuationRefreshResponse>("/api/property-valuations/refresh", {
    method: "POST",
    body: JSON.stringify({ ...payload, force: payload.force ?? false })
  });
}

export function fetchPersonalPensionReturnSnapshots() {
  return request<PersonalPensionReturnSnapshotRecord[]>("/api/personal-pension-returns");
}

export function refreshPersonalPensionReturns(force = false) {
  return request<PersonalPensionReturnRefreshResponse>("/api/personal-pension-returns/refresh", {
    method: "POST",
    body: JSON.stringify({ force, sources: [] })
  });
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

function generatedStrategyRequestKey(payload: GeneratedStrategyBatchRequest) {
  const cacheLayers = [...payload.cache_layers].sort((left, right) => (
    `${left.engine}:${left.input}:${left.strategy}:${left.ledger}:${left.visualization}`
      .localeCompare(`${right.engine}:${right.input}:${right.strategy}:${right.ledger}:${right.visualization}`)
  ));
  return JSON.stringify({ ...payload, cache_layers: cacheLayers });
}

export function peekCompletedGeneratedStrategies(payload: GeneratedStrategyBatchRequest) {
  const key = generatedStrategyRequestKey(payload);
  const completed = completedGeneratedStrategyResults.get(key);
  if (!completed) return null;
  completedGeneratedStrategyResults.delete(key);
  completedGeneratedStrategyResults.set(key, completed);
  return completed;
}

export function fetchGeneratedStrategiesByCacheLayers(payload: GeneratedStrategyBatchRequest) {
  const key = generatedStrategyRequestKey(payload);
  const completed = completedGeneratedStrategyResults.get(key);
  if (completed) {
    completedGeneratedStrategyResults.delete(key);
    completedGeneratedStrategyResults.set(key, completed);
    return Promise.resolve(completed);
  }
  const inFlight = inFlightGeneratedStrategyRequests.get(key);
  if (inFlight) return inFlight;
  const promise = request<GeneratedStrategyRecord[]>("/api/generated-strategies/by-cache-layers", {
    method: "POST",
    body: JSON.stringify(payload)
  }).then((result) => rememberGeneratedStrategyResult(key, result)).finally(() => {
    inFlightGeneratedStrategyRequests.delete(key);
  });
  inFlightGeneratedStrategyRequests.set(key, promise);
  return promise;
}

function affordabilityRequestBody(
  householdId: string,
  scenarioId: string,
  household: HouseholdData,
  scenario: ScenarioData,
  rulePack: RulePackData,
  marketSnapshot?: MarketSnapshotData | null,
  includeStressTests = false
) {
  const vehiclePlans = household.car_plan.vehicle_plans ?? [];
  const primaryVehicleSelection = vehiclePlans.find((vehicle) => vehicle.enabled !== false)?.selected_strategy_variant
    ?? vehiclePlans[0]?.selected_strategy_variant;
  const normalizedHousehold = primaryVehicleSelection && household.car_plan.selected_strategy_variant !== primaryVehicleSelection
    ? {
        ...household,
        car_plan: {
          ...household.car_plan,
          selected_strategy_variant: primaryVehicleSelection
        }
      }
    : household;
  return JSON.stringify({
    household_id: householdId,
    scenario_id: scenarioId,
    household: normalizedHousehold,
    scenario,
    rule_pack: rulePack,
    market_snapshot: marketSnapshot ?? null,
    include_stress_tests: includeStressTests
  });
}

export function peekCompletedAffordabilityResult(
  householdId: string,
  scenarioId: string,
  household: HouseholdData,
  scenario: ScenarioData,
  rulePack: RulePackData,
  marketSnapshot?: MarketSnapshotData | null,
  includeStressTests = false
) {
  const key = affordabilityRequestBody(
    householdId,
    scenarioId,
    household,
    scenario,
    rulePack,
    marketSnapshot,
    includeStressTests
  );
  const completed = completedCalculationResults.get(key);
  if (!completed) return null;
  completedCalculationResults.delete(key);
  completedCalculationResults.set(key, completed);
  return completed;
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
  const body = affordabilityRequestBody(
    householdId,
    scenarioId,
    household,
    scenario,
    rulePack,
    marketSnapshot,
    includeStressTests
  );
  const completed = completedCalculationResults.get(body);
  if (completed) {
    completedCalculationResults.delete(body);
    completedCalculationResults.set(body, completed);
    return Promise.resolve(completed);
  }
  const cached = inFlightCalculationRequests.get(body);
  if (cached) return cached;
  const promise = request<AffordabilityResult>("/api/calculations/affordability", {
    method: "POST",
    body
  }).then(assertCompleteAffordabilityResult).then((result) => rememberCalculationResult(body, result)).finally(() => {
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
