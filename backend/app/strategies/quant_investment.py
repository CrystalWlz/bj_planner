from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from math import floor
from typing import Protocol

from ..domain.quant_investment import (
    QuantRiskAssessment,
    assess_quant_risk,
    instrument_is_buyable,
    optimized_equity_weights,
    protected_cash_for_quant_investment,
)
from ..schemas import (
    HouseholdData,
    InvestmentInstrumentData,
    InvestmentMarketSnapshotData,
    PaperOrderData,
    PaperPortfolioSummary,
    QuantInvestmentPolicyData,
    QuantInvestmentProposalData,
)


SIGNAL_MODEL_VERSION = "monthly-drawdown-v2"
PORTFOLIO_CONSTRUCTOR_VERSION = "fixed-35-65-v2"
PRE_TRADE_RISK_VERSION = "cash-concentration-v2"
EXECUTION_PLANNER_VERSION = "paper-lot-slippage-v2"


@dataclass(frozen=True)
class QuantInstrumentCandidate:
    instrument_id: str
    instrument: InvestmentInstrumentData
    snapshot_id: str
    snapshot: InvestmentMarketSnapshotData
    price: float
    price_date: str
    execution_date: str = ""


@dataclass(frozen=True)
class TradeRiskDecision:
    allowed: bool
    maximum_amount: float
    reason: str


class SignalModel(Protocol):
    version: str

    def assess(
        self,
        policy: QuantInvestmentPolicyData,
        equity_snapshots: list[InvestmentMarketSnapshotData],
    ) -> QuantRiskAssessment: ...


class PortfolioConstructor(Protocol):
    version: str

    def target_weights(
        self,
        candidates: list[QuantInstrumentCandidate],
        policy: QuantInvestmentPolicyData,
        effective_equity_ratio: float,
    ) -> dict[str, float]: ...


class PreTradeRiskManager(Protocol):
    version: str

    def check(
        self,
        candidate: QuantInstrumentCandidate,
        requested_amount: float,
        total_budget: float,
        policy: QuantInvestmentPolicyData,
        as_of_date: str,
    ) -> TradeRiskDecision: ...


class ExecutionPlanner(Protocol):
    version: str

    def plan(
        self,
        candidate: QuantInstrumentCandidate,
        amount: float,
        policy: QuantInvestmentPolicyData,
        reason: str,
        side: str = "buy",
        funding_source: str = "external_contribution",
        is_rebalance: bool = False,
    ) -> PaperOrderData | None: ...


@dataclass(frozen=True)
class MonthlyDrawdownSignalModel:
    version: str = SIGNAL_MODEL_VERSION

    def assess(
        self,
        policy: QuantInvestmentPolicyData,
        equity_snapshots: list[InvestmentMarketSnapshotData],
    ) -> QuantRiskAssessment:
        return assess_quant_risk(policy, equity_snapshots)


@dataclass(frozen=True)
class Fixed3565PortfolioConstructor:
    version: str = PORTFOLIO_CONSTRUCTOR_VERSION

    def target_weights(
        self,
        candidates: list[QuantInstrumentCandidate],
        policy: QuantInvestmentPolicyData,
        effective_equity_ratio: float,
    ) -> dict[str, float]:
        if not candidates:
            return {}
        equity = [item for item in candidates if item.instrument.asset_class == "equity"]
        defensive = [item for item in candidates if item.instrument.asset_class == "defensive"]
        weights: dict[str, float] = {}
        if equity:
            if policy.research_strategy == "min_variance":
                relative = optimized_equity_weights([(item.instrument_id, item.snapshot) for item in equity])
            else:
                relative = {item.instrument_id: 1 / len(equity) for item in equity}
            for item in equity:
                weights[item.instrument_id] = max(0.0, effective_equity_ratio) * relative.get(item.instrument_id, 0.0)
        defensive_ratio = max(0.0, 1 - effective_equity_ratio)
        if defensive:
            for item in defensive:
                weights[item.instrument_id] = defensive_ratio / len(defensive)
        return weights


@dataclass(frozen=True)
class CashAndConcentrationRiskManager:
    version: str = PRE_TRADE_RISK_VERSION

    def check(
        self,
        candidate: QuantInstrumentCandidate,
        requested_amount: float,
        total_budget: float,
        policy: QuantInvestmentPolicyData,
        as_of_date: str,
    ) -> TradeRiskDecision:
        allowed, message = instrument_is_buyable(candidate.instrument, candidate.snapshot, policy, as_of_date=as_of_date)
        if not allowed:
            return TradeRiskDecision(False, 0.0, message)
        cap = min(
            max(0.0, total_budget * policy.max_single_instrument_ratio),
            policy.max_order_amount,
        )
        if candidate.instrument.monthly_purchase_limit is not None:
            cap = min(cap, candidate.instrument.monthly_purchase_limit)
        amount = min(max(0.0, requested_amount), cap)
        if amount <= 0:
            return TradeRiskDecision(False, 0.0, "订单金额触发单标的或最大订单金额限制。")
        return TradeRiskDecision(True, amount, "通过现金、交易资格、单标的集中度和最大订单金额检查。")


@dataclass(frozen=True)
class PaperLotExecutionPlanner:
    version: str = EXECUTION_PLANNER_VERSION

    def plan(
        self,
        candidate: QuantInstrumentCandidate,
        amount: float,
        policy: QuantInvestmentPolicyData,
        reason: str,
        side: str = "buy",
        funding_source: str = "external_contribution",
        is_rebalance: bool = False,
    ) -> PaperOrderData | None:
        if amount <= 0:
            return None
        price = candidate.price * (1 + policy.slippage_rate if side == "buy" else 1 - policy.slippage_rate)
        lot_size = max(1, candidate.instrument.lot_size)
        fee_rate = max(0.0, candidate.instrument.buy_fee_rate if side == "buy" else candidate.instrument.sell_fee_rate)
        quantity_budget = amount / (price * (1 + fee_rate)) if side == "buy" else amount / price
        quantity = floor(quantity_budget / lot_size) * lot_size
        if quantity <= 0:
            return None
        gross_amount = quantity * price
        fee = gross_amount * fee_rate
        total_amount = gross_amount + fee
        return PaperOrderData(
            proposal_id="",
            instrument_id=candidate.instrument_id,
            side=side,
            funding_source=funding_source,
            is_rebalance=is_rebalance,
            order_amount=round(total_amount if side == "buy" else gross_amount, 2),
            estimated_price=round(price, 6),
            estimated_quantity=round(quantity, 6),
            estimated_fee=round(fee, 2),
            lot_size=lot_size,
            expected_trade_date=candidate.execution_date or _next_weekday(candidate.price_date),
            status="proposed",
            reason=reason,
        )


@dataclass(frozen=True)
class QuantProposalBuildResult:
    proposal: QuantInvestmentProposalData
    orders: list[PaperOrderData]


def _latest_price(snapshot: InvestmentMarketSnapshotData, *, as_of_date: str) -> tuple[float, str] | None:
    bars = [
        bar
        for bar in snapshot.bars
        if bar.is_trading
        and not bar.is_suspended
        and (bar.adjusted_close or bar.close) > 0
        and (bar.price_date or bar.date) <= as_of_date
    ]
    if not bars:
        return None
    latest = max(bars, key=lambda bar: bar.price_date or bar.date)
    return latest.adjusted_close or latest.close, latest.price_date or latest.date


def _next_weekday(value: str) -> str:
    current = date.fromisoformat(value) + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.isoformat()


def _next_common_execution_date(
    candidates: list[QuantInstrumentCandidate],
    *,
    signal_date: str,
) -> tuple[str, bool]:
    future_calendars = [
        {day for day in candidate.snapshot.trading_days if day > signal_date}
        for candidate in candidates
    ]
    if future_calendars and all(future_calendars):
        common_dates = set.intersection(*future_calendars)
        if common_dates:
            return min(common_dates), True
    return _next_weekday(signal_date), False


def build_quant_monthly_proposal(
    *,
    household: HouseholdData,
    policy_id: str,
    policy: QuantInvestmentPolicyData,
    instruments: list[tuple[str, InvestmentInstrumentData]],
    snapshots: dict[str, tuple[str, InvestmentMarketSnapshotData]],
    signal_model: SignalModel | None = None,
    portfolio_constructor: PortfolioConstructor | None = None,
    risk_manager: PreTradeRiskManager | None = None,
    execution_planner: ExecutionPlanner | None = None,
    additional_goal_cash: float = 0.0,
    paper_portfolio: PaperPortfolioSummary | None = None,
) -> QuantProposalBuildResult:
    signal_model = signal_model or MonthlyDrawdownSignalModel()
    portfolio_constructor = portfolio_constructor or Fixed3565PortfolioConstructor()
    risk_manager = risk_manager or CashAndConcentrationRiskManager()
    execution_planner = execution_planner or PaperLotExecutionPlanner()
    instrument_map = dict(instruments)
    equity_snapshots = [snapshot for instrument_id, (_, snapshot) in snapshots.items() if instrument_map.get(instrument_id) and instrument_map[instrument_id].asset_class == "equity"]
    assessment = signal_model.assess(policy, equity_snapshots)
    protected_cash = protected_cash_for_quant_investment(household, additional_goal_cash=additional_goal_cash)
    investable_cash = max(0.0, household.cash_account_balance - protected_cash)
    monthly_surplus = max(0.0, household.monthly_income - household.monthly_expense - household.monthly_debt_payment)
    configured_budget = policy.default_monthly_budget or household.monthly_investment_amount or monthly_surplus * 0.25
    proposed_budget = min(investable_cash, max(0.0, configured_budget))
    reasons = list(assessment.reasons)
    if investable_cash <= 0:
        reasons.append("现金账户未超过应急金和近期计划支出保护线，本月不投入风险资产。")
    if assessment.state in {"frozen", "blocked"}:
        proposed_budget = 0.0

    candidates: list[QuantInstrumentCandidate] = []
    for instrument_id, instrument in instruments:
        snapshot_entry = snapshots.get(instrument_id)
        if snapshot_entry is None:
            reasons.append(f"{instrument.name} 缺少行情快照，已排除。")
            continue
        snapshot_id, snapshot = snapshot_entry
        historical_snapshot = snapshot.model_copy(
            update={
                "bars": [
                    bar
                    for bar in snapshot.bars
                    if (bar.price_date or bar.date) <= assessment.as_of_date
                ]
            }
        )
        price_data = _latest_price(historical_snapshot, as_of_date=assessment.as_of_date)
        if price_data is None:
            reasons.append(f"{instrument.name} 缺少有效收盘价，已排除。")
            continue
        price, price_date = price_data
        candidates.append(QuantInstrumentCandidate(instrument_id, instrument, snapshot_id, historical_snapshot, price, price_date))

    execution_date, execution_date_confirmed = _next_common_execution_date(
        candidates,
        signal_date=assessment.as_of_date,
    )
    candidates = [replace(candidate, execution_date=execution_date) for candidate in candidates]
    if candidates and not execution_date_confirmed:
        reasons.append("行情快照未覆盖下一共同开放日，订单日期按下一工作日估计，模拟成交前仍需人工确认交易日历。")

    weights = portfolio_constructor.target_weights(candidates, policy, assessment.effective_equity_cap)
    orders: list[PaperOrderData] = []
    market_allocations: dict[str, float] = {}
    for candidate in candidates:
        requested = proposed_budget * weights.get(candidate.instrument_id, 0.0)
        decision = risk_manager.check(candidate, requested, proposed_budget, policy, assessment.as_of_date)
        if not decision.allowed:
            reasons.append(f"{candidate.instrument.name}：{decision.reason}")
            continue
        market_cap = proposed_budget * policy.max_single_market_ratio
        market_remaining = max(0.0, market_cap - market_allocations.get(candidate.instrument.market, 0.0))
        approved_amount = min(decision.maximum_amount, market_remaining)
        if approved_amount <= 0:
            reasons.append(f"{candidate.instrument.name}：所在市场已达到单市场集中度上限。")
            continue
        order = execution_planner.plan(
            candidate,
            approved_amount,
            policy,
            f"月度定投 · {assessment.state} 风险状态 · {decision.reason} · 使用 {candidate.price_date} 已确认收盘价估算。",
        )
        if order is not None:
            orders.append(order)
            market_allocations[candidate.instrument.market] = market_allocations.get(candidate.instrument.market, 0.0) + order.order_amount
        else:
            reasons.append(f"{candidate.instrument.name}：订单金额不足以满足最小交易单位 {candidate.instrument.lot_size}。")
    rebalance_triggered = False
    current_equity_ratio = 0.0
    if paper_portfolio is not None and getattr(paper_portfolio, "total_equity", 0.0) > 0:
        total_equity = float(paper_portfolio.total_equity)
        current_equity = sum(position.market_value for position in paper_portfolio.positions if position.asset_class == "equity")
        current_equity_ratio = current_equity / total_equity
        current_month = int(assessment.as_of_date[5:7]) if len(assessment.as_of_date) >= 7 else 0
        rebalance_triggered = current_month in policy.rebalance_months and abs(current_equity_ratio - assessment.effective_equity_cap) >= policy.rebalance_threshold
        if rebalance_triggered:
            reasons.append("季度再平衡已触发：当前权益比例偏离目标超过阈值，订单只在模拟账户内调整。")
            candidate_by_id = {candidate.instrument_id: candidate for candidate in candidates}
            position_by_id = {position.instrument_id: position for position in paper_portfolio.positions}
            for position in paper_portfolio.positions:
                candidate = candidate_by_id.get(position.instrument_id)
                if candidate is None:
                    continue
                actual_weight = position.market_value / total_equity
                target_weight = weights.get(position.instrument_id, 0.0)
                if actual_weight <= target_weight + policy.rebalance_threshold:
                    continue
                sell_amount = (actual_weight - target_weight) * total_equity
                order = execution_planner.plan(candidate, sell_amount, policy, "季度再平衡卖出超配持仓", side="sell", funding_source="paper_cash", is_rebalance=True)
                if order is not None:
                    orders = [existing for existing in orders if existing.instrument_id != position.instrument_id]
                    orders.insert(0, order)
            available_cash = max(0.0, float(paper_portfolio.cash_balance))
            external_instrument_ids = {order.instrument_id for order in orders if order.funding_source == "external_contribution"}
            for candidate in candidates:
                if candidate.instrument_id in external_instrument_ids:
                    continue
                position = position_by_id.get(candidate.instrument_id)
                actual_weight = position.market_value / total_equity if position else 0.0
                target_weight = weights.get(candidate.instrument_id, 0.0)
                buy_amount = min(available_cash, max(0.0, target_weight - actual_weight - policy.rebalance_threshold) * total_equity)
                if buy_amount <= 0:
                    continue
                order = execution_planner.plan(candidate, buy_amount, policy, "季度再平衡买入低配持仓", side="buy", funding_source="paper_cash", is_rebalance=True)
                if order is not None:
                    orders.append(order)
                    available_cash = max(0.0, available_cash - order.order_amount)
    if not orders and proposed_budget > 0:
        reasons.append("没有通过交易、集中度、溢价和最小交易单位校验的标的，本月不生成买入订单。")

    proposal = QuantInvestmentProposalData(
        policy_id=policy_id,
        snapshot_ids=[candidate.snapshot_id for candidate in candidates],
        as_of_date=assessment.as_of_date,
        protected_cash=round(protected_cash, 2),
        investable_cash=round(investable_cash, 2),
        proposed_budget=round(sum(order.order_amount for order in orders if order.funding_source == "external_contribution"), 2),
        effective_equity_cap=assessment.effective_equity_cap,
        estimated_drawdown=round(assessment.drawdown, 6),
        risk_state=assessment.state,
        rebalance_triggered=rebalance_triggered,
        current_equity_ratio=round(current_equity_ratio, 6),
        target_weights=weights,
        strategy_versions={
            "signal_model": signal_model.version,
            "portfolio_constructor": portfolio_constructor.version,
            "pre_trade_risk_manager": risk_manager.version,
            "execution_planner": execution_planner.version,
        },
        reasons=reasons,
    )
    return QuantProposalBuildResult(proposal=proposal, orders=orders)
