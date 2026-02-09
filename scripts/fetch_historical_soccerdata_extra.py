#!/usr/bin/env python3
"""
通过 soccerdata 抓取 Sofascore、ESPN、WhoScored 联赛赛程/赛果，输出 pl_YYYY_sofascore.csv 等。
与 Understat/FBref/FotMob 同为多源可选；Sofascore/ESPN 用普通 requests，WhoScored 需 Selenium。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _norm_col(df, *candidates):
    cols = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        k = str(cand).strip().lower()
        if k in cols:
            return cols[k]
        for c in df.columns:
            if cand.lower() in str(c).lower():
                return c
    return None


def _schedule_to_rows(schedule, season_end: int, source: str):
    """将 soccerdata schedule DataFrame 转为 pl_*.csv 行（无 xG 填 0）。"""
    import pandas as pd

    if schedule is None or schedule.empty:
        return []
    if schedule.index.nlevels > 1:
        schedule = schedule.reset_index()
    if isinstance(schedule.columns, pd.MultiIndex):
        schedule.columns = [c[-1] if isinstance(c, tuple) else c for c in schedule.columns]

    home_col = _norm_col(schedule, "home_team", "Home")
    away_col = _norm_col(schedule, "away_team", "Away")
    if home_col is None or away_col is None:
        return []
    sh_col = _norm_col(schedule, "home_score")
    sa_col = _norm_col(schedule, "away_score")
    round_col = _norm_col(schedule, "round")

    out = []
    for idx, row in schedule.iterrows():
        home = (row.get(home_col) or "").strip()
        away = (row.get(away_col) or "").strip()
        if not home or not away:
            continue
        try:
            gh = int(float(row.get(sh_col) or 0))
            ga = int(float(row.get(sa_col) or 0))
        except (TypeError, ValueError):
            gh = ga = 0
        # 只保留已完赛（有比分）或统一保留
        if sh_col and sa_col and pd.isna(row.get(sh_col)) and pd.isna(row.get(sa_col)):
            continue
        rnd = int(row.get(round_col, idx + 1)) if round_col else (len(out) // 10 + 1)
        out.append({
            "season": season_end,
            "round": rnd,
            "home_team": home,
            "away_team": away,
            "xg_home": 0.0,
            "xg_away": 0.0,
            "goals_home": gh,
            "goals_away": ga,
        })
    return out


def fetch_sofascore(league_id: str, season_end: int) -> list[dict]:
    from football_ai.leagues import get_fotmob_league_id

    canonical = get_fotmob_league_id(league_id)
    if not canonical:
        return []
    try:
        import soccerdata as sd
    except ImportError:
        raise RuntimeError("请先安装 soccerdata：pip install soccerdata") from None
    reader = sd.Sofascore(leagues=canonical, seasons=season_end)
    schedule = reader.read_schedule()
    return _schedule_to_rows(schedule, season_end, "sofascore")


def fetch_espn(league_id: str, season_end: int) -> list[dict]:
    from football_ai.leagues import get_fotmob_league_id

    canonical = get_fotmob_league_id(league_id)
    if not canonical:
        return []
    try:
        import soccerdata as sd
    except ImportError:
        raise RuntimeError("请先安装 soccerdata：pip install soccerdata") from None
    reader = sd.ESPN(leagues=canonical, seasons=season_end)
    schedule = reader.read_schedule()
    return _schedule_to_rows(schedule, season_end, "espn")


def fetch_whoscored(league_id: str, season_end: int) -> list[dict]:
    """WhoScored 使用 Selenium，依赖较重，可能失败。"""
    from football_ai.leagues import get_fotmob_league_id

    canonical = get_fotmob_league_id(league_id)
    if not canonical:
        return []
    try:
        import soccerdata as sd
    except ImportError:
        raise RuntimeError("请先安装 soccerdata：pip install soccerdata") from None
    try:
        reader = sd.WhoScored(leagues=canonical, seasons=season_end)
        schedule = reader.read_schedule()
        return _schedule_to_rows(schedule, season_end, "whoscored")
    except Exception as e:
        raise RuntimeError(f"WhoScored 需 Selenium 且反爬较严，抓取失败: {e}") from e


def main() -> None:
    import argparse
    from football_ai.leagues import get_historical_dir, get_league, get_fotmob_league_id

    parser = argparse.ArgumentParser(description="soccerdata 抓取 Sofascore/ESPN/WhoScored → pl_YYYY_<source>.csv")
    parser.add_argument("--source", type=str, required=True, choices=["sofascore", "espn", "whoscored"])
    parser.add_argument("--league", type=str, default="EPL")
    parser.add_argument("--season", type=int, nargs="*", default=[2025])
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    if not get_fotmob_league_id(league_id):
        print(f"联赛 {league_id} 未配置 fotmob_league_id（soccerdata 联赛 ID），无法使用。", file=sys.stderr)
        sys.exit(1)
    league_cfg = get_league(league_id)
    if not league_cfg:
        sys.exit(1)

    fetchers = {"sofascore": fetch_sofascore, "espn": fetch_espn, "whoscored": fetch_whoscored}
    fetch = fetchers[args.source]
    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for season_end in args.season:
        try:
            rows = fetch(league_id, season_end)
        except RuntimeError as e:
            print(f"抓取失败: {e}", file=sys.stderr)
            continue
        if not rows:
            print(f"未获取到 {args.source} {league_id} {season_end} 场次。", file=sys.stderr)
            continue
        out_path = hist_dir / f"pl_{season_end}_{args.source}.csv"
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"])
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {len(rows)} 场 → {out_path}", file=sys.stderr)
        total += len(rows)
    if total == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
