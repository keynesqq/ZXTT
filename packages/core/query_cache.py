"""即时查询结果 JSON 落盘（按日历日、按代码合并）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from core.config import normalize_code
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR

QUERY_CACHE_SCHEMA_VERSION = 1


def query_cache_path(prefix: str, on_date: date | None = None) -> Path:
    d = on_date or date.today()
    return DATA_DIR / f"{prefix}_{d.isoformat()}.json"


def _load_cache(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("schema_version") or 0) != QUERY_CACHE_SCHEMA_VERSION:
        return None
    return data


def _dedupe_items(items: list[dict], key_fn: Callable[[dict], tuple]) -> list[dict]:
    order: list[tuple] = []
    by_key: dict[tuple, dict] = {}
    for item in items:
        key = key_fn(item)
        if key not in by_key:
            order.append(key)
        by_key[key] = item
    return [by_key[k] for k in order]


def _merge_items(
    base: list[dict],
    updates: list[dict],
    key_fn: Callable[[dict], tuple],
) -> list[dict]:
    out = list(base)
    index = {key_fn(item): i for i, item in enumerate(out)}
    for u in updates:
        key = key_fn(u)
        if key in index:
            out[index[key]] = u
        else:
            out.append(u)
    return out


def write_query_cache(
    prefix: str,
    *,
    payload_key: str,
    items: list[dict],
    query_meta: dict[str, Any],
    on_date: date | None = None,
    extra: dict[str, Any] | None = None,
    merge_key_fn: Callable[[dict], tuple] | None = None,
) -> Path:
    day = on_date or date.today()
    path = query_cache_path(prefix, day)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_cache(path)
    if existing and merge_key_fn and isinstance(existing.get(payload_key), list):
        items = _merge_items(existing[payload_key], items, merge_key_fn)
    if merge_key_fn:
        items = _dedupe_items(items, merge_key_fn)

    payload: dict[str, Any] = {
        "schema_version": QUERY_CACHE_SCHEMA_VERSION,
        "calendar_date": day.isoformat(),
        "updated_at": now_iso(),
        "query": query_meta,
        "count": len(items),
        payload_key: items,
    }
    if extra:
        payload.update(extra)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def code_merge_key(item: dict) -> tuple:
    return (normalize_code(str(item.get("code") or "")),)


def quote_merge_key(item: dict) -> tuple:
    return (normalize_code(str(item.get("code") or "")), str(item.get("group") or ""))
