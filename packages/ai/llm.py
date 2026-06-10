"""同步 LLM chat（httpx）。"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from core.config import evening_cfg, load_config


def chat(
    system: str,
    user: str,
    *,
    max_tokens: int | None = None,
    timeout_sec: float = 120.0,
) -> tuple[str, str, str]:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    tokens = max_tokens or int((load_config().get("llm") or {}).get("max_tokens") or 2500)
    if not api_key:
        return "", model, "未配置 LLM_API_KEY"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(f"{base}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip(), model, ""
    except Exception as e:
        return "", model, str(e)


def parse_json_blob(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"summary": text[:500]}


def digest_timeout_sec() -> float:
    return float(evening_cfg().get("request_timeout_sec") or 120)


__all__ = ["chat", "parse_json_blob", "digest_timeout_sec"]
