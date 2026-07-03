import json
from pathlib import Path

from fastapi.testclient import TestClient


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


def test_initialize_database_migrates_previous_json_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database

    database.DB_PATH = database.default_db_path()
    with database.get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE households (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE scenarios (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE rule_packs (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO households (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (
                "account-rename-household",
                json.dumps({"liquid_assets": 100000, "car_plan": {"enabled": False}}, ensure_ascii=False),
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            "INSERT INTO scenarios (id, household_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                "old-rate-scenario",
                None,
                json.dumps({"provident_rate": 0.0285}, ensure_ascii=False),
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            "INSERT INTO rule_packs (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (
                "old-policy-rule",
                json.dumps(
                    {"params": {"second_home_provident_min_down_payment_ratio": 0.25}},
                    ensure_ascii=False,
                ),
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    database.initialize_database()
    migrated = database.get_record("households", "account-rename-household")
    migrated_scenario = database.get_record("scenarios", "old-rate-scenario")
    migrated_rule = database.get_record("rule_packs", "old-policy-rule")

    assert migrated is not None
    assert migrated["data"]["schema_version"] == database.CURRENT_SCHEMA_VERSION
    assert migrated["data"]["cash_account_balance"] == 100000
    assert "liquid_assets" not in migrated["data"]
    assert migrated["data"]["family_down_payment_support_mode"] == "provident"
    assert migrated["data"]["investment_buy_fee_rate"] > 0
    assert migrated["data"]["car_plan"]["second_car_enabled"] is False
    assert migrated_scenario is not None
    assert migrated_scenario["data"]["schema_version"] == database.CURRENT_SCHEMA_VERSION
    assert migrated_scenario["data"]["provident_rate"] == 0.026
    assert migrated_rule is not None
    assert migrated_rule["data"]["schema_version"] == database.CURRENT_SCHEMA_VERSION
    assert migrated_rule["data"]["params"]["second_home_provident_min_down_payment_ratio"] == 0.30
    assert migrated_rule["data"]["params"]["provident_first_home_rate_6_to_30_years"] == 0.026


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
