"""早盘生成进度页（简版）。"""
from __future__ import annotations

import html
import json
from typing import Any

from report.morning_html import _MORNING_CSS


def build_morning_live_page(status: dict[str, Any]) -> str:
    detail = html.escape(str(status.get("detail") or ""))
    pct = int(status.get("progress_pct") or 0)
    label = html.escape(str(status.get("current_label") or "生成中"))
    state = html.escape(str(status.get("status") or "running"))
    err = status.get("error")
    err_html = f"<p class='err'>{html.escape(str(err))}</p>" if err else ""
    st_json = html.escape(json.dumps(status, ensure_ascii=False))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>开盘核对卡 · 生成中</title>
<style>{_MORNING_CSS}
.bar {{ height: 8px; background: #243044; border-radius: 4px; margin: 12px 0; }}
.bar > div {{ height: 100%; background: #4f8cff; border-radius: 4px; width: {pct}%; }}
.err {{ color: #ffb4b4; }}
</style></head><body><div class="wrap">
<h1>{label}</h1>
<p class="sub">{detail}</p>
<div class="bar"><div></div></div>
<p>状态：{state} · {pct}%</p>
{err_html}
<pre style="color:#8fa3be;font-size:12px">{st_json}</pre>
</div></body></html>"""


__all__ = ["build_morning_live_page"]
