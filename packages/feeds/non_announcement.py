"""非公告文字素材：研报 / 资讯 / 观点 / 行业资讯。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from threading import Lock
from typing import Any

from core.context_as_of import now_iso
from feeds.eastmoney import fetch_news as fetch_em_news
from feeds.eastmoney import fetch_research as fetch_em_research
from feeds.feed_classifier import classify_news
from feeds.feed_warnings import (
    IND_EMPTY,
    NEWS_EMPTY,
    NEWS_FILTERED,
    NEWS_STALE,
    RES_EMPTY,
    append_feed_warning,
    feed_warning,
)
from feeds.ths_f10 import fetch_research as fetch_ths_research
from feeds.ths_f10 import fetch_stock_news as fetch_ths_news
from watchlist.ths_blocks import StockItem

CATEGORY_NEWS = "news"
CATEGORY_OPINIONS = "opinions"
CATEGORY_RESEARCH = "research"
CATEGORY_INDUSTRY = "industry"

ALL_CATEGORIES = frozenset(
    {CATEGORY_NEWS, CATEGORY_OPINIONS, CATEGORY_RESEARCH, CATEGORY_INDUSTRY}
)

_CATEGORY_ALIASES = {
    "news": CATEGORY_NEWS,
    "opinion": CATEGORY_OPINIONS,
    "opinions": CATEGORY_OPINIONS,
    "research": CATEGORY_RESEARCH,
    "industry": CATEGORY_INDUSTRY,
    "industry_news": CATEGORY_INDUSTRY,
}


@dataclass(frozen=True)
class NonAnnouncementOptions:
    end_date: date
    cfg: dict[str, Any]
    unified_lookback_days: int | None = None
    max_count: int = 0
    categories: frozenset[str] = ALL_CATEGORIES
    industry_enabled: bool = True
    strict: bool = False
    industry_news_cache: dict[str, list[Any]] | None = None
    industry_cache_lock: Lock | None = None


@dataclass
class NonAnnouncementResult:
    news: list[Any] = field(default_factory=list)
    opinions: list[Any] = field(default_factory=list)
    research: list[Any] = field(default_factory=list)
    industry_news: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    warnings_struct: list[dict[str, Any]] = field(default_factory=list)


def parse_categories(raw: str | None) -> frozenset[str]:
    if not raw or not str(raw).strip():
        return ALL_CATEGORIES
    out: set[str] = set()
    for part in str(raw).split(","):
        key = part.strip().lower()
        if not key:
            continue
        canonical = _CATEGORY_ALIASES.get(key)
        if canonical is None:
            allowed = ", ".join(sorted(ALL_CATEGORIES | {"industry"}))
            raise ValueError(f"未知类别 {part!r}，可选：{allowed}")
        out.add(canonical)
    if not out:
        return ALL_CATEGORIES
    return frozenset(out)


def _lookback_days(cfg: dict, key: str, default: int, unified: int | None) -> int:
    if unified is not None:
        return unified
    block = cfg.get(key) or {}
    return int(block.get("lookback_days", default))


def _ths_f10_enabled(cfg: dict) -> bool:
    f10 = cfg.get("ths_f10") or {}
    return bool(f10.get("enabled", True))


def _on_empty(cfg: dict) -> bool:
    f10 = cfg.get("ths_f10") or {}
    return str(f10.get("trigger", "on_empty")).lower() == "on_empty"


def _akshare_timeout_sec(cfg: dict) -> float | None:
    raw = cfg.get("akshare_timeout_sec")
    if raw is None:
        return None
    try:
        return max(5.0, float(raw))
    except (TypeError, ValueError):
        return None


def _to_feed(category: str, row: dict) -> Any:
    from feeds.collect import FeedItem

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


def _apply_max_count(items: list[Any], max_count: int) -> list[Any]:
    if max_count > 0 and len(items) > max_count:
        return items[:max_count]
    return items


@dataclass
class _NewsOpinionFetch:
    news: list[Any]
    opinions: list[Any]
    rows: list[dict]
    used_fallback: bool
    start: date
    days: int


def _fetch_news_and_opinion(
    stock: StockItem,
    end: date,
    days: int,
    cfg: dict,
    *,
    strict: bool = False,
) -> _NewsOpinionFetch:
    code = stock.code
    name = stock.name
    start = end - timedelta(days=days)
    timeout = _akshare_timeout_sec(cfg)
    rows = fetch_em_news(code, start, end, name=name, timeout_sec=timeout, strict=strict)
    used_fallback = False
    if not strict and not rows and _ths_f10_enabled(cfg) and _on_empty(cfg):
        rows = fetch_ths_news(code, start, end, name=name)
        used_fallback = bool(rows)
    opinion_cfg = cfg.get("opinion") or {}
    news: list[Any] = []
    opinions: list[Any] = []
    for row in rows:
        cat = classify_news(row.get("title", ""), row.get("source", ""), opinion_cfg=opinion_cfg)
        item = _to_feed(cat, row)
        if cat == "观点":
            opinions.append(item)
        else:
            news.append(item)
    return _NewsOpinionFetch(
        news=news,
        opinions=opinions,
        rows=rows,
        used_fallback=used_fallback,
        start=start,
        days=days,
    )


def _warn_news_opinion_after_filter(
    stock: StockItem,
    categories: frozenset[str],
    news: list[Any],
    opinions: list[Any],
    fetched: _NewsOpinionFetch,
    warnings: list[str],
    warnings_struct: list[dict[str, Any]],
    *,
    strict: bool = False,
) -> None:
    want_news = CATEGORY_NEWS in categories
    want_opinions = CATEGORY_OPINIONS in categories
    if not want_news and not want_opinions:
        return

    code = stock.code
    days = fetched.days
    start = fetched.start
    news_missing = want_news and not news
    opinions_missing = want_opinions and not opinions

    if news_missing and opinions_missing:
        if fetched.used_fallback:
            msg = f"资讯/观点：近{days}日无数据（已跳过无效的同花顺快讯）"
            key = NEWS_FILTERED
        else:
            msg = f"资讯/观点：近{days}日无数据"
            key = NEWS_EMPTY
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(key, msg, category="资讯", code=code, group=stock.group),
        )
        return

    if news_missing:
        msg = f"资讯：近{days}日无数据"
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(NEWS_EMPTY, msg, category="资讯", code=code, group=stock.group),
        )
    if opinions_missing:
        msg = f"观点：近{days}日无数据"
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(NEWS_EMPTY, msg, category="观点", code=code, group=stock.group),
        )

    shown: list[Any] = []
    if want_news:
        shown.extend(news)
    if want_opinions:
        shown.extend(opinions)
    if (
        not strict
        and fetched.rows
        and shown
        and any(item.pub_date < start.isoformat() for item in shown)
    ):
        msg = f"资讯/观点：近{days}日内无新稿，已展示最近相关条目"
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(NEWS_STALE, msg, category="资讯", code=code, group=stock.group),
        )


def _collect_research(
    stock: StockItem,
    end: date,
    days: int,
    cfg: dict,
    warnings: list[str],
    warnings_struct: list[dict[str, Any]],
) -> list[Any]:
    code = stock.code
    start = end - timedelta(days=days)
    timeout = _akshare_timeout_sec(cfg)
    rows = fetch_em_research(code, start, end, timeout_sec=timeout)
    if not rows and _ths_f10_enabled(cfg) and _on_empty(cfg):
        rows = fetch_ths_research(code, start, end)
    if not rows:
        msg = f"研报：近{days}日无数据"
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(RES_EMPTY, msg, category="研报", code=code, group=stock.group),
        )
    return [_to_feed("研报", r) for r in rows]


def _collect_industry(
    stock: StockItem,
    industry: str,
    end: date,
    days: int,
    cfg: dict,
    warnings: list[str],
    warnings_struct: list[dict[str, Any]],
    *,
    strict: bool = False,
    industry_news_cache: dict[str, list[Any]] | None = None,
    industry_cache_lock: Lock | None = None,
) -> list[Any]:
    if not industry:
        return []
    start = end - timedelta(days=days)
    timeout = _akshare_timeout_sec(cfg)

    def _warn_empty() -> None:
        msg = f"行业资讯（{industry}）：近{days}日无数据"
        append_feed_warning(
            warnings,
            warnings_struct,
            feed_warning(IND_EMPTY, msg, category="行业资讯", code=stock.code, group=stock.group),
        )

    if industry_news_cache is not None:
        lock = industry_cache_lock
        if lock is not None:
            with lock:
                if industry in industry_news_cache:
                    items = list(industry_news_cache[industry])
                    if not items:
                        _warn_empty()
                    return items
        elif industry in industry_news_cache:
            items = list(industry_news_cache[industry])
            if not items:
                _warn_empty()
            return items

    rows = fetch_em_news(industry, start, end, timeout_sec=timeout, strict=strict)
    items = [_to_feed("行业资讯", r) for r in rows]

    if industry_news_cache is not None:
        lock = industry_cache_lock
        if lock is not None:
            with lock:
                if industry not in industry_news_cache:
                    industry_news_cache[industry] = items
                items = list(industry_news_cache[industry])
        else:
            industry_news_cache[industry] = items

    if not items:
        _warn_empty()
    return list(items)


def collect_non_announcement(
    stock: StockItem,
    *,
    industry: str,
    options: NonAnnouncementOptions,
) -> NonAnnouncementResult:
    cfg = options.cfg
    unified = options.unified_lookback_days
    max_count = int(options.max_count or 0)
    categories = options.categories
    warnings: list[str] = []
    warnings_struct: list[dict[str, Any]] = []

    research: list[Any] = []
    news: list[Any] = []
    opinions: list[Any] = []
    industry_news: list[Any] = []
    fetched: _NewsOpinionFetch | None = None

    want_news = CATEGORY_NEWS in categories or CATEGORY_OPINIONS in categories
    want_industry = (
        CATEGORY_INDUSTRY in categories
        and options.industry_enabled
        and bool(industry)
    )
    want_research = CATEGORY_RESEARCH in categories

    branch_count = sum((want_research, want_news, want_industry))
    if branch_count == 0:
        return NonAnnouncementResult()

    def _run_research() -> tuple[list[Any], list[str], list[dict[str, Any]]]:
        w: list[str] = []
        ws: list[dict[str, Any]] = []
        days = _lookback_days(cfg, "research", 7, unified)
        items = _collect_research(stock, options.end_date, days, cfg, w, ws)
        return items, w, ws

    def _run_news_opinion() -> tuple[
        list[Any],
        list[Any],
        _NewsOpinionFetch,
        list[str],
        list[dict[str, Any]],
    ]:
        w: list[str] = []
        ws: list[dict[str, Any]] = []
        days = _lookback_days(cfg, "news", 7, unified)
        got = _fetch_news_and_opinion(
            stock, options.end_date, days, cfg, strict=options.strict
        )
        branch_news = list(got.news)
        branch_opinions = list(got.opinions)
        if CATEGORY_NEWS not in categories:
            branch_news = []
        if CATEGORY_OPINIONS not in categories:
            branch_opinions = []
        _warn_news_opinion_after_filter(
            stock,
            categories,
            branch_news,
            branch_opinions,
            got,
            w,
            ws,
            strict=options.strict,
        )
        return branch_news, branch_opinions, got, w, ws

    def _run_industry() -> tuple[list[Any], list[str], list[dict[str, Any]]]:
        w: list[str] = []
        ws: list[dict[str, Any]] = []
        days = _lookback_days(cfg, "industry_news", 7, unified)
        items = _collect_industry(
            stock,
            industry,
            options.end_date,
            days,
            cfg,
            w,
            ws,
            strict=options.strict,
            industry_news_cache=options.industry_news_cache,
            industry_cache_lock=options.industry_cache_lock,
        )
        return items, w, ws

    def _apply_branch(
        items: list[Any],
        branch_warnings: list[str],
        branch_warnings_struct: list[dict[str, Any]],
    ) -> None:
        warnings.extend(branch_warnings)
        warnings_struct.extend(branch_warnings_struct)

    if branch_count == 1:
        if want_research:
            research, rw, rws = _run_research()
            _apply_branch(research, rw, rws)
        elif want_news:
            news, opinions, fetched, nw, nws = _run_news_opinion()
            _apply_branch([], nw, nws)
        else:
            industry_news, iw, iws = _run_industry()
            _apply_branch(industry_news, iw, iws)
    else:
        with ThreadPoolExecutor(max_workers=branch_count) as pool:
            futures: list[tuple[str, Any]] = []
            if want_research:
                futures.append(("research", pool.submit(_run_research)))
            if want_news:
                futures.append(("news", pool.submit(_run_news_opinion)))
            if want_industry:
                futures.append(("industry", pool.submit(_run_industry)))
            for kind, fut in futures:
                if kind == "research":
                    research, rw, rws = fut.result()
                    _apply_branch(research, rw, rws)
                elif kind == "news":
                    news, opinions, fetched, nw, nws = fut.result()
                    _apply_branch([], nw, nws)
                else:
                    industry_news, iw, iws = fut.result()
                    _apply_branch(industry_news, iw, iws)

    return NonAnnouncementResult(
        news=_apply_max_count(news, max_count),
        opinions=_apply_max_count(opinions, max_count),
        research=_apply_max_count(research, max_count),
        industry_news=_apply_max_count(industry_news, max_count),
        warnings=warnings,
        warnings_struct=warnings_struct,
    )
