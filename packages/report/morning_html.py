"""早盘开盘核对卡 HTML。"""
from __future__ import annotations

import html
from typing import Any

from report.md_html import markdown_to_html, push_summary_to_html

_MORNING_CSS = """
:root {
  --bg: #0c1118; --surface: #151d2b; --text: #e8eef6; --muted: #8fa3be;
  --accent: #4f8cff; --border: #2a384f; --up: #f05252; --down: #3ecf8e;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: "Segoe UI", "PingFang SC", sans-serif; line-height: 1.6; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 20px; }
h1 { margin: 0 0 8px; }
.sub { color: var(--muted); font-size: .9rem; margin-bottom: 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-bottom: 16px; }
table.data { width: 100%; border-collapse: collapse; font-size: .88rem; }
table.data th, table.data td { border-bottom: 1px solid var(--border); padding: 8px 6px; text-align: left; }
table.data th { color: var(--muted); font-weight: 600; }
.up { color: var(--up); } .down { color: var(--down); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 6px; background: #243044; font-size: .75rem; }
"""


def _pct_cls(v: float | None) -> str:
    if v is None:
        return ""
    return "up" if v > 0 else "down" if v < 0 else ""


def _pre_section(pre: dict[str, Any]) -> str:
    summary = pre.get("summary") or {}
    lines = [
        f"refresh {summary.get('refresh', 0)} · reuse {summary.get('reuse', 0)} · "
        f"no_new {summary.get('no_new', 0)} · failed {summary.get('failed', 0)}"
    ]
    if summary.get("no_new") and not summary.get("refresh"):
        lines.append("<p><strong>自昨晚 22:00 后无新公告/资讯</strong>（全池 no_new）</p>")
    return "\n".join(lines)


def _checks_table(rows: list[dict]) -> str:
    head = "<tr><th>代码</th><th>分组</th><th>预期</th><th>缺口%</th><th>9:20后</th><th>判定</th><th>素材</th></tr>"
    body_parts = []
    for r in rows:
        gap = r.get("end_gap")
        gap_s = f"{gap:.2f}" if isinstance(gap, (int, float)) else "—"
        body_parts.append(
            f"<tr><td>{html.escape(str(r.get('code') or ''))}</td>"
            f"<td>{html.escape(','.join(r.get('groups') or []))}</td>"
            f"<td>{html.escape(str(r.get('expected_open') or '—'))}</td>"
            f"<td class='{_pct_cls(gap if isinstance(gap, (int, float)) else None)}'>{gap_s}</td>"
            f"<td>{html.escape(str(r.get('shape_after_920') or ''))}</td>"
            f"<td><span class='badge'>{html.escape(str(r.get('verdict') or ''))}</span></td>"
            f"<td>{html.escape(str(r.get('pre_status') or ''))}</td></tr>"
        )
    return f"<table class='data'><thead>{head}</thead><tbody>{''.join(body_parts)}</tbody></table>"


def build_morning_page(rc: dict[str, Any]) -> str:
    pre = rc.get("morning_pre") or {}
    checks = rc.get("checks") or {}
    rows = checks.get("rows") or []
    title = "开盘核对卡"
    sub = f"集合竞价结束 · {rc.get('trade_date')} · 分析时刻 {rc.get('context_as_of') or '—'}"
    sla = ""
    if rc.get("sla_ms") is not None:
        sla = f" · SLA {rc.get('sla_ms')}ms {'✓' if rc.get('sla_ok') else '✗'}"
    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'/>",
        f"<title>{title}</title><style>{_MORNING_CSS}</style></head><body><div class='wrap'>",
        f"<h1>{title}</h1><p class='sub'>{html.escape(sub)}{sla}</p>",
        "<div class='card'><h2>9:15 素材</h2>",
        _pre_section(pre),
        "</div>",
        "<div class='card'><h2>核对表</h2>",
        _checks_table(rows),
        "</div>",
    ]
    if rc.get("ai_ok"):
        parts.append("<div class='card'><h2>推送摘要</h2>")
        parts.append(push_summary_to_html(rc.get("ai_summary_raw") or ""))
        parts.append("</div><div class='card'><h2>AI 研判</h2>")
        parts.append(markdown_to_html(rc.get("ai_body_raw") or ""))
        parts.append("</div>")
    elif rc.get("ai_error"):
        parts.append(f"<div class='card'><p>AI 未生成：{html.escape(str(rc.get('ai_error')))}</p></div>")
    parts.append("</div></body></html>")
    return "".join(parts)


__all__ = ["build_morning_page"]
