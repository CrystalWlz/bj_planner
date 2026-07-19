from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import json
from typing import Iterable

from ..schemas import (
    HouseholdData,
    InvestmentInstrumentData,
    InvestmentMarketBarData,
    InvestmentMarketSnapshotData,
    QuantBacktestResult,
    QuantInvestmentPolicyData,
)


QUANT_BACKTEST_ENGINE_VERSION = "calendar-risk-v8"
QUANT_RECORDER_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class QuantRiskAssessment:
    as_of_date: str
    drawdown: float
    effective_equity_cap: float
    state: str
    reasons: list[str]


def execution_market_price(bar: InvestmentMarketBarData) -> float:
    """Return the actual close used for executable orders and paper valuation."""
    return float(bar.close)


def research_market_price(bar: InvestmentMarketBarData) -> float:
    """Return the total-return research price without changing executable quotes."""
    return float(bar.adjusted_close or bar.close)


def _month_ordinal(value: str) -> int:
    year_text, month_text = value[:7].split("-", 1)
    return int(year_text) * 12 + int(month_text) - 1


def _scheduled_expenses_next_24_months(household: HouseholdData, *, as_of_month: str) -> float:
    start_ordinal = _month_ordinal(as_of_month)
    end_ordinal = start_ordinal + 23
    total = 0.0
    for item in household.scheduled_expenses:
        item_start = _month_ordinal(item.start_month)
        item_end = _month_ordinal(item.end_month) if item.end_month else end_ordinal
        overlap_start = max(start_ordinal, item_start)
        overlap_end = min(end_ordinal, item_end)
        if overlap_start > overlap_end:
            continue
        if item.frequency == "monthly":
            total += item.monthly_amount * (overlap_end - overlap_start + 1)
        elif item.frequency == "one_time":
            total += item.monthly_amount
        else:
            for ordinal in range(overlap_start, overlap_end + 1):
                if ordinal % 12 + 1 == item.annual_occurrence_month:
                    total += item.monthly_amount
    return total


def protected_cash_for_quant_investment(
    household: HouseholdData,
    *,
    additional_goal_cash: float = 0.0,
    as_of_month: str | None = None,
) -> float:
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
    current_month = as_of_month or date.today().isoformat()[:7]
    scheduled_next_24 = _scheduled_expenses_next_24_months(household, as_of_month=current_month)
    return round(monthly_expense * reserve_months + scheduled_next_24 + max(0.0, additional_goal_cash), 2)


def _latest_trading_bar(snapshot: InvestmentMarketSnapshotData, *, as_of_date: str = ""):
    bars = [
        bar
        for bar in snapshot.bars
        if bar.is_trading
        and not bar.is_suspended
        and (not as_of_date or (bar.price_date or bar.date) <= as_of_date)
    ]
    return max(bars, key=lambda bar: bar.price_date or bar.date) if bars else None


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


def market_trading_day_age(
    snapshot: InvestmentMarketSnapshotData,
    *,
    start_date: str,
    end_date: str,
) -> int:
    """Count open market days after start_date through end_date."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        raise ValueError("行情日期格式无效") from None
    if end <= start:
        return 0
    trading_days = sorted(set(snapshot.trading_days))
    if trading_days and trading_days[0] <= start_date and trading_days[-1] >= end_date:
        return sum(start_date < trading_day <= end_date for trading_day in trading_days)
    return (end - start).days


def effective_nav_available_date(
    snapshot: InvestmentMarketSnapshotData,
    bar: InvestmentMarketBarData,
) -> str:
    """Return a conservative NAV availability date for old or incomplete snapshots."""
    if not bar.nav_date:
        return bar.nav_available_date
    available_date = bar.nav_available_date
    if not available_date or (snapshot.schema_version < 3 and available_date == bar.nav_date):
        try:
            return (date.fromisoformat(bar.nav_date) + timedelta(days=1)).isoformat()
        except ValueError:
            return available_date or bar.nav_date
    return available_date


def assess_quant_risk(
    policy: QuantInvestmentPolicyData,
    equity_snapshots: Iterable[InvestmentMarketSnapshotData],
) -> QuantRiskAssessment:
    snapshots = list(equity_snapshots)
    price_series: list[dict[str, float]] = []
    for snapshot in snapshots:
        prices = {
            bar.price_date or bar.date: research_market_price(bar)
            for bar in snapshot.bars
            if bar.is_trading and not bar.is_suspended and research_market_price(bar) > 0
        }
        if len(prices) < 2:
            latest_date = max(prices) if prices else date.today().isoformat()
            return QuantRiskAssessment(
                as_of_date=latest_date,
                drawdown=0.0,
                effective_equity_cap=0.0,
                state="blocked",
                reasons=["至少一个权益标的不足两个有效交易日，不能绕过风险篮子校验。"],
            )
        price_series.append(prices)
    common_dates = sorted(set.intersection(*(set(prices) for prices in price_series))) if price_series else []
    as_of_date = common_dates[-1] if common_dates else date.today().isoformat()
    if len(common_dates) < 2:
        return QuantRiskAssessment(
            as_of_date=as_of_date,
            drawdown=0.0,
            effective_equity_cap=0.0,
            state="blocked",
            reasons=["权益标的没有至少两个共同交易日，不能生成跨市场量化定投提案。"],
        )

    basket = [
        sum(prices[day] / prices[common_dates[0]] for prices in price_series) / len(price_series)
        for day in common_dates
    ]
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
    if snapshot.status != "complete" and snapshot.source != "manual":
        return False, "行情数据集不完整，暂停新增买入。"
    if instrument.purchase_suspended:
        return False, "该标的已标记为暂停申购或交易。"
    if instrument.market == "hong_kong_connect" and not instrument.hong_kong_connect_eligible:
        return False, "尚未确认该标的为港股通合资格证券。"
    latest = _latest_trading_bar(snapshot, as_of_date=as_of_date)
    if latest is None:
        return False, "没有可用的交易日价格。"
    if instrument.market == "qdii_fund":
        return False, "场外 QDII 仅支持人工申购确认，暂不生成模拟盘口订单。"
    if latest.purchase_limited:
        return False, "该交易日存在申购或交易额度限制。"
    if instrument.market == "qdii_etf":
        nav_available_date = effective_nav_available_date(snapshot, latest)
        if latest.nav is None or not latest.nav_date or not nav_available_date:
            return False, "跨境 QDII ETF 缺少净值，不能判断溢价风险。"
        try:
            available_date = date.fromisoformat(nav_available_date)
            if available_date > date.fromisoformat(as_of_date):
                return False, "跨境 QDII ETF 净值在决策日尚不可得，禁止使用未来净值。"
            nav_age = market_trading_day_age(snapshot, start_date=latest.nav_date, end_date=as_of_date)
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


def execution_session_is_allowed(
    snapshot: InvestmentMarketSnapshotData,
    *,
    execution_date: str,
    side: str,
) -> tuple[bool, str]:
    """Validate execution-day market state without requiring future coverage."""
    if execution_date in snapshot.suspension_dates:
        return False, "执行日已标记为停牌，不能模拟成交。"
    trading_days = sorted(set(snapshot.trading_days))
    calendar_covers_date = bool(
        trading_days and trading_days[0] <= execution_date <= trading_days[-1]
    )
    if (
        snapshot.calendar_source == "provider"
        and calendar_covers_date
        and execution_date not in trading_days
    ):
        return False, "执行日不是该市场开放日，不能模拟成交。"
    exact_bars = [
        bar for bar in snapshot.bars if (bar.price_date or bar.date) == execution_date
    ]
    if exact_bars:
        execution_bar = exact_bars[-1]
        if not execution_bar.is_trading or execution_bar.is_suspended:
            return False, "执行日标的停牌或不可交易，不能模拟成交。"
        if side == "buy" and execution_bar.purchase_limited:
            return False, "执行日存在申购或买入限制，不能模拟买入。"
        return True, "执行日行情确认可交易。"
    if calendar_covers_date:
        if execution_date not in trading_days:
            return False, "执行日不是该市场开放日，不能模拟成交。"
        return False, "执行日开放但缺少价格，按停牌处理并禁止模拟成交。"
    return True, "行情数据集尚未覆盖执行日，需由人工成交确认补充。"


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
            bar.date: research_market_price(bar)
            for bar in snapshot.bars
            if bar.is_trading and research_market_price(bar) > 0
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
    from .quant_backtest import BacktestAsset, run_calendar_backtest

    assets = [
        BacktestAsset(
            instrument_id=f"legacy-{index}",
            instrument=InvestmentInstrumentData(
                symbol=f"LEGACY{index}",
                name=f"兼容回测标的 {index + 1}",
                market="mainland_etf",
                asset_class="equity",
                lot_size=1,
            ),
            snapshot=snapshot,
        )
        for index, snapshot in enumerate(equity_snapshots)
    ]
    return run_calendar_backtest(policy, assets, monthly_contribution=monthly_contribution)


def quant_backtest_fingerprint(
    policy: QuantInvestmentPolicyData,
    snapshots: list[tuple[str, InvestmentMarketSnapshotData]],
    *,
    monthly_contribution: float,
    instruments: list[tuple[str, InvestmentInstrumentData]] | None = None,
    extra_parameters: dict[str, object] | None = None,
) -> str:
    payload = {
        "engine_version": QUANT_BACKTEST_ENGINE_VERSION,
        "recorder_schema_version": QUANT_RECORDER_SCHEMA_VERSION,
        "policy": policy.model_dump(mode="json"),
        "monthly_contribution": round(monthly_contribution, 6),
        "extra_parameters": extra_parameters or {},
        "instruments": [
            {"id": instrument_id, "data": instrument.model_dump(mode="json")}
            for instrument_id, instrument in sorted(instruments or [], key=lambda item: item[0])
        ],
        "snapshots": [
            {"id": snapshot_id, "data": snapshot.model_dump(mode="json")}
            for snapshot_id, snapshot in sorted(snapshots, key=lambda item: item[0])
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
