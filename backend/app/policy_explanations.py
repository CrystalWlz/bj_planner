from __future__ import annotations

from typing import Literal


PolicyExplanationSource = Literal["policy", "user", "market"]

SOURCE_LABELS: dict[PolicyExplanationSource, str] = {
    "policy": "政策来源",
    "user": "用户配置",
    "market": "市场假设",
}


def source_labeled_note(source: PolicyExplanationSource, text: str) -> str:
    label = SOURCE_LABELS[source]
    cleaned = text.strip()
    if cleaned.startswith(f"{label}："):
        return cleaned
    return f"{label}：{cleaned}"


def policy_source_note(text: str) -> str:
    return source_labeled_note("policy", text)


def user_config_note(text: str) -> str:
    return source_labeled_note("user", text)


def market_assumption_note(text: str) -> str:
    return source_labeled_note("market", text)
