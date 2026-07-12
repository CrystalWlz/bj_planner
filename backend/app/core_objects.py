from __future__ import annotations

import json
import uuid
from typing import Any

from .core_object_concepts import calibration_target_label
from .schemas import CoreObjectData


def core_object_record_id(household_id: str | None, object_type: str, source: str, reference: str, category: str) -> str:
    raw = json.dumps(
        {
            "kind": "core_object",
            "household_id": household_id or "",
            "object_type": object_type,
            "source": source,
            "reference": reference,
            "category": category,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex


def derive_core_objects_for_household(household_id: str, household: dict[str, Any]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    objects.append(
        _core_object_payload(
            object_type="account",
            category="cash",
            name="现金账户",
            household_id=household_id,
            source="household",
            reference_id="cash_account_balance",
            current_balance=float(household.get("cash_account_balance") or 0),
        )
    )
    objects.append(
        _core_object_payload(
            object_type="account",
            category="investment",
            name="投资账户",
            household_id=household_id,
            source="household",
            reference_id="investments",
            current_balance=float(household.get("investments") or 0),
            monthly_flow=float(household.get("monthly_investment_amount") or 0),
        )
    )
    for index, member in enumerate(household.get("members") or []):
        if not isinstance(member, dict):
            continue
        member_name = str(member.get("name") or f"成员 {index + 1}")
        if bool(member.get("provident_account_enabled", True)):
            objects.append(
                _core_object_payload(
                    object_type="account",
                    category="provident",
                    name=f"{member_name}公积金账户",
                    household_id=household_id,
                    source="member",
                    reference_id=f"members.{index}.provident_fund_balance",
                    member_name=member_name,
                    current_balance=float(member.get("provident_fund_balance") or 0),
                    metadata={"management_center": member.get("provident_account_management_center", "")},
                )
            )
        if bool(member.get("pension_account_enabled", True)):
            objects.append(
                _core_object_payload(
                    object_type="account",
                    category="pension",
                    name=f"{member_name}基本养老个人账户",
                    household_id=household_id,
                    source="member",
                    reference_id=f"members.{index}.pension_account_balance",
                    member_name=member_name,
                    current_balance=float(member.get("pension_account_balance") or 0),
                )
            )
        if bool(member.get("medical_account_enabled", True)):
            objects.append(
                _core_object_payload(
                    object_type="account",
                    category="medical",
                    name=f"{member_name}医保个人账户",
                    household_id=household_id,
                    source="member",
                    reference_id=f"members.{index}.medical_account_balance",
                    member_name=member_name,
                    current_balance=float(member.get("medical_account_balance") or 0),
                )
            )
        if bool(member.get("personal_pension_account_enabled", False)):
            objects.append(
                _core_object_payload(
                    object_type="account",
                    category="personal_pension",
                    name=f"{member_name}个人养老金账户",
                    household_id=household_id,
                    source="member",
                    reference_id=f"members.{index}.personal_pension_balance",
                    member_name=member_name,
                    current_balance=float(member.get("personal_pension_balance") or 0),
                    metadata={
                        "contribution_mode": member.get("personal_pension_contribution_mode", ""),
                        "open_mode": member.get("personal_pension_open_mode", ""),
                    },
                )
            )
    for index, loan in enumerate(household.get("phased_loans") or []):
        if not isinstance(loan, dict):
            continue
        loan_type = str(loan.get("loan_type") or "other")
        category = _loan_core_object_category(loan_type)
        objects.append(
            _core_object_payload(
                object_type="loan",
                category=category,
                name=str(loan.get("name") or f"已有贷款 {index + 1}"),
                household_id=household_id,
                source="loan",
                reference_id=f"phased_loans.{index}",
                member_name=str(loan.get("borrower") or ""),
                current_balance=float(loan.get("principal") or 0),
                annual_rate=float(loan.get("annual_rate") or 0),
                metadata={
                    "repayment_method": loan.get("repayment_method", ""),
                    "remaining_months": loan.get("remaining_months", 0),
                },
            )
        )
    for index, calibration in enumerate(household.get("account_calibrations") or []):
        if not isinstance(calibration, dict) or not bool(calibration.get("enabled", True)):
            continue
        target = str(calibration.get("target") or "cash")
        reference_name = str(calibration.get("reference_name") or "")
        name = reference_name or calibration_target_label(target)
        month = str(calibration.get("month") or "")
        objects.append(
            _core_object_payload(
                object_type="adjustment",
                category="manual_adjustment",
                name=f"{name}校准",
                household_id=household_id,
                source="manual",
                reference_id=f"account_calibrations.{index}",
                member_name=str(calibration.get("member_name") or ""),
                current_balance=float(calibration.get("amount") or 0),
                metadata={
                    "target": target,
                    "target_label": calibration_target_label(target),
                    "month": month,
                    "calibration_scope": calibration.get("calibration_scope", "account"),
                    "source_id": calibration.get("source_id", ""),
                    "source_category": calibration.get("source_category", ""),
                    "source_title": calibration.get("source_title", ""),
                    "reference_name": calibration.get("reference_name", ""),
                    "note": calibration.get("note", ""),
                },
            )
        )
    return objects


def derive_core_objects_for_planning_goals(
    household_id: str,
    goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    processed_home_groups: set[int] = set()
    for goal in goals:
        data = goal.get("data") if isinstance(goal.get("data"), dict) else {}
        timing_mode = str(data.get("timing_mode") or "")
        if not data or not bool(data.get("enabled", True)) or timing_mode == "not_planned":
            continue
        target = data.get("target_params") if isinstance(data.get("target_params"), dict) else {}
        goal_type = str(goal.get("goal_type") or data.get("goal_type") or "")
        if goal_type == "home":
            priority = max(1, int(data.get("priority") or 1))
            if priority in processed_home_groups:
                continue
            processed_home_groups.add(priority)
            home_candidates = [
                candidate
                for candidate in goals
                if isinstance(candidate.get("data"), dict)
                and str(candidate.get("goal_type") or candidate["data"].get("goal_type") or "") == "home"
                and bool(candidate["data"].get("enabled", True))
                and str(candidate["data"].get("timing_mode") or "") != "not_planned"
                and max(1, int(candidate["data"].get("priority") or 1)) == priority
            ]
            goal_id = str(goal.get("id") or "")
            candidate_ids = [str(candidate.get("id") or "") for candidate in home_candidates]
            candidate_names = [str(candidate["data"].get("name") or "候选房源") for candidate in home_candidates]
            candidate_prices = [
                max(0.0, float((candidate["data"].get("target_params") or {}).get("total_price") or 0))
                for candidate in home_candidates
            ]
            demand_name = (
                ("第一套购房需求" if priority == 1 else f"第 {priority} 套购房需求")
                if len(home_candidates) > 1
                else str(data.get("name") or target.get("name") or "目标房产")
            )
            group_metadata = {
                "planning_group_id": goal_id,
                "planning_group_name": demand_name,
                "candidate_count": len(home_candidates),
                "candidate_goal_ids": candidate_ids,
                "candidate_names": candidate_names,
                "candidate_price_min": min(candidate_prices, default=0.0),
                "candidate_price_max": max(candidate_prices, default=0.0),
            }
            objects.append(
                _core_object_payload(
                    object_type="asset",
                    category="property_asset",
                    name=demand_name,
                    household_id=household_id,
                    source="goal",
                    reference_id=goal_id,
                    owner_key=goal_id,
                    current_balance=float(target.get("total_price") or 0),
                    metadata={
                        "goal_type": "home",
                        "priority": data.get("priority", 1),
                        "timing_mode": data.get("timing_mode", ""),
                        "planning_window_start_month": data.get("planning_window_start_month", ""),
                        "planning_window_end_month": data.get("planning_window_end_month", ""),
                        **group_metadata,
                    },
                )
            )
            objects.extend(
                _home_goal_planned_loan_objects(
                    household_id,
                    goal_id,
                    data,
                    target,
                    planning_group_metadata=group_metadata,
                )
            )
        elif goal_type == "vehicle":
            goal_id = str(goal.get("id") or "")
            objects.append(
                _core_object_payload(
                    object_type="asset",
                    category="vehicle_asset",
                    name=str(data.get("name") or target.get("name") or "目标车辆"),
                    household_id=household_id,
                    source="goal",
                    reference_id=goal_id,
                    owner_key=goal_id,
                    current_balance=float(target.get("total_price") or 0),
                    metadata={
                        "goal_type": "vehicle",
                        "priority": data.get("priority", 1),
                        "timing_mode": data.get("timing_mode", ""),
                        "planning_window_start_month": data.get("planning_window_start_month", ""),
                        "planning_window_end_month": data.get("planning_window_end_month", ""),
                        "energy_type": target.get("energy_type", ""),
                    },
                )
            )
            objects.extend(_vehicle_goal_planned_loan_objects(household_id, goal_id, data, target))
        elif goal_type == "child":
            objects.append(
                _core_object_payload(
                    object_type="asset",
                    category="child_goal",
                    name=str(data.get("name") or target.get("name") or "子女目标"),
                    household_id=household_id,
                    source="goal",
                    reference_id=str(goal.get("id") or ""),
                    owner_key=str(goal.get("id") or ""),
                    current_balance=_estimate_child_goal_budget(target),
                    metadata={
                        "goal_type": "child",
                        "priority": data.get("priority", 30),
                        "timing_mode": data.get("timing_mode", ""),
                        "planning_window_start_month": data.get("planning_window_start_month", ""),
                        "planning_window_end_month": data.get("planning_window_end_month", ""),
                    },
                )
            )
        elif goal_type in {"renovation", "other"}:
            objects.append(
                _core_object_payload(
                    object_type="asset",
                    category="planning_goal",
                    name=str(data.get("name") or target.get("name") or "规划目标"),
                    household_id=household_id,
                    source="goal",
                    reference_id=str(goal.get("id") or ""),
                    owner_key=str(goal.get("id") or ""),
                    current_balance=_estimate_generic_goal_budget(target),
                    metadata={
                        "goal_type": goal_type,
                        "priority": data.get("priority", 50),
                        "timing_mode": data.get("timing_mode", ""),
                        "planning_window_start_month": data.get("planning_window_start_month", ""),
                        "planning_window_end_month": data.get("planning_window_end_month", ""),
                    },
                )
            )
    return objects


def _home_goal_planned_loan_objects(
    household_id: str,
    goal_id: str,
    data: dict[str, Any],
    target: dict[str, Any],
    *,
    planning_group_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    goal_name = str(data.get("name") or target.get("name") or "目标房产")
    commercial_loan = max(0.0, float(target.get("commercial_loan_amount") or 0))
    provident_loan = max(0.0, float(target.get("provident_loan_amount") or 0))
    total_price = max(0.0, float(target.get("total_price") or 0))
    down_payment = max(0.0, float(target.get("down_payment_amount") or 0))
    if commercial_loan <= 0 and provident_loan <= 0 and total_price > 0 and down_payment > 0:
        commercial_loan = max(0.0, total_price - down_payment)

    if provident_loan > 0:
        objects.append(
            _core_object_payload(
                object_type="loan",
                category="mortgage",
                name=f"{goal_name}公积金贷款（规划）",
                household_id=household_id,
                source="goal",
                reference_id=f"{goal_id}.provident_loan",
                owner_key=goal_id,
                current_balance=provident_loan,
                metadata={
                    "goal_type": "home",
                    "loan_subtype": "provident",
                    "planned": True,
                    "rate_source": "policy_pack",
                    "rate_note": "公积金贷款利率由城市政策包按首套/二套和贷款年限返回，核心对象只记录规划负债结构。",
                    "repayment_method": target.get("provident_repayment_method") or target.get("repayment_method") or "",
                    "loan_years": target.get("loan_years", 0),
                    "timing_mode": data.get("timing_mode", ""),
                    **(planning_group_metadata or {}),
                },
            )
        )
    if commercial_loan > 0:
        objects.append(
            _core_object_payload(
                object_type="loan",
                category="mortgage",
                name=f"{goal_name}商业贷款（规划）",
                household_id=household_id,
                source="goal",
                reference_id=f"{goal_id}.commercial_loan",
                owner_key=goal_id,
                current_balance=commercial_loan,
                annual_rate=float(target.get("commercial_rate") or 0),
                metadata={
                    "goal_type": "home",
                    "loan_subtype": "commercial",
                    "planned": True,
                    "rate_source": "market_quote",
                    "repayment_method": target.get("commercial_repayment_method") or target.get("repayment_method") or "",
                    "loan_years": target.get("loan_years", 0),
                    "timing_mode": data.get("timing_mode", ""),
                    **(planning_group_metadata or {}),
                },
            )
        )
    return objects


def _vehicle_goal_planned_loan_objects(
    household_id: str,
    goal_id: str,
    data: dict[str, Any],
    target: dict[str, Any],
) -> list[dict[str, Any]]:
    total_price = max(0.0, float(target.get("total_price") or 0))
    explicit_down_payment = max(0.0, float(target.get("down_payment") or 0))
    down_payment_ratio = min(1.0, max(0.0, float(target.get("down_payment_ratio") or 0)))
    down_payment = explicit_down_payment if explicit_down_payment > 0 else total_price * down_payment_ratio
    loan_principal = max(0.0, total_price - down_payment)
    if loan_principal <= 0:
        return []
    goal_name = str(data.get("name") or target.get("name") or "目标车辆")
    return [
        _core_object_payload(
            object_type="loan",
            category="car_loan",
            name=f"{goal_name}车贷（规划）",
            household_id=household_id,
            source="goal",
            reference_id=f"{goal_id}.vehicle_loan",
            owner_key=goal_id,
            current_balance=loan_principal,
            annual_rate=float(target.get("later_annual_rate") or 0),
            metadata={
                "goal_type": "vehicle",
                "planned": True,
                "rate_source": "dealer_financing_option",
                "repayment_method": "equal_installment",
                "total_months": target.get("total_months", 0),
                "financing_option_id": target.get("selected_financing_option_id", ""),
                "financing_option_name": target.get("selected_financing_option_name", ""),
                "timing_mode": data.get("timing_mode", ""),
            },
        )
    ]


def _estimate_generic_goal_budget(target: dict[str, Any]) -> float:
    for key in ["estimated_cost", "total_price", "budget", "amount", "renovation_cost"]:
        value = target.get(key)
        if value is not None:
            return max(0.0, float(value or 0))
    return 0.0


def _estimate_child_goal_budget(target: dict[str, Any]) -> float:
    one_time_keys = [
        "birth_medical_cost",
        "postpartum_recovery_cost",
        "initial_baby_supplies_cost",
        "kindergarten_entry_cost",
        "primary_school_entry_cost",
        "higher_education_entry_cost",
    ]
    monthly_keys = [
        "monthly_preparation_cost",
        "monthly_pregnancy_cost",
        "monthly_childcare_cost_before_kindergarten",
        "monthly_kindergarten_cost",
        "monthly_primary_secondary_cost",
        "monthly_higher_education_cost",
    ]
    one_time_total = sum(float(target.get(key) or 0) for key in one_time_keys)
    annualized_monthly_total = sum(float(target.get(key) or 0) for key in monthly_keys) * 12
    return one_time_total + annualized_monthly_total


def _core_object_payload(
    *,
    object_type: str,
    category: str,
    name: str,
    household_id: str | None,
    source: str,
    reference_id: str,
    owner_key: str = "",
    member_name: str = "",
    current_balance: float = 0.0,
    monthly_flow: float = 0.0,
    annual_rate: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return CoreObjectData(
        object_type=object_type,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        name=name,
        member_name=member_name,
        owner_key=owner_key or member_name or household_id or "",
        reference_id=reference_id,
        source=source,  # type: ignore[arg-type]
        current_balance=round(float(current_balance or 0), 2),
        monthly_flow=round(float(monthly_flow or 0), 2),
        annual_rate=float(annual_rate or 0),
        metadata=metadata or {},
    ).model_dump(mode="json")


def _loan_core_object_category(loan_type: str) -> str:
    if loan_type == "education":
        return "education"
    if loan_type == "car":
        return "car_loan"
    if loan_type == "mortgage":
        return "mortgage"
    if loan_type == "consumer":
        return "consumer"
    return "other"
