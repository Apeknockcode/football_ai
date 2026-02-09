"""
机器学习特征与训练：基于历史场次、近期状态、H2H、xPts、Elo 等构建特征矩阵，可选训练分类/回归模型。
"""
from football_ai.ml.features import build_feature_row, build_dataset, FEATURE_NAMES

__all__ = ["build_feature_row", "build_dataset", "FEATURE_NAMES"]
