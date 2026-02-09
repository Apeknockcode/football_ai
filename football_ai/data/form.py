"""
近期状态：基于历史场次计算球队近 N 场胜负、进球/失球、积分等。
数据来源：load_historical_matches 的返回；供报告与预测上下文使用。
"""
from typing import Any

from football_ai.data.historical import sort_key_match


def get_team_form(
    team: str,
    matches: list[dict[str, Any]],
    season: int,
    round_before: int,
    n_matches: int = 5,
) -> dict[str, Any]:
    """
    计算某队在指定赛季、指定轮次之前的「近 N 场」状态。
    :param team: 球队名（与 historical 中 home_team/away_team 一致）
    :param matches: 历史场次列表，每项含 season, round, home_team, away_team, goals_home, goals_away 等
    :param season: 当前赛季年
    :param round_before: 当前轮次（不包含本场，即「本轮开打前」的近 N 场）
    :param n_matches: 取最近几场，默认 5
    :return: played, wins, draws, losses, goals_for, goals_against, points, xg_for, xg_against, summary_zh
    """
    # 按比赛时间升序（优先 match_date，否则 season/round），只取该轮前的场次
    sorted_matches = sorted(matches, key=sort_key_match)
    team_matches: list[dict[str, Any]] = []
    for m in sorted_matches:
        s, r = int(m.get("season", 0)), int(m.get("round", 0))
        # 无 match_date 时用 (season, round) 判断「本轮前」
        if (s, r) >= (season, round_before):
            break
        if m.get("home_team", "").strip() == team.strip():
            team_matches.append({**m, "_is_home": True})
        elif m.get("away_team", "").strip() == team.strip():
            team_matches.append({**m, "_is_home": False})

    recent = team_matches[-n_matches:] if len(team_matches) >= n_matches else team_matches
    played = len(recent)
    wins = draws = losses = 0
    goals_for = goals_against = 0
    xg_for = xg_against = 0.0

    for m in recent:
        is_home = m.get("_is_home", True)
        gh = int(float(m.get("goals_home", 0)))
        ga = int(float(m.get("goals_away", 0)))
        xgh = float(m.get("xg_home", 0))
        xga = float(m.get("xg_away", 0))
        if is_home:
            goals_for += gh
            goals_against += ga
            xg_for += xgh
            xg_against += xga
        else:
            goals_for += ga
            goals_against += gh
            xg_for += xga
            xg_against += xgh
        if gh > ga:
            wins += 1
        elif gh < ga:
            losses += 1
        else:
            draws += 1

    points = wins * 3 + draws
    summary_zh = _form_summary_zh(team, played, wins, draws, losses, goals_for, goals_against, points)
    return {
        "played": played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "points": points,
        "xg_for": round(xg_for, 2),
        "xg_against": round(xg_against, 2),
        "summary_zh": summary_zh,
    }


def _form_summary_zh(
    team: str,
    played: int,
    wins: int,
    draws: int,
    losses: int,
    goals_for: int,
    goals_against: int,
    points: int,
) -> str:
    if played == 0:
        return f"{team} 近期无历史数据。"
    return (
        f"近 {played} 场：{wins} 胜 {draws} 平 {losses} 负，"
        f"进 {goals_for} 失 {goals_against}，积 {points} 分。"
    )
