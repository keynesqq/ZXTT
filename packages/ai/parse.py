"""AI 报告解析。"""
from __future__ import annotations

import re

_SUMMARY_HEADING = re.compile(r"^##\s*推送摘要\s*$", re.MULTILINE)
_NEXT_SECTION = re.compile(r"\n##\s+")
_HEADING_CODE = re.compile(r"^###\s+(\d{6})\s+", re.MULTILINE)
_BODY_START = re.compile(r"(?:^|\n)(?:---\s*\n+)?(###\s+\d{6}\s+)", re.MULTILINE)


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
        body_match = _BODY_START.search(tail)
        if body_match:
            summary = tail[: body_match.start()].strip()
            body = tail[body_match.start() :].strip()
        else:
            summary = tail.strip()
            body = ""
    return body, summary


def codes_in_body(body: str) -> list[str]:
    return _HEADING_CODE.findall(body or "")


def resolve_ai_report_fields(
    *,
    raw: str,
    body: str = "",
    summary: str = "",
    stocks: list[dict] | None = None,
) -> dict[str, str | list[str]]:
    """统一拆 body/summary；body 空时从 raw 重拆（兼容旧落盘）。"""
    stocks = stocks or []
    out_body = body or ""
    out_summary = summary or ""
    if not out_body and raw:
        out_body, parsed_summary = split_ai_report(raw)
        if parsed_summary:
            out_summary = parsed_summary
    elif not out_summary and raw:
        _, parsed_summary = split_ai_report(raw)
        if parsed_summary:
            out_summary = parsed_summary
    expected = [str(s.get("code")) for s in stocks if s.get("code")]
    missing = [c for c in expected if c not in codes_in_body(str(out_body))]
    return {
        "body": out_body,
        "summary": out_summary,
        "missing_codes": missing,
    }


__all__ = ["split_ai_report", "codes_in_body", "resolve_ai_report_fields"]
