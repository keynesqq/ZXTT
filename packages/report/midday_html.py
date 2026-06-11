"""午间报告 HTML 页面（完整 UI）。"""
from __future__ import annotations

import html
from typing import Any

from report.md_html import markdown_sections_to_html, markdown_to_html, push_summary_to_html
from report.stock_fact_strip import (
    inject_stock_events_footer,
    inject_stock_fact_strips,
    snapshot_rows_by_code,
)

MIDDAY_CSS = """
:root {
  --bg: #0c1118;
  --surface: #151d2b;
  --surface-2: #1c2738;
  --surface-3: #243044;
  --text: #e8eef6;
  --muted: #8fa3be;
  --accent: #4f8cff;
  --accent-dim: rgba(79,140,255,.15);
  --border: #2a384f;
  --up: #f05252;
  --down: #3ecf8e;
  --warn: #f5a623;
  --radius: 12px;
  --shadow: 0 8px 32px rgba(0,0,0,.35);
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.6; font-size: 15px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 0 20px 48px; }

.hero {
  background: linear-gradient(135deg, #1a2744 0%, #0f1419 55%, #162032 100%);
  border-bottom: 1px solid var(--border);
  padding: 28px 0 20px;
  margin: 0 -20px 24px;
  padding-left: 20px; padding-right: 20px;
}
.hero-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px;
  margin: 0 0 4px;
}
.hero-name {
  margin: 0; font-size: 1.65rem; font-weight: 700; letter-spacing: .02em;
}
.summary-trigger {
  padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(79,140,255,.4);
  background: var(--accent-dim); color: #a8c7ff; font-size: .78rem; font-weight: 600;
  cursor: pointer; line-height: 1.4; letter-spacing: .04em;
}
.summary-trigger:hover { background: rgba(79,140,255,.28); color: #fff; }

.modal { display: none; position: fixed; inset: 0; z-index: 100; }
.modal.open {
  display: flex; align-items: center; justify-content: center; padding: 20px 16px;
}
.modal-backdrop {
  position: absolute; inset: 0; background: rgba(0,0,0,.6); backdrop-filter: blur(2px);
}
.modal-panel {
  position: relative; flex: 0 1 720px; width: 100%; max-height: min(88vh, 820px);
  margin: 0; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); display: flex; flex-direction: column;
}
.modal-head {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 16px 20px; border-bottom: 1px solid var(--border); font-weight: 700;
}
.modal-head-sub { font-size: .78rem; font-weight: 400; color: var(--muted); margin-left: 8px; }
.modal-close {
  border: none; background: var(--surface-2); color: var(--muted); font-size: 1.25rem;
  line-height: 1; cursor: pointer; padding: 4px 10px; border-radius: 8px;
}
.modal-close:hover { color: var(--text); background: var(--surface-3); }
.modal-body { padding: 16px 20px 20px; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.hero-head .chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 999px; font-size: .8rem;
  background: var(--surface-2); border: 1px solid var(--border); color: var(--muted);
}
.chip.ok { border-color: rgba(62,207,142,.4); color: #9ee8c0; }
.chip.warn { border-color: rgba(245,166,35,.45); color: #ffd08a; }
.chip.err { border-color: rgba(240,82,82,.45); color: #ffb4b4; }
.chip.accent { background: var(--accent-dim); border-color: rgba(79,140,255,.35); color: #a8c7ff; }
.health-bar {
  margin-top: 14px; padding: 10px 14px; border-radius: var(--radius);
  background: rgba(245,166,35,.08); border: 1px solid rgba(245,166,35,.25);
  font-size: .88rem; color: #ffd08a;
}
.alert { margin-top: 10px; padding: 10px 14px; border-radius: var(--radius); font-size: .88rem; }
.alert-warn { background: rgba(245,166,35,.1); border: 1px solid rgba(245,166,35,.3); color: #ffd08a; }
.alert-err { background: rgba(240,82,82,.1); border: 1px solid rgba(240,82,82,.3); color: #ffb4b4; }

.tab-nav {
  display: none;
}
.panel { display: block; }

.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 18px 20px; margin-bottom: 16px; box-shadow: var(--shadow);
}
.card h2 { margin: 0 0 12px; font-size: 1.05rem; color: var(--text); }
.card-label {
  font-size: .75rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); margin-bottom: 10px; font-weight: 600;
}

.push-summary { display: flex; flex-direction: column; gap: 12px; }
.push-section {
  padding: 12px 14px; border-radius: 10px; background: var(--surface-2);
  border: 1px solid var(--border);
}
.push-section-global { border-left: 3px solid var(--accent); }
.push-section-portfolio { border-left: 3px solid rgba(62,207,142,.75); }
.push-section-watch { border-left: 3px solid rgba(245,166,35,.65); }
.push-section-head { margin-bottom: 8px; }
.push-section-label {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: .75rem; font-weight: 800; letter-spacing: .04em;
  background: var(--surface-3); color: #a8c7ff;
}
.push-section-global .push-section-label { background: var(--accent-dim); color: #a8c7ff; }
.push-section-portfolio .push-section-label { background: rgba(62,207,142,.15); color: #9ee8c0; }
.push-section-watch .push-section-label { background: rgba(245,166,35,.12); color: #ffd08a; }
.push-section-body { font-size: .9rem; line-height: 1.65; color: #d4deee; }
.push-section-body strong { color: #fff; }
.push-stock-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.push-stock-item {
  padding: 10px 12px; border-radius: 8px; background: rgba(12,17,24,.45);
  border: 1px solid rgba(42,56,79,.8); font-size: .88rem; line-height: 1.6;
}
.push-code {
  display: inline-block; min-width: 4.5em; margin-right: 8px;
  font-family: ui-monospace, monospace; font-weight: 700; color: var(--accent);
}
.push-stock-text { color: #c8d4e6; }
.push-stock-text strong { color: #eef3fb; }
.push-meta {
  margin: 4px 0 0; padding-top: 12px; border-top: 1px dashed var(--border);
  font-size: .78rem; color: var(--muted); text-align: right;
}
.push-lead { margin: 0 0 4px; font-size: .88rem; color: var(--muted); }

.prose { font-size: .94rem; }
.prose h2.section-heading {
  margin: 28px 0 12px; padding-bottom: 8px; font-size: 1.15rem;
  border-bottom: 1px solid var(--border); color: #c5d4ea;
}
.prose h3.stock-heading,
.prose summary.stock-heading {
  margin: 22px 0 0; padding: 10px 14px; border-radius: 8px;
  background: var(--surface-2); border-left: 3px solid var(--accent); font-size: 1rem;
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px;
}
details.stock-block { margin-bottom: 16px; }
details.stock-block > summary.stock-heading {
  list-style: none; cursor: pointer; user-select: none;
  border-radius: 8px; transition: background .15s;
}
details.stock-block > summary.stock-heading::-webkit-details-marker { display: none; }
details.stock-block > summary.stock-heading::after {
  content: "展开 ▸"; margin-left: auto; font-size: .72rem; font-weight: 600;
  color: var(--muted); white-space: nowrap; flex-shrink: 0;
}
details.stock-block[open] > summary.stock-heading::after { content: "收起 ▾"; }
details.stock-block > summary.stock-heading:hover { background: var(--surface-3); }
details.stock-block[open] > summary.stock-heading {
  border-radius: 8px 8px 0 0; margin-bottom: 0;
}
.prose h3 .code,
.prose summary .code { font-family: ui-monospace, monospace; color: var(--accent); margin-right: 6px; }
.stock-fact-inline {
  display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px 10px;
  font-size: .78rem; font-weight: 400; color: var(--muted);
}
.stock-fact-inline::before {
  content: "·"; color: var(--border); font-weight: 700; margin: 0 2px;
}
.stock-fact-inline .fact-price { color: #e8eef6; font-weight: 600; }
.stock-fact-inline .fact-pct.up { color: var(--up); font-weight: 600; }
.stock-fact-inline .fact-pct.down { color: var(--down); font-weight: 600; }
.stock-fact-inline .fact-muted { color: var(--muted); }
.stock-fact-inline .fact-tags { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.stock-body {
  margin: 0 0 0 4px; padding: 12px 14px 14px 16px;
  border-left: 2px solid var(--border); background: rgba(28,39,56,.45);
  border-radius: 0 0 8px 8px;
}
.prose-list {
  margin: 0 0 12px; padding-left: 1.25em; list-style: disc;
}
.prose-list .prose-list { margin: 8px 0 4px; list-style: circle; }
.prose-list > li {
  margin: 10px 0; padding-left: 4px; color: #c8d4e6; line-height: 1.65;
}
.prose-list > li::marker { color: var(--muted); }
.prose-list li strong { color: #e8eef6; }
.stock-events-foot {
  margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border);
  font-size: .82rem; line-height: 1.55;
}
.stock-events-label {
  display: inline-block; margin-right: 8px; padding: 2px 8px; border-radius: 4px;
  background: var(--surface-3); color: var(--muted); font-weight: 600; font-size: .75rem;
  vertical-align: top;
}
.stock-events-text { color: #c8d4e6; }
.stock-events-text.stock-events-muted { color: var(--muted); }
.stock-event-item { margin: 4px 0 6px; color: #c8d4e6; }
.stock-event-item .event-date { color: var(--muted); font-size: .78rem; }
.prose p { margin: 8px 0; color: #c8d4e6; line-height: 1.65; }
.prose hr.prose-hr { border: none; border-top: 1px dashed var(--border); margin: 16px 0; }
.prose strong { color: #fff; }

.badge {
  display: inline-block; padding: 2px 8px; border-radius: 6px;
  font-size: .75rem; font-weight: 700; margin-right: 6px;
}
.badge-critical-bear { background: rgba(240,82,82,.2); color: #ff8a8a; }
.badge-critical-bull { background: rgba(62,207,142,.2); color: #7ee8b0; }
.badge-bear { background: rgba(240,82,82,.12); color: #f0a0a0; }
.badge-bull { background: rgba(62,207,142,.12); color: #90ddb8; }
.badge-unverified { background: rgba(245,166,35,.15); color: #ffd08a; font-size: .7rem; margin-left: 4px; }

.event-card {
  padding: 12px 14px; border-radius: 10px; background: var(--surface-2);
  border: 1px solid var(--border); margin-bottom: 10px;
}
.event-card .head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; }
.event-card .code-name { font-weight: 700; }
.event-card .groups { font-size: .8rem; color: var(--muted); }
.event-item { font-size: .88rem; margin: 4px 0; padding-left: 4px; }

details.accordion { margin-bottom: 12px; }
details.accordion summary {
  cursor: pointer; padding: 12px 16px; border-radius: var(--radius);
  background: var(--surface-2); border: 1px solid var(--border); font-weight: 600;
  list-style: none;
}
details.accordion summary::-webkit-details-marker { display: none; }
details.accordion[open] summary { border-radius: var(--radius) var(--radius) 0 0; border-bottom: none; }
details.accordion .inner { padding: 14px 16px; border: 1px solid var(--border); border-top: none; border-radius: 0 0 var(--radius) var(--radius); background: var(--surface); }

.group-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.group-tabs button {
  padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface-2); color: var(--muted); cursor: pointer; font-size: .85rem;
}
.group-tabs button.active { background: var(--accent-dim); border-color: var(--accent); color: #a8c7ff; }
.prose-panel { display: none; animation: fadeIn .2s ease; }
.prose-panel.active { display: block; }
.analysis-card { margin-bottom: 16px; }

.tag-pill {
  display: inline-block; margin: 2px 4px 2px 0; padding: 2px 7px;
  border-radius: 4px; background: var(--surface-3); font-size: .75rem; color: var(--muted);
}

.env-strip {
  margin-bottom: 20px; padding: 16px 18px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
}
.env-strip-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
  font-size: .75rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--muted);
}
.env-slot {
  padding: 2px 8px; border-radius: 999px; font-size: .72rem; font-weight: 600;
  background: var(--accent-dim); border: 1px solid rgba(79,140,255,.3); color: #a8c7ff;
  text-transform: none; letter-spacing: 0;
}
.env-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
.env-row:last-child { margin-bottom: 0; }
.env-label {
  flex: 0 0 26px; font-size: .78rem; font-weight: 800; color: var(--accent);
  line-height: 1.65; padding-top: 2px;
}
.env-segments { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; min-width: 0; }
.env-seg {
  padding: 4px 10px; border-radius: 8px; font-size: .84rem; line-height: 1.45;
  background: var(--surface-2); border: 1px solid var(--border); color: #c8d4e6;
}
.env-seg.warn { border-color: rgba(245,166,35,.35); background: rgba(245,166,35,.08); color: #ffd08a; }
.env-seg.up { border-color: rgba(240,82,82,.3); color: #ffb4b4; }
.env-seg.down { border-color: rgba(62,207,142,.3); color: #9ee8c0; }
.footer-note { margin-top: 32px; text-align: center; font-size: .78rem; color: var(--muted); }
"""

_LABEL_BADGE = {
    "大利空": "badge-critical-bear",
    "大利好": "badge-critical-bull",
    "利空": "badge-bear",
    "利好": "badge-bull",
    "轻空": "badge-bear",
    "轻多": "badge-bull",
}


def _badge_html(label: str, unverified: bool = False) -> str:
    base = str(label or "").split("·")[0]
    cls = _LABEL_BADGE.get(base, "badge-bear")
    out = f'<span class="badge {cls}">{html.escape(label)}</span>'
    if unverified or "待核实" in str(label):
        out += '<span class="badge badge-unverified">待核实</span>'
    return out


def _chip_time_label(context_as_of: str) -> str:
    s = str(context_as_of or "").strip()
    if " " in s:
        return s.split(" ", 1)[1]
    return s


def _hero_meta_chips_html(rc: dict[str, Any]) -> str:
    trade_date = html.escape(str(rc.get("trade_date") or ""))
    session = f'<span class="chip accent">上午复盘 · 午后策略 · 交易日 {trade_date}</span>'
    time_bit = _chip_time_label(str(rc.get("context_as_of") or ""))
    if rc.get("ai_ok"):
        ai_label = f"AI 已生成{time_bit}" if time_bit else "AI 已生成"
        ai = f'<span class="chip ok">{html.escape(ai_label)}</span>'
    else:
        ai_label = f"AI 未就绪{time_bit}" if time_bit else "AI 未就绪"
        ai = f'<span class="chip err">{html.escape(ai_label)}</span>'
    return session + ai


def _hero_head_html(rc: dict[str, Any]) -> str:
    return (
        f'<div class="hero-head">'
        f'<h1 class="hero-name">午间作战卡</h1>'
        f"{_summary_trigger_html(rc)}"
        f"{_hero_meta_chips_html(rc)}"
        f"</div>"
    )


def _alerts_html(rc: dict[str, Any]) -> str:
    parts = []
    if rc.get("missing_codes"):
        parts.append(f'<div class="alert alert-warn">漏股 {len(rc["missing_codes"])} 只：{html.escape(", ".join(rc["missing_codes"]))}</div>')
    if rc.get("truncated_suspected"):
        parts.append('<div class="alert alert-warn">疑似输出截断，请检查正文完整性</div>')
    if not rc.get("ai_ok") and rc.get("ai_error"):
        parts.append(f'<div class="alert alert-err">{html.escape(str(rc["ai_error"]))}</div>')
    return "".join(parts)


def _events_block_html(rc: dict[str, Any]) -> str:
    events_by_code = rc.get("events_by_code") or {}
    by_code = rc.get("by_code") or {}
    if not events_by_code:
        return ""
    cards = []
    for code in sorted(events_by_code.keys()):
        ev = events_by_code[code]
        lb = (by_code.get(code) or {}).get("local_block") or {}
        name = lb.get("name", code)
        groups = ", ".join(lb.get("groups") or [])
        items = []
        for item in ev.get("display") or []:
            items.append(
                f'<div class="event-item">{_badge_html(str(item.get("label", "")), bool(item.get("unverified")))}'
                f'{html.escape(str(item.get("title", "")))} '
                f'<span class="groups">{html.escape(str(item.get("pub_date", "")))}</span></div>'
            )
        if not items:
            items.append('<div class="event-item muted">无规则命中</div>')
        cards.append(
            f'<div class="event-card"><div class="head">'
            f'<span class="code-name">{html.escape(code)} {html.escape(name)}</span>'
            f'<span class="groups">{html.escape(groups)}</span></div>{"".join(items)}</div>'
        )
    return f'<div class="card"><div class="card-label">重大事件</div>{"".join(cards)}</div>'


def _strip_session_prefix(text: str) -> str:
    t = str(text or "").strip()
    for prefix in ("上午盘：", "上午盘:"):
        if t.startswith(prefix):
            return t[len(prefix) :].strip()
    return t


def _brief_segments(text: str) -> list[str]:
    body = _strip_session_prefix(text)
    if not body or body == "—":
        return []
    out: list[str] = []
    for seg in body.split("；"):
        seg = seg.strip()
        if not seg or seg in ("主线：", "主线:", "主线"):
            continue
        out.append(seg)
    return out


def _env_seg_class(seg: str) -> str:
    if "不可用" in seg or "存疑" in seg:
        return " warn"
    for key in ("沪指", "创业板", "深成指", "科创"):
        if not seg.startswith(key):
            continue
        try:
            pct = float(seg.split("%", 1)[0].split(key, 1)[1])
            if pct > 0:
                return " up"
            if pct < 0:
                return " down"
        except (IndexError, ValueError):
            pass
        break
    return ""


def _env_segments_html(segments: list[str]) -> str:
    if not segments:
        return '<span class="env-seg">—</span>'
    return "".join(
        f'<span class="env-seg{_env_seg_class(seg)}">{html.escape(seg)}</span>' for seg in segments
    )


def _market_env_top_html(rc: dict[str, Any]) -> str:
    ml = rc.get("market_local") or {}
    l1_segs = _brief_segments(str(ml.get("l1_brief") or ""))
    l2_segs = _brief_segments(str(ml.get("l2_brief") or ""))
    if not l1_segs and not l2_segs:
        return ""
    session = html.escape(str(rc.get("session_label") or "午间休市"))
    return (
        f'<div class="env-strip">'
        f'<div class="env-strip-head">上午大盘 <span class="env-slot">{session}</span></div>'
        f'<div class="env-row env-l1"><span class="env-label">L1</span>'
        f'<div class="env-segments">{_env_segments_html(l1_segs)}</div></div>'
        f'<div class="env-row env-l2"><span class="env-label">L2</span>'
        f'<div class="env-segments">{_env_segments_html(l2_segs)}</div></div>'
        f"</div>"
    )


def _prose_body_html(rc: dict[str, Any]) -> str:
    snap_by_code = snapshot_rows_by_code(rc.get("snapshot_rows"))
    sections = markdown_sections_to_html(rc.get("ai_body_raw") or "", stock_body=True)
    for sec in sections:
        sec["html"] = inject_stock_events_footer(
            inject_stock_fact_strips(sec["html"], snap_by_code),
            snap_by_code,
        )
    if not sections:
        return ""
    if len(sections) == 1 and sections[0]["label"] == "全文":
        return f'<div class="card prose analysis-card">{sections[0]["html"]}</div>'

    by_label = {str(s["label"]): s for s in sections}
    order = [str(g) for g in (rc.get("group_order") or []) if str(g) in by_label]
    for s in sections:
        if str(s["label"]) not in order:
            order.append(str(s["label"]))

    tab_btns: list[str] = []
    panels: list[str] = []
    for i, label in enumerate(order):
        sec = by_label.get(label)
        if not sec:
            continue
        active = " active" if i == 0 else ""
        cnt = sec.get("count", "0")
        suffix = f" ({cnt})" if cnt and cnt != "0" else ""
        tab_btns.append(
            f'<button type="button" class="{active.strip()}" data-prose-group="{html.escape(label)}">'
            f'{html.escape(label)}{suffix}</button>'
        )
        panels.append(
            f'<div class="prose-panel{active}" data-prose-panel="{html.escape(label)}">{sec["html"]}</div>'
        )
    return (
        f'<div class="card analysis-card">'
        f'<div class="group-tabs" id="prose-tabs">{"".join(tab_btns)}</div>'
        f'<div class="prose">{"".join(panels)}</div></div>'
    )


def _summary_trigger_html(rc: dict[str, Any]) -> str:
    if not rc.get("ai_ok"):
        return ""
    return (
        '<button type="button" class="summary-trigger" id="open-summary" '
        'aria-haspopup="dialog" aria-controls="summary-modal">摘要</button>'
    )


def _summary_modal_html(rc: dict[str, Any]) -> str:
    if not rc.get("ai_ok"):
        return ""
    body = push_summary_to_html(rc.get("ai_summary_raw") or "")
    return (
        '<div id="summary-modal" class="modal" role="dialog" aria-modal="true" '
        'aria-labelledby="summary-modal-title" hidden>'
        '<div class="modal-backdrop" data-close-summary></div>'
        '<div class="modal-panel">'
        '<div class="modal-head"><div><span id="summary-modal-title">推送摘要</span>'
        '<span class="modal-head-sub">与微信同版</span></div>'
        '<button type="button" class="modal-close" data-close-summary aria-label="关闭">×</button>'
        f"</div><div class=\"modal-body\">{body}</div></div></div>"
    )


def _analysis_panel(rc: dict[str, Any]) -> str:
    if rc.get("ai_ok"):
        return _prose_body_html(rc)
    msg = rc.get("ai_error") or "AI 未生成，请运行 generate --phase ai"
    return f'<div class="card alert-err">{html.escape(msg)}</div>'


MIDDAY_JS = """
function openSummaryModal() {
  const modal = document.getElementById('summary-modal');
  if (!modal) return;
  modal.hidden = false;
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeSummaryModal() {
  const modal = document.getElementById('summary-modal');
  if (!modal) return;
  modal.classList.remove('open');
  modal.hidden = true;
  document.body.style.overflow = '';
}
document.getElementById('open-summary')?.addEventListener('click', openSummaryModal);
document.querySelectorAll('[data-close-summary]').forEach(el => {
  el.addEventListener('click', closeSummaryModal);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeSummaryModal();
});
function activateProseTab(g) {
  document.querySelectorAll('#prose-tabs button').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('[data-prose-panel]').forEach(p => p.classList.remove('active'));
  document.querySelector(`#prose-tabs button[data-prose-group="${CSS.escape(g)}"]`)?.classList.add('active');
  document.querySelector(`[data-prose-panel="${CSS.escape(g)}"]`)?.classList.add('active');
}
document.querySelectorAll('#prose-tabs button').forEach(btn => {
  btn.addEventListener('click', () => activateProseTab(btn.dataset.proseGroup));
});
"""


def build_midday_page(rc: dict[str, Any]) -> str:
    trade_date = html.escape(str(rc.get("trade_date", "")))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZXTT 午间作战卡 · {trade_date}</title>
<style>{MIDDAY_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="hero">
{_hero_head_html(rc)}
{_alerts_html(rc)}
</header>
{_market_env_top_html(rc)}
<section id="panel-analysis" class="panel">{_analysis_panel(rc)}</section>
<p class="footer-note">ZXTT · 生成于 {html.escape(str(rc.get("generated_at", "")))}</p>
{_summary_modal_html(rc)}
</div>
<script>{MIDDAY_JS}</script>
</body>
</html>"""


__all__ = ["build_midday_page", "MIDDAY_CSS"]
