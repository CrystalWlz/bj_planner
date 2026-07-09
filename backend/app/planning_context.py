from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any

from .database import (
    list_core_object_records,
    list_planning_goal_records,
    list_scenario_records,
)
from .domain.planning_goals import resolve_planning_sequence
from .domain.time import add_months
from .reporting import build_account_concepts_from_core_object_snapshots, build_core_object_group_summaries
from .schemas import (
    AffordabilityRequest,
    CalculationContextCoreObjectSnapshot,
    CalculationContextGoalSnapshot,
    CalculationContextSnapshot,
    ChildPlanData,
    HouseholdData,
    PlanningFoundationSummary,
    PlanningGoalRecord,
    PlanningSequenceResult,
    ResolvedPlanningGoal,
    ScenarioData,
    VehiclePlanData,
)
from .storage.normalization import child_plan_from_goal, scenario_from_home_goal, vehicle_plan_from_goal


def planning_goal_records_for_request(household_id: str | None = None, goal_type: str | None = None) -> list[dict[str, Any]]:
    raw_records = list_planning_goal_records(goal_type=goal_type)
    if household_id is not None:
        raw_records = [
            record for record in raw_records
            if _household_id_in_scope(record.get("household_id"), household_id)
        ]
    return raw_records


def planning_goal_sequence_for_request(household_id: str | None = None, goal_type: str | None = None) -> PlanningSequenceResult:
    raw_records = planning_goal_records_for_request(household_id=household_id)
    sequence = resolve_planning_sequence([PlanningGoalRecord.model_validate(record) for record in raw_records])
    if not goal_type:
        return sequence
    visible_goals = [goal for goal in sequence.goals if goal.goal_type == goal_type]
    visible_goal_names = {goal.name for goal in visible_goals if goal.name}
    return sequence.model_copy(
        update={
            "goals": visible_goals,
            "warnings": [
                warning
                for warning in sequence.warnings
                if any(f"「{name}」" in warning for name in visible_goal_names)
            ],
        },
    )


def core_object_records_for_request(household_id: str | None = None) -> list[dict[str, Any]]:
    return list_core_object_records(household_id=household_id)


def planning_foundation_for_request(household_id: str | None = None) -> PlanningFoundationSummary:
    core_object_records = core_object_records_for_request(household_id=household_id)
    core_object_snapshots = [core_object_snapshot_from_record(record) for record in core_object_records]
    account_concepts = build_account_concepts_from_core_object_snapshots(core_object_snapshots)
    return PlanningFoundationSummary(
        planning_goals=planning_goal_records_for_request(household_id=household_id),
        planning_sequence=planning_goal_sequence_for_request(household_id=household_id),
        core_objects=core_object_records,
        account_concepts=account_concepts,
        core_object_groups=build_core_object_group_summaries(account_concepts),
    )


def calculation_context_snapshot(payload: AffordabilityRequest) -> CalculationContextSnapshot:
    household_id = payload.household_id
    scenario_id = payload.scenario_id
    scenario_goal_id = str(getattr(payload.scenario, "planning_goal_id", "") or "")
    if not household_id and scenario_id:
        scenario_record = next((record for record in list_scenario_records() if record["id"] == scenario_id), None)
        household_id = str(scenario_record.get("household_id") or "") if scenario_record else ""
    if not household_id and scenario_goal_id:
        goal_record = next((record for record in list_planning_goal_records() if record["id"] == scenario_goal_id), None)
        household_id = str(goal_record.get("household_id") or "") if goal_record else ""

    foundation = (
        planning_foundation_for_request(household_id=household_id)
        if household_id
        else PlanningFoundationSummary()
    )
    raw_goals = [record.model_dump(mode="json") for record in foundation.planning_goals]
    sequence = foundation.planning_sequence or PlanningSequenceResult()
    current_goal_ids = [goal_id for goal_id in [scenario_id, scenario_goal_id] if goal_id]
    current_goal = next((goal for goal in sequence.goals if goal.id in current_goal_ids), None)
    core_objects = [record.model_dump(mode="json") for record in foundation.core_objects]

    goal_fingerprint_payload = [
        {
            "id": record["id"],
            "household_id": record.get("household_id"),
            "goal_type": record.get("goal_type"),
            "data": record.get("data"),
        }
        for record in raw_goals
    ]
    core_fingerprint_payload = [
        {
            "id": record["id"],
            "household_id": record.get("household_id"),
            "object_type": record.get("object_type"),
            "category": record.get("category"),
            "data": record.get("data"),
        }
        for record in core_objects
    ]

    return CalculationContextSnapshot(
        base_month=sequence.base_month,
        household_id=household_id,
        scenario_id=scenario_id,
        current_goal_id=current_goal.id if current_goal else "",
        current_goal_name=current_goal.name if current_goal else "",
        current_goal_resolved_not_before_month=current_goal.resolved_not_before_month if current_goal else 0,
        current_goal_normalized_timing_mode=current_goal.normalized_timing_mode if current_goal else "",
        planning_goal_ids=[goal.id for goal in sequence.goals],
        planning_goals=[_goal_snapshot(goal) for goal in sequence.goals],
        core_object_ids=[str(record["id"]) for record in core_objects],
        core_objects=[core_object_snapshot_from_record(record) for record in core_objects],
        planning_goal_fingerprint=_stable_json_hash(goal_fingerprint_payload),
        core_object_fingerprint=_stable_json_hash(core_fingerprint_payload),
        resolved_goal_count=len(sequence.goals),
        core_object_count=len(core_objects),
        warnings=sequence.warnings,
    )


def core_object_snapshot_from_record(record: dict[str, Any]) -> CalculationContextCoreObjectSnapshot:
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    return CalculationContextCoreObjectSnapshot(
        id=str(record.get("id") or ""),
        object_type=record.get("object_type") or data.get("object_type") or "asset",
        category=record.get("category") or data.get("category") or "other",
        name=str(data.get("name") or ""),
        source=str(data.get("source") or ""),
        owner_key=str(data.get("owner_key") or ""),
        reference_id=str(data.get("reference_id") or ""),
        member_name=str(data.get("member_name") or ""),
        current_balance=float(data.get("current_balance") or 0),
        monthly_flow=float(data.get("monthly_flow") or 0),
    )


def _goal_snapshot(goal: ResolvedPlanningGoal) -> CalculationContextGoalSnapshot:
    return CalculationContextGoalSnapshot(
        id=goal.id,
        goal_type=goal.goal_type,
        name=goal.name,
        enabled=goal.enabled,
        priority=goal.priority,
        sequence_index=goal.sequence_index,
        normalized_timing_mode=goal.normalized_timing_mode,
        depends_on_goal_id=goal.depends_on_goal_id,
        depends_on_goal_name=goal.depends_on_goal_name,
        resolved_not_before_month=goal.resolved_not_before_month,
        resolved_window_start_month=goal.resolved_window_start_month,
        resolved_window_end_month=goal.resolved_window_end_month,
        explanation=goal.explanation,
        dependency_warning=goal.dependency_warning,
    )


def payload_with_calculation_context(payload: AffordabilityRequest) -> AffordabilityRequest:
    if payload.calculation_context is None:
        return payload.model_copy(update={"calculation_context": calculation_context_snapshot(payload)})
    return payload


def apply_planning_goal_constraints(payload: AffordabilityRequest) -> AffordabilityRequest:
    payload = payload_with_calculation_context(payload)
    constrained_scenario = scenario_with_planning_goal_constraints(payload)
    constrained_household = household_with_planning_goal_constraints(payload)
    if constrained_scenario is payload.scenario and constrained_household is payload.household:
        return payload
    return payload.model_copy(update={"household": constrained_household, "scenario": constrained_scenario})


def scenario_with_planning_goal_constraints(payload: AffordabilityRequest) -> ScenarioData:
    context = payload.calculation_context
    scenario = payload.scenario
    if context is None:
        return scenario
    home_goal = _home_goal_snapshot_for_scenario(scenario, context)
    if home_goal is None:
        return scenario
    scenario = _project_explicit_home_goal_to_scenario(scenario, context, home_goal)
    if not home_goal.enabled or home_goal.normalized_timing_mode == "not_planned":
        if not scenario.enabled:
            return scenario
        return scenario.model_copy(update={"enabled": False})
    resolved_not_before = max(0, home_goal.resolved_not_before_month, home_goal.resolved_window_start_month)
    if resolved_not_before <= scenario.manual_purchase_delay_months:
        return scenario
    return scenario.model_copy(update={"manual_purchase_delay_months": min(360, resolved_not_before)})


def _project_explicit_home_goal_to_scenario(
    scenario: ScenarioData,
    context: CalculationContextSnapshot,
    home_goal: CalculationContextGoalSnapshot,
) -> ScenarioData:
    scenario_goal_id = str(getattr(scenario, "planning_goal_id", "") or "")
    explicitly_selected = context.current_goal_id == home_goal.id or scenario_goal_id == home_goal.id
    if not explicitly_selected:
        return scenario
    home_record = _home_goal_record_for_snapshot(context, home_goal)
    if home_record is None:
        return scenario
    projected = ScenarioData.model_validate(
        scenario_from_home_goal(
            home_record.id,
            home_record.data.model_dump(mode="json"),
            sequence_index=home_goal.sequence_index,
        )
    )
    return projected


def _home_goal_record_for_snapshot(
    context: CalculationContextSnapshot,
    home_goal: CalculationContextGoalSnapshot,
) -> PlanningGoalRecord | None:
    for record in planning_goal_records_for_request(household_id=context.household_id or None, goal_type="home"):
        if record.get("id") == home_goal.id:
            return PlanningGoalRecord.model_validate(record)
    return None


def _home_goal_snapshot_for_scenario(
    scenario: ScenarioData,
    context: CalculationContextSnapshot,
) -> CalculationContextGoalSnapshot | None:
    if context.current_goal_id:
        current = next((goal for goal in context.planning_goals if goal.id == context.current_goal_id), None)
        if current is not None and current.goal_type == "home":
            return current
    scenario_goal_id = str(getattr(scenario, "planning_goal_id", "") or "")
    if scenario_goal_id:
        current = next((goal for goal in context.planning_goals if goal.id == scenario_goal_id), None)
        if current is not None and current.goal_type == "home":
            return current
    return next((goal for goal in context.planning_goals if goal.goal_type == "home"), None)


def household_with_planning_goal_constraints(payload: AffordabilityRequest) -> HouseholdData:
    context = payload.calculation_context
    household = payload.household
    if context is None or not context.household_id:
        return household
    all_goal_records = _all_goal_records_for_household(context.household_id)
    resolved_by_id = {goal.id: goal for goal in context.planning_goals}
    if not resolved_by_id:
        sequence = resolve_planning_sequence(all_goal_records)
        resolved_by_id = {goal.id: _goal_snapshot(goal) for goal in sequence.goals}
    household_changed = False

    constrained_household = household
    vehicle_goal_records = [
        goal for goal in all_goal_records
        if goal.goal_type == "vehicle" and _goal_applies_to_household(goal, context.household_id)
    ]
    if household.car_plan.vehicle_plans or vehicle_goal_records:
        if not household.car_plan.vehicle_plans and vehicle_goal_records:
            vehicle_plans = _project_vehicle_goal_records_to_vehicle_plans(vehicle_goal_records, resolved_by_id)
            car_plan = constrained_household.car_plan.model_copy(
                update={
                    "vehicle_plans": vehicle_plans,
                    "enabled": any(vehicle.enabled for vehicle in vehicle_plans),
                }
            )
            constrained_household = constrained_household.model_copy(update={"car_plan": car_plan})
            household_changed = True
        constrained_household = _household_with_vehicle_goal_constraints(
            constrained_household,
            context.household_id,
            all_goal_records,
            resolved_by_id,
        )
        household_changed = household_changed or constrained_household != household

    child_goal_records = [
        goal for goal in all_goal_records
        if goal.goal_type == "child" and _goal_applies_to_household(goal, context.household_id)
    ]
    if constrained_household.child_plans or child_goal_records:
        child_plans = constrained_household.child_plans
        if not child_plans and child_goal_records:
            child_plans = _project_child_goal_records_to_child_plans(child_goal_records, resolved_by_id)
            constrained_household = constrained_household.model_copy(update={"child_plans": child_plans})
            household_changed = True
        next_child_plans = _child_plans_with_planning_goal_constraints(
            child_plans,
            context.household_id,
            all_goal_records,
            resolved_by_id,
        )
        if next_child_plans != constrained_household.child_plans:
            constrained_household = constrained_household.model_copy(update={"child_plans": next_child_plans})
            household_changed = True
    return constrained_household if household_changed else household


def _stable_json_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _vehicle_plan_with_planning_goal_constraints(
    vehicle: VehiclePlanData,
    goal: PlanningGoalRecord,
    snapshot: CalculationContextGoalSnapshot | None = None,
) -> VehiclePlanData:
    data = goal.data
    resolved_snapshot = snapshot or CalculationContextGoalSnapshot(
        id=goal.id,
        goal_type=goal.goal_type,
        name=data.name,
        enabled=data.enabled,
        priority=data.priority,
        sequence_index=data.priority,
        normalized_timing_mode="parallel" if data.allow_parallel or data.timing_mode == "parallel" else data.timing_mode,
        resolved_not_before_month=data.earliest_purchase_delay_months,
        resolved_window_start_month=data.earliest_purchase_delay_months,
        resolved_window_end_month=None,
    )
    update = _vehicle_plan_update_from_goal_snapshot(
        vehicle,
        resolved_snapshot,
    )
    earliest_delay = max(
        update["manual_purchase_delay_months"],
        data.earliest_purchase_delay_months,
    )
    update["manual_purchase_delay_months"] = earliest_delay
    update["purchase_delay_months"] = min(120, earliest_delay)
    if data.planning_window_start_month:
        update["planning_window_start_month"] = data.planning_window_start_month
    if data.planning_window_end_month:
        update["planning_window_end_month"] = data.planning_window_end_month
    update["after_previous_event_delay_months"] = max(
        vehicle.after_previous_event_delay_months,
        data.delay_after_dependency_months,
    )
    if data.selected_strategy_id:
        update["selected_strategy_variant"] = data.selected_strategy_id
    return vehicle.model_copy(update=update)


def _vehicle_plan_update_from_goal_snapshot(vehicle: VehiclePlanData, goal: CalculationContextGoalSnapshot) -> dict[str, Any]:
    update: dict[str, Any] = {
        "planning_goal_id": goal.id,
        "planning_sequence": max(1, goal.sequence_index),
    }
    timing_mode = goal.normalized_timing_mode
    if timing_mode == "parallel":
        update["purchase_timing_mode"] = "parallel"
    elif timing_mode == "manual_month":
        update["purchase_timing_mode"] = "manual_month"
    elif timing_mode == "not_planned":
        update["enabled"] = False
        update["purchase_timing_mode"] = "not_planned"
    else:
        update["purchase_timing_mode"] = "auto_sequence"
    earliest_delay = max(
        vehicle.manual_purchase_delay_months,
        vehicle.purchase_delay_months,
        goal.resolved_not_before_month,
        goal.resolved_window_start_month,
    )
    update["manual_purchase_delay_months"] = earliest_delay
    update["purchase_delay_months"] = min(120, earliest_delay)
    return update


def _child_plan_with_planning_goal_constraints(
    child: ChildPlanData,
    goal: PlanningGoalRecord,
    resolved_not_before_month: int,
) -> ChildPlanData:
    data = goal.data
    update: dict[str, Any] = {}
    if data.name:
        update["name"] = data.name
    update["enabled"] = bool(data.enabled) and data.timing_mode != "not_planned"
    update["planning_goal_id"] = goal.id
    if data.timing_mode == "manual_month":
        update["timing_mode"] = "manual_month"
        month_label = data.earliest_purchase_month or _month_label_from_delay(resolved_not_before_month)
        update["planned_birth_month"] = month_label
        update["planned_birth_start_month"] = data.planning_window_start_month or month_label
        update["planned_birth_end_month"] = data.planning_window_end_month or month_label
    elif data.timing_mode == "not_planned":
        update["timing_mode"] = "not_planned"
    else:
        metadata = data.metadata if isinstance(data.metadata, dict) else {}
        child_timing = str(metadata.get("child_timing_mode") or child.timing_mode or "after_first_home")
        update["timing_mode"] = "after_first_home" if child_timing == "after_first_home" else child_timing
        if resolved_not_before_month > 0:
            month_label = _month_label_from_delay(resolved_not_before_month)
            update["planned_birth_start_month"] = data.planning_window_start_month or child.planned_birth_start_month or month_label
        elif data.planning_window_start_month:
            update["planned_birth_start_month"] = data.planning_window_start_month
        if data.planning_window_end_month:
            update["planned_birth_end_month"] = data.planning_window_end_month
    target = data.target_params if isinstance(data.target_params, dict) else {}
    for key in [
        "expense_strategy_mode",
        "birth_month",
        "tax_deduction_owner",
        "education_start_month",
        "preparation_months_before_birth",
        "pregnancy_months_before_birth",
        "monthly_preparation_cost",
        "monthly_pregnancy_cost",
        "birth_medical_cost",
        "postpartum_recovery_cost",
        "initial_baby_supplies_cost",
        "monthly_childcare_cost_before_kindergarten",
        "monthly_kindergarten_cost",
        "monthly_primary_secondary_cost",
        "monthly_higher_education_cost",
        "kindergarten_entry_cost",
        "primary_school_entry_cost",
        "higher_education_entry_cost",
        "notes",
    ]:
        if key in target:
            update[key] = target[key]
    return child.model_copy(update=update)


def _child_plan_with_goal_snapshot_constraints(
    child: ChildPlanData,
    goal: CalculationContextGoalSnapshot,
) -> ChildPlanData:
    update: dict[str, Any] = {
        "planning_goal_id": goal.id,
        "name": goal.name or child.name,
        "enabled": goal.enabled and goal.normalized_timing_mode != "not_planned",
    }
    if goal.normalized_timing_mode == "manual_month":
        month_label = _month_label_from_delay(goal.resolved_not_before_month)
        update["timing_mode"] = "manual_month"
        update["planned_birth_month"] = month_label
        update["planned_birth_start_month"] = month_label
        update["planned_birth_end_month"] = month_label
    elif goal.normalized_timing_mode == "not_planned":
        update["timing_mode"] = "not_planned"
    elif goal.resolved_not_before_month > 0:
        update["planned_birth_start_month"] = _month_label_from_delay(goal.resolved_not_before_month)
    return child.model_copy(update=update)


def _all_goal_records_for_household(household_id: str) -> list[PlanningGoalRecord]:
    return [
        PlanningGoalRecord.model_validate(record)
        for record in list_planning_goal_records()
        if _household_id_in_scope(record.get("household_id"), household_id)
    ]


def _goal_applies_to_household(goal: PlanningGoalRecord, household_id: str) -> bool:
    return _household_id_in_scope(goal.household_id, household_id)


def _household_id_in_scope(goal_household_id: object, household_id: str) -> bool:
    return goal_household_id in {None, "", household_id}


def _month_label_from_delay(delay: int) -> str:
    today = date.today()
    target = add_months(date(today.year, today.month, 1), max(0, delay))
    return f"{target.year:04d}-{target.month:02d}"


def _project_child_goal_records_to_child_plans(
    child_goals: list[PlanningGoalRecord],
    resolved_by_id: dict[str, CalculationContextGoalSnapshot],
) -> list[ChildPlanData]:
    ordered_goals = sorted(
        child_goals,
        key=lambda goal: (
            resolved_by_id.get(goal.id).sequence_index if resolved_by_id.get(goal.id) else goal.data.priority,
            goal.data.priority,
            goal.id,
        ),
    )
    child_plans: list[ChildPlanData] = []
    for index, goal in enumerate(ordered_goals):
        child_data = child_plan_from_goal(goal.id, goal.data.model_dump(mode="json"), index)
        child_plans.append(ChildPlanData.model_validate(child_data))
    return child_plans


def _project_vehicle_goal_records_to_vehicle_plans(
    vehicle_goals: list[PlanningGoalRecord],
    resolved_by_id: dict[str, CalculationContextGoalSnapshot],
) -> list[VehiclePlanData]:
    ordered_goals = sorted(
        vehicle_goals,
        key=lambda goal: (
            resolved_by_id.get(goal.id).sequence_index if resolved_by_id.get(goal.id) else goal.data.priority,
            goal.data.priority,
            goal.id,
        ),
    )
    vehicle_plans: list[VehiclePlanData] = []
    for index, goal in enumerate(ordered_goals):
        snapshot = resolved_by_id.get(goal.id)
        vehicle_data = vehicle_plan_from_goal(
            goal.id,
            goal.data.model_dump(mode="json"),
            index,
            sequence_index=snapshot.sequence_index if snapshot else None,
        )
        vehicle_plans.append(VehiclePlanData.model_validate(vehicle_data))
    return vehicle_plans


def _household_with_vehicle_goal_constraints(
    household: HouseholdData,
    household_id: str,
    all_goal_records: list[PlanningGoalRecord],
    resolved_by_id: dict[str, CalculationContextGoalSnapshot],
) -> HouseholdData:
    vehicle_goals = [
        goal for goal in all_goal_records
        if goal.goal_type == "vehicle" and _goal_applies_to_household(goal, household_id)
    ]
    has_vehicle_snapshots = any(snapshot.goal_type == "vehicle" for snapshot in resolved_by_id.values())
    if not vehicle_goals and not has_vehicle_snapshots:
        return household
    vehicle_goals = [
        goal.model_copy(
            update={
                "data": goal.data.model_copy(
                    update={
                        "earliest_purchase_delay_months": max(
                            goal.data.earliest_purchase_delay_months,
                            resolved_by_id.get(goal.id).resolved_not_before_month if resolved_by_id.get(goal.id) else 0,
                        )
                    }
                )
            }
        )
        for goal in vehicle_goals
    ]
    goals_by_id = {goal.id: goal for goal in vehicle_goals}
    goals_by_name = {goal.data.name: goal for goal in vehicle_goals if goal.data.name}
    goals_by_priority = {goal.data.priority: goal for goal in vehicle_goals}
    constrained_vehicles: list[VehiclePlanData] = []
    changed = False
    for vehicle in household.car_plan.vehicle_plans:
        goal_id = str(getattr(vehicle, "planning_goal_id", "") or "")
        goal = goals_by_id.get(goal_id) or goals_by_name.get(vehicle.name)
        if goal is None:
            goal = goals_by_priority.get(vehicle.planning_sequence)
        if goal is None:
            snapshot = resolved_by_id.get(goal_id) or _vehicle_goal_snapshot_by_name_or_priority(
                resolved_by_id,
                vehicle.name,
                vehicle.planning_sequence,
            )
            if snapshot is None:
                constrained_vehicles.append(vehicle)
                continue
            constrained = vehicle.model_copy(update=_vehicle_plan_update_from_goal_snapshot(vehicle, snapshot))
            constrained_vehicles.append(constrained)
            changed = changed or constrained != vehicle
            continue
        constrained = _vehicle_plan_with_planning_goal_constraints(vehicle, goal, resolved_by_id.get(goal.id))
        constrained_vehicles.append(constrained)
        changed = changed or constrained != vehicle
    if not changed:
        return household
    car_plan = household.car_plan.model_copy(update={"vehicle_plans": constrained_vehicles})
    return household.model_copy(update={"car_plan": car_plan})


def _vehicle_goal_snapshot_by_name_or_priority(
    resolved_by_id: dict[str, CalculationContextGoalSnapshot],
    vehicle_name: str,
    planning_sequence: int,
) -> CalculationContextGoalSnapshot | None:
    for snapshot in resolved_by_id.values():
        if snapshot.goal_type != "vehicle":
            continue
        if snapshot.name == vehicle_name or snapshot.priority == planning_sequence:
            return snapshot
    return None


def _child_plans_with_planning_goal_constraints(
    child_plans: list[ChildPlanData],
    household_id: str,
    all_goal_records: list[PlanningGoalRecord],
    resolved_by_id: dict[str, CalculationContextGoalSnapshot],
) -> list[ChildPlanData]:
    child_goals = [
        goal for goal in all_goal_records
        if goal.goal_type == "child" and _goal_applies_to_household(goal, household_id)
    ]
    has_child_snapshots = any(snapshot.goal_type == "child" for snapshot in resolved_by_id.values())
    if not child_goals and not has_child_snapshots:
        return child_plans
    goals_by_id = {goal.id: goal for goal in child_goals}
    goals_by_name = {goal.data.name: goal for goal in child_goals if goal.data.name}
    goals_by_priority = {goal.data.priority: goal for goal in child_goals}
    constrained: list[ChildPlanData] = []
    for index, child in enumerate(child_plans):
        goal_id = str(getattr(child, "planning_goal_id", "") or "")
        goal = goals_by_id.get(goal_id) or goals_by_name.get(child.name) or goals_by_priority.get(30 + index)
        if goal is None:
            snapshot = resolved_by_id.get(goal_id) or _child_goal_snapshot_by_name_or_priority(
                resolved_by_id,
                child.name,
                30 + index,
            )
            constrained.append(_child_plan_with_goal_snapshot_constraints(child, snapshot) if snapshot else child)
            continue
        resolved = resolved_by_id.get(goal.id)
        constrained.append(
            _child_plan_with_planning_goal_constraints(
                child,
                goal,
                resolved.resolved_not_before_month if resolved else goal.data.earliest_purchase_delay_months,
            )
        )
    return constrained


def _child_goal_snapshot_by_name_or_priority(
    resolved_by_id: dict[str, CalculationContextGoalSnapshot],
    child_name: str,
    priority: int,
) -> CalculationContextGoalSnapshot | None:
    for snapshot in resolved_by_id.values():
        if snapshot.goal_type != "child":
            continue
        if snapshot.name == child_name or snapshot.priority == priority:
            return snapshot
    return None
