"""第 3 步 3.7A · 每股 local_block。"""
from __future__ import annotations

from typing import Any

from intraday.digest import build_quote_line_with_intraday


def build_local_block(
    code: str,
    row: dict[str, Any],
    *,
    tags: dict[str, Any],
    events: dict[str, Any] | None,
    feeds_digest: dict[str, Any] | None,
    market_local: dict[str, Any],
    health_display: list[dict],
    intraday_digest_ok: bool = False,
) -> dict[str, Any]:
    quote = row.get("quote") or {}
    flow = row.get("flow_stock") or {}
    intraday = row.get("intraday_full") or {}
    name = str(quote.get("name") or code)
    industry = str(quote.get("industry") or (row.get("feeds_meta") or {}).get("industry") or "")
    ih = (market_local.get("industry_in_hot_by_code") or {}).get(code) or {}

    fd = feeds_digest or {}
    events_display = (events or {}).get("display") or []
    block = {
        "code": code,
        "name": name,
        "industry": industry,
        "primary_stance": tags.get("primary_stance"),
        "stance_label": tags.get("stance_label"),
        "groups": tags.get("groups") or row.get("groups") or [],
        "stance_hint": tags.get("stance_label"),
        "quote_line": build_quote_line_with_intraday(
            quote,
            flow,
            tags,
            intraday=intraday,
            slot="full",
            digest_ok=intraday_digest_ok,
        ),
        "intraday_full": intraday,
        "tag_facts": tags.get("tag_facts") or {},
        "tags": tags.get("tags") or [],
        "trend_short": tags.get("trend_short"),
        "trend_mid": tags.get("trend_mid"),
        "flow": {"main_net_yi": flow.get("main_net_yi"), "pct_chg": flow.get("pct_chg")},
        "events_display": events_display,
        "events_label": _events_label(events, events_display),
        "feeds_digest": {
            "status": fd.get("status"),
            "ok": fd.get("ok", False),
            "summary": fd.get("summary", ""),
            "facts_top": (fd.get("facts") or [])[:5],
            "event_net": fd.get("event_net", ""),
            "digested_at": fd.get("digested_at", ""),
            "digest_trade_date": fd.get("digest_trade_date", ""),
            "reuse_reason": fd.get("reuse_reason", ""),
            "context_note": fd.get("context_note", ""),
        },
        "industry_in_hot": ih,
        "health_display": health_display,
    }
    lines = [block["quote_line"], block["events_label"]]
    if fd.get("context_note"):
        lines.append(fd["context_note"])
    if not fd.get("ok"):
        lines.append("feeds digest 不可用，请依 events+标题")
    block["prompt_line"] = "\n".join(lines)
    return block


def _events_label(events: dict | None, display: list[dict]) -> str:
    if not display:
        return "无规则命中"
    return "；".join(f"{e.get('label','')}{e.get('title','')[:20]}" for e in display[:3])


__all__ = ["build_local_block"]
