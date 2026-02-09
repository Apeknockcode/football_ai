#!/usr/bin/env python3
"""
第四版多维度参考：将同一联赛多数据源（Understat、FBref、FotMob）合并为 pl_YYYY.csv。
同场 xG 取各源平均，进球数以主源顺序为准（understat > fbref > fotmob）。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 源名称及进球优先顺序（排前的优先用于进球数）
SOURCE_ORDER = ["understat", "fbref", "fotmob", "fd", "sofascore", "espn", "whoscored"]


def _norm(s: str) -> str:
    """队名归一化便于匹配（去空格、小写）。"""
    if not s or not isinstance(s, str):
        return ""
    return s.strip().lower().replace("  ", " ")


def _key(season: int, round_: int, home: str, away: str) -> tuple:
    return (season, round_, _norm(home), _norm(away))


def load_csv(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
            try:
                r["season"] = int(r.get("season", 0))
                r["round"] = int(r.get("round", 0))
                r["xg_home"] = float(r.get("xg_home", 0))
                r["xg_away"] = float(r.get("xg_away", 0))
                r["goals_home"] = int(float(r.get("goals_home", 0)))
                r["goals_away"] = int(float(r.get("goals_away", 0)))
            except (ValueError, TypeError):
                continue
            rows.append(r)
    return rows


def merge_multi_sources(sources: list[tuple[str, list[dict]]]) -> list[dict]:
    """
    sources: [(source_name, rows), ...]，如 [("understat", u_rows), ("fbref", f_rows), ("fotmob", fo_rows)]。
    同场 xG 取所有有该场数据的源的平均；进球数以 SOURCE_ORDER 中第一个有该场的源为准。
    """
    by_key: dict[tuple, dict] = {}
    # 每个 key 下记录：各源 xG 列表、优先进球来源行
    xg_lists: dict[tuple, list[tuple[float, float]]] = {}
    primary_row: dict[tuple, dict] = {}

    for source_name, rows in sources:
        for r in rows:
            k = _key(r["season"], r["round"], r.get("home_team", ""), r.get("away_team", ""))
            if k not in xg_lists:
                xg_lists[k] = []
            xg_lists[k].append((r["xg_home"], r["xg_away"]))
            if k not in primary_row:
                primary_row[k] = r.copy()

    for k, xg_pairs in xg_lists.items():
        r = primary_row[k].copy()
        r.pop("_source", None)
        n = len(xg_pairs)
        r["xg_home"] = sum(p[0] for p in xg_pairs) / n
        r["xg_away"] = sum(p[1] for p in xg_pairs) / n
        by_key[k] = r

    out = []
    for r in sorted(by_key.values(), key=lambda x: (x["season"], x["round"], x.get("home_team", ""))):
        out.append(r)
    return out


def main() -> None:
    import argparse
    from football_ai.leagues import get_competition, get_historical_dir

    parser = argparse.ArgumentParser(description="合并联赛多数据源（Understat + FBref + FotMob）为 pl_YYYY.csv")
    parser.add_argument("--league", type=str, default="EPL", help="联赛 id")
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        metavar="YEAR",
        help="赛季结束年，如 2026",
    )
    parser.add_argument(
        "--primary",
        type=str,
        choices=SOURCE_ORDER,
        default="understat",
        help="合并时进球数以哪一源为准（默认 understat）",
    )
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    comp = get_competition(league_id)
    if not comp or comp.get("type") != "league":
        print(f"未找到联赛配置: {league_id}。", file=sys.stderr)
        sys.exit(1)

    hist_dir = get_historical_dir(league_id)
    season = args.season
    file_sources = [
        ("understat", hist_dir / f"pl_{season}.csv"),
        ("fbref", hist_dir / f"pl_{season}_fbref.csv"),
        ("fotmob", hist_dir / f"pl_{season}_fotmob.csv"),
        ("fd", hist_dir / f"pl_{season}_fd.csv"),
        ("sofascore", hist_dir / f"pl_{season}_sofascore.csv"),
        ("espn", hist_dir / f"pl_{season}_espn.csv"),
        ("whoscored", hist_dir / f"pl_{season}_whoscored.csv"),
    ]
    sources = []
    for name, path in file_sources:
        if path.exists():
            rows = load_csv(path)
            if rows:
                for r in rows:
                    r["_source"] = name
                sources.append((name, rows))

    if not sources:
        print(f"未找到 pl_{season}.csv 或任意 pl_{season}_<源>.csv（fbref/fotmob/fd/sofascore/espn/whoscored）。", file=sys.stderr)
        sys.exit(1)

    if len(sources) == 1 and sources[0][0] == "understat":
        print(f"仅 Understat 有数据，pl_{season}.csv 已存在，无需合并。", file=sys.stderr)
        sys.exit(0)

    if len(sources) == 1:
        merged = sources[0][1]
        for r in merged:
            r.pop("_source", None)
        print(f"仅 {sources[0][0]} 有数据，将写为 pl_{season}.csv。", file=sys.stderr)
    else:
        merged = merge_multi_sources(sources)
        names = [s[0] for s in sources]
        print(f"已合并 {', '.join(names)} → {len(merged)} 场。", file=sys.stderr)

    out_path = hist_dir / f"pl_{season}.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"],
        )
        w.writeheader()
        for r in merged:
            w.writerow({
                "season": r["season"],
                "round": r["round"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "xg_home": round(r["xg_home"], 4),
                "xg_away": round(r["xg_away"], 4),
                "goals_home": r["goals_home"],
                "goals_away": r["goals_away"],
            })
    print(f"已写入 {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
