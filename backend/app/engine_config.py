from __future__ import annotations

from dataclasses import dataclass

from .schemas import RulePackData


EXECUTION_CONFIG_PARAM_KEYS = frozenset({"backend_parallel_workers"})


@dataclass(frozen=True)
class CalculationEngineConfig:
    parallel_workers: int = 4
    max_parallel_workers: int = 8

    def worker_count(self, task_count: int) -> int:
        if task_count <= 1:
            return 1
        return max(1, min(self.parallel_workers, task_count, self.max_parallel_workers))


def calculation_engine_config(rules: RulePackData) -> CalculationEngineConfig:
    raw_workers = rules.params.get("backend_parallel_workers", CalculationEngineConfig.parallel_workers)
    try:
        workers = int(raw_workers)
    except (TypeError, ValueError):
        workers = CalculationEngineConfig.parallel_workers
    return CalculationEngineConfig(parallel_workers=workers)


def parallel_worker_count(rules: RulePackData, task_count: int) -> int:
    return calculation_engine_config(rules).worker_count(task_count)
