from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from hashlib import sha256
import json

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from .cache import affordability_cache_key, calculation_code_fingerprints
from .calculator import calculate_affordability
from .database import (
    DuplicateClientOrderIdError,
    InvalidClientOrderIdError,
    delete_record,
    bump_quant_investment_data_version,
    broker_order_dispatch_retry_eligibility,
    claim_broker_order_dispatch,
    complete_broker_order_dispatch,
    confirm_paper_order_cancel,
    discard_pending_broker_order_dispatch,
    delete_quant_scoped_record,
    delete_planning_goal_record,
    delete_scenario_record,
    generated_strategies_exist_for_cache,
    get_quant_investment_data_version,
    get_calculation_cache_payload,
    initialize_database,
    insert_household_record,
    insert_broker_reconciliation_run,
    insert_planning_goal_record,
    insert_record,
    insert_paper_investment_order,
    insert_quant_scoped_record,
    insert_scenario_record,
    list_core_object_records,
    list_broker_reconciliation_runs,
    list_broker_order_dispatches,
    list_generated_strategies,
    list_generated_strategies_for_cache_layers,
    list_household_records,
    list_property_valuations,
    list_personal_pension_return_snapshots,
    list_records,
    list_investment_market_snapshots,
    list_paper_investment_fills,
    list_paper_investment_orders,
    list_paper_order_events,
    list_quant_backtest_runs,
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
    update_quant_scoped_record,
    update_scenario_record,
    record_paper_fill_atomic,
    paper_order_action_is_allowed,
    paper_order_is_persisted,
    prepare_broker_order_dispatch,
    request_paper_order_cancel,
    review_broker_order_dispatch_for_retry,
    resolve_broker_reconciliation_run,
    upsert_quant_backtest_run,
)
from .domain.property_valuation import estimate_property_value
from .domain.personal_pension_returns import refresh_personal_pension_return_snapshot
from .domain.paper_portfolio import build_paper_portfolio_summary, paper_fill_from_order
from .domain.quant_backtest import BacktestAsset, run_calendar_backtest
from .domain.quant_investment import (
    QUANT_BACKTEST_ENGINE_VERSION,
    execution_session_is_allowed,
    quant_backtest_fingerprint,
)
from .market_data import MarketDataConfigurationError, fetch_tushare_snapshot, trace_market_snapshot
from .broker_adapters import LocalFirstBrokerGateway, PaperBrokerAdapter
from .strategies.quant_investment import (
    EXECUTION_PLANNER_VERSION,
    PORTFOLIO_CONSTRUCTOR_VERSION,
    PRE_TRADE_RISK_VERSION,
    SIGNAL_MODEL_VERSION,
    build_quant_monthly_proposal,
    check_paper_buy_execution,
    paper_buy_reservations,
)
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
    BrokerReconciliationRequest,
    BrokerReconciliationReviewRequest,
    BrokerReconciliationRunData,
    BrokerReconciliationRunRecord,
    BrokerOrderDispatchData,
    BrokerOrderDispatchRecord,
    BrokerOrderDispatchRetryRequest,
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
    PaperOrderCancelRequest,
    PaperOrderData,
    PaperOrderEventRecord,
    PaperFillData,
    PaperFillRecord,
    PaperOrderRecord,
    PaperOrderSimulateRequest,
    PaperPortfolioSummary,
    QuantBacktestRequest,
    QuantBacktestResult,
    QuantBacktestRunData,
    QuantBacktestRunRecord,
    QuantExecutionAssumptionData,
    QuantInvestmentPolicyCreate,
    QuantInvestmentPolicyData,
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


def _attach_paper_portfolio(result: AffordabilityResult, household_id: str) -> AffordabilityResult:
    if not household_id:
        return result
    policy_records = list_quant_scoped_records("quant_investment_policies", household_id=household_id)
    policy = QuantInvestmentPolicyRecord.model_validate(policy_records[0]).data if policy_records else None
    return result.model_copy(update={"paper_portfolio": _paper_portfolio_for_household(household_id, policy)})


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
    snapshot = trace_market_snapshot(payload.data)
    record, inserted = upsert_investment_market_snapshot(
        instrument_id=payload.instrument_id,
        snapshot_date=snapshot.snapshot_date,
        source=snapshot.source,
        data=snapshot.model_dump(mode="json"),
    )
    if inserted:
        bump_quant_investment_data_version(payload.household_id)
    return record


@app.post("/api/quant-investment/market-data/refresh", response_model=QuantMarketRefreshResponse)
def refresh_quant_market_data(payload: QuantMarketRefreshRequest) -> dict:
    instruments = list_quant_scoped_records("investment_instruments", household_id=payload.household_id)
    records: list[dict] = []
    warnings: list[str] = []
    changed = False
    for instrument_record in instruments:
        instrument = InvestmentInstrumentRecord.model_validate(instrument_record)
        if not instrument.data.enabled:
            continue
        try:
            snapshot = fetch_tushare_snapshot(instrument.data, start_date=payload.start_date)
            record, inserted = upsert_investment_market_snapshot(
                instrument_id=instrument.id,
                snapshot_date=snapshot.snapshot_date,
                source=snapshot.source,
                data=snapshot.model_dump(mode="json"),
            )
            records.append(record)
            changed = changed or inserted
        except MarketDataConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # external provider failures must not erase prior snapshots
            warnings.append(f"{instrument.data.name}：{exc}")
    if changed:
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


def _insert_paper_order_or_conflict(
    *,
    household_id: str,
    proposal_id: str,
    instrument_id: str,
    data: dict,
) -> dict:
    try:
        return insert_paper_investment_order(
            household_id=household_id,
            proposal_id=proposal_id,
            instrument_id=instrument_id,
            data=data,
        )
    except DuplicateClientOrderIdError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidClientOrderIdError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/quant-investment/proposals", response_model=list[QuantInvestmentProposalRecord])
def get_quant_investment_proposals(household_id: str) -> list[dict]:
    return list_quant_scoped_records("quant_investment_proposals", household_id=household_id)


@app.post("/api/quant-investment/proposals", response_model=QuantInvestmentProposalRecord)
def create_quant_investment_proposal(payload: QuantInvestmentProposalRequest) -> dict:
    household = _quant_household_data(payload.household_id)
    policy_record = _quant_policy_record(payload.household_id, payload.policy_id)
    policy = QuantInvestmentPolicyRecord.model_validate(policy_record)
    instruments, snapshots = _quant_snapshot_map(payload.household_id)
    planning_sequence = planning_goal_sequence_for_request(payload.household_id)
    protected_by_group: dict[str, float] = {}
    for goal in planning_sequence.goals:
        if not goal.enabled or goal.resolved_window_start_month > 24:
            continue
        group_key = goal.planning_group_id or goal.id
        protected_by_group[group_key] = max(protected_by_group.get(group_key, 0.0), max(0.0, goal.target_amount))
    paper_portfolio = _paper_portfolio_for_household(payload.household_id, policy.data)
    result = build_quant_monthly_proposal(
        household=household,
        policy_id=policy.id,
        policy=policy.data,
        instruments=instruments,
        snapshots=snapshots,
        additional_goal_cash=sum(protected_by_group.values()),
        paper_portfolio=paper_portfolio,
    )
    proposal_data = result.proposal
    orders = result.orders
    if paper_portfolio.frozen:
        proposal_data = proposal_data.model_copy(
            update={
                "proposed_budget": 0.0,
                "risk_state": "frozen",
                "reasons": [*proposal_data.reasons, *paper_portfolio.warnings, "模拟账户事后风控异常，仅允许暂停新增，不执行自动补仓。"],
            }
        )
        orders = []
    proposal_record = insert_quant_scoped_record(
        "quant_investment_proposals",
        household_id=payload.household_id,
        data=proposal_data.model_dump(mode="json"),
    )
    for order in orders:
        order_data = order.model_copy(update={"proposal_id": proposal_record["id"]})
        _insert_paper_order_or_conflict(
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
    instrument_map = dict(instruments)
    asset_snapshot_entries = [
        (instrument_id, snapshot_id, snapshot)
        for instrument_id, (snapshot_id, snapshot) in snapshots.items()
        if instrument_map.get(instrument_id) and instrument_map[instrument_id].enabled
    ]
    assets = [
        BacktestAsset(instrument_id, instrument_map[instrument_id], snapshot)
        for instrument_id, _snapshot_id, snapshot in asset_snapshot_entries
    ]
    try:
        result = run_calendar_backtest(
            policy.data,
            assets,
            monthly_contribution=payload.monthly_contribution,
            walk_forward_train_months=payload.walk_forward_train_months,
            walk_forward_test_months=payload.walk_forward_test_months,
        ).model_copy(update={"policy_id": policy.id})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fingerprint = quant_backtest_fingerprint(
        policy.data,
        [(snapshot_id, snapshot) for _instrument_id, snapshot_id, snapshot in asset_snapshot_entries],
        monthly_contribution=payload.monthly_contribution,
        instruments=[(asset.instrument_id, asset.instrument) for asset in assets],
        extra_parameters={
            "walk_forward_train_months": payload.walk_forward_train_months,
            "walk_forward_test_months": payload.walk_forward_test_months,
        },
    )
    strategy_versions = {
        "signal_model": SIGNAL_MODEL_VERSION,
        "portfolio_constructor": PORTFOLIO_CONSTRUCTOR_VERSION,
        "pre_trade_risk_manager": PRE_TRADE_RISK_VERSION,
        "execution_planner": EXECUTION_PLANNER_VERSION,
    }
    universe_payload = [
        {"id": asset.instrument_id, "data": asset.instrument.model_dump(mode="json")}
        for asset in sorted(assets, key=lambda item: item.instrument_id)
    ]
    universe_version = sha256(json.dumps(universe_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    universe_snapshot = {
        asset.instrument_id: asset.instrument
        for asset in sorted(assets, key=lambda item: item.instrument_id)
    }
    execution_assumptions = {
        asset.instrument_id: QuantExecutionAssumptionData(
            instrument_id=asset.instrument_id,
            symbol=asset.instrument.symbol,
            market=asset.instrument.market,
            asset_class=asset.instrument.asset_class,
            currency=asset.instrument.currency,
            trading_mode=asset.instrument.trading_mode,
            lot_size=asset.instrument.lot_size,
            buy_fee_rate=asset.instrument.buy_fee_rate,
            sell_fee_rate=asset.instrument.sell_fee_rate,
            monthly_purchase_limit=asset.instrument.monthly_purchase_limit,
            qdii_premium_threshold=asset.instrument.qdii_premium_threshold,
            purchase_suspended=asset.instrument.purchase_suspended,
            hong_kong_connect_eligible=asset.instrument.hong_kong_connect_eligible,
        )
        for asset in sorted(assets, key=lambda item: item.instrument_id)
    }
    run_data = QuantBacktestRunData(
        engine_version=QUANT_BACKTEST_ENGINE_VERSION,
        policy_id=policy.id,
        snapshot_ids=[snapshot_id for _instrument_id, snapshot_id, _snapshot in asset_snapshot_entries],
        strategy_versions=strategy_versions,
        universe_version=universe_version,
        universe_snapshot=universe_snapshot,
        execution_assumptions=execution_assumptions,
        dataset_versions={snapshot_id: snapshot.data_version for _instrument_id, snapshot_id, snapshot in asset_snapshot_entries},
        data_fingerprint=fingerprint,
        monthly_contribution=payload.monthly_contribution,
        start_date=result.start_date,
        end_date=result.end_date,
        cost_assumptions={
            "slippage_rate": policy.data.slippage_rate,
            "maximum_buy_fee_rate": max((asset.instrument.buy_fee_rate for asset in assets), default=0.0),
            "maximum_sell_fee_rate": max((asset.instrument.sell_fee_rate for asset in assets), default=0.0),
        },
        parameters={
            "research_strategy": policy.data.research_strategy,
            "walk_forward_train_months": payload.walk_forward_train_months,
            "walk_forward_test_months": payload.walk_forward_test_months,
        },
        policy_snapshot=policy.data,
        result=result,
        warnings=result.warnings,
    )
    upsert_quant_backtest_run(
        household_id=payload.household_id,
        policy_id=policy.id,
        data_fingerprint=fingerprint,
        data=run_data.model_dump(mode="json"),
    )
    return result


@app.get("/api/quant-investment/backtest-runs", response_model=list[QuantBacktestRunRecord])
def get_quant_backtest_runs(household_id: str) -> list[dict]:
    return list_quant_backtest_runs(household_id=household_id)


def _paper_broker_gateway(
    *,
    household_id: str,
    adapter: PaperBrokerAdapter,
    expected_data_version: int | None = None,
) -> LocalFirstBrokerGateway:
    return LocalFirstBrokerGateway(
        adapter,
        is_order_persisted=lambda local_order_id, client_order_id: paper_order_is_persisted(
            local_order_id,
            household_id=household_id,
            client_order_id=client_order_id,
        ),
        is_order_action_allowed=lambda local_order_id, client_order_id, action: paper_order_action_is_allowed(
            local_order_id,
            household_id=household_id,
            client_order_id=client_order_id,
            action=action,
        ),
        claim_order_action=lambda local_order_id, client_order_id, action: claim_broker_order_dispatch(
            local_order_id,
            household_id=household_id,
            client_order_id=client_order_id,
            adapter="paper",
            action=action,
            expected_data_version=expected_data_version if action == "submit" else None,
        ),
        complete_order_action=(
            lambda local_order_id, client_order_id, action, status, response_data, error_message: complete_broker_order_dispatch(
                local_order_id,
                household_id=household_id,
                client_order_id=client_order_id,
                adapter="paper",
                action=action,
                status=status,
                response_data=response_data,
                error_message=error_message,
            )
        ),
    )


@app.get("/api/quant-investment/broker-order-dispatches", response_model=list[BrokerOrderDispatchRecord])
def get_quant_broker_order_dispatches(
    household_id: str,
    order_id: str | None = None,
) -> list[dict]:
    dispatches = list_broker_order_dispatches(household_id=household_id, order_id=order_id)
    reconciliations = list_broker_reconciliation_runs(household_id=household_id)
    result: list[dict] = []
    for dispatch in dispatches:
        retry_eligible, reconciliation_id, block_reason = broker_order_dispatch_retry_eligibility(
            dispatch,
            reconciliations,
        )
        result.append(
            {
                **dispatch,
                "retry_eligible": retry_eligible,
                "eligible_reconciliation_id": reconciliation_id,
                "retry_block_reason": block_reason,
            }
        )
    return result


@app.post(
    "/api/quant-investment/broker-order-dispatches/{record_id}/retry",
    response_model=BrokerOrderDispatchRecord,
)
def retry_quant_broker_order_dispatch(
    record_id: str,
    payload: BrokerOrderDispatchRetryRequest,
) -> dict:
    record, status = review_broker_order_dispatch_for_retry(
        record_id,
        household_id=payload.household_id,
        reconciliation_id=payload.reconciliation_id,
        review_note=payload.review_note,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到券商发送动作")
    error_messages = {
        "not_reviewable": "该券商发送动作不处于结果不确定状态",
        "dispatch_still_active": "券商动作仍可能处于发送中，请等待失联窗口结束后重新对账",
        "reconciliation_not_found": "未找到用于复核的对账记录",
        "reconciliation_adapter_mismatch": "对账记录与券商发送动作不属于同一适配器",
        "reconciliation_not_matched": "对账仍存在差异，不能重新发送订单",
        "reconciliation_too_old": "对账记录早于本次发送异常，请重新执行对账",
    }
    if status in error_messages:
        raise HTTPException(status_code=409, detail=error_messages[status])
    return record


@app.get("/api/quant-investment/broker-reconciliations", response_model=list[BrokerReconciliationRunRecord])
def get_quant_broker_reconciliations(household_id: str) -> list[dict]:
    return list_broker_reconciliation_runs(household_id=household_id)


@app.post("/api/quant-investment/broker-reconciliations/paper", response_model=BrokerReconciliationRunRecord)
def reconcile_quant_paper_broker(payload: BrokerReconciliationRequest) -> dict:
    local_orders = [
        PaperOrderRecord.model_validate(item).data
        for item in list_paper_investment_orders(household_id=payload.household_id)
    ]
    portfolio = _paper_portfolio_for_household(payload.household_id)
    adapter = PaperBrokerAdapter(
        orders=tuple(local_orders),
        positions=tuple(portfolio.positions),
        cash_balance=portfolio.cash_balance,
    )
    remote_orders = adapter.query_orders()
    remote_positions = adapter.query_positions()
    remote_cash = adapter.query_cash()
    result = adapter.reconcile(
        local_orders=local_orders,
        local_positions=portfolio.positions,
        local_cash=portfolio.cash_balance,
    )
    reconciliation_date = date.today().isoformat()
    data = BrokerReconciliationRunData(
        adapter="paper",
        reconciliation_date=reconciliation_date,
        matched=result.matched,
        freeze_new_orders=result.freeze_new_orders,
        review_status="not_required" if result.matched else "pending",
        local_state_hash=result.local_state_hash,
        remote_state_hash=result.remote_state_hash,
        local_order_count=len(local_orders),
        remote_order_count=len(remote_orders),
        local_position_count=len(portfolio.positions),
        remote_position_count=len(remote_positions),
        local_cash=portfolio.cash_balance,
        remote_cash=remote_cash,
        differences=result.differences,
    )
    record = insert_broker_reconciliation_run(
        household_id=payload.household_id,
        adapter=data.adapter,
        reconciliation_date=reconciliation_date,
        data=data.model_dump(mode="json"),
    )
    if result.freeze_new_orders:
        bump_quant_investment_data_version(payload.household_id)
    return record


@app.post(
    "/api/quant-investment/broker-reconciliations/{record_id}/review",
    response_model=BrokerReconciliationRunRecord,
)
def review_quant_broker_reconciliation(
    record_id: str,
    payload: BrokerReconciliationReviewRequest,
) -> dict:
    existing = next(
        (
            item
            for item in list_broker_reconciliation_runs(household_id=payload.household_id)
            if item["id"] == record_id
        ),
        None,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="未找到券商对账运行记录")
    existing_data = BrokerReconciliationRunRecord.model_validate(existing).data
    if existing_data.review_status != "pending":
        raise HTTPException(status_code=409, detail="该对账记录不处于待人工复核状态")
    record = resolve_broker_reconciliation_run(
        record_id,
        household_id=payload.household_id,
        review_note=payload.review_note,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到券商对账运行记录")
    bump_quant_investment_data_version(payload.household_id)
    return record


@app.get("/api/quant-investment/paper-orders", response_model=list[PaperOrderRecord])
def get_quant_paper_orders(household_id: str) -> list[dict]:
    return list_paper_investment_orders(household_id=household_id)


@app.get("/api/quant-investment/paper-fills", response_model=list[PaperFillRecord])
def get_quant_paper_fills(household_id: str) -> list[dict]:
    return list_paper_investment_fills(household_id=household_id)


@app.get("/api/quant-investment/paper-order-events", response_model=list[PaperOrderEventRecord])
def get_quant_paper_order_events(household_id: str, order_id: str | None = None) -> list[dict]:
    return list_paper_order_events(household_id=household_id, order_id=order_id)


@app.get("/api/quant-investment/paper-portfolio", response_model=PaperPortfolioSummary)
def get_quant_paper_portfolio(household_id: str) -> PaperPortfolioSummary:
    policy_records = list_quant_scoped_records("quant_investment_policies", household_id=household_id)
    policy = QuantInvestmentPolicyRecord.model_validate(policy_records[0]).data if policy_records else None
    return _paper_portfolio_for_household(household_id, policy)


def _paper_portfolio_for_household(
    household_id: str,
    policy: QuantInvestmentPolicyData | None = None,
    *,
    as_of_date: str | None = None,
) -> PaperPortfolioSummary:
    instrument_records = list_quant_scoped_records("investment_instruments", household_id=household_id)
    instruments = {
        item["id"]: InvestmentInstrumentRecord.model_validate(item).data
        for item in instrument_records
    }
    snapshot_records = list_investment_market_snapshots(instrument_ids=list(instruments))
    snapshots = {
        item["instrument_id"]: InvestmentMarketSnapshotRecord.model_validate(item).data
        for item in snapshot_records
    }
    fills = [
        PaperFillRecord.model_validate(item).data
        for item in list_paper_investment_fills(household_id=household_id)
    ]
    reconciliations = [
        (item["id"], BrokerReconciliationRunRecord.model_validate(item).data)
        for item in list_broker_reconciliation_runs(household_id=household_id)
    ]
    dispatches = [
        (item["id"], BrokerOrderDispatchRecord.model_validate(item).data)
        for item in list_broker_order_dispatches(household_id=household_id)
    ]
    return build_paper_portfolio_summary(
        household_id=household_id,
        fills=fills,
        instruments=instruments,
        snapshots=snapshots,
        policy=policy,
        reconciliations=reconciliations,
        broker_dispatches=dispatches,
        as_of_date=as_of_date,
    )


@app.post("/api/quant-investment/paper-orders", response_model=PaperOrderRecord)
def create_quant_paper_order(payload: PaperOrderCreate) -> dict:
    return _insert_paper_order_or_conflict(
        household_id=payload.household_id,
        proposal_id=payload.data.proposal_id,
        instrument_id=payload.data.instrument_id,
        data=payload.data.model_dump(mode="json"),
    )


@app.post("/api/quant-investment/paper-orders/{record_id}/cancel", response_model=PaperOrderRecord)
def cancel_quant_paper_order(record_id: str, payload: PaperOrderCancelRequest) -> dict:
    requested, request_status = request_paper_order_cancel(
        record_id,
        household_id=payload.household_id,
        reason=payload.reason,
    )
    if requested is None:
        raise HTTPException(status_code=404, detail="未找到模拟订单")
    if request_status == "not_cancellable":
        raise HTTPException(status_code=409, detail="订单已成交、已确认或已冻结，不能取消")
    if request_status == "already_cancelled":
        return requested
    requested_order = PaperOrderRecord.model_validate(requested)
    dispatch, dispatch_status = prepare_broker_order_dispatch(
        record_id,
        household_id=payload.household_id,
        client_order_id=requested_order.data.client_order_id,
        adapter="paper",
        action="cancel",
        request_data={"client_order_id": requested_order.data.client_order_id},
    )
    if dispatch is None:
        if dispatch_status == "action_not_allowed":
            raise HTTPException(status_code=409, detail="订单当前状态不允许发送取消动作")
        raise HTTPException(status_code=409, detail="模拟订单取消动作未能写入本地 outbox")
    if dispatch_status in {"dispatching", "uncertain"}:
        raise HTTPException(status_code=409, detail="取消结果尚未确定，请先核验模拟账户状态后再重试")
    if dispatch_status == "acknowledged":
        acknowledged = bool(dispatch["data"].get("response_data", {}).get("acknowledged"))
    else:
        adapter = PaperBrokerAdapter(orders=(requested_order.data,))
        gateway = _paper_broker_gateway(household_id=payload.household_id, adapter=adapter)
        try:
            acknowledged = gateway.cancel(
                local_order_id=record_id,
                client_order_id=requested_order.data.client_order_id,
            )
        except RuntimeError as exc:
            bump_quant_investment_data_version(payload.household_id)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not acknowledged:
        raise HTTPException(status_code=409, detail="适配器尚未确认取消，订单保持取消请求状态")
    cancelled, confirm_status = confirm_paper_order_cancel(
        record_id,
        household_id=payload.household_id,
        reason=payload.reason,
    )
    if cancelled is None:
        raise HTTPException(status_code=404, detail="未找到模拟订单")
    if confirm_status == "not_requested":
        raise HTTPException(status_code=409, detail="订单不处于取消请求状态")
    if confirm_status == "cancelled":
        bump_quant_investment_data_version(payload.household_id)
    return cancelled


def _validate_paper_fill_before_persist(
    *,
    household_id: str,
    order: PaperOrderData,
    fill: PaperFillData,
    policy: QuantInvestmentPolicyData | None,
    current_dispatch_id: str = "",
) -> int:
    validated_data_version = get_quant_investment_data_version(household_id)
    instrument_entries, market_snapshots = _quant_snapshot_map(household_id)
    instruments = dict(instrument_entries)
    instrument = instruments.get(order.instrument_id)
    market_snapshot_entry = market_snapshots.get(order.instrument_id)
    if market_snapshot_entry is not None:
        execution_allowed, execution_reason = execution_session_is_allowed(
            market_snapshot_entry[1],
            execution_date=fill.executed_date,
            side=fill.side,
        )
        if not execution_allowed:
            raise HTTPException(status_code=409, detail=execution_reason)
    fill_records = list_paper_investment_fills(household_id=household_id)
    persisted_fills = [PaperFillRecord.model_validate(item).data for item in fill_records]
    prior_fills = [item for item in persisted_fills if item.executed_date <= fill.executed_date]
    if order.side == "buy" and order.funding_source == "paper_cash":
        available_cash = sum(item.contribution_amount + item.cash_change for item in prior_fills)
        required_cash = max(0.0, -fill.cash_change)
        if required_cash > available_cash + 1e-6:
            raise HTTPException(status_code=409, detail="成交日模拟现金不足；请先成交更早的再平衡卖出订单或降低买入金额")
    if order.side == "sell":
        available_quantity = sum(
            item.executed_quantity if item.side == "buy" else -item.executed_quantity
            for item in prior_fills
            if item.instrument_id == order.instrument_id
        )
        if fill.executed_quantity > available_quantity + 1e-6:
            raise HTTPException(status_code=409, detail="成交日模拟卖出数量超过当前可用持仓")
    if order.side == "buy":
        if policy is None:
            raise HTTPException(status_code=409, detail="没有可用的量化投资政策，不能模拟新增买入")
        if instrument is None:
            raise HTTPException(status_code=409, detail="订单标的不在当前家庭手工标的池中，不能模拟新增买入")
        if market_snapshot_entry is None:
            raise HTTPException(status_code=409, detail="订单标的缺少可追溯行情数据集，不能模拟新增买入")
        portfolio_before = _paper_portfolio_for_household(
            household_id,
            policy,
            as_of_date=fill.executed_date,
        )
        month_key = fill.executed_date[:7]
        monthly_buy_amount_before = sum(
            item.gross_amount + item.fee
            for item in prior_fills
            if item.side == "buy"
            and item.instrument_id == order.instrument_id
            and item.executed_date[:7] == month_key
        )
        dispatches = list_broker_order_dispatches(household_id=household_id)
        reservations = paper_buy_reservations(
            dispatches=[
                (
                    str(item["id"]),
                    str(item["created_at"]),
                    BrokerOrderDispatchData.model_validate(item["data"]),
                )
                for item in dispatches
            ],
            instruments=instruments,
            filled_order_ids={str(item["order_id"]) for item in fill_records},
            as_of_date=fill.executed_date,
            current_dispatch_id=current_dispatch_id,
        )
        decision = check_paper_buy_execution(
            instrument_id=order.instrument_id,
            instrument=instrument,
            snapshot=market_snapshot_entry[1],
            fill=fill,
            policy=policy,
            portfolio_before=portfolio_before,
            monthly_buy_amount_before=monthly_buy_amount_before,
            reservations=reservations,
        )
        if not decision.allowed:
            raise HTTPException(status_code=409, detail=decision.reason)
    return validated_data_version


@app.post("/api/quant-investment/paper-orders/{record_id}/simulate", response_model=PaperOrderRecord)
def simulate_quant_paper_order(record_id: str, payload: PaperOrderSimulateRequest) -> dict:
    existing = next((item for item in list_paper_investment_orders(household_id=payload.household_id) if item["id"] == record_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="未找到模拟订单")
    order = PaperOrderRecord.model_validate(existing)
    if order.data.status not in {"proposed", "simulated"}:
        raise HTTPException(status_code=409, detail="当前订单状态不允许模拟成交")
    policy_records = list_quant_scoped_records("quant_investment_policies", household_id=payload.household_id)
    policy = QuantInvestmentPolicyRecord.model_validate(policy_records[0]).data if policy_records else None
    portfolio = _paper_portfolio_for_household(payload.household_id, policy)
    if order.data.status == "proposed" and order.data.side == "buy" and portfolio.frozen:
        raise HTTPException(status_code=409, detail="模拟账户事后风控已冻结新增买入；请先人工复核异常")
    fill_records = list_paper_investment_fills(household_id=payload.household_id)
    fill_existed = any(item["order_id"] == record_id for item in fill_records)
    dispatch: dict | None = None
    dispatch_status = ""
    adapter: PaperBrokerAdapter | None = None
    if order.data.status == "simulated":
        simulated = order.data
    else:
        requested_data = {
            "order": order.data.model_dump(mode="json"),
            "executed_date": payload.executed_date,
            "executed_price": payload.executed_price,
        }
        dispatch = next(
            (
                item
                for item in list_broker_order_dispatches(
                    household_id=payload.household_id,
                    order_id=record_id,
                )
                if item["adapter"] == "paper" and item["action"] == "submit"
            ),
            None,
        )
        if dispatch is None:
            preview_adapter = PaperBrokerAdapter(
                execution_date=payload.executed_date,
                execution_price=payload.executed_price,
            )
            try:
                preview_order = preview_adapter.simulate(
                    order.data,
                    executed_date=preview_adapter.execution_date,
                    executed_price=preview_adapter.execution_price,
                )
                preview_fill = paper_fill_from_order(record_id, preview_order)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            _validate_paper_fill_before_persist(
                household_id=payload.household_id,
                order=order.data,
                fill=preview_fill,
                policy=policy,
            )
            dispatch, dispatch_status = prepare_broker_order_dispatch(
                record_id,
                household_id=payload.household_id,
                client_order_id=order.data.client_order_id,
                adapter="paper",
                action="submit",
                request_data=requested_data,
            )
            if dispatch is None:
                if dispatch_status == "action_not_allowed":
                    raise HTTPException(status_code=409, detail="订单当前状态不允许发送模拟成交动作")
                raise HTTPException(status_code=409, detail="模拟成交动作未能写入本地 outbox")
        else:
            dispatch_status = str(dispatch["status"])
        if dispatch_status in {"dispatching", "uncertain"}:
            raise HTTPException(status_code=409, detail="模拟成交结果尚未确定，请先核验模拟账户状态后再重试")
        dispatch_data = BrokerOrderDispatchData.model_validate(dispatch["data"])
        request_data = dispatch_data.request_data
        if dispatch_status in {"pending", "retryable"} and request_data != requested_data:
            raise HTTPException(status_code=409, detail="该订单已有不同参数的待发送动作；请按原成交日期和价格重试")
        try:
            if dispatch_status == "acknowledged":
                simulated = PaperOrderData.model_validate(dispatch_data.response_data["order"])
            else:
                adapter = PaperBrokerAdapter(
                    execution_date=str(request_data.get("executed_date") or ""),
                    execution_price=request_data.get("executed_price"),
                )
                simulated = adapter.simulate(
                    order.data,
                    executed_date=adapter.execution_date,
                    executed_price=adapter.execution_price,
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"模拟成交 outbox 数据无效：{exc}") from exc
    try:
        fill = paper_fill_from_order(record_id, simulated)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if order.data.status == "proposed":
        try:
            validated_data_version = _validate_paper_fill_before_persist(
                household_id=payload.household_id,
                order=order.data,
                fill=fill,
                policy=policy,
                current_dispatch_id=str(dispatch["id"]) if dispatch is not None else "",
            )
        except HTTPException:
            if dispatch_status == "pending" and dispatch is not None:
                discard_pending_broker_order_dispatch(
                    str(dispatch["id"]),
                    household_id=payload.household_id,
                )
            raise
        if dispatch_status in {"pending", "retryable"}:
            if adapter is None:
                raise HTTPException(status_code=409, detail="模拟成交适配器尚未准备完成")
            gateway = _paper_broker_gateway(
                household_id=payload.household_id,
                adapter=adapter,
                expected_data_version=validated_data_version,
            )
            try:
                simulated = gateway.submit(local_order_id=record_id, order=order.data)
            except (RuntimeError, ValueError) as exc:
                if dispatch_status == "pending" and dispatch is not None:
                    discard_pending_broker_order_dispatch(
                        str(dispatch["id"]),
                        household_id=payload.household_id,
                    )
                status_code = 422 if isinstance(exc, ValueError) else 409
                raise HTTPException(status_code=status_code, detail=str(exc)) from exc
            try:
                fill = paper_fill_from_order(record_id, simulated)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            _validate_paper_fill_before_persist(
                household_id=payload.household_id,
                order=order.data,
                fill=fill,
                policy=policy,
                current_dispatch_id=str(dispatch["id"]) if dispatch is not None else "",
            )
    record, fill_record = record_paper_fill_atomic(
        record_id,
        household_id=payload.household_id,
        order_data=simulated.model_dump(mode="json"),
        fill_data=fill.model_dump(mode="json"),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="未找到模拟订单")
    if fill_record is None:
        raise HTTPException(status_code=409, detail="订单状态已变化，模拟成交未写入；请刷新订单后重试")
    if not fill_existed:
        bump_quant_investment_data_version(payload.household_id)
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
            cached_result = AffordabilityResult.model_validate(upgraded_payload)
            cached_result = _attach_paper_portfolio(cached_result, cache_payload.household_id)
            return cached_result

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
            result = _attach_paper_portfolio(result, cache_payload.household_id)
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
