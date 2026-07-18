from __future__ import annotations

from datetime import date, timedelta

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

    assert [api_name for api_name, _params in calls] == ["fund_daily", "fund_nav"]
    assert calls[1][1]["market"] == "E"
    assert [(bar.date, bar.nav, bar.nav_date) for bar in snapshot.bars] == [
        ("2026-07-16", 1.10, "2026-07-15"),
        ("2026-07-17", 1.15, "2026-07-17"),
    ]


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
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["data"]["status"] == "simulated"
    assert first.json()["data"]["executed_price"] == pytest.approx(4.2)


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
