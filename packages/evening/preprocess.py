"""第 3 步 · 本地预处理编排（3.1–3.8）。"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.config import evening_cfg, normalize_code
from core.trading_calendar import is_trading_day
from evening.assemble import build_evening_context_skeleton
from evening.cls_digest import run_cls_digest
from evening.feeds_digest import run_feeds_digest
from evening.feeds_fingerprint import baseline_for_day, decide_feeds_status, diff_vs_baseline
from evening.finalize import finalize_evening_context
from evening.health import build_health
from evening.local_block import build_local_block
from evening.market_local import build_market_local
from evening.normalize import build_evening_bundle
from evening.tags import build_tags_by_code
from events.cards import build_events_by_code

_IMPLEMENTED_STEPS = ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8")


def _feeds_diff_map(bundle: dict[str, Any], trade_date: date) -> dict[str, Any]:
    prev_bl, today_bl = baseline_for_day(trade_date)
    out: dict[str, Any] = {}
    for code, row in (bundle.get("by_code") or {}).items():
        feeds = row.get("feeds_merged") or {}
        _, fp, meta = decide_feeds_status(
            code,
            feeds,
            trade_date=trade_date,
            today_baseline=today_bl,
            prev_baseline=prev_bl,
        )
        out[code] = diff_vs_baseline(feeds, prev_fp=meta.get("prev_fingerprint"), curr_fp=fp)
    return out


def run_preprocess_evening(
    *,
    on_date: date | None = None,
    force: bool = False,
    skip_cls_recollect: bool = False,
) -> dict[str, Any]:
    """晚间预处理全链 3.1–3.8，落盘 evening_context。"""
    cal = on_date or date.today()
    if not force and not is_trading_day(cal):
        return {
            "outcome": "fail",
            "reason": "not_trading_day",
            "calendar_date": cal.isoformat(),
        }

    if evening_cfg().get("preprocess_cls_recollect") and not skip_cls_recollect:
        try:
            from market.cls import collect_cls

            collect_cls(cal, include_articles=True, force=force, calendar_date=cal)
        except Exception:
            pass

    try:
        bundle = build_evening_bundle(on_date=cal)
    except FileNotFoundError as e:
        return {"outcome": "fail", "reason": "missing_input", "message": str(e)}
    except Exception as e:
        return {"outcome": "fail", "reason": "normalize_error", "message": str(e)}

    trade_date = date.fromisoformat(str((bundle.get("meta") or {}).get("trade_date") or cal.isoformat()))
    tags_by_code = build_tags_by_code(bundle)
    health = build_health(bundle, tags_by_code=tags_by_code)
    feeds_diff = _feeds_diff_map(bundle, trade_date)
    events_by_code = build_events_by_code(bundle, feeds_diff_by_code=feeds_diff)
    market_local = build_market_local(bundle, health)
    digest_result = run_feeds_digest(bundle, tags_by_code, trade_date=trade_date)
    feeds_digest_by_code = digest_result.get("feeds_digest_by_code") or {}

    local_blocks: dict[str, Any] = {}
    for code, row in (bundle.get("by_code") or {}).items():
        code = normalize_code(code)
        local_blocks[code] = build_local_block(
            code,
            row,
            tags=tags_by_code.get(code, {}),
            events=events_by_code.get(code),
            feeds_digest=feeds_digest_by_code.get(code),
            market_local=market_local,
            health_display=(health.get("display_by_code") or {}).get(code, []),
        )

    skeleton = build_evening_context_skeleton(
        bundle,
        health=health,
        events_by_code=events_by_code,
        tags_by_code=tags_by_code,
        market_local=market_local,
        feeds_digest_by_code=feeds_digest_by_code,
        local_blocks=local_blocks,
    )
    cls_result = run_cls_digest(bundle, trade_date=trade_date)
    ctx = finalize_evening_context(skeleton, cls_result, trade_date=cal)

    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    return {
        "outcome": "ok",
        "implemented_steps": list(_IMPLEMENTED_STEPS),
        "calendar_date": cal.isoformat(),
        "path": ctx.get("path"),
        "code_count": meta.get("code_count"),
        "row_count": meta.get("row_count"),
        "context_as_of": meta.get("context_as_of"),
        "cls_articles_found": meta.get("cls_articles_found"),
        "prompt_stocks": len(prompt.get("stocks") or []),
        "feeds_digest_fail_count": digest_result.get("fail_count", 0),
    }


__all__ = ["run_preprocess_evening"]
