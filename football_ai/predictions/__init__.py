"""
预测模块：胜负平、让胜负平、半全场、比分。
第一版为占位与免责声明，不输出真实预测、不构成任何投注建议。
"""
from football_ai.predictions.service import get_predictions, adjust_xg_for_injuries

__all__ = ["get_predictions", "adjust_xg_for_injuries"]
