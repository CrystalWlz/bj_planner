from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import AffordabilityRequest


LAYER_CODE_PATHS: dict[str, tuple[str, ...]] = {
    "strategy": (
        "calculator.py",
        "tax_engine.py",
        "policies.py",
        "domain",
        "strategies",
    ),
    "ledger": (
        "calculator.py",
        "tax_engine.py",
        "policies.py",
        "domain",
        "projection",
    ),
    "visualization": (
        "visualization.py",
        "reporting.py",
        "events.py",
        "schemas.py",
    ),
}


def _hash_json(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iter_layer_files(app_dir: Path, entries: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for entry in entries:
        path = app_dir / entry
        if path.is_dir():
            paths.extend(sorted(path.glob("*.py")))
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
    layers["engine"] = _hash_json(layers)
    return layers


def affordability_input_payload(payload: AffordabilityRequest) -> dict[str, Any]:
    return {
        "household": payload.household.model_dump(mode="json"),
        "scenario": payload.scenario.model_dump(mode="json"),
        "rule_pack": payload.rule_pack.model_dump(mode="json"),
        "include_stress_tests": payload.include_stress_tests,
    }


def affordability_cache_layers(payload: AffordabilityRequest) -> dict[str, str]:
    input_hash = _hash_json(affordability_input_payload(payload))
    code_hashes = calculation_code_fingerprints()
    return {
        "input": input_hash,
        "strategy": _hash_json({"input": input_hash, "code": code_hashes["strategy"]}),
        "ledger": _hash_json(
            {
                "input": input_hash,
                "strategy": code_hashes["strategy"],
                "code": code_hashes["ledger"],
            }
        ),
        "visualization": _hash_json(
            {
                "input": input_hash,
                "strategy": code_hashes["strategy"],
                "ledger": code_hashes["ledger"],
                "code": code_hashes["visualization"],
            }
        ),
        "engine": code_hashes["engine"],
    }


def affordability_cache_key(payload: AffordabilityRequest) -> tuple[str, str, dict[str, str]]:
    layers = affordability_cache_layers(payload)
    cache_key = _hash_json(
        {
            "input": layers["input"],
            "strategy": layers["strategy"],
            "ledger": layers["ledger"],
            "visualization": layers["visualization"],
            "engine": layers["engine"],
        }
    )
    return cache_key, layers["engine"], layers
