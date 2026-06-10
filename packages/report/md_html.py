"""Markdown / 推送摘要 → HTML（无第三方依赖）。"""
from __future__ import annotations

import html
import re

_H3 = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_STRONG_TAG = re.compile(r"</?strong>", re.I)
_CODE_IN_H3 = re.compile(r"^(\d{6})\s+(.+)$")
_PUSH_SECTION = re.compile(r"【([^】]+)】")


def _h3_with_anchor(line: str) -> str:
    m = _CODE_IN_H3.match(line.strip())
    if m:
        code, name = m.group(1), m.group(2)
        return f'<h3 class="stock-heading" id="stock-{code}"><span class="code">{html.escape(code)}</span> {html.escape(name)}</h3>'
    return f"<h3>{html.escape(line)}</h3>"


def _inline_emphasis(text: str) -> str:
    out: list[str] = []
    last = 0
    for m in _BOLD.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        out.append(f"<strong>{html.escape(m.group(1))}</strong>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return re.sub(r"\*\*", "", "".join(out))


def markdown_sections_to_html(text: str) -> list[dict[str, str]]:
    """按 ## 标题拆成板块，供研判页 Tab 切换。"""
    raw = (text or "").strip()
    if not raw:
        return []
    matches = list(_H2.finditer(raw))
    if not matches:
        return [{"label": "全文", "title": "全文", "html": markdown_to_html(raw), "count": 0}]

    sections: list[dict[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        chunk = raw[start:end].strip()
        label = title.split("·", 1)[0].strip() if "·" in title else title
        count = len(re.findall(r"^###\s+", chunk, re.MULTILINE))
        sections.append(
            {
                "label": label,
                "title": title,
                "html": markdown_to_html(chunk),
                "count": str(count),
            }
        )
    return sections


def markdown_to_html(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = _H3.sub(lambda m: _h3_with_anchor(m.group(1)), raw)
    raw = _H2.sub(lambda m: f'<h2 class="section-heading">{html.escape(m.group(1))}</h2>', raw)
    raw = _BOLD.sub(lambda m: f"<strong>{html.escape(m.group(1))}</strong>", raw)
    parts = []
    for para in re.split(r"\n\s*\n", raw):
        para = para.strip()
        if not para:
            continue
        if para.startswith("<h"):
            parts.append(para)
        elif _STRONG_TAG.search(para):
            lines = "<br>".join(para.splitlines())
            parts.append(f"<p>{lines}</p>")
        else:
            lines = "<br>".join(_inline_emphasis(ln) for ln in para.splitlines())
            parts.append(f"<p>{lines}</p>")
    return "\n".join(parts)


def push_summary_to_html(text: str) -> str:
    """微信推送摘要：按【环境】【我的】等分段渲染。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    if not _PUSH_SECTION.search(raw):
        return f'<div class="push-summary-fallback">{markdown_to_html(raw)}</div>'

    parts: list[str] = []
    pos = 0
    for m in _PUSH_SECTION.finditer(raw):
        if m.start() > pos:
            chunk = raw[pos : m.start()].strip()
            if chunk:
                parts.append(f'<p class="push-lead">{_inline_emphasis(chunk)}</p>')
        label = m.group(1)
        pos = m.end()
        next_m = _PUSH_SECTION.search(raw, pos)
        end = next_m.start() if next_m else len(raw)
        body = raw[pos:end].strip()
        pos = end
        parts.append(
            f'<div class="push-row"><span class="push-label">【{html.escape(label)}】</span>'
            f'<span class="push-body">{_inline_emphasis(body)}</span></div>'
        )
    return '<div class="push-summary">' + "".join(parts) + "</div>"


__all__ = ["markdown_to_html", "markdown_sections_to_html", "push_summary_to_html"]
