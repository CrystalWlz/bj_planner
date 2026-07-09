import ast
from copy import deepcopy
from datetime import date
import json
import logging
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


def test_home_goal_financing_preferences_preserve_provident_repayment_switch() -> None:
    from app.schemas import ScenarioData
    from app.storage.normalization import home_goal_from_scenario, scenario_from_home_goal

    scenario = ScenarioData(
        name="示例购房目标",
        provident_account_repayment_strategy="monthly_repayment_withdrawal",
        provident_account_repayment_switch_enabled=True,
        provident_account_repayment_switch_after_month=18,
        provident_account_repayment_switch_to_strategy="semiannual_principal_offset",
    )

    goal = home_goal_from_scenario(
        scenario.model_dump(mode="json"),
        household_id="household-demo",
        goal_id="home-goal-demo",
    )
    restored = scenario_from_home_goal("home-goal-demo", goal, sequence_index=1)

    assert "provident_account_repayment_strategy" not in goal["target_params"]
    assert "provident_account_repayment_switch_enabled" not in goal["target_params"]
    assert goal["financing_preferences"]["provident_account_repayment_strategy"] == "monthly_repayment_withdrawal"
    assert goal["financing_preferences"]["provident_account_repayment_switch_enabled"] is True
    assert goal["financing_preferences"]["provident_account_repayment_switch_after_month"] == 18
    assert goal["financing_preferences"]["provident_account_repayment_switch_to_strategy"] == "semiannual_principal_offset"
    assert restored["provident_account_repayment_strategy"] == "monthly_repayment_withdrawal"
    assert restored["provident_account_repayment_switch_enabled"] is True
    assert restored["provident_account_repayment_switch_after_month"] == 18
    assert restored["provident_account_repayment_switch_to_strategy"] == "semiannual_principal_offset"


def test_member_pension_auto_setting_persists_without_global_switch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        record = client.get("/api/households").json()[0]
        payload = deepcopy(record["data"])
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "Sample A",
                "birth_month": "1999-01",
                "income_stages": [
                    {
                        **payload["members"][0]["income_stages"][0],
                        "provident_account_management_center": "national",
                    }
                ],
            },
            {
                **payload["members"][0],
                "name": "Sample B",
                "birth_month": "2001-07",
                "income_stages": [
                    {
                        **payload["members"][0]["income_stages"][0],
                        "provident_account_management_center": "beijing_municipal",
                    }
                ],
            },
        ]
        payload["career_shock"] = {
            **payload["career_shock"],
            "auto_pension_income": False,
            "member_settings": [
                {
                    "member_name": "Sample A",
                    "enabled": False,
                    "layoff_age": 35,
                    "retirement_age": 63,
                    "freelance_income_monthly": 3500,
                    "pension_monthly": 0,
                    "auto_pension_monthly": False,
                },
                {
                    "member_name": "Sample B",
                    "enabled": False,
                    "layoff_age": 35,
                    "retirement_age": 58,
                    "freelance_income_monthly": 0,
                    "pension_monthly": 0,
                    "auto_pension_monthly": True,
                },
            ],
        }

        response = client.put(f"/api/households/{record['id']}", json={"data": payload})
        persisted = client.get("/api/households").json()[0]["data"]

    assert response.status_code == 200
    saved_shock = response.json()["data"]["career_shock"]
    assert "auto_pension_income" not in saved_shock
    assert "auto_pension_income" not in persisted["career_shock"]
    assert "provident_account_management_center" not in persisted["members"][0]
    assert persisted["members"][0]["income_stages"][0]["provident_account_management_center"] == "national"
    assert persisted["members"][1]["income_stages"][0]["provident_account_management_center"] == "beijing_municipal"
    assert saved_shock["member_settings"][0]["freelance_income_monthly"] == 3500
    assert saved_shock["member_settings"][0]["auto_pension_monthly"] is False
    assert saved_shock["member_settings"][1]["auto_pension_monthly"] is True
    assert persisted["career_shock"]["member_settings"][0]["freelance_income_monthly"] == 3500
    assert persisted["career_shock"]["member_settings"][1]["auto_pension_monthly"] is True


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
        planning_goal_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'planning_goals'"
        ).fetchone()
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
    assert versions == [database.CURRENT_SCHEMA_VERSION]
    assert planning_goal_table is not None
    assert "idx_core_objects_owner" in indexes
    assert "idx_calculation_cache_layers" in indexes
    assert "idx_generated_strategies_layers" in indexes
    assert "idx_generated_strategies_owner" in indexes


def test_affordability_cache_key_includes_stress_switch() -> None:
    from app.cache import affordability_cache_key
    from app.schemas import AffordabilityRequest, HouseholdData, MarketSnapshotData, RulePackData, ScenarioData

    base_payload = {
        "household": HouseholdData(),
        "scenario": ScenarioData(),
        "rule_pack": RulePackData(),
    }

    normal_key, _, _ = affordability_cache_key(AffordabilityRequest(**base_payload, include_stress_tests=False))
    stress_key, _, _ = affordability_cache_key(AffordabilityRequest(**base_payload, include_stress_tests=True))

    assert normal_key != stress_key

    market_key, _, market_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            market_snapshot=MarketSnapshotData(commercial_loan_rate=0.032, default_broker_fee_rate=0.016),
        )
    )

    assert market_key != normal_key
    assert market_layers.input != affordability_cache_key(AffordabilityRequest(**base_payload))[2].input


def test_affordability_cache_key_exposes_layer_hashes() -> None:
    from app.cache import ENGINE_CODE_PATHS, LAYER_CODE_PATHS, affordability_cache_key, calculation_code_fingerprints
    from app.schemas import AffordabilityRequest, HouseholdData, RulePackData, ScenarioData

    _, engine_fingerprint, layers = affordability_cache_key(
        AffordabilityRequest(
            household=HouseholdData(),
            scenario=ScenarioData(),
            rule_pack=RulePackData(),
        )
    )

    assert set(layers.model_dump()) == {"input", "strategy", "ledger", "visualization", "engine"}
    code_layers = calculation_code_fingerprints()
    assert set(code_layers) == {"input", "strategy", "ledger", "visualization", "engine"}
    assert layers.engine == engine_fingerprint
    assert code_layers["input"] != code_layers["strategy"]
    assert layers.strategy != layers.ledger
    assert layers.ledger != layers.visualization
    assert all(len(value) == 64 for value in layers.model_dump().values())
    assert "calculation_context.py" in LAYER_CODE_PATHS["input"]
    assert "planning_context.py" in LAYER_CODE_PATHS["input"]
    assert "core_objects.py" in LAYER_CODE_PATHS["input"]
    assert "core_object_concepts.py" in LAYER_CODE_PATHS["input"]
    assert "storage" in LAYER_CODE_PATHS["input"]
    assert "domain/planning_goals.py" in LAYER_CODE_PATHS["input"]
    assert "engine_config.py" in LAYER_CODE_PATHS["strategy"]
    assert "engine_config.py" in LAYER_CODE_PATHS["ledger"]
    assert "strategy_pipeline.py" in LAYER_CODE_PATHS["strategy"]
    assert "purchase_facade.py" in LAYER_CODE_PATHS["strategy"]
    assert "planning_pipeline.py" in LAYER_CODE_PATHS["ledger"]
    assert "projection_facade.py" in LAYER_CODE_PATHS["ledger"]
    assert "result_assembly.py" in LAYER_CODE_PATHS["visualization"]
    assert "core_object_concepts.py" in LAYER_CODE_PATHS["visualization"]
    assert "cache.py" in ENGINE_CODE_PATHS
    assert "generated_strategies.py" in ENGINE_CODE_PATHS


def test_cache_layer_code_paths_are_declared_and_resolvable() -> None:
    from app.cache import ENGINE_CODE_PATHS, LAYER_CODE_PATHS

    app_dir = Path("backend/app")
    assert set(LAYER_CODE_PATHS) == {"input", "strategy", "ledger", "visualization"}
    for layer, entries in LAYER_CODE_PATHS.items():
        assert entries, layer
        for entry in entries:
            assert (app_dir / entry).exists(), f"{layer}:{entry}"
    for entry in ENGINE_CODE_PATHS:
        assert (app_dir / entry).exists(), f"engine:{entry}"

    assert "planning_context.py" in LAYER_CODE_PATHS["input"]
    assert "strategies" in LAYER_CODE_PATHS["strategy"]
    assert "projection" in LAYER_CODE_PATHS["ledger"]
    assert "visualization.py" in LAYER_CODE_PATHS["visualization"]


def test_calculation_profiling_is_env_gated_and_records_spans(monkeypatch, caplog) -> None:
    from app.profiling import calculation_profile, profile_span, profiling_enabled

    monkeypatch.delenv("HOUSE_PLANNER_PROFILE", raising=False)
    assert not profiling_enabled()
    with caplog.at_level(logging.INFO, logger="app.profiling"):
        with calculation_profile("disabled_sample"):
            with profile_span("disabled_stage"):
                pass
    assert "disabled_stage" not in caplog.text

    caplog.clear()
    monkeypatch.setenv("HOUSE_PLANNER_PROFILE", "1")
    assert profiling_enabled()
    with caplog.at_level(logging.INFO, logger="app.profiling"):
        with calculation_profile("enabled_sample"):
            with profile_span("enabled_stage"):
                pass

    assert "calculation_profile" in caplog.text
    assert "enabled_sample" in caplog.text
    assert "enabled_stage" in caplog.text


def test_affordability_pipeline_declares_profile_spans() -> None:
    expected_spans = {
        "calculation_context": Path("backend/app/main.py"),
        "cache_lookup": Path("backend/app/main.py"),
        "calculate_affordability": Path("backend/app/main.py"),
        "household_context": Path("backend/app/calculator.py"),
        "strategy_pipeline": Path("backend/app/calculator.py"),
        "tax_strategy": Path("backend/app/calculator.py"),
        "result_assembly": Path("backend/app/calculator.py"),
        "purchase_strategy_generation": Path("backend/app/strategy_pipeline.py"),
        "yield_sensitivity": Path("backend/app/strategy_pipeline.py"),
        "projection_pipeline": Path("backend/app/strategy_pipeline.py"),
        "ledger_projection": Path("backend/app/planning_pipeline.py"),
        "monthly_visualization": Path("backend/app/planning_pipeline.py"),
        "annual_reporting": Path("backend/app/planning_pipeline.py"),
    }
    for span_name, path in expected_spans.items():
        assert f'profile_span("{span_name}")' in path.read_text(encoding="utf-8")


def test_performance_sample_uses_temp_database_and_cache_hit_run() -> None:
    source = Path("scripts/perf_calculation_sample.py").read_text(encoding="utf-8")

    assert "HOUSE_PLANNER_DB" in source
    assert "tempfile.gettempdir()" in source
    assert "HOUSE_PLANNER_PROFILE" in source
    assert '"/api/calculations/affordability"' in source
    assert '"cold"' in source
    assert '"cache_hit"' in source
    assert "result_hash" in source
    assert "_assert_consistent_runs" in source
    assert "cache_layers" in source
    assert "monthly_ledger_count" in source


def test_architecture_closure_checklist_tracks_major_goal_areas() -> None:
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    checklist = Path("docs/architecture_closure_checklist.md").read_text(encoding="utf-8")

    assert "architecture_closure_checklist.md" in architecture
    assert "总体结论" in checklist
    assert "## 完成判定" in checklist
    for heading in (
        "## 1. 数据库核心对象表",
        "## 2. 统一 planning_goals",
        "## 3. 多目标顺序规划",
        "## 4. 政策接口继续解耦",
        "## 5. 缓存分层",
        "## 7. 前端概念统一",
        "## 11. 发布与验证",
    ):
        assert heading in checklist


def test_cache_layer_hashes_propagate_input_changes_downstream() -> None:
    from app.cache import affordability_cache_layers
    from app.schemas import AffordabilityRequest, HouseholdData, RulePackData, ScenarioData

    base_layers = affordability_cache_layers(
        AffordabilityRequest(
            household=HouseholdData(notes="base-input"),
            scenario=ScenarioData(),
            rule_pack=RulePackData(),
        )
    )
    changed_layers = affordability_cache_layers(
        AffordabilityRequest(
            household=HouseholdData(notes="changed-input"),
            scenario=ScenarioData(),
            rule_pack=RulePackData(),
        )
    )

    assert changed_layers.input != base_layers.input
    assert changed_layers.strategy != base_layers.strategy
    assert changed_layers.ledger != base_layers.ledger
    assert changed_layers.visualization != base_layers.visualization
    assert changed_layers.engine == base_layers.engine


def test_execution_config_does_not_change_business_cache_layers() -> None:
    from app.cache import affordability_cache_layers
    from app.schemas import AffordabilityRequest, HouseholdData, RulePackData, ScenarioData

    base_rules = RulePackData()
    serial_rules = base_rules.model_copy(update={"params": {**base_rules.params, "backend_parallel_workers": 1}})
    parallel_rules = base_rules.model_copy(update={"params": {**base_rules.params, "backend_parallel_workers": 8}})
    changed_policy_rules = base_rules.model_copy(
        update={"params": {**base_rules.params, "minimum_down_payment_ratio": 0.35}}
    )

    serial_layers = affordability_cache_layers(
        AffordabilityRequest(household=HouseholdData(), scenario=ScenarioData(), rule_pack=serial_rules)
    )
    parallel_layers = affordability_cache_layers(
        AffordabilityRequest(household=HouseholdData(), scenario=ScenarioData(), rule_pack=parallel_rules)
    )
    changed_policy_layers = affordability_cache_layers(
        AffordabilityRequest(household=HouseholdData(), scenario=ScenarioData(), rule_pack=changed_policy_rules)
    )

    assert parallel_layers == serial_layers
    assert changed_policy_layers.input != serial_layers.input
    assert changed_policy_layers.strategy != serial_layers.strategy
    assert changed_policy_layers.ledger != serial_layers.ledger
    assert changed_policy_layers.visualization != serial_layers.visualization


def test_cache_layer_file_fingerprint_recurses_into_subpackages(tmp_path: Path) -> None:
    from app.cache import _files_fingerprint

    app_dir = tmp_path / "app"
    nested_dir = app_dir / "projection" / "nested"
    nested_dir.mkdir(parents=True)
    (app_dir / "projection").mkdir(exist_ok=True)
    (app_dir / "projection" / "root_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    nested_file = nested_dir / "child_module.py"
    nested_file.write_text("VALUE = 1\n", encoding="utf-8")

    first = _files_fingerprint(app_dir, ("projection",))
    nested_file.write_text("VALUE = 2\n", encoding="utf-8")
    second = _files_fingerprint(app_dir, ("projection",))

    assert first != second


def test_engine_fingerprint_includes_cache_module(tmp_path: Path) -> None:
    from app.cache import ENGINE_CODE_PATHS, _files_fingerprint, _hash_json

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    cache_file = app_dir / "cache.py"
    cache_file.write_text("CACHE_VERSION = 1\n", encoding="utf-8")
    layers = {
        "input": "input-code",
        "strategy": "strategy-code",
        "ledger": "ledger-code",
        "visualization": "visualization-code",
    }

    first = _hash_json({"layers": layers, "cache_module": _files_fingerprint(app_dir, ENGINE_CODE_PATHS)})
    cache_file.write_text("CACHE_VERSION = 2\n", encoding="utf-8")
    second = _hash_json({"layers": layers, "cache_module": _files_fingerprint(app_dir, ENGINE_CODE_PATHS)})

    assert first != second


def test_affordability_cache_key_includes_calculation_context() -> None:
    from app.cache import affordability_cache_key
    from app.schemas import AffordabilityRequest, CalculationContextCoreObjectSnapshot, CalculationContextGoalSnapshot, CalculationContextSnapshot, HouseholdData, RulePackData, ScenarioData

    base_payload = {
        "household_id": "household-a",
        "scenario_id": "scenario-a",
        "household": HouseholdData(),
        "scenario": ScenarioData(),
        "rule_pack": RulePackData(),
    }

    first_key, _, first_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            calculation_context=CalculationContextSnapshot(
                household_id="household-a",
                scenario_id="scenario-a",
                planning_goal_fingerprint="goals-v1",
                core_object_fingerprint="objects-v1",
            ),
        )
    )
    second_key, _, second_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            calculation_context=CalculationContextSnapshot(
                household_id="household-a",
                scenario_id="scenario-a",
                planning_goal_fingerprint="goals-v2",
                core_object_fingerprint="objects-v1",
            ),
        )
    )

    assert first_key != second_key
    assert first_layers.input != second_layers.input

    goal_base = CalculationContextGoalSnapshot(
        id="goal-home",
        goal_type="home",
        name="示例目标",
        priority=1,
        sequence_index=1,
        resolved_not_before_month=6,
    )
    goal_changed = goal_base.model_copy(update={"resolved_not_before_month": 12})
    third_key, _, third_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            calculation_context=CalculationContextSnapshot(
                household_id="household-a",
                scenario_id="scenario-a",
                planning_goal_fingerprint="goals-v2",
                core_object_fingerprint="objects-v1",
                planning_goals=[goal_base],
            ),
        )
    )
    fourth_key, _, fourth_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            calculation_context=CalculationContextSnapshot(
                household_id="household-a",
                scenario_id="scenario-a",
                planning_goal_fingerprint="goals-v2",
                core_object_fingerprint="objects-v1",
                planning_goals=[goal_changed],
            ),
        )
    )

    assert third_key != fourth_key
    assert third_layers.input != fourth_layers.input

    core_object_base = CalculationContextCoreObjectSnapshot(
        id="core-object-cash",
        object_type="account",
        category="cash",
        name="现金账户",
        owner_key="household-a",
        current_balance=100_000,
    )
    core_object_changed = core_object_base.model_copy(update={"current_balance": 120_000})
    fifth_key, _, fifth_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            calculation_context=CalculationContextSnapshot(
                household_id="household-a",
                scenario_id="scenario-a",
                planning_goal_fingerprint="goals-v2",
                core_object_fingerprint="objects-v1",
                core_objects=[core_object_base],
            ),
        )
    )
    sixth_key, _, sixth_layers = affordability_cache_key(
        AffordabilityRequest(
            **base_payload,
            calculation_context=CalculationContextSnapshot(
                household_id="household-a",
                scenario_id="scenario-a",
                planning_goal_fingerprint="goals-v2",
                core_object_fingerprint="objects-v2",
                core_objects=[core_object_changed],
            ),
        )
    )

    assert fifth_key != sixth_key
    assert fifth_layers.input != sixth_layers.input


def test_planning_goal_constraints_use_context_goal_snapshot() -> None:
    from app.planning_context import apply_planning_goal_constraints
    from app.schemas import (
        AffordabilityRequest,
        CalculationContextGoalSnapshot,
        CalculationContextSnapshot,
        CarPlanData,
        HouseholdData,
        RulePackData,
        ScenarioData,
    )

    household = HouseholdData(
        car_plan=CarPlanData(
            enabled=True,
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="示例通勤车",
                    planning_goal_id="vehicle-goal-a",
                    purchase_delay_months=0,
                    manual_purchase_delay_months=0,
                )
            ],
        )
    )
    payload = AffordabilityRequest(
        household_id="household-a",
        scenario_id="scenario-record-a",
        household=household,
        scenario=ScenarioData(planning_goal_id="home-goal-a", manual_purchase_delay_months=0),
        rule_pack=RulePackData(),
        calculation_context=CalculationContextSnapshot(
            household_id="household-a",
            scenario_id="scenario-record-a",
            planning_goals=[
                CalculationContextGoalSnapshot(
                    id="home-goal-a",
                    goal_type="home",
                    name="示例房源",
                    priority=1,
                    sequence_index=1,
                    resolved_not_before_month=12,
                ),
                CalculationContextGoalSnapshot(
                    id="vehicle-goal-a",
                    goal_type="vehicle",
                    name="示例通勤车",
                    priority=1,
                    sequence_index=1,
                    resolved_not_before_month=18,
                )
            ],
        ),
    )

    constrained = apply_planning_goal_constraints(payload)
    vehicle = constrained.household.car_plan.vehicle_plans[0]

    assert constrained.scenario.manual_purchase_delay_months == 12
    assert vehicle.purchase_delay_months == 18
    assert vehicle.manual_purchase_delay_months == 18


def test_planning_goal_constraints_project_global_vehicle_and_child_goals_for_calculation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app
    from app.planning_context import apply_planning_goal_constraints
    from app.schemas import AffordabilityRequest, HouseholdData, RulePackData, ScenarioData

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["car_plan"] = {
            **household_payload.get("car_plan", {}),
            "enabled": False,
            "vehicle_plans": [],
        }
        household_payload["child_plans"] = []
        household_payload["child_count"] = 0
        saved_household = client.put(
            f"/api/households/{household['id']}",
            json={"data": household_payload},
        ).json()
        global_vehicle = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例全局车辆目标",
                    "priority": 2,
                    "timing_mode": "manual_month",
                    "earliest_purchase_delay_months": 10,
                    "target_params": {
                        "name": "示例全局车辆目标",
                        "total_price": 180000,
                    },
                },
            },
        ).json()
        global_child = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "child",
                    "name": "示例全局子女目标",
                    "priority": 3,
                    "timing_mode": "manual_month",
                    "earliest_purchase_delay_months": 18,
                    "target_params": {
                        "name": "示例全局子女目标",
                        "expense_strategy_mode": "balanced",
                    },
                },
            },
        ).json()
        persisted_household = client.get("/api/households").json()[0]

    request = AffordabilityRequest(
        household_id=household["id"],
        household=HouseholdData.model_validate(saved_household["data"]),
        scenario=ScenarioData(),
        rule_pack=RulePackData(),
    )
    constrained = apply_planning_goal_constraints(request)

    assert persisted_household["data"]["car_plan"]["vehicle_plans"] == []
    assert persisted_household["data"]["child_plans"] == []
    assert [vehicle.planning_goal_id for vehicle in constrained.household.car_plan.vehicle_plans] == [global_vehicle["id"]]
    assert constrained.household.car_plan.vehicle_plans[0].manual_purchase_delay_months == 10
    assert [child.planning_goal_id for child in constrained.household.child_plans] == [global_child["id"]]
    assert constrained.household.child_plans[0].enabled is True
    assert global_vehicle["household_id"] is None
    assert global_child["household_id"] is None


def test_affordability_api_attaches_database_calculation_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["members"] = []
        household_payload["monthly_income"] = 30_000
        household_payload["monthly_expense"] = 4_000
        household_payload["cash_account_balance"] = 100_000
        household_payload["investments"] = 0
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例计算房源",
                    "total_price": 2_000_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        global_goal = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "other",
                    "name": "示例全局计算目标",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "parallel",
                    "target_params": {"estimated_cost": 50_000},
                },
            },
        ).json()

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    context = response.json()["calculation_context"]
    assert context["base_month"] == f"{date.today().year:04d}-{date.today().month:02d}"
    assert context["household_id"] == household["id"]
    assert context["scenario_id"] == scenario["id"]
    assert scenario["id"] in context["planning_goal_ids"]
    assert global_goal["id"] in context["planning_goal_ids"]
    goal_snapshot = next(goal for goal in context["planning_goals"] if goal["id"] == scenario["id"])
    global_goal_snapshot = next(goal for goal in context["planning_goals"] if goal["id"] == global_goal["id"])
    assert goal_snapshot["goal_type"] == "home"
    assert goal_snapshot["name"] == "示例计算房源"
    assert goal_snapshot["sequence_index"] >= 1
    assert global_goal_snapshot["goal_type"] == "other"
    assert global_goal_snapshot["normalized_timing_mode"] == "parallel"
    assert "explanation" in goal_snapshot
    assert context["resolved_goal_count"] >= 1
    assert context["core_object_count"] >= 1
    assert context["core_objects"]
    assert context["core_object_ids"] == [item["id"] for item in context["core_objects"]]
    assert any(item["object_type"] == "account" for item in context["core_objects"])
    assert all("owner_key" in item for item in context["core_objects"])
    assert any(
        item["owner_key"] == scenario["id"] and item["object_type"] == "asset"
        for item in context["core_objects"]
    )
    assert any(
        item["owner_key"] == global_goal["id"] and item["object_type"] == "asset"
        for item in context["core_objects"]
    )
    assert len(context["planning_goal_fingerprint"]) == 64
    assert len(context["core_object_fingerprint"]) == 64
    account_concepts = {item["code"]: item for item in response.json()["account_concepts"]}
    assert account_concepts["cash_account"]["core_object_count"] == 1
    assert account_concepts["cash_account"]["current_balance"] >= 0
    assert account_concepts["fixed_asset_account"]["core_object_count"] >= 1
    assert account_concepts["fixed_asset_account"]["current_balance"] >= 2_000_000
    core_object_groups = {item["code"]: item for item in response.json()["core_object_groups"]}
    assert core_object_groups["liquid_assets"]["core_object_count"] >= 1
    assert core_object_groups["liquid_assets"]["current_balance"] >= 0
    assert core_object_groups["fixed_assets"]["core_object_count"] >= 1
    assert "fixed_asset_account" in core_object_groups["fixed_assets"]["concept_codes"]
    planning_goal_events = [
        event
        for event in response.json()["plan_events"]
        if event["source"] == "planning_goals" and event["title"] == "规划目标：示例计算房源"
    ]
    assert planning_goal_events
    assert planning_goal_events[0]["category"] == "home_purchase"


def test_affordability_api_projects_baseline_visualization_without_child_or_vehicle_plans(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        rule_pack = client.get("/api/rule-packs").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["members"] = []
        household_payload["monthly_income"] = 30_000
        household_payload["monthly_expense"] = 8_000
        household_payload["cash_account_balance"] = 250_000
        household_payload["investments"] = 80_000
        household_payload["child_count"] = 0
        household_payload["child_plans"] = []
        household_payload["car_plan"] = {
            **household_payload.get("car_plan", {}),
            "enabled": False,
            "vehicle_plans": [],
        }
        scenario_payload = {
            "name": "baseline",
            "enabled": False,
            "total_price": 0,
        }

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household": household_payload,
                "scenario": scenario_payload,
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["car_plan_analyses"] == []
    assert result["child_plan_strategies"] == []
    assert result["purchase_plan_analyses"][0]["source"] == "baseline"
    assert result["purchase_plan_analyses"][0]["variant"] == "家庭基线"
    assert result["monthly_cashflow_visualization"]
    assert result["monthly_visualization_details"]
    assert result["monthly_ledger"]
    assert result["account_snapshots"]
    assert result["annual_financial_summaries"]
    assert {item["plan_variant"] for item in result["monthly_cashflow_visualization"]} == {"家庭基线"}
    assert any(item["plan_variant"] == "家庭基线" for item in result["monthly_visualization_details"])


def test_calculation_context_fingerprints_ignore_record_timestamps(tmp_path: Path, monkeypatch) -> None:
    import time

    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app
    from app.planning_context import calculation_context_snapshot
    from app.schemas import AffordabilityRequest, HouseholdData, RulePackData, ScenarioData

    database.DB_PATH = database.default_db_path()

    def context_for(client: TestClient, household_id: str):
        current_household = next(item for item in client.get("/api/households").json() if item["id"] == household_id)
        return calculation_context_snapshot(
            AffordabilityRequest(
                household_id=household_id,
                household=HouseholdData.model_validate(current_household["data"]),
                scenario=ScenarioData(),
                rule_pack=RulePackData(),
            )
        )

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["cash_account_balance"] = 88_000
        client.put(f"/api/households/{household['id']}", json={"data": household_payload})
        goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例稳定指纹房源",
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "target_params": {"total_price": 2_000_000},
                },
            },
        ).json()
        first_context = context_for(client, household["id"])
        with database.get_connection() as conn:
            first_goal_updated_at = conn.execute(
                "SELECT updated_at FROM planning_goals WHERE id = ?",
                (goal["id"],),
            ).fetchone()["updated_at"]
            first_core_updated_at = conn.execute(
                "SELECT MAX(updated_at) AS updated_at FROM core_objects WHERE household_id = ?",
                (household["id"],),
            ).fetchone()["updated_at"]

        time.sleep(0.01)
        current_household = next(item for item in client.get("/api/households").json() if item["id"] == household["id"])
        client.put(f"/api/households/{household['id']}", json={"data": current_household["data"]})
        client.put(f"/api/planning-goals/{goal['id']}", json={"household_id": household["id"], "data": goal["data"]})
        second_context = context_for(client, household["id"])
        with database.get_connection() as conn:
            second_goal_updated_at = conn.execute(
                "SELECT updated_at FROM planning_goals WHERE id = ?",
                (goal["id"],),
            ).fetchone()["updated_at"]
            second_core_updated_at = conn.execute(
                "SELECT MAX(updated_at) AS updated_at FROM core_objects WHERE household_id = ?",
                (household["id"],),
            ).fetchone()["updated_at"]

        changed_household = next(item for item in client.get("/api/households").json() if item["id"] == household["id"])
        changed_household_payload = deepcopy(changed_household["data"])
        changed_household_payload["cash_account_balance"] = 99_000
        client.put(f"/api/households/{household['id']}", json={"data": changed_household_payload})
        third_context = context_for(client, household["id"])

        changed_goal_data = deepcopy(goal["data"])
        changed_goal_data["name"] = "示例变更指纹房源"
        client.put(f"/api/planning-goals/{goal['id']}", json={"household_id": household["id"], "data": changed_goal_data})
        fourth_context = context_for(client, household["id"])

    assert first_goal_updated_at != second_goal_updated_at
    assert first_core_updated_at != second_core_updated_at
    assert first_context.planning_goal_fingerprint == second_context.planning_goal_fingerprint
    assert first_context.core_object_fingerprint == second_context.core_object_fingerprint
    assert third_context.core_object_fingerprint != second_context.core_object_fingerprint
    assert fourth_context.planning_goal_fingerprint != third_context.planning_goal_fingerprint


def test_affordability_context_uses_scenario_planning_goal_id_without_scenario_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例目标 ID 房源",
                    "total_price": 1_600_000,
                    "purchase_sequence": 1,
                    "manual_purchase_delay_months": 9,
                },
            },
        ).json()
        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
            },
        )

    assert response.status_code == 200
    context = response.json()["calculation_context"]
    assert context["scenario_id"] == ""
    assert context["current_goal_id"] == scenario["id"]
    assert context["current_goal_name"] == "示例目标 ID 房源"
    assert context["current_goal_resolved_not_before_month"] == 9
    assert any(goal["id"] == scenario["id"] for goal in context["planning_goals"])


def test_affordability_context_without_household_id_does_not_read_all_database_goals(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["cash_account_balance"] = 180_000
        client.put(f"/api/households/{household['id']}", json={"data": household_payload})
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例不应泄漏的数据库目标",
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "target_params": {"total_price": 1_800_000},
                },
            },
        )
        rule_pack = client.get("/api/rule-packs").json()[0]
        response = client.post(
            "/api/calculations/affordability",
            json={
                "household": household["data"],
                "scenario": {"name": "临时测算房源", "total_price": 1_000_000},
                "rule_pack": rule_pack["data"],
            },
        )

    assert response.status_code == 200
    context = response.json()["calculation_context"]
    assert context["household_id"] == ""
    assert context["planning_goals"] == []
    assert context["core_objects"] == []
    assert context["planning_goal_ids"] == []
    assert context["core_object_ids"] == []
    assert context["resolved_goal_count"] == 0
    assert context["core_object_count"] == 0


def test_affordability_cache_persists_layer_hashes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["members"] = []
        household_payload["monthly_income"] = 30_000
        household_payload["monthly_expense"] = 4_000
        household_payload["cash_account_balance"] = 100_000
        household_payload["investments"] = 0
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例缓存房源",
                    "total_price": 1_800_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
            },
        )

    assert response.status_code == 200
    layers = response.json()["cache_layers"]
    with database.get_connection() as conn:
        cache_row = conn.execute("SELECT * FROM calculation_cache").fetchone()
        strategy_row = conn.execute("SELECT * FROM generated_strategies LIMIT 1").fetchone()
        purchase_strategy_row = conn.execute(
            "SELECT * FROM generated_strategies WHERE strategy_type = 'purchase' LIMIT 1"
        ).fetchone()

    assert cache_row is not None
    assert cache_row["input_hash"] == layers["input"]
    assert cache_row["strategy_hash"] == layers["strategy"]
    assert cache_row["ledger_hash"] == layers["ledger"]
    assert cache_row["visualization_hash"] == layers["visualization"]
    assert strategy_row is not None
    assert strategy_row["input_hash"] == layers["input"]
    assert strategy_row["strategy_hash"] == layers["strategy"]
    assert strategy_row["ledger_hash"] == layers["ledger"]
    assert strategy_row["visualization_hash"] == layers["visualization"]
    assert purchase_strategy_row is not None
    assert purchase_strategy_row["owner_key"] == scenario["id"]


def test_affordability_cache_hit_rehydrates_generated_strategies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例缓存策略房源",
                    "total_price": 1_800_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        payload = {
            "household_id": household["id"],
            "scenario_id": scenario["id"],
            "household": household["data"],
            "scenario": scenario["data"],
            "rule_pack": rule_pack["data"],
        }
        first_response = client.post("/api/calculations/affordability", json=payload)
        first_rows = client.get("/api/generated-strategies").json()
        with database.get_connection() as conn:
            cache_row = conn.execute("SELECT cache_key, result FROM calculation_cache LIMIT 1").fetchone()
            stale_payload = json.loads(cache_row["result"])
            stale_payload.pop("cache_layers", None)
            conn.execute(
                "UPDATE calculation_cache SET result = ? WHERE cache_key = ?",
                (json.dumps(stale_payload, ensure_ascii=False), cache_row["cache_key"]),
            )
            conn.execute("DELETE FROM generated_strategies")
        second_response = client.post("/api/calculations/affordability", json=payload)
        second_rows = client.get("/api/generated-strategies").json()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_rows
    assert second_rows
    assert second_response.json()["cache_layers"] == first_response.json()["cache_layers"]
    assert second_response.json()["calculation_context"] is not None
    assert {row["variant"] for row in second_rows} == {row["variant"] for row in first_rows}


def test_cleanup_database_storage_clears_generated_strategy_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database

    database.DB_PATH = database.default_db_path()
    database.initialize_database()
    timestamp = database.now_iso()

    with database.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO calculation_cache (
                cache_key, engine_fingerprint, input_hash, strategy_hash,
                ledger_hash, visualization_hash, result, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cache-cleanup",
                "engine-cleanup",
                "input-cleanup",
                "strategy-cleanup",
                "ledger-cleanup",
                "visualization-cleanup",
                "{}",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO generated_strategies (
                id, cache_key, engine_fingerprint, input_hash, strategy_hash,
                ledger_hash, visualization_hash, strategy_type, owner_key,
                strategy_key, variant, data, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "strategy-cleanup-row",
                "cache-cleanup",
                "engine-cleanup",
                "input-cleanup",
                "strategy-cleanup",
                "ledger-cleanup",
                "visualization-cleanup",
                "purchase",
                "goal-cleanup",
                "strategy-key-cleanup",
                "variant-cleanup",
                "{}",
                timestamp,
                timestamp,
            ),
        )

    database.cleanup_database_storage(create_backup=False)

    with database.get_connection() as conn:
        cache_count = conn.execute("SELECT COUNT(*) AS count FROM calculation_cache").fetchone()["count"]
        strategy_count = conn.execute("SELECT COUNT(*) AS count FROM generated_strategies").fetchone()["count"]

    assert cache_count == 0
    assert strategy_count == 0


def test_affordability_cache_without_monthly_details_is_rebuilt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.cache import affordability_cache_key
    from app.main import app
    from app.planning_context import apply_planning_goal_constraints
    from app.schemas import AffordabilityRequest

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["members"] = []
        household_payload["monthly_income"] = 30_000
        household_payload["monthly_expense"] = 4_000
        household_payload["cash_account_balance"] = 100_000
        household_payload["investments"] = 0
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例旧缓存房源",
                    "total_price": 1_500_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        payload = {
            "household_id": household["id"],
            "scenario_id": scenario["id"],
            "household": household_payload,
            "scenario": scenario["data"],
            "rule_pack": rule_pack["data"],
        }
        request_model = apply_planning_goal_constraints(AffordabilityRequest.model_validate(payload))
        cache_key, engine_fingerprint, cache_layers = affordability_cache_key(request_model)
        stale_result = {
            "monthly_cashflow_visualization": [
                {
                    "plan_variant": "stale",
                    "month": 1,
                    "cash_income": 30_000,
                    "living_expense": 4_000,
                    "monthly_cash_delta": 26_000,
                    "ledger_entries": [],
                }
            ],
            "monthly_visualization_details": [
                {
                    "plan_variant": "stale",
                    "month": 1,
                    "cash_flow_items": [],
                }
            ],
        }
        with database.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO calculation_cache (
                    cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                    visualization_hash, result, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    engine_fingerprint,
                    cache_layers.input,
                    cache_layers.strategy,
                    cache_layers.ledger,
                    cache_layers.visualization,
                    json.dumps(stale_result),
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )

        response = client.post("/api/calculations/affordability", json=payload)

    assert response.status_code == 200
    result = response.json()
    assert result["monthly_cashflow_visualization"]
    assert result["monthly_visualization_details"]
    non_empty_detail = next(
        item for item in result["monthly_visualization_details"] if item["cash_flow_items"]
    )
    assert any(item["kind"] == "income" for item in non_empty_detail["cash_flow_items"])


def test_affordability_api_applies_planning_goal_purchase_window_to_strategy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["cash_account_balance"] = 1_000_000
        household_payload["investments"] = 0
        household_payload["monthly_expense"] = 3_000
        household_payload["members"] = [
            {
                **household_payload["members"][0],
                "name": "样例成员A",
                "monthly_salary_gross": 30_000,
                "income_stages": [
                    {
                        **household_payload["members"][0]["income_stages"][0],
                        "monthly_salary_gross": 30_000,
                    }
                ],
            }
        ]
        household = client.put(f"/api/households/{household['id']}", json={"data": household_payload}).json()
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例窗口房源",
                    "total_price": 1_000_000,
                    "down_payment_amount": 300_000,
                    "manual_purchase_delay_months": 0,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        goals = client.get("/api/planning-goals", params={"goal_type": "home"}).json()
        goal = next(item for item in goals if item["id"] == scenario["id"])
        goal_payload = deepcopy(goal["data"])
        goal_payload["earliest_purchase_delay_months"] = 24
        client.put(f"/api/planning-goals/{goal['id']}", json={"household_id": household["id"], "data": goal_payload})

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": {
                    **scenario["data"],
                    "manual_purchase_delay_months": 0,
                },
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["calculation_context"]["current_goal_id"] == scenario["id"]
    assert result["calculation_context"]["current_goal_resolved_not_before_month"] == 24
    assert {plan["source"] for plan in result["purchase_plan_analyses"]} == {"planning_goals"}
    assert {plan["planning_goal_id"] for plan in result["purchase_plan_analyses"]} == {scenario["id"]}
    plan_months = [
        plan["months_to_buy"]
        for plan in result["purchase_plan_analyses"]
        if plan["months_to_buy"] is not None
    ]
    assert plan_months
    assert min(plan_months) >= 24


def test_affordability_api_projects_home_goal_when_scenario_payload_is_stale(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["members"] = []
        household_payload["cash_account_balance"] = 900_000
        household_payload["investments"] = 0
        household_payload["monthly_income"] = 45_000
        household_payload["monthly_expense"] = 5_000
        household = client.put(f"/api/households/{household['id']}", json={"data": household_payload}).json()
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例真源房源",
                    "total_price": 2_600_000,
                    "down_payment_amount": 780_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": {
                    **scenario["data"],
                    "planning_goal_id": "",
                    "total_price": 1_200_000,
                    "down_payment_amount": 360_000,
                },
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["calculation_context"]["current_goal_id"] == scenario["id"]
    plans = result["purchase_plan_analyses"]
    assert plans
    assert {plan["planning_goal_id"] for plan in plans} == {scenario["id"]}
    assert all(
        plan["planned_down_payment"] + plan["commercial_loan_amount"] + plan["provident_loan_amount"]
        >= 2_500_000
        for plan in plans
    )


def test_affordability_api_respects_not_planned_home_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "暂不纳入规划房源",
                    "total_price": 1_000_000,
                    "enabled": True,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        goal = next(
            item
            for item in client.get("/api/planning-goals", params={"goal_type": "home"}).json()
            if item["id"] == scenario["id"]
        )
        goal_payload = deepcopy(goal["data"])
        goal_payload["timing_mode"] = "not_planned"
        goal_payload["enabled"] = False
        client.put(f"/api/planning-goals/{goal['id']}", json={"household_id": household["id"], "data": goal_payload})
        projected_scenario = next(
            item for item in client.get("/api/scenarios", params={"household_id": household["id"]}).json()
            if item["id"] == scenario["id"]
        )

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": {
                    **scenario["data"],
                    "enabled": True,
                },
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    goal_snapshot = next(goal for goal in result["calculation_context"]["planning_goals"] if goal["id"] == scenario["id"])
    assert goal_snapshot["normalized_timing_mode"] == "not_planned"
    assert goal_snapshot["enabled"] is False
    assert projected_scenario["data"]["enabled"] is False
    assert result["purchase_plan_analyses"][0]["source"] == "baseline"
    assert result["purchase_plan_analyses"][0]["variant"] == "家庭基线"
    assert result["monthly_cashflow_visualization"]
    assert {item["plan_variant"] for item in result["monthly_cashflow_visualization"]} == {"家庭基线"}
    assert all(event["category"] != "home_purchase" for event in result["plan_events"])


def test_affordability_api_respects_home_planning_window_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["cash_account_balance"] = 20_000
        household_payload["investments"] = 0
        household_payload["monthly_expense"] = 6_000
        household_payload["members"] = [
            {
                **household_payload["members"][0],
                "name": "样例成员A",
                "monthly_salary_gross": 12_000,
                "income_stages": [
                    {
                        **household_payload["members"][0]["income_stages"][0],
                        "monthly_salary_gross": 12_000,
                    }
                ],
            }
        ]
        household = client.put(f"/api/households/{household['id']}", json={"data": household_payload}).json()
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "窗口很短房源",
                    "total_price": 1_000_000,
                    "down_payment_amount": 300_000,
                    "manual_purchase_delay_months": 0,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        goal = next(
            item
            for item in client.get("/api/planning-goals", params={"goal_type": "home"}).json()
            if item["id"] == scenario["id"]
        )
        goal_payload = deepcopy(goal["data"])
        goal_payload["planning_window_start_month"] = "2026-07"
        goal_payload["planning_window_end_month"] = "2026-08"
        client.put(f"/api/planning-goals/{goal['id']}", json={"household_id": household["id"], "data": goal_payload})

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    goal_snapshot = next(goal for goal in result["calculation_context"]["planning_goals"] if goal["id"] == scenario["id"])
    assert goal_snapshot["resolved_window_end_month"] is not None
    assert goal_snapshot["resolved_window_end_month"] <= 1
    assert result["purchase_plan_analyses"]
    assert all(plan["months_to_buy"] is None for plan in result["purchase_plan_analyses"])


def test_affordability_api_applies_child_planning_goal_to_strategy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "样例成员A",
                "sex": "female",
                "birth_month": "2000-01",
            }
        ]
        payload["child_plans"] = [
            {
                "name": "示例子女计划",
                "enabled": True,
                "timing_mode": "manual_month",
                "expense_strategy_mode": "balanced",
                "planned_birth_month": "2028-01",
                "planned_birth_start_month": "",
                "planned_birth_end_month": "",
                "birth_month": "",
                "tax_deduction_owner": "",
                "education_start_month": "",
                "preparation_months_before_birth": 6,
                "pregnancy_months_before_birth": 9,
                "monthly_preparation_cost": 1500,
                "monthly_pregnancy_cost": 3000,
                "birth_medical_cost": 30000,
                "postpartum_recovery_cost": 40000,
                "initial_baby_supplies_cost": 20000,
                "monthly_childcare_cost_before_kindergarten": 4500,
                "monthly_kindergarten_cost": 5000,
                "monthly_primary_secondary_cost": 6000,
                "monthly_higher_education_cost": 8000,
                "kindergarten_entry_cost": 10000,
                "primary_school_entry_cost": 15000,
                "higher_education_entry_cost": 50000,
                "notes": "",
            }
        ]
        household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        child_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()[0]
        goal_payload = deepcopy(child_goal["data"])
        goal_payload["timing_mode"] = "manual_month"
        goal_payload["earliest_purchase_month"] = "2030-06"
        goal_payload["planning_window_start_month"] = "2030-06"
        goal_payload["planning_window_end_month"] = "2030-06"
        client.put(
            f"/api/planning-goals/{child_goal['id']}",
            json={"household_id": household["id"], "data": goal_payload},
        )
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例购房目标",
                    "enabled": False,
                    "total_price": 2_000_000,
                },
            },
        ).json()
        rule_pack = client.get("/api/rule-packs").json()[0]

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    child_strategy = response.json()["child_plan_strategies"][0]
    assert child_strategy["child_name"] == "示例子女计划"
    assert child_strategy["timing_mode"] == "manual_month"
    assert child_strategy["birth_month_label"] == "2030-06"
    assert child_strategy["planning_goal_id"] == child_goal["id"]
    assert child_strategy["source"] == "planning_goals"


def test_affordability_api_projects_child_goals_when_payload_child_plans_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "样例成员A",
                "sex": "female",
                "birth_month": "2000-01",
            }
        ]
        payload["child_plans"] = []
        child_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例目标子女",
                    "enabled": True,
                    "priority": 31,
                    "timing_mode": "manual_month",
                    "earliest_purchase_month": "2031-05",
                    "planning_window_start_month": "2031-05",
                    "planning_window_end_month": "2031-05",
                    "target_params": {
                        "name": "示例目标子女",
                        "expense_strategy_mode": "balanced",
                        "planned_birth_month": "2031-05",
                        "monthly_childcare_cost_before_kindergarten": 4600,
                        "monthly_kindergarten_cost": 5200,
                        "monthly_primary_secondary_cost": 6300,
                        "monthly_higher_education_cost": 8200,
                    },
                },
            },
        ).json()
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例购房目标",
                    "enabled": False,
                    "total_price": 2_000_000,
                },
            },
        ).json()
        rule_pack = client.get("/api/rule-packs").json()[0]

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": payload,
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    child_strategies = response.json()["child_plan_strategies"]
    assert child_strategies
    child_strategy = child_strategies[0]
    assert child_strategy["child_name"] == "示例目标子女"
    assert child_strategy["birth_month_label"] == "2031-05"
    assert child_strategy["planning_goal_id"] == child_goal["id"]
    assert child_strategy["source"] == "planning_goals"
    assert any(
        item["id"] == child_goal["id"] and item["goal_type"] == "child"
        for item in response.json()["calculation_context"]["planning_goals"]
    )


def test_affordability_api_disables_child_plan_from_planning_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["child_plans"] = [
            {
                "name": "示例暂缓子女计划",
                "enabled": True,
                "timing_mode": "manual_month",
                "expense_strategy_mode": "balanced",
                "planned_birth_month": "2028-01",
                "planned_birth_start_month": "",
                "planned_birth_end_month": "",
                "birth_month": "",
                "tax_deduction_owner": "",
                "education_start_month": "",
                "preparation_months_before_birth": 6,
                "pregnancy_months_before_birth": 9,
                "monthly_preparation_cost": 1500,
                "monthly_pregnancy_cost": 3000,
                "birth_medical_cost": 30000,
                "postpartum_recovery_cost": 40000,
                "initial_baby_supplies_cost": 20000,
                "monthly_childcare_cost_before_kindergarten": 4500,
                "monthly_kindergarten_cost": 5000,
                "monthly_primary_secondary_cost": 6000,
                "monthly_higher_education_cost": 8000,
                "kindergarten_entry_cost": 10000,
                "primary_school_entry_cost": 15000,
                "higher_education_entry_cost": 50000,
                "notes": "",
            }
        ]
        household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        child_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()[0]
        goal_payload = deepcopy(child_goal["data"])
        goal_payload["timing_mode"] = "not_planned"
        goal_payload["enabled"] = False
        client.put(
            f"/api/planning-goals/{child_goal['id']}",
            json={"household_id": household["id"], "data": goal_payload},
        )
        projected_household = client.get("/api/households").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例购房目标",
                    "enabled": False,
                    "total_price": 2_000_000,
                },
            },
        ).json()
        rule_pack = client.get("/api/rule-packs").json()[0]

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    child_strategy = response.json()["child_plan_strategies"][0]
    projected_child = projected_household["data"]["child_plans"][0]
    assert projected_child["enabled"] is False
    assert projected_child["timing_mode"] == "not_planned"
    assert child_strategy["child_name"] == "示例暂缓子女计划"
    assert child_strategy["enabled"] is False
    assert child_strategy["timing_mode"] == "not_planned"


def test_scenario_api_is_backed_by_planning_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        created = client.post(
            "/api/scenarios",
            json={
                "data": {
                    "name": "示例房源 A",
                    "total_price": 3_200_000,
                    "purchase_sequence": 2,
                    "purchase_planning_mode": "after_previous_purchase",
                    "depends_on_goal_id": "anchor-home-goal",
                    "planning_window_start_month": "2028-01",
                    "planning_window_end_month": "2029-12",
                    "selected_purchase_plan_variant": "微量商贷",
                }
            },
        ).json()
        goals = client.get("/api/planning-goals", params={"goal_type": "home"}).json()
        goal = next(item for item in goals if item["id"] == created["id"])
        goal_payload = deepcopy(goal["data"])
        goal_payload["name"] = "示例房源 A 调整"
        goal_payload["priority"] = 3
        goal_payload["timing_mode"] = "auto_sequence"
        updated_goal = client.put(f"/api/planning-goals/{goal['id']}", json={"data": goal_payload}).json()
        scenarios = client.get("/api/scenarios").json()

    projected = next(item for item in scenarios if item["id"] == created["id"])
    assert created["data"]["total_price"] == 3_200_000
    assert goal["goal_type"] == "home"
    assert goal["data"]["target_params"]["total_price"] == 3_200_000
    assert "purchase_sequence" not in goal["data"]["target_params"]
    assert "depends_on_goal_id" not in goal["data"]["target_params"]
    assert "selected_purchase_plan_variant" not in goal["data"]["target_params"]
    assert "provident_rate" not in goal["data"]["target_params"]
    assert "deed_tax_rate" not in goal["data"]["target_params"]
    assert goal["data"]["planning_window_start_month"] == "2028-01"
    assert goal["data"]["planning_window_end_month"] == "2029-12"
    assert goal["data"]["timing_mode"] == "after_goal"
    assert goal["data"]["depends_on_goal_id"] == "anchor-home-goal"
    assert goal["data"]["selected_strategy_id"] == "微量商贷"
    assert updated_goal["data"]["name"] == "示例房源 A 调整"
    assert projected["data"]["name"] == "示例房源 A 调整"
    assert projected["data"]["planning_goal_id"] == created["id"]
    assert projected["data"]["depends_on_goal_id"] == "anchor-home-goal"
    assert projected["data"]["purchase_sequence"] == 1
    assert projected["data"]["purchase_planning_mode"] == "after_previous_purchase"
    assert projected["data"]["planning_window_start_month"] == "2028-01"
    assert projected["data"]["planning_window_end_month"] == "2029-12"


def test_scenario_api_filters_home_goals_by_household_scope(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post("/api/households", json={"data": first_household["data"]}).json()
        first_home = client.post(
            "/api/scenarios",
            json={
                "household_id": first_household["id"],
                "data": {
                    "name": "第一家庭房源",
                    "total_price": 2_800_000,
                    "purchase_sequence": 2,
                },
            },
        ).json()
        second_home = client.post(
            "/api/scenarios",
            json={
                "household_id": second_household["id"],
                "data": {
                    "name": "第二家庭房源",
                    "total_price": 3_200_000,
                    "purchase_sequence": 2,
                },
            },
        ).json()
        global_home = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "home",
                    "name": "全局示例房源",
                    "enabled": True,
                    "priority": 1,
                    "target_params": {
                        "name": "全局示例房源",
                        "total_price": 1_800_000,
                    },
                },
            },
        ).json()
        scoped = client.get("/api/scenarios", params={"household_id": first_household["id"]}).json()
        unscoped = client.get("/api/scenarios").json()

    scoped_ids = {item["id"] for item in scoped}
    assert scoped_ids == {first_home["id"], global_home["id"]}
    assert second_home["id"] not in scoped_ids
    assert {first_home["id"], second_home["id"], global_home["id"]} <= {item["id"] for item in unscoped}
    scoped_by_id = {item["id"]: item for item in scoped}
    assert scoped_by_id[global_home["id"]]["data"]["purchase_sequence"] == 1
    assert scoped_by_id[first_home["id"]]["data"]["purchase_sequence"] == 2


def test_create_scenario_preserves_household_scope(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        created = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "家庭作用域房源",
                    "total_price": 2_600_000,
                },
            },
        ).json()
        goal = client.get("/api/planning-goals", params={"household_id": household["id"], "goal_type": "home"}).json()[0]
        scoped = client.get("/api/scenarios", params={"household_id": household["id"]}).json()

    assert created["household_id"] == household["id"]
    assert goal["id"] == created["id"]
    assert goal["household_id"] == household["id"]
    assert {item["id"] for item in scoped} == {created["id"]}


def test_planning_goal_api_filters_by_household_scope_with_global_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post("/api/households", json={"data": first_household["data"]}).json()
        first_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": first_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "第一家庭车辆目标",
                    "target_params": {"name": "第一家庭车辆目标", "total_price": 120_000},
                },
            },
        ).json()
        second_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": second_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "第二家庭车辆目标",
                    "target_params": {"name": "第二家庭车辆目标", "total_price": 180_000},
                },
            },
        ).json()
        global_vehicle_goal = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "vehicle",
                    "name": "全局车辆模板",
                    "target_params": {"name": "全局车辆模板", "total_price": 150_000},
                },
            },
        ).json()
        global_home_goal = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "home",
                    "name": "全局房源模板",
                    "target_params": {"name": "全局房源模板", "total_price": 2_000_000},
                },
            },
        ).json()

        scoped = client.get("/api/planning-goals", params={"household_id": first_household["id"]}).json()
        scoped_vehicle = client.get(
            "/api/planning-goals",
            params={"household_id": first_household["id"], "goal_type": "vehicle"},
        ).json()
        unscoped = client.get("/api/planning-goals").json()

    assert {item["id"] for item in scoped} == {
        first_goal["id"],
        global_vehicle_goal["id"],
        global_home_goal["id"],
    }
    assert {item["id"] for item in scoped_vehicle} == {first_goal["id"], global_vehicle_goal["id"]}
    assert second_goal["id"] not in {item["id"] for item in scoped}
    assert {first_goal["id"], second_goal["id"], global_vehicle_goal["id"], global_home_goal["id"]} <= {
        item["id"] for item in unscoped
    }


def test_planning_goal_list_e2e_preserves_scope_order_and_shadow_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post("/api/households", json={"data": first_household["data"]}).json()
        home_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": first_household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例列表验收买房",
                    "enabled": True,
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 6,
                    "target_params": {"total_price": 3_200_000},
                },
            },
        ).json()
        vehicle_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": first_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例列表验收买车",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": home_goal["id"],
                    "delay_after_dependency_months": 4,
                    "target_params": {"name": "示例列表验收买车", "total_price": 180_000},
                },
            },
        ).json()
        child_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": first_household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例列表验收养娃",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": vehicle_goal["id"],
                    "delay_after_dependency_months": 8,
                    "target_params": {"name": "示例列表验收养娃"},
                },
            },
        ).json()
        second_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": second_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例第二家庭隔离目标",
                    "priority": 1,
                    "target_params": {"name": "示例第二家庭隔离目标", "total_price": 220_000},
                },
            },
        ).json()

        updated_vehicle_data = deepcopy(vehicle_goal["data"])
        updated_vehicle_data["priority"] = 5
        updated_vehicle_data["target_params"] = {
            **updated_vehicle_data["target_params"],
            "total_price": 190_000,
        }
        client.put(
            f"/api/planning-goals/{vehicle_goal['id']}",
            json={"household_id": first_household["id"], "data": updated_vehicle_data},
        )

        goals = client.get("/api/planning-goals", params={"household_id": first_household["id"]}).json()
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": first_household["id"]}).json()
        foundation = client.get("/api/planning-foundation", params={"household_id": first_household["id"]}).json()
        projected_household = client.get("/api/households").json()[0]
        raw_household = database.get_record("households", first_household["id"])
        second_goals = client.get("/api/planning-goals", params={"household_id": second_household["id"]}).json()

    first_ids = {home_goal["id"], vehicle_goal["id"], child_goal["id"]}
    assert {item["id"] for item in goals} == first_ids
    assert second_goal["id"] not in {item["id"] for item in goals}
    assert second_goal["id"] in {item["id"] for item in second_goals}
    assert foundation["planning_goals"] == goals
    assert {item["id"] for item in foundation["planning_sequence"]["goals"]} == first_ids
    assert {item["id"] for item in sequence["goals"]} == first_ids

    sequence_by_id = {item["id"]: item for item in sequence["goals"]}
    assert sequence_by_id[home_goal["id"]]["sequence_index"] == 1
    assert sequence_by_id[vehicle_goal["id"]]["depends_on_goal_id"] == home_goal["id"]
    assert sequence_by_id[child_goal["id"]]["depends_on_goal_id"] == vehicle_goal["id"]
    assert sequence_by_id[vehicle_goal["id"]]["resolved_not_before_month"] == 10
    assert sequence_by_id[child_goal["id"]]["resolved_not_before_month"] == 18
    assert not sequence["warnings"]

    projected_vehicle_ids = {
        item["planning_goal_id"]
        for item in projected_household["data"]["car_plan"]["vehicle_plans"]
    }
    projected_child_ids = {
        item["planning_goal_id"]
        for item in projected_household["data"]["child_plans"]
    }
    assert vehicle_goal["id"] in projected_vehicle_ids
    assert child_goal["id"] in projected_child_ids
    assert raw_household["data"]["car_plan"]["vehicle_plans"] == []
    assert raw_household["data"]["child_plans"] == []


def test_update_scenario_preserves_household_scope_when_payload_omits_household_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post("/api/households", json={"data": first_household["data"]}).json()
        created = client.post(
            "/api/scenarios",
            json={
                "household_id": first_household["id"],
                "data": {
                    "name": "家庭作用域房源",
                    "total_price": 2_600_000,
                },
            },
        ).json()

        updated = client.put(
            f"/api/scenarios/{created['id']}",
            json={
                "data": {
                    **created["data"],
                    "name": "家庭作用域房源调整",
                    "total_price": 2_900_000,
                },
            },
        ).json()
        goal = client.get(
            "/api/planning-goals",
            params={"household_id": first_household["id"], "goal_type": "home"},
        ).json()[0]
        first_scoped = client.get("/api/scenarios", params={"household_id": first_household["id"]}).json()
        second_scoped = client.get("/api/scenarios", params={"household_id": second_household["id"]}).json()
        unscoped = client.get("/api/scenarios").json()

    assert updated["household_id"] == first_household["id"]
    assert goal["id"] == created["id"]
    assert goal["household_id"] == first_household["id"]
    assert goal["data"]["target_params"]["total_price"] == 2_900_000
    assert {item["id"] for item in first_scoped} == {created["id"]}
    assert created["id"] not in {item["id"] for item in second_scoped}
    assert created["id"] in {item["id"] for item in unscoped}


def test_home_planning_goal_crud_does_not_write_scenario_shadow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        created = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "home",
                    "name": "示例直接目标房源",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "parallel",
                    "planning_window_start_month": "2028-03",
                    "planning_window_end_month": "2029-03",
                    "selected_strategy_id": "微量商贷",
                    "target_params": {
                        "name": "示例直接目标房源",
                        "enabled": True,
                        "total_price": 3_100_000,
                        "purchase_sequence": 2,
                        "purchase_planning_mode": "parallel",
                        "depends_on_goal_id": "stale-anchor",
                        "planning_window_start_month": "2028-03",
                        "planning_window_end_month": "2029-03",
                    },
                }
            },
        ).json()
        scenarios_after_create = client.get("/api/scenarios").json()
        shadow_after_create = database.get_record("scenarios", created["id"])

        goal_payload = deepcopy(created["data"])
        goal_payload["name"] = "示例直接目标房源调整"
        goal_payload["target_params"]["total_price"] = 3_300_000
        updated = client.put(f"/api/planning-goals/{created['id']}", json={"data": goal_payload}).json()
        scenarios_after_update = client.get("/api/scenarios").json()
        shadow_after_update = database.get_record("scenarios", created["id"])

        delete_response = client.delete(f"/api/planning-goals/{created['id']}")
        scenarios_after_delete = client.get("/api/scenarios").json()
        shadow_after_delete = database.get_record("scenarios", created["id"])

    projected_after_create = next(item for item in scenarios_after_create if item["id"] == created["id"])
    projected_after_update = next(item for item in scenarios_after_update if item["id"] == created["id"])
    assert created["goal_type"] == "home"
    assert projected_after_create["data"]["planning_goal_id"] == created["id"]
    assert projected_after_create["data"]["total_price"] == 3_100_000
    assert "depends_on_goal_id" not in created["data"]["target_params"]
    assert shadow_after_create is None
    assert updated["data"]["name"] == "示例直接目标房源调整"
    assert projected_after_update["data"]["name"] == "示例直接目标房源调整"
    assert projected_after_update["data"]["planning_goal_id"] == created["id"]
    assert projected_after_update["data"]["total_price"] == 3_300_000
    assert shadow_after_update is None
    assert delete_response.status_code == 200
    assert all(item["id"] != created["id"] for item in scenarios_after_delete)
    assert shadow_after_delete is None


def test_planning_goal_crud_does_not_upsert_scenario_shadow() -> None:
    import re

    database_source = Path("backend/app/database.py").read_text(encoding="utf-8")
    insert_match = re.search(
        r"def insert_planning_goal_record\((?P<body>.*?)\n\ndef update_planning_goal_record",
        database_source,
        re.DOTALL,
    )
    update_match = re.search(
        r"def update_planning_goal_record\((?P<body>.*?)\n\ndef delete_planning_goal_record",
        database_source,
        re.DOTALL,
    )
    scenario_insert_match = re.search(
        r"def insert_scenario_record\((?P<body>.*?)\n\ndef update_scenario_record",
        database_source,
        re.DOTALL,
    )
    assert insert_match is not None
    assert update_match is not None
    assert scenario_insert_match is not None

    assert "INSERT INTO scenarios" not in insert_match.group("body")
    assert "INSERT OR REPLACE INTO scenarios" not in insert_match.group("body")
    assert "INSERT INTO scenarios" not in update_match.group("body")
    assert "INSERT OR REPLACE INTO scenarios" not in update_match.group("body")
    assert "DELETE FROM scenarios" in update_match.group("body")
    assert "INSERT OR REPLACE INTO scenarios" in scenario_insert_match.group("body")


def test_changing_vehicle_planning_goal_to_home_cleans_old_household_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例待转房源车辆目标",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "total_price": 180_000,
                    "planning_sequence": 2,
                }
            ],
        }
        saved_household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        vehicle_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()[0]
        assert saved_household["data"]["car_plan"]["vehicle_plans"][0]["planning_goal_id"] == vehicle_goal["id"]

        updated_response = client.put(
            f"/api/planning-goals/{vehicle_goal['id']}",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例转为房源目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例转为房源目标",
                        "total_price": 2_800_000,
                    },
                },
            },
        )
        projected_household = client.get("/api/households").json()[0]
        scenarios = client.get("/api/scenarios", params={"household_id": household["id"]}).json()
        raw_household = database.get_record("households", household["id"])
        vehicle_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": vehicle_goal["id"], "category": "vehicle_asset"},
        ).json()
        property_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": vehicle_goal["id"], "category": "property_asset"},
        ).json()

    assert updated_response.status_code == 200
    assert updated_response.json()["goal_type"] == "home"
    assert projected_household["data"]["car_plan"]["vehicle_plans"] == []
    assert raw_household["data"]["car_plan"]["vehicle_plans"] == []
    assert any(item["id"] == vehicle_goal["id"] for item in scenarios)
    assert vehicle_objects == []
    assert len(property_objects) == 1
    assert property_objects[0]["data"]["metadata"]["goal_type"] == "home"


def test_changing_home_planning_goal_to_vehicle_does_not_depend_on_scenario_shadow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        home_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例待转车辆房源目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例待转车辆房源目标",
                        "total_price": 2_800_000,
                    },
                },
            },
        ).json()
        assert database.get_record("scenarios", home_goal["id"]) is None

        updated_response = client.put(
            f"/api/planning-goals/{home_goal['id']}",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例转为车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例转为车辆目标",
                        "total_price": 180_000,
                    },
                },
            },
        )
        projected_household = client.get("/api/households").json()[0]
        scenarios = client.get("/api/scenarios", params={"household_id": household["id"]}).json()
        shadow_after_update = database.get_record("scenarios", home_goal["id"])
        property_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": home_goal["id"], "category": "property_asset"},
        ).json()
        vehicle_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": home_goal["id"], "category": "vehicle_asset"},
        ).json()

    assert updated_response.status_code == 200
    assert updated_response.json()["goal_type"] == "vehicle"
    assert shadow_after_update is None
    assert all(item["id"] != home_goal["id"] for item in scenarios)
    assert [item["planning_goal_id"] for item in projected_household["data"]["car_plan"]["vehicle_plans"]] == [home_goal["id"]]
    assert property_objects == []
    assert len(vehicle_objects) == 1
    assert vehicle_objects[0]["data"]["metadata"]["goal_type"] == "vehicle"


def test_vehicle_plan_api_is_backed_by_planning_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例用车需求",
                    "selected_strategy_variant": "target",
                    "vehicle_plans": [],
                    "candidate_vehicles": [
                        {
                            **payload["car_plan"],
                            "enabled": True,
                            "name": "示例电车",
                            "vehicle_plans": [],
                            "candidate_vehicles": [],
                            "total_price": 180_000,
                            "down_payment_ratio": 0.3,
                        }
                    ],
                    "total_price": 180_000,
                    "planning_sequence": 2,
                    "purchase_timing_mode": "auto_sequence",
                    "depends_on_goal_id": "anchor-vehicle-goal",
                    "planning_window_start_month": "2028-06",
                    "planning_window_end_month": "2029-06",
                }
            ],
        }

        saved = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        vehicle_goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()
        goal_payload = deepcopy(vehicle_goals[0]["data"])
        goal_payload["name"] = "示例用车需求调整"
        goal_payload["priority"] = 4
        client.put(f"/api/planning-goals/{vehicle_goals[0]['id']}", json={"household_id": household["id"], "data": goal_payload})
        projected_household = client.get("/api/households").json()[0]

    assert saved["data"]["car_plan"]["vehicle_plans"][0]["name"] == "示例用车需求"
    assert len(vehicle_goals) == 1
    assert vehicle_goals[0]["goal_type"] == "vehicle"
    assert vehicle_goals[0]["data"]["target_params"]["candidate_vehicles"][0]["name"] == "示例电车"
    assert "planning_sequence" not in vehicle_goals[0]["data"]["target_params"]
    assert "purchase_timing_mode" not in vehicle_goals[0]["data"]["target_params"]
    assert "depends_on_goal_id" not in vehicle_goals[0]["data"]["target_params"]
    assert "selected_strategy_variant" not in vehicle_goals[0]["data"]["target_params"]
    assert vehicle_goals[0]["data"]["timing_mode"] == "after_goal"
    assert vehicle_goals[0]["data"]["depends_on_goal_id"] == "anchor-vehicle-goal"
    assert vehicle_goals[0]["data"]["planning_window_start_month"] == "2028-06"
    assert vehicle_goals[0]["data"]["planning_window_end_month"] == "2029-06"
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["name"] == "示例用车需求调整"
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["planning_sequence"] == 1
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["depends_on_goal_id"] == "anchor-vehicle-goal"
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["planning_window_start_month"] == "2028-06"
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["planning_window_end_month"] == "2029-06"


def test_vehicle_planning_goal_crud_projects_household_vehicle_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "sample vehicle demand",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "parallel",
                    "planning_window_start_month": "2028-06",
                    "planning_window_end_month": "2029-06",
                    "selected_strategy_id": "target",
                    "target_params": {
                        "name": "sample vehicle demand",
                        "enabled": True,
                        "selected_strategy_variant": "target",
                        "vehicle_plans": [],
                        "candidate_vehicles": [
                            {
                                "name": "sample ev",
                                "enabled": True,
                                "vehicle_plans": [],
                                "candidate_vehicles": [],
                                "total_price": 180_000,
                                "down_payment_ratio": 0.3,
                            }
                        ],
                        "total_price": 180_000,
                        "planning_sequence": 3,
                        "purchase_timing_mode": "parallel",
                        "planning_window_start_month": "2028-06",
                        "planning_window_end_month": "2029-06",
                    },
                },
            },
        ).json()
        projected_with_vehicle = client.get("/api/households").json()[0]
        delete_response = client.delete(f"/api/planning-goals/{created['id']}")
        projected_without_vehicle = client.get("/api/households").json()[0]

    projected_vehicle = projected_with_vehicle["data"]["car_plan"]["vehicle_plans"][0]
    assert created["goal_type"] == "vehicle"
    assert projected_vehicle["planning_goal_id"] == created["id"]
    assert projected_vehicle["name"] == "sample vehicle demand"
    assert projected_vehicle["purchase_timing_mode"] == "parallel"
    assert projected_vehicle["candidate_vehicles"][0]["name"] == "sample ev"
    assert delete_response.status_code == 200
    assert projected_without_vehicle["data"]["car_plan"]["vehicle_plans"] == []
    assert projected_without_vehicle["data"]["car_plan"]["enabled"] is False


def test_stale_household_update_preserves_direct_vehicle_planning_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        stale_payload = deepcopy(household["data"])
        stale_payload["cash_account_balance"] = 234_567
        stale_payload["car_plan"] = {
            **stale_payload["car_plan"],
            "enabled": False,
            "vehicle_plans": [],
        }
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例直接车辆目标",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "manual_month",
                    "planning_window_start_month": "2028-01",
                    "planning_window_end_month": "2028-12",
                    "target_params": {
                        "name": "示例直接车辆目标",
                        "enabled": True,
                        "vehicle_plans": [],
                        "candidate_vehicles": [],
                        "total_price": 180_000,
                        "down_payment_ratio": 0.3,
                    },
                },
            },
        ).json()
        response = client.put(f"/api/households/{household['id']}", json={"data": stale_payload})
        goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()
        projected_household = client.get("/api/households").json()[0]
        raw_household = database.get_record("households", household["id"])

    assert response.status_code == 200
    assert [goal["id"] for goal in goals] == [created["id"]]
    assert projected_household["data"]["cash_account_balance"] == 234_567
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["planning_goal_id"] == created["id"]
    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["name"] == "示例直接车辆目标"
    assert raw_household is not None
    assert raw_household["data"]["car_plan"]["vehicle_plans"] == []


def test_not_planned_vehicle_goal_projects_disabled_vehicle_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例暂不买车",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "not_planned",
                    "target_params": {
                        "name": "示例暂不买车",
                        "enabled": True,
                        "total_price": 180_000,
                        "down_payment_ratio": 0.3,
                    },
                },
            },
        ).json()
        projected_household = client.get("/api/households").json()[0]
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()
        core_objects = client.get("/api/core-objects", params={"household_id": household["id"]}).json()

    projected_vehicle = projected_household["data"]["car_plan"]["vehicle_plans"][0]
    sequence_goal = next(item for item in sequence["goals"] if item["id"] == created["id"])
    assert projected_vehicle["planning_goal_id"] == created["id"]
    assert projected_vehicle["enabled"] is False
    assert projected_vehicle["purchase_timing_mode"] == "not_planned"
    assert sequence_goal["normalized_timing_mode"] == "not_planned"
    assert sequence_goal["sequence_index"] == 0
    assert all(item["data"]["owner_key"] != created["id"] for item in core_objects)


def test_affordability_api_projects_vehicle_goals_when_payload_vehicle_plans_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": False,
            "vehicle_plans": [],
        }
        vehicle_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例目标车辆",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "manual_month",
                    "earliest_purchase_delay_months": 18,
                    "planning_window_start_month": "2028-01",
                    "planning_window_end_month": "2028-12",
                    "selected_strategy_id": "target",
                    "target_params": {
                        "name": "示例目标车辆",
                        "enabled": True,
                        "vehicle_plans": [],
                        "candidate_vehicles": [],
                        "total_price": 180_000,
                        "down_payment_ratio": 0.3,
                        "later_annual_rate": 0.036,
                    },
                },
            },
        ).json()
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例购房目标",
                    "enabled": False,
                    "total_price": 2_000_000,
                },
            },
        ).json()
        rule_pack = client.get("/api/rule-packs").json()[0]

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": payload,
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    analyses = response.json()["car_plan_analyses"]
    assert analyses
    assert {item["planning_goal_id"] for item in analyses} == {vehicle_goal["id"]}
    assert {item["vehicle_name"] for item in analyses} == {"示例目标车辆"}
    assert {item["source"] for item in analyses} == {"planning_goals"}
    assert any(
        item["id"] == vehicle_goal["id"] and item["goal_type"] == "vehicle"
        for item in response.json()["calculation_context"]["planning_goals"]
    )


def test_delete_vehicle_planning_goal_removes_projected_vehicle_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例待删车辆",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "total_price": 160_000,
                }
            ],
        }
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        vehicle_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()[0]
        response = client.delete(f"/api/planning-goals/{vehicle_goal['id']}")
        projected_household = client.get("/api/households").json()[0]
        vehicle_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "category": "vehicle_asset"},
        ).json()

    assert response.status_code == 200
    assert projected_household["data"]["car_plan"]["vehicle_plans"] == []
    assert projected_household["data"]["car_plan"]["enabled"] is False
    assert vehicle_objects == []


def test_household_projection_uses_global_planning_goal_sequence_for_vehicle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例先购房目标",
                    "total_price": 3_000_000,
                    "purchase_sequence": 1,
                },
            },
        )
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例后购车目标",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "total_price": 180_000,
                    "planning_sequence": 9,
                    "purchase_timing_mode": "auto_sequence",
                }
            ],
        }
        household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        vehicle_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()[0]
        goal_payload = deepcopy(vehicle_goal["data"])
        goal_payload["priority"] = 2
        client.put(f"/api/planning-goals/{vehicle_goal['id']}", json={"household_id": household["id"], "data": goal_payload})
        projected_household = client.get("/api/households").json()[0]

    assert projected_household["data"]["car_plan"]["vehicle_plans"][0]["planning_sequence"] == 2


def test_child_plan_api_is_backed_by_planning_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        home = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例首套房",
                    "total_price": 3_000_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        payload = deepcopy(household["data"])
        payload["child_plans"] = [
            {
                "name": "示例子女计划",
                "enabled": True,
                "planning_sequence": 9,
                "timing_mode": "after_first_home",
                "expense_strategy_mode": "balanced",
                "planned_birth_month": "",
                "planned_birth_start_month": "2029-01",
                "planned_birth_end_month": "2030-12",
                "birth_month": "",
                "tax_deduction_owner": "",
                "education_start_month": "",
                "preparation_months_before_birth": 6,
                "pregnancy_months_before_birth": 9,
                "monthly_preparation_cost": 1500,
                "monthly_pregnancy_cost": 3000,
                "birth_medical_cost": 30000,
                "postpartum_recovery_cost": 40000,
                "initial_baby_supplies_cost": 20000,
                "monthly_childcare_cost_before_kindergarten": 4500,
                "monthly_kindergarten_cost": 5000,
                "monthly_primary_secondary_cost": 6000,
                "monthly_higher_education_cost": 8000,
                "kindergarten_entry_cost": 10000,
                "primary_school_entry_cost": 15000,
                "higher_education_entry_cost": 50000,
                "notes": "",
            }
        ]

        saved = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        child_goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()
        goal_payload = deepcopy(child_goals[0]["data"])
        goal_payload["name"] = "示例子女计划调整"
        goal_payload["timing_mode"] = "manual_month"
        goal_payload["earliest_purchase_month"] = "2030-06"
        client.put(f"/api/planning-goals/{child_goals[0]['id']}", json={"household_id": household["id"], "data": goal_payload})
        projected_household = client.get("/api/households").json()[0]
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    child_plan = saved["data"]["child_plans"][0]
    projected_child = projected_household["data"]["child_plans"][0]
    child_sequence = next(item for item in sequence["goals"] if item["goal_type"] == "child")
    assert child_plan["name"] == "示例子女计划"
    assert child_plan["planning_goal_id"] == child_goals[0]["id"]
    assert len(child_goals) == 1
    assert child_goals[0]["goal_type"] == "child"
    assert child_goals[0]["data"]["target_params"]["name"] == "示例子女计划"
    assert "planning_sequence" not in child_goals[0]["data"]["target_params"]
    assert "timing_mode" not in child_goals[0]["data"]["target_params"]
    assert "planned_birth_start_month" not in child_goals[0]["data"]["target_params"]
    assert "planned_birth_end_month" not in child_goals[0]["data"]["target_params"]
    assert child_goals[0]["data"]["timing_mode"] == "after_goal"
    assert child_goals[0]["data"]["depends_on_goal_id"] == home["id"]
    assert child_goals[0]["data"]["planning_window_start_month"] == "2029-01"
    assert child_goals[0]["data"]["planning_window_end_month"] == "2030-12"
    assert projected_child["name"] == "示例子女计划调整"
    assert projected_child["timing_mode"] == "manual_month"
    assert projected_child["planned_birth_month"] == "2030-06"
    assert child_sequence["name"] == "示例子女计划调整"


def test_delete_child_planning_goal_removes_projected_child_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["child_plans"] = [
            {
                "name": "示例待删子女计划",
                "enabled": True,
                "timing_mode": "after_first_home",
                "expense_strategy_mode": "balanced",
            }
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        child_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()[0]
        response = client.delete(f"/api/planning-goals/{child_goal['id']}")
        projected_household = client.get("/api/households").json()[0]
        child_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "category": "child_goal"},
        ).json()

    assert response.status_code == 200
    assert projected_household["data"]["child_plans"] == []
    assert projected_household["data"]["child_count"] == 0
    assert child_objects == []


def test_changing_child_planning_goal_to_vehicle_removes_child_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["child_plans"] = [
            {
                "name": "示例待转车辆子女目标",
                "enabled": True,
                "timing_mode": "manual_month",
                "planned_birth_month": "2030-06",
                "expense_strategy_mode": "balanced",
            }
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        child_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()[0]

        updated_response = client.put(
            f"/api/planning-goals/{child_goal['id']}",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例转为车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例转为车辆目标",
                        "total_price": 180_000,
                    },
                },
            },
        )
        projected_household = client.get("/api/households").json()[0]
        raw_household = database.get_record("households", household["id"])
        child_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": child_goal["id"], "category": "child_goal"},
        ).json()
        vehicle_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": child_goal["id"], "category": "vehicle_asset"},
        ).json()

    assert updated_response.status_code == 200
    assert updated_response.json()["goal_type"] == "vehicle"
    assert projected_household["data"]["child_plans"] == []
    assert raw_household["data"]["child_plans"] == []
    assert [item["planning_goal_id"] for item in projected_household["data"]["car_plan"]["vehicle_plans"]] == [child_goal["id"]]
    assert child_objects == []
    assert len(vehicle_objects) == 1
    assert vehicle_objects[0]["data"]["metadata"]["goal_type"] == "vehicle"


def test_stale_household_update_preserves_direct_child_planning_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        stale_payload = deepcopy(household["data"])
        stale_payload["investments"] = 123_456
        stale_payload["child_count"] = 0
        stale_payload["child_plans"] = []
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例直接子女目标",
                    "enabled": True,
                    "priority": 5,
                    "timing_mode": "manual_month",
                    "earliest_purchase_month": "2030-05",
                    "target_params": {
                        "name": "示例直接子女目标",
                        "enabled": True,
                        "expense_strategy_mode": "balanced",
                    },
                },
            },
        ).json()
        response = client.put(f"/api/households/{household['id']}", json={"data": stale_payload})
        goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()
        projected_household = client.get("/api/households").json()[0]
        raw_household = database.get_record("households", household["id"])

    assert response.status_code == 200
    assert [goal["id"] for goal in goals] == [created["id"]]
    assert projected_household["data"]["investments"] == 123_456
    assert projected_household["data"]["child_plans"][0]["planning_goal_id"] == created["id"]
    assert projected_household["data"]["child_plans"][0]["name"] == "示例直接子女目标"
    assert raw_household is not None
    assert raw_household["data"]["child_plans"] == []


def test_planning_goal_list_order_has_stable_id_tiebreaker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        created = [
            client.post(
                "/api/planning-goals",
                json={
                    "household_id": household["id"],
                    "data": {
                        "goal_type": "other",
                        "name": f"示例同序目标{index}",
                        "priority": 8,
                        "timing_mode": "auto_sequence",
                        "target_params": {"estimated_cost": 10_000 + index},
                    },
                },
            ).json()
            for index in range(3)
        ]
        created_ids = [goal["id"] for goal in created]
        with database.get_connection() as conn:
            conn.execute(
                f"UPDATE planning_goals SET created_at = ? WHERE id IN ({','.join(['?'] * len(created_ids))})",
                ["2026-07-09T00:00:00+00:00", *created_ids],
            )
        goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "other"},
        ).json()

    returned_created_ids = [goal["id"] for goal in goals if goal["id"] in set(created_ids)]
    assert returned_created_ids == sorted(created_ids)


def test_empty_household_shadow_lists_delete_shadow_planning_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例影子车辆目标",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "total_price": 160_000,
                }
            ],
        }
        payload["child_plans"] = [
            {
                "name": "示例影子子女目标",
                "enabled": True,
                "timing_mode": "manual_month",
                "planned_birth_month": "2030-05",
                "expense_strategy_mode": "balanced",
            }
        ]
        saved = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        delete_payload = deepcopy(saved["data"])
        delete_payload["car_plan"] = {
            **delete_payload["car_plan"],
            "enabled": False,
            "vehicle_plans": [],
        }
        delete_payload["child_count"] = 0
        delete_payload["child_plans"] = []
        response = client.put(f"/api/households/{household['id']}", json={"data": delete_payload})
        vehicle_goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()
        child_goals = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "child"},
        ).json()
        projected_household = client.get("/api/households").json()[0]

    assert response.status_code == 200
    assert vehicle_goals == []
    assert child_goals == []
    assert projected_household["data"]["car_plan"]["vehicle_plans"] == []
    assert projected_household["data"]["child_plans"] == []


def test_planning_goal_sequence_resolves_dependencies_and_parallel_goals(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        first_home = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "home",
                    "name": "示例首套房",
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 12,
                },
            },
        ).json()
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例通勤车",
                    "priority": 2,
                    "timing_mode": "parallel",
                    "allow_parallel": True,
                    "earliest_purchase_delay_months": 3,
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例改善房",
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": first_home["id"],
                    "delay_after_dependency_months": 18,
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "other",
                    "name": "示例缺失依赖目标",
                    "priority": 4,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": "missing-goal",
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    goals = {item["name"]: item for item in sequence["goals"]}
    assert sequence["base_month"] == f"{date.today().year:04d}-{date.today().month:02d}"
    assert [item["name"] for item in sequence["goals"]][:3] == ["示例首套房", "示例通勤车", "示例改善房"]
    assert goals["示例首套房"]["resolved_not_before_month"] == 12
    assert goals["示例首套房"]["sequence_index"] == 1
    assert goals["示例通勤车"]["normalized_timing_mode"] == "parallel"
    assert goals["示例通勤车"]["sequence_index"] == 0
    assert goals["示例通勤车"]["resolved_not_before_month"] == 3
    assert goals["示例改善房"]["depends_on_goal_name"] == "示例首套房"
    assert goals["示例改善房"]["sequence_index"] == 2
    assert goals["示例改善房"]["resolved_not_before_month"] == 30
    assert goals["示例缺失依赖目标"]["normalized_timing_mode"] == "auto_sequence"
    assert sequence["warnings"]


def test_not_planned_goal_does_not_consume_sequence_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例暂不买车",
                    "enabled": False,
                    "priority": 1,
                    "timing_mode": "not_planned",
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例首个有效目标",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "auto_sequence",
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例后续有效目标",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "auto_sequence",
                    "delay_after_dependency_months": 6,
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    goals = {item["name"]: item for item in sequence["goals"]}
    assert goals["示例暂不买车"]["normalized_timing_mode"] == "not_planned"
    assert goals["示例暂不买车"]["sequence_index"] == 0
    assert goals["示例首个有效目标"]["sequence_index"] == 1
    assert goals["示例后续有效目标"]["sequence_index"] == 2
    assert goals["示例后续有效目标"]["depends_on_goal_name"] == "示例首个有效目标"
    assert goals["示例后续有效目标"]["resolved_not_before_month"] == 6


def test_not_planned_goal_window_does_not_emit_strategy_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例暂不规划且窗口过期",
                    "enabled": False,
                    "priority": 1,
                    "timing_mode": "not_planned",
                    "planning_window_start_month": "2030-01",
                    "planning_window_end_month": "2026-08",
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例有效目标窗口过期",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "auto_sequence",
                    "planning_window_start_month": "2030-01",
                    "planning_window_end_month": "2026-08",
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    warnings_text = "\n".join(sequence["warnings"])
    assert "示例暂不规划且窗口过期" not in warnings_text
    assert "示例有效目标窗口过期" in warnings_text


def test_after_goal_dependency_ignores_not_planned_anchor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        disabled_home = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例暂不买房",
                    "enabled": False,
                    "priority": 1,
                    "timing_mode": "not_planned",
                    "earliest_purchase_delay_months": 120,
                },
            },
        ).json()
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例有效买房",
                    "priority": 2,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 12,
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例无效依赖后买车",
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": disabled_home["id"],
                    "delay_after_dependency_months": 6,
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    goals = {item["name"]: item for item in sequence["goals"]}
    vehicle = goals["示例无效依赖后买车"]
    assert goals["示例暂不买房"]["sequence_index"] == 0
    assert vehicle["normalized_timing_mode"] == "auto_sequence"
    assert vehicle["depends_on_goal_name"] == "示例有效买房"
    assert vehicle["resolved_not_before_month"] == 18
    assert "暂不纳入规划" in vehicle["dependency_warning"]
    assert any("暂不纳入规划" in warning for warning in sequence["warnings"])


def test_after_goal_dependency_can_anchor_to_parallel_goal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例顺序买房",
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 12,
                },
            },
        )
        parallel_vehicle = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例并行购车",
                    "priority": 2,
                    "timing_mode": "parallel",
                    "allow_parallel": True,
                    "earliest_purchase_delay_months": 8,
                },
            },
        ).json()
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "renovation",
                    "name": "示例跟随并行目标装修",
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": parallel_vehicle["id"],
                    "delay_after_dependency_months": 5,
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    goals = {item["name"]: item for item in sequence["goals"]}
    assert goals["示例顺序买房"]["sequence_index"] == 1
    assert goals["示例并行购车"]["normalized_timing_mode"] == "parallel"
    assert goals["示例并行购车"]["sequence_index"] == 0
    dependent = goals["示例跟随并行目标装修"]
    assert dependent["sequence_index"] == 2
    assert dependent["normalized_timing_mode"] == "after_goal"
    assert dependent["depends_on_goal_name"] == "示例并行购车"
    assert dependent["resolved_not_before_month"] == 13
    assert not dependent["dependency_warning"]
    assert not sequence["warnings"]


def test_planning_goal_after_goal_dependency_reorders_priority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        base_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例先买房",
                    "priority": 5,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 10,
                },
            },
        ).json()
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例买房后换车",
                    "priority": 1,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": base_goal["id"],
                    "delay_after_dependency_months": 8,
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    names = [item["name"] for item in sequence["goals"]]
    goals = {item["name"]: item for item in sequence["goals"]}
    assert names[:2] == ["示例先买房", "示例买房后换车"]
    assert goals["示例先买房"]["sequence_index"] == 1
    assert goals["示例买房后换车"]["sequence_index"] == 2
    assert goals["示例买房后换车"]["depends_on_goal_name"] == "示例先买房"
    assert goals["示例买房后换车"]["resolved_not_before_month"] == 18


def test_planning_goal_sequence_type_filter_keeps_cross_type_dependencies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        home = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例先买房",
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 10,
                },
            },
        ).json()
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例买房后换车",
                    "priority": 2,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": home["id"],
                    "delay_after_dependency_months": 8,
                },
            },
        )
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "other",
                    "name": "示例无关缺失依赖",
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": "missing-goal",
                },
            },
        )
        sequence = client.get(
            "/api/planning-goals/sequence",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()
        full_sequence = client.get(
            "/api/planning-goals/sequence",
            params={"household_id": household["id"]},
        ).json()

    assert [item["name"] for item in sequence["goals"]] == ["示例买房后换车"]
    vehicle = sequence["goals"][0]
    assert vehicle["depends_on_goal_name"] == "示例先买房"
    assert vehicle["resolved_not_before_month"] == 18
    assert not sequence["warnings"]
    assert any("示例无关缺失依赖" in warning for warning in full_sequence["warnings"])


def test_planning_goal_sequence_resolves_dependency_chain_before_priority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        first = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例第一目标",
                    "priority": 30,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 6,
                },
            },
        ).json()
        second = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例第二目标",
                    "priority": 20,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": first["id"],
                    "delay_after_dependency_months": 4,
                },
            },
        ).json()
        client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例第三目标",
                    "priority": 10,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": second["id"],
                    "delay_after_dependency_months": 5,
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    assert [item["name"] for item in sequence["goals"][:3]] == ["示例第一目标", "示例第二目标", "示例第三目标"]
    goals = {item["name"]: item for item in sequence["goals"]}
    assert goals["示例第一目标"]["sequence_index"] == 1
    assert goals["示例第二目标"]["sequence_index"] == 2
    assert goals["示例第三目标"]["sequence_index"] == 3
    assert goals["示例第二目标"]["resolved_not_before_month"] == 10
    assert goals["示例第三目标"]["resolved_not_before_month"] == 15
    assert goals["示例第三目标"]["depends_on_goal_name"] == "示例第二目标"
    assert not sequence["warnings"]


def test_insert_planning_goal_invalidates_cache_and_syncs_core_objects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        with database.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO calculation_cache (
                    cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                    visualization_hash, result, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("stale-key", "engine", "input", "strategy", "ledger", "visualization", "{}", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            )
            conn.execute(
                """
                INSERT INTO generated_strategies (
                    id, cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                    visualization_hash, strategy_type, owner_key, strategy_key, variant,
                    data, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("stale-strategy", "stale-key", "engine", "input", "strategy", "ledger", "visualization", "home", "scenario", "variant", "variant", "{}", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            )
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例新增车辆目标",
                    "priority": 5,
                    "target_params": {
                        "name": "示例新增车辆目标",
                        "total_price": 180000,
                    },
                },
            },
        )

    assert created.status_code == 200
    with database.get_connection() as conn:
        cache_count = conn.execute("SELECT COUNT(*) AS count FROM calculation_cache").fetchone()["count"]
        generated_count = conn.execute("SELECT COUNT(*) AS count FROM generated_strategies").fetchone()["count"]
        vehicle_core_object = conn.execute(
            "SELECT data FROM core_objects WHERE household_id = ? AND category = 'vehicle_asset'",
            (household["id"],),
        ).fetchone()
    assert cache_count == 0
    assert generated_count == 0
    assert vehicle_core_object is not None
    assert "示例新增车辆目标" in vehicle_core_object["data"]


def test_generated_strategies_default_to_current_engine(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.cache import calculation_code_fingerprints
    from app.main import app

    database.DB_PATH = database.default_db_path()

    current_engine = calculation_code_fingerprints()["engine"]
    with TestClient(app) as client:
        with database.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO generated_strategies (
                    id, cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                    visualization_hash, strategy_type, owner_key, strategy_key, variant,
                    data, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "current-strategy",
                    "current-key",
                    current_engine,
                    "input-current",
                    "strategy-current",
                    "ledger-current",
                    "visualization-current",
                    "purchase",
                    "scenario",
                    "current",
                    "current",
                    '{"name": "current"}',
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO generated_strategies (
                    id, cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                    visualization_hash, strategy_type, owner_key, strategy_key, variant,
                    data, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stale-strategy",
                    "stale-key",
                    "old-engine",
                    "input-old",
                    "strategy-old",
                    "ledger-old",
                    "visualization-old",
                    "purchase",
                    "scenario",
                    "stale",
                    "stale",
                    '{"name": "stale"}',
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )

        default_rows = client.get("/api/generated-strategies").json()
        all_rows = client.get("/api/generated-strategies", params={"current_only": "false"}).json()
        by_layer = client.get(
            "/api/generated-strategies",
            params={"current_only": "false", "strategy_hash": "strategy-old"},
        ).json()
        by_owner = client.get(
            "/api/generated-strategies",
            params={"current_only": "false", "owner_key": "scenario"},
        ).json()

    assert {item["id"] for item in default_rows} == {"current-strategy"}
    assert {item["id"] for item in all_rows} == {"current-strategy", "stale-strategy"}
    assert {item["id"] for item in by_layer} == {"stale-strategy"}
    assert {item["id"] for item in by_owner} == {"current-strategy", "stale-strategy"}


def test_generated_strategies_can_be_loaded_by_multiple_cache_layers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.cache import calculation_code_fingerprints
    from app.main import app

    database.DB_PATH = database.default_db_path()

    current_engine = calculation_code_fingerprints()["engine"]
    with TestClient(app) as client:
        with database.get_connection() as conn:
            for index in range(2):
                conn.execute(
                    """
                    INSERT INTO generated_strategies (
                        id, cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                        visualization_hash, strategy_type, owner_key, strategy_key, variant,
                        data, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"strategy-{index}",
                        f"cache-{index}",
                        current_engine,
                        f"input-{index}",
                        f"strategy-{index}",
                        f"ledger-{index}",
                        f"visualization-{index}",
                        "purchase",
                        f"scenario-{index}",
                        f"variant-{index}",
                        f"variant-{index}",
                        '{"name": "strategy"}',
                        "2026-01-01T00:00:00",
                        "2026-01-01T00:00:00",
                    ),
                )
            conn.execute(
                """
                INSERT INTO generated_strategies (
                    id, cache_key, engine_fingerprint, input_hash, strategy_hash, ledger_hash,
                    visualization_hash, strategy_type, owner_key, strategy_key, variant,
                    data, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old-engine-strategy",
                    "cache-old",
                    "old-engine",
                    "input-0",
                    "strategy-0",
                    "ledger-0",
                    "visualization-0",
                    "purchase",
                    "scenario-old",
                    "old",
                    "old",
                    '{"name": "old"}',
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )

        rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": True,
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                        "engine": current_engine,
                    },
                    {
                        "input": "input-1",
                        "strategy": "strategy-1",
                        "ledger": "ledger-1",
                        "visualization": "visualization-1",
                        "engine": current_engine,
                    },
                    {
                        "input": "input-1",
                        "strategy": "strategy-1",
                        "ledger": "ledger-1",
                        "visualization": "visualization-1",
                        "engine": current_engine,
                    },
                ],
            },
        ).json()
        owner_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": True,
                "strategy_type": "purchase",
                "owner_key": "scenario-1",
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                        "engine": current_engine,
                    },
                    {
                        "input": "input-1",
                        "strategy": "strategy-1",
                        "ledger": "ledger-1",
                        "visualization": "visualization-1",
                        "engine": current_engine,
                    },
                ],
            },
        ).json()
        default_current_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                        "engine": current_engine,
                    },
                ],
            },
        ).json()
        historical_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": False,
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                        "engine": current_engine,
                    },
                ],
            },
        ).json()
        historical_old_engine_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": False,
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                        "engine": "old-engine",
                    },
                ],
            },
        ).json()
        historical_missing_engine_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": False,
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                    },
                ],
            },
        ).json()
        mismatched_visualization_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": True,
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-mismatch",
                        "engine": current_engine,
                    },
                ],
            },
        ).json()
        supplied_old_engine_current_rows = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "current_only": True,
                "cache_layers": [
                    {
                        "input": "input-0",
                        "strategy": "strategy-0",
                        "ledger": "ledger-0",
                        "visualization": "visualization-0",
                        "engine": "old-engine",
                    },
                ],
            },
        ).json()

    assert {item["id"] for item in rows} == {"strategy-0", "strategy-1"}
    assert [item["id"] for item in rows] == ["strategy-0", "strategy-1"]
    assert {item["id"] for item in owner_rows} == {"strategy-1"}
    assert {item["id"] for item in default_current_rows} == {"strategy-0"}
    assert {item["id"] for item in historical_rows} == {"strategy-0"}
    assert {item["id"] for item in historical_old_engine_rows} == {"old-engine-strategy"}
    assert historical_missing_engine_rows == []
    assert mismatched_visualization_rows == []
    assert {item["id"] for item in supplied_old_engine_current_rows} == {"strategy-0"}


def test_generated_strategy_api_rejects_unknown_strategy_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        get_response = client.get("/api/generated-strategies", params={"strategy_type": "unknown"})
        batch_response = client.post(
            "/api/generated-strategies/by-cache-layers",
            json={
                "strategy_type": "unknown",
                "cache_layers": [],
            },
        )

    assert get_response.status_code == 422
    assert batch_response.status_code == 422


def test_generated_strategy_owner_key_prefers_planning_goal_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.cache import calculation_code_fingerprints
    from app.main import app
    from app.schemas import CacheLayerHashes

    database.DB_PATH = database.default_db_path()

    layers = CacheLayerHashes(
        input="input-goal-owner",
        strategy="strategy-goal-owner",
        ledger="ledger-goal-owner",
        visualization="visualization-goal-owner",
        engine=calculation_code_fingerprints()["engine"],
    )
    result = {
        "purchase_plan_analyses": [
            {
                "variant": "home-plan-a",
                "planning_goal_id": "home-goal-a",
                "scenario_name": "fallback-home-name",
            }
        ],
        "car_plan_analyses": [
            {
                "variant": "vehicle-plan-a",
                "strategy_key": "low_down_keep_cash",
                "planning_goal_id": "vehicle-goal-a",
                "vehicle_index": 3,
                "vehicle_candidate_index": 2,
            }
        ],
        "child_plan_strategies": [
            {
                "child_name": "sample child",
                "planning_goal_id": "child-goal-a",
                "source": "planning_goals",
            }
        ],
    }
    with TestClient(app):
        database.upsert_generated_strategies(
            "goal-owner-cache",
            layers.engine,
            layers,
            result,
        )
        rows = database.list_generated_strategies(cache_key="goal-owner-cache")

    owner_keys = {(item["strategy_type"], item["owner_key"]) for item in rows}
    assert ("purchase", "home-goal-a") in owner_keys
    assert ("vehicle", "vehicle-goal-a") in owner_keys
    assert ("child_plan", "child-goal-a") in owner_keys
    assert ("purchase", "fallback-home-name") not in owner_keys
    assert all(not item["owner_key"].startswith("vehicle:3") for item in rows)


def test_generated_strategy_type_constants_match_frontend_helper() -> None:
    import re
    from typing import get_args
    from pathlib import Path

    from app.generated_strategies import GENERATED_STRATEGY_TYPES
    from app.schemas import GeneratedStrategyType

    frontend_helper = Path("frontend/src/generatedStrategies.ts").read_text(encoding="utf-8")
    constants_match = re.search(
        r"export const GENERATED_STRATEGY_TYPES = \{(?P<body>.*?)\} as const;",
        frontend_helper,
        re.DOTALL,
    )

    assert constants_match is not None
    frontend_types = set(re.findall(r': "([^"]+)"', constants_match.group("body")))
    assert frontend_types == GENERATED_STRATEGY_TYPES
    assert frontend_types == set(get_args(GeneratedStrategyType))


def test_generated_strategy_matching_stays_in_frontend_helper() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/generatedStrategies.ts").read_text(encoding="utf-8")

    assert 'from "./generatedStrategies"' in app_source
    assert "record.strategy_type" not in app_source
    assert "strategy_type ===" not in app_source
    assert "owner_key" not in app_source
    assert "export function generatedStrategiesByType" in helper_source
    assert "export function matchesPurchaseStrategyOwner" in helper_source
    assert "export function matchesVehicleStrategyOwner" in helper_source
    assert "export function matchesChildPlanStrategyOwner" in helper_source
    assert "strategyType: GeneratedStrategyType" in helper_source
    assert "strategyType: string" not in helper_source
    assert "generatedStrategyTypeLabel(type: GeneratedStrategyType)" in helper_source
    assert "generatedStrategyTypeLabel(type: string)" not in helper_source
    assert "record.strategy_type === strategyType" in helper_source
    assert "record.owner_key" in helper_source
    assert "if (scenario?.data.planning_goal_id) return new Set([scenario.data.planning_goal_id]);" in helper_source
    assert "if (scenario?.id) return new Set([scenario.id]);" in helper_source
    assert "if (scenario?.data.name) return new Set([scenario.data.name]);" in helper_source
    assert "} else if (child.name) {" in helper_source


def test_frontend_generated_strategy_reads_use_cache_layer_batch_endpoint() -> None:
    frontend_api = Path("frontend/src/api.ts").read_text(encoding="utf-8")
    frontend_app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "fetchGeneratedStrategiesByCacheLayers" in frontend_api
    assert "fetchGeneratedStrategiesByCacheLayers" in frontend_app
    assert '"/api/generated-strategies/by-cache-layers"' in frontend_api
    assert '"/api/generated-strategies"' not in frontend_api
    assert "`/api/generated-strategies" not in frontend_api


def test_frontend_foundation_and_core_object_reads_are_household_scoped() -> None:
    frontend_api = Path("frontend/src/api.ts").read_text(encoding="utf-8")
    frontend_app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "fetchScenarios(householdId: string)" in frontend_api
    assert "fetchScenarios(householdId?: string)" not in frontend_api
    assert "fetchPlanningGoalSequence(householdId: string" in frontend_api
    assert "fetchPlanningGoalSequence(householdId?: string" not in frontend_api
    assert "fetchPlanningGoals(householdId: string" in frontend_api
    assert "fetchPlanningGoals(householdId?: string" not in frontend_api
    assert "fetchPlanningFoundation(householdId: string)" in frontend_api
    assert "fetchPlanningFoundation(householdId?: string)" not in frontend_api
    assert "fetchCoreObjects(householdId: string" in frontend_api
    assert "fetchCoreObjects(householdId?: string" not in frontend_api
    assert "fetchAccountConcepts(householdId: string)" in frontend_api
    assert "fetchAccountConcepts(householdId?: string)" not in frontend_api
    assert "fetchCoreObjectGroups(householdId: string)" in frontend_api
    assert "fetchCoreObjectGroups(householdId?: string)" not in frontend_api
    assert 'params.set("household_id", householdId);' in frontend_api
    assert "fetchScenarios()" not in frontend_app
    assert "fetchPlanningGoalSequence()" not in frontend_app
    assert "fetchPlanningGoals()" not in frontend_app
    assert "fetchPlanningFoundation()" not in frontend_app
    assert "fetchCoreObjects()" not in frontend_app
    assert "fetchAccountConcepts()" not in frontend_app
    assert "fetchCoreObjectGroups()" not in frontend_app


def test_core_object_concept_constants_match_frontend_helper() -> None:
    import re

    from app.core_object_concepts import (
        ACCOUNT_CONCEPT_DEFINITIONS,
        CALIBRATION_TARGET_LABELS,
        CORE_OBJECT_GROUP_DEFINITIONS,
    )

    frontend_helper = Path("frontend/src/coreObjects.ts").read_text(encoding="utf-8")
    account_codes_match = re.search(
        r"export const ACCOUNT_CONCEPT_CODES = \{(?P<body>.*?)\} as const;",
        frontend_helper,
        re.DOTALL,
    )
    group_codes_match = re.search(
        r"export const CORE_OBJECT_GROUP_CODES = \{(?P<body>.*?)\} as const;",
        frontend_helper,
        re.DOTALL,
    )

    assert account_codes_match is not None
    assert group_codes_match is not None
    frontend_account_codes = set(re.findall(r': "([^"]+)"', account_codes_match.group("body")))
    frontend_group_codes = set(re.findall(r': "([^"]+)"', group_codes_match.group("body")))
    assert frontend_account_codes == {concept.code for concept in ACCOUNT_CONCEPT_DEFINITIONS}
    assert frontend_group_codes == {group.code for group in CORE_OBJECT_GROUP_DEFINITIONS}

    for target, label in CALIBRATION_TARGET_LABELS.items():
        assert f'value: "{target}", label: "{label}"' in frontend_helper


def test_frontend_schema_literal_unions_match_backend_schema() -> None:
    import re
    from typing import get_args

    from app.generated_strategies import GENERATED_STRATEGY_TYPES
    from app.schemas import (
        AccountCalibrationTarget,
        ChildPlanTimingMode,
        CoreObjectCategory,
        CoreObjectSource,
        CoreObjectType,
        GeneratedStrategyType,
        PlanningGoalType,
        PlanningTimingMode,
        VehiclePurchaseTimingMode,
    )

    frontend_types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    def frontend_union_values(type_name: str) -> set[str]:
        match = re.search(rf"export type {type_name}\s*=\s*(?P<body>.*?);", frontend_types, re.DOTALL)
        assert match is not None
        return set(re.findall(r'"([^"]+)"', match.group("body")))

    def frontend_interface_field_values(interface_name: str, field_name: str) -> set[str]:
        interface_match = re.search(rf"export interface {interface_name} \{{(?P<body>.*?)\n\}}", frontend_types, re.DOTALL)
        assert interface_match is not None
        field_match = re.search(rf"{field_name}: (?P<body>.*?);", interface_match.group("body"), re.DOTALL)
        assert field_match is not None
        return set(re.findall(r'"([^"]+)"', field_match.group("body")))

    assert frontend_union_values("AccountCalibrationTarget") == set(get_args(AccountCalibrationTarget))
    assert frontend_union_values("PlanningGoalType") == set(get_args(PlanningGoalType))
    assert frontend_union_values("PlanningTimingMode") == set(get_args(PlanningTimingMode))
    assert frontend_union_values("VehiclePurchaseTimingMode") == set(get_args(VehiclePurchaseTimingMode))
    assert frontend_union_values("ChildPlanTimingMode") == set(get_args(ChildPlanTimingMode))
    assert frontend_union_values("CoreObjectType") == set(get_args(CoreObjectType))
    assert frontend_union_values("CoreObjectCategory") == set(get_args(CoreObjectCategory))
    assert frontend_union_values("CoreObjectSource") == set(get_args(CoreObjectSource))
    assert frontend_union_values("GeneratedStrategyType") == set(get_args(GeneratedStrategyType))
    assert frontend_union_values("GeneratedStrategyType") == GENERATED_STRATEGY_TYPES
    assert re.search(r"^\s+purchase_timing_mode: VehiclePurchaseTimingMode;", frontend_types, re.MULTILINE)
    assert not re.search(r"^\s+purchase_timing_mode: \"auto_sequence\"", frontend_types, re.MULTILINE)
    assert re.search(r"^\s+timing_mode: ChildPlanTimingMode;", frontend_types, re.MULTILINE)
    assert not re.search(r"^\s+timing_mode: \"after_first_home\"", frontend_types, re.MULTILINE)
    assert re.search(r"^\s+normalized_timing_mode: PlanningTimingMode;", frontend_types, re.MULTILINE)
    assert not re.search(r"^\s+normalized_timing_mode: string;", frontend_types, re.MULTILINE)
    assert 'current_goal_normalized_timing_mode: PlanningTimingMode | "";' in frontend_types
    assert "current_goal_normalized_timing_mode: string;" not in frontend_types
    assert "source: CoreObjectSource;" in frontend_types
    assert 'source: CoreObjectSource | "";' in frontend_types
    assert 'source: "household" | "member" | "loan" | "goal" | "manual";' not in frontend_types
    assert "strategy_type?: GeneratedStrategyType | null;" in frontend_types
    assert "strategy_type?: string | null;" not in frontend_types
    assert 'export type GeneratedStrategyType = "purchase" | "vehicle" | "investment" | "child_plan" | "tax" | "career_shock" | string;' not in frontend_types


def test_calculation_context_current_goal_timing_mode_rejects_unknown_value() -> None:
    from pydantic import ValidationError

    from app.schemas import CalculationContextGoalSnapshot, CalculationContextSnapshot

    assert CalculationContextSnapshot(
        current_goal_normalized_timing_mode="auto_sequence"
    ).current_goal_normalized_timing_mode == "auto_sequence"
    assert CalculationContextSnapshot().current_goal_normalized_timing_mode == ""
    assert CalculationContextGoalSnapshot(
        id="goal-1",
        goal_type="home",
        name="示例目标",
        priority=1,
        sequence_index=1,
        normalized_timing_mode="manual_month",
    ).normalized_timing_mode == "manual_month"

    with pytest.raises(ValidationError):
        CalculationContextSnapshot(current_goal_normalized_timing_mode="custom_mode")
    with pytest.raises(ValidationError):
        CalculationContextGoalSnapshot(
            id="goal-1",
            goal_type="home",
            name="示例目标",
            priority=1,
            sequence_index=1,
            normalized_timing_mode="custom_mode",
        )


def test_core_object_source_rejects_unknown_value() -> None:
    from pydantic import ValidationError

    from app.schemas import CalculationContextCoreObjectSnapshot, CoreObjectData

    assert CoreObjectData(
        object_type="account",
        category="cash",
        name="示例账户",
        source="manual",
    ).source == "manual"
    assert CalculationContextCoreObjectSnapshot(
        id="object-1",
        object_type="account",
        category="cash",
        name="示例账户",
        source="manual",
    ).source == "manual"
    assert CalculationContextCoreObjectSnapshot(
        id="object-1",
        object_type="account",
        category="cash",
        name="示例账户",
    ).source == ""

    with pytest.raises(ValidationError):
        CoreObjectData(
            object_type="account",
            category="cash",
            name="示例账户",
            source="custom_source",
        )
    with pytest.raises(ValidationError):
        CalculationContextCoreObjectSnapshot(
            id="object-1",
            object_type="account",
            category="cash",
            name="示例账户",
            source="custom_source",
        )


def test_frontend_core_object_api_exposes_owner_key_filter() -> None:
    frontend_api = Path("frontend/src/api.ts").read_text(encoding="utf-8")

    assert "ownerKey?: string" in frontend_api
    assert "objectType?: CoreObjectType" in frontend_api
    assert "category?: CoreObjectCategory" in frontend_api
    assert "objectType?: string" not in frontend_api
    assert "category?: string" not in frontend_api
    assert 'params.set("owner_key", ownerKey)' in frontend_api


def test_core_object_query_filters_are_typed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        object_type_response = client.get("/api/core-objects", params={"object_type": "unknown"})
        category_response = client.get("/api/core-objects", params={"category": "unknown"})

    assert object_type_response.status_code == 422
    assert category_response.status_code == 422


def test_frontend_save_planning_goal_preserves_household_when_undefined() -> None:
    import re

    frontend_api = Path("frontend/src/api.ts").read_text(encoding="utf-8")
    match = re.search(
        r"export function savePlanningGoal\(.*?\n\}",
        frontend_api,
        re.DOTALL,
    )
    assert match is not None
    save_function = match.group(0)

    assert "household_id?: string | null" in save_function
    assert "if (householdId !== undefined) payload.household_id = householdId;" in save_function
    assert "householdId ?? null" not in save_function


def test_planning_goal_goal_type_query_is_typed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        goals_response = client.get("/api/planning-goals", params={"goal_type": "unknown"})
        sequence_response = client.get("/api/planning-goals/sequence", params={"goal_type": "unknown"})

    assert goals_response.status_code == 422
    assert sequence_response.status_code == 422


def test_frontend_planning_goal_api_uses_typed_goal_type() -> None:
    frontend_api = Path("frontend/src/api.ts").read_text(encoding="utf-8")

    assert "PlanningGoalType" in frontend_api
    assert "fetchPlanningGoalSequence(householdId: string, goalType?: PlanningGoalType)" in frontend_api
    assert "fetchPlanningGoals(householdId: string, goalType?: PlanningGoalType)" in frontend_api
    assert "fetchPlanningGoalSequence(householdId?: string" not in frontend_api
    assert "fetchPlanningGoals(householdId?: string" not in frontend_api
    assert "fetchPlanningGoalSequence(householdId?: string, goalType?: string)" not in frontend_api
    assert "fetchPlanningGoals(householdId?: string, goalType?: string)" not in frontend_api


def test_account_calibration_labels_share_core_object_concepts() -> None:
    from app.core_object_concepts import CALIBRATION_TARGET_LABELS
    from app.events import account_plan_events
    from app.projection.accounts_ledger import account_calibration_label
    from app.schemas import AccountCalibrationData, HouseholdData

    pension_calibration = AccountCalibrationData(
        month="2026-08",
        target="pension",
        amount=12_000,
        member_name="样例成员A",
    )
    household = HouseholdData(
        account_calibrations=[
            {
                "month": "2026-08",
                "target": "property_asset",
                "amount": 1_200_000,
                "reference_name": "示例房源",
            }
        ]
    )

    events = account_plan_events(
        household,
        plan_variant="base",
        current_month=date(2026, 7, 1),
        initial_provident_balance=0,
    )

    assert account_calibration_label(pension_calibration).startswith(
        f"{CALIBRATION_TARGET_LABELS['pension']}手动校准"
    )
    assert any(
        event.title == "手动校准：示例房源"
        for event in events
    )


def test_frontend_core_object_owner_summary_keeps_adjustments_out_of_balances() -> None:
    import re

    helper_source = Path("frontend/src/coreObjects.ts").read_text(encoding="utf-8")

    def frontend_type_list(const_name: str) -> list[str]:
        match = re.search(rf"export const {const_name} = \[(?P<body>.*?)\]", helper_source, re.DOTALL)
        assert match is not None
        return re.findall(r'"([^"]+)"', match.group("body"))

    assert frontend_type_list("CORE_OBJECT_OWNER_VISIBLE_TYPES") == ["asset", "loan", "adjustment"]
    assert frontend_type_list("CORE_OBJECT_OWNER_BALANCE_TYPES") == ["asset", "loan"]
    assert 'parts.push(`校准 ${summary.countsByType.adjustment}`)' in helper_source
    assert 'adjustmentBalance: balancesByType.adjustment' in helper_source


def test_frontend_readonly_account_fallbacks_stay_in_core_object_helper() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/coreObjects.ts").read_text(encoding="utf-8")

    assert "export function accountConceptBalanceTextWithHouseholdFallback" in helper_source
    assert "export function householdAccountConceptFallbackBalance" in helper_source
    assert "accountConceptBalanceTextWithHouseholdFallback(" in app_source
    assert "money(household.investments)" not in app_source


def test_frontend_visualization_and_strategy_explanations_share_core_object_concepts() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    reporting_source = Path("backend/app/reporting.py").read_text(encoding="utf-8")
    pipeline_source = Path("backend/app/planning_pipeline.py").read_text(encoding="utf-8")

    assert "accountConcepts={result?.account_concepts ?? accountConcepts}" in app_source
    assert "coreObjectGroups={result?.core_object_groups ?? coreObjectGroups}" in app_source
    assert "visualizationCoreObjectSummary" in app_source
    assert "核心对象口径：{visualizationCoreObjectSummary}" in app_source
    assert "accountConceptMap(accountConcepts)" in app_source
    assert "coreObjectGroupMap(coreObjectGroups)" in app_source

    assert "def build_strategy_explanations(" in reporting_source
    assert "account_concepts: list[AccountConceptSummary] | None = None" in reporting_source
    assert "core_object_groups: list[CoreObjectGroupSummary] | None = None" in reporting_source
    assert "核心对象口径：" in reporting_source
    assert "build_strategy_explanations(" in pipeline_source
    assert "account_concepts=account_concepts" in pipeline_source
    assert "core_object_groups=core_object_groups" in pipeline_source


def test_monthly_visualization_mapping_stays_in_frontend_helper() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/visualizationSeries.ts").read_text(encoding="utf-8")

    assert 'from "./visualizationSeries"' in app_source
    assert "const monthlySeries = buildMonthlyChartSeries(" in app_source
    assert "emptyMonthlyChartPoint(" in app_source
    assert "const loanPoint = loanVisualizationByMonth.get(item.month)" not in app_source
    assert "const providentPoint = providentVisualizationByMonth.get(item.month)" not in app_source
    assert "const socialSecurityPoint = socialSecurityVisualizationByMonth.get(item.month)" not in app_source
    assert "export function buildMonthlyChartSeries" in helper_source
    assert "export function emptyMonthlyChartPoint" in helper_source
    assert "const loanPoint = loanVisualizationByMonth.get(item.month)" in helper_source
    assert "const providentPoint = providentVisualizationByMonth.get(item.month)" in helper_source
    assert "const socialSecurityPoint = socialSecurityVisualizationByMonth.get(item.month)" in helper_source
    assert "return backendCashflowSeries\n    .filter((item) => item.month <= horizonMonths)\n    .map((item) => {" in helper_source
    for forbidden in (
        "for (let month",
        "for (let i = 0",
        "while (",
        "cashBalance +=",
        "investmentBalance +=",
        "loanBalance -=",
        "Array.from({ length",
    ):
        assert forbidden not in helper_source
    for forbidden in (
        "calculatedMonthlySeries",
        "localMonthlyProjection",
        "buildLocalProjection",
        "simulateMonthly",
        "projectMonthly",
    ):
        assert forbidden not in app_source


def test_visualization_timeline_displays_structured_calibration_source() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    frontend_types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    assert "calibration_source: string;" in frontend_types
    assert "calibrationSource: item.calibration_source" in app_source
    assert "校准来源：{item.calibrationSource}" in app_source


def test_vehicle_prepayment_labels_stay_in_planning_goal_helper() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/planningGoals.ts").read_text(encoding="utf-8")

    assert "vehiclePrepaymentModeLabel(primarySelectedStrategy)" in app_source
    assert "prepayment_strategy_type ===" not in app_source
    assert "export function vehiclePrepaymentModeLabel" in helper_source
    assert 'prepayment_strategy_type === "lump_sum"' in helper_source
    assert 'prepayment_strategy_type === "monthly"' in helper_source
    assert 'prepayment_strategy_type === "hybrid"' in helper_source


def test_planning_goal_helpers_use_typed_timing_modes() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/planningGoals.ts").read_text(encoding="utf-8")

    assert "PlanningTimingMode" in helper_source
    assert "PlanningGoalType" in helper_source
    assert "planningGoalTypeLabel(type: PlanningGoalType)" in helper_source
    assert "planningGoalIsNotPlanned(goal: { normalized_timing_mode: PlanningTimingMode })" in helper_source
    assert "export function resolveChildBirthMonth" in helper_source
    assert "export function childEducationStageLabel" in helper_source
    assert "export function childMonthlyCostAt" in helper_source
    assert "export function vehiclePlanUsesDependencySelector" in helper_source
    assert "export function vehiclePlanningControlDefaults" in helper_source
    assert "export function vehiclePlanningTimingModeValue" in helper_source
    assert "export function planningTimingModeFromScenario" in helper_source
    assert "vehiclePlanUsesDependencySelector(vehicle)" in app_source
    assert "vehiclePlanningControlDefaults(" in app_source
    assert "vehiclePlanningTimingModeValue(vehicle)" in app_source
    assert "planningTimingModeFromScenario(" in app_source
    assert '"auto_sequence"' not in app_source
    assert 'purchase_planning_mode === "parallel"' not in app_source
    assert "function resolveChildBirthMonth" not in app_source
    assert "function childEducationStageLabel" not in app_source
    assert "function childMonthlyCostAt" not in app_source
    assert "normalized_timing_mode: string" not in helper_source


def test_planning_goal_target_control_keys_match_frontend_helper() -> None:
    import re

    from app.storage.normalization import (
        CHILD_PLANNING_TARGET_CONTROL_KEYS,
        HOME_PLANNING_TARGET_CONTROL_KEYS,
        VEHICLE_PLANNING_TARGET_CONTROL_KEYS,
    )

    helper_source = Path("frontend/src/planningGoals.ts").read_text(encoding="utf-8")

    def frontend_control_keys(const_name: str) -> set[str]:
        match = re.search(rf"const {const_name} = \[(?P<body>.*?)\];", helper_source, re.DOTALL)
        assert match is not None
        return set(re.findall(r'"([^"]+)"', match.group("body")))

    assert frontend_control_keys("HOME_TARGET_CONTROL_KEYS") | {"schema_version"} == HOME_PLANNING_TARGET_CONTROL_KEYS
    assert frontend_control_keys("VEHICLE_TARGET_CONTROL_KEYS") | {"schema_version"} == VEHICLE_PLANNING_TARGET_CONTROL_KEYS
    assert frontend_control_keys("CHILD_TARGET_CONTROL_KEYS") | {"schema_version"} == CHILD_PLANNING_TARGET_CONTROL_KEYS


def test_frontend_new_home_goal_does_not_seed_policy_source_fields() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    function_match = re.search(
        r"function createTargetScenarioData\(sequence: number\): ScenarioData \{(?P<body>.*?)\n\}",
        app_source,
        re.DOTALL,
    )
    assert function_match is not None
    function_body = function_match.group("body")

    assert "provident_rate:" not in function_body
    assert "deed_tax_rate:" not in function_body
    assert "政策公积金利率" in app_source
    assert "政策契税比例" in app_source


def test_account_calibration_page_uses_full_source_catalogs() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(
        r"function AccountCalibrationPage\((?P<body>.*?)\nfunction ChildPlanPage",
        app_source,
        re.DOTALL,
    )
    assert page_match is not None
    page_body = page_match.group("body")

    assert "选择账户概念来源" in page_body
    assert "选择重大事件来源" in page_body
    assert "选择策略事件来源" in page_body
    assert "筛选账户概念" in page_body
    assert "筛选重大事件" in page_body
    assert "筛选策略事件" in page_body
    assert "当前匹配" in page_body
    assert "filteredConceptCalibrationOptions" in page_body
    assert "filteredMajorEventCalibrationOptions" in page_body
    assert "filteredStrategyCalibrationOptions" in page_body
    assert "sourceMatchesQuery" in page_body
    assert "来自策略库中的" in page_body
    assert "按账户概念摘要校准" in page_body
    assert "金额来自核心对象分组或本页账户输入" in page_body
    assert "来自后端生成的" not in page_body
    assert "按后端账户概念摘要校准" not in page_body
    assert "note: `策略键" not in page_body
    assert "strategy.variant || \"自动方案\"" in page_body
    assert "ACCOUNT_CALIBRATION_TARGET_OPTIONS.map" in page_body
    assert "calibration:" in page_body
    assert "planningGoalCalibrationOptions" in page_body
    assert "planning_goal:" in page_body
    assert "planEventCalibrationOptions.length" in page_body
    assert "const calibrationWarnings = (() => {" in page_body
    assert "已停用，不会进入后端账本和事件线" in page_body
    assert "后端会按记录顺序逐条应用" in page_body
    assert "重复启用校准" in page_body
    assert "calibration-warning-list" in page_body

    for const_name in ("conceptCalibrationOptions", "majorEventCalibrationOptions", "strategyCalibrationOptions"):
        source_match = re.search(rf"const {const_name} = (?P<body>.*?);", page_body, re.DOTALL)
        assert source_match is not None
        assert ".slice(" not in source_match.group("body")


def test_business_pages_prefer_generated_strategy_entities() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    expected_patterns = (
        r"const carStrategiesForPage = carStrategiesFromEntities\.length\s*\?\s*carStrategiesFromEntities\s*:\s*result\?\.car_plan_analyses \?\? \[\];",
        r"const childPlanStrategiesForPage = childPlanStrategiesFromEntities\.length\s*\?\s*childPlanStrategiesFromEntities\s*:\s*result\?\.child_plan_strategies \?\? \[\];",
        r"const investmentRecommendationsForPage = investmentRecommendationsFromEntities\.length\s*\?\s*investmentRecommendationsFromEntities\s*:\s*result\?\.investment_plan_recommendations \?\? \[\];",
        r"const taxStrategyItemsForPage = taxStrategyItemsFromEntities\.length\s*\?\s*taxStrategyItemsFromEntities\s*:\s*result\?\.tax_strategy_items \?\? \[\];",
        r"const taxStrategyTimelineForPage = taxStrategyTimelineFromEntities\.length\s*\?\s*taxStrategyTimelineFromEntities\s*:\s*result\?\.tax_strategy_timeline \?\? \[\];",
        r"const selectedScenarioPurchasePlans = selectedScenarioPurchasePlansFromEntities\.length\s*\?\s*selectedScenarioPurchasePlansFromEntities\s*:\s*result\?\.purchase_plan_analyses \?\? \[\];",
    )
    for pattern in expected_patterns:
        assert re.search(pattern, app_source) is not None

    assert 'purchasePlanSourceLabel = selectedScenarioPurchasePlansFromEntities.length ? "策略库方案" : "本次计算结果"' in app_source
    assert 'carStrategySourceLabel = carStrategiesFromEntities.length ? "策略库方案" : "本次计算结果"' in app_source
    assert 'childPlanStrategySourceLabel = childPlanStrategiesFromEntities.length ? "策略库方案" : "本次计算结果"' in app_source
    assert 'investmentRecommendationSourceLabel = investmentRecommendationsFromEntities.length ? "策略库方案" : "本次计算结果"' in app_source
    assert '"后端策略实体"' not in app_source


def test_generated_strategy_owner_matching_prefers_planning_goal_ids() -> None:
    source = Path("frontend/src/generatedStrategies.ts").read_text(encoding="utf-8")

    assert "if (child.planning_goal_id)" in source
    assert "goalOwnerKeys.add(child.planning_goal_id)" in source
    assert "} else if (child.name)" in source
    assert "if (vehicle.planning_goal_id)" in source
    assert "ownerKeys.add(vehicle.planning_goal_id)" in source
    assert "if (scenario?.data.planning_goal_id) return new Set([scenario.data.planning_goal_id]);" in source


def test_vehicle_strategy_selection_persists_to_planning_goal() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    function_match = re.search(
        r"const updateCarPlanSelection = \(vehicleIndex: number, variant: string\) => \{(?P<body>.*?)\n  \};",
        app_source,
        re.DOTALL,
    )
    assert function_match is not None
    function_body = function_match.group("body")

    assert "selected_strategy_variant: variant" in function_body
    assert "nextVehicle?.planning_goal_id" in function_body
    assert "savePlanningGoalData(nextVehicle.planning_goal_id, vehiclePlanningGoalData(nextVehicle, vehicleIndex))" in function_body
    assert 'userFacingError("保存车辆策略", err)' in function_body


def test_child_strategy_birth_month_adoption_updates_child_goal_config() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(
        r"function ChildPlanPage\((?P<body>.*?)\nfunction TaxPage",
        app_source,
        re.DOTALL,
    )
    assert page_match is not None
    page_body = page_match.group("body")

    assert "childStrategyBirthMonthValue(strategy)" in page_body
    assert 'inactiveLabel="采用策略出生月"' in page_body
    assert 'activeLabel="已采用策略出生月"' in page_body
    assert 'timing_mode: "manual_month"' in page_body
    assert "planned_birth_month: strategyBirthMonth" in page_body
    assert "planned_birth_start_month: strategyBirthMonth" in page_body
    assert "planned_birth_end_month: strategyBirthMonth" in page_body
    assert re.search(r"(?<!planned_)birth_month:\s*strategyBirthMonth", page_body) is None
    assert "updateChildPlanPatch(index, {" in page_body


def test_child_goal_duplicate_uses_planning_goal_api() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    function_match = re.search(
        r"const duplicateChildPlan = async \(index: number\) => \{(?P<body>.*?)\n  \};",
        app_source,
        re.DOTALL,
    )
    assert function_match is not None
    function_body = function_match.group("body")

    assert 'planning_goal_id: ""' in function_body
    assert "createPlanningGoal(childPlanningGoalData(child, childPlans.length, firstHomeGoalId), household.id)" in function_body
    assert "refreshPlanningFoundation(household.id, { clearGeneratedStrategies: true })" in function_body
    assert 'userFacingError("复制子女目标", err)' in function_body
    assert "duplicateChildPlan={duplicateChildPlan}" in app_source
    assert "onClick={() => duplicateChildPlan(index)}" in app_source


def test_generic_planning_goal_page_manages_renovation_and_other_goals() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/planningGoals.ts").read_text(encoding="utf-8")
    page_match = re.search(
        r"function GenericPlanningGoalPage\((?P<body>.*?)\nfunction AccountCalibrationPage",
        app_source,
        re.DOTALL,
    )
    assert page_match is not None
    page_body = page_match.group("body")

    assert '"规划目标"' in app_source
    assert "genericPlanningGoalDefaultData(goalType, genericGoals.length)" in app_source
    assert "genericPlanningGoalDuplicateData(goal, genericGoals.length)" in app_source
    assert "createPlanningGoal(genericPlanningGoalDefaultData" in app_source
    assert "createPlanningGoal(genericPlanningGoalDuplicateData" in app_source
    assert "savePlanningGoal(goalId, goalData, household.id)" in app_source
    assert "deletePlanningGoal(goalId)" in app_source
    assert 'planningGoals={planningGoals}' in app_source
    assert 'createGoal={createGenericPlanningGoal}' in app_source
    assert 'duplicateGoal={duplicateGenericPlanningGoal}' in app_source
    assert 'saveGoal={saveGenericPlanningGoal}' in app_source
    assert 'deleteGoal={deleteGenericPlanningGoal}' in app_source
    assert 'planning-goal-grid horizontal-card-list generic-goal-grid' in page_body
    assert '添加装修目标' in page_body
    assert '添加其它目标' in page_body
    assert '停用' in page_body
    assert '启用' in page_body
    assert '删除' in page_body
    assert '保存目标' in page_body
    assert 'target_params: {' in helper_source
    assert 'estimated_cost: defaultBudget' in helper_source
    assert 'goal_type: goalType' in helper_source
    assert 'duplicated_from_goal_id: goal.id' in helper_source


def test_export_page_uses_unified_workflow_and_business_copy() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(
        r"function ExportPage\((?P<body>.*?)\nfunction getPlanStatus",
        app_source,
        re.DOTALL,
    )
    assert page_match is not None
    page_body = page_match.group("body")

    for title in (
        'title="导出对象"',
        'title="当前选中项配置"',
        'title="策略说明"',
        'title="影响预览与导出"',
    ):
        assert title in page_body
    assert 'horizontal-card-list compact export-target-grid' in page_body
    assert 'profile="explanation"' in page_body
    assert "表格列名保持中文，避免出现内部字段名" in page_body
    assert "先刷新或完成一次计算" in page_body
    assert "本次计算尚未生成结构化文字导出" in app_source
    assert "本次计算尚未生成结构化导出表格" in app_source
    assert "后端字段名" not in page_body
    assert "后端尚未返回结构化" not in app_source


def test_business_pages_use_planner_page_shell() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_ranges = {
        "IncomePage": "GenericPlanningGoalPage",
        "GenericPlanningGoalPage": "AccountCalibrationPage",
        "ChildPlanPage": "TaxPage",
        "TaxPage": "InvestmentPlanPage",
        "InvestmentPlanPage": "ScenarioPage",
        "ScenarioPage": "CarPlanPage",
        "CarPlanPage": "RulePage",
        "RulePage": "VisualizationPage",
        "VisualizationPage": "SelectedPlanVisualization",
        "ExportPage": "getPlanStatus",
    }
    for page_name, next_page_name in page_ranges.items():
        page_match = re.search(
            rf"function {page_name}\((?P<body>.*?)\nfunction {next_page_name}",
            app_source,
            re.DOTALL,
        )
        assert page_match is not None, page_name
        page_body = page_match.group("body")
        assert "<PlannerPageShell" in page_body, page_name
        assert "summary={<p>" in page_body or "summary={" in page_body, page_name

    assert 'title="购房计划"' in app_source
    assert 'title="购车计划"' in app_source
    assert 'title="政策规则"' in app_source
    assert 'title="可视化"' in app_source


def test_business_pages_use_horizontal_selection_cards_and_business_copy() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_ranges = {
        "ChildPlanPage": "TaxPage",
        "InvestmentPlanPage": "ScenarioPage",
        "ScenarioPage": "CarPlanPage",
        "CarPlanPage": "RulePage",
        "ExportPage": "getPlanStatus",
    }
    expected_card_classes = {
        "ChildPlanPage": "child-goal-grid horizontal-card-list",
        "InvestmentPlanPage": "investment-plan-grid horizontal-card-list",
        "ScenarioPage": "planning-goal-grid horizontal-card-list purchase-demand-grid",
        "CarPlanPage": "planning-goal-grid horizontal-card-list vehicle-goal-grid",
        "ExportPage": "horizontal-card-list compact export-target-grid",
    }
    for page_name, next_page_name in page_ranges.items():
        page_match = re.search(
            rf"function {page_name}\((?P<body>.*?)\nfunction {next_page_name}",
            app_source,
            re.DOTALL,
        )
        assert page_match is not None, page_name
        assert expected_card_classes[page_name] in page_match.group("body"), page_name

    forbidden_copy = (
        "后端策略实体",
        "计算响应",
        "后端字段名",
        "后端尚未返回结构化",
        "后端并行工作数",
        "当前策略实体",
    )
    for text in forbidden_copy:
        assert text not in app_source


def test_business_pages_expose_unified_workflow_sections() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_ranges = {
        "IncomePage": "GenericPlanningGoalPage",
        "GenericPlanningGoalPage": "AccountCalibrationPage",
        "ChildPlanPage": "TaxPage",
        "TaxPage": "InvestmentPlanPage",
        "InvestmentPlanPage": "ScenarioPage",
        "ScenarioPage": "CarPlanPage",
        "CarPlanPage": "RulePage",
        "RulePage": "VisualizationPage",
        "VisualizationPage": "SelectedPlanVisualization",
    }
    expected_sections = {
        "IncomePage": ("家庭画像", "成员工资与收入阶段", "家庭支出", "已有贷款"),
        "GenericPlanningGoalPage": ("目标列表", "当前目标配置", "策略说明与影响预览"),
        "ChildPlanPage": ("目标列表", "当前目标配置", "策略建议"),
        "TaxPage": ("自动策略", "专项附加扣除", "手动覆盖"),
        "InvestmentPlanPage": ("自动方案", "手动参数", "目标配置"),
        "ScenarioPage": ("购房需求与候选房源", "手动参数", "候选策略", "当前策略说明"),
        "CarPlanPage": ("用车需求与候选车源", "车辆参数与手动策略", "政策与上牌", "车源对比", "当前购车策略说明"),
        "RulePage": ("规则包与来源", "rule-category-stack", "source-row"),
        "VisualizationPage": ("房源决策表", "选中策略", "事件时间线"),
    }
    for page_name, next_page_name in page_ranges.items():
        page_match = re.search(
            rf"function {page_name}\((?P<body>.*?)\nfunction {next_page_name}",
            app_source,
            re.DOTALL,
        )
        assert page_match is not None, page_name
        page_body = page_match.group("body")
        for section_name in expected_sections[page_name]:
            assert section_name in page_body, f"{page_name}:{section_name}"


def test_investment_strategy_adoption_updates_manual_strategy_config() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(
        r"function InvestmentPlanPage\((?P<body>.*?)\nfunction CarPlanPage",
        app_source,
        re.DOTALL,
    )
    assert page_match is not None
    page_body = page_match.group("body")
    function_match = re.search(
        r"const applyInvestmentPlan = \(plan: InvestmentPlanRecommendation\) => \{(?P<body>.*?)\n  \};",
        page_body,
        re.DOTALL,
    )
    assert function_match is not None
    function_body = function_match.group("body")

    assert "updateHouseholdPatch({" in function_body
    for field in (
        "investment_plan_name: plan.plan_name",
        "investment_risk_level: plan.risk_level",
        "monthly_investment_amount: plan.monthly_investment",
        "investment_cash_reserve_months: plan.cash_reserve_months",
        "investment_equity_ratio: plan.equity_ratio",
        "investment_bond_ratio: plan.bond_ratio",
        "investment_cash_ratio: plan.cash_ratio",
        "investment_auto_rebalance: true",
    ):
        assert field in function_body
    assert "updateInvestmentAnnualReturn(plan.annual_return)" in function_body
    assert "<AdoptStrategyButton active={active} onClick={() => applyInvestmentPlan(plan)} />" in page_body
    assert 'updateHouseholdPatch({ investment_plan_name: "manual_investment"' in page_body


def test_tax_strategy_controls_write_to_unified_manual_configs() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(
        r"function TaxPage\((?P<body>.*?)\nfunction InvestmentPlanPage",
        app_source,
        re.DOTALL,
    )
    assert page_match is not None
    page_body = page_match.group("body")

    assert 'updateChildPlan(childTarget.index, "tax_deduction_owner", event.target.value)' in page_body
    assert "updateSpecialDeduction(index, \"enabled\", checked)" in page_body
    assert "updateSpecialDeduction(index, \"member_name\", event.target.value)" in page_body
    assert "updateSpecialDeduction(index, \"settlement_mode\"" in page_body
    assert "updateSpecialDeduction(index, \"monthly_amount\", value)" in page_body
    assert "updateSpecialDeduction(index, \"annual_amount\", value)" in page_body
    assert "updateHousehold(\"investment_tax_profile\", { ...profile, [key]: value })" in page_body
    assert "updateHousehold(\"investment_taxable_return_ratio\", value)" in page_body
    assert "updateHousehold(\"investment_return_tax_rate\", value)" in page_body
    assert 'onClick={() => addSpecialDeduction(type)}' in page_body


def test_rule_page_keeps_detailed_rule_categories_collapsed_by_default() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(r"function RulePage\(.*?\nfunction VisualizationPage", app_source, re.DOTALL)
    assert page_match is not None
    page_body = page_match.group(0)

    assert "ruleGroups.map((group, groupIndex)" in page_body
    assert 'open={groupIndex === 0}' in page_body
    assert 'key={group.title} open>' not in page_body


def test_collapsible_sections_keep_accessible_state_and_visualization_details_collapsed() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    for component_name in ("WorkflowSection", "CollapsiblePanel", "CollapsibleSettingGroup"):
        component_match = re.search(
            rf"function {component_name}\((?P<body>.*?)\nfunction ",
            app_source,
            re.DOTALL,
        )
        assert component_match is not None
        component_body = component_match.group("body")
        assert "COLLAPSE_DEFAULTS[profile]" in component_body
        assert "useState(initialOpen)" in component_body
        assert "aria-expanded={open}" in component_body
        assert "setOpen((value) => !value)" in component_body
        assert "{open ? children : null}" in component_body

    visualization_match = re.search(
        r"function SelectedPlanVisualization\((?P<body>.*?)\nfunction ExportPage",
        app_source,
        re.DOTALL,
    )
    assert visualization_match is not None
    visualization_body = visualization_match.group("body")
    for details_class in (
        "advisor-details",
        "attribution-details",
        "tax-detail-panel",
        "month-detail-panel",
    ):
        assert re.search(rf"<details[^>]+className=\"[^\"]*{details_class}[^\"]*\"", visualization_body)
    assert "<details" in visualization_body
    assert "查看年度税务明细" in visualization_body
    assert "查看本月财务解释" in visualization_body


def test_collapsible_default_profiles_are_centralized() -> None:
    import re

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    defaults_match = re.search(
        r"const COLLAPSE_DEFAULTS: Record<CollapseProfile, boolean> = \{(?P<body>.*?)\};",
        app_source,
        re.DOTALL,
    )
    assert defaults_match is not None
    defaults_body = defaults_match.group("body")

    assert "core: true" in defaults_body
    assert "advanced: false" in defaults_body
    assert "explanation: false" in defaults_body
    assert "longList: false" in defaults_body
    assert 'profile = "core"' in app_source
    assert 'profile = "advanced"' in app_source
    assert 'title="购房需求设定" profile="core"' in app_source
    assert 'title="车辆属性" profile="core"' in app_source
    assert 'title="策略说明与影响预览"' in app_source
    assert 'profile="explanation"' in app_source


def test_scheduled_expense_medical_payment_toggle_is_medical_only() -> None:
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "现金账户支付" not in app_source
    assert 'label="使用医保个人账户支付"' in app_source
    assert 'scheduledExpenseCategory === "medical"' in app_source
    assert 'medical_account_payable: expenseCategory === "medical"' in app_source


def test_policy_params_are_only_read_through_policy_or_engine_interfaces() -> None:
    allowed_files = {
        Path("backend/app/policies.py"),
        Path("backend/app/engine_config.py"),
    }
    forbidden_patterns = ("rules.params", "rule_pack.params", ".params.get(")
    offenders: list[str] = []

    for path in Path("backend/app").rglob("*.py"):
        if "__pycache__" in path.parts or path in allowed_files:
            continue
        source = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in source:
                offenders.append(f"{path}:{pattern}")

    assert offenders == []


def test_rule_page_only_edits_declared_rule_pack_params() -> None:
    import re

    schemas_source = Path("backend/app/schemas.py").read_text(encoding="utf-8")
    schemas_tree = ast.parse(schemas_source)
    declared_params: set[str] = set()
    rule_pack_class = next(
        node
        for node in schemas_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RulePackData"
    )
    for node in rule_pack_class.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "params" or not isinstance(node.value, ast.Call):
            continue
        default_factory = next(
            (keyword.value for keyword in node.value.keywords if keyword.arg == "default_factory"),
            None,
        )
        assert isinstance(default_factory, ast.Lambda)
        assert isinstance(default_factory.body, ast.Dict)
        declared_params = {
            key.value
            for key in default_factory.body.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        break

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    page_match = re.search(r"function RulePage\(.*?\nfunction VisualizationPage", app_source, re.DOTALL)
    assert page_match is not None
    frontend_rule_keys = set(re.findall(r'key: "([^"]+)"', page_match.group(0)))

    assert frontend_rule_keys
    assert frontend_rule_keys <= declared_params


def test_child_planning_goal_normalization_strips_sequence_control_fields() -> None:
    from app.storage.normalization import normalize_planning_goal

    normalized = normalize_planning_goal(
        {
            "goal_type": "child",
            "name": "示例子女计划",
            "timing_mode": "manual_month",
            "target_params": {
                "name": "示例子女计划",
                "planning_goal_id": "goal-child",
                "planning_sequence": 3,
                "timing_mode": "manual_month",
                "planned_birth_month": "2030-06",
                "planned_birth_start_month": "2030-01",
                "planned_birth_end_month": "2030-12",
            },
        }
    )

    assert normalized["target_params"]["name"] == "示例子女计划"
    assert "planning_goal_id" not in normalized["target_params"]
    assert "planning_sequence" not in normalized["target_params"]
    assert "timing_mode" not in normalized["target_params"]
    assert "planned_birth_start_month" not in normalized["target_params"]
    assert "planned_birth_end_month" not in normalized["target_params"]


def test_update_planning_goal_preserves_household_when_payload_omits_household_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例车辆目标",
                        "total_price": 160000,
                    },
                },
            },
        ).json()
        updated_response = client.put(
            f"/api/planning-goals/{created['id']}",
            json={
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例车辆目标更新",
                    "priority": 2,
                    "target_params": {
                        "name": "示例车辆目标更新",
                        "total_price": 170000,
                    },
                },
            },
        )
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()

    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["household_id"] == household["id"]
    assert any(item["id"] == created["id"] for item in sequence["goals"])
    with database.get_connection() as conn:
        core_object = conn.execute(
            "SELECT data FROM core_objects WHERE household_id = ? AND json_extract(data, '$.reference_id') = ?",
            (household["id"], created["id"]),
        ).fetchone()
    assert core_object is not None
    assert "示例车辆目标更新" in core_object["data"]


def test_moving_planning_goal_between_households_resyncs_core_objects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post(
            "/api/households",
            json={"data": {**first_household["data"], "notes": "第二个样例家庭"}},
        ).json()
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": first_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例跨家庭车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例跨家庭车辆目标",
                        "total_price": 180000,
                    },
                },
            },
        ).json()
        first_before = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": created["id"]},
        ).json()
        second_before = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": created["id"]},
        ).json()

        updated = client.put(
            f"/api/planning-goals/{created['id']}",
            json={
                "household_id": second_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例跨家庭车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例跨家庭车辆目标",
                        "total_price": 180000,
                    },
                },
            },
        ).json()

        first_after = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": created["id"]},
        ).json()
        second_after = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": created["id"]},
        ).json()

    assert updated["household_id"] == second_household["id"]
    assert first_before
    assert second_before == []
    assert first_after == []
    assert second_after
    assert {item["data"]["owner_key"] for item in second_after} == {created["id"]}


def test_moving_planning_goal_from_household_to_global_resyncs_all_households(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post(
            "/api/households",
            json={"data": {**first_household["data"], "notes": "第二个样例家庭"}},
        ).json()
        created = client.post(
            "/api/planning-goals",
            json={
                "household_id": first_household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例转全局车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例转全局车辆目标",
                        "total_price": 180000,
                    },
                },
            },
        ).json()

        updated = client.put(
            f"/api/planning-goals/{created['id']}",
            json={
                "household_id": None,
                "data": created["data"],
            },
        ).json()
        first_objects = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": created["id"]},
        ).json()
        second_objects = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": created["id"]},
        ).json()
        first_projected = client.get("/api/households").json()[0]
        raw_first = database.get_record("households", first_household["id"])

    assert updated["household_id"] is None
    assert first_objects
    assert second_objects
    assert {item["data"]["owner_key"] for item in first_objects + second_objects} == {created["id"]}
    assert first_projected["data"]["car_plan"]["vehicle_plans"] == []
    assert raw_first["data"]["car_plan"]["vehicle_plans"] == []


def test_moving_planning_goal_from_global_to_household_resyncs_all_households(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post(
            "/api/households",
            json={"data": {**first_household["data"], "notes": "第二个样例家庭"}},
        ).json()
        created = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例全局转家庭车辆目标",
                    "priority": 2,
                    "target_params": {
                        "name": "示例全局转家庭车辆目标",
                        "total_price": 180000,
                    },
                },
            },
        ).json()
        first_before = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": created["id"]},
        ).json()
        second_before = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": created["id"]},
        ).json()

        updated = client.put(
            f"/api/planning-goals/{created['id']}",
            json={
                "household_id": second_household["id"],
                "data": created["data"],
            },
        ).json()
        first_after = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": created["id"]},
        ).json()
        second_after = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": created["id"]},
        ).json()
        projected_households = client.get("/api/households").json()
        projected_second = next(item for item in projected_households if item["id"] == second_household["id"])

    assert created["household_id"] is None
    assert updated["household_id"] == second_household["id"]
    assert first_before
    assert second_before
    assert first_after == []
    assert second_after
    assert [item["planning_goal_id"] for item in projected_second["data"]["car_plan"]["vehicle_plans"]] == [created["id"]]


def test_core_objects_are_derived_from_household_accounts_and_loans(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 88_000
        payload["investments"] = 120_000
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "样例成员A",
                "provident_fund_balance": 30_000,
                "pension_account_balance": 12_000,
                "medical_account_balance": 3_000,
                "personal_pension_account_enabled": True,
                "personal_pension_balance": 5_000,
            }
        ]
        payload["phased_loans"] = [
            {
                "borrower": "样例成员A",
                "name": "示例教育贷款",
                "loan_type": "education",
                "principal": 20_000,
                "annual_rate": 0.028,
                "repayment_method": "equal_installment",
                "remaining_months": 120,
                "interest_start_month": "2026-07",
                "interest_only_until": "2028-07",
            }
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        objects = client.get("/api/core-objects", params={"household_id": household["id"]}).json()
        groups = client.get("/api/core-object-groups", params={"household_id": household["id"]}).json()
        loan_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "object_type": "loan"},
        ).json()
        concepts = client.get("/api/account-concepts", params={"household_id": household["id"]}).json()

    categories = {item["category"] for item in objects}
    names = {item["data"]["name"] for item in objects}
    assert {"cash", "investment", "provident", "pension", "medical", "personal_pension", "education"} <= categories
    assert "现金账户" in names
    assert "样例成员A公积金账户" in names
    assert loan_objects[0]["data"]["name"] == "示例教育贷款"
    assert loan_objects[0]["data"]["current_balance"] == 20_000
    group_by_code = {item["code"]: item for item in groups}
    assert group_by_code["liquid_assets"]["core_object_count"] == 2
    assert group_by_code["restricted_accounts"]["core_object_count"] >= 4
    assert group_by_code["loan_accounts"]["current_balance"] == 20_000
    concept_by_code = {item["code"]: item for item in concepts}
    assert concept_by_code["pension_account"]["current_balance"] == 12_000
    assert concept_by_code["medical_account"]["current_balance"] == 3_000
    assert concept_by_code["social_security_personal_accounts"]["current_balance"] == 15_000


def test_core_object_record_id_includes_object_type() -> None:
    from app.core_objects import core_object_record_id

    account_id = core_object_record_id("household-a", "account", "manual", "same-reference", "manual_adjustment")
    adjustment_id = core_object_record_id("household-a", "adjustment", "manual", "same-reference", "manual_adjustment")

    assert account_id != adjustment_id


def test_core_objects_include_enabled_account_calibrations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 0
        payload["investments"] = 0
        payload["members"] = []
        payload["phased_loans"] = []
        payload["account_calibrations"] = [
            {
                "enabled": True,
                "month": "2026-08",
                "calibration_scope": "strategy_event",
                "target": "cash",
                "amount": 72_000,
                "reference_name": "样例现金账户",
                "source_id": "strategy-entity-1",
                "source_category": "investment",
                "source_title": "理财策略：稳健定投",
                "note": "示例校准",
            },
            {
                "enabled": False,
                "month": "2026-08",
                "target": "investment",
                "amount": 30_000,
                "reference_name": "停用校准",
            },
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        calibration_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "category": "manual_adjustment"},
        ).json()
        concepts = client.get("/api/account-concepts", params={"household_id": household["id"]}).json()
        groups = client.get("/api/core-object-groups", params={"household_id": household["id"]}).json()

    assert len(calibration_objects) == 1
    calibration_data = calibration_objects[0]["data"]
    assert calibration_data["object_type"] == "adjustment"
    assert calibration_data["source"] == "manual"
    assert calibration_data["name"] == "样例现金账户校准"
    assert calibration_data["current_balance"] == 72_000
    assert calibration_data["metadata"]["target"] == "cash"
    assert calibration_data["metadata"]["calibration_scope"] == "strategy_event"
    assert calibration_data["metadata"]["source_id"] == "strategy-entity-1"
    assert calibration_data["metadata"]["source_category"] == "investment"
    assert calibration_data["metadata"]["source_title"] == "理财策略：稳健定投"
    assert calibration_data["metadata"]["reference_name"] == "样例现金账户"
    account_calibration_concept = next(item for item in concepts if item["code"] == "account_calibration")
    assert account_calibration_concept["core_object_count"] == 1
    assert account_calibration_concept["current_balance"] == 72_000
    assert all("account_calibration" not in group["concept_codes"] for group in groups)
    assert sum(group["current_balance"] for group in groups) == 0


def test_core_object_group_api_uses_shared_reporting_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app
    from app.planning_context import core_object_snapshot_from_record
    from app.reporting import build_account_concepts_from_core_object_snapshots, build_core_object_group_summaries

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 50_000
        payload["investments"] = 80_000
        payload["phased_loans"] = [
            {
                "borrower": "样例成员A",
                "name": "示例当前贷款",
                "loan_type": "other",
                "principal": 15_000,
                "annual_rate": 0.03,
                "remaining_months": 24,
            }
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        object_records = client.get("/api/core-objects", params={"household_id": household["id"]}).json()
        api_groups = client.get("/api/core-object-groups", params={"household_id": household["id"]}).json()

    snapshots = [core_object_snapshot_from_record(record) for record in object_records]
    expected_groups = build_core_object_group_summaries(
        build_account_concepts_from_core_object_snapshots(snapshots)
    )

    assert api_groups == [group.model_dump(mode="json") for group in expected_groups]


def test_account_concept_api_uses_shared_reporting_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app
    from app.planning_context import core_object_snapshot_from_record
    from app.reporting import build_account_concepts_from_core_object_snapshots

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 50_000
        payload["investments"] = 80_000
        payload["phased_loans"] = [
            {
                "borrower": "样例成员A",
                "name": "示例当前贷款",
                "loan_type": "other",
                "principal": 15_000,
                "annual_rate": 0.03,
                "remaining_months": 24,
            }
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        object_records = client.get("/api/core-objects", params={"household_id": household["id"]}).json()
        api_concepts = client.get("/api/account-concepts", params={"household_id": household["id"]}).json()

    snapshots = [core_object_snapshot_from_record(record) for record in object_records]
    expected_concepts = build_account_concepts_from_core_object_snapshots(snapshots)

    assert api_concepts == [concept.model_dump(mode="json") for concept in expected_concepts]


def test_planning_foundation_api_returns_consistent_backend_concepts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_payload = deepcopy(household["data"])
        household_payload["cash_account_balance"] = 66_000
        household_payload["investments"] = 44_000
        client.put(f"/api/households/{household['id']}", json={"data": household_payload})
        goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "renovation",
                    "name": "示例装修目标",
                    "enabled": True,
                    "priority": 1,
                    "timing_mode": "manual_month",
                    "earliest_purchase_month": "2028-05",
                    "target_params": {"estimated_cost": 120_000},
                },
            },
        ).json()
        global_goal = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "other",
                    "name": "示例全局规划目标",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "parallel",
                    "target_params": {"estimated_cost": 30_000},
                },
            },
        ).json()
        foundation = client.get("/api/planning-foundation", params={"household_id": household["id"]}).json()
        goals = client.get("/api/planning-goals", params={"household_id": household["id"]}).json()
        sequence = client.get("/api/planning-goals/sequence", params={"household_id": household["id"]}).json()
        objects = client.get("/api/core-objects", params={"household_id": household["id"]}).json()
        concepts = client.get("/api/account-concepts", params={"household_id": household["id"]}).json()
        groups = client.get("/api/core-object-groups", params={"household_id": household["id"]}).json()

    assert foundation["planning_sequence"] == sequence
    assert foundation["core_objects"] == objects
    assert foundation["account_concepts"] == concepts
    assert foundation["core_object_groups"] == groups
    assert any(item["id"] == goal["id"] for item in foundation["planning_goals"])
    assert any(item["id"] == global_goal["id"] for item in foundation["planning_goals"])
    assert any(item["id"] == goal["id"] for item in foundation["planning_sequence"]["goals"])
    assert any(item["id"] == global_goal["id"] for item in foundation["planning_sequence"]["goals"])
    assert any(item["data"]["reference_id"] == goal["id"] for item in foundation["core_objects"])
    assert any(item["data"]["reference_id"] == global_goal["id"] for item in foundation["core_objects"])
    assert all(item["household_id"] in {None, household["id"]} for item in foundation["planning_goals"])
    assert {item["id"] for item in foundation["planning_goals"]} == {item["id"] for item in goals}
    assert global_goal["id"] in {item["id"] for item in goals}
    group_by_code = {item["code"]: item for item in foundation["core_object_groups"]}
    assert group_by_code["liquid_assets"]["current_balance"] >= 110_000
    assert group_by_code["fixed_assets"]["current_balance"] >= 150_000


def test_planning_foundation_covers_mixed_goal_sequence_and_core_objects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        home_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例混合买房",
                    "enabled": True,
                    "priority": 1,
                    "timing_mode": "auto_sequence",
                    "earliest_purchase_delay_months": 6,
                    "target_params": {
                        "total_price": 3_000_000,
                        "commercial_loan_amount": 1_200_000,
                        "provident_loan_amount": 600_000,
                    },
                },
            },
        ).json()
        vehicle_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例并行购车",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "parallel",
                    "allow_parallel": True,
                    "earliest_purchase_delay_months": 4,
                    "target_params": {"price": 220_000},
                },
            },
        ).json()
        child_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例养娃目标",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": home_goal["id"],
                    "delay_after_dependency_months": 18,
                    "target_params": {"name": "示例子女", "planned_birth_month": "2030-06"},
                },
            },
        ).json()
        renovation_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "renovation",
                    "name": "示例跟随并行目标装修",
                    "enabled": True,
                    "priority": 4,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": vehicle_goal["id"],
                    "delay_after_dependency_months": 5,
                    "target_params": {"estimated_cost": 90_000},
                },
            },
        ).json()
        foundation = client.get("/api/planning-foundation", params={"household_id": household["id"]}).json()

    sequence_by_name = {item["name"]: item for item in foundation["planning_sequence"]["goals"]}
    assert sequence_by_name["示例混合买房"]["sequence_index"] == 1
    assert sequence_by_name["示例并行购车"]["normalized_timing_mode"] == "parallel"
    assert sequence_by_name["示例并行购车"]["sequence_index"] == 0
    assert sequence_by_name["示例养娃目标"]["depends_on_goal_name"] == "示例混合买房"
    assert sequence_by_name["示例跟随并行目标装修"]["depends_on_goal_name"] == "示例并行购车"
    assert sequence_by_name["示例跟随并行目标装修"]["resolved_not_before_month"] == 9
    assert not foundation["planning_sequence"]["warnings"]

    visible_goal_ids = {item["id"] for item in foundation["planning_goals"]}
    assert {home_goal["id"], vehicle_goal["id"], child_goal["id"], renovation_goal["id"]} <= visible_goal_ids

    object_owner_keys = {item["data"].get("owner_key") for item in foundation["core_objects"]}
    assert {home_goal["id"], vehicle_goal["id"], child_goal["id"], renovation_goal["id"]} <= object_owner_keys
    categories_by_owner: dict[str, set[str]] = {}
    for item in foundation["core_objects"]:
        owner_key = item["data"].get("owner_key")
        if owner_key:
            categories_by_owner.setdefault(owner_key, set()).add(item["category"])
    assert "property_asset" in categories_by_owner[home_goal["id"]]
    assert "vehicle_asset" in categories_by_owner[vehicle_goal["id"]]
    assert "child_goal" in categories_by_owner[child_goal["id"]]
    assert "planning_goal" in categories_by_owner[renovation_goal["id"]]


def test_core_objects_include_planning_goal_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        home = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例目标房产",
                    "total_price": 3_100_000,
                    "commercial_loan_amount": 1_800_000,
                    "provident_loan_amount": 800_000,
                    "commercial_rate": 0.041,
                    "provident_rate": 0.199,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        payload = deepcopy(household["data"])
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例目标车辆",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "total_price": 160_000,
                    "down_payment_ratio": 0.25,
                    "later_annual_rate": 0.036,
                    "planning_sequence": 2,
                }
            ],
        }
        payload["child_plans"] = [
            {
                "name": "示例子女目标",
                "enabled": True,
                "timing_mode": "manual_month",
                "expense_strategy_mode": "balanced",
                "planned_birth_month": "2030-06",
                "planned_birth_start_month": "2030-01",
                "planned_birth_end_month": "2030-12",
                "birth_month": "",
                "tax_deduction_owner": "",
                "education_start_month": "",
                "preparation_months_before_birth": 6,
                "pregnancy_months_before_birth": 9,
                "monthly_preparation_cost": 1000,
                "monthly_pregnancy_cost": 2000,
                "birth_medical_cost": 30000,
                "postpartum_recovery_cost": 20000,
                "initial_baby_supplies_cost": 10000,
                "monthly_childcare_cost_before_kindergarten": 3000,
                "monthly_kindergarten_cost": 4000,
                "monthly_primary_secondary_cost": 5000,
                "monthly_higher_education_cost": 6000,
                "kindergarten_entry_cost": 10000,
                "primary_school_entry_cost": 15000,
                "higher_education_entry_cost": 50000,
                "notes": "",
            }
        ]
        client.put(f"/api/households/{household['id']}", json={"data": payload})
        renovation_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "renovation",
                    "name": "示例装修目标",
                    "priority": 4,
                    "target_params": {
                        "name": "示例装修目标",
                        "estimated_cost": 180_000,
                    },
                },
            },
        ).json()
        other_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "other",
                    "name": "示例其它目标",
                    "priority": 5,
                    "target_params": {
                        "name": "示例其它目标",
                        "budget": 60_000,
                    },
                },
            },
        ).json()
        asset_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "object_type": "asset"},
        ).json()
        loan_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "object_type": "loan"},
        ).json()
        home_owned_objects = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": home["id"]},
        ).json()
        home_owned_loans = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "owner_key": home["id"], "object_type": "loan"},
        ).json()
        vehicle_object = next(item for item in asset_objects if item["category"] == "vehicle_asset")
        home_object = next(item for item in asset_objects if item["category"] == "property_asset")
        child_object = next(item for item in asset_objects if item["category"] == "child_goal")
        planning_goal_objects = [item for item in asset_objects if item["category"] == "planning_goal"]
        fixed_asset_group = next(
            item
            for item in client.get("/api/core-object-groups", params={"household_id": household["id"]}).json()
            if item["code"] == "fixed_assets"
        )

        client.delete(f"/api/scenarios/{home['id']}")
        refreshed_assets = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "object_type": "asset"},
        ).json()

    assert home_object["data"]["name"] == "示例目标房产"
    assert home_object["data"]["current_balance"] == 3_100_000
    assert home_object["data"]["reference_id"] == home["id"]
    assert home_object["data"]["owner_key"] == home["id"]
    assert {item["data"]["reference_id"] for item in home_owned_objects} == {
        home["id"],
        f"{home['id']}.commercial_loan",
        f"{home['id']}.provident_loan",
    }
    assert {item["object_type"] for item in home_owned_objects} == {"asset", "loan"}
    assert {item["category"] for item in home_owned_loans} == {"mortgage"}
    assert {item["data"]["owner_key"] for item in home_owned_loans} == {home["id"]}
    assert vehicle_object["data"]["name"] == "示例目标车辆"
    assert vehicle_object["data"]["current_balance"] == 160_000
    assert vehicle_object["data"]["owner_key"] == vehicle_object["data"]["reference_id"]
    assert child_object["data"]["name"] == "示例子女目标"
    assert child_object["data"]["current_balance"] > 0
    assert child_object["data"]["owner_key"] == child_object["data"]["reference_id"]
    assert child_object["data"]["metadata"]["goal_type"] == "child"
    assert {item["data"]["reference_id"] for item in planning_goal_objects} == {renovation_goal["id"], other_goal["id"]}
    assert {item["data"]["owner_key"] for item in planning_goal_objects} == {renovation_goal["id"], other_goal["id"]}
    assert {item["data"]["metadata"]["goal_type"] for item in planning_goal_objects} == {"renovation", "other"}
    assert sum(item["data"]["current_balance"] for item in planning_goal_objects) == 240_000
    planned_loan_by_reference = {item["data"]["reference_id"]: item["data"] for item in loan_objects}
    assert planned_loan_by_reference[f"{home['id']}.commercial_loan"]["current_balance"] == 1_800_000
    assert planned_loan_by_reference[f"{home['id']}.commercial_loan"]["owner_key"] == home["id"]
    assert planned_loan_by_reference[f"{home['id']}.commercial_loan"]["metadata"]["loan_subtype"] == "commercial"
    assert planned_loan_by_reference[f"{home['id']}.commercial_loan"]["annual_rate"] == 0.041
    assert planned_loan_by_reference[f"{home['id']}.commercial_loan"]["metadata"]["rate_source"] == "market_quote"
    assert planned_loan_by_reference[f"{home['id']}.provident_loan"]["current_balance"] == 800_000
    assert planned_loan_by_reference[f"{home['id']}.provident_loan"]["owner_key"] == home["id"]
    assert planned_loan_by_reference[f"{home['id']}.provident_loan"]["metadata"]["loan_subtype"] == "provident"
    assert planned_loan_by_reference[f"{home['id']}.provident_loan"]["annual_rate"] == 0
    assert planned_loan_by_reference[f"{home['id']}.provident_loan"]["metadata"]["rate_source"] == "policy_pack"
    assert any(
        item["category"] == "car_loan"
        and item["data"]["owner_key"] == vehicle_object["data"]["reference_id"]
        and item["data"]["current_balance"] == 120_000
        and item["data"]["annual_rate"] == 0.036
        and item["data"]["metadata"]["planned"] is True
        and item["data"]["metadata"]["rate_source"] == "dealer_financing_option"
        for item in loan_objects
    )
    assert fixed_asset_group["core_object_count"] >= 5
    assert fixed_asset_group["current_balance"] >= 3_500_000
    assert all(item["data"]["reference_id"] != home["id"] for item in refreshed_assets)


def test_core_objects_owner_filter_is_exact_for_assets_and_planned_loans(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        first_home = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例首个目标房产",
                    "total_price": 3_000_000,
                    "commercial_loan_amount": 1_500_000,
                    "provident_loan_amount": 600_000,
                    "purchase_sequence": 1,
                },
            },
        ).json()
        second_home = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例第二个目标房产",
                    "total_price": 4_000_000,
                    "commercial_loan_amount": 2_000_000,
                    "provident_loan_amount": 700_000,
                    "purchase_sequence": 2,
                },
            },
        ).json()
        first_assets = client.get(
            "/api/core-objects",
            params={
                "household_id": household["id"],
                "owner_key": first_home["id"],
                "object_type": "asset",
                "category": "property_asset",
            },
        ).json()
        first_loans = client.get(
            "/api/core-objects",
            params={
                "household_id": household["id"],
                "owner_key": first_home["id"],
                "object_type": "loan",
                "category": "mortgage",
            },
        ).json()
        second_loans = client.get(
            "/api/core-objects",
            params={
                "household_id": household["id"],
                "owner_key": second_home["id"],
                "object_type": "loan",
                "category": "mortgage",
            },
        ).json()
        all_mortgages = client.get(
            "/api/core-objects",
            params={"household_id": household["id"], "object_type": "loan", "category": "mortgage"},
        ).json()

    assert len(first_assets) == 1
    assert first_assets[0]["data"]["owner_key"] == first_home["id"]
    assert {item["data"]["owner_key"] for item in first_loans} == {first_home["id"]}
    assert {item["data"]["reference_id"] for item in first_loans} == {
        f"{first_home['id']}.commercial_loan",
        f"{first_home['id']}.provident_loan",
    }
    assert {item["data"]["owner_key"] for item in second_loans} == {second_home["id"]}
    assert len(first_loans) == 2
    assert len(second_loans) == 2
    assert len(all_mortgages) == 4


def test_core_objects_exclude_not_planned_goal_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例暂不规划房源",
                    "enabled": True,
                    "timing_mode": "not_planned",
                    "target_params": {
                        "name": "示例暂不规划房源",
                        "total_price": 2_800_000,
                        "commercial_loan_amount": 1_500_000,
                        "provident_loan_amount": 600_000,
                    },
                },
            },
        ).json()
        foundation = client.get("/api/planning-foundation", params={"household_id": household["id"]}).json()
        objects = client.get("/api/core-objects", params={"household_id": household["id"]}).json()

    sequence_goal = next(item for item in foundation["planning_sequence"]["goals"] if item["id"] == goal["id"])
    assert sequence_goal["normalized_timing_mode"] == "not_planned"
    assert sequence_goal["sequence_index"] == 0
    assert any(item["id"] == goal["id"] for item in foundation["planning_goals"])
    assert all(item["data"]["owner_key"] != goal["id"] for item in foundation["core_objects"])
    assert all(item["data"]["reference_id"] != goal["id"] for item in objects)
    assert all(not str(item["data"]["reference_id"]).startswith(f"{goal['id']}.") for item in objects)


def test_deleting_global_planning_goal_syncs_core_objects_for_all_households(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        first_household = client.get("/api/households").json()[0]
        second_household = client.post(
            "/api/households",
            json={"data": {**first_household["data"], "notes": "第二个样例家庭"}},
        ).json()
        global_goal = client.post(
            "/api/planning-goals",
            json={
                "data": {
                    "goal_type": "other",
                    "name": "示例全局备用金目标",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "parallel",
                    "target_params": {"estimated_cost": 80_000},
                },
            },
        ).json()
        first_before = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": global_goal["id"]},
        ).json()
        second_before = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": global_goal["id"]},
        ).json()

        delete_response = client.delete(f"/api/planning-goals/{global_goal['id']}")

        first_after = client.get(
            "/api/core-objects",
            params={"household_id": first_household["id"], "owner_key": global_goal["id"]},
        ).json()
        second_after = client.get(
            "/api/core-objects",
            params={"household_id": second_household["id"], "owner_key": global_goal["id"]},
        ).json()

    assert first_before
    assert second_before
    assert delete_response.status_code == 200
    assert first_after == []
    assert second_after == []


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
                    "vehicle_service_years": 10,
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
    assert saved_vehicle["financing_options"]
    assert [option["name"] for option in saved_vehicle["financing_options"]] == [
        "全款",
        "三年前两年贴息",
        "最低20%首付两年贴息",
        "0首付五年低息",
    ]
    assert saved_vehicle["financing_options"][0]["prepayment_allowed"] is False


def test_vehicle_prepayment_switch_clears_hidden_amounts_on_save(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        record = client.get("/api/households").json()[0]
        payload = deepcopy(record["data"])
        vehicle = {
            **payload["car_plan"],
            "enabled": True,
            "name": "测试用车需求",
            "candidate_vehicles": [],
            "vehicle_plans": [],
            "total_price": 200000,
            "loan_prepayment_enabled": False,
            "loan_prepayment_strategy_type": "hybrid",
            "loan_prepayment_monthly_amount": 3000,
            "loan_prepayment_lump_sum_month": 12,
            "loan_prepayment_lump_sum_amount": 50000,
        }
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [vehicle],
        }

        response = client.put(f"/api/households/{record['id']}", json={"data": payload})

    assert response.status_code == 200
    saved_vehicle = response.json()["data"]["car_plan"]["vehicle_plans"][0]
    assert saved_vehicle["loan_prepayment_enabled"] is False
    assert saved_vehicle["loan_prepayment_strategy_type"] == "none"
    assert saved_vehicle["loan_prepayment_monthly_amount"] == 0
    assert saved_vehicle["loan_prepayment_lump_sum_amount"] == 0


def test_affordability_api_applies_vehicle_planning_goal_window_to_strategy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 500_000
        payload["monthly_expense"] = 3_000
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "样例成员A",
                "monthly_salary_gross": 25_000,
                "income_stages": [
                    {
                        **payload["members"][0]["income_stages"][0],
                        "monthly_salary_gross": 25_000,
                    }
                ],
            }
        ]
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "示例通勤车",
                    "selected_strategy_variant": "target",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "planning_sequence": 1,
                    "purchase_timing_mode": "auto_sequence",
                    "manual_purchase_delay_months": 0,
                    "purchase_delay_months": 0,
                    "total_price": 120_000,
                    "down_payment_ratio": 0.3,
                }
            ],
        }
        household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        vehicle_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()[0]
        goal_payload = deepcopy(vehicle_goal["data"])
        goal_payload["earliest_purchase_delay_months"] = 18
        client.put(
            f"/api/planning-goals/{vehicle_goal['id']}",
            json={"household_id": household["id"], "data": goal_payload},
        )
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "示例购房目标",
                    "enabled": False,
                    "total_price": 2_000_000,
                },
            },
        ).json()

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )
        vehicle_strategy_entities = client.get(
            "/api/generated-strategies",
            params={"strategy_type": "vehicle"},
        ).json()

    assert response.status_code == 200
    analyses = response.json()["car_plan_analyses"]
    assert analyses
    assert {item["source"] for item in analyses} == {"planning_goals"}
    assert {item["planning_goal_id"] for item in analyses} == {vehicle_goal["id"]}
    assert min(item["purchase_delay_months"] for item in analyses) >= 18
    months_to_buy = [item["months_to_buy"] for item in analyses if item["months_to_buy"] is not None]
    assert months_to_buy
    assert min(months_to_buy) >= 18
    assert vehicle_strategy_entities
    assert {item["owner_key"] for item in vehicle_strategy_entities} == {vehicle_goal["id"]}


def test_affordability_outputs_consume_resolved_planning_sequence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 600_000
        payload["monthly_expense"] = 6_000
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "样例成员A",
                "monthly_salary_gross": 45_000,
                "income_stages": [
                    {
                        **payload["members"][0]["income_stages"][0],
                        "monthly_salary_gross": 45_000,
                    }
                ],
            }
        ]
        household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        home_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "home",
                    "name": "示例先购房目标",
                    "enabled": False,
                    "priority": 1,
                    "timing_mode": "not_planned",
                    "target_params": {"total_price": 2_000_000},
                },
            },
        ).json()
        vehicle_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "vehicle",
                    "name": "示例顺序车辆",
                    "enabled": True,
                    "priority": 2,
                    "timing_mode": "manual_month",
                    "earliest_purchase_delay_months": 14,
                    "target_params": {
                        "name": "示例顺序车辆",
                        "total_price": 160_000,
                        "down_payment_ratio": 0.4,
                        "selected_strategy_variant": "target",
                    },
                },
            },
        ).json()
        child_goal = client.post(
            "/api/planning-goals",
            json={
                "household_id": household["id"],
                "data": {
                    "goal_type": "child",
                    "name": "示例顺序养娃",
                    "enabled": True,
                    "priority": 3,
                    "timing_mode": "after_goal",
                    "depends_on_goal_id": vehicle_goal["id"],
                    "delay_after_dependency_months": 8,
                    "target_params": {
                        "name": "示例顺序子女",
                        "planned_birth_month": "",
                        "tax_deduction_owner": "样例成员A",
                    },
                },
            },
        ).json()
        rule_pack = client.get("/api/rule-packs").json()[0]
        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": home_goal["id"],
                "household": household["data"],
                "scenario": {
                    **home_goal["data"]["target_params"],
                    "name": home_goal["data"]["name"],
                    "enabled": False,
                    "planning_goal_id": home_goal["id"],
                },
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    sequence_by_id = {item["id"]: item for item in result["calculation_context"]["planning_goals"]}
    assert sequence_by_id[vehicle_goal["id"]]["resolved_not_before_month"] == 14
    assert sequence_by_id[child_goal["id"]]["depends_on_goal_name"] == "示例顺序车辆"
    assert sequence_by_id[child_goal["id"]]["resolved_not_before_month"] == 22

    vehicle_analyses = [item for item in result["car_plan_analyses"] if item["planning_goal_id"] == vehicle_goal["id"]]
    assert vehicle_analyses
    assert min(item["purchase_delay_months"] for item in vehicle_analyses) >= 14

    child_strategy = next(item for item in result["child_plan_strategies"] if item["planning_goal_id"] == child_goal["id"])
    assert child_strategy["birth_month_index"] is None or child_strategy["birth_month_index"] >= 22
    assert result["monthly_cashflow_visualization"]
    assert result["monthly_ledger"]

    sequence_sheet = next(
        sheet
        for sheet in result["export_sheets"]
        if sheet["title"] == "统一规划顺序"
    )
    headers = sequence_sheet["headers"]
    id_index = headers.index("目标ID")
    not_before_index = headers.index("最早月份偏移")
    rows_by_id = {row[id_index]: row for row in sequence_sheet["rows"]}
    assert rows_by_id[vehicle_goal["id"]][not_before_index] == 14
    assert rows_by_id[child_goal["id"]][not_before_index] == 22


def test_affordability_api_respects_vehicle_planning_window_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        payload = deepcopy(household["data"])
        payload["cash_account_balance"] = 5_000
        payload["monthly_expense"] = 8_000
        payload["members"] = [
            {
                **payload["members"][0],
                "name": "样例成员A",
                "monthly_salary_gross": 10_000,
                "income_stages": [
                    {
                        **payload["members"][0]["income_stages"][0],
                        "monthly_salary_gross": 10_000,
                    }
                ],
            }
        ]
        payload["car_plan"] = {
            **payload["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **payload["car_plan"],
                    "enabled": True,
                    "name": "短窗口车辆",
                    "selected_strategy_variant": "target",
                    "vehicle_plans": [],
                    "candidate_vehicles": [],
                    "planning_sequence": 1,
                    "purchase_timing_mode": "auto_sequence",
                    "manual_purchase_delay_months": 0,
                    "purchase_delay_months": 0,
                    "total_price": 200_000,
                    "down_payment_ratio": 0.5,
                    "financing_options": [
                        {
                            "id": "cash_only",
                            "name": "全款",
                            "enabled": True,
                            "financing_type": "cash_only",
                            "total_months": 1,
                            "interest_free_months": 0,
                            "later_annual_rate": 0,
                            "min_down_payment_ratio": 1,
                            "max_down_payment_ratio": 1,
                            "prepayment_allowed": False,
                            "prepayment_allowed_after_month": 1,
                        }
                    ],
                }
            ],
        }
        household = client.put(f"/api/households/{household['id']}", json={"data": payload}).json()
        vehicle_goal = client.get(
            "/api/planning-goals",
            params={"household_id": household["id"], "goal_type": "vehicle"},
        ).json()[0]
        goal_payload = deepcopy(vehicle_goal["data"])
        goal_payload["planning_window_start_month"] = "2026-07"
        goal_payload["planning_window_end_month"] = "2026-08"
        client.put(
            f"/api/planning-goals/{vehicle_goal['id']}",
            json={"household_id": household["id"], "data": goal_payload},
        )
        rule_pack = client.get("/api/rule-packs").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={
                "household_id": household["id"],
                "data": {
                    "name": "无购房目标",
                    "enabled": False,
                    "total_price": 2_000_000,
                },
            },
        ).json()

        response = client.post(
            "/api/calculations/affordability",
            json={
                "household_id": household["id"],
                "scenario_id": scenario["id"],
                "household": household["data"],
                "scenario": scenario["data"],
                "rule_pack": rule_pack["data"],
                "include_stress_tests": False,
            },
        )

    assert response.status_code == 200
    result = response.json()
    goal_snapshot = next(goal for goal in result["calculation_context"]["planning_goals"] if goal["id"] == vehicle_goal["id"])
    assert goal_snapshot["resolved_window_end_month"] is not None
    assert goal_snapshot["resolved_window_end_month"] <= 1
    analyses = result["car_plan_analyses"]
    assert analyses
    assert all(item["months_to_buy"] is None for item in analyses)
    assert any("planning_window_exceeded" in note for item in analyses for note in item["notes"])


def test_scenario_switch_like_modes_are_normalized_on_save(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios",
            json={
                "data": {
                    "property_type": "新房",
                    "building_age_years": 28,
                    "building_structure": "brick_mixed",
                    "is_old_community_renovated": True,
                    "remaining_land_use_years": 45,
                    "commercial_prepayment_mode": "none",
                    "commercial_prepayment_enabled": True,
                    "commercial_prepayment_monthly_amount": 5000,
                }
            },
        )

    assert response.status_code == 200
    scenario = response.json()["data"]
    assert scenario["commercial_prepayment_mode"] == "none"
    assert scenario["commercial_prepayment_enabled"] is False
    assert scenario["commercial_prepayment_monthly_amount"] == 0
    assert scenario["building_age_years"] == 0
    assert scenario["building_structure"] == "unknown"
    assert scenario["is_old_community_renovated"] is False
    assert scenario["remaining_land_use_years"] is None


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


def test_affordability_cache_hit_does_not_rewrite_existing_cache_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database, main

    database.DB_PATH = database.default_db_path()

    cache_writes = {"count": 0}
    strategy_writes = {"count": 0}
    original_cache_upsert = main.upsert_calculation_cache
    original_strategy_upsert = main.upsert_generated_strategies

    def counted_cache_upsert(*args, **kwargs):
        cache_writes["count"] += 1
        return original_cache_upsert(*args, **kwargs)

    def counted_strategy_upsert(*args, **kwargs):
        strategy_writes["count"] += 1
        return original_strategy_upsert(*args, **kwargs)

    monkeypatch.setattr(main, "upsert_calculation_cache", counted_cache_upsert)
    monkeypatch.setattr(main, "upsert_generated_strategies", counted_strategy_upsert)

    with TestClient(main.app) as client:
        household = client.get("/api/households").json()[0]
        scenario = client.post(
            "/api/scenarios",
            json={"household_id": household["id"], "data": {"total_price": 3_000_000}},
        ).json()
        rule_pack = client.get("/api/rule-packs").json()[0]
        payload = {
            "household_id": household["id"],
            "scenario_id": scenario["id"],
            "household": household["data"],
            "scenario": scenario["data"],
            "rule_pack": rule_pack["data"],
        }

        first = client.post("/api/calculations/affordability", json=payload)
        assert first.status_code == 200
        cache_writes["count"] = 0
        strategy_writes["count"] = 0
        second = client.post("/api/calculations/affordability", json=payload)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert cache_writes["count"] == 0
    assert strategy_writes["count"] == 0


def test_calculation_persists_generated_strategy_entities(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))

    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()

    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]["data"]
        rule_pack = client.get("/api/rule-packs").json()[0]["data"]
        household["cash_account_balance"] = 600_000
        household["monthly_expense"] = 10_000
        household["members"] = [
            {
                **household["members"][0],
                "name": "样例成员A",
                "monthly_salary_gross": 50_000,
                "annual_bonus": 0,
            }
        ]
        household["car_plan"] = {
            **household["car_plan"],
            "enabled": True,
            "vehicle_plans": [
                {
                    **household["car_plan"],
                    "enabled": True,
                    "name": "示例用车需求",
                    "selected_strategy_variant": "target",
                    "candidate_vehicles": [
                        {
                            **household["car_plan"],
                            "enabled": True,
                            "name": "示例车辆",
                            "selected_strategy_variant": "target",
                            "candidate_vehicles": [],
                            "total_price": 220_000,
                            "down_payment_ratio": 0.3,
                            "down_payment": 66_000,
                        }
                    ],
                    "total_price": 220_000,
                    "down_payment_ratio": 0.3,
                    "down_payment": 66_000,
                }
            ],
        }
        household["child_plans"] = [
            {
                "name": "示例子女计划",
                "enabled": True,
                "timing_mode": "manual_month",
                "planned_birth_month": "2030-06",
                "monthly_childcare_cost_before_kindergarten": 3000,
            }
        ]
        scenario = {"total_price": 3_000_000}
        payload = {"household": household, "scenario": scenario, "rule_pack": rule_pack}

        response = client.post("/api/calculations/affordability", json=payload)
        all_strategies = client.get("/api/generated-strategies").json()
        vehicle_strategies = client.get("/api/generated-strategies", params={"strategy_type": "vehicle"}).json()
        child_plan_strategies = client.get("/api/generated-strategies", params={"strategy_type": "child_plan"}).json()
        tax_strategies = client.get("/api/generated-strategies", params={"strategy_type": "tax"}).json()

    assert response.status_code == 200
    assert any(item["strategy_type"] == "purchase" for item in all_strategies)
    assert any(item["strategy_type"] == "investment" for item in all_strategies)
    assert {item["strategy_key"] for item in vehicle_strategies} >= {
        "target",
        "cash",
        "high_down_low_loan",
        "low_down_keep_cash",
        "accelerated_principal",
        "delay_purchase",
    }
    assert all(item["data"]["vehicle_name"] == "示例用车需求" for item in vehicle_strategies)
    assert all("loan_principal" in item["data"] for item in vehicle_strategies)
    assert child_plan_strategies
    assert child_plan_strategies[0]["data"]["child_name"] == "示例子女计划"
    assert child_plan_strategies[0]["strategy_type"] == "child_plan"
    assert "happiness_score" in child_plan_strategies[0]["data"]
    assert tax_strategies
    assert {item["data"]["entity_kind"] for item in tax_strategies} >= {"strategy_item", "timeline_point"}
    assert any(item["strategy_key"] == "personal_pension" for item in tax_strategies)


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
