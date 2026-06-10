"""早盘一键编排。"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from morning.pipeline import run_morning_report
from morning.pre_collect import run_morning_pre
from morning.run_status import begin_run, fail_run, finish_run, step_begin, step_done


def run_morning_pre_pipeline(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cal = on_date or date.today()
    t0 = time.monotonic()
    result = run_morning_pre(on_date=cal, force=force)
    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return result


def run_morning_pipeline(
    *,
    on_date: date | None = None,
    force: bool = False,
    open_browser: bool = True,
) -> dict[str, Any]:
    cal = on_date or date.today()
    begin_run(cal, open_browser=open_browser)

    step_begin(cal, "assemble", detail="等待竞价就绪并拼装上下文…")
    t0 = time.monotonic()
    result = run_morning_report(on_date=cal, force=force)
    total_ms = int((time.monotonic() - t0) * 1000)

    if result.get("outcome") in ("fail", "error"):
        fail_run(cal, result.get("step") or "report", str(result.get("reason") or result.get("message")))
        result["duration_ms"] = total_ms
        return result

    if result.get("outcome") == "skip":
        finish_run(cal, ok=True)
        return result

    step_done(cal, "assemble", duration_ms=total_ms // 3, detail="上下文已拼装")
    step_done(cal, "ai", duration_ms=result.get("ai", {}).get("ai_duration_ms") or 0, detail="AI 完成")
    step_done(cal, "render", duration_ms=total_ms // 3, detail="页面与微信已更新")
    finish_run(cal, ok=bool(result.get("sla_ok")))
    result["duration_ms"] = total_ms
    return result


__all__ = ["run_morning_pipeline", "run_morning_pre_pipeline"]
