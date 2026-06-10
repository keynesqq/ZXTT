"""单股/多股非公告资讯即时查询（默认落盘）。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any

from announcement.query import resolve_query_stocks
from core.config import news_cfg
from core.context_as_of import now_iso
from feeds.collect import FeedItem
from feeds.feed_warnings import FEED_COLLECT_FAILED, feed_warning
from feeds.non_announcement import (
    ALL_CATEGORIES,
    CATEGORY_INDUSTRY,
    NonAnnouncementOptions,
    collect_non_announcement,
    parse_categories,
)
from quote.industry_cache import batch_industries
from watchlist.ths_blocks import StockItem

DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_MAX_COUNT = 0
PARALLEL_MIN_STOCKS = 2
DEFAULT_MAX_WORKERS = 4


@dataclass(frozen=True)
class NewsQueryOptions:
    lookback_days: int
    max_count: int
    end_date: date
    industry_enabled: bool
    categories: frozenset[str]
    strict: bool = False


def _cfg_int(cfg: dict, key: str, default: int) -> int:
    return int(cfg.get(key, default))


def _query_workers(stock_count: int, cfg: dict) -> int:
    if stock_count < PARALLEL_MIN_STOCKS:
        return 1
    cfg_workers = int(cfg.get("max_workers", DEFAULT_MAX_WORKERS))
    return max(1, min(cfg_workers, 16, stock_count))


def resolve_query_options(
    *,
    days: int | None = None,
    max_count: int | None = None,
    on_date: date | None = None,
    industry_enabled: bool | None = None,
    categories: frozenset[str] | None = None,
    strict: bool | None = None,
) -> NewsQueryOptions:
    cfg = news_cfg()
    lookback = days if days is not None else _cfg_int(cfg, "lookback_days", DEFAULT_LOOKBACK_DAYS)
    max_n = max_count if max_count is not None else _cfg_int(cfg, "max_count", DEFAULT_MAX_COUNT)
    ind = bool(cfg.get("industry_enabled", True)) if industry_enabled is None else industry_enabled
    cats = categories if categories is not None else ALL_CATEGORIES
    strict_mode = bool(cfg.get("strict", False)) if strict is None else bool(strict)
    if not ind:
        cats = frozenset(c for c in cats if c != CATEGORY_INDUSTRY)
    if not cats:
        raise ValueError("至少选择一类资讯（news / opinions / research / industry）")

    if lookback < 1 or lookback > 365:
        raise ValueError("资讯回溯天数须在 1–365 之间")
    if max_n < 0 or max_n > 200:
        raise ValueError("资讯最多展示条数须在 0–200 之间（0 表示不限制）")

    return NewsQueryOptions(
        lookback_days=lookback,
        max_count=max_n,
        end_date=on_date or date.today(),
        industry_enabled=ind,
        categories=cats,
        strict=strict_mode,
    )


def _item_dict(item: FeedItem) -> dict[str, str]:
    return {
        "title": item.title,
        "pub_date": item.pub_date,
        "pub_time": item.pub_time,
        "source": item.source,
        "url": item.url,
        "provider": item.provider,
        "extra": item.extra,
    }


def _query_meta(options: NewsQueryOptions) -> dict[str, Any]:
    return {
        "lookback_days": options.lookback_days,
        "max_count": options.max_count,
        "end_date": options.end_date.isoformat(),
        "industry_enabled": options.industry_enabled,
        "categories": sorted(options.categories),
        "strict": options.strict,
    }


def query_news_for_stock(
    stock: StockItem,
    *,
    options: NewsQueryOptions,
    industry: str = "",
    industry_news_cache: dict[str, list[Any]] | None = None,
    industry_cache_lock: Lock | None = None,
) -> dict[str, Any]:
    cfg = news_cfg()
    na_opts = NonAnnouncementOptions(
        end_date=options.end_date,
        cfg=cfg,
        unified_lookback_days=options.lookback_days,
        max_count=options.max_count,
        categories=options.categories,
        industry_enabled=options.industry_enabled,
        strict=options.strict,
        industry_news_cache=industry_news_cache,
        industry_cache_lock=industry_cache_lock,
    )
    result = collect_non_announcement(stock, industry=industry, options=na_opts)
    news = [_item_dict(it) for it in result.news]
    opinions = [_item_dict(it) for it in result.opinions]
    research = [_item_dict(it) for it in result.research]
    industry_news = [_item_dict(it) for it in result.industry_news]
    return {
        "code": stock.code,
        "name": stock.name,
        "group": stock.group,
        "industry": industry,
        "news_count": len(news),
        "news": news,
        "opinion_count": len(opinions),
        "opinions": opinions,
        "research_count": len(research),
        "research": research,
        "industry_news_count": len(industry_news),
        "industry_news": industry_news,
        "query": _query_meta(options),
        "warnings": list(result.warnings),
        "warnings_struct": list(result.warnings_struct),
        "queried_at": now_iso(),
    }


def query_news(
    codes: list[str],
    *,
    options: NewsQueryOptions | None = None,
    days: int | None = None,
    max_count: int | None = None,
    on_date: date | None = None,
    industry_enabled: bool | None = None,
    categories: frozenset[str] | None = None,
    strict: bool | None = None,
    save: bool = True,
) -> tuple[list[dict[str, Any]], Path | None]:
    opts = options or resolve_query_options(
        days=days,
        max_count=max_count,
        on_date=on_date,
        industry_enabled=industry_enabled,
        categories=categories,
        strict=strict,
    )
    stocks = resolve_query_stocks(codes)
    if not stocks:
        return [], None

    industry_map = batch_industries([s.code for s in stocks])
    cfg = news_cfg()
    workers = _query_workers(len(stocks), cfg)
    industry_news_cache: dict[str, list[Any]] = {}
    industry_cache_lock = Lock()

    def _one(stock: StockItem) -> dict[str, Any]:
        try:
            return query_news_for_stock(
                stock,
                options=opts,
                industry=industry_map.get(stock.code, ""),
                industry_news_cache=industry_news_cache,
                industry_cache_lock=industry_cache_lock,
            )
        except Exception as e:
            msg = f"资讯查询失败: {e}"
            return {
                "code": stock.code,
                "name": stock.name,
                "group": stock.group,
                "industry": industry_map.get(stock.code, ""),
                "news_count": 0,
                "news": [],
                "opinion_count": 0,
                "opinions": [],
                "research_count": 0,
                "research": [],
                "industry_news_count": 0,
                "industry_news": [],
                "query": _query_meta(opts),
                "warnings": [msg],
                "warnings_struct": [
                    feed_warning(
                        FEED_COLLECT_FAILED,
                        msg,
                        code=stock.code,
                        group=stock.group,
                    )
                ],
                "queried_at": now_iso(),
            }

    if workers == 1:
        items = [_one(stock) for stock in stocks]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            items = list(pool.map(_one, stocks))

    path: Path | None = None
    if save and items:
        from news.query_cache import persist_news_query

        path = persist_news_query(items, opts)
    return items, path


__all__ = [
    "NewsQueryOptions",
    "parse_categories",
    "query_news",
    "query_news_for_stock",
    "resolve_query_options",
]
