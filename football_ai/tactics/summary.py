"""
战术小结：根据指标与阵型生成简短中文描述（供报告组装使用）。
"""
from typing import Any


def build_tactics_summary(
    metrics: dict[str, Any],
    formation: dict[str, str],
    home_team: str,
    away_team: str,
    report_type: str = "pre",
) -> str:
    """
    生成战术小结文本。
    :param metrics: compute_metrics 输出
    :param formation: infer_formation 输出，键为队名或 home/away
    :param home_team: 主队名（中文）
    :param away_team: 客队名（中文）
    :param report_type: pre | post
    :return: 一段中文战术描述
    """
    f_home = formation.get("home") or formation.get(home_team) or "4-3-3"
    f_away = formation.get("away") or formation.get(away_team) or "4-3-3"
    xg_h = metrics.get("xg", {}).get("home") or metrics.get("xg", {}).get(home_team) or 0.0
    xg_a = metrics.get("xg", {}).get("away") or metrics.get("xg", {}).get(away_team) or 0.0
    pos = metrics.get("possession_pct", {})
    p_h = pos.get("home") or pos.get(home_team) or 0.5
    p_a = pos.get("away") or pos.get(away_team) or 0.5
    shots = metrics.get("shots", {})
    s_h = shots.get("home") or shots.get(home_team) or 0
    s_a = shots.get("away") or shots.get(away_team) or 0

    if report_type == "pre":
        return (
            f"主队{home_team}近期多以 {f_home} 出战，客队{away_team}常用 {f_away}。"
            "结合主客与伤停，具体战术执行以当场为准。"
        )
    # post：至少一项来自事件（控球率、xG、射门）
    parts = [
        f"实际阵型主队 {f_home}、客队 {f_away}。",
        f"控球率 主 {p_h:.0%} – 客 {p_a:.0%}；",
        f"xG 主 {xg_h:.2f} – 客 {xg_a:.2f}；",
        f"射门 主 {s_h} – 客 {s_a}。",
    ]
    return " ".join(parts)
