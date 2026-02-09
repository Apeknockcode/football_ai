#!/usr/bin/env python3
"""
从 Sofascore 公开 API 拉取联赛赛程/赛果，输出 pl_YYYY_sofascore.csv。不依赖 soccerdata（避免 tls_requests）。
仅用标准库 urllib + json。若 API 限流或需 TLS，可改用 soccerdata 或手动下载。
"""
import csv
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOFASCORE_API = "https://api.sofascore.com/api/v1"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 联赛 id -> Sofascore 联赛名称（与 soccerdata 一致，用于从 config API 匹配）
LEAGUE_TO_SOFASCORE_NAME = {
    "EPL": "Premier League",
    "La_Liga": "LaLiga",
    "Serie_A": "Serie A",
    "Bundesliga": "Bundesliga",
    "Ligue_1": "Ligue 1",
}


def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_sofascore_matches(league_id: str, season_end: int) -> list[dict]:
    """拉取指定联赛、赛季的赛程与比分（无 xG 填 0）。"""
    name = LEAGUE_TO_SOFASCORE_NAME.get(league_id)
    if not name:
        return []
    try:
        config = _get(f"{SOFASCORE_API}/config/default-unique-tournaments/EN/football")
    except Exception as e:
        raise RuntimeError(f"Sofascore config 请求失败: {e}") from e
    tours = config.get("uniqueTournaments") or []
    tid = None
    for t in tours:
        if (t.get("name") or "").strip() == name:
            tid = t.get("id")
            break
    if tid is None:
        raise RuntimeError(f"未找到 Sofascore 联赛: {name}")
    try:
        seasons_data = _get(f"{SOFASCORE_API}/unique-tournament/{tid}/seasons")
    except Exception as e:
        raise RuntimeError(f"Sofascore seasons 请求失败: {e}") from e
    seasons_list = seasons_data.get("seasons") or []
    # 选赛季：2024/25 -> year 如 "2024" 或 "2425"
    sid = None
    for s in seasons_list:
        yr = str(s.get("year") or "")
        if yr == str(season_end - 1) or yr == str(season_end) or yr == f"{(season_end-1)%100:02d}{season_end%100:02d}":
            sid = s.get("id")
            break
    if not seasons_list:
        raise RuntimeError(f"无赛季数据: {tid}")
    if sid is None:
        sid = seasons_list[0].get("id")
    try:
        rounds_data = _get(f"{SOFASCORE_API}/unique-tournament/{tid}/season/{sid}/rounds")
    except Exception as e:
        raise RuntimeError(f"Sofascore rounds 请求失败: {e}") from e
    rounds_list = rounds_data.get("rounds") or []
    out = []
    for rnd in rounds_list:
        round_num = rnd.get("round") or len(out) // 10 + 1
        try:
            events_data = _get(f"{SOFASCORE_API}/unique-tournament/{tid}/season/{sid}/events/round/{round_num}")
        except Exception:
            continue
        events = events_data.get("events") or []
        for ev in events:
            status = (ev.get("status") or {}).get("code")
            if status == 100:
                home_score = int((ev.get("homeScore") or {}).get("current") or 0)
                away_score = int((ev.get("awayScore") or {}).get("current") or 0)
            else:
                home_score = away_score = 0
            home_team = (ev.get("homeTeam") or {}).get("name") or ""
            away_team = (ev.get("awayTeam") or {}).get("name") or ""
            if not home_team or not away_team:
                continue
            out.append({
                "season": season_end,
                "round": round_num,
                "home_team": home_team.strip(),
                "away_team": away_team.strip(),
                "xg_home": 0.0,
                "xg_away": 0.0,
                "goals_home": home_score,
                "goals_away": away_score,
            })
    return out


def main() -> None:
    import argparse
    from football_ai.leagues import get_historical_dir, get_league

    parser = argparse.ArgumentParser(description="Sofascore API 拉取赛程（不依赖 soccerdata）→ pl_YYYY_sofascore.csv")
    parser.add_argument("--league", type=str, default="EPL")
    parser.add_argument("--season", type=int, nargs="*", default=[2025])
    args = parser.parse_args()
    league_id = (args.league or "EPL").strip()
    if league_id not in LEAGUE_TO_SOFASCORE_NAME:
        print(f"Sofascore 暂不支持联赛 {league_id}，支持: {list(LEAGUE_TO_SOFASCORE_NAME.keys())}", file=sys.stderr)
        sys.exit(1)
    league_cfg = get_league(league_id)
    if not league_cfg:
        sys.exit(1)
    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    for season_end in args.season:
        try:
            rows = fetch_sofascore_matches(league_id, season_end)
        except RuntimeError as e:
            print(f"抓取失败: {e}", file=sys.stderr)
            continue
        if not rows:
            print(f"未获取到 {league_id} {season_end} 场次", file=sys.stderr)
            continue
        out_path = hist_dir / f"pl_{season_end}_sofascore.csv"
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"])
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {len(rows)} 场 → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
