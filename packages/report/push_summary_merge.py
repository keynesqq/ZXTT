"""推送摘要解析与分片合并（页面 / 微信共用）。"""
from __future__ import annotations

import re

_SECTION_HEAD = re.compile(
    r"^(\*\*)?【([^】]+)】(\*\*)?(?:\s*(.*))?$",
    re.MULTILINE,
)
_ANALYSIS_TIME = re.compile(r"\*\*分析时刻\*\*[：:]\s*(.+)$", re.MULTILINE)
_ANALYSIS_TIME_PLAIN = re.compile(r"^分析时刻[：:]\s*(.+)$", re.MULTILINE)
_BARE_SECTION = re.compile(
    r"^(我的|想买的|观察|其它|重点|高度关注|跌幅达到预期重点关注)$"
)
_GLOBAL_LABELS = frozenset({"环境", "仓位", "操作", "超预期", "9:15素材"})


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


def _normalize_bare_section_lines(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if _BARE_SECTION.match(s):
            out.append(f"【{s}】")
        else:
            out.append(line)
    return "\n".join(out).strip()


def _section_items(label: str, body: str) -> list[str]:
    body = (body or "").strip()
    if not body or body in ("无", "（无）", "---"):
        return []
    lines: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s in ("无", "（无）", "---"):
            continue
        if _SECTION_HEAD.match(s) or _BARE_SECTION.match(s):
            continue
        lines.append(s.lstrip("-•* ").strip())
    return lines


def parse_push_summary_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """返回 (分析时刻, [(板块标签, 正文)])，正文为换行拼接的个股行。"""
    raw = _normalize_bare_section_lines((text or "").strip())
    raw, analysis_time = _extract_analysis_time(raw)
    raw = re.sub(r"\n---\s*$", "", raw).strip()
    matches = list(_SECTION_HEAD.finditer(raw))
    if not matches:
        return analysis_time, []
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        label = m.group(2).strip()
        inline = (m.group(4) or "").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        if inline:
            body = f"{inline}\n{body}".strip() if body else inline
        items = _section_items(label, body)
        if items or label in _GLOBAL_LABELS:
            sections.append((label, "\n".join(items) if items else body.strip()))
    return analysis_time, sections


def merge_push_summary_parts(*parts: str) -> str:
    """合并分片摘要：同【标签】只保留一块，个股行按出现顺序拼接。"""
    analysis_time = ""
    merged: dict[str, list[str]] = {}
    order: list[str] = []

    for part in parts:
        if not (part or "").strip():
            continue
        part_time, sections = parse_push_summary_sections(part)
        if part_time and not analysis_time:
            analysis_time = part_time
        for label, body in sections:
            items = _section_items(label, body)
            if label not in merged:
                order.append(label)
                merged[label] = []
            if label in _GLOBAL_LABELS:
                text = body.strip()
                if text and text not in merged[label]:
                    merged[label] = [text]
            elif items:
                merged[label].extend(items)

    lines: list[str] = []
    for label in order:
        if label in _GLOBAL_LABELS:
            text = merged[label][0] if merged[label] else "无"
            lines.append(f"【{label}】{text}")
        else:
            items = merged.get(label) or []
            lines.append(f"【{label}】")
            if items:
                lines.extend(items)
            else:
                lines.append("无")
    if analysis_time:
        lines.append(f"**分析时刻**：{analysis_time}")
    return "\n".join(lines).strip()


__all__ = ["merge_push_summary_parts", "parse_push_summary_sections"]
