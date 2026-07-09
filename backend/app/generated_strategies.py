from __future__ import annotations

from typing import Any


GENERATED_STRATEGY_TYPE_PURCHASE = "purchase"
GENERATED_STRATEGY_TYPE_VEHICLE = "vehicle"
GENERATED_STRATEGY_TYPE_INVESTMENT = "investment"
GENERATED_STRATEGY_TYPE_CHILD_PLAN = "child_plan"
GENERATED_STRATEGY_TYPE_TAX = "tax"
GENERATED_STRATEGY_TYPE_CAREER_SHOCK = "career_shock"

GENERATED_STRATEGY_TYPES = {
    GENERATED_STRATEGY_TYPE_PURCHASE,
    GENERATED_STRATEGY_TYPE_VEHICLE,
    GENERATED_STRATEGY_TYPE_INVESTMENT,
    GENERATED_STRATEGY_TYPE_CHILD_PLAN,
    GENERATED_STRATEGY_TYPE_TAX,
    GENERATED_STRATEGY_TYPE_CAREER_SHOCK,
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def generated_strategy_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in result.get("purchase_plan_analyses", []):
        if not isinstance(item, dict):
            continue
        variant = str(item.get("variant") or "")
        if not variant:
            continue
        planning_goal_id = str(item.get("planning_goal_id") or "")
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_PURCHASE,
                "owner_key": planning_goal_id or str(item.get("scenario_name") or "selected_scenario"),
                "strategy_key": variant,
                "variant": variant,
                "data": item,
            }
        )

    for item in result.get("car_plan_analyses", []):
        if not isinstance(item, dict):
            continue
        variant = str(item.get("variant") or "")
        if not variant:
            continue
        vehicle_index = _safe_int(item.get("vehicle_index"), 0)
        candidate_index = item.get("vehicle_candidate_index")
        planning_goal_id = str(item.get("planning_goal_id") or "")
        owner_key = planning_goal_id or f"vehicle:{vehicle_index}:candidate:{candidate_index if candidate_index is not None else 'target'}"
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_VEHICLE,
                "owner_key": owner_key,
                "strategy_key": str(item.get("strategy_key") or variant),
                "variant": variant,
                "data": item,
            }
        )

    for item in result.get("investment_plan_recommendations", []):
        if not isinstance(item, dict):
            continue
        variant = str(item.get("variant") or item.get("plan_name") or "")
        if not variant:
            continue
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_INVESTMENT,
                "owner_key": "household",
                "strategy_key": variant,
                "variant": variant,
                "data": item,
            }
        )

    for index, item in enumerate(result.get("child_plan_strategies", [])):
        if not isinstance(item, dict):
            continue
        child_name = str(item.get("child_name") or f"child-{index + 1}")
        planning_goal_id = str(item.get("planning_goal_id") or "")
        variant = planning_goal_id or child_name
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_CHILD_PLAN,
                "owner_key": planning_goal_id or child_name,
                "strategy_key": str(item.get("source") or "child_plan_strategy"),
                "variant": variant,
                "data": item,
            }
        )

    for index, item in enumerate(result.get("tax_strategy_items", [])):
        if not isinstance(item, dict):
            continue
        deduction_type = str(item.get("deduction_type") or "tax_strategy")
        member_name = str(item.get("member_name") or "household")
        start_month = str(item.get("start_month") or "no_start_month")
        variant = f"item:{deduction_type}:{member_name}:{start_month}:{index}"
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_TAX,
                "owner_key": member_name,
                "strategy_key": deduction_type,
                "variant": variant,
                "data": {"entity_kind": "strategy_item", **item},
            }
        )

    for index, item in enumerate(result.get("tax_strategy_timeline", [])):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "tax_timeline")
        member_name = str(item.get("member_name") or "household")
        month = _safe_int(item.get("month"), 0)
        year = _safe_int(item.get("year"), 0)
        variant = f"timeline:{month}:{category}:{member_name}:{index}"
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_TAX,
                "owner_key": member_name,
                "strategy_key": category,
                "variant": variant,
                "data": {"entity_kind": "timeline_point", **item, "year": year, "month": month},
            }
        )

    career_shock_projection = result.get("career_shock_projection")
    if isinstance(career_shock_projection, dict):
        rows.append(
            {
                "strategy_type": GENERATED_STRATEGY_TYPE_CAREER_SHOCK,
                "owner_key": "household",
                "strategy_key": "auto_projection",
                "variant": "auto_projection",
                "data": career_shock_projection,
            }
        )
    return rows
