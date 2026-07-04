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

from .schemas import HouseholdData, MarketSnapshotData, RulePackData, ScenarioData


CURRENT_SCHEMA_VERSION = 18


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

            CREATE TABLE IF NOT EXISTS calculation_cache (
                cache_key TEXT PRIMARY KEY,
                engine_fingerprint TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
    legacy_history = _has_legacy_migration_history(conn)
    changed = _normalize_current_records(conn)
    if legacy_history or not _migration_applied(conn, CURRENT_SCHEMA_VERSION):
        conn.execute("DELETE FROM schema_migrations")
        _mark_migration(conn, CURRENT_SCHEMA_VERSION, "current schema baseline")
        conn.execute("DELETE FROM calculation_cache")
    elif changed:
        conn.execute("DELETE FROM calculation_cache")


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


def _has_legacy_migration_history(conn: sqlite3.Connection) -> bool:
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


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _vehicle_from_legacy_car_plan(car_plan: dict[str, Any], *, name: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "name": name,
        "selected_strategy_variant": car_plan.get("selected_strategy_variant") or "手动设置",
        "candidate_vehicles": [],
        "total_price": max(0, _safe_float(car_plan.get("total_price"))),
        "down_payment_ratio": _clamp(_safe_float(car_plan.get("down_payment_ratio"), 0.5), 0, 1),
        "down_payment": max(0, _safe_float(car_plan.get("down_payment"))),
        "purchase_delay_months": max(0, _safe_int(car_plan.get("purchase_delay_months"), 0)),
        "total_months": max(1, _safe_int(car_plan.get("total_months"), 60)),
        "interest_free_months": max(0, _safe_int(car_plan.get("interest_free_months"), 24)),
        "later_annual_rate": max(0, _safe_float(car_plan.get("later_annual_rate"), 0.0199)),
        "loan_prepayment_enabled": bool(car_plan.get("loan_prepayment_enabled", False)),
        "loan_prepayment_start_month": max(1, _safe_int(car_plan.get("loan_prepayment_start_month"), 1)),
        "loan_prepayment_allowed_after_month": max(1, _safe_int(car_plan.get("loan_prepayment_allowed_after_month"), 12)),
        "loan_prepayment_monthly_amount": max(0, _safe_float(car_plan.get("loan_prepayment_monthly_amount"))),
        "current_month_index": max(1, _safe_int(car_plan.get("current_month_index"), 1)),
        "saving_start_date": car_plan.get("saving_start_date") or "2026-07-01",
        "monthly_operating_cost": max(0, _safe_float(car_plan.get("monthly_operating_cost"))),
        "no_car_monthly_commute_cost": max(0, _safe_float(car_plan.get("no_car_monthly_commute_cost"))),
        "annual_mileage_km": max(0, _safe_float(car_plan.get("annual_mileage_km"))),
        "electricity_kwh_per_100km": max(0, _safe_float(car_plan.get("electricity_kwh_per_100km"), 14)),
        "electricity_price_per_kwh": max(0, _safe_float(car_plan.get("electricity_price_per_kwh"), 0.8)),
        "monthly_parking_cost": max(0, _safe_float(car_plan.get("monthly_parking_cost"))),
        "annual_maintenance_cost": max(0, _safe_float(car_plan.get("annual_maintenance_cost"))),
        "annual_maintenance_growth_rate": max(0, _safe_float(car_plan.get("annual_maintenance_growth_rate"), 0.03)),
        "annual_insurance_rate": max(0, _safe_float(car_plan.get("annual_insurance_rate"), 0.018)),
        "annual_insurance_min": max(0, _safe_float(car_plan.get("annual_insurance_min"))),
        "annual_insurance_growth_rate": max(0, _safe_float(car_plan.get("annual_insurance_growth_rate"), 0.02)),
        "depreciation_years": max(1, _safe_int(car_plan.get("depreciation_years"), 8)),
        "vehicle_service_years": max(1, _safe_int(car_plan.get("vehicle_service_years"), 15)),
        "vehicle_retirement_mileage_km": max(0, _safe_float(car_plan.get("vehicle_retirement_mileage_km"), 600000)),
        "happiness_score": _clamp(_safe_float(car_plan.get("happiness_score"), 6.5), 0, 10),
        "notes": car_plan.get("notes") or "",
    }


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
    candidates = vehicle.get("candidate_vehicles")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                _fill_vehicle_prepayment_defaults(candidate)


def _normalize_car_plan(data: dict[str, Any]) -> None:
    car_plan = data.setdefault("car_plan", {})
    if not isinstance(car_plan, dict):
        data["car_plan"] = {}
        return
    car_plan.setdefault("annual_maintenance_growth_rate", 0.03)
    car_plan.setdefault("annual_insurance_growth_rate", 0.02)

    existing = car_plan.get("vehicle_plans")
    vehicle_plans = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    if not vehicle_plans:
        if bool(car_plan.get("enabled")) and _safe_float(car_plan.get("total_price")) > 0:
            vehicle_plans.append(_vehicle_from_legacy_car_plan(car_plan, name=car_plan.get("name") or "车辆 1"))
        if bool(car_plan.get("second_car_enabled")) and _safe_float(car_plan.get("second_car_total_price")) > 0:
            second = _vehicle_from_legacy_car_plan(car_plan, name="车辆 2")
            second["selected_strategy_variant"] = "手动设置"
            second["total_price"] = max(0, _safe_float(car_plan.get("second_car_total_price")))
            second["down_payment_ratio"] = _clamp(_safe_float(car_plan.get("second_car_down_payment_ratio"), 0.4), 0, 1)
            second["down_payment"] = second["total_price"] * second["down_payment_ratio"]
            second["purchase_delay_months"] = max(0, _safe_int(car_plan.get("second_car_purchase_delay_months"), 60))
            second["total_months"] = max(1, _safe_int(car_plan.get("second_car_total_months"), 60))
            second["interest_free_months"] = max(0, _safe_int(car_plan.get("second_car_interest_free_months"), 24))
            second["later_annual_rate"] = max(0, _safe_float(car_plan.get("second_car_later_annual_rate"), 0.0199))
            second["annual_mileage_km"] = max(0, _safe_float(car_plan.get("second_car_annual_mileage_km")))
            second["monthly_parking_cost"] = max(0, _safe_float(car_plan.get("second_car_monthly_parking_cost")))
            vehicle_plans.append(second)

    for index, vehicle in enumerate(vehicle_plans):
        if not isinstance(vehicle, dict):
            continue
        candidates = vehicle.get("candidate_vehicles")
        candidate_vehicles = [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []
        if not candidate_vehicles and bool(vehicle.get("enabled")) and _safe_float(vehicle.get("total_price")) > 0:
            candidate_vehicles = [_strip_nested_vehicle_candidates(vehicle)]
        for candidate in candidate_vehicles:
            candidate.setdefault("enabled", True)
            candidate.setdefault("selected_strategy_variant", "手动设置")
            candidate.setdefault("candidate_vehicles", [])
            _fill_vehicle_timing_defaults(candidate, index)
            _fill_vehicle_prepayment_defaults(candidate)
        vehicle["candidate_vehicles"] = candidate_vehicles
        _fill_vehicle_timing_defaults(vehicle, index)
        _fill_vehicle_prepayment_defaults(vehicle)

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

    legacy_birth_months = [str(career_shock.get("self_birth_month") or ""), str(career_shock.get("spouse_birth_month") or "")]
    legacy_current_ages = [_safe_int(career_shock.get("self_current_age"), 30), _safe_int(career_shock.get("spouse_current_age"), 30)]
    legacy_retirement_ages = [_safe_int(career_shock.get("self_retirement_age"), 63), _safe_int(career_shock.get("spouse_retirement_age"), 58)]
    legacy_pensions = [_safe_float(career_shock.get("self_pension_monthly")), _safe_float(career_shock.get("spouse_pension_monthly"))]
    legacy_layoff_member = str(career_shock.get("layoff_member_name") or "")
    legacy_layoff_age = _safe_int(career_shock.get("layoff_age"), 35)
    legacy_global_enabled = bool(career_shock.get("enabled"))

    existing_settings = career_shock.get("member_settings")
    existing_by_name: dict[str, dict[str, Any]] = {}
    if isinstance(existing_settings, list):
        for item in existing_settings:
            if isinstance(item, dict):
                existing_by_name[str(item.get("member_name") or "")] = item

    next_settings: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            continue
        name = str(member.get("name") or f"成员 {index + 1}")
        member.setdefault("birth_month", legacy_birth_months[index] if index < len(legacy_birth_months) else "")
        member.setdefault("current_age", legacy_current_ages[index] if index < len(legacy_current_ages) else 30)
        legacy_retirement_age = legacy_retirement_ages[index] if index < len(legacy_retirement_ages) else 63
        member.setdefault("retirement_category", _retirement_category_from_age(legacy_retirement_age, index))
        for stage in member.get("income_stages", []):
            if isinstance(stage, dict):
                stage.setdefault("stage_kind", "salary")
                stage.setdefault("annual_bonus_payout_month", 4)
                stage.setdefault("monthly_freelance_income", 0)
        existing = existing_by_name.get(name, {})
        member_enabled = bool(existing.get("enabled")) if existing else legacy_global_enabled and name == legacy_layoff_member
        next_settings.append(
            {
                "member_name": name,
                "enabled": member_enabled,
                "layoff_age": _safe_int(existing.get("layoff_age") if existing else legacy_layoff_age, legacy_layoff_age),
                "retirement_age": _policy_retirement_age(str(member.get("retirement_category") or "male_60")),
                "pension_monthly": _safe_float(
                    existing.get("pension_monthly")
                    if existing
                    else (legacy_pensions[index] if index < len(legacy_pensions) else 0)
                ),
                "auto_pension_monthly": bool(existing.get("auto_pension_monthly", True)) if existing else True,
            }
        )

    career_shock["enabled"] = any(bool(item.get("enabled")) for item in next_settings)
    career_shock["member_settings"] = next_settings
    career_shock.setdefault("auto_flexible_housing_fund", True)
    career_shock.setdefault("auto_pension_income", True)
    career_shock.setdefault("self_housing_fund_monthly", 0)
    for legacy_key in (
        "layoff_member_name",
        "layoff_age",
        "self_birth_month",
        "spouse_birth_month",
        "self_current_age",
        "spouse_current_age",
        "self_retirement_age",
        "spouse_retirement_age",
        "self_pension_monthly",
        "spouse_pension_monthly",
    ):
        career_shock.pop(legacy_key, None)


def _normalize_household(data: dict[str, Any]) -> dict[str, Any]:
    if "cash_account_balance" not in data and "liquid_assets" in data:
        data["cash_account_balance"] = data.get("liquid_assets") or 0
    data.pop("liquid_assets", None)
    data.setdefault("family_down_payment_support_mode", "provident")
    data.setdefault("family_savings_support_amount", 0)
    data.setdefault("investment_buy_fee_rate", 0.0015)
    data.setdefault("investment_sell_fee_rate", 0.005)
    data.setdefault("scheduled_expenses", [])
    data.setdefault("phased_loans", [])
    data.setdefault("elderly_dependents", [])
    data.setdefault("property_goals", [])
    _normalize_car_plan(data)
    _normalize_members_and_career_shock(data)
    normalized = HouseholdData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def _normalize_scenario(data: dict[str, Any]) -> dict[str, Any]:
    if _safe_float(data.get("provident_rate")) == 0.0285:
        data["provident_rate"] = 0.026
    data.setdefault("selected_purchase_plan_variant", "")
    data.setdefault("enabled", True)
    data.setdefault("purchase_sequence", 1)
    data.setdefault("purchase_planning_mode", "after_previous_purchase")
    data.setdefault("after_previous_purchase_delay_months", 0)
    data.setdefault("investment_withdrawal_mode", "auto")
    data.setdefault("investment_min_balance_after_purchase", 0)
    data.setdefault("commercial_prepayment_enabled", False)
    data.setdefault("commercial_prepayment_start_month", 1)
    data.setdefault("commercial_prepayment_allowed_after_month", 12)
    data.setdefault("commercial_prepayment_monthly_amount", 0)
    normalized = ScenarioData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


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


def _normalize_market_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    normalized = MarketSnapshotData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def _normalize_current_records(conn: sqlite3.Connection) -> bool:
    changed = 0
    changed += _update_table_json(conn, "households", _normalize_household)
    changed += _update_table_json(conn, "scenarios", _normalize_scenario)
    changed += _update_table_json(conn, "rule_packs", _normalize_rule_pack)
    changed += _update_table_json(conn, "market_snapshots", _normalize_market_snapshot)
    return changed > 0


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
