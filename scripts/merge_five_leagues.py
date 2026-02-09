#!/usr/bin/env python3
"""
合并五大联赛（英超、西甲、德甲、意甲、法甲）历史数据，写入 data/historical/Combined/。
用于基于统一大样本的校准与回测。输出 CSV 含 league 列标识来源联赛。
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIVE_LEAGUES = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"]
HIST_DIR = ROOT / "data" / "historical"
OUT_DIR = HIST_DIR / "Combined"
REQUIRED_COLUMNS = ["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"]


def main() -> None:
    parser = argparse.ArgumentParser(description="合并五大联赛历史数据到 data/historical/Combined/")
    parser.add_argument(
        "--seasons",
        type=str,
        nargs="+",
        default=["2024", "2025"],
        help="要合并的赛季年，如 2024 2025",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="输出目录",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    all_matches: list[dict] = []
    for league_id in FIVE_LEAGUES:
        league_dir = HIST_DIR / league_id
        if not league_dir.exists():
            print(f"跳过（目录不存在）: {league_id}", file=sys.stderr)
            continue
        for season in args.seasons:
            candidates = [
                league_dir / f"pl_{season}.csv",
                league_dir / f"pl_{season}_understat.csv",
            ]
            for fp in candidates:
                if fp.exists():
                    count = 0
                    with open(fp, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
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
                            r["league"] = league_id
                            all_matches.append(r)
                            count += 1
                    print(f"读取 {league_id} pl_{season}.csv: {count} 场")
                    break
            else:
                print(f"未找到 {league_id} 赛季 {season} 数据", file=sys.stderr)

    if not all_matches:
        print("未合并到任何场次，请确保五大联赛目录下存在 pl_2024.csv、pl_2025.csv 等。", file=sys.stderr)
        sys.exit(1)

    # 按 season、league、round 排序
    all_matches.sort(key=lambda m: (m["season"], m.get("league", ""), m["round"], m.get("home_team", "")))

    # 按赛季分文件输出
    by_season: dict[int, list[dict]] = {}
    for m in all_matches:
        s = m["season"]
        if s not in by_season:
            by_season[s] = []
        by_season[s].append(m)

    total = 0
    for season in sorted(by_season.keys()):
        rows = by_season[season]
        out_path = out_dir / f"pl_{season}.csv"
        fieldnames = ["league", "season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"]
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        total += len(rows)
        print(f"已写入 {out_path}: {len(rows)} 场")

    print(f"合并完成，共 {total} 场，来自 {len(FIVE_LEAGUES)} 个联赛、{len(by_season)} 个赛季。")


if __name__ == "__main__":
    main()
