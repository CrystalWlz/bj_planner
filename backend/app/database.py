from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import uuid
import zlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .core_objects import (
    core_object_record_id as _core_object_record_id,
    derive_core_objects_for_household as _derive_core_objects_for_household,
    derive_core_objects_for_planning_goals as _derive_core_objects_for_planning_goals,
)
from .domain.planning_goals import resolve_planning_sequence
from .generated_strategies import generated_strategy_rows
from .storage.normalization import (
    child_goal_from_plan as _child_goal_from_plan,
    child_plan_from_goal as _child_plan_from_goal,
    home_goal_from_scenario as _home_goal_from_scenario,
    normalize_household as _normalize_household,
    normalize_market_snapshot as _normalize_market_snapshot,
    normalize_planning_goal as _normalize_planning_goal,
    normalize_rule_pack as _normalize_rule_pack,
    normalize_scenario as _normalize_scenario,
    safe_int as _safe_int,
    scenario_from_home_goal as _scenario_from_home_goal,
    vehicle_goal_from_plan as _vehicle_goal_from_plan,
    vehicle_plan_from_goal as _vehicle_plan_from_goal,
)
from .storage.schema_version import CURRENT_SCHEMA_VERSION
from .schemas import CacheLayerHashes, HouseholdData, MarketSnapshotData, PlanningGoalRecord, RulePackData


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

            CREATE TABLE IF NOT EXISTS core_objects (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                object_type TEXT NOT NULL,
                category TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_core_objects_household_type
                ON core_objects(household_id, object_type);

            CREATE INDEX IF NOT EXISTS idx_core_objects_category
                ON core_objects(category);

            CREATE INDEX IF NOT EXISTS idx_core_objects_owner
                ON core_objects(household_id, json_extract(data, '$.owner_key'), object_type, category);

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

            CREATE TABLE IF NOT EXISTS quant_investment_policies (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_quant_investment_policies_household
                ON quant_investment_policies(household_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS investment_instruments (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_investment_instruments_household
                ON investment_instruments(household_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS investment_market_snapshots (
                id TEXT PRIMARY KEY,
                instrument_id TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                source TEXT NOT NULL,
                dataset_hash TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(instrument_id, dataset_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_investment_market_snapshots_instrument
                ON investment_market_snapshots(instrument_id, snapshot_date DESC);

            CREATE TABLE IF NOT EXISTS quant_investment_proposals (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_quant_investment_proposals_household
                ON quant_investment_proposals(household_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS paper_investment_orders (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(proposal_id, instrument_id)
            );

            CREATE INDEX IF NOT EXISTS idx_paper_investment_orders_household
                ON paper_investment_orders(household_id, updated_at DESC);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_investment_orders_client_order_id
                ON paper_investment_orders(json_extract(data, '$.client_order_id'))
                WHERE json_extract(data, '$.client_order_id') IS NOT NULL
                  AND json_extract(data, '$.client_order_id') <> '';

            CREATE TABLE IF NOT EXISTS paper_investment_fills (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                order_id TEXT NOT NULL UNIQUE,
                proposal_id TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_paper_investment_fills_household
                ON paper_investment_fills(household_id, created_at ASC);

            CREATE TABLE IF NOT EXISTS paper_investment_order_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(order_id, event_type)
            );

            CREATE INDEX IF NOT EXISTS idx_paper_investment_order_events_household
                ON paper_investment_order_events(household_id, created_at ASC);

            CREATE TABLE IF NOT EXISTS quant_backtest_runs (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                data_fingerprint TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(household_id, data_fingerprint)
            );

            CREATE INDEX IF NOT EXISTS idx_quant_backtest_runs_household
                ON quant_backtest_runs(household_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS broker_reconciliation_runs (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                adapter TEXT NOT NULL,
                reconciliation_date TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_broker_reconciliation_runs_household
                ON broker_reconciliation_runs(household_id, reconciliation_date DESC, created_at DESC);

            CREATE TABLE IF NOT EXISTS property_valuations (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                planning_goal_id TEXT NOT NULL,
                valuation_date TEXT NOT NULL,
                market_snapshot_id TEXT NOT NULL DEFAULT '',
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(planning_goal_id, valuation_date)
            );

            CREATE INDEX IF NOT EXISTS idx_property_valuations_household_goal
                ON property_valuations(household_id, planning_goal_id, valuation_date DESC);

            CREATE TABLE IF NOT EXISTS personal_pension_return_snapshots (
                id TEXT PRIMARY KEY,
                snapshot_date TEXT NOT NULL UNIQUE,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personal_pension_return_snapshots_date
                ON personal_pension_return_snapshots(snapshot_date DESC);

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
                input_hash TEXT NOT NULL DEFAULT '',
                strategy_hash TEXT NOT NULL DEFAULT '',
                ledger_hash TEXT NOT NULL DEFAULT '',
                visualization_hash TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_calculation_cache_layers
                ON calculation_cache(engine_fingerprint, input_hash, strategy_hash, ledger_hash, visualization_hash);

            CREATE TABLE IF NOT EXISTS generated_strategies (
                id TEXT PRIMARY KEY,
                cache_key TEXT NOT NULL,
                engine_fingerprint TEXT NOT NULL,
                input_hash TEXT NOT NULL DEFAULT '',
                strategy_hash TEXT NOT NULL DEFAULT '',
                ledger_hash TEXT NOT NULL DEFAULT '',
                visualization_hash TEXT NOT NULL DEFAULT '',
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

            CREATE INDEX IF NOT EXISTS idx_generated_strategies_layers
                ON generated_strategies(engine_fingerprint, input_hash, strategy_hash, ledger_hash, visualization_hash, strategy_type);

            CREATE INDEX IF NOT EXISTS idx_generated_strategies_owner
                ON generated_strategies(strategy_type, owner_key, engine_fingerprint);

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


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> bool:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    changed = False
    for column_name, column_sql in columns.items():
        if column_name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_sql}")
        changed = True
    return changed


def _ensure_versioned_investment_market_snapshots(conn: sqlite3.Connection) -> bool:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(investment_market_snapshots)").fetchall()}
    if "dataset_hash" in columns:
        return False
    rows = conn.execute("SELECT * FROM investment_market_snapshots").fetchall()
    conn.executescript(
        """
        CREATE TABLE investment_market_snapshots_next (
            id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            source TEXT NOT NULL,
            dataset_hash TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(instrument_id, dataset_hash)
        );
        """
    )
    for row in rows:
        data = _load_json(row["data"])
        dataset_hash = str(data.get("dataset_hash") or row["id"])
        conn.execute(
            """
            INSERT INTO investment_market_snapshots_next
                (id, instrument_id, snapshot_date, source, dataset_hash, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (row["id"], row["instrument_id"], row["snapshot_date"], row["source"], dataset_hash, row["data"], row["created_at"], row["updated_at"]),
        )
    conn.executescript(
        """
        DROP TABLE investment_market_snapshots;
        ALTER TABLE investment_market_snapshots_next RENAME TO investment_market_snapshots;
        CREATE INDEX idx_investment_market_snapshots_instrument
            ON investment_market_snapshots(instrument_id, snapshot_date DESC, created_at DESC);
        """
    )
    return True


def _normalize_paper_order_cash_contributions(conn: sqlite3.Connection) -> bool:
    changed = False
    rows = conn.execute("SELECT id, data FROM paper_investment_orders").fetchall()
    for row in rows:
        data = _load_json(row["data"])
        try:
            schema_version = int(data.get("schema_version") or 1)
        except (TypeError, ValueError):
            schema_version = 1
        if schema_version >= 2 and "cash_contribution_amount" in data:
            continue
        is_external_buy = (
            str(data.get("side") or "buy") == "buy"
            and str(data.get("funding_source") or "external_contribution") == "external_contribution"
        )
        try:
            order_amount = max(0.0, float(data.get("order_amount") or 0.0))
        except (TypeError, ValueError):
            order_amount = 0.0
        data["schema_version"] = 2
        data["cash_contribution_amount"] = order_amount if is_external_buy else 0.0
        conn.execute(
            "UPDATE paper_investment_orders SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), now_iso(), row["id"]),
        )
        changed = True
    return changed


def migrate_database(conn: sqlite3.Connection) -> None:
    previous_schema_history = _has_previous_schema_history(conn)
    child_count_semantics_migration_pending = not _migration_applied(conn, CURRENT_SCHEMA_VERSION)
    changed = _migrate_home_renovation_fields_to_planning_events(conn)
    changed = _normalize_current_records(conn) or changed
    changed = _migrate_scenario_shadows_to_planning_goals(conn) or changed
    changed = _ensure_versioned_investment_market_snapshots(conn) or changed
    changed = _normalize_paper_order_cash_contributions(conn) or changed
    cache_layer_columns = {
        "input_hash": "TEXT NOT NULL DEFAULT ''",
        "strategy_hash": "TEXT NOT NULL DEFAULT ''",
        "ledger_hash": "TEXT NOT NULL DEFAULT ''",
        "visualization_hash": "TEXT NOT NULL DEFAULT ''",
    }
    changed = _ensure_columns(conn, "calculation_cache", cache_layer_columns) or changed
    changed = _ensure_columns(conn, "generated_strategies", cache_layer_columns) or changed
    for row in conn.execute("SELECT id, data FROM households").fetchall():
        household_id = str(row["id"])
        household = _load_json(row["data"])
        has_vehicle_goals = conn.execute(
            "SELECT 1 FROM planning_goals WHERE household_id = ? AND goal_type = 'vehicle' LIMIT 1",
            (household_id,),
        ).fetchone()
        has_child_goals = conn.execute(
            "SELECT 1 FROM planning_goals WHERE household_id = ? AND goal_type = 'child' LIMIT 1",
            (household_id,),
        ).fetchone()
        car_plan = household.get("car_plan") if isinstance(household.get("car_plan"), dict) else {}
        has_vehicle_plan_source = bool(car_plan.get("vehicle_plans")) if isinstance(car_plan.get("vehicle_plans"), list) else False
        has_child_plan_source = bool(household.get("child_plans")) if isinstance(household.get("child_plans"), list) else False
        if has_vehicle_goals is None and has_vehicle_plan_source:
            _sync_vehicle_goals_from_household(conn, household_id, household)
        if has_child_goals is None and has_child_plan_source:
            _sync_child_goals_from_household(conn, household_id, household)
        shadow_free_household = _without_planning_goal_shadows(household)
        if shadow_free_household != household:
            conn.execute(
                "UPDATE households SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(shadow_free_household, ensure_ascii=False), now_iso(), household_id),
            )
            household = shadow_free_household
            changed = True
        _sync_core_objects_from_household(conn, household_id, household)
    if child_count_semantics_migration_pending:
        changed = _migrate_child_count_to_current_birth_semantics(conn) or changed
    if previous_schema_history or not _migration_applied(conn, CURRENT_SCHEMA_VERSION):
        conn.execute("DELETE FROM schema_migrations")
        _mark_migration(conn, CURRENT_SCHEMA_VERSION, "current schema baseline")
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    elif changed:
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")


def _migrate_home_renovation_fields_to_planning_events(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        "SELECT id, household_id, goal_type, data, created_at FROM planning_goals ORDER BY household_id, created_at, id"
    ).fetchall()
    goals_by_household: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        household_key = str(row["household_id"] or "")
        goals_by_household.setdefault(household_key, []).append(row)
    changed = False
    for household_key, household_goals in goals_by_household.items():
        home_rows = [row for row in household_goals if row["goal_type"] == "home"]
        if not home_rows:
            continue
        renovation_rows = [row for row in household_goals if row["goal_type"] == "renovation"]
        first_home = min(
            home_rows,
            key=lambda row: (
                _safe_int(_load_json(row["data"]).get("priority"), 1),
                str(row["created_at"]),
                str(row["id"]),
            ),
        )
        first_home_data = _load_json(first_home["data"])
        migrated_budget = 0.0
        migrated_funding_mode = "after_goal_saving"
        for row in home_rows:
            data = _load_json(row["data"])
            target = data.get("target_params") if isinstance(data.get("target_params"), dict) else {}
            try:
                migrated_budget = max(migrated_budget, float(target.get("renovation_cost") or 0))
            except (TypeError, ValueError):
                pass
            if target.get("renovation_funding_mode") == "upfront_cash":
                migrated_funding_mode = "cash_or_investment"
            if "renovation_cost" in target or "renovation_funding_mode" in target:
                target.pop("renovation_cost", None)
                target.pop("renovation_funding_mode", None)
                data["target_params"] = target
                conn.execute(
                    "UPDATE planning_goals SET data = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(data, ensure_ascii=False), now_iso(), row["id"]),
                )
                changed = True

        if renovation_rows:
            renovation_row = min(
                renovation_rows,
                key=lambda row: (
                    _safe_int(_load_json(row["data"]).get("priority"), 999),
                    str(row["created_at"]),
                    str(row["id"]),
                ),
            )
            renovation_data = _load_json(renovation_row["data"])
            if str(renovation_data.get("timing_mode") or "auto_sequence") == "auto_sequence" and not renovation_data.get("depends_on_goal_id"):
                renovation_data["timing_mode"] = "after_goal"
                renovation_data["depends_on_goal_id"] = str(first_home["id"])
                renovation_data["priority"] = max(1, _safe_int(first_home_data.get("priority"), 1) + 1)
                conn.execute(
                    "UPDATE planning_goals SET data = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(renovation_data, ensure_ascii=False), now_iso(), renovation_row["id"]),
                )
                changed = True
            continue

        if migrated_budget <= 0:
            continue
        timestamp = now_iso()
        renovation_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"house-planner:renovation-goal:{household_key or 'global'}:{first_home['id']}",
        ).hex
        renovation_data = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "goal_type": "renovation",
            "name": "装修目标",
            "enabled": True,
            "priority": max(1, _safe_int(first_home_data.get("priority"), 1) + 1),
            "timing_mode": "after_goal",
            "earliest_purchase_month": "",
            "earliest_purchase_delay_months": 0,
            "planning_window_start_month": "",
            "planning_window_end_month": "",
            "depends_on_goal_id": str(first_home["id"]),
            "delay_after_dependency_months": 0,
            "allow_parallel": False,
            "selected_strategy_id": "",
            "target_params": {
                "name": "装修目标",
                "estimated_cost": migrated_budget,
                "category": "renovation",
            },
            "financing_preferences": {"funding_mode": migrated_funding_mode},
            "holding_cost_params": {},
            "metadata": {"migrated_from_home_candidates": True},
            "notes": "",
        }
        conn.execute(
            """
            INSERT OR IGNORE INTO planning_goals (
                id, household_id, goal_type, data, created_at, updated_at
            ) VALUES (?, ?, 'renovation', ?, ?, ?)
            """,
            (
                renovation_id,
                household_key or None,
                json.dumps(renovation_data, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        changed = True
    return changed


def _load_json(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _year_month_key(value: Any) -> tuple[int, int] | None:
    raw = str(value or "").strip()
    if len(raw) < 7 or raw[4] != "-":
        return None
    try:
        year = int(raw[:4])
        month = int(raw[5:7])
    except ValueError:
        return None
    return (year, month) if year >= 1900 and 1 <= month <= 12 else None


def _migrate_child_count_to_current_birth_semantics(conn: sqlite3.Connection) -> bool:
    """Repair only the count signature produced by the legacy goal projection."""
    current_month = (datetime.now().year, datetime.now().month)
    changed = False
    for household_row in conn.execute("SELECT id, data FROM households").fetchall():
        household_id = str(household_row["id"])
        household = _load_json(household_row["data"])
        goal_rows = conn.execute(
            "SELECT data FROM planning_goals WHERE household_id = ? AND goal_type = 'child'",
            (household_id,),
        ).fetchall()
        enabled_goals = []
        for goal_row in goal_rows:
            goal = _load_json(goal_row["data"])
            if bool(goal.get("enabled", True)) and str(goal.get("timing_mode") or "") != "not_planned":
                enabled_goals.append(goal)
        if not enabled_goals:
            continue
        born_goal_count = 0
        for goal in enabled_goals:
            target = goal.get("target_params") if isinstance(goal.get("target_params"), dict) else {}
            birth_month = _year_month_key(target.get("birth_month"))
            if birth_month is not None and birth_month <= current_month:
                born_goal_count += 1
        stored_count = _safe_int(household.get("child_count"), 0)
        if stored_count != len(enabled_goals) or born_goal_count >= len(enabled_goals):
            continue
        household["child_count"] = born_goal_count
        conn.execute(
            "UPDATE households SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(household, ensure_ascii=False), now_iso(), household_id),
        )
        changed = True
    return changed


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


def normalize_household_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_household(data)


def normalize_scenario_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_scenario(data)


def normalize_planning_goal_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_planning_goal(data)


def normalize_rule_pack_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_rule_pack(data)


def normalize_market_snapshot_data(data: dict[str, Any]) -> dict[str, Any]:
    return _normalize_market_snapshot(data)


def _normalize_current_records(conn: sqlite3.Connection) -> bool:
    changed = 0
    changed += _update_table_json(conn, "households", _normalize_household)
    changed += _update_table_json(conn, "scenarios", _normalize_scenario)
    changed += _update_table_json(conn, "rule_packs", _normalize_rule_pack)
    changed += _update_table_json(conn, "market_snapshots", _normalize_market_snapshot)
    changed += _update_table_json(conn, "planning_goals", _normalize_planning_goal)
    return changed > 0


def _stable_vehicle_goal_id(household_id: str, index: int, vehicle: dict[str, Any]) -> str:
    existing = vehicle.get("planning_goal_id")
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


def _stable_child_goal_id(household_id: str, index: int, child: dict[str, Any]) -> str:
    existing = child.get("planning_goal_id")
    if existing:
        return str(existing)
    raw = json.dumps(
        {
            "kind": "child_goal",
            "household_id": household_id,
            "index": index,
            "name": child.get("name") or "",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex


def _first_home_goal_id_for_household(conn: sqlite3.Connection, household_id: str) -> str:
    row = conn.execute(
        """
        SELECT id FROM planning_goals
        WHERE goal_type = 'home' AND (household_id = ? OR household_id IS NULL)
        ORDER BY json_extract(data, '$.priority') ASC, created_at ASC, id ASC
        LIMIT 1
        """,
        (household_id,),
    ).fetchone()
    return str(row["id"]) if row else ""


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


def _planning_goal_records_for_core_objects(conn: sqlite3.Connection, household_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM planning_goals
        WHERE household_id IS NULL OR household_id = ?
        ORDER BY json_extract(data, '$.priority') ASC, created_at ASC, id ASC
        """,
        (household_id,),
    ).fetchall()
    return [_row_to_planning_goal_record(row) for row in rows]


def _sync_core_objects_from_household(conn: sqlite3.Connection, household_id: str, household: dict[str, Any]) -> int:
    conn.execute("DELETE FROM core_objects WHERE household_id = ?", (household_id,))
    timestamp = now_iso()
    changed = 0
    payloads = [
        *_derive_core_objects_for_household(household_id, household),
        *_derive_core_objects_for_planning_goals(
            household_id,
            _planning_goal_records_for_core_objects(conn, household_id),
        ),
    ]
    for payload in payloads:
        record_id = _core_object_record_id(
            household_id,
            str(payload.get("object_type")),
            str(payload.get("source")),
            str(payload.get("reference_id")),
            str(payload.get("category")),
        )
        conn.execute(
            """
            INSERT INTO core_objects (id, household_id, object_type, category, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                household_id,
                payload["object_type"],
                payload["category"],
                json.dumps(payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        changed += 1
    return changed


def _sync_core_objects_for_households_affected_by_goal(conn: sqlite3.Connection, household_id: str | None) -> int:
    if household_id:
        rows = conn.execute("SELECT id, data FROM households WHERE id = ?", (household_id,)).fetchall()
    else:
        rows = conn.execute("SELECT id, data FROM households").fetchall()
    changed = 0
    for row in rows:
        changed += _sync_core_objects_from_household(conn, str(row["id"]), _load_json(row["data"]))
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
        conn.execute("DELETE FROM generated_strategies")
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
        row = conn.execute(f"SELECT data FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        if _load_json(row["data"]) == data:
            return get_record(table, record_id)
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


_QUANT_SCOPED_TABLES = {
    "quant_investment_policies",
    "investment_instruments",
    "quant_investment_proposals",
}


def _quant_scoped_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = _load_json(record["data"])
    return record


def insert_quant_scoped_record(table: str, *, household_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if table not in _QUANT_SCOPED_TABLES:
        raise ValueError(f"Unsupported quant scoped table: {table}")
    record_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO {table} (id, household_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (record_id, household_id, json.dumps(data, ensure_ascii=False), timestamp, timestamp),
        )
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise RuntimeError("Quant scoped record insert failed")
    return _quant_scoped_record(row)


def update_quant_scoped_record(table: str, record_id: str, *, household_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if table not in _QUANT_SCOPED_TABLES:
        raise ValueError(f"Unsupported quant scoped table: {table}")
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ? AND household_id = ?", (record_id, household_id)).fetchone()
        if row is None:
            return None
        if _load_json(row["data"]) != data:
            conn.execute(
                f"UPDATE {table} SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(data, ensure_ascii=False), timestamp, record_id),
            )
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return _quant_scoped_record(row) if row else None


def list_quant_scoped_records(table: str, *, household_id: str) -> list[dict[str, Any]]:
    if table not in _QUANT_SCOPED_TABLES:
        raise ValueError(f"Unsupported quant scoped table: {table}")
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE household_id = ? ORDER BY updated_at DESC, created_at DESC",
            (household_id,),
        ).fetchall()
    return [_quant_scoped_record(row) for row in rows]


def delete_quant_scoped_record(table: str, record_id: str, *, household_id: str) -> bool:
    if table not in _QUANT_SCOPED_TABLES:
        raise ValueError(f"Unsupported quant scoped table: {table}")
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM {table} WHERE id = ? AND household_id = ?", (record_id, household_id))
    return cursor.rowcount > 0


def bump_quant_investment_data_version(household_id: str) -> None:
    """Invalidate affordability input cache when a selected local market input changes."""
    with get_connection() as conn:
        row = conn.execute("SELECT data FROM households WHERE id = ?", (household_id,)).fetchone()
        if row is None:
            return
        household = _load_json(row["data"])
        household["quant_investment_data_version"] = max(0, int(household.get("quant_investment_data_version") or 0)) + 1
        normalized = _normalize_household(household)
        conn.execute(
            "UPDATE households SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(normalized, ensure_ascii=False), now_iso(), household_id),
        )


def upsert_investment_market_snapshot(
    *,
    instrument_id: str,
    snapshot_date: str,
    source: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    dataset_hash = str(data.get("dataset_hash") or uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(data, ensure_ascii=False, sort_keys=True)).hex)
    record_id = uuid.uuid5(uuid.NAMESPACE_URL, f"house-planner:investment-market:{instrument_id}:{dataset_hash}").hex
    timestamp = now_iso()
    payload = json.dumps(data, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO investment_market_snapshots (id, instrument_id, snapshot_date, source, dataset_hash, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_id, dataset_hash) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (record_id, instrument_id, snapshot_date, source, dataset_hash, payload, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM investment_market_snapshots WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise RuntimeError("Investment market snapshot upsert failed")
    return _quant_market_snapshot_record(row)


def _quant_market_snapshot_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = _load_json(record["data"])
    return record


def list_investment_market_snapshots(*, instrument_ids: list[str]) -> list[dict[str, Any]]:
    if not instrument_ids:
        return []
    placeholders = ", ".join("?" for _ in instrument_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM investment_market_snapshots
            WHERE instrument_id IN ({placeholders})
            ORDER BY snapshot_date DESC, updated_at DESC
            """,
            instrument_ids,
        ).fetchall()
    latest_by_instrument: dict[str, sqlite3.Row] = {}
    for row in rows:
        latest_by_instrument.setdefault(str(row["instrument_id"]), row)
    return [_quant_market_snapshot_record(row) for row in latest_by_instrument.values()]


def insert_paper_investment_order(*, household_id: str, proposal_id: str, instrument_id: str, data: dict[str, Any]) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM paper_investment_orders WHERE proposal_id = ? AND instrument_id = ?",
            (proposal_id, instrument_id),
        ).fetchone()
        if existing is not None:
            return _paper_order_record(existing)
        conn.execute(
            """
            INSERT INTO paper_investment_orders (id, household_id, proposal_id, instrument_id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, household_id, proposal_id, instrument_id, json.dumps(data, ensure_ascii=False), timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM paper_investment_orders WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise RuntimeError("Paper investment order insert failed")
    return _paper_order_record(row)


def _paper_order_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = _load_json(record["data"])
    return record


def list_paper_investment_orders(*, household_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_investment_orders WHERE household_id = ? ORDER BY updated_at DESC, created_at DESC",
            (household_id,),
        ).fetchall()
    return [_paper_order_record(row) for row in rows]


def update_paper_investment_order(record_id: str, *, household_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM paper_investment_orders WHERE id = ? AND household_id = ?",
            (record_id, household_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE paper_investment_orders SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), timestamp, record_id),
        )
        row = conn.execute("SELECT * FROM paper_investment_orders WHERE id = ?", (record_id,)).fetchone()
    return _paper_order_record(row) if row else None


def paper_order_is_persisted(
    record_id: str,
    *,
    household_id: str,
    client_order_id: str,
) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data FROM paper_investment_orders WHERE id = ? AND household_id = ?",
            (record_id, household_id),
        ).fetchone()
    if row is None:
        return False
    data = _load_json(row["data"])
    return str(data.get("client_order_id") or "") == client_order_id


def _insert_paper_order_event(
    conn: sqlite3.Connection,
    *,
    household_id: str,
    order_id: str,
    data: dict[str, Any],
    timestamp: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO paper_investment_order_events
            (id, household_id, order_id, event_type, data, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            household_id,
            order_id,
            str(data["event_type"]),
            json.dumps(data, ensure_ascii=False),
            timestamp,
        ),
    )


def request_paper_order_cancel(
    record_id: str,
    *,
    household_id: str,
    reason: str,
) -> tuple[dict[str, Any] | None, str]:
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM paper_investment_orders WHERE id = ? AND household_id = ?",
            (record_id, household_id),
        ).fetchone()
        if row is None:
            return None, "not_found"
        data = _load_json(row["data"])
        status = str(data.get("status") or "proposed")
        if status == "cancelled":
            return _paper_order_record(row), "already_cancelled"
        if status == "cancel_requested":
            return _paper_order_record(row), "already_requested"
        if status != "proposed":
            return _paper_order_record(row), "not_cancellable"
        client_order_id = str(data.get("client_order_id") or "")
        event_data = {
            "schema_version": 1,
            "order_id": record_id,
            "client_order_id": client_order_id,
            "event_type": "cancel_requested",
            "from_status": status,
            "to_status": "cancel_requested",
            "reason": reason,
        }
        data["status"] = "cancel_requested"
        conn.execute(
            "UPDATE paper_investment_orders SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), timestamp, record_id),
        )
        _insert_paper_order_event(
            conn,
            household_id=household_id,
            order_id=record_id,
            data=event_data,
            timestamp=timestamp,
        )
        row = conn.execute("SELECT * FROM paper_investment_orders WHERE id = ?", (record_id,)).fetchone()
    return (_paper_order_record(row) if row else None), "requested"


def confirm_paper_order_cancel(
    record_id: str,
    *,
    household_id: str,
    reason: str,
) -> tuple[dict[str, Any] | None, str]:
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM paper_investment_orders WHERE id = ? AND household_id = ?",
            (record_id, household_id),
        ).fetchone()
        if row is None:
            return None, "not_found"
        data = _load_json(row["data"])
        status = str(data.get("status") or "proposed")
        if status == "cancelled":
            return _paper_order_record(row), "already_cancelled"
        if status != "cancel_requested":
            return _paper_order_record(row), "not_requested"
        event_data = {
            "schema_version": 1,
            "order_id": record_id,
            "client_order_id": str(data.get("client_order_id") or ""),
            "event_type": "cancelled",
            "from_status": status,
            "to_status": "cancelled",
            "reason": reason,
        }
        data["status"] = "cancelled"
        conn.execute(
            "UPDATE paper_investment_orders SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), timestamp, record_id),
        )
        _insert_paper_order_event(
            conn,
            household_id=household_id,
            order_id=record_id,
            data=event_data,
            timestamp=timestamp,
        )
        row = conn.execute("SELECT * FROM paper_investment_orders WHERE id = ?", (record_id,)).fetchone()
    return (_paper_order_record(row) if row else None), "cancelled"


def list_paper_order_events(*, household_id: str, order_id: str | None = None) -> list[dict[str, Any]]:
    clauses = ["household_id = ?"]
    params: list[Any] = [household_id]
    if order_id:
        clauses.append("order_id = ?")
        params.append(order_id)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM paper_investment_order_events
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at ASC, id ASC
            """,
            params,
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["data"] = _load_json(record["data"])
        result.append(record)
    return result


def record_paper_fill_atomic(
    order_id: str,
    *,
    household_id: str,
    order_data: dict[str, Any],
    fill_data: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Persist the simulated order state and immutable fill in one transaction."""
    timestamp = now_iso()
    with get_connection() as conn:
        order_row = conn.execute(
            "SELECT * FROM paper_investment_orders WHERE id = ? AND household_id = ?",
            (order_id, household_id),
        ).fetchone()
        if order_row is None:
            return None, None
        fill_row = conn.execute(
            "SELECT * FROM paper_investment_fills WHERE order_id = ? AND household_id = ?",
            (order_id, household_id),
        ).fetchone()
        if fill_row is None:
            persisted_order_data = _load_json(order_row["data"])
            persisted_status = str(persisted_order_data.get("status") or "proposed")
            if persisted_status not in {"proposed", "simulated"}:
                return _paper_order_record(order_row), None
            conn.execute(
                "UPDATE paper_investment_orders SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(order_data, ensure_ascii=False), timestamp, order_id),
            )
            fill_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO paper_investment_fills
                    (id, household_id, order_id, proposal_id, instrument_id, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_id,
                    household_id,
                    order_id,
                    str(fill_data["proposal_id"]),
                    str(fill_data["instrument_id"]),
                    json.dumps(fill_data, ensure_ascii=False),
                    timestamp,
                ),
            )
        order_row = conn.execute("SELECT * FROM paper_investment_orders WHERE id = ?", (order_id,)).fetchone()
        fill_row = conn.execute("SELECT * FROM paper_investment_fills WHERE order_id = ?", (order_id,)).fetchone()
    return (
        _paper_order_record(order_row) if order_row else None,
        _paper_fill_record(fill_row) if fill_row else None,
    )


def _paper_fill_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = _load_json(record["data"])
    return record


def list_paper_investment_fills(*, household_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_investment_fills WHERE household_id = ? ORDER BY created_at ASC, id ASC",
            (household_id,),
        ).fetchall()
    return [_paper_fill_record(row) for row in rows]


def upsert_quant_backtest_run(
    *,
    household_id: str,
    policy_id: str,
    data_fingerprint: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM quant_backtest_runs WHERE household_id = ? AND data_fingerprint = ?",
            (household_id, data_fingerprint),
        ).fetchone()
        if row is None:
            record_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO quant_backtest_runs
                    (id, household_id, policy_id, data_fingerprint, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    household_id,
                    policy_id,
                    data_fingerprint,
                    json.dumps(data, ensure_ascii=False),
                    timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM quant_backtest_runs WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise RuntimeError("Quant backtest run upsert failed")
    return _quant_backtest_run_record(row)


def _quant_backtest_run_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = _load_json(record["data"])
    return record


def list_quant_backtest_runs(*, household_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM quant_backtest_runs WHERE household_id = ? ORDER BY created_at DESC, id DESC",
            (household_id,),
        ).fetchall()
    return [_quant_backtest_run_record(row) for row in rows]


def insert_broker_reconciliation_run(
    *,
    household_id: str,
    adapter: str,
    reconciliation_date: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO broker_reconciliation_runs
                (id, household_id, adapter, reconciliation_date, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                household_id,
                adapter,
                reconciliation_date,
                json.dumps(data, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute("SELECT * FROM broker_reconciliation_runs WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise RuntimeError("Broker reconciliation run insert failed")
    return _broker_reconciliation_run_record(row)


def _broker_reconciliation_run_record(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["data"] = _load_json(record["data"])
    return record


def list_broker_reconciliation_runs(*, household_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM broker_reconciliation_runs
            WHERE household_id = ?
            ORDER BY reconciliation_date DESC, created_at DESC, id DESC
            """,
            (household_id,),
        ).fetchall()
    return [_broker_reconciliation_run_record(row) for row in rows]


def resolve_broker_reconciliation_run(
    record_id: str,
    *,
    household_id: str,
    review_note: str,
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM broker_reconciliation_runs WHERE id = ? AND household_id = ?",
            (record_id, household_id),
        ).fetchone()
        if row is None:
            return None
        data = _load_json(row["data"])
        if data.get("review_status") != "pending":
            return _broker_reconciliation_run_record(row)
        data["review_status"] = "resolved"
        data["freeze_new_orders"] = False
        data["reviewed_at"] = timestamp
        data["review_note"] = review_note
        conn.execute(
            "UPDATE broker_reconciliation_runs SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), timestamp, record_id),
        )
        row = conn.execute("SELECT * FROM broker_reconciliation_runs WHERE id = ?", (record_id,)).fetchone()
    return _broker_reconciliation_run_record(row) if row else None


def list_property_valuations(
    *,
    household_id: str,
    planning_goal_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["household_id = ?"]
    params = [household_id]
    if planning_goal_id:
        clauses.append("planning_goal_id = ?")
        params.append(planning_goal_id)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM property_valuations
            WHERE {' AND '.join(clauses)}
            ORDER BY valuation_date DESC, created_at DESC
            """,
            params,
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def latest_property_valuation(
    *,
    household_id: str,
    planning_goal_id: str,
) -> dict[str, Any] | None:
    records = list_property_valuations(
        household_id=household_id,
        planning_goal_id=planning_goal_id,
    )
    return records[0] if records else None


def upsert_property_valuation(
    *,
    household_id: str,
    planning_goal_id: str,
    valuation_date: str,
    market_snapshot_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_iso()
    record_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"house-planner:property-valuation:{planning_goal_id}:{valuation_date}",
    ).hex
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO property_valuations (
                id, household_id, planning_goal_id, valuation_date,
                market_snapshot_id, data, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(planning_goal_id, valuation_date) DO UPDATE SET
                household_id = excluded.household_id,
                market_snapshot_id = excluded.market_snapshot_id,
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (
                record_id,
                household_id,
                planning_goal_id,
                valuation_date,
                market_snapshot_id,
                payload,
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute("SELECT * FROM property_valuations WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise RuntimeError("Property valuation upsert failed")
    return _row_to_record(row)


def list_personal_pension_return_snapshots() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM personal_pension_return_snapshots ORDER BY snapshot_date DESC, updated_at DESC"
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def latest_personal_pension_return_snapshot() -> dict[str, Any] | None:
    records = list_personal_pension_return_snapshots()
    return records[0] if records else None


def upsert_personal_pension_return_snapshot(
    *,
    snapshot_date: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_iso()
    record_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"house-planner:personal-pension-return:{snapshot_date}",
    ).hex
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO personal_pension_return_snapshots (id, snapshot_date, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (record_id, snapshot_date, json.dumps(data, ensure_ascii=False, sort_keys=True), timestamp, timestamp),
        )
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        row = conn.execute(
            "SELECT * FROM personal_pension_return_snapshots WHERE snapshot_date = ?",
            (snapshot_date,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Personal pension return snapshot upsert failed")
    return _row_to_record(row)


def list_core_object_records(
    *,
    household_id: str | None = None,
    object_type: str | None = None,
    category: str | None = None,
    owner_key: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[str] = []
    if household_id is not None:
        clauses.append("household_id = ?")
        params.append(household_id)
    if object_type is not None:
        clauses.append("object_type = ?")
        params.append(object_type)
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if owner_key is not None:
        clauses.append("json_extract(data, '$.owner_key') = ?")
        params.append(owner_key)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM core_objects
            {where}
            ORDER BY object_type ASC, category ASC, json_extract(data, '$.name') ASC
            """,
            params,
        ).fetchall()
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


def _resolved_goal_sequence_index(
    goals: list[dict[str, Any]],
    *,
    household_id: str | None = None,
) -> dict[str, int]:
    scoped_goals = [
        goal
        for goal in goals
        if goal.get("household_id") in ({None, ""} if household_id is None else {None, household_id})
    ]
    sequence = resolve_planning_sequence([PlanningGoalRecord.model_validate(goal) for goal in scoped_goals])
    return {goal.id: goal.sequence_index for goal in sequence.goals}


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
            ORDER BY json_extract(data, '$.priority') ASC, created_at ASC, id ASC
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
        _sync_core_objects_for_households_affected_by_goal(conn, household_id)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return get_planning_goal_record(record_id)


def update_planning_goal_record(
    record_id: str,
    data: dict[str, Any],
    household_id: str | None = None,
    *,
    preserve_household_when_omitted: bool = True,
) -> dict[str, Any] | None:
    normalized = _normalize_planning_goal(data)
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM planning_goals WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        previous_household_id = str(row["household_id"] or "") or None
        previous_goal_type = str(row["goal_type"] or "")
        previous_goal_data = _load_json(row["data"])
        effective_household_id = previous_household_id if preserve_household_when_omitted else household_id
        next_goal_type = str(normalized.get("goal_type") or "home")
        if (
            previous_household_id == effective_household_id
            and previous_goal_type == next_goal_type
            and previous_goal_data == normalized
        ):
            return _row_to_planning_goal_record(row)
        timestamp = now_iso()
        if (
            previous_household_id
            and previous_goal_type in {"vehicle", "child"}
            and (previous_goal_type != next_goal_type or previous_household_id != effective_household_id)
        ):
            _remove_deleted_planning_goal_from_household(
                conn,
                previous_household_id,
                record_id,
                previous_goal_type,
                previous_goal_data,
            )
        _insert_or_replace_planning_goal(
            conn,
            goal_id=record_id,
            household_id=effective_household_id,
            goal_type=next_goal_type,
            data=normalized,
            created_at=row["created_at"],
            updated_at=timestamp,
        )
        if previous_goal_type == "home" and next_goal_type != "home":
            conn.execute("DELETE FROM scenarios WHERE id = ?", (record_id,))
        affected_household_ids = {previous_household_id, effective_household_id}
        for affected_household_id in affected_household_ids:
            _sync_core_objects_for_households_affected_by_goal(conn, affected_household_id)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return get_planning_goal_record(record_id)


def delete_planning_goal_record(record_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT household_id, goal_type, data FROM planning_goals WHERE id = ?", (record_id,)).fetchone()
        cursor = conn.execute("DELETE FROM planning_goals WHERE id = ?", (record_id,))
        household_id = str(row["household_id"] or "") if row else ""
        goal_type = str(row["goal_type"] or "") if row else ""
        goal_data = _load_json(row["data"]) if row else {}
        if cursor.rowcount > 0 and goal_type == "home":
            conn.execute("DELETE FROM scenarios WHERE id = ?", (record_id,))
        if cursor.rowcount > 0 and household_id and goal_type in {"vehicle", "child"}:
            _remove_deleted_planning_goal_from_household(conn, household_id, record_id, goal_type, goal_data)
        _sync_core_objects_for_households_affected_by_goal(conn, household_id or None)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return cursor.rowcount > 0


def _remove_deleted_planning_goal_from_household(
    conn: sqlite3.Connection,
    household_id: str,
    goal_id: str,
    goal_type: str,
    goal_data: dict[str, Any],
) -> None:
    row = conn.execute("SELECT data FROM households WHERE id = ?", (household_id,)).fetchone()
    if row is None:
        return
    household = _load_json(row["data"])
    changed = False
    if goal_type == "vehicle":
        car_plan = household.get("car_plan") if isinstance(household.get("car_plan"), dict) else {}
        vehicles = car_plan.get("vehicle_plans") if isinstance(car_plan.get("vehicle_plans"), list) else []
        next_vehicles = [
            vehicle
            for index, vehicle in enumerate(vehicles)
            if not _household_vehicle_matches_deleted_goal(household_id, index, vehicle, goal_id, goal_data)
        ]
        if len(next_vehicles) != len(vehicles):
            car_plan["vehicle_plans"] = next_vehicles
            car_plan["enabled"] = any(bool(vehicle.get("enabled")) for vehicle in next_vehicles if isinstance(vehicle, dict))
            household["car_plan"] = car_plan
            changed = True
    elif goal_type == "child":
        child_plans = household.get("child_plans") if isinstance(household.get("child_plans"), list) else []
        next_children = [
            child
            for index, child in enumerate(child_plans)
            if not _household_child_matches_deleted_goal(household_id, index, child, goal_id, goal_data)
        ]
        if len(next_children) != len(child_plans):
            household["child_plans"] = next_children
            changed = True
    if not changed:
        return
    conn.execute(
        "UPDATE households SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(_normalize_household(household), ensure_ascii=False), now_iso(), household_id),
    )


def _household_vehicle_matches_deleted_goal(
    household_id: str,
    index: int,
    vehicle: object,
    goal_id: str,
    goal_data: dict[str, Any],
) -> bool:
    if not isinstance(vehicle, dict):
        return False
    if str(vehicle.get("planning_goal_id") or "") == goal_id:
        return True
    if _stable_vehicle_goal_id(household_id, index, vehicle) == goal_id:
        return True
    goal_name = str(goal_data.get("name") or "")
    target = goal_data.get("target_params") if isinstance(goal_data.get("target_params"), dict) else {}
    return bool(goal_name) and str(vehicle.get("name") or target.get("name") or "") == goal_name


def _household_child_matches_deleted_goal(
    household_id: str,
    index: int,
    child: object,
    goal_id: str,
    goal_data: dict[str, Any],
) -> bool:
    if not isinstance(child, dict):
        return False
    if str(child.get("planning_goal_id") or "") == goal_id:
        return True
    if _stable_child_goal_id(household_id, index, child) == goal_id:
        return True
    goal_name = str(goal_data.get("name") or "")
    target = goal_data.get("target_params") if isinstance(goal_data.get("target_params"), dict) else {}
    return bool(goal_name) and str(child.get("name") or target.get("name") or "") == goal_name


def get_planning_goal_record(record_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM planning_goals WHERE id = ?", (record_id,)).fetchone()
    return _row_to_planning_goal_record(row) if row else None


def _vehicle_goals_for_household(household_id: str) -> list[dict[str, Any]]:
    return [
        _row_to_planning_goal_record(row)
        for row in _planning_goal_rows(household_id=household_id, goal_type="vehicle")
    ]


def _child_goals_for_household(household_id: str) -> list[dict[str, Any]]:
    return [
        _row_to_planning_goal_record(row)
        for row in _planning_goal_rows(household_id=household_id, goal_type="child")
    ]


def _project_vehicle_goals_into_household(record: dict[str, Any]) -> dict[str, Any]:
    household_id = str(record["id"])
    data = deepcopy(record["data"])
    vehicle_goals = _vehicle_goals_for_household(household_id)
    car_plan = data.get("car_plan") if isinstance(data.get("car_plan"), dict) else {}
    has_goal_backed_vehicle_plans = any(
        isinstance(vehicle, dict) and bool(vehicle.get("planning_goal_id"))
        for vehicle in (car_plan.get("vehicle_plans") if isinstance(car_plan.get("vehicle_plans"), list) else [])
    )
    if vehicle_goals or has_goal_backed_vehicle_plans:
        sequence_index_by_id = _resolved_goal_sequence_index(
            list_planning_goal_records(),
            household_id=household_id,
        )
        vehicles = [
            _vehicle_plan_from_goal(
                goal["id"],
                goal["data"],
                index,
                sequence_index=sequence_index_by_id.get(str(goal["id"])),
            )
            for index, goal in enumerate(vehicle_goals)
        ]
        if not isinstance(car_plan, dict):
            car_plan = {}
            data["car_plan"] = car_plan
        car_plan["vehicle_plans"] = vehicles
        car_plan["enabled"] = any(bool(vehicle.get("enabled")) for vehicle in vehicles)
    record = deepcopy(record)
    record["data"] = _normalize_household(data)
    return record


def _project_child_goals_into_household(record: dict[str, Any]) -> dict[str, Any]:
    household_id = str(record["id"])
    data = deepcopy(record["data"])
    child_goals = _child_goals_for_household(household_id)
    has_goal_backed_child_plans = any(
        isinstance(child, dict) and bool(child.get("planning_goal_id"))
        for child in (data.get("child_plans") if isinstance(data.get("child_plans"), list) else [])
    )
    if child_goals or has_goal_backed_child_plans:
        projected_children = [
            _child_plan_from_goal(goal["id"], goal["data"], index)
            for index, goal in enumerate(child_goals)
        ]
        data["child_plans"] = projected_children
    record = deepcopy(record)
    record["data"] = _normalize_household(data)
    return record


def _project_planning_goals_into_household(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    projected = _project_vehicle_goals_into_household(record)
    return _project_child_goals_into_household(projected)


def _vehicle_plan_items_from_household(household: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(household, dict):
        return []
    car_plan = household.get("car_plan") if isinstance(household.get("car_plan"), dict) else {}
    vehicles = car_plan.get("vehicle_plans") if isinstance(car_plan.get("vehicle_plans"), list) else []
    return [vehicle for vehicle in vehicles if isinstance(vehicle, dict)]


def _child_plan_items_from_household(household: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(household, dict):
        return []
    children = household.get("child_plans") if isinstance(household.get("child_plans"), list) else []
    return [child for child in children if isinstance(child, dict)]


def _without_planning_goal_shadows(household: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(household)
    car_plan = normalized.get("car_plan") if isinstance(normalized.get("car_plan"), dict) else {}
    car_plan["vehicle_plans"] = []
    normalized["car_plan"] = car_plan
    normalized["child_plans"] = []
    return normalized


def _ingest_unlinked_household_goal_shadows(
    conn: sqlite3.Connection,
    household_id: str,
    household: dict[str, Any],
) -> None:
    """Import legacy, unlinked goal lists once without accepting projected goals as a write source."""
    vehicles = _vehicle_plan_items_from_household(household)
    if vehicles and all(not str(vehicle.get("planning_goal_id") or "").strip() for vehicle in vehicles):
        existing = conn.execute(
            "SELECT 1 FROM planning_goals WHERE household_id = ? AND goal_type = 'vehicle' LIMIT 1",
            (household_id,),
        ).fetchone()
        if existing is None:
            _sync_vehicle_goals_from_household(conn, household_id, household)

    children = _child_plan_items_from_household(household)
    if children and all(not str(child.get("planning_goal_id") or "").strip() for child in children):
        existing = conn.execute(
            "SELECT 1 FROM planning_goals WHERE household_id = ? AND goal_type = 'child' LIMIT 1",
            (household_id,),
        ).fetchone()
        if existing is None:
            _sync_child_goals_from_household(conn, household_id, household)


def _empty_shadow_list_is_stale(
    current_items: list[dict[str, Any]],
    previous_items: list[dict[str, Any]],
    previous_household: dict[str, Any] | None,
) -> bool:
    return previous_household is not None and not current_items and not previous_items


def _sync_vehicle_goals_from_household(
    conn: sqlite3.Connection,
    household_id: str,
    household: dict[str, Any],
    *,
    previous_household: dict[str, Any] | None = None,
) -> int:
    vehicles = _vehicle_plan_items_from_household(household)
    previous_vehicles = _vehicle_plan_items_from_household(previous_household)
    if _empty_shadow_list_is_stale(vehicles, previous_vehicles, previous_household):
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return 0

    conn.execute("DELETE FROM planning_goals WHERE household_id = ? AND goal_type = 'vehicle'", (household_id,))
    changed = 0
    for index, vehicle in enumerate(vehicles):
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


def _sync_child_goals_from_household(
    conn: sqlite3.Connection,
    household_id: str,
    household: dict[str, Any],
    *,
    previous_household: dict[str, Any] | None = None,
) -> int:
    children = _child_plan_items_from_household(household)
    previous_children = _child_plan_items_from_household(previous_household)
    if _empty_shadow_list_is_stale(children, previous_children, previous_household):
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return 0

    conn.execute("DELETE FROM planning_goals WHERE household_id = ? AND goal_type = 'child'", (household_id,))
    first_home_goal_id = _first_home_goal_id_for_household(conn, household_id)
    changed = 0
    for index, child in enumerate(children):
        goal_id = _stable_child_goal_id(household_id, index, child)
        goal_data = _child_goal_from_plan(
            child,
            household_id=household_id,
            index=index,
            goal_id=goal_id,
            first_home_goal_id=first_home_goal_id,
        )
        _insert_or_replace_planning_goal(
            conn,
            goal_id=goal_id,
            household_id=household_id,
            goal_type="child",
            data=goal_data,
        )
        changed += 1
    conn.execute("DELETE FROM calculation_cache")
    conn.execute("DELETE FROM generated_strategies")
    return changed


def _migrate_scenario_shadows_to_planning_goals(conn: sqlite3.Connection) -> bool:
    """Promote any legacy scenario rows before removing the obsolete shadow table data."""
    rows = conn.execute("SELECT id, household_id, data, created_at, updated_at FROM scenarios").fetchall()
    changed = False
    for row in rows:
        goal_exists = conn.execute(
            "SELECT 1 FROM planning_goals WHERE id = ? AND goal_type = 'home'",
            (row["id"],),
        ).fetchone()
        if goal_exists is not None:
            continue
        scenario = _normalize_scenario(_load_json(row["data"]))
        goal = _home_goal_from_scenario(
            scenario,
            goal_id=str(row["id"]),
            household_id=row["household_id"],
        )
        _insert_or_replace_planning_goal(
            conn,
            goal_id=str(row["id"]),
            household_id=row["household_id"],
            goal_type="home",
            data=goal,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        changed = True
    if rows:
        conn.execute("DELETE FROM scenarios")
        changed = True
    return changed


def list_household_records() -> list[dict[str, Any]]:
    return [
        projected for record in list_records("households")
        if (projected := _project_planning_goals_into_household(record)) is not None
    ]


def insert_household_record(data: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_household(data)
    record = insert_record("households", _without_planning_goal_shadows(normalized))
    with get_connection() as conn:
        _ingest_unlinked_household_goal_shadows(conn, str(record["id"]), normalized)
        _sync_core_objects_from_household(conn, str(record["id"]), record["data"])
    saved = get_record("households", str(record["id"]))
    return _project_planning_goals_into_household(saved)


def update_household_record(record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    incoming = _normalize_household(data)
    normalized = _without_planning_goal_shadows(incoming)
    record = update_record("households", record_id, normalized)
    if record is None:
        return None
    with get_connection() as conn:
        _ingest_unlinked_household_goal_shadows(conn, record_id, incoming)
        _sync_core_objects_from_household(conn, record_id, normalized)
    saved = get_record("households", record_id)
    return _project_planning_goals_into_household(saved)


def list_scenario_records(household_id: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    all_goals = list_planning_goal_records()
    goals = [
        goal for goal in all_goals
        if goal.get("goal_type") == "home"
        and (household_id is None or goal.get("household_id") in {None, household_id})
    ]
    sequence_index_by_household: dict[str, dict[str, int]] = {}
    scoped_sequence_index = (
        _resolved_goal_sequence_index(all_goals, household_id=household_id)
        if household_id is not None
        else None
    )
    for goal in goals:
        household_key = str(goal.get("household_id") or "")
        if scoped_sequence_index is not None:
            sequence_index = scoped_sequence_index.get(str(goal["id"]))
        elif household_key not in sequence_index_by_household:
            sequence_index_by_household[household_key] = _resolved_goal_sequence_index(
                all_goals,
                household_id=household_key or None,
            )
            sequence_index = sequence_index_by_household[household_key].get(str(goal["id"]))
        else:
            sequence_index = sequence_index_by_household[household_key].get(str(goal["id"]))
        scenario = _scenario_from_home_goal(
            goal["id"],
            goal["data"],
            sequence_index=sequence_index,
        )
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
        _sync_core_objects_for_households_affected_by_goal(conn, household_id)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return next(record for record in list_scenario_records() if record["id"] == record_id)


def update_scenario_record(record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    normalized_scenario = _normalize_scenario(data)
    with get_connection() as conn:
        goal_row = conn.execute("SELECT household_id, created_at FROM planning_goals WHERE id = ? AND goal_type = 'home'", (record_id,)).fetchone()
        if goal_row is None:
            return None
        household_id = goal_row["household_id"]
        created_at = goal_row["created_at"]
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
        _sync_core_objects_for_households_affected_by_goal(conn, household_id)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return next((record for record in list_scenario_records() if record["id"] == record_id), None)


def delete_scenario_record(record_id: str) -> bool:
    with get_connection() as conn:
        goal_cursor = conn.execute("DELETE FROM planning_goals WHERE id = ? AND goal_type = 'home'", (record_id,))
        _sync_core_objects_for_households_affected_by_goal(conn, None)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return goal_cursor.rowcount > 0


def get_calculation_cache(cache_key: str) -> dict[str, Any] | None:
    payload = get_calculation_cache_payload(cache_key)
    if payload is None:
        return None
    try:
        result = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def get_calculation_cache_payload(cache_key: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT result FROM calculation_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    payload = row["result"]
    if not isinstance(payload, str):
        return None
    if payload.startswith("zlib:"):
        try:
            compressed = base64.b64decode(payload[5:].encode("ascii"), validate=True)
            payload = zlib.decompress(compressed).decode("utf-8")
        except (ValueError, UnicodeDecodeError, zlib.error):
            return None
    return payload if payload.strip().startswith("{") else None


def generated_strategies_exist_for_cache(cache_key: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM generated_strategies WHERE cache_key = ? LIMIT 1",
            (cache_key,),
        ).fetchone()
    return row is not None


def upsert_calculation_cache(
    cache_key: str,
    engine_fingerprint: str,
    cache_layers: CacheLayerHashes,
    result: dict[str, Any],
) -> None:
    timestamp = now_iso()
    raw_payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    payload = raw_payload
    if len(raw_payload) >= 64 * 1024:
        payload = "zlib:" + base64.b64encode(zlib.compress(raw_payload.encode("utf-8"), level=6)).decode("ascii")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO calculation_cache (
                cache_key, engine_fingerprint, input_hash, strategy_hash,
                ledger_hash, visualization_hash, result, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                engine_fingerprint = excluded.engine_fingerprint,
                input_hash = excluded.input_hash,
                strategy_hash = excluded.strategy_hash,
                ledger_hash = excluded.ledger_hash,
                visualization_hash = excluded.visualization_hash,
                result = excluded.result,
                updated_at = excluded.updated_at
            """,
            (
                cache_key,
                engine_fingerprint,
                cache_layers.input,
                cache_layers.strategy,
                cache_layers.ledger,
                cache_layers.visualization,
                payload,
                timestamp,
                timestamp,
            ),
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


def upsert_generated_strategies(
    cache_key: str,
    engine_fingerprint: str,
    cache_layers: CacheLayerHashes,
    result: dict[str, Any],
) -> None:
    rows = generated_strategy_rows(result)
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
                    id, cache_key, engine_fingerprint, input_hash, strategy_hash,
                    ledger_hash, visualization_hash, strategy_type, owner_key,
                    strategy_key, variant, data, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key, strategy_type, owner_key, variant) DO UPDATE SET
                    engine_fingerprint = excluded.engine_fingerprint,
                    input_hash = excluded.input_hash,
                    strategy_hash = excluded.strategy_hash,
                    ledger_hash = excluded.ledger_hash,
                    visualization_hash = excluded.visualization_hash,
                    strategy_key = excluded.strategy_key,
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (
                    strategy_id,
                    cache_key,
                    engine_fingerprint,
                    cache_layers.input,
                    cache_layers.strategy,
                    cache_layers.ledger,
                    cache_layers.visualization,
                    row["strategy_type"],
                    row["owner_key"],
                    row["strategy_key"],
                    row["variant"],
                    json.dumps(row["data"], ensure_ascii=False, sort_keys=True),
                    timestamp,
                    timestamp,
                ),
            )


def list_generated_strategies(
    cache_key: str | None = None,
    strategy_type: str | None = None,
    owner_key: str | None = None,
    *,
    engine_fingerprint: str | None = None,
    input_hash: str | None = None,
    strategy_hash: str | None = None,
    ledger_hash: str | None = None,
    visualization_hash: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[str] = []
    if cache_key:
        clauses.append("cache_key = ?")
        params.append(cache_key)
    if strategy_type:
        clauses.append("strategy_type = ?")
        params.append(strategy_type)
    if owner_key:
        clauses.append("owner_key = ?")
        params.append(owner_key)
    if engine_fingerprint:
        clauses.append("engine_fingerprint = ?")
        params.append(engine_fingerprint)
    if input_hash:
        clauses.append("input_hash = ?")
        params.append(input_hash)
    if strategy_hash:
        clauses.append("strategy_hash = ?")
        params.append(strategy_hash)
    if ledger_hash:
        clauses.append("ledger_hash = ?")
        params.append(ledger_hash)
    if visualization_hash:
        clauses.append("visualization_hash = ?")
        params.append(visualization_hash)
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
    return _generated_strategy_records_from_rows(rows)


def _generated_strategy_records_from_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["data"] = json.loads(record["data"])
        records.append(record)
    return records


def list_generated_strategies_for_cache_layers(
    cache_layers: list[CacheLayerHashes],
    strategy_type: str | None = None,
    owner_key: str | None = None,
    *,
    engine_fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    unique_layers = set()
    for layers in cache_layers:
        layer_engine = engine_fingerprint or layers.engine
        if not (
            layer_engine
            and layers.input
            and layers.strategy
            and layers.ledger
            and layers.visualization
        ):
            continue
        unique_layers.add(
            (
                layer_engine,
                layers.input,
                layers.strategy,
                layers.ledger,
                layers.visualization,
            )
        )
    if not unique_layers:
        return []

    clauses: list[str] = []
    params: list[str] = []
    if strategy_type:
        clauses.append("strategy_type = ?")
        params.append(strategy_type)
    if owner_key:
        clauses.append("owner_key = ?")
        params.append(owner_key)

    layer_clauses: list[str] = []
    for layer_engine, input_hash, strategy_hash, ledger_hash, visualization_hash in sorted(unique_layers):
        layer_clauses.append(
            "(engine_fingerprint = ? AND input_hash = ? AND strategy_hash = ? AND ledger_hash = ? AND visualization_hash = ?)"
        )
        params.extend([layer_engine, input_hash, strategy_hash, ledger_hash, visualization_hash])
    clauses.append(f"({' OR '.join(layer_clauses)})")
    where = f"WHERE {' AND '.join(clauses)}"

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM generated_strategies
            {where}
            ORDER BY strategy_type ASC, owner_key ASC, variant ASC
            """,
            params,
        ).fetchall()
    records_by_id = {
        record["id"]: record
        for record in _generated_strategy_records_from_rows(rows)
    }
    return sorted(
        records_by_id.values(),
        key=lambda item: (
            str(item.get("strategy_type") or ""),
            str(item.get("owner_key") or ""),
            str(item.get("variant") or ""),
        ),
    )


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

    with get_connection() as conn:
        for row in conn.execute("SELECT id, data FROM households").fetchall():
            _sync_core_objects_from_household(conn, str(row["id"]), _load_json(row["data"]))
