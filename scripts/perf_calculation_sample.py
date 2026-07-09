from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import hashlib
import sys
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

if "HOUSE_PLANNER_DB" not in os.environ:
    os.environ["HOUSE_PLANNER_DB"] = str(Path(tempfile.gettempdir()) / f"house_planner_perf_sample_{os.getpid()}.sqlite")
os.environ.setdefault("HOUSE_PLANNER_PROFILE", "1")
logging.basicConfig(level=logging.INFO, format="%(message)s")

from fastapi.testclient import TestClient  # noqa: E402

from app import database  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import ScenarioData  # noqa: E402


def _calculation_payload(client: TestClient) -> dict[str, object]:
    household = client.get("/api/households").json()[0]
    scenarios = client.get("/api/scenarios", params={"household_id": household["id"]}).json()
    if scenarios:
        scenario = scenarios[0]
    else:
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": ScenarioData(name="性能样例房源", total_price=3_000_000).model_dump(mode="json"),
            },
        ).json()
    rule_pack = client.get("/api/rule-packs").json()[0]
    market_snapshots = client.get("/api/market-snapshots").json()
    return {
        "household_id": household["id"],
        "scenario_id": scenario["id"],
        "household": household["data"],
        "scenario": scenario["data"],
        "rule_pack": rule_pack["data"],
        "market_snapshot": market_snapshots[0]["data"] if market_snapshots else None,
        "include_stress_tests": False,
    }


def _timed_calculation(client: TestClient, payload: dict[str, object], label: str) -> dict[str, object]:
    started_at = perf_counter()
    response = client.post("/api/calculations/affordability", json=payload)
    elapsed_ms = (perf_counter() - started_at) * 1000
    response.raise_for_status()
    result = response.json()
    result_hash = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "label": label,
        "elapsed_ms": round(elapsed_ms, 3),
        "result_hash": result_hash,
        "cache_layers": result.get("cache_layers", {}),
        "purchase_plan_count": len(result.get("purchase_plan_analyses") or []),
        "monthly_ledger_count": len(result.get("monthly_ledger") or []),
    }


def _assert_consistent_runs(runs: list[dict[str, object]]) -> None:
    cold, cache_hit = runs
    comparable_keys = ("result_hash", "cache_layers", "purchase_plan_count", "monthly_ledger_count")
    mismatches = {
        key: {"cold": cold.get(key), "cache_hit": cache_hit.get(key)}
        for key in comparable_keys
        if cold.get(key) != cache_hit.get(key)
    }
    if mismatches:
        raise RuntimeError(f"Performance sample result mismatch: {json.dumps(mismatches, ensure_ascii=False, sort_keys=True)}")


def main() -> None:
    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        payload = _calculation_payload(client)
        runs = [
            _timed_calculation(client, payload, "cold"),
            _timed_calculation(client, payload, "cache_hit"),
        ]
    _assert_consistent_runs(runs)
    print(json.dumps({"database": str(database.DB_PATH), "runs": runs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
