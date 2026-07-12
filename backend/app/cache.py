from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .engine_config import EXECUTION_CONFIG_PARAM_KEYS
from .schemas import AffordabilityRequest, CacheLayerHashes


LAYER_CODE_PATHS: dict[str, tuple[str, ...]] = {
    "input": (
        "calculation_context.py",
        "planning_context.py",
        "core_object_concepts.py",
        "core_objects.py",
        "storage",
        "domain/planning_goals.py",
    ),
    "strategy": (
        "calculator.py",
        "calculation_context.py",
        "engine_config.py",
        "planning_summary.py",
        "purchase_facade.py",
        "strategy_pipeline.py",
        "tax_engine.py",
        "vehicle_facade.py",
        "policies.py",
        "domain",
        "strategies",
    ),
    "ledger": (
        "calculator.py",
        "calculation_context.py",
        "engine_config.py",
        "planning_pipeline.py",
        "projection_facade.py",
        "strategy_pipeline.py",
        "tax_engine.py",
        "policies.py",
        "domain",
        "projection",
    ),
    "visualization": (
        "planning_pipeline.py",
        "projection_facade.py",
        "result_assembly.py",
        "visualization.py",
        "core_object_concepts.py",
        "reporting.py",
        "events.py",
        "schemas.py",
    ),
}
ENGINE_CODE_PATHS: tuple[str, ...] = ("cache.py", "generated_strategies.py")
RULE_PACK_CALCULATION_FIELDS: tuple[str, ...] = ("jurisdiction", "params")


def _hash_json(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iter_layer_files(app_dir: Path, entries: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for entry in entries:
        path = app_dir / entry
        if path.is_dir():
            paths.extend(
                sorted(
                    item
                    for item in path.rglob("*.py")
                    if "__pycache__" not in item.parts
                )
            )
        elif path.exists():
            paths.append(path)
    return paths


def _files_fingerprint(app_dir: Path, entries: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for path in _iter_layer_files(app_dir, entries):
        relative_path = path.relative_to(app_dir).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def calculation_code_fingerprints() -> dict[str, str]:
    app_dir = Path(__file__).resolve().parent
    layers = {
        layer: _files_fingerprint(app_dir, entries)
        for layer, entries in LAYER_CODE_PATHS.items()
    }
    layers["engine"] = _hash_json(
        {
            "layers": layers,
            "cache_module": _files_fingerprint(app_dir, ENGINE_CODE_PATHS),
        }
    )
    return layers


def affordability_input_payload(payload: AffordabilityRequest) -> dict[str, Any]:
    return {
        "household_id": payload.household_id,
        "scenario_id": payload.scenario_id,
        "household": payload.household.model_dump(mode="json"),
        "scenario": payload.scenario.model_dump(mode="json"),
        "rule_pack": _business_rule_pack_payload(payload.rule_pack.model_dump(mode="json")),
        "market_snapshot": payload.market_snapshot.model_dump(mode="json") if payload.market_snapshot else None,
        "include_stress_tests": payload.include_stress_tests,
        "calculation_context": payload.calculation_context.model_dump(mode="json") if payload.calculation_context else None,
    }


def _business_rule_pack_payload(rule_pack: dict[str, Any]) -> dict[str, Any]:
    params = rule_pack.get("params")
    if not isinstance(params, dict):
        params = {}
    business_payload = {
        key: rule_pack.get(key)
        for key in RULE_PACK_CALCULATION_FIELDS
        if key != "params"
    }
    business_payload["params"] = {
        key: value
        for key, value in params.items()
        if key not in EXECUTION_CONFIG_PARAM_KEYS
    }
    return business_payload


def affordability_cache_layers(payload: AffordabilityRequest) -> CacheLayerHashes:
    input_data_hash = _hash_json(affordability_input_payload(payload))
    code_hashes = calculation_code_fingerprints()
    input_hash = _hash_json({"data": input_data_hash, "code": code_hashes["input"]})
    strategy_hash = _hash_json({"input": input_hash, "code": code_hashes["strategy"]})
    ledger_hash = _hash_json(
        {
            "strategy": strategy_hash,
            "code": code_hashes["ledger"],
        }
    )
    visualization_hash = _hash_json(
        {
            "ledger": ledger_hash,
            "code": code_hashes["visualization"],
        }
    )
    return CacheLayerHashes(
        input=input_hash,
        strategy=strategy_hash,
        ledger=ledger_hash,
        visualization=visualization_hash,
        engine=code_hashes["engine"],
    )


def affordability_cache_key(payload: AffordabilityRequest) -> tuple[str, str, CacheLayerHashes]:
    layers = affordability_cache_layers(payload)
    cache_key = _hash_json(
        {
            "input": layers.input,
            "strategy": layers.strategy,
            "ledger": layers.ledger,
            "visualization": layers.visualization,
            "engine": layers.engine,
        }
    )
    return cache_key, layers.engine, layers
