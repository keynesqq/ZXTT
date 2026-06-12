"""第 3 步 · 午间本地预处理编排（3.1–3.7，无 3.8）。"""
from __future__ import annotations

import json
import time
from datetime import date
from typing import Any

from core.config import normalize_code
from core.health_gate import first_global_health_block
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import is_trading_day
from events.cards import build_events_by_code
from midday.assemble import build_midday_context_skeleton
from midday.feeds_digest import run_feeds_digest
from midday.feeds_fingerprint import baseline_for_day, decide_feeds_status, diff_vs_baseline
from midday.finalize import finalize_midday_context
from midday.health import build_health
from midday.local_block import build_local_block
from midday.market_local import build_market_local
from midday.normalize import build_midday_bundle
from midday.tags import build_tags_by_code

_IMPLEMENTED_STEPS = ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")


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


def run_preprocess_midday(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """午间预处理全链 3.1–3.7，落盘 midday_context。"""
    t0 = time.monotonic()
    cal = on_date or date.today()
    if not force and not is_trading_day(cal):
        return {
            "outcome": "fail",
            "reason": "not_trading_day",
            "calendar_date": cal.isoformat(),
        }

    try:
        bundle = build_midday_bundle(on_date=cal)
    except FileNotFoundError as e:
        return {"outcome": "fail", "reason": "missing_input", "message": str(e)}
    except Exception as e:
        return {"outcome": "fail", "reason": "normalize_error", "message": str(e)}

    trade_date = date.fromisoformat(str((bundle.get("meta") or {}).get("trade_date") or cal.isoformat()))
    tags_by_code = build_tags_by_code(bundle)
    health = build_health(bundle, tags_by_code=tags_by_code)
    blocked = first_global_health_block(health)
    if blocked:
        return {
            "outcome": "fail",
            "reason": "health_block",
            "code_key": blocked.get("code_key"),
            "message": blocked.get("message"),
            "calendar_date": cal.isoformat(),
        }
    feeds_diff = _feeds_diff_map(bundle, trade_date)
    events_by_code = build_events_by_code(bundle, feeds_diff_by_code=feeds_diff)
    market_local = build_market_local(bundle, health)
    digest_result = run_feeds_digest(bundle, tags_by_code, trade_date=trade_date)
    feeds_digest_by_code = digest_result.get("feeds_digest_by_code") or {}
    intraday_digest_ok = bool((bundle.get("meta") or {}).get("intraday_digest_ok"))

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
            intraday_digest_ok=intraday_digest_ok,
        )

    skeleton = build_midday_context_skeleton(
        bundle,
        health=health,
        events_by_code=events_by_code,
        tags_by_code=tags_by_code,
        market_local=market_local,
        feeds_digest_by_code=feeds_digest_by_code,
        local_blocks=local_blocks,
    )
    ctx = finalize_midday_context(skeleton, trade_date=cal)

    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    duration_ms = int((time.monotonic() - t0) * 1000)
    feeds_counts: dict[str, int] = {}
    for rec in (digest_result.get("feeds_digest_by_code") or {}).values():
        st = str(rec.get("status") or "unknown")
        feeds_counts[st] = feeds_counts.get(st, 0) + 1
    manifest_path = DATA_DIR / "ai_digest" / trade_date.isoformat() / "midday_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "slot": "midday",
        "session_label": "午间休市",
        "trade_date": trade_date.isoformat(),
        "stages": {
            "preprocess": {
                "duration_ms": duration_ms,
                "feeds_status": feeds_counts,
                "feeds_fail_count": digest_result.get("fail_count", 0),
            }
        },
    }
    atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return {
        "outcome": "ok",
        "implemented_steps": list(_IMPLEMENTED_STEPS),
        "calendar_date": cal.isoformat(),
        "path": ctx.get("path"),
        "code_count": meta.get("code_count"),
        "row_count": meta.get("row_count"),
        "context_as_of": meta.get("context_as_of"),
        "prompt_stocks": len(prompt.get("stocks") or []),
        "feeds_digest_fail_count": digest_result.get("fail_count", 0),
        "feeds_status": feeds_counts,
        "duration_ms": duration_ms,
    }


__all__ = ["run_preprocess_midday"]
