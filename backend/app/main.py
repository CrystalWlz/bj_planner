from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.gzip import GZipMiddleware

from .cache import affordability_cache_key
from .calculator import calculate_affordability
from .database import (
    delete_record,
    delete_planning_goal_record,
    delete_scenario_record,
    get_calculation_cache,
    get_calculation_cache_payload,
    initialize_database,
    insert_household_record,
    insert_planning_goal_record,
    insert_record,
    insert_scenario_record,
    list_generated_strategies,
    list_household_records,
    list_planning_goal_records,
    list_records,
    normalize_household_data,
    normalize_planning_goal_data,
    normalize_rule_pack_data,
    normalize_scenario_data,
    update_household_record,
    update_planning_goal_record,
    upsert_calculation_cache,
    upsert_generated_strategies,
    update_record,
    update_scenario_record,
    list_scenario_records,
)
from .schemas import (
    AffordabilityRequest,
    AffordabilityResult,
    HouseholdCreate,
    HouseholdData,
    HouseholdRecord,
    MarketSnapshotCreate,
    MarketSnapshotData,
    MarketSnapshotRecord,
    PlanningGoalCreate,
    PlanningGoalData,
    PlanningGoalRecord,
    RulePackCreate,
    RulePackData,
    RulePackRecord,
    ScenarioCreate,
    ScenarioData,
    ScenarioRecord,
    SourceDocumentRecord,
    SourceFetchRequest,
)
from .source_monitor import fetch_preview


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="北京买房可行性规划计算器", version="0.1.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=4096)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:5176",
        "http://localhost:5176",
        "http://127.0.0.1:5177",
        "http://localhost:5177",
        "http://127.0.0.1:5178",
        "http://localhost:5178",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/households", response_model=list[HouseholdRecord])
def get_households() -> list[dict]:
    return list_household_records()


@app.post("/api/households", response_model=HouseholdRecord)
def create_household(payload: HouseholdCreate) -> dict:
    return insert_household_record(normalize_household_data(payload.data.model_dump(mode="json")))


@app.put("/api/households/{record_id}", response_model=HouseholdRecord)
def save_household(record_id: str, payload: HouseholdCreate) -> dict:
    record = update_household_record(record_id, normalize_household_data(payload.data.model_dump(mode="json")))
    if record is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return record


@app.get("/api/scenarios", response_model=list[ScenarioRecord])
def get_scenarios() -> list[dict]:
    return list_scenario_records()


@app.post("/api/scenarios", response_model=ScenarioRecord)
def create_scenario(payload: ScenarioCreate) -> dict:
    return insert_scenario_record(normalize_scenario_data(payload.data.model_dump(mode="json")), payload.household_id)


@app.put("/api/scenarios/{record_id}", response_model=ScenarioRecord)
def save_scenario(record_id: str, payload: ScenarioCreate) -> dict:
    record = update_scenario_record(record_id, normalize_scenario_data(payload.data.model_dump(mode="json")))
    if record is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return record


@app.delete("/api/scenarios/{record_id}")
def delete_scenario(record_id: str) -> dict[str, bool]:
    deleted = delete_scenario_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"deleted": True}


@app.get("/api/planning-goals", response_model=list[PlanningGoalRecord])
def get_planning_goals(household_id: str | None = None, goal_type: str | None = None) -> list[dict]:
    return list_planning_goal_records(household_id=household_id, goal_type=goal_type)


@app.post("/api/planning-goals", response_model=PlanningGoalRecord)
def create_planning_goal(payload: PlanningGoalCreate) -> dict:
    return insert_planning_goal_record(normalize_planning_goal_data(payload.data.model_dump(mode="json")), payload.household_id)


@app.put("/api/planning-goals/{record_id}", response_model=PlanningGoalRecord)
def save_planning_goal(record_id: str, payload: PlanningGoalCreate) -> dict:
    record = update_planning_goal_record(record_id, normalize_planning_goal_data(payload.data.model_dump(mode="json")), payload.household_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Planning goal not found")
    return record


@app.delete("/api/planning-goals/{record_id}")
def delete_planning_goal(record_id: str) -> dict[str, bool]:
    deleted = delete_planning_goal_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Planning goal not found")
    return {"deleted": True}


@app.get("/api/rule-packs", response_model=list[RulePackRecord])
def get_rule_packs() -> list[dict]:
    return list_records("rule_packs")


@app.post("/api/rule-packs", response_model=RulePackRecord)
def create_rule_pack(payload: RulePackCreate) -> dict:
    return insert_record("rule_packs", normalize_rule_pack_data(payload.data.model_dump(mode="json")))


@app.put("/api/rule-packs/{record_id}", response_model=RulePackRecord)
def save_rule_pack(record_id: str, payload: RulePackCreate) -> dict:
    record = update_record("rule_packs", record_id, normalize_rule_pack_data(payload.data.model_dump(mode="json")))
    if record is None:
        raise HTTPException(status_code=404, detail="Rule pack not found")
    return record


@app.get("/api/market-snapshots", response_model=list[MarketSnapshotRecord])
def get_market_snapshots() -> list[dict]:
    return list_records("market_snapshots")


@app.post("/api/market-snapshots", response_model=MarketSnapshotRecord)
def create_market_snapshot(payload: MarketSnapshotCreate) -> dict:
    return insert_record("market_snapshots", payload.data.model_dump(mode="json"))


@app.post("/api/calculations/affordability", response_model=AffordabilityResult)
def calculate(payload: AffordabilityRequest) -> AffordabilityResult | Response:
    cache_key, engine_fingerprint, cache_layers = affordability_cache_key(payload)
    cached_payload = get_calculation_cache_payload(cache_key)
    if cached_payload is not None:
        return Response(content=cached_payload, media_type="application/json")

    result = calculate_affordability(
        payload.household,
        payload.scenario,
        payload.rule_pack,
        include_stress_tests=payload.include_stress_tests,
    )
    result = result.model_copy(update={"cache_layers": cache_layers})
    result_payload = result.model_dump(mode="json")
    upsert_calculation_cache(cache_key, engine_fingerprint, result_payload)
    upsert_generated_strategies(cache_key, engine_fingerprint, result_payload)
    return result


@app.get("/api/generated-strategies")
def get_generated_strategies(cache_key: str | None = None, strategy_type: str | None = None) -> list[dict]:
    return list_generated_strategies(cache_key=cache_key, strategy_type=strategy_type)


@app.post("/api/sources/fetch-preview", response_model=SourceDocumentRecord)
async def fetch_source_preview(payload: SourceFetchRequest) -> dict:
    try:
        return await fetch_preview(str(payload.url), payload.name)
    except httpx.HTTPError as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}") from exc


def _schema_refs() -> tuple[type[HouseholdData], type[ScenarioData], type[RulePackData], type[MarketSnapshotData], type[PlanningGoalData]]:
    return HouseholdData, ScenarioData, RulePackData, MarketSnapshotData, PlanningGoalData
