from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from ..schemas import CarLoanSummary, CarPlanData, HouseholdData, PurchasePlanAnalysis, RulePackData, ScenarioData
from .vehicles import VehicleMonthProjection

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


class MemberIncomeRowsProvider(Protocol):
    def __call__(
        self,
        household: HouseholdData,
        rules: RulePackData,
        months_from_now: int,
        *,
        as_of: date | None = None,
    ) -> Sequence[tuple[int, str, object]]: ...


@dataclass
class MemberIncomeProjectionContext:
    household: HouseholdData
    rules: RulePackData
    base_month: date
    rows_provider: MemberIncomeRowsProvider
    _rows_cache: dict[int, list[tuple[int, str, object]]] = field(default_factory=dict)
    _profiles_by_member_cache: dict[int, dict[int, object]] = field(default_factory=dict)

    def rows_at_month(self, month: int) -> list[tuple[int, str, object]]:
        if month not in self._rows_cache:
            self._rows_cache[month] = list(
                self.rows_provider(
                    self.household,
                    self.rules,
                    month,
                    as_of=self.base_month,
                )
            )
        return self._rows_cache[month]

    def profiles_by_member_at(self, month: int) -> dict[int, object]:
        if month not in self._profiles_by_member_cache:
            self._profiles_by_member_cache[month] = {
                index: profile for index, _, profile in self.rows_at_month(month)
            }
        return self._profiles_by_member_cache[month]


@dataclass
class MonthlyLedgerProjectionContext:
    household: HouseholdData
    scenario: ScenarioData
    base_month: date
    selected_vehicle_states: list[VehicleLoanState] | None
    income_provider: Callable[[int], object]
    expense_provider: Callable[[int], object]
    vehicle_states_provider: Callable[[PurchasePlanAnalysis], list[VehicleLoanState]]
    vehicle_month_projection_provider: Callable[[list[VehicleLoanState], int], VehicleMonthProjection]
    _income_cache: dict[int, object] = field(default_factory=dict)
    _expense_cache: dict[int, object] = field(default_factory=dict)
    _vehicle_monthly_caches: dict[str, dict[int, VehicleMonthProjection]] = field(default_factory=dict)

    def income_at_month(self, month: int) -> object:
        if month not in self._income_cache:
            self._income_cache[month] = self.income_provider(month)
        return self._income_cache[month]

    def expense_breakdown_at_month(self, month: int) -> object:
        if month not in self._expense_cache:
            self._expense_cache[month] = self.expense_provider(month)
        return self._expense_cache[month]

    def plan_vehicle_states_at(
        self,
        plan: PurchasePlanAnalysis,
        selected_vehicle_states: list[VehicleLoanState] | None,
    ) -> list[VehicleLoanState]:
        return selected_vehicle_states if selected_vehicle_states is not None else self.vehicle_states_provider(plan)

    def vehicle_month_projection_at(
        self,
        plan: PurchasePlanAnalysis,
        plan_vehicle_states: list[VehicleLoanState],
        month: int,
    ) -> VehicleMonthProjection:
        vehicle_monthly_cache = self._vehicle_monthly_caches.setdefault(plan.variant, {})
        if month not in vehicle_monthly_cache:
            vehicle_monthly_cache[month] = self.vehicle_month_projection_provider(plan_vehicle_states, month)
        return vehicle_monthly_cache[month]
