"""22 点晚间报告管线（第 ②–⑤ 步编排）。"""
from __future__ import annotations

from evening.collect import run_collect_evening
from evening.generate import run_evening_ai
from evening.pipeline import run_evening_generate
from evening.preprocess import run_preprocess_evening
from evening.render import run_evening_render
from evening.run_full import run_evening_pipeline

__all__ = [
    "run_evening_pipeline",
    "run_collect_evening",
    "run_preprocess_evening",
    "run_evening_generate",
    "run_evening_ai",
    "run_evening_render",
]
