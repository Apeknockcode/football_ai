"""战术模块基础测试。"""
import pandas as pd
import pytest

from football_ai.tactics import compute_metrics, infer_formation, build_tactics_summary


def test_compute_metrics_empty():
    out = compute_metrics(pd.DataFrame())
    assert "possession_pct" in out and "xg" in out
    assert out["xg"]["home"] == 0.0 and out["xg"]["away"] == 0.0


def test_infer_formation_from_lineup():
    out = infer_formation(lineup={"home": "4-2-3-1", "away": "4-3-3"})
    assert out["home"] == "4-2-3-1" and out["away"] == "4-3-3"


def test_infer_formation_default():
    out = infer_formation()
    assert out["home"] == "4-3-3" and out["away"] == "4-3-3"


def test_build_tactics_summary_pre():
    metrics = {"xg": {"home": 0.0, "away": 0.0}, "possession_pct": {"home": 0.5, "away": 0.5}}
    formation = {"home": "4-2-3-1", "away": "4-3-3"}
    s = build_tactics_summary(metrics, formation, "曼联", "利物浦", report_type="pre")
    assert "曼联" in s and "利物浦" in s and "4-2-3-1" in s
