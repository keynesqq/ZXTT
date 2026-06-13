"""行情快照独立页（静态 HTML，UI 对齐 ZXReport snapshot.html）。"""
from __future__ import annotations

import html
import json
from typing import Any

from report.web_common import web_topbar, web_topbar_css

_SNAPSHOT_CSS = """
:root {
  --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b98a8;
  --accent:#4d9fff; --up:#f5444a; --down:#00b050; --border:#2a3544;
  --warn:#e6a817;
}
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--text);
  margin: 0; padding: 24px; line-height: 1.55;
}
.wrap { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.45rem; margin: 0 0 8px; }
.meta { color: var(--muted); font-size: 0.88rem; margin-bottom: 20px; }
section {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px 18px; margin-bottom: 18px;
}
h2 { font-size: 1rem; margin: 0 0 12px; color: var(--accent); }
.up { color: var(--up); }
.down { color: var(--down); }
.muted { color: var(--muted); font-size: 0.78rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--border); text-align: left; }
th { color: var(--muted); font-weight: 500; }
footer { color: var(--muted); font-size: 0.78rem; text-align: center; margin-top: 28px; }
.warn-badge {
  display: inline-block; background: rgba(230,168,23,.2); color: var(--warn);
  border: 1px solid var(--warn); border-radius: 4px; padding: 0 5px;
  font-size: 0.72rem; cursor: help; margin-left: 4px;
}
.missing { color: var(--up); }
.report-stale-hint { color: var(--warn); margin: 4px 0 0; font-size: 0.84rem; }
.snap-table-wrap { overflow-x: auto; }
.snap-table-wrap table { white-space: nowrap; }
.snap-table-wrap th { position: sticky; top: 0; background: var(--card); z-index: 1; }
.snap-tab-root { margin-bottom: 8px; }
.snap-tab-bar {
  display: flex; flex-direction: row; align-items: center;
  gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.snap-group-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 14px; font-size: 0.82rem; font-weight: 500;
  background: rgba(0,0,0,.2); border: 1px solid var(--border);
  border-radius: 6px; cursor: pointer; color: var(--text); font-family: inherit;
}
.snap-group-btn:hover { border-color: var(--muted); }
.snap-group-btn.active {
  border-color: var(--accent); background: rgba(77,159,255,.15); color: var(--accent);
}
.snap-group-btn .count { font-size: 0.75rem; font-weight: 400; color: var(--muted); }
.snap-group-btn.active .count { color: var(--accent); opacity: 0.85; }
.snap-panels { width: 100%; }
.snap-panel { display: none; }
.snap-panel.active { display: block; }
.snap-panel-empty { color: var(--muted); font-size: 0.85rem; padding: 12px 0; }
.watchlist-source {
  margin: 0 0 16px; padding: 10px 14px; border-radius: 8px;
  border: 1px solid var(--border); background: rgba(77,159,255,.08);
  font-size: 0.82rem; line-height: 1.55;
}
.watchlist-source a { color: var(--accent); }
"""

_SNAPSHOT_JS = """
(function () {
  function showSnapPanel(root, groupName) {
    root.querySelectorAll('.snap-group-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-group') === groupName);
    });
    root.querySelectorAll('.snap-panel').forEach(function (panel) {
      panel.classList.toggle('active', panel.getAttribute('data-group') === groupName);
    });
  }
  document.querySelectorAll('.snap-tab-root').forEach(function (root) {
    root.querySelectorAll('.snap-group-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showSnapPanel(root, btn.getAttribute('data-group'));
      });
    });
  });
})();
"""


def _fmt_pct(val: Any) -> str:
    if val is None or val == "":
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if n >= 0 else ""
    return f"{sign}{n:.2f}%"


def _fmt_num(val: Any, *, suffix: str = "") -> str:
    if val is None or val == "":
        return "—"
    if isinstance(val, (int, float)):
        return f"{val:g}{suffix}"
    return html.escape(str(val))


def _pct_class(val: Any) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return ""
    if n > 0:
        return "up"
    if n < 0:
        return "down"
    return ""


def _render_full_row(r: dict[str, Any]) -> str:
    code = html.escape(str(r.get("code") or ""))
    name = html.escape(str(r.get("name") or ""))
    warnings = r.get("warnings") or []
    warn_html = ""
    if warnings:
        title = html.escape("；".join(str(w) for w in warnings))
        warn_html = f'<span class="warn-badge" title="{title}">⚠</span>'
    missing = '<span class="missing">缺失</span>' if r.get("data_missing") else ""
    st_flag = "ST" if r.get("is_st") else ""
    board = html.escape(str(r.get("board") or "—"))
    pct_cls = _pct_class(r.get("pct_chg"))
    return f"""<tr data-code="{code}" data-group="{html.escape(str(r.get('group') or ''))}">
  <td>{code}</td>
  <td class="snap-name">{name}{warn_html}{missing}</td>
  <td class="snap-val">{html.escape(str(r.get('industry') or '—'))}</td>
  <td class="snap-val">{board}{st_flag}</td>
  <td class="snap-val snap-price">{_fmt_num(r.get('price'))}</td>
  <td class="snap-val">{_fmt_num(r.get('pre_close'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('open_gap_pct'))}</td>
  <td class="snap-val snap-pct {pct_cls}">{_fmt_pct(r.get('pct_chg'))}</td>
  <td class="snap-val">{html.escape(str(r.get('limit_status') or '—'))}</td>
  <td class="snap-val">{_fmt_num(r.get('consecutive_boards'))}</td>
  <td class="snap-val">{_fmt_num(r.get('open'))}</td>
  <td class="snap-val">{_fmt_num(r.get('high'))}</td>
  <td class="snap-val">{_fmt_num(r.get('low'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('amplitude')) if r.get('amplitude') is not None else '—'}</td>
  <td class="snap-val">{_fmt_pct(r.get('turnover')) if r.get('turnover') is not None else '—'}</td>
  <td class="snap-val">{_fmt_num(r.get('amount_yi'))}</td>
  <td class="snap-val">{_fmt_num(r.get('amount_ratio'), suffix='×') if r.get('amount_ratio') is not None else '—'}</td>
  <td class="snap-val">{_fmt_pct(r.get('pct_5d'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('pct_20d'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('pct_60d'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('pct_ytd'))}</td>
  <td class="snap-val">{_fmt_num(r.get('ma5'))}</td>
  <td class="snap-val">{_fmt_num(r.get('ma20'))}</td>
  <td class="snap-val">{_fmt_num(r.get('ma60'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('ma5_dist'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('ma20_dist'))}</td>
  <td class="snap-val">{_fmt_pct(r.get('ma60_dist'))}</td>
  <td class="snap-val">{_fmt_num(r.get('pe'))}</td>
  <td class="snap-val">{_fmt_num(r.get('pb'))}</td>
  <td class="snap-val">{_fmt_num(r.get('total_mv_yi'))}</td>
  <td class="snap-val">{_fmt_num(r.get('float_mv_yi'))}</td>
  <td class="snap-val">{html.escape(str(r.get('intraday_shape') or '—'))}</td>
  <td class="snap-val snap-at muted">{html.escape(str(r.get('snapshot_at') or '—'))}</td>
</tr>"""


_FULL_HEADERS = (
    "代码", "名称", "行业", "板", "现价", "昨收", "缺口%", "今%", "状态", "连板",
    "开", "高", "低", "振幅", "换手", "额(亿)", "额比",
    "5日", "20日", "60日", "今年",
    "MA5", "MA20", "MA60", "MA5距%", "MA20距%", "MA60距%",
    "PE", "PB", "总市值", "流通值", "形态", "采集",
)


def _build_grouped_table(rows: list[dict], groups: list[str]) -> str:
    by_group: dict[str, list[dict]] = {g: [] for g in groups}
    for row in rows:
        g = str(row.get("group") or "").strip()
        if g in by_group:
            by_group[g].append(row)

    active_idx = 0
    for i, g in enumerate(groups):
        if by_group.get(g):
            active_idx = i
            break

    tab_btns: list[str] = []
    panels: list[str] = []
    for i, g in enumerate(groups):
        cnt = len(by_group.get(g) or [])
        active = " active" if i == active_idx else ""
        tab_btns.append(
            f'<button type="button" class="snap-group-btn{active}" data-group="{html.escape(g)}">'
            f'{html.escape(g)}<span class="count">{cnt}只</span></button>'
        )
        if cnt:
            body_rows = "\n".join(_render_full_row(r) for r in by_group[g])
            thead = "".join(f"<th>{html.escape(h)}</th>" for h in _FULL_HEADERS)
            panel_html = f"""<div class="snap-table-wrap">
<table>
  <thead><tr>{thead}</tr></thead>
  <tbody>{body_rows}</tbody>
</table>
</div>"""
        else:
            panel_html = '<p class="snap-panel-empty">该分组暂无股票</p>'
        panels.append(
            f'<div class="snap-panel{active}" data-group="{html.escape(g)}">{panel_html}</div>'
        )

    return f"""<div class="snap-tab-root" data-variant="full">
  <div class="snap-tab-bar">{"".join(tab_btns)}</div>
  <div class="snap-panels">{"".join(panels)}</div>
</div>"""


def _render_watchlist_source_banner(ctx: dict[str, Any], *, nav_mode: str = "relative") -> str:
    src = ctx.get("watchlist_source") or {}
    if src.get("error"):
        set_href = "/reports/settings.html" if nav_mode == "server" else "settings.html"
        return (
            f'<p class="meta watchlist-source">股票来源：同花顺 PC · '
            f'<span class="muted">{html.escape(str(src["error"]))}</span> · '
            f'<a href="{set_href}">前往设置</a></p>'
        )
    groups = "、".join(html.escape(g) for g in (src.get("watchlist_groups") or [])[:8])
    extra = len(src.get("watchlist_groups") or []) - 8
    if extra > 0:
        groups += f" 等{len(src.get('watchlist_groups') or [])}组"
    wl_n = int(src.get("watchlist_stock_count") or 0)
    set_href = "/reports/settings.html" if nav_mode == "server" else "settings.html"
    return (
        f'<p class="meta watchlist-source">股票列表：<strong>同花顺 PC</strong> · '
        f'板块 {groups or "未配置"} · 共 {wl_n} 只 · '
        f'<span class="muted">行情快照与开盘/午间/晚间三报告共用此列表（设置页勾选）</span> · '
        f'<a href="{set_href}">修改板块</a></p>'
    )


def build_snapshot_page(ctx: dict[str, Any], *, nav_mode: str = "relative") -> str:
    trade_date = html.escape(str(ctx.get("trade_date") or ""))
    row_count = int(ctx.get("row_count") or 0)
    generated_at = html.escape(str(ctx.get("generated_at") or ""))
    stale_hint = ""
    if ctx.get("snapshot_stale"):
        stale_hint = (
            '<p class="meta report-stale-hint" role="status">'
            "⚠ 行情快照可能已过期，请运行 quote query 或报告采集后刷新本页。</p>"
        )
    gen_part = f" · 快照 {generated_at}" if generated_at else ""
    table_html = _build_grouped_table(ctx.get("rows") or [], ctx.get("snapshot_groups") or [])
    source_banner = _render_watchlist_source_banner(ctx, nav_mode=nav_mode)
    nav = web_topbar(active="snapshot", trade_date=str(ctx.get("trade_date") or ""), nav_mode=nav_mode)
    boot = json.dumps(
        {"trade_date": ctx.get("trade_date"), "row_count": row_count, "source": ctx.get("source")},
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>行情快照 · {trade_date}</title>
<style>{_SNAPSHOT_CSS}{web_topbar_css()}</style>
</head>
<body data-trade-date="{trade_date}">
<div class="wrap">
  {nav}
  <h1>行情快照</h1>
  {source_banner}
  <p class="meta">{trade_date} · {row_count} 条 · 展示口径：同花顺（腾讯校验/补全){gen_part}</p>
  {stale_hint}
  <section class="snapshot-section">
    <h2>快照表</h2>
    {table_html}
  </section>
  <footer>个人研究工具，非投资建议 · ZXTT · 悬停 ⚠ 查看校验详情</footer>
</div>
<script>window.__SNAPSHOT_BOOT__={boot};</script>
<script>{_SNAPSHOT_JS}</script>
</body>
</html>"""


__all__ = ["build_snapshot_page"]
