"""主 WEB 共用顶栏与基础样式。"""
from __future__ import annotations

import html


_WEB_TOPBAR_CSS = """
.web-topbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap;
  margin-bottom: 18px; padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.web-topbar-left { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.web-brand { font-weight: 600; font-size: 0.95rem; color: var(--text); text-decoration: none; }
.web-brand:hover { color: var(--accent); text-decoration: none; }
.web-trade-date { color: var(--muted); font-size: 0.88rem; font-weight: 400; }
.web-topnav { display: flex; gap: 8px; flex-wrap: wrap; }
.web-topnav a {
  display: inline-flex; align-items: center; padding: 4px 12px;
  font-size: 0.8rem; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); background: rgba(0,0,0,.15); text-decoration: none;
}
.web-topnav a:hover { border-color: var(--accent); color: var(--accent); }
.web-topnav a.active { border-color: var(--accent); background: rgba(77,159,255,.15); color: var(--accent); }
"""


def web_topbar_css() -> str:
    return _WEB_TOPBAR_CSS


def web_topbar(*, active: str, trade_date: str = "", nav_mode: str = "relative") -> str:
    q = f"?date={html.escape(trade_date)}" if trade_date else ""
    if nav_mode == "server":
        hub_href = f"/reports/index.html{q}"
        snap_href = f"/reports/snapshot.html{q}"
        feeds_href = f"/reports/feeds.html{q}"
        set_href = f"/reports/settings.html{q}"
        brand_href = hub_href
    else:
        hub_href = f"index.html{q}"
        snap_href = f"snapshot.html{q}"
        feeds_href = f"feeds.html{q}"
        set_href = f"settings.html{q}"
        brand_href = hub_href

    def _link(href: str, label: str, nav_id: str) -> str:
        cls = ' class="active"' if active == nav_id else ""
        return f'<a href="{href}"{cls}>{html.escape(label)}</a>'

    trade_label = ""
    if trade_date:
        trade_label = (
            f'<span class="web-trade-date" id="trade-date">'
            f"交易日 {html.escape(trade_date)}</span>"
        )

    return f"""<header class="web-topbar">
  <div class="web-topbar-left">
    <a class="web-brand" href="{brand_href}">ZXTT</a>
    {trade_label}
  </div>
  <nav class="web-topnav" aria-label="站点导航">
    {_link(hub_href, "作战卡", "hub")}
    {_link(snap_href, "行情快照", "snapshot")}
    {_link(feeds_href, "公告资讯", "feeds")}
    {_link(set_href, "设置", "settings")}
  </nav>
</header>"""


__all__ = ["web_topbar", "web_topbar_css"]
