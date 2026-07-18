from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from ..schemas import (
    HouseholdData,
    InvestmentInstrumentData,
    InvestmentMarketSnapshotData,
    QuantBacktestResult,
    QuantInvestmentPolicyData,
)


@dataclass(frozen=True)
class QuantRiskAssessment:
    as_of_date: str
    drawdown: float
    effective_equity_cap: float
    state: str
    reasons: list[str]


def protected_cash_for_quant_investment(household: HouseholdData) -> float:
    """Cash that remains unavailable to the investment strategy.

    The normal ledger remains the source of truth for full lifecycle goal
    feasibility.  This conservative boundary prevents the trade proposal
    endpoint from treating its own estimate as permission to spend emergency
    funds or the next two years of scheduled cash obligations.
    """
    reserve_months = max(
        household.required_liquidity_months,
        household.investment_cash_reserve_months,
        6,
    )
    monthly_expense = max(0.0, household.monthly_expense + household.monthly_debt_payment)
    scheduled_next_24 = sum(
        max(0.0, item.amount)
        for item in household.scheduled_expenses
        if item.enabled and item.frequency in {"one_time", "annual_once"}
    )
    return round(monthly_expense * reserve_months + scheduled_next_24, 2)


def _latest_trading_bar(snapshot: InvestmentMarketSnapshotData):
    bars = [bar for bar in snapshot.bars if bar.is_trading]
    return max(bars, key=lambda bar: bar.date) if bars else None


def _drawdown_from_prices(prices: Iterable[float]) -> float:
    high_water = 0.0
    maximum = 0.0
    for value in prices:
        if value <= 0:
            continue
        high_water = max(high_water, value)
        if high_water > 0:
            maximum = max(maximum, (high_water - value) / high_water)
    return maximum


def assess_quant_risk(
    policy: QuantInvestmentPolicyData,
    equity_snapshots: Iterable[InvestmentMarketSnapshotData],
) -> QuantRiskAssessment:
    series: list[list[float]] = []
    dates: set[str] = set()
    for snapshot in equity_snapshots:
        usable = [bar for bar in snapshot.bars if bar.is_trading and (bar.adjusted_close or bar.close) > 0]
        if len(usable) < 2:
            continue
        usable.sort(key=lambda bar: bar.date)
        series.append([bar.adjusted_close or bar.close for bar in usable])
        dates.add(usable[-1].date)
    as_of_date = max(dates) if dates else date.today().isoformat()
    if not series:
        return QuantRiskAssessment(
            as_of_date=as_of_date,
            drawdown=0.0,
            effective_equity_cap=0.0,
            state="blocked",
            reasons=["没有足够的权益标的日线数据，不能生成量化定投提案。"],
        )

    # Normalize each price series, then use the equal-weighted basket only as a
    # risk sensor.  It is not a claim that the family currently holds it.
    common_length = min(len(values) for values in series)
    normalized = [values[-common_length:] for values in series]
    basket = [sum(values[index] / values[0] for values in normalized) / len(normalized) for index in range(common_length)]
    drawdown = _drawdown_from_prices(basket)
    if drawdown >= policy.drawdown_freeze_threshold:
        return QuantRiskAssessment(as_of_date, drawdown, 0.0, "frozen", ["权益风险篮子回撤达到冻结阈值，停止生成风险资产买入提案并等待人工复核。"])
    if drawdown >= policy.drawdown_pause_threshold:
        return QuantRiskAssessment(as_of_date, drawdown, 0.0, "paused", ["权益风险篮子回撤达到暂停阈值，本月资金保留在防御资产或现金桶。"])
    if drawdown >= policy.drawdown_reduce_threshold:
        return QuantRiskAssessment(as_of_date, drawdown, min(policy.equity_cap, policy.drawdown_reduced_equity_cap), "reduced", ["权益风险篮子回撤达到降仓阈值，新增权益比例已下调。"])
    return QuantRiskAssessment(as_of_date, drawdown, policy.equity_cap, "normal", ["风险篮子未触发回撤保护，按既定权益上限生成月度提案。"])


def instrument_is_buyable(
    instrument: InvestmentInstrumentData,
    snapshot: InvestmentMarketSnapshotData,
    policy: QuantInvestmentPolicyData,
    *,
    as_of_date: str,
) -> tuple[bool, str]:
    if not instrument.enabled:
        return False, "标的已停用。"
    if instrument.purchase_suspended:
        return False, "该标的已标记为暂停申购或交易。"
    if instrument.market == "hong_kong_connect" and not instrument.hong_kong_connect_eligible:
        return False, "尚未确认该标的为港股通合资格证券。"
    latest = _latest_trading_bar(snapshot)
    if latest is None:
        return False, "没有可用的交易日价格。"
    if instrument.market == "qdii_fund":
        return False, "场外 QDII 仅支持人工申购确认，暂不生成模拟盘口订单。"
    if instrument.market == "qdii_etf":
        if latest.nav is None or not latest.nav_date:
            return False, "跨境 QDII ETF 缺少净值，不能判断溢价风险。"
        try:
            nav_age = (date.fromisoformat(as_of_date) - date.fromisoformat(latest.nav_date)).days
        except ValueError:
            return False, "跨境 QDII ETF 的净值日期格式无效。"
        if nav_age > policy.qdii_nav_max_stale_days:
            return False, "跨境 QDII ETF 净值已过期，暂停新增买入。"
        premium = latest.premium_rate
        if premium is None:
            premium = latest.close / latest.nav - 1
        threshold = instrument.qdii_premium_threshold if instrument.qdii_premium_threshold is not None else policy.qdii_premium_threshold
        if premium > threshold:
            return False, "跨境 QDII ETF 溢价超过风险阈值，暂停新增买入。"
    return True, "可交易。"


def rebalance_due(current_equity_ratio: float, target_equity_ratio: float, policy: QuantInvestmentPolicyData) -> bool:
    return abs(max(0.0, current_equity_ratio) - max(0.0, target_equity_ratio)) >= policy.rebalance_threshold


def optimized_equity_weights(
    snapshots: list[tuple[str, InvestmentMarketSnapshotData]],
) -> dict[str, float]:
    """Use PyPortfolioOpt when available, with an equal-weight safe fallback.

    The optimizer only chooses weights among the user's manually approved
    equity universe.  It never selects new securities and does not bypass
    policy-level cash, drawdown or QDII premium gates.
    """
    if not snapshots:
        return {}
    equal = {instrument_id: 1 / len(snapshots) for instrument_id, _ in snapshots}
    try:
        import pandas as pd
        from pypfopt import EfficientFrontier, risk_models
    except ImportError:
        return equal
    price_by_instrument: dict[str, dict[str, float]] = {}
    for instrument_id, snapshot in snapshots:
        price_by_instrument[instrument_id] = {
            bar.date: float(bar.adjusted_close or bar.close)
            for bar in snapshot.bars
            if bar.is_trading and (bar.adjusted_close or bar.close) > 0
        }
    common_dates = set.intersection(*(set(values) for values in price_by_instrument.values())) if price_by_instrument else set()
    if len(common_dates) < 60:
        return equal
    prices = pd.DataFrame(
        {instrument_id: [values[day] for day in sorted(common_dates)] for instrument_id, values in price_by_instrument.items()},
        index=sorted(common_dates),
    )
    try:
        covariance = risk_models.sample_cov(prices)
        optimizer = EfficientFrontier(None, covariance, weight_bounds=(0, 1))
        optimizer.min_volatility()
        cleaned = optimizer.clean_weights(cutoff=1e-4)
        total = sum(max(0.0, float(value)) for value in cleaned.values())
        if total <= 0:
            return equal
        return {instrument_id: max(0.0, float(cleaned.get(instrument_id, 0))) / total for instrument_id, _ in snapshots}
    except Exception:
        return equal


def run_monthly_backtest(
    policy: QuantInvestmentPolicyData,
    equity_snapshots: Iterable[InvestmentMarketSnapshotData],
    *,
    monthly_contribution: float,
) -> QuantBacktestResult:
    series = []
    for snapshot in equity_snapshots:
        values = [bar for bar in snapshot.bars if bar.is_trading and (bar.adjusted_close or bar.close) > 0]
        if len(values) >= 36:
            values.sort(key=lambda bar: bar.date)
            series.append(values)
    if not series:
        raise ValueError("至少需要一只拥有 36 个交易月的权益 ETF 日线数据才能回测。")
    common_length = min(len(values) for values in series)
    # Keep at most five years of daily history.  A completed month is roughly
    # 21 trading sessions, not 12 daily observations.
    monthly_points = min(common_length, 60 * 21)
    # A daily source is compressed into regular monthly checkpoints without
    # looking ahead.  The last observation in each completed 21-day window is
    # used for the next month's contribution.
    prices = [values[-monthly_points:] for values in series]
    checkpoints = list(range(20, monthly_points, 21))
    if len(checkpoints) < 36:
        raise ValueError("共同可用历史不足 36 个月，不能给出可比较的回测结果。")
    strategy_value = 0.0
    static_value = 0.0
    strategy_high = 0.0
    static_high = 0.0
    strategy_dd = 0.0
    static_dd = 0.0
    basket_history: list[float] = []
    start_date = prices[0][0].date
    end_date = prices[0][checkpoints[-1]].date
    prior_prices: list[float] | None = None
    for checkpoint in checkpoints:
        current_prices = [values[checkpoint].adjusted_close or values[checkpoint].close for values in prices]
        if prior_prices is None:
            monthly_return = 0.0
        else:
            monthly_return = sum(current / prior - 1 for current, prior in zip(current_prices, prior_prices)) / len(current_prices)
        basket_history.append((basket_history[-1] if basket_history else 1.0) * (1 + monthly_return))
        drawdown = _drawdown_from_prices(basket_history)
        if drawdown >= policy.drawdown_pause_threshold:
            strategy_equity = 0.0
        elif drawdown >= policy.drawdown_reduce_threshold:
            strategy_equity = min(policy.equity_cap, policy.drawdown_reduced_equity_cap)
        else:
            strategy_equity = policy.equity_cap
        strategy_value = strategy_value * (1 + monthly_return * strategy_equity) + monthly_contribution
        static_value = static_value * (1 + monthly_return * policy.equity_cap) + monthly_contribution
        strategy_high = max(strategy_high, strategy_value)
        static_high = max(static_high, static_value)
        if strategy_high:
            strategy_dd = max(strategy_dd, (strategy_high - strategy_value) / strategy_high)
        if static_high:
            static_dd = max(static_dd, (static_high - static_value) / static_high)
        prior_prices = current_prices
    return QuantBacktestResult(
        policy_id="",
        start_date=start_date,
        end_date=end_date,
        months=len(checkpoints),
        strategy_terminal_value=round(strategy_value, 2),
        static_terminal_value=round(static_value, 2),
        strategy_max_drawdown=round(strategy_dd, 6),
        static_max_drawdown=round(static_dd, 6),
        warnings=["回测基于用户手工标的池，不代表未来收益；未将回测结果用于自动选择标的。"],
    )
