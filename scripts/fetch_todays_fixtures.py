#!/usr/bin/env python3
"""
自动获取指定日期的五大联赛（英超、西甲、德甲、意甲、法甲）赛程，写入 data/<日期>/todays_matches.csv。
使用 ESPN 公开 API（按日期 scoreboard），仅标准库，无需 API Key。
输出格式与桌面应用 / predict_batch 一致：match_id, league_id, league_zh, home_team, away_team, round, handicap_note, xg_home, xg_away。
"""
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ESPN_API = "http://site.api.espn.com/apis/site/v2/sports/soccer"
USER_AGENT = "Mozilla/5.0 (compatible; football-ai/1.0)"

# 五大联赛 id -> ESPN slug；name_zh 从 leagues 配置读，此处仅作回退
FIVE_LEAGUES = [
    ("EPL", "eng.1", "英超"),
    ("La_Liga", "esp.1", "西甲"),
    ("Bundesliga", "ger.1", "德甲"),
    ("Serie_A", "ita.1", "意甲"),
    ("Ligue_1", "fra.1", "法甲"),
]


def _get_league_name_zh(league_id: str) -> str:
    try:
        from football_ai.leagues import get_league
        cfg = get_league(league_id)
        if cfg and cfg.get("name_zh"):
            return cfg["name_zh"]
    except Exception:
        pass
    for lid, _, zh in FIVE_LEAGUES:
        if lid == league_id:
            return zh
    return ""


def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_fixtures_for_date(league_id: str, slug: str, league_zh: str, day_yyyymmdd: str) -> list[dict]:
    """拉取指定联赛、日期的赛程（主客队名、无 xG/轮次则留空）。"""
    url = f"{ESPN_API}/{slug}/scoreboard?dates={day_yyyymmdd}"
    try:
        data = _get(url)
    except Exception:
        return []
    events = data.get("events") or []
    out = []
    for ev in events:
        comps = (ev.get("competitions") or [None])[0]
        if not comps:
            continue
        competitors = comps.get("competitors") or []
        if len(competitors) < 2:
            continue
        home = (competitors[0].get("team") or {}).get("displayName") or (competitors[0].get("team") or {}).get("name") or ""
        away = (competitors[1].get("team") or {}).get("displayName") or (competitors[1].get("team") or {}).get("name") or ""
        if not home or not away:
            continue
        out.append({
            "league_id": league_id,
            "league_zh": league_zh,
            "home_team": home.strip(),
            "away_team": away.strip(),
        })
    return out


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="获取指定日期五大联赛赛程 → data/<日期>/todays_matches.csv")
    parser.add_argument("--date", type=str, default=None, help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--out", type=Path, default=None, help="输出 CSV 路径，默认 data/<日期>/todays_matches.csv")
    parser.add_argument("--fetch-odds", action="store_true", help="写赛程后自动拉取盘口（需设置 THE_ODDS_API_KEY）")
    args = parser.parse_args()

    if args.date:
        try:
            dt = datetime.strptime(args.date.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            print(f"无效日期: {args.date}，请使用 YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        dt = date.today()
    day_str = dt.strftime("%Y-%m-%d")
    day_yyyymmdd = dt.strftime("%Y%m%d")

    all_rows = []
    for league_id, slug, default_zh in FIVE_LEAGUES:
        league_zh = _get_league_name_zh(league_id) or default_zh
        matches = fetch_fixtures_for_date(league_id, slug, league_zh, day_yyyymmdd)
        for m in matches:
            all_rows.append(m)

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = ROOT / "data" / day_str / "todays_matches.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["match_id", "league_id", "league_zh", "home_team", "away_team", "round", "handicap_note", "xg_home", "xg_away"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, row in enumerate(all_rows, 1):
            w.writerow({
                "match_id": f"{i:03d}",
                "league_id": row["league_id"],
                "league_zh": row["league_zh"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "round": "",
                "handicap_note": "",
                "xg_home": "",
                "xg_away": "",
            })

    print(f"已写入 {len(all_rows)} 场 → {out_path}", file=sys.stderr)

    if args.fetch_odds and all_rows:
        import subprocess
        cmd = [sys.executable, str(ROOT / "scripts" / "fetch_odds.py"), "--csv", str(out_path)]
        try:
            subprocess.run(cmd, cwd=str(ROOT), check=False)
        except Exception as e:
            print(f"拉取盘口失败（请设置 THE_ODDS_API_KEY）: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
