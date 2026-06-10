"""晚间报告 HTML 页面（完整 UI）。"""
from __future__ import annotations

import html
import json
from typing import Any

from report.md_html import markdown_sections_to_html, markdown_to_html, push_summary_to_html

EVENING_CSS = """
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
.hero h1 { margin: 0 0 8px; font-size: 1.65rem; font-weight: 700; letter-spacing: .02em; }
.hero .sub { color: var(--muted); font-size: .92rem; margin: 0 0 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
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
  display: flex; gap: 6px; padding: 6px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 20px; position: sticky; top: 0; z-index: 10;
}
.tab-nav button {
  flex: 1; padding: 10px 16px; border: none; border-radius: 8px;
  background: transparent; color: var(--muted); font-size: .95rem; font-weight: 600;
  cursor: pointer; transition: .15s;
}
.tab-nav button:hover { color: var(--text); background: var(--surface-2); }
.tab-nav button.active { background: var(--accent); color: #fff; box-shadow: 0 2px 8px rgba(79,140,255,.35); }
.panel { display: none; animation: fadeIn .2s ease; }
.panel.active { display: block; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 18px 20px; margin-bottom: 16px; box-shadow: var(--shadow);
}
.card h2 { margin: 0 0 12px; font-size: 1.05rem; color: var(--text); }
.card-label {
  font-size: .75rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); margin-bottom: 10px; font-weight: 600;
}

.push-summary { display: flex; flex-direction: column; gap: 10px; }
.push-row { display: grid; grid-template-columns: 88px 1fr; gap: 10px; align-items: start; font-size: .9rem; }
.push-label { color: var(--accent); font-weight: 700; white-space: nowrap; }
.push-body { color: var(--text); line-height: 1.55; }
.push-body strong { color: #fff; }

.prose { font-size: .94rem; }
.prose h2.section-heading {
  margin: 28px 0 12px; padding-bottom: 8px; font-size: 1.15rem;
  border-bottom: 1px solid var(--border); color: #c5d4ea;
}
.prose h3.stock-heading {
  margin: 22px 0 10px; padding: 10px 14px; border-radius: 8px;
  background: var(--surface-2); border-left: 3px solid var(--accent); font-size: 1rem;
}
.prose h3 .code { font-family: ui-monospace, monospace; color: var(--accent); margin-right: 6px; }
.prose p { margin: 8px 0; color: #c8d4e6; }
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

.cls-grid { display: grid; gap: 10px; }
.cls-item { padding: 10px 12px; border-radius: 8px; background: var(--surface-2); border: 1px solid var(--border); font-size: .88rem; }
.cls-item .slot { font-weight: 700; color: var(--accent); margin-bottom: 4px; }

.group-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.group-tabs button {
  padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface-2); color: var(--muted); cursor: pointer; font-size: .85rem;
}
.group-tabs button.active { background: var(--accent-dim); border-color: var(--accent); color: #a8c7ff; }
.group-panel { display: none; }
.group-panel.active { display: block; }
.prose-panel { display: none; animation: fadeIn .2s ease; }
.prose-panel.active { display: block; }
.analysis-card { margin-bottom: 16px; }

.table-wrap { overflow-x: auto; border-radius: var(--radius); border: 1px solid var(--border); }
table.data { width: 100%; border-collapse: collapse; font-size: .84rem; }
table.data th {
  text-align: left; padding: 10px 12px; background: var(--surface-3);
  color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
table.data td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
table.data tr:hover td { background: rgba(79,140,255,.06); }
table.data tr:last-child td { border-bottom: none; }
td.up { color: var(--up); font-weight: 600; }
td.down { color: var(--down); font-weight: 600; }
.tag-pill {
  display: inline-block; margin: 2px 4px 2px 0; padding: 2px 7px;
  border-radius: 4px; background: var(--surface-3); font-size: .75rem; color: var(--muted);
}
.stance-pill {
  display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .75rem; font-weight: 600;
}
.stance-holding { background: rgba(79,140,255,.2); color: #a8c7ff; }
.stance-candidate { background: rgba(62,207,142,.15); color: #9ee8c0; }
.stance-watch { background: rgba(245,166,35,.15); color: #ffd08a; }
.stance-other { background: rgba(143,163,190,.15); color: var(--muted); }

.material-list { display: flex; flex-direction: column; gap: 8px; }
.material-item summary { font-size: .9rem; }
.material-meta { font-size: .8rem; color: var(--muted); margin-top: 6px; }
.status-reuse { color: #9ee8c0; }
.status-refresh, .status-first_run { color: #a8c7ff; }
.status-failed { color: #ffb4b4; }

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

_STANCE_CLASS = {
    "持仓": "stance-holding",
    "候选": "stance-candidate",
    "观察": "stance-watch",
    "其它": "stance-other",
}


def _badge_html(label: str, unverified: bool = False) -> str:
    base = str(label or "").split("·")[0]
    cls = _LABEL_BADGE.get(base, "badge-bear")
    out = f'<span class="badge {cls}">{html.escape(label)}</span>'
    if unverified or "待核实" in str(label):
        out += '<span class="badge badge-unverified">待核实</span>'
    return out


def _pct_td(val: Any) -> str:
    try:
        v = float(val)
        cls = "up" if v > 0 else "down" if v < 0 else ""
        return f'<td class="{cls}">{v:+.2f}%</td>'
    except (TypeError, ValueError):
        return f"<td>{html.escape(str(val or '—'))}</td>"


def _stance_pill(label: str, primary: str = "") -> str:
    cls = _STANCE_CLASS.get(label, "stance-other")
    return f'<span class="stance-pill {cls}">{html.escape(label or "—")}</span>'


def _chips_html(rc: dict[str, Any]) -> str:
    chips = [
        f'<span class="chip accent">{rc.get("code_count", 0)} 只分析</span>',
        f'<span class="chip accent">{rc.get("row_count", 0)} 行板块</span>',
        f'<span class="chip {"ok" if rc.get("cls_complete") else "warn"}">财联社 {html.escape(str(rc.get("cls_articles_found", "")))}</span>',
    ]
    if rc.get("ai_ok"):
        chips.append('<span class="chip ok">AI 已生成</span>')
    else:
        chips.append('<span class="chip err">AI 未就绪</span>')
    if rc.get("ai_model"):
        chips.append(f'<span class="chip">{html.escape(str(rc["ai_model"]))}</span>')
    return "".join(chips)


def _alerts_html(rc: dict[str, Any]) -> str:
    parts = []
    if rc.get("health_brief"):
        parts.append(f'<div class="health-bar">{html.escape(str(rc["health_brief"]))}</div>')
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


def _market_accordion(rc: dict[str, Any]) -> str:
    ml = rc.get("market_local") or {}
    constraints = "".join(f"<li>{html.escape(c)}</li>" for c in (ml.get("constraints") or []))
    return f"""<details class="accordion">
<summary>大盘环境（L1 / L2）</summary>
<div class="inner">
<p><strong>L1</strong> {html.escape(str(ml.get("l1_brief", "")))}</p>
<p><strong>L2</strong> {html.escape(str(ml.get("l2_brief", "")))}</p>
<ul>{constraints}</ul>
</div></details>"""


def _cls_appendix(rc: dict[str, Any]) -> str:
    slots = (rc.get("cls_digest") or {}).get("slots") or {}
    items = []
    for key, rec in slots.items():
        if not isinstance(rec, dict):
            continue
        status = "ok" if rec.get("ok") else "missing"
        summary = str(rec.get("summary") or rec.get("message") or "")[:280]
        label = rec.get("label", key)
        items.append(
            f'<div class="cls-item"><div class="slot">{html.escape(str(label))} [{status}]</div>'
            f'{html.escape(summary)}</div>'
        )
    feeds = rc.get("feeds_digest_by_code") or {}
    stats = {"reuse": 0, "refresh": 0, "first_run": 0, "failed": 0, "empty": 0}
    for rec in feeds.values():
        st = str(rec.get("status") or "")
        if st in stats:
            stats[st] += 1
    stat_line = " · ".join(f"{k} {v}" for k, v in stats.items() if v)
    return f"""<details class="accordion">
<summary>预消化资料（财联社 + feeds）</summary>
<div class="inner"><div class="cls-grid">{"".join(items)}</div>
<p class="material-meta">feeds digest：{html.escape(stat_line or "—")}</p></div></details>"""


def _snapshot_html(rc: dict[str, Any]) -> str:
    group_order = rc.get("group_order") or []
    rows = rc.get("snapshot_rows") or []
    by_group: dict[str, list] = {}
    for row in rows:
        g = str(row.get("group") or "其它")
        by_group.setdefault(g, []).append(row)

    tab_btns = []
    panels = []
    for i, g in enumerate(group_order):
        grp_rows = by_group.get(g) or []
        if not grp_rows:
            continue
        active = " active" if i == 0 else ""
        tab_btns.append(
            f'<button type="button" class="{active.strip()}" data-group="{html.escape(g)}">'
            f'{html.escape(g)} ({len(grp_rows)})</button>'
        )
        trs = []
        for r in grp_rows:
            tags = "".join(f'<span class="tag-pill">{html.escape(t)}</span>' for t in (r.get("tags") or [])[:5])
            trs.append(
                "<tr>"
                f'<td><a href="{html.escape(r.get("stock_href", ""))}" onclick="jumpStock(event)">{html.escape(str(r.get("code", "")))}</a></td>'
                f"<td>{html.escape(str(r.get('name', '')))}</td>"
                f"{_pct_td(r.get('pct_chg'))}"
                f"<td>{html.escape(str(r.get('pct_5d', '—')))}</td>"
                f"<td>{html.escape(str(r.get('main_net_yi', '—')))}</td>"
                f"<td>{tags}</td>"
                f"<td>{html.escape(str(r.get('events_label', '')))}</td>"
                f"<td>{_stance_pill(str(r.get('stance_label', '')))}</td>"
                "</tr>"
            )
        panels.append(
            f'<div class="group-panel{active}" data-group-panel="{html.escape(g)}">'
            f'<div class="table-wrap"><table class="data"><thead><tr>'
            f"<th>代码</th><th>名称</th><th>今%</th><th>5日%</th><th>主力(亿)</th><th>标签</th><th>事件</th><th>镜头</th>"
            f"</tr></thead><tbody>{''.join(trs)}</tbody></table></div></div>"
        )
    return f"""<div class="group-tabs" id="group-tabs">{"".join(tab_btns)}</div>{"".join(panels)}"""


def _materials_html(rc: dict[str, Any]) -> str:
    by_code = rc.get("by_code") or {}
    feeds = rc.get("feeds_digest_by_code") or {}
    events = rc.get("events_by_code") or {}
    items = []
    for code in sorted(by_code.keys()):
        lb = (by_code.get(code) or {}).get("local_block") or {}
        fd = feeds.get(code) or {}
        ev_disp = (events.get(code) or {}).get("display") or []
        st = str(fd.get("status") or "—")
        st_cls = f"status-{st}" if st in ("reuse", "refresh", "first_run", "failed") else ""
        ev_lines = "".join(
            f"<li>{html.escape(str(e.get('label', '')))} {html.escape(str(e.get('title', ''))[:40])}</li>"
            for e in ev_disp[:3]
        )
        items.append(
            f'<details class="accordion material-item"><summary>'
            f'<strong>{html.escape(code)}</strong> {html.escape(str(lb.get("name", "")))} '
            f'<span class="{st_cls}">[{html.escape(st)}]</span></summary><div class="inner">'
            f'<p>{html.escape(str(fd.get("summary", ""))[:300])}</p>'
            f'<p class="material-meta">{html.escape(str(fd.get("context_note", "")))}</p>'
            f"<ul>{ev_lines}</ul></div></details>"
        )
    exp = rc.get("expectations_path") or ""
    return f'<div class="card"><p class="material-meta">明日预期：{html.escape(exp)}</p></div><div class="material-list">{"".join(items)}</div>'


def _prose_body_html(rc: dict[str, Any]) -> str:
    sections = markdown_sections_to_html(rc.get("ai_body_raw") or "")
    if not sections:
        return ""
    if len(sections) == 1 and sections[0]["label"] == "全文":
        return f'<div class="card prose analysis-card"><div class="card-label">AI 正文</div>{sections[0]["html"]}</div>'

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
        f'<div class="card analysis-card"><div class="card-label">AI 正文</div>'
        f'<div class="group-tabs" id="prose-tabs">{"".join(tab_btns)}</div>'
        f'<div class="prose">{"".join(panels)}</div></div>'
    )


def _analysis_panel(rc: dict[str, Any]) -> str:
    if rc.get("ai_ok"):
        summary_html = push_summary_to_html(rc.get("ai_summary_raw") or "")
        ai_block = f"""<details class="accordion">
<summary>推送摘要（与微信同版，点击展开）</summary>
<div class="inner">{summary_html}</div></details>
{_prose_body_html(rc)}"""
    else:
        msg = rc.get("ai_error") or "AI 未生成，请运行 generate --phase ai"
        ai_block = f'<div class="card alert-err">{html.escape(msg)}</div>'
    return ai_block + _events_block_html(rc) + _market_accordion(rc) + _cls_appendix(rc)


EVENING_JS = """
function showTab(id, btn) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-nav button').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (btn) btn.classList.add('active');
}
function activateProseTab(g) {
  document.querySelectorAll('#prose-tabs button').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('[data-prose-panel]').forEach(p => p.classList.remove('active'));
  document.querySelector(`#prose-tabs button[data-prose-group="${CSS.escape(g)}"]`)?.classList.add('active');
  document.querySelector(`[data-prose-panel="${CSS.escape(g)}"]`)?.classList.add('active');
}
function jumpStock(e) {
  e.preventDefault();
  const href = e.currentTarget.getAttribute('href');
  showTab('panel-analysis', document.querySelector('.tab-nav button'));
  if (href) {
    const el = document.querySelector(href);
    const panel = el?.closest('[data-prose-panel]');
    if (panel?.dataset.prosePanel) activateProseTab(panel.dataset.prosePanel);
    location.hash = href;
    el?.scrollIntoView({behavior:'smooth'});
  }
}
document.querySelectorAll('#prose-tabs button').forEach(btn => {
  btn.addEventListener('click', () => activateProseTab(btn.dataset.proseGroup));
});
document.querySelectorAll('#group-tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    const g = btn.dataset.group;
    document.querySelectorAll('#group-tabs button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('#panel-snapshot .group-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector(`#panel-snapshot [data-group-panel="${CSS.escape(g)}"]`)?.classList.add('active');
  });
});
"""


def build_evening_page(rc: dict[str, Any]) -> str:
    trade_date = html.escape(str(rc.get("trade_date", "")))
    ctx_as_of = html.escape(str(rc.get("context_as_of", "")))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZXTT 明日作战卡 · {trade_date}</title>
<style>{EVENING_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="hero">
<h1>明日作战卡</h1>
<p class="sub">分析时刻 {ctx_as_of} · 交易日 {trade_date}</p>
<div class="chips">{_chips_html(rc)}</div>
{_alerts_html(rc)}
</header>
<nav class="tab-nav">
<button type="button" class="active" onclick="showTab('panel-analysis', this)">研判</button>
<button type="button" onclick="showTab('panel-snapshot', this)">行情快照</button>
<button type="button" onclick="showTab('panel-material', this)">素材</button>
</nav>
<section id="panel-analysis" class="panel active">{_analysis_panel(rc)}</section>
<section id="panel-snapshot" class="panel"><div class="card">{_snapshot_html(rc)}</div></section>
<section id="panel-material" class="panel">{_materials_html(rc)}</section>
<p class="footer-note">ZXTT · 生成于 {html.escape(str(rc.get("generated_at", "")))}</p>
</div>
<script>{EVENING_JS}</script>
</body>
</html>"""


__all__ = ["build_evening_page", "EVENING_CSS"]
