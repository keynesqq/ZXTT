"""参数化 AI 合成（evening / midday 共用）。"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from ai.llm import chat
from ai.parse import codes_in_body, split_ai_report

_STANCE_FROM_HINT = {
    "持仓": "holding",
    "候选": "candidate",
    "观察": "watch_right",
    "其它": "theme_other",
}

_SHARDS: list[tuple[str, str, str, str, float]] = [
    ("holding", "持仓", "我的·持仓深度", "【我的】", 120.0),
    ("candidate", "候选", "想买的·候选跟踪", "【想买的】", 120.0),
    ("watch_right", "观察", "观察·跌幅达预期", "【观察】", 150.0),
    ("theme_other", "其它", "其它·风向跟踪", "【其它】", 90.0),
]

_SEP = re.compile(r"^---\s*$", re.MULTILINE)


def _stance_counts(stocks: list[dict]) -> dict[str, int]:
    counts = {"holding": 0, "candidate": 0, "watch_right": 0, "theme_other": 0}
    for s in stocks:
        hint = str(s.get("stance_hint") or "")
        key = _STANCE_FROM_HINT.get(hint, "theme_other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _max_tokens(stocks: list[dict], *, cap: int) -> int:
    c = _stance_counts(stocks)
    est = 2000 + c["holding"] * 480 + c["candidate"] * 360 + c["watch_right"] * 180 + c["theme_other"] * 80
    return min(cap, est)


def _stocks_for_stance(stocks: list[dict], stance: str) -> list[dict]:
    return [s for s in stocks if _STANCE_FROM_HINT.get(str(s.get("stance_hint") or ""), "theme_other") == stance]


def _normalize_global_raw(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if not raw.lstrip().startswith("##"):
        raw = f"## 推送摘要\n{raw}"
    _, summary = split_ai_report(raw)
    return summary.strip()


def _parse_shard_raw(text: str, *, push_label: str, chapter: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return f"{push_label}无", f"## {chapter}\n"
    parts = _SEP.split(raw, maxsplit=1)
    if len(parts) == 2:
        summary_part = parts[0].strip()
        body_part = parts[1].strip()
    else:
        body_match = re.search(rf"(^##\s*{re.escape(chapter)}\b.*)", raw, re.MULTILINE | re.DOTALL)
        if body_match:
            body_part = body_match.group(1).strip()
            summary_part = raw[: body_match.start()].strip()
        else:
            summary_part = raw
            body_part = f"## {chapter}\n"
    if push_label not in summary_part:
        lines = [ln for ln in summary_part.splitlines() if ln.strip()]
        summary_part = "\n".join(lines) if lines else f"{push_label}无"
    if not body_part.lstrip().startswith("##"):
        body_part = f"## {chapter}\n{body_part}".strip()
    return summary_part, body_part


def _empty_shard(push_label: str, chapter: str) -> tuple[str, str]:
    return f"{push_label}无", f"## {chapter}\n（本档无股票）"


def merge_sharded(global_summary: str, shard_outputs: list[tuple[str, str, str]]) -> str:
    summary_lines = [global_summary.strip()] if global_summary.strip() else []
    body_parts: list[str] = []
    for _, summary_part, body_part in shard_outputs:
        if summary_part.strip():
            summary_lines.append(summary_part.strip())
        if body_part.strip():
            body_parts.append(body_part.strip())
    summary = "\n".join(summary_lines)
    body = "\n\n".join(body_parts)
    return f"## 推送摘要\n{summary}\n\n{body}".strip()


def _chat_with_retry(
    system: str,
    user: str,
    *,
    max_tokens: int,
    timeout_sec: float,
    retries: int = 2,
) -> tuple[str, str, str]:
    raw, model, err = "", "", ""
    for _ in range(retries):
        raw, model, err = chat(system, user, max_tokens=max_tokens, timeout_sec=timeout_sec)
        if raw and not err:
            return raw, model, err
    return raw, model, err


def run_monolithic_synthesize(
    ctx: dict[str, Any],
    user_prompt: str,
    *,
    system: str,
    group_max_tokens: int,
    estimate_max_tokens: Callable[[list[dict], int], int] | None = None,
) -> dict[str, Any]:
    t0 = time.monotonic()
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    token_fn = estimate_max_tokens or _max_tokens
    max_tok = token_fn(stocks, cap=group_max_tokens)
    raw, model, err = _chat_with_retry(
        system,
        user_prompt,
        max_tokens=max_tok,
        timeout_sec=180.0,
    )
    return {
        "mode": "monolithic",
        "raw": raw,
        "model": model,
        "error": err,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "shards": [],
    }


def run_sharded_synthesize(
    ctx: dict[str, Any],
    *,
    systems: tuple[str, str, str],
    build_global_prompt: Callable[[dict[str, Any]], str],
    build_shard_prompt: Callable[[dict[str, Any], str], str],
    build_user_prompt: Callable[[dict[str, Any]], str],
    cfg: dict[str, Any],
    group_max_tokens: int,
    touch_progress: Callable[[dict[str, Any], str, int], None] | None = None,
    estimate_max_tokens: Callable[[list[dict], int], int] | None = None,
    shard_specs: list[tuple[str, str, str, str, float]] | None = None,
    stocks_for_shard: Callable[[list[dict], str], list[dict]] | None = None,
    critical_shard_keys: list[str] | None = None,
) -> dict[str, Any]:
    t0 = time.monotonic()
    monolithic_system, global_system, shard_system = systems
    workers = min(int(cfg.get("synthesize_workers") or 4), 4)
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    token_fn = estimate_max_tokens or _max_tokens
    shards = shard_specs or _SHARDS
    shard_records: list[dict[str, Any]] = []

    global_prompt = build_global_prompt(ctx)
    global_raw, global_model, global_err = _chat_with_retry(
        global_system,
        global_prompt,
        max_tokens=1200,
        timeout_sec=60.0,
    )
    global_summary = _normalize_global_raw(global_raw)
    if touch_progress:
        touch_progress(ctx, "全局摘要已完成，分档并行合成中…", 48)
    if not global_summary:
        return {
            "mode": "sharded",
            "raw": "",
            "model": global_model,
            "error": global_err or "global_empty",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "shards": [{"phase": "global", "ok": False, "error": global_err}],
        }

    def _run_shard(item: tuple[str, str, str, str, float]) -> tuple[str, str, str, dict[str, Any]]:
        stance, _hint, chapter, push_label, timeout = item
        if stocks_for_shard is not None:
            tier_stocks = stocks_for_shard(stocks, stance)
        else:
            tier_stocks = _stocks_for_stance(stocks, stance)
        rec: dict[str, Any] = {"stance": stance, "stock_count": len(tier_stocks)}
        t1 = time.monotonic()
        if not tier_stocks:
            summary_part, body_part = _empty_shard(push_label, chapter)
            rec.update({"ok": True, "skipped": True, "duration_ms": 0})
            return stance, summary_part, body_part, rec

        user = build_shard_prompt(ctx, stance)
        shard_sys = f"{shard_system}\n\n本档推送标签：{push_label}\n本档章标题：## {chapter}"
        raw, model, err = _chat_with_retry(
            shard_sys,
            user,
            max_tokens=token_fn(tier_stocks, cap=group_max_tokens),
            timeout_sec=timeout,
        )
        rec.update({"model": model, "error": err or "", "duration_ms": int((time.monotonic() - t1) * 1000)})
        if not raw:
            rec["ok"] = False
            return stance, "", "", rec
        summary_part, body_part = _parse_shard_raw(raw, push_label=push_label, chapter=chapter)
        rec["ok"] = True
        return stance, summary_part, body_part, rec

    outputs: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_run_shard, item): item[0] for item in shards}
        shard_pct = {"holding": 55, "candidate": 62, "watch_right": 68, "theme_other": 74}
        for fut in as_completed(futs):
            stance, summary_part, body_part, rec = fut.result()
            shard_records.append(rec)
            if rec.get("ok"):
                outputs[stance] = (summary_part, body_part)
                if touch_progress:
                    touch_progress(
                        ctx,
                        f"分片完成：{rec.get('stance', stance)}（{rec.get('stock_count', 0)} 只）",
                        shard_pct.get(stance, 70),
                    )

    critical = list(critical_shard_keys or ("holding", "candidate"))
    failed_critical = [s for s in critical if s in {_r["stance"] for _r in shard_records if not _r.get("ok")}]
    if failed_critical and cfg.get("synthesize_fallback_monolithic", True):
        mono = run_monolithic_synthesize(
            ctx,
            build_user_prompt(ctx),
            system=monolithic_system,
            group_max_tokens=group_max_tokens,
            estimate_max_tokens=estimate_max_tokens,
        )
        mono["fallback_from"] = "sharded"
        mono["failed_shards"] = failed_critical
        mono["shards"] = shard_records
        return mono

    ordered: list[tuple[str, str, str]] = []
    for stance, _, chapter, push_label, _ in shards:
        if stance in outputs:
            sp, bp = outputs[stance]
            ordered.append((stance, sp, bp))
        else:
            sp, bp = _empty_shard(push_label, chapter)
            ordered.append((stance, sp, bp))

    merged = merge_sharded(global_summary, ordered)
    models = sorted({str(r.get("model") or "") for r in shard_records if r.get("model")} | {global_model})
    return {
        "mode": "sharded",
        "raw": merged,
        "model": "+".join(m for m in models if m) or global_model,
        "error": "",
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "shards": [{"phase": "global", "ok": True, "model": global_model}] + shard_records,
    }


def evaluate_raw(raw: str, stocks: list[dict]) -> dict[str, Any]:
    if not raw:
        return {
            "body": "",
            "summary": "",
            "missing_codes": [s.get("code") for s in stocks],
            "truncated_suspected": False,
            "critical_missing": True,
        }
    if not raw.lstrip().startswith("##"):
        raw = f"## 推送摘要\n（模型未按模板输出，见正文）\n\n{raw}"
    truncated = bool(raw) and raw.rstrip().endswith("…")
    body, summary = split_ai_report(raw)
    parsed = codes_in_body(body)
    expected = [str(s.get("code")) for s in stocks if s.get("code")]
    missing = [c for c in expected if c not in parsed]
    missing_set = set(missing)
    critical_missing = any(
        str(s.get("code")) in missing_set
        and _STANCE_FROM_HINT.get(str(s.get("stance_hint") or ""), "") in ("holding", "candidate")
        for s in stocks
    )
    return {
        "body": body,
        "summary": summary,
        "missing_codes": missing,
        "truncated_suspected": truncated,
        "critical_missing": critical_missing,
        "raw": raw,
    }


def needs_quality_retry(eval_result: dict[str, Any]) -> bool:
    if not eval_result.get("body"):
        return True
    if eval_result.get("critical_missing"):
        return True
    if eval_result.get("truncated_suspected") and eval_result.get("missing_codes"):
        return True
    return False


__all__ = [
    "run_monolithic_synthesize",
    "run_sharded_synthesize",
    "merge_sharded",
    "evaluate_raw",
    "needs_quality_retry",
]
