"""
政治 · 赛事/国家：德比、轮次重要性、赛事阶段、比赛时间。规则表 + 元数据。
"""
from pathlib import Path
from typing import Any


def _format_datetime(date_str: str | None, time_str: str | None) -> str:
    """将 YYYY-MM-DD 与 HH:MM 格式化为中文：2025年3月15日 20:00"""
    if not date_str:
        return ""
    parts = []
    try:
        y, m, d = date_str.strip().split("-")[:3]
        parts.append(f"{y}年{int(m)}月{int(d)}日")
    except (ValueError, IndexError):
        return date_str
    if time_str and time_str.strip():
        t = time_str.strip()
        if len(t) >= 5:
            parts.append(t[:5])
        else:
            parts.append(t)
    return " ".join(parts)


def get_competition_context(
    home_team: str,
    away_team: str,
    round_: int,
    derby_rules_path: str | Path | None = None,
    match_date: str | None = None,
    match_time: str | None = None,
    league_id: str | None = None,
) -> dict[str, Any]:
    """
    返回本场的赛事背景（德比标签、轮次、比赛时间、叙事定位）。
    :param match_date: 比赛日期，如 "2025-03-15"
    :param match_time: 开球时间，如 "20:00"（可选）
    :param league_id: 联赛 id（见 config/leagues.yaml），用于赛事名称展示
    :return: {"derby_label_zh": ..., "round": 28, "match_datetime_zh": "...", "summary_zh": "..."}
    """
    derby_label = None
    if derby_rules_path and Path(derby_rules_path).exists():
        import csv
        with open(derby_rules_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                h, a = row.get("home_team", "").strip(), row.get("away_team", "").strip()
                if (h == home_team and a == away_team) or (h == away_team and a == home_team):
                    derby_label = row.get("label_zh", "").strip() or "德比"
                    break

    match_datetime_zh = _format_datetime(match_date, match_time)
    comp_name = "英超"
    stage_suffix = f"第 {round_} 轮"
    if league_id:
        try:
            from football_ai.leagues import get_competition, get_competition_type
            C = get_competition(league_id)
            if C:
                comp_name = C.get("name_zh") or comp_name
                if C.get("type") == "cup":
                    labels = C.get("stage_labels") or {}
                    stage_suffix = labels.get(round_, f"第 {round_} 轮")
        except Exception:
            pass
    summary_zh = f"本场为{comp_name}{stage_suffix}。"
    if match_datetime_zh:
        summary_zh += f"比赛时间：{match_datetime_zh}。"
    if derby_label:
        summary_zh += f"传统「{derby_label}」（{home_team} vs {away_team}）。"

    return {
        "derby_label_zh": derby_label,
        "round": round_,
        "match_date": match_date,
        "match_time": match_time,
        "match_datetime_zh": match_datetime_zh,
        "summary_zh": summary_zh,
    }
