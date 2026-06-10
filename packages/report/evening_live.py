"""晚间报告生成中 · 实时进度页。"""
from __future__ import annotations

import html
import json
from typing import Any

from report.evening_html import EVENING_CSS

_STEPS: list[tuple[str, str]] = [
    ("collect", "② 采集行情与资讯"),
    ("preprocess", "③ 本地预处理"),
    ("ai", "④ AI 研判合成"),
    ("render", "⑤ 生成页面与推送"),
]

_LIVE_JS = """
function fmtElapsed(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return (m > 0 ? m + '分' : '') + s + '秒';
}
function tick() {
  const st = window.RUN_STATUS || {};
  const el = document.getElementById('run-elapsed');
  if (!el || !st.started_at) return;
  const start = new Date(String(st.started_at).replace(' ', 'T'));
  const sec = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
  el.textContent = fmtElapsed(sec);
}
function maybeReload() {
  const st = window.RUN_STATUS || {};
  if (st.status === 'running') {
    setTimeout(() => location.reload(), 2500);
  }
}
setInterval(tick, 1000);
tick();
maybeReload();
"""


def _steps_html(status: dict[str, Any]) -> str:
    done = set(status.get("steps_done") or [])
    current = str(status.get("current_step") or "")
    durs = status.get("step_durations_ms") or {}
    rows = []
    for key, label in _STEPS:
        if key in done:
            icon, cls = "✓", "done"
            dur = durs.get(key)
            extra = f' <span class="step-dur">{dur // 1000}s</span>' if dur else ""
        elif key == current and status.get("status") == "running":
            icon, cls = "●", "active"
            extra = ""
        elif status.get("status") == "fail" and key == current:
            icon, cls = "✗", "fail"
            extra = ""
        else:
            icon, cls = "○", "pending"
            extra = ""
        rows.append(
            f'<li class="run-step {cls}"><span class="step-icon">{icon}</span>'
            f'<span class="step-label">{html.escape(label)}</span>{extra}</li>'
        )
    return f'<ul class="run-steps">{"".join(rows)}</ul>'


def build_evening_live_page(status: dict[str, Any]) -> str:
    trade_date = html.escape(str(status.get("trade_date", "")))
    pct = int(status.get("progress_pct") or 0)
    detail = html.escape(str(status.get("detail") or ""))
    label = html.escape(str(status.get("current_label") or "生成中"))
    run_state = html.escape(str(status.get("status") or "running"))
    err = html.escape(str(status.get("error") or ""))
    status_json = json.dumps(status, ensure_ascii=False).replace("</", "<\\/")

    err_block = f'<div class="alert alert-err">{err}</div>' if err and run_state == "fail" else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZXTT 明日作战卡 · 生成中 · {trade_date}</title>
<style>
{EVENING_CSS}
.run-card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 22px 24px; margin-bottom: 20px;
  box-shadow: var(--shadow);
}}
.run-card h2 {{ margin: 0 0 6px; font-size: 1.2rem; }}
.run-detail {{ color: var(--muted); font-size: .92rem; margin: 0 0 16px; min-height: 1.4em; }}
.run-timer {{
  font-size: 2rem; font-weight: 700; font-variant-numeric: tabular-nums;
  color: var(--accent); margin-bottom: 14px;
}}
.run-timer span {{ font-size: .85rem; color: var(--muted); font-weight: 500; margin-left: 8px; }}
.run-bar {{
  height: 8px; border-radius: 999px; background: var(--surface-3);
  overflow: hidden; margin-bottom: 18px;
}}
.run-bar-fill {{
  height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--accent), #7eb6ff);
  transition: width .4s ease; width: {pct}%;
}}
.run-steps {{ list-style: none; margin: 0; padding: 0; }}
.run-step {{
  display: flex; align-items: center; gap: 10px; padding: 10px 0;
  border-bottom: 1px solid var(--border); font-size: .92rem;
}}
.run-step:last-child {{ border-bottom: none; }}
.step-icon {{ width: 1.2em; text-align: center; font-weight: 700; }}
.run-step.done .step-icon {{ color: #9ee8c0; }}
.run-step.active .step-icon {{ color: var(--accent); animation: pulse 1.2s infinite; }}
.run-step.fail .step-icon {{ color: #ffb4b4; }}
.run-step.pending {{ color: var(--muted); }}
.step-dur {{ color: var(--muted); font-size: .8rem; }}
@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .45; }} }}
.run-hint {{ font-size: .78rem; color: var(--muted); margin-top: 12px; }}
</style>
</head>
<body>
<div class="wrap">
<header class="hero">
<h1>明日作战卡</h1>
<p class="sub">交易日 {trade_date} · <span id="run-state">{label}</span></p>
<div class="chips">
<span class="chip accent">生成中</span>
<span class="chip">{pct}%</span>
</div>
</header>
<nav class="tab-nav">
<button type="button" class="active">研判</button>
<button type="button" disabled style="opacity:.45;cursor:default">行情快照</button>
<button type="button" disabled style="opacity:.45;cursor:default">素材</button>
</nav>
<section class="panel active">
<div class="run-card">
<h2>管线进度</h2>
<p class="run-detail" id="run-detail">{detail}</p>
<div class="run-timer"><span id="run-elapsed">0秒</span><span>已用时间</span></div>
<div class="run-bar"><div class="run-bar-fill" id="run-bar"></div></div>
{_steps_html(status)}
<p class="run-hint">页面每 2 秒自动刷新以同步进度；完成后将显示完整报告。</p>
{err_block}
</div>
</section>
<p class="footer-note">ZXTT · 状态 {run_state}</p>
</div>
<script>window.RUN_STATUS = {status_json};</script>
<script>{_LIVE_JS}</script>
</body>
</html>"""


__all__ = ["build_evening_live_page"]
