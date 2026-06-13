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
.badge.warn { background: rgba(230,184,77,.15); color: #f0d48a; }
.report-body { border-top: 1px solid var(--border); background: var(--bg); }
.report-item > details:not([open]) .report-body {
  display: none !important;
  height: 0 !important;
  overflow: hidden;
  margin: 0;
  padding: 0;
  border: none;
}
.report-embed { min-height: 0; }
.report-item > details:not([open]) .report-embed {
  display: none !important;
  height: 0 !important;
  overflow: hidden;
  margin: 0;
  padding: 0;
}
.report-chunk { padding: 0; }
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
.status-dash {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 16px 18px; margin-bottom: 20px;
}
.dash-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  margin-bottom: 14px;
}
.dash-title { font-size: 1rem; font-weight: 700; margin: 0; }
.dash-updated { font-size: .75rem; color: var(--muted); margin-left: auto; }
.dash-groups {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;
}
.dash-group {
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px 12px;
}
.dash-group-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
  font-size: .82rem; font-weight: 700;
}
.dash-items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.dash-item {
  display: grid; grid-template-columns: 8px 1fr; gap: 8px; align-items: start;
  font-size: .78rem;
}
.dash-dot {
  width: 8px; height: 8px; border-radius: 50%; margin-top: 5px;
  background: #4a5a72;
}
.dash-dot.ok { background: #3ecf8e; }
.dash-dot.warn { background: #e6b84d; }
.dash-dot.fail { background: #f05252; }
.dash-dot.running { background: var(--accent); animation: dash-pulse 1.2s ease-in-out infinite; }
.dash-dot.idle { background: #4a5a72; }
@keyframes dash-pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.dash-item-label { font-weight: 600; color: var(--text); }
.dash-item-detail { color: var(--muted); font-size: .72rem; margin-top: 1px; }
.dash-item-bar {
  grid-column: 2; height: 3px; background: #243044; border-radius: 2px; overflow: hidden; margin-top: 2px;
}
.dash-item-bar > div { height: 100%; background: var(--accent); transition: width .3s; }
.hub-steps {
  list-style: none; margin: 10px auto 0; padding: 0; max-width: 320px; text-align: left;
  font-size: .78rem; color: var(--muted);
}
.hub-steps li { padding: 3px 0; }
.hub-steps li.done { color: #9ee8c0; }
.hub-steps li.active { color: #a8c7ff; font-weight: 600; }
.hub-steps li.fail { color: #ffb4b4; }
"""

_HUB_JS = """
let __hubRevision = "";
let __hubPollPending = false;

function qp(name) {
  const m = new RegExp("[?&]" + name + "=([^&]*)").exec(location.search);
  return m ? decodeURIComponent(m[1]) : "";
}
function statusClass(st) {
  if (st === "running") return "running";
  if (st === "ok") return "ok";
  if (st === "fail") return "fail";
  if (st === "warn") return "warn";
  return "idle";
}
function dashStatusLabel(st) {
  const map = { running: "运行中", ok: "正常", fail: "失败", warn: "部分完成", idle: "未运行" };
  return map[st] || st || "未运行";
}
function reportStatusLabel(st) {
  const map = { running: "生成中", ok: "已完成", fail: "失败", idle: "未运行" };
  return map[st] || st || "未运行";
}
function statusLabel(st) {
  return reportStatusLabel(st);
}
function hubRevision(data) {
  if (!data) return "";
  const slots = data.slots || {};
  const parts = [data.updated_at || ""];
  ["evening_prev", "morning", "midday", "evening"].forEach((id) => {
    const s = slots[id] || {};
    parts.push([
      s.status, s.progress_pct, s.updated_at, s.run_seq,
      s.report_href, s.report_ready, s.report_rev, s.detail,
    ].join(":"));
  });
  const svc = data.services || {};
  parts.push(svc.updated_at || "", svc.collect_updated_at || "", svc.overall || "");
  (svc.groups || []).forEach((g) => {
    parts.push(g.id || "", g.status || "");
    (g.items || []).forEach((it) => {
      parts.push([it.id, it.status, it.detail, it.updated_at].join("~"));
    });
  });
  return parts.join("|");
}
function templateRevsFromData(data) {
  const revs = {};
  const slots = (data && data.slots) || {};
  Object.keys(slots).forEach((id) => {
    const s = slots[id];
    if (s && s.report_ready && s.report_rev) revs[id] = String(s.report_rev);
  });
  return revs;
}
function maybeReloadForNewReports(data) {
  const next = templateRevsFromData(data);
  const prev = window.__HUB_TEMPLATE_REVS__ || {};
  for (const id of Object.keys(next)) {
    const nextRev = next[id];
    if (!nextRev) continue;
    const tpl = document.getElementById("tpl-" + id);
    const prevRev = prev[id] || "";
    if (!tpl || (prevRev && prevRev !== nextRev) || (!prevRev && tpl.dataset.rev !== nextRev)) {
      location.reload();
      return true;
    }
  }
  return false;
}
function runEmbedScripts(container) {
  container.querySelectorAll("script").forEach((old) => {
    const s = document.createElement("script");
    if (old.src) s.src = old.src;
    else s.textContent = old.textContent;
    old.replaceWith(s);
  });
}
function unmountReportEmbed(item) {
  if (!item) return;
  const slot = item.dataset.slot || "";
  const embed = item.querySelector(".report-embed");
  if (embed) embed.innerHTML = "";
  const modal = document.getElementById(slot + "-summary-modal");
  if (modal) modal.remove();
  document.body.style.overflow = "";
  delete item.dataset.embedRev;
}
function collapseReportItem(item, opts) {
  if (!item) return;
  const details = item.querySelector("details");
  if (details && opts?.userClosed) details.dataset.userCollapsed = "1";
  unmountReportEmbed(item);
}
function expandReportItem(item) {
  const details = item.querySelector("details");
  if (details) delete details.dataset.userCollapsed;
}
function loadReportEmbed(item, data) {
  const details = item.querySelector("details");
  const embed = item.querySelector(".report-embed");
  const empty = item.querySelector(".report-empty");
  if (!details?.open || !embed) return;
  const slot = item.dataset.slot || "";
  if (!data?.report_ready) {
    unmountReportEmbed(item);
    if (empty) empty.hidden = false;
    return;
  }
  const tpl = document.getElementById("tpl-" + slot);
  if (!tpl || !tpl.innerHTML.trim()) {
    if (empty) empty.hidden = false;
    return;
  }
  const rev = tpl.dataset.rev || "";
  if (item.dataset.embedRev === rev && embed.innerHTML) {
    if (empty) empty.hidden = true;
    return;
  }
  unmountReportEmbed(item);
  const modalId = slot + "-summary-modal";
  embed.innerHTML = tpl.innerHTML
    .replace(/id="summary-modal"/g, 'id="' + modalId + '"')
    .replace(/getElementById\\(['"]summary-modal['"]\\)/g, "getElementById('" + modalId + "')");
  runEmbedScripts(embed);
  item.dataset.embedRev = rev;
  if (empty) empty.hidden = true;
}
function renderSlotSteps(container, data) {
  const order = data.step_order || [];
  if (!order.length) return;
  let stepsEl = container.querySelector(".hub-steps");
  if (!stepsEl) {
    stepsEl = document.createElement("ul");
    stepsEl.className = "hub-steps";
    container.appendChild(stepsEl);
  }
  const done = new Set(data.steps_done || []);
  const current = data.current_step || "";
  const st = data.status || "idle";
  const labels = data.step_labels || {};
  stepsEl.innerHTML = "";
  order.forEach((key) => {
    const li = document.createElement("li");
    let cls = "pending";
    if (done.has(key)) cls = "done";
    else if (key === current && st === "running") cls = "active";
    else if (key === current && st === "fail") cls = "fail";
    li.className = cls;
    li.textContent = labels[key] || key;
    stepsEl.appendChild(li);
  });
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
  const showEmbed = !!(data.report_ready && data.report_href);
  el.dataset.reportHref = showEmbed ? (data.report_href || "") : "";
  el.dataset.status = st;
  const empty = el.querySelector(".report-empty");
  const details = el.querySelector("details");
  if (details && !details.open) collapseReportItem(el);
  if (empty) {
    if (showEmbed && details?.open) {
      empty.hidden = true;
    } else if (!showEmbed) {
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
      renderSlotSteps(empty, data);
    }
  }
  if (st === "running" && details && !details.dataset.userCollapsed) details.open = true;
  loadReportEmbed(el, data);
}
function renderServices(services) {
  const root = document.getElementById("status-dash");
  if (!root || !services) return;
  const overall = services.overall || "idle";
  const badge = root.querySelector(".dash-overall");
  if (badge) {
    badge.className = "badge dash-overall " + statusClass(overall);
    badge.textContent = dashStatusLabel(overall);
  }
  const upd = root.querySelector(".dash-updated");
  if (upd) {
    const parts = [];
    if (services.updated_at) parts.push("刷新 " + services.updated_at);
    if (services.collect_updated_at) parts.push("采集 " + services.collect_updated_at);
    upd.textContent = parts.join(" · ");
  }
  (services.groups || []).forEach((group) => {
    const box = root.querySelector('[data-group="' + group.id + '"]');
    if (!box) return;
    const gb = box.querySelector(".group-badge");
    if (gb) {
      gb.className = "badge group-badge " + statusClass(group.status || "idle");
      gb.textContent = dashStatusLabel(group.status || "idle");
    }
    const list = box.querySelector(".dash-items");
    if (!list) return;
    list.innerHTML = "";
    (group.items || []).forEach((item) => {
      const li = document.createElement("li");
      li.className = "dash-item";
      const st = item.status || "idle";
      const dot = document.createElement("span");
      dot.className = "dash-dot " + statusClass(st);
      li.appendChild(dot);
      const body = document.createElement("div");
      const label = document.createElement("div");
      label.className = "dash-item-label";
      label.textContent = item.label || item.id || "";
      body.appendChild(label);
      const detail = document.createElement("div");
      detail.className = "dash-item-detail";
      detail.textContent = item.detail || "";
      body.appendChild(detail);
      if (st === "running" && item.progress_pct != null) {
        const bar = document.createElement("div");
        bar.className = "dash-item-bar";
        const inner = document.createElement("div");
        const pct = Math.max(0, Math.min(100, Number(item.progress_pct) || 0));
        inner.style.width = pct + "%";
        bar.appendChild(inner);
        body.appendChild(bar);
      }
      li.appendChild(body);
      list.appendChild(li);
    });
  });
}
function applyHub(data) {
  if (!data) return;
  if (maybeReloadForNewReports(data)) return;
  const rev = hubRevision(data);
  if (rev && rev === __hubRevision) return;
  __hubRevision = rev;
  window.HUB_STATUS = data;
  const td = document.getElementById("trade-date");
  if (td) td.textContent = data.trade_date || "";
  document.body.dataset.tradeDate = data.trade_date || "";
  renderServices(data.services);
  const slots = data.slots || {};
  ["evening_prev", "morning", "midday", "evening"].forEach((id) => renderSlot(id, slots[id]));
}
function hubJsonUrl() {
  const td = (window.HUB_STATUS && window.HUB_STATUS.trade_date) || qp("date") || document.body.dataset.tradeDate;
  return td ? "../data/report_hub/" + td + ".json" : "";
}
function pollHubViaFetch() {
  const url = hubJsonUrl();
  if (!url) { __hubPollPending = false; return; }
  fetch(url + "?t=" + Date.now())
    .then((r) => r.json())
    .then((data) => { __hubPollPending = false; applyHub(data); })
    .catch(() => { __hubPollPending = false; pollHubViaScript(); });
}
function pollHubViaScript() {
  const old = document.getElementById("hub-status-loader");
  if (old) old.remove();
  const s = document.createElement("script");
  s.id = "hub-status-loader";
  s.src = "hub_status.js?t=" + Date.now();
  s.onerror = () => { __hubPollPending = false; pollHubViaFetch(); };
  s.onload = () => { __hubPollPending = false; };
  document.body.appendChild(s);
}
function pollHub() {
  if (__hubPollPending) return;
  __hubPollPending = true;
  pollHubViaScript();
}
document.querySelectorAll(".report-item details").forEach((details) => {
  details.addEventListener("toggle", () => {
    const item = details.closest(".report-item");
    if (!item) return;
    if (details.open) {
      expandReportItem(item);
      document.querySelectorAll(".report-item details[open]").forEach((other) => {
        if (other !== details) {
          other.open = false;
          collapseReportItem(other.closest(".report-item"));
        }
      });
      const slotId = item.dataset.slot || "";
      const slotData = (window.HUB_STATUS && window.HUB_STATUS.slots || {})[slotId] || {};
      loadReportEmbed(item, slotData);
    } else {
      collapseReportItem(item, { userClosed: true });
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


def _build_dash_group(group: dict[str, Any]) -> str:
    gid = html.escape(str(group.get("id") or ""))
    label = html.escape(str(group.get("label") or ""))
    gst = group.get("status") or "idle"
    badge_cls = gst if gst in ("running", "ok", "fail", "warn") else "idle"
    item_rows: list[str] = []
    for item in group.get("items") or []:
        st = item.get("status") or "idle"
        dot_cls = st if st in ("running", "ok", "fail", "warn") else "idle"
        pct = item.get("progress_pct")
        bar = ""
        if st == "running" and pct is not None:
            pw = max(0, min(100, int(pct)))
            bar = f'<div class="dash-item-bar"><div style="width:{pw}%"></div></div>'
        item_rows.append(
            f"""<li class="dash-item">
  <span class="dash-dot {html.escape(dot_cls)}"></span>
  <div>
    <div class="dash-item-label">{html.escape(str(item.get("label") or ""))}</div>
    <div class="dash-item-detail">{html.escape(str(item.get("detail") or ""))}</div>
    {bar}
  </div>
</li>"""
        )
    items_html = "\n".join(item_rows) or '<li class="dash-item"><span class="dash-dot idle"></span><div><div class="dash-item-detail">无数据</div></div></li>'
    return f"""<section class="dash-group" data-group="{gid}">
  <div class="dash-group-head">
    <span>{label}</span>
    <span class="badge group-badge {html.escape(badge_cls)}">{html.escape(str(gst))}</span>
  </div>
  <ul class="dash-items">{items_html}</ul>
</section>"""


def _build_templates_html(hub: dict[str, Any]) -> str:
    templates = hub.get("templates") or {}
    parts: list[str] = []
    for slot_id, _, _ in _SLOT_ORDER:
        chunk = templates.get(slot_id)
        if not chunk or not chunk.get("html"):
            continue
        rev = html.escape(str(chunk.get("rev") or ""))
        parts.append(f'<template id="tpl-{slot_id}" data-rev="{rev}">{chunk["html"]}</template>')
    return "\n".join(parts)


def _template_revs_js(hub: dict[str, Any]) -> str:
    revs: dict[str, str] = {}
    for slot_id, _, _ in _SLOT_ORDER:
        slot = (hub.get("slots") or {}).get(slot_id) or {}
        if slot.get("report_ready") and slot.get("report_rev"):
            revs[slot_id] = str(slot["report_rev"])
    return json.dumps(revs, ensure_ascii=False)


def build_hub_page(hub: dict[str, Any]) -> str:
    trade_date = html.escape(str(hub.get("trade_date") or ""))
    boot_hub = {k: v for k, v in hub.items() if k != "templates"}
    boot = json.dumps(boot_hub, ensure_ascii=False).replace("</", "<\\/")
    services = hub.get("services") or {}
    overall = services.get("overall") or "idle"
    overall_cls = overall if overall in ("running", "ok", "fail", "warn") else "idle"
    dash_parts = [
        _build_dash_group(g) for g in (services.get("groups") or [])
    ]
    dash_groups = "\n".join(dash_parts)
    upd_parts: list[str] = []
    if services.get("updated_at"):
        upd_parts.append(f"刷新 {services['updated_at']}")
    if services.get("collect_updated_at"):
        upd_parts.append(f"采集 {services['collect_updated_at']}")
    dash_updated = html.escape(" · ".join(upd_parts))
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
      <div class="report-embed"></div>
    </div>
  </details>
</li>"""
        )
    list_html = "\n".join(items)
    templates_html = _build_templates_html(hub)
    template_revs = _template_revs_js(hub)
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
  <section class="status-dash" id="status-dash">
    <div class="dash-head">
      <h2 class="dash-title">系统状态</h2>
      <span class="badge dash-overall {html.escape(overall_cls)}">{html.escape(str(overall))}</span>
      <span class="dash-updated">{dash_updated}</span>
    </div>
    <div class="dash-groups">{dash_groups}</div>
  </section>
  <ul class="report-list">{list_html}</ul>
  <p class="footer">每 2 秒自动刷新状态 · 展开后内嵌完整报告 · 生成完成后自动更新</p>
</div>
<div id="hub-templates" hidden>{templates_html}</div>
<script>window.__HUB_TEMPLATE_REVS__={template_revs};</script>
<script>window.__HUB_BOOT__={boot};</script>
<script>{_HUB_JS}</script>
</body>
</html>"""


def build_hub_status_js(hub: dict[str, Any]) -> str:
    payload = json.dumps(hub, ensure_ascii=False)
    return f"window.__HUB_BOOT__={payload};if(window.applyHub)window.applyHub(window.__HUB_BOOT__);"


__all__ = ["build_hub_page", "build_hub_status_js"]
