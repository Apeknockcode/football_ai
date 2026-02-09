#!/usr/bin/env python3
"""
用 FBref 赛程页的本地 HTML 覆盖五大联赛 2024 的 pl_2024.csv（换源，避免 403）。
用法：
  1. 在浏览器中打开各联赛 2023-24 赛程页，另存为「完整网页」到同一目录。
  2. 将文件命名为：EPL.html, La_Liga.html, Bundesliga.html, Serie_A.html, Ligue_1.html
  3. 执行：python scripts/replace_pl2024_from_fbref_html.py --html-dir <目录>
  4. 运行 ./run.sh merge-five 重新生成 Combined/pl_2024.csv

赛程页 URL 示例（赛季 2023-2024）：
  - 英超: https://fbref.com/en/comps/9/2023-2024/schedule/2023-2024-Premier-League-Scores-and-Fixtures
  - 西甲: https://fbref.com/en/comps/12/2023-2024/schedule/2023-2024-La-Liga-Scores-and-Fixtures
  - 德甲: https://fbref.com/en/comps/20/2023-2024/schedule/2023-2024-Bundesliga-Scores-and-Fixtures
  - 意甲: https://fbref.com/en/comps/11/2023-2024/schedule/2023-2024-Serie-A-Scores-and-Fixtures
  - 法甲: https://fbref.com/en/comps/13/2023-2024/schedule/2023-2024-Ligue-1-Scores-and-Fixtures
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

FIVE_LEAGUES = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"]
SEASON_END = 2024  # 2023-24 赛季


def main() -> None:
    import argparse
    from football_ai.leagues import get_fbref_league_config, get_historical_dir
    from fetch_historical_fbref_cups import fetch_cup_matches_fbref

    parser = argparse.ArgumentParser(
        description="用 FBref 本地 HTML 覆盖五大联赛 pl_2024.csv（换源）"
    )
    parser.add_argument(
        "--html-dir",
        type=Path,
        required=True,
        help="存放 5 个联赛 HTML 的目录，文件名为 EPL.html, La_Liga.html, ...",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=SEASON_END,
        help="赛季结束年，默认 2024（即 2023-24）",
    )
    args = parser.parse_args()

    html_dir = args.html_dir.resolve()
    if not html_dir.is_dir():
        print(f"目录不存在: {html_dir}", file=sys.stderr)
        sys.exit(1)

    season_end = args.season
    total = 0
    for league_id in FIVE_LEAGUES:
        comp_id, slug = get_fbref_league_config(league_id)
        if comp_id is None or not slug:
            print(f"跳过 {league_id}：未配置 fbref。", file=sys.stderr)
            continue
        # 支持 EPL.html 或 epl.html 等
        candidates = [html_dir / f"{league_id}.html", html_dir / f"{league_id.lower()}.html"]
        html_path = None
        for p in candidates:
            if p.exists():
                html_path = p
                break
        if not html_path:
            print(f"跳过 {league_id}：未找到 {league_id}.html。", file=sys.stderr)
            continue
        try:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"{league_id} 读取失败: {e}", file=sys.stderr)
            continue
        try:
            matches = fetch_cup_matches_fbref(comp_id, slug, season_end, html=html_content)
        except Exception as e:
            print(f"{league_id} 解析失败: {e}", file=sys.stderr)
            continue
        if not matches:
            print(f"{league_id} 未解析到场次。", file=sys.stderr)
            continue
        # 仅保留正赛轮次（FBref 页内其他表格可能被解析成 round 很大）
        max_round = 34 if league_id in ("Bundesliga", "Ligue_1") else 38
        matches = [m for m in matches if m["round"] <= max_round]
        out_path = get_historical_dir(league_id) / f"pl_{season_end}.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "season": season_end,
                "round": m["round"],
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "xg_home": m["xg_home"],
                "xg_away": m["xg_away"],
                "goals_home": m["goals_home"],
                "goals_away": m["goals_away"],
            }
            for m in matches
        ]
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"],
            )
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {len(rows)} 场 → {out_path}")
        total += len(rows)

    if total == 0:
        print("未成功写入任何联赛，请检查 --html-dir 下是否有 EPL.html 等文件。", file=sys.stderr)
        sys.exit(1)
    print(f"共写入 {total} 场。请运行 ./run.sh merge-five 生成 Combined/pl_2024.csv。")


if __name__ == "__main__":
    main()
