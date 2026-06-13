"""ZXTT 设置页 HTML（对照 ZXReport templates/settings.html + partials）。"""
from __future__ import annotations

import html
from typing import Any

from report.web_common import web_topbar, web_topbar_css

_BASE_CSS = """
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
footer { color: var(--muted); font-size: 0.78rem; text-align: center; margin-top: 28px; }
.muted { color: var(--muted); font-size: 0.78rem; }
code { font-size: 0.85em; }
"""

_SETTINGS_CSS = """
.settings-scope .hint { color: var(--muted); font-size: 0.78rem; margin: 0 0 12px; }
.settings-scope h2 { font-size: 0.95rem; margin: 0 0 10px; color: var(--accent); }
.settings-scope table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.settings-scope th, .settings-scope td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.settings-scope th { color: var(--muted); font-weight: 500; }
.settings-scope td.chk { width: 72px; text-align: center; }
.settings-scope .time-in, .settings-scope .num-in {
  width: 72px; background: rgba(0,0,0,.25); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); padding: 4px 8px; font-size: 0.82rem; font-family: inherit;
}
.settings-scope table.ann-settings td .muted { margin-left: 8px; }
.settings-scope input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer; }
.settings-scope .section-toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
.settings-scope .btn {
  padding: 8px 18px; font-size: 0.85rem; border-radius: 6px; border: 1px solid var(--border);
  background: rgba(77,159,255,.15); color: var(--accent); cursor: pointer; font-family: inherit;
}
.settings-scope .btn:hover:not(:disabled) { background: rgba(77,159,255,.25); }
.settings-scope .btn:disabled {
  opacity: 0.45; cursor: not-allowed;
  background: rgba(0,0,0,.2); color: var(--muted); border-color: var(--border);
}
.settings-scope .btn-secondary { background: rgba(0,0,0,.2); color: var(--text); }
.settings-scope .btn-secondary:hover:not(:disabled) { background: rgba(0,0,0,.32); }
.settings-scope .settings-msg { margin-top: 12px; font-size: 0.82rem; padding: 10px 12px; border-radius: 8px; display: none; }
.settings-scope .settings-msg.ok { display: block; background: rgba(0,176,80,.12); border: 1px solid var(--down); color: var(--down); }
.settings-scope .settings-msg.err { display: block; background: rgba(245,68,74,.12); border: 1px solid var(--up); color: var(--up); }
.settings-scope .err-box { color: var(--warn); font-size: 0.85rem; }
.settings-offline { color: var(--warn); font-size: 0.85rem; margin-bottom: 12px; display: none; }
.settings-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
@media (max-width: 720px) { .settings-cards { grid-template-columns: 1fr; } }
button.settings-card {
  display: flex; flex-direction: column; align-items: flex-start; gap: 4px;
  padding: 12px 14px; text-align: left; background: rgba(0,0,0,.18);
  border: 1px solid var(--border); border-radius: 10px; cursor: pointer;
  font-family: inherit; color: var(--text); transition: border-color .15s, background .15s;
  position: relative;
}
button.settings-card:hover { border-color: var(--muted); background: rgba(0,0,0,.28); }
button.settings-card.active { border-color: var(--accent); background: rgba(77,159,255,.12); box-shadow: 0 0 0 1px rgba(77,159,255,.25); }
button.settings-card.dirty::after {
  content: ''; position: absolute; top: 10px; right: 10px;
  width: 7px; height: 7px; border-radius: 50%; background: var(--warn);
}
.settings-card-title { font-size: 0.88rem; font-weight: 600; }
button.settings-card.active .settings-card-title { color: var(--accent); }
.settings-card-desc { font-size: 0.72rem; color: var(--muted); line-height: 1.35; }
.settings-panel-wrap { background: rgba(0,0,0,.12); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }
.settings-panel { display: none; }
.settings-panel.active { display: block; }
"""

_SETTINGS_JS = r"""
(function () {
  var SCOPE_LABELS = { schedule: '报告时间点', announcement: '公告采集', watchlist: '自选板块' };

  function initSettings(scope) {
    if (!scope) return;
    var root = scope.querySelector('.settings-form');
    if (!root) return;
    var msg = scope.querySelector('.settings-msg');
    var offline = scope.querySelector('.settings-offline');
    var isHttp = location.protocol === 'http:' || location.protocol === 'https:';
    if (!isHttp && offline) offline.style.display = 'block';

    var saved = { schedule: '', announcement: '', watchlist: '' };
    var saving = false;

    function showMsg(text, ok) {
      if (!msg) return;
      msg.textContent = text;
      msg.className = 'settings-msg ' + (ok ? 'ok' : 'err');
    }

    function collectSlots() {
      var slots = {};
      scope.querySelectorAll('tr[data-slot-id]').forEach(function (row) {
        var id = row.getAttribute('data-slot-id');
        slots[id] = {
          enabled: row.querySelector('input[name="slot_enabled"]').checked,
          time: row.querySelector('input[name="slot_time"]').value.trim()
        };
      });
      return slots;
    }

    function collectWatchlist() {
      var watchlist = [];
      scope.querySelectorAll('tr[data-group]').forEach(function (row) {
        var cb = row.querySelector('.cb-watchlist');
        if (cb && cb.checked) watchlist.push(cb.value);
      });
      return { watchlist_blocks: watchlist, auto_analyze_blocks: watchlist };
    }

    function collectAnnouncement() {
      return {
        lookback_days: parseInt(scope.querySelector('.ann-lookback').value, 10) || 30,
        fallback_latest_count: parseInt(scope.querySelector('.ann-fallback-count').value, 10) || 5,
        max_count: parseInt(scope.querySelector('.ann-max-count').value, 10) || 0
      };
    }

    function serializeSchedule() { return JSON.stringify({ slots: collectSlots() }); }
    function serializeAnnouncement() { return JSON.stringify(collectAnnouncement()); }
    function serializeWatchlist() { return JSON.stringify(collectWatchlist()); }

    function snapshotScope(s) {
      if (s === 'schedule') saved.schedule = serializeSchedule();
      else if (s === 'announcement') saved.announcement = serializeAnnouncement();
      else if (s === 'watchlist') saved.watchlist = serializeWatchlist();
    }

    function snapshotAll() { snapshotScope('schedule'); snapshotScope('announcement'); snapshotScope('watchlist'); }

    function isDirty(s) {
      if (s === 'schedule') return serializeSchedule() !== saved.schedule;
      if (s === 'announcement') return serializeAnnouncement() !== saved.announcement;
      if (s === 'watchlist') return serializeWatchlist() !== saved.watchlist;
      return false;
    }

    function restoreSaveButtonLabels() {
      scope.querySelectorAll('.btn-save-section').forEach(function (b) {
        var sc = b.getAttribute('data-scope');
        if (sc && SCOPE_LABELS[sc]) b.textContent = '保存' + SCOPE_LABELS[sc];
      });
    }

    function updateSaveButtons() {
      scope.querySelectorAll('.btn-save-section').forEach(function (btn) {
        btn.disabled = saving || !isHttp || !isDirty(btn.getAttribute('data-scope'));
      });
      scope.querySelectorAll('.settings-card').forEach(function (card) {
        var sc = card.getAttribute('data-panel');
        card.classList.toggle('dirty', isHttp && isDirty(sc));
      });
    }

    function showSettingsPanel(panelId) {
      scope.querySelectorAll('.settings-card').forEach(function (card) {
        var on = card.getAttribute('data-panel') === panelId;
        card.classList.toggle('active', on);
        card.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      scope.querySelectorAll('.settings-panel').forEach(function (panel) {
        var on = panel.id === 'settings-panel-' + panelId;
        panel.classList.toggle('active', on);
        if (on) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
      });
      var nextHash = '#settings-' + panelId;
      if (location.hash !== nextHash) history.replaceState(null, '', nextHash);
    }

    function bindWatchlistCheckboxes(container) {
      (container || scope).querySelectorAll('.cb-watchlist').forEach(function (cb) {
        if (cb.dataset.bound) return;
        cb.dataset.bound = '1';
        cb.addEventListener('change', updateSaveButtons);
      });
    }

    function renderBlocksTable(blocks) {
      var tbody = scope.querySelector('.watchlist-blocks-tbody');
      var wrap = scope.querySelector('.watchlist-blocks-wrap');
      var errEl = scope.querySelector('.watchlist-blocks-error');
      if (!tbody || !wrap) return;
      var prev = {};
      scope.querySelectorAll('tr[data-group]').forEach(function (row) {
        var g = row.getAttribute('data-group');
        var wcb = row.querySelector('.cb-watchlist');
        if (g && wcb) prev[g] = wcb.checked;
      });
      tbody.textContent = '';
      blocks.forEach(function (b) {
        var g = b.group_name;
        var wlOn = Object.prototype.hasOwnProperty.call(prev, g) ? prev[g] : !!b.watchlist;
        var tr = document.createElement('tr');
        tr.setAttribute('data-group', g);
        var tdWl = document.createElement('td');
        tdWl.className = 'chk';
        var cbWl = document.createElement('input');
        cbWl.type = 'checkbox';
        cbWl.className = 'cb-watchlist';
        cbWl.value = g;
        cbWl.checked = wlOn;
        tdWl.appendChild(cbWl);
        tr.appendChild(tdWl);
        var tdName = document.createElement('td');
        tdName.textContent = g + ' ';
        var idSpan = document.createElement('span');
        idSpan.className = 'muted';
        idSpan.textContent = 'id=' + b.block_id;
        tdName.appendChild(idSpan);
        tr.appendChild(tdName);
        var tdCount = document.createElement('td');
        tdCount.textContent = String(b.count);
        tr.appendChild(tdCount);
        var tdMtime = document.createElement('td');
        tdMtime.className = 'muted';
        tdMtime.textContent = b.mtime || '';
        tr.appendChild(tdMtime);
        tbody.appendChild(tr);
      });
      wrap.hidden = false;
      if (errEl) errEl.hidden = true;
      bindWatchlistCheckboxes(tbody);
      updateSaveButtons();
    }

    function refreshBlocksList(btn) {
      if (!isHttp) { showMsg('请使用 python run.py open 启动本地服务后再刷新', false); return; }
      var label = '刷新板块列表';
      btn.disabled = true;
      btn.textContent = '刷新中…';
      fetch('/api/settings')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          btn.disabled = false;
          btn.textContent = label;
          if (data.blocks_error) {
            var errEl = scope.querySelector('.watchlist-blocks-error');
            if (errEl) { errEl.textContent = data.blocks_error; errEl.hidden = false; }
            showMsg('同步失败: ' + data.blocks_error, false);
            return;
          }
          if (!data.blocks || !data.blocks.length) { showMsg('未读取到同花顺板块', false); return; }
          renderBlocksTable(data.blocks);
          showMsg('已同步 ' + data.blocks.length + ' 个板块', true);
        })
        .catch(function (err) { btn.disabled = false; btn.textContent = label; showMsg('请求失败: ' + err, false); });
    }

    function buildPayload(sectionScope) {
      var body = { scope: sectionScope };
      if (sectionScope === 'schedule') body.slots = collectSlots();
      else if (sectionScope === 'announcement') body.announcement = collectAnnouncement();
      else if (sectionScope === 'watchlist') {
        var wl = collectWatchlist();
        body.watchlist_blocks = wl.watchlist_blocks;
        body.auto_analyze_blocks = wl.auto_analyze_blocks;
      }
      return body;
    }

    function saveSection(sectionScope, btn) {
      if (!isHttp) { showMsg('请使用 python run.py open 启动本地服务后再保存', false); return; }
      if (!isDirty(sectionScope)) return;
      var label = SCOPE_LABELS[sectionScope] || sectionScope;
      saving = true;
      if (btn) btn.textContent = '保存中…';
      updateSaveButtons();
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(sectionScope))
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          saving = false;
          restoreSaveButtonLabels();
          if (!res.ok || !res.data.ok) {
            updateSaveButtons();
            showMsg((res.data && res.data.error) || (label + '保存失败'), false);
            return;
          }
          snapshotScope(sectionScope);
          updateSaveButtons();
          var extra = sectionScope === 'watchlist'
            ? ' · 快照与三报告将共用此列表'
            : '';
          showMsg(label + '已保存' + extra, true);
        })
        .catch(function (err) {
          saving = false;
          restoreSaveButtonLabels();
          updateSaveButtons();
          showMsg('请求失败: ' + err, false);
        });
    }

    scope.querySelectorAll('.settings-card').forEach(function (card) {
      card.addEventListener('click', function () { showSettingsPanel(card.getAttribute('data-panel')); });
    });
    var btnRefresh = scope.querySelector('.btn-refresh-blocks');
    if (btnRefresh) btnRefresh.addEventListener('click', function () { refreshBlocksList(btnRefresh); });
    bindWatchlistCheckboxes();
    scope.querySelectorAll('tr[data-slot-id] input, .ann-lookback, .ann-fallback-count, .ann-max-count').forEach(function (el) {
      el.addEventListener('change', updateSaveButtons);
      el.addEventListener('input', updateSaveButtons);
    });
    var btnAll = scope.querySelector('.btn-select-all-wl');
    if (btnAll) btnAll.addEventListener('click', function () {
      scope.querySelectorAll('.cb-watchlist').forEach(function (cb) { cb.checked = true; });
      updateSaveButtons();
    });
    scope.querySelectorAll('.btn-save-section').forEach(function (btn) {
      btn.addEventListener('click', function () { saveSection(btn.getAttribute('data-scope'), btn); });
    });
    snapshotAll();
    updateSaveButtons();
    var hash = (location.hash || '').replace(/^#/, '');
    if (hash.indexOf('settings-') === 0) {
      var sub = hash.slice('settings-'.length);
      if (scope.querySelector('#settings-panel-' + sub)) showSettingsPanel(sub);
    }
    window.addEventListener('hashchange', function () {
      var h = (location.hash || '').replace(/^#/, '');
      if (h.indexOf('settings-') === 0) {
        var id = h.slice('settings-'.length);
        if (scope.querySelector('#settings-panel-' + id)) showSettingsPanel(id);
      }
    });
  }
  document.querySelectorAll('.settings-scope').forEach(initSettings);
})();
"""


def _slot_rows(slots: list[dict]) -> str:
    rows: list[str] = []
    for s in slots:
        sid = html.escape(str(s.get("id") or ""))
        checked = " checked" if s.get("enabled") else ""
        rows.append(
            f"""<tr data-slot-id="{sid}">
  <td class="chk"><input type="checkbox" name="slot_enabled"{checked}></td>
  <td>{html.escape(str(s.get("label") or ""))}</td>
  <td><input type="text" class="time-in" name="slot_time" value="{html.escape(str(s.get('time') or ''))}" placeholder="HH:MM"></td>
</tr>"""
        )
    return "\n".join(rows)


def _block_rows(blocks: list[dict]) -> str:
    rows: list[str] = []
    for b in blocks:
        g = html.escape(str(b.get("group_name") or ""))
        wl = " checked" if b.get("watchlist") else ""
        rows.append(
            f"""<tr data-group="{g}">
  <td class="chk"><input type="checkbox" class="cb-watchlist" value="{g}"{wl}></td>
  <td>{g} <span class="muted">id={html.escape(str(b.get('block_id') or ''))}</span></td>
  <td>{html.escape(str(b.get('count') or ''))}</td>
  <td class="muted">{html.escape(str(b.get('mtime') or ''))}</td>
</tr>"""
        )
    return "\n".join(rows)


def _build_form_html(view: dict[str, Any]) -> str:
    ann = view.get("announcement") or {}
    account_hint = ""
    if view.get("account_dir"):
        account_hint = f'<p class="hint">同花顺账号：{html.escape(str(view["account_dir"]))}</p>'
    blocks_error = str(view.get("blocks_error") or "")
    err_hidden = "" if blocks_error else " hidden"
    err_text = html.escape(blocks_error)
    blocks = view.get("blocks") or []
    wrap_hidden = "" if blocks and not blocks_error else " hidden"
    slot_rows = _slot_rows(view.get("slots") or [])
    block_rows = _block_rows(blocks)

    return f"""<div class="settings-scope">
  <p class="settings-offline" id="settings-offline-hint">当前为离线文件，无法保存。请使用 <code>python run.py open</code> 打开。</p>
  {account_hint}
  <div class="settings-form">
    <nav class="settings-cards" role="tablist" aria-label="设置分类">
      <button type="button" class="settings-card active" role="tab" aria-selected="true" data-panel="schedule" id="settings-tab-schedule">
        <span class="settings-card-title">报告时间点</span>
        <span class="settings-card-desc">仅参考 · 手动执行</span>
      </button>
      <button type="button" class="settings-card" role="tab" aria-selected="false" data-panel="announcement" id="settings-tab-announcement">
        <span class="settings-card-title">公告采集</span>
        <span class="settings-card-desc">回溯天数 · 展示条数</span>
      </button>
      <button type="button" class="settings-card" role="tab" aria-selected="false" data-panel="watchlist" id="settings-tab-watchlist">
        <span class="settings-card-title">自选板块</span>
        <span class="settings-card-desc">同花顺板块勾选</span>
      </button>
    </nav>
    <div class="settings-panel-wrap">
      <div id="settings-panel-schedule" class="settings-panel active" role="tabpanel">
        <h2>报告时间点</h2>
        <p class="hint">各档位仅作时间参考；需在本机手动执行 <code>python run.py morning / midday / evening</code>，不会自动注册 Windows 计划任务。</p>
        <table>
          <thead><tr><th>启用</th><th>节点</th><th>时间</th></tr></thead>
          <tbody>{slot_rows}</tbody>
        </table>
        <p class="section-toolbar"><button type="button" class="btn btn-save-section" data-scope="schedule" disabled>保存报告时间点</button></p>
      </div>
      <div id="settings-panel-announcement" class="settings-panel" role="tabpanel" hidden>
        <h2>公告采集</h2>
        <p class="hint">影响资讯素材中的「公告」列。</p>
        <table class="ann-settings"><tbody>
          <tr><td>回溯天数</td><td><input type="number" class="num-in ann-lookback" min="1" max="365" value="{int(ann.get('lookback_days', 30))}"><span class="muted">近 N 个自然日内公告</span></td></tr>
          <tr><td>备用条数</td><td><input type="number" class="num-in ann-fallback-count" min="1" max="50" value="{int(ann.get('fallback_latest_count', 5))}"><span class="muted">窗口内无公告时取最新 N 条</span></td></tr>
          <tr><td>最多展示</td><td><input type="number" class="num-in ann-max-count" min="0" max="200" value="{int(ann.get('max_count', 0))}"><span class="muted">0 = 不限制</span></td></tr>
        </tbody></table>
        <p class="section-toolbar"><button type="button" class="btn btn-save-section" data-scope="announcement" disabled>保存公告采集</button></p>
      </div>
      <div id="settings-panel-watchlist" class="settings-panel" role="tabpanel" hidden>
        <h2>自选板块</h2>
        <p class="hint">勾选同花顺 PC 板块 → 写入 config → <strong>行情快照</strong>与<strong>开盘/午间/晚间三报告</strong>共用同一股票列表。保存后自动刷新快照页。</p>
        <p class="err-box watchlist-blocks-error"{err_hidden}>{err_text}</p>
        <div class="watchlist-blocks-wrap"{wrap_hidden}>
          <table>
            <thead><tr><th class="chk">启用</th><th>板块</th><th>数量</th><th>更新</th></tr></thead>
            <tbody class="watchlist-blocks-tbody">{block_rows}</tbody>
          </table>
        </div>
        <p class="section-toolbar">
          <button type="button" class="btn btn-secondary btn-refresh-blocks">刷新板块列表</button>
          <button type="button" class="btn btn-secondary btn-select-all-wl">全选</button>
          <button type="button" class="btn btn-save-section" data-scope="watchlist" disabled>保存自选板块</button>
        </p>
      </div>
    </div>
    <div class="settings-msg"></div>
  </div>
</div>"""


def build_settings_page(view: dict[str, Any] | None = None, *, nav_mode: str = "relative") -> str:
    from core.trading_calendar import market_data_date, today_cn
    from report.settings import build_settings_view

    view = view if view is not None else build_settings_view()
    trade_date = market_data_date(today_cn()).isoformat()
    nav = web_topbar(active="settings", trade_date=trade_date, nav_mode=nav_mode)
    form = _build_form_html(view)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ZXTT 设置</title>
<style>{_BASE_CSS}{web_topbar_css()}{_SETTINGS_CSS}</style>
</head>
<body>
<div class="wrap">
  {nav}
  <h1>ZXTT 设置</h1>
  <p class="meta">保存后写入 config.yaml；报告需手动执行 evening / midday / morning 命令。</p>
  {form}
  <footer>个人研究工具 · ZXTT</footer>
</div>
<script>{_SETTINGS_JS}</script>
</body>
</html>"""


__all__ = ["build_settings_page"]
