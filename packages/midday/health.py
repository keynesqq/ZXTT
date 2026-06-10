"""第 3 步 3.2 · 午间数据健康与 trust_flags（无 B 层长文检查）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.config import health_cfg, normalize_code
from core.paths import DATA_DIR
from feeds.feed_warnings import (
    ANN_EMPTY,
    ANN_LATEST_FALLBACK,
    FEED_COLLECT_FAILED,
    IND_EMPTY,
    NEWS_EMPTY,
    NEWS_STALE,
    RES_EMPTY,
)

_INFO_STANCES = frozenset({"holding", "candidate", "watch_right"})
_WARN_LEVEL = {
    FEED_COLLECT_FAILED: "block",
    "QUOTE_MISSING": "block",
    ANN_LATEST_FALLBACK: "warn",
    NEWS_STALE: "warn",
    "FEEDS_ALL_EMPTY": "warn",
    "QUOTE_VERIFY": "warn",
    "NAME_INCOMPLETE": "warn",
}
_INFO_LEVEL = {ANN_EMPTY, NEWS_EMPTY, RES_EMPTY, IND_EMPTY}


def _load_manifest(day: date) -> dict[str, Any] | None:
    path = DATA_DIR / "collect_manifest" / f"{day.isoformat()}_midday.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _source_ok(manifest: dict | None, key: str) -> bool:
    if not manifest:
        return False
    rec = (manifest.get("sources") or {}).get(key) or {}
    return rec.get("status") in ("ok", "warn")


def _trust_flags_from_bundle(bundle: dict[str, Any], manifest: dict | None) -> dict[str, bool]:
    market = bundle.get("market") or {}
    flow_meta = market.get("flow_meta") or {}
    north = flow_meta.get("northbound") or {}
    mkt = flow_meta.get("market") or {}

    main_net = mkt.get("main_net_yi")
    sectors = flow_meta.get("sectors_inflow_top") or []
    net_yi = north.get("net_yi")
    connect = north.get("connect_status") or {}
    suspicious_connect = any(str(v) not in ("1", "3", "") for v in connect.values())
    northbound_suspicious = (
        net_yi == 0
        and bool(health_cfg().get("northbound_zero_warn", True))
        and (suspicious_connect or not _source_ok(manifest, "market_flow"))
    )
    by_code = bundle.get("by_code") or {}
    wl_count = sum(1 for row in by_code.values() if (row.get("flow_stock") or {}).get("main_net_yi") is not None)

    return {
        "ecosystem": _source_ok(manifest, "market_sentiment"),
        "cls_finance": _source_ok(manifest, "cls_finance"),
        "index": _source_ok(manifest, "market_index"),
        "market_main_flow": main_net is not None,
        "sector_flow": bool(sectors),
        "northbound_suspicious": northbound_suspicious,
        "watchlist_flow": wl_count >= len(by_code) * 0.8 if by_code else False,
    }


def _global_health(bundle: dict[str, Any], trust: dict[str, bool]) -> list[dict[str, Any]]:
    global_items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(code_key: str, level: str, message: str) -> None:
        if code_key in seen:
            return
        seen.add(code_key)
        global_items.append({"code_key": code_key, "level": level, "message": message})

    if not trust.get("market_main_flow"):
        _add("FLOW_MARKET_FAIL", "warn", "大盘主力采集失败")
    if not trust.get("sector_flow"):
        _add("FLOW_SECTOR_FAIL", "warn", "行业资金 TOP 不可用")
    if trust.get("northbound_suspicious"):
        _add("NORTHBOUND_SUSPICIOUS", "warn", "北向成交净买额为零且数据存疑")
    return global_items


def _code_health_row(
    code: str,
    row: dict[str, Any],
    *,
    primary_stance: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    del code
    full: list[dict[str, Any]] = []
    feeds = row.get("feeds_merged") or {}
    ws = feeds.get("warnings_struct") or []
    for item in ws:
        ck = str(item.get("code_key") or "")
        if ck in _WARN_LEVEL:
            level = _WARN_LEVEL[ck]
        elif ck == NEWS_STALE:
            level = str(health_cfg().get("news_stale_level") or "warn")
        elif ck in _INFO_LEVEL:
            level = str(health_cfg().get("ann_empty_level") or "info")
        else:
            level = "info"
        full.append({"code_key": ck, "level": level, "message": str(item.get("message") or "")})

    counts = {k: len(feeds.get(k) or []) for k in ("公告", "资讯", "观点", "研报", "行业资讯")}
    if all(v == 0 for v in counts.values()) and not any(
        x.get("code_key") == FEED_COLLECT_FAILED for x in full
    ):
        full.append({"code_key": "FEEDS_ALL_EMPTY", "level": "warn", "message": "五类素材皆空"})

    display = [
        x
        for x in full
        if x.get("level") in ("block", "warn")
        or (x.get("level") == "info" and primary_stance in _INFO_STANCES)
    ]
    return full, display


def _health_brief(trust: dict[str, bool], summary: dict[str, Any]) -> str:
    parts: list[str] = []
    if not trust.get("market_main_flow"):
        parts.append("大盘主力不可用")
    if not trust.get("sector_flow"):
        parts.append("行业资金不可用")
    if trust.get("northbound_suspicious"):
        parts.append("北向存疑")
    if trust.get("watchlist_flow"):
        parts.append("自选主力可用")
    ann_empty = int(summary.get("ann_empty_codes") or 0)
    if ann_empty:
        parts.append(f"{ann_empty} 只近3日无公告")
    return "；".join(parts) + "。" if parts else "数据整体可用。"


def build_health(bundle: dict[str, Any], *, tags_by_code: dict[str, Any] | None = None) -> dict[str, Any]:
    """3.2：health + trust_flags + health_brief（午间，无 B 层）。"""
    meta = bundle.get("meta") or {}
    day = date.fromisoformat(str(meta.get("calendar_date") or meta.get("trade_date")))
    manifest = _load_manifest(day)
    trust = _trust_flags_from_bundle(bundle, manifest)
    global_items = _global_health(bundle, trust)

    by_code: dict[str, list[dict[str, Any]]] = {}
    display_by_code: dict[str, list[dict[str, Any]]] = {}
    summary = {
        "block_codes": 0,
        "warn_codes": 0,
        "ann_empty_codes": 0,
        "news_stale_codes": 0,
        "feeds_all_empty_codes": 0,
    }

    for code, row in (bundle.get("by_code") or {}).items():
        stance = (tags_by_code or {}).get(code, {}).get("primary_stance", "theme_other")
        full, display = _code_health_row(code, row, primary_stance=stance)
        by_code[code] = full
        display_by_code[code] = display
        if any(x.get("level") == "block" for x in full):
            summary["block_codes"] += 1
        if any(x.get("level") == "warn" for x in full):
            summary["warn_codes"] += 1
        if any(x.get("code_key") == ANN_EMPTY for x in full):
            summary["ann_empty_codes"] += 1
        if any(x.get("code_key") == NEWS_STALE for x in full):
            summary["news_stale_codes"] += 1
        if any(x.get("code_key") == "FEEDS_ALL_EMPTY" for x in full):
            summary["feeds_all_empty_codes"] += 1

    return {
        "health_brief": _health_brief(trust, summary),
        "global": global_items,
        "trust_flags": trust,
        "by_code": by_code,
        "display_by_code": display_by_code,
        "summary": summary,
    }


__all__ = ["build_health"]
