"""
传统统计与 xPts/xGA：按球队、赛季（及可选轮次前）聚合胜平负、进球/失球、积分与预期积分。
单场 xPts = 3 * P(胜) + 1 * P(平)，由该场 xG/xGA 经 Poisson 得到胜平负概率。
"""
import math
from typing import Any


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _xpts_from_xg(xg_for: float, xg_against: float) -> float:
    """单场预期积分：由 Poisson(xg_for) vs Poisson(xg_against) 得 P(胜/平/负)，xPts = 3*P胜 + 1*P平。"""
    max_goals = 10
    p_win = p_draw = p_lose = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = _poisson_pmf(i, xg_for) * _poisson_pmf(j, xg_against)
            if i > j:
                p_win += p
            elif i == j:
                p_draw += p
            else:
                p_lose += p
    return 3.0 * p_win + 1.0 * p_draw


def get_team_season_stats(
    team: str,
    matches: list[dict[str, Any]],
    season: int,
    round_before: int | None = None,
) -> dict[str, Any]:
    """
    某队在该赛季（及 optional 在某轮之前）的统计：胜平负、进失球、积分、xG/xGA、xPts。
    :param team: 球队名
    :param matches: 历史场次，含 season, round, home_team, away_team, goals_*, xg_*
    :param season: 赛季年
    :param round_before: 若指定，只统计 (season, round) < (season, round_before) 的场次
    :return: played, wins, draws, losses, goals_for, goals_against, pts, xg_for, xg_against, xpts, summary_zh
    """
    team_matches: list[dict[str, Any]] = []
    for m in matches:
        if int(m.get("season", 0)) != season:
            continue
        r = int(m.get("round", 0))
        if round_before is not None and r >= round_before:
            continue
        if (m.get("home_team") or "").strip() == team.strip():
            team_matches.append({**m, "_is_home": True})
        elif (m.get("away_team") or "").strip() == team.strip():
            team_matches.append({**m, "_is_home": False})

    played = len(team_matches)
    wins = draws = losses = 0
    goals_for = goals_against = 0
    xg_for = xg_against = 0.0
    xpts_total = 0.0

    for m in team_matches:
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
            xpts_total += _xpts_from_xg(xgh, xga)
        else:
            goals_for += ga
            goals_against += gh
            xg_for += xga
            xg_against += xgh
            xpts_total += _xpts_from_xg(xga, xgh)
        if gh > ga:
            wins += 1
        elif gh < ga:
            losses += 1
        else:
            draws += 1

    pts = wins * 3 + draws
    summary_zh = _team_stats_summary_zh(
        team, played, wins, draws, losses,
        goals_for, goals_against, pts,
        round(xg_for, 2), round(xg_against, 2), round(xpts_total, 1),
    )
    return {
        "played": played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "pts": pts,
        "xg_for": round(xg_for, 2),
        "xg_against": round(xg_against, 2),
        "xpts": round(xpts_total, 1),
        "summary_zh": summary_zh,
    }


def _team_stats_summary_zh(
    team: str,
    played: int,
    wins: int,
    draws: int,
    losses: int,
    goals_for: int,
    goals_against: int,
    pts: int,
    xg_for: float,
    xg_against: float,
    xpts: float,
) -> str:
    if played == 0:
        return f"{team} 本季暂无数据。"
    win_rate = (wins / played * 100) if played else 0
    avg_gf = goals_for / played
    avg_ga = goals_against / played
    return (
        f"{team} 赛季至今 {played} 场：{wins} 胜 {draws} 平 {losses} 负（胜率 {win_rate:.0f}%），"
        f"场均进 {avg_gf:.1f} 失 {avg_ga:.1f}；实际积分 {pts}，预期积分 xPts {xpts:.1f}（xG {xg_for:.1f} / xGA {xg_against:.1f}）。"
    )
