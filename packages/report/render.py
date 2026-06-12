"""第 5 步 5A · 渲染上下文。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.paths import DATA_DIR, ROOT
from core.trading_calendar import previous_trading_day
from quote.query_cache import join_quotes_with_memberships, load_quote_query_cache
from report.md_html import markdown_to_html, push_summary_to_html
from ai.parse import resolve_ai_report_fields

_CTX_DIR = DATA_DIR / "evening_context"
_MIDDAY_CTX_DIR = DATA_DIR / "midday_context"
_MORNING_CTX_DIR = DATA_DIR / "morning_context"
_CHECKS_DIR = DATA_DIR / "morning_checks"
_PRE_DIR = DATA_DIR / "morning_pre"
_RUN_DIR = DATA_DIR / "morning_run"
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
                "events_display": lb.get("events_display") or [],
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


def build_midday_render_context(*, on_date: date) -> dict[str, Any]:
    ctx = _load_json(_MIDDAY_CTX_DIR / f"{on_date.isoformat()}.json") or {}
    ai = _load_json(_AI_DIR / f"midday_{on_date.isoformat()}.json") or {}
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
                "events_display": lb.get("events_display") or [],
                "stance_label": lb.get("stance_label") or "",
                "primary_stance": lb.get("primary_stance") or "",
                "main_net_yi": flow.get("main_net_yi"),
                "stock_href": f"#stock-{code}",
            }
        )

    ai_ok = bool(ai.get("body")) and not ai.get("ai_error")
    exp_path = f"data/expectations/{on_date.isoformat()}_midday.json"

    return {
        "trade_date": meta.get("trade_date") or on_date.isoformat(),
        "context_as_of": meta.get("context_as_of") or "",
        "generated_at": now_iso(),
        "code_count": meta.get("code_count", 0),
        "row_count": meta.get("row_count", 0),
        "health_brief": health.get("health_brief", ""),
        "trust_flags": health.get("trust_flags") or {},
        "ai_ok": ai_ok,
        "ai_error": ai.get("ai_error") or "",
        "ai_model": ai.get("model") or "",
        "missing_codes": ai.get("missing_codes") or [],
        "truncated_suspected": ai.get("truncated_suspected", False),
        "critical_missing": ai.get("critical_missing", False),
        "ai_summary_html": push_summary_to_html(
            ai.get("summary") or "",
            label_aliases={"仓位": "操作"},
        ),
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
        "expectations_path": exp_path,
        "slot": "midday",
        "session_label": "午间休市",
    }


def _morning_ai_fields(ai: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """解析 AI 字段；与 generate 写盘同源。"""
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    fields = resolve_ai_report_fields(
        raw=ai.get("raw") or "",
        body=ai.get("body") or "",
        summary=ai.get("summary") or "",
        stocks=stocks,
    )
    body = str(fields["body"])
    return {
        "body": body,
        "summary": str(fields["summary"]),
        "missing_codes": list(fields["missing_codes"]),
        "ai_ok": bool(body) and not ai.get("ai_error"),
    }


def build_morning_render_context(*, on_date: date) -> dict[str, Any]:
    ctx = _load_json(_MORNING_CTX_DIR / f"{on_date.isoformat()}.json") or {}
    ai = _load_json(_AI_DIR / f"morning_{on_date.isoformat()}.json") or {}
    checks = _load_json(_CHECKS_DIR / f"{on_date.isoformat()}.json") or ctx.get("checks") or {}
    pre = _load_json(_PRE_DIR / f"{on_date.isoformat()}.json") or ctx.get("morning_pre") or {}
    run_st = _load_json(_RUN_DIR / f"{on_date.isoformat()}.json") or {}
    meta = ctx.get("meta") or {}

    ai_fields = _morning_ai_fields(ai, ctx)
    ai_ok = ai_fields["ai_ok"]
    body = ai_fields["body"]
    summary = ai_fields["summary"]

    quote_data = load_quote_query_cache(on_date=on_date) or {}
    if not quote_data.get("quotes"):
        prev = previous_trading_day(on_date)
        if prev:
            quote_data = load_quote_query_cache(on_date=prev) or quote_data
    structure = quote_data.get("structure") or {}
    group_order = [
        str(g.get("name")).strip()
        for g in (structure.get("groups") or [])
        if isinstance(g, dict) and str(g.get("name") or "").strip()
    ]
    check_codes = {str(r.get("code") or "") for r in (checks.get("rows") or [])}
    joined = join_quotes_with_memberships(
        quote_data.get("quotes") or [],
        quote_data.get("memberships") or [],
    )
    membership_rows = [r for r in joined if str(r.get("code") or "") in check_codes]

    return {
        "trade_date": meta.get("calendar_date") or on_date.isoformat(),
        "context_as_of": meta.get("context_as_of") or "",
        "generated_at": now_iso(),
        "code_count": meta.get("code_count", 0),
        "point_count": meta.get("point_count") or checks.get("point_count"),
        "ai_ok": ai_ok,
        "ai_error": ai.get("ai_error") or "",
        "ai_model": ai.get("model") or "",
        "missing_codes": ai_fields["missing_codes"],
        "ai_summary_html": push_summary_to_html(summary),
        "ai_body_html": markdown_to_html(body),
        "ai_body_raw": body,
        "ai_summary_raw": summary,
        "checks": checks,
        "morning_pre": pre,
        "evening_summary": meta.get("evening_summary") or "",
        "group_order": group_order,
        "membership_rows": membership_rows,
        "open_market": ctx.get("open_market") or {},
        "slot": "morning",
        "session_label": "集合竞价结束",
        "sla_ms": run_st.get("sla_ms"),
        "sla_ok": run_st.get("sla_ok"),
        "ai_duration_ms": ai.get("ai_duration_ms") or run_st.get("ai_duration_ms"),
    }


__all__ = ["build_evening_render_context", "build_midday_render_context", "build_morning_render_context"]
