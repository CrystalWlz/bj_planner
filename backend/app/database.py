from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .schemas import HouseholdData, MarketSnapshotData, PlanningGoalData, RulePackData, ScenarioData


CURRENT_SCHEMA_VERSION = 34


def default_db_path() -> Path:
    override = os.environ.get("HOUSE_PLANNER_DB")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "house-planner" / "planner.db"
    return Path.home() / ".house-planner" / "planner.db"


DB_PATH = default_db_path()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS households (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS planning_goals (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                goal_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_planning_goals_household_type
                ON planning_goals(household_id, goal_type);

            CREATE INDEX IF NOT EXISTS idx_planning_goals_type_priority
                ON planning_goals(goal_type, json_extract(data, '$.priority'));

            CREATE TABLE IF NOT EXISTS rule_packs (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calculation_cache (
                cache_key TEXT PRIMARY KEY,
                engine_fingerprint TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generated_strategies (
                id TEXT PRIMARY KEY,
                cache_key TEXT NOT NULL,
                engine_fingerprint TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                owner_key TEXT NOT NULL,
                strategy_key TEXT NOT NULL,
                variant TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(cache_key, strategy_type, owner_key, variant)
            );

            CREATE INDEX IF NOT EXISTS idx_generated_strategies_cache
                ON generated_strategies(cache_key);

            CREATE INDEX IF NOT EXISTS idx_generated_strategies_type
                ON generated_strategies(strategy_type, owner_key);

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT NOT NULL
            );
            """
        )
        migrate_database(conn)
    seed_database()


def _migration_applied(conn: sqlite3.Connection, version: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()
    return row is not None


def _mark_migration(conn: sqlite3.Connection, version: int, description: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
        (version, now_iso(), description),
    )


def migrate_database(conn: sqlite3.Connection) -> None:
    previous_schema_history = _has_previous_schema_history(conn)
    changed = _normalize_current_records(conn)
    if previous_schema_history or not _migration_applied(conn, CURRENT_SCHEMA_VERSION):
        conn.execute("DELETE FROM schema_migrations")
        _mark_migration(conn, CURRENT_SCHEMA_VERSION, "current schema baseline")
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    elif changed:
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")


def _load_json(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _planning_timing_from_scenario(scenario: dict[str, Any]) -> str:
    mode = str(scenario.get("purchase_planning_mode") or "after_previous_purchase")
    return "parallel" if mode == "parallel" else "auto_sequence"


def _scenario_mode_from_goal(goal: dict[str, Any]) -> str:
    timing_mode = str(goal.get("timing_mode") or "auto_sequence")
    return "parallel" if timing_mode == "parallel" else "after_previous_purchase"


def _planning_timing_from_vehicle(vehicle: dict[str, Any]) -> str:
    mode = str(vehicle.get("purchase_timing_mode") or "auto_sequence")
    return mode if mode in {"auto_sequence", "parallel", "manual_month"} else "auto_sequence"


def _vehicle_timing_from_goal(goal: dict[str, Any]) -> str:
    timing_mode = str(goal.get("timing_mode") or "auto_sequence")
    if timing_mode in {"parallel", "manual_month"}:
        return timing_mode
    return "auto_sequence"


def _home_goal_from_scenario(
    scenario: dict[str, Any],
    *,
    goal_id: str,
    household_id: str | None = None,
) -> dict[str, Any]:
    normalized_scenario = _normalize_scenario(deepcopy(scenario))
    return _normalize_planning_goal(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "goal_type": "home",
            "name": normalized_scenario.get("name") or "购房目标",
            "enabled": bool(normalized_scenario.get("enabled", True)),
            "priority": max(1, _safe_int(normalized_scenario.get("purchase_sequence"), 1)),
            "timing_mode": _planning_timing_from_scenario(normalized_scenario),
            "earliest_purchase_delay_months": max(0, _safe_int(normalized_scenario.get("manual_purchase_delay_months"), 0)),
            "delay_after_dependency_months": max(0, _safe_int(normalized_scenario.get("after_previous_purchase_delay_months"), 0)),
            "allow_parallel": str(normalized_scenario.get("purchase_planning_mode") or "") == "parallel",
            "selected_strategy_id": str(normalized_scenario.get("selected_purchase_plan_variant") or ""),
            "target_params": normalized_scenario,
            "financing_preferences": {
                "commercial_repayment_method": normalized_scenario.get("commercial_repayment_method"),
                "provident_repayment_method": normalized_scenario.get("provident_repayment_method"),
                "commercial_prepayment_mode": normalized_scenario.get("commercial_prepayment_mode"),
                "provident_account_repayment_strategy": normalized_scenario.get("provident_account_repayment_strategy"),
                "investment_withdrawal_mode": normalized_scenario.get("investment_withdrawal_mode"),
            },
            "metadata": {
                "legacy_scenario_id": goal_id,
                "household_id": household_id or "",
            },
        }
    )


def _scenario_from_home_goal(goal_id: str, goal: dict[str, Any]) -> dict[str, Any]:
    scenario = deepcopy(goal.get("target_params") if isinstance(goal.get("target_params"), dict) else {})
    scenario["name"] = goal.get("name") or scenario.get("name") or "购房目标"
    scenario["enabled"] = bool(goal.get("enabled", True))
    scenario["purchase_sequence"] = max(1, _safe_int(goal.get("priority"), _safe_int(scenario.get("purchase_sequence"), 1)))
    scenario["purchase_planning_mode"] = _scenario_mode_from_goal(goal)
    scenario["after_previous_purchase_delay_months"] = max(
        0,
        _safe_int(goal.get("delay_after_dependency_months"), _safe_int(scenario.get("after_previous_purchase_delay_months"), 0)),
    )
    scenario["manual_purchase_delay_months"] = max(
        0,
        _safe_int(goal.get("earliest_purchase_delay_months"), _safe_int(scenario.get("manual_purchase_delay_months"), 0)),
    )
    if goal.get("selected_strategy_id"):
        scenario["selected_purchase_plan_variant"] = str(goal.get("selected_strategy_id"))
    metadata = goal.get("metadata") if isinstance(goal.get("metadata"), dict) else {}
    scenario["planning_goal_id"] = goal_id
    scenario["legacy_scenario_id"] = metadata.get("legacy_scenario_id") or goal_id
    return _normalize_scenario(scenario)


def _vehicle_goal_from_plan(
    vehicle: dict[str, Any],
    *,
    household_id: str,
    index: int,
    goal_id: str,
) -> dict[str, Any]:
    vehicle_data = deepcopy(vehicle)
    _fill_vehicle_timing_defaults(vehicle_data, index)
    _fill_vehicle_prepayment_defaults(vehicle_data)
    _normalize_vehicle_financing_options(vehicle_data)
    timing_mode = _planning_timing_from_vehicle(vehicle_data)
    return _normalize_planning_goal(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "goal_type": "vehicle",
            "name": vehicle_data.get("name") or f"用车需求 {index + 1}",
            "enabled": bool(vehicle_data.get("enabled", True)),
            "priority": max(1, _safe_int(vehicle_data.get("planning_sequence"), index + 1)),
            "timing_mode": timing_mode,
            "earliest_purchase_delay_months": max(
                0,
                _safe_int(vehicle_data.get("manual_purchase_delay_months"), _safe_int(vehicle_data.get("purchase_delay_months"), 0)),
            ),
            "delay_after_dependency_months": max(0, _safe_int(vehicle_data.get("after_previous_event_delay_months"), 0)),
            "allow_parallel": timing_mode == "parallel",
            "selected_strategy_id": str(vehicle_data.get("selected_strategy_variant") or "target"),
            "target_params": vehicle_data,
            "financing_preferences": {
                "financing_options": vehicle_data.get("financing_options", []),
                "loan_prepayment_enabled": vehicle_data.get("loan_prepayment_enabled", False),
                "loan_prepayment_strategy_type": vehicle_data.get("loan_prepayment_strategy_type", "none"),
            },
            "holding_cost_params": {
                "annual_mileage_km": vehicle_data.get("annual_mileage_km", 0),
                "monthly_parking_cost": vehicle_data.get("monthly_parking_cost", 0),
                "annual_maintenance_cost": vehicle_data.get("annual_maintenance_cost", 0),
                "annual_insurance_rate": vehicle_data.get("annual_insurance_rate", 0),
            },
            "metadata": {
                "legacy_household_id": household_id,
                "legacy_vehicle_index": index,
                "legacy_vehicle_goal_id": goal_id,
            },
        }
    )


def _vehicle_plan_from_goal(goal: dict[str, Any], index: int) -> dict[str, Any]:
    vehicle = deepcopy(goal.get("target_params") if isinstance(goal.get("target_params"), dict) else {})
    vehicle["name"] = goal.get("name") or vehicle.get("name") or f"用车需求 {index + 1}"
    vehicle["enabled"] = bool(goal.get("enabled", True))
    vehicle["planning_sequence"] = max(1, _safe_int(goal.get("priority"), index + 1))
    vehicle["purchase_timing_mode"] = _vehicle_timing_from_goal(goal)
    vehicle["manual_purchase_delay_months"] = max(
        0,
        _safe_int(goal.get("earliest_purchase_delay_months"), _safe_int(vehicle.get("manual_purchase_delay_months"), 0)),
    )
    vehicle["after_previous_event_delay_months"] = max(
        0,
        _safe_int(goal.get("delay_after_dependency_months"), _safe_int(vehicle.get("after_previous_event_delay_months"), 0)),
    )
    if goal.get("selected_strategy_id"):
        vehicle["selected_strategy_variant"] = str(goal.get("selected_strategy_id"))
    _fill_vehicle_timing_defaults(vehicle, index)
    _fill_vehicle_prepayment_defaults(vehicle)
    _normalize_vehicle_financing_options(vehicle)
    return vehicle


def _normalize_planning_goal(data: dict[str, Any]) -> dict[str, Any]:
    if "target_params" not in data or not isinstance(data.get("target_params"), dict):
        legacy_payload = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "schema_version",
                "goal_type",
                "name",
                "enabled",
                "priority",
                "timing_mode",
                "earliest_purchase_month",
                "earliest_purchase_delay_months",
                "depends_on_goal_id",
                "delay_after_dependency_months",
                "allow_parallel",
                "selected_strategy_id",
                "financing_preferences",
                "holding_cost_params",
                "metadata",
                "notes",
            }
        }
        data["target_params"] = legacy_payload
    data.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    data.setdefault("goal_type", "home")
    data.setdefault("name", "规划目标")
    data.setdefault("enabled", True)
    data.setdefault("priority", 1)
    data.setdefault("timing_mode", "auto_sequence")
    data.setdefault("earliest_purchase_month", "")
    data.setdefault("earliest_purchase_delay_months", 0)
    data.setdefault("depends_on_goal_id", "")
    data.setdefault("delay_after_dependency_months", 0)
    data.setdefault("allow_parallel", False)
    data.setdefault("selected_strategy_id", "")
    data.setdefault("financing_preferences", {})
    data.setdefault("holding_cost_params", {})
    data.setdefault("metadata", {})
    data.setdefault("notes", "")
    goal_type = str(data.get("goal_type") or "home")
    if goal_type == "home":
        data["target_params"] = _normalize_scenario(data.get("target_params") if isinstance(data.get("target_params"), dict) else {})
        data["priority"] = max(1, _safe_int(data.get("priority"), _safe_int(data["target_params"].get("purchase_sequence"), 1)))
    elif goal_type == "vehicle":
        target = data.get("target_params") if isinstance(data.get("target_params"), dict) else {}
        _fill_vehicle_timing_defaults(target, max(0, _safe_int(data.get("priority"), 1) - 1))
        _fill_vehicle_prepayment_defaults(target)
        candidates = target.get("candidate_vehicles")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                _fill_vehicle_timing_defaults(candidate, max(0, _safe_int(data.get("priority"), 1) - 1))
                _fill_vehicle_prepayment_defaults(candidate)
                _normalize_vehicle_financing_options(candidate)
        _normalize_vehicle_financing_options(target)
        data["target_params"] = target
        data["priority"] = max(1, _safe_int(data.get("priority"), _safe_int(target.get("planning_sequence"), 1)))
    normalized = PlanningGoalData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def _update_table_json(
    conn: sqlite3.Connection,
    table: str,
    migrate: Callable[[dict[str, Any]], dict[str, Any]],
) -> int:
    rows = conn.execute(f"SELECT id, data FROM {table}").fetchall()
    changed = 0
    for row in rows:
        original = _load_json(row["data"])
        migrated = migrate(deepcopy(original))
        if migrated != original:
            conn.execute(
                f"UPDATE {table} SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(migrated, ensure_ascii=False), now_iso(), row["id"]),
            )
            changed += 1
    return changed


def _has_previous_schema_history(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version < ? LIMIT 1",
        (CURRENT_SCHEMA_VERSION,),
    ).fetchone()
    return row is not None


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _default_vehicle_financing_options() -> list[dict[str, Any]]:
    return [
        {
            "id": "cash_only",
            "name": "全款",
            "enabled": True,
            "financing_type": "cash_only",
            "total_months": 1,
            "interest_free_months": 0,
            "later_annual_rate": 0.0,
            "min_down_payment_ratio": 1.0,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": False,
            "prepayment_allowed_after_month": 1,
            "prepayment_policy_note": "全款购车不形成车贷，也不存在提前还本。",
            "notes": "交易当月一次性支付车价，后续只保留保险、保养、停车、电费等持有成本。",
        },
        {
            "id": "three_year_two_year_subsidy",
            "name": "三年前两年贴息",
            "enabled": True,
            "financing_type": "dealer_subsidy",
            "total_months": 36,
            "interest_free_months": 24,
            "later_annual_rate": 0.0199,
            "min_down_payment_ratio": 0.30,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "通常需满足合同约定期数后提前还本；贴息期内提前还本可能影响补贴资格。",
            "notes": "合同仍按全期等额本息计息，前两年由厂家或经销商补贴部分利息。",
        },
        {
            "id": "twenty_down_two_year_subsidy",
            "name": "最低20%首付两年贴息",
            "enabled": True,
            "financing_type": "dealer_subsidy",
            "total_months": 60,
            "interest_free_months": 24,
            "later_annual_rate": 0.0249,
            "min_down_payment_ratio": 0.20,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "最低首付换来更高贷款本金，提前还本需按合同约定期数和违约金条款判断。",
            "notes": "适合比较低首付保现金方案；贴息来自厂家或经销商补贴，不改变贷款余额推演。",
        },
        {
            "id": "zero_down_five_year_low_rate",
            "name": "0首付五年低息",
            "enabled": True,
            "financing_type": "bank_loan",
            "total_months": 60,
            "interest_free_months": 0,
            "later_annual_rate": 0.029,
            "min_down_payment_ratio": 0.0,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "低息方案是否允许提前还本、是否收违约金要以具体合同为准。",
            "notes": "适合比较极低首付对买房现金池的影响；家庭承担合同全期利息。",
        },
    ]


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _strip_nested_vehicle_candidates(vehicle: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(vehicle)
    cleaned["candidate_vehicles"] = []
    return cleaned


def _fill_vehicle_timing_defaults(vehicle: dict[str, Any], index: int) -> None:
    vehicle.setdefault("planning_sequence", index + 1)
    vehicle.setdefault("purchase_timing_mode", "auto_sequence")
    vehicle.setdefault("after_previous_event_delay_months", 0)
    vehicle.setdefault("manual_purchase_delay_months", max(0, _safe_int(vehicle.get("purchase_delay_months"), 0)))
    candidates = vehicle.get("candidate_vehicles")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate.setdefault("planning_sequence", _safe_int(vehicle.get("planning_sequence"), index + 1))
            candidate.setdefault("purchase_timing_mode", vehicle.get("purchase_timing_mode") or "auto_sequence")
            candidate.setdefault("after_previous_event_delay_months", _safe_int(vehicle.get("after_previous_event_delay_months"), 0))
            candidate.setdefault(
                "manual_purchase_delay_months",
                max(0, _safe_int(candidate.get("purchase_delay_months") or vehicle.get("manual_purchase_delay_months"), 0)),
            )


def _fill_vehicle_prepayment_defaults(vehicle: dict[str, Any]) -> None:
    vehicle.setdefault("loan_prepayment_enabled", False)
    vehicle.setdefault("loan_prepayment_start_month", 1)
    vehicle.setdefault("loan_prepayment_allowed_after_month", 12)
    vehicle.setdefault("loan_prepayment_monthly_amount", 0)
    vehicle.setdefault("loan_prepayment_strategy_type", "none")
    vehicle.setdefault("loan_prepayment_lump_sum_month", 0)
    vehicle.setdefault("loan_prepayment_lump_sum_amount", 0)
    if not bool(vehicle.get("loan_prepayment_enabled")):
        vehicle["loan_prepayment_strategy_type"] = "none"
        vehicle["loan_prepayment_monthly_amount"] = 0
        vehicle["loan_prepayment_lump_sum_month"] = 0
        vehicle["loan_prepayment_lump_sum_amount"] = 0
    elif str(vehicle.get("loan_prepayment_strategy_type") or "none") == "none":
        has_extra_payment = (
            _safe_float(vehicle.get("loan_prepayment_monthly_amount")) > 0
            or _safe_float(vehicle.get("loan_prepayment_lump_sum_amount")) > 0
        )
        if has_extra_payment:
            vehicle["loan_prepayment_strategy_type"] = "manual"
    candidates = vehicle.get("candidate_vehicles")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                _fill_vehicle_prepayment_defaults(candidate)


def _normalize_vehicle_financing_options(vehicle: dict[str, Any]) -> None:
    options = vehicle.get("financing_options")
    normalized: list[dict[str, Any]] = []
    legacy_option_names = {"当前经销商金融方案", "当前普通贷款方案", "当前经销商贴息方案"}
    legacy_options = (
        isinstance(options, list)
        and bool(options)
        and all(
            isinstance(option, dict)
            and (str(option.get("id") or "") == "legacy_current" or str(option.get("name") or "") in legacy_option_names)
            for option in options
        )
    )
    if isinstance(options, list) and not legacy_options:
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            total_months = max(1, min(120, _safe_int(option.get("total_months"), _safe_int(vehicle.get("total_months"), 60))))
            interest_free_months = max(0, min(total_months, _safe_int(option.get("interest_free_months"), 0)))
            min_ratio = _clamp(_safe_float(option.get("min_down_payment_ratio"), 0.10), 0.0, 1.0)
            max_ratio = _clamp(_safe_float(option.get("max_down_payment_ratio"), 1.0), min_ratio, 1.0)
            financing_type = str(option.get("financing_type") or ("dealer_subsidy" if interest_free_months > 0 else "standard"))
            if financing_type == "cash_only":
                total_months = 1
                interest_free_months = 0
                min_ratio = 1.0
                max_ratio = 1.0
            prepayment_allowed = financing_type != "cash_only" and bool(option.get("prepayment_allowed", True))
            normalized.append(
                {
                    **option,
                    "id": option.get("id") or f"financing_{index + 1}",
                    "name": option.get("name") or f"金融方案 {index + 1}",
                    "enabled": bool(option.get("enabled", True)),
                    "financing_type": financing_type,
                    "total_months": total_months,
                    "interest_free_months": interest_free_months,
                    "later_annual_rate": _clamp(_safe_float(option.get("later_annual_rate"), _safe_float(vehicle.get("later_annual_rate"), 0.0199)), 0.0, 0.5),
                    "min_down_payment_ratio": min_ratio,
                    "max_down_payment_ratio": max_ratio,
                    "prepayment_allowed": prepayment_allowed,
                    "prepayment_allowed_after_month": (
                        max(1, min(total_months, _safe_int(option.get("prepayment_allowed_after_month"), 12)))
                        if prepayment_allowed
                        else 1
                    ),
                    "prepayment_policy_note": option.get("prepayment_policy_note")
                    or ("提前还本规则以经销商或银行合同为准。" if prepayment_allowed else "该金融方案不形成或不允许提前还本。"),
                    "notes": option.get("notes") or "",
                }
            )
    if not normalized:
        normalized = _default_vehicle_financing_options()
    vehicle["financing_options"] = normalized
    selected = next((option for option in normalized if option.get("enabled")), normalized[0])
    vehicle.setdefault("selected_financing_option_id", selected.get("id") or "")
    vehicle.setdefault("selected_financing_option_name", selected.get("name") or "")
    vehicle.setdefault("selected_financing_type", selected.get("financing_type") or "")
    vehicle.setdefault("selected_financing_min_down_payment_ratio", selected.get("min_down_payment_ratio", 0.0))
    vehicle.setdefault("selected_financing_max_down_payment_ratio", selected.get("max_down_payment_ratio", 1.0))
    vehicle.setdefault("selected_financing_prepayment_allowed", selected.get("prepayment_allowed", True))
    vehicle.setdefault("selected_financing_prepayment_policy_note", selected.get("prepayment_policy_note", ""))


def _normalize_car_plan(data: dict[str, Any]) -> None:
    car_plan = data.setdefault("car_plan", {})
    if not isinstance(car_plan, dict):
        data["car_plan"] = {}
        return
    car_plan.setdefault("annual_maintenance_growth_rate", 0.03)
    car_plan.setdefault("annual_insurance_growth_rate", 0.02)

    existing = car_plan.get("vehicle_plans")
    vehicle_plans = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []

    for index, vehicle in enumerate(vehicle_plans):
        if not isinstance(vehicle, dict):
            continue
        candidates = vehicle.get("candidate_vehicles")
        has_explicit_candidate_list = isinstance(candidates, list)
        candidate_vehicles = [item for item in candidates if isinstance(item, dict)] if has_explicit_candidate_list else []
        if not has_explicit_candidate_list and bool(vehicle.get("enabled")) and _safe_float(vehicle.get("total_price")) > 0:
            candidate_vehicles = [_strip_nested_vehicle_candidates(vehicle)]
        for candidate in candidate_vehicles:
            candidate.setdefault("enabled", True)
            candidate.setdefault("selected_strategy_variant", "target")
            candidate.setdefault("candidate_vehicles", [])
            _fill_vehicle_timing_defaults(candidate, index)
            _fill_vehicle_prepayment_defaults(candidate)
            _normalize_vehicle_financing_options(candidate)
        vehicle["candidate_vehicles"] = candidate_vehicles
        _fill_vehicle_timing_defaults(vehicle, index)
        _fill_vehicle_prepayment_defaults(vehicle)
        _normalize_vehicle_financing_options(vehicle)

    car_plan["vehicle_plans"] = vehicle_plans
    car_plan["enabled"] = any(
        bool(item.get("enabled")) and _safe_float(item.get("total_price")) > 0
        for item in vehicle_plans
        if isinstance(item, dict)
    )


def _retirement_category_from_age(age: int, index: int) -> str:
    if age <= 55 and index != 0:
        return "female_50"
    if age <= 58 and index != 0:
        return "female_55"
    return "male_60"


def _policy_retirement_age(category: str) -> int:
    if category == "female_50":
        return 55
    if category == "female_55":
        return 58
    return 63


def _normalize_members_and_career_shock(data: dict[str, Any]) -> None:
    members = data.get("members")
    if not isinstance(members, list):
        data["members"] = []
        members = data["members"]

    household_balance = max(0.0, _safe_float(data.get("provident_fund_balance")))
    member_balance_total = sum(
        max(0.0, _safe_float(member.get("provident_fund_balance")))
        for member in members
        if isinstance(member, dict)
    )
    if household_balance > 0 and member_balance_total <= 0 and members:
        weights: list[float] = []
        for member in members:
            if not isinstance(member, dict):
                weights.append(0.0)
                continue
            stages = member.get("income_stages")
            first_stage = stages[0] if isinstance(stages, list) and stages and isinstance(stages[0], dict) else {}
            weights.append(max(0.0, _safe_float(first_stage.get("monthly_housing_fund")) or _safe_float(member.get("monthly_housing_fund"))))
        if sum(weights) <= 0:
            weights = [1.0 for _ in members]
        total_weight = sum(weights) or float(len(members))
        for index, member in enumerate(members):
            if isinstance(member, dict):
                member["provident_fund_balance"] = round(household_balance * weights[index] / total_weight, 2)

    career_shock = data.setdefault("career_shock", {})
    if not isinstance(career_shock, dict):
        career_shock = {}
        data["career_shock"] = career_shock


    existing_settings = career_shock.get("member_settings")
    existing_by_name: dict[str, dict[str, Any]] = {}
    if isinstance(existing_settings, list):
        for item in existing_settings:
            if isinstance(item, dict):
                existing_by_name[str(item.get("member_name") or "")] = item
    legacy_auto_pension = bool(career_shock.get("auto_pension_income", True))

    next_settings: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            continue
        name = str(member.get("name") or f"成员 {index + 1}")
        member.setdefault("birth_month", "")
        member.setdefault("family_join_month", "2026-07")
        member.setdefault("current_age", 30)
        member.setdefault("retirement_category", _retirement_category_from_age(63 if index == 0 else 58, index))
        member.setdefault("social_security_months", 0)
        member.setdefault("income_tax_months", 0)
        member.setdefault("existing_home_count", 0)
        member.setdefault("existing_mortgage_count", 0)
        member.setdefault("initial_cash_balance", 0)
        member.setdefault("initial_investments", 0)
        member.setdefault("initial_other_asset_value", 0)
        member.setdefault("initial_other_debt_balance", 0)
        member_center = str(member.pop("provident_account_management_center", "") or "").strip().lower()
        default_stage_center = (
            "national"
            if member_center in {"national", "central_state", "guoguan", "state"}
            else "beijing_municipal"
        )
        if not isinstance(member.get("income_stages"), list) or not member.get("income_stages"):
            member["income_stages"] = [
                {
                    "name": "当前收入",
                    "stage_kind": "salary",
                    "start_date": member.get("employment_start_date") or "2026-07-01",
                    "end_date": None,
                    "monthly_salary_gross": _safe_float(member.get("monthly_salary_gross")),
                    "annual_bonus": _safe_float(member.get("annual_bonus")),
                    "annual_bonus_payout_month": 4,
                    "monthly_freelance_income": 0,
                    "monthly_non_taxable_income": _safe_float(member.get("monthly_non_taxable_income")),
                    "monthly_extra_cash_expense": _safe_float(member.get("monthly_extra_cash_expense")),
                    "monthly_social_insurance": _safe_float(member.get("monthly_social_insurance")),
                    "monthly_housing_fund": _safe_float(member.get("monthly_housing_fund")),
                    "housing_fund_personal_rate": _safe_float(member.get("housing_fund_personal_rate"), 0.12),
                    "housing_fund_employer_rate": _safe_float(member.get("housing_fund_employer_rate"), 0.12),
                    "monthly_special_additional_deduction": _safe_float(member.get("monthly_special_additional_deduction")),
                    "other_annual_deductions": _safe_float(member.get("other_annual_deductions")),
                    "other_annual_taxable_income": _safe_float(member.get("other_annual_taxable_income")),
                    "bonus_tax_method": member.get("bonus_tax_method") or "best",
                    "payroll_contributions_enabled": True,
                }
            ]
        for stage in member.get("income_stages", []):
            if isinstance(stage, dict):
                stage.setdefault("stage_kind", "salary")
                stage.setdefault("annual_bonus_payout_month", 4)
                center = str(stage.get("provident_account_management_center") or default_stage_center).strip().lower()
                stage["provident_account_management_center"] = (
                    "national"
                    if center in {"national", "central_state", "guoguan", "state"}
                    else "beijing_municipal"
                )
                stage.setdefault("monthly_freelance_income", 0)
        existing = existing_by_name.get(name, {})
        member_enabled = bool(existing.get("enabled")) if existing else False
        next_settings.append(
            {
                "member_name": name,
                "enabled": member_enabled,
                "layoff_age": _safe_int(existing.get("layoff_age") if existing else 35, 35),
                "retirement_age": _policy_retirement_age(str(member.get("retirement_category") or "male_60")),
                "freelance_income_monthly": _safe_float(existing.get("freelance_income_monthly") if existing else 0),
                "pension_monthly": _safe_float(existing.get("pension_monthly") if existing else 0),
                "auto_pension_monthly": bool(existing.get("auto_pension_monthly", legacy_auto_pension)) if existing else legacy_auto_pension,
            }
        )

    career_shock["enabled"] = any(bool(item.get("enabled")) for item in next_settings)
    career_shock["member_settings"] = next_settings
    career_shock.setdefault("auto_flexible_housing_fund", True)
    career_shock.pop("auto_pension_income", None)
    career_shock.setdefault("self_housing_fund_monthly", 0)

def _normalize_household(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("family_down_payment_support_mode", "provident")
    data.setdefault("family_savings_support_amount", 0)
    data.setdefault("investment_buy_fee_rate", 0.0015)
    data.setdefault("investment_sell_fee_rate", 0.005)
    data.setdefault("investment_taxable_return_ratio", 0)
    data.setdefault("investment_return_tax_rate", 0)
    if not isinstance(data.get("household_expense_stages"), list) or not data.get("household_expense_stages"):
        rent_amount = _safe_float(data.get("monthly_rent_from_housing_fund"))
        data["household_expense_stages"] = [
            {
                "name": "当前家庭支出",
                "start_month": "2026-07",
                "end_month": None,
                "base_living_expense": _safe_float(data.get("monthly_expense")),
                "other_fixed_debt_payment": _safe_float(data.get("monthly_debt_payment")),
                "rent_amount": rent_amount,
                "rent_payment_mode": "provident" if rent_amount > 0 else "cash",
                "rent_payment_frequency": "monthly",
            }
        ]
    for stage in data.get("household_expense_stages", []):
        if isinstance(stage, dict):
            stage["rent_payment_mode"] = "provident" if stage.get("rent_payment_mode") == "provident" else "cash"
            stage["rent_payment_frequency"] = "quarterly" if stage.get("rent_payment_frequency") == "quarterly" else "monthly"
    data.setdefault("scheduled_expenses", [])
    for expense in data["scheduled_expenses"]:
        if isinstance(expense, dict):
            frequency = str(expense.get("frequency") or "monthly")
            expense["frequency"] = "annual_once" if frequency == "annual_once" else "monthly"
            default_month = _safe_int(str(expense.get("start_month") or "2026-01").split("-")[-1], 1)
            expense.setdefault("annual_occurrence_month", max(1, min(12, default_month)))
    data.setdefault("phased_loans", [])
    for loan in data["phased_loans"]:
        if isinstance(loan, dict):
            loan.setdefault("prepayment_mode", "none")
            loan.setdefault("prepayment_start_month", 1)
            loan.setdefault("prepayment_allowed_after_month", 1)
            loan.setdefault("prepayment_monthly_amount", 0)
    data.setdefault("elderly_dependents", [])
    data.setdefault("property_goals", [])
    _normalize_car_plan(data)
    _normalize_members_and_career_shock(data)
    normalized = HouseholdData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_household_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_household(data)


def _normalize_scenario(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("selected_purchase_plan_variant", "")
    data.setdefault("enabled", True)
    data.setdefault("purchase_sequence", 1)
    data.setdefault("purchase_planning_mode", "after_previous_purchase")
    data.setdefault("after_previous_purchase_delay_months", 0)
    data.setdefault("investment_withdrawal_mode", "auto")
    data.setdefault("investment_min_balance_after_purchase", 0)
    commercial_prepayment_mode = str(
        data.get("commercial_prepayment_mode")
        or ("manual" if bool(data.get("commercial_prepayment_enabled")) else "auto")
    )
    if commercial_prepayment_mode not in {"auto", "manual", "none"}:
        commercial_prepayment_mode = "auto"
    data["commercial_prepayment_mode"] = commercial_prepayment_mode
    data["commercial_prepayment_enabled"] = commercial_prepayment_mode == "manual"
    data.setdefault("commercial_prepayment_start_month", 1)
    data.setdefault("commercial_prepayment_allowed_after_month", 12)
    data.setdefault("commercial_prepayment_monthly_amount", 0)
    if commercial_prepayment_mode == "none":
        data["commercial_prepayment_monthly_amount"] = 0
    data.setdefault("provident_account_repayment_strategy", "auto")
    if "二手" not in str(data.get("property_type") or ""):
        data["building_age_years"] = 0
        data["building_structure"] = "unknown"
        data["is_old_community_renovated"] = False
        data["remaining_land_use_years"] = None
    normalized = ScenarioData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_scenario_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_scenario(data)


def normalize_planning_goal_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_planning_goal(data)


def _normalize_rule_pack(data: dict[str, Any]) -> dict[str, Any]:
    defaults = RulePackData().model_dump(mode="json")
    params = data.get("params")
    merged_params = defaults["params"] | (params if isinstance(params, dict) else {})
    if _safe_float(merged_params.get("second_home_provident_min_down_payment_ratio")) < 0.30:
        merged_params["second_home_provident_min_down_payment_ratio"] = 0.30
    data = defaults | data
    data["params"] = merged_params
    normalized = RulePackData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_rule_pack_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_rule_pack(data)


def _normalize_market_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    normalized = MarketSnapshotData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_market_snapshot_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_market_snapshot(data)


def _normalize_current_records(conn: sqlite3.Connection) -> bool:
    changed = 0
    changed += _update_table_json(conn, "households", _normalize_household)
    changed += _update_table_json(conn, "scenarios", _normalize_scenario)
    changed += _update_table_json(conn, "rule_packs", _normalize_rule_pack)
    changed += _update_table_json(conn, "market_snapshots", _normalize_market_snapshot)
    changed += _update_table_json(conn, "planning_goals", _normalize_planning_goal)
    changed += _ensure_planning_goals_from_legacy(conn)
    return changed > 0


def _stable_vehicle_goal_id(household_id: str, index: int, vehicle: dict[str, Any]) -> str:
    metadata = vehicle.get("metadata") if isinstance(vehicle.get("metadata"), dict) else {}
    existing = metadata.get("planning_goal_id") or vehicle.get("planning_goal_id")
    if existing:
        return str(existing)
    raw = json.dumps(
        {
            "kind": "vehicle_goal",
            "household_id": household_id,
            "index": index,
            "name": vehicle.get("name") or "",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex


def _planning_goal_exists(conn: sqlite3.Connection, goal_id: str) -> bool:
    return conn.execute("SELECT 1 FROM planning_goals WHERE id = ?", (goal_id,)).fetchone() is not None


def _insert_or_replace_planning_goal(
    conn: sqlite3.Connection,
    *,
    goal_id: str,
    household_id: str | None,
    goal_type: str,
    data: dict[str, Any],
    created_at: str | None = None,
    updated_at: str | None = None,
) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO planning_goals (id, household_id, goal_type, data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            household_id = excluded.household_id,
            goal_type = excluded.goal_type,
            data = excluded.data,
            updated_at = excluded.updated_at
        """,
        (
            goal_id,
            household_id,
            goal_type,
            json.dumps(_normalize_planning_goal(data), ensure_ascii=False),
            created_at or timestamp,
            updated_at or timestamp,
        ),
    )


def _ensure_planning_goals_from_legacy(conn: sqlite3.Connection) -> int:
    changed = 0
    for row in conn.execute("SELECT id, household_id, data, created_at, updated_at FROM scenarios").fetchall():
        goal_id = str(row["id"])
        if _planning_goal_exists(conn, goal_id):
            continue
        scenario = _load_json(row["data"])
        goal_data = _home_goal_from_scenario(scenario, goal_id=goal_id, household_id=row["household_id"])
        _insert_or_replace_planning_goal(
            conn,
            goal_id=goal_id,
            household_id=row["household_id"],
            goal_type="home",
            data=goal_data,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        changed += 1

    for row in conn.execute("SELECT id, data FROM households").fetchall():
        household_id = str(row["id"])
        existing_vehicle_goal = conn.execute(
            "SELECT 1 FROM planning_goals WHERE household_id = ? AND goal_type = 'vehicle' LIMIT 1",
            (household_id,),
        ).fetchone()
        if existing_vehicle_goal is not None:
            continue
        household = _load_json(row["data"])
        car_plan = household.get("car_plan") if isinstance(household.get("car_plan"), dict) else {}
        vehicles = car_plan.get("vehicle_plans") if isinstance(car_plan.get("vehicle_plans"), list) else []
        for index, vehicle in enumerate(item for item in vehicles if isinstance(item, dict)):
            goal_id = _stable_vehicle_goal_id(household_id, index, vehicle)
            goal_data = _vehicle_goal_from_plan(vehicle, household_id=household_id, index=index, goal_id=goal_id)
            _insert_or_replace_planning_goal(
                conn,
                goal_id=goal_id,
                household_id=household_id,
                goal_type="vehicle",
                data=goal_data,
            )
            changed += 1
    return changed


def cleanup_database_storage(*, create_backup: bool = True) -> Path | None:
    backup_path: Path | None = None
    if create_backup and DB_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = DB_PATH.with_name(f"{DB_PATH.stem}.backup-{timestamp}{DB_PATH.suffix}")
        shutil.copy2(DB_PATH, backup_path)
    with get_connection() as conn:
        migrate_database(conn)
        conn.execute("DELETE FROM calculation_cache")
        conn.commit()
        conn.execute("VACUUM")
    return backup_path


def _count(table: str) -> int:
    with get_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])


def insert_record(table: str, data: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    timestamp = now_iso()
    payload = json.dumps(data, ensure_ascii=False)
    fields = {"id": record_id, "data": payload, "created_at": timestamp, "updated_at": timestamp}
    if extra:
        fields.update(extra)

    columns = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            list(fields.values()),
        )
    return get_record(table, record_id)


def update_record(table: str, record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = now_iso()
    payload = json.dumps(data, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE {table} SET data = ?, updated_at = ? WHERE id = ?",
            (payload, timestamp, record_id),
        )
    return get_record(table, record_id)


def delete_record(table: str, record_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
        return cursor.rowcount > 0


def list_records(table: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at ASC").fetchall()
    return [_row_to_record(row) for row in rows]


def get_record(table: str, record_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return _row_to_record(row) if row else None


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    if "data" in record:
        record["data"] = json.loads(record["data"])
    return record


def _row_to_planning_goal_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = json.loads(record["data"])
    return record


def _planning_goal_rows(
    *,
    household_id: str | None = None,
    goal_type: str | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[str] = []
    if household_id is not None:
        clauses.append("household_id = ?")
        params.append(household_id)
    if goal_type is not None:
        clauses.append("goal_type = ?")
        params.append(goal_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT * FROM planning_goals
            {where}
            ORDER BY json_extract(data, '$.priority') ASC, created_at ASC
            """,
            params,
        ).fetchall()


def list_planning_goal_records(
    *,
    household_id: str | None = None,
    goal_type: str | None = None,
) -> list[dict[str, Any]]:
    return [
        _row_to_planning_goal_record(row)
        for row in _planning_goal_rows(household_id=household_id, goal_type=goal_type)
    ]


def insert_planning_goal_record(data: dict[str, Any], household_id: str | None = None) -> dict[str, Any]:
    normalized = _normalize_planning_goal(data)
    record_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_connection() as conn:
        _insert_or_replace_planning_goal(
            conn,
            goal_id=record_id,
            household_id=household_id,
            goal_type=str(normalized.get("goal_type") or "home"),
            data=normalized,
            created_at=timestamp,
            updated_at=timestamp,
        )
    return get_planning_goal_record(record_id)


def update_planning_goal_record(record_id: str, data: dict[str, Any], household_id: str | None = None) -> dict[str, Any] | None:
    normalized = _normalize_planning_goal(data)
    with get_connection() as conn:
        row = conn.execute("SELECT created_at FROM planning_goals WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        _insert_or_replace_planning_goal(
            conn,
            goal_id=record_id,
            household_id=household_id,
            goal_type=str(normalized.get("goal_type") or "home"),
            data=normalized,
            created_at=row["created_at"],
            updated_at=now_iso(),
        )
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return get_planning_goal_record(record_id)


def delete_planning_goal_record(record_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM planning_goals WHERE id = ?", (record_id,))
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return cursor.rowcount > 0


def get_planning_goal_record(record_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM planning_goals WHERE id = ?", (record_id,)).fetchone()
    return _row_to_planning_goal_record(row) if row else None


def _vehicle_goals_for_household(household_id: str) -> list[dict[str, Any]]:
    return [
        _row_to_planning_goal_record(row)
        for row in _planning_goal_rows(household_id=household_id, goal_type="vehicle")
    ]


def _project_vehicle_goals_into_household(record: dict[str, Any]) -> dict[str, Any]:
    household_id = str(record["id"])
    data = deepcopy(record["data"])
    vehicle_goals = _vehicle_goals_for_household(household_id)
    if vehicle_goals:
        vehicles = [
            _vehicle_plan_from_goal(goal["data"], index)
            for index, goal in enumerate(vehicle_goals)
        ]
        car_plan = data.setdefault("car_plan", {})
        if not isinstance(car_plan, dict):
            car_plan = {}
            data["car_plan"] = car_plan
        car_plan["vehicle_plans"] = vehicles
        car_plan["enabled"] = any(bool(vehicle.get("enabled")) for vehicle in vehicles)
    record = deepcopy(record)
    record["data"] = _normalize_household(data)
    return record


def _sync_vehicle_goals_from_household(conn: sqlite3.Connection, household_id: str, household: dict[str, Any]) -> int:
    conn.execute("DELETE FROM planning_goals WHERE household_id = ? AND goal_type = 'vehicle'", (household_id,))
    car_plan = household.get("car_plan") if isinstance(household.get("car_plan"), dict) else {}
    vehicles = car_plan.get("vehicle_plans") if isinstance(car_plan.get("vehicle_plans"), list) else []
    changed = 0
    for index, vehicle in enumerate(item for item in vehicles if isinstance(item, dict)):
        goal_id = _stable_vehicle_goal_id(household_id, index, vehicle)
        goal_data = _vehicle_goal_from_plan(vehicle, household_id=household_id, index=index, goal_id=goal_id)
        _insert_or_replace_planning_goal(
            conn,
            goal_id=goal_id,
            household_id=household_id,
            goal_type="vehicle",
            data=goal_data,
        )
        changed += 1
    conn.execute("DELETE FROM calculation_cache")
    conn.execute("DELETE FROM generated_strategies")
    return changed


def list_household_records() -> list[dict[str, Any]]:
    return [_project_vehicle_goals_into_household(record) for record in list_records("households")]


def insert_household_record(data: dict[str, Any]) -> dict[str, Any]:
    record = insert_record("households", _normalize_household(data))
    with get_connection() as conn:
        _sync_vehicle_goals_from_household(conn, str(record["id"]), record["data"])
    saved = get_record("households", str(record["id"]))
    return _project_vehicle_goals_into_household(saved)


def update_household_record(record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    normalized = _normalize_household(data)
    record = update_record("households", record_id, normalized)
    if record is None:
        return None
    with get_connection() as conn:
        _sync_vehicle_goals_from_household(conn, record_id, normalized)
    saved = get_record("households", record_id)
    return _project_vehicle_goals_into_household(saved)


def list_scenario_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for goal in list_planning_goal_records(goal_type="home"):
        scenario = _scenario_from_home_goal(goal["id"], goal["data"])
        records.append(
            {
                "id": goal["id"],
                "household_id": goal.get("household_id"),
                "data": scenario,
                "created_at": goal["created_at"],
                "updated_at": goal["updated_at"],
            }
        )
    return records


def insert_scenario_record(data: dict[str, Any], household_id: str | None = None) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    normalized_scenario = _normalize_scenario(data)
    goal = _home_goal_from_scenario(normalized_scenario, goal_id=record_id, household_id=household_id)
    timestamp = now_iso()
    with get_connection() as conn:
        _insert_or_replace_planning_goal(
            conn,
            goal_id=record_id,
            household_id=household_id,
            goal_type="home",
            data=goal,
            created_at=timestamp,
            updated_at=timestamp,
        )
        conn.execute(
            "INSERT OR REPLACE INTO scenarios (id, household_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (record_id, household_id, json.dumps(normalized_scenario, ensure_ascii=False), timestamp, timestamp),
        )
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return next(record for record in list_scenario_records() if record["id"] == record_id)


def update_scenario_record(record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    normalized_scenario = _normalize_scenario(data)
    with get_connection() as conn:
        goal_row = conn.execute("SELECT household_id, created_at FROM planning_goals WHERE id = ? AND goal_type = 'home'", (record_id,)).fetchone()
        scenario_row = conn.execute("SELECT household_id, created_at FROM scenarios WHERE id = ?", (record_id,)).fetchone()
        if goal_row is None and scenario_row is None:
            return None
        household_id = (goal_row or scenario_row)["household_id"]
        created_at = (goal_row or scenario_row)["created_at"]
        goal = _home_goal_from_scenario(normalized_scenario, goal_id=record_id, household_id=household_id)
        timestamp = now_iso()
        _insert_or_replace_planning_goal(
            conn,
            goal_id=record_id,
            household_id=household_id,
            goal_type="home",
            data=goal,
            created_at=created_at,
            updated_at=timestamp,
        )
        conn.execute(
            "INSERT OR REPLACE INTO scenarios (id, household_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (record_id, household_id, json.dumps(normalized_scenario, ensure_ascii=False), created_at, timestamp),
        )
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return next((record for record in list_scenario_records() if record["id"] == record_id), None)


def delete_scenario_record(record_id: str) -> bool:
    with get_connection() as conn:
        goal_cursor = conn.execute("DELETE FROM planning_goals WHERE id = ? AND goal_type = 'home'", (record_id,))
        scenario_cursor = conn.execute("DELETE FROM scenarios WHERE id = ?", (record_id,))
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return goal_cursor.rowcount > 0 or scenario_cursor.rowcount > 0


def get_calculation_cache(cache_key: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT result FROM calculation_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    try:
        result = json.loads(row["result"])
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def upsert_calculation_cache(cache_key: str, engine_fingerprint: str, result: dict[str, Any]) -> None:
    timestamp = now_iso()
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO calculation_cache (cache_key, engine_fingerprint, result, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                engine_fingerprint = excluded.engine_fingerprint,
                result = excluded.result,
                updated_at = excluded.updated_at
            """,
            (cache_key, engine_fingerprint, payload, timestamp, timestamp),
        )


def _generated_strategy_id(cache_key: str, strategy_type: str, owner_key: str, variant: str) -> str:
    raw = json.dumps(
        {
            "cache_key": cache_key,
            "strategy_type": strategy_type,
            "owner_key": owner_key,
            "variant": variant,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex


def _generated_strategy_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in result.get("purchase_plan_analyses", []):
        if not isinstance(item, dict):
            continue
        variant = str(item.get("variant") or "")
        if not variant:
            continue
        rows.append(
            {
                "strategy_type": "purchase",
                "owner_key": str(item.get("scenario_name") or "selected_scenario"),
                "strategy_key": variant,
                "variant": variant,
                "data": item,
            }
        )

    for item in result.get("car_plan_analyses", []):
        if not isinstance(item, dict):
            continue
        variant = str(item.get("variant") or "")
        if not variant:
            continue
        vehicle_index = _safe_int(item.get("vehicle_index"), 0)
        candidate_index = item.get("vehicle_candidate_index")
        owner_key = f"vehicle:{vehicle_index}:candidate:{candidate_index if candidate_index is not None else 'target'}"
        rows.append(
            {
                "strategy_type": "vehicle",
                "owner_key": owner_key,
                "strategy_key": str(item.get("strategy_key") or variant),
                "variant": variant,
                "data": item,
            }
        )

    for item in result.get("investment_plan_recommendations", []):
        if not isinstance(item, dict):
            continue
        variant = str(item.get("variant") or item.get("plan_name") or "")
        if not variant:
            continue
        rows.append(
            {
                "strategy_type": "investment",
                "owner_key": "household",
                "strategy_key": variant,
                "variant": variant,
                "data": item,
            }
        )

    career_shock_projection = result.get("career_shock_projection")
    if isinstance(career_shock_projection, dict):
        rows.append(
            {
                "strategy_type": "career_shock",
                "owner_key": "household",
                "strategy_key": "auto_projection",
                "variant": "auto_projection",
                "data": career_shock_projection,
            }
        )
    return rows


def upsert_generated_strategies(cache_key: str, engine_fingerprint: str, result: dict[str, Any]) -> None:
    rows = _generated_strategy_rows(result)
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute("DELETE FROM generated_strategies WHERE cache_key = ?", (cache_key,))
        for row in rows:
            strategy_id = _generated_strategy_id(
                cache_key,
                row["strategy_type"],
                row["owner_key"],
                row["variant"],
            )
            conn.execute(
                """
                INSERT INTO generated_strategies (
                    id, cache_key, engine_fingerprint, strategy_type, owner_key,
                    strategy_key, variant, data, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key, strategy_type, owner_key, variant) DO UPDATE SET
                    engine_fingerprint = excluded.engine_fingerprint,
                    strategy_key = excluded.strategy_key,
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (
                    strategy_id,
                    cache_key,
                    engine_fingerprint,
                    row["strategy_type"],
                    row["owner_key"],
                    row["strategy_key"],
                    row["variant"],
                    json.dumps(row["data"], ensure_ascii=False, sort_keys=True),
                    timestamp,
                    timestamp,
                ),
            )


def list_generated_strategies(cache_key: str | None = None, strategy_type: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[str] = []
    if cache_key:
        clauses.append("cache_key = ?")
        params.append(cache_key)
    if strategy_type:
        clauses.append("strategy_type = ?")
        params.append(strategy_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM generated_strategies
            {where}
            ORDER BY strategy_type ASC, owner_key ASC, variant ASC
            """,
            params,
        ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["data"] = json.loads(record["data"])
        records.append(record)
    return records


def latest_source_hash(url: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content_hash FROM source_documents WHERE url = ? ORDER BY fetched_at DESC LIMIT 1",
            (url,),
        ).fetchone()
    return str(row["content_hash"]) if row else None


def insert_source_document(
    *,
    name: str,
    url: str,
    content_hash: str,
    status: str,
    summary: str,
) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    fetched_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO source_documents (id, name, url, fetched_at, content_hash, status, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, name, url, fetched_at, content_hash, status, summary),
        )
        row = conn.execute("SELECT * FROM source_documents WHERE id = ?", (record_id,)).fetchone()
    return dict(row)


def seed_database() -> None:
    if _count("households") == 0:
        insert_record("households", _normalize_household(HouseholdData().model_dump(mode="json")))

    if _count("rule_packs") == 0:
        insert_record("rule_packs", _normalize_rule_pack(RulePackData().model_dump(mode="json")))

    if _count("market_snapshots") == 0:
        insert_record("market_snapshots", _normalize_market_snapshot(MarketSnapshotData().model_dump(mode="json")))
