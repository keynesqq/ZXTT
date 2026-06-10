"""第 5 步 5A · 渲染上下文。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.paths import DATA_DIR, ROOT
from quote.query_cache import join_quotes_with_memberships, load_quote_query_cache
from report.md_html import markdown_to_html, push_summary_to_html

_CTX_DIR = DATA_DIR / "evening_context"
_AI_DIR = DATA_DIR / "scheduled_ai"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _critical_events(events_by_code: dict[str, Any], by_code: dict[str, Any]) -> list[dict]:
    rows: list[dict] = []
    for code, ev in (events_by_code or {}).items():
        lb = (by_code.get(code) or {}).get("local_block") or {}
        groups = lb.get("groups") or []
        for bucket in ("critical_bear", "critical_bull", "bear", "bull"):
            for item in ev.get(bucket) or []:
                rows.append({**item, "code": code, "name": lb.get("name", code), "groups": groups})
    return rows


def build_evening_render_context(*, on_date: date) -> dict[str, Any]:
    ctx = _load_json(_CTX_DIR / f"{on_date.isoformat()}.json") or {}
    ai = _load_json(_AI_DIR / f"evening_{on_date.isoformat()}.json") or {}
    meta = ctx.get("meta") or {}
    health = ctx.get("health") or {}
    quote_data = load_quote_query_cache(on_date=on_date) or {}
    quotes = quote_data.get("quotes") or []
    memberships = ctx.get("memberships") or quote_data.get("memberships") or []
    joined = join_quotes_with_memberships(quotes, memberships)

    by_code = ctx.get("by_code") or {}
    snapshot_rows = []
    for row in joined:
        code = str(row.get("code") or "")
        lb = (by_code.get(code) or {}).get("local_block") or {}
        flow = lb.get("flow") or {}
        snapshot_rows.append(
            {
                **row,
                "tags": lb.get("tags") or [],
                "events_label": lb.get("events_label") or "",
                "stance_label": lb.get("stance_label") or "",
                "primary_stance": lb.get("primary_stance") or "",
                "main_net_yi": flow.get("main_net_yi"),
                "stock_href": f"#stock-{code}",
            }
        )

    ai_ok = bool(ai.get("body")) and not ai.get("ai_error")
    target = None
    exp_path = ""
    from core.trading_calendar import next_trading_day

    nxt = next_trading_day(on_date)
    if nxt:
        exp_path = f"data/expectations/{nxt.isoformat()}.json"

    return {
        "trade_date": meta.get("trade_date") or on_date.isoformat(),
        "context_as_of": meta.get("context_as_of") or "",
        "generated_at": now_iso(),
        "code_count": meta.get("code_count", 0),
        "row_count": meta.get("row_count", 0),
        "cls_articles_found": meta.get("cls_articles_found", ""),
        "cls_complete": (ctx.get("cls_digest") or {}).get("complete", False),
        "health_brief": health.get("health_brief", ""),
        "trust_flags": health.get("trust_flags") or {},
        "ai_ok": ai_ok,
        "ai_error": ai.get("ai_error") or "",
        "ai_model": ai.get("model") or "",
        "missing_codes": ai.get("missing_codes") or [],
        "truncated_suspected": ai.get("truncated_suspected", False),
        "critical_missing": ai.get("critical_missing", False),
        "ai_summary_html": push_summary_to_html(ai.get("summary") or ""),
        "ai_body_html": markdown_to_html(ai.get("body") or ""),
        "ai_body_raw": ai.get("body") or "",
        "ai_summary_raw": ai.get("summary") or "",
        "group_order": ctx.get("group_order") or [],
        "snapshot_rows": snapshot_rows,
        "events_by_code": ctx.get("events_by_code") or {},
        "critical_events": _critical_events(ctx.get("events_by_code") or {}, by_code),
        "market_local": ctx.get("market_local") or {},
        "feeds_digest_by_code": ctx.get("feeds_digest_by_code") or {},
        "by_code": by_code,
        "cls_digest": ctx.get("cls_digest") or {},
        "expectations_path": exp_path,
    }


__all__ = ["build_evening_render_context"]
