from __future__ import annotations

import json
import os
import sqlite3
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .schemas import HouseholdData, MarketSnapshotData, RulePackData, ScenarioData


CURRENT_SCHEMA_VERSION = 13


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
    if not _migration_applied(conn, 1):
        _mark_migration(conn, 1, "baseline json record storage")
    if not _migration_applied(conn, 2):
        _migrate_json_records_to_v2(conn)
        _mark_migration(conn, 2, "add schema_version and account-oriented defaults")
    if not _migration_applied(conn, 3):
        _migrate_json_records_to_v3(conn)
        _mark_migration(conn, 3, "add per-income-stage annual bonus payout month")
    if not _migration_applied(conn, 4):
        _migrate_json_records_to_v4(conn)
        _mark_migration(conn, 4, "add per-member provident account balances")
    if not _migration_applied(conn, 5):
        _migrate_json_records_to_v5(conn)
        _mark_migration(conn, 5, "rename household liquid assets input to cash account balance")
    if not _migration_applied(conn, 6):
        _migrate_json_records_to_v6(conn)
        _mark_migration(conn, 6, "add calculation result cache")
    if not _migration_applied(conn, 7):
        _migrate_json_records_to_v7(conn)
        _mark_migration(conn, 7, "refresh Beijing provident loan defaults")
    if not _migration_applied(conn, 8):
        _migrate_json_records_to_v8(conn)
        _mark_migration(conn, 8, "normalize vehicle plans and add purchase goal container")
    if not _migration_applied(conn, 9):
        _migrate_json_records_to_v9(conn)
        _mark_migration(conn, 9, "add vehicle source candidates for car planning")
    if not _migration_applied(conn, 10):
        _migrate_json_records_to_v10(conn)
        _mark_migration(conn, 10, "add optional property targets and multi-home planning mode")
    if not _migration_applied(conn, 11):
        _migrate_json_records_to_v11(conn)
        _mark_migration(conn, 11, "add vehicle purchase event sequencing fields")
    if not _migration_applied(conn, 12):
        _migrate_json_records_to_v12(conn)
        _mark_migration(conn, 12, "add home purchase investment withdrawal strategy fields")
    if not _migration_applied(conn, 13):
        _migrate_json_records_to_v13(conn)
        _mark_migration(conn, 13, "move member age and career shock settings to household members")


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
        migrated = migrate(deepcopy(original))
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


def _migrate_household_v4(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    members = data.get("members")
    if not isinstance(members, list) or not members:
        return data
    explicit_total = 0.0
    for member in members:
        if isinstance(member, dict):
            explicit_total += max(0.0, float(member.get("provident_fund_balance") or 0))
    if explicit_total > 0:
        for member in members:
            if isinstance(member, dict):
                member.setdefault("provident_fund_balance", 0)
        return data

    household_balance = max(0.0, float(data.get("provident_fund_balance") or 0))
    weights: list[float] = []
    for member in members:
        if not isinstance(member, dict):
            weights.append(0.0)
            continue
        stages = member.get("income_stages")
        first_stage = stages[0] if isinstance(stages, list) and stages and isinstance(stages[0], dict) else {}
        weight = float(first_stage.get("monthly_housing_fund") or member.get("monthly_housing_fund") or 0)
        weights.append(max(0.0, weight))
    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1.0 for _ in members]
        total_weight = float(len(members))
    for index, member in enumerate(members):
        if isinstance(member, dict):
            member["provident_fund_balance"] = round(household_balance * weights[index] / total_weight, 2)
    return data


def _set_schema_version_current(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    return data


def _migrate_json_records_to_v4(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v4)
    _update_table_json(conn, "scenarios", _set_schema_version_current)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _migrate_household_v5(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    if "cash_account_balance" not in data and "liquid_assets" in data:
        data["cash_account_balance"] = data.get("liquid_assets") or 0
    data.pop("liquid_assets", None)
    return data


def _migrate_json_records_to_v5(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v5)
    _update_table_json(conn, "scenarios", _set_schema_version_current)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _migrate_json_records_to_v6(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calculation_cache (
            cache_key TEXT PRIMARY KEY,
            engine_fingerprint TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    _update_table_json(conn, "households", _set_schema_version_current)
    _update_table_json(conn, "scenarios", _set_schema_version_current)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _migrate_scenario_v7(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    if float(data.get("provident_rate") or 0) == 0.0285:
        data["provident_rate"] = 0.026
    return data


def _migrate_rule_pack_v7(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    params = data.setdefault("params", {})
    if isinstance(params, dict):
        if float(params.get("second_home_provident_min_down_payment_ratio") or 0) < 0.30:
            params["second_home_provident_min_down_payment_ratio"] = 0.30
        params.setdefault("provident_first_home_rate_1_to_5_years", 0.021)
        params.setdefault("provident_first_home_rate_6_to_30_years", 0.026)
        params.setdefault("provident_second_home_rate_1_to_5_years", 0.02325)
        params.setdefault("provident_second_home_rate_6_to_30_years", 0.03075)
    return data


def _migrate_json_records_to_v7(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _set_schema_version_current)
    _update_table_json(conn, "scenarios", _migrate_scenario_v7)
    _update_table_json(conn, "rule_packs", _migrate_rule_pack_v7)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _vehicle_from_legacy_car_plan(car_plan: dict[str, Any], *, name: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "name": name,
        "selected_strategy_variant": car_plan.get("selected_strategy_variant") or "手动设置",
        "candidate_vehicles": [],
        "total_price": max(0, float(car_plan.get("total_price") or 0)),
        "down_payment_ratio": min(1, max(0, float(car_plan.get("down_payment_ratio") or 0.5))),
        "down_payment": max(0, float(car_plan.get("down_payment") or 0)),
        "purchase_delay_months": max(0, int(car_plan.get("purchase_delay_months") or 0)),
        "total_months": max(1, int(car_plan.get("total_months") or 60)),
        "interest_free_months": max(0, int(car_plan.get("interest_free_months") or 24)),
        "later_annual_rate": max(0, float(car_plan.get("later_annual_rate") or 0.0199)),
        "current_month_index": max(1, int(car_plan.get("current_month_index") or 1)),
        "saving_start_date": car_plan.get("saving_start_date") or "2026-07-01",
        "monthly_operating_cost": max(0, float(car_plan.get("monthly_operating_cost") or 0)),
        "no_car_monthly_commute_cost": max(0, float(car_plan.get("no_car_monthly_commute_cost") or 0)),
        "annual_mileage_km": max(0, float(car_plan.get("annual_mileage_km") or 0)),
        "electricity_kwh_per_100km": max(0, float(car_plan.get("electricity_kwh_per_100km") or 14)),
        "electricity_price_per_kwh": max(0, float(car_plan.get("electricity_price_per_kwh") or 0.8)),
        "monthly_parking_cost": max(0, float(car_plan.get("monthly_parking_cost") or 0)),
        "annual_maintenance_cost": max(0, float(car_plan.get("annual_maintenance_cost") or 0)),
        "annual_maintenance_growth_rate": max(0, float(car_plan.get("annual_maintenance_growth_rate") or 0.03)),
        "annual_insurance_rate": max(0, float(car_plan.get("annual_insurance_rate") or 0.018)),
        "annual_insurance_min": max(0, float(car_plan.get("annual_insurance_min") or 0)),
        "annual_insurance_growth_rate": max(0, float(car_plan.get("annual_insurance_growth_rate") or 0.02)),
        "depreciation_years": max(1, int(car_plan.get("depreciation_years") or 8)),
        "vehicle_service_years": max(1, int(car_plan.get("vehicle_service_years") or 15)),
        "vehicle_retirement_mileage_km": max(0, float(car_plan.get("vehicle_retirement_mileage_km") or 600000)),
        "happiness_score": min(10, max(0, float(car_plan.get("happiness_score") or 6.5))),
        "notes": car_plan.get("notes") or "",
    }


def _migrate_household_v8(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    car_plan = data.setdefault("car_plan", {})
    if isinstance(car_plan, dict):
        existing = car_plan.get("vehicle_plans")
        vehicle_plans = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
        if not vehicle_plans:
            if bool(car_plan.get("enabled")) and float(car_plan.get("total_price") or 0) > 0:
                vehicle_plans.append(_vehicle_from_legacy_car_plan(car_plan, name=car_plan.get("name") or "车辆 1"))
            if bool(car_plan.get("second_car_enabled")) and float(car_plan.get("second_car_total_price") or 0) > 0:
                second = _vehicle_from_legacy_car_plan(car_plan, name="车辆 2")
                second["selected_strategy_variant"] = "手动设置"
                second["total_price"] = max(0, float(car_plan.get("second_car_total_price") or 0))
                second["down_payment_ratio"] = min(1, max(0, float(car_plan.get("second_car_down_payment_ratio") or 0.4)))
                second["down_payment"] = second["total_price"] * second["down_payment_ratio"]
                second["purchase_delay_months"] = max(0, int(car_plan.get("second_car_purchase_delay_months") or 60))
                second["total_months"] = max(1, int(car_plan.get("second_car_total_months") or 60))
                second["interest_free_months"] = max(0, int(car_plan.get("second_car_interest_free_months") or 24))
                second["later_annual_rate"] = max(0, float(car_plan.get("second_car_later_annual_rate") or 0.0199))
                second["annual_mileage_km"] = max(0, float(car_plan.get("second_car_annual_mileage_km") or 0))
                second["monthly_parking_cost"] = max(0, float(car_plan.get("second_car_monthly_parking_cost") or 0))
                vehicle_plans.append(second)
        car_plan["vehicle_plans"] = vehicle_plans
        car_plan["enabled"] = any(bool(item.get("enabled")) and float(item.get("total_price") or 0) > 0 for item in vehicle_plans)
    data.setdefault("property_goals", [])
    return data


def _migrate_json_records_to_v8(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v8)
    _update_table_json(conn, "scenarios", _set_schema_version_current)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _strip_nested_vehicle_candidates(vehicle: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(vehicle)
    cleaned["candidate_vehicles"] = []
    return cleaned


def _migrate_household_v9(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    car_plan = data.setdefault("car_plan", {})
    if not isinstance(car_plan, dict):
        return data
    vehicle_plans = car_plan.get("vehicle_plans")
    if not isinstance(vehicle_plans, list):
        car_plan["vehicle_plans"] = []
        return data
    for vehicle in vehicle_plans:
        if not isinstance(vehicle, dict):
            continue
        candidates = vehicle.get("candidate_vehicles")
        candidate_vehicles = [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []
        if not candidate_vehicles and bool(vehicle.get("enabled")) and float(vehicle.get("total_price") or 0) > 0:
            candidate_vehicles = [_strip_nested_vehicle_candidates(vehicle)]
        for candidate in candidate_vehicles:
            candidate.setdefault("enabled", True)
            candidate.setdefault("selected_strategy_variant", "鎵嬪姩璁剧疆")
            candidate.setdefault("candidate_vehicles", [])
        vehicle["candidate_vehicles"] = candidate_vehicles
    car_plan["enabled"] = any(
        bool(item.get("enabled")) and float(item.get("total_price") or 0) > 0
        for item in vehicle_plans
        if isinstance(item, dict)
    )
    return data


def _migrate_json_records_to_v9(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v9)
    _update_table_json(conn, "scenarios", _set_schema_version_current)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _migrate_household_v10(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    goals = data.get("property_goals")
    if isinstance(goals, list):
        for index, goal in enumerate(goals):
            if not isinstance(goal, dict):
                continue
            goal.setdefault("enabled", True)
            goal.setdefault("priority", index + 1)
            goal.setdefault("planning_mode", "after_previous_purchase")
            goal.setdefault("after_previous_purchase_delay_months", 0)
            goal.setdefault("earliest_purchase_delay_months", 0)
    else:
        data["property_goals"] = []
    return data


def _migrate_scenario_v10(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    data.setdefault("enabled", True)
    data.setdefault("purchase_sequence", 1)
    data.setdefault("purchase_planning_mode", "after_previous_purchase")
    data.setdefault("after_previous_purchase_delay_months", 0)
    return data


def _migrate_json_records_to_v10(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v10)
    _update_table_json(conn, "scenarios", _migrate_scenario_v10)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _fill_vehicle_timing_defaults(vehicle: dict[str, Any], index: int) -> None:
    vehicle.setdefault("planning_sequence", index + 1)
    vehicle.setdefault("purchase_timing_mode", "auto_sequence")
    vehicle.setdefault("after_previous_event_delay_months", 0)
    vehicle.setdefault("manual_purchase_delay_months", max(0, int(vehicle.get("purchase_delay_months") or 0)))
    candidates = vehicle.get("candidate_vehicles")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate.setdefault("planning_sequence", int(vehicle.get("planning_sequence") or index + 1))
            candidate.setdefault("purchase_timing_mode", vehicle.get("purchase_timing_mode") or "auto_sequence")
            candidate.setdefault("after_previous_event_delay_months", int(vehicle.get("after_previous_event_delay_months") or 0))
            candidate.setdefault(
                "manual_purchase_delay_months",
                max(0, int(candidate.get("purchase_delay_months") or vehicle.get("manual_purchase_delay_months") or 0)),
            )


def _migrate_household_v11(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    car_plan = data.setdefault("car_plan", {})
    if isinstance(car_plan, dict):
        _fill_vehicle_timing_defaults(car_plan, 0)
        vehicle_plans = car_plan.get("vehicle_plans")
        if isinstance(vehicle_plans, list):
            for index, vehicle in enumerate(vehicle_plans):
                if isinstance(vehicle, dict):
                    _fill_vehicle_timing_defaults(vehicle, index)
    return data


def _migrate_json_records_to_v11(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v11)


def _migrate_scenario_v12(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    data.setdefault("investment_withdrawal_mode", "auto")
    data.setdefault("investment_min_balance_after_purchase", 0)
    return data


def _migrate_json_records_to_v12(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _set_schema_version_current)
    _update_table_json(conn, "scenarios", _migrate_scenario_v12)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _migrate_household_v13(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    members = data.get("members")
    if not isinstance(members, list):
        members = []
        data["members"] = members

    career_shock = data.setdefault("career_shock", {})
    if not isinstance(career_shock, dict):
        career_shock = {}
        data["career_shock"] = career_shock

    legacy_birth_months = [
        str(career_shock.get("self_birth_month") or ""),
        str(career_shock.get("spouse_birth_month") or ""),
    ]
    legacy_current_ages = [
        _safe_int(career_shock.get("self_current_age"), 30),
        _safe_int(career_shock.get("spouse_current_age"), 30),
    ]
    legacy_retirement_ages = [
        _safe_int(career_shock.get("self_retirement_age"), 63),
        _safe_int(career_shock.get("spouse_retirement_age"), 58),
    ]
    legacy_pensions = [
        float(career_shock.get("self_pension_monthly") or 0),
        float(career_shock.get("spouse_pension_monthly") or 0),
    ]
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
        existing = existing_by_name.get(name, {})
        member_enabled = bool(existing.get("enabled")) if existing else legacy_global_enabled and name == legacy_layoff_member
        next_settings.append(
            {
                "member_name": name,
                "enabled": member_enabled,
                "layoff_age": _safe_int(existing.get("layoff_age") if existing else legacy_layoff_age, legacy_layoff_age),
                "retirement_age": _safe_int(
                    existing.get("retirement_age") if existing else (
                        legacy_retirement_ages[index] if index < len(legacy_retirement_ages) else 63
                    ),
                    63,
                ),
                "pension_monthly": float(
                    existing.get("pension_monthly") if existing else (
                        legacy_pensions[index] if index < len(legacy_pensions) else 0
                    ) or 0
                ),
            }
        )

    career_shock["enabled"] = any(bool(item.get("enabled")) for item in next_settings)
    career_shock["member_settings"] = next_settings
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
    return data


def _migrate_json_records_to_v13(conn: sqlite3.Connection) -> None:
    _update_table_json(conn, "households", _migrate_household_v13)
    _update_table_json(conn, "scenarios", _set_schema_version_current)
    _update_table_json(conn, "rule_packs", _set_schema_version_current)
    _update_table_json(conn, "market_snapshots", _set_schema_version_current)


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
        insert_record("households", HouseholdData().model_dump(mode="json"))

    if _count("rule_packs") == 0:
        insert_record("rule_packs", RulePackData().model_dump(mode="json"))

    if _count("market_snapshots") == 0:
        insert_record("market_snapshots", MarketSnapshotData().model_dump(mode="json"))
