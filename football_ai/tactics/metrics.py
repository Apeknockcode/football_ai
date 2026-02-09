"""
战术指标：控球率（按持续时间）、xG、射门次数等。输入为归一化后的事件表。
第二版：从 StatsBomb 事件流计算真实控球率与 xG。
"""
from typing import Any

import pandas as pd


def compute_metrics(events: pd.DataFrame) -> dict[str, Any]:
    """
    基于事件流计算一场比赛的战术指标。
    控球率：按各队 possession 相关事件的 duration 之和占比（有 duration 则按时间，否则按事件数）。
    xG/射门：仅 Shot 事件，shot_xg 列求和；射门次数为 Shot 事件数。
    :param events: 归一化后事件表，含 type, team, duration, shot_xg 等
    :return: possession_pct, xg, shots 等，键为队名（主/客或中文）
    """
    if events is None or events.empty:
        return _empty_metrics()

    out = {
        "possession_pct": {},
        "xg": {},
        "shots": {},
        "pressure": {"home": {}, "away": {}},
        "zones": {"home": {"left": 0.33, "center": 0.34, "right": 0.33}, "away": {"left": 0.33, "center": 0.34, "right": 0.33}},
        "transitions": {},
    }

    # 控球：优先按 duration 汇总（使用 possession_team 或 team）
    poss_col = "possession_team" if "possession_team" in events.columns else "team"
    if poss_col not in events.columns:
        poss_col = "team"
    if poss_col in events.columns:
        total_dur = events["duration"].fillna(0).sum()
        if total_dur > 0 and "duration" in events.columns:
            by_team = events.groupby(poss_col)["duration"].sum()
            for t in by_team.index:
                out["possession_pct"][t] = float(by_team[t] / total_dur)
        else:
            cnt = events[poss_col].value_counts()
            total = cnt.sum()
            if total > 0:
                for t in cnt.index:
                    out["possession_pct"][t] = float(cnt[t] / total)
    if not out["possession_pct"] and "team" in events.columns:
        cnt = events["team"].value_counts()
        total = cnt.sum()
        if total > 0:
            for t in cnt.index:
                out["possession_pct"][t] = float(cnt[t] / total)

    # 射门与 xG
    shots = events[events["type"] == "Shot"] if "type" in events.columns else pd.DataFrame()
    if not shots.empty and "team" in shots.columns:
        for team in shots["team"].dropna().unique():
            t_shots = shots[shots["team"] == team]
            out["shots"][team] = len(t_shots)
            if "shot_xg" in t_shots.columns:
                out["xg"][team] = float(t_shots["shot_xg"].fillna(0).sum())
            else:
                out["xg"][team] = 0.0
    # 若没有 Shot 事件，用默认 0
    teams = events["team"].dropna().unique() if "team" in events.columns else []
    for t in teams:
        if t not in out.get("xg", {}):
            out["xg"][t] = 0.0
        if t not in out.get("shots", {}):
            out["shots"][t] = 0
    if not out["possession_pct"] and len(teams) >= 2:
        out["possession_pct"] = {teams[0]: 0.5, teams[1]: 0.5}
    return out


def _empty_metrics() -> dict[str, Any]:
    return {
        "possession_pct": {"home": 0.5, "away": 0.5},
        "xg": {"home": 0.0, "away": 0.0},
        "shots": {},
        "pressure": {"home": {}, "away": {}},
        "zones": {"home": {"left": 0.33, "center": 0.34, "right": 0.33}, "away": {"left": 0.33, "center": 0.34, "right": 0.33}},
        "transitions": {},
    }
