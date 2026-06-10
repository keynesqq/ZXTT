"""午间管线一键编排：采集 → 预处理 → AI → 渲染。"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from core.trading_calendar import is_trading_day
from midday.collect import run_collect_midday
from midday.pipeline import run_midday_generate
from midday.preprocess import run_preprocess_midday
from midday.run_status import begin_run, fail_run, finish_run, step_begin, step_done


def run_midday_pipeline(
    *,
    on_date: date | None = None,
    force: bool = False,
    open_browser: bool = True,
) -> dict[str, Any]:
    cal = on_date or date.today()
    if not force and not is_trading_day(cal):
        return {"outcome": "fail", "reason": "not_trading_day", "calendar_date": cal.isoformat()}

    begin_run(cal, open_browser=open_browser)

    # ② collect
    step_begin(cal, "collect", detail="采集行情、资讯、大盘与财联社…")
    t0 = time.monotonic()
    coll = run_collect_midday(on_date=cal, force=force)
    coll_ms = int((time.monotonic() - t0) * 1000)
    if coll.get("overall") == "fail":
        fail_run(cal, "collect", str(coll.get("reason") or "collect_failed"))
        return {"outcome": "fail", "step": "collect", "result": coll}
    step_done(
        cal,
        "collect",
        duration_ms=coll_ms,
        detail=f"采集完成 · {coll.get('code_count', 0)} 只 · {coll_ms // 1000}s",
    )

    # ③ preprocess
    step_begin(cal, "preprocess", detail="预处理：标签、事件、feeds digest…")
    t0 = time.monotonic()
    prep = run_preprocess_midday(on_date=cal, force=force)
    prep_ms = int((time.monotonic() - t0) * 1000)
    if prep.get("outcome") != "ok":
        fail_run(cal, "preprocess", str(prep.get("message") or prep.get("reason") or "preprocess_failed"))
        return {"outcome": "fail", "step": "preprocess", "result": prep}
    feeds_st = prep.get("feeds_status") or {}
    feeds_line = " · ".join(f"{k} {v}" for k, v in feeds_st.items() if v)
    step_done(
        cal,
        "preprocess",
        duration_ms=prep_ms,
        detail=f"预处理完成 · feeds {feeds_line or '—'} · {prep_ms // 1000}s",
    )

    # ④ AI
    step_begin(cal, "ai", detail="AI 研判合成（拆分模式）…")
    t0 = time.monotonic()
    gen_ai = run_midday_generate(on_date=cal, phase="ai", force=force)
    ai_ms = int((time.monotonic() - t0) * 1000)
    ai = gen_ai.get("phases", {}).get("ai") or gen_ai
    if gen_ai.get("outcome") == "fail" or ai.get("outcome") == "fail":
        fail_run(cal, "ai", str(ai.get("message") or ai.get("reason") or "generate_failed"))
        return {"outcome": "fail", "step": "ai", "result": gen_ai}
    step_done(
        cal,
        "ai",
        duration_ms=ai_ms,
        detail=f"AI 完成 · {ai.get('synthesize_mode', '')} · 漏股 {len(ai.get('missing_codes') or [])} · {ai_ms // 1000}s",
    )

    # ⑤ render
    step_begin(cal, "render", detail="生成 HTML 页面与微信推送…")
    t0 = time.monotonic()
    gen_render = run_midday_generate(on_date=cal, phase="render", force=force)
    render_ms = int((time.monotonic() - t0) * 1000)
    render = gen_render.get("phases", {}).get("render") or gen_render
    if gen_render.get("outcome") == "fail" or render.get("outcome") == "fail":
        fail_run(cal, "render", str(render.get("message") or "render_failed"))
        return {"outcome": "fail", "step": "render", "result": gen_render}
    step_done(cal, "render", duration_ms=render_ms, detail="页面与微信推送已更新")
    finish_run(cal, ok=True)

    gen_ms = ai_ms + render_ms
    return {
        "outcome": "ok",
        "trade_date": cal.isoformat(),
        "collect_ms": coll_ms,
        "preprocess_ms": prep_ms,
        "generate_ms": gen_ms,
        "report_path": render.get("path"),
        "push": render.get("push"),
        "phases": {"ai": ai, "render": render},
    }


__all__ = ["run_midday_pipeline"]
