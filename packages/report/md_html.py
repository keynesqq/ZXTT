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
_SECTION_HEAD = re.compile(
    r"^(\*\*)?【([^】]+)】(\*\*)?(?:\s*(.*))?$",
    re.MULTILINE,
)
_PUSH_GLOBAL = frozenset({"环境", "仓位", "操作", "9:15素材", "超预期"})
_PUSH_PORTFOLIO = frozenset({"我的", "想买的"})
_PUSH_SUMMARY_HIDDEN = frozenset({"9:15素材"})
_PUSH_SECTION_ORDER = (
    "环境",
    "仓位",
    "超预期",
    "操作",
    "我的",
    "想买的",
    "观察",
    "其它",
    "重点",
)
_ANALYSIS_TIME = re.compile(r"\*\*分析时刻\*\*[：:]\s*(.+)$", re.MULTILINE)
_ANALYSIS_TIME_PLAIN = re.compile(r"^分析时刻[：:]\s*(.+)$", re.MULTILINE)
_STOCK_CODE_LEAD = re.compile(r"^(\d{6})\s+(.+)$")
_PUSH_ITEM_CODE = re.compile(r"^\*\*(\d{6})\s+([^*]+)\*\*[：:]\s*(.*)$")
_PUSH_ITEM_NAME_CODE = re.compile(r"^\*\*([^*（]+)（(\d{6})）\*\*[：:]\s*(.*)$")
_LIST_ITEM = re.compile(r"^(\s*)[-*]\s+(.*)$")
_LIST_BULLET = re.compile(r"^[-*]\s+(.*)$", re.MULTILINE)


def _h3_with_anchor(line: str, *, as_summary: bool = False) -> str:
    m = _CODE_IN_H3.match(line.strip())
    if m:
        code, name = m.group(1), m.group(2)
        tag = "summary" if as_summary else "h3"
        cls = "stock-heading"
        return (
            f'<{tag} class="{cls}" id="stock-{code}">'
            f'<span class="code">{html.escape(code)}</span> {html.escape(name)}</{tag}>'
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
            parts.append("</div></details>")
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
            if stock_body:
                parts.append('<details class="stock-block">')
                parts.append(_h3_with_anchor(h3m.group(1), as_summary=True))
                parts.append('<div class="stock-body">')
                stock_open = True
            else:
                parts.append(_h3_with_anchor(h3m.group(1)))
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


def _push_section_kind(label: str) -> str:
    if label in _PUSH_GLOBAL:
        return "global"
    if label in _PUSH_PORTFOLIO:
        return "portfolio"
    return "watch"


def _extract_analysis_time(text: str) -> tuple[str, str]:
    m = _ANALYSIS_TIME.search(text)
    if m:
        time_text = m.group(1).strip()
        cleaned = (text[: m.start()] + text[m.end() :]).strip()
        return cleaned, time_text
    lines: list[str] = []
    time_text = ""
    for line in text.splitlines():
        pm = _ANALYSIS_TIME_PLAIN.match(line.strip())
        if pm:
            time_text = pm.group(1).strip()
            continue
        lines.append(line)
    return "\n".join(lines).strip(), time_text


def _parse_push_sections(raw: str) -> tuple[str, str, list[tuple[str, str]]]:
    text, analysis_time = _extract_analysis_time(raw.strip())
    text = re.sub(r"\n---\s*$", "", text).strip()
    matches = list(_SECTION_HEAD.finditer(text))
    if not matches:
        return text, analysis_time, []
    lead = text[: matches[0].start()].strip()
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        label = m.group(2).strip()
        inline = (m.group(4) or "").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if inline:
            body = f"{inline}\n{body}".strip() if body else inline
        if body == "---":
            body = ""
        sections.append((label, body))
    return lead, analysis_time, sections


def extract_push_section_body(text: str, label: str) -> str:
    """取推送摘要某段正文（仅行首【label】）。"""
    _, _, sections = _parse_push_sections((text or "").strip())
    for sec_label, body in _prepare_push_sections(sections):
        if sec_label == label:
            return body.strip()
    return ""


def _apply_label_aliases(
    sections: list[tuple[str, str]],
    aliases: dict[str, str] | None,
) -> list[tuple[str, str]]:
    if not aliases:
        return sections
    merged: dict[str, str] = {}
    order: list[str] = []
    for label, body in sections:
        mapped = aliases.get(label, label)
        text = (body or "").strip()
        if mapped in merged:
            if text:
                prev = merged[mapped].strip()
                merged[mapped] = f"{prev}\n{text}".strip() if prev else text
        else:
            order.append(mapped)
            merged[mapped] = text
    return [(label, merged[label]) for label in order]


def _prepare_push_sections(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    order_idx = {name: i for i, name in enumerate(_PUSH_SECTION_ORDER)}
    default = len(_PUSH_SECTION_ORDER)
    kept = [(label, body) for label, body in sections if label not in _PUSH_SUMMARY_HIDDEN]
    return sorted(kept, key=lambda item: order_idx.get(item[0], default))


def _split_push_items(body: str) -> list[str]:
    items: list[str] = []
    has_bullets = any(_LIST_BULLET.match(ln.strip()) for ln in body.splitlines() if ln.strip())
    if has_bullets:
        for line in body.splitlines():
            m = _LIST_BULLET.match(line.strip())
            if not m:
                continue
            content = m.group(1).strip()
            if content and content != "---":
                items.append(content)
        return items
    for line in body.splitlines():
        line = line.strip()
        if not line or line == "---":
            continue
        for seg in re.split(r"[；;]", line):
            seg = seg.strip()
            if seg:
                items.append(seg)
    return items


def _strip_analysis_time(body: str) -> tuple[str, str]:
    return _extract_analysis_time(body)


def _push_stock_li(code: str, text: str) -> str:
    return (
        f'<li class="push-stock-item">'
        f'<span class="push-code">{html.escape(code)}</span>'
        f'<span class="push-stock-text">{_inline_emphasis(text)}</span></li>'
    )


def _format_push_item(item: str) -> str:
    s = item.strip()
    if not s:
        return ""
    m = _PUSH_ITEM_CODE.match(s)
    if m:
        code, name, rest = m.group(1), m.group(2).strip(), m.group(3).strip()
        text = f"{name}：{rest}" if rest else name
        return _push_stock_li(code, text)
    m = _PUSH_ITEM_NAME_CODE.match(s)
    if m:
        name, code, rest = m.group(1).strip(), m.group(2), m.group(3).strip()
        text = f"{name}：{rest}" if rest else name
        return _push_stock_li(code, text)
    m = _STOCK_CODE_LEAD.match(s)
    if m:
        return _push_stock_li(m.group(1), m.group(2).strip())
    return f'<li class="push-stock-item"><span class="push-stock-text">{_inline_emphasis(s)}</span></li>'


def _format_push_body(label: str, body: str) -> tuple[str, str]:
    body, time_text = _strip_analysis_time(body)
    kind = _push_section_kind(label)
    if kind == "global":
        if _LIST_BULLET.search(body):
            inner = markdown_to_html(body)
            return f'<div class="push-section-body push-section-prose">{inner}</div>', time_text
        return f'<div class="push-section-body">{_inline_emphasis(body)}</div>', time_text
    items = [it for it in _split_push_items(body) if it.strip() and it.strip() != "---"]
    if items:
        lis = "".join(x for it in items if (x := _format_push_item(it)))
        if lis:
            return f'<ul class="push-stock-list">{lis}</ul>', time_text
    return f'<div class="push-section-body">{_inline_emphasis(body)}</div>', time_text


def push_summary_to_html(text: str, *, label_aliases: dict[str, str] | None = None) -> str:
    """微信推送摘要：按【环境】【我的】等分段渲染。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    if not _SECTION_HEAD.search(raw):
        return f'<div class="push-summary-fallback">{markdown_to_html(raw)}</div>'

    lead, analysis_time, sections = _parse_push_sections(raw)
    sections = _apply_label_aliases(sections, label_aliases)
    sections = _prepare_push_sections(sections)
    sections_html: list[str] = []
    if lead:
        sections_html.append(f'<p class="push-lead">{_inline_emphasis(lead)}</p>')
    for label, body in sections:
        if not body and label not in _PUSH_GLOBAL and label not in _PUSH_PORTFOLIO:
            continue
        content, time_text = _format_push_body(label, body)
        if time_text and not analysis_time:
            analysis_time = time_text
        kind = _push_section_kind(label)
        sections_html.append(
            f'<section class="push-section push-section-{kind}">'
            f'<div class="push-section-head"><span class="push-section-label">{html.escape(label)}</span></div>'
            f"{content}</section>"
        )
    meta = (
        f'<p class="push-meta">分析时刻 · {html.escape(analysis_time)}</p>'
        if analysis_time
        else ""
    )
    return f'<div class="push-summary">{"".join(sections_html)}{meta}</div>'


__all__ = [
    "extract_push_section_body",
    "markdown_to_html",
    "markdown_sections_to_html",
    "push_summary_to_html",
]
