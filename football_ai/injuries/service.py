"""
伤停服务：将原始伤停列表转为报告用结构化文本与要点。
"""
from typing import Any

from football_ai.data.injuries import load_injuries


def get_injury_report(
    path: str | None = None,
    api_url: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
) -> dict[str, Any]:
    """
    获取与主客队相关的伤停报告。
    :return: {
        "home": [{"player": "A", "reason": "伤缺", "source": "..."}, ...],
        "away": [...],
        "summary_zh": "主队 A、B 伤缺；客队 C 停赛。",
    }
    """
    raw = load_injuries(path=path, api_url=api_url)
    home_list = []
    away_list = []
    for r in raw:
        team = r.get("team") or r.get("team_name")
        if not team:
            continue
        item = {
            "player": r.get("player") or r.get("player_name", ""),
            "reason": r.get("reason") or r.get("type", "伤缺"),
            "source": r.get("source", ""),
        }
        if home_team and team.strip() == home_team.strip():
            home_list.append(item)
        elif away_team and team.strip() == away_team.strip():
            away_list.append(item)

    def _line(team_label: str, lst: list) -> str:
        if not lst:
            return ""
        parts = [f"{x['player']}（{x['reason']}）" for x in lst]
        return f"{team_label} {', '.join(parts)}；"

    summary_zh = _line("主队", home_list) + _line("客队", away_list)
    if summary_zh.endswith("；"):
        summary_zh = summary_zh[:-1] + "。"

    return {
        "home": home_list,
        "away": away_list,
        "summary_zh": summary_zh or "暂无伤停信息。",
    }
