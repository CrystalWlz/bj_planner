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
    ProjectionBalances,
    ProjectionOffsets,
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
    investment_withdrawal_at_purchase: Callable[..., InvestmentWithdrawalLike],
    investment_allocation_for_month: Callable[..., tuple[float, float]],
    monthly_happiness_score: Callable[..., float],
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
    calibrations_by_month = account_calibrations_by_month(household, base_month)
    for plan in purchase_plans:
        plan_vehicle_states = plan_vehicle_states_at(plan, vehicle_states)
        vehicle_monthly_cache: dict[int, VehicleMonthProjection] = {}

        def vehicle_projection_at(month: int) -> VehicleMonthProjection:
            if month not in vehicle_monthly_cache:
                vehicle_monthly_cache[month] = vehicle_month_projection_at(plan, plan_vehicle_states, month)
            return vehicle_monthly_cache[month]

        cash_balance = max(0.0, household.cash_account_balance)
        investment_balance = max(0.0, household.investments)
        personal_pension_balance = sum(
            max(0.0, float(getattr(member, "personal_pension_account_balance", 0.0)))
            for member in household.members
            if bool(getattr(member, "personal_pension_account_enabled", False))
        )
        offsets = ProjectionOffsets()
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 999999
        for month in range(0, horizon + 1):
            entries: list[MonthlyLedgerEntry] = []
            cash_income = 0.0
            pension_income = 0.0
            living_expense = 0.0
            scheduled_expense = 0.0
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
                cash_balance = max(0.0, cash_balance + provident_cash_receipt)

            if month > 0:
                profile = income_at_month(month)
                cash_income = profile.net_income
                pension_income = profile.pension_income
                personal_pension_contribution = profile.personal_pension_contribution
                if personal_pension_balance > 0 or personal_pension_contribution > 0:
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
                        - personal_pension_contribution
                        - debt_payment
                        - vehicle_total
                        + provident_cash_receipt
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
                        - personal_pension_contribution
                        - debt_payment
                        - house_payment
                        - vehicle_total
                        + provident_cash_receipt
                    )
                    investment_cash_state = apply_regular_month_investment_cash_state(
                        cash_balance=cash_balance,
                        investment_balance=investment_balance,
                        monthly_surplus=monthly_surplus,
                        vehicle_down_payment=vehicle_down_payment,
                        reserve_target=investment_reserve_target,
                        monthly_return=monthly_return,
                        investment_enabled=investment_enabled,
                        investment_auto_rebalance=household.investment_auto_rebalance,
                        investment_effective_tax_rate=investment_effective_tax_rate,
                        buy_fee_rate=buy_fee_rate,
                        sell_fee_rate=sell_fee_rate,
                        allocation_provider=lambda investable_surplus, current_cash_balance, reserve_target: investment_allocation_for_month(
                            monthly_surplus=investable_surplus,
                            cash_balance=current_cash_balance,
                            reserve_target=reserve_target,
                            household=household,
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
                home_total_price=scenario.total_price,
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
            monthly_cash_delta = (
                cash_income
                + provident_cash_receipt
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
                monthly_expense=(living_expense + scheduled_expense + child_expense + career_shock_self_payment + debt_payment + house_payment + vehicle_payment + vehicle_operating_cost),
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
    return MonthlyLedgerResult(
        projection_states=projection_states,
        account_snapshots=snapshots,
        ledger_entries=ledger,
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
    investment_withdrawal_at_purchase: Callable[..., InvestmentWithdrawalLike],
    investment_allocation_for_month: Callable[..., tuple[float, float]],
    monthly_happiness_score: Callable[..., float],
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
        investment_withdrawal_at_purchase=investment_withdrawal_at_purchase,
        investment_allocation_for_month=investment_allocation_for_month,
        monthly_happiness_score=monthly_happiness_score,
    )
