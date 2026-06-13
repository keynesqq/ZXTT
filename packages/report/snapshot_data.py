"""行情快照页数据：snapshot 缓存 → quote query → 自选占位。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.trading_calendar import market_data_date, previous_trading_day, today_cn
from quote.query_cache import join_quotes_with_memberships, load_quote_query_cache
from quote.snapshot.build import build_placeholder_snapshots, snapshot_row_dict
from quote.snapshot.cache import (
    load_snapshot_cache_file,
    normalize_snapshot_rows,
    structure_from_row_dicts,
    structure_from_stocks,
)
from watchlist.loader import load_stocks, watchlist_group_names, watchlist_source_summary
from watchlist.refresh import codes_match_watchlist

_CN_TZ = ZoneInfo("Asia/Shanghai")
_STALE_SEC = 6 * 3600


def snapshot_view_day(day: date | None = None) -> date:
    return market_data_date(day or today_cn())


def _parse_ts(text: str) -> datetime | None:
    s = (text or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=_CN_TZ)
        except ValueError:
            continue
    return None


def _is_stale(generated_at: str, *, quotes_pending: bool) -> bool:
    if quotes_pending:
        return True
    ts = _parse_ts(generated_at)
    if ts is None:
        return True
    age = (datetime.now(_CN_TZ) - ts).total_seconds()
    return age > _STALE_SEC


def _ordered_groups(rows: list[dict], structure: dict[str, Any] | None) -> list[str]:
    names: list[str] = []
    if structure and isinstance(structure.get("groups"), list):
        for g in structure["groups"]:
            if isinstance(g, dict):
                n = str(g.get("name") or "").strip()
                if n and n not in names:
                    names.append(n)
    for g in watchlist_group_names():
        if g not in names:
            names.append(g)
    for row in rows:
        n = str(row.get("group") or "").strip()
        if n and n not in names:
            names.append(n)
    present = {str(r.get("group") or "").strip() for r in rows}
    return [g for g in names if g in present]


def load_snapshot_page_context(day: date | None = None) -> dict[str, Any]:
    cal = snapshot_view_day(day)
    rows: list[dict] | None = None
    structure: dict[str, Any] | None = None
    generated_at = ""
    quotes_pending = False
    source = ""

    cache = load_snapshot_cache_file(on_date=cal)
    if cache and isinstance(cache.get("rows"), list) and cache["rows"]:
        candidate = normalize_snapshot_rows(cache["rows"])
        if codes_match_watchlist(candidate):
            rows = candidate
            structure = structure_from_row_dicts(rows)
            generated_at = str(cache.get("generated_at") or "")
            quotes_pending = bool(cache.get("quotes_pending"))
            source = "snapshot_cache"

    if not rows:
        qq = load_quote_query_cache(on_date=cal)
        if qq:
            joined = join_quotes_with_memberships(
                qq.get("quotes") or [],
                qq.get("memberships") or [],
            )
            if joined and codes_match_watchlist(joined):
                rows = normalize_snapshot_rows(joined)
                structure = qq.get("structure") if isinstance(qq.get("structure"), dict) else None
                generated_at = str(qq.get("updated_at") or "")
                source = "quote_query"

    if not rows:
        prev = previous_trading_day(cal)
        if prev:
            qq = load_quote_query_cache(on_date=prev)
            if qq:
                joined = join_quotes_with_memberships(
                    qq.get("quotes") or [],
                    qq.get("memberships") or [],
                )
                if joined:
                    rows = normalize_snapshot_rows(joined)
                    structure = qq.get("structure") if isinstance(qq.get("structure"), dict) else None
                    generated_at = str(qq.get("updated_at") or "")
                    source = "quote_query_prev"

    if not rows:
        stocks = load_stocks()
        placeholders = build_placeholder_snapshots(stocks)
        rows = [snapshot_row_dict(r, quotes_pending=True) for r in placeholders]
        structure = structure_from_stocks(stocks)
        quotes_pending = True
        source = "watchlist_placeholder"

    groups = _ordered_groups(rows, structure)
    stale = _is_stale(generated_at, quotes_pending=quotes_pending)
    wl_src = watchlist_source_summary()

    return {
        "trade_date": cal.isoformat(),
        "row_count": len(rows),
        "rows": rows,
        "snapshot_groups": groups,
        "generated_at": generated_at,
        "snapshot_stale": stale,
        "quotes_pending": quotes_pending,
        "source": source,
        "watchlist_source": wl_src,
    }


__all__ = ["load_snapshot_page_context", "snapshot_view_day"]
