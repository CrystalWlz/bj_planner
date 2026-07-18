from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from .schemas import InvestmentInstrumentData, InvestmentMarketBarData, InvestmentMarketSnapshotData


TUSHARE_API_URL = "https://api.tushare.pro"


class MarketDataConfigurationError(RuntimeError):
    pass


def tushare_private_config_path() -> Path:
    """Return the per-user, untracked location for the Tushare token."""
    appdata = os.environ.get("APPDATA")
    config_root = Path(appdata) / "house-planner" if appdata else Path.home() / ".house-planner"
    return config_root / "tushare.env"


def _token_from_private_config(path: Path) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Personal Tushare Pro configuration. Keep this file private.\n"
            "# Do not commit it, copy it into exports, or paste it into chat.\n"
            "TUSHARE_TOKEN=\n",
            encoding="utf-8",
        )
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MarketDataConfigurationError(f"Unable to read local Tushare configuration: {path}") from exc
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "TUSHARE_TOKEN":
            return value.strip().strip('"').strip("'")
    return ""


def tushare_token() -> str:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token:
        return token
    token = _token_from_private_config(tushare_private_config_path())
    if not token:
        raise MarketDataConfigurationError("未检测到 TUSHARE_TOKEN；请仅在本机私有环境变量中设置后再刷新行情。")
    return token


def _tushare_query(api_name: str, params: dict[str, Any], fields: str) -> list[dict[str, Any]]:
    response = httpx.post(
        TUSHARE_API_URL,
        json={"api_name": api_name, "token": tushare_token(), "params": params, "fields": fields},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", -1)) != 0:
        raise RuntimeError(str(payload.get("msg") or "Tushare Pro 返回了未知错误。"))
    data = payload.get("data") or {}
    columns = data.get("fields") or []
    return [dict(zip(columns, row, strict=False)) for row in data.get("items") or []]


def _iso_tushare_date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _fund_daily_bars(
    price_rows: list[dict[str, Any]],
    nav_rows: list[dict[str, Any]] | None = None,
) -> list[InvestmentMarketBarData]:
    """Join the latest published NAV to each ETF trading day without look-ahead."""
    nav_items = sorted(
        (
            (_iso_tushare_date(row.get("nav_date")), float(row["unit_nav"]), float(row.get("adj_nav") or row.get("accum_nav") or row["unit_nav"]))
            for row in (nav_rows or [])
            if row.get("nav_date") and row.get("unit_nav")
        ),
        key=lambda item: item[0],
    )
    latest_nav: tuple[str, float, float] | None = None
    nav_index = 0
    bars: list[InvestmentMarketBarData] = []
    for row in sorted(price_rows, key=lambda item: _iso_tushare_date(item.get("trade_date"))):
        if not row.get("close"):
            continue
        trade_date = _iso_tushare_date(row.get("trade_date"))
        while nav_index < len(nav_items) and nav_items[nav_index][0] <= trade_date:
            latest_nav = nav_items[nav_index]
            nav_index += 1
        close = float(row["close"])
        bars.append(
            InvestmentMarketBarData(
                date=trade_date,
                close=close,
                adjusted_close=close,
                nav=latest_nav[1] if latest_nav else None,
                nav_date=latest_nav[0] if latest_nav else "",
            )
        )
    return bars


def fetch_tushare_snapshot(instrument: InvestmentInstrumentData, *, start_date: str = "") -> InvestmentMarketSnapshotData:
    start = start_date.replace("-", "") or f"{date.today().year - 3}0101"
    if instrument.market in {"mainland_etf", "qdii_etf"}:
        rows = _tushare_query("fund_daily", {"ts_code": instrument.symbol, "start_date": start}, "ts_code,trade_date,close")
        nav_rows = (
            _tushare_query(
                "fund_nav",
                {"ts_code": instrument.symbol, "start_date": start, "market": "E"},
                "ts_code,nav_date,unit_nav,accum_nav,adj_nav",
            )
            if instrument.market == "qdii_etf"
            else []
        )
        bars = _fund_daily_bars(rows, nav_rows)
    elif instrument.market == "hong_kong_connect":
        rows = _tushare_query("hk_daily", {"ts_code": instrument.symbol, "start_date": start}, "ts_code,trade_date,close")
        bars = [InvestmentMarketBarData(date=f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}", close=float(row["close"]), adjusted_close=float(row["close"])) for row in rows if row.get("close")]
    else:
        rows = _tushare_query("fund_nav", {"ts_code": instrument.symbol, "start_date": start, "market": "O"}, "ts_code,nav_date,unit_nav,accum_nav,adj_nav")
        bars = [
            InvestmentMarketBarData(
                date=_iso_tushare_date(row.get("nav_date")),
                close=float(row["unit_nav"]),
                adjusted_close=float(row.get("adj_nav") or row.get("accum_nav") or row["unit_nav"]),
                nav=float(row["unit_nav"]),
                nav_date=_iso_tushare_date(row.get("nav_date")),
            )
            for row in rows
            if row.get("unit_nav")
        ]
    bars.sort(key=lambda item: item.date)
    return InvestmentMarketSnapshotData(
        source="tushare_pro",
        snapshot_date=date.today().isoformat(),
        status="complete" if bars else "empty",
        bars=bars,
        warning="" if bars else "数据源未返回可用日线，请检查标的代码和数据权限。",
    )
