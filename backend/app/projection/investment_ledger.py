from __future__ import annotations

from .ledger_models import (
    InvestmentAllocationProvider,
    InvestmentCashState,
    InvestmentWithdrawalProvider,
)


def apply_purchase_month_investment_cash_state(
    *,
    cash_balance: float,
    investment_balance: float,
    monthly_surplus: float,
    required_cash_after_pf: float,
    vehicle_down_payment: float,
    monthly_return: float,
    investment_enabled: bool,
    investment_effective_tax_rate: float,
    withdrawal_provider: InvestmentWithdrawalProvider,
) -> InvestmentCashState:
    investment_return = investment_balance * monthly_return if investment_enabled else 0.0
    investment_tax = max(0.0, investment_return) * investment_effective_tax_rate if investment_return else 0.0
    investment_balance_after_return = max(0.0, investment_balance + investment_return - investment_tax)
    withdrawal = withdrawal_provider(cash_balance + monthly_surplus, investment_balance_after_return)
    cash_after = withdrawal.cash_after_transaction - vehicle_down_payment
    investment_after = max(0.0, withdrawal.investment_after_transaction)
    return InvestmentCashState(
        cash_balance=cash_after,
        investment_balance=investment_after,
        investment_return=investment_return,
        investment_tax=investment_tax,
        investment_fee=withdrawal.sell_fee,
        investment_sell_fee=withdrawal.sell_fee,
        investment_sell_proceeds=withdrawal.sell_proceeds,
        transaction_cash_in=withdrawal.sell_proceeds,
        transaction_cash_out=required_cash_after_pf,
    )


def apply_regular_month_investment_cash_state(
    *,
    cash_balance: float,
    investment_balance: float,
    monthly_surplus: float,
    vehicle_down_payment: float,
    reserve_target: float,
    monthly_return: float,
    investment_enabled: bool,
    investment_auto_rebalance: bool,
    investment_effective_tax_rate: float,
    buy_fee_rate: float,
    sell_fee_rate: float,
    allocation_provider: InvestmentAllocationProvider,
) -> InvestmentCashState:
    investable_surplus = monthly_surplus - vehicle_down_payment
    investment_return = investment_balance * monthly_return if investment_enabled else 0.0
    investment_tax = max(0.0, investment_return) * investment_effective_tax_rate if investment_return else 0.0
    investment_balance_after_return = max(0.0, investment_balance + investment_return - investment_tax)
    projected_cash_before_investment = cash_balance + investable_surplus
    liquidity_sell_proceeds = 0.0
    investment_sell_fee = 0.0
    investment_sell_proceeds = 0.0
    investment_fee = 0.0
    cash_after_liquidity = cash_balance
    investment_after_liquidity = investment_balance_after_return
    if (
        investment_enabled
        and investment_auto_rebalance
        and projected_cash_before_investment < reserve_target
        and investment_after_liquidity > 0
    ):
        liquidity_need = max(0.0, reserve_target - projected_cash_before_investment)
        gross_sell = min(
            investment_after_liquidity,
            liquidity_need / max(0.01, 1 - sell_fee_rate),
        )
        investment_sell_fee = gross_sell * sell_fee_rate
        liquidity_sell_proceeds = max(0.0, gross_sell - investment_sell_fee)
        investment_sell_proceeds += liquidity_sell_proceeds
        investment_fee += investment_sell_fee
        investment_after_liquidity = max(0.0, investment_after_liquidity - gross_sell)
        cash_after_liquidity += liquidity_sell_proceeds
    investment_contribution_base = 0.0
    investment_contribution_cash_sweep = 0.0
    if investment_enabled:
        investment_contribution_base, investment_contribution_cash_sweep = allocation_provider(
            investable_surplus,
            cash_after_liquidity,
            reserve_target,
        )
    investment_contribution = investment_contribution_base + investment_contribution_cash_sweep
    investment_buy_fee = investment_contribution * buy_fee_rate
    investment_fee += investment_buy_fee
    net_investment = max(0.0, investment_contribution - investment_buy_fee)
    cash_after = cash_after_liquidity + monthly_surplus - investment_contribution - vehicle_down_payment
    investment_after = max(0.0, investment_after_liquidity + net_investment)
    return InvestmentCashState(
        cash_balance=cash_after,
        investment_balance=investment_after,
        investment_return=investment_return,
        investment_tax=investment_tax,
        investment_fee=investment_fee,
        investment_buy_fee=investment_buy_fee,
        investment_sell_fee=investment_sell_fee,
        investment_sell_proceeds=investment_sell_proceeds,
        liquidity_sell_proceeds=liquidity_sell_proceeds,
        investment_contribution_base=investment_contribution_base,
        investment_contribution_cash_sweep=investment_contribution_cash_sweep,
        investment_contribution=investment_contribution,
    )


