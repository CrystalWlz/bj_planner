from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .schemas import HouseholdData, MarketSnapshotData, RulePackData, ScenarioData


CURRENT_SCHEMA_VERSION = 3


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
    if not _migration_applied(conn, 1):
        _mark_migration(conn, 1, "baseline json record storage")
    if not _migration_applied(conn, 2):
        _migrate_json_records_to_v2(conn)
        _mark_migration(conn, 2, "add schema_version and account-oriented defaults")
    if not _migration_applied(conn, 3):
        _migrate_json_records_to_v3(conn)
        _mark_migration(conn, 3, "add per-income-stage annual bonus payout month")


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
) -> None:
    rows = conn.execute(f"SELECT id, data FROM {table}").fetchall()
    for row in rows:
        original = _load_json(row["data"])
        migrated = migrate(dict(original))
        if migrated != original:
            conn.execute(
                f"UPDATE {table} SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(migrated, ensure_ascii=False), now_iso(), row["id"]),
            )


def _migrate_household_v2(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = 2
    car_plan = data.get("car_plan")
    if isinstance(car_plan, dict):
        car_plan.setdefault("annual_maintenance_growth_rate", 0.03)
        car_plan.setdefault("annual_insurance_growth_rate", 0.02)
        car_plan.setdefault("second_car_enabled", False)
    data.setdefault("family_down_payment_support_mode", "provident")
    data.setdefault("family_savings_support_amount", 0)
    data.setdefault("investment_buy_fee_rate", 0.0015)
    data.setdefault("investment_sell_fee_rate", 0.005)
    data.setdefault("scheduled_expenses", [])
    data.setdefault("phased_loans", [])
    data.setdefault("elderly_dependents", [])
    return data


def _migrate_scenario_v2(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = 2
    data.setdefault("selected_purchase_plan_variant", "")
    return data


def _migrate_rule_pack_v2(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = 2
    params = data.setdefault("params", {})
    if isinstance(params, dict):
        params.setdefault("backend_parallel_workers", 4)
        params.setdefault("provident_post_purchase_strategy_mode", "auto")
        params.setdefault("provident_post_purchase_cashflow_enabled", False)
        params.setdefault("provident_repayment_capacity_enabled", True)
        params.setdefault("provident_repayment_income_ratio", 0.60)
        params.setdefault("provident_basic_living_cost_per_person", 1778)
    return data


def _migrate_market_snapshot_v2(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = 2
    return data


def _migrate_json_records_to_v2(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v2)
    _update_table_json(conn, "scenarios", _migrate_scenario_v2)
    _update_table_json(conn, "rule_packs", _migrate_rule_pack_v2)
    _update_table_json(conn, "market_snapshots", _migrate_market_snapshot_v2)


def _migrate_household_v3(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    for member in data.get("members", []):
        if not isinstance(member, dict):
            continue
        for stage in member.get("income_stages", []):
            if isinstance(stage, dict):
                stage.setdefault("annual_bonus_payout_month", 4)
    return data


def _set_schema_version_v3(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    return data


def _migrate_json_records_to_v3(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v3)
    _update_table_json(conn, "scenarios", _set_schema_version_v3)
    _update_table_json(conn, "rule_packs", _set_schema_version_v3)
    _update_table_json(conn, "market_snapshots", _set_schema_version_v3)


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
        insert_record("households", HouseholdData().model_dump(mode="json"))

    if _count("scenarios") == 0:
        insert_record("scenarios", ScenarioData().model_dump(mode="json"))

    if _count("rule_packs") == 0:
        insert_record("rule_packs", RulePackData().model_dump(mode="json"))

    if _count("market_snapshots") == 0:
        insert_record("market_snapshots", MarketSnapshotData().model_dump(mode="json"))
