"""公告资讯独立页（静态 HTML，UI 对齐 ZXReport feeds.html）。"""
from __future__ import annotations

import html
import json
from typing import Any

from report.web_common import web_topbar, web_topbar_css

_FEEDS_CSS = """
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
.muted { color: var(--muted); font-size: 0.78rem; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
ul { margin: 6px 0; padding-left: 18px; font-size: 0.86rem; }
li { margin: 5px 0; }
details { margin: 8px 0; border: 1px solid var(--border); border-radius: 8px; padding: 0 12px; background: rgba(0,0,0,.12); }
summary { cursor: pointer; padding: 10px 0; font-size: 0.88rem; }
footer { color: var(--muted); font-size: 0.78rem; text-align: center; margin-top: 28px; }
.report-stale-hint { color: var(--warn); margin: 4px 0 0; font-size: 0.84rem; }
.watchlist-source {
  margin: 0 0 16px; padding: 10px 14px; border-radius: 8px;
  border: 1px solid var(--border); background: rgba(77,159,255,.08);
  font-size: 0.82rem; line-height: 1.55;
}
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
.feeds-panel-wrap {
  background: rgba(0,0,0,.12);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}
.feeds-panel { display: none; }
.feeds-panel.active { display: block; }
.feeds-warn { color: var(--warn); font-size: 0.78rem; margin: 4px 0 8px; }
.empty { color: var(--muted); font-size: 0.82rem; }
"""

_FEEDS_JS = """
(function () {
  function showFeedsPanel(root, panelId) {
    root.querySelectorAll('.snap-group-btn').forEach(function (btn) {
      var on = btn.getAttribute('data-panel') === String(panelId);
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    root.querySelectorAll('.feeds-panel').forEach(function (panel) {
      var on = panel.id === 'feeds-panel-' + panelId;
      panel.classList.toggle('active', on);
      if (on) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    });
  }
  document.querySelectorAll('.feeds-scope').forEach(function (root) {
    root.querySelectorAll('.snap-group-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showFeedsPanel(root, btn.getAttribute('data-panel'));
      });
    });
  });
})();
"""


def _render_feed_item(item: dict[str, Any]) -> str:
    pub = html.escape(str(item.get("pub_date") or ""))
    pub_time = str(item.get("pub_time") or "").strip()
    if pub_time:
        pub = f"{pub} {html.escape(pub_time)}"
    fetched = str(item.get("fetched_at") or "").strip()
    fetched_part = f" · 采集 {html.escape(fetched)}" if fetched else ""
    title = html.escape(str(item.get("title") or ""))
    url = str(item.get("url") or "").strip()
    title_html = (
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{title}</a>'
        if url
        else title
    )
    source = str(item.get("source") or "").strip()
    source_part = f' <span class="muted">· {html.escape(source)}</span>' if source else ""
    return (
        f"<li><span class=\"muted\">{pub}{fetched_part}</span> "
        f"{title_html}{source_part}</li>"
    )


def _render_stock(stock: dict[str, Any], categories: list[str]) -> str:
    code = html.escape(str(stock.get("code") or ""))
    name = html.escape(str(stock.get("name") or ""))
    industry = str(stock.get("industry") or "").strip()
    industry_part = f" · {html.escape(industry)}" if industry else ""
    queried = str(stock.get("queried_at") or "").strip()
    queried_part = f" · 查询 {html.escape(queried)}" if queried else ""
    warns = "".join(
        f'<p class="feeds-warn">⚠ {html.escape(str(w))}</p>' for w in (stock.get("warnings") or [])
    )
    cats_html: list[str] = []
    cats = stock.get("categories") or {}
    for cat in categories:
        items = cats.get(cat) or []
        if items:
            body = f"<ul>{''.join(_render_feed_item(it) for it in items)}</ul>"
        else:
            body = '<p class="muted">无</p>'
        cats_html.append(
            f"<details><summary>{html.escape(cat)}（{len(items)}）</summary>{body}</details>"
        )
    return (
        f"<details><summary>{code} {name}{industry_part}{queried_part}</summary>"
        f"{warns}{''.join(cats_html)}</details>"
    )


def _build_grouped_panels(ctx: dict[str, Any]) -> str:
    groups: dict[str, list] = ctx.get("groups") or {}
    order: list[str] = ctx.get("feeds_group_order") or list(groups.keys())
    categories: list[str] = ctx.get("categories") or []
    if not order:
        return '<p class="empty">暂无资讯素材</p>'

    active_idx = 0
    for i, g in enumerate(order):
        if groups.get(g):
            active_idx = i
            break

    tab_btns: list[str] = []
    panels: list[str] = []
    for i, g in enumerate(order):
        stocks = groups.get(g) or []
        active = " active" if i == active_idx else ""
        hidden = "" if i == active_idx else ' hidden=""'
        tab_btns.append(
            f'<button type="button" class="snap-group-btn{active}" role="tab" '
            f'data-group="{html.escape(g)}" data-panel="{i}" id="feeds-tab-{i}" '
            f'aria-selected="{"true" if i == active_idx else "false"}">'
            f'{html.escape(g)}<span class="count">{len(stocks)}只</span></button>'
        )
        if stocks:
            body = "".join(_render_stock(s, categories) for s in stocks)
        else:
            body = '<p class="empty">该分组暂无股票</p>'
        panels.append(
            f'<div id="feeds-panel-{i}" class="feeds-panel{active}" role="tabpanel" '
            f'data-group="{html.escape(g)}" aria-labelledby="feeds-tab-{i}"{hidden}>{body}</div>'
        )

    return f"""<div class="feeds-scope snap-tab-root">
  <div class="snap-tab-bar" role="tablist" aria-label="资讯板块">{"".join(tab_btns)}</div>
  <div class="feeds-panel-wrap">{"".join(panels)}</div>
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
    wl_n = int(src.get("watchlist_stock_count") or 0)
    set_href = "/reports/settings.html" if nav_mode == "server" else "settings.html"
    return (
        f'<p class="meta watchlist-source">股票列表：<strong>同花顺 PC</strong> · '
        f'板块 {groups or "未配置"} · 共 {wl_n} 只 · '
        f'<span class="muted">与行情快照共用自选列表</span> · '
        f'<a href="{set_href}">修改板块</a></p>'
    )


def build_feeds_page(ctx: dict[str, Any], *, nav_mode: str = "relative") -> str:
    trade_date = html.escape(str(ctx.get("trade_date") or ""))
    stock_count = int(ctx.get("stock_count") or 0)
    item_count = int(ctx.get("item_count") or 0)
    ann_lb = ctx.get("ann_lookback_days")
    news_lb = ctx.get("news_lookback_days")
    lb_parts: list[str] = []
    if ann_lb is not None:
        lb_parts.append(f"公告近{ann_lb}日")
    if news_lb is not None:
        lb_parts.append(f"资讯近{news_lb}日")
    lb_text = " · ".join(lb_parts) if lb_parts else "公告(巨潮) / 研报·资讯·行业(东财)"
    updated_parts: list[str] = []
    if ctx.get("ann_updated_at"):
        updated_parts.append(f"公告 {html.escape(str(ctx['ann_updated_at']))}")
    if ctx.get("news_updated_at"):
        updated_parts.append(f"资讯 {html.escape(str(ctx['news_updated_at']))}")
    updated_text = f" · {' · '.join(updated_parts)}" if updated_parts else ""

    stale_hint = ""
    if ctx.get("feeds_missing"):
        stale_hint = (
            '<p class="meta report-stale-hint" role="status">'
            "⚠ 暂无公告/资讯缓存，请运行报告采集或 "
            "<code>python run.py announcement query</code> / "
            "<code>python run.py news query</code> 后刷新本页。</p>"
        )

    nav = web_topbar(active="feeds", trade_date=str(ctx.get("trade_date") or ""), nav_mode=nav_mode)
    source_banner = _render_watchlist_source_banner(ctx, nav_mode=nav_mode)
    panels_html = _build_grouped_panels(ctx)
    boot = json.dumps(
        {
            "trade_date": ctx.get("trade_date"),
            "stock_count": stock_count,
            "item_count": item_count,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>公告资讯 · {trade_date}</title>
<style>{_FEEDS_CSS}{web_topbar_css()}</style>
</head>
<body data-trade-date="{trade_date}">
<div class="wrap">
  {nav}
  <h1>公告资讯</h1>
  {source_banner}
  <p class="meta">{trade_date} · {stock_count} 只 · {item_count} 条 · {lb_text}{updated_text}</p>
  {stale_hint}
  {panels_html}
  <footer>个人研究工具，非投资建议 · ZXTT</footer>
</div>
<script>window.__FEEDS_BOOT__={boot};</script>
<script>{_FEEDS_JS}</script>
</body>
</html>"""


__all__ = ["build_feeds_page"]
