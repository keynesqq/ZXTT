"""分片合成合并与质量重试判定单测。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.synthesize import evaluate_raw, merge_sharded, needs_quality_retry


class MergeShardedTests(unittest.TestCase):
    def test_merge_order(self) -> None:
        global_summary = "【环境】中\n【仓位】观望\n【操作】核对"
        shards = [
            ("holding", "【我的】· 600519 茅台 | 守 | 基准", "## 我的·持仓深度\n### 600519 贵州茅台"),
            ("candidate", "【想买的】· 000021 深科技 | 等 | 基准", "## 想买的·候选跟踪\n### 000021 深科技"),
        ]
        raw = merge_sharded(global_summary, shards)
        self.assertIn("## 推送摘要", raw)
        self.assertIn("【环境】", raw)
        self.assertIn("【我的】", raw)
        self.assertIn("## 我的·持仓深度", raw)
        self.assertIn("600519", raw)
        self.assertIn("000021", raw)


class EvaluateRawTests(unittest.TestCase):
    def test_missing_critical(self) -> None:
        raw = """## 推送摘要
【环境】中

## 我的 · 持仓深度
### 600519 贵州茅台
预期
"""
        stocks = [
            {"code": "600519", "stance_hint": "持仓", "groups": ["我的"]},
            {"code": "000021", "stance_hint": "候选", "groups": ["想买的"]},
        ]
        ev = evaluate_raw(raw, stocks)
        self.assertIn("000021", ev["missing_codes"])
        self.assertTrue(ev["critical_missing"])
        self.assertTrue(needs_quality_retry(ev))

    def test_shallow_stock_triggers_retry(self) -> None:
        raw = """## 推送摘要
【环境】中

## 我的
### 600519 贵州茅台
今日微涨，观望。

## 想买的
### 000021 深科技
**无规则事件**：略。
- **情景推演**：若涨则持有
- **对应策略**：等
- **开盘参考**：基准
"""
        stocks = [
            {"code": "600519", "groups": ["我的"]},
            {"code": "000021", "groups": ["想买的"]},
        ]
        ev = evaluate_raw(raw, stocks)
        self.assertIn("600519", ev["shallow_codes"])
        self.assertNotIn("000021", ev["shallow_codes"])
        self.assertTrue(needs_quality_retry(ev))


if __name__ == "__main__":
    unittest.main()
