from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .schemas import InvestmentInstrumentData


CalendarQuery = Callable[[str, dict[str, Any], str], list[dict[str, Any]]]


@dataclass(frozen=True)
class TradingCalendarResult:
    calendar_name: str
    source: str
    trading_days: list[str]
    warning: str = ""


def _iso_date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def fetch_tushare_trading_calendar(
    instrument: InvestmentInstrumentData,
    *,
    start_date: str,
    end_date: str,
    query: CalendarQuery,
) -> TradingCalendarResult:
    """Fetch an exchange calendar without coupling it to credentials/storage."""
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    if instrument.market == "hong_kong_connect":
        api_name = "hk_tradecal"
        params = {"start_date": start, "end_date": end}
        calendar_name = "hkex"
    elif instrument.market in {"mainland_etf", "qdii_etf"}:
        api_name = "trade_cal"
        exchange = "SZSE" if instrument.symbol.upper().endswith(".SZ") else "SSE"
        params = {"exchange": exchange, "start_date": start, "end_date": end}
        calendar_name = "szse" if exchange == "SZSE" else "sse"
    else:
        return TradingCalendarResult("fund_nav", "observed_prices", [])
    rows = query(api_name, params, "exchange,cal_date,trade_date,is_open")
    trading_days = sorted(
        {
            _iso_date(row.get("cal_date") or row.get("trade_date"))
            for row in rows
            if row.get("cal_date") or row.get("trade_date")
            if str(row.get("is_open", "1")) not in {"0", "False", "false"}
        }
    )
    if not trading_days:
        raise RuntimeError(f"{api_name} 未返回开放交易日")
    return TradingCalendarResult(calendar_name, "provider", trading_days)
