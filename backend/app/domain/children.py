from __future__ import annotations

from datetime import date
from typing import Any

from ..policies import get_policy
from ..schemas import CalculationContextGoalSnapshot, CalculationContextSnapshot, ChildPlanStrategyPoint, HouseholdData, IncomeMember, RulePackData
from .time import (
    format_year_month_tuple,
    month_after,
    month_distance,
    month_tuple_to_date,
    parse_year_month,
)


def _money_text(amount: float) -> str:
    return f"{round(amount):,} 元".replace(",", "")


def _child_policy(rules: RulePackData):
    return get_policy(rules).child_planning_policy()


def child_plan_birth_month_for_strategy(
    child: object,
    *,
    as_of: date,
    home_purchase_month: int | None = None,
    rules: RulePackData,
) -> tuple[int, int] | None:
    actual = parse_year_month(getattr(child, "birth_month", ""))
    if actual is not None:
        return actual
    start = parse_year_month(getattr(child, "planned_birth_start_month", ""))
    end = parse_year_month(getattr(child, "planned_birth_end_month", ""))
    single = parse_year_month(getattr(child, "planned_birth_month", ""))
    if start is None and end is None and single is not None:
        start = single
        end = single
    if start is not None or end is not None:
        if start is None:
            start = end
        if end is None:
            end = start
        if start is None or end is None:
            return None
        if month_distance(start, end) < 0:
            start, end = end, start
        earliest = start
        if getattr(child, "timing_mode", "") == "after_first_home" and home_purchase_month is not None:
            delay = _child_policy(rules).birth_after_home_delay_months
            after_home = month_after(as_of, max(0, home_purchase_month + delay))
            if month_distance(earliest, after_home) > 0:
                earliest = after_home
        return earliest if month_distance(earliest, end) >= 0 else end
    if getattr(child, "timing_mode", "") == "after_first_home":
        if home_purchase_month is None:
            return None
        delay = _child_policy(rules).birth_after_home_delay_months
        return month_after(as_of, max(0, home_purchase_month + delay))
    return None


def child_plan_stage_expense_at(
    child: object,
    target_month: tuple[int, int],
    *,
    as_of: date,
    home_purchase_month: int | None = None,
    rules: RulePackData,
) -> tuple[float, list[tuple[str, float]]]:
    birth_month = child_plan_birth_month_for_strategy(
        child,
        as_of=as_of,
        home_purchase_month=home_purchase_month,
        rules=rules,
    )
    if birth_month is None:
        return 0.0, []
    total = 0.0
    components: list[tuple[str, float]] = []
    age_months = month_distance(birth_month, target_month)
    months_until_birth = month_distance(target_month, birth_month)
    preparation_months = max(0, int(getattr(child, "preparation_months_before_birth", 6)))
    pregnancy_months = max(0, int(getattr(child, "pregnancy_months_before_birth", 9)))
    if months_until_birth > 0:
        if months_until_birth <= pregnancy_months:
            amount = float(getattr(child, "monthly_pregnancy_cost", 0))
            total += amount
            components.append(("孕期检查与营养", amount))
        elif months_until_birth <= preparation_months:
            amount = float(getattr(child, "monthly_preparation_cost", 0))
            total += amount
            components.append(("备孕准备", amount))
        return max(0.0, total), [(name, value) for name, value in components if value > 0]
    if age_months == 0:
        for name, attr in [
            ("生产医疗", "birth_medical_cost"),
            ("产后恢复与月嫂", "postpartum_recovery_cost"),
            ("新生儿初始用品", "initial_baby_supplies_cost"),
        ]:
            amount = float(getattr(child, attr, 0))
            total += amount
            components.append((name, amount))
    if age_months >= 0:
        if age_months < 36:
            amount = float(getattr(child, "monthly_childcare_cost_before_kindergarten", 0))
            total += amount
            components.append(("婴幼儿月支出", amount))
        else:
            education_start = parse_year_month(getattr(child, "education_start_month", ""))
            if education_start is None:
                kindergarten_start = (birth_month[0] + 3, birth_month[1])
                primary_start = (birth_month[0] + 6, 9)
                higher_start = (birth_month[0] + 18, 9)
            else:
                primary_start = education_start
                kindergarten_start = (birth_month[0] + 3, birth_month[1])
                higher_start = (education_start[0] + 12, education_start[1])
            if target_month == kindergarten_start:
                amount = float(getattr(child, "kindergarten_entry_cost", 0))
                total += amount
                components.append(("幼儿园入园一次性支出", amount))
            if target_month == primary_start:
                amount = float(getattr(child, "primary_school_entry_cost", 0))
                total += amount
                components.append(("中小学入学一次性支出", amount))
            if target_month == higher_start:
                amount = float(getattr(child, "higher_education_entry_cost", 0))
                total += amount
                components.append(("高等教育启动支出", amount))
            if education_start is not None and month_distance(education_start, target_month) >= 0:
                if age_months < 18 * 12:
                    amount = float(getattr(child, "monthly_primary_secondary_cost", 0))
                    total += amount
                    components.append(("中小学月支出", amount))
                else:
                    amount = float(getattr(child, "monthly_higher_education_cost", 0))
                    total += amount
                    components.append(("高等教育月支出", amount))
            else:
                amount = float(getattr(child, "monthly_kindergarten_cost", 0))
                total += amount
                components.append(("幼儿园月支出", amount))
    return max(0.0, total), [(name, value) for name, value in components if value > 0]


def child_plan_monthly_expense_at(
    household: HouseholdData,
    target_month: tuple[int, int],
    *,
    as_of: date | None = None,
    home_purchase_month: int | None = None,
    rules: RulePackData,
) -> float:
    total = 0.0
    current = as_of or date.today()
    for child in household.child_plans:
        if not child.enabled:
            continue
        amount, _ = child_plan_stage_expense_at(
            child,
            target_month,
            as_of=current,
            home_purchase_month=home_purchase_month,
            rules=rules,
        )
        total += amount
    return max(0.0, total)


def _child_mother_member(household: HouseholdData) -> IncomeMember | None:
    female_members = [member for member in household.members if member.sex == "female"]
    return female_members[0] if female_members else None


def _age_years_from_birth_month_at(birth_month: str, target_month: tuple[int, int]) -> float | None:
    parsed = parse_year_month(birth_month)
    if parsed is None:
        return None
    return max(0.0, month_distance(parsed, target_month) / 12)


def _child_plan_happiness_score(
    *,
    first_year_cash_need: float,
    total_to_age_18: float,
    mother_age: float | None,
    rules: RulePackData,
) -> float:
    policy = get_policy(rules).child_planning_policy()
    advanced_age = policy.advanced_maternal_age
    cashflow_score = 10.0 if first_year_cash_need <= 80000 else max(0.0, 10 - (first_year_cash_need - 80000) / 30000)
    long_term_score = 10.0 if total_to_age_18 <= 900000 else max(0.0, 10 - (total_to_age_18 - 900000) / 200000)
    age_score = 8.0
    if mother_age is not None:
        if mother_age < 25:
            age_score = 7.0
        elif mother_age <= advanced_age:
            age_score = 9.0
        else:
            age_score = max(3.0, 9.0 - (mother_age - advanced_age) * 0.8)
    weights = policy.happiness_weights
    score = (
        8.0 * float(weights.get("timing", 0.22))
        + cashflow_score * float(weights.get("cashflow", 0.26))
        + long_term_score * float(weights.get("liquidity", 0.20))
        + age_score * float(weights.get("maternal_age", 0.18))
        + 8.0 * float(weights.get("education_readiness", 0.14))
    )
    return round(max(0.0, min(10.0, score)), 2)


def _child_goal_snapshots_by_key(
    calculation_context: CalculationContextSnapshot | None,
) -> tuple[dict[str, CalculationContextGoalSnapshot], dict[str, CalculationContextGoalSnapshot], dict[int, CalculationContextGoalSnapshot]]:
    if calculation_context is None:
        return {}, {}, {}
    goals = [goal for goal in calculation_context.planning_goals if goal.goal_type == "child"]
    return (
        {goal.id: goal for goal in goals if goal.id},
        {goal.name: goal for goal in goals if goal.name},
        {goal.priority: goal for goal in goals},
    )


def _child_goal_snapshot_for_plan(
    child: object,
    index: int,
    *,
    by_id: dict[str, CalculationContextGoalSnapshot],
    by_name: dict[str, CalculationContextGoalSnapshot],
    by_priority: dict[int, CalculationContextGoalSnapshot],
) -> CalculationContextGoalSnapshot | None:
    goal_id = str(getattr(child, "planning_goal_id", "") or "")
    return by_id.get(goal_id) or by_name.get(str(getattr(child, "name", "") or "")) or by_priority.get(30 + index)


def _birth_month_from_goal_snapshot(
    goal: CalculationContextGoalSnapshot | None,
    *,
    as_of: date,
) -> tuple[int, int] | None:
    if goal is None:
        return None
    if goal.normalized_timing_mode == "not_planned":
        return None
    month_index = goal.resolved_window_start_month or goal.resolved_not_before_month
    return month_after(as_of, max(0, month_index))


def build_child_plan_strategies(
    household: HouseholdData,
    rules: RulePackData,
    *,
    home_purchase_month: int | None = None,
    as_of: date | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[ChildPlanStrategyPoint]:
    current = date((as_of or date.today()).year, (as_of or date.today()).month, 1)
    mother = _child_mother_member(household)
    advanced_age = get_policy(rules).child_planning_policy().advanced_maternal_age
    points: list[ChildPlanStrategyPoint] = []
    child_goals_by_id, child_goals_by_name, child_goals_by_priority = _child_goal_snapshots_by_key(calculation_context)
    child_plans_with_goal = [
        (
            child_index,
            child,
            _child_goal_snapshot_for_plan(
                child,
                child_index,
                by_id=child_goals_by_id,
                by_name=child_goals_by_name,
                by_priority=child_goals_by_priority,
            ),
        )
        for child_index, child in enumerate(household.child_plans)
    ]
    ordered_child_plans = sorted(
        child_plans_with_goal,
        key=lambda item: (max(1, item[2].sequence_index) if item[2] is not None else 10_000 + item[0], item[0]),
    )
    for child_index, child, goal in ordered_child_plans:
        goal_birth_month = _birth_month_from_goal_snapshot(goal, as_of=current)
        birth_month = goal_birth_month or child_plan_birth_month_for_strategy(
            child,
            as_of=current,
            home_purchase_month=home_purchase_month,
            rules=rules,
        )
        effective_enabled = child.enabled if goal is None else goal.enabled and goal.normalized_timing_mode != "not_planned"
        effective_timing_mode = child.timing_mode
        if goal is not None:
            if goal.normalized_timing_mode == "manual_month":
                effective_timing_mode = "manual_month"
            elif goal.normalized_timing_mode == "not_planned":
                effective_timing_mode = "not_planned"
        birth_index = month_distance((current.year, current.month), birth_month) if birth_month else None
        prep_index = None
        pregnancy_index = None
        education_index = None
        stages: list[dict[str, Any]] = []
        first_year_cash_need = 0.0
        total_to_age_18 = 0.0
        monthly_now = (
            child_plan_stage_expense_at(
                child,
                (current.year, current.month),
                as_of=current,
                home_purchase_month=home_purchase_month,
                rules=rules,
            )[0]
            if effective_enabled
            else 0.0
        )
        if birth_month is not None:
            prep_start = month_after(month_tuple_to_date(birth_month), -max(0, child.preparation_months_before_birth))
            pregnancy_start = month_after(month_tuple_to_date(birth_month), -max(0, child.pregnancy_months_before_birth))
            prep_index = month_distance((current.year, current.month), prep_start)
            pregnancy_index = month_distance((current.year, current.month), pregnancy_start)
            education_start = parse_year_month(child.education_start_month) or (birth_month[0] + 6, 9)
            education_index = month_distance((current.year, current.month), education_start)
            for offset in range(max(0, birth_index or 0), max(0, (birth_index or 0) + 12)):
                amount, _ = child_plan_stage_expense_at(
                    child,
                    month_after(current, offset),
                    as_of=current,
                    home_purchase_month=home_purchase_month,
                    rules=rules,
                )
                first_year_cash_need += amount
            horizon_months = max(0, (birth_index or 0) + 18 * 12)
            for offset in range(max(0, prep_index), horizon_months + 1):
                amount, _ = child_plan_stage_expense_at(
                    child,
                    month_after(current, offset),
                    as_of=current,
                    home_purchase_month=home_purchase_month,
                    rules=rules,
                )
                total_to_age_18 += amount
            stage_specs = [
                ("备孕准备", prep_index, child.monthly_preparation_cost, "按月"),
                ("孕期检查与营养", pregnancy_index, child.monthly_pregnancy_cost, "按月"),
                ("生产医疗", birth_index, child.birth_medical_cost, "一次性"),
                ("产后恢复与月嫂", birth_index, child.postpartum_recovery_cost, "一次性"),
                ("新生儿初始用品", birth_index, child.initial_baby_supplies_cost, "一次性"),
                ("婴幼儿照护", birth_index, child.monthly_childcare_cost_before_kindergarten, "0-3岁按月"),
                ("幼儿园", (birth_index or 0) + 36 if birth_index is not None else None, child.monthly_kindergarten_cost, "按月"),
                ("中小学", education_index, child.monthly_primary_secondary_cost, "按月"),
                ("高等教育", (birth_index or 0) + 18 * 12 if birth_index is not None else None, child.monthly_higher_education_cost, "按月"),
            ]
            stages = [
                {
                    "name": name,
                    "month_index": month_index,
                    "month_label": format_year_month_tuple(month_after(current, month_index)) if month_index is not None else "",
                    "amount": round(float(amount), 2),
                    "frequency": frequency,
                }
                for name, month_index, amount, frequency in stage_specs
                if amount > 0
            ]
        mother_age = _age_years_from_birth_month_at(mother.birth_month, birth_month) if mother and birth_month else None
        warnings: list[str] = []
        if not effective_enabled:
            warnings.append("该子女目标未纳入当前现金流测算。")
        if goal is not None:
            if goal.dependency_warning:
                warnings.append(goal.dependency_warning)
            if goal.explanation:
                warnings.append(f"时间安排来自统一规划目标：{goal.explanation}")
        if birth_month is None:
            warnings.append("尚未形成具体出生月；未设置时间范围时会等选中购房方案后按买房后开始计划推定。")
        if mother is None:
            warnings.append("家庭成员未设置女性成员，暂无法自动评估母亲生产年龄。")
        if mother_age is not None and mother_age >= advanced_age:
            warnings.append(
                f"按当前策略，母亲生产年龄约 {mother_age:.1f} 岁，已达到 {advanced_age:.0f} 岁高龄妊娠提示线，应预留更多医疗与时间弹性。"
            )
        if first_year_cash_need > 120000:
            warnings.append("出生后首年现金需求较高，策略应同步检查现金安全垫和父母照护支出。")
        happiness_score = _child_plan_happiness_score(
            first_year_cash_need=first_year_cash_need,
            total_to_age_18=total_to_age_18,
            mother_age=mother_age,
            rules=rules,
        )
        explanation = (
            f"策略按{format_year_month_tuple(birth_month) or '待定'}作为出生月推演；"
            f"首年现金需求约 {_money_text(first_year_cash_need)}，18岁前口径累计约 {_money_text(total_to_age_18)}。"
            f"幸福指数综合时间可控性、现金流压力、长期教育支出和母亲生产年龄风险，当前为 {happiness_score}/10。"
        )
        points.append(
            ChildPlanStrategyPoint(
                planning_goal_id=goal.id if goal else getattr(child, "planning_goal_id", ""),
                source="planning_goals" if goal else "child_plans",
                child_name=child.name,
                enabled=effective_enabled,
                timing_mode=effective_timing_mode,
                expense_strategy_mode=child.expense_strategy_mode,
                birth_month_index=birth_index,
                birth_month_label=format_year_month_tuple(birth_month),
                preparation_start_month_index=prep_index,
                pregnancy_start_month_index=pregnancy_index,
                education_start_month_index=education_index,
                mother_member_name=mother.name if mother else "",
                mother_age_at_birth=round(mother_age, 2) if mother_age is not None else None,
                happiness_score=happiness_score,
                warnings=warnings,
                monthly_cost_now=round(monthly_now, 2),
                first_year_cash_need=round(first_year_cash_need, 2),
                total_to_age_18=round(total_to_age_18, 2),
                stages=stages,
                explanation=explanation,
            )
        )
    return points
