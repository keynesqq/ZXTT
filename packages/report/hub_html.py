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
  --border: #2a384f;
  --radius: 12px;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.5; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }
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
  content: "展开报告"; margin-left: auto; font-size: .72rem; color: var(--muted);
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
.report-body { border-top: 1px solid var(--border); background: var(--bg); }
.report-frame {
  display: block; width: 100%; border: none;
  height: 480px; background: var(--bg); overflow: hidden;
}
.report-empty {
  padding: 32px 20px; text-align: center; color: var(--muted); font-size: .9rem;
}
.report-empty .empty-title { font-size: 1rem; color: var(--text); margin-bottom: 8px; }
.report-empty .empty-bar {
  height: 6px; max-width: 240px; margin: 12px auto 0;
  background: #243044; border-radius: 4px; overflow: hidden;
}
.report-empty .empty-bar > div { height: 100%; background: var(--accent); transition: width .3s; }
.footer { margin-top: 24px; font-size: .8rem; color: var(--muted); }
"""

_HUB_JS = """
function qp(name) {
  const m = new RegExp("[?&]" + name + "=([^&]*)").exec(location.search);
  return m ? decodeURIComponent(m[1]) : "";
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
function resizeReportFrame(frame) {
  if (!frame || frame.hidden) return;
  try {
    const doc = frame.contentDocument || frame.contentWindow?.document;
    if (!doc) return;
    const h = Math.max(
      doc.documentElement?.scrollHeight || 0,
      doc.body?.scrollHeight || 0,
      480
    );
    frame.style.height = h + "px";
  } catch (e) { /* 跨域时保留默认高度 */ }
}
function bindFrameAutoHeight(frame) {
  if (!frame || frame.dataset.autoHeight === "1") return;
  frame.dataset.autoHeight = "1";
  frame.addEventListener("load", () => {
    resizeReportFrame(frame);
    try {
      const doc = frame.contentDocument;
      const root = doc?.documentElement;
      if (root && window.ResizeObserver) {
        new ResizeObserver(() => resizeReportFrame(frame)).observe(root);
      }
    } catch (e) {}
  });
}
function loadReportFrame(item) {
  const href = item.dataset.reportHref || "";
  const details = item.querySelector("details");
  const frame = item.querySelector(".report-frame");
  const empty = item.querySelector(".report-empty");
  if (!details || !details.open) return;
  if (!href) {
    if (frame) frame.hidden = true;
    if (empty) empty.hidden = false;
    return;
  }
  if (frame) {
    bindFrameAutoHeight(frame);
    if (!frame.src || frame.dataset.src !== href) {
      frame.src = href;
      frame.dataset.src = href;
    }
    frame.hidden = false;
    if (frame.contentDocument?.readyState === "complete") resizeReportFrame(frame);
  }
  if (empty) empty.hidden = true;
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
  const ready = !!(data.report_ready && data.report_href);
  el.dataset.reportHref = ready ? data.report_href : "";
  el.dataset.status = st;
  const empty = el.querySelector(".report-empty");
  if (empty && !ready) {
    empty.hidden = false;
    const title = empty.querySelector(".empty-title");
    const note = empty.querySelector(".empty-note");
    const bar = empty.querySelector(".empty-bar-inner");
    if (title) {
      title.textContent = st === "running" ? "报告生成中…" : st === "fail" ? "报告生成失败" : "报告未就绪";
    }
    if (note) note.textContent = data.detail || data.error || "";
    if (bar) {
      const pct = Math.max(0, Math.min(100, Number(data.progress_pct) || 0));
      bar.style.width = st === "running" ? pct + "%" : "0%";
    }
  }
  if (st === "running") {
    const details = el.querySelector("details");
    if (details) details.open = true;
  }
  loadReportFrame(el);
}
function applyHub(data) {
  if (!data) return;
  window.HUB_STATUS = data;
  const td = document.getElementById("trade-date");
  if (td) td.textContent = data.trade_date || "";
  document.body.dataset.tradeDate = data.trade_date || "";
  const slots = data.slots || {};
  ["evening_prev", "morning", "midday", "evening"].forEach((id) => renderSlot(id, slots[id]));
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
    const item = details.closest(".report-item");
    if (!item) return;
    if (details.open) {
      document.querySelectorAll(".report-item details[open]").forEach((other) => {
        if (other !== details) other.open = false;
      });
      loadReportFrame(item);
    } else if (item.querySelector(".report-frame")) {
      item.querySelector(".report-frame").hidden = true;
      const empty = item.querySelector(".report-empty");
      if (empty && !item.dataset.reportHref) empty.hidden = false;
    }
  });
});
window.applyHub = applyHub;
if (window.__HUB_BOOT__) applyHub(window.__HUB_BOOT__);
setInterval(pollHub, 2000);
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
      <div class="report-empty">
        <div class="empty-title">报告未就绪</div>
        <div class="empty-note"></div>
        <div class="empty-bar"><div class="empty-bar-inner" style="width:0%"></div></div>
      </div>
      <iframe class="report-frame" title="{html.escape(label)}" hidden loading="lazy"></iframe>
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
  <p class="sub">交易日 <strong id="trade-date">{trade_date}</strong> · 点击标题展开对应报告</p>
  <ul class="report-list">{list_html}</ul>
  <p class="footer">自动刷新状态 · 展开后内嵌完整报告（高度随内容）</p>
</div>
<script>window.__HUB_BOOT__={boot};</script>
<script>{_HUB_JS}</script>
</body>
</html>"""


def build_hub_status_js(hub: dict[str, Any]) -> str:
    payload = json.dumps(hub, ensure_ascii=False)
    return f"window.__HUB_BOOT__={payload};if(window.applyHub)window.applyHub(window.__HUB_BOOT__);"


__all__ = ["build_hub_page", "build_hub_status_js"]
