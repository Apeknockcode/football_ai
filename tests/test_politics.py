"""政治模块基础测试。"""
from pathlib import Path

import pytest

from football_ai.politics import (
    get_competition_context,
    get_discipline_referee,
    get_narrative,
    get_club_manager_context,
)


def test_competition_context_no_derby():
    out = get_competition_context("阿森纳", "切尔西", 28, derby_rules_path=None)
    assert "第 28 轮" in out["summary_zh"]
    assert out.get("derby_label_zh") is None


def test_competition_context_derby():
    rules = Path(__file__).resolve().parent.parent / "config" / "derby_rules.csv"
    if not rules.exists():
        pytest.skip("config/derby_rules.csv not found")
    out = get_competition_context("曼联", "利物浦", 28, derby_rules_path=rules)
    assert "双红会" in out["summary_zh"]


def test_discipline_referee():
    out = get_discipline_referee(referee_name="张三", referee_stats={"yellow_per_match": 4.2})
    assert "张三" in out["summary_zh"] and "4.2" in out["summary_zh"]


def test_narrative_default():
    out = get_narrative("曼联", "利物浦", 28)
    assert "媒体" in out["summary_zh"]
