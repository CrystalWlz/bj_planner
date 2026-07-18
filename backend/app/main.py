from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
import json

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from .cache import affordability_cache_key, calculation_code_fingerprints
from .calculator import calculate_affordability
from .database import (
    delete_record,
    bump_quant_investment_data_version,
    delete_quant_scoped_record,
    delete_planning_goal_record,
    delete_scenario_record,
    generated_strategies_exist_for_cache,
    get_calculation_cache_payload,
    initialize_database,
    insert_household_record,
    insert_planning_goal_record,
    insert_record,
    insert_paper_investment_order,
    insert_quant_scoped_record,
    insert_scenario_record,
    list_core_object_records,
    list_generated_strategies,
    list_generated_strategies_for_cache_layers,
    list_household_records,
    list_property_valuations,
    list_personal_pension_return_snapshots,
    list_records,
    list_investment_market_snapshots,
    list_paper_investment_orders,
    list_quant_scoped_records,
    list_scenario_records,
    normalize_household_data,
    normalize_market_snapshot_data,
    normalize_planning_goal_data,
    normalize_rule_pack_data,
    normalize_scenario_data,
    upsert_investment_market_snapshot,
    latest_property_valuation,
    latest_personal_pension_return_snapshot,
    update_household_record,
    update_planning_goal_record,
    upsert_calculation_cache,
    upsert_generated_strategies,
    upsert_property_valuation,
    upsert_personal_pension_return_snapshot,
    update_record,
    update_paper_investment_order,
    update_quant_scoped_record,
    update_scenario_record,
)
from .domain.property_valuation import estimate_property_value
from .domain.personal_pension_returns import refresh_personal_pension_return_snapshot
from .domain.quant_investment import run_monthly_backtest
from .market_data import MarketDataConfigurationError, fetch_tushare_snapshot
from .broker_adapters import PaperBrokerAdapter
from .strategies.quant_investment import build_quant_monthly_proposal
from .planning_context import (
    apply_planning_goal_constraints,
    core_object_snapshot_from_record,
    payload_with_calculation_context,
    planning_foundation_for_request,
    planning_goal_records_for_request,
    planning_goal_sequence_for_request,
)
from .profiling import calculation_profile, profile_span
from .reporting import build_account_concepts_from_core_object_snapshots, build_core_object_group_summaries
from .schemas import (
    AffordabilityRequest,
    AffordabilityResult,
    AccountConceptSummary,
    CacheLayerHashes,
    CalculationContextSnapshot,
    CoreObjectGroupSummary,
    CoreObjectRecord,
    CoreObjectCategory,
    CoreObjectType,
    GeneratedStrategyBatchRequest,
    GeneratedStrategyType,
    HouseholdCreate,
    HouseholdData,
    HouseholdRecord,
    MarketSnapshotCreate,
    MarketSnapshotData,
    MarketSnapshotRecord,
    PropertyValuationRecord,
    PropertyValuationRefreshRequest,
    PropertyValuationRefreshResponse,
    PersonalPensionReturnRefreshRequest,
    PersonalPensionReturnRefreshResponse,
    PersonalPensionReturnSnapshotData,
    PersonalPensionReturnSnapshotRecord,
    PlanningGoalCreate,
    PlanningGoalData,
    PlanningFoundationSummary,
    PlanningGoalRecord,
    PlanningGoalType,
    PlanningSequenceResult,
    RulePackCreate,
    RulePackData,
    RulePackRecord,
    ScenarioCreate,
    ScenarioData,
    ScenarioRecord,
    SourceDocumentRecord,
    SourceFetchRequest,
    InvestmentInstrumentCreate,
    InvestmentInstrumentRecord,
    InvestmentMarketSnapshotCreate,
    InvestmentMarketSnapshotData,
    InvestmentMarketSnapshotRecord,
    PaperOrderCreate,
    PaperOrderRecord,
    PaperOrderSimulateRequest,
    QuantBacktestRequest,
    QuantBacktestResult,
    QuantInvestmentPolicyCreate,
    QuantInvestmentPolicyRecord,
    QuantInvestmentProposalRecord,
    QuantInvestmentProposalRequest,
    QuantMarketRefreshRequest,
    QuantMarketRefreshResponse,
)
from .source_monitor import fetch_preview
from .policies import with_personal_pension_return_snapshot


def _with_latest_personal_pension_returns(payload: AffordabilityRequest) -> AffordabilityRequest:
    latest = latest_personal_pension_return_snapshot()
    if latest is None:
        return payload
    data = PersonalPensionReturnSnapshotData.model_validate(latest["data"])
    return payload.model_copy(
        update={
            "rule_pack": with_personal_pension_return_snapshot(
                payload.rule_pack,
                pre_retirement_annual_return=data.pre_retirement_annual_return,
                post_retirement_annual_return=data.post_retirement_annual_return,
                snapshot_date=data.snapshot_date,
                source_count=data.parsed_source_count,
            )
        }
    )


def _load_current_cached_affordability_payload(payload: str) -> dict | None:
    try:
        result = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(result, dict):
        return None
    monthly_rows = result.get("monthly_cashflow_visualization")
    monthly_details = result.get("monthly_visualization_details")
    if isinstance(monthly_rows, list) and monthly_rows and not monthly_details:
        return None
    if isinstance(monthly_rows, list) and isinstance(monthly_details, list) and monthly_rows:
        has_cashflow_activity = any(
            isinstance(row, dict)
            and (
                abs(float(row.get("cash_income") or 0)) > 0
                or abs(float(row.get("living_expense") or 0)) > 0
                or abs(float(row.get("monthly_cash_delta") or 0)) > 0
                or bool(row.get("ledger_entries"))
            )
            for row in monthly_rows
        )
        has_cashflow_detail_items = any(
            isinstance(detail, dict) and bool(detail.get("cash_flow_items"))
            for detail in monthly_details
        )
        if has_cashflow_activity and not has_cashflow_detail_items:
            return None
    return result


def _upgrade_cached_affordability_payload(
    result: dict,
    cache_layers: CacheLayerHashes,
    calculation_context: CalculationContextSnapshot | None,
) -> tuple[dict, bool]:
    changed = False
    next_cache_layers = cache_layers.model_dump(mode="json")
    next_calculation_context = calculation_context.model_dump(mode="json") if calculation_context else None
    if result.get("cache_layers") != next_cache_layers:
        result["cache_layers"] = next_cache_layers
        changed = True
    if result.get("calculation_context") != next_calculation_context:
        result["calculation_context"] = next_calculation_context
        changed = True
    return result, changed


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


@app.get("/api/core-objects", response_model=list[CoreObjectRecord])
def get_core_objects(
    household_id: str | None = None,
    object_type: CoreObjectType | None = None,
    category: CoreObjectCategory | None = None,
    owner_key: str | None = None,
) -> list[dict]:
    return list_core_object_records(
        household_id=household_id,
        object_type=object_type,
        category=category,
        owner_key=owner_key,
    )


@app.get("/api/account-concepts", response_model=list[AccountConceptSummary])
def get_account_concepts(household_id: str | None = None) -> list[AccountConceptSummary]:
    records = list_core_object_records(household_id=household_id)
    snapshots = [core_object_snapshot_from_record(record) for record in records]
    return build_account_concepts_from_core_object_snapshots(snapshots)


@app.get("/api/core-object-groups", response_model=list[CoreObjectGroupSummary])
def get_core_object_groups(household_id: str | None = None) -> list[CoreObjectGroupSummary]:
    records = list_core_object_records(household_id=household_id)
    snapshots = [core_object_snapshot_from_record(record) for record in records]
    account_concepts = build_account_concepts_from_core_object_snapshots(snapshots)
    return build_core_object_group_summaries(account_concepts)


@app.get("/api/planning-foundation", response_model=PlanningFoundationSummary)
def get_planning_foundation(household_id: str | None = None) -> PlanningFoundationSummary:
    return planning_foundation_for_request(household_id=household_id)


@app.get("/api/scenarios", response_model=list[ScenarioRecord])
def get_scenarios(household_id: str | None = None) -> list[dict]:
    return list_scenario_records(household_id=household_id)


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
def get_planning_goals(household_id: str | None = None, goal_type: PlanningGoalType | None = None) -> list[dict]:
    return planning_goal_records_for_request(household_id=household_id, goal_type=goal_type)


@app.get("/api/planning-goals/sequence", response_model=PlanningSequenceResult)
def get_planning_goal_sequence(household_id: str | None = None, goal_type: PlanningGoalType | None = None) -> PlanningSequenceResult:
    return planning_goal_sequence_for_request(household_id=household_id, goal_type=goal_type)


@app.post("/api/planning-goals", response_model=PlanningGoalRecord)
def create_planning_goal(payload: PlanningGoalCreate) -> dict:
    return insert_planning_goal_record(normalize_planning_goal_data(payload.data.model_dump(mode="json")), payload.household_id)


@app.put("/api/planning-goals/{record_id}", response_model=PlanningGoalRecord)
def save_planning_goal(record_id: str, payload: PlanningGoalCreate) -> dict:
    record = update_planning_goal_record(
        record_id,
        normalize_planning_goal_data(payload.data.model_dump(mode="json")),
        payload.household_id,
        preserve_household_when_omitted="household_id" not in payload.model_fields_set,
    )
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


def _quant_household_data(household_id: str) -> HouseholdData:
    record = next((item for item in list_household_records() if item["id"] == household_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到家庭记录")
    return HouseholdData.model_validate(record["data"])


def _quant_policy_record(household_id: str, policy_id: str) -> dict:
    record = next(
        (item for item in list_quant_scoped_records("quant_investment_policies", household_id=household_id) if item["id"] == policy_id),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到量化定投策略")
    return record


@app.get("/api/quant-investment/policies", response_model=list[QuantInvestmentPolicyRecord])
def get_quant_investment_policies(household_id: str) -> list[dict]:
    return list_quant_scoped_records("quant_investment_policies", household_id=household_id)


@app.post("/api/quant-investment/policies", response_model=QuantInvestmentPolicyRecord)
def create_quant_investment_policy(payload: QuantInvestmentPolicyCreate) -> dict:
    _quant_household_data(payload.household_id)
    record = insert_quant_scoped_record(
        "quant_investment_policies",
        household_id=payload.household_id,
        data=payload.data.model_dump(mode="json"),
    )
    bump_quant_investment_data_version(payload.household_id)
    return record


@app.put("/api/quant-investment/policies/{record_id}", response_model=QuantInvestmentPolicyRecord)
def save_quant_investment_policy(record_id: str, payload: QuantInvestmentPolicyCreate) -> dict:
    record = update_quant_scoped_record(
        "quant_investment_policies",
        record_id,
        household_id=payload.household_id,
        data=payload.data.model_dump(mode="json"),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到量化定投策略")
    bump_quant_investment_data_version(payload.household_id)
    return record


@app.delete("/api/quant-investment/policies/{record_id}")
def remove_quant_investment_policy(record_id: str, household_id: str) -> dict[str, bool]:
    if not delete_quant_scoped_record("quant_investment_policies", record_id, household_id=household_id):
        raise HTTPException(status_code=404, detail="未找到量化定投策略")
    bump_quant_investment_data_version(household_id)
    return {"deleted": True}


@app.get("/api/quant-investment/instruments", response_model=list[InvestmentInstrumentRecord])
def get_quant_investment_instruments(household_id: str) -> list[dict]:
    return list_quant_scoped_records("investment_instruments", household_id=household_id)


@app.post("/api/quant-investment/instruments", response_model=InvestmentInstrumentRecord)
def create_quant_investment_instrument(payload: InvestmentInstrumentCreate) -> dict:
    _quant_household_data(payload.household_id)
    record = insert_quant_scoped_record(
        "investment_instruments",
        household_id=payload.household_id,
        data=payload.data.model_dump(mode="json"),
    )
    bump_quant_investment_data_version(payload.household_id)
    return record


@app.put("/api/quant-investment/instruments/{record_id}", response_model=InvestmentInstrumentRecord)
def save_quant_investment_instrument(record_id: str, payload: InvestmentInstrumentCreate) -> dict:
    record = update_quant_scoped_record(
        "investment_instruments",
        record_id,
        household_id=payload.household_id,
        data=payload.data.model_dump(mode="json"),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到量化投资标的")
    bump_quant_investment_data_version(payload.household_id)
    return record


@app.delete("/api/quant-investment/instruments/{record_id}")
def remove_quant_investment_instrument(record_id: str, household_id: str) -> dict[str, bool]:
    if not delete_quant_scoped_record("investment_instruments", record_id, household_id=household_id):
        raise HTTPException(status_code=404, detail="未找到量化投资标的")
    bump_quant_investment_data_version(household_id)
    return {"deleted": True}


@app.get("/api/quant-investment/market-snapshots", response_model=list[InvestmentMarketSnapshotRecord])
def get_quant_market_snapshots(household_id: str) -> list[dict]:
    instruments = list_quant_scoped_records("investment_instruments", household_id=household_id)
    return list_investment_market_snapshots(instrument_ids=[item["id"] for item in instruments])


@app.post("/api/quant-investment/market-snapshots", response_model=InvestmentMarketSnapshotRecord)
def create_quant_market_snapshot(payload: InvestmentMarketSnapshotCreate) -> dict:
    instrument_exists = any(
        item["id"] == payload.instrument_id
        for item in list_quant_scoped_records("investment_instruments", household_id=payload.household_id)
    )
    if not instrument_exists:
        raise HTTPException(status_code=404, detail="未找到该家庭的投资标的")
    record = upsert_investment_market_snapshot(
        instrument_id=payload.instrument_id,
        snapshot_date=payload.data.snapshot_date,
        source=payload.data.source,
        data=payload.data.model_dump(mode="json"),
    )
    bump_quant_investment_data_version(payload.household_id)
    return record


@app.post("/api/quant-investment/market-data/refresh", response_model=QuantMarketRefreshResponse)
def refresh_quant_market_data(payload: QuantMarketRefreshRequest) -> dict:
    instruments = list_quant_scoped_records("investment_instruments", household_id=payload.household_id)
    records: list[dict] = []
    warnings: list[str] = []
    for instrument_record in instruments:
        instrument = InvestmentInstrumentRecord.model_validate(instrument_record)
        if not instrument.data.enabled:
            continue
        try:
            snapshot = fetch_tushare_snapshot(instrument.data, start_date=payload.start_date)
            records.append(
                upsert_investment_market_snapshot(
                    instrument_id=instrument.id,
                    snapshot_date=snapshot.snapshot_date,
                    source=snapshot.source,
                    data=snapshot.model_dump(mode="json"),
                )
            )
        except MarketDataConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # external provider failures must not erase prior snapshots
            warnings.append(f"{instrument.data.name}：{exc}")
    if records:
        bump_quant_investment_data_version(payload.household_id)
    return {"records": records, "warnings": warnings}


def _quant_snapshot_map(household_id: str) -> tuple[list[tuple[str, object]], dict[str, tuple[str, InvestmentMarketSnapshotData]]]:
    instruments = list_quant_scoped_records("investment_instruments", household_id=household_id)
    snapshots = list_investment_market_snapshots(instrument_ids=[item["id"] for item in instruments])
    parsed_instruments = [
        (item["id"], InvestmentInstrumentRecord.model_validate(item).data)
        for item in instruments
    ]
    parsed_snapshots = {
        item["instrument_id"]: (item["id"], InvestmentMarketSnapshotRecord.model_validate(item).data)
        for item in snapshots
    }
    return parsed_instruments, parsed_snapshots


@app.get("/api/quant-investment/proposals", response_model=list[QuantInvestmentProposalRecord])
def get_quant_investment_proposals(household_id: str) -> list[dict]:
    return list_quant_scoped_records("quant_investment_proposals", household_id=household_id)


@app.post("/api/quant-investment/proposals", response_model=QuantInvestmentProposalRecord)
def create_quant_investment_proposal(payload: QuantInvestmentProposalRequest) -> dict:
    household = _quant_household_data(payload.household_id)
    policy_record = _quant_policy_record(payload.household_id, payload.policy_id)
    policy = QuantInvestmentPolicyRecord.model_validate(policy_record)
    instruments, snapshots = _quant_snapshot_map(payload.household_id)
    result = build_quant_monthly_proposal(
        household=household,
        policy_id=policy.id,
        policy=policy.data,
        instruments=instruments,
        snapshots=snapshots,
    )
    proposal_record = insert_quant_scoped_record(
        "quant_investment_proposals",
        household_id=payload.household_id,
        data=result.proposal.model_dump(mode="json"),
    )
    for order in result.orders:
        order_data = order.model_copy(update={"proposal_id": proposal_record["id"]})
        insert_paper_investment_order(
            household_id=payload.household_id,
            proposal_id=proposal_record["id"],
            instrument_id=order_data.instrument_id,
            data=order_data.model_dump(mode="json"),
        )
    return proposal_record


@app.post("/api/quant-investment/backtests", response_model=QuantBacktestResult)
def run_quant_investment_backtest(payload: QuantBacktestRequest) -> QuantBacktestResult:
    policy_record = _quant_policy_record(payload.household_id, payload.policy_id)
    policy = QuantInvestmentPolicyRecord.model_validate(policy_record)
    instruments, snapshots = _quant_snapshot_map(payload.household_id)
    equity_snapshots = [
        snapshot
        for instrument_id, (_snapshot_id, snapshot) in snapshots.items()
        if any(item_id == instrument_id and item.asset_class == "equity" for item_id, item in instruments)
    ]
    try:
        result = run_monthly_backtest(policy.data, equity_snapshots, monthly_contribution=payload.monthly_contribution)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.model_copy(update={"policy_id": policy.id})


@app.get("/api/quant-investment/paper-orders", response_model=list[PaperOrderRecord])
def get_quant_paper_orders(household_id: str) -> list[dict]:
    return list_paper_investment_orders(household_id=household_id)


@app.post("/api/quant-investment/paper-orders", response_model=PaperOrderRecord)
def create_quant_paper_order(payload: PaperOrderCreate) -> dict:
    return insert_paper_investment_order(
        household_id=payload.household_id,
        proposal_id=payload.data.proposal_id,
        instrument_id=payload.data.instrument_id,
        data=payload.data.model_dump(mode="json"),
    )


@app.post("/api/quant-investment/paper-orders/{record_id}/simulate", response_model=PaperOrderRecord)
def simulate_quant_paper_order(record_id: str, payload: PaperOrderSimulateRequest) -> dict:
    existing = next((item for item in list_paper_investment_orders(household_id=payload.household_id) if item["id"] == record_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="未找到模拟订单")
    order = PaperOrderRecord.model_validate(existing)
    if order.data.status == "simulated":
        return existing
    try:
        simulated = PaperBrokerAdapter().simulate(
            order.data,
            executed_date=payload.executed_date,
            executed_price=payload.executed_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record = update_paper_investment_order(
        record_id,
        household_id=payload.household_id,
        data=simulated.model_dump(mode="json"),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到模拟订单")
    return record


@app.get("/api/market-snapshots", response_model=list[MarketSnapshotRecord])
def get_market_snapshots() -> list[dict]:
    return list_records("market_snapshots")


@app.post("/api/market-snapshots", response_model=MarketSnapshotRecord)
def create_market_snapshot(payload: MarketSnapshotCreate) -> dict:
    return insert_record("market_snapshots", normalize_market_snapshot_data(payload.data.model_dump(mode="json")))


@app.get("/api/property-valuations", response_model=list[PropertyValuationRecord])
def get_property_valuations(
    household_id: str,
    planning_goal_id: str | None = None,
) -> list[dict]:
    return list_property_valuations(
        household_id=household_id,
        planning_goal_id=planning_goal_id,
    )


@app.post("/api/property-valuations/refresh", response_model=PropertyValuationRefreshResponse)
def refresh_property_valuation(payload: PropertyValuationRefreshRequest) -> dict:
    latest = latest_property_valuation(
        household_id=payload.household_id,
        planning_goal_id=payload.planning_goal_id,
    )
    today = date.today()
    if latest is not None and not payload.force:
        next_due = str(latest.get("data", {}).get("next_due_date") or "")
        if next_due and next_due > today.isoformat():
            return {"record": latest, "refreshed": False}

    valuation = estimate_property_value(
        payload.property_data,
        payload.market_snapshot,
        valuation_date=today,
    )
    record = upsert_property_valuation(
        household_id=payload.household_id,
        planning_goal_id=payload.planning_goal_id,
        valuation_date=valuation.valuation_date,
        market_snapshot_id=payload.market_snapshot_id,
        data=valuation.model_dump(mode="json"),
    )
    return {"record": record, "refreshed": True}


@app.get("/api/personal-pension-returns", response_model=list[PersonalPensionReturnSnapshotRecord])
def get_personal_pension_return_snapshots() -> list[dict]:
    return list_personal_pension_return_snapshots()


@app.post("/api/personal-pension-returns/refresh", response_model=PersonalPensionReturnRefreshResponse)
async def refresh_personal_pension_returns(payload: PersonalPensionReturnRefreshRequest) -> dict:
    latest = latest_personal_pension_return_snapshot()
    today = date.today()
    if latest is not None and not payload.force:
        next_due = str(latest.get("data", {}).get("next_due_date") or "")
        if next_due and next_due > today.isoformat():
            return {"record": latest, "refreshed": False}
    previous = (
        PersonalPensionReturnSnapshotData.model_validate(latest["data"])
        if latest is not None
        else None
    )
    snapshot = await refresh_personal_pension_return_snapshot(
        payload.sources,
        today=today,
        previous=previous,
    )
    record = upsert_personal_pension_return_snapshot(
        snapshot_date=snapshot.snapshot_date,
        data=snapshot.model_dump(mode="json"),
    )
    return {"record": record, "refreshed": True}


@app.post("/api/calculations/affordability", response_model=AffordabilityResult)
def calculate(payload: AffordabilityRequest) -> AffordabilityResult:
    with calculation_profile("affordability_api"):
        with profile_span("calculation_context"):
            cache_payload = payload_with_calculation_context(_with_latest_personal_pension_returns(payload))
        with profile_span("cache_key"):
            cache_key, engine_fingerprint, cache_layers = affordability_cache_key(cache_payload)
        with profile_span("cache_lookup"):
            cached_payload = get_calculation_cache_payload(cache_key)
        if cached_payload is not None:
            with profile_span("cache_hit_load"):
                cached_result = _load_current_cached_affordability_payload(cached_payload)
        else:
            cached_result = None
        if cached_result is not None:
            with profile_span("cache_hit_upgrade"):
                upgrade_result = _upgrade_cached_affordability_payload(
                    cached_result,
                    cache_layers,
                    cache_payload.calculation_context,
                )
            upgraded_payload, cache_payload_changed = upgrade_result
            with profile_span("cache_hit_strategy_check"):
                strategies_exist = generated_strategies_exist_for_cache(cache_key)
            if cache_payload_changed:
                with profile_span("cache_hit_cache_writeback"):
                    upsert_calculation_cache(cache_key, engine_fingerprint, cache_layers, upgraded_payload)
            if not strategies_exist:
                with profile_span("cache_hit_strategy_writeback"):
                    upsert_generated_strategies(cache_key, engine_fingerprint, cache_layers, upgraded_payload)
            return AffordabilityResult.model_validate(upgraded_payload)

        with profile_span("planning_goal_constraints"):
            payload = apply_planning_goal_constraints(cache_payload)
        with profile_span("calculate_affordability"):
            result = calculate_affordability(
                payload.household,
                payload.scenario,
                payload.rule_pack,
                market_snapshot=payload.market_snapshot,
                include_stress_tests=payload.include_stress_tests,
                calculation_context=payload.calculation_context,
            )
        with profile_span("result_payload"):
            result = result.model_copy(update={"cache_layers": cache_layers})
            result_payload = result.model_dump(mode="json")
        with profile_span("calculation_cache_write"):
            upsert_calculation_cache(cache_key, engine_fingerprint, cache_layers, result_payload)
        with profile_span("generated_strategies_write"):
            upsert_generated_strategies(cache_key, engine_fingerprint, cache_layers, result_payload)
        return result


@app.get("/api/generated-strategies")
def get_generated_strategies(
    cache_key: str | None = None,
    strategy_type: GeneratedStrategyType | None = None,
    owner_key: str | None = None,
    current_only: bool = True,
    input_hash: str | None = None,
    strategy_hash: str | None = None,
    ledger_hash: str | None = None,
    visualization_hash: str | None = None,
) -> list[dict]:
    engine_fingerprint = calculation_code_fingerprints()["engine"] if current_only and cache_key is None else None
    return list_generated_strategies(
        cache_key=cache_key,
        strategy_type=strategy_type,
        owner_key=owner_key,
        engine_fingerprint=engine_fingerprint,
        input_hash=input_hash,
        strategy_hash=strategy_hash,
        ledger_hash=ledger_hash,
        visualization_hash=visualization_hash,
    )


@app.post("/api/generated-strategies/by-cache-layers")
def get_generated_strategies_by_cache_layers(payload: GeneratedStrategyBatchRequest) -> list[dict]:
    engine_fingerprint = calculation_code_fingerprints()["engine"] if payload.current_only else None
    return list_generated_strategies_for_cache_layers(
        payload.cache_layers,
        strategy_type=payload.strategy_type,
        owner_key=payload.owner_key,
        engine_fingerprint=engine_fingerprint,
    )


@app.post("/api/sources/fetch-preview", response_model=SourceDocumentRecord)
async def fetch_source_preview(payload: SourceFetchRequest) -> dict:
    try:
        return await fetch_preview(str(payload.url), payload.name)
    except httpx.HTTPError as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}") from exc


def _schema_refs() -> tuple[type[HouseholdData], type[ScenarioData], type[RulePackData], type[MarketSnapshotData], type[PlanningGoalData]]:
    return HouseholdData, ScenarioData, RulePackData, MarketSnapshotData, PlanningGoalData
