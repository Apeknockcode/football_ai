#!/usr/bin/env python3
"""
通过免费库 soccerdata 抓取联赛数据（FotMob），输出 pl_YYYY_fotmob.csv。
第四版多维度参考：与 Understat、FBref 同为可选数据源，合并时可用。
依赖：pip install soccerdata。请遵守 FotMob 使用条款与访问频率，仅供个人/教育用途。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _norm_col(df, *candidates):
    """在 DataFrame 列名中查找候选（含大小写变体），返回第一个存在的列名。"""
    cols = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        k = str(cand).strip().lower()
        if k in cols:
            return cols[k]
        for c in df.columns:
            if cand.lower() in str(c).lower():
                return c
    return None


def _infer_rounds(schedule_df, date_col, matches_per_round=10):
    """按日期排序后按 matches_per_round 推断轮次。"""
    if date_col is None or date_col not in schedule_df.columns:
        return list(range(1, len(schedule_df) + 1))
    df = schedule_df.sort_values(date_col).reset_index(drop=True)
    rounds = []
    r = 1
    for i in range(len(df)):
        rounds.append(r)
        if (i + 1) % matches_per_round == 0:
            r += 1
    return rounds


def fetch_fotmob_matches(league_id: str, season_end: int) -> list[dict]:
    """
    使用 soccerdata.FotMob 拉取指定联赛、赛季的赛程与 xG，返回与 pl_YYYY.csv 同格式的 list[dict]。
    """
    import pandas as pd

    from football_ai.leagues import get_fotmob_league_id, get_league

    fotmob_league = get_fotmob_league_id(league_id)
    if not fotmob_league:
        return []

    try:
        import soccerdata as sd
    except ImportError:
        raise RuntimeError("请先安装 soccerdata：pip install soccerdata") from None

    # season_end=2024 表示 2023/24，soccerdata 接受 2024 或 "2023/2024"
    fotmob = sd.FotMob(leagues=fotmob_league, seasons=season_end)
    schedule = fotmob.read_schedule()
    if schedule is None or schedule.empty:
        return []

    # 统一为扁平列（soccerdata 可能返回 MultiIndex）
    if isinstance(schedule.columns, pd.MultiIndex):
        schedule.columns = [c[-1] if isinstance(c, tuple) else c for c in schedule.columns]
    if schedule.index.nlevels > 1:
        schedule = schedule.reset_index()

    home_col = _norm_col(schedule, "home_team", "Home")
    away_col = _norm_col(schedule, "away_team", "Away")
    score_h_col = _norm_col(schedule, "home_score", "home_score")
    score_a_col = _norm_col(schedule, "away_score", "away_score")
    game_col = _norm_col(schedule, "game", "game_id")
    date_col = _norm_col(schedule, "date")

    if home_col is None or away_col is None:
        return []
    if score_h_col is None:
        score_h_col = _norm_col(schedule, "home_score")
    if score_a_col is None:
        score_a_col = _norm_col(schedule, "away_score")

    # 只保留已完赛场次（有比分）
    schedule = schedule.copy()
    schedule = schedule.dropna(subset=[home_col, away_col])
    if score_h_col and score_a_col:
        schedule = schedule.dropna(subset=[score_h_col, score_a_col], how="all")
    if schedule.empty:
        return []

    # xG：读球队比赛统计，每场每队一行
    xg_by_game: dict[str, dict[str, float]] = {}
    try:
        stats = fotmob.read_team_match_stats(stat_type="Expected goals (xG)", opponent_stats=False)
        if stats is not None and not stats.empty:
            if isinstance(stats.columns, pd.MultiIndex):
                stats.columns = [c[-1] if isinstance(c, tuple) else c for c in stats.columns]
            if stats.index.nlevels > 1:
                stats = stats.reset_index()
            team_col = _norm_col(stats, "team", "Team")
            xg_col = _norm_col(stats, "Expected goals (xG)", "xG")
            stat_game_col = _norm_col(stats, "game", "game_id")
            if team_col and xg_col and stat_game_col:
                for _, row in stats.iterrows():
                    g = row.get(stat_game_col)
                    team = row.get(team_col)
                    try:
                        xg_val = float(row.get(xg_col, 0) or 0)
                    except (TypeError, ValueError):
                        xg_val = 0.0
                    if g is None or team is None:
                        continue
                    gk = str(g).strip()
                    if gk not in xg_by_game:
                        xg_by_game[gk] = {}
                    xg_by_game[gk][str(team).strip()] = xg_val
    except Exception:
        pass

    def get_xg(row, home_team, away_team):
        g = row.get(game_col) if game_col else None
        if g is None:
            return 0.0, 0.0
        gk = str(g).strip()
        by_team = xg_by_game.get(gk, {})
        h = str(home_team).strip() if home_team else ""
        a = str(away_team).strip() if away_team else ""
        return float(by_team.get(h, 0.0)), float(by_team.get(a, 0.0))

    rounds = _infer_rounds(schedule, date_col)
    out = []
    for idx, row in schedule.iterrows():
        home_team = row.get(home_col) or ""
        away_team = row.get(away_col) or ""
        try:
            goals_home = int(float(row.get(score_h_col, 0) or 0))
            goals_away = int(float(row.get(score_a_col, 0) or 0))
        except (TypeError, ValueError):
            goals_home = goals_away = 0
        xg_h, xg_a = get_xg(row, home_team, away_team)
        round_ = rounds[idx] if idx < len(rounds) else (idx + 1)
        out.append({
            "season": season_end,
            "round": round_,
            "home_team": home_team.strip(),
            "away_team": away_team.strip(),
            "xg_home": round(xg_h, 4),
            "xg_away": round(xg_a, 4),
            "goals_home": goals_home,
            "goals_away": goals_away,
        })
    return out


def main() -> None:
    import argparse
    from football_ai.leagues import get_historical_dir, get_league, get_fotmob_league_id

    parser = argparse.ArgumentParser(
        description="通过 soccerdata 抓取 FotMob 联赛数据 → pl_YYYY_fotmob.csv（第四版多源）"
    )
    parser.add_argument("--league", type=str, default="EPL", help="联赛 id（config/leagues.yaml）")
    parser.add_argument(
        "--season",
        type=int,
        nargs="*",
        default=[2025],
        metavar="YEAR",
        help="赛季结束年，如 2025、2026；可多个",
    )
    parser.add_argument("--out", type=Path, default=None, help="单赛季时指定输出 CSV")
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    league_cfg = get_league(league_id)
    if not league_cfg:
        print(f"未找到联赛配置: {league_id}。", file=sys.stderr)
        sys.exit(1)
    if not get_fotmob_league_id(league_id):
        print(f"联赛 {league_id} 未配置 fotmob_league_id，请在 config/leagues.yaml 中添加。", file=sys.stderr)
        sys.exit(1)

    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    seasons = args.season if args.season else [2025]
    total_written = 0

    for season_end in seasons:
        try:
            matches = fetch_fotmob_matches(league_id, season_end)
        except RuntimeError as e:
            print(f"FotMob 抓取失败: {e}", file=sys.stderr)
            continue
        if not matches:
            print(f"未获取到 {league_cfg.get('name_zh', league_id)} {season_end} 场次。", file=sys.stderr)
            continue
        out_path = (
            args.out
            if args.out and len(seasons) == 1
            else hist_dir / f"pl_{season_end}_fotmob.csv"
        )
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"],
            )
            w.writeheader()
            w.writerows(matches)
        print(f"已写入 {len(matches)} 场 → {out_path}", file=sys.stderr)
        total_written += len(matches)
    if total_written == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
