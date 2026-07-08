from __future__ import annotations

from datetime import date

from ..domain.time import month_distance, parse_year_month
from ..schemas import (
    AccountCalibrationData,
    AccountSnapshotPoint,
    HouseholdData,
    LoanVisualizationPoint,
    MonthlyLedgerEntry,
    ProvidentVisualizationPoint,
    SocialSecurityVisualizationPoint,
)
from .ledger_entries import ledger_entry
from .ledger_models import (
    AccountProjectionInputs,
    MonthlyProjectionState,
    ProjectionBalances,
    ProjectionOffsets,
)


ACCOUNT_CALIBRATION_TARGET_LABELS: dict[str, str] = {
    "cash": "现金账户",
    "investment": "投资账户",
    "provident": "公积金账户",
    "pension": "养老个人账户",
    "medical": "医保个人账户",
    "property_asset": "房产估值",
    "vehicle_asset": "车辆估值",
    "fixed_asset": "固定资产",
    "total_loan": "贷款余额",
}

def account_calibrations_by_month(
    household: HouseholdData,
    base_month: date,
) -> dict[int, list[AccountCalibrationData]]:
    grouped: dict[int, list[AccountCalibrationData]] = {}
    base_tuple = (base_month.year, base_month.month)
    for calibration in household.account_calibrations:
        if not calibration.enabled:
            continue
        target_month = parse_year_month(calibration.month)
        if target_month is None:
            continue
        month_index = max(0, month_distance(base_tuple, target_month))
        grouped.setdefault(month_index, []).append(calibration)
    return grouped


def account_calibration_label(calibration: AccountCalibrationData) -> str:
    target_label = ACCOUNT_CALIBRATION_TARGET_LABELS.get(calibration.target, "账户")
    suffix_parts = [
        value
        for value in (calibration.member_name, calibration.reference_name)
        if value
    ]
    suffix = f"（{' / '.join(suffix_parts)}）" if suffix_parts else ""
    return f"{target_label}手动校准{suffix}"

def account_inputs_from_projection_points(
    *,
    provident_point: ProvidentVisualizationPoint | None,
    social_security_point: SocialSecurityVisualizationPoint | None,
    loan_point: LoanVisualizationPoint | None,
    offsets: ProjectionOffsets,
    initial_provident_balance: float,
) -> AccountProjectionInputs:
    provident_balance = max(
        0.0,
        (provident_point.balance_end if provident_point else max(0.0, initial_provident_balance))
        + offsets.provident_balance,
    )
    pension_account_balance = max(
        0.0,
        (social_security_point.pension_balance_end if social_security_point else 0.0)
        + offsets.pension_balance,
    )
    medical_account_balance = max(
        0.0,
        (social_security_point.medical_balance_end if social_security_point else 0.0)
        + offsets.medical_balance,
    )
    social_security_account_balance = pension_account_balance + medical_account_balance
    provident_deposit = provident_point.total_deposit if provident_point else 0.0
    provident_cash_receipt = (
        provident_point.rent_withdrawal
        + provident_point.post_transaction_withdrawal
        + provident_point.agreed_withdrawal
        + provident_point.retirement_withdrawal
        if provident_point
        else 0.0
    )
    provident_house_offset_payment = loan_point.provident_offset_payment if loan_point else (
        (provident_point.monthly_repayment_withdrawal + provident_point.loan_offset_payment)
        if provident_point
        else 0.0
    )
    return AccountProjectionInputs(
        provident_balance=provident_balance,
        pension_account_balance=pension_account_balance,
        medical_account_balance=medical_account_balance,
        social_security_account_balance=social_security_account_balance,
        provident_deposit=provident_deposit,
        provident_cash_receipt=provident_cash_receipt,
        provident_house_offset_payment=provident_house_offset_payment,
    )


def apply_account_calibrations(
    *,
    balances: ProjectionBalances,
    offsets: ProjectionOffsets,
    calibrations: list[AccountCalibrationData],
    plan_variant: str,
    month: int,
) -> tuple[ProjectionBalances, ProjectionOffsets, list[MonthlyLedgerEntry]]:
    entries: list[MonthlyLedgerEntry] = []
    for calibration in calibrations:
        old_value = {
            "cash": balances.cash_balance,
            "investment": balances.investment_balance,
            "provident": balances.provident_balance,
            "pension": balances.pension_account_balance,
            "medical": balances.medical_account_balance,
            "property_asset": balances.property_asset_value,
            "vehicle_asset": balances.vehicle_asset_value,
            "fixed_asset": balances.fixed_asset_value,
            "total_loan": balances.total_loan_balance,
        }.get(calibration.target, 0.0)
        target_value = max(0.0, calibration.amount)
        delta = target_value - old_value
        if calibration.target == "cash":
            balances.cash_balance = target_value
        elif calibration.target == "investment":
            balances.investment_balance = target_value
        elif calibration.target == "provident":
            offsets.provident_balance += delta
            balances.provident_balance = target_value
        elif calibration.target == "pension":
            offsets.pension_balance += delta
            balances.pension_account_balance = target_value
        elif calibration.target == "medical":
            offsets.medical_balance += delta
            balances.medical_account_balance = target_value
        elif calibration.target == "property_asset":
            offsets.property_asset += delta
            balances.property_asset_value = target_value
        elif calibration.target == "vehicle_asset":
            offsets.vehicle_asset += delta
            balances.vehicle_asset_value = target_value
            balances.first_vehicle_asset_value = target_value
            balances.second_vehicle_asset_value = 0.0
        elif calibration.target == "fixed_asset":
            offsets.fixed_asset += delta
            balances.fixed_asset_value = target_value
        elif calibration.target == "total_loan":
            offsets.total_loan += delta
            balances.total_loan_balance = target_value

        balances.social_security_account_balance = balances.pension_account_balance + balances.medical_account_balance
        balances.fixed_asset_value = max(
            0.0,
            balances.fixed_asset_value
            if calibration.target == "fixed_asset"
            else balances.property_asset_value + balances.vehicle_asset_value + offsets.fixed_asset,
        )
        entries.append(
            ledger_entry(
                plan_variant=plan_variant,
                month=month,
                account=calibration.target,
                category="account_calibration",
                label=account_calibration_label(calibration),
                amount=delta,
                direction="valuation",
            )
        )
    return balances, offsets, entries

def account_snapshot_from_state(state: MonthlyProjectionState) -> AccountSnapshotPoint:
    return AccountSnapshotPoint(
        plan_variant=state.plan_variant,
        month=state.month,
        cash_balance=round(state.cash_balance, 2),
        investment_balance=round(state.investment_balance, 2),
        liquid_asset_value=round(state.liquid_asset_value, 2),
        provident_balance=round(state.provident_balance, 2),
        pension_account_balance=round(state.pension_account_balance, 2),
        medical_account_balance=round(state.medical_account_balance, 2),
        social_security_account_balance=round(state.social_security_account_balance, 2),
        personal_pension_balance=round(state.personal_pension_balance, 2),
        property_asset_value=round(state.property_asset_value, 2),
        vehicle_asset_value=round(state.vehicle_asset_value, 2),
        first_vehicle_asset_value=round(state.first_vehicle_asset_value, 2),
        second_vehicle_asset_value=round(state.second_vehicle_asset_value, 2),
        fixed_asset_value=round(state.fixed_asset_value, 2),
        total_asset_value=round(state.total_asset_value, 2),
        total_loan_balance=round(state.total_loan_balance, 2),
        net_worth=round(state.net_worth, 2),
    )


