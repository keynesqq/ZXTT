"""announcement query 落盘。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from announcement.query import AnnouncementQueryOptions
from core.query_cache import code_merge_key, query_cache_path, write_query_cache

PREFIX = "announcement_query"


def announcement_query_cache_path(on_date: date | None = None) -> Path:
    return query_cache_path(PREFIX, on_date)


def persist_announcement_query(
    items: list[dict],
    options: AnnouncementQueryOptions,
) -> Path:
    query_meta = {
        "lookback_days": options.lookback_days,
        "max_count": options.max_count,
        "fallback_latest_count": options.fallback_latest_count,
        "end_date": options.end_date.isoformat(),
    }
    return write_query_cache(
        PREFIX,
        payload_key="items",
        items=items,
        query_meta=query_meta,
        on_date=options.end_date,
        merge_key_fn=code_merge_key,
    )
