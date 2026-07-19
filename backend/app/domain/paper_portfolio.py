from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from ..schemas import (
    AccountSnapshotPoint,
    BrokerOrderDispatchData,
    BrokerReconciliationRunData,
    InvestmentInstrumentData,
    InvestmentMarketBarData,
    InvestmentMarketSnapshotData,
    MonthlyLedgerEntry,
    MonthlyVisualizationDetail,
    PaperFillData,
    PaperOrderData,
    PaperPortfolioSummary,
    PaperPositionData,
    PostTradeRiskIssueData,
    QuantInvestmentPolicyData,
    VisualizationBreakdownItem,
)
from .quant_investment import (
    _drawdown_from_prices,
    effective_nav_available_date,
    execution_market_price,
    market_trading_day_age,
)


@dataclass
class _PositionState:
    quantity: float = 0.0
    total_cost: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0


def _ordered_fills(fills: list[PaperFillData]) -> list[PaperFillData]:
    return sorted(fills, key=lambda item: (item.executed_date, item.order_id))


def _apply_fill_to_position(state: _PositionState, fill: PaperFillData) -> tuple[float, float]:
    state.total_fees += fill.fee
    if fill.side == "buy":
        state.quantity += fill.executed_quantity
        state.total_cost += fill.gross_amount + fill.fee
        return fill.executed_quantity, 0.0
    sold_quantity = min(state.quantity, fill.executed_quantity)
    average_cost = state.total_cost / state.quantity if state.quantity > 0 else 0.0
    removed_cost = average_cost * sold_quantity
    allocated_fee = fill.fee * sold_quantity / fill.executed_quantity if fill.executed_quantity > 0 else 0.0
    sale_proceeds = fill.executed_price * sold_quantity - allocated_fee
    state.realized_pnl += sale_proceeds - removed_cost
    state.quantity = max(0.0, state.quantity - sold_quantity)
    state.total_cost = max(0.0, state.total_cost - removed_cost)
    return sold_quantity, removed_cost


def _month_keys_between(start_month: str, end_month: str) -> list[str]:
    start_year, start_value = (int(item) for item in start_month.split("-", 1))
    end_year, end_value = (int(item) for item in end_month.split("-", 1))
    start_ordinal = start_year * 12 + start_value - 1
    end_ordinal = end_year * 12 + end_value - 1
    return [
        f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"
        for ordinal in range(start_ordinal, end_ordinal + 1)
    ]


def _latest_confirmed_bar(
    snapshot: InvestmentMarketSnapshotData,
    *,
    as_of_date: str,
) -> InvestmentMarketBarData | None:
    bars = [
        bar
        for bar in snapshot.bars
        if bar.is_trading
        and not bar.is_suspended
        and execution_market_price(bar) > 0
        and (bar.price_date or bar.date) <= as_of_date
    ]
    return max(bars, key=lambda bar: bar.price_date or bar.date) if bars else None


def _paper_nav_drawdowns(
    fills: list[PaperFillData],
    snapshots: dict[str, InvestmentMarketSnapshotData],
    *,
    as_of_date: str,
) -> tuple[float, float]:
    if not fills:
        return 0.0, 0.0
    ordered_fills = _ordered_fills(fills)
    first_fill_date = ordered_fills[0].executed_date
    fills_by_date: dict[str, list[PaperFillData]] = {}
    for fill in ordered_fills:
        fills_by_date.setdefault(fill.executed_date, []).append(fill)
    price_updates: dict[str, dict[str, float]] = {}
    for instrument_id, snapshot in snapshots.items():
        for bar in snapshot.bars:
            price_date = bar.price_date or bar.date
            if (
                price_date < first_fill_date
                or price_date > as_of_date
                or not bar.is_trading
                or bar.is_suspended
            ):
                continue
            price_updates.setdefault(price_date, {})[instrument_id] = execution_market_price(bar)

    timeline = sorted(set(fills_by_date) | set(price_updates))
    quantities: dict[str, float] = {}
    latest_prices: dict[str, float] = {}
    cash = 0.0
    units = 0.0
    nav_history: list[float] = []
    for current_date in timeline:
        updated_instruments = set(price_updates.get(current_date, {}))
        latest_prices.update(price_updates.get(current_date, {}))
        equity_before_contribution = cash + sum(
            quantity * latest_prices.get(instrument_id, 0.0)
            for instrument_id, quantity in quantities.items()
        )
        day_fills = fills_by_date.get(current_date, [])
        contribution = sum(fill.contribution_amount for fill in day_fills)
        nav_before_contribution = equity_before_contribution / units if units > 0 else 1.0
        if contribution > 0:
            units += contribution / max(nav_before_contribution, 1e-9)
        for fill in day_fills:
            cash += fill.contribution_amount + fill.cash_change
            current_quantity = quantities.get(fill.instrument_id, 0.0)
            if fill.side == "buy":
                quantities[fill.instrument_id] = current_quantity + fill.executed_quantity
            else:
                quantities[fill.instrument_id] = max(0.0, current_quantity - fill.executed_quantity)
            if fill.instrument_id not in updated_instruments:
                latest_prices[fill.instrument_id] = fill.executed_price
        total_equity = cash + sum(
            quantity * latest_prices.get(instrument_id, 0.0)
            for instrument_id, quantity in quantities.items()
        )
        if units > 0 and total_equity > 0:
            nav_history.append(total_equity / units)
    if not nav_history:
        return 0.0, 0.0
    peak = max(nav_history)
    current_drawdown = (peak - nav_history[-1]) / peak if peak > 0 else 0.0
    return current_drawdown, _drawdown_from_prices(nav_history)


def paper_fill_from_order(order_id: str, order: PaperOrderData) -> PaperFillData:
    if order.status != "simulated" or order.executed_price is None or order.executed_quantity is None:
        raise ValueError("只有已模拟成交且包含成交价格和数量的订单才能写入成交账本")
    gross_amount = order.executed_price * order.executed_quantity
    if order.side == "buy":
        cash_change = -(gross_amount + order.estimated_fee)
        if order.funding_source == "external_contribution":
            contribution_amount = order.cash_contribution_amount or order.order_amount
        else:
            contribution_amount = 0.0
    else:
        cash_change = gross_amount - order.estimated_fee
        contribution_amount = 0.0
    return PaperFillData(
        order_id=order_id,
        client_order_id=order.client_order_id,
        proposal_id=order.proposal_id,
        instrument_id=order.instrument_id,
        side=order.side,
        executed_date=order.executed_date,
        executed_price=order.executed_price,
        executed_quantity=order.executed_quantity,
        gross_amount=round(gross_amount, 2),
        fee=round(order.estimated_fee, 2),
        slippage_amount=round(abs(order.executed_price - order.estimated_price) * order.executed_quantity, 2),
        cash_change=round(cash_change, 2),
        contribution_amount=round(contribution_amount, 2),
    )


def _ledger_entry(
    *,
    month: int,
    account: str,
    category: str,
    label: str,
    amount: float,
    direction: str,
) -> MonthlyLedgerEntry:
    return MonthlyLedgerEntry(
        plan_variant="paper_quant",
        month=month,
        account=account,
        category=category,
        label=label,
        amount=round(amount, 2),
        direction=direction,
        source="paper_portfolio_ledger",
    )


def _paper_ledger_artifacts(
    fills: list[PaperFillData],
    *,
    market_snapshots: dict[str, InvestmentMarketSnapshotData],
    current_drawdown: float,
    max_drawdown: float,
    as_of_date: str,
) -> tuple[list[MonthlyLedgerEntry], list[AccountSnapshotPoint], list[MonthlyVisualizationDetail]]:
    if not fills:
        return [], [], []
    ordered_fills = _ordered_fills(fills)
    latest_price_date = max(
        (
            bar.price_date or bar.date
            for snapshot in market_snapshots.values()
            for bar in snapshot.bars
            if bar.is_trading and not bar.is_suspended and (bar.price_date or bar.date) <= as_of_date
        ),
        default=ordered_fills[-1].executed_date,
    )
    month_keys = _month_keys_between(
        ordered_fills[0].executed_date[:7],
        max(ordered_fills[-1].executed_date, latest_price_date)[:7],
    )
    month_index = {key: index + 1 for index, key in enumerate(month_keys)}
    entries: list[MonthlyLedgerEntry] = []
    running_cash = 0.0
    states: dict[str, _PositionState] = {}
    latest_execution_prices: dict[str, float] = {}
    prior_realized_pnl = 0.0
    prior_unrealized_pnl = 0.0
    snapshots: list[AccountSnapshotPoint] = []
    details: list[MonthlyVisualizationDetail] = []
    fills_by_month: dict[str, list[PaperFillData]] = {key: [] for key in month_keys}
    for fill in ordered_fills:
        fills_by_month[fill.executed_date[:7]].append(fill)

    for key in month_keys:
        month = month_index[key]
        month_entries: list[MonthlyLedgerEntry] = []
        for fill in fills_by_month[key]:
            running_cash += fill.contribution_amount + fill.cash_change
            latest_execution_prices[fill.instrument_id] = fill.executed_price
            if fill.contribution_amount:
                month_entries.append(_ledger_entry(month=month, account="paper_cash", category="paper_contribution", label="模拟账户资金投入", amount=fill.contribution_amount, direction="inflow"))
            if fill.side == "buy":
                month_entries.append(_ledger_entry(month=month, account="paper_cash", category="paper_buy", label="模拟买入现金划出", amount=-fill.gross_amount, direction="transfer"))
                month_entries.append(_ledger_entry(month=month, account="paper_investment", category="paper_buy", label="模拟投资持仓增加", amount=fill.gross_amount, direction="transfer"))
            else:
                month_entries.append(_ledger_entry(month=month, account="paper_investment", category="paper_sell", label="模拟投资持仓卖出", amount=-fill.gross_amount, direction="transfer"))
                month_entries.append(_ledger_entry(month=month, account="paper_cash", category="paper_sell", label="模拟卖出现金到账", amount=fill.gross_amount, direction="transfer"))
            if fill.fee:
                month_entries.append(_ledger_entry(month=month, account="paper_cash", category="paper_fee", label="模拟交易手续费", amount=-fill.fee, direction="outflow"))
            _apply_fill_to_position(states.setdefault(fill.instrument_id, _PositionState()), fill)

        year, month_of_year = (int(item) for item in key.split("-", 1))
        valuation_date = min(
            as_of_date,
            f"{key}-{monthrange(year, month_of_year)[1]:02d}",
        )
        snapshot_market_value = 0.0
        for instrument_id, state in states.items():
            if state.quantity <= 1e-9:
                continue
            latest_price = (
                state.total_cost / state.quantity
                if state.total_cost > 0
                else latest_execution_prices.get(instrument_id, 0.0)
            )
            market_snapshot = market_snapshots.get(instrument_id)
            if market_snapshot is not None:
                latest_bar = _latest_confirmed_bar(market_snapshot, as_of_date=valuation_date)
                if latest_bar is not None:
                    latest_price = execution_market_price(latest_bar)
            snapshot_market_value += state.quantity * latest_price
        snapshot_cash = max(0.0, running_cash)
        snapshot_total = snapshot_cash + snapshot_market_value
        realized_pnl = sum(state.realized_pnl for state in states.values())
        remaining_cost = sum(state.total_cost for state in states.values())
        unrealized_pnl = snapshot_market_value - remaining_cost
        realized_change = realized_pnl - prior_realized_pnl
        unrealized_change = unrealized_pnl - prior_unrealized_pnl
        if abs(unrealized_change) > 0.005:
            month_entries.append(_ledger_entry(month=month, account="paper_investment", category="paper_unrealized_pnl", label="模拟持仓未实现盈亏变动", amount=unrealized_change, direction="valuation"))
        if abs(realized_change) > 0.005:
            month_entries.append(_ledger_entry(month=month, account="paper_investment", category="paper_realized_pnl", label="模拟交易已实现盈亏", amount=realized_change, direction="valuation"))
        prior_realized_pnl = realized_pnl
        prior_unrealized_pnl = unrealized_pnl
        entries.extend(month_entries)
        snapshots.append(
            AccountSnapshotPoint(
                plan_variant="paper_quant",
                month=month,
                cash_balance=round(snapshot_cash, 2),
                investment_balance=round(snapshot_market_value, 2),
                liquid_asset_value=round(snapshot_total, 2),
                provident_balance=0.0,
                fixed_asset_value=0.0,
                total_asset_value=round(snapshot_total, 2),
                total_loan_balance=0.0,
                net_worth=round(snapshot_total, 2),
            )
        )
        cash_flow_items = [
            VisualizationBreakdownItem(
                name=item.label,
                value=abs(item.amount),
                amount=item.amount,
                kind=(
                    "result"
                    if item.direction == "valuation"
                    else "income"
                    if item.direction == "inflow"
                    else "expense"
                    if item.direction == "outflow"
                    else "asset"
                ),
            )
            for item in month_entries
        ]
        is_last = key == month_keys[-1]
        details.append(
            MonthlyVisualizationDetail(
                plan_variant="paper_quant",
                month=month,
                cash_flow_items=cash_flow_items,
                cash_flow_drivers=sorted(cash_flow_items, key=lambda item: item.value, reverse=True)[:5],
                advisor_text=(
                    f"模拟账户第 {month} 期净值 {snapshot_total:.2f} 元；"
                    + (
                        f"当前回撤 {current_drawdown:.1%}，历史最大回撤 {max_drawdown:.1%}；"
                        if is_last
                        else ""
                    )
                    + "该账户与家庭真实现金、投资账户相互隔离。"
                ),
                explanation_items=[
                    {"title": "模拟账本", "body": "提案生成订单意图，成交事件进入账本，再由账本派生账户快照和可视化；任何异常只冻结新增订单。"},
                    *(
                        [{"title": "组合回撤", "body": "回撤按资金流中性的模拟账户单位净值计算，追加资金不会掩盖既有亏损。"}]
                        if is_last
                        else []
                    ),
                ],
            )
        )
    return entries, snapshots, details


def build_paper_portfolio_summary(
    *,
    household_id: str,
    fills: list[PaperFillData],
    instruments: dict[str, InvestmentInstrumentData],
    snapshots: dict[str, InvestmentMarketSnapshotData],
    policy: QuantInvestmentPolicyData | None = None,
    reconciliations: list[tuple[str, BrokerReconciliationRunData]] | None = None,
    broker_dispatches: list[tuple[str, BrokerOrderDispatchData]] | None = None,
    as_of_date: str | None = None,
) -> PaperPortfolioSummary:
    valuation_date = as_of_date or date.today().isoformat()
    try:
        date.fromisoformat(valuation_date)
    except ValueError:
        raise ValueError("模拟组合估值日期必须是有效的 YYYY-MM-DD 日期") from None
    states: dict[str, _PositionState] = {}
    warnings: list[str] = []
    risk_issues: list[PostTradeRiskIssueData] = []
    frozen = False
    reconciliation_mismatch = False
    reconciliation_status = "not_required"
    latest_reconciliation_id = ""

    def add_issue(
        *,
        code: str,
        severity: str,
        source: str,
        message: str,
        order_id: str = "",
        instrument_id: str = "",
        observed_value: float | None = None,
        threshold: float | None = None,
    ) -> None:
        risk_issues.append(
            PostTradeRiskIssueData(
                code=code,
                severity=severity,
                source=source,
                message=message,
                order_id=order_id,
                instrument_id=instrument_id,
                observed_value=observed_value,
                threshold=threshold,
            )
        )
        warnings.append(message)

    reconciliation_records = reconciliations or []
    if reconciliation_records:
        latest_reconciliation_id, latest_reconciliation = reconciliation_records[0]
        pending_reconciliation = next(
            (
                (record_id, reconciliation)
                for record_id, reconciliation in reconciliation_records
                if reconciliation.freeze_new_orders and reconciliation.review_status == "pending"
            ),
            None,
        )
        if pending_reconciliation is not None:
            pending_id, pending_data = pending_reconciliation
            latest_reconciliation_id = pending_id
            frozen = True
            reconciliation_mismatch = True
            reconciliation_status = "mismatch"
            add_issue(
                code="reconciliation_mismatch",
                severity="freeze",
                source="reconciliation",
                message=(
                    f"对账运行 {pending_id} 存在未复核差异，已锁存冻结新增；"
                    + ("；".join(pending_data.differences) if pending_data.differences else "请人工核对订单、持仓和现金")
                ),
            )
        elif latest_reconciliation.matched:
            reconciliation_status = "matched"
        elif latest_reconciliation.review_status == "resolved":
            reconciliation_status = "reviewed"

    for dispatch_id, dispatch in broker_dispatches or []:
        if dispatch.status not in {"dispatching", "uncertain"}:
            continue
        frozen = True
        reconciliation_mismatch = True
        reconciliation_status = "mismatch"
        state_text = "发送中断" if dispatch.status == "dispatching" else "返回结果不确定"
        add_issue(
            code="broker_dispatch_uncertain",
            severity="freeze",
            source="reconciliation",
            order_id=dispatch.order_id,
            message=(
                f"券商动作 {dispatch_id}（{dispatch.action}）{state_text}，已冻结新增；"
                f"client_order_id={dispatch.client_order_id}，请先查询订单并完成对账"
            ),
        )

    contributions = 0.0
    cash_balance = 0.0
    ordered_fills = _ordered_fills(
        [fill for fill in fills if fill.executed_date <= valuation_date]
    )
    for fill in ordered_fills:
        if fill.reconciliation_status == "mismatch":
            reconciliation_mismatch = True
            frozen = True
            reconciliation_status = "mismatch"
            add_issue(
                code="reconciliation_mismatch",
                severity="freeze",
                source="fill",
                order_id=fill.order_id,
                instrument_id=fill.instrument_id,
                message=f"订单 {fill.client_order_id or fill.order_id} 存在对账差异，已冻结新增提案",
            )
        if policy and fill.gross_amount > 0 and fill.slippage_amount / fill.gross_amount > policy.post_trade_price_deviation_limit:
            frozen = True
            deviation = fill.slippage_amount / fill.gross_amount
            add_issue(
                code="execution_price_deviation",
                severity="freeze",
                source="fill",
                order_id=fill.order_id,
                instrument_id=fill.instrument_id,
                observed_value=deviation,
                threshold=policy.post_trade_price_deviation_limit,
                message=f"订单 {fill.client_order_id or fill.order_id} 的成交偏离超过阈值，已冻结新增提案",
            )
        state = states.setdefault(fill.instrument_id, _PositionState())
        contributions += fill.contribution_amount
        cash_balance += fill.cash_change + fill.contribution_amount
        available_quantity = state.quantity
        sold_quantity, _removed_cost = _apply_fill_to_position(state, fill)
        if fill.side == "sell" and sold_quantity < fill.executed_quantity:
            add_issue(
                code="position_oversell",
                severity="warning",
                source="fill",
                order_id=fill.order_id,
                instrument_id=fill.instrument_id,
                observed_value=fill.executed_quantity,
                threshold=available_quantity,
                message=f"{fill.instrument_id} 的卖出成交超过模拟持仓，已按可用持仓计算",
            )

    positions: list[PaperPositionData] = []
    for instrument_id, state in states.items():
        if state.quantity <= 1e-9:
            continue
        instrument = instruments.get(instrument_id)
        if instrument is None:
            warnings.append(f"成交账本中的标的 {instrument_id} 已不在当前标的池")
            continue
        average_cost = state.total_cost / state.quantity if state.quantity > 0 else 0.0
        latest_price = average_cost
        latest_price_date = ""
        snapshot = snapshots.get(instrument_id)
        if snapshot is not None:
            latest_bar = _latest_confirmed_bar(snapshot, as_of_date=valuation_date)
            if latest_bar is not None:
                latest_price = execution_market_price(latest_bar)
                latest_price_date = latest_bar.price_date or latest_bar.date
                if policy and instrument.market == "qdii_etf":
                    nav_available_date = effective_nav_available_date(snapshot, latest_bar)
                    if not nav_available_date or latest_bar.nav is None:
                        frozen = True
                        add_issue(
                            code="qdii_nav_missing",
                            severity="freeze",
                            source="market_data",
                            instrument_id=instrument_id,
                            message=f"{instrument.name} 的最新可得净值缺失，已冻结新增提案",
                        )
                    elif nav_available_date > valuation_date:
                        frozen = True
                        add_issue(
                            code="qdii_nav_not_available",
                            severity="freeze",
                            source="market_data",
                            instrument_id=instrument_id,
                            message=f"{instrument.name} 的最新净值尚未公告，已冻结新增提案",
                        )
                    elif latest_bar.nav_date:
                        try:
                            nav_age = market_trading_day_age(
                                snapshot,
                                start_date=latest_bar.nav_date,
                                end_date=latest_price_date,
                            )
                        except ValueError:
                            nav_age = policy.qdii_nav_max_stale_days + 1
                        if nav_age > policy.qdii_nav_max_stale_days:
                            frozen = True
                            add_issue(
                                code="qdii_nav_stale",
                                severity="freeze",
                                source="market_data",
                                instrument_id=instrument_id,
                                observed_value=float(nav_age),
                                threshold=float(policy.qdii_nav_max_stale_days),
                                message=f"{instrument.name} 的最新可得净值已过期，已冻结新增提案",
                            )
        if not latest_price_date:
            add_issue(
                code="market_price_missing",
                severity="warning",
                source="market_data",
                instrument_id=instrument_id,
                message=f"{instrument.name} 缺少最新行情，暂按持仓成本估值",
            )
        market_value = state.quantity * latest_price
        positions.append(
            PaperPositionData(
                instrument_id=instrument_id,
                symbol=instrument.symbol,
                name=instrument.name,
                market=instrument.market,
                asset_class=instrument.asset_class,
                currency=instrument.currency,
                quantity=round(state.quantity, 6),
                average_cost=round(average_cost, 6),
                total_cost=round(state.total_cost, 2),
                latest_price=round(latest_price, 6),
                latest_price_date=latest_price_date,
                market_value=round(market_value, 2),
                unrealized_pnl=round(market_value - state.total_cost, 2),
                realized_pnl=round(state.realized_pnl, 2),
                total_fees=round(state.total_fees, 2),
            )
        )
    positions.sort(key=lambda item: (-item.market_value, item.symbol))
    market_value = sum(item.market_value for item in positions)
    unrealized_pnl = sum(item.unrealized_pnl for item in positions)
    realized_pnl = sum(state.realized_pnl for state in states.values())
    total_fees = sum(state.total_fees for state in states.values())
    current_drawdown, max_drawdown = _paper_nav_drawdowns(
        ordered_fills,
        snapshots,
        as_of_date=valuation_date,
    )
    if policy and max_drawdown >= policy.drawdown_freeze_threshold:
        frozen = True
        add_issue(
            code="portfolio_drawdown_limit",
            severity="freeze",
            source="portfolio",
            observed_value=max_drawdown,
            threshold=policy.drawdown_freeze_threshold,
            message=f"模拟账户历史最大回撤 {max_drawdown:.1%} 达到冻结阈值，已暂停新增并等待人工复核",
        )
    ledger_entries, account_snapshots, visualization_details = _paper_ledger_artifacts(
        ordered_fills,
        market_snapshots=snapshots,
        current_drawdown=current_drawdown,
        max_drawdown=max_drawdown,
        as_of_date=valuation_date,
    )
    current_month_buy_amounts: dict[str, float] = {}
    for fill in ordered_fills:
        if fill.side != "buy" or fill.executed_date[:7] != valuation_date[:7]:
            continue
        current_month_buy_amounts[fill.instrument_id] = (
            current_month_buy_amounts.get(fill.instrument_id, 0.0)
            + fill.gross_amount
            + fill.fee
        )
    return PaperPortfolioSummary(
        household_id=household_id,
        ledger_version="paper-portfolio-v2",
        valuation_price_basis="raw_close",
        valuation_date=valuation_date,
        ledger_start_month=ordered_fills[0].executed_date[:7] if ordered_fills else "",
        net_contributions=round(contributions, 2),
        cash_balance=round(max(0.0, cash_balance), 2),
        market_value=round(market_value, 2),
        total_equity=round(max(0.0, cash_balance) + market_value, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        realized_pnl=round(realized_pnl, 2),
        total_fees=round(total_fees, 2),
        fill_count=len(ordered_fills),
        current_month_buy_amounts={
            instrument_id: round(amount, 2)
            for instrument_id, amount in current_month_buy_amounts.items()
        },
        current_drawdown=round(current_drawdown, 6),
        max_drawdown=round(max_drawdown, 6),
        frozen=frozen,
        reconciliation_status=(
            "mismatch"
            if reconciliation_mismatch
            else reconciliation_status
            if reconciliation_status != "not_required"
            else "matched"
            if fills
            else "not_required"
        ),
        latest_reconciliation_id=latest_reconciliation_id,
        post_trade_risk_issues=risk_issues,
        positions=positions,
        ledger_entries=ledger_entries,
        account_snapshots=account_snapshots,
        visualization_details=visualization_details,
        warnings=warnings,
    )
