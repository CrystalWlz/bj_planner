from __future__ import annotations

from datetime import date

from ..schemas import PlanningGoalRecord, PlanningSequenceResult, ResolvedPlanningGoal
from .time import month_distance, parse_year_month


def _month_offset(value: str, base_month: date) -> int | None:
    parsed = parse_year_month(value)
    if parsed is None:
        return None
    return max(0, month_distance((base_month.year, base_month.month), parsed))


def _timing_mode(goal: PlanningGoalRecord) -> str:
    mode = goal.data.timing_mode
    if not goal.data.enabled:
        return "not_planned"
    if mode == "parallel" or goal.data.allow_parallel:
        return "parallel"
    if mode in {"manual_month", "after_goal", "not_planned"}:
        return mode
    return "auto_sequence"


def _goal_label(goal: PlanningGoalRecord) -> str:
    return goal.data.name or goal.id


def _home_demand_label(priority: int) -> str:
    sequence = max(1, priority)
    return "第一套购房需求" if sequence == 1 else f"第 {sequence} 套购房需求"


def _planning_group_key(goal: PlanningGoalRecord) -> str:
    if goal.goal_type == "home":
        return f"home:{max(1, goal.data.priority)}"
    return goal.id


def _planning_group_label(goals: list[PlanningGoalRecord]) -> str:
    representative = goals[0]
    if representative.goal_type == "home" and len(goals) > 1:
        return _home_demand_label(representative.data.priority)
    return _goal_label(representative)


def _goal_target_amount(goal: PlanningGoalRecord) -> float:
    target = goal.data.target_params
    for key in ("estimated_cost", "budget", "amount", "total_price"):
        value = target.get(key)
        if value is not None:
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _consumes_sequence_index(mode: str) -> bool:
    return mode not in {"not_planned", "parallel"}


def _base_goal_order(goals: list[PlanningGoalRecord]) -> list[PlanningGoalRecord]:
    return sorted(goals, key=lambda item: (item.data.priority, item.created_at, item.id))


def _base_goal_groups(goals: list[PlanningGoalRecord]) -> list[list[PlanningGoalRecord]]:
    groups: dict[str, list[PlanningGoalRecord]] = {}
    for goal in _base_goal_order(goals):
        key = _planning_group_key(goal)
        groups.setdefault(key, []).append(goal)
    return list(groups.values())


def _ordered_goal_groups_respecting_dependencies(
    goals: list[PlanningGoalRecord],
) -> tuple[list[list[PlanningGoalRecord]], list[str]]:
    base_groups = _base_goal_groups(goals)
    by_key = {_planning_group_key(group[0]): group for group in base_groups}
    group_key_by_goal_id = {
        goal.id: _planning_group_key(group[0])
        for group in base_groups
        for goal in group
    }
    visited: set[str] = set()
    visiting: set[str] = set()
    ordered: list[list[PlanningGoalRecord]] = []
    warnings: list[str] = []

    def visit(group: list[PlanningGoalRecord]) -> None:
        key = _planning_group_key(group[0])
        if key in visited:
            return
        if key in visiting:
            warning = f"目标「{_planning_group_label(group)}」的依赖关系形成循环，已按优先级顺序保守处理。"
            if warning not in warnings:
                warnings.append(warning)
            return
        visiting.add(key)
        representative = group[0]
        if _timing_mode(representative) == "after_goal":
            dependency_key = group_key_by_goal_id.get(representative.data.depends_on_goal_id)
            dependency = by_key.get(dependency_key or "")
            if dependency is not None and dependency_key != key and _timing_mode(dependency[0]) != "not_planned":
                visit(dependency)
        visiting.remove(key)
        if key not in visited:
            visited.add(key)
            ordered.append(group)

    for group in base_groups:
        visit(group)
    return ordered, warnings


def resolve_planning_sequence(
    goals: list[PlanningGoalRecord],
    *,
    base_month: date | None = None,
) -> PlanningSequenceResult:
    current_month = base_month or date.today()
    base_month_label = f"{current_month.year:04d}-{current_month.month:02d}"
    ordered_groups, ordering_warnings = _ordered_goal_groups_respecting_dependencies(goals)
    groups_by_key = {_planning_group_key(group[0]): group for group in ordered_groups}
    group_key_by_goal_id = {
        goal.id: _planning_group_key(group[0])
        for group in ordered_groups
        for goal in group
    }
    resolved_by_group_key: dict[str, ResolvedPlanningGoal] = {}
    warnings: list[str] = list(ordering_warnings)
    resolved: list[ResolvedPlanningGoal] = []

    previous_sequential_group_key = ""
    planned_sequence_index = 0
    for group in ordered_groups:
        representative = group[0]
        data = representative.data
        group_key = _planning_group_key(representative)
        group_id = representative.id
        group_name = _planning_group_label(group)
        group_member_ids = [goal.id for goal in group]
        mode = _timing_mode(representative)
        sequence_index = 0
        if _consumes_sequence_index(mode):
            planned_sequence_index += 1
            sequence_index = planned_sequence_index
        dependency_warning = ""
        depends_on_goal_id = data.depends_on_goal_id
        depends_on_goal_name = ""
        explicit_start = _month_offset(data.earliest_purchase_month, current_month)
        window_start = _month_offset(data.planning_window_start_month, current_month)
        window_end = _month_offset(data.planning_window_end_month, current_month)
        not_before = max(0, data.earliest_purchase_delay_months, explicit_start or 0, window_start or 0)

        if mode == "after_goal":
            dependency_group_key = group_key_by_goal_id.get(depends_on_goal_id)
            dependency_group = groups_by_key.get(dependency_group_key or "")
            if dependency_group is None:
                dependency_warning = f"目标「{group_name}」设置为跟随其他目标，但依赖目标不存在，已按自动顺序处理。"
                warnings.append(dependency_warning)
                mode = "auto_sequence"
                depends_on_goal_id = ""
            elif dependency_group_key == group_key:
                dependency_warning = f"目标「{group_name}」不能依赖同一需求内的候选项，已按自动顺序处理。"
                warnings.append(dependency_warning)
                mode = "auto_sequence"
                depends_on_goal_id = ""
            elif _timing_mode(dependency_group[0]) == "not_planned":
                depends_on_goal_name = _planning_group_label(dependency_group)
                dependency_warning = f"目标「{group_name}」设置为跟随「{depends_on_goal_name}」，但该目标暂不纳入规划，已按自动顺序处理。"
                warnings.append(dependency_warning)
                mode = "auto_sequence"
                depends_on_goal_id = ""
                depends_on_goal_name = ""
            else:
                dependency_group_id = dependency_group[0].id
                dependency_resolved = resolved_by_group_key.get(dependency_group_key or "")
                depends_on_goal_id = dependency_group_id
                depends_on_goal_name = _planning_group_label(dependency_group)
                if dependency_resolved is None:
                    dependency_warning = f"目标「{group_name}」依赖的目标尚未在排序中出现，已按依赖目标的最早窗口保守处理。"
                    warnings.append(dependency_warning)
                    not_before = max(not_before, data.delay_after_dependency_months)
                else:
                    not_before = max(
                        not_before,
                        dependency_resolved.resolved_not_before_month + data.delay_after_dependency_months,
                    )
        if mode == "auto_sequence" and previous_sequential_group_key:
            dependency_resolved = resolved_by_group_key.get(previous_sequential_group_key)
            if dependency_resolved is not None:
                depends_on_goal_id = dependency_resolved.planning_group_id or dependency_resolved.id
                depends_on_goal_name = dependency_resolved.planning_group_name or dependency_resolved.name
                not_before = max(not_before, dependency_resolved.resolved_not_before_month + data.delay_after_dependency_months)

        if mode == "manual_month" and explicit_start is None and data.earliest_purchase_delay_months <= 0:
            dependency_warning = f"目标「{group_name}」设置为手动指定时间，但没有填写年月，已按当前月作为下限。"
            warnings.append(dependency_warning)

        if mode != "not_planned" and window_end is not None and window_end < not_before:
            warning = f"目标「{group_name}」的规划窗口结束早于最早可考虑月份，策略生成时可能不可行。"
            warnings.append(warning)
            dependency_warning = dependency_warning or warning

        if _consumes_sequence_index(mode):
            previous_sequential_group_key = group_key

        explanation = _goal_explanation(
            mode=mode,
            goal_label=group_name,
            delay_after_dependency_months=data.delay_after_dependency_months,
            not_before=not_before,
            window_end=window_end,
            depends_on_goal_name=depends_on_goal_name,
        )
        group_items: list[ResolvedPlanningGoal] = []
        for goal in group:
            item = ResolvedPlanningGoal(
                id=goal.id,
                household_id=goal.household_id,
                goal_type=goal.goal_type,
                name=_goal_label(goal),
                planning_group_id=group_id,
                planning_group_name=group_name,
                planning_group_size=len(group),
                planning_group_member_ids=group_member_ids,
                target_amount=_goal_target_amount(goal),
                funding_mode=str(goal.data.financing_preferences.get("funding_mode") or ""),
                enabled=goal.data.enabled,
                priority=goal.data.priority,
                sequence_index=sequence_index,
                timing_mode=goal.data.timing_mode,
                normalized_timing_mode=mode,  # type: ignore[arg-type]
                depends_on_goal_id=depends_on_goal_id,
                depends_on_goal_name=depends_on_goal_name,
                delay_after_dependency_months=data.delay_after_dependency_months,
                allow_parallel=data.allow_parallel or mode == "parallel",
                earliest_purchase_month=data.earliest_purchase_month,
                earliest_purchase_delay_months=data.earliest_purchase_delay_months,
                planning_window_start_month=data.planning_window_start_month,
                planning_window_end_month=data.planning_window_end_month,
                resolved_not_before_month=not_before,
                resolved_window_start_month=window_start or 0,
                resolved_window_end_month=window_end,
                dependency_warning=dependency_warning,
                explanation=explanation,
            )
            group_items.append(item)
            resolved.append(item)
        if group_items:
            resolved_by_group_key[group_key] = group_items[0]

    return PlanningSequenceResult(base_month=base_month_label, goals=resolved, warnings=warnings)


def _goal_explanation(
    *,
    mode: str,
    goal_label: str,
    delay_after_dependency_months: int,
    not_before: int,
    window_end: int | None,
    depends_on_goal_name: str,
) -> str:
    window_text = f"，最早从第 {not_before} 个月开始考虑"
    if window_end is not None:
        window_text += f"，窗口最晚到第 {window_end} 个月"
    if mode == "not_planned":
        return f"目标「{goal_label}」暂不纳入当前规划。"
    if mode == "parallel":
        return f"目标「{goal_label}」允许与其他目标并行评估{window_text}。"
    if mode == "manual_month":
        return f"目标「{goal_label}」使用手动指定时间{window_text}。"
    if mode == "after_goal":
        dependency = depends_on_goal_name or "指定目标"
        return f"目标「{goal_label}」排在「{dependency}」之后，延迟 {delay_after_dependency_months} 个月再考虑。"
    if depends_on_goal_name:
        return f"目标「{goal_label}」按优先级排在「{depends_on_goal_name}」之后{window_text}。"
    return f"目标「{goal_label}」按自动顺序进入规划{window_text}。"
