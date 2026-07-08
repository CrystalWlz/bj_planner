from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..schemas import DailyExpenseStageData, HouseholdData, RentExpenseStageData, RulePackData, ScheduledExpenseData
from .career import career_shock_self_payment_at_month
from .children import child_plan_monthly_expense_at
from .time import month_after, month_distance, parse_month


@dataclass(frozen=True)
class MonthlyHouseholdExpenseBreakdown:
    base_living_expense: float
    rent_cash_expense: float
    scheduled_expense: float
    medical_account_payable_expense: float
    child_expense: float
    career_shock_self_payment: float

    @property
    def total(self) -> float:
        return max(
            0.0,
            self.base_living_expense
            + self.rent_cash_expense
            + self.scheduled_expense
            + self.child_expense
            + self.career_shock_self_payment,
        )

    @property
    def cash_scheduled_expense(self) -> float:
        return max(0.0, self.scheduled_expense)


def scheduled_expense_occurs_in_month(item: ScheduledExpenseData, target_month: tuple[int, int]) -> bool:
    start_month = parse_month(item.start_month)
    end_month = parse_month(item.end_month) if item.end_month else None
    if start_month is None:
        return False
    if item.frequency == "one_time":
        resolved_month = scheduled_one_time_month(item, start_month, end_month)
        return resolved_month == target_month
    if month_distance(start_month, target_month) < 0:
        return False
    if end_month is not None and month_distance(target_month, end_month) < 0:
        return False
    if item.frequency == "annual_once" and target_month[1] != item.annual_occurrence_month:
        return False
    return True


def scheduled_one_time_month(
    item: ScheduledExpenseData,
    start_month: tuple[int, int],
    end_month: tuple[int, int] | None,
) -> tuple[int, int]:
    if item.one_time_timing_mode != "flexible_range":
        return start_month
    if end_month is None or month_distance(start_month, end_month) < 0:
        return start_month
    return end_month


def stage_at(
    stages: list[Any],
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> Any | None:
    current = as_of or date.today()
    target_month = month_after(current, max(0, months_from_now))
    for stage in sorted(stages, key=lambda item: item.start_month):
        start_month = parse_month(stage.start_month)
        end_month = parse_month(stage.end_month) if stage.end_month else None
        if start_month is None or month_distance(start_month, target_month) < 0:
            continue
        if end_month is not None and month_distance(target_month, end_month) < 0:
            continue
        return stage
    return None


def daily_expense_stage_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> DailyExpenseStageData | None:
    return stage_at(household.daily_expense_stages or [], months_from_now, as_of=as_of)


def rent_expense_stage_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> RentExpenseStageData | None:
    return stage_at(household.rent_expense_stages or [], months_from_now, as_of=as_of)


def base_living_expense_at(household: HouseholdData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    stage = daily_expense_stage_at(household, months_from_now, as_of=as_of)
    return max(0.0, stage.base_living_expense if stage else household.monthly_expense)


def regular_debt_payment_at(household: HouseholdData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    return max(0.0, household.monthly_debt_payment)


def rent_cash_payment_at(household: HouseholdData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    stage = rent_expense_stage_at(household, months_from_now, as_of=as_of)
    if not stage:
        return 0.0
    rent_cash_payment = rent_stage_payment_amount_at(stage, months_from_now, as_of=as_of) if stage.rent_payment_mode == "cash" else 0.0
    return rent_cash_payment + rent_stage_service_fee_at(stage, months_from_now, as_of=as_of) + rent_stage_broker_fee_at(stage, months_from_now, as_of=as_of)


def rent_provident_monthly_at(household: HouseholdData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    stage = rent_expense_stage_at(household, months_from_now, as_of=as_of)
    if not stage:
        return max(0.0, household.monthly_rent_from_housing_fund)
    if stage.rent_payment_mode != "provident":
        return 0.0
    return rent_stage_payment_amount_at(stage, months_from_now, as_of=as_of)


def rent_withdrawal_before_purchase(household: HouseholdData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    if household.existing_home_count > 0:
        return 0.0
    return rent_provident_monthly_at(household, months_from_now, as_of=as_of)


def quarterly_rent_withdrawal_before_purchase_at(
    household: HouseholdData,
    months_from_now: int,
    *,
    as_of: date | None = None,
) -> float:
    if household.existing_home_count > 0:
        return 0.0
    stage = rent_expense_stage_at(household, months_from_now, as_of=as_of)
    if stage and stage.rent_payment_mode == "provident":
        return rent_stage_payment_amount_at(stage, months_from_now, as_of=as_of)
    monthly_withdrawal = rent_provident_monthly_at(household, months_from_now, as_of=as_of)
    if monthly_withdrawal <= 0 or months_from_now <= 0 or months_from_now % 3 != 0:
        return 0.0
    return monthly_withdrawal * 3


def rent_stage_payment_amount_at(stage: RentExpenseStageData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    monthly_rent = max(0.0, stage.rent_amount)
    if monthly_rent <= 0:
        return 0.0
    if stage.rent_payment_frequency != "quarterly":
        return monthly_rent
    current = as_of or date.today()
    target_month = month_after(current, max(0, months_from_now))
    start_month = parse_month(stage.start_month)
    if start_month is None:
        return monthly_rent * 3
    elapsed = month_distance(start_month, target_month)
    return monthly_rent * 3 if elapsed >= 0 and elapsed % 3 == 0 else 0.0


def rent_stage_elapsed_months(stage: RentExpenseStageData, months_from_now: int = 0, *, as_of: date | None = None) -> int | None:
    current = as_of or date.today()
    target_month = month_after(current, max(0, months_from_now))
    start_month = parse_month(stage.start_month)
    if start_month is None:
        return None
    return month_distance(start_month, target_month)


def rent_stage_service_fee_at(stage: RentExpenseStageData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    rent_payment = rent_stage_payment_amount_at(stage, months_from_now, as_of=as_of)
    if rent_payment <= 0:
        return 0.0
    elapsed = rent_stage_elapsed_months(stage, months_from_now, as_of=as_of)
    if elapsed is None or elapsed < 0:
        return 0.0
    rate = stage.service_fee_first_year_rate if elapsed < 12 else stage.service_fee_later_year_rate
    return max(0.0, rent_payment * max(0.0, rate))


def rent_stage_broker_fee_at(stage: RentExpenseStageData, months_from_now: int = 0, *, as_of: date | None = None) -> float:
    elapsed = rent_stage_elapsed_months(stage, months_from_now, as_of=as_of)
    if elapsed != 0:
        return 0.0
    if stage.broker_fee_amount is not None:
        return max(0.0, stage.broker_fee_amount)
    return max(0.0, stage.rent_amount * stage.broker_fee_months)


def monthly_household_expense_breakdown_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
    rules: RulePackData | None = None,
    home_purchase_month: int | None = None,
) -> MonthlyHouseholdExpenseBreakdown:
    current = as_of or date.today()
    target_month = month_after(current, max(0, months_from_now))
    stage = daily_expense_stage_at(household, months_from_now, as_of=current)
    base_living_expense = stage.base_living_expense if stage else household.monthly_expense
    rent_cash_expense = rent_cash_payment_at(household, months_from_now, as_of=current)
    scheduled_total = 0.0
    medical_account_payable_total = 0.0
    for item in household.scheduled_expenses:
        if scheduled_expense_occurs_in_month(item, target_month):
            amount = max(0.0, float(item.monthly_amount))
            scheduled_total += amount
            if bool(getattr(item, "medical_account_payable", False)):
                medical_account_payable_total += amount
    child_expense = child_plan_monthly_expense_at(
        household,
        target_month,
        as_of=current,
        home_purchase_month=home_purchase_month,
        rules=rules,
    )
    career_shock_self_payment = (
        career_shock_self_payment_at_month(household, rules, months_from_now, as_of=current)
        if rules is not None
        else 0.0
    )
    return MonthlyHouseholdExpenseBreakdown(
        base_living_expense=max(0.0, base_living_expense),
        rent_cash_expense=max(0.0, rent_cash_expense),
        scheduled_expense=max(0.0, scheduled_total),
        medical_account_payable_expense=max(0.0, medical_account_payable_total),
        child_expense=max(0.0, child_expense),
        career_shock_self_payment=max(0.0, career_shock_self_payment),
    )


def monthly_household_expense_at(
    household: HouseholdData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
    rules: RulePackData | None = None,
    home_purchase_month: int | None = None,
) -> float:
    return monthly_household_expense_breakdown_at(
        household,
        months_from_now,
        as_of=as_of,
        rules=rules,
        home_purchase_month=home_purchase_month,
    ).total
