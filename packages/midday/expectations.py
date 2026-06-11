"""第 4 步 4C · 解析并落盘午后 expectations。"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR

_GROUP_SECTION = re.compile(r"^##\s+(.+)$")
_SKIP_SECTIONS = frozenset({"推送摘要"})
_SECTION_STOP = re.compile(r"^##\s*(情绪|主线|午后|下午|跟踪|L1|L2|推送)")
_HEADING = re.compile(r"^###\s+(\d{6})\s+(.+)$")
_FIELD = re.compile(r"^\*\*(.+?)\*\*[：:]\s*(.+)$")
_EXP_DIR = DATA_DIR / "expectations"


def _parse_body_sections(text: str) -> dict[str, dict[str, Any]]:
    current_group = ""
    current_block: list[str] = []
    sections: list[tuple[str, str]] = []

    for line in (text or "").splitlines():
        gm = _GROUP_SECTION.match(line.strip())
        if gm:
            title = gm.group(1).strip()
            if title in _SKIP_SECTIONS:
                continue
            if current_group and current_block:
                sections.append((current_group, "\n".join(current_block)))
            current_group = title
            current_block = []
            continue
        if _SECTION_STOP.search(line):
            if current_group and current_block:
                sections.append((current_group, "\n".join(current_block)))
            current_group, current_block = "", []
            continue
        if current_group:
            current_block.append(line)
    if current_group and current_block:
        sections.append((current_group, "\n".join(current_block)))

    out: dict[str, dict[str, Any]] = {}
    for group_name, block in sections:
        code = ""
        name = ""
        fields: dict[str, str] = {}

        def flush() -> None:
            nonlocal code, name, fields
            if not code:
                return
            short_exp = (
                fields.get("下午提示")
                or fields.get("短线预期")
                or fields.get("午后开盘情景")
                or fields.get("持仓操作")
                or fields.get("买点评估")
                or ""
            )
            out[code] = {
                "code": code,
                "name": name.strip(),
                "primary_group": group_name,
                "group_label": group_name,
                "primary_stance": group_name,
                "stance_label": group_name,
                "short_expectation": short_exp.strip(),
                "afternoon_open_scenario": fields.get("午后开盘情景")
                or fields.get("午后情景")
                or fields.get("开盘情景")
                or "",
                "afternoon_hint": fields.get("下午提示") or "",
                "discipline": (fields.get("失效条件") or fields.get("纪律动作") or "").strip(),
                "message_net": fields.get("消息 net") or "",
                "check_1300": fields.get("13:00 核对要点") or fields.get("午后核对要点") or "",
                "ai_fields": dict(fields),
                "critical": [],
            }
            code, name, fields = "", "", {}

        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            hm = _HEADING.match(line)
            if hm:
                flush()
                code, name = hm.group(1), hm.group(2)
                continue
            fm = _FIELD.match(line)
            if fm and code:
                fields[fm.group(1).strip()] = fm.group(2).strip()
        flush()
    return out


def enrich_expectations(
    stocks: dict[str, dict[str, Any]],
    ctx: dict[str, Any],
    *,
    missing_codes: list[str],
) -> dict[str, Any]:
    by_code = ctx.get("by_code") or {}
    events = ctx.get("events_by_code") or {}
    for code, row in stocks.items():
        lb = (by_code.get(code) or {}).get("local_block") or {}
        row.setdefault("groups", lb.get("groups") or [])
        ev = events.get(code) or {}
        critical = []
        for bucket in ("critical_bear", "critical_bull"):
            for item in ev.get(bucket) or []:
                critical.append(item.get("title", ""))
        row["critical"] = critical
    meta_src = ctx.get("market_local") or {}
    return {
        "schema_version": 1,
        "source_trade_date": (ctx.get("meta") or {}).get("trade_date"),
        "saved_at": now_iso(),
        "context_as_of": (ctx.get("meta") or {}).get("context_as_of"),
        "slot": "midday",
        "session_label": "午间休市",
        "meta": {
            "l1_axes": meta_src.get("l1"),
            "l2_mainlines": (meta_src.get("l2") or {}).get("mainlines") or [],
            "constraints_applied": bool(meta_src.get("constraints")),
        },
        "stocks": stocks,
        "missing_codes": missing_codes,
        "codes_analysis_order": [s.get("code") for s in (ctx.get("prompt") or {}).get("stocks") or [] if s.get("code")],
    }


def save_expectations(payload: dict[str, Any], target_date: date) -> Path:
    path = _EXP_DIR / f"{target_date.isoformat()}_midday.json"
    payload = dict(payload)
    payload["target_trade_date"] = target_date.isoformat()
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def extract_and_save_expectations(
    body: str,
    ctx: dict[str, Any],
    *,
    target_date: date,
    missing_codes: list[str],
) -> Path | None:
    stocks = _parse_body_sections(body)
    if not stocks:
        return None
    payload = enrich_expectations(stocks, ctx, missing_codes=missing_codes)
    return save_expectations(payload, target_date)


__all__ = ["extract_and_save_expectations", "save_expectations", "_parse_body_sections"]
