"""
报告模块：整合战术+伤停+政治，生成赛前/赛后中文报告。
完整版（分析师）+ 摘要版（球迷）；模板 + 可选 LLM 润色。
"""
from football_ai.report.assembler import build_report_inputs, render_report
from football_ai.report.template import fill_pre_match_template, fill_post_match_template

__all__ = ["build_report_inputs", "render_report", "fill_pre_match_template", "fill_post_match_template"]
