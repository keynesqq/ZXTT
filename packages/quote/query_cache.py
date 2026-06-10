"""quote query 分层落盘：事实 quotes（按 code）+ 结构 memberships/structure（板块归属）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.config import normalize_code
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.query_cache import code_merge_key
from quote.snapshot.cache import structure_from_stocks
from watchlist.ths_blocks import StockItem

PREFIX = "quote_query"
QUOTE_QUERY_SCHEMA_VERSION = 2


def quote_query_cache_path(on_date: date | None = None) -> Path:
    d = on_date or date.today()
    return DATA_DIR / f"{PREFIX}_{d.isoformat()}.json"


def memberships_from_stocks(stocks: list[StockItem]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for s in stocks:
        code = normalize_code(s.code)
        if not code:
            continue
        out.append(
            {
                "code": code,
                "name": (s.name or code).strip() or code,
                "group": str(s.group or "").strip(),
            }
        )
    return out


def _membership_key(row: dict) -> tuple[str, str]:
    return (normalize_code(str(row.get("code") or "")), str(row.get("group") or ""))


def _dedupe_memberships(rows: list[dict]) -> list[dict]:
    order: list[tuple[str, str]] = []
    by_key: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = _membership_key(row)
        if not key[0]:
            continue
        if key not in by_key:
            order.append(key)
        by_key[key] = row
    return [by_key[k] for k in order]


def _merge_quotes(base: list[dict], updates: list[dict]) -> list[dict]:
    index = {code_merge_key(q): i for i, q in enumerate(base)}
    out = list(base)
    for q in updates:
        key = code_merge_key(q)
        if key in index:
            out[index[key]] = q
        else:
            out.append(q)
    return out


def _merge_memberships(
    base: list[dict],
    updates: list[dict],
    *,
    replace_codes: set[str] | None,
) -> list[dict]:
    if replace_codes is None:
        return _dedupe_memberships(updates)
    kept = [m for m in base if normalize_code(str(m.get("code") or "")) not in replace_codes]
    return _dedupe_memberships(kept + updates)


def _load_quote_query_cache(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("schema_version") or 0) != QUOTE_QUERY_SCHEMA_VERSION:
        return None
    return data


def join_quotes_with_memberships(quotes: list[dict], memberships: list[dict]) -> list[dict]:
    """34 行结构 join 31 条事实（报告/展示用，每板块一行含行情）。"""
    by_code = {normalize_code(str(q.get("code") or "")): q for q in quotes if normalize_code(str(q.get("code") or ""))}
    out: list[dict] = []
    for m in memberships:
        code = normalize_code(str(m.get("code") or ""))
        if not code:
            continue
        fact = by_code.get(code)
        if fact is None:
            continue
        row = dict(fact)
        row["group"] = str(m.get("group") or "")
        name = str(m.get("name") or "").strip()
        if name:
            row["name"] = name
        out.append(row)
    return out


def structure_row_count(stocks: list[StockItem]) -> int:
    return len(_dedupe_memberships(memberships_from_stocks(stocks)))


def structure_payload_from_stocks(stocks: list[StockItem]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """去重 memberships + structure（meta 与落盘共用）。"""
    memberships = _dedupe_memberships(memberships_from_stocks(stocks))
    structure = structure_from_stocks(
        [
            StockItem(code=m["code"], name=m["name"], group=m["group"], block_id="")
            for m in memberships
        ]
    )
    return memberships, structure


def load_joined_quote_rows(*, on_date: date | None = None) -> list[dict] | None:
    """读落盘并按 structure join 事实层（报告/展示用 34/35 行）。"""
    data = load_quote_query_cache(on_date=on_date)
    if not data:
        return None
    quotes = data.get("quotes")
    memberships = data.get("memberships")
    if not isinstance(quotes, list) or not isinstance(memberships, list):
        return None
    return join_quotes_with_memberships(quotes, memberships)


def persist_quote_query(
    quotes: list[dict],
    *,
    mode: str,
    structure_stocks: list[StockItem],
    on_date: date | None = None,
) -> Path:
    day = on_date or date.today()
    path = quote_query_cache_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)

    memberships = memberships_from_stocks(structure_stocks)
    existing = _load_quote_query_cache(path)

    if mode == "all" or existing is None:
        merged_quotes = quotes
        merged_memberships = _dedupe_memberships(memberships)
    else:
        merged_quotes = _merge_quotes(list(existing.get("quotes") or []), quotes)
        replace_codes = {normalize_code(str(q.get("code") or "")) for q in quotes}
        merged_memberships = _merge_memberships(
            list(existing.get("memberships") or []),
            memberships,
            replace_codes=replace_codes,
        )

    deduped_quotes = _merge_quotes([], merged_quotes)
    _, structure = structure_payload_from_stocks(
        [
            StockItem(code=m["code"], name=m["name"], group=m["group"], block_id="")
            for m in merged_memberships
        ]
    )
    query_meta: dict[str, Any] = {"mode": mode}
    payload: dict[str, Any] = {
        "schema_version": QUOTE_QUERY_SCHEMA_VERSION,
        "calendar_date": day.isoformat(),
        "updated_at": now_iso(),
        "query": query_meta,
        "mode": mode,
        "code_count": len(deduped_quotes),
        "row_count": len(merged_memberships),
        "count": len(deduped_quotes),
        "quotes": deduped_quotes,
        "memberships": merged_memberships,
        "structure": structure,
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def load_quote_query_cache(*, on_date: date | None = None) -> dict | None:
    return _load_quote_query_cache(quote_query_cache_path(on_date))
