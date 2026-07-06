from __future__ import annotations

from datetime import date
from functools import lru_cache


@lru_cache(maxsize=512)
def parse_iso_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def add_months(base: date, months: int) -> date:
    zero_based_month = base.month - 1 + months
    return date(base.year + zero_based_month // 12, zero_based_month % 12 + 1, 1)


def end_of_previous_month(month_start: date) -> date:
    if month_start.month == 1:
        return date(month_start.year - 1, 12, 31)
    return date(month_start.year, month_start.month - 1, 28)


def parse_year_month(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        year_text, month_text = value[:7].split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (ValueError, TypeError):
        return None
    if not 1 <= month <= 12:
        return None
    return year, month


def parse_month(value: str) -> tuple[int, int] | None:
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (ValueError, AttributeError):
        return None
    if not 1 <= month <= 12:
        return None
    return year, month


def month_distance(start: tuple[int, int], end: tuple[int, int]) -> int:
    return (end[0] - start[0]) * 12 + end[1] - start[1]


def month_after(base: date, months_from_now: int) -> tuple[int, int]:
    target = add_months(base, months_from_now)
    return target.year, target.month


def month_tuple_to_date(value: tuple[int, int]) -> date:
    return date(value[0], value[1], 1)


def format_year_month_tuple(value: tuple[int, int] | None) -> str:
    return f"{value[0]:04d}-{value[1]:02d}" if value else ""


def month_start_for_age(as_of: date, current_age: int, target_age: int) -> date:
    months_until = max(0, (target_age - current_age) * 12)
    return add_months(date(as_of.year, as_of.month, 1), months_until)


def month_start_for_birth_month_or_age(
    as_of: date,
    birth_month_value: str | None,
    current_age: int,
    target_age: int,
) -> date:
    birth_month = parse_year_month(birth_month_value)
    if birth_month is not None:
        target = date(birth_month[0] + target_age, birth_month[1], 1)
        return max(date(as_of.year, as_of.month, 1), target)
    return month_start_for_age(as_of, current_age, target_age)


def months_between_months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)
