"""单股/多股公告即时查询（巨潮主源 + AkShare 兜底，默认落盘）。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from core.config import feeds_cfg, normalize_code
from core.context_as_of import now_iso
from feeds.announcements import fetch_announcement_rows, warning_dict
from watchlist.loader import watchlist_by_code
from watchlist.ths_blocks import StockItem

DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MAX_COUNT = 0
PARALLEL_MIN_STOCKS = 2
DEFAULT_MAX_WORKERS = 4


@dataclass(frozen=True)
class AnnouncementQueryOptions:
    lookback_days: int
    max_count: int
    fallback_latest_count: int
    end_date: date


def _cfg_int(block: dict, key: str, default: int) -> int:
    return int(block.get(key, default))


def _query_workers(stock_count: int) -> int:
    if stock_count < PARALLEL_MIN_STOCKS:
        return 1
    cfg_workers = int(feeds_cfg().get("max_workers", DEFAULT_MAX_WORKERS))
    return max(1, min(cfg_workers, 16, stock_count))


def resolve_query_options(
    *,
    days: int | None = None,
    max_count: int | None = None,
    latest: int | None = None,
    on_date: date | None = None,
) -> AnnouncementQueryOptions:
    ann_cfg = feeds_cfg().get("announcement") or {}
    lookback = days if days is not None else _cfg_int(ann_cfg, "lookback_days", DEFAULT_LOOKBACK_DAYS)
    latest_n = int(latest) if latest is not None else 0
    max_n = max_count if max_count is not None else _cfg_int(ann_cfg, "max_count", DEFAULT_MAX_COUNT)

    if lookback < 1 or lookback > 365:
        raise ValueError("公告回溯天数须在 1–365 之间")
    if latest is not None and (latest_n < 1 or latest_n > 50):
        raise ValueError("公告备用条数须在 1–50 之间")
    if max_n < 0 or max_n > 200:
        raise ValueError("公告最多展示条数须在 0–200 之间（0 表示不限制）")

    return AnnouncementQueryOptions(
        lookback_days=lookback,
        max_count=max_n,
        fallback_latest_count=latest_n,
        end_date=on_date or date.today(),
    )


def _row_dict(row: dict) -> dict[str, str]:
    return {
        "title": row.get("title", ""),
        "pub_date": row.get("pub_date", ""),
        "pub_time": row.get("pub_time", ""),
        "source": row.get("source", ""),
        "url": row.get("url", ""),
        "provider": row.get("provider", ""),
        "extra": row.get("extra", ""),
    }


def resolve_query_stocks(codes: list[str]) -> list[StockItem]:
    """按代码查：在自选里的保留分组/名称，不在自选的也可查。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = normalize_code(str(raw).strip())
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    if not normalized:
        return []

    wl_map = watchlist_by_code()
    stocks: list[StockItem] = []
    for code in normalized:
        if code in wl_map:
            stocks.append(wl_map[code])
        else:
            stocks.append(StockItem(code=code, name=code, group="", block_id=""))
    return stocks


def query_announcements_for_stock(
    stock: StockItem,
    options: AnnouncementQueryOptions,
) -> dict[str, Any]:
    start = options.end_date - timedelta(days=options.lookback_days)
    fetched = fetch_announcement_rows(
        stock.code,
        start=start,
        end=options.end_date,
        lookback_days=options.lookback_days,
        fallback_latest_count=options.fallback_latest_count,
        max_count=options.max_count,
    )
    return {
        "code": stock.code,
        "name": stock.name,
        "group": stock.group,
        "announcement_count": len(fetched.rows),
        "announcements": [_row_dict(r) for r in fetched.rows],
        "query": {
            "lookback_days": options.lookback_days,
            "max_count": options.max_count,
            "fallback_latest_count": options.fallback_latest_count,
            "end_date": options.end_date.isoformat(),
        },
        "warning": warning_dict(fetched),
        "queried_at": now_iso(),
    }


def query_announcements(
    codes: list[str],
    *,
    options: AnnouncementQueryOptions | None = None,
    days: int | None = None,
    max_count: int | None = None,
    latest: int | None = None,
    on_date: date | None = None,
    save: bool = True,
) -> tuple[list[dict[str, Any]], Path | None]:
    """查公告；默认落盘 data/announcement_query_{日}.json。返回 (items, path|None)。"""
    opts = options or resolve_query_options(
        days=days,
        max_count=max_count,
        latest=latest,
        on_date=on_date,
    )
    stocks = resolve_query_stocks(codes)
    if not stocks:
        return [], None

    workers = _query_workers(len(stocks))
    if workers == 1:
        items = [query_announcements_for_stock(stock, opts) for stock in stocks]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            items = list(pool.map(lambda stock: query_announcements_for_stock(stock, opts), stocks))

    path: Path | None = None
    if save and items:
        from announcement.query_cache import persist_announcement_query

        path = persist_announcement_query(items, opts)
    return items, path
