#!/usr/bin/env python3
"""
从 The Odds API 拉取五大联赛 1X2 赔率，合并到赛程 CSV（添加 odds_home, odds_draw, odds_away）。
需设置环境变量 THE_ODDS_API_KEY 或 config/odds_api_key.txt（免费注册 https://the-odds-api.com）。
可选：config/odds_team_mapping.csv（api_name, our_name）将 API 队名映射为赛程 CSV 队名，提高匹配率，见 config/odds_team_mapping.example.csv。
用法：
  python scripts/fetch_odds.py --csv data/2026-02-09/todays_matches.csv
  python scripts/fetch_odds.py --date 2026-02-09   # 默认写 data/<日期>/todays_matches.csv
"""
import csv
import os
import re
import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent

# 项目 league_id -> The Odds API sport_key（五大联赛）
LEAGUE_TO_SPORT_KEY = {
    "EPL": "soccer_epl",
    "La_Liga": "soccer_spain_la_liga",
    "Bundesliga": "soccer_germany_bundesliga",
    "Serie_A": "soccer_italy_serie_a",
    "Ligue_1": "soccer_france_ligue_one",
}

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
USER_AGENT = "football-ai/1.0"

# 本地 Key 文件（不提交到 Git），优先于环境变量便于桌面/IDE 启动时使用
ODDS_API_KEY_FILE = ROOT / "config" / "odds_api_key.txt"
# 队名映射：API 返回的队名 → 赛程 CSV 中使用的队名，提高匹配率（见 config/odds_team_mapping.example.csv）
ODDS_TEAM_MAPPING_FILE = ROOT / "config" / "odds_team_mapping.csv"


def _get_odds_api_key() -> str:
    """从环境变量 THE_ODDS_API_KEY 或 config/odds_api_key.txt 读取 Key。"""
    key = (os.environ.get("THE_ODDS_API_KEY") or "").strip()
    if key:
        return key
    if ODDS_API_KEY_FILE.exists():
        try:
            with open(ODDS_API_KEY_FILE, "r", encoding="utf-8") as f:
                key = (f.read() or "").strip()
            if key:
                return key
        except Exception:
            pass
    return ""


def _norm(s: str) -> str:
    """归一化队名便于匹配：小写、去多余空格。"""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", str(s).strip().lower())
    return s


def _load_odds_team_mapping() -> dict[str, str]:
    """加载 config/odds_team_mapping.csv：api_name -> our_name，键为归一化的 API 队名。"""
    out: dict[str, str] = {}
    if not ODDS_TEAM_MAPPING_FILE.exists():
        return out
    try:
        with open(ODDS_TEAM_MAPPING_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                api = (row.get("api_name") or row.get("api") or "").strip()
                our = (row.get("our_name") or row.get("our") or row.get("csv_name") or "").strip()
                if api:
                    out[_norm(api)] = our or api
    except Exception:
        pass
    return out


def _ssl_context():
    """使用 certifi 证书库，避免 macOS 等环境 SSL 验证失败。"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def _get_odds_api(sport_key: str, api_key: str, team_mapping: dict[str, str] | None = None) -> list[dict]:
    """拉取某联赛的 1X2 赔率（h2h）。返回 list[dict] 每场含 home_team, away_team, odds_home, odds_draw, odds_away。若提供 team_mapping（norm(api_name)->our_name），则用 our_name 便于与赛程 CSV 匹配。"""
    # regions=eu 常用；markets: h2h 足球含平局，h2h_3_way 明确三项
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds?regions=eu&markets=h2h&oddsFormat=decimal&apiKey={api_key}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    ctx = _ssl_context()
    try:
        with urlopen(req, timeout=20, context=ctx) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"拉取 {sport_key} 赔率失败: {e}\n")
        return []

    try:
        import json
        events = json.loads(data)
    except Exception as e:
        sys.stderr.write(f"解析 {sport_key} 响应失败: {e}\n")
        return []

    out = []
    for ev in events:
        home_team = (ev.get("home_team") or "").strip()
        away_team = (ev.get("away_team") or "").strip()
        if not home_team or not away_team:
            continue
        odds_home = odds_draw = odds_away = None
        bookmakers = ev.get("bookmakers") or []
        for bm in bookmakers:
            for m in bm.get("markets") or []:
                if m.get("key") not in ("h2h_3_way", "h2h"):
                    continue
                for o in m.get("outcomes") or []:
                    name = (o.get("name") or "").strip()
                    price = o.get("price")
                    if price is None:
                        continue
                    try:
                        price = float(price)
                    except (TypeError, ValueError):
                        continue
                    n = _norm(name)
                    if n == "draw":
                        odds_draw = price
                    elif n == _norm(home_team) or n == "home":
                        odds_home = price
                    elif n == _norm(away_team) or n == "away":
                        odds_away = price
                if odds_home is not None and odds_draw is not None and odds_away is not None:
                    break
            if odds_home is not None and odds_draw is not None and odds_away is not None:
                break
        if odds_home is not None and odds_draw is not None and odds_away is not None:
            # 用映射表把 API 队名换成赛程 CSV 用的队名，提高匹配率
            m = team_mapping or {}
            out_home = m.get(_norm(home_team), home_team)
            out_away = m.get(_norm(away_team), away_team)
            out.append({
                "home_team": out_home,
                "away_team": out_away,
                "odds_home": odds_home,
                "odds_draw": odds_draw,
                "odds_away": odds_away,
            })
    return out


def _match_row_to_odds(row: dict, odds_list: list[dict]) -> tuple[float | None, float | None, float | None]:
    """根据主客队名在 odds_list 中找匹配，返回 (odds_home, odds_draw, odds_away)。"""
    home = _norm(row.get("home_team") or row.get("home") or "")
    away = _norm(row.get("away_team") or row.get("away") or "")
    if not home or not away:
        return None, None, None
    for o in odds_list:
        if _norm(o["home_team"]) == home and _norm(o["away_team"]) == away:
            return o["odds_home"], o["odds_draw"], o["odds_away"]
    return None, None, None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="从 The Odds API 拉取 1X2 赔率并合并到赛程 CSV")
    parser.add_argument("--csv", type=Path, default=None, help="赛程 CSV 路径（含 match_id, league_id, home_team, away_team 等）")
    parser.add_argument("--date", type=str, default=None, help="日期 YYYY-MM-DD，与 --csv 二选一；指定则用 data/<日期>/todays_matches.csv")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将写入的赔率，不修改 CSV")
    args = parser.parse_args()

    api_key = _get_odds_api_key()
    if not api_key:
        sys.stderr.write(
            "未设置 THE_ODDS_API_KEY。请任选其一：\n"
            "  1) 环境变量：export THE_ODDS_API_KEY=你的key\n"
            "  2) 本地文件：在 config/odds_api_key.txt 中写一行 Key（见 config/odds_api_key.example.txt）\n"
            "注册获取免费 Key：https://the-odds-api.com\n"
        )
        sys.exit(1)

    if args.csv is not None:
        csv_path = Path(args.csv)
    elif args.date:
        try:
            from datetime import datetime
            datetime.strptime(args.date.strip()[:10], "%Y-%m-%d")
        except ValueError:
            sys.stderr.write(f"无效日期: {args.date}\n")
            sys.exit(1)
        csv_path = ROOT / "data" / args.date.strip()[:10] / "todays_matches.csv"
    else:
        from datetime import date
        csv_path = ROOT / "data" / date.today().isoformat() / "todays_matches.csv"

    if not csv_path.exists():
        sys.stderr.write(f"赛程文件不存在: {csv_path}\n")
        sys.exit(1)

    # 可选队名映射：API 队名 -> 赛程 CSV 队名，提高匹配率
    team_mapping = _load_odds_team_mapping()
    if team_mapping:
        sys.stderr.write(f"已加载队名映射 {len(team_mapping)} 条（config/odds_team_mapping.csv）\n")

    # 按联赛拉取赔率
    league_odds: dict[str, list[dict]] = {}
    for league_id, sport_key in LEAGUE_TO_SPORT_KEY.items():
        league_odds[league_id] = _get_odds_api(sport_key, api_key, team_mapping)
        if league_odds[league_id]:
            sys.stderr.write(f"已拉取 {league_id} 共 {len(league_odds[league_id])} 场赔率\n")

    # 读赛程
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            rows.append({k.strip(): v for k, v in r.items() if k})

    # 确保有赔率列
    for col in ("odds_home", "odds_draw", "odds_away"):
        if col not in fieldnames:
            fieldnames.append(col)

    # 为每行匹配赔率
    updated = 0
    for r in rows:
        league_id = (r.get("league_id") or "").strip()
        odds_list = league_odds.get(league_id) or []
        oh, od, oa = _match_row_to_odds(r, odds_list)
        if oh is not None and od is not None and oa is not None:
            r["odds_home"] = f"{oh:.2f}"
            r["odds_draw"] = f"{od:.2f}"
            r["odds_away"] = f"{oa:.2f}"
            updated += 1
        else:
            r["odds_home"] = r.get("odds_home", "")
            r["odds_draw"] = r.get("odds_draw", "")
            r["odds_away"] = r.get("odds_away", "")

    if args.dry_run:
        for r in rows:
            if r.get("odds_home"):
                print(f"  {r.get('home_team')} vs {r.get('away_team')}  {r.get('odds_home')} / {r.get('odds_draw')} / {r.get('odds_away')}")
        print(f"共匹配 {updated}/{len(rows)} 场（dry-run，未写入）")
        return

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"已合并赔率到 {csv_path}，匹配 {updated}/{len(rows)} 场。")


if __name__ == "__main__":
    main()
