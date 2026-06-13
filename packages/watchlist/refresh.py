"""设置页保存自选后，按同花顺 PC + config 刷新 quote / 快照页。"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.config import normalize_code
from core.trading_calendar import market_data_date, today_cn
from quote.snapshot.cache import snapshot_cache_path
from watchlist.loader import (
    load_stocks,
    watchlist_group_names,
    watchlist_source_summary,
    align_group_order,
)


def clear_snapshot_cache(on_date: date | None = None) -> None:
    snapshot_cache_path(on_date).unlink(missing_ok=True)


def refresh_watchlist_pages(*, on_date: date | None = None, fetch_quotes: bool = True) -> dict[str, Any]:
    """自选板块变更后：重建 quote_query + 静态快照页（与设置页勾选一致）。"""
    cal = market_data_date(on_date or today_cn())
    clear_snapshot_cache(cal)

    quote_ok = False
    quote_error = ""
    if fetch_quotes:
        try:
            from quote.query import query_quotes

            _, path, meta = query_quotes(all_watchlist=True, on_date=cal)
            quote_ok = path is not None and int(meta.get("code_count") or 0) > 0
        except Exception as e:
            quote_error = str(e)

    from report.hub import publish_hub, publish_snapshot, refresh_hub_feed

    publish_snapshot(cal)
    publish_hub(cal)
    refresh_hub_feed(cal, force=True)

    summary = watchlist_source_summary()
    return {
        "ok": True,
        "trade_date": cal.isoformat(),
        "quote_refreshed": quote_ok,
        "quote_error": quote_error,
        **summary,
    }


def current_watchlist_codes() -> set[str]:
    try:
        stocks = load_stocks()
    except Exception:
        return set()
    return {normalize_code(s.code) for s in stocks if normalize_code(s.code)}


def codes_match_watchlist(rows: list[dict]) -> bool:
    if not rows:
        return False
    row_codes = {
        normalize_code(str(r.get("code") or ""))
        for r in rows
        if normalize_code(str(r.get("code") or ""))
    }
    expected = current_watchlist_codes()
    return bool(expected) and row_codes == expected


def align_group_order_for_reports(group_order: list[str]) -> list[str]:
    """三报告分片顺序 = 设置页勾选板块 = 行情快照 Tab 顺序。"""
    return align_group_order(group_order)


__all__ = [
    "align_group_order_for_reports",
    "clear_snapshot_cache",
    "codes_match_watchlist",
    "current_watchlist_codes",
    "refresh_watchlist_pages",
]
