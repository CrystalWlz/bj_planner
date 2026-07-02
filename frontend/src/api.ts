import type {
  AffordabilityResult,
  HouseholdData,
  RecordEnvelope,
  RulePackData,
  ScenarioData,
  SourceDocumentRecord
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

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

export function loadInitialData() {
  return Promise.all([
    request<RecordEnvelope<HouseholdData>[]>("/api/households"),
    request<RecordEnvelope<ScenarioData>[]>("/api/scenarios"),
    request<RecordEnvelope<RulePackData>[]>("/api/rule-packs")
  ]);
}

export function calculateAffordability(
  household: HouseholdData,
  scenario: ScenarioData,
  rulePack: RulePackData
) {
  return request<AffordabilityResult>("/api/calculations/affordability", {
    method: "POST",
    body: JSON.stringify({
      household,
      scenario,
      rule_pack: rulePack
    })
  });
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

export function createScenario(scenario: ScenarioData) {
  return request<RecordEnvelope<ScenarioData>>("/api/scenarios", {
    method: "POST",
    body: JSON.stringify({ data: scenario })
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

