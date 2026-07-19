from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from math import floor, sqrt
from statistics import pstdev

from ..schemas import (
    InvestmentInstrumentData,
    InvestmentMarketBarData,
    InvestmentMarketSnapshotData,
    QuantBenchmarkResult,
    QuantBacktestResult,
    QuantInvestmentPolicyData,
    QuantWalkForwardFold,
)
from .quant_investment import (
    _drawdown_from_prices,
    execution_session_is_allowed,
    instrument_is_buyable,
    optimized_equity_weights,
    research_market_price,
)


@dataclass(frozen=True)
class BacktestAsset:
    instrument_id: str
    instrument: InvestmentInstrumentData
    snapshot: InvestmentMarketSnapshotData


@dataclass
class _PortfolioState:
    cash: float = 0.0
    quantities: dict[str, float] = field(default_factory=dict)
    fees: float = 0.0
    traded_value: float = 0.0
    trade_count: int = 0
    monthly_buy_amounts: dict[tuple[str, str], float] = field(default_factory=dict)
    minimum_cash: float = float("inf")
    twr_index: float = 1.0
    twr_history: list[float] = field(default_factory=lambda: [1.0])
    daily_returns: list[float] = field(default_factory=list)
    equity_history: list[float] = field(default_factory=list)
    twr_by_date: dict[str, float] = field(default_factory=dict)


def _price(bar: InvestmentMarketBarData) -> float:
    return research_market_price(bar)


def _month_key(value: str) -> str:
    return value[:7]


def _portfolio_value(state: _PortfolioState, prices: dict[str, float]) -> float:
    return state.cash + sum(state.quantities.get(instrument_id, 0.0) * price for instrument_id, price in prices.items())


def _record_day(state: _PortfolioState, *, current_date: str, prior_value: float, contribution: float, end_value: float) -> None:
    if prior_value > 0:
        daily_return = (end_value - contribution) / prior_value - 1
        state.daily_returns.append(daily_return)
        state.twr_index *= 1 + daily_return
        state.twr_history.append(state.twr_index)
    state.equity_history.append(end_value)
    if end_value > 0:
        state.minimum_cash = min(state.minimum_cash, state.cash)
        state.twr_by_date[current_date] = state.twr_index


def _execute_contribution(
    state: _PortfolioState,
    *,
    assets: list[BacktestAsset],
    bars: dict[str, InvestmentMarketBarData],
    contribution: float,
    equity_ratio: float,
    policy: QuantInvestmentPolicyData,
    signal_date: str,
    equity_weights: dict[str, float] | None = None,
) -> None:
    state.cash += contribution
    eligible: list[BacktestAsset] = []
    for asset in assets:
        history = [
            bar
            for bar in asset.snapshot.bars
            if (bar.price_date or bar.date) <= signal_date
        ]
        historical_snapshot = asset.snapshot.model_copy(update={"bars": history})
        allowed, _reason = instrument_is_buyable(
            asset.instrument,
            historical_snapshot,
            policy,
            as_of_date=signal_date,
        )
        execution_bar = bars.get(asset.instrument_id)
        execution_allowed = (
            execution_bar is not None
            and execution_session_is_allowed(
                asset.snapshot,
                execution_date=execution_bar.price_date or execution_bar.date,
                side="buy",
            )[0]
        )
        if allowed and execution_bar is not None and execution_allowed:
            eligible.append(asset)
    if not eligible:
        return
    groups = {
        "equity": [asset for asset in eligible if asset.instrument.asset_class == "equity"],
        "defensive": [asset for asset in eligible if asset.instrument.asset_class == "defensive"],
    }
    class_budgets = {"equity": contribution * equity_ratio, "defensive": contribution * max(0.0, 1 - equity_ratio)}
    for asset_class, group in groups.items():
        if not group:
            continue
        relative_weights = (
            equity_weights
            if asset_class == "equity" and equity_weights
            else {asset.instrument_id: 1 / len(group) for asset in group}
        )
        for asset in group:
            _buy_with_budget(
                state,
                asset,
                bars[asset.instrument_id],
                class_budgets[asset_class] * relative_weights.get(asset.instrument_id, 0.0),
                policy,
            )


def _buy_with_budget(
    state: _PortfolioState,
    asset: BacktestAsset,
    bar: InvestmentMarketBarData,
    budget: float,
    policy: QuantInvestmentPolicyData,
) -> None:
    purchase_key = (_month_key(bar.price_date or bar.date), asset.instrument_id)
    effective_budget = min(max(0.0, budget), policy.max_order_amount, state.cash)
    if asset.instrument.monthly_purchase_limit is not None:
        remaining_limit = max(
            0.0,
            asset.instrument.monthly_purchase_limit
            - state.monthly_buy_amounts.get(purchase_key, 0.0),
        )
        effective_budget = min(effective_budget, remaining_limit)
    if effective_budget <= 0:
        return
    execution_price = _price(bar) * (1 + policy.slippage_rate)
    lot_size = max(1, asset.instrument.lot_size)
    fee_rate = max(0.0, asset.instrument.buy_fee_rate)
    quantity = floor((effective_budget / (execution_price * (1 + fee_rate))) / lot_size) * lot_size
    if quantity <= 0:
        return
    gross = quantity * execution_price
    fee = gross * fee_rate
    total = gross + fee
    if total > state.cash + 1e-8:
        return
    state.cash -= total
    state.quantities[asset.instrument_id] = state.quantities.get(asset.instrument_id, 0.0) + quantity
    state.fees += fee
    state.traded_value += gross
    state.trade_count += 1
    state.monthly_buy_amounts[purchase_key] = (
        state.monthly_buy_amounts.get(purchase_key, 0.0) + total
    )


def _rebalance_portfolio(
    state: _PortfolioState,
    *,
    assets: list[BacktestAsset],
    bars: dict[str, InvestmentMarketBarData],
    policy: QuantInvestmentPolicyData,
    equity_ratio: float,
    signal_date: str,
    equity_weights: dict[str, float] | None = None,
) -> None:
    prices = {instrument_id: _price(bar) for instrument_id, bar in bars.items()}
    total_value = _portfolio_value(state, prices)
    if total_value <= 0:
        return
    equity_value = sum(
        state.quantities.get(asset.instrument_id, 0.0) * prices[asset.instrument_id]
        for asset in assets
        if asset.instrument.asset_class == "equity"
    )
    if abs(equity_value / total_value - equity_ratio) < policy.rebalance_threshold:
        return
    class_groups = {
        "equity": [asset for asset in assets if asset.instrument.asset_class == "equity"],
        "defensive": [asset for asset in assets if asset.instrument.asset_class == "defensive"],
    }
    target_weights: dict[str, float] = {}
    for asset_class, group in class_groups.items():
        class_weight = equity_ratio if asset_class == "equity" else max(0.0, 1 - equity_ratio)
        if group:
            relative_weights = (
                equity_weights
                if asset_class == "equity" and equity_weights
                else {asset.instrument_id: 1 / len(group) for asset in group}
            )
            for asset in group:
                target_weights[asset.instrument_id] = class_weight * relative_weights.get(asset.instrument_id, 0.0)

    for asset in assets:
        quantity = state.quantities.get(asset.instrument_id, 0.0)
        execution_bar = bars[asset.instrument_id]
        sell_allowed, _reason = execution_session_is_allowed(
            asset.snapshot,
            execution_date=execution_bar.price_date or execution_bar.date,
            side="sell",
        )
        if quantity <= 0 or not sell_allowed:
            continue
        price = prices[asset.instrument_id]
        excess_value = quantity * price - target_weights.get(asset.instrument_id, 0.0) * total_value
        if excess_value <= 0:
            continue
        lot_size = max(1, asset.instrument.lot_size)
        sell_quantity = min(quantity, floor((excess_value / price) / lot_size) * lot_size)
        if sell_quantity <= 0:
            continue
        execution_price = price * (1 - policy.slippage_rate)
        gross = sell_quantity * execution_price
        fee = gross * asset.instrument.sell_fee_rate
        state.quantities[asset.instrument_id] = quantity - sell_quantity
        state.cash += gross - fee
        state.fees += fee
        state.traded_value += gross
        state.trade_count += 1

    for asset in assets:
        execution_bar = bars[asset.instrument_id]
        buy_allowed, _reason = execution_session_is_allowed(
            asset.snapshot,
            execution_date=execution_bar.price_date or execution_bar.date,
            side="buy",
        )
        if not buy_allowed:
            continue
        history = [bar for bar in asset.snapshot.bars if (bar.price_date or bar.date) <= signal_date]
        allowed, _reason = instrument_is_buyable(
            asset.instrument,
            asset.snapshot.model_copy(update={"bars": history}),
            policy,
            as_of_date=signal_date,
        )
        if not allowed:
            continue
        current_value = state.quantities.get(asset.instrument_id, 0.0) * prices[asset.instrument_id]
        deficit = target_weights.get(asset.instrument_id, 0.0) * total_value - current_value
        if deficit > 0:
            _buy_with_budget(state, asset, bars[asset.instrument_id], min(deficit, state.cash), policy)


def _cagr(twr_index: float, start_date: str, end_date: str) -> float:
    years = max(1 / 365.25, (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days / 365.25)
    return twr_index ** (1 / years) - 1 if twr_index > 0 else -1.0


def _volatility(returns: list[float]) -> float:
    return pstdev(returns) * sqrt(252) if len(returns) >= 2 else 0.0


def _turnover(state: _PortfolioState) -> float:
    positive_values = [value for value in state.equity_history if value > 0]
    average_value = sum(positive_values) / len(positive_values) if positive_values else 0.0
    return state.traded_value / average_value if average_value > 0 else 0.0


def _period_return(state: _PortfolioState, start_date: str, end_date: str) -> float:
    available = sorted(day for day in state.twr_by_date if start_date <= day <= end_date)
    if not available:
        return 0.0
    start_value = state.twr_by_date[available[0]]
    end_value = state.twr_by_date[available[-1]]
    return end_value / start_value - 1 if start_value > 0 else 0.0


def _period_drawdown(state: _PortfolioState, start_date: str, end_date: str) -> float:
    values = [state.twr_by_date[day] for day in sorted(state.twr_by_date) if start_date <= day <= end_date]
    return _drawdown_from_prices(values)


def _walk_forward_folds(
    *,
    month_keys: list[str],
    common_dates: list[str],
    strategy: _PortfolioState,
    static: _PortfolioState,
    train_months: int,
    test_months: int,
    research_strategy: str,
) -> list[QuantWalkForwardFold]:
    folds: list[QuantWalkForwardFold] = []
    cursor = train_months
    while cursor + test_months <= len(month_keys):
        train_slice = month_keys[cursor - train_months:cursor]
        test_slice = month_keys[cursor:cursor + test_months]
        train_start = next(day for day in common_dates if _month_key(day) == train_slice[0])
        train_end = next(day for day in reversed(common_dates) if _month_key(day) == train_slice[-1])
        test_start = next(day for day in common_dates if _month_key(day) == test_slice[0])
        test_end = next(day for day in reversed(common_dates) if _month_key(day) == test_slice[-1])
        folds.append(
            QuantWalkForwardFold(
                fold_index=len(folds) + 1,
                train_start_date=train_start,
                train_end_date=train_end,
                test_start_date=test_start,
                test_end_date=test_end,
                strategy_return=round(_period_return(strategy, test_start, test_end), 6),
                static_return=round(_period_return(static, test_start, test_end), 6),
                strategy_max_drawdown=round(_period_drawdown(strategy, test_start, test_end), 6),
                static_max_drawdown=round(_period_drawdown(static, test_start, test_end), 6),
                warnings=[
                    (
                        "最小方差权重在每个信号日仅使用此前训练窗口重估；测试窗口只评价当时可得数据。"
                        if research_strategy == "min_variance"
                        else "默认策略不拟合参数；训练窗口用于固定研究切分，测试窗口只评价当时可得数据。"
                    )
                ],
            )
        )
        cursor += test_months
    return folds


def _shift_months(value: str, months: int) -> str:
    parsed = date.fromisoformat(value)
    ordinal = parsed.year * 12 + parsed.month - 1 + months
    year, month_index = divmod(ordinal, 12)
    month = month_index + 1
    day = min(parsed.day, monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def _research_equity_weights(
    assets: list[BacktestAsset],
    *,
    policy: QuantInvestmentPolicyData,
    signal_date: str,
    train_months: int,
) -> dict[str, float] | None:
    equity_assets = [asset for asset in assets if asset.instrument.asset_class == "equity"]
    if not equity_assets or policy.research_strategy == "disabled":
        return None
    train_start = _shift_months(signal_date, -train_months)
    sliced = []
    for asset in equity_assets:
        snapshot = asset.snapshot.model_copy(
            update={
                "bars": [
                    bar
                    for bar in asset.snapshot.bars
                    if train_start <= (bar.price_date or bar.date) <= signal_date
                ]
            }
        )
        sliced.append((asset.instrument_id, snapshot))
    if policy.research_strategy == "min_variance":
        return optimized_equity_weights(sliced)
    return None


def run_calendar_backtest(
    policy: QuantInvestmentPolicyData,
    assets: list[BacktestAsset],
    *,
    monthly_contribution: float,
    walk_forward_train_months: int = 24,
    walk_forward_test_months: int = 12,
) -> QuantBacktestResult:
    if not assets:
        raise ValueError("至少需要一只权益 ETF 才能回测。")
    bars_by_asset: dict[str, dict[str, InvestmentMarketBarData]] = {}
    calendar_by_asset: dict[str, set[str]] = {}
    for asset in assets:
        bars_by_asset[asset.instrument_id] = {
            bar.price_date or bar.date: bar
            for bar in asset.snapshot.bars
            if bar.is_trading and not bar.is_suspended and _price(bar) > 0
        }
        calendar_by_asset[asset.instrument_id] = set(asset.snapshot.trading_days or bars_by_asset[asset.instrument_id])
    if any(not values for values in bars_by_asset.values()):
        raise ValueError("标的池中存在没有可交易日线的资产，不能建立共同回测时钟。")
    if any(not values for values in calendar_by_asset.values()):
        raise ValueError("标的池中存在没有交易日历的资产，不能建立共同回测时钟。")
    common_calendar = set.intersection(*calendar_by_asset.values())
    first_observation = max(min(values) for values in bars_by_asset.values())
    last_observation = min(max(values) for values in bars_by_asset.values())
    common_dates = sorted(
        day for day in common_calendar
        if first_observation <= day <= last_observation
    )
    joint_tradable_dates = [
        day
        for day in common_dates
        if all(day in bars_by_asset[asset.instrument_id] for asset in assets)
    ]
    month_keys = sorted({_month_key(value) for value in joint_tradable_dates})
    if len(month_keys) < 37:
        raise ValueError("共同可用历史不足 36 个完整交易月，不能给出可比较的回测结果。")

    first_date_by_month = {
        month: next(value for value in joint_tradable_dates if _month_key(value) == month)
        for month in month_keys
    }
    execution_dates = set(first_date_by_month[month] for month in month_keys[1:])
    strategy = _PortfolioState()
    static = _PortfolioState()
    equity_benchmark = _PortfolioState()
    basket_history: list[float] = []
    prior_prices: dict[str, float] | None = None
    prior_strategy_value = 0.0
    prior_static_value = 0.0
    prior_equity_benchmark_value = 0.0
    last_date = common_dates[0]
    contribution_months = 0
    last_bar_by_asset: dict[str, InvestmentMarketBarData] = {}
    equity_keys = [asset.instrument_id for asset in assets if asset.instrument.asset_class == "equity"]
    if not equity_keys:
        raise ValueError("回测至少需要一只权益资产作为风险信号。")

    for current_date in common_dates:
        bars: dict[str, InvestmentMarketBarData] = {}
        for asset in assets:
            observed_bar = bars_by_asset[asset.instrument_id].get(current_date)
            if observed_bar is not None:
                last_bar_by_asset[asset.instrument_id] = observed_bar
                bars[asset.instrument_id] = observed_bar
            elif asset.instrument_id in last_bar_by_asset:
                bars[asset.instrument_id] = last_bar_by_asset[asset.instrument_id].model_copy(
                    update={"date": current_date, "price_date": current_date, "is_trading": False, "is_suspended": True}
                )
        if len(bars) != len(assets):
            continue
        prices = {instrument_id: _price(bar) for instrument_id, bar in bars.items()}
        if prior_prices is None:
            basket_history.append(1.0)
        else:
            basket_return = sum(prices[key] / prior_prices[key] - 1 for key in equity_keys) / len(equity_keys)
            basket_history.append(basket_history[-1] * (1 + basket_return))

        contribution = 0.0
        if current_date in execution_dates:
            contribution = monthly_contribution
            contribution_months += 1
            signal_date = last_date
            equity_weights = _research_equity_weights(
                assets,
                policy=policy,
                signal_date=signal_date,
                train_months=walk_forward_train_months,
            )
            drawdown = _drawdown_from_prices(basket_history[:-1] or basket_history)
            if drawdown >= policy.drawdown_pause_threshold:
                strategy_equity_ratio = 0.0
            elif drawdown >= policy.drawdown_reduce_threshold:
                strategy_equity_ratio = min(policy.equity_cap, policy.drawdown_reduced_equity_cap)
            else:
                strategy_equity_ratio = policy.equity_cap
            _execute_contribution(
                strategy,
                assets=assets,
                bars=bars,
                contribution=contribution,
                equity_ratio=strategy_equity_ratio,
                policy=policy,
                signal_date=signal_date,
                equity_weights=equity_weights,
            )
            _execute_contribution(
                static,
                assets=assets,
                bars=bars,
                contribution=contribution,
                equity_ratio=policy.equity_cap,
                policy=policy,
                signal_date=signal_date,
                equity_weights=None,
            )
            _execute_contribution(
                equity_benchmark,
                assets=assets,
                bars=bars,
                contribution=contribution,
                equity_ratio=1.0,
                policy=policy,
                signal_date=signal_date,
                equity_weights=None,
            )
            if int(current_date[5:7]) in policy.rebalance_months:
                _rebalance_portfolio(strategy, assets=assets, bars=bars, policy=policy, equity_ratio=strategy_equity_ratio, signal_date=signal_date, equity_weights=equity_weights)
                _rebalance_portfolio(static, assets=assets, bars=bars, policy=policy, equity_ratio=policy.equity_cap, signal_date=signal_date)

        strategy_value = _portfolio_value(strategy, prices)
        static_value = _portfolio_value(static, prices)
        equity_benchmark_value = _portfolio_value(equity_benchmark, prices)
        _record_day(strategy, current_date=current_date, prior_value=prior_strategy_value, contribution=contribution, end_value=strategy_value)
        _record_day(static, current_date=current_date, prior_value=prior_static_value, contribution=contribution, end_value=static_value)
        _record_day(equity_benchmark, current_date=current_date, prior_value=prior_equity_benchmark_value, contribution=contribution, end_value=equity_benchmark_value)
        prior_strategy_value = strategy_value
        prior_static_value = static_value
        prior_equity_benchmark_value = equity_benchmark_value
        prior_prices = prices
        last_date = current_date

    start_date = first_date_by_month[month_keys[1]]
    end_date = common_dates[-1]
    strategy_drawdown = _drawdown_from_prices(strategy.twr_history)
    static_drawdown = _drawdown_from_prices(static.twr_history)
    equity_benchmark_drawdown = _drawdown_from_prices(equity_benchmark.twr_history)
    benchmarks = [
        QuantBenchmarkResult(
            benchmark_id="cash_contribution",
            name="纯现金定投",
            terminal_value=round(monthly_contribution * contribution_months, 2),
            cagr=0.0,
            annualized_volatility=0.0,
            max_drawdown=0.0,
            total_fees=0.0,
        ),
        QuantBenchmarkResult(
            benchmark_id="equity_dca",
            name="100% 权益固定定投",
            terminal_value=round(prior_equity_benchmark_value, 2),
            cagr=round(_cagr(equity_benchmark.twr_index, start_date, end_date), 6),
            annualized_volatility=round(_volatility(equity_benchmark.daily_returns), 6),
            max_drawdown=round(equity_benchmark_drawdown, 6),
            total_fees=round(equity_benchmark.fees, 2),
        ),
    ]
    walk_forward = _walk_forward_folds(
        month_keys=month_keys[1:],
        common_dates=common_dates,
        strategy=strategy,
        static=static,
        train_months=walk_forward_train_months,
        test_months=walk_forward_test_months,
        research_strategy=policy.research_strategy,
    )
    return QuantBacktestResult(
        policy_id="",
        start_date=start_date,
        end_date=end_date,
        months=contribution_months,
        strategy_terminal_value=round(prior_strategy_value, 2),
        static_terminal_value=round(prior_static_value, 2),
        strategy_max_drawdown=round(strategy_drawdown, 6),
        static_max_drawdown=round(static_drawdown, 6),
        strategy_cagr=round(_cagr(strategy.twr_index, start_date, end_date), 6),
        static_cagr=round(_cagr(static.twr_index, start_date, end_date), 6),
        strategy_annualized_volatility=round(_volatility(strategy.daily_returns), 6),
        static_annualized_volatility=round(_volatility(static.daily_returns), 6),
        strategy_turnover=round(_turnover(strategy), 6),
        static_turnover=round(_turnover(static), 6),
        strategy_total_fees=round(strategy.fees, 2),
        static_total_fees=round(static.fees, 2),
        strategy_min_cash_balance=round(max(0.0, strategy.minimum_cash if strategy.minimum_cash != float("inf") else 0.0), 2),
        static_min_cash_balance=round(max(0.0, static.minimum_cash if static.minimum_cash != float("inf") else 0.0), 2),
        trade_count=strategy.trade_count,
        benchmarks=benchmarks,
        walk_forward_folds=walk_forward,
        warnings=[
            "回测按行情数据集的沪深/港股共同开放日推进，月末信号只在下一可交易日成交。",
            "日历开放但缺少价格的日期按停牌估值并禁止成交；最小交易单位、费率、滑点、申购限制和 QDII 净值可得日期均进入撮合。",
            "回测基于用户手工标的池，不代表未来收益，也不会自动选择标的。",
        ],
    )
