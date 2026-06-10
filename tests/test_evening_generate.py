"""第 4 步 AI 冒烟（mock LLM）。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.generate import run_evening_ai

_DAY = date(2026, 6, 10)

_MOCK_RAW = """## 推送摘要
【环境】池子参考中
【仓位】观望
【我的】· 600519 茅台 | 守 | 基准
【想买的】· 000021 深科技 | 等 | 基准
【观察】· 301293 三博 | 观察 | 基准
【其它】无
【操作】核对开盘
**分析时刻**：2026-06-10 22:00

## 情绪与胜率（L1）
数据

## 我的 · 持仓深度
### 600519 贵州茅台
**短线预期**：基准
**消息 net**：中性

## 想买的 · 候选跟踪
### 000021 深科技
**短线预期**：偏低开

## 观察 · 跌幅达预期
### 301293 三博脑科
**短线预期**：不确定

## 其它 · 风向跟踪
### 600021 上海电力
跟踪
"""


class TestEveningGenerate(unittest.TestCase):
    @patch("evening.synthesize.chat")
    def test_ai_mock(self, mock_chat) -> None:
        mock_chat.return_value = (_MOCK_RAW, "mock-model", "")
        result = run_evening_ai(on_date=_DAY, force=True)
        self.assertIn(result.get("outcome"), ("ok", "warn"))
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data.get("body"))
        self.assertTrue(data.get("summary"))


if __name__ == "__main__":
    unittest.main()
