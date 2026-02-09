"""
CLI 入口：生成赛前/赛后报告、指定主客队与轮次等。
"""
import argparse
import sys
from pathlib import Path

from football_ai.report import build_report_inputs, render_report


def _config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "config"


def _load_team_mapping(path: Path | None) -> dict[str, str] | None:
    """从 CSV（statsbomb_name, report_name）加载队名映射。"""
    if path is None or not path.exists():
        return None
    import csv
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = (row.get("statsbomb_name") or row.get("en") or "").strip()
            v = (row.get("report_name") or row.get("zh") or "").strip()
            if k:
                out[k] = v or k
    return out if out else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Football AI · 足球分析报告（第一版：英超、仅中文）")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # 赛前报告
    pre = sub.add_parser("pre", help="生成赛前报告")
    pre.add_argument("--league", default=None, help="联赛 id（见 config/leagues.yaml），默认 EPL/英超）")
    pre.add_argument("--home", default=None, help="主队名（中文）；与 --away、--round 二选一与 --match-code+--fixtures）")
    pre.add_argument("--away", default=None, help="客队名（中文）")
    pre.add_argument("--round", type=int, default=None, dest="round_", help="轮次（如 28）")
    pre.add_argument("--match-code", type=str, default=None, dest="match_code", help="竞彩场次（如 周五012、012），需同时提供 --fixtures，从赛程表解析主客队与轮次")
    pre.add_argument("--events", type=Path, default=None, help="StatsBomb 事件 JSON 路径（可选，第二版）")
    pre.add_argument("--team-mapping", type=Path, default=None, dest="team_mapping", help="队名映射 CSV：statsbomb_name,report_name（可选）")
    pre.add_argument("--injuries", type=Path, default=None, help="伤停数据路径（可选）")
    pre.add_argument("--fixtures", type=Path, default=None, help="赛程元数据路径（可选；与 --match-code 联用可自动解析主客/轮次/时间）")
    pre.add_argument("--referee", type=str, default=None, help="主裁姓名（可选）")
    pre.add_argument("--date", type=str, default=None, help="比赛日期 YYYY-MM-DD（如 2025-03-15）")
    pre.add_argument("--time", type=str, default=None, help="开球时间（如 20:00）")
    pre.add_argument("--xg-home", type=float, default=None, dest="xg_home", help="赛前预期主队 xG（无事件数据时用于推算胜负平/比分概率）")
    pre.add_argument("--xg-away", type=float, default=None, dest="xg_away", help="赛前预期客队 xG")
    pre.add_argument("--expected-xg", type=Path, default=None, dest="expected_xg", help="赛前预期 xG 表 CSV：按场次(round,home_team,away_team,xg_home,xg_away)或按球队(team,xg,xg_home,xg_away)，每场/每队不同")
    pre.add_argument("--expected-xg-season", type=int, default=None, dest="expected_xg_season", help="预期 xG 表按球队时的赛季年（如 2024），可选")
    pre.add_argument("--historical", type=Path, default=None, dest="historical", help="历史场次 CSV 或目录（用于近期状态、历史交锋、Elo，见 data/historical/README.md）")
    pre.add_argument("--season", type=int, default=None, help="赛季年（如 2025），与 --historical 联用时过滤场次；不指定则用历史数据中最大赛季")
    pre.add_argument("--odds", type=Path, default=None, dest="odds_path", help="赔率 CSV（可选，用于模型概率 vs 隐含概率对比，不构成投注建议）")
    pre.add_argument("--odds-home", type=float, default=None, dest="odds_home", help="主胜欧洲赔率（与 --odds-draw/--odds-away 联用）")
    pre.add_argument("--odds-draw", type=float, default=None, dest="odds_draw", help="平局欧洲赔率")
    pre.add_argument("--odds-away", type=float, default=None, dest="odds_away", help="客胜欧洲赔率")
    pre.add_argument("--predictions-demo", action="store_true", dest="predictions_demo", help="展示预测栏占位格式（胜负平/让胜负平/半全场/比分），非真实预测")
    pre.add_argument("--llm", action="store_true", dest="use_llm", help="使用 LLM 润色报告（需 config 中 report.llm.enabled 与 provider，及 API key）")
    pre.add_argument("--version", choices=["full", "summary"], default="full", help="完整版 / 摘要版")
    pre.add_argument("--out", type=Path, default=None, help="输出文件路径（不指定则打印到 stdout）")

    # 赛后报告
    post = sub.add_parser("post", help="生成赛后报告")
    post.add_argument("--league", default=None, help="联赛 id（见 config/leagues.yaml），默认 EPL）")
    post.add_argument("--home", required=True, help="主队名")
    post.add_argument("--away", required=True, help="客队名")
    post.add_argument("--round", type=int, required=True, dest="round_", help="轮次")
    post.add_argument("--events", type=Path, default=None, help="StatsBomb 事件 JSON 路径（建议提供，用于战术指标）")
    post.add_argument("--team-mapping", type=Path, default=None, dest="team_mapping", help="队名映射 CSV（可选）")
    post.add_argument("--fixtures", type=Path, default=None, help="赛程表 CSV/JSON（从中读取本场比赛时间，不依赖 --date/--time）")
    post.add_argument("--injuries", type=Path, default=None, help="伤停数据路径（可选）")
    post.add_argument("--date", type=str, default=None, help="比赛日期 YYYY-MM-DD")
    post.add_argument("--time", type=str, default=None, help="开球时间")
    post.add_argument("--llm", action="store_true", dest="use_llm", help="使用 LLM 润色报告")
    post.add_argument("--historical", type=Path, default=None, dest="historical", help="历史场次 CSV 或目录（用于近期状态、历史交锋）")
    post.add_argument("--season", type=int, default=None, help="赛季年，与 --historical 联用")
    post.add_argument("--version", choices=["full", "summary"], default="full")
    post.add_argument("--out", type=Path, default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    home_team = args.home
    away_team = args.away
    round_ = getattr(args, "round_", None)
    match_date = getattr(args, "date", None)
    match_time = getattr(args, "time", None)
    fixtures_path = getattr(args, "fixtures", None)
    match_code = getattr(args, "match_code", None)

    if match_code and fixtures_path and fixtures_path.exists():
        from football_ai.data.fixtures import load_fixture_meta
        meta = load_fixture_meta(path=fixtures_path, match_code=match_code)
        if meta and meta.get("home") and meta.get("away"):
            home_team = home_team or str(meta.get("home", "")).strip()
            away_team = away_team or str(meta.get("away", "")).strip()
            if meta.get("round") is not None:
                try:
                    round_ = round_ if round_ is not None else int(float(meta["round"]))
                except (TypeError, ValueError):
                    pass
            if meta.get("date"):
                match_date = match_date or str(meta["date"])[:10]
            if meta.get("time"):
                match_time = match_time or str(meta["time"]).strip()[:5]

    if not home_team or not away_team or round_ is None:
        print("错误：请提供 --home、--away、--round，或使用 --match-code 与 --fixtures 从赛程表解析。", file=sys.stderr)
        sys.exit(1)

    derby_rules = _config_dir() / "derby_rules.csv"
    if not derby_rules.exists():
        derby_rules = None

    team_mapping = _load_team_mapping(getattr(args, "team_mapping", None))

    league_id = (getattr(args, "league", None) or "EPL").strip()
    common = dict(
        home_team=home_team,
        away_team=away_team,
        round_=round_,
        events_path=getattr(args, "events", None),
        injuries_path=getattr(args, "injuries", None),
        fixtures_path=fixtures_path,
        derby_rules_path=derby_rules,
        match_date=match_date,
        match_time=match_time,
        predictions_available=getattr(args, "predictions_demo", False),
        team_name_mapping=team_mapping,
        report_type=args.command,
        match_code=match_code,
        league_id=league_id,
        historical_path=getattr(args, "historical", None),
        historical_directory=None,
        season=getattr(args, "season", None),
    )
    if common.get("historical_path"):
        p = Path(common["historical_path"])
        if p.is_dir():
            common["historical_directory"] = p
            common["historical_path"] = None
    else:
        common.pop("historical_path", None)
        common.pop("historical_directory", None)
        common.pop("season", None)
    common["odds_path"] = getattr(args, "odds_path", None)
    common["odds_home"] = getattr(args, "odds_home", None)
    common["odds_draw"] = getattr(args, "odds_draw", None)
    common["odds_away"] = getattr(args, "odds_away", None)
    if args.command == "pre":
        common["expected_xg_home"] = getattr(args, "xg_home", None)
        common["expected_xg_away"] = getattr(args, "xg_away", None)
        common["expected_xg_path"] = getattr(args, "expected_xg", None)
        common["expected_xg_season"] = getattr(args, "expected_xg_season", None)
        inputs = build_report_inputs(
            **common,
            referee_name=getattr(args, "referee", None),
        )
        text = render_report(inputs, report_type="pre", version=args.version, use_llm=getattr(args, "use_llm", False))
    else:
        inputs = build_report_inputs(**common)
        text = render_report(inputs, report_type="post", version=args.version, use_llm=getattr(args, "use_llm", False))

    out_path = getattr(args, "out", None)
    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"已写入 {out_path}")
    else:
        print(text)


if __name__ == "__main__":
    main()
