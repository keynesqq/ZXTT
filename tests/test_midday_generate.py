"""午间 generate 冒烟（mock LLM）。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from midday.generate import run_midday_ai

_DAY = date(2026, 6, 10)
_MOCK_RAW = """## 推送摘要
【环境】上午盘震荡
【仓位】中性
【操作】下午观望为主
【我的】600519 持有观察
【想买的】无
【观察】无
【其它】无
**分析时刻**：2026-06-10 12:50:00

## 我的·持仓深度
### 600519 贵州茅台
**午后开盘情景**：基准
**下午提示**：持有观望
"""


class TestMiddayGenerate(unittest.TestCase):
    @patch("ai.report_synthesis.chat")
    def test_ai_writes_midday_slot(self, mock_chat) -> None:
        mock_chat.return_value = (_MOCK_RAW, "mock-model", "")
        result = run_midday_ai(on_date=_DAY, force=True)
        self.assertIn(result.get("outcome"), ("ok", "warn"))
        ai_path = ROOT / "data" / "scheduled_ai" / f"midday_{_DAY.isoformat()}.json"
        self.assertTrue(ai_path.is_file())
        payload = json.loads(ai_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("slot"), "midday")


if __name__ == "__main__":
    unittest.main()
