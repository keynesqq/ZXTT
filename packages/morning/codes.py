"""解析 31 只代码列表（quote_query 回退链）。"""
from __future__ import annotations

from datetime import date

from core.config import normalize_code
from core.trading_calendar import previous_trading_day
from quote.query_cache import load_quote_query_cache
from watchlist.loader import load_stocks


def codes_from_quote(day: date) -> tuple[list[str], str]:
    for label, d in (
        ("today", day),
        ("prev_td", previous_trading_day(day)),
    ):
        if not d:
            continue
        data = load_quote_query_cache(on_date=d)
        if not data:
            continue
        codes: list[str] = []
        seen: set[str] = set()
        for row in data.get("quotes") or []:
            code = normalize_code(str(row.get("code") or ""))
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        if codes:
            return codes, f"quote_query_{d.isoformat()}.json"
    stocks = load_stocks()
    if stocks:
        codes = []
        seen: set[str] = set()
        for s in stocks:
            code = normalize_code(s.code)
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        if codes:
            return codes, "watchlist"
    return [], ""


__all__ = ["codes_from_quote"]
