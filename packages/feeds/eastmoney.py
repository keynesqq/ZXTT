"""东方财富数据（经 AkShare）。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from datetime import date, timedelta
from threading import Lock
from typing import Any, Callable, Iterator, TypeVar

import pandas as pd

from core.config import feeds_cfg, normalize_code
from feeds.news_filter import filter_news_rows

T = TypeVar("T")
_DEFAULT_AKSHARE_TIMEOUT_SEC = 45.0
_akshare_progress_lock = Lock()
_akshare_progress_depth = 0
_akshare_progress_patched: list[tuple[Any, str, Callable[..., Any]]] = []


def _noop_tqdm_factory(enable: bool = True) -> Callable[..., Any]:
    return lambda iterable, *a, **k: iterable


def _patch_akshare_get_tqdm() -> None:
    try:
        import sys

        import akshare.utils.tqdm as ak_tqdm
    except ImportError:
        return

    original = ak_tqdm.get_tqdm
    ak_tqdm.get_tqdm = _noop_tqdm_factory
    _akshare_progress_patched.append((ak_tqdm, "get_tqdm", original))
    for mod in sys.modules.values():
        if mod is None:
            continue
        if getattr(mod, "get_tqdm", None) is original:
            mod.get_tqdm = _noop_tqdm_factory  # type: ignore[attr-defined]
            _akshare_progress_patched.append((mod, "get_tqdm", original))


def _restore_akshare_get_tqdm() -> None:
    seen: set[tuple[Any, str]] = set()
    for mod, attr, original in reversed(_akshare_progress_patched):
        key = (mod, attr)
        if key in seen:
            continue
        seen.add(key)
        setattr(mod, attr, original)
    _akshare_progress_patched.clear()


def _akshare_timeout_sec() -> float:
    cfg = feeds_cfg()
    try:
        return max(5.0, float(cfg.get("akshare_timeout_sec") or _DEFAULT_AKSHARE_TIMEOUT_SEC))
    except (TypeError, ValueError):
        return _DEFAULT_AKSHARE_TIMEOUT_SEC


@contextmanager
def _suppress_akshare_progress() -> Iterator[None]:
    """研报等接口会刷 tqdm 进度条，批量 query 时静默（引用计数，支持并发 call）。"""
    global _akshare_progress_depth
    with _akshare_progress_lock:
        if _akshare_progress_depth == 0:
            _patch_akshare_get_tqdm()
        _akshare_progress_depth += 1
    try:
        yield
    finally:
        with _akshare_progress_lock:
            _akshare_progress_depth -= 1
            if _akshare_progress_depth == 0:
                _restore_akshare_get_tqdm()


def call_akshare(
    fn: Callable[..., T],
    /,
    *args: Any,
    timeout_sec: float | None = None,
    **kwargs: Any,
) -> T | None:
    """AkShare 无内置超时，用线程池限时避免资讯采集 worker 永久阻塞。"""
    timeout = max(5.0, float(timeout_sec)) if timeout_sec is not None else _akshare_timeout_sec()
    with _suppress_akshare_progress(), ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeoutError:
            return None


def _date_str(d: date) -> str:
    return d.strftime("%Y%m%d")


def get_industry(code: str) -> str:
    c = normalize_code(code)
    try:
        import akshare as ak

        df = call_akshare(ak.stock_individual_info_em, symbol=c)
        if df is None or df.empty:
            return ""
        item_col = "item" if "item" in df.columns else df.columns[0]
        val_col = "value" if "value" in df.columns else df.columns[1]
        row = df[df[item_col].astype(str) == "行业"]
        if not row.empty:
            return str(row.iloc[0][val_col]).strip()
    except Exception:
        pass
    return ""


def fetch_announcements_akshare(code: str, start: date, end: date) -> list[dict]:
    c = normalize_code(code)
    rows: list[dict] = []
    try:
        import akshare as ak

        df = call_akshare(
            ak.stock_zh_a_disclosure_report_cninfo,
            symbol=c,
            market="沪深京",
            start_date=_date_str(start),
            end_date=_date_str(end),
        )
        if df is None or df.empty:
            return rows
        title_col = "公告标题" if "公告标题" in df.columns else df.columns[2]
        date_col = "公告时间" if "公告时间" in df.columns else df.columns[3]
        url_col = "公告链接" if "公告链接" in df.columns else df.columns[4]
        type_col = "公告分类" if "公告分类" in df.columns else None
        for _, row in df.iterrows():
            pub = pd.to_datetime(row[date_col], errors="coerce")
            if pd.isna(pub):
                continue
            pub_d = pub.date()
            if pub_d < start or pub_d > end:
                continue
            rows.append(
                {
                    "pub_date": pub_d.isoformat(),
                    "pub_time": pub.strftime("%H:%M") if hasattr(pub, "strftime") else "",
                    "title": str(row[title_col])[:500],
                    "source": str(row[type_col]) if type_col and type_col in row.index else "公告",
                    "url": str(row[url_col]) if url_col in row.index else "",
                    "provider": "东财",
                }
            )
    except Exception:
        pass
    return rows


def fetch_latest_announcements_akshare(code: str, limit: int = 5) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=3650)
    rows = fetch_announcements_akshare(code, start, end)
    rows.sort(key=lambda r: (r.get("pub_date", ""), r.get("pub_time", "")), reverse=True)
    return rows[: max(1, limit)]


def fetch_news(
    code: str,
    start: date,
    end: date,
    *,
    name: str = "",
    limit: int = 30,
    timeout_sec: float | None = None,
    strict: bool = False,
) -> list[dict]:
    c = normalize_code(code)
    keywords: list[str] = []
    for kw in (name, c):
        kw = (kw or "").strip()
        if kw and kw not in keywords:
            keywords.append(kw)
    if not keywords:
        return []

    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _merge_rows(rows: list[dict]) -> None:
        for row in rows:
            key = (row.get("title", ""), row.get("pub_date", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)

    if len(keywords) == 1:
        _merge_rows(_fetch_news_em(keywords[0], limit=limit * 2, timeout_sec=timeout_sec))
    else:
        with ThreadPoolExecutor(max_workers=len(keywords)) as pool:
            for rows in pool.map(
                lambda kw: _fetch_news_em(kw, limit=limit * 2, timeout_sec=timeout_sec),
                keywords,
            ):
                _merge_rows(rows)

    merged = filter_news_rows(merged, c, name)
    in_range = [r for r in merged if start <= _parse_row_date(r) <= end]
    if in_range:
        return in_range[:limit]
    if strict:
        return []

    recent = sorted(merged, key=lambda r: (r.get("pub_date", ""), r.get("pub_time", "")), reverse=True)
    return recent[: min(limit, 10)]


def _parse_row_date(row: dict) -> date:
    try:
        return date.fromisoformat(str(row.get("pub_date", ""))[:10])
    except ValueError:
        return date.min


def _fetch_news_em(keyword: str, *, limit: int = 30, timeout_sec: float | None = None) -> list[dict]:
    if not keyword:
        return []
    rows: list[dict] = []
    try:
        import akshare as ak

        df = call_akshare(ak.stock_news_em, symbol=keyword, timeout_sec=timeout_sec)
        if df is None or df.empty:
            return rows
        title_col = "新闻标题" if "新闻标题" in df.columns else df.columns[1]
        date_col = "发布时间" if "发布时间" in df.columns else df.columns[3]
        source_col = "文章来源" if "文章来源" in df.columns else df.columns[4]
        url_col = "新闻链接" if "新闻链接" in df.columns else df.columns[5]
        for _, row in df.iterrows():
            pub = pd.to_datetime(row[date_col], errors="coerce")
            if pd.isna(pub):
                continue
            pub_d = pub.date()
            rows.append(
                {
                    "pub_date": pub_d.isoformat(),
                    "pub_time": pub.strftime("%H:%M") if hasattr(pub, "strftime") else "",
                    "title": str(row[title_col])[:500],
                    "source": str(row[source_col]) if source_col in row.index else "",
                    "url": str(row[url_col]) if url_col in row.index else "",
                    "provider": "东财",
                }
            )
            if len(rows) >= limit:
                break
    except Exception:
        pass
    return rows


def fetch_research(
    code: str,
    start: date,
    end: date,
    *,
    timeout_sec: float | None = None,
) -> list[dict]:
    c = normalize_code(code)
    rows: list[dict] = []
    try:
        import akshare as ak

        df = call_akshare(ak.stock_research_report_em, symbol=c, timeout_sec=timeout_sec)
        if df is None or df.empty:
            return rows
        date_col = "日期" if "日期" in df.columns else None
        org_col = "机构" if "机构" in df.columns else None
        title_col = "报告名称" if "报告名称" in df.columns else None
        rating_col = "东财评级" if "东财评级" in df.columns else None
        if not date_col:
            return rows
        for _, row in df.iterrows():
            pub = pd.to_datetime(row[date_col], errors="coerce")
            if pd.isna(pub):
                continue
            pub_d = pub.date()
            if pub_d < start or pub_d > end:
                continue
            rows.append(
                {
                    "pub_date": pub_d.isoformat(),
                    "pub_time": "",
                    "title": str(row[title_col])[:500] if title_col else "",
                    "source": str(row[org_col]) if org_col else "",
                    "url": "",
                    "extra": str(row[rating_col]) if rating_col else "",
                    "provider": "东财",
                }
            )
    except Exception:
        pass
    return rows
