"""第 3 步 3.1 · 合并对齐 MiddayBundle（无 B 层长文）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.config import normalize_code
from core.context_as_of import max_ts_iso
from core.paths import DATA_DIR
from quote.query_cache import load_quote_query_cache, quote_query_cache_path

_SLOT = "midday"
_FEED_KEYS = ("公告", "资讯", "观点", "研报", "行业资讯")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _items_by_code(items: list[dict] | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in items or []:
        code = normalize_code(str(row.get("code") or ""))
        if code:
            out[code] = row
    return out


def _flat_slot(data: dict[str, Any] | None, *, slot: str = _SLOT) -> dict[str, Any]:
    if not data:
        return {}
    if data.get("latest_slot") == slot:
        return data
    for snap in data.get("snapshots") or []:
        if isinstance(snap, dict) and snap.get("slot") == slot:
            return snap
    return data


def _feed_item_key(item: dict) -> str:
    key = str(item.get("code_key") or "").strip()
    if key:
        return key
    url = str(item.get("url") or "").strip()
    if url:
        return url
    return f"{item.get('title', '')}|{item.get('pub_date', '')}"


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        k = _feed_item_key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _merge_feeds(ann_row: dict | None, news_row: dict | None) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "公告": _dedupe_items(list((ann_row or {}).get("announcements") or [])),
        "资讯": _dedupe_items(list((news_row or {}).get("news") or [])),
        "观点": _dedupe_items(list((news_row or {}).get("opinions") or [])),
        "研报": _dedupe_items(list((news_row or {}).get("research") or [])),
        "行业资讯": _dedupe_items(list((news_row or {}).get("industry_news") or [])),
        "warnings": [],
        "warnings_struct": [],
    }
    warning = (ann_row or {}).get("warning")
    if isinstance(warning, dict) and warning.get("message"):
        merged["warnings"].append(str(warning["message"]))
        merged["warnings_struct"].append(
            {
                "code_key": str(warning.get("code") or "ANN_WARN"),
                "message": str(warning["message"]),
                "category": "公告",
                "code": str((ann_row or {}).get("code") or ""),
                "group": "",
            }
        )
    for msg in (news_row or {}).get("warnings") or []:
        if msg and msg not in merged["warnings"]:
            merged["warnings"].append(str(msg))
    for ws in (news_row or {}).get("warnings_struct") or []:
        if isinstance(ws, dict):
            merged["warnings_struct"].append(dict(ws))
    return merged


def _groups_for_code(memberships: list[dict], code: str) -> list[str]:
    groups: list[str] = []
    for row in memberships:
        if normalize_code(str(row.get("code") or "")) == code:
            g = str(row.get("group") or "").strip()
            if g and g not in groups:
                groups.append(g)
    return groups


def _flow_by_code(flow_data: dict[str, Any] | None) -> dict[str, dict]:
    flat = _flat_slot(flow_data)
    out: dict[str, dict] = {}
    for row in flat.get("watchlist_flow") or []:
        code = normalize_code(str(row.get("code") or ""))
        if code and code not in out:
            out[code] = {
                "main_net_yi": row.get("main_net_yi"),
                "pct_chg": row.get("pct_chg"),
            }
    return out


def _paths_meta(day: date) -> dict[str, str]:
    iso = day.isoformat()
    return {
        "quote": f"data/quote_query_{iso}.json",
        "announcement": f"data/announcement_query_{iso}.json",
        "news": f"data/news_query_{iso}.json",
        "market_sentiment": f"data/market_sentiment/{iso}.json",
        "market_index": f"data/market_index/{iso}.json",
        "market_flow": f"data/market_flow/{iso}.json",
        "cls_finance": f"data/cls_finance/{iso}.json",
        "collect_manifest": f"data/collect_manifest/{iso}_midday.json",
    }


def _context_as_of_draft(
    *,
    quote: dict | None,
    ann: dict | None,
    news: dict | None,
    sentiment: dict | None,
    index: dict | None,
    flow: dict | None,
    cls_fin: dict | None,
) -> str:
    stamps: list[str | None] = []
    if quote:
        stamps.append(str(quote.get("updated_at") or ""))
    if ann:
        stamps.append(str(ann.get("updated_at") or ""))
    if news:
        stamps.append(str(news.get("updated_at") or ""))
    if sentiment:
        stamps.append(str(sentiment.get("collected_at_iso") or sentiment.get("updated_at_iso") or ""))
    index_flat = _flat_slot(index)
    flow_flat = _flat_slot(flow)
    stamps.append(str(index_flat.get("collected_at_iso") or index_flat.get("updated_at_iso") or ""))
    stamps.append(str(flow_flat.get("collected_at_iso") or flow_flat.get("updated_at_iso") or ""))
    if cls_fin:
        stamps.append(str(cls_fin.get("collected_at_iso") or cls_fin.get("updated_at_iso") or ""))
    for items in (ann or {}).get("items") or []:
        stamps.append(str(items.get("queried_at") or ""))
    for items in (news or {}).get("items") or []:
        stamps.append(str(items.get("queried_at") or ""))
    return max_ts_iso(*stamps)


def build_midday_bundle(*, on_date: date | None = None) -> dict[str, Any]:
    """读 6 路 raw，合并为 MiddayBundle。"""
    day = on_date or date.today()
    iso = day.isoformat()
    paths = _paths_meta(day)

    quote = load_quote_query_cache(on_date=day)
    if not quote:
        raise FileNotFoundError(f"quote_query missing: {quote_query_cache_path(day)}")

    ann = _load_json(DATA_DIR / f"announcement_query_{iso}.json")
    news = _load_json(DATA_DIR / f"news_query_{iso}.json")
    sentiment = _load_json(DATA_DIR / "market_sentiment" / f"{iso}.json")
    index_raw = _load_json(DATA_DIR / "market_index" / f"{iso}.json")
    flow_raw = _load_json(DATA_DIR / "market_flow" / f"{iso}.json")
    cls_fin = _load_json(DATA_DIR / "cls_finance" / f"{iso}.json")

    memberships = list(quote.get("memberships") or [])
    structure = dict(quote.get("structure") or {})
    group_order = [
        str(g.get("name")).strip()
        for g in (structure.get("groups") or [])
        if isinstance(g, dict) and str(g.get("name") or "").strip()
    ]

    whitelist: list[str] = []
    seen: set[str] = set()
    for row in quote.get("quotes") or []:
        code = normalize_code(str(row.get("code") or ""))
        if code and code not in seen:
            seen.add(code)
            whitelist.append(code)

    ann_by = _items_by_code((ann or {}).get("items"))
    news_by = _items_by_code((news or {}).get("items"))
    flow_by = _flow_by_code(flow_raw)
    index_flat = _flat_slot(index_raw)
    flow_flat = _flat_slot(flow_raw)

    orphan_codes: list[str] = []
    for code in set(ann_by) | set(news_by):
        if code not in seen:
            orphan_codes.append(code)
    orphan_codes.sort()

    missing_feeds_sources: list[str] = []
    by_code: dict[str, Any] = {}

    for code in whitelist:
        quote_row = next(
            (dict(q) for q in (quote.get("quotes") or []) if normalize_code(str(q.get("code") or "")) == code),
            {},
        )
        quote_clean = {k: v for k, v in quote_row.items() if k != "group"}
        ann_row = ann_by.get(code)
        news_row = news_by.get(code)
        if ann_row is None:
            missing_feeds_sources.append(f"{code}:announcement")
        if news_row is None:
            missing_feeds_sources.append(f"{code}:news")
        feeds_merged = _merge_feeds(ann_row, news_row)
        industry = str(quote_clean.get("industry") or (news_row or {}).get("industry") or "")
        by_code[code] = {
            "quote": quote_clean,
            "groups": _groups_for_code(memberships, code),
            "feeds_merged": feeds_merged,
            "feeds_meta": {
                "industry": industry,
                "ann_queried_at": str((ann_row or {}).get("queried_at") or ""),
                "news_queried_at": str((news_row or {}).get("queried_at") or ""),
            },
            "flow_stock": flow_by.get(code) or {"main_net_yi": None, "pct_chg": quote_clean.get("pct_chg")},
        }

    market: dict[str, Any] = {
        "sentiment": sentiment or {},
        "index": {
            "indices": index_flat.get("indices") or [],
            "latest_slot": index_flat.get("slot") or index_raw.get("latest_slot") if index_raw else None,
            "collected_at_iso": index_flat.get("collected_at_iso") or (index_raw or {}).get("updated_at_iso"),
        },
        "cls_finance": cls_fin or {},
        "flow_meta": {
            "latest_slot": flow_flat.get("slot") or (flow_raw or {}).get("latest_slot"),
            "watchlist_enabled": flow_flat.get("watchlist_enabled"),
            "northbound": flow_flat.get("northbound") or {},
            "market": flow_flat.get("market") or {},
            "sectors_inflow_top": flow_flat.get("sectors_inflow_top") or [],
            "sectors_outflow_top": flow_flat.get("sectors_outflow_top") or [],
            "flow_score": flow_flat.get("flow_score") or (flow_raw or {}).get("flow_score"),
            "flow_signal": flow_flat.get("flow_signal") or (flow_raw or {}).get("flow_signal"),
            "flow_hint": flow_flat.get("flow_hint") or (flow_raw or {}).get("flow_hint"),
            "file_warnings": list((flow_raw or {}).get("warnings") or []),
        },
    }

    meta = {
        "schema_version": 1,
        "slot": _SLOT,
        "session_label": "午间休市",
        "pipeline_step": "3.1",
        "trade_date": str(quote.get("calendar_date") or iso),
        "calendar_date": iso,
        "context_as_of": _context_as_of_draft(
            quote=quote,
            ann=ann,
            news=news,
            sentiment=sentiment,
            index=index_raw,
            flow=flow_raw,
            cls_fin=cls_fin,
        ),
        "code_count": len(whitelist),
        "row_count": int(quote.get("row_count") or len(memberships)),
        "orphan_codes": orphan_codes,
        "missing_feeds_sources": missing_feeds_sources,
        "paths": paths,
    }

    return {
        "meta": meta,
        "group_order": group_order,
        "memberships": memberships,
        "structure": structure,
        "by_code": by_code,
        "market": market,
    }


__all__ = ["build_midday_bundle"]
