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


def migrate_database(conn: sqlite3.Connection) -> None:
    previous_schema_history = _has_previous_schema_history(conn)
    changed = _normalize_current_records(conn)
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
        _sync_core_objects_from_household(conn, household_id, household)
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
        row = conn.execute("SELECT household_id, goal_type, data, created_at FROM planning_goals WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        previous_household_id = str(row["household_id"] or "") or None
        previous_goal_type = str(row["goal_type"] or "")
        previous_goal_data = _load_json(row["data"])
        effective_household_id = previous_household_id if preserve_household_when_omitted else household_id
        next_goal_type = str(normalized.get("goal_type") or "home")
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
        data["child_count"] = sum(1 for child in projected_children if bool(child.get("enabled")))
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


def list_household_records() -> list[dict[str, Any]]:
    return [
        projected for record in list_records("households")
        if (projected := _project_planning_goals_into_household(record)) is not None
    ]


def insert_household_record(data: dict[str, Any]) -> dict[str, Any]:
    record = insert_record("households", _normalize_household(data))
    with get_connection() as conn:
        _sync_vehicle_goals_from_household(conn, str(record["id"]), record["data"])
        _sync_child_goals_from_household(conn, str(record["id"]), record["data"])
        _sync_core_objects_from_household(conn, str(record["id"]), record["data"])
    saved = get_record("households", str(record["id"]))
    return _project_planning_goals_into_household(saved)


def update_household_record(record_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    previous_record = get_record("households", record_id)
    previous_household = deepcopy(previous_record["data"]) if previous_record is not None else None
    normalized = _normalize_household(data)
    record = update_record("households", record_id, normalized)
    if record is None:
        return None
    with get_connection() as conn:
        _sync_vehicle_goals_from_household(conn, record_id, normalized, previous_household=previous_household)
        _sync_child_goals_from_household(conn, record_id, normalized, previous_household=previous_household)
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
        conn.execute(
            "INSERT OR REPLACE INTO scenarios (id, household_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (record_id, household_id, json.dumps(normalized_scenario, ensure_ascii=False), timestamp, timestamp),
        )
        _sync_core_objects_for_households_affected_by_goal(conn, household_id)
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
        _sync_core_objects_for_households_affected_by_goal(conn, household_id)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
    return next((record for record in list_scenario_records() if record["id"] == record_id), None)


def delete_scenario_record(record_id: str) -> bool:
    with get_connection() as conn:
        goal_cursor = conn.execute("DELETE FROM planning_goals WHERE id = ? AND goal_type = 'home'", (record_id,))
        scenario_cursor = conn.execute("DELETE FROM scenarios WHERE id = ?", (record_id,))
        _sync_core_objects_for_households_affected_by_goal(conn, None)
        conn.execute("DELETE FROM calculation_cache")
        conn.execute("DELETE FROM generated_strategies")
        return goal_cursor.rowcount > 0 or scenario_cursor.rowcount > 0


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
    return payload if isinstance(payload, str) and payload.strip().startswith("{") else None


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
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
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
