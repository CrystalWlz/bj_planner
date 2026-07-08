from __future__ import annotations

from dataclasses import dataclass

from ..domain.loans import vehicle_loan_point_after_payments
from ..domain.vehicles import license_plate_rental_payment_at, vehicle_update_month
from ..schemas import CarLoanSummary, CarPlanData

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


@dataclass(frozen=True)
class VehicleMonthProjection:
    total_cash_cost: float
    first_down_payment: float
    extra_down_payment: float
    total_down_payment: float
    plate_rental_payment: float
    no_car_commute_cost: float
    components_by_index: dict[int, dict[str, float]]
    first_asset_value: float
    extra_asset_value: float
    total_asset_value: float


def no_car_commute_cost(plan: CarPlanData) -> float:
    return max(0.0, plan.no_car_monthly_commute_cost)


def car_monthly_cash_cost_without_annual(loan: CarLoanSummary) -> float:
    return max(0.0, loan.monthly_energy_cost + loan.monthly_parking_cost)


def car_annual_cash_cost_at(
    loan: CarLoanSummary,
    plan: CarPlanData,
    month: int,
    purchase_month: int | None,
) -> float:
    if purchase_month is None:
        return 0.0
    owning_year = max(0, (month - purchase_month) // 12)
    insurance_growth = (1 + max(0.0, plan.annual_insurance_growth_rate)) ** owning_year
    maintenance_growth = (1 + max(0.0, plan.annual_maintenance_growth_rate)) ** owning_year
    annual_insurance = max(0.0, loan.monthly_insurance_cost * 12) * insurance_growth
    annual_maintenance = max(0.0, loan.monthly_maintenance_cost * 12) * maintenance_growth
    annual_vehicle_vessel_tax = max(0.0, loan.annual_vehicle_vessel_tax)
    return annual_insurance + annual_maintenance + annual_vehicle_vessel_tax


def is_car_annual_cost_month(month: int, purchase_month: int | None) -> bool:
    if purchase_month is None or month < purchase_month:
        return False
    return (month - purchase_month) % 12 == 0


def vehicle_is_in_service(plan: CarPlanData, purchase_month: int | None, month: int) -> bool:
    if purchase_month is None or month < purchase_month:
        return False
    update_month = vehicle_update_month(plan, purchase_month)
    return update_month is None or month < update_month


def car_monthly_cash_cost_at(
    plan: CarPlanData,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState],
) -> float:
    commute_cost = no_car_commute_cost(plan)
    if not vehicle_states:
        return commute_cost
    first_purchase_month = min((purchase_month for _, _, _, purchase_month in vehicle_states if purchase_month is not None), default=None)
    total = commute_cost if first_purchase_month is None or month < first_purchase_month else 0.0
    any_vehicle_in_service = False
    for _, vehicle_plan, loan, purchase_month in vehicle_states:
        if purchase_month is None or month < purchase_month:
            continue
        month_after_car = month - purchase_month
        payment = 0.0
        if month_after_car > 0:
            _, contract_payment, extra_payment = vehicle_loan_point_after_payments(loan, month_after_car)
            payment = contract_payment + extra_payment
        in_service = vehicle_is_in_service(vehicle_plan, purchase_month, month)
        any_vehicle_in_service = any_vehicle_in_service or in_service
        annual_cost = (
            car_annual_cash_cost_at(loan, vehicle_plan, month, purchase_month)
            if in_service and is_car_annual_cost_month(month, purchase_month)
            else 0.0
        )
        plate_rental_payment = license_plate_rental_payment_at(vehicle_plan, month, purchase_month) if in_service else 0.0
        total += payment + (car_monthly_cash_cost_without_annual(loan) if in_service else 0.0) + annual_cost + plate_rental_payment
    if first_purchase_month is not None and month >= first_purchase_month and not any_vehicle_in_service:
        total += commute_cost
    return total


def car_down_payment_at(
    month: int,
    *,
    vehicle_states: list[VehicleLoanState],
) -> float:
    total = 0.0
    for _, _, loan, purchase_month in vehicle_states:
        if loan.enabled and purchase_month == month:
            total += loan.down_payment
    return total


def vehicle_asset_value_at(price: float, depreciation_years: int, purchase_month: int | None, month: int) -> float:
    if purchase_month is None or month < purchase_month or price <= 0:
        return 0.0
    depreciation_months = max(12, depreciation_years * 12)
    age_months = max(0, month - purchase_month)
    return max(0.0, price * (1 - age_months / depreciation_months))


def vehicle_in_service_asset_value_at(
    plan: CarPlanData,
    price: float,
    purchase_month: int | None,
    month: int,
) -> float:
    if not vehicle_is_in_service(plan, purchase_month, month):
        return 0.0
    return vehicle_asset_value_at(price, plan.depreciation_years, purchase_month, month)


def vehicle_cash_components_at(
    loan: CarLoanSummary,
    plan: CarPlanData,
    month: int,
    purchase_month: int | None,
) -> dict[str, float]:
    if purchase_month is None or month < purchase_month:
        return {
            "payment": 0.0,
            "energy": 0.0,
            "insurance": 0.0,
            "maintenance": 0.0,
            "parking": 0.0,
            "plate_rental": 0.0,
        }
    elapsed = month - purchase_month
    payment = 0.0
    if elapsed > 0:
        _, contract_payment, extra_payment = vehicle_loan_point_after_payments(loan, elapsed)
        payment = contract_payment + extra_payment
    if not vehicle_is_in_service(plan, purchase_month, month):
        return {
            "payment": payment,
            "energy": 0.0,
            "insurance": 0.0,
            "maintenance": 0.0,
            "parking": 0.0,
            "plate_rental": 0.0,
        }
    annual_cost = (
        car_annual_cash_cost_at(loan, plan, month, purchase_month)
        if is_car_annual_cost_month(month, purchase_month)
        else 0.0
    )
    base_annual = (
        max(0.0, loan.monthly_insurance_cost * 12)
        + max(0.0, loan.monthly_maintenance_cost * 12)
        + max(0.0, loan.annual_vehicle_vessel_tax)
    )
    insurance = 0.0
    maintenance = 0.0
    if annual_cost > 0 and base_annual > 0:
        insurance = annual_cost * max(0.0, loan.monthly_insurance_cost * 12) / base_annual
        maintenance = max(0.0, annual_cost - insurance)
    return {
        "payment": payment,
        "energy": loan.monthly_energy_cost,
        "insurance": insurance,
        "maintenance": maintenance,
        "parking": loan.monthly_parking_cost,
        "plate_rental": license_plate_rental_payment_at(plan, month, purchase_month),
    }


def car_down_payment_components_at(
    month: int,
    *,
    vehicle_states: list[VehicleLoanState],
) -> tuple[float, float]:
    first = 0.0
    extra = 0.0
    for index, _, loan, purchase_month in vehicle_states:
        if not loan.enabled or purchase_month != month:
            continue
        transaction_cash = loan.down_payment + loan.purchase_tax
        if index == 0:
            first += transaction_cash
        else:
            extra += transaction_cash
    return first, extra


def build_vehicle_month_projection(
    plan: CarPlanData,
    month: int,
    *,
    vehicle_states: list[VehicleLoanState],
) -> VehicleMonthProjection:
    first_purchase_month = min(
        (purchase_month for _, _, _, purchase_month in vehicle_states if purchase_month is not None),
        default=None,
    )
    vehicle_total = car_monthly_cash_cost_at(
        plan,
        month,
        vehicle_states=vehicle_states,
    )
    components_by_index = {
        vehicle_index: vehicle_cash_components_at(vehicle_loan, vehicle_plan, month, vehicle_purchase_month)
        for vehicle_index, vehicle_plan, vehicle_loan, vehicle_purchase_month in vehicle_states
    }
    first_down, extra_down = car_down_payment_components_at(
        month,
        vehicle_states=vehicle_states,
    )
    first_asset = 0.0
    extra_asset = 0.0
    plate_rental_payment = 0.0
    any_vehicle_in_service = False
    for vehicle_index, vehicle_plan, vehicle_loan, vehicle_purchase_month in vehicle_states:
        in_service = vehicle_is_in_service(vehicle_plan, vehicle_purchase_month, month)
        any_vehicle_in_service = any_vehicle_in_service or in_service
        plate_rental_payment += (
            license_plate_rental_payment_at(vehicle_plan, month, vehicle_purchase_month)
            if in_service
            else 0.0
        )
        asset_value = vehicle_in_service_asset_value_at(
            vehicle_plan,
            vehicle_loan.total_price if vehicle_loan.enabled else 0.0,
            vehicle_purchase_month,
            month,
        )
        if vehicle_index == 0:
            first_asset += asset_value
        else:
            extra_asset += asset_value
    commute_cost = (
        no_car_commute_cost(plan)
        if (
            first_purchase_month is None
            or month < first_purchase_month
            or (first_purchase_month is not None and month >= first_purchase_month and not any_vehicle_in_service)
        )
        else 0.0
    )
    return VehicleMonthProjection(
        total_cash_cost=vehicle_total,
        first_down_payment=first_down,
        extra_down_payment=extra_down,
        total_down_payment=first_down + extra_down,
        plate_rental_payment=plate_rental_payment,
        no_car_commute_cost=commute_cost,
        components_by_index=components_by_index,
        first_asset_value=first_asset,
        extra_asset_value=extra_asset,
        total_asset_value=first_asset + extra_asset,
    )
