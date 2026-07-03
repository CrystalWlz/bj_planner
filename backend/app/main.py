from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .calculator import calculate_affordability
from .database import (
    delete_record,
    get_calculation_cache,
    initialize_database,
    insert_record,
    list_records,
    upsert_calculation_cache,
    update_record,
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


CALCULATION_ENGINE_FILES = ("calculator.py", "schemas.py", "policies.py")


@lru_cache(maxsize=1)
def calculation_engine_fingerprint() -> str:
    digest = hashlib.sha256()
    app_dir = Path(__file__).resolve().parent
    for file_name in CALCULATION_ENGINE_FILES:
        path = app_dir / file_name
        digest.update(file_name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def affordability_cache_key(payload: AffordabilityRequest) -> tuple[str, str]:
    engine_fingerprint = calculation_engine_fingerprint()
    request_payload = {
        "engine_fingerprint": engine_fingerprint,
        "household": payload.household.model_dump(mode="json"),
        "scenario": payload.scenario.model_dump(mode="json"),
        "rule_pack": payload.rule_pack.model_dump(mode="json"),
    }
    canonical = json.dumps(request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), engine_fingerprint


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="北京买房可行性规划计算器", version="0.1.0", lifespan=lifespan)

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
    return list_records("households")


@app.post("/api/households", response_model=HouseholdRecord)
def create_household(payload: HouseholdCreate) -> dict:
    return insert_record("households", payload.data.model_dump(mode="json"))


@app.put("/api/households/{record_id}", response_model=HouseholdRecord)
def save_household(record_id: str, payload: HouseholdCreate) -> dict:
    record = update_record("households", record_id, payload.data.model_dump(mode="json"))
    if record is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return record


@app.get("/api/scenarios", response_model=list[ScenarioRecord])
def get_scenarios() -> list[dict]:
    return list_records("scenarios")


@app.post("/api/scenarios", response_model=ScenarioRecord)
def create_scenario(payload: ScenarioCreate) -> dict:
    return insert_record(
        "scenarios",
        payload.data.model_dump(mode="json"),
        extra={"household_id": payload.household_id},
    )


@app.put("/api/scenarios/{record_id}", response_model=ScenarioRecord)
def save_scenario(record_id: str, payload: ScenarioCreate) -> dict:
    record = update_record("scenarios", record_id, payload.data.model_dump(mode="json"))
    if record is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return record


@app.delete("/api/scenarios/{record_id}")
def delete_scenario(record_id: str) -> dict[str, bool]:
    deleted = delete_record("scenarios", record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"deleted": True}


@app.get("/api/rule-packs", response_model=list[RulePackRecord])
def get_rule_packs() -> list[dict]:
    return list_records("rule_packs")


@app.post("/api/rule-packs", response_model=RulePackRecord)
def create_rule_pack(payload: RulePackCreate) -> dict:
    return insert_record("rule_packs", payload.data.model_dump(mode="json"))


@app.put("/api/rule-packs/{record_id}", response_model=RulePackRecord)
def save_rule_pack(record_id: str, payload: RulePackCreate) -> dict:
    record = update_record("rule_packs", record_id, payload.data.model_dump(mode="json"))
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
def calculate(payload: AffordabilityRequest) -> AffordabilityResult:
    cache_key, engine_fingerprint = affordability_cache_key(payload)
    cached = get_calculation_cache(cache_key)
    if cached is not None:
        return AffordabilityResult.model_validate(cached)

    result = calculate_affordability(payload.household, payload.scenario, payload.rule_pack)
    upsert_calculation_cache(cache_key, engine_fingerprint, result.model_dump(mode="json"))
    return result


@app.post("/api/sources/fetch-preview", response_model=SourceDocumentRecord)
async def fetch_source_preview(payload: SourceFetchRequest) -> dict:
    try:
        return await fetch_preview(str(payload.url), payload.name)
    except httpx.HTTPError as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}") from exc


def _schema_refs() -> tuple[type[HouseholdData], type[ScenarioData], type[RulePackData], type[MarketSnapshotData]]:
    return HouseholdData, ScenarioData, RulePackData, MarketSnapshotData
