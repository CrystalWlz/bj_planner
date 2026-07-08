from __future__ import annotations

from ..schemas import HouseholdData, RulePackData, ScenarioData


def household_with_member_derived_profile(household: HouseholdData) -> HouseholdData:
    members = household.members or []
    if not members:
        return household
    social_security_months = max((member.social_security_months for member in members), default=0)
    income_tax_months = max((member.income_tax_months for member in members), default=0)
    existing_home_count = sum(max(0, member.existing_home_count) for member in members)
    existing_mortgage_count = sum(max(0, member.existing_mortgage_count) for member in members)
    member_cash = sum(max(0.0, member.initial_cash_balance) for member in members)
    member_investments = sum(max(0.0, member.initial_investments) for member in members)

    update: dict[str, object] = {
        "social_security_months": max(household.social_security_months, social_security_months, income_tax_months),
        "existing_home_count": existing_home_count if existing_home_count > 0 else household.existing_home_count,
        "existing_mortgage_count": existing_mortgage_count if existing_mortgage_count > 0 else household.existing_mortgage_count,
    }
    if member_cash > 0:
        update["cash_account_balance"] = member_cash
    if member_investments > 0:
        update["investments"] = member_investments
    return household.model_copy(update=update)


def evaluate_home_purchase_eligibility(household: HouseholdData, rules: RulePackData) -> tuple[bool, list[str]]:
    params = rules.params
    required_months = int(params.get("required_social_security_months", 36))
    max_home_count = int(params.get("max_home_count", 2))

    notes: list[str] = []
    has_local_qualification = household.has_beijing_hukou or household.social_security_months >= required_months
    if has_local_qualification:
        notes.append("已满足北京户籍或社保/个税年限的规则包条件。")
    else:
        notes.append(f"社保/个税年限低于当前规则包要求的 {required_months} 个月。")

    within_home_count = household.existing_home_count < max_home_count
    if within_home_count:
        notes.append("现有住房套数低于规则包上限。")
    else:
        notes.append(f"现有住房套数已达到规则包上限 {max_home_count} 套。")

    return has_local_qualification and within_home_count, notes


def property_goal_for_scenario(household: HouseholdData, scenario: ScenarioData) -> tuple[int, str]:
    enabled_goals = [goal for goal in household.property_goals if goal.enabled]
    if not enabled_goals:
        return max(1, scenario.purchase_sequence), scenario.name
    matched = [
        goal for goal in enabled_goals
        if goal.scenario_id and goal.scenario_id == scenario.name
    ] or [
        goal for goal in enabled_goals
        if not goal.scenario_id and (goal.name == scenario.name or len(enabled_goals) == 1)
    ]
    if not matched:
        return 1, ""
    goal = sorted(matched, key=lambda item: item.priority)[0]
    return max(1, goal.priority), goal.name


def household_with_property_goal(household: HouseholdData, scenario: ScenarioData) -> tuple[HouseholdData, str]:
    priority, goal_name = property_goal_for_scenario(household, scenario)
    if scenario.purchase_planning_mode == "parallel":
        label = goal_name or f"第 {priority} 套购房需求"
        note = (
            f"已按「{label}」作为可并行考虑的第 {priority} 套购房目标处理：策略生成不默认等待前一套成交，"
            "但仍会使用当前既有住房、既有房贷和规则包资格条件测算。"
        )
        return household, note
    prior_purchase_count = max(0, priority - 1)
    if prior_purchase_count <= 0:
        return household, ""
    adjusted = household.model_copy(
        update={
            "existing_home_count": min(10, household.existing_home_count + prior_purchase_count),
            "existing_mortgage_count": min(10, household.existing_mortgage_count + prior_purchase_count),
        }
    )
    label = goal_name or f"第 {priority} 套购房需求"
    note = (
        f"已按「{label}」作为第 {priority} 套购房目标处理：策略生成时把前置 {prior_purchase_count} 套购房需求"
        "计入既有住房和既有房贷口径，首付比例、公积金资格和贷款压力按更保守口径测算。"
    )
    return adjusted, note
