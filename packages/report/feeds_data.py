"""公告资讯页数据：行情快照股票池 + announcement/news query 缓存。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.config import normalize_code
from core.query_cache import QUERY_CACHE_SCHEMA_VERSION, query_cache_path
from core.trading_calendar import previous_trading_day
from morning.feeds_merge import merge_feeds
from report.snapshot_data import load_snapshot_page_context, snapshot_view_day

FEED_CATEGORIES = ("公告", "研报", "资讯", "观点", "行业资讯")


def _load_query_cache(prefix: str, on_date: date) -> dict[str, Any] | None:
    path = query_cache_path(prefix, on_date)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("schema_version") or 0) != QUERY_CACHE_SCHEMA_VERSION:
        return None
    return data


def _items_by_code(items: list[dict] | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in items or []:
        code = normalize_code(str(row.get("code") or ""))
        if code:
            out[code] = row
    return out


def _resolve_query_caches(cal: date) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    ann: dict[str, Any] | None = None
    news: dict[str, Any] | None = None
    source = ""
    for try_day in (cal, previous_trading_day(cal)):
        if try_day is None:
            continue
        if ann is None:
            ann = _load_query_cache("announcement_query", try_day)
        if news is None:
            news = _load_query_cache("news_query", try_day)
        if ann and news:
            source = try_day.isoformat()
            break
        if ann or news:
            source = try_day.isoformat()
    return ann, news, source


def load_feeds_page_context(day: date | None = None) -> dict[str, Any]:
    snap = load_snapshot_page_context(day)
    cal = snapshot_view_day(day)
    ann_data, news_data, cache_date = _resolve_query_caches(cal)
    ann_by_code = _items_by_code((ann_data or {}).get("items"))
    news_by_code = _items_by_code((news_data or {}).get("items"))

    groups: dict[str, list[dict[str, Any]]] = {}
    stock_count = 0
    item_count = 0
    warn_rows = 0

    for row in snap.get("rows") or []:
        code = normalize_code(str(row.get("code") or ""))
        group = str(row.get("group") or "").strip()
        if not code or not group:
            continue
        ann_row = ann_by_code.get(code)
        news_row = news_by_code.get(code)
        merged = merge_feeds(ann_row, news_row)
        warnings = list(merged.get("warnings") or [])
        categories = {cat: list(merged.get(cat) or []) for cat in FEED_CATEGORIES}
        item_count += sum(len(categories[c]) for c in FEED_CATEGORIES)
        if warnings:
            warn_rows += 1
        stock_count += 1
        groups.setdefault(group, []).append(
            {
                "code": code,
                "name": str(row.get("name") or (ann_row or {}).get("name") or code),
                "group": group,
                "industry": str(row.get("industry") or (news_row or {}).get("industry") or ""),
                "warnings": warnings,
                "queried_at": str((ann_row or {}).get("queried_at") or (news_row or {}).get("queried_at") or ""),
                "categories": categories,
            }
        )

    group_order = [g for g in (snap.get("snapshot_groups") or []) if g in groups]
    for g in groups:
        if g not in group_order:
            group_order.append(g)

    ann_query = (ann_data or {}).get("query") or {}
    news_query = (news_data or {}).get("query") or {}
    feeds_missing = ann_data is None and news_data is None

    return {
        "trade_date": snap.get("trade_date") or cal.isoformat(),
        "stock_count": stock_count,
        "item_count": item_count,
        "warn_rows": warn_rows,
        "groups": groups,
        "feeds_group_order": group_order,
        "categories": list(FEED_CATEGORIES),
        "ann_updated_at": str((ann_data or {}).get("updated_at") or ""),
        "news_updated_at": str((news_data or {}).get("updated_at") or ""),
        "ann_lookback_days": ann_query.get("lookback_days"),
        "news_lookback_days": news_query.get("lookback_days"),
        "cache_date": cache_date,
        "feeds_missing": feeds_missing,
        "watchlist_source": snap.get("watchlist_source") or {},
    }


__all__ = ["FEED_CATEGORIES", "load_feeds_page_context"]
