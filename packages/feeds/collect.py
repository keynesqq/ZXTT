"""公告 / 研报 / 资讯 / 观点 / 行业资讯 采集与合并。"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from collect.manifest import track_source
from core.config import feeds_cfg
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import market_data_date
from feeds.announcements import fetch_announcement_rows
from feeds.feed_warnings import (
    ANN_EMPTY,
    ANN_LATEST_FALLBACK,
    FEED_COLLECT_FAILED,
    append_feed_warning,
    feed_warning,
)
from feeds.non_announcement import ALL_CATEGORIES, NonAnnouncementOptions, collect_non_announcement
from quote.industry_cache import batch_industries
from watchlist.loader import load_stocks
from watchlist.ths_blocks import StockItem

FEED_CATEGORIES = ("公告", "研报", "资讯", "观点", "行业资讯")


@dataclass
class FeedItem:
    category: str
    title: str
    pub_date: str
    pub_time: str = ""
    source: str = ""
    url: str = ""
    provider: str = ""
    extra: str = ""
    fetched_at: str = ""


@dataclass
class StockFeeds:
    code: str
    name: str
    group: str
    industry: str = ""
    feeds: dict[str, list[FeedItem]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    warnings_struct: list[dict[str, Any]] = field(default_factory=list)
    collected_at: str = ""


def _collect_workers(count: int, override: int | None = None) -> int:
    if override is not None:
        workers = override
    else:
        workers = int(feeds_cfg().get("max_workers", 4))
    workers = max(1, min(int(workers), 16))
    return min(workers, count or 1)


def _lookback(key: str, default: int) -> int:
    block = feeds_cfg().get(key) or {}
    return int(block.get("lookback_days", default))


def _to_feed(category: str, row: dict) -> FeedItem:
    return FeedItem(
        category=category,
        title=row.get("title", ""),
        pub_date=row.get("pub_date", ""),
        pub_time=row.get("pub_time", ""),
        source=row.get("source", ""),
        url=row.get("url", ""),
        provider=row.get("provider", ""),
        extra=row.get("extra", ""),
        fetched_at=now_iso(),
    )


def _collect_announcements(
    stock: StockItem,
    end: date,
    warnings: list[str],
    warnings_struct: list[dict[str, Any]],
) -> list[FeedItem]:
    code = stock.code
    ann_cfg = feeds_cfg().get("announcement") or {}
    days = _lookback("announcement", 30)
    latest_n = int(ann_cfg.get("fallback_latest_count", 5))
    start = end - timedelta(days=days)
    max_count = int(ann_cfg.get("max_count") or 0)

    fetched = fetch_announcement_rows(
        code,
        start=start,
        end=end,
        lookback_days=days,
        fallback_latest_count=latest_n,
        max_count=max_count,
    )
    if fetched.warning_code == ANN_EMPTY:
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(
                ANN_EMPTY,
                fetched.warning_message or "",
                category="公告",
                code=code,
                group=stock.group,
            ),
        )
    elif fetched.warning_code == ANN_LATEST_FALLBACK:
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(
                ANN_LATEST_FALLBACK,
                fetched.warning_message or "",
                category="公告",
                code=code,
                group=stock.group,
            ),
        )

    return [_to_feed("公告", r) for r in fetched.rows]


def collect_stock_feeds(
    stock: StockItem,
    *,
    report_date: date | None = None,
    industry: str | None = None,
) -> StockFeeds:
    end = report_date or date.today()
    warnings: list[str] = []
    warnings_struct: list[dict[str, Any]] = []
    if industry is None:
        industry = batch_industries([stock.code]).get(stock.code, "")
    else:
        industry = industry or ""

    ann = _collect_announcements(stock, end, warnings, warnings_struct)
    cfg = feeds_cfg()
    na = collect_non_announcement(
        stock,
        industry=industry,
        options=NonAnnouncementOptions(
            end_date=end,
            cfg=cfg,
            unified_lookback_days=None,
            max_count=0,
            categories=ALL_CATEGORIES,
            industry_enabled=True,
        ),
    )
    warnings.extend(na.warnings)
    warnings_struct.extend(na.warnings_struct)

    feeds = {
        "公告": ann,
        "研报": na.research,
        "资讯": na.news,
        "观点": na.opinions,
        "行业资讯": na.industry_news,
    }
    return StockFeeds(
        code=stock.code,
        name=stock.name,
        group=stock.group,
        industry=industry,
        feeds=feeds,
        warnings=warnings,
        warnings_struct=warnings_struct,
        collected_at=now_iso(),
    )


def collect_all_feeds(
    stocks: list[StockItem] | None = None,
    *,
    report_date: date | None = None,
    max_workers: int | None = None,
) -> list[StockFeeds]:
    from concurrent.futures import ThreadPoolExecutor

    stocks = stocks or load_stocks()
    if not stocks:
        return []

    end = report_date or date.today()
    trade = market_data_date(end)

    unique_by_code: dict[str, StockItem] = {}
    for s in stocks:
        if s.code not in unique_by_code:
            unique_by_code[s.code] = s

    industry_map = batch_industries(list(unique_by_code.keys()))
    cache: dict[str, StockFeeds] = {}

    def _one(item: StockItem) -> tuple[str, StockFeeds]:
        return item.code, collect_stock_feeds(
            item,
            report_date=end,
            industry=industry_map.get(item.code, ""),
        )

    workers = _collect_workers(len(unique_by_code), max_workers)
    with track_source(trade, "feeds", calendar_date=end) as rec:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_one, item): item for item in unique_by_code.values()}
            for fut, item in futs.items():
                try:
                    code, feeds = fut.result()
                    cache[code] = feeds
                except Exception as e:
                    msg = f"素材采集失败: {e}"
                    cache[item.code] = StockFeeds(
                        code=item.code,
                        name=item.name,
                        group=item.group,
                        warnings=[msg],
                        warnings_struct=[
                            feed_warning(
                                FEED_COLLECT_FAILED,
                                msg,
                                code=item.code,
                                group=item.group,
                            )
                        ],
                    )

        result: list[StockFeeds] = []
        for s in stocks:
            base = cache.get(s.code)
            if base is None:
                msg = "素材采集失败"
                result.append(
                    StockFeeds(
                        code=s.code,
                        name=s.name,
                        group=s.group,
                        warnings=[msg],
                        warnings_struct=[
                            feed_warning(FEED_COLLECT_FAILED, msg, code=s.code, group=s.group)
                        ],
                    )
                )
                continue
            result.append(
                StockFeeds(
                    code=s.code,
                    name=s.name or base.name,
                    group=s.group,
                    industry=base.industry,
                    feeds=base.feeds,
                    warnings=base.warnings,
                    warnings_struct=base.warnings_struct,
                )
            )
        item_count = sum(sum(len(sf.feeds.get(c, [])) for c in FEED_CATEGORIES) for sf in result)
        warn_codes = sum(1 for sf in result if sf.warnings)
        rec["stock_count"] = len(unique_by_code)
        rec["row_count"] = len(result)
        rec["item_count"] = item_count
        rec["warn_rows"] = warn_codes
        rec["ok"] = warn_codes < len(result) or len(result) == 0
        return result


def feeds_cache_path(on_date: date | None = None) -> Path:
    d = on_date or date.today()
    return DATA_DIR / f"feeds_cache_{d.isoformat()}.json"


def _feed_item_to_dict(item: FeedItem) -> dict[str, str]:
    return {
        "category": item.category,
        "title": item.title,
        "pub_date": item.pub_date,
        "pub_time": item.pub_time,
        "source": item.source,
        "url": item.url,
        "provider": item.provider,
        "extra": item.extra,
        "fetched_at": item.fetched_at,
    }


def _feed_item_from_dict(row: dict) -> FeedItem:
    return FeedItem(
        category=str(row.get("category") or ""),
        title=str(row.get("title") or ""),
        pub_date=str(row.get("pub_date") or ""),
        pub_time=str(row.get("pub_time") or ""),
        source=str(row.get("source") or ""),
        url=str(row.get("url") or ""),
        provider=str(row.get("provider") or ""),
        extra=str(row.get("extra") or ""),
        fetched_at=str(row.get("fetched_at") or ""),
    )


def save_feeds_cache(feeds_list: list[StockFeeds], *, on_date: date | None = None) -> Path:
    day = on_date or date.today()
    path = feeds_cache_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": day.isoformat(),
        "saved_at": time.time(),
        "items": [
            {
                "code": sf.code,
                "name": sf.name,
                "group": sf.group,
                "industry": sf.industry,
                "collected_at": sf.collected_at,
                "warnings": list(sf.warnings),
                "warnings_struct": list(sf.warnings_struct),
                "feeds": {
                    cat: [_feed_item_to_dict(it) for it in sf.feeds.get(cat, [])]
                    for cat in FEED_CATEGORIES
                },
            }
            for sf in feeds_list
        ],
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False))
    return path


def load_feeds_cache(
    *,
    on_date: date | None = None,
    max_age_sec: int | None = 7200,
) -> list[StockFeeds] | None:
    day = on_date or date.today()
    path = feeds_cache_path(day)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if max_age_sec is not None:
        saved_at = float(payload.get("saved_at") or 0)
        if saved_at <= 0 or time.time() - saved_at > max_age_sec:
            return None
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return None
    out: list[StockFeeds] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        feeds = {
            cat: [_feed_item_from_dict(it) for it in (row.get("feeds") or {}).get(cat, []) if isinstance(it, dict)]
            for cat in FEED_CATEGORIES
        }
        out.append(
            StockFeeds(
                code=str(row.get("code") or ""),
                name=str(row.get("name") or ""),
                group=str(row.get("group") or ""),
                industry=str(row.get("industry") or ""),
                feeds=feeds,
                warnings=[str(w) for w in (row.get("warnings") or [])],
                warnings_struct=[w for w in (row.get("warnings_struct") or []) if isinstance(w, dict)],
                collected_at=str(row.get("collected_at") or ""),
            )
        )
    return out or None
