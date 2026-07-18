from __future__ import annotations

from datetime import date, timedelta
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


def test_tushare_token_reads_private_user_file_and_prefers_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    from app.market_data import tushare_private_config_path, tushare_token

    config_path = tushare_private_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("TUSHARE_TOKEN=file-token\n", encoding="utf-8")
    assert tushare_token() == "file-token"

    monkeypatch.setenv("TUSHARE_TOKEN", "environment-token")
    assert tushare_token() == "environment-token"


def test_tushare_token_creates_private_template_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    from app.market_data import MarketDataConfigurationError, tushare_private_config_path, tushare_token

    config_path = tushare_private_config_path()
    with pytest.raises(MarketDataConfigurationError):
        tushare_token()
    assert config_path.read_text(encoding="utf-8").endswith("TUSHARE_TOKEN=\n")


def test_qdii_etf_refresh_uses_official_fund_daily_and_joins_latest_nav(monkeypatch) -> None:
    from app import market_data
    from app.schemas import InvestmentInstrumentData

    calls: list[tuple[str, dict]] = []

    def fake_query(api_name: str, params: dict, fields: str) -> list[dict]:
        calls.append((api_name, params))
        if api_name == "fund_daily":
            return [
                {"trade_date": "20260717", "close": 1.25},
                {"trade_date": "20260716", "close": 1.20},
            ]
        if api_name == "fund_nav":
            return [
                {"nav_date": "20260715", "unit_nav": 1.10, "adj_nav": 1.12},
                {"nav_date": "20260717", "unit_nav": 1.15, "adj_nav": 1.17},
            ]
        raise AssertionError(api_name)

    monkeypatch.setattr(market_data, "_tushare_query", fake_query)
    snapshot = market_data.fetch_tushare_snapshot(
        InvestmentInstrumentData(symbol="513500.SH", name="示例跨境ETF", market="qdii_etf", trading_mode="exchange", asset_class="equity"),
        start_date="2026-07-01",
    )

    assert [api_name for api_name, _params in calls[:2]] == ["fund_daily", "fund_nav"]
    assert calls[2][0] == "trade_cal"
    assert calls[1][1]["market"] == "E"
    assert [(bar.date, bar.nav, bar.nav_date, bar.nav_available_date) for bar in snapshot.bars] == [
        ("2026-07-16", 1.10, "2026-07-15", "2026-07-16"),
        ("2026-07-17", 1.10, "2026-07-15", "2026-07-16"),
    ]
    assert snapshot.calendar_source == "observed_prices"
    assert "交易日历接口不可用" in snapshot.warning


def test_tushare_exchange_calendar_filters_closed_days() -> None:
    from app.market_calendar import fetch_tushare_trading_calendar
    from app.schemas import InvestmentInstrumentData

    calls: list[tuple[str, dict]] = []

    def fake_query(api_name: str, params: dict, fields: str) -> list[dict]:
        calls.append((api_name, params))
        return [
            {"cal_date": "20260716", "is_open": 1},
            {"cal_date": "20260717", "is_open": 0},
            {"cal_date": "20260718", "is_open": 1},
        ]

    result = fetch_tushare_trading_calendar(
        InvestmentInstrumentData(symbol="159915.SZ", name="示例深市 ETF", market="mainland_etf", asset_class="equity"),
        start_date="2026-07-01",
        end_date="2026-07-31",
        query=fake_query,
    )
    assert calls == [("trade_cal", {"exchange": "SZSE", "start_date": "20260701", "end_date": "20260731"})]
    assert result.calendar_name == "szse"
    assert result.trading_days == ["2026-07-16", "2026-07-18"]


def test_snapshot_trace_does_not_mark_future_calendar_days_as_suspensions() -> None:
    from app.market_data import trace_market_snapshot
    from app.schemas import InvestmentMarketSnapshotData

    snapshot = trace_market_snapshot(
        InvestmentMarketSnapshotData(
            source="manual",
            snapshot_date="2026-07-17",
            calendar_source="provider",
            trading_days=["2026-07-17", "2026-07-20"],
            expected_bar_count=1,
            bars=[{"date": "2026-07-17", "close": 1}],
        )
    )

    assert snapshot.suspension_dates == []
    assert snapshot.trading_days == ["2026-07-17", "2026-07-20"]


def test_quant_investment_proposal_and_paper_order_are_safe_and_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household = client.get("/api/households").json()[0]
        household_id = household["id"]
        updated = household["data"] | {
            "cash_account_balance": 300_000,
            "monthly_income": 30_000,
            "monthly_expense": 10_000,
            "monthly_debt_payment": 0,
            "monthly_investment_amount": 8_000,
            "required_liquidity_months": 6,
        }
        assert client.put(f"/api/households/{household_id}", json={"data": updated}).status_code == 200
        policy = client.post("/api/quant-investment/policies", json={"household_id": household_id, "data": {}}).json()
        instrument = client.post(
            "/api/quant-investment/instruments",
            json={
                "household_id": household_id,
                "data": {
                    "symbol": "510300.SH",
                    "name": "示例宽基 ETF",
                    "market": "mainland_etf",
                    "trading_mode": "exchange",
                    "asset_class": "equity",
                },
            },
        ).json()
        snapshot = client.post(
            "/api/quant-investment/market-snapshots",
            json={
                "household_id": household_id,
                "instrument_id": instrument["id"],
                "data": {
                    "source": "manual",
                    "snapshot_date": "2026-07-17",
                    "status": "complete",
                    "bars": [
                        {"date": "2026-07-15", "close": 4.0, "adjusted_close": 4.0},
                        {"date": "2026-07-16", "close": 4.1, "adjusted_close": 4.1},
                    ],
                },
            },
        )
        assert snapshot.status_code == 200
        proposal = client.post(
            "/api/quant-investment/proposals",
            json={"household_id": household_id, "policy_id": policy["id"]},
        )
        assert proposal.status_code == 200
        assert proposal.json()["data"]["risk_state"] == "normal"
        assert proposal.json()["data"]["proposed_budget"] == pytest.approx(8_000)
        orders = client.get(f"/api/quant-investment/paper-orders?household_id={household_id}").json()
        assert len(orders) == 1
        first = client.post(
            f"/api/quant-investment/paper-orders/{orders[0]['id']}/simulate",
            json={"household_id": household_id, "executed_price": 4.2},
        )
        second = client.post(
            f"/api/quant-investment/paper-orders/{orders[0]['id']}/simulate",
            json={"household_id": household_id, "executed_price": 4.3},
        )
        fills = client.get(f"/api/quant-investment/paper-fills?household_id={household_id}").json()
        portfolio = client.get(f"/api/quant-investment/paper-portfolio?household_id={household_id}").json()
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["data"]["status"] == "simulated"
    assert first.json()["data"]["executed_date"] == orders[0]["data"]["expected_trade_date"]
    assert first.json()["data"]["executed_price"] == pytest.approx(4.2)
    assert len(fills) == 1
    assert fills[0]["order_id"] == orders[0]["id"]
    assert portfolio["fill_count"] == 1
    assert orders[0]["data"]["cash_contribution_amount"] == pytest.approx(8_000)
    assert portfolio["net_contributions"] == pytest.approx(orders[0]["data"]["cash_contribution_amount"])
    assert portfolio["cash_balance"] == pytest.approx(
        orders[0]["data"]["cash_contribution_amount"]
        - first.json()["data"]["executed_price"] * first.json()["data"]["executed_quantity"]
        - first.json()["data"]["estimated_fee"]
    )
    assert portfolio["ledger_entries"]
    assert portfolio["account_snapshots"]
    assert portfolio["visualization_details"]
    assert len(portfolio["positions"]) == 1
    assert portfolio["positions"][0]["quantity"] == pytest.approx(first.json()["data"]["executed_quantity"])


def test_quant_backtest_run_is_reproducible_and_deduplicated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    start = date(2022, 1, 3)
    bars = []
    for index in range(1_300):
        current = start + timedelta(days=index)
        if current.weekday() >= 5:
            continue
        close = 1 + index * 0.0005
        bars.append({"date": current.isoformat(), "close": close, "adjusted_close": close})
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        policy = client.post(
            "/api/quant-investment/policies",
            json={"household_id": household_id, "data": {}},
        ).json()
        instrument = client.post(
            "/api/quant-investment/instruments",
            json={
                "household_id": household_id,
                "data": {
                    "symbol": "510300.SH",
                    "name": "示例回测 ETF",
                    "market": "mainland_etf",
                    "trading_mode": "exchange",
                    "asset_class": "equity",
                },
            },
        ).json()
        snapshot_payload = {
            "household_id": household_id,
            "instrument_id": instrument["id"],
            "data": {
                "source": "manual",
                "snapshot_date": bars[-1]["date"],
                "status": "complete",
                "bars": bars,
            },
        }
        initial_snapshot = client.post("/api/quant-investment/market-snapshots", json=snapshot_payload)
        assert initial_snapshot.status_code == 200
        request = {
            "household_id": household_id,
            "policy_id": policy["id"],
            "monthly_contribution": 1_000,
        }
        first = client.post("/api/quant-investment/backtests", json=request)
        repeated_snapshot = client.post("/api/quant-investment/market-snapshots", json=snapshot_payload)
        assert repeated_snapshot.status_code == 200
        second = client.post("/api/quant-investment/backtests", json=request)
        runs = client.get(f"/api/quant-investment/backtest-runs?household_id={household_id}").json()

    assert first.status_code == 200
    assert second.status_code == 200
    assert repeated_snapshot.json()["id"] == initial_snapshot.json()["id"]
    assert first.json() == second.json()
    assert len(runs) == 1
    assert len(runs[0]["data_fingerprint"]) == 64
    assert runs[0]["data"]["snapshot_ids"]
    assert runs[0]["data"]["strategy_versions"]["signal_model"]
    assert runs[0]["data"]["universe_version"]
    assert runs[0]["data"]["dataset_versions"]
    assert runs[0]["data"]["start_date"] == first.json()["start_date"]
    assert runs[0]["data"]["cost_assumptions"]["slippage_rate"] == pytest.approx(0.001)
    assert runs[0]["data"]["result"] == first.json()


def test_qdii_stale_nav_blocks_new_buy() -> None:
    from app.domain.quant_investment import instrument_is_buyable
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    instrument = InvestmentInstrumentData(
        symbol="513000.SH",
        name="示例跨境 ETF",
        market="qdii_etf",
        asset_class="equity",
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-17",
        bars=[{"date": "2026-07-17", "close": 1.2, "nav": 1.1, "nav_date": "2026-07-10"}],
    )
    allowed, reason = instrument_is_buyable(
        instrument,
        snapshot,
        QuantInvestmentPolicyData(),
        as_of_date="2026-07-17",
    )
    assert not allowed
    assert "净值已过期" in reason


def test_qdii_nav_age_counts_open_trading_days_instead_of_weekend_days() -> None:
    from app.domain.quant_investment import instrument_is_buyable
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    instrument = InvestmentInstrumentData(
        symbol="513000.SH",
        name="示例跨境 ETF",
        market="qdii_etf",
        asset_class="equity",
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-20",
        trading_days=["2026-07-17", "2026-07-20"],
        bars=[{
            "date": "2026-07-20",
            "close": 1.1,
            "nav": 1.1,
            "nav_date": "2026-07-17",
            "nav_available_date": "2026-07-20",
        }],
    )

    allowed, reason = instrument_is_buyable(
        instrument,
        snapshot,
        QuantInvestmentPolicyData(qdii_nav_max_stale_days=1),
        as_of_date="2026-07-20",
    )

    assert allowed
    assert reason == "可交易。"


def test_quant_risk_basket_aligns_assets_by_common_market_dates() -> None:
    from app.domain.quant_investment import assess_quant_risk
    from app.schemas import InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    mainland = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-03",
        bars=[
            {"date": "2026-07-01", "close": 100},
            {"date": "2026-07-02", "close": 50},
            {"date": "2026-07-03", "close": 100},
        ],
    )
    hong_kong = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-04",
        bars=[
            {"date": "2026-07-01", "close": 100},
            {"date": "2026-07-03", "close": 100},
            {"date": "2026-07-04", "close": 50},
        ],
    )

    assessment = assess_quant_risk(QuantInvestmentPolicyData(), [mainland, hong_kong])

    assert assessment.as_of_date == "2026-07-03"
    assert assessment.drawdown == pytest.approx(0)
    assert assessment.state == "normal"


def test_quant_risk_blocks_when_any_equity_asset_has_insufficient_history() -> None:
    from app.domain.quant_investment import assess_quant_risk
    from app.schemas import InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    sufficient = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-02",
        bars=[{"date": "2026-07-01", "close": 1}, {"date": "2026-07-02", "close": 1}],
    )
    insufficient = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-02",
        bars=[{"date": "2026-07-02", "close": 1}],
    )

    assessment = assess_quant_risk(QuantInvestmentPolicyData(), [sufficient, insufficient])

    assert assessment.state == "blocked"
    assert assessment.effective_equity_cap == 0
    assert "不能绕过" in assessment.reasons[0]


def test_research_constructor_receives_only_data_available_on_common_signal_date(monkeypatch) -> None:
    from app.schemas import HouseholdData, InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData
    from app.strategies import quant_investment

    captured_dates: dict[str, list[str]] = {}

    def fake_optimizer(snapshots: list[tuple[str, InvestmentMarketSnapshotData]]) -> dict[str, float]:
        for instrument_id, snapshot in snapshots:
            captured_dates[instrument_id] = [bar.price_date for bar in snapshot.bars]
        return {instrument_id: 1 / len(snapshots) for instrument_id, _snapshot in snapshots}

    monkeypatch.setattr(quant_investment, "optimized_equity_weights", fake_optimizer)
    instrument_a = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例权益 ETF A",
        market="mainland_etf",
        asset_class="equity",
        lot_size=1,
    )
    instrument_b = instrument_a.model_copy(update={"symbol": "159915.SZ", "name": "示例权益 ETF B"})
    snapshot_a = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-03",
        trading_days=["2026-07-01", "2026-07-02", "2026-07-03"],
        bars=[
            {"date": "2026-07-01", "close": 1},
            {"date": "2026-07-02", "close": 1},
            {"date": "2026-07-03", "close": 10},
        ],
    )
    snapshot_b = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-02",
        trading_days=["2026-07-01", "2026-07-02", "2026-07-03"],
        bars=[
            {"date": "2026-07-01", "close": 1},
            {"date": "2026-07-02", "close": 1},
        ],
    )

    result = quant_investment.build_quant_monthly_proposal(
        household=HouseholdData(cash_account_balance=100000, monthly_expense=1000),
        policy_id="policy-1",
        policy=QuantInvestmentPolicyData(
            default_monthly_budget=1000,
            research_strategy="min_variance",
            max_single_instrument_ratio=1,
            max_single_market_ratio=1,
        ),
        instruments=[("equity-a", instrument_a), ("equity-b", instrument_b)],
        snapshots={
            "equity-a": ("snapshot-a", snapshot_a),
            "equity-b": ("snapshot-b", snapshot_b),
        },
    )

    assert result.proposal.as_of_date == "2026-07-02"
    assert captured_dates == {
        "equity-a": ["2026-07-01", "2026-07-02"],
        "equity-b": ["2026-07-01", "2026-07-02"],
    }
    assert result.orders
    assert all(order.estimated_price < 2 for order in result.orders)
    assert all(order.expected_trade_date == "2026-07-03" for order in result.orders)
    assert not any("下一工作日估计" in reason for reason in result.proposal.reasons)


def test_quant_backtest_requires_three_year_history_and_has_no_future_lookahead() -> None:
    from app.domain.quant_investment import run_monthly_backtest
    from app.schemas import InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    start = date(2022, 1, 3)
    bars = []
    for index in range(1_300):
        current = start + timedelta(days=index)
        if current.weekday() >= 5:
            continue
        close = 1 + index * 0.0005
        bars.append({"date": current.isoformat(), "close": close, "adjusted_close": close})
    snapshot = InvestmentMarketSnapshotData(source="manual", snapshot_date="2026-07-17", bars=bars)
    result = run_monthly_backtest(QuantInvestmentPolicyData(), [snapshot], monthly_contribution=1000)
    assert result.months >= 36
    assert result.strategy_terminal_value > 0
    assert result.static_terminal_value > 0
    assert result.trade_count > 0
    assert result.strategy_total_fees > 0
    assert result.strategy_annualized_volatility >= 0
    assert {item.benchmark_id for item in result.benchmarks} == {"cash_contribution", "equity_dca"}
    assert result.walk_forward_folds
    assert any("下一可交易日" in warning for warning in result.warnings)


def test_calendar_clock_waits_until_suspended_asset_has_a_tradable_bar() -> None:
    from app.domain.quant_backtest import BacktestAsset, run_calendar_backtest
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    trading_days: list[str] = []
    bars: list[dict] = []
    suspended_date = "2024-06-01"
    for index in range(38):
        year = 2022 + index // 12
        month = index % 12 + 1
        first = f"{year:04d}-{month:02d}-01"
        second = f"{year:04d}-{month:02d}-02"
        trading_days.extend([first, second])
        if first != suspended_date:
            bars.append({"date": first, "close": 1.0})
        bars.append({"date": second, "close": 1.0})
    future_calendar_date = "2025-03-03"
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date=trading_days[-1],
        calendar_source="provider",
        trading_days=[*trading_days, future_calendar_date],
        suspension_dates=[suspended_date],
        bars=bars,
    )
    result = run_calendar_backtest(
        QuantInvestmentPolicyData(),
        [BacktestAsset("equity", InvestmentInstrumentData(symbol="510300.SH", name="示例权益 ETF", market="mainland_etf", asset_class="equity", lot_size=1), snapshot)],
        monthly_contribution=1000,
    )
    assert result.months == 37
    assert result.trade_count == 37
    assert result.end_date == trading_days[-1]


def test_min_variance_research_uses_only_trailing_training_window(monkeypatch) -> None:
    from app.domain import quant_backtest
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    captured: list[list[tuple[str, InvestmentMarketSnapshotData]]] = []

    def fake_optimizer(snapshots: list[tuple[str, InvestmentMarketSnapshotData]]) -> dict[str, float]:
        captured.append(snapshots)
        return {instrument_id: 1 / len(snapshots) for instrument_id, _snapshot in snapshots}

    monkeypatch.setattr(quant_backtest, "optimized_equity_weights", fake_optimizer)
    bars = [
        {"date": "2024-07-30", "close": 0.9},
        {"date": "2024-07-31", "close": 1.0},
        {"date": "2025-07-31", "close": 1.1},
        {"date": "2026-07-31", "close": 1.2},
        {"date": "2026-08-01", "close": 1.3},
    ]
    snapshot = InvestmentMarketSnapshotData(source="manual", snapshot_date="2026-08-01", bars=bars)
    assets = [
        quant_backtest.BacktestAsset(
            "equity-1",
            InvestmentInstrumentData(
                symbol="510300.SH",
                name="示例权益 ETF",
                market="mainland_etf",
                asset_class="equity",
            ),
            snapshot,
        )
    ]

    weights = quant_backtest._research_equity_weights(
        assets,
        policy=QuantInvestmentPolicyData(research_strategy="min_variance"),
        signal_date="2026-07-31",
        train_months=24,
    )

    assert weights == {"equity-1": 1.0}
    assert len(captured) == 1
    captured_dates = [bar.price_date for bar in captured[0][0][1].bars]
    assert captured_dates == ["2024-07-31", "2025-07-31", "2026-07-31"]
    assert max(captured_dates) <= "2026-07-31"


def test_disabled_backtest_research_never_calls_optimizer(monkeypatch) -> None:
    from app.domain import quant_backtest
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    monkeypatch.setattr(
        quant_backtest,
        "optimized_equity_weights",
        lambda _snapshots: (_ for _ in ()).throw(AssertionError("研究优化器默认不应调用")),
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-31",
        bars=[{"date": "2026-07-31", "close": 1.0}],
    )
    assets = [
        quant_backtest.BacktestAsset(
            "equity-1",
            InvestmentInstrumentData(
                symbol="510300.SH",
                name="示例权益 ETF",
                market="mainland_etf",
                asset_class="equity",
            ),
            snapshot,
        )
    ]

    assert quant_backtest._research_equity_weights(
        assets,
        policy=QuantInvestmentPolicyData(),
        signal_date="2026-07-31",
        train_months=24,
    ) is None


def test_market_snapshots_keep_content_addressed_versions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        instrument = client.post(
            "/api/quant-investment/instruments",
            json={
                "household_id": household_id,
                "data": {
                    "symbol": "510300.SH",
                    "name": "示例版本化 ETF",
                    "market": "mainland_etf",
                    "asset_class": "equity",
                },
            },
        ).json()
        version_before_snapshot = client.get("/api/households").json()[0]["data"]["quant_investment_data_version"]
        payload = {
            "household_id": household_id,
            "instrument_id": instrument["id"],
            "data": {
                "source": "manual",
                "snapshot_date": "2026-07-17",
                "status": "complete",
                "bars": [{"date": "2026-07-17", "close": 1.0}],
            },
        }
        first = client.post("/api/quant-investment/market-snapshots", json=payload).json()
        version_after_first = client.get("/api/households").json()[0]["data"]["quant_investment_data_version"]
        repeated = client.post(
            "/api/quant-investment/market-snapshots",
            json={
                "household_id": household_id,
                "instrument_id": instrument["id"],
                "data": first["data"],
            },
        ).json()
        version_after_repeat = client.get("/api/households").json()[0]["data"]["quant_investment_data_version"]
        changed_payload = json.loads(json.dumps(payload))
        changed_payload["data"]["bars"][0]["close"] = 1.1
        second = client.post("/api/quant-investment/market-snapshots", json=changed_payload).json()
        version_after_change = client.get("/api/households").json()[0]["data"]["quant_investment_data_version"]

    with database.get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM investment_market_snapshots WHERE instrument_id = ?",
            (instrument["id"],),
        ).fetchone()[0]
    assert count == 2
    assert repeated["id"] == first["id"]
    assert repeated["data"]["fetched_at"] == first["data"]["fetched_at"]
    assert repeated["updated_at"] == first["updated_at"]
    assert version_after_repeat == version_after_first
    assert version_after_first == version_before_snapshot + 1
    assert version_after_change == version_after_first + 1
    assert first["data"]["dataset_hash"] != second["data"]["dataset_hash"]
    assert second["data"]["actual_bar_count"] == 1
    assert second["data"]["data_version"].startswith("manual:")


def test_market_snapshot_table_migrates_existing_rows_without_rebuild_loss(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "planner.db"
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(db_path))
    legacy_data = {
        "source": "manual",
        "snapshot_date": "2026-07-17",
        "status": "complete",
        "bars": [{"date": "2026-07-17", "close": 1.0}],
    }
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE investment_market_snapshots (
                id TEXT PRIMARY KEY,
                instrument_id TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                source TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(instrument_id, snapshot_date, source)
            );
            """
        )
        conn.execute(
            "INSERT INTO investment_market_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy-snapshot", "instrument-1", "2026-07-17", "manual", json.dumps(legacy_data), "2026-07-17", "2026-07-17"),
        )
    from app import database

    database.DB_PATH = database.default_db_path()
    database.initialize_database()
    reused, inserted = database.upsert_investment_market_snapshot(
        instrument_id="instrument-1",
        snapshot_date="2026-07-17",
        source="manual",
        data={**legacy_data, "dataset_hash": "legacy-snapshot"},
    )
    with database.get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(investment_market_snapshots)").fetchall()}
        row = conn.execute("SELECT id, dataset_hash FROM investment_market_snapshots WHERE id = 'legacy-snapshot'").fetchone()
    assert "dataset_hash" in columns
    assert row is not None
    assert row["dataset_hash"] == "legacy-snapshot"
    assert inserted is False
    assert reused["id"] == "legacy-snapshot"


def test_default_strategy_interfaces_disable_research_optimizer_and_plan_round_lots(monkeypatch) -> None:
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData
    from app.strategies import quant_investment

    instrument = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例整手 ETF",
        market="mainland_etf",
        asset_class="equity",
        lot_size=100,
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-17",
        bars=[{"date": "2026-07-17", "close": 1.0}],
    )
    candidate = quant_investment.QuantInstrumentCandidate("instrument-1", instrument, "snapshot-1", snapshot, 1.0, "2026-07-17")
    monkeypatch.setattr(quant_investment, "optimized_equity_weights", lambda _snapshots: (_ for _ in ()).throw(AssertionError("研究优化器默认不应调用")))
    policy = QuantInvestmentPolicyData()
    defensive_instrument = instrument.model_copy(update={"symbol": "511010.SH", "name": "示例防御 ETF", "asset_class": "defensive"})
    defensive_candidate = quant_investment.QuantInstrumentCandidate("instrument-2", defensive_instrument, "snapshot-2", snapshot, 1.0, "2026-07-17")
    weights = quant_investment.Fixed3565PortfolioConstructor().target_weights([candidate, defensive_candidate], policy, policy.equity_cap)
    order = quant_investment.PaperLotExecutionPlanner().plan(candidate, 1000, policy, "测试整手执行")
    assert weights == pytest.approx({"instrument-1": 0.35, "instrument-2": 0.65})
    assert order is not None
    assert order.estimated_price == pytest.approx(1.001)
    assert order.estimated_quantity % 100 == 0
    assert order.client_order_id


def test_external_order_batch_contributes_budget_once_and_keeps_round_lot_cash() -> None:
    from app.schemas import HouseholdData, InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData
    from app.strategies.quant_investment import build_quant_monthly_proposal

    equity = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例权益 ETF",
        market="mainland_etf",
        asset_class="equity",
        lot_size=100,
    )
    defensive = equity.model_copy(
        update={"symbol": "511010.SH", "name": "示例防御 ETF", "asset_class": "defensive"}
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-31",
        bars=[{"date": "2026-06-30", "close": 1}, {"date": "2026-07-31", "close": 1}],
    )

    result = build_quant_monthly_proposal(
        household=HouseholdData(cash_account_balance=100000, monthly_expense=1000),
        policy_id="policy-1",
        policy=QuantInvestmentPolicyData(
            default_monthly_budget=1000,
            max_single_instrument_ratio=1,
            max_single_market_ratio=1,
        ),
        instruments=[("equity", equity), ("defensive", defensive)],
        snapshots={
            "equity": ("snapshot-equity", snapshot),
            "defensive": ("snapshot-defensive", snapshot),
        },
    )

    assert len(result.orders) == 2
    assert sum(order.cash_contribution_amount for order in result.orders) == pytest.approx(1000)
    assert all(order.cash_contribution_amount >= order.order_amount for order in result.orders)
    assert sum(order.order_amount for order in result.orders) < 1000
    assert result.proposal.proposed_budget == pytest.approx(1000)


def test_qdii_nav_not_yet_available_is_never_used() -> None:
    from app.domain.quant_investment import instrument_is_buyable
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData

    instrument = InvestmentInstrumentData(symbol="513500.SH", name="示例跨境 ETF", market="qdii_etf", asset_class="equity")
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-17",
        bars=[{
            "date": "2026-07-17",
            "close": 1.2,
            "nav": 1.1,
            "nav_date": "2026-07-17",
            "nav_available_date": "2026-07-18",
        }],
    )
    allowed, reason = instrument_is_buyable(instrument, snapshot, QuantInvestmentPolicyData(), as_of_date="2026-07-17")
    assert not allowed
    assert "未来净值" in reason


def test_post_trade_reconciliation_mismatch_freezes_only_new_orders() -> None:
    from app.domain.paper_portfolio import build_paper_portfolio_summary
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, PaperFillData, QuantInvestmentPolicyData

    instrument = InvestmentInstrumentData(symbol="510300.SH", name="示例对账 ETF", market="mainland_etf", asset_class="equity")
    fill = PaperFillData(
        order_id="order-1",
        client_order_id="client-order-1",
        proposal_id="proposal-1",
        instrument_id="instrument-1",
        side="buy",
        executed_date="2026-07-17",
        executed_price=1.0,
        executed_quantity=100,
        gross_amount=100,
        fee=0.15,
        cash_change=-100.15,
        contribution_amount=110,
        reconciliation_status="mismatch",
    )
    summary = build_paper_portfolio_summary(
        household_id="household-1",
        fills=[fill],
        instruments={"instrument-1": instrument},
        snapshots={"instrument-1": InvestmentMarketSnapshotData(source="manual", snapshot_date="2026-07-17", bars=[{"date": "2026-07-17", "close": 1.0}])},
        policy=QuantInvestmentPolicyData(),
    )
    assert summary.frozen
    assert summary.reconciliation_status == "mismatch"
    assert {issue.code for issue in summary.post_trade_risk_issues} == {"reconciliation_mismatch"}
    assert summary.positions
    assert summary.ledger_entries
    assert summary.account_snapshots[-1].net_worth == pytest.approx(summary.total_equity)


def test_paper_portfolio_drawdown_is_cashflow_neutral_and_freezes_new_orders() -> None:
    from app.domain.paper_portfolio import build_paper_portfolio_summary
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, PaperFillData, QuantInvestmentPolicyData

    instrument = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例权益 ETF",
        market="mainland_etf",
        asset_class="equity",
    )
    fills = [
        PaperFillData(
            order_id="order-1",
            client_order_id="client-order-1",
            proposal_id="proposal-1",
            instrument_id="instrument-1",
            side="buy",
            executed_date="2026-07-01",
            executed_price=10,
            executed_quantity=100,
            gross_amount=1000,
            fee=0,
            cash_change=-1000,
            contribution_amount=1000,
        ),
        PaperFillData(
            order_id="order-2",
            client_order_id="client-order-2",
            proposal_id="proposal-2",
            instrument_id="instrument-1",
            side="buy",
            executed_date="2026-07-03",
            executed_price=8,
            executed_quantity=125,
            gross_amount=1000,
            fee=0,
            cash_change=-1000,
            contribution_amount=1000,
        ),
    ]
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-03",
        bars=[
            {"date": "2026-07-01", "close": 10},
            {"date": "2026-07-02", "close": 8},
            {"date": "2026-07-03", "close": 8},
        ],
    )

    summary = build_paper_portfolio_summary(
        household_id="household-1",
        fills=fills,
        instruments={"instrument-1": instrument},
        snapshots={"instrument-1": snapshot},
        policy=QuantInvestmentPolicyData(),
    )

    assert summary.net_contributions == pytest.approx(2000)
    assert summary.total_equity == pytest.approx(1800)
    assert summary.current_drawdown == pytest.approx(0.2)
    assert summary.max_drawdown == pytest.approx(0.2)
    assert summary.frozen
    assert any("历史最大回撤" in warning for warning in summary.warnings)


def test_paper_portfolio_replays_out_of_order_fills_into_month_end_snapshots() -> None:
    from app.domain.paper_portfolio import build_paper_portfolio_summary
    from app.schemas import InvestmentInstrumentData, InvestmentMarketSnapshotData, PaperFillData

    instrument = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例账本 ETF",
        market="mainland_etf",
        asset_class="equity",
    )
    buy = PaperFillData(
        order_id="order-buy",
        client_order_id="client-order-buy",
        proposal_id="proposal-buy",
        instrument_id="instrument-1",
        side="buy",
        executed_date="2026-01-10",
        executed_price=10,
        executed_quantity=100,
        gross_amount=1000,
        fee=10,
        cash_change=-1010,
        contribution_amount=1100,
    )
    sell = PaperFillData(
        order_id="order-sell",
        client_order_id="client-order-sell",
        proposal_id="proposal-sell",
        instrument_id="instrument-1",
        side="sell",
        executed_date="2026-02-20",
        executed_price=12,
        executed_quantity=50,
        gross_amount=600,
        fee=6,
        cash_change=594,
        contribution_amount=0,
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-02-20",
        bars=[
            {"date": "2026-01-31", "close": 11},
            {"date": "2026-02-20", "close": 12},
        ],
    )

    summary = build_paper_portfolio_summary(
        household_id="household-1",
        fills=[sell, buy],
        instruments={"instrument-1": instrument},
        snapshots={"instrument-1": snapshot},
    )

    assert len(summary.positions) == 1
    assert summary.positions[0].quantity == pytest.approx(50)
    assert summary.positions[0].average_cost == pytest.approx(10.1)
    assert summary.positions[0].total_cost == pytest.approx(505)
    assert summary.realized_pnl == pytest.approx(89)
    assert summary.unrealized_pnl == pytest.approx(95)
    assert summary.cash_balance == pytest.approx(684)
    assert summary.total_equity == pytest.approx(1284)
    assert not any(issue.code == "position_oversell" for issue in summary.post_trade_risk_issues)
    assert [point.cash_balance for point in summary.account_snapshots] == pytest.approx([90, 684])
    assert [point.investment_balance for point in summary.account_snapshots] == pytest.approx([1100, 600])
    assert [point.net_worth for point in summary.account_snapshots] == pytest.approx([1190, 1284])
    unrealized_changes = [
        entry.amount
        for entry in summary.ledger_entries
        if entry.category == "paper_unrealized_pnl"
    ]
    realized_changes = [
        entry.amount
        for entry in summary.ledger_entries
        if entry.category == "paper_realized_pnl"
    ]
    assert unrealized_changes == pytest.approx([90, 5])
    assert realized_changes == pytest.approx([89])

    cost_valued = build_paper_portfolio_summary(
        household_id="household-1",
        fills=[buy],
        instruments={"instrument-1": instrument},
        snapshots={},
    )
    assert cost_valued.positions[0].market_value == pytest.approx(1010)
    assert cost_valued.account_snapshots[-1].investment_balance == pytest.approx(1010)
    assert cost_valued.account_snapshots[-1].net_worth == pytest.approx(cost_valued.total_equity)


def test_qmt_boundary_requires_local_persistence_and_remains_disabled() -> None:
    from app.broker_adapters import LocalFirstBrokerGateway, PaperBrokerAdapter, QmtBrokerAdapter
    from app.schemas import PaperOrderData

    order = PaperOrderData(
        proposal_id="proposal-1",
        instrument_id="instrument-1",
        order_amount=1000,
        estimated_price=1,
        estimated_quantity=900,
        estimated_fee=1.35,
    )
    with pytest.raises(RuntimeError, match="先在本地账本落库"):
        LocalFirstBrokerGateway(PaperBrokerAdapter()).submit(local_order_id="", order=order)
    with pytest.raises(RuntimeError, match="持久化校验器"):
        LocalFirstBrokerGateway(PaperBrokerAdapter()).submit(local_order_id="local-order-1", order=order)
    with pytest.raises(RuntimeError, match="无法在持久化账本中匹配"):
        LocalFirstBrokerGateway(
            PaperBrokerAdapter(),
            is_order_persisted=lambda _local_order_id, _client_order_id: False,
        ).submit(local_order_id="local-order-1", order=order)
    with pytest.raises(RuntimeError, match="尚未启用"):
        QmtBrokerAdapter().query_cash()
    with pytest.raises(ValueError, match="不能小于订单成交预算"):
        PaperOrderData(
            proposal_id="proposal-1",
            instrument_id="instrument-1",
            order_amount=1000,
            estimated_price=1,
            estimated_quantity=900,
            estimated_fee=1.35,
            cash_contribution_amount=500,
        )
    with pytest.raises(ValueError, match="只有外部资金买入订单"):
        PaperOrderData(
            proposal_id="proposal-1",
            instrument_id="instrument-1",
            side="sell",
            funding_source="paper_cash",
            order_amount=1000,
            estimated_price=1,
            estimated_quantity=1000,
            estimated_fee=5,
            cash_contribution_amount=1000,
        )


def test_paper_broker_uses_planned_trade_date_and_rejects_backdating() -> None:
    from app.broker_adapters import PaperBrokerAdapter
    from app.schemas import PaperOrderData

    expected_date = date.today().isoformat()
    order = PaperOrderData(
        proposal_id="proposal-1",
        instrument_id="instrument-1",
        order_amount=1000,
        estimated_price=1,
        estimated_quantity=900,
        estimated_fee=1.35,
        expected_trade_date=expected_date,
    )

    simulated = PaperBrokerAdapter().simulate(order)

    assert simulated.executed_date == order.expected_trade_date
    with pytest.raises(ValueError, match="不能早于订单计划成交日"):
        PaperBrokerAdapter().simulate(
            order,
            executed_date=(date.today() - timedelta(days=1)).isoformat(),
        )
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        PaperBrokerAdapter().simulate(order, executed_date="2026/07/20")
    with pytest.raises(ValueError, match="不能晚于当前日期"):
        PaperBrokerAdapter().simulate(
            order,
            executed_date=(date.today() + timedelta(days=1)).isoformat(),
        )


def test_paper_order_api_rejects_duplicate_client_order_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        order_data = {
            "client_order_id": "duplicate-client-order-id",
            "proposal_id": "proposal-a",
            "instrument_id": "instrument-a",
            "order_amount": 1000,
            "estimated_price": 1,
            "estimated_quantity": 995,
            "estimated_fee": 5,
        }
        first = client.post(
            "/api/quant-investment/paper-orders",
            json={"household_id": household_id, "data": order_data},
        )
        repeated_same_order = client.post(
            "/api/quant-investment/paper-orders",
            json={"household_id": household_id, "data": order_data},
        )
        duplicate = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    **order_data,
                    "proposal_id": "proposal-b",
                    "instrument_id": "instrument-b",
                },
            },
        )
        orders = client.get(
            "/api/quant-investment/paper-orders",
            params={"household_id": household_id},
        ).json()

    assert first.status_code == 200
    assert repeated_same_order.status_code == 200
    assert repeated_same_order.json()["id"] == first.json()["id"]
    assert duplicate.status_code == 409
    assert "client_order_id" in duplicate.json()["detail"]
    assert len(orders) == 1
    with pytest.raises(database.InvalidClientOrderIdError):
        database.insert_paper_investment_order(
            household_id=household_id,
            proposal_id="proposal-invalid",
            instrument_id="instrument-invalid",
            data={"client_order_id": "short"},
        )


def test_concurrent_paper_orders_cannot_share_client_order_id(tmp_path, monkeypatch) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database

    database.DB_PATH = database.default_db_path()
    database.initialize_database()
    barrier = Barrier(2)

    def insert_order(suffix: str) -> str:
        barrier.wait()
        try:
            database.insert_paper_investment_order(
                household_id="household-a",
                proposal_id=f"proposal-{suffix}",
                instrument_id=f"instrument-{suffix}",
                data={
                    "client_order_id": "concurrent-client-order-id",
                    "proposal_id": f"proposal-{suffix}",
                    "instrument_id": f"instrument-{suffix}",
                },
            )
        except database.DuplicateClientOrderIdError:
            return "duplicate"
        return "inserted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(insert_order, ("a", "b")))

    with database.get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM paper_investment_orders WHERE json_extract(data, '$.client_order_id') = ?",
            ("concurrent-client-order-id",),
        ).fetchone()[0]

    assert results == ["duplicate", "inserted"]
    assert count == 1


def test_database_repairs_duplicate_legacy_client_order_ids_before_indexing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database

    database.DB_PATH = database.default_db_path()
    database.initialize_database()
    timestamp = "2026-07-01T00:00:00+00:00"
    with database.get_connection() as conn:
        conn.execute("DROP INDEX idx_paper_investment_orders_client_order_id")
        for suffix in ("a", "b"):
            order_data = {
                "schema_version": 2,
                "client_order_id": "legacy-duplicate-client-id",
                "proposal_id": f"proposal-{suffix}",
                "instrument_id": f"instrument-{suffix}",
                "side": "buy",
                "funding_source": "external_contribution",
                "order_amount": 1000,
                "estimated_price": 1,
                "estimated_quantity": 995,
                "estimated_fee": 5,
                "cash_contribution_amount": 1000,
                "status": "simulated" if suffix == "b" else "proposed",
            }
            conn.execute(
                """
                INSERT INTO paper_investment_orders
                    (id, household_id, proposal_id, instrument_id, data, created_at, updated_at)
                VALUES (?, 'household-a', ?, ?, ?, ?, ?)
                """,
                (
                    f"order-{suffix}",
                    order_data["proposal_id"],
                    order_data["instrument_id"],
                    json.dumps(order_data, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        fill_data = {
            "schema_version": 1,
            "order_id": "order-b",
            "client_order_id": "legacy-duplicate-client-id",
            "proposal_id": "proposal-b",
            "instrument_id": "instrument-b",
            "side": "buy",
            "executed_date": "2026-07-01",
            "executed_price": 1,
            "executed_quantity": 995,
            "gross_amount": 995,
            "fee": 5,
            "cash_change": -1000,
            "contribution_amount": 1000,
        }
        conn.execute(
            """
            INSERT INTO paper_investment_fills
                (id, household_id, order_id, proposal_id, instrument_id, data, created_at)
            VALUES ('fill-b', 'household-a', 'order-b', 'proposal-b', 'instrument-b', ?, ?)
            """,
            (json.dumps(fill_data, ensure_ascii=False), timestamp),
        )
        event_data = {
            "schema_version": 1,
            "order_id": "order-b",
            "client_order_id": "legacy-duplicate-client-id",
            "event_type": "cancel_requested",
            "from_status": "proposed",
            "to_status": "cancel_requested",
            "reason": "legacy event",
        }
        conn.execute(
            """
            INSERT INTO paper_investment_order_events
                (id, household_id, order_id, event_type, data, created_at)
            VALUES ('event-b', 'household-a', 'order-b', 'cancel_requested', ?, ?)
            """,
            (json.dumps(event_data, ensure_ascii=False), timestamp),
        )

    database.initialize_database()
    with database.get_connection() as conn:
        first_state = {
            row["id"]: json.loads(row["data"])
            for row in conn.execute(
                "SELECT id, data FROM paper_investment_orders ORDER BY id"
            ).fetchall()
        }
        fill_client_order_id = json.loads(
            conn.execute("SELECT data FROM paper_investment_fills WHERE id = 'fill-b'").fetchone()["data"]
        )["client_order_id"]
        event_client_order_id = json.loads(
            conn.execute("SELECT data FROM paper_investment_order_events WHERE id = 'event-b'").fetchone()["data"]
        )["client_order_id"]
        index_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_paper_investment_orders_client_order_id'"
        ).fetchone()
    database.initialize_database()
    with database.get_connection() as conn:
        second_state = {
            row["id"]: json.loads(row["data"])
            for row in conn.execute(
                "SELECT id, data FROM paper_investment_orders ORDER BY id"
            ).fetchall()
        }

    assert first_state["order-a"]["client_order_id"] == "legacy-duplicate-client-id"
    assert first_state["order-b"]["client_order_id"] != "legacy-duplicate-client-id"
    assert fill_client_order_id == first_state["order-b"]["client_order_id"]
    assert event_client_order_id == first_state["order-b"]["client_order_id"]
    assert index_exists is not None
    assert second_state == first_state


def test_broker_reconciliation_compares_orders_positions_and_cash() -> None:
    from app.broker_adapters import LocalFirstBrokerGateway, PaperBrokerAdapter
    from app.schemas import PaperOrderData, PaperPositionData

    local_order = PaperOrderData(
        proposal_id="proposal-1",
        instrument_id="instrument-1",
        order_amount=1000,
        estimated_price=1,
        estimated_quantity=995,
        estimated_fee=5,
    )
    remote_order = local_order.model_copy(update={"status": "simulated", "executed_date": "2026-07-19", "executed_price": 1, "executed_quantity": 995})
    local_position = PaperPositionData(
        instrument_id="instrument-1",
        symbol="510300.SH",
        name="示例对账 ETF",
        market="mainland_etf",
        asset_class="equity",
        currency="CNY",
        quantity=100,
        average_cost=1,
        total_cost=100,
        latest_price=1,
        market_value=100,
        unrealized_pnl=0,
        total_fees=0,
    )
    remote_position = local_position.model_copy(update={"quantity": 99, "market_value": 99})
    adapter = PaperBrokerAdapter(
        orders=(remote_order,),
        positions=(remote_position,),
        cash_balance=10,
    )

    result = LocalFirstBrokerGateway(adapter).reconcile(
        local_orders=[local_order],
        local_positions=[local_position],
        local_cash=20,
    )

    assert not result.matched
    assert result.freeze_new_orders
    assert result.local_state_hash != result.remote_state_hash
    assert any("状态或成交字段" in difference for difference in result.differences)
    assert any("持仓" in difference for difference in result.differences)
    assert any("现金余额" in difference for difference in result.differences)

    noisy_remote_order = remote_order.model_copy(
        update={"executed_price": 1.00000001, "executed_quantity": 995.00000001}
    )
    noisy_remote_position = local_position.model_copy(
        update={"quantity": 100.00000001, "market_value": 100.00000001}
    )
    matched_result = LocalFirstBrokerGateway(
        PaperBrokerAdapter(
            orders=(noisy_remote_order,),
            positions=(noisy_remote_position,),
            cash_balance=20.004,
        )
    ).reconcile(
        local_orders=[remote_order],
        local_positions=[local_position],
        local_cash=20,
    )
    assert matched_result.matched
    assert not matched_result.freeze_new_orders
    assert matched_result.local_state_hash == matched_result.remote_state_hash


def test_paper_order_cancel_is_local_first_atomic_and_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        first_order = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "cancel-proposal-1",
                    "instrument_id": "cancel-instrument-1",
                    "order_amount": 1000,
                    "estimated_price": 1,
                    "estimated_quantity": 995,
                    "estimated_fee": 5,
                },
            },
        ).json()
        first_cancel = client.post(
            f"/api/quant-investment/paper-orders/{first_order['id']}/cancel",
            json={"household_id": household_id, "reason": "本月不再执行该模拟订单"},
        )
        second_cancel = client.post(
            f"/api/quant-investment/paper-orders/{first_order['id']}/cancel",
            json={"household_id": household_id, "reason": "重复取消不应新增事件"},
        )
        events = client.get(
            "/api/quant-investment/paper-order-events",
            params={"household_id": household_id, "order_id": first_order["id"]},
        ).json()
        simulate_cancelled = client.post(
            f"/api/quant-investment/paper-orders/{first_order['id']}/simulate",
            json={"household_id": household_id},
        )
        invalid_initial_status = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "cancel-proposal-invalid",
                    "instrument_id": "cancel-instrument-invalid",
                    "order_amount": 1000,
                    "estimated_price": 1,
                    "estimated_quantity": 995,
                    "estimated_fee": 5,
                    "status": "cancelled",
                },
            },
        )

        filled_order = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "cancel-proposal-2",
                    "instrument_id": "cancel-instrument-2",
                    "order_amount": 1000,
                    "estimated_price": 1,
                    "estimated_quantity": 995,
                    "estimated_fee": 5,
                },
            },
        ).json()
        simulated = client.post(
            f"/api/quant-investment/paper-orders/{filled_order['id']}/simulate",
            json={"household_id": household_id},
        )
        cancel_filled = client.post(
            f"/api/quant-investment/paper-orders/{filled_order['id']}/cancel",
            json={"household_id": household_id, "reason": "已成交订单不能取消"},
        )
        filled_events = client.get(
            "/api/quant-investment/paper-order-events",
            params={"household_id": household_id, "order_id": filled_order["id"]},
        ).json()

    blocked_order, blocked_fill = database.record_paper_fill_atomic(
        first_order["id"],
        household_id=household_id,
        order_data={**first_cancel.json()["data"], "status": "simulated"},
        fill_data={
            "order_id": first_order["id"],
            "client_order_id": first_order["data"]["client_order_id"],
            "proposal_id": "cancel-proposal-1",
            "instrument_id": "cancel-instrument-1",
            "side": "buy",
            "executed_date": "2026-07-19",
            "executed_price": 1,
            "executed_quantity": 995,
            "gross_amount": 995,
            "fee": 5,
            "cash_change": -1000,
            "contribution_amount": 1000,
        },
    )

    assert first_cancel.status_code == 200
    assert second_cancel.status_code == 200
    assert first_cancel.json()["data"]["status"] == "cancelled"
    assert second_cancel.json() == first_cancel.json()
    assert [event["data"]["event_type"] for event in events] == ["cancel_requested", "cancelled"]
    assert events[0]["data"]["from_status"] == "proposed"
    assert events[1]["data"]["from_status"] == "cancel_requested"
    assert simulate_cancelled.status_code == 409
    assert invalid_initial_status.status_code == 422
    assert simulated.status_code == 200
    assert cancel_filled.status_code == 409
    assert not filled_events
    assert blocked_order is not None
    assert blocked_order["data"]["status"] == "cancelled"
    assert blocked_fill is None


def test_persisted_reconciliation_mismatch_latches_freeze_until_manual_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        policy = client.post(
            "/api/quant-investment/policies",
            json={"household_id": household_id, "data": {}},
        ).json()
        mismatch = database.insert_broker_reconciliation_run(
            household_id=household_id,
            adapter="qmt",
            reconciliation_date="2026-07-19",
            data={
                "adapter": "qmt",
                "reconciliation_date": "2026-07-19",
                "matched": False,
                "freeze_new_orders": True,
                "review_status": "pending",
                "local_state_hash": "a" * 64,
                "remote_state_hash": "b" * 64,
                "local_order_count": 1,
                "remote_order_count": 0,
                "local_position_count": 1,
                "remote_position_count": 0,
                "local_cash": 100,
                "remote_cash": 0,
                "differences": ["示例订单、持仓和现金差异"],
            },
        )
        frozen_portfolio = client.get(
            "/api/quant-investment/paper-portfolio",
            params={"household_id": household_id},
        ).json()
        frozen_proposal = client.post(
            "/api/quant-investment/proposals",
            json={"household_id": household_id, "policy_id": policy["id"]},
        ).json()
        matched = client.post(
            "/api/quant-investment/broker-reconciliations/paper",
            json={"household_id": household_id},
        )
        still_frozen = client.get(
            "/api/quant-investment/paper-portfolio",
            params={"household_id": household_id},
        ).json()
        review = client.post(
            f"/api/quant-investment/broker-reconciliations/{mismatch['id']}/review",
            json={"household_id": household_id, "review_note": "已逐项核对本地订单、持仓和现金"},
        )
        released = client.get(
            "/api/quant-investment/paper-portfolio",
            params={"household_id": household_id},
        ).json()
        runs = client.get(
            "/api/quant-investment/broker-reconciliations",
            params={"household_id": household_id},
        ).json()
        repeated_review = client.post(
            f"/api/quant-investment/broker-reconciliations/{mismatch['id']}/review",
            json={"household_id": household_id, "review_note": "重复复核"},
        )

    assert frozen_portfolio["frozen"]
    assert frozen_portfolio["reconciliation_status"] == "mismatch"
    assert frozen_portfolio["post_trade_risk_issues"][0]["code"] == "reconciliation_mismatch"
    assert frozen_proposal["data"]["risk_state"] == "frozen"
    assert matched.status_code == 200
    assert matched.json()["data"]["matched"]
    assert still_frozen["frozen"]
    assert still_frozen["reconciliation_status"] == "mismatch"
    assert still_frozen["latest_reconciliation_id"] == mismatch["id"]
    assert review.status_code == 200
    assert review.json()["data"]["review_status"] == "resolved"
    assert review.json()["data"]["review_note"]
    assert not released["frozen"]
    assert released["reconciliation_status"] == "matched"
    assert not released["post_trade_risk_issues"]
    assert len(runs) == 2
    assert repeated_review.status_code == 409


def test_protected_cash_expands_real_scheduled_expenses_only_within_24_months() -> None:
    from app.domain.quant_investment import protected_cash_for_quant_investment
    from app.schemas import HouseholdData

    baseline = HouseholdData(monthly_expense=1000, scheduled_expenses=[])
    household_data = baseline.model_dump(mode="json")
    household_data["scheduled_expenses"] = [
        {"name": "近期月度支出", "monthly_amount": 100, "frequency": "monthly", "start_month": "2026-07", "end_month": "2026-08"},
        {"name": "近期一次性支出", "monthly_amount": 500, "frequency": "one_time", "start_month": "2026-09"},
        {"name": "远期支出", "monthly_amount": 9999, "frequency": "one_time", "start_month": "2029-01"},
    ]
    household = HouseholdData.model_validate(household_data)
    baseline_cash = protected_cash_for_quant_investment(baseline, as_of_month="2026-07")
    protected_cash = protected_cash_for_quant_investment(household, additional_goal_cash=1234, as_of_month="2026-07")
    assert protected_cash - baseline_cash == pytest.approx(1934)


def test_existing_position_caps_new_instrument_exposure_after_contribution() -> None:
    from app.schemas import (
        HouseholdData,
        InvestmentInstrumentData,
        InvestmentMarketSnapshotData,
        PaperPortfolioSummary,
        PaperPositionData,
        QuantInvestmentPolicyData,
    )
    from app.strategies.quant_investment import build_quant_monthly_proposal

    instrument = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例权益 ETF",
        market="mainland_etf",
        asset_class="equity",
        lot_size=1,
    )
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-31",
        bars=[{"date": "2026-06-30", "close": 1}, {"date": "2026-07-31", "close": 1}],
    )
    portfolio = PaperPortfolioSummary(
        household_id="household-1",
        net_contributions=10000,
        cash_balance=6210,
        market_value=3790,
        total_equity=10000,
        unrealized_pnl=0,
        realized_pnl=0,
        total_fees=0,
        fill_count=1,
        positions=[
            PaperPositionData(
                instrument_id="equity",
                symbol=instrument.symbol,
                name=instrument.name,
                market=instrument.market,
                asset_class="equity",
                currency="CNY",
                quantity=3790,
                average_cost=1,
                total_cost=3790,
                latest_price=1,
                latest_price_date="2026-07-31",
                market_value=3790,
                unrealized_pnl=0,
                total_fees=0,
            )
        ],
    )

    result = build_quant_monthly_proposal(
        household=HouseholdData(cash_account_balance=100000, monthly_expense=1000),
        policy_id="policy-1",
        policy=QuantInvestmentPolicyData(
            default_monthly_budget=1000,
            max_single_instrument_ratio=0.35,
            max_single_market_ratio=1,
        ),
        instruments=[("equity", instrument)],
        snapshots={"equity": ("snapshot-equity", snapshot)},
        paper_portfolio=portfolio,
    )

    assert len(result.orders) == 1
    order = result.orders[0]
    assert order.order_amount <= 60
    assert order.cash_contribution_amount == pytest.approx(1000)
    assert (3790 + order.order_amount) / 11000 <= 0.35


def test_existing_market_exposure_caps_all_new_orders_in_same_market() -> None:
    from app.schemas import (
        HouseholdData,
        InvestmentInstrumentData,
        InvestmentMarketSnapshotData,
        PaperPortfolioSummary,
        PaperPositionData,
        QuantInvestmentPolicyData,
    )
    from app.strategies.quant_investment import build_quant_monthly_proposal

    existing = InvestmentInstrumentData(
        symbol="510300.SH",
        name="示例已有 ETF",
        market="mainland_etf",
        asset_class="equity",
        lot_size=1,
    )
    candidate = existing.model_copy(update={"symbol": "159915.SZ", "name": "示例新增 ETF"})
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-07-31",
        bars=[{"date": "2026-06-30", "close": 1}, {"date": "2026-07-31", "close": 1}],
    )
    portfolio = PaperPortfolioSummary(
        household_id="household-1",
        net_contributions=10000,
        cash_balance=6210,
        market_value=3790,
        total_equity=10000,
        unrealized_pnl=0,
        realized_pnl=0,
        total_fees=0,
        fill_count=1,
        positions=[
            PaperPositionData(
                instrument_id="existing",
                symbol=existing.symbol,
                name=existing.name,
                market=existing.market,
                asset_class="equity",
                currency="CNY",
                quantity=3790,
                average_cost=1,
                total_cost=3790,
                latest_price=1,
                latest_price_date="2026-07-31",
                market_value=3790,
                unrealized_pnl=0,
                total_fees=0,
            )
        ],
    )

    result = build_quant_monthly_proposal(
        household=HouseholdData(cash_account_balance=100000, monthly_expense=1000),
        policy_id="policy-1",
        policy=QuantInvestmentPolicyData(
            default_monthly_budget=1000,
            max_single_instrument_ratio=1,
            max_single_market_ratio=0.35,
        ),
        instruments=[("candidate", candidate)],
        snapshots={"candidate": ("snapshot-candidate", snapshot)},
        paper_portfolio=portfolio,
    )

    assert len(result.orders) == 1
    assert result.orders[0].order_amount <= 60
    assert result.orders[0].cash_contribution_amount == pytest.approx(1000)
    assert (3790 + result.orders[0].order_amount) / 11000 <= 0.35


def test_paused_equity_signal_can_still_allocate_to_defensive_pool() -> None:
    from app.schemas import HouseholdData, InvestmentInstrumentData, InvestmentMarketSnapshotData, QuantInvestmentPolicyData
    from app.strategies.quant_investment import build_quant_monthly_proposal

    equity = InvestmentInstrumentData(symbol="510300.SH", name="示例权益 ETF", market="mainland_etf", asset_class="equity", lot_size=1)
    defensive = InvestmentInstrumentData(symbol="511010.SH", name="示例防御 ETF", market="mainland_etf", asset_class="defensive", lot_size=1)
    equity_snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-06-30",
        bars=[
            {"date": "2026-05-29", "close": 1.0},
            {"date": "2026-06-30", "close": 0.87},
        ],
    )
    defensive_snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-06-30",
        bars=[
            {"date": "2026-05-29", "close": 1.0},
            {"date": "2026-06-30", "close": 1.0},
        ],
    )
    policy = QuantInvestmentPolicyData(
        default_monthly_budget=1000,
        max_single_instrument_ratio=1,
        max_single_market_ratio=1,
    )
    result = build_quant_monthly_proposal(
        household=HouseholdData(cash_account_balance=100000, monthly_expense=1000),
        policy_id="policy-1",
        policy=policy,
        instruments=[("equity", equity), ("defensive", defensive)],
        snapshots={
            "equity": ("snapshot-equity", equity_snapshot),
            "defensive": ("snapshot-defensive", defensive_snapshot),
        },
    )
    assert result.proposal.risk_state == "paused"
    assert result.orders
    assert {order.instrument_id for order in result.orders} == {"defensive"}


def test_quarterly_rebalance_generates_paper_cash_sell_order() -> None:
    from app.schemas import (
        HouseholdData,
        InvestmentInstrumentData,
        InvestmentMarketSnapshotData,
        PaperPortfolioSummary,
        PaperPositionData,
        QuantInvestmentPolicyData,
    )
    from app.strategies.quant_investment import build_quant_monthly_proposal

    equity = InvestmentInstrumentData(symbol="510300.SH", name="示例权益 ETF", market="mainland_etf", asset_class="equity", lot_size=100)
    defensive = InvestmentInstrumentData(symbol="511010.SH", name="示例防御 ETF", market="mainland_etf", asset_class="defensive", lot_size=100)
    snapshot = InvestmentMarketSnapshotData(
        source="manual",
        snapshot_date="2026-06-30",
        bars=[{"date": "2026-06-27", "close": 1.0}, {"date": "2026-06-30", "close": 1.0}],
    )
    portfolio = PaperPortfolioSummary(
        household_id="household-1",
        net_contributions=10000,
        cash_balance=1000,
        market_value=9000,
        total_equity=10000,
        unrealized_pnl=0,
        realized_pnl=0,
        total_fees=0,
        fill_count=1,
        positions=[
            PaperPositionData(
                instrument_id="equity",
                symbol=equity.symbol,
                name=equity.name,
                market=equity.market,
                asset_class="equity",
                currency="CNY",
                quantity=9000,
                average_cost=1,
                total_cost=9000,
                latest_price=1,
                latest_price_date="2026-06-30",
                market_value=9000,
                unrealized_pnl=0,
                total_fees=0,
            )
        ],
    )
    policy = QuantInvestmentPolicyData(default_monthly_budget=1000)
    result = build_quant_monthly_proposal(
        household=HouseholdData(cash_account_balance=100000, monthly_expense=1000),
        policy_id="policy-1",
        policy=policy,
        instruments=[("equity", equity), ("defensive", defensive)],
        snapshots={"equity": ("snapshot-equity", snapshot), "defensive": ("snapshot-defensive", snapshot)},
        paper_portfolio=portfolio,
    )
    sell_orders = [order for order in result.orders if order.side == "sell"]
    assert result.proposal.rebalance_triggered
    assert result.proposal.current_equity_ratio == pytest.approx(0.9)
    assert sell_orders
    assert sell_orders[0].instrument_id == "equity"
    assert sell_orders[0].funding_source == "paper_cash"
    assert sell_orders[0].is_rebalance


def test_rebalance_execution_cannot_overdraw_cash_or_oversell_positions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        instrument = client.post(
            "/api/quant-investment/instruments",
            json={
                "household_id": household_id,
                "data": {"symbol": "511010.SH", "name": "示例防御 ETF", "market": "mainland_etf", "asset_class": "defensive"},
            },
        ).json()
        buy = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "rebalance-buy",
                    "instrument_id": instrument["id"],
                    "side": "buy",
                    "funding_source": "paper_cash",
                    "is_rebalance": True,
                    "order_amount": 1000,
                    "estimated_price": 1,
                    "estimated_quantity": 900,
                    "estimated_fee": 1.35,
                    "lot_size": 100,
                },
            },
        ).json()
        sell = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "rebalance-sell",
                    "instrument_id": instrument["id"],
                    "side": "sell",
                    "funding_source": "paper_cash",
                    "is_rebalance": True,
                    "order_amount": 1000,
                    "estimated_price": 1,
                    "estimated_quantity": 1000,
                    "estimated_fee": 5,
                    "lot_size": 100,
                },
            },
        ).json()
        buy_response = client.post(
            f"/api/quant-investment/paper-orders/{buy['id']}/simulate",
            json={"household_id": household_id},
        )
        sell_response = client.post(
            f"/api/quant-investment/paper-orders/{sell['id']}/simulate",
            json={"household_id": household_id},
        )
    assert buy_response.status_code == 409
    assert "模拟现金不足" in buy_response.json()["detail"]
    assert sell_response.status_code == 409
    assert "超过当前可用持仓" in sell_response.json()["detail"]


def test_paper_sell_uses_position_available_on_execution_date(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOUSE_PLANNER_DB", str(tmp_path / "planner.db"))
    from app import database
    from app.main import app

    database.DB_PATH = database.default_db_path()
    with TestClient(app) as client:
        household_id = client.get("/api/households").json()[0]["id"]
        instrument = client.post(
            "/api/quant-investment/instruments",
            json={
                "household_id": household_id,
                "data": {
                    "symbol": "510300.SH",
                    "name": "示例成交时钟 ETF",
                    "market": "mainland_etf",
                    "asset_class": "equity",
                },
            },
        ).json()
        buy = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "clock-buy",
                    "instrument_id": instrument["id"],
                    "order_amount": 1000,
                    "estimated_price": 1,
                    "estimated_quantity": 995,
                    "estimated_fee": 5,
                    "cash_contribution_amount": 1000,
                },
            },
        ).json()
        buy_response = client.post(
            f"/api/quant-investment/paper-orders/{buy['id']}/simulate",
            json={"household_id": household_id, "executed_date": "2026-02-01"},
        )
        sell = client.post(
            "/api/quant-investment/paper-orders",
            json={
                "household_id": household_id,
                "data": {
                    "proposal_id": "clock-sell",
                    "instrument_id": instrument["id"],
                    "side": "sell",
                    "funding_source": "paper_cash",
                    "order_amount": 500,
                    "estimated_price": 1,
                    "estimated_quantity": 500,
                    "estimated_fee": 2.5,
                },
            },
        ).json()
        backdated_sell = client.post(
            f"/api/quant-investment/paper-orders/{sell['id']}/simulate",
            json={"household_id": household_id, "executed_date": "2026-01-15"},
        )
        valid_sell = client.post(
            f"/api/quant-investment/paper-orders/{sell['id']}/simulate",
            json={"household_id": household_id, "executed_date": "2026-02-02"},
        )

    assert buy_response.status_code == 200
    assert backdated_sell.status_code == 409
    assert "成交日" in backdated_sell.json()["detail"]
    assert valid_sell.status_code == 200
