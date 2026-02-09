#!/usr/bin/env python3
"""
从 ESPN 公开 API 拉取联赛赛程/赛果，输出 pl_YYYY_espn.csv。不依赖 soccerdata（避免 tls_requests）。
仅用标准库 urllib + json，适用于 Sofascore/ESPN 因 TLS 库无法下载时的替代。
"""
import csv
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ESPN_API = "http://site.api.espn.com/apis/site/v2/sports/soccer"
USER_AGENT = "Mozilla/5.0 (compatible; football-ai/1.0)"

# 联赛 id -> ESPN 联赛 slug（与 soccerdata 一致）
LEAGUE_TO_ESPN = {
    "EPL": "eng.1",
    "La_Liga": "esp.1",
    "Serie_A": "ita.1",
    "Bundesliga": "ger.1",
    "Ligue_1": "fra.1",
}


def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_espn_matches(league_id: str, season_end: int) -> list[dict]:
    """拉取指定联赛、赛季的赛程与比分，返回 pl_*.csv 格式（无 xG 填 0）。"""
    slug = LEAGUE_TO_ESPN.get(league_id)
    if not slug:
        return []
    # 2024/25 赛季从 2024-07 左右开始
    start_year = season_end - 1
    start_date = f"{start_year}0701"
    url = f"{ESPN_API}/{slug}/scoreboard?dates={start_date}"
    try:
        data = _get(url)
    except Exception as e:
        raise RuntimeError(f"ESPN API 请求失败: {e}") from e
    leagues = data.get("leagues") or []
    if not leagues:
        return []
    calendar = leagues[0].get("calendar") or []
    out = []
    round_ = 1
    for date_str in calendar:
        if not date_str or len(date_str) < 10:
            continue
        try:
            # "2024-08-17T14:00Z" -> 20240817
            dt = date_str.replace("T", " ").replace("Z", "")[:10].replace("-", "")
        except Exception:
            continue
        day_url = f"{ESPN_API}/{slug}/scoreboard?dates={dt}"
        try:
            day_data = _get(day_url)
        except Exception:
            continue
        events = day_data.get("events") or []
        for ev in events:
            comps = (ev.get("competitions") or [None])[0]
            if not comps:
                continue
            competitors = comps.get("competitors") or []
            if len(competitors) < 2:
                continue
            home = (competitors[0].get("team") or {}).get("name") or ""
            away = (competitors[1].get("team") or {}).get("name") or ""
            if not home or not away:
                continue
            try:
                gh = int(competitors[0].get("score") or 0)
                ga = int(competitors[1].get("score") or 0)
            except (TypeError, ValueError):
                gh = ga = 0
            out.append({
                "season": season_end,
                "round": round_,
                "home_team": home.strip(),
                "away_team": away.strip(),
                "xg_home": 0.0,
                "xg_away": 0.0,
                "goals_home": gh,
                "goals_away": ga,
            })
        if events:
            round_ += 1
    return out


def main() -> None:
    import argparse
    from football_ai.leagues import get_historical_dir, get_league

    parser = argparse.ArgumentParser(description="ESPN 公开 API 拉取赛程（不依赖 soccerdata）→ pl_YYYY_espn.csv")
    parser.add_argument("--league", type=str, default="EPL")
    parser.add_argument("--season", type=int, nargs="*", default=[2025])
    args = parser.parse_args()
    league_id = (args.league or "EPL").strip()
    if league_id not in LEAGUE_TO_ESPN:
        print(f"ESPN 暂不支持联赛 {league_id}，支持: {list(LEAGUE_TO_ESPN.keys())}", file=sys.stderr)
        sys.exit(1)
    league_cfg = get_league(league_id)
    if not league_cfg:
        sys.exit(1)
    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    for season_end in args.season:
        try:
            rows = fetch_espn_matches(league_id, season_end)
        except RuntimeError as e:
            print(f"抓取失败: {e}", file=sys.stderr)
            continue
        if not rows:
            print(f"未获取到 {league_id} {season_end} 场次", file=sys.stderr)
            continue
        out_path = hist_dir / f"pl_{season_end}_espn.csv"
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"])
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {len(rows)} 场 → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
