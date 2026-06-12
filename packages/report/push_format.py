"""微信推送摘要 HTML（迁自 ZXReport push_summary_format，补【观察】）。"""
from __future__ import annotations

import html
import re

from report.push_summary_merge import (
    clean_push_line,
    merge_push_summary_parts,
    parse_push_summary_sections,
    split_push_items,
)

_STOCK_SPLIT = re.compile(r"[、;]\s*(?=\d{6})")
_STOCK_HEAD = re.compile(r"^(\d{6})\s*(.+)$")
_STOCK_CODE_NAME = re.compile(r"^(\d{6})\s+([^：:|]+?)\s*[：:]\s*(.+)$")
_STOCK_PIPE = re.compile(
    r"^(?:[⛔★·\s]|大利空|大利好|利空|利好|轻空|轻多|待核|待核实)*\s*"
    r"(\d{6})\s*[·•]?\s*([^|]+?)(?:\s*\|\s*(.+))?$"
)
_STOCK_COLON_CODE = re.compile(r"^(\d{6})\s*:\s*(.+)$")
_GLOBAL_LABELS = frozenset({"环境", "仓位", "操作", "超预期", "9:15素材"})
_PIPE_ACTION_BEAR = frozenset({"减", "放弃"})
_PIPE_ACTION_BULL = frozenset({"试", "守"})
_BEAR_EVENT = re.compile(r"(?:^|\s)(大利空|利空|轻空)")
_BULL_EVENT = re.compile(r"(?:^|\s)(大利好|利好|轻多)")
_BEAR_DISCIPLINE = re.compile(r"(减仓|减持|回避|避险|放弃|偏弱|偏空)")
_BULL_DISCIPLINE = re.compile(r"(试仓|小仓试|轻仓试|偏强|偏多)")
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


def _normalize_stock_item(item: str) -> str:
    raw = clean_push_line(item)
    m = _STOCK_CODE_NAME.match(raw)
    if m:
        return f"{m.group(1)} {m.group(2).strip()}：{m.group(3).strip()}"
    m = _STOCK_PIPE.match(raw)
    if m:
        code, name, tail = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
        return f"{code} {name} | {tail}" if tail else f"{code} {name}"
    m = _STOCK_COLON_CODE.match(raw)
    if m:
        return f"{m.group(1)} {m.group(2).strip()}"
    return raw


def _split_stock_items(line: str) -> list[str]:
    s = clean_push_line(line).rstrip("。.")
    if not s:
        return []
    if not re.search(r"\d{6}", s):
        return [s]
    parts = _STOCK_SPLIT.split(s)
    items = [_normalize_stock_item(p.strip().rstrip("、；;")) for p in parts if p.strip()]
    return [it for it in items if it] or [s]


def _global_body_html(body: str) -> str:
    text = re.sub(r"\*\*", "", (body or "").strip())
    return _esc(text)


def _line_kind(line: str) -> tuple[str, str, str]:
    s = line.strip()
    if "|" in s:
        parts = [p.strip() for p in s.split("|") if p.strip()]
        if len(parts) >= 2 and parts[1] in _PIPE_ACTION_BEAR:
            return "bear", "#fff5f5", "#e74c3c"
        if len(parts) >= 2 and parts[1] in _PIPE_ACTION_BULL:
            return "bull", "#f0faf4", "#27ae60"
        head = parts[0] if parts else s
        if _BEAR_EVENT.search(head):
            return "bear", "#fff5f5", "#e74c3c"
        if _BULL_EVENT.search(head):
            return "bull", "#f0faf4", "#27ae60"
    if _BEAR_DISCIPLINE.search(s):
        return "bear", "#fff5f5", "#e74c3c"
    if _BULL_DISCIPLINE.search(s):
        return "bull", "#f0faf4", "#27ae60"
    return "neutral", "#fff", "#e4e8ec"


def _render_stock_card(chunks: list[str], item: str, *, accent: str) -> None:
    raw = _normalize_stock_item(item).rstrip("。.")
    m = _STOCK_HEAD.match(raw)
    bg, border = "#fff", "#e4e8ec"
    if m:
        code, rest = m.group(1), m.group(2).strip()
        _kind, bg, border = _line_kind(rest)
        body = _highlight_codes(rest)
        headline = (
            f'<span style="font-size:17px;font-weight:700;color:{accent};">{_esc(code)}</span>'
            f'<span style="font-size:17px;font-weight:600;color:#222;"> {body}</span>'
        )
    else:
        headline = f'<span style="font-size:16px;line-height:1.55;color:#222;">{_highlight_codes(raw)}</span>'
    chunks.append(
        f'<div style="margin:0 0 10px;padding:11px 13px;background:{bg};'
        f'border:1px solid {border};border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.04);">'
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
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#222;white-space:pre-wrap;">{_global_body_html(body)}</div>'
            "</div>"
        )
        return
    if label == "仓位" and slot != "midday":
        chunks.append(
            '<div style="margin-bottom:14px;padding:12px 14px;background:#eef6ff;border-radius:8px;border:1px solid #c8dff7;">'
            '<div style="font-size:13px;font-weight:700;color:#2980b9;letter-spacing:2px;margin-bottom:6px;">仓 位</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#1a5276;white-space:pre-wrap;">{_global_body_html(body)}</div>'
            "</div>"
        )
        return
    if label == "操作":
        chunks.append(
            '<div style="margin-top:14px;padding:12px 14px;background:#fff8e6;border-radius:8px;border:1px solid #f0d78c;">'
            '<div style="font-size:13px;font-weight:700;color:#b7950b;letter-spacing:2px;margin-bottom:6px;">操 作</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#333;white-space:pre-wrap;">{_global_body_html(body)}</div>'
            "</div>"
        )


def _render_surprise_block(chunks: list[str], body: str) -> None:
    items = split_push_items(body)
    if not items:
        return
    chunks.append(
        '<div style="margin-bottom:14px;padding:12px 14px;background:#fdf2e9;border-radius:8px;border:1px solid #f5cba7;">'
        '<div style="font-size:13px;font-weight:700;color:#d35400;letter-spacing:2px;margin-bottom:8px;">超 预 期</div>'
    )
    for item in items:
        chunks.append(
            f'<div style="font-size:16px;line-height:1.55;color:#333;margin:0 0 6px;">{_highlight_codes(item)}</div>'
        )
    chunks.append("</div>")


def _render_stock_tier(chunks: list[str], label: str, body: str) -> None:
    items = split_push_items(body)
    lines = [ln for ln in items if ln.strip() and ln.strip() not in ("无", "（无）")]
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
        if label == "超预期":
            _render_surprise_block(chunks, body)
            continue
        if label == "环境":
            _render_global_block(chunks, label, body, slot=slot)
            continue
        if label in _GLOBAL_LABELS:
            continue
        stock_sections.append((label, body))

    if slot == "midday":
        op_text = action
        if position and action:
            op_text = f"{clean_push_line(position)}\n{clean_push_line(action)}".strip()
        elif position:
            op_text = position
    else:
        op_text = action
    if op_text:
        _render_global_block(chunks, "操作", op_text, slot=slot)

    for label, body in stock_sections:
        _render_stock_tier(chunks, label, body)

    if time_line:
        chunks.append(
            f'<div style="margin-top:14px;font-size:14px;color:#999;text-align:right;">分析时刻 · {_esc(time_line)}</div>'
        )

    if len(chunks) == 1:
        chunks.append(f'<div style="font-size:17px;line-height:1.7;">{_highlight_codes(summary)}</div>')

    chunks.append("</div>")
    return "".join(chunks)


__all__ = ["format_wechat_push_html", "normalize_push_summary"]
