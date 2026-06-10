"""9:15 指纹对比（只读 evening_baseline）。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from core.paths import DATA_DIR
from feeds.feed_warnings import FEED_COLLECT_FAILED

_FEED_KEYS = ("公告", "资讯", "观点", "研报", "行业资讯")
_EVENING_BASELINE = DATA_DIR / "evening_baseline"


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


def load_evening_baseline(day: date) -> dict[str, Any] | None:
    path = _EVENING_BASELINE / f"{day.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def decide_feeds_status(
    code: str,
    feeds_merged: dict[str, Any],
    *,
    prev_baseline: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any]]:
    ws = feeds_merged.get("warnings_struct") or []
    if any(str(x.get("code_key") or "") == FEED_COLLECT_FAILED for x in ws):
        return "failed", "", {"reason": FEED_COLLECT_FAILED}

    counts = item_counts(feeds_merged)
    if all(v == 0 for v in counts.values()):
        return "no_new", fingerprint_feeds(feeds_merged), {"item_counts": counts}

    fp = fingerprint_feeds(feeds_merged)
    prev_fp = ((prev_baseline or {}).get("codes") or {}).get(code, {}).get("fingerprint")
    meta: dict[str, Any] = {"item_counts": counts}

    if prev_fp is not None and fp != prev_fp:
        meta["prev_fingerprint"] = prev_fp
        return "refresh", fp, meta
    if prev_fp is not None and fp == prev_fp:
        meta["prev_fingerprint"] = prev_fp
        return "reuse", fp, meta
    return "first_run", fp, meta


__all__ = [
    "fingerprint_feeds",
    "decide_feeds_status",
    "load_evening_baseline",
    "item_counts",
]
