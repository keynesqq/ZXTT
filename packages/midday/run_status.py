"""午间管线运行状态 · 供 live 页面轮询刷新。"""
from __future__ import annotations

import json
import webbrowser
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR, ROOT
_STATUS_DIR = DATA_DIR / "midday_run"
_REPORTS = ROOT / "reports"

_STEPS: list[tuple[str, str, int]] = [
    ("collect", "② 采集行情与资讯", 10),
    ("preprocess", "③ 本地预处理", 35),
    ("ai", "④ AI 研判合成", 75),
    ("render", "⑤ 生成页面与推送", 95),
]


def _status_path(day: date) -> Path:
    return _STATUS_DIR / f"{day.isoformat()}.json"


def _report_path(day: date) -> Path:
    return _REPORTS / day.isoformat() / "daily_midday.html"


def load_status(day: date) -> dict[str, Any] | None:
    path = _status_path(day)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_status(payload: dict[str, Any], day: date) -> Path:
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = _status_path(day)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def _report_dir(day: date) -> Path:
    out = _REPORTS / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_run_status_js(day: date, status: dict[str, Any]) -> Path:
    from report.midday_live import build_run_status_js

    path = _report_dir(day) / "run_status.js"
    atomic_write_text(path, build_run_status_js(status))
    return path


def refresh_live_html(day: date, status: dict[str, Any]) -> Path:
    from report.midday_live import build_midday_live_page

    out_dir = _report_dir(day)
    path = out_dir / "daily_midday.html"
    page = build_midday_live_page(status)
    atomic_write_text(path, page)
    atomic_write_text(out_dir / "index.html", page)
    write_run_status_js(day, status)
    return path


def publish_status(day: date, status: dict[str, Any]) -> None:
    """仅写 JSON + run_status.js，供已打开的页面局部刷新。"""
    status["seq"] = int(status.get("seq") or 0) + 1
    write_status(status, day)
    write_run_status_js(day, status)
    from report.hub import publish_hub

    publish_hub(day)


def open_report_browser(day: date) -> None:
    from report.hub import open_hub

    open_hub(day, open_browser=True, slot="midday")


def begin_run(day: date, *, open_browser: bool = True) -> dict[str, Any]:
    status: dict[str, Any] = {
        "schema_version": 1,
        "slot": "midday",
        "session_label": "午间休市",
        "trade_date": day.isoformat(),
        "status": "running",
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "current_step": "collect",
        "current_label": _STEPS[0][1],
        "detail": "准备启动…",
        "progress_pct": 0,
        "steps_done": [],
        "step_durations_ms": {},
        "error": "",
        "seq": 0,
    }
    write_status(status, day)
    from report.hub import publish_hub

    publish_hub(day)
    if open_browser:
        open_report_browser(day)
    return status


def step_begin(day: date, step: str, *, detail: str = "") -> dict[str, Any]:
    status = load_status(day) or begin_run(day, open_browser=False)
    label = next((lbl for k, lbl, _ in _STEPS if k == step), step)
    pct = next((p for k, _, p in _STEPS if k == step), 0)
    status.update(
        {
            "status": "running",
            "current_step": step,
            "current_label": label,
            "detail": detail or label,
            "progress_pct": pct,
            "updated_at": now_iso(),
        }
    )
    publish_status(day, status)
    return status


def step_done(day: date, step: str, *, duration_ms: int = 0, detail: str = "") -> dict[str, Any]:
    status = load_status(day) or {}
    done = list(status.get("steps_done") or [])
    if step not in done:
        done.append(step)
    status["steps_done"] = done
    if duration_ms:
        durs = dict(status.get("step_durations_ms") or {})
        durs[step] = duration_ms
        status["step_durations_ms"] = durs
    if detail:
        status["detail"] = detail
    status["updated_at"] = now_iso()
    publish_status(day, status)
    return status


def touch_progress(day: date, *, detail: str, progress_pct: int | None = None) -> None:
    status = load_status(day)
    if not status or status.get("status") != "running":
        return
    status["detail"] = detail
    if progress_pct is not None:
        status["progress_pct"] = min(99, max(0, progress_pct))
    status["updated_at"] = now_iso()
    publish_status(day, status)


def finish_run(day: date, *, ok: bool = True, error: str = "") -> dict[str, Any]:
    status = load_status(day) or {}
    status.update(
        {
            "status": "ok" if ok else "fail",
            "progress_pct": 100 if ok else status.get("progress_pct", 0),
            "detail": "报告已生成" if ok else (error or "运行失败"),
            "error": error,
            "updated_at": now_iso(),
            "finished_at": now_iso(),
        }
    )
    publish_status(day, status)
    return status


def fail_run(day: date, step: str, message: str) -> dict[str, Any]:
    status = load_status(day) or {}
    status.update(
        {
            "status": "fail",
            "current_step": step,
            "detail": message,
            "error": message,
            "updated_at": now_iso(),
            "finished_at": now_iso(),
        }
    )
    publish_status(day, status)
    return status


__all__ = [
    "begin_run",
    "step_begin",
    "step_done",
    "touch_progress",
    "finish_run",
    "fail_run",
    "open_report_browser",
    "load_status",
    "publish_status",
    "write_run_status_js",
    "_STEPS",
]
