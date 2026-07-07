from __future__ import annotations

from datetime import date
from math import ceil

from ..schemas import CarPlanData, RulePackData
from .time import add_months, month_distance, parse_year_month


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _money_text(amount: float) -> str:
    return f"{round(amount):,} 元".replace(",", "")


def policy_string_set(value: object, fallback: list[str]) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    return set(fallback)


def is_new_energy_vehicle(plan: CarPlanData, rules: RulePackData) -> bool:
    eligible_types = rules.params.get("new_energy_vehicle_types", ["pure_electric", "plug_in_hybrid", "range_extended", "fuel_cell"])
    if not isinstance(eligible_types, list):
        eligible_types = ["pure_electric", "plug_in_hybrid", "range_extended", "fuel_cell"]
    return bool(plan.new_energy_catalog_eligible) and str(plan.energy_type) in {str(item) for item in eligible_types}


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


def _whole_years_between(start_month: tuple[int, int] | None, end_month: tuple[int, int]) -> int:
    if start_month is None:
        return 0
    return max(0, month_distance(start_month, end_month) // 12)


def _indicator_applicant_label(value: str) -> str:
    return {
        "main": "主申请人",
        "spouse": "配偶",
        "child": "子女",
        "parent": "父母",
        "parent_in_law": "配偶父母",
        "other": "其他家庭申请人",
    }.get(value, "其他家庭申请人")


def _indicator_eligibility_label(value: str) -> str:
    return {
        "beijing_household": "北京户籍",
        "beijing_work_residence_permit": "北京工作居住证",
        "beijing_residence_permit_social_tax": "北京居住证+连续社保/个税",
        "active_military_or_police": "驻京现役军人/武警",
        "hongkong_macao_taiwan_foreign": "港澳台/外籍按规定居留",
        "unknown": "资格待确认",
    }.get(value, "资格待确认")


def _family_indicator_from_applicants(plan: CarPlanData) -> tuple[float, float, int, list[str]] | None:
    applicants = [item for item in plan.beijing_family_indicator_applicants if item.enabled]
    if not applicants:
        return None

    today = date.today()
    current_month = (today.year, today.month)
    default_start = parse_year_month(plan.beijing_family_indicator_application_start_month)
    weighted_points = 0.0
    weighted_annual_gain = 0.0
    generations = {item.generation for item in applicants}
    generation_multiplier = max(1, min(3, len(generations)))
    notes = [f"家庭指标按 {len(applicants)} 名申请人、{generation_multiplier} 代计算；仅参与指标算分的老人不会进入家庭现金流。"]

    for index, applicant in enumerate(applicants):
        relationship = str(applicant.relationship)
        is_main_or_spouse = relationship in {"main", "spouse"}
        weight = 2 if is_main_or_spouse else 1
        base_points = 2 if relationship == "main" else 1
        start_month = parse_year_month(applicant.family_application_start_month) or default_start
        family_years = _whole_years_between(start_month, current_month)
        history_points = 0.0
        if applicant.personal_history_points_override is not None:
            history_points = max(0.0, applicant.personal_history_points_override)
        else:
            if applicant.personal_indicator_history_type in {"ordinary_lottery", "both"}:
                history_points += max(0, applicant.ordinary_lottery_steps)
            if applicant.personal_indicator_history_type in {"new_energy_queue", "both"}:
                history_points += _whole_years_between(parse_year_month(applicant.new_energy_queue_start_month), start_month or current_month)
        subtotal = base_points + family_years + history_points
        weighted_points += subtotal * weight
        weighted_annual_gain += weight
        notes.append(
            f"{applicant.name or f'申请人{index + 1}'}（{_indicator_applicant_label(relationship)}，{_indicator_eligibility_label(str(applicant.eligibility_type))}）："
            f"基础 {base_points} 分、家庭申请满年 {family_years} 分、个人摇号/轮候历史 {history_points:.1f} 分，按权重 {weight} 计入。"
        )

    score = weighted_points * generation_multiplier
    annual_gain = weighted_annual_gain * generation_multiplier
    notes.append(f"当前家庭积分约 {score:.2f} 分；以后每满一年约增加 {annual_gain:.2f} 分。公式口径为：主申请人和配偶积分权重 2，其他申请人权重 1，再乘家庭代际数。")
    return score, annual_gain, generation_multiplier, notes


def beijing_family_indicator_projection(plan: CarPlanData, rules: RulePackData) -> tuple[float, int | None, list[str]]:
    if not plan.beijing_family_indicator_score_enabled:
        return 0.0, None, []
    applicant_projection = _family_indicator_from_applicants(plan)
    if applicant_projection is None:
        generation_multiplier = max(1, plan.beijing_family_indicator_generations)
        application_years = max(0, plan.beijing_family_indicator_application_years)
        main_points = max(0.0, plan.beijing_family_indicator_main_points) + application_years
        spouse_points = (
            max(0.0, plan.beijing_family_indicator_spouse_points) + application_years
            if plan.beijing_family_indicator_has_spouse
            else 0.0
        )
        other_count = max(0, plan.beijing_family_indicator_other_applicant_count)
        other_points = max(0.0, plan.beijing_family_indicator_other_points_total) + other_count * application_years
        spouse_weight = 2 if plan.beijing_family_indicator_has_spouse else 1
        score = max(0.0, ((main_points + spouse_points) * spouse_weight + other_points) * generation_multiplier)
        annual_gain = ((1 + (1 if plan.beijing_family_indicator_has_spouse else 0)) * spouse_weight + other_count) * generation_multiplier
        detail_notes = ["当前未配置家庭指标申请人明细，使用简化积分参数估算。"]
    else:
        score, annual_gain, generation_multiplier, detail_notes = applicant_projection
    cutoff = max(0.0, plan.beijing_family_indicator_current_cutoff_score)
    cutoff_growth = plan.beijing_family_indicator_cutoff_score_annual_change
    annual_quota = max(1, plan.beijing_family_indicator_annual_quota)
    reference_quota = max(1.0, float(rules.params.get("beijing_family_new_energy_reference_annual_quota", 119200)))
    quota_wait_factor = _clamp(reference_quota / annual_quota, 0.5, 3.0)
    wait_months: int | None
    if score >= cutoff:
        wait_months = 0
    else:
        effective_gain = annual_gain - cutoff_growth
        if effective_gain <= 0:
            wait_months = None
        else:
            years_to_cross = ceil((cutoff - score) / effective_gain * quota_wait_factor)
            today = date.today()
            base_year = max(today.year, plan.beijing_family_indicator_last_config_year)
            target_year = base_year + years_to_cross
            target_month = int(rules.params.get("beijing_family_new_energy_config_month", 5))
            wait_months = max(0, (target_year - today.year) * 12 + target_month - today.month)
    notes = [
        f"家庭新能源指标估算分数约 {score:.2f} 分；按最近入围分数 {cutoff:.2f}、年度新能源家庭指标约 {plan.beijing_family_indicator_annual_quota} 个估算。",
    ]
    notes.extend(detail_notes)
    if quota_wait_factor != 1:
        notes.append(f"年度指标量相对基准 {round(reference_quota)} 个做粗略校正，等待年限系数约 {quota_wait_factor:.2f}；实际仍以年度公告和家庭申请人分布为准。")
    if wait_months is None:
        notes.append("当前积分年增长不高于入围分年增长，无法可靠估计排到时间；请补充更准确的家庭积分或公告分数变化。")
    elif wait_months > 0:
        estimated_date = add_months(date.today().replace(day=1), wait_months)
        notes.append(f"按当前积分增长估计约 {wait_months} 个月后可能进入家庭新能源指标配置窗口，约为 {estimated_date.year} 年。")
    else:
        notes.append("当前估算分数已达到或超过最近入围分数，购车时间不额外等待家庭新能源指标。")
    return score, wait_months, notes


def vehicle_purchase_tax_and_relief(plan: CarPlanData, rules: RulePackData, purchase_month: int = 0) -> tuple[float, float]:
    taxable_price = max(0.0, plan.total_price) * float(rules.params.get("vehicle_purchase_tax_taxable_price_ratio", 1 / 1.13))
    gross_tax = taxable_price * float(rules.params.get("vehicle_purchase_tax_rate", 0.10))
    if not is_new_energy_vehicle(plan, rules):
        return gross_tax, 0.0
    today = date.today()
    purchase_date = add_months(date(today.year, today.month, 1), max(0, purchase_month))
    exempt_until = parse_year_month(str(rules.params.get("new_energy_vehicle_purchase_tax_exempt_until", "2025-12")))
    half_until = parse_year_month(str(rules.params.get("new_energy_vehicle_purchase_tax_half_until", "2027-12")))
    target = (purchase_date.year, purchase_date.month)
    if exempt_until is not None and month_distance(target, exempt_until) >= 0:
        relief = min(gross_tax, float(rules.params.get("new_energy_vehicle_purchase_tax_exemption_cap", 30000)))
        return max(0.0, gross_tax - relief), relief
    if half_until is not None and month_distance(target, half_until) >= 0:
        relief = min(gross_tax * 0.5, float(rules.params.get("new_energy_vehicle_purchase_tax_half_relief_cap", 15000)))
        return max(0.0, gross_tax - relief), relief
    return gross_tax, 0.0


def vehicle_vessel_tax_annual(plan: CarPlanData, rules: RulePackData) -> float:
    return vehicle_vessel_tax_annual_at(plan, rules, 0)


def vehicle_vessel_tax_annual_at(plan: CarPlanData, rules: RulePackData, month: int = 0) -> float:
    if plan.vehicle_vessel_tax_annual_override is not None:
        return max(0.0, plan.vehicle_vessel_tax_annual_override)
    passenger_not_taxable_types = rules.params.get("vehicle_vessel_tax_passenger_not_taxable_types", ["pure_electric", "fuel_cell"])
    if isinstance(passenger_not_taxable_types, list) and str(plan.energy_type) in {str(item) for item in passenger_not_taxable_types}:
        return 0.0
    exempt_types = rules.params.get("new_energy_vehicle_vessel_tax_exempt_types", ["pure_electric", "fuel_cell"])
    if isinstance(exempt_types, list) and str(plan.energy_type) in {str(item) for item in exempt_types}:
        return 0.0
    if str(plan.energy_type) in {"plug_in_hybrid", "range_extended"}:
        today = date.today()
        target_date = add_months(date(today.year, today.month, 1), max(0, month))
        exempt_until = parse_year_month(str(rules.params.get("plug_in_hybrid_vehicle_vessel_tax_exempt_until", "2026-12")))
        if exempt_until is not None and month_distance((target_date.year, target_date.month), exempt_until) >= 0:
            return 0.0
        return max(0.0, float(rules.params.get("plug_in_hybrid_vehicle_vessel_tax_annual", 0)))
    return max(0.0, float(rules.params.get("fuel_vehicle_vessel_tax_annual_default", 420)))


def vehicle_indicator_policy_notes(plan: CarPlanData, rules: RulePackData) -> list[str]:
    if not bool(rules.params.get("beijing_small_passenger_indicator_required", True)):
        return []
    status = str(plan.beijing_license_indicator_status or "unknown")
    energy_type = str(plan.energy_type)
    beijing_new_energy_types = policy_string_set(
        rules.params.get("beijing_new_energy_indicator_vehicle_types"),
        ["pure_electric"],
    )
    tail_restriction_exempt_types = policy_string_set(
        rules.params.get("beijing_tail_restriction_exempt_vehicle_types"),
        ["pure_electric"],
    )
    can_use_beijing_new_energy_indicator = energy_type in beijing_new_energy_types
    tail_restriction_exempt = energy_type in tail_restriction_exempt_types
    notes: list[str] = []
    if is_new_energy_vehicle(plan, rules) and not can_use_beijing_new_energy_indicator:
        notes.append("国家新能源购置税口径不等于北京新能源小客车指标口径；当前能源类型不按北京新能源指标车型处理。")
    if not tail_restriction_exempt:
        notes.append("当前能源类型不按北京纯电小客车尾号限行豁免口径处理，日常使用便利性和幸福指数应按普通小客车复核。")
    if status == "already_have":
        notes.append("已按拥有北京小客车指标处理，购车时间不再额外等待指标。")
        return notes
    if status == "family_new_energy_pending":
        if can_use_beijing_new_energy_indicator:
            notes.append("按北京家庭新能源指标等待处理；家庭积分优先于个人轮候，策略会叠加用户设定的预计等待月份。")
        else:
            notes.append("当前能源类型不能按北京家庭新能源指标上牌；请改选纯电车源、改为普通指标等待，或标记为已取得指标。")
        return notes
    if status == "personal_new_energy_pending":
        if can_use_beijing_new_energy_indicator:
            notes.append("按北京个人新能源指标轮候处理；个人轮候存在较长不确定性，策略会叠加用户设定的预计等待月份。")
        else:
            notes.append("当前能源类型不能按北京个人新能源指标上牌；请改选纯电车源、改为普通指标等待，或标记为已取得指标。")
        return notes
    if status == "ordinary_indicator_pending":
        notes.append("按北京普通小客车指标等待处理；策略会叠加用户设定的预计等待月份，实际取得时间仍有较大不确定性。")
        return notes
    if status == "not_eligible":
        notes.append("当前标记为不具备北京小客车指标资格，购车策略应视为存在上牌前置风险。")
        return notes
    notes.append("北京小客车上牌需要指标；当前未明确指标状态，建议在车辆需求里设置新能源指标、普通指标或已获指标。")
    return notes


def beijing_new_energy_indicator_eligible(plan: CarPlanData, rules: RulePackData) -> bool:
    beijing_new_energy_types = policy_string_set(
        rules.params.get("beijing_new_energy_indicator_vehicle_types"),
        ["pure_electric"],
    )
    return str(plan.energy_type) in beijing_new_energy_types


def vehicle_indicator_wait_months(plan: CarPlanData, rules: RulePackData, family_wait_months: int | None) -> int:
    if not bool(rules.params.get("beijing_small_passenger_indicator_required", True)):
        return 0
    if plan.license_plate_rental_enabled:
        return 0
    status = str(plan.beijing_license_indicator_status or "unknown")
    expected_delay = max(0, plan.beijing_indicator_expected_delay_months)
    if status == "already_have":
        return 0
    if status == "family_new_energy_pending" and beijing_new_energy_indicator_eligible(plan, rules):
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
        f"车辆购置税按不含增值税车价的 {float(rules.params.get('vehicle_purchase_tax_rate', 0.10)):.0%} 估算。"
    ]
    if relief > 0:
        notes.append(f"当前能源类型按新能源车政策减免购置税约 {_money_text(relief)}。")
    if annual_vehicle_vessel_tax <= 0:
        if str(plan.energy_type) in {"plug_in_hybrid", "range_extended"}:
            notes.append("车船税按购车月份仍处于新能源车船税优惠期估算为 0；2027 年起插混/增程等车型需按规则包或用户覆盖值复核。")
        else:
            notes.append("车船税按当前能源类型估算为 0；纯电动乘用车通常因无排量不进入车船税征税口径。")
    else:
        if str(plan.energy_type) in {"plug_in_hybrid", "range_extended"}:
            notes.append(f"年度车船税按 {_money_text(annual_vehicle_vessel_tax)} 估算，并在购车周年月进入现金流；2027 年起插混/增程等车型需按规则包或用户覆盖值复核。")
        else:
            notes.append(f"年度车船税按 {_money_text(annual_vehicle_vessel_tax)} 估算，并在购车周年月进入现金流。")
    notes.extend(vehicle_indicator_policy_notes(plan, rules))
    if plate_rental_initial_fee > 0:
        notes.append(
            f"租牌费用按上牌现金情景支出单独计入，首期 {_money_text(plate_rental_initial_fee)}、周期 {plan.license_plate_rental_term_months} 个月；该费用不计入车辆首付、贷款本金或车辆资产，合规和合同风险需单独复核。"
        )
        if plan.license_plate_rental_after_term_mode == "renew_until_own_indicator":
            notes.append(f"租牌到期后按每 {plan.license_plate_rental_renewal_term_months} 个月续租一次、每次 {_money_text(plan.license_plate_rental_renewal_fee)} 进入现金流，直到取得自有指标口径。")
        else:
            notes.append("租牌到期后按改用自有指标处理，后续不再自动计入续租费用。")
    notes.append(
        f"非营运小微型载客汽车通常没有固定强制报废年限；模型按用户设定的 {plan.vehicle_service_years} 年实际性能使用期和"
        f" {round(plan.vehicle_retirement_mileage_km)} 公里引导报废/更新阈值择早安排更新提醒，并从该月起停止车辆资产、"
        "电费、停车费、保险、保养和车船税测算；若贷款合同未结清，车贷仍会继续进入贷款现金流。"
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
