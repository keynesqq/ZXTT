"""报告数据归档与复现：按层记录原始数据，支持任意时刻重跑/重渲染。"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

from core.config import load_config_cached
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR, ROOT
from core.trading_calendar import next_trading_day, previous_trading_day

_ARCHIVE_DIR = DATA_DIR / "report_archive"
_SLOT_HTML = {
    "evening": "daily_evening.html",
    "midday": "daily_midday.html",
    "morning": "daily_morning.html",
}
ReproducePhase = Literal["verify", "snapshot", "render", "preprocess", "ai", "full"]
LayerId = Literal["L0_raw", "L1_process", "L2_ai", "L3_render"]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _file_entry(path: Path, *, role: str, layer: LayerId, required: bool = True) -> dict[str, Any]:
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    digest = ""
    if exists and size <= 8_000_000:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except OSError:
            digest = ""
    return {
        "role": role,
        "layer": layer,
        "path": _rel(path),
        "required": required,
        "exists": exists,
        "size": size,
        "sha256_16": digest,
    }


def _glob_entries(
    pattern: str,
    *,
    role_prefix: str,
    layer: LayerId,
    required: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(ROOT.glob(pattern)):
        if path.is_file():
            out.append(_file_entry(path, role=f"{role_prefix}:{path.name}", layer=layer, required=required))
    return out


def _paths_from_context(ctx_path: Path, layer: LayerId = "L0_raw") -> list[dict[str, Any]]:
    ctx = _load_json(ctx_path)
    if not ctx:
        return []
    meta = ctx.get("meta") or {}
    paths = meta.get("paths") or {}
    optional_roles = {"intraday_digest_full", "intraday_digest_morning", "collect_manifest"}
    if not meta.get("intraday_digest_ok"):
        optional_roles.add("intraday_digest_full")
    entries: list[dict[str, Any]] = []
    for role, rel in paths.items():
        if not rel:
            continue
        required = str(role) not in optional_roles
        entries.append(
            _file_entry(ROOT / str(rel), role=str(role), layer=layer, required=required)
        )
    return entries


def _evening_files(day: date) -> list[dict[str, Any]]:
    iso = day.isoformat()
    ctx_path = DATA_DIR / "evening_context" / f"{iso}.json"
    entries: list[dict[str, Any]] = []
    entries.extend(_paths_from_context(ctx_path))
    entries.append(_file_entry(DATA_DIR / "evening_baseline" / f"{iso}.json", role="evening_baseline", layer="L1_process"))
    entries.append(_file_entry(ctx_path, role="evening_context", layer="L1_process"))
    entries.extend(
        _glob_entries(f"data/ai_digest/{iso}/stock_*.json", role_prefix="ai_digest_stock", layer="L1_process")
    )
    entries.extend(
        _glob_entries(f"data/ai_digest/{iso}/cls_*.json", role_prefix="ai_digest_cls", layer="L1_process", required=False)
    )
    entries.append(
        _file_entry(DATA_DIR / "ai_digest" / iso / "manifest.json", role="ai_digest_manifest", layer="L1_process", required=False)
    )
    entries.append(
        _file_entry(DATA_DIR / "collect_manifest" / f"{iso}.json", role="collect_manifest", layer="L0_raw", required=False)
    )
    nxt = next_trading_day(day)
    if nxt:
        entries.append(
            _file_entry(
                DATA_DIR / "expectations" / f"{nxt.isoformat()}.json",
                role="expectations_next",
                layer="L2_ai",
                required=False,
            )
        )
    entries.append(
        _file_entry(DATA_DIR / "scheduled_ai" / f"evening_{iso}.json", role="scheduled_ai", layer="L2_ai")
    )
    entries.append(
        _file_entry(ROOT / "reports" / iso / _SLOT_HTML["evening"], role="report_html", layer="L3_render", required=False)
    )
    return entries


def _midday_files(day: date) -> list[dict[str, Any]]:
    iso = day.isoformat()
    ctx_path = DATA_DIR / "midday_context" / f"{iso}.json"
    entries: list[dict[str, Any]] = []
    entries.extend(_paths_from_context(ctx_path))
    entries.append(_file_entry(DATA_DIR / "midday_baseline" / f"{iso}.json", role="midday_baseline", layer="L1_process"))
    entries.append(_file_entry(ctx_path, role="midday_context", layer="L1_process"))
    entries.extend(
        _glob_entries(f"data/ai_digest/{iso}/stock_*.json", role_prefix="ai_digest_stock", layer="L1_process")
    )
    entries.append(
        _file_entry(DATA_DIR / "ai_digest" / iso / "midday_manifest.json", role="ai_digest_manifest", layer="L1_process", required=False)
    )
    entries.append(
        _file_entry(DATA_DIR / "collect_manifest" / f"{iso}_midday.json", role="collect_manifest", layer="L0_raw", required=False)
    )
    entries.append(
        _file_entry(DATA_DIR / f"intraday_digest_{iso}_morning.json", role="intraday_digest_morning", layer="L0_raw", required=False)
    )
    entries.append(
        _file_entry(DATA_DIR / "expectations" / f"{iso}_midday.json", role="expectations_midday", layer="L2_ai", required=False)
    )
    entries.append(
        _file_entry(DATA_DIR / "scheduled_ai" / f"midday_{iso}.json", role="scheduled_ai", layer="L2_ai")
    )
    entries.append(
        _file_entry(ROOT / "reports" / iso / _SLOT_HTML["midday"], role="report_html", layer="L3_render", required=False)
    )
    return entries


def _morning_files(day: date) -> list[dict[str, Any]]:
    iso = day.isoformat()
    ctx_path = DATA_DIR / "morning_context" / f"{iso}.json"
    ctx = _load_json(ctx_path)
    entries: list[dict[str, Any]] = []
    if ctx:
        entries.extend(_paths_from_context(ctx_path))
    pre = _load_json(DATA_DIR / "morning_pre" / f"{iso}.json") or {}
    for role, rel in (pre.get("source_paths") or {}).items():
        if rel:
            entries.append(_file_entry(ROOT / str(rel), role=f"pre_{role}", layer="L0_raw", required=True))
    prev_td = previous_trading_day(day)
    entries.extend(
        [
            _file_entry(DATA_DIR / f"auction_trend_{iso}.json", role="auction_trend", layer="L0_raw"),
            _file_entry(DATA_DIR / f"auction_series_{iso}.json", role="auction_series", layer="L0_raw", required=False),
            _file_entry(DATA_DIR / "morning_pre" / f"{iso}.json", role="morning_pre", layer="L0_raw"),
            _file_entry(DATA_DIR / f"quote_query_{iso}.json", role="quote", layer="L0_raw", required=False),
            _file_entry(DATA_DIR / f"announcement_query_{iso}.json", role="announcement", layer="L0_raw", required=False),
            _file_entry(DATA_DIR / f"news_query_{iso}.json", role="news", layer="L0_raw", required=False),
            _file_entry(DATA_DIR / "expectations" / f"{iso}.json", role="expectations_today", layer="L0_raw", required=False),
            _file_entry(ctx_path, role="morning_context", layer="L1_process"),
            _file_entry(DATA_DIR / "morning_checks" / f"{iso}.json", role="morning_checks", layer="L1_process"),
            _file_entry(DATA_DIR / "scheduled_ai" / f"morning_{iso}.json", role="scheduled_ai", layer="L2_ai"),
            _file_entry(
                ROOT / "reports" / iso / _SLOT_HTML["morning"],
                role="report_html",
                layer="L3_render",
                required=False,
            ),
        ]
    )
    if prev_td:
        entries.append(
            _file_entry(
                DATA_DIR / "scheduled_ai" / f"evening_{prev_td.isoformat()}.json",
                role="evening_ai_prev",
                layer="L0_raw",
                required=False,
            )
        )
        entries.append(
            _file_entry(
                DATA_DIR / "evening_baseline" / f"{prev_td.isoformat()}.json",
                role="evening_baseline_prev",
                layer="L0_raw",
                required=False,
            )
        )
    return entries


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in entries:
        path = str(item.get("path") or "")
        if path in seen:
            continue
        seen.add(path)
        out.append(item)
    return out


def _config_snapshot() -> dict[str, Any]:
    cfg = load_config_cached()
    evening = cfg.get("evening") or {}
    midday = cfg.get("midday") or {}
    morning = cfg.get("morning") or {}
    return {
        "llm_model": os.environ.get("LLM_MODEL") or cfg.get("llm_model") or "",
        "evening_synthesize_mode": evening.get("synthesize_mode") or "",
        "midday_synthesize_mode": midday.get("synthesize_mode") or "",
        "morning_synthesize_mode": morning.get("synthesize_mode") or "",
    }


def _layer_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    layers: dict[str, dict[str, Any]] = {}
    for layer in ("L0_raw", "L1_process", "L2_ai", "L3_render"):
        layer_items = [e for e in entries if e.get("layer") == layer]
        req = [e for e in layer_items if e.get("required")]
        missing = [e for e in req if not e.get("exists")]
        layers[layer] = {
            "total": len(layer_items),
            "required": len(req),
            "missing_required": len(missing),
            "ok": len(missing) == 0,
        }
    return layers


def _reproduce_hints(slot: str) -> dict[str, str]:
    iso = "{date}"
    return {
        "render": f"python run.py reproduce --slot {slot} --date {iso} --phase render",
        "preprocess": f"python run.py preprocess --slot {slot} --date {iso}",
        "ai": f"python run.py generate --slot {slot} --phase ai --date {iso}",
        "full": f"python run.py {slot} --date {iso}",
        "verify": f"python run.py reproduce --slot {slot} --date {iso} --phase verify",
    }


def build_report_archive(slot: str, day: date) -> dict[str, Any]:
    if slot == "evening":
        entries = _evening_files(day)
    elif slot == "midday":
        entries = _midday_files(day)
    elif slot == "morning":
        entries = _morning_files(day)
    else:
        raise ValueError(f"unknown slot: {slot}")

    entries = _dedupe_entries(entries)
    layers = _layer_summary(entries)
    missing = [e for e in entries if e.get("required") and not e.get("exists")]
    render_ok = layers.get("L3_render", {}).get("ok", False) or any(
        e.get("role") == "report_html" and e.get("exists") for e in entries
    )
    reproduce_ready = layers.get("L1_process", {}).get("ok") and layers.get("L2_ai", {}).get("ok")

    return {
        "schema_version": 1,
        "slot": slot,
        "trade_date": day.isoformat(),
        "archived_at": now_iso(),
        "layers": layers,
        "files": entries,
        "missing_required": [{"role": e["role"], "path": e["path"]} for e in missing],
        "reproduce_ready": reproduce_ready,
        "render_ready": reproduce_ready and bool(
            next((e for e in entries if e.get("role") == "scheduled_ai" and e.get("exists")), None)
        ),
        "report_html_exists": render_ok,
        "config_snapshot": _config_snapshot(),
        "reproduce": _reproduce_hints(slot),
    }


def archive_path(day: date, slot: str) -> Path:
    return _ARCHIVE_DIR / f"{day.isoformat()}_{slot}.json"


def save_report_archive(slot: str, day: date, *, report_path: str | None = None) -> Path:
    payload = build_report_archive(slot, day)
    if report_path:
        payload["report_path"] = report_path.replace("\\", "/")
    path = archive_path(day, slot)
    _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def load_report_archive(day: date, slot: str) -> dict[str, Any] | None:
    return _load_json(archive_path(day, slot))


def verify_report_archive(
    slot: str,
    day: date,
    *,
    min_layer: LayerId = "L2_ai",
) -> dict[str, Any]:
    archive = build_report_archive(slot, day)
    order = ("L0_raw", "L1_process", "L2_ai", "L3_render")
    min_idx = order.index(min_layer)
    needed = set(order[: min_idx + 1])
    missing: list[dict[str, str]] = []
    for item in archive.get("files") or []:
        if item.get("layer") not in needed or not item.get("required"):
            continue
        if not item.get("exists"):
            missing.append({"role": str(item.get("role")), "path": str(item.get("path"))})
    ok = not missing
    return {
        "outcome": "ok" if ok else "fail",
        "slot": slot,
        "trade_date": day.isoformat(),
        "min_layer": min_layer,
        "missing": missing,
        "archive": archive,
    }


def reproduce_report(
    slot: str,
    day: date,
    *,
    phase: ReproducePhase = "verify",
    force: bool = False,
) -> dict[str, Any]:
    if phase == "verify":
        result = verify_report_archive(slot, day, min_layer="L2_ai")
        save_report_archive(slot, day)
        return result

    if phase == "snapshot":
        path = save_report_archive(slot, day)
        archive = load_report_archive(day, slot) or {}
        return {"outcome": "ok", "path": str(path), "missing_required": archive.get("missing_required") or []}

    if phase == "render":
        check = verify_report_archive(slot, day, min_layer="L2_ai")
        if check.get("outcome") != "ok":
            return {"outcome": "fail", "reason": "missing_inputs", **check}
        if slot == "evening":
            from evening.render import run_evening_render

            return run_evening_render(on_date=day)
        if slot == "midday":
            from midday.render import run_midday_render

            return run_midday_render(on_date=day)
        from morning.render import run_morning_render

        return run_morning_render(on_date=day)

    if phase == "preprocess":
        if slot == "morning":
            return {"outcome": "fail", "reason": "morning_has_no_preprocess", "hint": "python run.py morning --date ..."}
        check = verify_report_archive(slot, day, min_layer="L0_raw")
        if check.get("outcome") != "ok":
            return {"outcome": "fail", "reason": "missing_raw", **check}
        if slot == "evening":
            from evening.preprocess import run_preprocess_evening

            return run_preprocess_evening(on_date=day, force=force)
        from midday.preprocess import run_preprocess_midday

        return run_preprocess_midday(on_date=day, force=force)

    if phase == "ai":
        check = verify_report_archive(slot, day, min_layer="L1_process")
        if check.get("outcome") != "ok":
            return {"outcome": "fail", "reason": "missing_context", **check}
        if slot == "morning":
            from morning.generate import run_morning_ai

            return run_morning_ai(on_date=day)
        if slot == "evening":
            from evening.pipeline import run_evening_generate

            return run_evening_generate(on_date=day, phase="ai", force=force)
        from midday.pipeline import run_midday_generate

        return run_midday_generate(on_date=day, phase="ai", force=force)

    if phase == "full":
        check = verify_report_archive(slot, day, min_layer="L0_raw")
        skip_collect = check.get("outcome") == "ok"
        if slot == "evening":
            if skip_collect:
                from evening.preprocess import run_preprocess_evening
                from evening.pipeline import run_evening_generate

                prep = run_preprocess_evening(on_date=day, force=force)
                if prep.get("outcome") != "ok":
                    return {"outcome": "fail", "step": "preprocess", "result": prep}
                gen = run_evening_generate(on_date=day, phase="all", force=force)
                save_report_archive(slot, day)
                return {"outcome": gen.get("outcome", "ok"), "skip_collect": True, "result": gen}
            from evening.run_full import run_evening_pipeline

            result = run_evening_pipeline(on_date=day, force=force, open_browser=False)
            if result.get("outcome") == "ok":
                save_report_archive(slot, day, report_path=result.get("report_path"))
            return result
        if slot == "midday":
            if skip_collect:
                from midday.preprocess import run_preprocess_midday
                from midday.pipeline import run_midday_generate

                prep = run_preprocess_midday(on_date=day, force=force)
                if prep.get("outcome") != "ok":
                    return {"outcome": "fail", "step": "preprocess", "result": prep}
                gen = run_midday_generate(on_date=day, phase="all", force=force)
                save_report_archive(slot, day)
                return {"outcome": gen.get("outcome", "ok"), "skip_collect": True, "result": gen}
            from midday.run_full import run_midday_pipeline

            result = run_midday_pipeline(on_date=day, force=force, open_browser=False)
            if result.get("outcome") == "ok":
                save_report_archive(slot, day, report_path=result.get("report_path"))
            return result
        from morning.run_full import run_morning_pipeline

        result = run_morning_pipeline(on_date=day, force=force, open_browser=False)
        if result.get("outcome") == "ok":
            save_report_archive(slot, day, report_path=result.get("report_path"))
        return result

    return {"outcome": "fail", "reason": "unknown_phase", "phase": phase}


__all__ = [
    "build_report_archive",
    "save_report_archive",
    "load_report_archive",
    "verify_report_archive",
    "reproduce_report",
    "archive_path",
]
