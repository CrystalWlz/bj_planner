from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
import os
from time import perf_counter
from typing import Iterator


LOGGER = logging.getLogger("app.profiling")
_CURRENT_PROFILE: ContextVar[CalculationProfile | None] = ContextVar("calculation_profile", default=None)


def profiling_enabled() -> bool:
    return os.getenv("HOUSE_PLANNER_PROFILE", "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ProfileSpan:
    name: str
    elapsed_ms: float


@dataclass
class CalculationProfile:
    label: str
    spans: list[ProfileSpan] = field(default_factory=list)

    def add_span(self, name: str, elapsed_ms: float) -> None:
        self.spans.append(ProfileSpan(name=name, elapsed_ms=round(elapsed_ms, 3)))

    def summary(self, total_ms: float) -> dict[str, object]:
        return {
            "label": self.label,
            "total_ms": round(total_ms, 3),
            "span_count": len(self.spans),
            "spans": [span.__dict__ for span in self.spans],
        }


@contextmanager
def calculation_profile(label: str) -> Iterator[CalculationProfile | None]:
    if not profiling_enabled():
        yield None
        return

    # Enable this logger only for an explicitly requested profile run.  Let
    # the application logging tree own handlers so test capture, Uvicorn and
    # desktop runs observe the same profiling record.
    LOGGER.setLevel(logging.INFO)
    profile = CalculationProfile(label=label)
    token = _CURRENT_PROFILE.set(profile)
    started_at = perf_counter()
    try:
        yield profile
    finally:
        elapsed_ms = (perf_counter() - started_at) * 1000
        LOGGER.info(
            "calculation_profile %s",
            json.dumps(profile.summary(elapsed_ms), ensure_ascii=False, sort_keys=True),
        )
        _CURRENT_PROFILE.reset(token)


@contextmanager
def profile_span(name: str) -> Iterator[None]:
    profile = _CURRENT_PROFILE.get()
    if profile is None:
        yield
        return

    started_at = perf_counter()
    try:
        yield
    finally:
        profile.add_span(name, (perf_counter() - started_at) * 1000)
