"""早盘进度页状态。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR, ROOT

_STATUS_DIR = DATA_DIR / "morning_run"
_REPORTS = ROOT / "reports"

_STEPS = [
    ("assemble", "拼装+核对", 15),
    ("ai", "AI 合成", 85),
    ("render", "页面与推送", 95),
]


def _status_path(day: date) -> Path:
    return _STATUS_DIR / f"{day.isoformat()}.json"


def _report_dir(day: date) -> Path:
    out = _REPORTS / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_status(payload: dict[str, Any], day: date) -> Path:
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = _status_path(day)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def publish_status(day: date, status: dict[str, Any]) -> None:
    status["seq"] = int(status.get("seq") or 0) + 1
    write_status(status, day)
    from report.hub import refresh_hub_feed

    refresh_hub_feed(day, force=True)


def begin_run(day: date, *, open_browser: bool = True) -> None:
    status = {
        "schema_version": 1,
        "slot": "morning",
        "session_label": "集合竞价结束",
        "trade_date": day.isoformat(),
        "status": "running",
        "current_step": "assemble",
        "current_label": "开盘核对卡",
        "detail": "启动…",
        "progress_pct": 2,
        "started_at": now_iso(),
        "started_at_iso": now_iso(),
        "steps_done": [],
        "step_durations_ms": {},
        "seq": 0,
    }
    write_status(status, day)
    from report.hub import open_hub_for_scheduled_task

    if open_browser:
        open_hub_for_scheduled_task(day, slot="morning")


def step_begin(day: date, step: str, detail: str = "") -> None:
    st = json.loads(_status_path(day).read_text(encoding="utf-8"))
    pct = next((p for k, _, p in _STEPS if k == step), 10)
    st["current_step"] = step
    st["detail"] = detail
    st["progress_pct"] = pct
    publish_status(day, st)


def step_done(day: date, step: str, duration_ms: int = 0, detail: str = "") -> None:
    st = json.loads(_status_path(day).read_text(encoding="utf-8"))
    done = list(st.get("steps_done") or [])
    if step not in done:
        done.append(step)
    st["steps_done"] = done
    durs = dict(st.get("step_durations_ms") or {})
    if duration_ms:
        durs[step] = duration_ms
    st["step_durations_ms"] = durs
    if detail:
        st["detail"] = detail
    pct = next((p for k, _, p in _STEPS if k == step), st.get("progress_pct"))
    st["progress_pct"] = pct
    publish_status(day, st)


def fail_run(day: date, step: str, error: str) -> None:
    st = json.loads(_status_path(day).read_text(encoding="utf-8"))
    st["status"] = "fail"
    st["current_step"] = step
    st["error"] = error
    publish_status(day, st)


def finish_run(day: date, *, ok: bool = True) -> None:
    st = json.loads(_status_path(day).read_text(encoding="utf-8"))
    st["status"] = "ok" if ok else "warn"
    st["progress_pct"] = 100
    st["current_step"] = "done"
    st["detail"] = "完成"
    st["finished_at"] = now_iso()
    st["finished_at_iso"] = now_iso()
    publish_status(day, st)


__all__ = ["begin_run", "step_begin", "step_done", "fail_run", "finish_run"]
