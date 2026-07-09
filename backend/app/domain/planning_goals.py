from __future__ import annotations

from datetime import date

from ..schemas import PlanningGoalRecord, ResolvedPlanningGoal, PlanningSequenceResult
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


def _consumes_sequence_index(mode: str) -> bool:
    return mode not in {"not_planned", "parallel"}


def _base_goal_order(goals: list[PlanningGoalRecord]) -> list[PlanningGoalRecord]:
    return sorted(goals, key=lambda item: (item.data.priority, item.created_at, item.id))


def _ordered_goals_respecting_dependencies(
    goals: list[PlanningGoalRecord],
) -> tuple[list[PlanningGoalRecord], list[str]]:
    base_order = _base_goal_order(goals)
    by_id = {item.id: item for item in base_order}
    visited: set[str] = set()
    visiting: set[str] = set()
    ordered: list[PlanningGoalRecord] = []
    warnings: list[str] = []

    def visit(goal: PlanningGoalRecord) -> None:
        if goal.id in visited:
            return
        if goal.id in visiting:
            warning = f"目标「{_goal_label(goal)}」的依赖关系形成循环，已按优先级顺序保守处理。"
            if warning not in warnings:
                warnings.append(warning)
            return
        visiting.add(goal.id)
        if _timing_mode(goal) == "after_goal":
            dependency = by_id.get(goal.data.depends_on_goal_id)
            if dependency is not None and dependency.id != goal.id and _timing_mode(dependency) != "not_planned":
                visit(dependency)
        visiting.remove(goal.id)
        if goal.id not in visited:
            visited.add(goal.id)
            ordered.append(goal)

    for goal in base_order:
        visit(goal)
    return ordered, warnings


def resolve_planning_sequence(
    goals: list[PlanningGoalRecord],
    *,
    base_month: date | None = None,
) -> PlanningSequenceResult:
    current_month = base_month or date.today()
    base_month_label = f"{current_month.year:04d}-{current_month.month:02d}"
    ordered, ordering_warnings = _ordered_goals_respecting_dependencies(goals)
    by_id = {item.id: item for item in ordered}
    resolved_by_id: dict[str, ResolvedPlanningGoal] = {}
    warnings: list[str] = list(ordering_warnings)
    resolved: list[ResolvedPlanningGoal] = []

    previous_sequential_goal_id = ""
    planned_sequence_index = 0
    for goal in ordered:
        data = goal.data
        mode = _timing_mode(goal)
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
            dependency = by_id.get(depends_on_goal_id)
            depends_on_goal_name = _goal_label(dependency) if dependency else ""
            if dependency is None:
                dependency_warning = f"目标「{_goal_label(goal)}」设置为跟随其他目标，但依赖目标不存在，已按自动顺序处理。"
                warnings.append(dependency_warning)
                mode = "auto_sequence"
                depends_on_goal_id = ""
                depends_on_goal_name = ""
            elif _timing_mode(dependency) == "not_planned":
                dependency_warning = f"目标「{_goal_label(goal)}」设置为跟随「{_goal_label(dependency)}」，但该目标暂不纳入规划，已按自动顺序处理。"
                warnings.append(dependency_warning)
                mode = "auto_sequence"
                depends_on_goal_id = ""
                depends_on_goal_name = ""
            else:
                dependency_resolved = resolved_by_id.get(depends_on_goal_id)
                if dependency_resolved is None:
                    dependency_warning = f"目标「{_goal_label(goal)}」依赖的目标尚未在排序中出现，已按依赖目标的最早窗口保守处理。"
                    warnings.append(dependency_warning)
                    not_before = max(not_before, data.delay_after_dependency_months)
                else:
                    not_before = max(
                        not_before,
                        dependency_resolved.resolved_not_before_month + data.delay_after_dependency_months,
                    )
        if mode == "auto_sequence" and previous_sequential_goal_id:
            dependency_resolved = resolved_by_id.get(previous_sequential_goal_id)
            if dependency_resolved is not None:
                depends_on_goal_id = previous_sequential_goal_id
                depends_on_goal_name = dependency_resolved.name
                not_before = max(not_before, dependency_resolved.resolved_not_before_month + data.delay_after_dependency_months)

        if mode == "manual_month" and explicit_start is None and data.earliest_purchase_delay_months <= 0:
            dependency_warning = f"目标「{_goal_label(goal)}」设置为手动指定时间，但没有填写年月，已按当前月作为下限。"
            warnings.append(dependency_warning)

        if mode != "not_planned" and window_end is not None and window_end < not_before:
            warning = f"目标「{_goal_label(goal)}」的规划窗口结束早于最早可考虑月份，策略生成时可能不可行。"
            warnings.append(warning)
            dependency_warning = dependency_warning or warning

        if _consumes_sequence_index(mode):
            previous_sequential_goal_id = goal.id

        explanation = _goal_explanation(
            mode=mode,
            goal=goal,
            not_before=not_before,
            window_end=window_end,
            depends_on_goal_name=depends_on_goal_name,
        )
        item = ResolvedPlanningGoal(
            id=goal.id,
            household_id=goal.household_id,
            goal_type=goal.goal_type,
            name=_goal_label(goal),
            enabled=data.enabled,
            priority=data.priority,
            sequence_index=sequence_index,
            timing_mode=data.timing_mode,
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
        resolved_by_id[goal.id] = item
        resolved.append(item)

    return PlanningSequenceResult(base_month=base_month_label, goals=resolved, warnings=warnings)


def _goal_explanation(
    *,
    mode: str,
    goal: PlanningGoalRecord,
    not_before: int,
    window_end: int | None,
    depends_on_goal_name: str,
) -> str:
    window_text = f"，最早从第 {not_before} 个月开始考虑"
    if window_end is not None:
        window_text += f"，窗口最晚到第 {window_end} 个月"
    if mode == "not_planned":
        return f"目标「{_goal_label(goal)}」暂不纳入当前规划。"
    if mode == "parallel":
        return f"目标「{_goal_label(goal)}」允许与其他目标并行评估{window_text}。"
    if mode == "manual_month":
        return f"目标「{_goal_label(goal)}」使用手动指定时间{window_text}。"
    if mode == "after_goal":
        dependency = depends_on_goal_name or "指定目标"
        return f"目标「{_goal_label(goal)}」排在「{dependency}」之后，延迟 {goal.data.delay_after_dependency_months} 个月再考虑。"
    if depends_on_goal_name:
        return f"目标「{_goal_label(goal)}」按优先级排在「{depends_on_goal_name}」之后{window_text}。"
    return f"目标「{_goal_label(goal)}」按自动顺序进入规划{window_text}。"
