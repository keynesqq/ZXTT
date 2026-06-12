"""微信推送摘要 HTML（迁自 ZXReport push_summary_format，补【观察】）。"""
from __future__ import annotations

import html
import re

from report.push_summary_merge import merge_push_summary_parts, parse_push_summary_sections

_STOCK_SPLIT = re.compile(r"[、;]\s*(?=\d{6})")
_STOCK_HEAD = re.compile(r"^(\d{6})\s*(.+)$")
_GLOBAL_LABELS = frozenset({"环境", "仓位", "操作", "超预期", "9:15素材"})
_TIER_DISPLAY = {
    "我的": "我 的",
    "想买的": "想 买 的",
    "观察": "观 察",
    "其它": "其 它",
    "重点": "重 点",
}
_TIER_COLORS = {
    "我的": "#2980b9",
    "想买的": "#27ae60",
    "观察": "#d68910",
    "其它": "#7f8c8d",
    "重点": "#7f8c8d",
    "高度关注": "#d68910",
    "跌幅达到预期重点关注": "#c0392b",
}


def _esc(text: str) -> str:
    return html.escape((text or "").strip())


def _highlight_codes(text: str) -> str:
    s = _esc(text)
    return re.sub(r"(\d{6})", r'<strong style="font-weight:700;color:#111;">\1</strong>', s)


def _split_stock_items(line: str) -> list[str]:
    s = (line or "").strip().rstrip("。.")
    if not s:
        return []
    if not re.search(r"\d{6}", s):
        return [s]
    parts = _STOCK_SPLIT.split(s)
    items = [p.strip().rstrip("、；;") for p in parts if p.strip()]
    return items or [s]


def _render_stock_card(chunks: list[str], item: str, *, accent: str) -> None:
    raw = item.strip().rstrip("。.")
    m = _STOCK_HEAD.match(raw)
    if m:
        code, rest = m.group(1), m.group(2).strip()
        body = _highlight_codes(rest)
        headline = (
            f'<span style="font-size:17px;font-weight:700;color:{accent};">{_esc(code)}</span>'
            f'<span style="font-size:17px;font-weight:600;color:#222;"> {body}</span>'
        )
    else:
        headline = f'<span style="font-size:16px;line-height:1.55;color:#222;">{_highlight_codes(raw)}</span>'
    chunks.append(
        '<div style="margin:0 0 10px;padding:11px 13px;background:#fff;'
        'border:1px solid #e4e8ec;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.04);">'
        f'<div style="line-height:1.55;">{headline}</div></div>'
    )


def normalize_push_summary(text: str) -> str:
    s = (text or "").strip()
    s = s.replace("**", "")
    s = re.sub(r"(【[^】]+】)", r"\n\1 ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _render_global_block(chunks: list[str], label: str, body: str, *, slot: str) -> None:
    if not body.strip():
        return
    if label == "环境":
        chunks.append(
            '<div style="margin-bottom:14px;padding:12px 14px;background:#f4f6f8;border-radius:8px;">'
            '<div style="font-size:13px;font-weight:700;color:#666;letter-spacing:2px;margin-bottom:6px;">环 境</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#222;">{_esc(body)}</div>'
            "</div>"
        )
        return
    if label == "仓位" and slot != "midday":
        chunks.append(
            '<div style="margin-bottom:14px;padding:12px 14px;background:#eef6ff;border-radius:8px;border:1px solid #c8dff7;">'
            '<div style="font-size:13px;font-weight:700;color:#2980b9;letter-spacing:2px;margin-bottom:6px;">仓 位</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#1a5276;">{_esc(body)}</div>'
            "</div>"
        )
        return
    if label == "操作":
        chunks.append(
            '<div style="margin-top:14px;padding:12px 14px;background:#fff8e6;border-radius:8px;border:1px solid #f0d78c;">'
            '<div style="font-size:13px;font-weight:700;color:#b7950b;letter-spacing:2px;margin-bottom:6px;">操 作</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#333;">{_esc(body)}</div>'
            "</div>"
        )


def _render_stock_tier(chunks: list[str], label: str, body: str) -> None:
    lines = [ln.strip() for ln in body.splitlines() if ln.strip() and ln.strip() not in ("无", "（无）")]
    if not lines:
        return
    color = _TIER_COLORS.get(label, "#7f8c8d")
    display = _TIER_DISPLAY.get(label, label)
    chunks.append(
        f'<div style="font-size:13px;font-weight:700;color:{color};letter-spacing:2px;margin:14px 0 10px;">'
        f"{_esc(display)}</div>"
    )
    chunks.append(
        '<div style="margin:0 0 14px;padding:8px 6px 2px;background:#f8f9fb;border-radius:10px;">'
    )
    for line in lines:
        for item in _split_stock_items(line):
            _render_stock_card(chunks, item, accent=color)
    chunks.append("</div>")


def format_wechat_push_html(summary: str, *, slot: str = "evening") -> str:
    merged = merge_push_summary_parts(summary)
    time_line, sections = parse_push_summary_sections(merged)
    chunks: list[str] = [
        '<div style="font-size:17px;line-height:1.75;color:#1a1a1a;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
    ]

    position = ""
    action = ""
    stock_sections: list[tuple[str, str]] = []

    for label, body in sections:
        if label == "仓位":
            position = body
            if slot != "midday":
                _render_global_block(chunks, label, body, slot=slot)
            continue
        if label == "操作":
            action = body
            continue
        if label in _GLOBAL_LABELS:
            _render_global_block(chunks, label, body, slot=slot)
        else:
            stock_sections.append((label, body))

    for label, body in stock_sections:
        _render_stock_tier(chunks, label, body)

    if slot == "midday":
        op_text = action
        if position and action:
            op_text = f"{position}\n{action}".strip()
        elif position:
            op_text = position
    else:
        op_text = action
    if op_text:
        _render_global_block(chunks, "操作", op_text, slot=slot)

    if time_line:
        chunks.append(
            f'<div style="margin-top:14px;font-size:14px;color:#999;text-align:right;">分析时刻 · {_esc(time_line)}</div>'
        )

    if len(chunks) == 1:
        chunks.append(f'<div style="font-size:17px;line-height:1.7;">{_highlight_codes(summary)}</div>')

    chunks.append("</div>")
    return "".join(chunks)


__all__ = ["format_wechat_push_html", "normalize_push_summary"]
