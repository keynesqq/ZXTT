"""从 daily_*.html 抽取可烘焙进主 WEB 的片段。"""
from __future__ import annotations

import re
from pathlib import Path

_STYLE_RE = re.compile(r"<style\b[^>]*>([\s\S]*?)</style>", re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>([\s\S]*?)</script>", re.IGNORECASE)
def _report_rev(path: Path) -> str:
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return ""


def _strip_hub_child_script(tag: str, body: str) -> bool:
    if "hub_embed_child" in tag.lower():
        return True
    return "hub_embed_child" in body


def _extract_wrap_inner(raw: str) -> str | None:
    m = re.search(
        r'<div\s+class=(["\'])([^"\']*\bwrap\b[^"\']*)\1[^>]*>',
        raw,
        re.IGNORECASE,
    )
    if not m:
        return None
    start = m.end()
    script_start = len(raw)
    for sm in _SCRIPT_RE.finditer(raw, start):
        tag, body = sm.group(1), sm.group(2)
        if _strip_hub_child_script(tag, body):
            continue
        script_start = sm.start()
        break
    chunk = raw[start:script_start].rstrip()
    if chunk.endswith("</div>"):
        chunk = chunk[:-6].rstrip()
    return chunk or None


def extract_report_chunk(path: Path) -> dict[str, str] | None:
    """返回 {rev, html}；html 含 style + wrap 正文 + 内联 script。"""
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    styles = _STYLE_RE.findall(raw)
    wrap_inner = _extract_wrap_inner(raw)
    if wrap_inner is None:
        return None
    scripts: list[str] = []
    for tag, body in _SCRIPT_RE.findall(raw):
        if _strip_hub_child_script(tag, body):
            continue
        if body.strip():
            scripts.append(f"<script{tag}>{body}</script>")
    style_block = "".join(f"<style>{s}</style>" for s in styles)
    script_block = "".join(scripts)
    chunk_html = f'{style_block}<div class="report-chunk">{wrap_inner}</div>{script_block}'
    if "</template>" in chunk_html.lower():
        return None
    return {"rev": _report_rev(path), "html": chunk_html}


__all__ = ["extract_report_chunk"]
