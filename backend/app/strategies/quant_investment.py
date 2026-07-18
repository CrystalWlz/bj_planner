from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.quant_investment import assess_quant_risk, instrument_is_buyable, optimized_equity_weights, protected_cash_for_quant_investment
from ..schemas import (
    HouseholdData,
    InvestmentInstrumentData,
    InvestmentMarketSnapshotData,
    PaperOrderData,
    QuantInvestmentPolicyData,
    QuantInvestmentProposalData,
)


@dataclass(frozen=True)
class QuantProposalBuildResult:
    proposal: QuantInvestmentProposalData
    orders: list[PaperOrderData]


def _latest_price(snapshot: InvestmentMarketSnapshotData) -> tuple[float, str] | None:
    bars = [bar for bar in snapshot.bars if bar.is_trading and (bar.adjusted_close or bar.close) > 0]
    if not bars:
        return None
    latest = max(bars, key=lambda bar: bar.date)
    return latest.adjusted_close or latest.close, latest.date


def build_quant_monthly_proposal(
    *,
    household: HouseholdData,
    policy_id: str,
    policy: QuantInvestmentPolicyData,
    instruments: list[tuple[str, InvestmentInstrumentData]],
    snapshots: dict[str, tuple[str, InvestmentMarketSnapshotData]],
) -> QuantProposalBuildResult:
    equity_snapshots = [snapshot for instrument_id, (_, snapshot) in snapshots.items() if any(item_id == instrument_id and item.asset_class == "equity" for item_id, item in instruments)]
    assessment = assess_quant_risk(policy, equity_snapshots)
    protected_cash = protected_cash_for_quant_investment(household)
    investable_cash = max(0.0, household.cash_account_balance - protected_cash)
    monthly_surplus = max(0.0, household.monthly_income - household.monthly_expense - household.monthly_debt_payment)
    configured_budget = policy.default_monthly_budget or household.monthly_investment_amount or monthly_surplus * 0.25
    proposed_budget = min(investable_cash, max(0.0, configured_budget))
    reasons = list(assessment.reasons)
    if investable_cash <= 0:
        reasons.append("现金账户未超过应急金和近期计划支出保护线，本月不投入风险资产。")
    if assessment.effective_equity_cap <= 0:
        proposed_budget = 0.0

    candidates: list[tuple[str, InvestmentInstrumentData, InvestmentMarketSnapshotData, float, str]] = []
    for instrument_id, instrument in instruments:
        if instrument.asset_class != "equity":
            continue
        snapshot_entry = snapshots.get(instrument_id)
        if snapshot_entry is None:
            reasons.append(f"{instrument.name} 缺少行情快照，已排除。")
            continue
        _, snapshot = snapshot_entry
        allowed, message = instrument_is_buyable(instrument, snapshot, policy, as_of_date=assessment.as_of_date)
        if not allowed:
            reasons.append(f"{instrument.name}：{message}")
            continue
        price_data = _latest_price(snapshot)
        if price_data is None:
            reasons.append(f"{instrument.name} 缺少有效收盘价，已排除。")
            continue
        price, price_date = price_data
        candidates.append((instrument_id, instrument, snapshot, price, price_date))

    if not candidates and proposed_budget > 0:
        reasons.append("没有通过交易与溢价校验的权益 ETF，本月不生成买入订单。")
        proposed_budget = 0.0
    orders: list[PaperOrderData] = []
    allocation_budget = proposed_budget * assessment.effective_equity_cap
    if allocation_budget > 0 and candidates:
        optimized_weights = optimized_equity_weights([(instrument_id, snapshot) for instrument_id, _instrument, snapshot, _price, _price_date in candidates])
        for instrument_id, instrument, _snapshot, price, price_date in candidates:
            per_instrument = allocation_budget * optimized_weights.get(instrument_id, 1 / len(candidates))
            if instrument.monthly_purchase_limit is not None:
                per_order_budget = min(per_instrument, instrument.monthly_purchase_limit)
            else:
                per_order_budget = per_instrument
            estimated_fee = per_order_budget * instrument.buy_fee_rate
            quantity = max(0.0, (per_order_budget - estimated_fee) / price)
            if quantity <= 0:
                continue
            orders.append(
                PaperOrderData(
                    proposal_id="",
                    instrument_id=instrument_id,
                    side="buy",
                    order_amount=round(per_order_budget, 2),
                    estimated_price=round(price, 6),
                    estimated_quantity=round(quantity, 6),
                    estimated_fee=round(estimated_fee, 2),
                    status="proposed",
                    reason=f"月度定投 · {assessment.state} 风险状态 · 使用 {price_date} 已确认收盘价估算。",
                )
            )
    snapshot_ids = [snapshot_id for snapshot_id, _snapshot in snapshots.values()]
    proposal = QuantInvestmentProposalData(
        policy_id=policy_id,
        snapshot_ids=snapshot_ids,
        as_of_date=assessment.as_of_date,
        protected_cash=round(protected_cash, 2),
        investable_cash=round(investable_cash, 2),
        proposed_budget=round(allocation_budget if orders else 0.0, 2),
        effective_equity_cap=assessment.effective_equity_cap,
        estimated_drawdown=round(assessment.drawdown, 6),
        risk_state=assessment.state,
        reasons=reasons,
    )
    return QuantProposalBuildResult(proposal=proposal, orders=orders)
