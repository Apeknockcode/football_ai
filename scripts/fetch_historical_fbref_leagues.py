#!/usr/bin/env python3
"""
从 FBref 抓取联赛（英超、西甲、德甲、意甲、法甲、英冠等）指定赛季的赛果与 xG，
写入 data/historical/{league_id}/pl_YYYY_fbref.csv。第四版多维度参考：与 Understat 同联赛多源。
依赖：pandas。请遵守 fbref.com 使用条款与访问频率，仅供个人/教育用途。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

# 联赛赛程页与杯赛结构相同，复用杯赛抓取函数
from fetch_historical_fbref_cups import fetch_cup_matches_fbref


def main() -> None:
    import argparse
    from football_ai.leagues import get_league, get_historical_dir, get_fbref_league_config

    parser = argparse.ArgumentParser(
        description="从 FBref 抓取联赛历史场次并写入 data/historical/{league_id}/pl_YYYY_fbref.csv（第四版多源）"
    )
    parser.add_argument("--league", type=str, default=None, help="联赛 id（见 config/leagues.yaml），如 EPL、La_Liga")
    parser.add_argument(
        "--season",
        type=int,
        nargs="*",
        default=[2025],
        metavar="YEAR",
        help="赛季结束年，如 2025=2024/25、2026=2025/26（含 2026 年 1–2 月）；可多个",
    )
    parser.add_argument("--out", type=Path, default=None, help="单赛季时指定输出 CSV（多赛季时忽略）")
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        help="从本地保存的 FBref 赛程页 HTML 解析（遇 403 时可浏览器另存为完整网页）",
    )
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    league_cfg = get_league(league_id)
    if not league_cfg:
        print(f"未找到联赛配置: {league_id}，请检查 config/leagues.yaml。", file=sys.stderr)
        sys.exit(1)
    comp_id, slug = get_fbref_league_config(league_id)
    if comp_id is None or not slug:
        print(
            f"联赛 {league_id} 未配置 fbref_comp_id/fbref_slug，无法从 FBref 抓取。可在 leagues.yaml 中添加。",
            file=sys.stderr,
        )
        sys.exit(1)

    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    seasons = args.season if args.season else [2025]
    total_written = 0

    html_content = None
    if args.html:
        if not args.html.exists():
            print(f"文件不存在: {args.html}", file=sys.stderr)
            sys.exit(1)
        html_content = args.html.read_text(encoding="utf-8", errors="replace")
        if len(seasons) != 1:
            print("--html 仅支持单赛季，将只解析一次。", file=sys.stderr)
            seasons = seasons[:1]

    for season_end in seasons:
        try:
            matches = fetch_cup_matches_fbref(comp_id, slug, season_end, html=html_content)
        except RuntimeError as e:
            print(f"抓取 {league_cfg.get('name_zh', league_id)} {season_end} 失败: {e}", file=sys.stderr)
            continue
        if not matches:
            print(f"未解析到 {league_id} {season_end} 场次。", file=sys.stderr)
            continue
        out_path = (
            args.out
            if args.out and len(seasons) == 1
            else hist_dir / f"pl_{season_end}_fbref.csv"
        )
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
        print(f"已写入 {len(rows)} 场 → {out_path}", file=sys.stderr)
        total_written += len(rows)
    if total_written == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
