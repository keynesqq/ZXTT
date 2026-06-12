"""早盘开盘核对卡 HTML（对齐午间 UI）。"""
from __future__ import annotations

import html
import re
from typing import Any

from report.md_html import markdown_to_html, push_summary_to_html
from report.stock_fact_strip import inject_stock_fact_strips, snapshot_rows_by_code

_STOCK_HEAD = re.compile(
    r'(<summary class="stock-heading" id="stock-(\d{6})"[^>]*>)(.*?)(</summary>)',
    re.DOTALL,
)
_STANCE_PREFIX = re.compile(r"^（[^）]+）\s*")
_VERDICT_LINE = re.compile(r"^verdict[：:].*$", re.IGNORECASE)

MORNING_CSS = """
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
.hero-name { margin: 0; font-size: 1.65rem; font-weight: 700; letter-spacing: .02em; }
.summary-trigger {
  padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(79,140,255,.4);
  background: var(--accent-dim); color: #a8c7ff; font-size: .78rem; font-weight: 600;
  cursor: pointer; line-height: 1.4;
}
.summary-trigger:hover { background: rgba(79,140,255,.28); color: #fff; }
.hero-head .chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 999px; font-size: .8rem;
  background: var(--surface-2); border: 1px solid var(--border); color: var(--muted);
}
.chip.ok { border-color: rgba(62,207,142,.4); color: #9ee8c0; }
.chip.err { border-color: rgba(240,82,82,.45); color: #ffb4b4; }
.chip.accent { background: var(--accent-dim); border-color: rgba(79,140,255,.35); color: #a8c7ff; }
.chip.sla-ok { border-color: rgba(62,207,142,.35); color: #9ee8c0; }
.chip.sla-err { border-color: rgba(240,82,82,.4); color: #ffb4b4; }
.alert { margin-top: 10px; padding: 10px 14px; border-radius: var(--radius); font-size: .88rem; }
.alert-warn { background: rgba(245,166,35,.1); border: 1px solid rgba(245,166,35,.3); color: #ffd08a; }
.alert-err { background: rgba(240,82,82,.1); border: 1px solid rgba(240,82,82,.3); color: #ffb4b4; }

.modal { display: none; position: fixed; inset: 0; z-index: 100; }
.modal.open { display: flex; align-items: center; justify-content: center; padding: 20px 16px; }
.modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,.6); backdrop-filter: blur(2px); }
.modal-panel {
  position: relative; flex: 0 1 720px; width: 100%; max-height: min(88vh, 820px);
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); display: flex; flex-direction: column;
}
.modal-head {
  flex-shrink: 0; display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border); font-weight: 700;
}
.modal-head-sub { font-size: .78rem; font-weight: 400; color: var(--muted); margin-left: 8px; }
.modal-close {
  border: none; background: var(--surface-2); color: var(--muted); font-size: 1.25rem;
  cursor: pointer; padding: 4px 10px; border-radius: 8px;
}
.modal-close:hover { color: var(--text); background: var(--surface-3); }
.modal-body { padding: 16px 20px 20px; overflow-y: auto; }

.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 18px 20px; margin-bottom: 16px; box-shadow: var(--shadow);
}
.card-label {
  font-size: .75rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); margin-bottom: 10px; font-weight: 600;
}
.pre-stats { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.tag-pill {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  background: var(--surface-3); font-size: .78rem; color: var(--muted);
}

.env-strip {
  margin-bottom: 20px; padding: 16px 18px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
}
.env-strip-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
  font-size: .75rem; font-weight: 700; letter-spacing: .06em; color: var(--muted);
}
.env-slot {
  padding: 2px 8px; border-radius: 999px; font-size: .72rem; font-weight: 600;
  background: var(--accent-dim); border: 1px solid rgba(79,140,255,.3); color: #a8c7ff;
}
.env-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
.env-row:last-child { margin-bottom: 0; }
.env-label { flex: 0 0 52px; font-size: .78rem; font-weight: 800; color: var(--accent); }
.env-segments { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.env-seg {
  padding: 4px 10px; border-radius: 8px; font-size: .84rem;
  background: var(--surface-2); border: 1px solid var(--border); color: #c8d4e6;
}
.env-seg.up { border-color: rgba(240,82,82,.3); color: #ffb4b4; }
.env-seg.down { border-color: rgba(62,207,142,.3); color: #9ee8c0; }

table.data { width: 100%; border-collapse: collapse; font-size: .88rem; }
table.data th, table.data td {
  border-bottom: 1px solid var(--border); padding: 8px 6px; text-align: left; vertical-align: top;
}
table.data th { color: var(--muted); font-weight: 600; }
.checks-table .code-cell { font-family: ui-monospace, monospace; color: var(--accent); font-weight: 600; }
.checks-table tr.highlight td { background: rgba(79,140,255,.06); }
.gap-up { color: var(--up); font-weight: 600; }
.gap-down { color: var(--down); font-weight: 600; }

.verdict-badge {
  display: inline-block; padding: 2px 8px; border-radius: 6px;
  font-size: .72rem; font-weight: 700;
}
.verdict-超预期偏强 { background: rgba(62,207,142,.2); color: #7ee8b0; }
.verdict-超预期偏弱 { background: rgba(240,82,82,.2); color: #ff8a8a; }
.verdict-符合 { background: rgba(62,207,142,.12); color: #90ddb8; }
.verdict-部分符合 { background: rgba(79,140,255,.15); color: #a8c7ff; }
.verdict-不符合 { background: rgba(240,82,82,.15); color: #ffb4b4; }
.verdict-数据缺失 { background: rgba(245,166,35,.15); color: #ffd08a; }

.badge-status {
  display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .72rem; font-weight: 700;
}
.badge-status.refresh { background: rgba(79,140,255,.2); color: #a8c7ff; }
.badge-status.reuse { background: rgba(143,163,190,.15); color: var(--muted); }
.badge-status.no_new { background: var(--surface-3); color: var(--muted); }
.pre-titles { color: var(--muted); font-size: .82rem; line-height: 1.5; }

details.accordion { margin-bottom: 16px; }
details.accordion summary {
  cursor: pointer; padding: 12px 16px; border-radius: var(--radius);
  background: var(--surface-2); border: 1px solid var(--border); font-weight: 600; list-style: none;
}
details.accordion summary::-webkit-details-marker { display: none; }
details.accordion[open] summary {
  border-radius: var(--radius) var(--radius) 0 0; border-bottom: none;
}
details.accordion .inner {
  padding: 14px 16px; border: 1px solid var(--border); border-top: none;
  border-radius: 0 0 var(--radius) var(--radius); background: var(--surface);
  color: #c8d4e6; font-size: .9rem; white-space: pre-wrap; line-height: 1.65;
}

.push-summary { display: flex; flex-direction: column; gap: 12px; }
.push-section {
  padding: 12px 14px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--border);
}
.push-section-global { border-left: 3px solid var(--accent); }
.push-section-portfolio { border-left: 3px solid rgba(62,207,142,.75); }
.push-section-head { margin-bottom: 8px; }
.push-section-label {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: .75rem; font-weight: 800; background: var(--accent-dim); color: #a8c7ff;
}
.push-section-portfolio .push-section-label { background: rgba(62,207,142,.15); color: #9ee8c0; }
.push-section-body { font-size: .9rem; line-height: 1.65; color: #d4deee; }
.push-stock-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.push-stock-item {
  padding: 10px 12px; border-radius: 8px; background: rgba(12,17,24,.45);
  border: 1px solid rgba(42,56,79,.8); font-size: .88rem;
}
.push-code { font-family: ui-monospace, monospace; font-weight: 700; color: var(--accent); margin-right: 8px; }
.push-meta {
  margin: 4px 0 0; padding-top: 12px; border-top: 1px dashed var(--border);
  font-size: .78rem; color: var(--muted); text-align: right;
}

.prose { font-size: .94rem; }
.prose h2.section-heading {
  margin: 20px 0 12px; padding-bottom: 8px; font-size: 1.15rem;
  border-bottom: 1px solid var(--border); color: #c5d4ea;
}
details.stock-block { margin-bottom: 16px; }
details.stock-block > summary.stock-heading {
  list-style: none; cursor: pointer; user-select: none;
  margin: 0; padding: 10px 14px; border-radius: 8px;
  background: var(--surface-2); border-left: 3px solid var(--accent); font-size: 1rem;
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px;
}
details.stock-block > summary.stock-heading::-webkit-details-marker { display: none; }
details.stock-block > summary.stock-heading::after {
  content: "展开 ▸"; margin-left: auto; font-size: .72rem; color: var(--muted);
}
details.stock-block[open] > summary.stock-heading::after { content: "收起 ▾"; }
details.stock-block > summary.stock-heading:hover { background: var(--surface-3); }
details.stock-block[open] > summary.stock-heading { border-radius: 8px 8px 0 0; }
.prose summary .code { font-family: ui-monospace, monospace; color: var(--accent); margin-right: 6px; }
.stock-fact-inline { font-size: .78rem; color: var(--muted); }
.stock-fact-inline .fact-pct.up { color: var(--up); font-weight: 600; }
.stock-fact-inline .fact-pct.down { color: var(--down); font-weight: 600; }
.stock-body {
  margin: 0 0 0 4px; padding: 12px 14px 14px 16px;
  border-left: 2px solid var(--border); background: rgba(28,39,56,.45);
  border-radius: 0 0 8px 8px;
}
.prose p { margin: 8px 0; color: #c8d4e6; line-height: 1.65; }
.stock-events-foot {
  margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); font-size: .82rem;
}
.stock-events-label {
  display: inline-block; margin-right: 8px; padding: 2px 8px; border-radius: 4px;
  background: var(--surface-3); color: var(--muted); font-size: .75rem; font-weight: 600;
}
.stock-events-text { color: #c8d4e6; }
.stock-events-muted { color: var(--muted); }
.analysis-card { margin-bottom: 16px; }
.check-heading-inline {
  display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px 10px;
  font-size: .78rem; font-weight: 400; color: var(--muted);
}
.check-heading-inline::before {
  content: "·"; color: var(--border); font-weight: 700; margin: 0 2px;
}
.check-heading-inline .chk-item { white-space: nowrap; }
.check-heading-inline .verdict-badge { font-size: .7rem; }
.group-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.group-tabs button {
  padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface-2); color: var(--muted); cursor: pointer; font-size: .85rem;
}
.group-tabs button.active { background: var(--accent-dim); border-color: var(--accent); color: #a8c7ff; }
.prose-panel { display: none; }
.prose-panel.active { display: block; }
.footer-note { margin-top: 32px; text-align: center; font-size: .78rem; color: var(--muted); }
"""

_STOCK_BLOCK = re.compile(r'<details class="stock-block">.*?</details>', re.DOTALL)
_STOCK_CODE = re.compile(r'id="stock-(\d{6})"')

_MORNING_CSS = MORNING_CSS

MORNING_JS = """
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

_VERDICT_CLS = {
    "超预期偏强": "verdict-超预期偏强",
    "超预期偏弱": "verdict-超预期偏弱",
    "符合": "verdict-符合",
    "部分符合": "verdict-部分符合",
    "不符合": "verdict-不符合",
    "数据缺失": "verdict-数据缺失",
}


def _chip_time_label(context_as_of: str) -> str:
    s = str(context_as_of or "").strip()
    if " " in s:
        return s.split(" ", 1)[1]
    return s


def _hero_meta_chips(rc: dict[str, Any]) -> str:
    trade_date = html.escape(str(rc.get("trade_date") or ""))
    chips = [f'<span class="chip accent">集合竞价 · 交易日 {trade_date}</span>']
    time_bit = _chip_time_label(str(rc.get("context_as_of") or ""))
    if rc.get("ai_ok"):
        label = f"AI 已生成{time_bit}" if time_bit else "AI 已生成"
        chips.append(f'<span class="chip ok">{html.escape(label)}</span>')
    elif rc.get("ai_error"):
        chips.append(f'<span class="chip err">AI 未就绪</span>')
    if rc.get("point_count"):
        chips.append(f'<span class="chip">{int(rc["point_count"])} 采样点</span>')
    if rc.get("sla_ms") is not None:
        ok = rc.get("sla_ok")
        cls = "sla-ok" if ok else "sla-err"
        mark = "✓" if ok else "✗"
        chips.append(f'<span class="chip {cls}">SLA {int(rc["sla_ms"])}ms {mark}</span>')
    return "".join(chips)


def _env_strip_html(open_m: dict[str, Any], rc: dict[str, Any]) -> str:
    if not open_m:
        return ""
    segs_html: list[str] = []
    hint = str(open_m.get("pool_hint") or open_m.get("position_hint") or "").strip()
    if hint:
        segs_html.append(f'<span class="env-seg">{html.escape(hint)}</span>')
    for g in open_m.get("index_open_gaps") or []:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name") or g.get("symbol") or "")
        gap = g.get("open_gap_pct")
        if isinstance(gap, (int, float)):
            cls = " up" if gap > 0 else " down" if gap < 0 else ""
            segs_html.append(
                f'<span class="env-seg{cls}">{html.escape(name)} {gap:+.2f}%</span>'
            )
        else:
            segs_html.append(f'<span class="env-seg">{html.escape(name)} —</span>')
    if not segs_html:
        return ""
    session = html.escape(str(rc.get("session_label") or "集合竞价结束"))
    return (
        f'<div class="env-strip"><div class="env-strip-head">'
        f'竞价大盘 <span class="env-slot">{session}</span></div>'
        f'<div class="env-row"><span class="env-label">缺口</span>'
        f'<div class="env-segments">{"".join(segs_html)}</div></div></div>'
    )


def _hero_html(rc: dict[str, Any]) -> str:
    trigger = ""
    if rc.get("ai_ok"):
        trigger = (
            '<button type="button" class="summary-trigger" id="open-summary" '
            'aria-haspopup="dialog" aria-controls="summary-modal">摘要</button>'
        )
    return (
        f'<header class="hero"><div class="hero-head">'
        f'<h1 class="hero-name">开盘核对卡</h1>{trigger}{_hero_meta_chips(rc)}</div>'
        f"{_alerts_html(rc)}</header>"
    )


def _alerts_html(rc: dict[str, Any]) -> str:
    parts: list[str] = []
    if rc.get("missing_codes"):
        codes = ", ".join(str(c) for c in rc["missing_codes"])
        parts.append(f'<div class="alert alert-warn">漏股 {len(rc["missing_codes"])} 只：{html.escape(codes)}</div>')
    if not rc.get("ai_ok") and rc.get("ai_error"):
        parts.append(f'<div class="alert alert-err">{html.escape(str(rc["ai_error"]))}</div>')
    return "".join(parts)


def _gap_cls(v: float | None) -> str:
    if v is None:
        return ""
    if v > 0:
        return "gap-up"
    if v < 0:
        return "gap-down"
    return ""


def _verdict_badge(verdict: str) -> str:
    v = str(verdict or "")
    cls = _VERDICT_CLS.get(v, "verdict-部分符合")
    return f'<span class="verdict-badge {cls}">{html.escape(v or "—")}</span>'


def _check_heading_inline_html(row: dict[str, Any]) -> str:
    gap = row.get("end_gap")
    if isinstance(gap, (int, float)):
        gap_s = f"{gap:+.2f}%"
        gap_cls = _gap_cls(float(gap))
    else:
        gap_s = "—"
        gap_cls = ""
    parts: list[str] = []
    parts.append(
        f'<span class="chk-item">预期 {html.escape(str(row.get("expected_open") or "—"))}</span>'
    )
    parts.append(
        f'<span class="chk-item">缺口 <span class="{gap_cls}">{html.escape(gap_s)}</span></span>'
    )
    parts.append(
        f'<span class="chk-item">9:20后 {html.escape(str(row.get("shape_after_920") or "—"))}</span>'
    )
    parts.append(_verdict_badge(str(row.get("verdict") or "")))
    return f'<span class="check-heading-inline">{"".join(parts)}</span>'


def _checks_by_code(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r.get("code") or ""): r for r in rows if r.get("code")}


def _inject_checks_into_heading(prose_html: str, by_code: dict[str, dict[str, Any]]) -> str:
    if not prose_html or not by_code:
        return prose_html

    def repl(m: re.Match[str]) -> str:
        row = by_code.get(m.group(2))
        inline = _check_heading_inline_html(row) if row else ""
        return m.group(1) + m.group(3) + inline + m.group(4)

    return _STOCK_HEAD.sub(repl, prose_html)


def _snapshot_rows_from_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": r.get("code"),
            "name": r.get("name"),
            "pct_chg": r.get("end_gap"),
            "tags": [],
        }
        for r in rows
    ]


def _stock_blocks_by_code(html_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in _STOCK_BLOCK.finditer(html_text or ""):
        text = block.group(0)
        m = _STOCK_CODE.search(text)
        if m:
            out[m.group(1)] = text
    return out


def _grouped_prose_html(rc: dict[str, Any], prose: str) -> str:
    blocks = _stock_blocks_by_code(prose)
    group_order = [str(g) for g in (rc.get("group_order") or []) if str(g)]
    membership_rows = rc.get("membership_rows") or []
    if not group_order or not blocks:
        return prose

    visible: list[tuple[str, list[str]]] = []
    placed: set[str] = set()
    for g in group_order:
        codes: list[str] = []
        for row in membership_rows:
            if str(row.get("group") or "") != g:
                continue
            code = str(row.get("code") or "")
            if code and code in blocks and code not in codes:
                codes.append(code)
        if codes:
            visible.append((g, codes))
            placed.update(codes)

    orphans = [c for c in blocks if c not in placed]
    if orphans:
        visible.append(("其它", sorted(orphans)))

    if len(visible) <= 1 and visible:
        label, codes = visible[0]
        parts = [blocks[c] for c in codes if c in blocks]
        return "".join(parts) if parts else prose

    tab_btns: list[str] = []
    panels: list[str] = []
    for i, (label, codes) in enumerate(visible):
        active = " active" if i == 0 else ""
        tab_btns.append(
            f'<button type="button" class="{active.strip()}" data-prose-group="{html.escape(label)}">'
            f'{html.escape(label)} ({len(codes)})</button>'
        )
        parts = [blocks[c] for c in codes if c in blocks]
        panels.append(
            f'<div class="prose-panel{active}" data-prose-panel="{html.escape(label)}">'
            f'{"".join(parts)}</div>'
        )
    return (
        f'<div class="group-tabs" id="prose-tabs">{"".join(tab_btns)}</div>'
        f'<div class="prose">{"".join(panels)}</div>'
    )


def _clean_morning_body_text(text: str) -> str:
    out: list[str] = []
    for line in (text or "").splitlines():
        if _VERDICT_LINE.match(line.strip()):
            continue
        out.append(_STANCE_PREFIX.sub("", line))
    return "\n".join(out)


def _analysis_html(rc: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if not rc.get("ai_ok"):
        msg = rc.get("ai_error") or "AI 未生成"
        return f'<div class="card alert-err">{html.escape(str(msg))}</div>'
    snap_by_code = snapshot_rows_by_code(_snapshot_rows_from_checks(rows))
    chk_by_code = _checks_by_code(rows)
    prose = markdown_to_html(_clean_morning_body_text(rc.get("ai_body_raw") or ""), stock_body=True)
    prose = inject_stock_fact_strips(prose, snap_by_code)
    prose = _inject_checks_into_heading(prose, chk_by_code)
    body = _grouped_prose_html(rc, prose)
    return f'<div class="card analysis-card"><div class="card-label">正式报告</div>{body}</div>'


def _summary_modal(rc: dict[str, Any]) -> str:
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


def build_morning_page(rc: dict[str, Any]) -> str:
    checks = rc.get("checks") or {}
    rows = checks.get("rows") or []
    trade_date = html.escape(str(rc.get("trade_date") or ""))
    generated = html.escape(str(rc.get("generated_at") or rc.get("context_as_of") or ""))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZXTT 开盘核对卡 · {trade_date}</title>
<style>{MORNING_CSS}</style>
</head>
<body>
<div class="wrap">
{_hero_html(rc)}
{_env_strip_html(rc.get("open_market") or {{}}, rc)}
<section id="panel-analysis" class="panel">{_analysis_html(rc, rows)}</section>
<p class="footer-note">ZXTT · 生成于 {generated}</p>
{_summary_modal(rc)}
</div>
<script>{MORNING_JS}</script>
</body>
</html>"""


__all__ = ["build_morning_page", "MORNING_CSS", "_MORNING_CSS"]
