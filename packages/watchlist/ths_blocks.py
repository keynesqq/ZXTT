from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.config import load_config, normalize_code, ths_cfg

CODE_IN_TEXT = re.compile(r"\b(\d{6})\b")


@dataclass
class BlockPreview:
    block_id: str
    group_name: str
    codes: list[str] = field(default_factory=list)
    mtime: str = ""


@dataclass
class StockItem:
    code: str
    name: str
    group: str
    block_id: str = ""


class ThsBlocksError(Exception):
    pass


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def resolve_account_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or ths_cfg()
    raw = (cfg.get("account_dir") or "").strip()
    if not raw:
        raise ThsBlocksError("请在 config.yaml 配置 ths.account_dir")
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise ThsBlocksError(f"同花顺账号目录不存在: {path}")
    return path


def load_block_name_map(account_dir: Path) -> dict[str, str]:
    ini_path = account_dir / "stockblock.ini"
    if not ini_path.is_file():
        return {}
    names: dict[str, str] = {}
    section = ""
    for line in _read_text(ini_path).splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().upper()
            continue
        if section != "BLOCK_NAME_MAP_TABLE" or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip().upper(), val.strip()
        if key and val:
            names[key] = val
    return names


def _block_file_id_to_hex_key(block_id: str) -> str:
    if not str(block_id).isdigit():
        return str(block_id).upper()
    return format(int(block_id), "X")


def lookup_block_name(block_id: str, name_map: dict[str, str]) -> str | None:
    if not name_map:
        return None
    hex_key = _block_file_id_to_hex_key(block_id)
    return name_map.get(hex_key) or name_map.get(hex_key.upper())


def _extract_codes(context) -> list[str]:
    if context is None:
        return []
    if isinstance(context, list):
        parts = [str(x) for x in context]
    else:
        parts = re.split(r"[|,\s;]+", str(context))
    codes: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = part.strip()
        if len(part) == 6 and part.isdigit():
            c = normalize_code(part)
        else:
            m = CODE_IN_TEXT.search(part)
            c = normalize_code(m.group(1)) if m else ""
        if c and c not in seen:
            seen.add(c)
            codes.append(c)
    return codes


def _group_name_for_block(block_id: str, data: dict, name_map: dict[str, str]) -> str:
    mapped = lookup_block_name(block_id, name_map)
    if mapped:
        return mapped
    for key in ("name", "blockname", "blockName", "title", "block_title"):
        val = data.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return f"板块_{block_id}"


def parse_custom_block_file(path: Path, name_map: dict[str, str]) -> BlockPreview:
    block_id = path.name
    data = json.loads(_read_text(path))
    codes = _extract_codes(data.get("context"))
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return BlockPreview(
        block_id=block_id,
        group_name=_group_name_for_block(block_id, data, name_map),
        codes=codes,
        mtime=mtime,
    )


def _parse_analyze_blocks(ab: dict) -> tuple[set[str], set[str]]:
    by_name = {str(x).strip() for x in (ab.get("by_name") or []) if str(x).strip()}
    by_id = {str(x).strip() for x in (ab.get("by_id") or []) if str(x).strip()}
    return by_name, by_id


def _block_selected(preview: BlockPreview, by_name: set[str], by_id: set[str]) -> bool:
    if by_name and preview.group_name in by_name:
        return True
    if by_id and preview.block_id in by_id:
        return True
    if by_name and preview.block_id in by_name:
        return True
    return False


def load_selected_blocks() -> list[BlockPreview]:
    cfg = ths_cfg()
    account_dir = resolve_account_dir(cfg)
    by_name, by_id = _parse_analyze_blocks(cfg.get("analyze_blocks") or {})
    if not by_name and not by_id:
        raise ThsBlocksError("ths.analyze_blocks 未配置板块白名单")
    name_map = load_block_name_map(account_dir)
    block_dir = account_dir / "custom_block"
    selected: list[BlockPreview] = []
    if block_dir.is_dir():
        for path in sorted(block_dir.iterdir(), key=lambda p: p.name):
            if not path.is_file() or not path.name.isdigit():
                continue
            try:
                preview = parse_custom_block_file(path, name_map)
            except (json.JSONDecodeError, OSError, ValueError):
                continue
            if not preview.codes:
                continue
            if _block_selected(preview, by_name, by_id):
                selected.append(preview)
    if not selected:
        raise ThsBlocksError(f"白名单 [{', '.join(sorted(by_name | by_id))}] 未匹配到任何板块")
    return selected


def load_stocks_from_ths() -> list[StockItem]:
    blocks = load_selected_blocks()
    items: list[StockItem] = []
    for block in blocks:
        for code in block.codes:
            items.append(StockItem(code=code, name=code, group=block.group_name, block_id=block.block_id))
    if items:
        _fill_names(items)
    return items


def _fill_names(items: list[StockItem]) -> None:
    from quote.tencent import fetch_quotes
    from quote.ths import fetch_metrics_batch

    codes = list({s.code for s in items})
    metrics = fetch_metrics_batch(codes)
    unresolved = [c for c in codes if not str((metrics.get(c) or {}).get("name") or c).strip() or (metrics.get(c) or {}).get("name") == c]
    tx = fetch_quotes(unresolved) if unresolved else {}
    for item in items:
        m = metrics.get(item.code) or {}
        t = tx.get(item.code) or {}
        item.name = str(m.get("name") or t.get("name") or item.name or item.code).strip()
