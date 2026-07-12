from __future__ import annotations

from ..schemas import SocialSecurityVisualizationPoint
from .ledger_models import (
    FixedAssetProjection,
    HouseholdExpenseProjection,
    ProjectionOffsets,
    VehicleCashBreakdown,
)


def household_expense_projection_from_breakdown(
    *,
    base_living_expense: float,
    rent_cash_expense: float,
    scheduled_expense: float,
    child_expense: float,
    career_shock_self_payment: float,
    social_security_point: SocialSecurityVisualizationPoint | None,
) -> HouseholdExpenseProjection:
    medical_account_healthcare_payment = (
        social_security_point.medical_healthcare_outflow
        if social_security_point
        else 0.0
    )
    medical_account_mutual_aid_payment = (
        social_security_point.medical_mutual_aid_outflow
        if social_security_point
        else 0.0
    )
    pension_account_payout = (
        social_security_point.pension_account_payout
        if social_security_point
        else 0.0
    )
    living_expense = base_living_expense
    cash_scheduled_expense = max(0.0, rent_cash_expense + scheduled_expense - medical_account_healthcare_payment)
    total_expense = max(
        0.0,
        living_expense + cash_scheduled_expense + child_expense + career_shock_self_payment,
    )
    return HouseholdExpenseProjection(
        living_expense=living_expense,
        scheduled_expense=cash_scheduled_expense,
        child_expense=child_expense,
        career_shock_self_payment=career_shock_self_payment,
        total_expense=total_expense,
        pension_account_payout=pension_account_payout,
        medical_account_healthcare_payment=medical_account_healthcare_payment,
        medical_account_mutual_aid_payment=medical_account_mutual_aid_payment,
    )


def vehicle_cash_breakdown_from_projection(
    *,
    vehicle_total: float,
    loan_vehicle_payment: float,
    components_by_index: dict[int, dict[str, float]],
    no_car_commute_cost: float,
    first_down_payment: float,
    extra_down_payment: float,
    total_down_payment: float,
    plate_rental_payment: float,
) -> VehicleCashBreakdown:
    vehicle_payment = min(vehicle_total, loan_vehicle_payment)
    vehicle_operating_cost = max(0.0, vehicle_total - vehicle_payment)
    first_vehicle_payment = 0.0
    second_vehicle_payment = 0.0
    first_vehicle_energy_cost = 0.0
    first_vehicle_insurance_cost = 0.0
    first_vehicle_maintenance_cost = 0.0
    first_vehicle_parking_cost = 0.0
    second_vehicle_energy_cost = 0.0
    second_vehicle_insurance_cost = 0.0
    second_vehicle_maintenance_cost = 0.0
    second_vehicle_parking_cost = 0.0
    for vehicle_index, components in components_by_index.items():
        if vehicle_index == 0:
            first_vehicle_payment += components["payment"]
            first_vehicle_energy_cost += components["energy"]
            first_vehicle_insurance_cost += components["insurance"]
            first_vehicle_maintenance_cost += components["maintenance"]
            first_vehicle_parking_cost += components["parking"]
        else:
            second_vehicle_payment += components["payment"]
            second_vehicle_energy_cost += components["energy"]
            second_vehicle_insurance_cost += components["insurance"]
            second_vehicle_maintenance_cost += components["maintenance"]
            second_vehicle_parking_cost += components["parking"]
    return VehicleCashBreakdown(
        vehicle_total=vehicle_total,
        vehicle_payment=vehicle_payment,
        first_vehicle_payment=first_vehicle_payment,
        second_vehicle_payment=second_vehicle_payment,
        vehicle_operating_cost=vehicle_operating_cost,
        first_vehicle_energy_cost=first_vehicle_energy_cost,
        first_vehicle_insurance_cost=first_vehicle_insurance_cost,
        first_vehicle_maintenance_cost=first_vehicle_maintenance_cost,
        first_vehicle_parking_cost=first_vehicle_parking_cost,
        second_vehicle_energy_cost=second_vehicle_energy_cost,
        second_vehicle_insurance_cost=second_vehicle_insurance_cost,
        second_vehicle_maintenance_cost=second_vehicle_maintenance_cost,
        second_vehicle_parking_cost=second_vehicle_parking_cost,
        no_car_commute_cost=no_car_commute_cost,
        first_vehicle_down_payment=first_down_payment,
        second_vehicle_down_payment=extra_down_payment,
        vehicle_down_payment=total_down_payment,
        vehicle_plate_rental_payment=plate_rental_payment,
    )


def fixed_asset_projection_from_values(
    *,
    month: int,
    purchase_month: int,
    home_total_price: float,
    property_annual_price_growth_rate: float = 0.0,
    property_sale_cost_rate: float = 0.0,
    property_liquidity_discount_rate: float = 0.0,
    raw_first_vehicle_asset_value: float,
    raw_second_vehicle_asset_value: float,
    raw_vehicle_asset_value: float,
    total_loan_balance_base: float,
    offsets: ProjectionOffsets,
) -> FixedAssetProjection:
    if month >= purchase_month and home_total_price > 0:
        holding_years = max(0.0, month - purchase_month) / 12
        growth_factor = (1 + max(-0.99, property_annual_price_growth_rate)) ** holding_years
        gross_property_value = home_total_price * growth_factor
        net_sale_rate = min(
            0.90,
            max(0.0, property_sale_cost_rate) + max(0.0, property_liquidity_discount_rate),
        )
        property_asset_value = gross_property_value * (1 - net_sale_rate)
    else:
        property_asset_value = 0.0
    property_asset_value = max(0.0, property_asset_value + offsets.property_asset)
    vehicle_asset_value = max(0.0, raw_vehicle_asset_value + offsets.vehicle_asset)
    if raw_vehicle_asset_value > 0:
        vehicle_asset_scale = vehicle_asset_value / raw_vehicle_asset_value
        first_vehicle_asset_value = max(0.0, raw_first_vehicle_asset_value * vehicle_asset_scale)
        second_vehicle_asset_value = max(0.0, raw_second_vehicle_asset_value * vehicle_asset_scale)
    else:
        first_vehicle_asset_value = vehicle_asset_value
        second_vehicle_asset_value = 0.0
    fixed_asset_value = max(0.0, property_asset_value + vehicle_asset_value + offsets.fixed_asset)
    total_loan_balance = max(0.0, total_loan_balance_base + offsets.total_loan)
    return FixedAssetProjection(
        property_asset_value=property_asset_value,
        vehicle_asset_value=vehicle_asset_value,
        first_vehicle_asset_value=first_vehicle_asset_value,
        second_vehicle_asset_value=second_vehicle_asset_value,
        fixed_asset_value=fixed_asset_value,
        total_loan_balance=total_loan_balance,
    )


