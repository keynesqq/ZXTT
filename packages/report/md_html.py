"""Markdown / 推送摘要 → HTML（无第三方依赖）。"""
from __future__ import annotations

import html
import re

_H3_LINE = re.compile(r"^###\s+(.+)$")
_H2_LINE = re.compile(r"^##\s+(.+)$")
_H3 = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_STRONG_TAG = re.compile(r"</?strong>", re.I)
_CODE_IN_H3 = re.compile(r"^(\d{6})\s+(.+)$")
_PUSH_SECTION = re.compile(r"【([^】]+)】")
_LIST_ITEM = re.compile(r"^(\s*)[-*]\s+(.*)$")


def _h3_with_anchor(line: str) -> str:
    m = _CODE_IN_H3.match(line.strip())
    if m:
        code, name = m.group(1), m.group(2)
        return (
            f'<h3 class="stock-heading" id="stock-{code}">'
            f'<span class="code">{html.escape(code)}</span> {html.escape(name)}</h3>'
        )
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


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_list_tree(lines: list[str], start: int) -> tuple[list[tuple[str, list]], int]:
    nodes: list[tuple[str, list]] = []
    i = start
    base: int | None = None
    while i < len(lines):
        m = _LIST_ITEM.match(lines[i])
        if not m:
            break
        indent = _line_indent(lines[i])
        if base is None:
            base = indent
        if indent < base:
            break
        if indent > base:
            break
        content = _inline_emphasis(m.group(2).strip())
        i += 1
        children: list[tuple[str, list]] = []
        if i < len(lines):
            m2 = _LIST_ITEM.match(lines[i])
            if m2 and _line_indent(lines[i]) > base:
                children, i = _parse_list_tree(lines, i)
        nodes.append((content, children))
    return nodes, i


def _list_tree_to_html(nodes: list[tuple[str, list]]) -> str:
    if not nodes:
        return ""
    items: list[str] = []
    for content, children in nodes:
        child_html = _list_tree_to_html(children)
        if child_html:
            items.append(f"<li>{content}{child_html}</li>")
        else:
            items.append(f"<li>{content}</li>")
    return f'<ul class="prose-list">{"".join(items)}</ul>'


def _is_block_start(line: str) -> bool:
    s = line.strip()
    return bool(
        _H2_LINE.match(line)
        or _H3_LINE.match(line)
        or _LIST_ITEM.match(line)
        or s == "---"
    )


def markdown_to_html(text: str, *, stock_body: bool = False) -> str:
    lines = (text or "").splitlines()
    if not lines:
        return ""

    parts: list[str] = []
    stock_open = False
    para_buf: list[str] = []
    i = 0

    def flush_para() -> None:
        nonlocal para_buf
        if not para_buf:
            return
        body = "<br>".join(_inline_emphasis(ln) for ln in para_buf)
        parts.append(f"<p>{body}</p>")
        para_buf = []

    def close_stock_body() -> None:
        nonlocal stock_open
        if stock_body and stock_open:
            parts.append("</div>")
            stock_open = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        h2m = _H2_LINE.match(line)
        if h2m:
            flush_para()
            close_stock_body()
            parts.append(f'<h2 class="section-heading">{html.escape(h2m.group(1))}</h2>')
            i += 1
            continue

        h3m = _H3_LINE.match(line)
        if h3m:
            flush_para()
            close_stock_body()
            parts.append(_h3_with_anchor(h3m.group(1)))
            if stock_body:
                parts.append('<div class="stock-body">')
                stock_open = True
            i += 1
            continue

        if stripped == "---":
            flush_para()
            parts.append('<hr class="prose-hr">')
            i += 1
            continue

        if _LIST_ITEM.match(line):
            flush_para()
            nodes, i = _parse_list_tree(lines, i)
            parts.append(_list_tree_to_html(nodes))
            continue

        if stock_body and stock_open and para_buf and _is_block_start(line):
            flush_para()

        para_buf.append(stripped)
        i += 1

    flush_para()
    close_stock_body()
    return "\n".join(parts)


def markdown_sections_to_html(text: str, *, stock_body: bool = False) -> list[dict[str, str]]:
    """按 ## 标题拆成板块，供研判页 Tab 切换。"""
    raw = (text or "").strip()
    if not raw:
        return []
    matches = list(_H2.finditer(raw))
    if not matches:
        return [
            {
                "label": "全文",
                "title": "全文",
                "html": markdown_to_html(raw, stock_body=stock_body),
                "count": 0,
            }
        ]

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
                "html": markdown_to_html(chunk, stock_body=stock_body),
                "count": str(count),
            }
        )
    return sections


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
