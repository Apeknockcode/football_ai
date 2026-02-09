"""报告组装与模板测试。"""
from football_ai.report import build_report_inputs, render_report
from football_ai.report.template import fill_pre_match_template


def test_build_report_inputs_minimal():
    inputs = build_report_inputs(
        home_team="曼联",
        away_team="利物浦",
        round_=28,
    )
    assert "competition" in inputs and "injury" in inputs
    assert "tactics_summary" in inputs
    assert "第 28 轮" in inputs["competition"]["summary_zh"]


def test_render_pre_report():
    inputs = build_report_inputs("曼联", "利物浦", 28)
    text = render_report(inputs, report_type="pre", version="full")
    assert "赛事与背景" in text and "伤停" in text and "战术" in text


def test_render_pre_report_summary():
    inputs = build_report_inputs("曼联", "利物浦", 28)
    text = render_report(inputs, report_type="pre", version="summary")
    assert "曼联" in text or "利物浦" in text
