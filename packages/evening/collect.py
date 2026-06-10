"""第 2 步 · 晚间事实采集编排（7 模块，无竞价）。"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from announcement.query import query_announcements
from core.config import market_cfg, normalize_code
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR, ROOT
from core.trading_calendar import is_trading_day, market_data_date
from market.cls import collect_cls
from market.flow_snapshot import collect_market_flow
from market.index_snapshot import collect_market_index
from market.sentiment import collect_market_sentiment
from news.query import query_news
from quote.query import query_quotes
from quote.query_cache import load_quote_query_cache, quote_query_cache_path

_MANIFEST_DIR = DATA_DIR / "collect_manifest"
_SLOT = "evening"


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _codes_from_quote(day: date) -> tuple[list[str], int, int]:
    data = load_quote_query_cache(on_date=day)
    if not data:
        return [], 0, 0
    codes: list[str] = []
    seen: set[str] = set()
    for row in data.get("quotes") or []:
        code = normalize_code(str(row.get("code") or ""))
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes, int(data.get("code_count") or len(codes)), int(data.get("row_count") or 0)


def _quote_status(day: date, *, fetched: bool, error: str | None = None) -> dict[str, Any]:
    path = quote_query_cache_path(day)
    if error:
        return {"status": "fail", "path": _rel(path), "message": error}
    if not path.is_file():
        return {"status": "fail", "path": _rel(path), "message": "quote_query_missing"}
    data = load_quote_query_cache(on_date=day) or {}
    code_count = int(data.get("code_count") or 0)
    row_count = int(data.get("row_count") or 0)
    if code_count <= 0:
        return {"status": "fail", "path": _rel(path), "message": "code_count_zero"}
    status = "ok" if fetched or path.is_file() else "warn"
    return {
        "status": status,
        "path": _rel(path),
        "code_count": code_count,
        "row_count": row_count,
    }


def _items_status(
    path: Path | None,
    items: list[dict],
    *,
    item_key: str = "item_count",
) -> dict[str, Any]:
    rel = _rel(path) if path else ""
    if not path or not path.is_file():
        return {"status": "fail", "path": rel, "message": "file_missing"}
    return {"status": "ok", "path": rel, item_key: len(items)}


def _market_sentiment_status(day: date, *, force: bool) -> dict[str, Any]:
    if not market_cfg().get("enabled", True):
        path = DATA_DIR / "market_sentiment" / f"{day.isoformat()}.json"
        return {"status": "skip", "path": _rel(path), "message": "market_disabled"}
    try:
        collect_market_sentiment(day, calendar_date=day)
    except Exception as e:
        path = DATA_DIR / "market_sentiment" / f"{day.isoformat()}.json"
        return {"status": "fail", "path": _rel(path), "message": str(e)}
    path = DATA_DIR / "market_sentiment" / f"{day.isoformat()}.json"
    if not path.is_file():
        return {"status": "fail", "path": _rel(path), "message": "file_missing"}
    return {"status": "ok", "path": _rel(path)}


def _index_status(day: date, *, force: bool) -> dict[str, Any]:
    try:
        data = collect_market_index(calendar_date=day, slot=_SLOT)
    except Exception as e:
        path = DATA_DIR / "market_index" / f"{day.isoformat()}.json"
        return {"status": "fail", "path": _rel(path), "message": str(e)}
    path = DATA_DIR / "market_index" / f"{day.isoformat()}.json"
    indices = data.get("indices") or []
    status = "ok" if indices else "warn"
    return {
        "status": status,
        "path": _rel(path),
        "latest_slot": data.get("latest_slot"),
        "index_count": len(indices),
        "message": None if indices else "indices_empty",
    }


def _flow_status(day: date, *, force: bool) -> dict[str, Any]:
    try:
        data = collect_market_flow(calendar_date=day, slot=_SLOT)
    except Exception as e:
        path = DATA_DIR / "market_flow" / f"{day.isoformat()}.json"
        return {"status": "fail", "path": _rel(path), "message": str(e)}
    if data.get("outcome") == "skip":
        return {"status": "skip", "path": data.get("path", ""), "message": data.get("message")}
    path = Path(str(data.get("path") or DATA_DIR / "market_flow" / f"{day.isoformat()}.json"))
    north = data.get("northbound") or {}
    market_row = data.get("market") or {}
    ok = north.get("net_yi") is not None or market_row.get("main_net_yi") is not None
    rec: dict[str, Any] = {
        "status": "ok" if ok else "warn",
        "path": _rel(path),
        "latest_slot": data.get("latest_slot"),
        "watchlist_count": len(data.get("watchlist_flow") or []),
    }
    if not ok:
        rec["message"] = "market_main_net_failed"
    return rec


def _cls_finance_status(day: date, *, force: bool) -> dict[str, Any]:
    if not market_cfg().get("cls_enabled", True):
        path = DATA_DIR / "cls_finance" / f"{day.isoformat()}.json"
        return {"status": "skip", "path": _rel(path), "message": "cls_disabled"}
    try:
        data = collect_cls(day, include_articles=False, force=force, calendar_date=day)
    except Exception as e:
        path = DATA_DIR / "cls_finance" / f"{day.isoformat()}.json"
        return {"status": "fail", "path": _rel(path), "message": str(e)}
    path = DATA_DIR / "cls_finance" / f"{day.isoformat()}.json"
    status = "ok" if data.get("layer_a_ok") else "warn"
    return {"status": status, "path": _rel(path)}


def _cls_articles_status(day: date, *, force: bool) -> dict[str, Any]:
    if not market_cfg().get("cls_articles_enabled", True):
        path = DATA_DIR / "cls_articles" / f"{day.isoformat()}.json"
        return {"status": "skip", "path": _rel(path), "message": "cls_articles_disabled"}
    try:
        data = collect_cls(day, include_articles=True, force=force, calendar_date=day)
    except Exception as e:
        path = DATA_DIR / "cls_articles" / f"{day.isoformat()}.json"
        return {"status": "fail", "path": _rel(path), "message": str(e)}
    path = DATA_DIR / "cls_articles" / f"{day.isoformat()}.json"
    found = int(data.get("articles_found") or 0)
    expected = int(data.get("articles_expected") or 0)
    ok = bool(data.get("articles_ok"))
    rec: dict[str, Any] = {
        "status": "ok" if ok else "warn",
        "path": _rel(path),
        "articles_found": found,
        "articles_expected": expected,
    }
    if not ok and expected:
        rec["message"] = f"cls_incomplete_{found}_{expected}"
    return rec


def _aggregate_overall(sources: dict[str, dict[str, Any]]) -> str:
    quote = sources.get("quote_query") or {}
    if quote.get("status") == "fail":
        return "fail"
    for rec in sources.values():
        if rec.get("status") == "fail":
            return "fail"
    for rec in sources.values():
        if rec.get("status") == "warn":
            return "warn"
    return "ok"


def _collect_warnings(sources: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    flow = sources.get("market_flow") or {}
    if flow.get("status") == "warn" and flow.get("message") == "market_main_net_failed":
        warnings.append("FLOW_L1_FAIL")
    cls_art = sources.get("cls_articles") or {}
    found = cls_art.get("articles_found")
    expected = cls_art.get("articles_expected")
    if isinstance(found, int) and isinstance(expected, int) and expected and found < expected:
        warnings.append(f"CLS_INCOMPLETE_{found}_{expected}")
    return warnings


def _write_manifest(payload: dict[str, Any], day: date) -> Path:
    path = _MANIFEST_DIR / f"{day.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def run_collect_evening(
    *,
    on_date: date | None = None,
    force: bool = False,
    skip_network: bool = False,
) -> dict[str, Any]:
    """编排 7 路采集并写 collect_manifest。quote 失败则阻断。"""
    t0 = time.monotonic()
    cal = on_date or date.today()
    if not force and not is_trading_day(cal):
        return {
            "outcome": "fail",
            "reason": "not_trading_day",
            "calendar_date": cal.isoformat(),
            "overall": "fail",
        }

    trade = market_data_date(cal)
    sources: dict[str, Any] = {}
    warnings: list[str] = []

    # 1 quote
    quote_path = quote_query_cache_path(cal)
    quote_fetched = False
    quote_error: str | None = None
    if not quote_path.is_file():
        if skip_network:
            quote_error = "quote_query_missing"
        else:
            try:
                _, path, meta = query_quotes(all_watchlist=True, on_date=cal)
                quote_fetched = path is not None and int(meta.get("code_count") or 0) > 0
                if not quote_fetched:
                    quote_error = "quote_fetch_empty"
            except Exception as e:
                quote_error = str(e)
    sources["quote_query"] = _quote_status(cal, fetched=quote_fetched, error=quote_error)
    if sources["quote_query"]["status"] == "fail":
        payload = {
            "schema_version": 1,
            "slot": _SLOT,
            "trade_date": trade.isoformat(),
            "calendar_date": cal.isoformat(),
            "collected_at_iso": now_iso(),
            "code_count": 0,
            "row_count": 0,
            "overall": "fail",
            "sources": sources,
            "warnings": [],
        }
        manifest_path = _write_manifest(payload, cal)
        return {
            "outcome": "fail",
            "reason": "quote_failed",
            "overall": "fail",
            "manifest_path": _rel(manifest_path),
            "sources": sources,
        }

    codes, code_count, row_count = _codes_from_quote(cal)

    # 2–3 feeds（可并行）
    ann_rec: dict[str, Any] = {"status": "fail", "path": "", "message": "not_run"}
    news_rec: dict[str, Any] = {"status": "fail", "path": "", "message": "not_run"}

    if skip_network:
        ann_path = DATA_DIR / f"announcement_query_{cal.isoformat()}.json"
        news_path = DATA_DIR / f"news_query_{cal.isoformat()}.json"
        ann_rec = (
            {"status": "ok", "path": _rel(ann_path), "item_count": 0}
            if ann_path.is_file()
            else {"status": "warn", "path": _rel(ann_path), "message": "file_missing"}
        )
        news_rec = (
            {"status": "ok", "path": _rel(news_path), "item_count": 0}
            if news_path.is_file()
            else {"status": "warn", "path": _rel(news_path), "message": "file_missing"}
        )
    else:

        def _run_ann() -> tuple[list[dict], Path | None]:
            return query_announcements(codes, on_date=cal)

        def _run_news() -> tuple[list[dict], Path | None]:
            return query_news(codes, on_date=cal)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_ann = pool.submit(_run_ann)
                fut_news = pool.submit(_run_news)
                ann_items, ann_path = fut_ann.result()
                news_items, news_path = fut_news.result()
            ann_rec = _items_status(ann_path, ann_items)
            news_rec = _items_status(news_path, news_items)
        except Exception as e:
            ann_rec = {"status": "warn", "path": "", "message": str(e)}
            news_rec = {"status": "warn", "path": "", "message": str(e)}

    sources["announcement_query"] = ann_rec
    sources["news_query"] = news_rec

    # 4–7 market
    if skip_network:
        for name, subpath in (
            ("market_sentiment", f"market_sentiment/{trade.isoformat()}.json"),
            ("market_index", f"market_index/{trade.isoformat()}.json"),
            ("market_flow", f"market_flow/{trade.isoformat()}.json"),
            ("cls_finance", f"cls_finance/{trade.isoformat()}.json"),
            ("cls_articles", f"cls_articles/{trade.isoformat()}.json"),
        ):
            p = DATA_DIR / subpath
            sources[name] = (
                {"status": "ok", "path": _rel(p)}
                if p.is_file()
                else {"status": "warn", "path": _rel(p), "message": "file_missing"}
            )
    else:
        market_jobs = {
            "market_sentiment": lambda: _market_sentiment_status(trade, force=force),
            "market_index": lambda: _index_status(cal, force=force),
            "market_flow": lambda: _flow_status(cal, force=force),
            "cls_finance": lambda: _cls_finance_status(trade, force=force),
            "cls_articles": lambda: _cls_articles_status(trade, force=force),
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(fn): name for name, fn in market_jobs.items()}
            for fut in as_completed(futs):
                sources[futs[fut]] = fut.result()

    overall = _aggregate_overall(sources)
    warnings = _collect_warnings(sources)
    duration_ms = int((time.monotonic() - t0) * 1000)
    payload = {
        "schema_version": 1,
        "slot": _SLOT,
        "trade_date": trade.isoformat(),
        "calendar_date": cal.isoformat(),
        "collected_at_iso": now_iso(),
        "duration_ms": duration_ms,
        "code_count": code_count,
        "row_count": row_count,
        "overall": overall,
        "sources": sources,
        "warnings": warnings,
    }
    manifest_path = _write_manifest(payload, cal)
    return {
        "outcome": "ok" if overall != "fail" else "fail",
        "overall": overall,
        "trade_date": trade.isoformat(),
        "calendar_date": cal.isoformat(),
        "code_count": code_count,
        "row_count": row_count,
        "manifest_path": _rel(manifest_path),
        "duration_ms": duration_ms,
        "sources": sources,
        "warnings": warnings,
    }


__all__ = ["run_collect_evening"]
