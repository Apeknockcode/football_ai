"""
赛程与元数据：轮次、主客队、日期、裁判等。供政治·赛事/国家与报告使用。
"""
from pathlib import Path
from typing import Any

import pandas as pd


def load_fixture_meta(
    path: str | Path | None = None,
    fixture_id: str | None = None,
    round_: int | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    match_code: str | None = None,
) -> dict[str, Any]:
    """
    加载单场或一轮的赛程元数据。比赛时间应从数据中读取，不依赖用户输入。
    :param path: 本地赛程表 CSV/JSON（列可含 date, time/kick_off, home, away, round, match_code/竞彩场次）
    :param fixture_id: 若指定，返回该场
    :param round_: 若指定，可配合 home_team/away_team 筛选该轮某场
    :param home_team: 主队名，与 away_team 一起时从数据中匹配本场并返回 date/time
    :param away_team: 客队名
    :param match_code: 竞彩场次或第三方 ID（如 周五012、012），赛程表需含 match_code 或 竞彩场次 列
    :return: 单场时为 {"home", "away", "round", "date", "time", "referee", ...}；
             多场时为 {"fixtures": [...]}
    """
    if path is None:
        return {}

    path = Path(path)
    if not path.exists():
        return {}

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8")
    else:
        data = pd.read_json(path)
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data

    if df.empty:
        return {}

    # 列名兼容
    rename = {
        "home_team": "home",
        "away_team": "away",
        "matchday": "round",
        "match_day": "round",
        "kick_off": "time",
        "竞彩场次": "match_code",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if match_code and "match_code" in df.columns:
        code_str = str(match_code).strip()
        # 支持去掉前缀后匹配，如 周五012 与 012
        mask = df["match_code"].astype(str).str.strip() == code_str
        if not mask.any():
            mask = df["match_code"].astype(str).str.strip().str.endswith(code_str)
        if mask.any():
            return df[mask].iloc[0].to_dict()
        return {}
    if fixture_id and "fixture_id" in df.columns:
        row = df[df["fixture_id"] == fixture_id]
        if row.empty:
            return {}
        return row.iloc[0].to_dict()
    if round_ is not None and home_team is not None and away_team is not None:
        # 按轮次 + 主客队从数据中匹配本场，取 date/time
        if "round" in df.columns:
            df = df[df["round"] == round_]
        home_col = "home" if "home" in df.columns else None
        away_col = "away" if "away" in df.columns else None
        if home_col and away_col:
            mask = (df[home_col].astype(str).str.strip() == str(home_team).strip()) & (
                df[away_col].astype(str).str.strip() == str(away_team).strip()
            )
            row = df[mask]
            if not row.empty:
                return row.iloc[0].to_dict()
    if round_ is not None and "round" in df.columns:
        rows = df[df["round"] == round_]
        return {"fixtures": rows.to_dict("records")}
    return df.iloc[0].to_dict() if len(df) == 1 else {"fixtures": df.to_dict("records")}
