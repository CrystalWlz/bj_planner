from __future__ import annotations

import inspect
from pathlib import Path


def _source_for_item(item) -> str:
    try:
        return inspect.getsource(item.obj)
    except (OSError, TypeError):
        return ""


def _contains_any(source: str, tokens: tuple[str, ...]) -> bool:
    return any(token in source for token in tokens)


FRONTEND_CONTRACT_TOKENS = (
    "frontend/src/",
    "frontend\\\\src\\\\",
    "Path(\"frontend/",
    "Path('frontend/",
    "frontend_types",
    "frontend_api",
    "app_source",
    "helper_source",
    "generatedStrategies.ts",
    "planningGoals.ts",
    "visualizationSeries.ts",
    "coreObjects.ts",
)

ARCHITECTURE_TOKENS = (
    "docs/architecture",
    "architecture_closure_checklist",
    "perf_calculation_sample",
    "profiling.py",
    "forbidden_fragments",
    "allowed_default_rule_pack_files",
    "allowed_rule_param_access_files",
    "allowed_execution_config_key_files",
    "backend/app\")",
    "backend/app')",
    ".rglob(\"*.py\")",
    ".rglob('*.py')",
)

SLOW_NAME_TOKENS = (
    "affordability",
    "projection",
    "visualization",
    "cashflow",
    "timeline",
    "generated_strategy",
    "purchase_plan",
    "car_plan",
    "child_plan",
    "provident",
    "cache",
)

SLOW_SOURCE_TOKENS = (
    "calculate_affordability(",
    "build_car_plan_analyses(",
    "build_child_plan_strategies(",
    "build_monthly_cashflow_visualization(",
    "build_social_security_visualization(",
    "client.post(\"/api/affordability",
    "client.post('/api/affordability",
)


def pytest_collection_modifyitems(config, items) -> None:
    for item in items:
        source = _source_for_item(item)
        test_file = Path(str(item.path)).name
        lower_name = item.name.lower()

        is_frontend_contract = _contains_any(source, FRONTEND_CONTRACT_TOKENS)
        is_architecture = _contains_any(source, ARCHITECTURE_TOKENS)
        is_integration = "TestClient(" in source
        is_slow = _contains_any(source, SLOW_SOURCE_TOKENS) or any(
            token in lower_name for token in SLOW_NAME_TOKENS
        )

        if test_file == "test_encoding_scan.py":
            item.add_marker("encoding")

        if test_file == "test_api.py":
            item.add_marker("api")

        if test_file == "test_calculator.py" and not is_architecture:
            item.add_marker("domain")

        if is_integration:
            item.add_marker("integration")

        if is_frontend_contract:
            item.add_marker("frontend_contract")

        if is_architecture:
            item.add_marker("architecture")

        if is_slow:
            item.add_marker("slow")
