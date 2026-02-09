"""
事件数据接入。第二版：StatsBomb JSON 文件加载与归一化为战术模块所需格式。
"""
from pathlib import Path
from typing import Any

import pandas as pd


def load_events(
    path: str | Path | None = None,
    match_id: str | None = None,
    provider: str = "statsbomb",
) -> pd.DataFrame:
    """
    加载单场或多场事件流。
    :param path: 本地文件或目录。StatsBomb 为单场 JSON 文件（事件数组）。
    :param match_id: 若指定，仅返回该场（StatsBomb 暂按单文件单场处理）
    :param provider: statsbomb | opta | wyscout
    :return: 事件表，列含 type, team, period, duration, x, y 等；StatsBomb 含 shot_xg
    """
    if path is None:
        return pd.DataFrame()

    path = Path(path)
    if not path.exists():
        return pd.DataFrame()

    if provider.lower() == "statsbomb":
        return _load_statsbomb(path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8")
    elif path.suffix.lower() == ".json":
        df = pd.read_json(path)
        if isinstance(df, list):
            df = pd.json_normalize(df)
        elif "events" in df.columns and len(df) == 1:
            raw = df["events"].iloc[0]
            df = pd.json_normalize(raw) if raw else pd.DataFrame()
    else:
        return pd.DataFrame()

    if df.empty or match_id is None:
        return df
    if "match_id" in df.columns:
        df = df[df["match_id"] == match_id].copy()
    return df


def _load_statsbomb(path: Path) -> pd.DataFrame:
    """读取 StatsBomb 单场事件 JSON（顶层为事件数组）。"""
    import json
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list) or not raw:
        return pd.DataFrame()
    rows = []
    for ev in raw:
        team = (ev.get("team") or {}).get("name")
        typ = (ev.get("type") or {}).get("name")
        pos_team = (ev.get("possession_team") or {}).get("name")
        loc = ev.get("location") or []
        x = loc[0] if len(loc) >= 1 else None
        y = loc[1] if len(loc) >= 2 else None
        duration = ev.get("duration")
        if duration is None:
            duration = 0.0
        row = {
            "id": ev.get("id"),
            "index": ev.get("index"),
            "period": ev.get("period"),
            "minute": ev.get("minute"),
            "second": ev.get("second"),
            "timestamp": ev.get("timestamp"),
            "type": typ,
            "team": team,
            "possession_team": pos_team,
            "duration": float(duration),
            "x": x,
            "y": y,
        }
        if typ == "Shot":
            shot = ev.get("shot") or {}
            row["shot_xg"] = shot.get("statsbomb_xg") or shot.get("xg")
            if row["shot_xg"] is None:
                row["shot_xg"] = 0.0
        else:
            row["shot_xg"] = None
        rows.append(row)
    return pd.DataFrame(rows)


def normalize_events_for_tactics(
    df: pd.DataFrame,
    provider: str = "statsbomb",
    team_name_mapping: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    将原始事件表统一为战术模块所需字段。
    :param team_name_mapping: 可选，如 {"Manchester United": "曼联"}，将 team 列替换为中文
    :return: 列至少含 type, team, period, duration, x, y；若有射门则含 shot_xg
    """
    if df.empty:
        return df
    out = df.copy()
    if provider.lower() == "statsbomb":
        if "possession_team" in out.columns and "team" not in out.columns:
            out["team"] = out["possession_team"]
        if team_name_mapping:
            def _map(t):
                return team_name_mapping.get(t, t) if isinstance(t, str) else t
            if "team" in out.columns:
                out["team"] = out["team"].map(_map)
            if "possession_team" in out.columns:
                out["possession_team"] = out["possession_team"].map(_map)
        if "shot_xg" not in out.columns:
            out["shot_xg"] = None
    return out
