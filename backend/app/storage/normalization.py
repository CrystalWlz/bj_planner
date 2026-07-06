from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..schemas import (
    HouseholdData,
    MarketSnapshotData,
    PlanningGoalData,
    RulePackData,
    ScenarioData,
    normalize_retirement_category_for_sex,
)
from .schema_version import CURRENT_SCHEMA_VERSION


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def planning_timing_from_scenario(scenario: dict[str, Any]) -> str:
    mode = str(scenario.get("purchase_planning_mode") or "after_previous_purchase")
    return "parallel" if mode == "parallel" else "auto_sequence"


def scenario_mode_from_goal(goal: dict[str, Any]) -> str:
    timing_mode = str(goal.get("timing_mode") or "auto_sequence")
    return "parallel" if timing_mode == "parallel" else "after_previous_purchase"


def planning_timing_from_vehicle(vehicle: dict[str, Any]) -> str:
    mode = str(vehicle.get("purchase_timing_mode") or "auto_sequence")
    return mode if mode in {"auto_sequence", "parallel", "manual_month"} else "auto_sequence"


def vehicle_timing_from_goal(goal: dict[str, Any]) -> str:
    timing_mode = str(goal.get("timing_mode") or "auto_sequence")
    if timing_mode in {"parallel", "manual_month"}:
        return timing_mode
    return "auto_sequence"


def home_goal_from_scenario(
    scenario: dict[str, Any],
    *,
    goal_id: str,
    household_id: str | None = None,
) -> dict[str, Any]:
    normalized_scenario = normalize_scenario(deepcopy(scenario))
    return normalize_planning_goal(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "goal_type": "home",
            "name": normalized_scenario.get("name") or "购房目标",
            "enabled": bool(normalized_scenario.get("enabled", True)),
            "priority": max(1, safe_int(normalized_scenario.get("purchase_sequence"), 1)),
            "timing_mode": planning_timing_from_scenario(normalized_scenario),
            "earliest_purchase_delay_months": max(0, safe_int(normalized_scenario.get("manual_purchase_delay_months"), 0)),
            "delay_after_dependency_months": max(0, safe_int(normalized_scenario.get("after_previous_purchase_delay_months"), 0)),
            "allow_parallel": str(normalized_scenario.get("purchase_planning_mode") or "") == "parallel",
            "selected_strategy_id": str(normalized_scenario.get("selected_purchase_plan_variant") or ""),
            "target_params": normalized_scenario,
            "financing_preferences": {
                "commercial_repayment_method": normalized_scenario.get("commercial_repayment_method"),
                "provident_repayment_method": normalized_scenario.get("provident_repayment_method"),
                "commercial_prepayment_mode": normalized_scenario.get("commercial_prepayment_mode"),
                "provident_account_repayment_strategy": normalized_scenario.get("provident_account_repayment_strategy"),
                "investment_withdrawal_mode": normalized_scenario.get("investment_withdrawal_mode"),
            },
            "metadata": {"household_id": household_id or ""},
        }
    )


def scenario_from_home_goal(goal_id: str, goal: dict[str, Any]) -> dict[str, Any]:
    scenario = deepcopy(goal.get("target_params") if isinstance(goal.get("target_params"), dict) else {})
    scenario["name"] = goal.get("name") or scenario.get("name") or "购房目标"
    scenario["enabled"] = bool(goal.get("enabled", True))
    scenario["purchase_sequence"] = max(1, safe_int(goal.get("priority"), safe_int(scenario.get("purchase_sequence"), 1)))
    scenario["purchase_planning_mode"] = scenario_mode_from_goal(goal)
    scenario["after_previous_purchase_delay_months"] = max(
        0,
        safe_int(goal.get("delay_after_dependency_months"), safe_int(scenario.get("after_previous_purchase_delay_months"), 0)),
    )
    scenario["manual_purchase_delay_months"] = max(
        0,
        safe_int(goal.get("earliest_purchase_delay_months"), safe_int(scenario.get("manual_purchase_delay_months"), 0)),
    )
    if goal.get("selected_strategy_id"):
        scenario["selected_purchase_plan_variant"] = str(goal.get("selected_strategy_id"))
    scenario["planning_goal_id"] = goal_id
    return normalize_scenario(scenario)


def vehicle_goal_from_plan(
    vehicle: dict[str, Any],
    *,
    household_id: str,
    index: int,
    goal_id: str,
) -> dict[str, Any]:
    vehicle_data = deepcopy(vehicle)
    fill_vehicle_timing_defaults(vehicle_data, index)
    fill_vehicle_prepayment_defaults(vehicle_data)
    normalize_vehicle_financing_options(vehicle_data)
    timing_mode = planning_timing_from_vehicle(vehicle_data)
    return normalize_planning_goal(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "goal_type": "vehicle",
            "name": vehicle_data.get("name") or f"用车需求 {index + 1}",
            "enabled": bool(vehicle_data.get("enabled", True)),
            "priority": max(1, safe_int(vehicle_data.get("planning_sequence"), index + 1)),
            "timing_mode": timing_mode,
            "earliest_purchase_delay_months": max(
                0,
                safe_int(vehicle_data.get("manual_purchase_delay_months"), safe_int(vehicle_data.get("purchase_delay_months"), 0)),
            ),
            "delay_after_dependency_months": max(0, safe_int(vehicle_data.get("after_previous_event_delay_months"), 0)),
            "allow_parallel": timing_mode == "parallel",
            "selected_strategy_id": str(vehicle_data.get("selected_strategy_variant") or "target"),
            "target_params": vehicle_data,
            "financing_preferences": {
                "financing_options": vehicle_data.get("financing_options", []),
                "loan_prepayment_enabled": vehicle_data.get("loan_prepayment_enabled", False),
                "loan_prepayment_strategy_type": vehicle_data.get("loan_prepayment_strategy_type", "none"),
            },
            "holding_cost_params": {
                "annual_mileage_km": vehicle_data.get("annual_mileage_km", 0),
                "monthly_parking_cost": vehicle_data.get("monthly_parking_cost", 0),
                "annual_maintenance_cost": vehicle_data.get("annual_maintenance_cost", 0),
                "annual_insurance_rate": vehicle_data.get("annual_insurance_rate", 0),
            },
            "metadata": {"household_id": household_id},
        }
    )


def vehicle_plan_from_goal(goal: dict[str, Any], index: int) -> dict[str, Any]:
    vehicle = deepcopy(goal.get("target_params") if isinstance(goal.get("target_params"), dict) else {})
    vehicle["name"] = goal.get("name") or vehicle.get("name") or f"用车需求 {index + 1}"
    vehicle["enabled"] = bool(goal.get("enabled", True))
    vehicle["planning_sequence"] = max(1, safe_int(goal.get("priority"), index + 1))
    vehicle["purchase_timing_mode"] = vehicle_timing_from_goal(goal)
    vehicle["manual_purchase_delay_months"] = max(
        0,
        safe_int(goal.get("earliest_purchase_delay_months"), safe_int(vehicle.get("manual_purchase_delay_months"), 0)),
    )
    vehicle["after_previous_event_delay_months"] = max(
        0,
        safe_int(goal.get("delay_after_dependency_months"), safe_int(vehicle.get("after_previous_event_delay_months"), 0)),
    )
    if goal.get("selected_strategy_id"):
        vehicle["selected_strategy_variant"] = str(goal.get("selected_strategy_id"))
    fill_vehicle_timing_defaults(vehicle, index)
    fill_vehicle_prepayment_defaults(vehicle)
    normalize_vehicle_financing_options(vehicle)
    return vehicle


def normalize_planning_goal(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data.get("target_params"), dict):
        data["target_params"] = {}
    data.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    data.setdefault("goal_type", "home")
    data.setdefault("name", "规划目标")
    data.setdefault("enabled", True)
    data.setdefault("priority", 1)
    data.setdefault("timing_mode", "auto_sequence")
    data.setdefault("earliest_purchase_month", "")
    data.setdefault("earliest_purchase_delay_months", 0)
    data.setdefault("depends_on_goal_id", "")
    data.setdefault("delay_after_dependency_months", 0)
    data.setdefault("allow_parallel", False)
    data.setdefault("selected_strategy_id", "")
    data.setdefault("financing_preferences", {})
    data.setdefault("holding_cost_params", {})
    data.setdefault("metadata", {})
    data.setdefault("notes", "")
    goal_type = str(data.get("goal_type") or "home")
    if goal_type == "home":
        data["target_params"] = normalize_scenario(data.get("target_params") if isinstance(data.get("target_params"), dict) else {})
        data["priority"] = max(1, safe_int(data.get("priority"), safe_int(data["target_params"].get("purchase_sequence"), 1)))
    elif goal_type == "vehicle":
        target = data.get("target_params") if isinstance(data.get("target_params"), dict) else {}
        fill_vehicle_timing_defaults(target, max(0, safe_int(data.get("priority"), 1) - 1))
        fill_vehicle_prepayment_defaults(target)
        candidates = target.get("candidate_vehicles")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                fill_vehicle_timing_defaults(candidate, max(0, safe_int(data.get("priority"), 1) - 1))
                fill_vehicle_prepayment_defaults(candidate)
                normalize_vehicle_financing_options(candidate)
        normalize_vehicle_financing_options(target)
        data["target_params"] = target
        data["priority"] = max(1, safe_int(data.get("priority"), safe_int(target.get("planning_sequence"), 1)))
    normalized = PlanningGoalData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def default_vehicle_financing_options() -> list[dict[str, Any]]:
    return [
        {
            "id": "cash_only",
            "name": "全款",
            "enabled": True,
            "financing_type": "cash_only",
            "total_months": 1,
            "interest_free_months": 0,
            "later_annual_rate": 0.0,
            "min_down_payment_ratio": 1.0,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": False,
            "prepayment_allowed_after_month": 1,
            "prepayment_policy_note": "全款购车不形成车贷，也不存在提前还本。",
            "notes": "交易当月一次性支付车价，后续只保留保险、保养、停车、电费等持有成本。",
        },
        {
            "id": "three_year_two_year_subsidy",
            "name": "三年前两年贴息",
            "enabled": True,
            "financing_type": "dealer_subsidy",
            "total_months": 36,
            "interest_free_months": 24,
            "later_annual_rate": 0.0199,
            "min_down_payment_ratio": 0.30,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "通常需满足合同约定期数后提前还本；贴息期内提前还本可能影响补贴资格。",
            "notes": "合同仍按全期等额本息计息，前两年由厂家或经销商补贴部分利息。",
        },
        {
            "id": "twenty_down_two_year_subsidy",
            "name": "最低20%首付两年贴息",
            "enabled": True,
            "financing_type": "dealer_subsidy",
            "total_months": 60,
            "interest_free_months": 24,
            "later_annual_rate": 0.0249,
            "min_down_payment_ratio": 0.20,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "最低首付换来更高贷款本金，提前还本需按合同约定期数和违约金条款判断。",
            "notes": "适合比较低首付保现金方案；贴息来自厂家或经销商补贴，不改变贷款余额推演。",
        },
        {
            "id": "zero_down_five_year_low_rate",
            "name": "0首付五年低息",
            "enabled": True,
            "financing_type": "bank_loan",
            "total_months": 60,
            "interest_free_months": 0,
            "later_annual_rate": 0.029,
            "min_down_payment_ratio": 0.0,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "低息方案是否允许提前还本、是否收违约金要以具体合同为准。",
            "notes": "适合比较极低首付对买房现金池的影响；家庭承担合同全期利息。",
        },
    ]


def clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def strip_nested_vehicle_candidates(vehicle: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(vehicle)
    cleaned["candidate_vehicles"] = []
    return cleaned


def fill_vehicle_timing_defaults(vehicle: dict[str, Any], index: int) -> None:
    vehicle.setdefault("planning_sequence", index + 1)
    vehicle.setdefault("purchase_timing_mode", "auto_sequence")
    vehicle.setdefault("after_previous_event_delay_months", 0)
    vehicle.setdefault("manual_purchase_delay_months", max(0, safe_int(vehicle.get("purchase_delay_months"), 0)))
    candidates = vehicle.get("candidate_vehicles")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate.setdefault("planning_sequence", safe_int(vehicle.get("planning_sequence"), index + 1))
            candidate.setdefault("purchase_timing_mode", vehicle.get("purchase_timing_mode") or "auto_sequence")
            candidate.setdefault("after_previous_event_delay_months", safe_int(vehicle.get("after_previous_event_delay_months"), 0))
            candidate.setdefault(
                "manual_purchase_delay_months",
                max(0, safe_int(candidate.get("purchase_delay_months") or vehicle.get("manual_purchase_delay_months"), 0)),
            )


def fill_vehicle_prepayment_defaults(vehicle: dict[str, Any]) -> None:
    vehicle.setdefault("loan_prepayment_enabled", False)
    vehicle.setdefault("loan_prepayment_start_month", 1)
    vehicle.setdefault("loan_prepayment_allowed_after_month", 12)
    vehicle.setdefault("loan_prepayment_monthly_amount", 0)
    vehicle.setdefault("loan_prepayment_strategy_type", "none")
    vehicle.setdefault("loan_prepayment_lump_sum_month", 0)
    vehicle.setdefault("loan_prepayment_lump_sum_amount", 0)
    if not bool(vehicle.get("loan_prepayment_enabled")):
        vehicle["loan_prepayment_strategy_type"] = "none"
        vehicle["loan_prepayment_monthly_amount"] = 0
        vehicle["loan_prepayment_lump_sum_month"] = 0
        vehicle["loan_prepayment_lump_sum_amount"] = 0
    elif str(vehicle.get("loan_prepayment_strategy_type") or "none") == "none":
        has_extra_payment = (
            safe_float(vehicle.get("loan_prepayment_monthly_amount")) > 0
            or safe_float(vehicle.get("loan_prepayment_lump_sum_amount")) > 0
        )
        if has_extra_payment:
            vehicle["loan_prepayment_strategy_type"] = "manual"
    candidates = vehicle.get("candidate_vehicles")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                fill_vehicle_prepayment_defaults(candidate)


def normalize_vehicle_financing_options(vehicle: dict[str, Any]) -> None:
    options = vehicle.get("financing_options")
    normalized: list[dict[str, Any]] = []
    if isinstance(options, list):
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            total_months = max(1, min(120, safe_int(option.get("total_months"), safe_int(vehicle.get("total_months"), 60))))
            interest_free_months = max(0, min(total_months, safe_int(option.get("interest_free_months"), 0)))
            min_ratio = clamp(safe_float(option.get("min_down_payment_ratio"), 0.10), 0.0, 1.0)
            max_ratio = clamp(safe_float(option.get("max_down_payment_ratio"), 1.0), min_ratio, 1.0)
            financing_type = str(option.get("financing_type") or ("dealer_subsidy" if interest_free_months > 0 else "standard"))
            if financing_type == "cash_only":
                total_months = 1
                interest_free_months = 0
                min_ratio = 1.0
                max_ratio = 1.0
            prepayment_allowed = financing_type != "cash_only" and bool(option.get("prepayment_allowed", True))
            normalized.append(
                {
                    **option,
                    "id": option.get("id") or f"financing_{index + 1}",
                    "name": option.get("name") or f"金融方案 {index + 1}",
                    "enabled": bool(option.get("enabled", True)),
                    "financing_type": financing_type,
                    "total_months": total_months,
                    "interest_free_months": interest_free_months,
                    "later_annual_rate": clamp(safe_float(option.get("later_annual_rate"), safe_float(vehicle.get("later_annual_rate"), 0.0199)), 0.0, 0.5),
                    "min_down_payment_ratio": min_ratio,
                    "max_down_payment_ratio": max_ratio,
                    "prepayment_allowed": prepayment_allowed,
                    "prepayment_allowed_after_month": (
                        max(1, min(total_months, safe_int(option.get("prepayment_allowed_after_month"), 12)))
                        if prepayment_allowed
                        else 1
                    ),
                    "prepayment_policy_note": option.get("prepayment_policy_note")
                    or ("提前还本规则以经销商或银行合同为准。" if prepayment_allowed else "该金融方案不形成或不允许提前还本。"),
                    "notes": option.get("notes") or "",
                }
            )
    if not normalized:
        normalized = default_vehicle_financing_options()
    vehicle["financing_options"] = normalized
    selected = next((option for option in normalized if option.get("enabled")), normalized[0])
    vehicle.setdefault("selected_financing_option_id", selected.get("id") or "")
    vehicle.setdefault("selected_financing_option_name", selected.get("name") or "")
    vehicle.setdefault("selected_financing_type", selected.get("financing_type") or "")
    vehicle.setdefault("selected_financing_min_down_payment_ratio", selected.get("min_down_payment_ratio", 0.0))
    vehicle.setdefault("selected_financing_max_down_payment_ratio", selected.get("max_down_payment_ratio", 1.0))
    vehicle.setdefault("selected_financing_prepayment_allowed", selected.get("prepayment_allowed", True))
    vehicle.setdefault("selected_financing_prepayment_policy_note", selected.get("prepayment_policy_note", ""))


def normalize_car_plan(data: dict[str, Any]) -> None:
    car_plan = data.setdefault("car_plan", {})
    if not isinstance(car_plan, dict):
        data["car_plan"] = {}
        return
    car_plan.setdefault("annual_maintenance_growth_rate", 0.03)
    car_plan.setdefault("annual_insurance_growth_rate", 0.02)

    existing = car_plan.get("vehicle_plans")
    vehicle_plans = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []

    for index, vehicle in enumerate(vehicle_plans):
        if not isinstance(vehicle, dict):
            continue
        candidates = vehicle.get("candidate_vehicles")
        has_explicit_candidate_list = isinstance(candidates, list)
        candidate_vehicles = [item for item in candidates if isinstance(item, dict)] if has_explicit_candidate_list else []
        if not has_explicit_candidate_list and bool(vehicle.get("enabled")) and safe_float(vehicle.get("total_price")) > 0:
            candidate_vehicles = [strip_nested_vehicle_candidates(vehicle)]
        for candidate in candidate_vehicles:
            candidate.setdefault("enabled", True)
            candidate.setdefault("selected_strategy_variant", "target")
            candidate.setdefault("candidate_vehicles", [])
            fill_vehicle_timing_defaults(candidate, index)
            fill_vehicle_prepayment_defaults(candidate)
            normalize_vehicle_financing_options(candidate)
        vehicle["candidate_vehicles"] = candidate_vehicles
        fill_vehicle_timing_defaults(vehicle, index)
        fill_vehicle_prepayment_defaults(vehicle)
        normalize_vehicle_financing_options(vehicle)

    car_plan["vehicle_plans"] = vehicle_plans
    car_plan["enabled"] = any(
        bool(item.get("enabled")) and safe_float(item.get("total_price")) > 0
        for item in vehicle_plans
        if isinstance(item, dict)
    )


def retirement_category_from_age(age: int, index: int) -> str:
    if age <= 55 and index != 0:
        return "female_50"
    if age <= 58 and index != 0:
        return "female_55"
    return "male_60"


def default_retirement_category_for_member_sex(sex: str, index: int) -> str:
    if sex == "male":
        return "male_60"
    if sex == "female":
        return "female_55"
    return retirement_category_from_age(63 if index == 0 else 58, index)


def policy_retirement_age(category: str) -> int:
    if category == "female_50":
        return 55
    if category == "female_55":
        return 58
    return 63


def normalize_members_and_career_shock(data: dict[str, Any]) -> None:
    members = data.get("members")
    if not isinstance(members, list):
        data["members"] = []
        members = data["members"]

    household_balance = max(0.0, safe_float(data.get("provident_fund_balance")))
    member_balance_total = sum(
        max(0.0, safe_float(member.get("provident_fund_balance")))
        for member in members
        if isinstance(member, dict)
    )
    if household_balance > 0 and member_balance_total <= 0 and members:
        weights: list[float] = []
        for member in members:
            if not isinstance(member, dict):
                weights.append(0.0)
                continue
            stages = member.get("income_stages")
            first_stage = stages[0] if isinstance(stages, list) and stages and isinstance(stages[0], dict) else {}
            weights.append(max(0.0, safe_float(first_stage.get("monthly_housing_fund")) or safe_float(member.get("monthly_housing_fund"))))
        if sum(weights) <= 0:
            weights = [1.0 for _ in members]
        total_weight = sum(weights) or float(len(members))
        for index, member in enumerate(members):
            if isinstance(member, dict):
                member["provident_fund_balance"] = round(household_balance * weights[index] / total_weight, 2)

    data.pop("personal_pension_accounts", None)

    career_shock = data.setdefault("career_shock", {})
    if not isinstance(career_shock, dict):
        career_shock = {}
        data["career_shock"] = career_shock

    existing_settings = career_shock.get("member_settings")
    existing_by_name: dict[str, dict[str, Any]] = {}
    if isinstance(existing_settings, list):
        for item in existing_settings:
            if isinstance(item, dict):
                existing_by_name[str(item.get("member_name") or "")] = item
    next_settings: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            continue
        name = str(member.get("name") or f"成员 {index + 1}")
        member["sex"] = str(member.get("sex") or "unspecified")
        member.setdefault("birth_month", "")
        member.setdefault("family_join_month", "2026-07")
        member.setdefault("current_age", 30)
        member["retirement_category"] = normalize_retirement_category_for_sex(
            str(member.get("retirement_category") or ""),
            str(member.get("sex") or "unspecified"),
            default_retirement_category_for_member_sex(str(member.get("sex") or "unspecified"), index),
        )
        member.setdefault("social_security_months", 0)
        member.setdefault("income_tax_months", 0)
        member.setdefault("existing_home_count", 0)
        member.setdefault("existing_mortgage_count", 0)
        member.setdefault("initial_cash_balance", 0)
        member.setdefault("initial_investments", 0)
        member.setdefault("initial_other_asset_value", 0)
        member.setdefault("initial_other_debt_balance", 0)
        member.setdefault("provident_account_enabled", True)
        member.setdefault("provident_account_open_month", member.get("family_join_month") or "2026-07")
        member.setdefault("pension_account_balance", 0)
        member.setdefault("pension_account_enabled", True)
        member.setdefault("pension_account_open_month", member.get("family_join_month") or "2026-07")
        member.setdefault("medical_account_balance", 0)
        member.setdefault("medical_account_enabled", True)
        member.setdefault("medical_account_open_month", member.get("family_join_month") or "2026-07")
        member.setdefault("personal_pension_account_enabled", True)
        member.setdefault("personal_pension_account_balance", 0)
        member.setdefault("personal_pension_open_mode", "auto_tax_optimal")
        member.setdefault("personal_pension_account_open_month", "")
        member.setdefault("personal_pension_contribution_mode", "auto_tax_optimal")
        member.setdefault("personal_pension_monthly_contribution", 0)
        member.setdefault("personal_pension_annual_contribution_target", 0)
        member.setdefault("personal_pension_contribution_month", 12)
        member.setdefault("personal_pension_contribution_start_month", "")
        member.setdefault("personal_pension_contribution_end_month", None)
        member.setdefault("personal_pension_annual_return", 0.025)
        if not bool(member.get("personal_pension_account_enabled")):
            member["personal_pension_open_mode"] = "none"
            member["personal_pension_contribution_mode"] = "none"
        elif not member.get("personal_pension_open_mode") or str(member.get("personal_pension_open_mode")) == "none":
            member["personal_pension_open_mode"] = "auto_tax_optimal"
        elif not member.get("personal_pension_contribution_mode") or str(member.get("personal_pension_contribution_mode")) == "none":
            member["personal_pension_contribution_mode"] = "auto_tax_optimal"
        member_center = str(member.pop("provident_account_management_center", "") or "").strip().lower()
        default_stage_center = (
            "national"
            if member_center in {"national", "central_state", "guoguan", "state"}
            else "beijing_municipal"
        )
        if "income_stages" not in member:
            member["income_stages"] = [
                {
                    "name": "当前收入",
                    "stage_kind": "salary",
                    "start_date": member.get("employment_start_date") or "2026-07-01",
                    "end_date": None,
                    "monthly_salary_gross": safe_float(member.get("monthly_salary_gross")),
                    "annual_bonus": safe_float(member.get("annual_bonus")),
                    "annual_bonus_payout_mode": member.get("annual_bonus_payout_mode") or "lump_sum",
                    "annual_bonus_payout_month": 4,
                    "monthly_freelance_income": 0,
                    "monthly_non_taxable_income": safe_float(member.get("monthly_non_taxable_income")),
                    "monthly_extra_cash_expense": safe_float(member.get("monthly_extra_cash_expense")),
                    "monthly_social_insurance": safe_float(member.get("monthly_social_insurance")),
                    "monthly_housing_fund": safe_float(member.get("monthly_housing_fund")),
                    "housing_fund_personal_rate": safe_float(member.get("housing_fund_personal_rate"), 0.12),
                    "housing_fund_employer_rate": safe_float(member.get("housing_fund_employer_rate"), 0.12),
                    "monthly_special_additional_deduction": safe_float(member.get("monthly_special_additional_deduction")),
                    "other_annual_deductions": safe_float(member.get("other_annual_deductions")),
                    "other_annual_taxable_income": safe_float(member.get("other_annual_taxable_income")),
                    "bonus_tax_method": member.get("bonus_tax_method") or "best",
                    "payroll_contributions_enabled": True,
                }
            ]
        elif not isinstance(member.get("income_stages"), list):
            member["income_stages"] = []
        for stage in member.get("income_stages", []):
            if isinstance(stage, dict):
                stage.setdefault("stage_kind", "salary")
                stage.setdefault("annual_bonus_payout_mode", "lump_sum")
                stage.setdefault("annual_bonus_payout_month", 4)
                center = str(stage.get("provident_account_management_center") or default_stage_center).strip().lower()
                stage["provident_account_management_center"] = (
                    "national"
                    if center in {"national", "central_state", "guoguan", "state"}
                    else "beijing_municipal"
                )
                stage.setdefault("monthly_freelance_income", 0)
        existing = existing_by_name.get(name, {})
        member_enabled = bool(existing.get("enabled")) if existing else False
        next_settings.append(
            {
                "member_name": name,
                "enabled": member_enabled,
                "layoff_age": safe_int(existing.get("layoff_age") if existing else 35, 35),
                "retirement_age": policy_retirement_age(str(member.get("retirement_category") or "male_60")),
                "freelance_income_monthly": safe_float(existing.get("freelance_income_monthly") if existing else 0),
                "pension_monthly": safe_float(existing.get("pension_monthly") if existing else 0),
                "auto_pension_monthly": bool(existing.get("auto_pension_monthly", True)) if existing else True,
            }
        )

    career_shock["enabled"] = any(bool(item.get("enabled")) for item in next_settings)
    career_shock["member_settings"] = next_settings
    career_shock.setdefault("auto_flexible_housing_fund", True)
    career_shock.pop("auto_pension_income", None)
    career_shock.setdefault("self_housing_fund_monthly", 0)


def normalize_household(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("family_down_payment_support_mode", "provident")
    data.setdefault("family_savings_support_amount", 0)
    data.setdefault("investment_buy_fee_rate", 0.0015)
    data.setdefault("investment_sell_fee_rate", 0.005)
    data.setdefault("investment_taxable_return_ratio", 0)
    data.setdefault("investment_return_tax_rate", 0)
    if not isinstance(data.get("scheduled_expenses"), list):
        data["scheduled_expenses"] = []
    data.pop("household_expense_stages", None)
    if not isinstance(data.get("daily_expense_stages"), list) or not data.get("daily_expense_stages"):
        data["daily_expense_stages"] = [
            {
                "name": "日常支出阶段",
                "start_month": "2026-07",
                "end_month": None,
                "base_living_expense": safe_float(data.get("monthly_expense")),
            }
        ]
    if not isinstance(data.get("rent_expense_stages"), list) or not data.get("rent_expense_stages"):
        rent_amount = safe_float(data.get("monthly_rent_from_housing_fund"))
        data["rent_expense_stages"] = [
            {
                "name": "租房支出阶段",
                "start_month": "2026-07",
                "end_month": None,
                "rent_amount": rent_amount,
                "broker_fee_months": 1,
                "broker_fee_amount": None,
                "service_fee_first_year_rate": 0.09,
                "service_fee_later_year_rate": 0.06,
                "rent_payment_mode": "provident" if rent_amount > 0 else "cash",
                "rent_payment_frequency": "monthly",
            }
        ]
    for stage in data.get("rent_expense_stages", []):
        if isinstance(stage, dict):
            stage["rent_payment_mode"] = "provident" if stage.get("rent_payment_mode") == "provident" else "cash"
            stage["rent_payment_frequency"] = "quarterly" if stage.get("rent_payment_frequency") == "quarterly" else "monthly"
            stage.setdefault("broker_fee_months", 1)
            stage.setdefault("broker_fee_amount", None)
            stage.setdefault("service_fee_first_year_rate", 0.09)
            stage.setdefault("service_fee_later_year_rate", 0.06)
    monthly_debt_payment = safe_float(data.get("monthly_debt_payment"))
    if monthly_debt_payment > 0:
        scheduled = data.setdefault("scheduled_expenses", [])
        if isinstance(scheduled, list) and not any(
            isinstance(item, dict)
            and str(item.get("name") or "") == "其他固定还款"
            and safe_float(item.get("monthly_amount")) == monthly_debt_payment
            for item in scheduled
        ):
            scheduled.append(
                {
                    "name": "其他固定还款",
                    "monthly_amount": monthly_debt_payment,
                    "frequency": "monthly",
                    "one_time_timing_mode": "fixed_month",
                    "annual_occurrence_month": 1,
                    "start_month": "2026-07",
                    "end_month": None,
                    "tax_deductible_elderly_care": False,
                    "notes": "由每月固定还款字段转入通用计划支出。",
                }
            )
        data["monthly_debt_payment"] = 0
    data.setdefault("scheduled_expenses", [])
    for expense in data["scheduled_expenses"]:
        if isinstance(expense, dict):
            frequency = str(expense.get("frequency") or "monthly")
            expense["frequency"] = frequency if frequency in {"monthly", "annual_once", "one_time"} else "monthly"
            timing_mode = str(expense.get("one_time_timing_mode") or "fixed_month")
            expense["one_time_timing_mode"] = "flexible_range" if timing_mode == "flexible_range" else "fixed_month"
            default_month = safe_int(str(expense.get("start_month") or "2026-01").split("-")[-1], 1)
            expense.setdefault("annual_occurrence_month", max(1, min(12, default_month)))
    data.setdefault("phased_loans", [])
    for loan in data["phased_loans"]:
        if isinstance(loan, dict):
            loan.setdefault("prepayment_mode", "none")
            loan.setdefault("prepayment_start_month", 1)
            loan.setdefault("prepayment_allowed_after_month", 1)
            loan.setdefault("prepayment_monthly_amount", 0)
    data.setdefault("elderly_dependents", [])
    data.setdefault("child_plans", [])
    for child in data["child_plans"]:
        if isinstance(child, dict):
            child.setdefault("expense_strategy_mode", "balanced")
            child.setdefault("planned_birth_month", "")
            child.setdefault("planned_birth_start_month", "")
            child.setdefault("planned_birth_end_month", "")
            child.setdefault("preparation_months_before_birth", 6)
            child.setdefault("pregnancy_months_before_birth", 9)
            child.setdefault("monthly_preparation_cost", 1000)
            child.setdefault("monthly_pregnancy_cost", 2000)
            child.setdefault("birth_medical_cost", 20000)
            child.setdefault("postpartum_recovery_cost", 30000)
            child.setdefault("initial_baby_supplies_cost", 15000)
            child.setdefault("kindergarten_entry_cost", 0)
            child.setdefault("primary_school_entry_cost", 0)
            child.setdefault("higher_education_entry_cost", 0)
    data.setdefault("special_deductions", [])
    data.setdefault("investment_tax_profile", {})
    data.setdefault("property_goals", [])
    normalize_car_plan(data)
    normalize_members_and_career_shock(data)
    normalized = HouseholdData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_scenario(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("selected_purchase_plan_variant", "")
    data.setdefault("enabled", True)
    data.setdefault("purchase_sequence", 1)
    data.setdefault("purchase_planning_mode", "after_previous_purchase")
    data.setdefault("after_previous_purchase_delay_months", 0)
    data.setdefault("investment_withdrawal_mode", "auto")
    data.setdefault("investment_min_balance_after_purchase", 0)
    commercial_prepayment_mode = str(
        data.get("commercial_prepayment_mode")
        or ("manual" if bool(data.get("commercial_prepayment_enabled")) else "auto")
    )
    if commercial_prepayment_mode not in {"auto", "manual", "none"}:
        commercial_prepayment_mode = "auto"
    data["commercial_prepayment_mode"] = commercial_prepayment_mode
    data["commercial_prepayment_enabled"] = commercial_prepayment_mode == "manual"
    data.setdefault("commercial_prepayment_start_month", 1)
    data.setdefault("commercial_prepayment_allowed_after_month", 12)
    data.setdefault("commercial_prepayment_monthly_amount", 0)
    if commercial_prepayment_mode == "none":
        data["commercial_prepayment_monthly_amount"] = 0
    data.setdefault("provident_account_repayment_strategy", "auto")
    data.setdefault("seller_tax_pass_through_enabled", False)
    data.setdefault("seller_tax_pass_through_rate", 0)
    data.setdefault("seller_tax_pass_through_amount", 0)
    if "二手" not in str(data.get("property_type") or ""):
        data["building_age_years"] = 0
        data["building_structure"] = "unknown"
        data["is_old_community_renovated"] = False
        data["remaining_land_use_years"] = None
    normalized = ScenarioData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_rule_pack(data: dict[str, Any]) -> dict[str, Any]:
    defaults = RulePackData().model_dump(mode="json")
    params = data.get("params")
    merged_params = defaults["params"] | (params if isinstance(params, dict) else {})
    if safe_float(merged_params.get("second_home_provident_min_down_payment_ratio")) < 0.30:
        merged_params["second_home_provident_min_down_payment_ratio"] = 0.30
    data = defaults | data
    data["params"] = merged_params
    normalized = RulePackData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized


def normalize_market_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    normalized = MarketSnapshotData.model_validate(data).model_dump(mode="json")
    normalized["schema_version"] = CURRENT_SCHEMA_VERSION
    return normalized
