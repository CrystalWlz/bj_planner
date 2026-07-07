from __future__ import annotations

from dataclasses import dataclass

from ..schemas import HouseholdData, InvestmentAllocationSummary, InvestmentTaxProfileData


@dataclass(frozen=True)
class InvestmentTaxEstimate:
    effective_rate: float
    source: str
    detail: str


def investment_tax_profile_weighted_rate(profile: InvestmentTaxProfileData) -> float:
    return max(
        0.0,
        min(
            1.0,
            profile.deposit_interest_ratio * profile.deposit_interest_tax_rate
            + profile.fund_dividend_ratio * profile.fund_dividend_tax_rate
            + profile.stock_dividend_short_ratio * profile.stock_dividend_short_holding_tax_rate
            + profile.stock_dividend_long_ratio * profile.stock_dividend_long_holding_tax_rate
            + profile.bond_interest_ratio * profile.bond_interest_tax_rate
            + profile.overseas_asset_ratio * profile.overseas_asset_tax_rate,
        ),
    )


def investment_tax_profile_has_manual_source(profile: InvestmentTaxProfileData) -> bool:
    return any(
        value > 0
        for value in (
            profile.deposit_interest_ratio,
            profile.fund_dividend_ratio,
            profile.stock_dividend_short_ratio,
            profile.stock_dividend_long_ratio,
            profile.bond_interest_ratio,
            profile.overseas_asset_ratio,
        )
    )


def investment_strategy_allocation(household: HouseholdData) -> tuple[float, float, float]:
    if household.investment_plan_name == "cash_only":
        return 0.0, 0.0, 1.0

    equity = max(0.0, household.investment_equity_ratio)
    bond = max(0.0, household.investment_bond_ratio)
    cash = max(0.0, household.investment_cash_ratio)
    total = equity + bond + cash
    if total <= 0:
        return 0.25, 0.45, 0.30
    return equity / total, bond / total, cash / total


def auto_investment_tax_profile_from_strategy(household: HouseholdData) -> InvestmentTaxProfileData:
    equity, bond, cash = investment_strategy_allocation(household)
    return InvestmentTaxProfileData(
        deposit_interest_ratio=cash,
        deposit_interest_tax_rate=0.0,
        bond_interest_ratio=bond * 0.30,
        bond_interest_tax_rate=0.20,
        stock_dividend_short_ratio=equity * 0.05,
        stock_dividend_short_holding_tax_rate=0.20,
        stock_dividend_long_ratio=equity * 0.10,
        stock_dividend_long_holding_tax_rate=0.0,
        fund_dividend_ratio=equity * 0.03,
        fund_dividend_tax_rate=0.0,
        overseas_asset_ratio=0.0,
        overseas_asset_tax_rate=0.0,
    )


def investment_tax_estimate(household: HouseholdData) -> InvestmentTaxEstimate:
    profile = household.investment_tax_profile or InvestmentTaxProfileData()
    if investment_tax_profile_has_manual_source(profile):
        rate = investment_tax_profile_weighted_rate(profile)
        return InvestmentTaxEstimate(
            effective_rate=rate,
            source="manual",
            detail=(
                f"当前使用手动填写的理财收益来源占比，折算有效税率约 {rate:.2%}。"
                "这里的占比是收益来源占比，不是资产配置占比；后端会把它直接用于投资账户税后收益推演。"
            ),
        )

    simplified_rate = max(0.0, min(1.0, household.investment_taxable_return_ratio * household.investment_return_tax_rate))
    if simplified_rate > 0:
        return InvestmentTaxEstimate(
            effective_rate=simplified_rate,
            source="manual",
            detail=(
                f"当前使用简化参数：应税收益比例 {household.investment_taxable_return_ratio:.2%}，"
                f"理财收益税率 {household.investment_return_tax_rate:.2%}，折算有效税率约 {simplified_rate:.2%}。"
            ),
        )

    auto_profile = auto_investment_tax_profile_from_strategy(household)
    auto_rate = investment_tax_profile_weighted_rate(auto_profile)
    equity, bond, cash = investment_strategy_allocation(household)
    if auto_rate <= 0:
        return InvestmentTaxEstimate(
            effective_rate=0.0,
            source="strategy_auto",
            detail=(
                "当前未手动填写理财税务来源占比，后端按理财策略资产配置自动估算。"
                f"当前配置约为权益 {equity:.0%}、固收 {bond:.0%}、现金 {cash:.0%}；"
                "现金部分按储蓄存款利息暂免个税、长持股息和国债/政策性金融债等免税口径处理，因此有效税率为 0。"
            ),
        )

    return InvestmentTaxEstimate(
        effective_rate=auto_rate,
        source="strategy_auto",
        detail=(
            "当前未手动填写理财税务来源占比，后端按理财策略资产配置自动估算："
            f"权益 {equity:.0%}、固收 {bond:.0%}、现金 {cash:.0%}。"
            "现金部分按储蓄存款利息暂免个税；固收部分按普通债券利息的保守比例计入 20% 利息税口径，"
            "其余国债、政策性金融债或债基净值收益暂按免税/不单独扣税口径；权益部分只对预计短持分红收益按持有期差别化口径计税，"
            f"折算当前投资收益有效税率约 {auto_rate:.2%}。"
        ),
    )


def investment_effective_tax_rate(household: HouseholdData) -> float:
    return investment_tax_estimate(household).effective_rate


def investment_allocation_for_month(
    *,
    monthly_surplus: float,
    cash_balance: float,
    reserve_target: float,
    household: HouseholdData,
) -> tuple[float, float]:
    setting = max(0.0, household.monthly_investment_amount)
    if setting <= 0:
        return 0.0, 0.0
    if not household.investment_auto_rebalance:
        return min(setting, max(0.0, monthly_surplus)), 0.0

    projected_cash_before_investment = cash_balance + monthly_surplus
    available_above_reserve = max(0.0, projected_cash_before_investment - reserve_target)
    if available_above_reserve <= 0:
        return 0.0, 0.0

    base = min(setting, max(0.0, monthly_surplus), available_above_reserve)
    excess_cash = max(0.0, cash_balance - reserve_target)
    sweep = min(excess_cash / 12, max(0.0, available_above_reserve - base))
    return max(0.0, base), max(0.0, sweep)


def build_investment_allocation_summary(
    household: HouseholdData,
    *,
    monthly_surplus: float,
    current_monthly_expense: float,
) -> InvestmentAllocationSummary:
    reserve_months = household.investment_cash_reserve_months or household.required_liquidity_months or 6
    reserve_target = max(0.0, current_monthly_expense * reserve_months)
    monthly_setting = 0.0 if household.investment_plan_name == "cash_only" else max(0.0, household.monthly_investment_amount)
    allocation_household = household.model_copy(update={"monthly_investment_amount": monthly_setting})
    base, sweep = investment_allocation_for_month(
        monthly_surplus=monthly_surplus,
        cash_balance=household.cash_account_balance,
        reserve_target=reserve_target,
        household=allocation_household,
    )
    total = max(0.0, base + sweep)
    buy_fee = total * max(0.0, household.investment_buy_fee_rate)
    return InvestmentAllocationSummary(
        monthly_surplus=round(max(0.0, monthly_surplus), 2),
        reserve_target=round(reserve_target, 2),
        reserve_gap=round(max(0.0, reserve_target - household.cash_account_balance), 2),
        base_investment=round(base, 2),
        cash_sweep_investment=round(sweep, 2),
        total_investment=round(total, 2),
        buy_fee=round(buy_fee, 2),
        net_investment=round(max(0.0, total - buy_fee), 2),
    )
