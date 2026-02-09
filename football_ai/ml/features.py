"""
ML 特征：从历史场次为每场比赛构建特征向量（仅使用该场之前的数据），用于训练或预测。
特征含：本场 xG、双方近期状态、赛季统计/xPts、H2H、Elo。
"""
from typing import Any

import numpy as np

from football_ai.data.form import get_team_form
from football_ai.data.h2h import get_h2h
from football_ai.data.historical import sort_key_match
from football_ai.data.team_stats import get_team_season_stats
from football_ai.data.elo import get_elo_for_report

FEATURE_NAMES = [
    "xg_home", "xg_away",
    "home_pts_last5", "home_gf_last5", "home_ga_last5",
    "away_pts_last5", "away_gf_last5", "away_ga_last5",
    "home_pts_season", "home_xpts_season", "home_xg_season", "home_xga_season",
    "away_pts_season", "away_xpts_season", "away_xg_season", "away_xga_season",
    "h2h_home_wins", "h2h_draws", "h2h_away_wins", "h2h_matches",
    "elo_home", "elo_away",
]


def build_feature_row(
    match: dict[str, Any],
    past_matches: list[dict[str, Any]],
    n_form: int = 5,
    n_h2h: int = 10,
) -> dict[str, float]:
    """
    为单场比赛构建特征（仅用 past_matches 中该场之前的场次）。
    :param match: 本场，含 season, round, home_team, away_team, xg_home, xg_away, goals_home, goals_away
    :param past_matches: 本场之前的所有历史场次（同联赛/同赛季）
    :return: 特征名 -> 数值，缺失填 0
    """
    season = int(match.get("season", 0))
    round_ = int(match.get("round", 0))
    home = (match.get("home_team") or "").strip()
    away = (match.get("away_team") or "").strip()
    xg_h = float(match.get("xg_home", 0))
    xg_a = float(match.get("xg_away", 0))

    form_h = get_team_form(home, past_matches, season, round_before=round_, n_matches=n_form)
    form_a = get_team_form(away, past_matches, season, round_before=round_, n_matches=n_form)
    stats_h = get_team_season_stats(home, past_matches, season, round_before=round_)
    stats_a = get_team_season_stats(away, past_matches, season, round_before=round_)
    h2h = get_h2h(home, away, past_matches, last_n=n_h2h)
    elo_block = get_elo_for_report(home, away, past_matches, season, round_)

    elo_h = elo_block["elo_home"] if elo_block else 1500.0
    elo_a = elo_block["elo_away"] if elo_block else 1500.0

    return {
        "xg_home": xg_h,
        "xg_away": xg_a,
        "home_pts_last5": float(form_h["points"]),
        "home_gf_last5": float(form_h["goals_for"]),
        "home_ga_last5": float(form_h["goals_against"]),
        "away_pts_last5": float(form_a["points"]),
        "away_gf_last5": float(form_a["goals_for"]),
        "away_ga_last5": float(form_a["goals_against"]),
        "home_pts_season": float(stats_h["pts"]),
        "home_xpts_season": float(stats_h["xpts"]),
        "home_xg_season": float(stats_h["xg_for"]),
        "home_xga_season": float(stats_h["xg_against"]),
        "away_pts_season": float(stats_a["pts"]),
        "away_xpts_season": float(stats_a["xpts"]),
        "away_xg_season": float(stats_a["xg_for"]),
        "away_xga_season": float(stats_a["xg_against"]),
        "h2h_home_wins": float(h2h["home_wins"]),
        "h2h_draws": float(h2h["draws"]),
        "h2h_away_wins": float(h2h["away_wins"]),
        "h2h_matches": float(h2h["total"]),
        "elo_home": elo_h,
        "elo_away": elo_a,
    }


def build_dataset(
    matches: list[dict[str, Any]],
    n_form: int = 5,
    n_h2h: int = 10,
    target: str = "wdl",
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    为多场比赛构建特征矩阵与目标变量。
    :param matches: 历史场次列表（会按 season, round 排序，每场用其之前的场次做特征）
    :param target: "wdl" -> 0=客胜 1=平 2=主胜；"goals_home"/"goals_away" 回归
    :return: X (n, n_features), y (n,) 或 (n, 3) for wdl one-hot, feature_names
    """
    sorted_matches = sorted(matches, key=sort_key_match)
    rows: list[dict[str, float]] = []
    targets: list[Any] = []

    for i, m in enumerate(sorted_matches):
        past = sorted_matches[:i]
        if len(past) < 2:
            continue
        row = build_feature_row(m, past, n_form=n_form, n_h2h=n_h2h)
        rows.append(row)
        gh = int(float(m.get("goals_home", 0)))
        ga = int(float(m.get("goals_away", 0)))
        if target == "wdl":
            if gh > ga:
                targets.append(2)
            elif gh < ga:
                targets.append(0)
            else:
                targets.append(1)
        elif target == "goals_home":
            targets.append(gh)
        elif target == "goals_away":
            targets.append(ga)
        else:
            targets.append(2 if gh > ga else (1 if gh == ga else 0))

    X = np.array([[row[k] for k in FEATURE_NAMES] for row in rows], dtype=np.float64)
    y = np.array(targets, dtype=np.int64 if target == "wdl" else np.float64)
    return X, y, FEATURE_NAMES.copy()
