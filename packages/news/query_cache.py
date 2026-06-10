"""news query 落盘。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from core.query_cache import code_merge_key, query_cache_path, write_query_cache
from news.query import NewsQueryOptions

PREFIX = "news_query"


def news_query_cache_path(on_date: date | None = None) -> Path:
    return query_cache_path(PREFIX, on_date)


def persist_news_query(
    items: list[dict],
    options: NewsQueryOptions,
) -> Path:
    query_meta = {
        "lookback_days": options.lookback_days,
        "max_count": options.max_count,
        "end_date": options.end_date.isoformat(),
        "industry_enabled": options.industry_enabled,
        "categories": sorted(options.categories),
        "strict": options.strict,
    }
    return write_query_cache(
        PREFIX,
        payload_key="items",
        items=items,
        query_meta=query_meta,
        on_date=options.end_date,
        merge_key_fn=code_merge_key,
    )
