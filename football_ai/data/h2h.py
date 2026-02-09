"""
历史交锋（H2H）：从历史场次中筛选同一对主客队的对战记录。
数据来源：load_historical_matches；供报告展示。排序见 sort_key_match（优先 match_date）。
"""
from typing import Any

from football_ai.data.historical import sort_key_match


def get_h2h(
    home_team: str,
    away_team: str,
    matches: list[dict[str, Any]],
    last_n: int | None = 10,
) -> dict[str, Any]:
    """
    统计主队 vs 客队的历史交锋。
    :param home_team: 主队名
    :param away_team: 客队名
    :param matches: 历史场次列表
    :param last_n: 最多取最近几场，None 表示全部
    :return: total, home_wins, draws, away_wins, goals_home, goals_away, last_result_zh, summary_zh
    """
    home = home_team.strip()
    away = away_team.strip()
    h2h_matches: list[dict[str, Any]] = []
    for m in matches:
        h = (m.get("home_team") or "").strip()
        a = (m.get("away_team") or "").strip()
        if (h == home and a == away) or (h == away and a == home):
            h2h_matches.append(m)

    # 按比赛时间升序（优先 match_date），取最后 last_n 场
    sorted_h2h = sorted(h2h_matches, key=sort_key_match)
    if last_n is not None and len(sorted_h2h) > last_n:
        sorted_h2h = sorted_h2h[-last_n:]

    total = len(sorted_h2h)
    home_wins = draws = away_wins = 0
    goals_home_total = goals_away_total = 0

    for m in sorted_h2h:
        h = (m.get("home_team") or "").strip()
        a = (m.get("away_team") or "").strip()
        gh = int(float(m.get("goals_home", 0)))
        ga = int(float(m.get("goals_away", 0)))
        if h == home and a == away:
            goals_home_total += gh
            goals_away_total += ga
            if gh > ga:
                home_wins += 1
            elif gh < ga:
                away_wins += 1
            else:
                draws += 1
        else:
            goals_home_total += ga
            goals_away_total += gh
            if ga > gh:
                home_wins += 1
            elif ga < gh:
                away_wins += 1
            else:
                draws += 1

    last_result_zh = ""
    if sorted_h2h:
        last = sorted_h2h[-1]
        lh = (last.get("home_team") or "").strip()
        la = (last.get("away_team") or "").strip()
        lgh = int(float(last.get("goals_home", 0)))
        lga = int(float(last.get("goals_away", 0)))
        if lh == home and la == away:
            last_result_zh = f"上次交锋：{home} {lgh}-{lga} {away}"
        else:
            last_result_zh = f"上次交锋：{away} {lga}-{lgh} {home}（{away} 主场）"

    summary_zh = _h2h_summary_zh(
        home, away, total, home_wins, draws, away_wins, goals_home_total, goals_away_total, last_result_zh
    )
    return {
        "total": total,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "goals_home": goals_home_total,
        "goals_away": goals_away_total,
        "last_result_zh": last_result_zh,
        "summary_zh": summary_zh,
    }


def _h2h_summary_zh(
    home: str,
    away: str,
    total: int,
    home_wins: int,
    draws: int,
    away_wins: int,
    goals_home: int,
    goals_away: int,
    last_result_zh: str,
) -> str:
    if total == 0:
        return "暂无历史交锋数据。"
    parts = [
        f"近 {total} 次交锋：{home} {home_wins} 胜 {draws} 平 {away_wins} 负，"
        f"总比分 {goals_home}-{goals_away}（主队视角）。"
    ]
    if last_result_zh:
        parts.append(last_result_zh)
    return " ".join(parts)
