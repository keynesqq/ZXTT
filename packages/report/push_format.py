"""微信推送摘要 HTML（迁自 ZXReport push_summary_format，补【观察】）。"""
from __future__ import annotations

import html
import re

_SECTION_ENV = re.compile(r"^【环境】\s*(.*)$")
_SECTION_MY = re.compile(r"^【我的】\s*(.*)$")
_SECTION_BUY = re.compile(r"^【想买的】\s*(.*)$")
_SECTION_WATCH = re.compile(r"^【观察】\s*(.*)$")
_SECTION_OTHER = re.compile(r"^【其它】\s*(.*)$")
_SECTION_FOCUS = re.compile(r"^【重点】\s*(.*)$")
_SECTION_ACTION = re.compile(r"^【操作】\s*(.*)$")
_SECTION_POSITION = re.compile(r"^【仓位】\s*(.*)$")
_TIME_LINE = re.compile(r"^\*\*分析时刻\*\*[：:]\s*(.+)$")
_STOCK_SPLIT = re.compile(r"[、;]\s*(?=\d{6})")
_STOCK_HEAD = re.compile(r"^(\d{6})\s*(.+)$")

_TIER_SECTIONS = (
    ("my", _SECTION_MY, "我的"),
    ("buy", _SECTION_BUY, "想买的"),
    ("watch", _SECTION_WATCH, "观察"),
    ("other", _SECTION_OTHER, "其它"),
    ("focus", _SECTION_FOCUS, "重点"),
)


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


def _parse_sections(text: str) -> dict[str, object]:
    env = ""
    action = ""
    position = ""
    time_line = ""
    buckets: dict[str, list[str]] = {k: [] for k, _, _ in _TIER_SECTIONS}
    mode: str | None = None

    for raw in normalize_push_summary(text).splitlines():
        line = raw.strip()
        if not line:
            continue

        m = _SECTION_ENV.match(line)
        if m:
            env = m.group(1).strip()
            mode = None
            continue

        matched_tier = False
        for key, pattern, _label in _TIER_SECTIONS:
            m = pattern.match(line)
            if m:
                mode = key
                tail = m.group(1).strip()
                if tail and tail not in ("无", "（无）"):
                    buckets[key].append(tail)
                matched_tier = True
                break
        if matched_tier:
            continue

        m = _SECTION_ACTION.match(line)
        if m:
            action = m.group(1).strip()
            mode = None
            continue

        m = _SECTION_POSITION.match(line)
        if m:
            position = m.group(1).strip()
            mode = None
            continue

        m = _TIME_LINE.match(line)
        if m:
            time_line = m.group(1).strip()
            mode = None
            continue

        if "分析时刻" in line:
            time_line = re.sub(r"^\*+|\*+$", "", line.replace("分析时刻：", "").replace("分析时刻:", "")).strip()
            mode = None
            continue

        if mode and mode in buckets:
            if line in ("无", "（无）"):
                mode = None
                continue
            buckets[mode].append(line.lstrip("-•* ").strip())
            continue

        if line.startswith(("⛔", "★", "·")):
            buckets["focus"].append(line.lstrip("-• ").strip())
            continue

        if line.startswith(("-", "•", "*")):
            content = line.lstrip("-•* ").strip()
            if not env and not any(buckets.values()) and not action:
                env = content
            else:
                buckets["focus"].append(content)
            continue

        if not env:
            env = line
        else:
            buckets["focus"].append(line)

    return {
        "env": env,
        "my": buckets["my"],
        "buy": buckets["buy"],
        "watch": buckets["watch"],
        "other": buckets["other"],
        "focus": buckets["focus"],
        "action": action,
        "position": position,
        "time": time_line,
    }


def _render_tier_blocks_wechat(chunks: list[str], sec: dict[str, object]) -> None:
    tier_defs = (
        ("my", "我 的", "#2980b9"),
        ("buy", "想 买 的", "#27ae60"),
        ("watch", "观 察", "#d68910"),
        ("other", "其 它", "#7f8c8d"),
        ("focus", "重 点", "#7f8c8d"),
    )
    for key, label, color in tier_defs:
        lines = sec.get(key) or []
        if not lines:
            continue
        chunks.append(
            f'<div style="font-size:13px;font-weight:700;color:{color};letter-spacing:2px;margin:14px 0 10px;">{label}</div>'
        )
        chunks.append(
            f'<div style="margin:0 0 14px;padding:8px 6px 2px;background:#f8f9fb;border-radius:10px;">'
        )
        for line in lines:
            for item in _split_stock_items(str(line)):
                _render_stock_card(chunks, item, accent=color)
        chunks.append("</div>")


def _midday_action_text(sec: dict[str, object]) -> str:
    action = str(sec.get("action") or "").strip()
    position = str(sec.get("position") or "").strip()
    if position and action:
        return f"{position}\n{action}".strip()
    return position or action


def format_wechat_push_html(summary: str, *, slot: str = "evening") -> str:
    sec = _parse_sections(summary)
    chunks: list[str] = [
        '<div style="font-size:17px;line-height:1.75;color:#1a1a1a;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
    ]

    env = str(sec["env"])
    if env:
        chunks.append(
            '<div style="margin-bottom:14px;padding:12px 14px;background:#f4f6f8;border-radius:8px;">'
            '<div style="font-size:13px;font-weight:700;color:#666;letter-spacing:2px;margin-bottom:6px;">环 境</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#222;">{_esc(env)}</div>'
            "</div>"
        )

    position = str(sec.get("position") or "")
    if position and slot != "midday":
        chunks.append(
            '<div style="margin-bottom:14px;padding:12px 14px;background:#eef6ff;border-radius:8px;border:1px solid #c8dff7;">'
            '<div style="font-size:13px;font-weight:700;color:#2980b9;letter-spacing:2px;margin-bottom:6px;">仓 位</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#1a5276;">{_esc(position)}</div>'
            "</div>"
        )

    _render_tier_blocks_wechat(chunks, sec)

    action = _midday_action_text(sec) if slot == "midday" else str(sec["action"])
    if action:
        chunks.append(
            '<div style="margin-top:14px;padding:12px 14px;background:#fff8e6;border-radius:8px;border:1px solid #f0d78c;">'
            '<div style="font-size:13px;font-weight:700;color:#b7950b;letter-spacing:2px;margin-bottom:6px;">操 作</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.55;color:#333;">{_esc(action)}</div>'
            "</div>"
        )

    time_line = str(sec["time"])
    if time_line:
        chunks.append(
            f'<div style="margin-top:14px;font-size:14px;color:#999;text-align:right;">分析时刻 · {_esc(time_line)}</div>'
        )

    if len(chunks) == 1:
        chunks.append(f'<div style="font-size:17px;line-height:1.7;">{_highlight_codes(summary)}</div>')

    chunks.append("</div>")
    return "".join(chunks)


__all__ = ["format_wechat_push_html", "normalize_push_summary"]
