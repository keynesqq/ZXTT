"""第 3 步 3.6A · feeds 指纹与 baseline（午间独立目录）。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import previous_trading_day
from feeds.feed_warnings import FEED_COLLECT_FAILED

_FEED_KEYS = ("公告", "资讯", "观点", "研报", "行业资讯")
_BASELINE_DIR = DATA_DIR / "midday_baseline"


def normalize_title(title: str) -> str:
    s = (title or "").strip().replace("\u3000", " ")
    return re.sub(r"\s+", " ", s)


def fingerprint_feeds(feeds_merged: dict[str, Any]) -> str:
    items: list[dict[str, str]] = []
    for cat in _FEED_KEYS:
        for row in feeds_merged.get(cat) or []:
            items.append(
                {
                    "category": cat,
                    "title": normalize_title(str(row.get("title") or "")),
                    "pub_date": str(row.get("pub_date") or ""),
                }
            )
    items.sort(key=lambda x: (x["category"], x["pub_date"], x["title"]))
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def item_counts(feeds_merged: dict[str, Any]) -> dict[str, int]:
    return {cat: len(feeds_merged.get(cat) or []) for cat in _FEED_KEYS}


def load_baseline(day: date) -> dict[str, Any] | None:
    path = _BASELINE_DIR / f"{day.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_baseline(payload: dict[str, Any], day: date) -> Path:
    path = _BASELINE_DIR / f"{day.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def decide_feeds_status(
    code: str,
    feeds_merged: dict[str, Any],
    *,
    trade_date: date,
    today_baseline: dict[str, Any] | None,
    prev_baseline: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any]]:
    ws = feeds_merged.get("warnings_struct") or []
    if any(str(x.get("code_key") or "") == FEED_COLLECT_FAILED for x in ws):
        return "failed", "", {"reason": FEED_COLLECT_FAILED}

    counts = item_counts(feeds_merged)
    if all(v == 0 for v in counts.values()):
        return "empty", fingerprint_feeds(feeds_merged), {"item_counts": counts}

    fp = fingerprint_feeds(feeds_merged)
    prev_fp = ((prev_baseline or {}).get("codes") or {}).get(code, {}).get("fingerprint")
    today_fp = ((today_baseline or {}).get("codes") or {}).get(code, {}).get("fingerprint")
    meta: dict[str, Any] = {"item_counts": counts}

    if prev_fp is not None and fp != prev_fp:
        meta["prev_fingerprint"] = prev_fp
        return "refresh", fp, meta
    if today_fp and fp != today_fp:
        meta["prev_fingerprint"] = today_fp
        return "refresh", fp, meta
    if prev_fp is not None and fp == prev_fp:
        meta["prev_fingerprint"] = prev_fp
        return "reuse", fp, meta
    if today_fp and fp == today_fp:
        meta["prev_fingerprint"] = today_fp
        return "reuse", fp, meta
    return "first_run", fp, meta


def diff_vs_baseline(
    feeds_merged: dict[str, Any],
    *,
    prev_fp: str | None,
    curr_fp: str,
) -> dict[str, Any]:
    del feeds_merged
    return {
        "unchanged": prev_fp == curr_fp if prev_fp else False,
        "new_items": [] if prev_fp == curr_fp else ["fingerprint_changed"],
        "removed_items": [],
    }


def baseline_for_day(trade_date: date) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prev_day = previous_trading_day(trade_date)
    prev = load_baseline(prev_day) if prev_day else None
    today = load_baseline(trade_date)
    return prev, today


def update_baseline_entry(
    baseline: dict[str, Any],
    code: str,
    *,
    fingerprint: str,
    item_counts_map: dict[str, int],
    digest_trade_date: str,
    source_id: str,
) -> None:
    baseline.setdefault("codes", {})[code] = {
        "fingerprint": fingerprint,
        "item_counts": item_counts_map,
        "last_digest_trade_date": digest_trade_date,
        "last_digest_source_id": source_id,
        "updated_at": now_iso(),
    }


__all__ = [
    "fingerprint_feeds",
    "decide_feeds_status",
    "diff_vs_baseline",
    "load_baseline",
    "save_baseline",
    "baseline_for_day",
    "update_baseline_entry",
    "item_counts",
]
