from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _set_nested_value(payload: dict, path: tuple[str | int, ...], value) -> dict:
    next_payload = deepcopy(payload)
    cursor = next_payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return next_payload


def test_fetch_preview_does_not_change_rule_pack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database, main

    database.DB_PATH = database.default_db_path()

    async def fake_fetch_preview(url: str, name: str | None = None) -> dict:
        return {
            "id": "preview-id",
            "name": name or "preview",
            "url": url,
            "fetched_at": "2026-06-30T00:00:00+00:00",
            "content_hash": "hash",
            "status": "preview",
            "summary": "测试预览",
            "changed_from_previous": False,
        }

    monkeypatch.setattr(main, "fetch_preview", fake_fetch_preview)

    with TestClient(main.app) as client:
        before = client.get("/api/rule-packs").json()
        response = client.post(
            "/api/sources/fetch-preview",
            json={"url": "https://example.com", "name": "example"},
        )
        after = client.get("/api/rule-packs").json()

    assert response.status_code == 200
    assert before == after


def test_household_update_is_persisted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        record = client.get("/api/households").json()[0]
        record_id = record["id"]
        payload = record["data"] | {
            "child_count": 2,
            "cash_account_balance": 345_678,
            "investments": 0,
            "investment_plan_name": "稳健月度理财",
        }

        response = client.put(f"/api/households/{record_id}", json={"data": payload})
        persisted = client.get("/api/households").json()[0]["data"]

    assert response.status_code == 200
    assert response.json()["data"]["child_count"] == 2
    assert persisted["cash_account_balance"] == 345_678
    assert persisted["investments"] == 0
    assert persisted["investment_plan_name"] == "稳健月度理财"


def test_initialize_database_uses_current_schema_baseline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database

    database.DB_PATH = database.default_db_path()
    database.initialize_database()
    households = database.list_records("households")
    rule_packs = database.list_records("rule_packs")

    assert households[0]["data"]["schema_version"] == database.CURRENT_SCHEMA_VERSION
    assert households[0]["data"]["cash_account_balance"] == 0
    assert households[0]["data"]["car_plan"]["vehicle_plans"] == []
    assert rule_packs[0]["data"]["schema_version"] == database.CURRENT_SCHEMA_VERSION
    with database.get_connection() as conn:
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()]
    assert versions == [database.CURRENT_SCHEMA_VERSION]


def test_invalid_household_payload_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        record = client.get("/api/households").json()[0]
        payload = record["data"] | {"child_count": -1}
        response = client.put(f"/api/households/{record['id']}", json={"data": payload})

    assert response.status_code == 422


def test_empty_vehicle_candidate_list_is_preserved_on_save(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        record = client.get("/api/households").json()[0]
        payload = deepcopy(record["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    "enabled": True,
                    "name": "测试用车需求",
                    "selected_strategy_variant": "target",
                    "candidate_vehicles": [],
                    "planning_sequence": 1,
                    "purchase_timing_mode": "auto_sequence",
                    "after_previous_event_delay_months": 0,
                    "manual_purchase_delay_months": 0,
                    "total_price": 200000,
                    "down_payment_ratio": 0.3,
                    "down_payment": 60000,
                    "purchase_delay_months": 0,
                    "total_months": 60,
                    "interest_free_months": 24,
                    "later_annual_rate": 0.0199,
                    "current_month_index": 1,
                    "saving_start_date": "2026-07-01",
                    "monthly_operating_cost": 0,
                    "no_car_monthly_commute_cost": 800,
                    "annual_mileage_km": 12000,
                    "electricity_kwh_per_100km": 14,
                    "electricity_price_per_kwh": 0.8,
                    "monthly_parking_cost": 0,
                    "annual_maintenance_cost": 2500,
                    "annual_maintenance_growth_rate": 0.03,
                    "annual_insurance_rate": 0.018,
                    "annual_insurance_min": 4500,
                    "annual_insurance_growth_rate": 0.02,
                    "depreciation_years": 8,
                    "vehicle_service_years": 15,
                    "vehicle_retirement_mileage_km": 600000,
                    "happiness_score": 6.5,
                    "notes": "",
                }
            ],
        }
        response = client.put(f"/api/households/{record['id']}", json={"data": payload})

    assert response.status_code == 200
    saved_vehicle = response.json()["data"]["car_plan"]["vehicle_plans"][0]
    assert saved_vehicle["candidate_vehicles"] == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("members", 0, "income_stages", 0, "annual_bonus_payout_month"), 13),
        (("members", 0, "housing_fund_personal_rate"), 0.20),
        (("car_plan", "total_months"), 0),
        (("investment_buy_fee_rate",), 0.20),
        (("phased_loans",), [{"name": "非法贷款", "principal": 10_000, "remaining_months": 0}]),
        (("scheduled_expenses",), [{"name": "非法支出", "monthly_amount": -1, "start_month": "2027-01"}]),
    ],
)
def test_invalid_nested_household_payload_is_rejected(
    tmp_path: Path,
    monkeypatch,
    path: tuple[str | int, ...],
    value,
) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        record = client.get("/api/households").json()[0]
        payload = _set_nested_value(record["data"], path, value)
        response = client.put(f"/api/households/{record['id']}", json={"data": payload})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "scenario_patch",
    [
        {"total_price": -1},
        {"loan_years": 31},
        {"annual_investment_return": -0.51},
        {"commercial_prepayment_start_month": 0},
    ],
)
def test_invalid_scenario_payload_is_rejected(tmp_path: Path, monkeypatch, scenario_patch: dict) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        response = client.post("/api/scenarios", json={"data": scenario_patch})

    assert response.status_code == 422


def test_invalid_calculation_payload_is_rejected_before_cache_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]["data"]
        scenario = {"total_price": 3_000_000, "commercial_rate": 0.30}
        rule_pack = client.get("/api/rule-packs").json()[0]["data"]
        response = client.post(
            "/api/calculations/affordability",
            json={"household": household, "scenario": scenario, "rule_pack": rule_pack},
        )

    assert response.status_code == 422


def test_affordability_calculation_is_cached_until_inputs_change(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database, main

    database.DB_PATH = database.default_db_path()
    original_calculate = main.calculate_affordability
    calls = {"count": 0}

    def counted_calculate(household, scenario, rule_pack, *args, **kwargs):
        calls["count"] += 1
        return original_calculate(household, scenario, rule_pack, *args, **kwargs)

    monkeypatch.setattr(main, "calculate_affordability", counted_calculate)

    with TestClient(main.app) as client:
        household = client.get("/api/households").json()[0]["data"]
        scenario = client.post("/api/scenarios", json={"data": {"total_price": 3_000_000}}).json()["data"]
        rule_pack = client.get("/api/rule-packs").json()[0]["data"]
        payload = {"household": household, "scenario": scenario, "rule_pack": rule_pack}

        first = client.post("/api/calculations/affordability", json=payload)
        second = client.post("/api/calculations/affordability", json=payload)
        changed = client.post(
            "/api/calculations/affordability",
            json={
                **payload,
                "scenario": scenario | {"total_price": scenario["total_price"] + 10_000},
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert changed.status_code == 200
    assert first.json() == second.json()
    assert calls["count"] == 2


def test_scenario_can_be_deleted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        before = client.get("/api/scenarios").json()
        created = client.post("/api/scenarios", json={"data": {"total_price": 3_000_000}}).json()
        response = client.delete(f"/api/scenarios/{created['id']}")
        after = client.get("/api/scenarios").json()

    assert before == []
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert created["id"] not in {item["id"] for item in after}
