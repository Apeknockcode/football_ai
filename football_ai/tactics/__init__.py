"""
战术模块：指标、阵型、小结。
基于事件/阵型数据，输出指标与文字小结（阵型、压迫、转换、控球区域、强弱侧等）。
"""
from football_ai.tactics.metrics import compute_metrics
from football_ai.tactics.formation import infer_formation
from football_ai.tactics.summary import build_tactics_summary

__all__ = ["compute_metrics", "infer_formation", "build_tactics_summary"]
