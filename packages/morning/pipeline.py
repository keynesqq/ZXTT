"""早盘报告档编排。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from core.config import morning_cfg
from core.paths import DATA_DIR
from core.trading_calendar import is_trading_day, previous_trading_day
from morning.assemble import build_morning_context, load_morning_pre, save_context
from morning.generate import run_morning_ai
from morning.render import run_morning_render
from morning.wait_auction import wait_auction_ready

_EXP = DATA_DIR / "expectations"
_AI = DATA_DIR / "scheduled_ai"


def _check_prerequisites(cal: date, *, force: bool) -> dict[str, Any] | None:
    if not force and not is_trading_day(cal):
        return {"outcome": "skip", "reason": "not_trading_day"}
    pre = load_morning_pre(cal)
    if not pre:
        return {"outcome": "error", "reason": "morning_pre_missing", "hint": "morning --phase pre"}
    prev = previous_trading_day(cal)
    if not (_EXP / f"{cal.isoformat()}.json").is_file():
        if not prev or not (_AI / f"evening_{prev.isoformat()}.json").is_file():
            return {"outcome": "error", "reason": "evening_missing", "hint": "run evening first"}
    if not (DATA_DIR / "quote_query_{}.json".format(cal.isoformat())).is_file():
        if not prev or not (DATA_DIR / f"quote_query_{prev.isoformat()}.json").is_file():
            return {"outcome": "error", "reason": "quote_query_missing"}
    return None


def run_morning_report(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    sla_start = time.monotonic()
    cal = on_date or date.today()
    err = _check_prerequisites(cal, force=force)
    if err:
        return err

    ready, _manifest = wait_auction_ready(cal)
    if not ready and not force:
        trend_path = DATA_DIR / f"auction_trend_{cal.isoformat()}.json"
        if not trend_path.is_file():
            return {"outcome": "error", "reason": "auction_not_ready", "hint": "run auction"}

    auction_ready_at = time.time()
    open_market: dict[str, Any] | None = None
    try:
        from market.sentiment import collect_open_market_context

        open_market = collect_open_market_context(calendar_date=cal)
    except Exception as e:
        open_market = {"warnings": [str(e)]}

    try:
        ctx = build_morning_context(calendar_date=cal, open_market=open_market)
        save_context(ctx, cal)
    except FileNotFoundError as e:
        return {"outcome": "error", "reason": "assemble_failed", "message": str(e)}

    ai_result = run_morning_ai(on_date=cal)
    if ai_result.get("outcome") == "fail":
        on_fail = str(morning_cfg().get("on_ai_fail") or "error")
        if on_fail == "error":
            return {
                "outcome": "fail",
                "step": "ai",
                "ai": ai_result,
                "sla_ms": int((time.monotonic() - sla_start) * 1000),
            }

    render_result = run_morning_render(on_date=cal)
    sla_ms = int((time.monotonic() - sla_start) * 1000)
    sla_limit = int(morning_cfg().get("sla_sec") or 120) * 1000
    sla_ok = sla_ms <= sla_limit and render_result.get("push", {}).get("outcome") in ("ok", "skip")

    run_payload = {
        "schema_version": 1,
        "slot": "morning",
        "calendar_date": cal.isoformat(),
        "auction_ready_at": auction_ready_at,
        "delivered_at": time.time(),
        "sla_ms": sla_ms,
        "sla_ok": sla_ok,
        "ai_duration_ms": ai_result.get("ai_duration_ms"),
    }
    run_dir = DATA_DIR / "morning_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    from core.io import atomic_write_text

    atomic_write_text(
        run_dir / f"{cal.isoformat()}.json",
        json.dumps(run_payload, ensure_ascii=False, indent=2),
    )

    if ai_result.get("outcome") == "fail":
        return {
            "outcome": "fail",
            "step": "ai",
            "ai": ai_result,
            "render": render_result,
            "sla_ms": sla_ms,
            "sla_ok": sla_ok,
        }

    return {
        "outcome": "ok",
        "report_path": render_result.get("path"),
        "push": render_result.get("push"),
        "ai": ai_result,
        "sla_ms": sla_ms,
        "sla_ok": sla_ok,
    }


__all__ = ["run_morning_report"]
