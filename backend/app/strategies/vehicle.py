from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from ..domain.loans import (
    prepayment_investment_hurdle_rate,
    vehicle_loan_projection,
)
from ..domain.scoring import (
    cash_flow_score,
    clamp_score,
    prepayment_rate_spread_score,
    ratio_score,
    wait_score,
)
from ..domain.tax import clamp
from ..domain.time import format_year_month_tuple, month_after, month_distance, parse_year_month
from ..domain.vehicles import vehicle_update_month
from ..domain.vehicles import (
    estimate_car_operating_cost,
    vehicle_indicator_wait_months,
    vehicle_purchase_policy_amounts,
)
from ..schemas import (
    CarLoanSummary,
    CarPlanAnalysis,
    CarPlanData,
    CalculationContextGoalSnapshot,
    CalculationContextSnapshot,
    HouseholdData,
    PlanEventPoint,
    RulePackData,
    ScenarioData,
    VehicleFinancingOptionData,
    VehiclePlanData,
)

CarLoanCalculator = Callable[..., CarLoanSummary]
VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]
VEHICLE_POLICY_FIELD_NAMES = (
    "beijing_license_indicator_status",
    "beijing_indicator_expected_delay_months",
    "license_plate_rental_enabled",
    "license_plate_rental_upfront_fee",
    "license_plate_rental_term_months",
    "license_plate_rental_renewal_fee",
    "license_plate_rental_renewal_term_months",
    "license_plate_rental_after_term_mode",
    "beijing_family_indicator_score_enabled",
    "beijing_family_indicator_application_start_month",
    "beijing_family_indicator_applicants",
    "beijing_family_indicator_generations",
    "beijing_family_indicator_has_spouse",
    "beijing_family_indicator_main_points",
    "beijing_family_indicator_spouse_points",
    "beijing_family_indicator_other_applicant_count",
    "beijing_family_indicator_other_points_total",
    "beijing_family_indicator_application_years",
    "beijing_family_indicator_current_cutoff_score",
    "beijing_family_indicator_cutoff_score_annual_change",
    "beijing_family_indicator_last_config_year",
    "beijing_family_indicator_annual_quota",
)


def vehicle_policy_field_values(vehicle: VehiclePlanData) -> dict[str, object]:
    return {field: getattr(vehicle, field) for field in VEHICLE_POLICY_FIELD_NAMES}


@dataclass(frozen=True)
class VehiclePrepaymentChoice:
    enabled: bool
    strategy_type: str
    start_month: int
    allowed_after_month: int
    monthly_amount: float
    lump_sum_month: int
    lump_sum_amount: float
    total_extra_principal: float
    interest_saved: float
    net_benefit: float
    actual_payoff_months: int
    explanation: str


def _money_text(amount: float) -> str:
    if abs(amount) >= 10000:
        return f"{amount / 10000:.1f} 万"
    return f"{amount:.0f} 元"


def default_vehicle_financing_options() -> list[dict[str, object]]:
    return [
        {
            "id": "cash_only",
            "name": "全款",
            "financing_type": "cash_only",
            "total_months": 1,
            "interest_free_months": 0,
            "later_annual_rate": 0.0,
            "min_down_payment_ratio": 1.0,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": False,
            "prepayment_allowed_after_month": 1,
            "prepayment_policy_note": "全款购车不形成车贷，也不存在提前还本。",
        },
        {
            "id": "three_year_two_year_subsidy",
            "name": "三年前两年贴息",
            "financing_type": "dealer_subsidy",
            "total_months": 36,
            "interest_free_months": 24,
            "later_annual_rate": 0.0199,
            "min_down_payment_ratio": 0.30,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "通常需满足合同约定期数后提前还本；贴息期内提前还本可能影响补贴资格。",
        },
        {
            "id": "twenty_down_two_year_subsidy",
            "name": "最低20%首付两年贴息",
            "financing_type": "dealer_subsidy",
            "total_months": 60,
            "interest_free_months": 24,
            "later_annual_rate": 0.0249,
            "min_down_payment_ratio": 0.20,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "最低首付换来更高贷款本金，提前还本需按合同约定期数和违约金条款判断。",
        },
        {
            "id": "zero_down_five_year_low_rate",
            "name": "0首付五年低息",
            "financing_type": "bank_loan",
            "total_months": 60,
            "interest_free_months": 0,
            "later_annual_rate": 0.029,
            "min_down_payment_ratio": 0.0,
            "max_down_payment_ratio": 1.0,
            "prepayment_allowed": True,
            "prepayment_allowed_after_month": 12,
            "prepayment_policy_note": "低息方案是否允许提前还本、是否收违约金要以具体合同为准。",
        },
    ]


def vehicle_loan_states(
    plan: CarPlanData,
    *,
    calculate_car_loan: CarLoanCalculator,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[VehicleLoanState]:
    states: list[VehicleLoanState] = []
    for index, vehicle_plan in enumerate(
        vehicle_plans(
            plan,
            scenario=scenario,
            home_purchase_month=home_purchase_month,
            include_after_home=include_after_home,
            calculation_context=calculation_context,
        )
    ):
        loan = calculate_car_loan(vehicle_plan, rules=rules)
        purchase_month = (
            loan.months_to_down_payment
            if loan.months_to_down_payment is not None
            else vehicle_plan.purchase_delay_months
        ) if loan.enabled else None
        states.append((index, vehicle_plan, loan, purchase_month))
    return states


def aggregate_car_loan(
    plan: CarPlanData,
    *,
    calculate_car_loan: CarLoanCalculator,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    rules: RulePackData,
    calculation_context: CalculationContextSnapshot | None = None,
) -> CarLoanSummary:
    active_vehicle_plans = vehicle_plans(
        plan,
        scenario=scenario,
        home_purchase_month=home_purchase_month,
        include_after_home=include_after_home,
        calculation_context=calculation_context,
    )
    if not active_vehicle_plans:
        return calculate_car_loan(
            plan.model_copy(update={"enabled": False, "total_price": 0}),
            initial_cash=initial_cash,
            monthly_cash_savings_before_car=monthly_cash_savings_before_car,
            rules=rules,
        )
    loans = [
        calculate_car_loan(
            vehicle_plan,
            initial_cash=initial_cash,
            monthly_cash_savings_before_car=monthly_cash_savings_before_car,
            rules=rules,
        )
        for vehicle_plan in active_vehicle_plans
    ]
    first = loans[0]
    return first.model_copy(
        update={
            "enabled": any(loan.enabled for loan in loans),
            "total_price": round(sum(loan.total_price for loan in loans), 2),
            "down_payment": round(sum(loan.down_payment for loan in loans), 2),
            "purchase_tax": round(sum(loan.purchase_tax for loan in loans), 2),
            "purchase_tax_relief": round(sum(loan.purchase_tax_relief for loan in loans), 2),
            "annual_vehicle_vessel_tax": round(sum(loan.annual_vehicle_vessel_tax for loan in loans), 2),
            "license_plate_rental_initial_fee": round(sum(loan.license_plate_rental_initial_fee for loan in loans), 2),
            "beijing_family_indicator_score": round(sum(loan.beijing_family_indicator_score for loan in loans), 2),
            "beijing_family_indicator_estimated_wait_months": max(
                (
                    loan.beijing_family_indicator_estimated_wait_months
                    for loan in loans
                    if loan.beijing_family_indicator_estimated_wait_months is not None
                ),
                default=None,
            ),
            "loan_principal": round(sum(loan.loan_principal for loan in loans), 2),
            "current_monthly_payment": round(sum(loan.current_monthly_payment for loan in loans), 2),
            "total_interest": round(sum(loan.total_interest for loan in loans), 2),
            "monthly_energy_cost": round(sum(loan.monthly_energy_cost for loan in loans), 2),
            "monthly_insurance_cost": round(sum(loan.monthly_insurance_cost for loan in loans), 2),
            "monthly_maintenance_cost": round(sum(loan.monthly_maintenance_cost for loan in loans), 2),
            "monthly_parking_cost": round(sum(loan.monthly_parking_cost for loan in loans), 2),
            "monthly_cash_operating_cost": round(sum(loan.monthly_cash_operating_cost for loan in loans), 2),
            "monthly_depreciation_cost": round(sum(loan.monthly_depreciation_cost for loan in loans), 2),
            "monthly_total_ownership_cost": round(sum(loan.monthly_total_ownership_cost for loan in loans), 2),
            "policy_notes": [note for loan in loans for note in loan.policy_notes],
            "months_to_down_payment": min(
                (loan.months_to_down_payment for loan in loans if loan.months_to_down_payment is not None),
                default=None,
            ),
        }
    )


def scenario_purchase_sequence(scenario: ScenarioData | None) -> int:
    return max(1, scenario.purchase_sequence if scenario else 1)


def _current_home_goal(
    calculation_context: CalculationContextSnapshot | None,
) -> CalculationContextGoalSnapshot | None:
    if calculation_context is None:
        return None
    if calculation_context.current_goal_id:
        current = next(
            (goal for goal in calculation_context.planning_goals if goal.id == calculation_context.current_goal_id),
            None,
        )
        if current is not None and current.goal_type == "home":
            return current
    return next((goal for goal in calculation_context.planning_goals if goal.goal_type == "home"), None)


def _vehicle_goal_for_plan(
    vehicle: CarPlanData,
    calculation_context: CalculationContextSnapshot | None,
) -> CalculationContextGoalSnapshot | None:
    if calculation_context is None:
        return None
    goal_id = str(getattr(vehicle, "planning_goal_id", "") or "")
    if goal_id:
        matched = next((goal for goal in calculation_context.planning_goals if goal.id == goal_id), None)
        if matched is not None and matched.goal_type == "vehicle":
            return matched
    return next(
        (
            goal
            for goal in calculation_context.planning_goals
            if goal.goal_type == "vehicle" and (goal.name == vehicle.name or goal.priority == vehicle.planning_sequence)
        ),
        None,
    )


def planning_window_delay_months(window_month: str, *, as_of: date | None = None) -> int | None:
    parsed = parse_year_month(window_month)
    if parsed is None:
        return None
    current = as_of or date.today()
    return max(0, month_distance((current.year, current.month), parsed))


def vehicle_is_before_or_parallel_home(
    vehicle: CarPlanData,
    scenario: ScenarioData | None,
    *,
    calculation_context: CalculationContextSnapshot | None = None,
) -> bool:
    if scenario is None or vehicle.purchase_timing_mode in {"parallel", "manual_month"}:
        return True
    home_goal = _current_home_goal(calculation_context)
    vehicle_goal = _vehicle_goal_for_plan(vehicle, calculation_context)
    if home_goal is not None and vehicle_goal is not None:
        return vehicle_goal.sequence_index <= home_goal.sequence_index
    return max(1, vehicle.planning_sequence) <= scenario_purchase_sequence(scenario)


def vehicle_base_purchase_month(
    vehicle: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    calculation_context: CalculationContextSnapshot | None = None,
) -> int:
    window_start_delay = planning_window_delay_months(vehicle.planning_window_start_month)
    if vehicle.purchase_timing_mode == "manual_month":
        return max(0, window_start_delay if window_start_delay is not None else vehicle.manual_purchase_delay_months)
    home_goal = _current_home_goal(calculation_context)
    vehicle_goal = _vehicle_goal_for_plan(vehicle, calculation_context)
    vehicle_after_home_by_context = (
        home_goal is not None
        and vehicle_goal is not None
        and vehicle_goal.sequence_index > home_goal.sequence_index
    )
    if (
        (scenario is not None or vehicle_after_home_by_context)
        and home_purchase_month is not None
        and vehicle.purchase_timing_mode == "auto_sequence"
        and (
            vehicle_after_home_by_context
            or (scenario is not None and vehicle.planning_sequence > scenario_purchase_sequence(scenario))
        )
    ):
        sequenced_month = max(0, home_purchase_month + vehicle.after_previous_event_delay_months)
        return max(sequenced_month, window_start_delay or 0)
    return max(0, vehicle.purchase_delay_months, window_start_delay or 0)


def _vehicle_goal_snapshots_by_key(
    calculation_context: CalculationContextSnapshot | None,
) -> tuple[dict[str, CalculationContextGoalSnapshot], dict[str, CalculationContextGoalSnapshot], dict[int, CalculationContextGoalSnapshot]]:
    if calculation_context is None:
        return {}, {}, {}
    goals = [goal for goal in calculation_context.planning_goals if goal.goal_type == "vehicle"]
    return (
        {goal.id: goal for goal in goals if goal.id},
        {goal.name: goal for goal in goals if goal.name},
        {goal.priority: goal for goal in goals},
    )


def _vehicle_goal_snapshot_for_plan(
    vehicle: CarPlanData,
    index: int,
    *,
    by_id: dict[str, CalculationContextGoalSnapshot],
    by_name: dict[str, CalculationContextGoalSnapshot],
    by_priority: dict[int, CalculationContextGoalSnapshot],
) -> CalculationContextGoalSnapshot | None:
    goal_id = str(getattr(vehicle, "planning_goal_id", "") or "")
    return by_id.get(goal_id) or by_name.get(vehicle.name) or by_priority.get(vehicle.planning_sequence) or by_priority.get(index + 1)


def _vehicle_with_goal_snapshot(vehicle: CarPlanData, goal: CalculationContextGoalSnapshot | None) -> CarPlanData:
    if goal is None:
        return vehicle
    update: dict[str, object] = {
        "planning_goal_id": goal.id,
        "planning_sequence": max(1, goal.sequence_index),
    }
    if goal.normalized_timing_mode == "not_planned":
        update["enabled"] = False
        update["purchase_timing_mode"] = "not_planned"
    elif goal.normalized_timing_mode == "parallel":
        update["purchase_timing_mode"] = "parallel"
    elif goal.normalized_timing_mode == "manual_month":
        update["purchase_timing_mode"] = "manual_month"
    else:
        update["purchase_timing_mode"] = "auto_sequence"
    earliest_delay = max(
        vehicle.purchase_delay_months,
        vehicle.manual_purchase_delay_months,
        goal.resolved_not_before_month,
        goal.resolved_window_start_month,
    )
    update["purchase_delay_months"] = min(120, earliest_delay)
    update["manual_purchase_delay_months"] = earliest_delay
    if goal.resolved_window_end_month is not None:
        update["planning_window_end_month"] = format_year_month_tuple(
            month_after(date.today(), max(0, goal.resolved_window_end_month))
        )
    return vehicle.model_copy(update=update)


def vehicle_plans(
    plan: CarPlanData,
    *,
    scenario: ScenarioData | None = None,
    home_purchase_month: int | None = None,
    include_after_home: bool = True,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[CarPlanData]:
    plans: list[CarPlanData] = []
    goals_by_id, goals_by_name, goals_by_priority = _vehicle_goal_snapshots_by_key(calculation_context)
    raw_vehicle_plans_with_goal = [
        (
            index,
            vehicle,
            _vehicle_goal_snapshot_for_plan(
                vehicle,
                index,
                by_id=goals_by_id,
                by_name=goals_by_name,
                by_priority=goals_by_priority,
            ),
        )
        for index, vehicle in enumerate(plan.vehicle_plans)
    ]
    raw_vehicle_plans = sorted(
        raw_vehicle_plans_with_goal,
        key=lambda item: (max(1, item[2].sequence_index) if item[2] is not None else max(1, item[1].planning_sequence), item[0]),
    )
    previous_sequence_month: int | None = None
    for index, vehicle, goal in raw_vehicle_plans:
        vehicle = _vehicle_with_goal_snapshot(vehicle, goal)
        if not vehicle.enabled or vehicle.total_price <= 0:
            continue
        if not include_after_home and not vehicle_is_before_or_parallel_home(vehicle, scenario, calculation_context=calculation_context):
            continue
        base_purchase_month = vehicle_base_purchase_month(
            vehicle,
            scenario=scenario,
            home_purchase_month=home_purchase_month,
            calculation_context=calculation_context,
        )
        effective_purchase_month = base_purchase_month
        if vehicle.purchase_timing_mode == "auto_sequence" and previous_sequence_month is not None:
            effective_purchase_month = max(
                effective_purchase_month,
                previous_sequence_month + vehicle.after_previous_event_delay_months,
            )
        plans.append(
            plan.model_copy(
                update={
                    **vehicle.model_dump(),
                    "enabled": True,
                    "name": vehicle.name or f"车辆 {index + 1}",
                    "purchase_delay_months": effective_purchase_month,
                    "vehicle_plans": [],
                }
            )
        )
        previous_sequence_month = effective_purchase_month
    if plans:
        return plans
    fallback_goal = _vehicle_goal_snapshot_for_plan(
        plan,
        0,
        by_id=goals_by_id,
        by_name=goals_by_name,
        by_priority=goals_by_priority,
    )
    plan = _vehicle_with_goal_snapshot(plan, fallback_goal)
    if plan.enabled and plan.total_price > 0 and (
        include_after_home or vehicle_is_before_or_parallel_home(plan, scenario, calculation_context=calculation_context)
    ):
        plans.append(plan.model_copy(update={"vehicle_plans": []}))
    return plans


def vehicle_financing_options(plan: CarPlanData) -> list[dict[str, object]]:
    normalized_options = [
        option if isinstance(option, VehicleFinancingOptionData) else VehicleFinancingOptionData.model_validate(option)
        for option in plan.financing_options
        if isinstance(option, (VehicleFinancingOptionData, dict))
    ]
    enabled_options: list[dict[str, object]] = [
        option.model_dump()
        for option in normalized_options
        if option.enabled and option.total_months > 0
    ]
    if not enabled_options:
        enabled_options = default_vehicle_financing_options()
    result: list[dict[str, object]] = []
    for option in enabled_options:
        financing_type = str(option.get("financing_type") or "standard")
        total_months = max(1, min(120, int(option.get("total_months", 60))))
        interest_free_months = max(0, min(total_months, int(option.get("interest_free_months", 0))))
        min_ratio = max(0.0, min(1.0, float(option.get("min_down_payment_ratio", 0.10))))
        max_ratio = max(min_ratio, min(1.0, float(option.get("max_down_payment_ratio", 1.0))))
        later_annual_rate = max(0.0, min(0.5, float(option.get("later_annual_rate", 0.0))))
        if financing_type == "cash_only":
            total_months = 1
            interest_free_months = 0
            min_ratio = 1.0
            max_ratio = 1.0
            later_annual_rate = 0.0
        prepayment_allowed = financing_type != "cash_only" and bool(option.get("prepayment_allowed", True))
        result.append(
            {
                "id": str(option.get("id") or option.get("name") or "financing"),
                "name": str(option.get("name") or "金融方案"),
                "financing_type": financing_type,
                "total_months": total_months,
                "interest_free_months": interest_free_months,
                "later_annual_rate": later_annual_rate,
                "min_down_payment_ratio": min_ratio,
                "max_down_payment_ratio": max_ratio,
                "prepayment_allowed": prepayment_allowed,
                "prepayment_allowed_after_month": (
                    max(1, min(total_months, int(option.get("prepayment_allowed_after_month", 12))))
                    if prepayment_allowed
                    else 1
                ),
                "prepayment_policy_note": str(
                    option.get("prepayment_policy_note")
                    or ("提前还本规则以经销商或银行合同为准。" if prepayment_allowed else "该金融方案不形成或不允许提前还本。")
                ),
            }
        )
    return result


def vehicle_candidate_plans(plan: CarPlanData) -> list[tuple[int | None, CarPlanData]]:
    raw_candidates = [
        candidate if isinstance(candidate, CarPlanData) else CarPlanData.model_validate(candidate)
        for candidate in plan.candidate_vehicles
        if isinstance(candidate, (CarPlanData, dict))
    ]
    candidates = [
        candidate
        for candidate in raw_candidates
        if candidate.enabled and candidate.total_price > 0
    ]
    if not candidates:
        return [
            (
                None,
                plan.model_copy(
                    update={
                        "candidate_vehicles": [],
                        "selected_financing_option_id": financing["id"],
                        "selected_financing_option_name": financing["name"],
                        "selected_financing_type": financing["financing_type"],
                        "selected_financing_min_down_payment_ratio": financing["min_down_payment_ratio"],
                        "selected_financing_max_down_payment_ratio": financing["max_down_payment_ratio"],
                        "selected_financing_prepayment_allowed": financing["prepayment_allowed"],
                        "selected_financing_prepayment_policy_note": financing["prepayment_policy_note"],
                        "total_months": financing["total_months"],
                        "interest_free_months": financing["interest_free_months"],
                        "later_annual_rate": financing["later_annual_rate"],
                        "loan_prepayment_allowed_after_month": financing["prepayment_allowed_after_month"],
                    }
                ),
            )
            for financing in vehicle_financing_options(plan)
        ]

    options: list[tuple[int | None, CarPlanData]] = []
    for index, candidate in enumerate(candidates):
        for financing in vehicle_financing_options(candidate):
            candidate_data = candidate.model_dump()
            candidate_data.update(vehicle_policy_field_values(plan))
            candidate_data["candidate_vehicles"] = []
            candidate_data["planning_sequence"] = plan.planning_sequence
            candidate_data["purchase_timing_mode"] = plan.purchase_timing_mode
            candidate_data["after_previous_event_delay_months"] = plan.after_previous_event_delay_months
            candidate_data["manual_purchase_delay_months"] = plan.manual_purchase_delay_months
            candidate_data["enabled"] = True
            candidate_data["selected_strategy_variant"] = plan.selected_strategy_variant
            candidate_data["selected_financing_option_id"] = financing["id"]
            candidate_data["selected_financing_option_name"] = financing["name"]
            candidate_data["selected_financing_type"] = financing["financing_type"]
            candidate_data["selected_financing_min_down_payment_ratio"] = financing["min_down_payment_ratio"]
            candidate_data["selected_financing_max_down_payment_ratio"] = financing["max_down_payment_ratio"]
            candidate_data["selected_financing_prepayment_allowed"] = financing["prepayment_allowed"]
            candidate_data["selected_financing_prepayment_policy_note"] = financing["prepayment_policy_note"]
            candidate_data["total_months"] = financing["total_months"]
            candidate_data["interest_free_months"] = financing["interest_free_months"]
            candidate_data["later_annual_rate"] = financing["later_annual_rate"]
            candidate_data["loan_prepayment_allowed_after_month"] = financing["prepayment_allowed_after_month"]
            options.append((index, plan.model_copy(update=candidate_data)))
    return options


def months_until_cash_target(initial_cash: float, monthly_savings: float, target_cash: float, max_months: int = 120) -> int | None:
    if target_cash <= initial_cash:
        return 0
    if monthly_savings <= 0:
        return None
    months = int((target_cash - initial_cash + monthly_savings - 1) // monthly_savings)
    return months if months <= max_months else None


def annualized_amortizing_interest_rate(
    *,
    total_interest: float,
    principal: float,
    months: int,
) -> float:
    if principal <= 0 or months <= 0 or total_interest <= 0:
        return 0.0
    years = max(1 / 12, months / 12)
    return max(0.0, total_interest / principal / years * 2)


def round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return max(0.0, value)
    return max(0.0, (value // step) * step)


def choose_auto_vehicle_prepayment(
    plan: CarPlanData,
    *,
    down_payment_ratio: float,
    purchase_delay_months: int,
    total_months: int,
    interest_free_months: int,
    later_annual_rate: float,
    initial_cash: float,
    monthly_savings_before_car: float,
    monthly_savings_before_transport: float,
    current_monthly_expense: float,
    required_reserve: float,
    annual_investment_return: float = 0.0,
    investment_buy_fee_rate: float = 0.0,
    investment_sell_fee_rate: float = 0.0,
) -> VehiclePrepaymentChoice:
    total_months = max(1, total_months)
    interest_free_months = max(0, min(interest_free_months, total_months))
    allowed_after = max(
        1,
        min(
            total_months,
            plan.loan_prepayment_allowed_after_month if plan.loan_prepayment_enabled else 12,
        ),
    )
    no_prepayment_choice = VehiclePrepaymentChoice(
        enabled=False,
        strategy_type="none",
        start_month=allowed_after,
        allowed_after_month=allowed_after,
        monthly_amount=0.0,
        lump_sum_month=0,
        lump_sum_amount=0.0,
        total_extra_principal=0.0,
        interest_saved=0.0,
        net_benefit=0.0,
        actual_payoff_months=total_months,
        explanation=(
            plan.selected_financing_prepayment_policy_note
            if not plan.selected_financing_prepayment_allowed and plan.selected_financing_prepayment_policy_note
            else "当前金融方案不允许提前还本，自动策略不会安排额外还本金。"
            if not plan.selected_financing_prepayment_allowed
            else "车贷贴息后实际资金成本不高，或现金安全垫不足，自动策略暂不安排提前还本。"
        ),
    )
    if not plan.selected_financing_prepayment_allowed:
        return no_prepayment_choice
    preferred_start = (
        plan.loan_prepayment_start_month
        if plan.loan_prepayment_enabled
        else max(allowed_after, interest_free_months + 1)
    )
    start_candidates = sorted({
        max(allowed_after, min(total_months, preferred_start)),
        max(allowed_after, min(total_months, interest_free_months + 1)),
        max(allowed_after, min(total_months, 25)),
    })
    base_plan = plan.model_copy(
        update={
            "enabled": True,
            "down_payment_ratio": down_payment_ratio,
            "down_payment": plan.total_price * down_payment_ratio,
            "purchase_delay_months": purchase_delay_months,
            "total_months": total_months,
            "interest_free_months": interest_free_months,
            "later_annual_rate": later_annual_rate,
            "loan_prepayment_enabled": False,
            "loan_prepayment_monthly_amount": 0.0,
        }
    )
    down_payment = max(0.0, base_plan.total_price * down_payment_ratio)
    principal = max(0.0, base_plan.total_price - down_payment)
    if principal <= 0:
        return no_prepayment_choice
    baseline_projection = vehicle_loan_projection(
        principal,
        total_months,
        interest_free_months,
        later_annual_rate,
        prepayment_monthly_amount=0.0,
        prepayment_start_month=allowed_after,
    )
    hurdle_rate = prepayment_investment_hurdle_rate(
        annual_investment_return,
        buy_fee_rate=investment_buy_fee_rate,
        sell_fee_rate=investment_sell_fee_rate,
    )
    effective_vehicle_rate = annualized_amortizing_interest_rate(
        total_interest=baseline_projection.total_interest,
        principal=principal,
        months=total_months,
    )
    if effective_vehicle_rate <= hurdle_rate:
        return no_prepayment_choice
    first_regular_point = baseline_projection.points[0] if baseline_projection.points else None
    post_subsidy_regular_point = (
        baseline_projection.points[interest_free_months]
        if interest_free_months < len(baseline_projection.points)
        else first_regular_point
    )
    operating_cost = estimate_car_operating_cost(base_plan)

    regular_payment = max(
        first_regular_point.contract_payment if first_regular_point else 0.0,
        post_subsidy_regular_point.contract_payment if post_subsidy_regular_point else 0.0,
    )
    monthly_room_after_regular_car = (
        monthly_savings_before_transport
        - regular_payment
        - operating_cost["monthly_cash_operating_cost"]
    )
    cashflow_buffer = max(500.0, current_monthly_expense * 0.08)
    auto_monthly_cap = max(0.0, monthly_room_after_regular_car - cashflow_buffer)
    manual_cap = max(0.0, plan.loan_prepayment_monthly_amount) if plan.loan_prepayment_enabled else 0.0
    strategy_cap = min(
        auto_monthly_cap,
        manual_cap if manual_cap > 0 else min(8000.0, max(1000.0, principal * 0.04)),
    )
    amount_candidates = {0.0}
    if strategy_cap >= 500:
        for ratio in (0.25, 0.5, 0.75, 1.0):
            rounded = round_down_to_step(strategy_cap * ratio, 500)
            if rounded >= 500:
                amount_candidates.add(rounded)
    if manual_cap > 0 and auto_monthly_cap >= 500:
        amount_candidates.add(round_down_to_step(min(manual_cap, auto_monthly_cap), 500))

    safe_cash_after_down = max(0.0, initial_cash + monthly_savings_before_car * max(0, purchase_delay_months) - down_payment - required_reserve)
    lump_cap = max(0.0, min(principal * 0.60, safe_cash_after_down * 0.55))
    lump_candidates = {0.0}
    if lump_cap >= 1000:
        for ratio in (0.25, 0.5, 0.75, 1.0):
            amount = round_down_to_step(lump_cap * ratio, 1000)
            if amount >= 1000:
                lump_candidates.add(amount)
    lump_month_candidates = sorted({
        max(allowed_after, min(total_months, preferred_start)),
        max(allowed_after, min(total_months, interest_free_months + 1)),
        max(allowed_after, min(total_months, 12)),
        max(allowed_after, min(total_months, 24)),
    })

    best: tuple[float, VehiclePrepaymentChoice] | None = None
    for strategy_type in ("none", "monthly", "lump_sum", "hybrid"):
        monthly_candidates = [0.0] if strategy_type in {"none", "lump_sum"} else sorted(amount_candidates)
        lump_amount_candidates = [0.0] if strategy_type in {"none", "monthly"} else sorted(lump_candidates)
        for monthly_amount in monthly_candidates:
            for lump_amount in lump_amount_candidates:
                if strategy_type != "none" and monthly_amount <= 0 and lump_amount <= 0:
                    continue
                if strategy_type == "hybrid" and (monthly_amount <= 0 or lump_amount <= 0):
                    continue
                starts = start_candidates if monthly_amount > 0 else [allowed_after]
                lump_months = lump_month_candidates if lump_amount > 0 else [0]
                for start_month in starts:
                    for lump_month in lump_months:
                        projection = vehicle_loan_projection(
                            principal,
                            total_months,
                            interest_free_months,
                            later_annual_rate,
                            prepayment_monthly_amount=monthly_amount,
                            prepayment_start_month=start_month,
                            prepayment_lump_sum_amount=lump_amount,
                            prepayment_lump_sum_month=lump_month,
                        )
                        total_extra_principal = sum(point.extra_principal_payment for point in projection.points)
                        required_cash = down_payment + required_reserve + (lump_amount if lump_month <= max(1, purchase_delay_months + 1) else 0.0)
                        cash_ready_month = months_until_cash_target(initial_cash, monthly_savings_before_car, required_cash)
                        if cash_ready_month is None:
                            months_to_buy = None
                            cash_after_purchase = initial_cash - down_payment - lump_amount
                        else:
                            months_to_buy = max(purchase_delay_months, cash_ready_month)
                            cash_after_purchase = initial_cash + monthly_savings_before_car * months_to_buy - down_payment
                            if lump_amount > 0 and lump_month <= max(1, months_to_buy + 1):
                                cash_after_purchase -= lump_amount
                        expected_point = projection.points[0] if projection.points else None
                        expected_post_subsidy_point = (
                            projection.points[interest_free_months]
                            if interest_free_months < len(projection.points)
                            else expected_point
                        )
                        expected_payment = max(
                            expected_point.contract_payment if expected_point else 0.0,
                            expected_post_subsidy_point.contract_payment if expected_post_subsidy_point else 0.0,
                        )
                        monthly_after_car = monthly_savings_before_transport - expected_payment - monthly_amount - operating_cost["monthly_cash_operating_cost"]
                        opportunity_years = max(1 / 12, max(0, projection.actual_payoff_months - min(start_month, lump_month or start_month)) / 12)
                        opportunity_cost = total_extra_principal * max(0.0, hurdle_rate) * opportunity_years * 0.55
                        net_benefit = projection.interest_saved_by_prepayment - opportunity_cost
                        interest_score = clamp_score(projection.interest_saved_by_prepayment / max(baseline_projection.total_interest, 1.0) * 10)
                        opportunity_score = prepayment_rate_spread_score(effective_vehicle_rate, hurdle_rate)
                        payoff_score = clamp_score((total_months - projection.actual_payoff_months) / max(total_months, 1) * 10)
                        net_benefit_score = clamp_score(net_benefit / max(baseline_projection.total_interest, 1.0) * 10)
                        score = (
                            cash_flow_score(monthly_after_car, current_monthly_expense) * 0.26
                            + ratio_score(cash_after_purchase, required_reserve) * 0.23
                            + wait_score(months_to_buy, 24) * 0.14
                            + interest_score * 0.13
                            + payoff_score * 0.10
                            + opportunity_score * 0.06
                            + net_benefit_score * 0.08
                        )
                        if monthly_after_car < 0:
                            score -= 4.0
                        if cash_after_purchase < required_reserve:
                            score -= 3.0
                        if net_benefit <= 0 and (monthly_amount > 0 or lump_amount > 0):
                            score -= 3.5
                        if monthly_amount > 0 and later_annual_rate <= 0.02 and start_month <= interest_free_months:
                            score -= 1.0
                        if lump_amount > 0 and cash_after_purchase < required_reserve * 1.15:
                            score -= 1.2
                        if monthly_amount <= 0 and lump_amount <= 0:
                            score -= 0.8

                        if strategy_type == "none":
                            explanation = "自动策略比较车贷资金成本、理财净收益和现金安全垫后，选择不提前还本。"
                        elif strategy_type == "lump_sum":
                            explanation = (
                                f"自动策略选择第 {lump_month} 期一次性提前还本金 {round(lump_amount)}，"
                                f"预计节省家庭承担利息 {round(projection.interest_saved_by_prepayment)}，"
                                f"扣除理财机会成本后的净收益约 {round(net_benefit)}。"
                            )
                        elif strategy_type == "monthly":
                            explanation = (
                                f"自动策略选择第 {start_month} 期起每月额外还本金 {round(monthly_amount)}，"
                                f"预计 {projection.actual_payoff_months} 个月结清，"
                                f"节省家庭承担利息 {round(projection.interest_saved_by_prepayment)}。"
                            )
                        else:
                            explanation = (
                                f"自动策略选择第 {lump_month} 期先一次性还本金 {round(lump_amount)}，"
                                f"再从第 {start_month} 期起每月额外还本金 {round(monthly_amount)}；"
                                f"兼顾降低利息和保留购房现金。"
                            )
                        choice = VehiclePrepaymentChoice(
                            enabled=monthly_amount > 0 or lump_amount > 0,
                            strategy_type=strategy_type,
                            start_month=start_month,
                            allowed_after_month=allowed_after,
                            monthly_amount=monthly_amount,
                            lump_sum_month=lump_month,
                            lump_sum_amount=lump_amount,
                            total_extra_principal=total_extra_principal,
                            interest_saved=projection.interest_saved_by_prepayment,
                            net_benefit=net_benefit,
                            actual_payoff_months=projection.actual_payoff_months,
                            explanation=explanation,
                        )
                        if best is None or score > best[0]:
                            best = (score, choice)

    if best is None or not best[1].enabled:
        return no_prepayment_choice
    return best[1]


def build_car_plan_analyses(
    household: HouseholdData,
    *,
    net_monthly_income: float,
    current_monthly_expense: float,
    calculate_car_loan: CarLoanCalculator,
    annual_investment_return: float = 0.0,
    rules: RulePackData,
    calculation_context: CalculationContextSnapshot | None = None,
) -> list[CarPlanAnalysis]:
    active_vehicle_plans = vehicle_plans(household.car_plan, calculation_context=calculation_context)
    if not active_vehicle_plans:
        return []

    initial_cash = household.cash_account_balance + household.investments
    monthly_savings_before_transport = max(
        0,
        net_monthly_income - current_monthly_expense - household.monthly_debt_payment,
    )
    no_car_commute = max(0.0, household.car_plan.no_car_monthly_commute_cost)
    monthly_savings_before_car = max(0, monthly_savings_before_transport - no_car_commute)
    required_reserve = current_monthly_expense * household.required_liquidity_months

    def optimized_vehicle_down_ratio(plan: CarPlanData, strategy_key: str, purchase_delay: int) -> float:
        if plan.total_price <= 0:
            return 0.0
        min_ratio = clamp(plan.selected_financing_min_down_payment_ratio, 0.0, 1.0)
        max_ratio = max(min_ratio, clamp(plan.selected_financing_max_down_payment_ratio, 0.0, 1.0))
        cash_capacity = initial_cash + monthly_savings_before_car * max(0, purchase_delay) - required_reserve
        capacity_ratio = clamp(cash_capacity / plan.total_price, 0.0, 1.0)
        target_ratio = clamp(plan.down_payment_ratio, 0.0, 1.0)
        if strategy_key == "cash":
            return 1.0
        if strategy_key == "low_down_keep_cash":
            preferred = min(0.20, max(0.10, target_ratio * 0.55))
            return clamp(min(preferred, max(min_ratio, capacity_ratio * 0.35)), min_ratio, min(max_ratio, 0.25))
        if strategy_key == "high_down_low_loan":
            pressure_ratio = 0.42 if monthly_savings_before_transport >= current_monthly_expense * 0.75 else 0.34
            preferred = pressure_ratio + (0.08 if annual_investment_return < plan.later_annual_rate else 0.0)
            return clamp(min(preferred, max(min_ratio, capacity_ratio * 0.75)), min_ratio, min(max_ratio, 0.70))
        if strategy_key == "accelerated_principal":
            pressure_ratio = 0.28 if plan.later_annual_rate <= annual_investment_return else 0.36
            return clamp(min(pressure_ratio, max(min_ratio, capacity_ratio * 0.65)), min_ratio, min(max_ratio, 0.58))
        if strategy_key == "delay_purchase":
            preferred = min(0.35, max(0.15, target_ratio * 0.70))
            return clamp(min(preferred, max(min_ratio, capacity_ratio * 0.55)), min_ratio, min(max_ratio, 0.45))
        return clamp(target_ratio, min_ratio, max_ratio)

    analyses: list[CarPlanAnalysis] = []
    for vehicle_index, vehicle_plan in enumerate(active_vehicle_plans):
        candidate_options = vehicle_candidate_plans(vehicle_plan)
        seen_zero_loan_signatures: set[tuple[int, int | None, int, int, int, int]] = set()
        for candidate_index, plan in candidate_options:
            candidate_name = plan.name or vehicle_plan.name
            financing_name = plan.selected_financing_option_name or "金融方案"
            financing_type = plan.selected_financing_type or ("dealer_subsidy" if plan.interest_free_months > 0 else "standard")
            variant_prefix = candidate_name if len(active_vehicle_plans) > 1 or len(candidate_options) > 1 else ""
            purchase_policy = vehicle_purchase_policy_amounts(plan, rules, plan.purchase_delay_months)
            indicator_delay = vehicle_indicator_wait_months(
                plan,
                rules,
                purchase_policy["beijing_family_indicator_estimated_wait_months"],  # type: ignore[arg-type]
            )
            base_purchase_delay = max(plan.purchase_delay_months, indicator_delay)
            delay_months = max(base_purchase_delay, 12)
            no_prepayment = VehiclePrepaymentChoice(
                enabled=False,
                strategy_type="none",
                start_month=1,
                allowed_after_month=1,
                monthly_amount=0.0,
                lump_sum_month=0,
                lump_sum_amount=0.0,
                total_extra_principal=0.0,
                interest_saved=0.0,
                net_benefit=0.0,
                actual_payoff_months=0,
                explanation="本策略不安排提前还本。",
            )
            ratio_candidates = {
                "target": sorted({optimized_vehicle_down_ratio(plan, "target", plan.purchase_delay_months)}),
                "cash": [1.0],
                "high_down_low_loan": [optimized_vehicle_down_ratio(plan, "high_down_low_loan", plan.purchase_delay_months)],
                "low_down_keep_cash": [optimized_vehicle_down_ratio(plan, "low_down_keep_cash", plan.purchase_delay_months)],
                "accelerated_principal": [optimized_vehicle_down_ratio(plan, "accelerated_principal", plan.purchase_delay_months)],
                "delay_purchase": [optimized_vehicle_down_ratio(plan, "delay_purchase", delay_months)],
            }
            cash_spec = ("cash", "全款购买，不形成车贷，适合现金安全垫非常充足时。", base_purchase_delay, 1, 0, 0.0)
            specs = [cash_spec] if financing_type == "cash_only" else [
                ("target", "按当前车源和金融方案测算，适合细调首付、购车时间和是否提前还本。", base_purchase_delay, plan.total_months, plan.interest_free_months, plan.later_annual_rate),
                cash_spec,
                ("high_down_low_loan", "在经销商金融方案内选择较高首付比例，用较低贷款本金控制月供和总利息。", base_purchase_delay, plan.total_months, plan.interest_free_months, plan.later_annual_rate),
                ("low_down_keep_cash", "在经销商金融方案内选择较低首付比例，尽量保留购房现金和应急垫。", base_purchase_delay, plan.total_months, plan.interest_free_months, plan.later_annual_rate),
                ("accelerated_principal", "沿用经销商金融方案，系统比较一次性、分月和组合提前还本，选择净收益更好的还本节奏。", base_purchase_delay, plan.total_months, plan.interest_free_months, plan.later_annual_rate),
                ("delay_purchase", "延后购车并在经销商金融方案内搜索较稳首付比例，把现金优先留给购房窗口和安全垫。", delay_months, plan.total_months, plan.interest_free_months, plan.later_annual_rate),
            ]
            for strategy_key, description, purchase_delay, total_months, interest_free_months, later_rate in specs:
                skip_strategy = False
                for down_ratio in ratio_candidates[strategy_key]:
                    if strategy_key not in {"cash", "delay_purchase"} and down_ratio >= 0.999:
                        skip_strategy = True
                        break
                    prepayment_choice = (
                        choose_auto_vehicle_prepayment(
                            plan,
                            down_payment_ratio=down_ratio,
                            purchase_delay_months=purchase_delay,
                            total_months=total_months,
                            interest_free_months=interest_free_months,
                            later_annual_rate=later_rate,
                            initial_cash=initial_cash,
                            monthly_savings_before_car=monthly_savings_before_car,
                            monthly_savings_before_transport=monthly_savings_before_transport,
                            current_monthly_expense=current_monthly_expense,
                            required_reserve=required_reserve,
                            annual_investment_return=annual_investment_return,
                            investment_buy_fee_rate=household.investment_buy_fee_rate,
                            investment_sell_fee_rate=household.investment_sell_fee_rate,
                        )
                        if strategy_key == "accelerated_principal"
                        else no_prepayment
                    )
                    strategy_plan = plan.model_copy(
                        update={
                            "enabled": True,
                            "down_payment_ratio": down_ratio,
                            "down_payment": plan.total_price * down_ratio,
                            "purchase_delay_months": purchase_delay,
                            "total_months": total_months,
                            "interest_free_months": min(interest_free_months, total_months),
                            "later_annual_rate": later_rate,
                            "loan_prepayment_enabled": prepayment_choice.enabled,
                            "loan_prepayment_strategy_type": prepayment_choice.strategy_type,
                            "loan_prepayment_start_month": min(total_months, max(1, prepayment_choice.start_month)),
                            "loan_prepayment_allowed_after_month": min(total_months, max(1, prepayment_choice.allowed_after_month)),
                            "loan_prepayment_monthly_amount": max(0.0, prepayment_choice.monthly_amount),
                            "loan_prepayment_lump_sum_month": min(total_months, max(0, prepayment_choice.lump_sum_month)),
                            "loan_prepayment_lump_sum_amount": max(0.0, prepayment_choice.lump_sum_amount),
                        }
                    )
                    loan = calculate_car_loan(
                        strategy_plan,
                        initial_cash=initial_cash,
                        monthly_cash_savings_before_car=monthly_savings_before_car,
                        rules=rules,
                    )
                    if loan.loan_principal <= 1:
                        zero_loan_signature = (
                            vehicle_index,
                            candidate_index,
                            purchase_delay,
                            round(loan.down_payment),
                            round(loan.monthly_cash_operating_cost),
                            round(loan.monthly_total_ownership_cost),
                        )
                        if zero_loan_signature in seen_zero_loan_signatures:
                            skip_strategy = True
                            break
                        seen_zero_loan_signatures.add(zero_loan_signature)
                if skip_strategy:
                    continue
                required_cash = loan.down_payment + loan.purchase_tax + loan.license_plate_rental_initial_fee + required_reserve
                cash_ready_month = months_until_cash_target(initial_cash, monthly_savings_before_car, required_cash)
                if cash_ready_month is None:
                    months_to_buy = None
                    cash_after_purchase = initial_cash - loan.down_payment - loan.purchase_tax - loan.license_plate_rental_initial_fee
                else:
                    months_to_buy = max(purchase_delay, cash_ready_month)
                    cash_after_purchase = (
                        initial_cash
                        + monthly_savings_before_car * months_to_buy
                        - loan.down_payment
                        - loan.purchase_tax
                        - loan.license_plate_rental_initial_fee
                    )
                planning_window_end_delay = planning_window_delay_months(plan.planning_window_end_month)
                window_end_blocked = (
                    planning_window_end_delay is not None
                    and months_to_buy is not None
                    and months_to_buy > planning_window_end_delay
                )
                if window_end_blocked:
                    months_to_buy = None
                expected_payment = max(loan.first_phase_monthly_payment, loan.later_phase_monthly_payment)
                expected_total_payment = expected_payment + (loan.prepayment_monthly_amount if loan.prepayment_enabled else 0.0)
                monthly_after_car = monthly_savings_before_transport - expected_total_payment - loan.monthly_cash_operating_cost
                debt_burden_score = clamp_score(10 - expected_payment / max(net_monthly_income, 1) / 0.18 * 10)
                total_cost_score = clamp_score(10 - loan.monthly_total_ownership_cost / max(net_monthly_income, 1) / 0.16 * 10)
                happiness_score = (
                    plan.happiness_score * 0.28
                    + ratio_score(cash_after_purchase, required_reserve) * 0.22
                    + cash_flow_score(monthly_after_car, current_monthly_expense) * 0.20
                    + debt_burden_score * 0.12
                    + total_cost_score * 0.08
                    + wait_score(months_to_buy, 24) * 0.10
                )
                notes = [
                    f"vehicle_goal:{vehicle_plan.name}",
                    f"vehicle_source:{candidate_name}",
                    f"down_payment_ratio:{down_ratio:.0%}",
                    f"cash_operating_cost_monthly:{round(loan.monthly_cash_operating_cost)}",
                    f"total_ownership_cost_monthly:{round(loan.monthly_total_ownership_cost)}",
                    f"purchase_tax:{round(loan.purchase_tax)}",
                    f"purchase_tax_relief:{round(loan.purchase_tax_relief)}",
                    f"annual_vehicle_vessel_tax:{round(loan.annual_vehicle_vessel_tax)}",
                    f"plate_rental_initial_fee:{round(loan.license_plate_rental_initial_fee)}",
                    f"beijing_family_indicator_score:{round(loan.beijing_family_indicator_score, 2)}",
                    (
                        f"beijing_family_indicator_wait_months:{loan.beijing_family_indicator_estimated_wait_months}"
                        if loan.beijing_family_indicator_estimated_wait_months is not None
                        else "beijing_family_indicator_wait_months:unknown"
                    ),
                    "no_auto_loan" if loan.loan_principal == 0 else f"loan_principal:{round(loan.loan_principal)}",
                    (
                        f"auto_extra_principal:{loan.prepayment_strategy_type}, monthly:{round(loan.prepayment_monthly_amount)}, "
                        f"lump:{round(loan.prepayment_lump_sum_amount)} at month {loan.prepayment_lump_sum_month}, "
                        f"payoff_months:{loan.actual_payoff_months}, interest_saved:{round(loan.interest_saved_by_prepayment)}"
                    )
                    if loan.prepayment_enabled and strategy_key == "accelerated_principal"
                    else (
                        f"extra_principal:{round(loan.prepayment_monthly_amount)} from month {loan.prepayment_start_month}, "
                        f"payoff_months:{loan.actual_payoff_months}, interest_saved:{round(loan.interest_saved_by_prepayment)}"
                    )
                    if loan.prepayment_enabled
                    else "no_extra_principal",
                    "manual_target" if strategy_key == "target" else "preserve_home_purchase_cash" if strategy_key in {"low_down_keep_cash", "delay_purchase"} else "reduce_long_term_auto_debt_pressure",
                ]
                if window_end_blocked and planning_window_end_delay is not None:
                    notes.append(f"planning_window_exceeded:{planning_window_end_delay}")
                notes.extend(loan.policy_notes)
                analyses.append(
                    CarPlanAnalysis(
                        variant=" | ".join(
                            part
                            for part in [variant_prefix, financing_name, strategy_key]
                            if part
                        ),
                        description=description,
                        planning_goal_id=vehicle_plan.planning_goal_id,
                        source="planning_goals" if vehicle_plan.planning_goal_id else "car_plan",
                        vehicle_index=vehicle_index,
                        vehicle_name=vehicle_plan.name,
                        vehicle_candidate_index=candidate_index,
                        vehicle_candidate_name=candidate_name,
                        financing_option_id=plan.selected_financing_option_id,
                        financing_option_name=financing_name,
                        financing_type=financing_type,
                        strategy_key=strategy_key,
                        purchase_delay_months=purchase_delay,
                        months_to_buy=months_to_buy,
                        years_to_buy=round(months_to_buy / 12, 1) if months_to_buy is not None else None,
                        total_price=round(plan.total_price, 2),
                        down_payment_ratio=down_ratio,
                        down_payment=loan.down_payment,
                        purchase_tax=loan.purchase_tax,
                        purchase_tax_relief=loan.purchase_tax_relief,
                        annual_vehicle_vessel_tax=loan.annual_vehicle_vessel_tax,
                        license_plate_rental_initial_fee=loan.license_plate_rental_initial_fee,
                        beijing_family_indicator_score=loan.beijing_family_indicator_score,
                        beijing_family_indicator_estimated_wait_months=loan.beijing_family_indicator_estimated_wait_months,
                        loan_principal=loan.loan_principal,
                        total_months=loan.total_months,
                        interest_free_months=loan.interest_free_months,
                        later_annual_rate=loan.later_annual_rate,
                        first_phase_monthly_payment=loan.first_phase_monthly_payment,
                        later_phase_monthly_payment=loan.later_phase_monthly_payment,
                        contract_monthly_payment=loan.contract_monthly_payment,
                        first_phase_interest_subsidy=loan.first_phase_interest_subsidy,
                        total_interest_subsidy=loan.total_interest_subsidy,
                        borrower_total_interest=loan.borrower_total_interest,
                        expected_monthly_payment_after_purchase=round(expected_total_payment, 2),
                        prepayment_allowed=loan.prepayment_allowed,
                        prepayment_enabled=loan.prepayment_enabled,
                        prepayment_start_month=loan.prepayment_start_month,
                        prepayment_allowed_after_month=loan.prepayment_allowed_after_month,
                        prepayment_monthly_amount=loan.prepayment_monthly_amount,
                        prepayment_strategy_type=loan.prepayment_strategy_type,
                        prepayment_lump_sum_month=loan.prepayment_lump_sum_month,
                        prepayment_lump_sum_amount=loan.prepayment_lump_sum_amount,
                        prepayment_total_extra_principal=loan.prepayment_total_extra_principal,
                        prepayment_net_benefit=round(prepayment_choice.net_benefit, 2) if strategy_key == "accelerated_principal" else loan.prepayment_net_benefit,
                        prepayment_explanation=prepayment_choice.explanation if strategy_key == "accelerated_principal" else loan.prepayment_explanation,
                        actual_payoff_months=loan.actual_payoff_months,
                        interest_saved_by_prepayment=loan.interest_saved_by_prepayment,
                        total_interest=loan.total_interest,
                        required_cash_at_purchase=round(required_cash, 2),
                        cash_after_purchase=round(cash_after_purchase, 2),
                        monthly_cash_flow_after_car=round(monthly_after_car, 2),
                        operating_cost=loan.monthly_cash_operating_cost,
                        monthly_energy_cost=loan.monthly_energy_cost,
                        monthly_insurance_cost=loan.monthly_insurance_cost,
                        monthly_maintenance_cost=loan.monthly_maintenance_cost,
                        monthly_parking_cost=loan.monthly_parking_cost,
                        monthly_cash_operating_cost=loan.monthly_cash_operating_cost,
                        monthly_depreciation_cost=loan.monthly_depreciation_cost,
                        monthly_total_ownership_cost=loan.monthly_total_ownership_cost,
                        happiness_score=round(clamp_score(happiness_score), 2),
                        notes=notes,
                    )
                )
    return representative_car_plan_analyses(analyses)


def representative_car_plan_analyses(analyses: list[CarPlanAnalysis]) -> list[CarPlanAnalysis]:
    if not analyses:
        return []

    grouped: dict[tuple[int, int | None, str], list[CarPlanAnalysis]] = {}
    group_order: dict[tuple[int, int | None, str], int] = {}
    for index, analysis in enumerate(analyses):
        source_name = analysis.vehicle_candidate_name or analysis.vehicle_name
        key = (analysis.vehicle_index, analysis.vehicle_candidate_index, source_name)
        grouped.setdefault(key, []).append(analysis)
        group_order.setdefault(key, index)

    def is_viable(item: CarPlanAnalysis) -> bool:
        return item.months_to_buy is not None and item.cash_after_purchase >= 0 and item.monthly_cash_flow_after_car >= 0

    def target_score(item: CarPlanAnalysis) -> tuple[bool, bool, float, float, float]:
        return (
            item.financing_type != "cash_only",
            is_viable(item),
            item.happiness_score,
            -item.expected_monthly_payment_after_purchase,
            -item.total_interest,
        )

    def strategy_score(item: CarPlanAnalysis) -> tuple[float, ...]:
        viable_bonus = 1.0 if is_viable(item) else 0.0
        if item.strategy_key == "cash":
            return (
                viable_bonus,
                -float(item.months_to_buy if item.months_to_buy is not None else 999999),
                item.happiness_score,
                item.cash_after_purchase,
            )
        if item.strategy_key == "high_down_low_loan":
            return (
                viable_bonus,
                -item.expected_monthly_payment_after_purchase,
                -item.total_interest,
                item.happiness_score,
                item.cash_after_purchase,
            )
        if item.strategy_key == "low_down_keep_cash":
            return (
                viable_bonus,
                item.cash_after_purchase,
                -item.down_payment,
                item.happiness_score,
                -item.expected_monthly_payment_after_purchase,
            )
        if item.strategy_key == "accelerated_principal":
            return (
                1.0 if item.prepayment_enabled else 0.0,
                viable_bonus,
                item.prepayment_net_benefit,
                item.interest_saved_by_prepayment,
                -item.expected_monthly_payment_after_purchase,
                item.happiness_score,
            )
        if item.strategy_key == "delay_purchase":
            return (
                viable_bonus,
                item.cash_after_purchase,
                item.happiness_score,
                -item.expected_monthly_payment_after_purchase,
                -float(item.months_to_buy if item.months_to_buy is not None else 999999),
            )
        return (viable_bonus, item.happiness_score)

    def difference_signature(item: CarPlanAnalysis) -> tuple[object, ...]:
        return (
            item.strategy_key,
            round(item.down_payment / 1000),
            round(item.loan_principal / 1000),
            item.purchase_delay_months,
            item.total_months,
            item.interest_free_months,
            round(item.later_annual_rate * 10000),
            item.prepayment_enabled,
            round(item.prepayment_monthly_amount / 500),
            item.prepayment_lump_sum_month,
            round(item.prepayment_lump_sum_amount / 1000),
        )

    result: list[CarPlanAnalysis] = []
    strategy_order = ["cash", "high_down_low_loan", "low_down_keep_cash", "accelerated_principal", "delay_purchase"]
    for group_key in sorted(grouped, key=lambda key: group_order[key]):
        items = grouped[group_key]
        selected: list[CarPlanAnalysis] = []
        targets = [item for item in items if item.strategy_key == "target"]
        if targets:
            selected.append(max(targets, key=target_score))

        for strategy_key in strategy_order:
            candidates = [item for item in items if item.strategy_key == strategy_key]
            if not candidates:
                continue
            representative = max(candidates, key=strategy_score)
            if strategy_key == "accelerated_principal" and not representative.prepayment_enabled:
                continue
            selected.append(representative)

        seen_signatures: set[tuple[object, ...]] = set()
        for item in selected:
            signature = difference_signature(item)
            if item.strategy_key != "target" and signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            result.append(item)
    return result


def car_strategy_key_from_selection(selection: str) -> str:
    value = (selection or "").strip()
    if not value:
        return "target"
    aliases = {
        "手动设置": "target",
        "手动策略": "target",
        "按目标设置": "target",
        "全款": "cash",
        "高首付低贷": "high_down_low_loan",
        "低首付保现金": "low_down_keep_cash",
        "提前还本降息": "accelerated_principal",
        "延后买车": "delay_purchase",
    }
    if value in aliases:
        return aliases[value]
    tail = value.split("|")[-1].strip()
    if tail in aliases:
        return aliases[tail]
    known = {"target", "cash", "high_down_low_loan", "low_down_keep_cash", "accelerated_principal", "delay_purchase"}
    if value in known:
        return value
    if tail in known:
        return tail
    return "target"


def selected_car_strategy_for_vehicle(
    selection: str,
    vehicle_index: int,
    analyses: list[CarPlanAnalysis],
) -> CarPlanAnalysis | None:
    vehicle_analyses = [item for item in analyses if item.vehicle_index == vehicle_index]
    if not vehicle_analyses:
        return None
    normalized_selection = (selection or "").strip()
    exact = next((item for item in vehicle_analyses if item.variant == normalized_selection), None)
    if exact is not None:
        return exact
    selected_key = car_strategy_key_from_selection(normalized_selection)
    return next((item for item in vehicle_analyses if item.strategy_key == selected_key), None)


def vehicle_plan_with_selected_strategy(
    vehicle: VehiclePlanData,
    strategy: CarPlanAnalysis,
) -> VehiclePlanData:
    source: VehiclePlanData = vehicle
    if strategy.vehicle_candidate_index is not None and 0 <= strategy.vehicle_candidate_index < len(vehicle.candidate_vehicles):
        candidate = vehicle.candidate_vehicles[strategy.vehicle_candidate_index]
        source = candidate if isinstance(candidate, VehiclePlanData) else VehiclePlanData.model_validate(candidate)
    return source.model_copy(
        update={
            "enabled": True,
            "name": strategy.vehicle_candidate_name or strategy.vehicle_name or source.name,
            "selected_strategy_variant": strategy.variant,
            "candidate_vehicles": [],
            **vehicle_policy_field_values(vehicle),
            "planning_sequence": vehicle.planning_sequence,
            "purchase_timing_mode": vehicle.purchase_timing_mode,
            "after_previous_event_delay_months": vehicle.after_previous_event_delay_months,
            "manual_purchase_delay_months": vehicle.manual_purchase_delay_months,
            "total_price": strategy.total_price,
            "down_payment_ratio": strategy.down_payment_ratio,
            "down_payment": strategy.down_payment,
            "purchase_delay_months": strategy.purchase_delay_months,
            "total_months": strategy.total_months,
            "interest_free_months": strategy.interest_free_months,
            "later_annual_rate": strategy.later_annual_rate,
            "selected_financing_option_id": strategy.financing_option_id,
            "selected_financing_option_name": strategy.financing_option_name,
            "selected_financing_type": strategy.financing_type,
            "selected_financing_min_down_payment_ratio": strategy.down_payment_ratio,
            "selected_financing_max_down_payment_ratio": max(strategy.down_payment_ratio, source.selected_financing_max_down_payment_ratio),
            "selected_financing_prepayment_allowed": strategy.prepayment_allowed,
            "loan_prepayment_enabled": strategy.prepayment_enabled,
            "loan_prepayment_start_month": strategy.prepayment_start_month,
            "loan_prepayment_allowed_after_month": strategy.prepayment_allowed_after_month,
            "loan_prepayment_monthly_amount": strategy.prepayment_monthly_amount,
            "loan_prepayment_strategy_type": strategy.prepayment_strategy_type,
            "loan_prepayment_lump_sum_month": strategy.prepayment_lump_sum_month,
            "loan_prepayment_lump_sum_amount": strategy.prepayment_lump_sum_amount,
        }
    )


def car_plan_with_selected_strategies(
    plan: CarPlanData,
    analyses: list[CarPlanAnalysis],
) -> CarPlanData:
    if not analyses:
        return plan
    if plan.vehicle_plans:
        effective_vehicle_plans: list[VehiclePlanData] = []
        for vehicle_index, vehicle in enumerate(plan.vehicle_plans):
            strategy = selected_car_strategy_for_vehicle(vehicle.selected_strategy_variant, vehicle_index, analyses)
            effective_vehicle_plans.append(
                vehicle_plan_with_selected_strategy(vehicle, strategy)
                if strategy is not None
                else vehicle
            )
        selected_variant = next(
            (vehicle.selected_strategy_variant for vehicle in effective_vehicle_plans if vehicle.selected_strategy_variant),
            plan.selected_strategy_variant,
        )
        return plan.model_copy(
            update={
                "vehicle_plans": effective_vehicle_plans,
                "selected_strategy_variant": selected_variant,
            }
        )
    strategy = selected_car_strategy_for_vehicle(plan.selected_strategy_variant, 0, analyses)
    if strategy is None:
        return plan
    effective_plan = vehicle_plan_with_selected_strategy(plan, strategy)
    return plan.model_copy(update={**effective_plan.model_dump(), "vehicle_plans": []})


def vehicle_events_for_plan(
    *,
    plan_variant: str,
    title_prefix: str,
    car_plan: CarPlanData,
    car_loan: CarLoanSummary,
) -> list[PlanEventPoint]:
    if not car_plan.enabled or not car_loan.enabled:
        return []
    purchase_month = car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else car_plan.purchase_delay_months
    events = [
        PlanEventPoint(
            plan_variant=plan_variant,
            month=max(0, int(purchase_month or 0)),
            category="vehicle",
            title=f"{title_prefix}购入",
            detail=(
                f"首付 {_money_text(car_loan.down_payment)}，车贷本金 {_money_text(car_loan.loan_principal)}，"
                f"现金养车月度成本约 {_money_text(car_loan.monthly_cash_operating_cost)}；保险和保养按年度发生月计入现金流。"
            ),
            amount=round(car_loan.down_payment, 2),
            severity="success",
        )
    ]
    if car_loan.loan_principal > 0 and car_loan.interest_free_months > 0 and car_loan.interest_free_months < car_loan.total_months:
        events.append(
            PlanEventPoint(
                plan_variant=plan_variant,
                month=max(0, int(purchase_month + car_loan.interest_free_months)),
                category="loan",
                title=f"{title_prefix}贴息期结束",
                detail=(
                    f"贴息期内合同仍按等额本息推演，厂家/经销商累计贴息约 {_money_text(car_loan.total_interest_subsidy)}；"
                    f"贴息结束后家庭现金月供约 {_money_text(car_loan.later_phase_monthly_payment)}。"
                ),
                amount=round(car_loan.later_phase_monthly_payment, 2),
                severity="warning",
            )
        )
    if car_loan.loan_principal > 0:
        events.append(
            PlanEventPoint(
                plan_variant=plan_variant,
                month=max(0, int(purchase_month + car_loan.total_months)),
                category="loan",
                title=f"{title_prefix}贷款结清",
                detail="车贷结清后，现金流只保留电费、停车、年度保险和年度保养等持有成本。",
                amount=None,
                severity="success",
            )
        )
    update_month = vehicle_update_month(car_plan, purchase_month)
    if update_month is not None:
        events.append(
            PlanEventPoint(
                plan_variant=plan_variant,
                month=max(0, int(update_month)),
                category="vehicle",
                title=f"{title_prefix}更新/报废提醒",
                detail=(
                    f"按 {car_plan.vehicle_service_years} 年实际性能使用年限和 {round(car_plan.vehicle_retirement_mileage_km)} 公里阈值估算，"
                    "届时应重新评估置换预算和贷款策略。"
                ),
                amount=None,
                severity="warning",
            )
        )
    return events
