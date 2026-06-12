"""三报告共用 Web 中枢：状态聚合、落盘、打开浏览器。"""
from __future__ import annotations

import json
import webbrowser
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR, ROOT
from core.trading_calendar import previous_trading_day, today_cn

_HUB_DIR = DATA_DIR / "report_hub"
_REPORTS = ROOT / "reports"

_SLOTS: tuple[tuple[str, str, str, str], ...] = (
    ("evening_prev", "昨日作战卡", "", "daily_evening.html"),
    ("morning", "开盘核对卡", "morning_run", "daily_morning.html"),
    ("midday", "午间作战卡", "midday_run", "daily_midday.html"),
    ("evening", "晚间收盘卡", "evening_run", "daily_evening.html"),
)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _report_ready(day: date, filename: str) -> bool:
    return (_REPORTS / day.isoformat() / filename).is_file()


def _evening_prev_report_day(view_day: date) -> date:
    """昨收报告交易日 = 上一交易日（服务于 view_day 当日）。"""
    prev = previous_trading_day(view_day)
    return prev if prev else view_day


def _slot_run_status(view_day: date, run_dir: str) -> dict[str, Any]:
    return _load_json(DATA_DIR / run_dir / f"{view_day.isoformat()}.json") or {}


def _step_meta(slot_id: str) -> tuple[list[str], dict[str, str]]:
    if slot_id == "morning":
        return ["assemble", "ai", "render"], {
            "assemble": "拼装核对",
            "ai": "AI 合成",
            "render": "页面与推送",
        }
    return ["collect", "preprocess", "ai", "render"], {
        "collect": "采集",
        "preprocess": "预处理",
        "ai": "AI 合成",
        "render": "页面与推送",
    }


def _aggregate_slot(
    slot_id: str,
    label: str,
    run_dir: str,
    html_name: str,
    *,
    view_day: date,
) -> dict[str, Any]:
    if slot_id == "evening_prev":
        report_day = _evening_prev_report_day(view_day)
        run_st = _slot_run_status(report_day, "evening_run") if run_dir else {}
        report_ready = _report_ready(report_day, html_name)
        status = "ok" if report_ready else "idle"
        detail = f"昨收报告 · 交易日 {report_day.isoformat()}" if report_ready else "昨收未就绪"
    else:
        report_day = view_day
        run_st = _slot_run_status(view_day, run_dir) if run_dir else {}
        report_ready = _report_ready(report_day, html_name)
        status = str(run_st.get("status") or "")
        if not status:
            status = "ok" if report_ready else "idle"
        detail = run_st.get("detail") or ""
        if not detail:
            detail = "完成" if report_ready else "未运行"

    step_order, step_labels = _step_meta(slot_id if slot_id != "evening_prev" else "evening")
    return {
        "slot": slot_id,
        "label": label,
        "step_order": step_order,
        "step_labels": step_labels,
        "status": status,
        "progress_pct": run_st.get("progress_pct", 100 if status == "ok" else 0),
        "detail": detail,
        "current_step": run_st.get("current_step") or "",
        "current_label": run_st.get("current_label") or label,
        "started_at": run_st.get("started_at") or run_st.get("started_at_iso") or "",
        "finished_at": run_st.get("finished_at") or run_st.get("finished_at_iso") or "",
        "updated_at": run_st.get("updated_at") or "",
        "error": run_st.get("error") or "",
        "steps_done": run_st.get("steps_done") or [],
        "step_durations_ms": run_st.get("step_durations_ms") or {},
        "report_href": f"{report_day.isoformat()}/{html_name}" if report_ready else "",
        "report_ready": report_ready,
        "report_trade_date": report_day.isoformat(),
        "sla_ok": run_st.get("sla_ok"),
        "sla_ms": run_st.get("sla_ms"),
        "ai_duration_ms": run_st.get("ai_duration_ms"),
    }


def aggregate_hub(day: date) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    for slot_id, label, run_dir, html_name in _SLOTS:
        slots[slot_id] = _aggregate_slot(
            slot_id, label, run_dir, html_name, view_day=day
        )
    from report.system_status import aggregate_system_status

    return {
        "schema_version": 2,
        "trade_date": day.isoformat(),
        "updated_at": now_iso(),
        "slots": slots,
        "services": aggregate_system_status(day, slots),
    }


def publish_hub(day: date | None = None) -> Path:
    cal = day or today_cn()
    payload = aggregate_hub(cal)
    _HUB_DIR.mkdir(parents=True, exist_ok=True)
    json_path = _HUB_DIR / f"{cal.isoformat()}.json"
    atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2))

    from report.hub_html import build_hub_page, build_hub_status_js

    html = build_hub_page(payload)
    _REPORTS.mkdir(parents=True, exist_ok=True)
    index_path = _REPORTS / "index.html"
    atomic_write_text(index_path, html)
    atomic_write_text(_REPORTS / "hub_status.js", build_hub_status_js(payload))
    return json_path


def hub_url(day: date | None = None) -> str:
    cal = day or today_cn()
    index = (_REPORTS / "index.html").resolve()
    return f"{index.as_uri()}?date={cal.isoformat()}"


_BROWSER_MARKER = _HUB_DIR / "browser_session.json"


def _load_browser_session() -> dict[str, Any]:
    return _load_json(_BROWSER_MARKER) or {}


def _save_browser_session(cal: date, url: str, *, slot: str | None = None) -> None:
    _HUB_DIR.mkdir(parents=True, exist_ok=True)
    session = _load_browser_session()
    slots = dict(session.get("slots") or {}) if session.get("trade_date") == cal.isoformat() else {}
    if slot:
        slots[slot] = now_iso()
    atomic_write_text(
        _BROWSER_MARKER,
        json.dumps(
            {
                "trade_date": cal.isoformat(),
                "url": url,
                "opened_at": now_iso(),
                "slots": slots,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def _slot_opened_today(cal: date, slot: str) -> bool:
    session = _load_browser_session()
    if session.get("trade_date") != cal.isoformat():
        return False
    return slot in (session.get("slots") or {})


def open_hub(day: date | None = None, *, open_browser: bool = True, slot: str | None = None) -> str:
    cal = day or today_cn()
    publish_hub(cal)
    url = hub_url(cal)
    if not open_browser:
        return url
    if slot and _slot_opened_today(cal, slot):
        return url
    webbrowser.open(url, new=0)
    _save_browser_session(cal, url, slot=slot)
    return url


__all__ = ["aggregate_hub", "publish_hub", "open_hub", "hub_url", "_SLOTS"]
