from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from ..schemas import (
    AccountSnapshotPoint,
    CarLoanSummary,
    HouseholdData,
    IncomeMember,
    LoanVisualizationPoint,
    MonthlyLedgerEntry,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    ScenarioData,
    SocialSecurityVisualizationPoint,
)
from .context import MonthlyLedgerProjectionContext
from .investment_ledger import (
    apply_purchase_month_investment_cash_state,
    apply_regular_month_investment_cash_state,
)
from .accounts_ledger import (
    account_calibrations_by_month,
    account_inputs_from_projection_points,
    account_snapshot_from_state,
    apply_account_calibrations,
)
from .ledger_entries import build_monthly_ledger_entries
from .ledger_cashflows import (
    fixed_asset_projection_from_values,
    household_expense_projection_from_breakdown,
    vehicle_cash_breakdown_from_projection,
)
from .ledger_models import (
    InvestmentWithdrawalLike,
    MonthlyHouseholdExpenseBreakdownLike,
    MonthlyIncomeProfileLike,
    MonthlyLedgerEntryInputs,
    MonthlyLedgerResult,
    MonthlyProjectionState,
    PersonalPensionMonthResultLike,
    ProjectionBalances,
    ProjectionOffsets,
    ProjectionRiskSummary,
    VehicleLoanState,
)
from .vehicles import VehicleMonthProjection


def build_projected_monthly_ledger(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    base_month: date,
    horizon_months: int,
    initial_provident_balance: float,
    income_at_month: Callable[[int], MonthlyIncomeProfileLike],
    expense_breakdown_at_month: Callable[[int], MonthlyHouseholdExpenseBreakdownLike],
    plan_vehicle_states_at: Callable[[PurchasePlanAnalysis, list[VehicleLoanState] | None], list[VehicleLoanState]],
    vehicle_month_projection_at: Callable[[PurchasePlanAnalysis, list[VehicleLoanState], int], VehicleMonthProjection],
    regular_debt_payment_at: Callable[[HouseholdData, int], float],
    investment_effective_tax_rate: float,
    weighted_personal_pension_monthly_return: Callable[[Sequence[IncomeMember], float], float],
    member_income_profiles_at: Callable[[int], list[tuple[int, str, MonthlyIncomeProfileLike]]] | None = None,
    personal_pension_month_at: Callable[..., PersonalPensionMonthResultLike] | None = None,
    investment_withdrawal_at_purchase: Callable[..., InvestmentWithdrawalLike],
    investment_allocation_for_month: Callable[..., tuple[float, float]],
    monthly_happiness_score: Callable[..., float],
    property_annual_price_growth_rate: float = 0.0,
    property_sale_cost_rate: float = 0.0,
    property_liquidity_discount_rate: float = 0.0,
) -> MonthlyLedgerResult:
    horizon = horizon_months
    loan_by_plan_month = {(row.plan_variant, row.month): row for row in loan_visualization}
    provident_by_plan_month = {(row.plan_variant, row.month): row for row in provident_visualization}
    social_security_by_plan_month = {
        (row.plan_variant, row.month): row
        for row in (social_security_visualization or [])
    }
    monthly_return = scenario.annual_investment_return / 12
    buy_fee_rate = max(0.0, household.investment_buy_fee_rate)
    sell_fee_rate = max(0.0, household.investment_sell_fee_rate)
    investment_enabled = household.investment_plan_name != "cash_only"
    projection_states: list[MonthlyProjectionState] = []
    snapshots: list[AccountSnapshotPoint] = []
    ledger: list[MonthlyLedgerEntry] = []
    risk_by_plan: dict[str, ProjectionRiskSummary] = {}
    calibrations_by_month = account_calibrations_by_month(household, base_month)
    for plan in purchase_plans:
        plan_vehicle_states = plan_vehicle_states_at(plan, vehicle_states)
        vehicle_monthly_cache: dict[int, VehicleMonthProjection] = {}

        def vehicle_projection_at(month: int) -> VehicleMonthProjection:
            if month not in vehicle_monthly_cache:
                vehicle_monthly_cache[month] = vehicle_month_projection_at(plan, plan_vehicle_states, month)
            return vehicle_monthly_cache[month]

        cash_balance = household.cash_account_balance
        investment_balance = max(0.0, household.investments)
        personal_pension_balance = sum(
            max(0.0, float(getattr(member, "personal_pension_account_balance", 0.0)))
            for member in household.members
            if bool(getattr(member, "personal_pension_account_enabled", False))
        )
        offsets = ProjectionOffsets()
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 999999
        renovation_month = (
            purchase_month + plan.months_to_renovation
            if plan.renovation_cost > 0 and plan.months_to_renovation is not None
            else 999999
        )
        personal_pension_balances = {
            index: max(0.0, float(member.personal_pension_account_balance))
            for index, member in enumerate(household.members)
            if member.personal_pension_account_enabled
        }
        pre_purchase_investment_horizon = (
            purchase_month
            if plan.months_to_buy is not None
            else (12 if plan.source != "baseline" and scenario.enabled else 999999)
        )
        worst_cash_balance = cash_balance
        insolvency_month: int | None = None
        liquid_assets_exhausted_month: int | None = None
        terminal_net_worth = 0.0
        for month in range(0, horizon + 1):
            entries: list[MonthlyLedgerEntry] = []
            cash_income = 0.0
            pension_income = 0.0
            living_expense = 0.0
            scheduled_expense = 0.0
            renovation_expense = 0.0
            child_expense = 0.0
            career_shock_self_payment = 0.0
            debt_payment = 0.0
            regular_debt_payment = 0.0
            phased_loan_payment = 0.0
            house_payment = 0.0
            house_contract_payment = 0.0
            provident_house_offset_payment = 0.0
            vehicle_payment = 0.0
            first_vehicle_payment = 0.0
            second_vehicle_payment = 0.0
            vehicle_operating_cost = 0.0
            first_vehicle_energy_cost = 0.0
            first_vehicle_insurance_cost = 0.0
            first_vehicle_maintenance_cost = 0.0
            first_vehicle_parking_cost = 0.0
            second_vehicle_energy_cost = 0.0
            second_vehicle_insurance_cost = 0.0
            second_vehicle_maintenance_cost = 0.0
            second_vehicle_parking_cost = 0.0
            no_car_commute_cost = 0.0
            vehicle_down_payment = 0.0
            first_vehicle_down_payment = 0.0
            second_vehicle_down_payment = 0.0
            vehicle_plate_rental_payment = 0.0
            investment_contribution = 0.0
            investment_contribution_base = 0.0
            investment_contribution_cash_sweep = 0.0
            investment_return = 0.0
            investment_tax = 0.0
            investment_fee = 0.0
            investment_buy_fee = 0.0
            investment_sell_fee = 0.0
            investment_sell_proceeds = 0.0
            liquidity_sell_proceeds = 0.0
            personal_pension_contribution = 0.0
            personal_pension_return = 0.0
            personal_pension_withdrawal = 0.0
            personal_pension_redemption_fee = 0.0
            personal_pension_withdrawal_tax = 0.0
            personal_pension_suspended_contribution = 0.0
            pension_account_payout = 0.0
            medical_account_healthcare_payment = 0.0
            medical_account_mutual_aid_payment = 0.0
            transaction_cash_out = 0.0
            transaction_cash_in = 0.0
            phase = "购房前"

            provident_point = provident_by_plan_month.get((plan.variant, month))
            social_security_point = social_security_by_plan_month.get((plan.variant, month))
            loan_point = loan_by_plan_month.get((plan.variant, month))
            account_inputs = account_inputs_from_projection_points(
                provident_point=provident_point,
                social_security_point=social_security_point,
                loan_point=loan_point,
                offsets=offsets,
                initial_provident_balance=initial_provident_balance,
            )
            provident_balance = account_inputs.provident_balance
            pension_account_balance = account_inputs.pension_account_balance
            medical_account_balance = account_inputs.medical_account_balance
            social_security_account_balance = account_inputs.social_security_account_balance
            provident_deposit = account_inputs.provident_deposit
            provident_cash_receipt = account_inputs.provident_cash_receipt
            provident_house_offset_payment = account_inputs.provident_house_offset_payment
            provident_house_payment_relief = 0.0

            if month == 0 and provident_cash_receipt:
                cash_balance += provident_cash_receipt

            if month > 0:
                if member_income_profiles_at is not None and personal_pension_month_at is not None:
                    member_profiles = member_income_profiles_at(month)
                    if member_profiles:
                        cash_income = sum(member_profile.net_income for _, _, member_profile in member_profiles)
                        pension_income = sum(member_profile.pension_income for _, _, member_profile in member_profiles)
                        for member_index, _, member_profile in member_profiles:
                            if member_index >= len(household.members):
                                continue
                            member = household.members[member_index]
                            result = personal_pension_month_at(
                                member=member,
                                member_index=member_index,
                                months_from_now=month,
                                balance_start=personal_pension_balances.get(member_index, 0.0),
                                planned_contribution=member_profile.personal_pension_contribution,
                                planned_tax_saving=member_profile.personal_pension_tax_saving,
                                cash_balance=cash_balance,
                                household_monthly_expense=household.monthly_expense,
                            )
                            personal_pension_balances[member_index] = result.balance_end
                            personal_pension_contribution += result.cash_contribution
                            personal_pension_suspended_contribution += result.suspended_contribution
                            personal_pension_return += result.investment_return
                            personal_pension_withdrawal += result.net_withdrawal
                            personal_pension_redemption_fee += result.redemption_fee
                            personal_pension_withdrawal_tax += result.withdrawal_tax
                            cash_income -= result.lost_tax_saving
                        personal_pension_balance = sum(personal_pension_balances.values())
                    else:
                        profile = income_at_month(month)
                        cash_income = profile.net_income
                        pension_income = profile.pension_income
                else:
                    profile = income_at_month(month)
                    cash_income = profile.net_income
                    pension_income = profile.pension_income
                    personal_pension_contribution = profile.personal_pension_contribution
                if personal_pension_month_at is None and (personal_pension_balance > 0 or personal_pension_contribution > 0):
                    personal_pension_monthly_return = weighted_personal_pension_monthly_return(
                        household.members,
                        personal_pension_balance,
                    )
                    personal_pension_return = (
                        personal_pension_balance + personal_pension_contribution
                    ) * personal_pension_monthly_return
                    personal_pension_balance = max(
                        0.0,
                        personal_pension_balance + personal_pension_contribution + personal_pension_return,
                    )
                expense_breakdown = expense_breakdown_at_month(month)
                household_expense = household_expense_projection_from_breakdown(
                    base_living_expense=expense_breakdown.base_living_expense,
                    rent_cash_expense=expense_breakdown.rent_cash_expense,
                    scheduled_expense=expense_breakdown.scheduled_expense,
                    child_expense=expense_breakdown.child_expense,
                    career_shock_self_payment=expense_breakdown.career_shock_self_payment,
                    social_security_point=social_security_point,
                )
                living_expense = household_expense.living_expense
                scheduled_expense = household_expense.scheduled_expense
                child_expense = household_expense.child_expense
                career_shock_self_payment = household_expense.career_shock_self_payment
                total_expense = household_expense.total_expense
                if month == renovation_month:
                    renovation_expense = max(0.0, plan.renovation_cost)
                pension_account_payout = household_expense.pension_account_payout
                medical_account_healthcare_payment = household_expense.medical_account_healthcare_payment
                medical_account_mutual_aid_payment = household_expense.medical_account_mutual_aid_payment
                investment_reserve_target = max(0.0, total_expense * household.investment_cash_reserve_months)
                regular_debt_payment = regular_debt_payment_at(household, month)
                debt_payment = loan_point.existing_monthly_payment if loan_point else regular_debt_payment
                phased_loan_payment = max(0.0, debt_payment - regular_debt_payment)
                vehicle_projection = vehicle_projection_at(month)
                vehicle_cash = vehicle_cash_breakdown_from_projection(
                    vehicle_total=vehicle_projection.total_cash_cost,
                    loan_vehicle_payment=loan_point.vehicle_monthly_payment if loan_point else 0.0,
                    components_by_index=vehicle_projection.components_by_index,
                    no_car_commute_cost=vehicle_projection.no_car_commute_cost,
                    first_down_payment=vehicle_projection.first_down_payment,
                    extra_down_payment=vehicle_projection.extra_down_payment,
                    total_down_payment=vehicle_projection.total_down_payment,
                    plate_rental_payment=vehicle_projection.plate_rental_payment,
                )
                vehicle_total = vehicle_cash.vehicle_total
                vehicle_payment = vehicle_cash.vehicle_payment
                first_vehicle_payment = vehicle_cash.first_vehicle_payment
                second_vehicle_payment = vehicle_cash.second_vehicle_payment
                vehicle_operating_cost = vehicle_cash.vehicle_operating_cost
                first_vehicle_energy_cost = vehicle_cash.first_vehicle_energy_cost
                first_vehicle_insurance_cost = vehicle_cash.first_vehicle_insurance_cost
                first_vehicle_maintenance_cost = vehicle_cash.first_vehicle_maintenance_cost
                first_vehicle_parking_cost = vehicle_cash.first_vehicle_parking_cost
                second_vehicle_energy_cost = vehicle_cash.second_vehicle_energy_cost
                second_vehicle_insurance_cost = vehicle_cash.second_vehicle_insurance_cost
                second_vehicle_maintenance_cost = vehicle_cash.second_vehicle_maintenance_cost
                second_vehicle_parking_cost = vehicle_cash.second_vehicle_parking_cost
                no_car_commute_cost = vehicle_cash.no_car_commute_cost
                first_vehicle_down_payment = vehicle_cash.first_vehicle_down_payment
                second_vehicle_down_payment = vehicle_cash.second_vehicle_down_payment
                vehicle_down_payment = vehicle_cash.vehicle_down_payment
                vehicle_plate_rental_payment = vehicle_cash.vehicle_plate_rental_payment
                if vehicle_down_payment:
                    transaction_cash_out += vehicle_down_payment
                entries.extend(
                    build_monthly_ledger_entries(
                        MonthlyLedgerEntryInputs(
                            plan_variant=plan.variant,
                            month=month,
                            vehicle_down_payment=vehicle_down_payment,
                            vehicle_plate_rental_payment=vehicle_plate_rental_payment,
                        )
                    )
                )

                if month == purchase_month:
                    phase = "交易月"
                    monthly_surplus = (
                        cash_income
                        - total_expense
                        - renovation_expense
                        - personal_pension_contribution
                        - debt_payment
                        - vehicle_total
                        + provident_cash_receipt
                        + personal_pension_withdrawal
                    )
                    investment_cash_state = apply_purchase_month_investment_cash_state(
                        cash_balance=cash_balance,
                        investment_balance=investment_balance,
                        monthly_surplus=monthly_surplus,
                        required_cash_after_pf=plan.required_cash_after_pf_extract,
                        vehicle_down_payment=vehicle_down_payment,
                        monthly_return=monthly_return,
                        investment_enabled=investment_enabled,
                        investment_effective_tax_rate=investment_effective_tax_rate,
                        withdrawal_provider=lambda cash_before_transaction, investment_before_transaction: investment_withdrawal_at_purchase(
                            scenario=scenario,
                            cash_before_transaction=cash_before_transaction,
                            investment_before_transaction=investment_before_transaction,
                            required_cash_after_pf=plan.required_cash_after_pf_extract,
                            required_liquidity_reserve=plan.required_liquidity_reserve,
                            sell_fee_rate=sell_fee_rate,
                            investment_enabled=investment_enabled,
                            minimum_investment_balance_override=plan.investment_reserve_target,
                        ),
                    )
                    cash_balance = investment_cash_state.cash_balance
                    investment_balance = investment_cash_state.investment_balance
                    investment_return = investment_cash_state.investment_return
                    investment_tax = investment_cash_state.investment_tax
                    investment_fee += investment_cash_state.investment_fee
                    investment_sell_fee = investment_cash_state.investment_sell_fee
                    investment_sell_proceeds = investment_cash_state.investment_sell_proceeds
                    transaction_cash_in += investment_cash_state.transaction_cash_in
                    transaction_cash_out += investment_cash_state.transaction_cash_out
                    entries.extend(
                        build_monthly_ledger_entries(
                            MonthlyLedgerEntryInputs(
                                plan_variant=plan.variant,
                                month=month,
                                include_home_purchase_entries=True,
                                home_purchase_cash_out=plan.required_cash_after_pf_extract,
                                investment_sell_proceeds=investment_sell_proceeds,
                            )
                        )
                    )
                else:
                    if month > purchase_month:
                        phase = "购房后"
                        house_contract_payment = loan_point.home_monthly_payment if loan_point else plan.total_monthly_payment
                        commercial_house_payment = loan_point.commercial_monthly_payment if loan_point else plan.commercial_monthly_payment
                        commercial_extra_principal_payment = loan_point.commercial_extra_principal_payment if loan_point else 0.0
                        provident_house_contract_payment = loan_point.provident_monthly_payment if loan_point else plan.provident_monthly_payment
                        provident_current_payment_relief = (
                            loan_point.provident_monthly_payment_relief
                            if loan_point
                            else min(provident_house_contract_payment, provident_house_offset_payment)
                        )
                        provident_house_payment_relief = provident_current_payment_relief
                        house_payment = commercial_house_payment + commercial_extra_principal_payment + max(
                            0.0,
                            provident_house_contract_payment - provident_current_payment_relief,
                        )
                    monthly_surplus = (
                        cash_income
                        - total_expense
                        - renovation_expense
                        - personal_pension_contribution
                        - debt_payment
                        - house_payment
                        - vehicle_total
                        + provident_cash_receipt
                        + personal_pension_withdrawal
                    )
                    investment_cash_state = apply_regular_month_investment_cash_state(
                        cash_balance=cash_balance,
                        investment_balance=investment_balance,
                        monthly_surplus=monthly_surplus,
                        vehicle_down_payment=vehicle_down_payment,
                        reserve_target=investment_reserve_target,
                        monthly_return=monthly_return,
                        investment_enabled=(
                            investment_enabled
                            and not (
                                renovation_expense > 0
                                and plan.renovation_funding_mode == "cash_only"
                            )
                        ),
                        investment_auto_rebalance=household.investment_auto_rebalance,
                        investment_effective_tax_rate=investment_effective_tax_rate,
                        buy_fee_rate=buy_fee_rate,
                        sell_fee_rate=sell_fee_rate,
                        allocation_provider=lambda investable_surplus, current_cash_balance, reserve_target: tuple(
                            value
                            * (
                                0.0
                                if 0 <= pre_purchase_investment_horizon - month <= 12
                                else 0.35
                                if 12 < pre_purchase_investment_horizon - month <= 24
                                else 1.0
                            )
                            for value in investment_allocation_for_month(
                                monthly_surplus=investable_surplus,
                                cash_balance=current_cash_balance,
                                reserve_target=reserve_target,
                                household=household,
                            )
                        ),
                    )
                    cash_balance = investment_cash_state.cash_balance
                    investment_balance = investment_cash_state.investment_balance
                    investment_return = investment_cash_state.investment_return
                    investment_tax = investment_cash_state.investment_tax
                    investment_fee += investment_cash_state.investment_fee
                    investment_buy_fee = investment_cash_state.investment_buy_fee
                    investment_sell_fee = investment_cash_state.investment_sell_fee
                    investment_sell_proceeds += investment_cash_state.investment_sell_proceeds
                    liquidity_sell_proceeds = investment_cash_state.liquidity_sell_proceeds
                    investment_contribution_base = investment_cash_state.investment_contribution_base
                    investment_contribution_cash_sweep = investment_cash_state.investment_contribution_cash_sweep
                    investment_contribution = investment_cash_state.investment_contribution
                if renovation_expense:
                    transaction_cash_out += renovation_expense
                    entries.extend(
                        build_monthly_ledger_entries(
                            MonthlyLedgerEntryInputs(
                                plan_variant=plan.variant,
                                month=month,
                                renovation_expense=renovation_expense,
                            )
                        )
                    )
                entries.extend(
                    build_monthly_ledger_entries(
                        MonthlyLedgerEntryInputs(
                            plan_variant=plan.variant,
                            month=month,
                            cash_income=cash_income,
                            pension_income=pension_income,
                            living_expense=living_expense,
                            scheduled_expense=scheduled_expense,
                            child_expense=child_expense,
                            career_shock_self_payment=career_shock_self_payment,
                            regular_debt_payment=regular_debt_payment,
                            phased_loan_payment=phased_loan_payment,
                            house_payment=house_payment,
                            vehicle_payment=vehicle_payment,
                            vehicle_operating_cost=vehicle_operating_cost,
                            personal_pension_contribution=personal_pension_contribution,
                            personal_pension_return=personal_pension_return,
                            personal_pension_withdrawal=personal_pension_withdrawal,
                            personal_pension_redemption_fee=personal_pension_redemption_fee,
                            personal_pension_withdrawal_tax=personal_pension_withdrawal_tax,
                            personal_pension_suspended_contribution=personal_pension_suspended_contribution,
                            investment_contribution=investment_contribution,
                            investment_return=investment_return,
                            investment_tax=investment_tax,
                            investment_fee=investment_fee,
                            liquidity_sell_proceeds=liquidity_sell_proceeds,
                            provident_deposit=provident_deposit,
                        )
                    )
                )

            entries.extend(
                build_monthly_ledger_entries(
                    MonthlyLedgerEntryInputs(
                        plan_variant=plan.variant,
                        month=month,
                        pension_account_payout=pension_account_payout,
                        medical_account_healthcare_payment=medical_account_healthcare_payment,
                        medical_account_mutual_aid_payment=medical_account_mutual_aid_payment,
                        provident_cash_receipt=provident_cash_receipt,
                    )
                )
            )

            vehicle_projection = vehicle_projection_at(month)
            fixed_asset_projection = fixed_asset_projection_from_values(
                month=month,
                purchase_month=purchase_month,
                home_total_price=(plan.projected_purchase_price or scenario.total_price),
                property_annual_price_growth_rate=property_annual_price_growth_rate,
                property_sale_cost_rate=property_sale_cost_rate,
                property_liquidity_discount_rate=property_liquidity_discount_rate,
                raw_first_vehicle_asset_value=vehicle_projection.first_asset_value,
                raw_second_vehicle_asset_value=vehicle_projection.extra_asset_value,
                raw_vehicle_asset_value=vehicle_projection.total_asset_value,
                total_loan_balance_base=loan_point.total_loan_balance if loan_point else 0.0,
                offsets=offsets,
            )
            property_asset_value = fixed_asset_projection.property_asset_value
            vehicle_asset_value = fixed_asset_projection.vehicle_asset_value
            first_vehicle_asset_value = fixed_asset_projection.first_vehicle_asset_value
            second_vehicle_asset_value = fixed_asset_projection.second_vehicle_asset_value
            fixed_asset_value = fixed_asset_projection.fixed_asset_value
            total_loan_balance = fixed_asset_projection.total_loan_balance
            balances, offsets, calibration_entries = apply_account_calibrations(
                balances=ProjectionBalances(
                    cash_balance=cash_balance,
                    investment_balance=investment_balance,
                    provident_balance=provident_balance,
                    pension_account_balance=pension_account_balance,
                    medical_account_balance=medical_account_balance,
                    social_security_account_balance=social_security_account_balance,
                    property_asset_value=property_asset_value,
                    vehicle_asset_value=vehicle_asset_value,
                    first_vehicle_asset_value=first_vehicle_asset_value,
                    second_vehicle_asset_value=second_vehicle_asset_value,
                    fixed_asset_value=fixed_asset_value,
                    total_loan_balance=total_loan_balance,
                ),
                offsets=offsets,
                calibrations=calibrations_by_month.get(month, []),
                plan_variant=plan.variant,
                month=month,
            )
            cash_balance = balances.cash_balance
            investment_balance = balances.investment_balance
            provident_balance = balances.provident_balance
            pension_account_balance = balances.pension_account_balance
            medical_account_balance = balances.medical_account_balance
            social_security_account_balance = balances.social_security_account_balance
            property_asset_value = balances.property_asset_value
            vehicle_asset_value = balances.vehicle_asset_value
            first_vehicle_asset_value = balances.first_vehicle_asset_value
            second_vehicle_asset_value = balances.second_vehicle_asset_value
            fixed_asset_value = balances.fixed_asset_value
            total_loan_balance = balances.total_loan_balance
            entries.extend(calibration_entries)
            liquid_asset_value = cash_balance + investment_balance
            total_asset_value = cash_balance + investment_balance + provident_balance + personal_pension_balance + fixed_asset_value
            net_worth = total_asset_value - total_loan_balance
            worst_cash_balance = min(worst_cash_balance, cash_balance)
            if insolvency_month is None and cash_balance < 0:
                insolvency_month = month
            if liquid_assets_exhausted_month is None and cash_balance + investment_balance <= 0:
                liquid_assets_exhausted_month = month
            terminal_net_worth = net_worth
            monthly_cash_delta = (
                cash_income
                + provident_cash_receipt
                + personal_pension_withdrawal
                + (investment_sell_proceeds if month != purchase_month else 0.0)
                + transaction_cash_in
                - living_expense
                - scheduled_expense
                - career_shock_self_payment
                - personal_pension_contribution
                - debt_payment
                - house_payment
                - vehicle_payment
                - vehicle_operating_cost
                - investment_contribution
                - transaction_cash_out
            )
            happiness_score = monthly_happiness_score(
                plan,
                month=month,
                purchase_month=purchase_month if purchase_month < 999999 else None,
                cash_balance=cash_balance,
                monthly_cash_delta=monthly_cash_delta,
                monthly_expense=(living_expense + scheduled_expense + renovation_expense + child_expense + career_shock_self_payment + debt_payment + house_payment + vehicle_payment + vehicle_operating_cost),
                cash_income=cash_income,
                total_loan_balance=total_loan_balance,
                vehicle_asset_value=vehicle_asset_value,
                child_expense=child_expense,
            )
            ledger.extend(entries)
            state = MonthlyProjectionState(
                plan_variant=plan.variant,
                month=month,
                cash_balance=cash_balance,
                investment_balance=investment_balance,
                liquid_asset_value=liquid_asset_value,
                provident_balance=provident_balance,
                pension_account_balance=pension_account_balance,
                medical_account_balance=medical_account_balance,
                social_security_account_balance=social_security_account_balance,
                fixed_asset_value=fixed_asset_value,
                total_asset_value=total_asset_value,
                total_loan_balance=total_loan_balance,
                net_worth=net_worth,
                happiness_score=happiness_score,
                monthly_cash_delta=monthly_cash_delta,
                cash_income=cash_income,
                pension_income=pension_income,
                living_expense=living_expense,
                scheduled_expense=scheduled_expense,
                renovation_expense=renovation_expense,
                child_expense=child_expense,
                career_shock_self_payment=career_shock_self_payment,
                debt_payment=debt_payment,
                regular_debt_payment=regular_debt_payment,
                phased_loan_payment=phased_loan_payment,
                house_payment=house_payment,
                house_contract_payment=house_contract_payment,
                provident_house_offset_payment=provident_house_offset_payment,
                provident_house_payment_relief=provident_house_payment_relief,
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
                first_vehicle_down_payment=first_vehicle_down_payment,
                second_vehicle_down_payment=second_vehicle_down_payment,
                vehicle_down_payment=vehicle_down_payment,
                vehicle_plate_rental_payment=vehicle_plate_rental_payment,
                investment_contribution=investment_contribution,
                investment_contribution_base=investment_contribution_base,
                investment_contribution_cash_sweep=investment_contribution_cash_sweep,
                investment_return=investment_return,
                investment_tax=investment_tax,
                investment_fee=investment_fee,
                investment_buy_fee=investment_buy_fee,
                investment_sell_fee=investment_sell_fee,
                investment_sell_proceeds=investment_sell_proceeds,
                personal_pension_contribution=personal_pension_contribution,
                personal_pension_return=personal_pension_return,
                personal_pension_balance=personal_pension_balance,
                personal_pension_withdrawal=personal_pension_withdrawal,
                personal_pension_redemption_fee=personal_pension_redemption_fee,
                personal_pension_withdrawal_tax=personal_pension_withdrawal_tax,
                personal_pension_suspended_contribution=personal_pension_suspended_contribution,
                provident_deposit=provident_deposit,
                provident_withdrawal=provident_cash_receipt,
                transaction_cash_out=transaction_cash_out,
                transaction_cash_in=transaction_cash_in,
                property_asset_value=property_asset_value,
                vehicle_asset_value=vehicle_asset_value,
                first_vehicle_asset_value=first_vehicle_asset_value,
                second_vehicle_asset_value=second_vehicle_asset_value,
                phase=phase,
            )
            projection_states.append(state)
            snapshots.append(account_snapshot_from_state(state))
        risk_by_plan[plan.variant] = ProjectionRiskSummary(
            cash_shortfall=round(max(0.0, -worst_cash_balance), 2),
            insolvency_month=insolvency_month,
            liquid_assets_exhausted_month=liquid_assets_exhausted_month,
            worst_cash_balance=round(worst_cash_balance, 2),
            terminal_net_worth=round(terminal_net_worth, 2),
        )
    return MonthlyLedgerResult(
        projection_states=projection_states,
        account_snapshots=snapshots,
        ledger_entries=ledger,
        risk_by_plan=risk_by_plan,
    )


def build_projected_monthly_ledger_from_context(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_plans: list[PurchasePlanAnalysis],
    car_loan: CarLoanSummary,
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    vehicle_states: list[VehicleLoanState] | None = None,
    base_month: date,
    horizon_months: int,
    initial_provident_balance: float,
    income_provider: Callable[[int], MonthlyIncomeProfileLike],
    expense_provider: Callable[[int], MonthlyHouseholdExpenseBreakdownLike],
    vehicle_states_provider: Callable[[PurchasePlanAnalysis], list[VehicleLoanState]],
    vehicle_month_projection_provider: Callable[[list[VehicleLoanState], int], VehicleMonthProjection],
    regular_debt_payment_at: Callable[[HouseholdData, int], float],
    investment_effective_tax_rate: float,
    weighted_personal_pension_monthly_return: Callable[[Sequence[IncomeMember], float], float],
    member_income_profiles_at: Callable[[int], list[tuple[int, str, MonthlyIncomeProfileLike]]] | None = None,
    personal_pension_month_at: Callable[..., PersonalPensionMonthResultLike] | None = None,
    investment_withdrawal_at_purchase: Callable[..., InvestmentWithdrawalLike],
    investment_allocation_for_month: Callable[..., tuple[float, float]],
    monthly_happiness_score: Callable[..., float],
    property_annual_price_growth_rate: float = 0.0,
    property_sale_cost_rate: float = 0.0,
    property_liquidity_discount_rate: float = 0.0,
) -> MonthlyLedgerResult:
    ledger_context = MonthlyLedgerProjectionContext(
        household=household,
        scenario=scenario,
        base_month=base_month,
        selected_vehicle_states=vehicle_states,
        income_provider=income_provider,
        expense_provider=expense_provider,
        vehicle_states_provider=vehicle_states_provider,
        vehicle_month_projection_provider=vehicle_month_projection_provider,
    )
    member_profile_cache: dict[int, list[tuple[int, str, MonthlyIncomeProfileLike]]] = {}

    def cached_member_income_profiles_at(
        month: int,
    ) -> list[tuple[int, str, MonthlyIncomeProfileLike]]:
        if member_income_profiles_at is None:
            return []
        if month not in member_profile_cache:
            member_profile_cache[month] = member_income_profiles_at(month)
        return member_profile_cache[month]

    return build_projected_monthly_ledger(
        household,
        scenario,
        purchase_plans,
        car_loan,
        loan_visualization,
        provident_visualization,
        social_security_visualization,
        vehicle_states=vehicle_states,
        base_month=base_month,
        horizon_months=horizon_months,
        initial_provident_balance=initial_provident_balance,
        income_at_month=ledger_context.income_at_month,
        expense_breakdown_at_month=ledger_context.expense_breakdown_at_month,
        plan_vehicle_states_at=ledger_context.plan_vehicle_states_at,
        vehicle_month_projection_at=ledger_context.vehicle_month_projection_at,
        regular_debt_payment_at=regular_debt_payment_at,
        investment_effective_tax_rate=investment_effective_tax_rate,
        weighted_personal_pension_monthly_return=weighted_personal_pension_monthly_return,
        member_income_profiles_at=(
            cached_member_income_profiles_at if member_income_profiles_at is not None else None
        ),
        personal_pension_month_at=personal_pension_month_at,
        investment_withdrawal_at_purchase=investment_withdrawal_at_purchase,
        investment_allocation_for_month=investment_allocation_for_month,
        monthly_happiness_score=monthly_happiness_score,
        property_annual_price_growth_rate=property_annual_price_growth_rate,
        property_sale_cost_rate=property_sale_cost_rate,
        property_liquidity_discount_rate=property_liquidity_discount_rate,
    )
