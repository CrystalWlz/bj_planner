from __future__ import annotations

from datetime import date

from ..domain.career import career_shock_settings_by_member, policy_retirement_age_for_member_with_rules
from ..domain.time import month_start_for_birth_month_or_age, months_between_months
from ..domain.vehicles import vehicle_update_month
from ..schemas import CarLoanSummary, CarPlanData, HouseholdData, PurchasePlanAnalysis, RulePackData

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


def retirement_tail_months(
    household: HouseholdData,
    *,
    rules: RulePackData,
    as_of: date | None = None,
) -> int:
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    targets: list[int] = []
    settings = career_shock_settings_by_member(household)
    for index, member in enumerate(household.members):
        setting = settings.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = setting.retirement_age if setting else policy_retirement_age_for_member_with_rules(member, index, rules)
        retirement_month = month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        targets.append(max(0, months_between_months(current_month, retirement_month)))
    # 至少覆盖最晚退休成员退休后 30 年，避免只看退休初期而漏掉长寿与晚年现金风险。
    return (max(targets) if targets else 0) + 360


def visualization_horizon_months(
    household: HouseholdData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    *,
    second_loan: CarLoanSummary | None = None,
    vehicle_states: list[VehicleLoanState] | None = None,
    as_of: date | None = None,
    rules: RulePackData,
) -> int:
    plan_horizons = [
        (plan.months_to_buy or 0)
        + max(
            plan.commercial_loan_years * 12 if plan.commercial_loan_amount > 0 else 0,
            plan.provident_loan_years * 12 if plan.provident_loan_amount > 0 else 0,
        )
        + 12
        for plan in purchase_plans
    ]
    vehicle_horizons = [
        max(
            (purchase_month or 0) + loan.total_months + 24,
            (vehicle_update_month(vehicle_plan, purchase_month) or 0) + 12,
        )
        for _, vehicle_plan, loan, purchase_month in (vehicle_states or [])
        if loan.enabled
    ]
    if not vehicle_horizons and car_loan.enabled:
        first_vehicle_start = car_loan.months_to_down_payment if car_loan.months_to_down_payment is not None else car_loan.purchase_delay_months
        vehicle_horizons.append(first_vehicle_start + car_loan.total_months + 24)
    if second_loan and second_loan.enabled:
        second_vehicle_start = second_loan.months_to_down_payment if second_loan.months_to_down_payment is not None else second_loan.purchase_delay_months
        vehicle_horizons.append(second_vehicle_start + second_loan.total_months + 24)
    return min(960, max(180, retirement_tail_months(household, rules=rules, as_of=as_of), *plan_horizons, *vehicle_horizons))
