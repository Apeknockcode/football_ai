#!/usr/bin/env python3
"""
校验历史数据质量。

1) 默认：扫描各联赛目录，统计无效场次（0-0 且 xG 全 0）。
2) --merged-2024：对合并后的 2024 年数据做自动化核对，确保场次数、无重复、轮次与比分范围合理。
   可选 --ref <参考CSV> 与权威样本逐条 diff 比分。

参见：docs/历史数据-2024合并数据核对流程.md
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIST_DIR = ROOT / "data" / "historical"
COMBINED_DIR = HIST_DIR / "Combined"

# 五大联赛完整赛季预期场次（20 队×38 轮=380，18 队×34 轮=306），允许小幅偏差（补赛等）
EXPECTED_FULL = {
    "EPL": (376, 384),
    "La_Liga": (376, 384),
    "Bundesliga": (302, 312),
    "Serie_A": (376, 384),
    "Ligue_1": (302, 312),
}
# 进行中赛季（如 2026）：场次可为 0 到完整赛季上限
EXPECTED_PARTIAL = {
    "EPL": (0, 384),
    "La_Liga": (0, 384),
    "Bundesliga": (0, 312),
    "Serie_A": (0, 384),
    "Ligue_1": (0, 312),
}
EXPECTED_2024 = EXPECTED_FULL  # 兼容旧引用
ROUND_RANGE_20 = (1, 38)
ROUND_RANGE_18 = (1, 34)
LEAGUE_18 = {"Bundesliga", "Ligue_1"}
GOALS_MAX = 15
XG_MAX = 10.0


def _load_combined(season: int) -> list[dict]:
    """加载 Combined/pl_YYYY.csv，返回 list[dict]。"""
    path = COMBINED_DIR / f"pl_{season}.csv"
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            try:
                r["season"] = int(r.get("season", 0))
                r["round"] = int(r.get("round", 0))
                r["xg_home"] = float(r.get("xg_home", 0))
                r["xg_away"] = float(r.get("xg_away", 0))
                r["goals_home"] = int(float(r.get("goals_home", 0)))
                r["goals_away"] = int(float(r.get("goals_away", 0)))
            except (ValueError, TypeError):
                continue
            out.append(r)
    return out


def _check_counts(matches: list[dict], expected: dict | None = None) -> list[str]:
    """按联赛统计场次，是否在预期范围内。expected 默认 EXPECTED_FULL，进行中赛季传 EXPECTED_PARTIAL。"""
    from collections import Counter
    exp = expected or EXPECTED_FULL
    errors = []
    cnt = Counter(m.get("league") for m in matches if m.get("league"))
    for league, (lo, hi) in exp.items():
        n = cnt.get(league, 0)
        if n < lo or n > hi:
            errors.append(f"  {league}: 场次 {n}，预期范围 [{lo}, {hi}]")
    return errors


def _check_duplicates(matches: list[dict]) -> list[str]:
    """检查 (league, season, round, home_team, away_team) 是否重复。"""
    seen = set()
    dupes = []
    for m in matches:
        key = (m.get("league"), m.get("season"), m.get("round"),
               m.get("home_team"), m.get("away_team"))
        if key in seen:
            dupes.append(f"  {m.get('league')} round {m.get('round')} {m.get('home_team')} vs {m.get('away_team')}")
        seen.add(key)
    return dupes


def _check_round_ranges(matches: list[dict]) -> list[str]:
    """检查 round 是否在合理区间。"""
    errors = []
    for m in matches:
        league = m.get("league", "")
        r = m.get("round", 0)
        lo, hi = ROUND_RANGE_18 if league in LEAGUE_18 else ROUND_RANGE_20
        if r < lo or r > hi:
            errors.append(f"  {league} round={r} {m.get('home_team')} vs {m.get('away_team')}（预期 [{lo},{hi}]）")
    return errors


def _check_goals_xg_range(matches: list[dict]) -> list[str]:
    """检查比分与 xG 是否在合理范围。"""
    errors = []
    for m in matches:
        gh, ga = m.get("goals_home", 0), m.get("goals_away", 0)
        xh, xa = m.get("xg_home", 0), m.get("xg_away", 0)
        if gh < 0 or ga < 0 or gh > GOALS_MAX or ga > GOALS_MAX:
            errors.append(f"  {m.get('league')} 比分异常: {m.get('home_team')} {gh}-{ga} {m.get('away_team')}")
        if xh < 0 or xa < 0 or xh > XG_MAX or xa > XG_MAX:
            errors.append(f"  {m.get('league')} xG 异常: {m.get('home_team')} {xh}-{xa} {m.get('away_team')}")
    return errors


def _check_ref_diff(matches: list[dict], ref_path: Path) -> list[str]:
    """与参考 CSV 比对：参考列 league, home_team, away_team, goals_home, goals_away。"""
    errors = []
    key_to_ref = {}
    with open(ref_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            league = row.get("league", "").strip()
            home = row.get("home_team", "").strip()
            away = row.get("away_team", "").strip()
            try:
                gh = int(float(row.get("goals_home", 0)))
                ga = int(float(row.get("goals_away", 0)))
            except (ValueError, TypeError):
                continue
            key_to_ref[(league, home, away)] = (gh, ga)
    key_to_ours = {(m.get("league"), m.get("home_team"), m.get("away_team")): (m.get("goals_home"), m.get("goals_away")) for m in matches}
    for key, (gh_ref, ga_ref) in key_to_ref.items():
        our = key_to_ours.get(key)
        if our is None:
            errors.append(f"  参考中有但数据中缺失: {key[0]} {key[1]} vs {key[2]} ({gh_ref}-{ga_ref})")
            continue
        gh_our, ga_our = our
        if (gh_our, ga_our) != (gh_ref, ga_ref):
            errors.append(f"  比分会差: {key[0]} {key[1]} vs {key[2]} 数据={gh_our}-{ga_our} 参考={gh_ref}-{ga_ref}")
    return errors


def run_merged_checks(season: int, ref_path: Path | None = None) -> bool:
    """执行指定赛季合并数据核对，返回是否全部通过。"""
    matches = _load_combined(season)
    if not matches:
        print(f"未找到 data/historical/Combined/pl_{season}.csv，请先运行 ./run.sh merge-five。", file=sys.stderr)
        return False

    print(f"{season} 合并数据 · 自动化核对")
    print("-" * 50)
    all_ok = True

    # 1) 场次数（进行中赛季如 2026 用较宽范围）
    expected_counts = EXPECTED_PARTIAL if season >= 2026 else EXPECTED_FULL
    errs = _check_counts(matches, expected_counts)
    if errs:
        print("[失败] 场次数量不在预期范围:")
        for e in errs:
            print(e)
        all_ok = False
    else:
        from collections import Counter
        cnt = Counter(m.get("league") for m in matches if m.get("league"))
        print("[通过] 场次数量: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))

    # 2) 重复场次
    dupes = _check_duplicates(matches)
    if dupes:
        print("[失败] 重复场次 (前 10 条):")
        for d in dupes[:10]:
            print(d)
        if len(dupes) > 10:
            print(f"  ... 共 {len(dupes)} 条")
        all_ok = False
    else:
        print("[通过] 无重复场次")

    # 3) 轮次范围
    errs = _check_round_ranges(matches)
    if errs:
        print("[失败] 轮次超出合理范围 (前 10 条):")
        for e in errs[:10]:
            print(e)
        if len(errs) > 10:
            print(f"  ... 共 {len(errs)} 条")
        all_ok = False
    else:
        print("[通过] 轮次均在 1–38（20 队）或 1–34（18 队）")

    # 4) 比分与 xG 范围
    errs = _check_goals_xg_range(matches)
    if errs:
        print("[失败] 比分或 xG 异常 (前 10 条):")
        for e in errs[:10]:
            print(e)
        if len(errs) > 10:
            print(f"  ... 共 {len(errs)} 条")
        all_ok = False
    else:
        print("[通过] 比分与 xG 在合理范围内")

    # 5) 可选：参考 diff
    if ref_path and ref_path.exists():
        errs = _check_ref_diff(matches, ref_path)
        if errs:
            print("[失败] 与参考 CSV 比分会差 (前 15 条):")
            for e in errs[:15]:
                print(e)
            if len(errs) > 15:
                print(f"  ... 共 {len(errs)} 条")
            all_ok = False
        else:
            print("[通过] 与参考 CSV 比对一致")
    elif ref_path:
        print("[跳过] 未找到参考文件: " + str(ref_path))

    print("-" * 50)
    print("结果: " + ("全部通过" if all_ok else "存在异常，请修正后重跑"))
    return all_ok


def run_invalid_scan() -> None:
    """原有逻辑：扫描各目录统计无效场次。"""
    dirs = sorted(d for d in HIST_DIR.iterdir() if d.is_dir() and not d.name.startswith("_"))
    if not dirs:
        print("未找到历史数据目录。", file=sys.stderr)
        sys.exit(1)

    total_rows = 0
    invalid_rows = 0
    zero_zero_real = 0

    for d in dirs:
        csvs = sorted(d.glob("*.csv"))
        for fp in csvs:
            with open(fp, encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    try:
                        gh = int(float(row.get("goals_home", 0)))
                        ga = int(float(row.get("goals_away", 0)))
                        xgh = float(row.get("xg_home", 0))
                        xga = float(row.get("xg_away", 0))
                    except (ValueError, TypeError):
                        continue
                    total_rows += 1
                    if gh == 0 and ga == 0 and xgh == 0 and xga == 0:
                        invalid_rows += 1
                    elif gh == 0 and ga == 0 and (xgh > 0 or xga > 0):
                        zero_zero_real += 1

    print("历史数据质量校验")
    print("-" * 40)
    print(f"总行数: {total_rows}")
    print(f"无效场次 (0-0 且 xG 全 0，已自动排除): {invalid_rows}")
    print(f"真实 0-0 (有 xG 数据): {zero_zero_real}")
    if total_rows > 0:
        pct = 100 * invalid_rows / total_rows
        print(f"无效占比: {pct:.1f}%")
        if pct > 10:
            print()
            print("⚠ 无效场次较多，多为未开赛或缺数据的赛程（如未来轮次、抓取不全等）。")
            print("  load_historical_matches 已自动过滤，校准/回测不受影响。")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="校验历史数据质量。默认统计无效场次；--2024 对合并的 2024 数据做完整核对。"
    )
    parser.add_argument(
        "--merged-2024",
        dest="merged_season",
        action="store_const",
        const=2024,
        help="对 Combined/pl_2024.csv 做场次/重复/轮次/比分核对",
    )
    parser.add_argument(
        "--merged-2025",
        dest="merged_season",
        action="store_const",
        const=2025,
        help="对 Combined/pl_2025.csv 做场次/重复/轮次/比分核对",
    )
    parser.add_argument(
        "--merged-2026",
        dest="merged_season",
        action="store_const",
        const=2026,
        help="对 Combined/pl_2026.csv 做场次/重复/轮次/比分核对（进行中赛季，场次范围放宽）",
    )
    default_ref_2024 = ROOT / "data" / "historical" / "_common" / "validation_ref_2024_sample.csv"
    default_ref_2025 = ROOT / "data" / "historical" / "_common" / "validation_ref_2025_sample.csv"
    default_ref_2026 = ROOT / "data" / "historical" / "_common" / "validation_ref_2026_sample.csv"
    parser.add_argument(
        "--ref",
        type=Path,
        nargs="?",
        const=default_ref_2024,
        default=None,
        metavar="PATH",
        help="参考 CSV 与合并数据 diff；不写路径时 2024 用 validation_ref_2024_sample.csv，2025 用 validation_ref_2025_sample.csv",
    )
    args = parser.parse_args()
    # 按赛季选用专用参考文件，避免跨赛季误用
    if args.merged_season == 2025 and args.ref is not None and args.ref == default_ref_2024:
        args.ref = default_ref_2025
    elif args.merged_season == 2026 and args.ref is not None and args.ref == default_ref_2024:
        args.ref = default_ref_2026

    if args.merged_season is not None:
        ok = run_merged_checks(args.merged_season, args.ref)
        sys.exit(0 if ok else 1)
    run_invalid_scan()


if __name__ == "__main__":
    main()
