"""晚报结构化预期 → 早报 AI prompt（来自 expectations，非摘要截断）。"""
from __future__ import annotations

from typing import Any

_TIER0 = frozenset({"holding", "candidate"})


def _clip(text: str, max_chars: int) -> str:
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)] + "…"


def evening_recap_text(exp_stock: dict[str, Any], *, max_chars: int = 320) -> str:
    parts: list[str] = []
    short = str(exp_stock.get("short_expectation") or "").strip()
    if short:
        parts.append(short)
    net = str(exp_stock.get("message_net") or "").strip()
    if net:
        parts.append(f"消息net={net}")
    for key, val in (exp_stock.get("ai_fields") or {}).items():
        v = str(val or "").strip()
        if v:
            parts.append(f"{key}: {v}")
    return _clip(" ".join(parts), max_chars)


def _index_pct(index: dict[str, Any], key: str) -> str:
    row = index.get(key) if isinstance(index, dict) else None
    if not isinstance(row, dict):
        return ""
    pct = row.get("pct_chg")
    if pct is None:
        return ""
    name = str(row.get("name") or key)
    sign = "+" if float(pct) > 0 else ""
    return f"{name}{sign}{pct}%"


def format_evening_global(expectations: dict[str, Any]) -> str:
    if not expectations:
        return ""
    meta = expectations.get("meta") or {}
    l1 = meta.get("l1_axes") or {}
    axes = l1.get("axes") or {}
    pool = axes.get("pool") or {}
    breadth = axes.get("breadth") or {}
    index = axes.get("index") or {}
    capital = axes.get("capital") or {}
    wl = capital.get("watchlist") or {}

    parts: list[str] = []
    if pool:
        parts.append(
            f"池子{pool.get('signal', '—')}({pool.get('score', '—')}) "
            f"涨停{pool.get('limit_up', '—')} 炸{pool.get('broken_limit', '—')}"
        )
    if breadth:
        parts.append(
            f"热度{breadth.get('market_heat', '—')}° "
            f"成交{breadth.get('turnover', '—')} "
            f"涨{int(breadth.get('rise_count') or 0)}/跌{int(breadth.get('fall_count') or 0)}"
        )
    idx_bits = [_index_pct(index, k) for k in ("sh", "cy")]
    idx_bits = [b for b in idx_bits if b]
    if idx_bits:
        parts.append(" ".join(idx_bits))
    if wl:
        parts.append(
            f"自选主力净{'+' if (wl.get('total_net_yi') or 0) >= 0 else ''}"
            f"{wl.get('total_net_yi', '—')}亿 "
            f"({wl.get('inflow_count', 0)}进{wl.get('outflow_count', 0)}出)"
        )
    mainlines = meta.get("l2_mainlines") or []
    ml_names: list[str] = []
    for row in mainlines[:4]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            ml_names.append(name)
            continue
        desc = _clip(str(row.get("desc_short") or ""), 24)
        if desc:
            ml_names.append(desc)
    if ml_names:
        parts.append("主线：" + "、".join(ml_names))
    src = str(expectations.get("source_trade_date") or "").strip()
    if src:
        parts.append(f"来源交易日={src}")
    return " | ".join(parts)


def stock_tier(row: dict[str, Any]) -> str:
    if row.get("primary_stance") in _TIER0:
        return "tier0"
    if row.get("highlight"):
        return "tier1_star"
    return "tier1"


def _resolved_expected_open(row: dict[str, Any], exp_stock: dict[str, Any]) -> str:
    for src in (row, exp_stock):
        val = str(src.get("expected_open") or "").strip()
        if val:
            return val
    return "—"


def format_evening_stock_block(
    *,
    code: str,
    name: str,
    row: dict[str, Any],
    exp_stock: dict[str, Any],
    tier: str,
) -> str:
    exp_open = _resolved_expected_open(row, exp_stock)
    discipline = str(exp_stock.get("discipline") or "").strip()
    check = str(exp_stock.get("check_925") or "").strip()
    recap = evening_recap_text(exp_stock, max_chars=420 if tier == "tier0" else 160)
    critical = [str(x).strip() for x in (exp_stock.get("critical") or []) if str(x).strip()]

    if tier == "tier1":
        bits = [f"开盘预期={exp_open}"]
        if discipline:
            bits.append(f"纪律={discipline}")
        return f"- {code} {name}: " + " | ".join(bits)

    lines = [f"### {code} {name}"]
    lines.append(f"开盘预期={exp_open}")
    if discipline:
        lines.append(f"失效/纪律={discipline}")
    if check:
        lines.append(f"9:25核对={check}")
    if recap:
        lines.append(f"昨晚结论={recap}")
    if critical:
        lines.append("重大事件=" + "；".join(critical[:2]))
    return "\n".join(lines)


def build_evening_expectations_section(
    *,
    expectations: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    stocks = expectations.get("stocks") or {}
    global_line = format_evening_global(expectations)
    if not stocks and not global_line:
        return ""

    parts: list[str] = ["## [昨晚结构化预期]（来自晚报 expectations，核对时须对照，无新证据勿推翻）"]
    if global_line:
        parts.append("### 大盘环境\n" + global_line)

    tier0_blocks: list[str] = []
    tier1_star_blocks: list[str] = []
    tier1_lines: list[str] = []

    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        exp = stocks.get(code) or {}
        tier = stock_tier(row)
        block = format_evening_stock_block(
            code=code,
            name=str(row.get("name") or code),
            row=row,
            exp_stock=exp,
            tier=tier,
        )
        if tier == "tier0":
            tier0_blocks.append(block)
        elif tier == "tier1_star":
            tier1_star_blocks.append(block)
        else:
            tier1_lines.append(block)

    if tier0_blocks:
        parts.append("### 我的/想买的（完整预期）\n" + "\n\n".join(tier0_blocks))
    if tier1_star_blocks:
        parts.append("### highlight（升格预期）\n" + "\n\n".join(tier1_star_blocks))
    if tier1_lines:
        parts.append("### 其余（一行预期）\n" + "\n".join(tier1_lines))
    return "\n\n".join(parts)


def _prefer_nonempty(row_val: str, exp_val: str) -> str:
    row_s = str(row_val or "").strip()
    exp_s = str(exp_val or "").strip()
    return row_s or exp_s


def merge_evening_into_row(row: dict[str, Any], exp_stock: dict[str, Any]) -> dict[str, Any]:
    """给 checks / prompt 行附加晚报字段（expectations 非空字段可补 row 空位）。"""
    out = dict(row)
    out["expected_open"] = _prefer_nonempty(
        str(row.get("expected_open") or ""),
        str(exp_stock.get("expected_open") or ""),
    )
    out["discipline"] = _prefer_nonempty(
        str(row.get("discipline") or ""),
        str(exp_stock.get("discipline") or ""),
    )
    out["check_925"] = _prefer_nonempty(
        str(row.get("check_925") or ""),
        str(exp_stock.get("check_925") or ""),
    )
    out["evening_recap"] = evening_recap_text(exp_stock)
    out["evening_critical"] = list(exp_stock.get("critical") or [])
    return out


__all__ = [
    "build_evening_expectations_section",
    "evening_recap_text",
    "format_evening_global",
    "format_evening_stock_block",
    "merge_evening_into_row",
    "stock_tier",
]
