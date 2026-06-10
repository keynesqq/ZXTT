"""午间报告生成中 · 实时进度页。"""
from __future__ import annotations

import html
import json
from typing import Any

from report.midday_html import MIDDAY_CSS

_LIVE_JS = """
window.__MIDDAY_LIVE__ = true;
let __runLastSeq = 0;
let __runPollPending = false;

const RUN_STEP_LABELS = {
  collect: "② 采集行情与资讯",
  preprocess: "③ 本地预处理",
  ai: "④ AI 研判合成",
  render: "⑤ 生成页面与推送",
};
const RUN_STEP_ORDER = ["collect", "preprocess", "ai", "render"];

function fmtElapsed(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return (m > 0 ? m + "分" : "") + s + "秒";
}

function renderSteps(st) {
  const ul = document.getElementById("run-steps");
  if (!ul) return;
  const done = new Set(st.steps_done || []);
  const current = st.current_step || "";
  const durs = st.step_durations_ms || {};
  ul.innerHTML = "";
  for (const key of RUN_STEP_ORDER) {
    const label = RUN_STEP_LABELS[key] || key;
    let icon = "○", cls = "pending", extra = "";
    if (done.has(key)) {
      icon = "✓"; cls = "done";
      if (durs[key]) extra = `<span class="step-dur">${Math.floor(durs[key] / 1000)}s</span>`;
    } else if (key === current && st.status === "running") {
      icon = "●"; cls = "active";
    } else if (key === current && st.status === "fail") {
      icon = "✗"; cls = "fail";
    }
    const li = document.createElement("li");
    li.className = `run-step ${cls}`;
    li.innerHTML = `<span class="step-icon">${icon}</span><span class="step-label">${label}</span>${extra}`;
    ul.appendChild(li);
  }
}

function switchToReport() {
  if (!window.__MIDDAY_LIVE__ || window.__runReloaded) return;
  window.__runReloaded = true;
  if (window.__runPollTimer) clearInterval(window.__runPollTimer);
  const base = location.pathname.split("?")[0];
  window.location.replace(base + "?_report=" + Date.now());
}

function applyRunStatus(st) {
  if (!st) return;
  const seq = Number(st.seq) || 0;
  if (seq > 0 && seq < __runLastSeq) return;
  if (seq > 0) __runLastSeq = seq;
  window.RUN_STATUS = st;
  const pct = Math.max(0, Math.min(100, Number(st.progress_pct) || 0));
  const el = (id) => document.getElementById(id);
  if (el("run-state")) el("run-state").textContent = st.current_label || "生成中";
  if (el("run-detail")) el("run-detail").textContent = st.detail || "";
  if (el("run-pct")) el("run-pct").textContent = `${pct}%`;
  if (el("run-bar")) el("run-bar").style.width = `${pct}%`;
  if (el("run-footer-state")) el("run-footer-state").textContent = st.status || "running";
  const errBox = el("run-err");
  if (errBox) {
    if (st.status === "fail" && st.error) {
      errBox.textContent = st.error;
      errBox.style.display = "block";
    } else {
      errBox.textContent = "";
      errBox.style.display = "none";
    }
  }
  renderSteps(st);
  if (st.status === "ok") {
    switchToReport();
    return;
  }
  if (st.status === "fail" && window.__runPollTimer) {
    clearInterval(window.__runPollTimer);
  }
}

function tick() {
  const st = window.RUN_STATUS || {};
  const el = document.getElementById("run-elapsed");
  if (!el || !st.started_at) return;
  const start = new Date(String(st.started_at).replace(" ", "T"));
  const sec = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
  el.textContent = fmtElapsed(sec);
}

function statusJsonUrl() {
  const td = (window.RUN_STATUS && window.RUN_STATUS.trade_date) || document.body.dataset.tradeDate;
  return td ? `../../data/midday_run/${td}.json` : "";
}

function pollViaFetch() {
  const url = statusJsonUrl();
  if (!url) return;
  fetch(url + "?t=" + Date.now())
    .then((r) => r.json())
    .then((st) => { __runPollPending = false; applyRunStatus(st); })
    .catch(() => { __runPollPending = false; pollViaScript(); });
}

function pollViaScript() {
  const old = document.getElementById("run-status-loader");
  if (old) old.remove();
  const s = document.createElement("script");
  s.id = "run-status-loader";
  s.src = "run_status.js?t=" + Date.now();
  s.onerror = () => {
    __runPollPending = false;
    pollViaFetch();
  };
  s.onload = () => { __runPollPending = false; };
  document.body.appendChild(s);
}

function pollStatus() {
  if (__runPollPending) return;
  __runPollPending = true;
  pollViaScript();
}

window.applyRunStatus = applyRunStatus;
if (document.getElementById("run-steps")) {
  setInterval(tick, 1000);
  tick();
  applyRunStatus(window.RUN_STATUS || {});
  window.__runPollTimer = setInterval(pollStatus, 2000);
  pollStatus();
}
"""


def build_run_status_js(status: dict[str, Any]) -> str:
    payload = json.dumps(status, ensure_ascii=False)
    return f"window.__RUN_STATUS__={payload};if(window.applyRunStatus)window.applyRunStatus(window.__RUN_STATUS__);"


def build_midday_live_page(status: dict[str, Any]) -> str:
    trade_date = html.escape(str(status.get("trade_date", "")))
    pct = int(status.get("progress_pct") or 0)
    detail = html.escape(str(status.get("detail") or ""))
    label = html.escape(str(status.get("current_label") or "生成中"))
    run_state = html.escape(str(status.get("status") or "running"))
    status_json = json.dumps(status, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZXTT 午间作战卡 · 生成中 · {trade_date}</title>
<style>
{MIDDAY_CSS}
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
  transition: width .4s ease;
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
.step-dur {{ color: var(--muted); font-size: .8rem; margin-left: 6px; }}
@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .45; }} }}
.run-hint {{ font-size: .78rem; color: var(--muted); margin-top: 12px; }}
#run-err {{ display: none; margin-top: 12px; }}
</style>
</head>
<body data-trade-date="{trade_date}">
<div class="wrap">
<header class="hero">
<h1>午间作战卡</h1>
<p class="sub">交易日 {trade_date} · <span id="run-state">{label}</span></p>
<div class="chips">
<span class="chip accent">生成中</span>
<span class="chip" id="run-pct">{pct}%</span>
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
<div class="run-bar"><div class="run-bar-fill" id="run-bar" style="width:{pct}%"></div></div>
<ul class="run-steps" id="run-steps"></ul>
<p class="run-hint">进度每 2 秒局部更新；完成后自动载入完整报告。</p>
<div class="alert alert-err" id="run-err"></div>
</div>
</section>
<p class="footer-note">ZXTT · 状态 <span id="run-footer-state">{run_state}</span></p>
</div>
<script>window.RUN_STATUS = {status_json};</script>
<script>{_LIVE_JS}</script>
</body>
</html>"""


__all__ = ["build_midday_live_page", "build_run_status_js"]
