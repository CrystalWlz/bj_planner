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
            "liquid_assets": 345_678,
            "investments": 0,
            "investment_plan_name": "稳健月度理财",
        }

        response = client.put(f"/api/households/{record_id}", json={"data": payload})
        persisted = client.get("/api/households").json()[0]["data"]

    assert response.status_code == 200
    assert response.json()["data"]["child_count"] == 2
    assert persisted["liquid_assets"] == 345_678
    assert persisted["investments"] == 0
    assert persisted["investment_plan_name"] == "稳健月度理财"


def test_initialize_database_migrates_legacy_json_records(tmp_path: Path, monkeypatch) -> None:
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
            "INSERT INTO households (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (
                "legacy-household",
                json.dumps({"liquid_assets": 100000, "car_plan": {"enabled": False}}, ensure_ascii=False),
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    database.initialize_database()
    migrated = database.get_record("households", "legacy-household")

    assert migrated is not None
    assert migrated["data"]["schema_version"] == database.CURRENT_SCHEMA_VERSION
    assert migrated["data"]["family_down_payment_support_mode"] == "provident"
    assert migrated["data"]["investment_buy_fee_rate"] > 0
    assert migrated["data"]["car_plan"]["second_car_enabled"] is False


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
