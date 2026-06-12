"""ZXTT 三报告共用 Web 中枢页。"""
from __future__ import annotations

import html
import json
from typing import Any

_SLOT_ORDER: tuple[tuple[str, str, str], ...] = (
    ("evening_prev", "昨日作战卡", "昨收 · 服务今日"),
    ("morning", "开盘核对卡", "约 9:25"),
    ("midday", "午间作战卡", "约 12:50"),
    ("evening", "晚间收盘卡", "约 22:00"),
)

_HUB_CSS = """
:root {
  --bg: #0c1118; --surface: #151d2b; --surface-2: #1c2738;
  --text: #e8eef6; --muted: #8fa3be; --accent: #4f8cff;
  --border: #2a384f; --warn: #f5a623;
  --radius: 12px;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.5; }
.wrap { max-width: 720px; margin: 0 auto; padding: 24px 20px 48px; }
h1 { margin: 0 0 6px; font-size: 1.5rem; }
.sub { color: var(--muted); font-size: .9rem; margin-bottom: 20px; }
.report-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.report-item {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.report-item > details > summary {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  padding: 14px 16px; cursor: pointer; user-select: none;
  list-style: none;
}
.report-item > details > summary::-webkit-details-marker { display: none; }
.report-item > details > summary::after {
  content: "展开"; margin-left: auto; font-size: .72rem; color: var(--muted);
}
.report-item > details[open] > summary::after { content: "收起"; }
.report-item > details > summary:hover { background: var(--surface-2); }
.report-title { font-size: 1rem; font-weight: 700; }
.report-meta { font-size: .78rem; color: var(--muted); }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: .72rem; font-weight: 600;
}
.badge.idle { background: #243044; color: var(--muted); }
.badge.running { background: rgba(79,140,255,.2); color: #a8c7ff; }
.badge.ok { background: rgba(62,207,142,.15); color: #9ee8c0; }
.badge.fail { background: rgba(240,82,82,.15); color: #ffb4b4; }
.report-body {
  padding: 0 16px 16px; border-top: 1px solid var(--border);
  background: rgba(12,17,24,.35);
}
.timer {
  font-size: 1.35rem; font-weight: 700; font-variant-numeric: tabular-nums;
  color: var(--accent); margin: 12px 0 8px;
}
.bar { height: 6px; background: #243044; border-radius: 4px; overflow: hidden; margin: 8px 0 10px; }
.bar > div { height: 100%; background: var(--accent); transition: width .3s; }
.detail { font-size: .88rem; color: var(--muted); }
.steps { list-style: none; padding: 0; margin: 10px 0 0; font-size: .82rem; }
.steps li { padding: 3px 0; color: var(--muted); }
.steps li.done { color: #9ee8c0; }
.steps li.active { color: var(--accent); }
a.report-link {
  display: inline-block; margin-top: 12px; padding: 8px 14px;
  background: var(--accent); color: #fff; border-radius: 8px;
  text-decoration: none; font-size: .88rem; font-weight: 600;
}
a.report-link.disabled { opacity: .4; pointer-events: none; background: #243044; }
.footer { margin-top: 24px; font-size: .8rem; color: var(--muted); }
"""

_HUB_JS = """
function qp(name) {
  const m = new RegExp("[?&]" + name + "=([^&]*)").exec(location.search);
  return m ? decodeURIComponent(m[1]) : "";
}
function fmtElapsed(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return (m > 0 ? m + "分" : "") + s + "秒";
}
function statusClass(st) {
  if (st === "running") return "running";
  if (st === "ok") return "ok";
  if (st === "fail") return "fail";
  return "idle";
}
function statusLabel(st) {
  const map = { running: "生成中", ok: "已完成", fail: "失败", idle: "未运行" };
  return map[st] || st || "未运行";
}
function renderSlot(slot, data) {
  const el = document.getElementById("slot-" + slot);
  if (!el || !data) return;
  const st = data.status || "idle";
  const badge = el.querySelector(".badge");
  if (badge) {
    badge.className = "badge " + statusClass(st);
    badge.textContent = statusLabel(st);
  }
  const pct = Math.max(0, Math.min(100, Number(data.progress_pct) || 0));
  const bar = el.querySelector(".bar-inner");
  if (bar) bar.style.width = pct + "%";
  const detail = el.querySelector(".detail");
  if (detail) detail.textContent = data.detail || "";
  const link = el.querySelector(".report-link");
  if (link) {
    if (data.report_ready && data.report_href) {
      link.href = data.report_href;
      link.classList.remove("disabled");
      const labels = { evening_prev: "打开昨收报告", evening: "打开收盘报告" };
      link.textContent = labels[slot] || "打开报告";
    } else {
      link.href = "#";
      link.classList.add("disabled");
      link.textContent = "报告未就绪";
    }
  }
  const stepsEl = el.querySelector(".steps");
  if (stepsEl) {
    stepsEl.innerHTML = "";
    const order = data.step_order || [];
    const done = new Set(data.steps_done || []);
    const cur = data.current_step || "";
    for (const key of order) {
      const li = document.createElement("li");
      li.textContent = (data.step_labels && data.step_labels[key]) || key;
      if (done.has(key)) li.className = "done";
      else if (key === cur && st === "running") li.className = "active";
      const dur = (data.step_durations_ms || {})[key];
      if (dur) li.textContent += " · " + Math.floor(dur / 1000) + "s";
      stepsEl.appendChild(li);
    }
  }
  el.dataset.startedAt = data.started_at || "";
  el.dataset.status = st;
  if (st === "running") {
    const details = el.querySelector("details");
    if (details) details.open = true;
  }
}
function tickTimers() {
  document.querySelectorAll(".report-item[data-slot]").forEach((item) => {
    const timer = item.querySelector(".timer");
    const st = item.dataset.status;
    const started = item.dataset.startedAt;
    if (!timer) return;
    if (st !== "running" || !started) {
      timer.textContent = st === "ok" ? "—" : "00秒";
      return;
    }
    const start = new Date(String(started).replace(" ", "T"));
    const sec = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
    timer.textContent = fmtElapsed(sec);
  });
}
function applyHub(data) {
  if (!data) return;
  window.HUB_STATUS = data;
  const td = document.getElementById("trade-date");
  if (td) td.textContent = data.trade_date || "";
  document.body.dataset.tradeDate = data.trade_date || "";
  const slots = data.slots || {};
  ["evening_prev", "morning", "midday", "evening"].forEach((id) => renderSlot(id, slots[id]));
  tickTimers();
}
function hubJsonUrl() {
  const td = (window.HUB_STATUS && window.HUB_STATUS.trade_date) || qp("date") || document.body.dataset.tradeDate;
  return td ? "../data/report_hub/" + td + ".json" : "";
}
function pollHub() {
  const url = hubJsonUrl();
  if (!url) return;
  fetch(url + "?t=" + Date.now())
    .then((r) => r.json())
    .then(applyHub)
    .catch(() => {
      const s = document.createElement("script");
      s.src = "hub_status.js?t=" + Date.now();
      document.body.appendChild(s);
    });
}
document.querySelectorAll(".report-item details").forEach((details) => {
  details.addEventListener("toggle", () => {
    if (!details.open) return;
    document.querySelectorAll(".report-item details[open]").forEach((other) => {
      if (other !== details) other.open = false;
    });
  });
});
window.applyHub = applyHub;
if (window.__HUB_BOOT__) applyHub(window.__HUB_BOOT__);
setInterval(tickTimers, 1000);
setInterval(pollHub, 2000);
tickTimers();
pollHub();
"""


def build_hub_page(hub: dict[str, Any]) -> str:
    trade_date = html.escape(str(hub.get("trade_date") or ""))
    boot = json.dumps(hub, ensure_ascii=False).replace("</", "<\\/")
    items: list[str] = []
    for slot_id, label, schedule in _SLOT_ORDER:
        data = (hub.get("slots") or {}).get(slot_id) or {}
        st = data.get("status") or "idle"
        badge_cls = st if st in ("running", "ok", "fail") else "idle"
        items.append(
            f"""
<li class="report-item" id="slot-{slot_id}" data-slot="{slot_id}" data-status="{html.escape(st)}">
  <details>
    <summary>
      <span class="report-title">{html.escape(label)}</span>
      <span class="badge {html.escape(badge_cls)}">{html.escape(st)}</span>
      <span class="report-meta">{html.escape(schedule)}</span>
    </summary>
    <div class="report-body">
      <div class="timer">00秒</div>
      <div class="bar"><div class="bar-inner" style="width:0%"></div></div>
      <div class="detail"></div>
      <ul class="steps"></ul>
      <a class="report-link disabled" href="#">报告未就绪</a>
    </div>
  </details>
</li>"""
        )
    list_html = "\n".join(items)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZXTT 作战卡 · {trade_date}</title>
<style>{_HUB_CSS}</style>
</head>
<body data-trade-date="{trade_date}">
<div class="wrap">
  <h1>ZXTT 作战卡</h1>
  <p class="sub">交易日 <strong id="trade-date">{trade_date}</strong> · 点击标题展开进度与入口</p>
  <ul class="report-list">{list_html}</ul>
  <p class="footer">自动刷新 · 生成中自动展开</p>
</div>
<script>window.__HUB_BOOT__={boot};</script>
<script>{_HUB_JS}</script>
</body>
</html>"""


def build_hub_status_js(hub: dict[str, Any]) -> str:
    payload = json.dumps(hub, ensure_ascii=False)
    return f"window.__HUB_BOOT__={payload};if(window.applyHub)window.applyHub(window.__HUB_BOOT__);"


__all__ = ["build_hub_page", "build_hub_status_js"]
