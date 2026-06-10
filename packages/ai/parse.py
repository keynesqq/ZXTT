"""AI 报告解析。"""
from __future__ import annotations

import re

_SUMMARY_HEADING = re.compile(r"^##\s*推送摘要\s*$", re.MULTILINE)
_NEXT_SECTION = re.compile(r"\n##\s+")
_HEADING_CODE = re.compile(r"^###\s+(\d{6})\s+", re.MULTILINE)


def split_ai_report(text: str) -> tuple[str, str]:
    """返回 (正文 Markdown, 推送摘要 Markdown)。"""
    raw = (text or "").strip()
    if not raw:
        return "", ""
    match = _SUMMARY_HEADING.search(raw)
    if not match:
        return raw, ""
    tail = raw[match.end() :]
    next_match = _NEXT_SECTION.search(tail)
    if next_match:
        summary = tail[: next_match.start()].strip()
        body = tail[next_match.start() :].strip()
    else:
        summary = tail.strip()
        body = ""
    return body, summary


def codes_in_body(body: str) -> list[str]:
    return _HEADING_CODE.findall(body or "")


__all__ = ["split_ai_report", "codes_in_body"]
