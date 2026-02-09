"""
政治 · 纪律/裁判：禁赛、主裁风格（出牌/点球倾向）。半结构化数据。
"""
from typing import Any


def get_discipline_referee(
    referee_name: str | None = None,
    referee_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    返回主裁信息与纪律相关描述。
    :param referee_name: 主裁姓名
    :param referee_stats: 如 {"yellow_per_match": 4.2, "penalty_ratio": "above_average"}
    :return: {"referee": "...", "summary_zh": "主裁 XXX，本赛季场均 X.X 张黄牌。"}
    """
    if not referee_name and not referee_stats:
        return {"referee": None, "summary_zh": ""}

    name = referee_name or "未知"
    summary = f"主裁 {name}"
    if referee_stats:
        ypm = referee_stats.get("yellow_per_match")
        if ypm is not None:
            summary += f"，本赛季场均 {float(ypm):.1f} 张黄牌"
        pen = referee_stats.get("penalty_ratio")
        if pen:
            summary += "，点球判罚略高于联赛平均" if pen == "above_average" else "，点球判罚接近联赛平均"
        summary += "。"
    else:
        summary += "。"

    return {"referee": name, "referee_stats": referee_stats, "summary_zh": summary}
