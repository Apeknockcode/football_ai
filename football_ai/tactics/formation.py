"""
阵型识别或读取。可为数据商提供，或从事件/位置数据推断。
"""
from typing import Any

import pandas as pd


def infer_formation(
    events: pd.DataFrame | None = None,
    lineup: dict[str, Any] | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
) -> dict[str, str]:
    """
    得到主客队阵型标签。
    :param events: 事件表（若有位置/阵型信息可推断）
    :param lineup: 若数据商直接给阵型，格式 {"home": "4-2-3-1", "away": "4-3-3"}
    :param home_team: 主队名（与 events 中 team 对应时可映射为 home）
    :param away_team: 客队名
    :return: {"home": "4-2-3-1", "away": "4-3-3"}，或含队名为 key 的映射
    """
    if lineup and isinstance(lineup, dict) and ("home" in lineup or "away" in lineup):
        return {
            "home": lineup.get("home", "4-3-3"),
            "away": lineup.get("away", "4-3-3"),
        }
    if events is not None and not events.empty and "formation" in events.columns:
        teams = events["team"].dropna().unique().tolist()
        if len(teams) >= 2:
            t0, t1 = teams[0], teams[1]
            f0 = events.loc[events["team"] == t0, "formation"].iloc[0]
            f1 = events.loc[events["team"] == t1, "formation"].iloc[0]
            out = {t0: f0, t1: f1}
            if home_team is not None and away_team is not None:
                out["home"] = out.get(home_team) or f0
                out["away"] = out.get(away_team) or f1
            return out
    return {"home": "4-3-3", "away": "4-3-3"}
