from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import httpx

from .market_calendar import TradingCalendarResult, fetch_tushare_trading_calendar
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
            (
                _iso_tushare_date(row.get("nav_date")),
                _iso_tushare_date(row.get("ann_date"))
                or (
                    date.fromisoformat(_iso_tushare_date(row.get("nav_date"))) + timedelta(days=1)
                ).isoformat(),
                float(row["unit_nav"]),
                float(row.get("adj_nav") or row.get("accum_nav") or row["unit_nav"]),
            )
            for row in (nav_rows or [])
            if row.get("nav_date") and row.get("unit_nav")
        ),
        key=lambda item: (item[1], item[0]),
    )
    latest_nav: tuple[str, str, float, float] | None = None
    nav_index = 0
    bars: list[InvestmentMarketBarData] = []
    for row in sorted(price_rows, key=lambda item: _iso_tushare_date(item.get("trade_date"))):
        if not row.get("close"):
            continue
        trade_date = _iso_tushare_date(row.get("trade_date"))
        while nav_index < len(nav_items) and nav_items[nav_index][1] <= trade_date:
            latest_nav = nav_items[nav_index]
            nav_index += 1
        close = float(row["close"])
        bars.append(
            InvestmentMarketBarData(
                date=trade_date,
                close=close,
                adjusted_close=close,
                nav=latest_nav[2] if latest_nav else None,
                nav_date=latest_nav[0] if latest_nav else "",
                nav_available_date=latest_nav[1] if latest_nav else "",
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
                "ts_code,nav_date,ann_date,unit_nav,accum_nav,adj_nav",
            )
            if instrument.market == "qdii_etf"
            else []
        )
        bars = _fund_daily_bars(rows, nav_rows)
    elif instrument.market == "hong_kong_connect":
        rows = _tushare_query("hk_daily", {"ts_code": instrument.symbol, "start_date": start}, "ts_code,trade_date,close")
        bars = [InvestmentMarketBarData(date=f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}", close=float(row["close"]), adjusted_close=float(row["close"])) for row in rows if row.get("close")]
    else:
        rows = _tushare_query("fund_nav", {"ts_code": instrument.symbol, "start_date": start, "market": "O"}, "ts_code,nav_date,ann_date,unit_nav,accum_nav,adj_nav")
        bars = [
            InvestmentMarketBarData(
                date=_iso_tushare_date(row.get("nav_date")),
                close=float(row["unit_nav"]),
                adjusted_close=float(row.get("adj_nav") or row.get("accum_nav") or row["unit_nav"]),
                nav=float(row["unit_nav"]),
                nav_date=_iso_tushare_date(row.get("nav_date")),
                nav_available_date=_iso_tushare_date(row.get("ann_date")) or (
                    date.fromisoformat(_iso_tushare_date(row.get("nav_date"))) + timedelta(days=1)
                ).isoformat(),
            )
            for row in rows
            if row.get("unit_nav")
        ]
    bars.sort(key=lambda item: item.date)
    observed_days = sorted({bar.price_date or bar.date for bar in bars if bar.is_trading})
    calendar = TradingCalendarResult(
        "hkex" if instrument.market == "hong_kong_connect" else ("fund_nav" if instrument.market == "qdii_fund" else "sse_szse"),
        "observed_prices",
        observed_days,
    )
    calendar_warning = ""
    if instrument.market != "qdii_fund":
        try:
            calendar = fetch_tushare_trading_calendar(
                instrument,
                start_date=observed_days[0] if observed_days else f"{start[:4]}-{start[4:6]}-{start[6:]}",
                end_date=(date.today() + timedelta(days=14)).isoformat(),
                query=_tushare_query,
            )
        except Exception as exc:
            calendar_warning = f"交易日历接口不可用，已回退到实际价格日期：{exc}"
    observation_cutoff = observed_days[-1] if observed_days else date.today().isoformat()
    observed_calendar = {day for day in calendar.trading_days if day <= observation_cutoff}
    suspension_dates = sorted(observed_calendar - set(observed_days)) if calendar.source == "provider" else []
    warning_parts = []
    if not bars:
        warning_parts.append("数据源未返回可用日线，请检查标的代码和数据权限。")
    if calendar_warning:
        warning_parts.append(calendar_warning)
    return trace_market_snapshot(
        InvestmentMarketSnapshotData(
            source="tushare_pro",
            api_name={
                "qdii_etf": "fund_daily+fund_nav",
                "mainland_etf": "fund_daily",
                "hong_kong_connect": "hk_daily",
                "qdii_fund": "fund_nav",
            }[instrument.market],
            snapshot_date=date.today().isoformat(),
            trading_calendar=calendar.calendar_name,
            calendar_source=calendar.source,
            trading_days=calendar.trading_days,
            suspension_dates=suspension_dates,
            adjustment="provider" if instrument.market != "hong_kong_connect" else "none",
            expected_bar_count=len(observed_calendar) or None,
            status="complete" if bars else "empty",
            bars=bars,
            warning="；".join(warning_parts),
        )
    )


def trace_market_snapshot(snapshot: InvestmentMarketSnapshotData) -> InvestmentMarketSnapshotData:
    """Attach reproducibility metadata without storing credentials."""
    bars = [bar.model_copy(update={"price_date": bar.price_date or bar.date}) for bar in snapshot.bars]
    observed_days = sorted({bar.price_date or bar.date for bar in bars if bar.is_trading})
    trading_days = sorted(set(snapshot.trading_days or observed_days))
    observation_cutoff = observed_days[-1] if observed_days else snapshot.snapshot_date
    observed_calendar = {day for day in trading_days if day <= observation_cutoff}
    suspension_dates = sorted(
        set(snapshot.suspension_dates or [])
        | (observed_calendar - set(observed_days) if snapshot.calendar_source == "provider" else set())
    )
    completeness_ratio = (
        min(1.0, len(bars) / snapshot.expected_bar_count)
        if snapshot.expected_bar_count
        else (1.0 if snapshot.status == "complete" and bars else 0.0)
    )
    payload = snapshot.model_copy(
        update={
            "fetched_at": snapshot.fetched_at or datetime.now(timezone.utc).isoformat(),
            "actual_bar_count": len(bars),
            "completeness_ratio": completeness_ratio,
            "trading_days": trading_days,
            "suspension_dates": suspension_dates,
            "bars": bars,
        }
    )
    # These fields are derived or capture metadata; neither may change content identity.
    hash_payload = payload.model_copy(
        update={"dataset_hash": "", "data_version": "", "fetched_at": ""}
    ).model_dump(mode="json")
    digest = sha256(json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return payload.model_copy(update={"dataset_hash": digest, "data_version": f"{payload.source}:{payload.api_name or 'manual'}:{digest[:12]}"})
