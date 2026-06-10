"""第 5 步 5C · 微信推送（PushPlus，迁自 ZXReport wechat_push）。"""
from __future__ import annotations

import os
from typing import Any

import httpx

from core.config import load_config
from report.push_format import format_wechat_push_html

PUSHPLUS_URL = "https://www.pushplus.plus/send"


def _wechat_cfg() -> dict:
    return load_config().get("wechat") or {}


def _push_enabled() -> bool:
    cfg = _wechat_cfg()
    token = os.getenv("WECHAT_PUSH_TOKEN", "").strip()
    if cfg.get("enabled"):
        return True
    return bool(token)


def format_push_text(summary: str, *, trade_date: str, title_prefix: str = "ZXTT 盘后") -> str:
    body = (summary or "").strip()
    title = f"{title_prefix} · {trade_date}"
    return f"{title}\n\n{body}" if body else title


def _push_once(*, token: str, title: str, content: str) -> str:
    payload = {
        "token": token,
        "title": title[:100],
        "content": content[:8000],
        "template": "html",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(PUSHPLUS_URL, json=payload)
        r.raise_for_status()
        data = r.json()
    if data.get("code") == 200:
        return ""
    return str(data.get("msg") or data)


def _push_pushplus(summary: str, *, trade_date: str, title_prefix: str) -> dict[str, Any]:
    token = os.getenv("WECHAT_PUSH_TOKEN", "").strip()
    if not token:
        return {"outcome": "skip", "reason": "token_missing"}
    body = (summary or "").strip()
    if not body:
        return {"outcome": "skip", "reason": "summary_empty"}
    title = f"{title_prefix} · {trade_date}"
    content = format_wechat_push_html(body)
    try:
        err = _push_once(token=token, title=title, content=content)
        if not err:
            return {"outcome": "ok", "channel": "pushplus"}
    except Exception as e:
        err = str(e)
    try:
        err2 = _push_once(token=token, title=title, content=content)
        if not err2:
            return {"outcome": "ok", "channel": "pushplus", "retry": True}
        return {"outcome": "fail", "message": err2, "channel": "pushplus"}
    except Exception as e:
        return {"outcome": "fail", "message": str(e), "channel": "pushplus"}


def _push_webhook(summary: str, *, trade_date: str, url: str, title_prefix: str) -> dict[str, Any]:
    text = format_push_text(summary, trade_date=trade_date, title_prefix=title_prefix)
    payload = {"msgtype": "text", "text": {"content": text[:4000]}}
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        if data.get("errcode", 0) != 0:
            return {"outcome": "fail", "message": data.get("errmsg", str(data)), "channel": "webhook"}
        return {"outcome": "ok", "channel": "webhook"}
    except Exception as e:
        return {"outcome": "fail", "message": str(e), "channel": "webhook"}


def push_wechat_summary(summary: str, *, trade_date: str) -> dict[str, Any]:
    if not _push_enabled():
        return {"outcome": "skip", "reason": "wechat_disabled"}
    cfg = _wechat_cfg()
    title_prefix = str(cfg.get("title_prefix") or "ZXTT 盘后")
    token = os.getenv("WECHAT_PUSH_TOKEN", "").strip()
    if token:
        return _push_pushplus(summary, trade_date=trade_date, title_prefix=title_prefix)
    url = (cfg.get("webhook_url") or os.getenv("WECHAT_WEBHOOK_URL") or "").strip()
    if not url:
        return {"outcome": "skip", "reason": "webhook_missing"}
    return _push_webhook(summary, trade_date=trade_date, url=url, title_prefix=title_prefix)


__all__ = ["push_wechat_summary", "format_push_text"]
