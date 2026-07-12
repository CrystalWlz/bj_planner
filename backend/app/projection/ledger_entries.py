from __future__ import annotations

from typing import Literal

from ..schemas import MonthlyLedgerEntry
from .ledger_models import MonthlyLedgerEntryInputs


def ledger_entry(
    *,
    plan_variant: str,
    month: int,
    account: str,
    category: str,
    label: str,
    amount: float,
    direction: Literal["inflow", "outflow", "transfer", "valuation"],
) -> MonthlyLedgerEntry:
    return MonthlyLedgerEntry(
        plan_variant=plan_variant,
        month=month,
        account=account,
        category=category,
        label=label,
        amount=round(amount, 2),
        direction=direction,
    )


def build_monthly_ledger_entries(inputs: MonthlyLedgerEntryInputs) -> list[MonthlyLedgerEntry]:
    entries: list[MonthlyLedgerEntry] = []
    if inputs.vehicle_down_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="vehicle_down_payment",
                label="车辆首付及购置税现金支出",
                amount=-inputs.vehicle_down_payment,
                direction="outflow",
            )
        )
    if inputs.vehicle_plate_rental_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="vehicle_plate_rental",
                label="车辆牌照租赁现金支出",
                amount=-inputs.vehicle_plate_rental_payment,
                direction="outflow",
            )
        )
    if inputs.include_home_purchase_entries:
        entries.extend(
            [
                ledger_entry(
                    plan_variant=inputs.plan_variant,
                    month=inputs.month,
                    account="investment",
                    category="sell",
                    label="交易月理财变现",
                    amount=inputs.investment_sell_proceeds,
                    direction="transfer",
                ),
                ledger_entry(
                    plan_variant=inputs.plan_variant,
                    month=inputs.month,
                    account="cash",
                    category="home_purchase",
                    label="购房交易现金支出",
                    amount=-inputs.home_purchase_cash_out,
                    direction="outflow",
                ),
            ]
        )
    if inputs.renovation_expense:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="renovation",
                label="装修规划事件支出",
                amount=-inputs.renovation_expense,
                direction="outflow",
            )
        )
    if inputs.cash_income:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="income",
                label="家庭税后现金收入",
                amount=inputs.cash_income,
                direction="inflow",
            )
        )
    if inputs.pension_income:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="pension_income",
                label="养老金领取入账",
                amount=inputs.pension_income,
                direction="inflow",
            )
        )
    if inputs.living_expense:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="living_expense",
                label="家庭基础生活支出",
                amount=-inputs.living_expense,
                direction="outflow",
            )
        )
    if inputs.scheduled_expense:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="scheduled_expense",
                label="阶段性与定时支出",
                amount=-inputs.scheduled_expense,
                direction="outflow",
            )
        )
    if inputs.child_expense:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="child_expense",
                label="养娃计划支出",
                amount=-inputs.child_expense,
                direction="outflow",
            )
        )
    if inputs.career_shock_self_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="career_shock_self_payment",
                label="灵活就业自缴社保公积金",
                amount=-inputs.career_shock_self_payment,
                direction="outflow",
            )
        )
    if inputs.regular_debt_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="regular_debt_payment",
                label="已有固定还款",
                amount=-inputs.regular_debt_payment,
                direction="outflow",
            )
        )
    if inputs.phased_loan_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="phased_loan_payment",
                label="已有贷款还款",
                amount=-inputs.phased_loan_payment,
                direction="outflow",
            )
        )
    if inputs.house_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="house_payment",
                label="房贷现金还款",
                amount=-inputs.house_payment,
                direction="outflow",
            )
        )
    if inputs.vehicle_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="vehicle_payment",
                label="车贷现金还款",
                amount=-inputs.vehicle_payment,
                direction="outflow",
            )
        )
    if inputs.vehicle_operating_cost:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="vehicle_operating_cost",
                label="车辆使用现金支出",
                amount=-inputs.vehicle_operating_cost,
                direction="outflow",
            )
        )
    if inputs.personal_pension_contribution:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="personal_pension",
                category="personal_pension_contribution",
                label="个人养老金账户缴费",
                amount=-inputs.personal_pension_contribution,
                direction="transfer",
            )
        )
    if inputs.personal_pension_return:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="personal_pension",
                category="personal_pension_return",
                label="个人养老金账户收益",
                amount=inputs.personal_pension_return,
                direction="valuation",
            )
        )
    if inputs.personal_pension_withdrawal:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="personal_pension",
                category="personal_pension_withdrawal",
                label="个人养老金领取到账",
                amount=inputs.personal_pension_withdrawal,
                direction="inflow",
            )
        )
    if inputs.personal_pension_suspended_contribution:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="personal_pension",
                category="personal_pension_suspended_contribution",
                label="因现金安全暂停的个人养老金缴费",
                amount=inputs.personal_pension_suspended_contribution,
                direction="valuation",
            )
        )
    if inputs.personal_pension_withdrawal_tax:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="personal_pension",
                category="personal_pension_withdrawal_tax",
                label="个人养老金领取税",
                amount=-inputs.personal_pension_withdrawal_tax,
                direction="outflow",
            )
        )
    if inputs.personal_pension_redemption_fee:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="personal_pension",
                category="personal_pension_redemption_fee",
                label="个人养老金产品赎回或退保费用",
                amount=-inputs.personal_pension_redemption_fee,
                direction="outflow",
            )
        )
    if inputs.investment_return:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="investment",
                category="investment_return",
                label="理财账户收益",
                amount=inputs.investment_return,
                direction="valuation",
            )
        )
    if inputs.investment_tax:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="investment",
                category="investment_tax",
                label="理财收益税费",
                amount=-inputs.investment_tax,
                direction="outflow",
            )
        )
    if inputs.investment_fee:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="investment",
                category="investment_fee",
                label="理财交易手续费",
                amount=-inputs.investment_fee,
                direction="outflow",
            )
        )
    if inputs.investment_contribution:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="investment",
                category="contribution",
                label="理财定投买入",
                amount=inputs.investment_contribution,
                direction="transfer",
            )
        )
    if inputs.liquidity_sell_proceeds:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="investment",
                category="liquidity_redemption",
                label="现金安全垫赎回",
                amount=inputs.liquidity_sell_proceeds,
                direction="transfer",
            )
        )
    if inputs.provident_deposit:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="provident",
                category="provident_deposit",
                label="公积金账户缴存",
                amount=inputs.provident_deposit,
                direction="inflow",
            )
        )
    if inputs.pension_account_payout:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="social_security",
                category="pension_account_payout",
                label="养老保险个人账户计发支出",
                amount=-inputs.pension_account_payout,
                direction="outflow",
            )
        )
    if inputs.medical_account_healthcare_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="social_security",
                category="medical_healthcare_outflow",
                label="医保个人账户支付医疗支出",
                amount=-inputs.medical_account_healthcare_payment,
                direction="outflow",
            )
        )
    if inputs.medical_account_mutual_aid_payment:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="social_security",
                category="medical_mutual_aid_outflow",
                label="医保大额互助扣缴",
                amount=-inputs.medical_account_mutual_aid_payment,
                direction="outflow",
            )
        )
    if inputs.provident_cash_receipt:
        entries.append(
            ledger_entry(
                plan_variant=inputs.plan_variant,
                month=inputs.month,
                account="cash",
                category="provident_withdrawal",
                label="公积金提取现金到账",
                amount=inputs.provident_cash_receipt,
                direction="inflow",
            )
        )
    return entries


