from __future__ import annotations

from math import ceil

from ..policy_explanations import market_assumption_note, policy_source_note, user_config_note
from ..policies import get_policy
from ..schemas import CarLoanSummary, CarPlanData, RulePackData
from .loans import vehicle_loan_projection


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _money_text(amount: float) -> str:
    return f"{round(amount):,} 元".replace(",", "")


def is_new_energy_vehicle(plan: CarPlanData, rules: RulePackData) -> bool:
    return get_policy(rules).is_new_energy_vehicle(plan)


def license_plate_rental_initial_fee(plan: CarPlanData) -> float:
    return max(0.0, plan.license_plate_rental_upfront_fee) if plan.license_plate_rental_enabled else 0.0


def license_plate_rental_payment_at(plan: CarPlanData, month: int, purchase_month: int | None) -> float:
    if not plan.license_plate_rental_enabled or purchase_month is None or month < purchase_month:
        return 0.0
    elapsed = month - purchase_month
    if elapsed == 0:
        return max(0.0, plan.license_plate_rental_upfront_fee)
    if plan.license_plate_rental_after_term_mode != "renew_until_own_indicator":
        return 0.0
    first_term = max(1, plan.license_plate_rental_term_months)
    renewal_term = max(1, plan.license_plate_rental_renewal_term_months)
    if elapsed < first_term:
        return 0.0
    if (elapsed - first_term) % renewal_term == 0:
        return max(0.0, plan.license_plate_rental_renewal_fee)
    return 0.0


def vehicle_update_month(plan: CarPlanData, purchase_month: int | None) -> int | None:
    if purchase_month is None:
        return None
    service_months = max(1, plan.vehicle_service_years) * 12
    mileage_months = ceil(max(1.0, plan.vehicle_retirement_mileage_km) / max(plan.annual_mileage_km, 1) * 12)
    return purchase_month + min(service_months, mileage_months)


def beijing_family_indicator_projection(plan: CarPlanData, rules: RulePackData) -> tuple[float, int | None, list[str]]:
    if not plan.beijing_family_indicator_score_enabled:
        return 0.0, None, []
    policy = get_policy(rules)
    projection = policy.beijing_family_new_energy_projection(plan)
    return projection.score, projection.wait_months, projection.notes


def vehicle_purchase_tax_and_relief(plan: CarPlanData, rules: RulePackData, purchase_month: int = 0) -> tuple[float, float]:
    return get_policy(rules).vehicle_purchase_tax_and_relief(plan, purchase_month=purchase_month)


def vehicle_vessel_tax_annual(plan: CarPlanData, rules: RulePackData) -> float:
    return vehicle_vessel_tax_annual_at(plan, rules, 0)


def vehicle_vessel_tax_annual_at(plan: CarPlanData, rules: RulePackData, month: int = 0) -> float:
    if plan.vehicle_vessel_tax_annual_override is not None:
        return max(0.0, plan.vehicle_vessel_tax_annual_override)
    return get_policy(rules).vehicle_vessel_tax_annual_at(plan, month=month)


def vehicle_indicator_policy_notes(plan: CarPlanData, rules: RulePackData) -> list[str]:
    policy = get_policy(rules)
    if not policy.beijing_small_passenger_indicator_required():
        return []
    status = str(plan.beijing_license_indicator_status or "unknown")
    can_use_beijing_new_energy_indicator = policy.beijing_new_energy_indicator_eligible(plan)
    tail_restriction_exempt = policy.beijing_tail_restriction_exempt(plan)
    notes: list[str] = []
    if is_new_energy_vehicle(plan, rules) and not can_use_beijing_new_energy_indicator:
        notes.append(policy_source_note("国家新能源购置税口径不等于北京新能源小客车指标口径；当前能源类型不按北京新能源指标车型处理。"))
    if not tail_restriction_exempt:
        notes.append(policy_source_note("当前能源类型不按北京纯电小客车尾号限行豁免口径处理，日常使用便利性和幸福指数应按普通小客车复核。"))
    if status == "already_have":
        notes.append(user_config_note("已按拥有北京小客车指标处理，购车时间不再额外等待指标。"))
        return notes
    if status == "family_new_energy_pending":
        if can_use_beijing_new_energy_indicator:
            notes.append(policy_source_note("按北京家庭新能源指标等待处理；家庭积分优先于个人轮候，策略会叠加用户设定的预计等待月份。"))
        else:
            notes.append(policy_source_note("当前能源类型不能按北京家庭新能源指标上牌；请改选纯电车源、改为普通指标等待，或标记为已取得指标。"))
        return notes
    if status == "personal_new_energy_pending":
        if can_use_beijing_new_energy_indicator:
            notes.append(policy_source_note("按北京个人新能源指标轮候处理；个人轮候存在较长不确定性，策略会叠加用户设定的预计等待月份。"))
        else:
            notes.append(policy_source_note("当前能源类型不能按北京个人新能源指标上牌；请改选纯电车源、改为普通指标等待，或标记为已取得指标。"))
        return notes
    if status == "ordinary_indicator_pending":
        notes.append(policy_source_note("按北京普通小客车指标等待处理；策略会叠加用户设定的预计等待月份，实际取得时间仍有较大不确定性。"))
        return notes
    if status == "not_eligible":
        notes.append(user_config_note("当前标记为不具备北京小客车指标资格，购车策略应视为存在上牌前置风险。"))
        return notes
    notes.append(policy_source_note("北京小客车上牌需要指标；当前未明确指标状态，建议在车辆需求里设置新能源指标、普通指标或已获指标。"))
    return notes


def beijing_new_energy_indicator_eligible(plan: CarPlanData, rules: RulePackData) -> bool:
    return get_policy(rules).beijing_new_energy_indicator_eligible(plan)


def vehicle_indicator_wait_months(plan: CarPlanData, rules: RulePackData, family_wait_months: int | None) -> int:
    policy = get_policy(rules)
    if not policy.beijing_small_passenger_indicator_required():
        return 0
    if plan.license_plate_rental_enabled:
        return 0
    status = str(plan.beijing_license_indicator_status or "unknown")
    expected_delay = max(0, plan.beijing_indicator_expected_delay_months)
    if status == "already_have":
        return 0
    if status == "family_new_energy_pending" and policy.beijing_new_energy_indicator_eligible(plan):
        if family_wait_months is None:
            return expected_delay
        return max(expected_delay, max(0, family_wait_months))
    if status in {"personal_new_energy_pending", "ordinary_indicator_pending"}:
        return expected_delay
    return expected_delay


def vehicle_purchase_policy_amounts(plan: CarPlanData, rules: RulePackData, purchase_month: int = 0) -> dict[str, object]:
    purchase_tax, relief = vehicle_purchase_tax_and_relief(plan, rules, purchase_month)
    annual_vehicle_vessel_tax = vehicle_vessel_tax_annual_at(plan, rules, purchase_month)
    family_score, family_wait_months, family_notes = beijing_family_indicator_projection(plan, rules)
    plate_rental_initial_fee = license_plate_rental_initial_fee(plan)
    notes = [
        policy_source_note(f"车辆购置税按不含增值税车价的 {get_policy(rules).vehicle_purchase_tax_rate():.0%} 估算。")
    ]
    if relief > 0:
        notes.append(policy_source_note(f"当前能源类型按新能源车政策减免购置税约 {_money_text(relief)}。"))
    if annual_vehicle_vessel_tax <= 0:
        if str(plan.energy_type) in {"plug_in_hybrid", "range_extended"}:
            notes.append(policy_source_note("车船税按购车月份仍处于新能源车船税优惠期估算为 0；2027 年起插混/增程等车型需按规则包或用户覆盖值复核。"))
        else:
            notes.append(policy_source_note("车船税按当前能源类型估算为 0；纯电动乘用车通常因无排量不进入车船税征税口径。"))
    else:
        if str(plan.energy_type) in {"plug_in_hybrid", "range_extended"}:
            notes.append(policy_source_note(f"年度车船税按 {_money_text(annual_vehicle_vessel_tax)} 估算，并在购车周年月进入现金流；2027 年起插混/增程等车型需按规则包或用户覆盖值复核。"))
        else:
            notes.append(policy_source_note(f"年度车船税按 {_money_text(annual_vehicle_vessel_tax)} 估算，并在购车周年月进入现金流。"))
    notes.extend(vehicle_indicator_policy_notes(plan, rules))
    if plate_rental_initial_fee > 0:
        notes.append(
            user_config_note(f"租牌费用按上牌现金情景支出单独计入，首期 {_money_text(plate_rental_initial_fee)}、周期 {plan.license_plate_rental_term_months} 个月；该费用不计入车辆首付、贷款本金或车辆资产，合规和合同风险需单独复核。")
        )
        if plan.license_plate_rental_after_term_mode == "renew_until_own_indicator":
            notes.append(user_config_note(f"租牌到期后按每 {plan.license_plate_rental_renewal_term_months} 个月续租一次、每次 {_money_text(plan.license_plate_rental_renewal_fee)} 进入现金流，直到取得自有指标口径。"))
        else:
            notes.append(user_config_note("租牌到期后按改用自有指标处理，后续不再自动计入续租费用。"))
    notes.append(
        market_assumption_note(
            f"非营运小微型载客汽车通常没有固定强制报废年限；模型按用户设定的 {plan.vehicle_service_years} 年实际性能使用期和"
            f" {round(plan.vehicle_retirement_mileage_km)} 公里引导报废/更新阈值择早安排更新提醒，并从该月起停止车辆资产、"
            "电费、停车费、保险、保养和车船税测算；若贷款合同未结清，车贷仍会继续进入贷款现金流。"
        )
    )
    notes.extend(family_notes)
    return {
        "purchase_tax": purchase_tax,
        "purchase_tax_relief": relief,
        "annual_vehicle_vessel_tax": annual_vehicle_vessel_tax,
        "license_plate_rental_initial_fee": plate_rental_initial_fee,
        "beijing_family_indicator_score": family_score,
        "beijing_family_indicator_estimated_wait_months": family_wait_months,
        "policy_notes": notes,
    }


def estimate_car_operating_cost(plan: CarPlanData) -> dict[str, float]:
    monthly_energy = plan.annual_mileage_km / 100 * plan.electricity_kwh_per_100km * plan.electricity_price_per_kwh / 12
    annual_insurance = max(plan.annual_insurance_min, plan.total_price * plan.annual_insurance_rate)
    monthly_insurance = annual_insurance / 12
    monthly_maintenance = plan.annual_maintenance_cost / 12
    monthly_parking = plan.monthly_parking_cost
    monthly_cash = monthly_energy + monthly_insurance + monthly_maintenance + monthly_parking
    monthly_depreciation = plan.total_price / max(1, plan.depreciation_years * 12)
    return {
        "monthly_energy_cost": round(monthly_energy, 2),
        "monthly_insurance_cost": round(monthly_insurance, 2),
        "monthly_maintenance_cost": round(monthly_maintenance, 2),
        "monthly_parking_cost": round(monthly_parking, 2),
        "monthly_cash_operating_cost": round(monthly_cash, 2),
        "monthly_depreciation_cost": round(monthly_depreciation, 2),
        "monthly_total_ownership_cost": round(monthly_cash + monthly_depreciation, 2),
    }


def calculate_car_loan_summary(
    plan: CarPlanData,
    *,
    initial_cash: float = 0,
    monthly_cash_savings_before_car: float = 0,
    rules: RulePackData,
) -> CarLoanSummary:
    purchase_policy = vehicle_purchase_policy_amounts(plan, rules, plan.purchase_delay_months)
    down_payment = max(0, plan.total_price * plan.down_payment_ratio)
    months_to_down: int | None
    if not plan.enabled or down_payment <= 0:
        months_to_down = 0
    elif initial_cash >= down_payment:
        months_to_down = 0
    elif monthly_cash_savings_before_car <= 0:
        months_to_down = None
    else:
        months_to_down = int((down_payment - initial_cash + monthly_cash_savings_before_car - 1) // monthly_cash_savings_before_car)
    if months_to_down is not None:
        months_to_down = max(plan.purchase_delay_months, months_to_down)

    if not plan.enabled or plan.total_price <= 0:
        operating_cost = estimate_car_operating_cost(plan)
        return CarLoanSummary(
            enabled=False,
            total_price=round(plan.total_price, 2),
            down_payment_ratio=plan.down_payment_ratio,
            down_payment=round(down_payment, 2),
            purchase_tax=round(purchase_policy["purchase_tax"], 2),
            purchase_tax_relief=round(purchase_policy["purchase_tax_relief"], 2),
            annual_vehicle_vessel_tax=round(purchase_policy["annual_vehicle_vessel_tax"], 2),
            license_plate_rental_initial_fee=round(purchase_policy["license_plate_rental_initial_fee"], 2),
            beijing_family_indicator_score=round(purchase_policy["beijing_family_indicator_score"], 2),
            beijing_family_indicator_estimated_wait_months=purchase_policy["beijing_family_indicator_estimated_wait_months"],
            purchase_delay_months=plan.purchase_delay_months,
            loan_principal=0,
            months_to_down_payment=months_to_down,
            years_to_down_payment=round(months_to_down / 12, 1) if months_to_down is not None else None,
            first_phase_monthly_payment=0,
            later_phase_monthly_payment=0,
            contract_monthly_payment=0,
            first_phase_interest_subsidy=0,
            total_interest_subsidy=0,
            borrower_total_interest=0,
            current_monthly_payment=0,
            prepayment_allowed=plan.selected_financing_prepayment_allowed,
            prepayment_enabled=False,
            prepayment_start_month=max(1, plan.loan_prepayment_start_month, plan.loan_prepayment_allowed_after_month),
            prepayment_allowed_after_month=max(1, plan.loan_prepayment_allowed_after_month),
            prepayment_monthly_amount=0,
            prepayment_strategy_type="none",
            prepayment_lump_sum_month=0,
            prepayment_lump_sum_amount=0,
            prepayment_total_extra_principal=0,
            prepayment_net_benefit=0,
            prepayment_explanation="当前不形成车贷，不安排提前还本。",
            actual_payoff_months=0,
            interest_saved_by_prepayment=0,
            total_interest=0,
            total_months=plan.total_months,
            interest_free_months=plan.interest_free_months,
            later_annual_rate=plan.later_annual_rate,
            policy_notes=purchase_policy["policy_notes"],
            **operating_cost,
        )

    total_months = max(1, plan.total_months)
    interest_free_months = max(0, min(plan.interest_free_months, total_months))
    principal = max(0, plan.total_price - down_payment)

    prepayment_monthly_amount = (
        max(0.0, plan.loan_prepayment_monthly_amount)
        if plan.loan_prepayment_enabled and plan.selected_financing_prepayment_allowed
        else 0.0
    )
    prepayment_allowed_after_month = (
        max(1, min(total_months, plan.loan_prepayment_allowed_after_month))
        if plan.selected_financing_prepayment_allowed
        else 1
    )
    prepayment_start_month = max(
        prepayment_allowed_after_month,
        max(1, min(total_months, plan.loan_prepayment_start_month)),
    )
    prepayment_lump_sum_amount = (
        max(0.0, plan.loan_prepayment_lump_sum_amount)
        if plan.loan_prepayment_enabled and plan.selected_financing_prepayment_allowed
        else 0.0
    )
    prepayment_lump_sum_month = (
        max(prepayment_allowed_after_month, min(total_months, plan.loan_prepayment_lump_sum_month))
        if plan.loan_prepayment_enabled and prepayment_lump_sum_amount > 0 and plan.loan_prepayment_lump_sum_month > 0
        else 0
    )
    loan_projection = vehicle_loan_projection(
        principal,
        total_months,
        interest_free_months,
        plan.later_annual_rate,
        prepayment_monthly_amount=prepayment_monthly_amount,
        prepayment_start_month=prepayment_start_month,
        prepayment_lump_sum_amount=prepayment_lump_sum_amount,
        prepayment_lump_sum_month=prepayment_lump_sum_month,
    )
    first_point = loan_projection.points[0] if loan_projection.points else None
    first_after_subsidy_point = (
        loan_projection.points[interest_free_months]
        if interest_free_months < len(loan_projection.points)
        else first_point
    )
    first_phase_monthly = first_point.contract_payment if first_point else 0.0
    later_monthly = first_after_subsidy_point.contract_payment if first_after_subsidy_point else 0.0
    contract_monthly_payment = first_point.gross_contract_payment if first_point else 0.0
    first_phase_interest_subsidy = first_point.interest_subsidy if first_point else 0.0

    current_month = max(1, min(plan.current_month_index, total_months))
    if plan.purchase_delay_months > 0:
        current_monthly = 0.0
    else:
        current_point = loan_projection.points[current_month - 1] if current_month <= len(loan_projection.points) else None
        current_monthly = current_point.contract_payment if current_point else 0.0

    operating_cost = estimate_car_operating_cost(plan)
    return CarLoanSummary(
        enabled=True,
        total_price=round(plan.total_price, 2),
        down_payment_ratio=plan.down_payment_ratio,
        down_payment=round(down_payment, 2),
        purchase_tax=round(purchase_policy["purchase_tax"], 2),
        purchase_tax_relief=round(purchase_policy["purchase_tax_relief"], 2),
        annual_vehicle_vessel_tax=round(purchase_policy["annual_vehicle_vessel_tax"], 2),
        license_plate_rental_initial_fee=round(purchase_policy["license_plate_rental_initial_fee"], 2),
        beijing_family_indicator_score=round(purchase_policy["beijing_family_indicator_score"], 2),
        beijing_family_indicator_estimated_wait_months=purchase_policy["beijing_family_indicator_estimated_wait_months"],
        purchase_delay_months=plan.purchase_delay_months,
        loan_principal=round(principal, 2),
        months_to_down_payment=months_to_down,
        years_to_down_payment=round(months_to_down / 12, 1) if months_to_down is not None else None,
        first_phase_monthly_payment=round(first_phase_monthly, 2),
        later_phase_monthly_payment=round(later_monthly, 2),
        contract_monthly_payment=round(contract_monthly_payment, 2),
        first_phase_interest_subsidy=round(first_phase_interest_subsidy, 2),
        total_interest_subsidy=round(loan_projection.total_interest_subsidy, 2),
        borrower_total_interest=round(loan_projection.total_interest, 2),
        current_monthly_payment=round(current_monthly, 2),
        prepayment_allowed=plan.selected_financing_prepayment_allowed,
        prepayment_enabled=prepayment_monthly_amount > 0 or prepayment_lump_sum_amount > 0,
        prepayment_start_month=prepayment_start_month,
        prepayment_allowed_after_month=prepayment_allowed_after_month,
        prepayment_monthly_amount=round(prepayment_monthly_amount, 2),
        prepayment_strategy_type=plan.loan_prepayment_strategy_type if prepayment_monthly_amount > 0 or prepayment_lump_sum_amount > 0 else "none",
        prepayment_lump_sum_month=prepayment_lump_sum_month,
        prepayment_lump_sum_amount=round(prepayment_lump_sum_amount, 2),
        prepayment_total_extra_principal=round(
            sum(point.extra_principal_payment for point in loan_projection.points),
            2,
        ),
        prepayment_net_benefit=round(loan_projection.interest_saved_by_prepayment, 2),
        prepayment_explanation=(
            "按车辆需求中设置的提前还本参数推演。"
            if plan.selected_financing_prepayment_allowed
            else (plan.selected_financing_prepayment_policy_note or "当前金融方案不允许提前还本。")
        ),
        actual_payoff_months=loan_projection.actual_payoff_months,
        interest_saved_by_prepayment=round(loan_projection.interest_saved_by_prepayment, 2),
        total_interest=round(loan_projection.total_interest, 2),
        total_months=total_months,
        interest_free_months=interest_free_months,
        later_annual_rate=plan.later_annual_rate,
        policy_notes=purchase_policy["policy_notes"],
        **operating_cost,
    )
