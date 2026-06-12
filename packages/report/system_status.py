"""系统服务状态聚合：供 Hub 仪表盘展示。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import from_unix_iso, now_iso
from core.paths import DATA_DIR

_SOURCE_LABELS: dict[str, str] = {
    "quote_query": "自选行情",
    "market_index": "大盘指数",
    "market_sentiment": "涨停生态",
    "market_flow": "主力资金",
    "announcement_query": "公告",
    "news_query": "资讯",
    "cls_finance": "财联社快讯",
    "cls_articles": "财联社文章",
}

_MARKET_SOURCES = ("quote_query", "market_index", "market_sentiment", "market_flow")
_FEED_SOURCES = ("announcement_query", "news_query", "cls_finance", "cls_articles")
_REPORT_SLOTS = ("morning", "midday", "evening")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_status(raw: str | None) -> str:
    st = (raw or "").strip().lower()
    if st in ("ok", "warn", "fail", "running", "idle"):
        return st
    return "idle"


def _source_status(rec: dict[str, Any]) -> str:
    st = rec.get("status")
    if isinstance(st, str) and st.strip():
        return _normalize_status(st)
    if rec.get("ok") is False:
        return "fail"
    if rec.get("ok") is True:
        return "ok"
    return "idle"


def _source_detail(name: str, rec: dict[str, Any]) -> str:
    msg = str(rec.get("message") or "").strip()
    if msg and msg not in ("null", "None"):
        return msg
    if name == "quote_query":
        cc = rec.get("code_count")
        rc = rec.get("row_count")
        if cc is not None:
            return f"{cc} 只" + (f" · {rc} 行" if rc is not None else "")
    if name in ("announcement_query", "news_query"):
        ic = rec.get("item_count")
        if ic is not None:
            return f"{ic} 只标的"
    if name == "market_index":
        ic = rec.get("index_count")
        slot = rec.get("latest_slot")
        if ic is not None:
            return f"{ic} 指数" + (f" · {slot}" if slot else "")
    if name == "market_flow":
        wc = rec.get("watchlist_count")
        slot = rec.get("latest_slot")
        if wc is not None:
            return f"{wc} 只" + (f" · {slot}" if slot else "")
    if name == "cls_articles":
        found = rec.get("articles_found")
        expected = rec.get("articles_expected")
        if found is not None and expected is not None:
            return f"{found}/{expected} 篇"
    at = rec.get("at_iso") or rec.get("updated_at_iso")
    return str(at or "").strip()


def _merge_collect_sources(day: date) -> tuple[dict[str, dict[str, Any]], str]:
    merged: dict[str, dict[str, Any]] = {}
    latest_at = ""
    for suffix in ("_midday", ""):
        path = DATA_DIR / "collect_manifest" / f"{day.isoformat()}{suffix}.json"
        manifest = _load_json(path)
        if not manifest:
            continue
        collected = str(manifest.get("collected_at_iso") or manifest.get("updated_at_iso") or "")
        if collected > latest_at:
            latest_at = collected
        for name, rec in (manifest.get("sources") or {}).items():
            if not isinstance(rec, dict):
                continue
            prev = merged.get(name)
            if prev is None:
                merged[name] = dict(rec)
                continue
            prev_at = str(prev.get("at_iso") or prev.get("updated_at_iso") or "")
            rec_at = str(rec.get("at_iso") or rec.get("updated_at_iso") or collected)
            if rec_at >= prev_at:
                merged[name] = dict(rec)
    return merged, latest_at


def _collect_running_slots(day: date) -> dict[str, dict[str, Any]]:
    running: dict[str, dict[str, Any]] = {}
    for slot, run_dir in (("midday", "midday_run"), ("evening", "evening_run")):
        run_st = _load_json(DATA_DIR / run_dir / f"{day.isoformat()}.json") or {}
        if run_st.get("status") == "running" and run_st.get("current_step") == "collect":
            running[slot] = run_st
    return running


def _collect_item(name: str, rec: dict[str, Any] | None, *, running: bool) -> dict[str, Any]:
    label = _SOURCE_LABELS.get(name, name)
    if running:
        return {
            "id": name,
            "label": label,
            "status": "running",
            "detail": "采集中",
            "updated_at": "",
        }
    if not rec:
        return {"id": name, "label": label, "status": "idle", "detail": "今日未采集", "updated_at": ""}
    return {
        "id": name,
        "label": label,
        "status": _source_status(rec),
        "detail": _source_detail(name, rec),
        "updated_at": str(rec.get("at_iso") or rec.get("updated_at_iso") or ""),
    }


_PHASE_LABELS: dict[str, str] = {
    "auction": "竞价",
    "morning": "上午",
    "afternoon": "下午",
}


def _phase_label(phase: str) -> str:
    return _PHASE_LABELS.get(phase, phase)


def _intraday_phase_detail(data: dict[str, Any]) -> str:
    parts: list[str] = []
    auc = data.get("auction_point_count")
    if auc:
        parts.append(f"竞价{auc}点")
    am = data.get("morning_point_count")
    if am:
        parts.append(f"上午{am}点")
    pm = data.get("afternoon_point_count")
    if pm:
        parts.append(f"下午{pm}点")
    if parts:
        return " · ".join(parts)
    phases = data.get("phases_done") or []
    if phases:
        return " · ".join(_phase_label(str(p)) for p in phases)
    pc = data.get("point_count") or data.get("merged_point_count")
    sc = data.get("stock_count")
    if pc is not None:
        return f"{pc} 点" + (f" · {sc} 只" if sc is not None else "")
    return ""


def _intraday_watch_item(day: date) -> dict[str, Any]:
    data = _load_json(DATA_DIR / "last_intraday_watch.json") or {}
    cal = str(data.get("calendar_date") or "")
    outcome = _normalize_status(str(data.get("outcome") or ""))
    if cal != day.isoformat() and outcome != "running":
        return {
            "id": "intraday",
            "label": "全天监控",
            "status": "idle",
            "detail": "今日未运行（含竞价+盘中）",
            "updated_at": "",
        }

    if outcome == "running":
        phase = _phase_label(str(data.get("last_phase") or "").strip())
        phase_detail = _intraday_phase_detail(data)
        detail = f"采集中 · {phase}" if phase else "采集中"
        if phase_detail:
            detail += f" · {phase_detail}"
    elif outcome == "ok":
        phase_detail = _intraday_phase_detail(data)
        detail = "完成" + (f" · {phase_detail}" if phase_detail else "")
    elif outcome == "fail":
        detail = str(data.get("message") or "失败")
    else:
        detail = str(data.get("message") or outcome or "未知")

    finished = data.get("finished_at")
    updated_at = ""
    if isinstance(finished, (int, float)) and finished > 0:
        updated_at = from_unix_iso(float(finished))
    elif isinstance(finished, str):
        updated_at = finished

    return {
        "id": "intraday",
        "label": "全天监控",
        "status": outcome,
        "detail": detail,
        "updated_at": updated_at,
    }


def _morning_pre_item(day: date) -> dict[str, Any]:
    data = _load_json(DATA_DIR / "morning_pre" / f"{day.isoformat()}.json")
    if not data:
        return {
            "id": "morning_pre",
            "label": "盘前增量",
            "status": "idle",
            "detail": "9:15 未采集",
            "updated_at": "",
        }
    by_code = data.get("by_code") or {}
    refresh = sum(1 for v in by_code.values() if isinstance(v, dict) and v.get("status") == "refresh")
    failed = sum(1 for v in by_code.values() if isinstance(v, dict) and v.get("status") == "failed")
    cc = data.get("code_count") or len(by_code)
    detail = f"{cc} 只"
    if refresh:
        detail += f" · 更新 {refresh}"
    if failed:
        detail += f" · 失败 {failed}"
    status = "fail" if failed else "ok"
    return {
        "id": "morning_pre",
        "label": "盘前增量",
        "status": status,
        "detail": detail,
        "updated_at": str(data.get("finished_at") or ""),
    }


def _report_item(slot_id: str, slot: dict[str, Any]) -> dict[str, Any]:
    st = _normalize_status(str(slot.get("status") or "idle"))
    detail = str(slot.get("detail") or slot.get("error") or "").strip()
    if not detail:
        detail = "完成" if slot.get("report_ready") else "未运行"
    step = str(slot.get("current_step") or "").strip()
    if st == "running" and step:
        labels = slot.get("step_labels") or {}
        step_label = labels.get(step) or step
        detail = f"{step_label} · {detail}" if detail else step_label
    return {
        "id": slot_id,
        "label": str(slot.get("label") or slot_id),
        "status": st,
        "detail": detail,
        "updated_at": str(slot.get("updated_at") or slot.get("finished_at") or ""),
        "progress_pct": slot.get("progress_pct"),
    }


def _group_status(items: list[dict[str, Any]]) -> str:
    statuses = [_normalize_status(str(it.get("status") or "idle")) for it in items]
    if "fail" in statuses:
        return "fail"
    if "running" in statuses:
        return "running"
    if "warn" in statuses:
        return "warn"
    if statuses and all(s == "ok" for s in statuses):
        return "ok"
    if any(s == "ok" for s in statuses):
        return "warn"
    return "idle"


def _overall_status(groups: list[dict[str, Any]]) -> str:
    statuses = [_normalize_status(str(g.get("status") or "idle")) for g in groups]
    if "fail" in statuses:
        return "fail"
    if "running" in statuses:
        return "running"
    if "warn" in statuses:
        return "warn"
    if statuses and all(s == "ok" for s in statuses):
        return "ok"
    if any(s in ("ok", "warn") for s in statuses):
        return "warn"
    return "idle"


def aggregate_system_status(day: date, slots: dict[str, Any] | None = None) -> dict[str, Any]:
    slots = slots or {}
    sources, collect_updated = _merge_collect_sources(day)
    collect_running = _collect_running_slots(day)
    collect_active = bool(collect_running)

    live_items = [_intraday_watch_item(day)]
    market_items = [
        _collect_item(name, sources.get(name), running=collect_active)
        for name in _MARKET_SOURCES
    ]
    feed_items = [
        _collect_item(name, sources.get(name), running=collect_active)
        for name in _FEED_SOURCES
    ]
    feed_items.append(_morning_pre_item(day))
    report_items = [_report_item(sid, slots.get(sid) or {}) for sid in _REPORT_SLOTS]

    groups = [
        {"id": "live", "label": "实时采集", "items": live_items},
        {"id": "market", "label": "行情数据", "items": market_items},
        {"id": "feeds", "label": "资讯公告", "items": feed_items},
        {"id": "reports", "label": "报告生成", "items": report_items},
    ]
    for group in groups:
        group["status"] = _group_status(group["items"])

    return {
        "overall": _overall_status(groups),
        "collect_updated_at": collect_updated,
        "groups": groups,
        "updated_at": now_iso(),
    }


__all__ = ["aggregate_system_status"]
