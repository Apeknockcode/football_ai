"""
历史场次数据：用于校准与回测。格式见 data/historical/README.md。
数据定义、轮次语义与清洗流程见 docs/历史数据-定义与清洗.md。
若 CSV 含 match_date（YYYY-MM-DD），会原样保留；依赖时间顺序的逻辑应优先按 match_date 排序，无则按 (season, round)。
"""
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = [
    "season", "round", "home_team", "away_team",
    "xg_home", "xg_away", "goals_home", "goals_away",
]
# 推荐列：存在时保留，用于正确排序与清洗（见 历史数据-定义与清洗.md）
OPTIONAL_ORDER_COLUMN = "match_date"


def load_historical_matches(
    path: str | Path | None = None,
    *,
    directory: str | Path | None = None,
    paths: list[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """
    加载历史场次表。可从单文件、目录（所有 CSV）或显式路径列表读取。
    :param path: 单文件路径（CSV）
    :param directory: 目录路径，将读取该目录下所有 .csv
    :param paths: 多个文件路径
    :return: 每场一行，键含 season, round, home_team, away_team, xg_home, xg_away, goals_home, goals_away 等
    """
    import csv

    to_read: list[Path] = []
    if path is not None:
        p = Path(path)
        if p.is_file():
            to_read.append(p)
        elif p.is_dir():
            to_read.extend(sorted(p.glob("*.csv")))
    if directory is not None:
        d = Path(directory)
        if d.is_dir():
            to_read.extend(sorted(d.glob("*.csv")))
    if paths:
        for f in paths:
            pf = Path(f)
            if pf.is_file():
                to_read.append(pf)

    seen = set()
    to_read = [p for p in to_read if p not in seen and not seen.add(p)]
    rows: list[dict[str, Any]] = []

    for fp in to_read:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 归一化列名：strip
                    r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                    # 保留 match_date（若存在），用于时间排序
                    if "match_date" in r and r["match_date"]:
                        r["match_date"] = str(r["match_date"]).strip()[:10]
                    # 必选列转为数值
                    try:
                        r["season"] = int(r.get("season", 0))
                        r["round"] = int(r.get("round", 0))
                        r["xg_home"] = float(r.get("xg_home", 0))
                        r["xg_away"] = float(r.get("xg_away", 0))
                        r["goals_home"] = int(float(r.get("goals_home", 0)))
                        r["goals_away"] = int(float(r.get("goals_away", 0)))
                    except (ValueError, TypeError):
                        continue
                    # 排除无效场次：goals 与 xG 均为 0 多为未开赛/缺数据，非真实 0-0
                    if (
                        r["goals_home"] == 0
                        and r["goals_away"] == 0
                        and r["xg_home"] == 0
                        and r["xg_away"] == 0
                    ):
                        continue
                    rows.append(r)
        except OSError:
            continue

    return rows


def sort_key_match(row: dict[str, Any]) -> tuple:
    """
    用于按「比赛时间」排序的键。优先使用 match_date（YYYY-MM-DD），无则退化为 (season, round)。
    依赖时间顺序的模块（近期状态、H2H、Elo、xPts、ML）应对 load_historical_matches 结果用此键排序。
    """
    md = (row.get("match_date") or "").strip()[:10]
    s, r = int(row.get("season", 0)), int(row.get("round", 0))
    if len(md) >= 10 and md.count("-") == 2:
        return (md, s, r)
    return ("0000-00-00", s, r)  # 无日期时放前段，按 season/round 排
