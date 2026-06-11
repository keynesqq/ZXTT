"""AI 正文标题行内注入行情事实、正文末注入事件（与 snapshot_rows 同源）。"""
from __future__ import annotations

import html
import re
from typing import Any

_STOCK_H3 = re.compile(
    r'(<h3 class="stock-heading" id="stock-(\d{6})"[^>]*>)(.*?)(</h3>)',
    re.DOTALL,
)
_STOCK_BODY = re.compile(
    r'(<h3 class="stock-heading" id="stock-(\d{6})"[^>]*>.*?</h3>\s*<div class="stock-body">)(.*?)(</div>)',
    re.DOTALL,
)

_EVENT_BADGE = {
    "大利空": "badge-critical-bear",
    "大利好": "badge-critical-bull",
    "利空": "badge-bear",
    "利好": "badge-bull",
    "轻空": "badge-bear",
    "轻多": "badge-bull",
}

def snapshot_rows_by_code(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        code = str(row.get("code") or "").strip()
        if code:
            out[code] = row
    return out


def _pct_span(val: Any, *, label: str) -> str:
    try:
        v = float(val)
        cls = "up" if v > 0 else "down" if v < 0 else ""
        return f'<span class="fact fact-pct {cls}">{html.escape(label)}{v:+.2f}%</span>'
    except (TypeError, ValueError):
        return f'<span class="fact fact-muted">{html.escape(label)}—</span>'


def _price_span(val: Any, *, label: str) -> str:
    try:
        v = float(val)
        text = f"{v:.2f}".rstrip("0").rstrip(".")
        return f'<span class="fact fact-price">{html.escape(label)}{text}</span>'
    except (TypeError, ValueError):
        return f'<span class="fact fact-muted">{html.escape(label)}—</span>'


def _main_net_span(val: Any) -> str:
    try:
        v = float(val)
        cls = "up" if v > 0 else "down" if v < 0 else ""
        return f'<span class="fact fact-pct {cls}">主力{v:+.2f}亿</span>'
    except (TypeError, ValueError):
        return '<span class="fact fact-muted">主力—</span>'


def _event_badge(label: str, *, unverified: bool = False) -> str:
    base = str(label or "").split("·")[0]
    cls = _EVENT_BADGE.get(base, "badge-bear")
    out = f'<span class="badge {cls}">{html.escape(label)}</span>'
    if unverified or "待核实" in str(label):
        out += '<span class="badge badge-unverified">待核实</span>'
    return out


def stock_fact_strip_html(row: dict[str, Any] | None) -> str:
    if not row:
        return (
            '<span class="stock-fact-inline stock-fact-inline-missing">'
            '<span class="fact fact-muted">现— · 高— · 低— · 今— · 5日— · 主力— · 标签—</span></span>'
        )
    tags_html = "".join(
        f'<span class="tag-pill">{html.escape(str(t))}</span>' for t in (row.get("tags") or [])[:5]
    )
    if not tags_html:
        tags_html = '<span class="fact fact-muted">标签—</span>'
    parts = [
        _price_span(row.get("price"), label="现"),
        _price_span(row.get("high"), label="高"),
        _price_span(row.get("low"), label="低"),
        _pct_span(row.get("pct_chg"), label="今"),
        _pct_span(row.get("pct_5d"), label="5日"),
        _main_net_span(row.get("main_net_yi")),
        f'<span class="fact-tags">{tags_html}</span>',
    ]
    return f'<span class="stock-fact-inline">{"".join(parts)}</span>'


def stock_events_footer_html(row: dict[str, Any] | None) -> str:
    display = list((row or {}).get("events_display") or [])
    if display:
        items = []
        for ev in display[:3]:
            label = str(ev.get("label") or "")
            title = str(ev.get("title") or "")
            pub = str(ev.get("pub_date") or "")
            date_bit = f' <span class="event-date">{html.escape(pub)}</span>' if pub else ""
            items.append(
                f'<div class="stock-event-item">{_event_badge(label, unverified=bool(ev.get("unverified")))}'
                f'{html.escape(title)}{date_bit}</div>'
            )
        body = "".join(items)
    else:
        text = str((row or {}).get("events_label") or "无规则命中")
        muted = " stock-events-muted" if text == "无规则命中" else ""
        body = f'<span class="stock-events-text{muted}">{html.escape(text)}</span>'
    return (
        f'<div class="stock-events-foot">'
        f'<span class="stock-events-label">事件</span>{body}</div>'
    )


def inject_stock_fact_strips(prose_html: str, by_code: dict[str, dict[str, Any]]) -> str:
    if not prose_html or not by_code:
        return prose_html

    def repl(m: re.Match[str]) -> str:
        return m.group(1) + m.group(3) + stock_fact_strip_html(by_code.get(m.group(2))) + m.group(4)

    return _STOCK_H3.sub(repl, prose_html)


def inject_stock_events_footer(prose_html: str, by_code: dict[str, dict[str, Any]]) -> str:
    if not prose_html or not by_code:
        return prose_html

    def repl(m: re.Match[str]) -> str:
        return m.group(1) + m.group(3) + stock_events_footer_html(by_code.get(m.group(2))) + m.group(4)

    return _STOCK_BODY.sub(repl, prose_html)


__all__ = [
    "inject_stock_events_footer",
    "inject_stock_fact_strips",
    "snapshot_rows_by_code",
    "stock_events_footer_html",
    "stock_fact_strip_html",
]
