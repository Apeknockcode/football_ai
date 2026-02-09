#!/usr/bin/env python3
"""
从 Understat 拉取指定联赛、赛季的球队场均 xG（整体及主/客），写入预期 xG 按球队 CSV。
用于填充 data/expected_xg_teams.csv 或 data/expected_xg/<league>_<season>.csv，供赛前报告与预测使用。
数据来源：与 fetch_historical_understat 相同的联赛场次接口，按队聚合主/客 xG 得场均。
仅供个人/教育用途，请遵守 understat.com 使用条款与访问频率。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    import argparse
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fetch_historical_understat",
        ROOT / "scripts" / "fetch_historical_understat.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fetch_league_matches = mod.fetch_league_matches

    parser = argparse.ArgumentParser(description="从 Understat 拉取联赛球队 xG（主/客）写入预期 xG 按球队表")
    parser.add_argument("--league", type=str, default="EPL", help="联赛 id（见 config/leagues.yaml），对应 Understat 代码")
    parser.add_argument("--season", type=int, default=2025, help="赛季结束年，如 2025 表示 2024/25")
    parser.add_argument("--out", type=Path, default=None, help="输出 CSV；不指定则 data/expected_xg/<league>_<season>.csv 或 data/expected_xg_teams.csv")
    parser.add_argument("--html", type=Path, default=None, help="从本地保存的联赛页 HTML 解析（无法直连时用）")
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    try:
        from football_ai.leagues import get_understat_code
        understat_code = get_understat_code(league_id) or league_id
    except Exception:
        understat_code = league_id

    html_content = None
    if args.html and args.html.exists():
        html_content = args.html.read_text(encoding="utf-8", errors="replace")

    matches = fetch_league_matches(league=understat_code, season=args.season, html=html_content)
    if not matches:
        print(f"未获取到 {understat_code} {args.season} 场次数据（可尝试 --html 本地页面）。", file=sys.stderr)
        sys.exit(1)

    # 按队聚合：主队贡献 xg_home，客队贡献 xg_away；统计主/客场次以算场均
    team_home_xg: dict[str, list[float]] = {}
    team_away_xg: dict[str, list[float]] = {}
    for m in matches:
        h = m.get("h") or {}
        a = m.get("a") or {}
        xg = m.get("xG") or {}
        if isinstance(h, dict):
            home_team = (h.get("title") or h.get("short_title") or "").strip()
        else:
            home_team = str(h).strip()
        if isinstance(a, dict):
            away_team = (a.get("title") or a.get("short_title") or "").strip()
        else:
            away_team = str(a).strip()
        xg_h = xg.get("h") if isinstance(xg, dict) else None
        xg_a = xg.get("a") if isinstance(xg, dict) else None
        try:
            xg_home = float(xg_h) if xg_h is not None else 0.0
            xg_away = float(xg_a) if xg_a is not None else 0.0
        except (TypeError, ValueError):
            continue
        if home_team:
            team_home_xg.setdefault(home_team, []).append(xg_home)
        if away_team:
            team_away_xg.setdefault(away_team, []).append(xg_away)

    all_teams = sorted(set(team_home_xg) | set(team_away_xg))
    rows = []
    for team in all_teams:
        home_vals = team_home_xg.get(team) or []
        away_vals = team_away_xg.get(team) or []
        n_home = len(home_vals)
        n_away = len(away_vals)
        avg_home = sum(home_vals) / n_home if n_home else 0.0
        avg_away = sum(away_vals) / n_away if n_away else 0.0
        total_xg = sum(home_vals) + sum(away_vals)
        n = n_home + n_away
        avg_overall = total_xg / n if n else 0.0
        rows.append({
            "team": team,
            "xg": round(avg_overall, 4),
            "xg_home": round(avg_home, 4) if n_home else "",
            "xg_away": round(avg_away, 4) if n_away else "",
            "season": args.season,
        })

    out = args.out
    if out is None:
        out_dir = ROOT / "data" / "expected_xg"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{league_id}_{args.season}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["team", "xg", "xg_home", "xg_away", "season"])
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v == "" else v) for k, v in r.items()})

    print(f"已写入 {len(rows)} 队至 {out}（联赛 {league_id}，赛季 {args.season}）。")


if __name__ == "__main__":
    main()
