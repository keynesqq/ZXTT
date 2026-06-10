"""第 4 步 4C · 解析并落盘 expectations（stocks[code]）。"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR

_SECTIONS = (
    (re.compile(r"^##\s*我的\s*[·•]"), "holding", "持仓"),
    (re.compile(r"^##\s*想买的\s*[·•]"), "candidate", "候选"),
    (re.compile(r"^##\s*观察\s*[·•]"), "watch_right", "观察"),
    (re.compile(r"^##\s*其它\s*[·•]"), "theme_other", "其它"),
)
_SECTION_STOP = re.compile(
    r"^##\s*(情绪|主线|明日|跟踪|L1|L2|推送)"
)
_HEADING = re.compile(r"^###\s+(\d{6})\s+(.+)$")
_FIELD = re.compile(r"^\*\*(.+?)\*\*[：:]\s*(.+)$")
_EXP_DIR = DATA_DIR / "expectations"


def _parse_body_sections(text: str) -> dict[str, dict[str, Any]]:
    current_stance = ""
    current_label = ""
    current_block: list[str] = []
    sections: list[tuple[str, str, str]] = []

    for line in (text or "").splitlines():
        if any(pat.search(line) for pat, _, _ in _SECTIONS):
            if current_stance and current_block:
                sections.append((current_stance, current_label, "\n".join(current_block)))
            for pat, stance, label in _SECTIONS:
                if pat.search(line):
                    current_stance, current_label = stance, label
                    current_block = []
                    break
            continue
        if _SECTION_STOP.search(line):
            if current_stance and current_block:
                sections.append((current_stance, current_label, "\n".join(current_block)))
            current_stance, current_block = "", []
            continue
        if current_stance:
            current_block.append(line)
    if current_stance and current_block:
        sections.append((current_stance, current_label, "\n".join(current_block)))

    out: dict[str, dict[str, Any]] = {}
    for stance, stance_label, block in sections:
        code = ""
        name = ""
        fields: dict[str, str] = {}

        def flush() -> None:
            nonlocal code, name, fields
            if not code:
                return
            short_exp = (
                fields.get("短线预期")
                or fields.get("短线预期（明日）")
                or fields.get("次日开盘情景")
                or fields.get("持仓操作")
                or fields.get("买点评估")
                or ""
            )
            out[code] = {
                "code": code,
                "name": name.strip(),
                "primary_stance": stance,
                "stance_label": stance_label,
                "short_expectation": short_exp.strip(),
                "expected_open": fields.get("次日开盘情景") or fields.get("开盘情景") or "",
                "discipline": (fields.get("失效条件") or fields.get("纪律动作") or "").strip(),
                "message_net": fields.get("消息 net") or "",
                "check_925": fields.get("9:25 核对要点") or "",
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
        "slot": "evening",
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
    path = _EXP_DIR / f"{target_date.isoformat()}.json"
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
