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

from .storage.normalization import (
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
from .schemas import (
    HouseholdData,
    MarketSnapshotData,
    RulePackData,
)


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


def upsert_calculation_cache(cache_key: str, engine_fingerprint: str, result: dict[str, Any]) -> None:
    timestamp = now_iso()
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
