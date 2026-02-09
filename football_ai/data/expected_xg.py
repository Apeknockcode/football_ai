"""
赛前预期 xG 数据：从 CSV 按场次或按球队解析，使每场比赛的预期进球数有据可查。
支持两种格式：
  - 按场次：round, home_team, away_team, xg_home, xg_away（每场一行，可从第三方或自建）
  - 按球队：team, xg, xg_home, xg_away（每队一行，如从 Understat 联赛表抄写）
"""
from pathlib import Path
from typing import Any


def load_expected_xg(
    path: str | Path | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    round_: int | None = None,
    season: int | None = None,
    team_name_mapping: dict[str, str] | None = None,
    match_code: str | None = None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """
    从 CSV 解析本场赛前预期 xG（及可选半场 xG）。
    :return: (xg_home, xg_away, xg_ht_home, xg_ht_away)，未匹配到则 (None, None, None, None)；半场列可选
    """
    _none4 = (None, None, None, None)
    if not path:
        return _none4
    if not home_team or not away_team:
        if not match_code:
            return _none4
    path = Path(path)
    if not path.exists():
        # 若用户指定了 expected_xg_teams.csv 等但尚未创建，尝试同目录下的 .example，再尝试 data/test/ 下的示例
        fallback = path.parent / (path.stem + ".example" + path.suffix)
        if fallback.exists():
            path = fallback
        else:
            test_dir = path.parent / "test"
            fallback = test_dir / (path.stem + ".example" + path.suffix)
            if fallback.exists():
                path = fallback
            else:
                return _none4

    import csv
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
    if not rows:
        return _none4

    # 反查：报告名 -> 英文（用于按球队表时 CSV 列为英文）
    report_to_en: dict[str, str] = {}
    if team_name_mapping:
        for en, zh in team_name_mapping.items():
            if zh and zh not in report_to_en:
                report_to_en[zh] = en

    # 1) 按场次表：含 round, home_team, away_team, xg_home, xg_away；可选 match_code
    if all(k in rows[0] for k in ("round", "home_team", "away_team", "xg_home", "xg_away")):
        code_str = (match_code or "").strip()
        def _read_ht(r: dict) -> tuple[float | None, float | None]:
            try:
                h = r.get("xg_ht_home")
                a = r.get("xg_ht_away")
                if h is not None and str(h).strip() and a is not None and str(a).strip():
                    return float(h), float(a)
            except (ValueError, TypeError):
                pass
            return None, None

        if code_str and "match_code" in rows[0]:
            for r in rows:
                if (r.get("match_code") or "").strip() != code_str:
                    continue
                try:
                    xht_h, xht_a = _read_ht(r)
                    return float(r.get("xg_home", 0)), float(r.get("xg_away", 0)), xht_h, xht_a
                except (ValueError, TypeError):
                    continue
        if round_ is not None and home_team and away_team:
            for r in rows:
                try:
                    rnd = int(float(r.get("round", 0)))
                except (ValueError, TypeError):
                    continue
                if rnd != round_:
                    continue
                h = (r.get("home_team") or "").strip()
                a = (r.get("away_team") or "").strip()
                if h != home_team.strip() or a != away_team.strip():
                    continue
                try:
                    xh = float(r.get("xg_home", 0))
                    xa = float(r.get("xg_away", 0))
                    xht_h, xht_a = _read_ht(r)
                    return xh, xa, xht_h, xht_a
                except (ValueError, TypeError):
                    continue
        return _none4

    # 2) 按球队表：含 team, xg（必选），可选 xg_home, xg_away, season
    if "team" in rows[0] and "xg" in rows[0]:
        by_team: dict[str, dict[str, Any]] = {}
        for r in rows:
            team = (r.get("team") or "").strip()
            if not team:
                continue
            if season is not None and "season" in r:
                try:
                    if int(float(r["season"])) != season:
                        continue
                except (ValueError, TypeError):
                    continue
            try:
                xg = float(r.get("xg", 0))
                xg_h = float(r.get("xg_home", r.get("xg", 0))) if r.get("xg_home") else xg
                xg_a = float(r.get("xg_away", r.get("xg", 0))) if r.get("xg_away") else xg
            except (ValueError, TypeError):
                continue
            by_team[team] = {"xg": xg, "xg_home": xg_h, "xg_away": xg_a}

        def get_team_xg(team_name: str, is_home: bool) -> float | None:
            t = team_name.strip()
            row = by_team.get(t)
            if row is None and report_to_en.get(t):
                row = by_team.get(report_to_en[t])
            if row is None:
                return None
            return row["xg_home"] if is_home else row["xg_away"]

        xh = get_team_xg(home_team, True)
        xa = get_team_xg(away_team, False)
        if xh is not None and xa is not None:
            return xh, xa, None, None
        return _none4

    return _none4
