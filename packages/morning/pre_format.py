"""9:15 素材行格式化（assemble / prompt 共用）。"""
from __future__ import annotations

from typing import Any


def format_pre_material(*, status: str, titles: list[str] | None) -> str:
    st = (status or "").strip()
    items = [str(t).strip() for t in (titles or []) if str(t).strip()]
    if st == "refresh":
        if items:
            shown = "；".join(items[:3])
            if len(items) > 3:
                shown += f"等{len(items)}条"
            return f"新素材={shown}"
        return "新素材=指纹变化（无标题）"
    if st == "no_new":
        return "新素材=无"
    if st == "reuse":
        return "新素材=与昨晚一致"
    if st == "failed":
        return "新素材=采集失败"
    return ""


def format_stock_prompt_line(row: dict[str, Any]) -> str:
    titles = row.get("pre_titles") or []
    pre_bit = format_pre_material(status=str(row.get("pre_status") or ""), titles=titles)
    parts = [
        f"预期={row.get('expected_open') or '—'}",
        f"终缺口={row.get('end_gap')}%",
        f"9:20后={row.get('shape_after_920')}",
        f"判定={row.get('verdict')}",
        f"素材={row.get('pre_status')}",
    ]
    if pre_bit:
        parts.append(pre_bit)
    return " | ".join(parts)


__all__ = ["format_pre_material", "format_stock_prompt_line"]
