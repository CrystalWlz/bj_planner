from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..schemas import AccountSnapshotPoint, CarLoanSummary, CarPlanData, MonthlyLedgerEntry


@dataclass(frozen=True)
class MonthlyLedgerResult:
    projection_states: list[MonthlyProjectionState]
    account_snapshots: list[AccountSnapshotPoint]
    ledger_entries: list[MonthlyLedgerEntry]


VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


class MonthlyIncomeProfileLike(Protocol):
    net_income: float
    pension_income: float
    personal_pension_contribution: float


class MonthlyHouseholdExpenseBreakdownLike(Protocol):
    base_living_expense: float
    rent_cash_expense: float
    scheduled_expense: float
    child_expense: float
    career_shock_self_payment: float


@dataclass
class ProjectionOffsets:
    provident_balance: float = 0.0
    pension_balance: float = 0.0
    medical_balance: float = 0.0
    property_asset: float = 0.0
    vehicle_asset: float = 0.0
    fixed_asset: float = 0.0
    total_loan: float = 0.0


@dataclass
class ProjectionBalances:
    cash_balance: float
    investment_balance: float
    provident_balance: float
    pension_account_balance: float
    medical_account_balance: float
    social_security_account_balance: float
    property_asset_value: float
    vehicle_asset_value: float
    first_vehicle_asset_value: float
    second_vehicle_asset_value: float
    fixed_asset_value: float
    total_loan_balance: float


@dataclass(frozen=True)
class AccountProjectionInputs:
    provident_balance: float
    pension_account_balance: float
    medical_account_balance: float
    social_security_account_balance: float
    provident_deposit: float
    provident_cash_receipt: float
    provident_house_offset_payment: float


@dataclass(frozen=True)
class FixedAssetProjection:
    property_asset_value: float
    vehicle_asset_value: float
    first_vehicle_asset_value: float
    second_vehicle_asset_value: float
    fixed_asset_value: float
    total_loan_balance: float


@dataclass(frozen=True)
class VehicleCashBreakdown:
    vehicle_total: float
    vehicle_payment: float
    first_vehicle_payment: float
    second_vehicle_payment: float
    vehicle_operating_cost: float
    first_vehicle_energy_cost: float
    first_vehicle_insurance_cost: float
    first_vehicle_maintenance_cost: float
    first_vehicle_parking_cost: float
    second_vehicle_energy_cost: float
    second_vehicle_insurance_cost: float
    second_vehicle_maintenance_cost: float
    second_vehicle_parking_cost: float
    no_car_commute_cost: float
    first_vehicle_down_payment: float
    second_vehicle_down_payment: float
    vehicle_down_payment: float
    vehicle_plate_rental_payment: float


@dataclass(frozen=True)
class HouseholdExpenseProjection:
    living_expense: float
    scheduled_expense: float
    child_expense: float
    career_shock_self_payment: float
    total_expense: float
    pension_account_payout: float
    medical_account_healthcare_payment: float
    medical_account_mutual_aid_payment: float


class InvestmentWithdrawalLike(Protocol):
    sell_fee: float
    sell_proceeds: float
    cash_after_transaction: float
    investment_after_transaction: float


InvestmentWithdrawalProvider = Callable[[float, float], InvestmentWithdrawalLike]
InvestmentAllocationProvider = Callable[[float, float, float], tuple[float, float]]


@dataclass(frozen=True)
class InvestmentCashState:
    cash_balance: float
    investment_balance: float
    investment_return: float = 0.0
    investment_tax: float = 0.0
    investment_fee: float = 0.0
    investment_buy_fee: float = 0.0
    investment_sell_fee: float = 0.0
    investment_sell_proceeds: float = 0.0
    liquidity_sell_proceeds: float = 0.0
    investment_contribution_base: float = 0.0
    investment_contribution_cash_sweep: float = 0.0
    investment_contribution: float = 0.0
    transaction_cash_in: float = 0.0
    transaction_cash_out: float = 0.0


@dataclass(frozen=True)
class MonthlyLedgerEntryInputs:
    plan_variant: str
    month: int
    vehicle_down_payment: float = 0.0
    vehicle_plate_rental_payment: float = 0.0
    include_home_purchase_entries: bool = False
    home_purchase_cash_out: float = 0.0
    investment_sell_proceeds: float = 0.0
    cash_income: float = 0.0
    pension_income: float = 0.0
    living_expense: float = 0.0
    scheduled_expense: float = 0.0
    child_expense: float = 0.0
    career_shock_self_payment: float = 0.0
    regular_debt_payment: float = 0.0
    phased_loan_payment: float = 0.0
    house_payment: float = 0.0
    vehicle_payment: float = 0.0
    vehicle_operating_cost: float = 0.0
    personal_pension_contribution: float = 0.0
    personal_pension_return: float = 0.0
    investment_contribution: float = 0.0
    investment_return: float = 0.0
    investment_tax: float = 0.0
    investment_fee: float = 0.0
    liquidity_sell_proceeds: float = 0.0
    provident_deposit: float = 0.0
    pension_account_payout: float = 0.0
    medical_account_healthcare_payment: float = 0.0
    medical_account_mutual_aid_payment: float = 0.0
    provident_cash_receipt: float = 0.0


@dataclass(frozen=True)
class MonthlyProjectionState:
    plan_variant: str
    month: int
    cash_balance: float
    investment_balance: float
    liquid_asset_value: float
    provident_balance: float
    pension_account_balance: float
    medical_account_balance: float
    social_security_account_balance: float
    fixed_asset_value: float
    total_asset_value: float
    total_loan_balance: float
    net_worth: float
    happiness_score: float
    monthly_cash_delta: float
    cash_income: float
    pension_income: float
    living_expense: float
    scheduled_expense: float
    child_expense: float
    career_shock_self_payment: float
    debt_payment: float
    regular_debt_payment: float
    phased_loan_payment: float
    house_payment: float
    house_contract_payment: float
    provident_house_offset_payment: float
    provident_house_payment_relief: float
    vehicle_payment: float
    first_vehicle_payment: float
    second_vehicle_payment: float
    vehicle_operating_cost: float
    first_vehicle_energy_cost: float
    first_vehicle_insurance_cost: float
    first_vehicle_maintenance_cost: float
    first_vehicle_parking_cost: float
    second_vehicle_energy_cost: float
    second_vehicle_insurance_cost: float
    second_vehicle_maintenance_cost: float
    second_vehicle_parking_cost: float
    no_car_commute_cost: float
    first_vehicle_down_payment: float
    second_vehicle_down_payment: float
    vehicle_down_payment: float
    vehicle_plate_rental_payment: float
    investment_contribution: float
    investment_contribution_base: float
    investment_contribution_cash_sweep: float
    investment_return: float
    investment_tax: float
    investment_fee: float
    investment_buy_fee: float
    investment_sell_fee: float
    investment_sell_proceeds: float
    personal_pension_contribution: float
    personal_pension_return: float
    personal_pension_balance: float
    provident_deposit: float
    provident_withdrawal: float
    transaction_cash_out: float
    transaction_cash_in: float
    property_asset_value: float
    vehicle_asset_value: float
    first_vehicle_asset_value: float
    second_vehicle_asset_value: float
    phase: str
