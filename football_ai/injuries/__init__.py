"""
伤停模块：缺阵、复出、累计黄牌，对阵容/战术的影响描述。
数据由 data.injuries 接入；预留结构化 API。
"""
from football_ai.injuries.service import get_injury_report

__all__ = ["get_injury_report"]
