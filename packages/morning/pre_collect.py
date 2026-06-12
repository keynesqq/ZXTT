"""9:15 采集档：31 只公告+资讯 + 指纹三态。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from announcement.query import query_announcements, resolve_query_options
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import is_trading_day, previous_trading_day
from morning.codes import codes_from_quote
from morning.feeds_fingerprint import decide_feeds_status, load_evening_baseline
from morning.feeds_merge import merge_feeds, new_titles
from news.query import query_news, resolve_query_options as news_resolve_options
from watchlist.ths_blocks import StockItem

_PRE_DIR = DATA_DIR / "morning_pre"


def _ann_row_for_code(items: list[dict], code: str) -> dict | None:
    for row in items:
        if str(row.get("code") or "").zfill(6) == code:
            return row
    return None


def _news_row_for_code(items: list[dict], code: str) -> dict | None:
    for row in items:
        if str(row.get("code") or "").zfill(6) == code:
            return row
    return None


def run_morning_pre(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    t0 = time.monotonic()
    cal = on_date or date.today()
    if not force and not is_trading_day(cal):
        return {"outcome": "skip", "reason": "not_trading_day", "calendar_date": cal.isoformat()}

    codes, code_src = codes_from_quote(cal)
    if not codes:
        return {
            "outcome": "error",
            "reason": "no_codes",
            "message": "需要 quote_query 或 watchlist",
        }

    prev_td = previous_trading_day(cal)
    prev_baseline = load_evening_baseline(prev_td) if prev_td else None

    ann_opts = resolve_query_options(on_date=cal)
    news_opts = news_resolve_options(on_date=cal)
    stocks = [StockItem(code=c, name=c, group="", block_id="") for c in codes]
    ann_items, _ = query_announcements(codes, options=ann_opts)
    news_items, _ = query_news(codes, options=news_opts)

    by_code: dict[str, Any] = {}
    summary = {"refresh": 0, "reuse": 0, "no_new": 0, "failed": 0, "first_run": 0}

    for code in codes:
        ann_row = _ann_row_for_code(ann_items, code)
        news_row = _news_row_for_code(news_items, code)
        merged = merge_feeds(ann_row, news_row)
        status, fp, meta = decide_feeds_status(code, merged, prev_baseline=prev_baseline)
        summary[status] = summary.get(status, 0) + 1
        titles = new_titles(merged) if status == "refresh" else []
        by_code[code] = {
            "status": status,
            "fingerprint": fp,
            "item_counts": meta.get("item_counts") or {},
            "new_titles": titles,
        }

    payload = {
        "schema_version": 1,
        "slot": "morning",
        "phase": "pre",
        "session_label": "集合竞价前采集",
        "calendar_date": cal.isoformat(),
        "finished_at": now_iso(),
        "code_count": len(codes),
        "code_source": code_src,
        "source_paths": {
            "quote": code_src if str(code_src).startswith("data/") else f"data/quote_query_{cal.isoformat()}.json",
            "announcement": f"data/announcement_query_{cal.isoformat()}.json",
            "news": f"data/news_query_{cal.isoformat()}.json",
        },
        "prev_baseline_date": prev_td.isoformat() if prev_td else "",
        "by_code": by_code,
        "summary": summary,
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }
    _PRE_DIR.mkdir(parents=True, exist_ok=True)
    path = _PRE_DIR / f"{cal.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return {"outcome": "ok", "path": str(path), **payload}


__all__ = ["run_morning_pre"]
