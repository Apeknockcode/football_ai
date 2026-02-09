#!/usr/bin/env python3
"""
从 Football-Data.co.uk 下载联赛 CSV（赛果 + 赔率），转为 pl_YYYY_fd.csv。
无 xG，仅赛果与赔率，可与 Understat 等做赔率/校准对比。仅需 requests。
"""
import csv
import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE_URL = "https://www.football-data.co.uk/mmz4281"


def _urlopen(req: Request, timeout: int = 60):
    """请求 CSV；若环境变量 FD_NO_SSL_VERIFY=1 则跳过 SSL 校验（解决证书/握手超时）。"""
    if __import__("os").environ.get("FD_NO_SSL_VERIFY"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urlopen(req, timeout=timeout, context=ctx)
    return urlopen(req, timeout=timeout)

# 我们联赛 id -> Football-Data.co.uk 联赛代码（仅主联赛有 CSV）
LEAGUE_TO_FD = {
    "EPL": "E0",
    "Championship": "E1",
    "La_Liga": "SP1",
    "Bundesliga": "D1",
    "Serie_A": "I1",
    "Ligue_1": "F1",
}


def _season_to_fd(season_end: int) -> str:
    """2025 -> 2425 (2024/25)."""
    return f"{(season_end - 1) % 100:02d}{season_end % 100:02d}"


def fetch_fd_csv(fd_code: str, season_end: int) -> list[dict]:
    """下载单赛季 CSV，解析为 list[dict]，含 home_team, away_team, goals_home, goals_away, round（按日期推断）。无 xG 填 0。"""
    skey = _season_to_fd(season_end)
    url = f"{BASE_URL}/{skey}/{fd_code}.csv"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; football-ai/1.0)"})
    try:
        with _urlopen(req, timeout=60) as r:
            raw = r.read()
    except Exception as e:
        raise RuntimeError(
            f"下载失败: {url} — {e}\n若为 SSL/超时，可尝试: FD_NO_SSL_VERIFY=1 ./run.sh fetch fd EPL 2025"
        ) from e

    try:
        encoding = "utf-8-sig" if season_end >= 2025 else "latin-1"
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    import csv as csv_module
    reader = csv_module.DictReader(csv_module.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    # 列名可能带空格
    def col(d: dict, *names: str):
        for n in names:
            for k in d:
                if k.strip().lower() == n.strip().lower():
                    return k
        return None

    out = []
    for i, row in enumerate(rows):
        ht_col = col(row, "HomeTeam", "Home")
        at_col = col(row, "AwayTeam", "Away")
        gh_col = col(row, "FTHG", "HG")
        ga_col = col(row, "FTAG", "AG")
        if not ht_col or not at_col:
            continue
        home = (row.get(ht_col) or "").strip()
        away = (row.get(at_col) or "").strip()
        if not home or not away:
            continue
        try:
            goals_home = int(float(row.get(gh_col, 0) or 0))
            goals_away = int(float(row.get(ga_col, 0) or 0))
        except (TypeError, ValueError):
            continue
        # 每轮约 10 场
        round_ = (i // 10) + 1
        out.append({
            "season": season_end,
            "round": round_,
            "home_team": home,
            "away_team": away,
            "xg_home": 0.0,
            "xg_away": 0.0,
            "goals_home": goals_home,
            "goals_away": goals_away,
        })
    return out


def main() -> None:
    import argparse
    from football_ai.leagues import get_historical_dir, get_league

    parser = argparse.ArgumentParser(description="从 Football-Data.co.uk 下载联赛 CSV → pl_YYYY_fd.csv（无 xG，含赛果）")
    parser.add_argument("--league", type=str, default="EPL", help="联赛 id")
    parser.add_argument("--season", type=int, nargs="*", default=[2025], metavar="YEAR", help="赛季结束年")
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    fd_code = LEAGUE_TO_FD.get(league_id)
    if not fd_code:
        print(f"Football-Data.co.uk 暂不支持联赛 {league_id}，支持: {list(LEAGUE_TO_FD.keys())}", file=sys.stderr)
        sys.exit(1)

    league_cfg = get_league(league_id)
    if not league_cfg:
        print(f"未找到联赛配置: {league_id}", file=sys.stderr)
        sys.exit(1)

    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    for season_end in args.season:
        try:
            rows = fetch_fd_csv(fd_code, season_end)
        except RuntimeError as e:
            print(f"抓取失败: {e}", file=sys.stderr)
            continue
        if not rows:
            print(f"未解析到 {league_id} {season_end} 场次", file=sys.stderr)
            continue
        out_path = hist_dir / f"pl_{season_end}_fd.csv"
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"])
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {len(rows)} 场 → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
