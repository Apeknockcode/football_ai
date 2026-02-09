"""
报告组装：从各模块收集输出，填入模板，可选 LLM 润色。
"""
from pathlib import Path
from typing import Any

from football_ai.report.template import fill_pre_match_template, fill_post_match_template


def build_report_inputs(
    home_team: str,
    away_team: str,
    round_: int,
    events_path: str | Path | None = None,
    injuries_path: str | Path | None = None,
    fixtures_path: str | Path | None = None,
    derby_rules_path: str | Path | None = None,
    referee_name: str | None = None,
    referee_stats: dict[str, Any] | None = None,
    match_date: str | None = None,
    match_time: str | None = None,
    predictions_available: bool = False,
    team_name_mapping: dict[str, str] | None = None,
    events_provider: str = "statsbomb",
    report_type: str = "pre",
    expected_xg_home: float | None = None,
    expected_xg_away: float | None = None,
    expected_xg_path: str | Path | None = None,
    expected_xg_season: int | None = None,
    match_code: str | None = None,
    league_id: str | None = None,
    historical_path: str | Path | None = None,
    historical_directory: str | Path | None = None,
    season: int | None = None,
    odds_path: str | Path | None = None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> dict[str, Any]:
    """
    调用战术、伤停、政治各模块，汇总为报告所需的结构化输入。
    :return: {"competition": {...}, "injury": {...}, "tactics_summary": "...", ...}
    """
    from football_ai.data import load_events, load_fixture_meta, load_injuries
    from football_ai.data.events import normalize_events_for_tactics
    from football_ai.tactics import compute_metrics, infer_formation, build_tactics_summary
    from football_ai.injuries import get_injury_report
    from football_ai.politics import (
        get_competition_context,
        get_discipline_referee,
        get_narrative,
        get_club_manager_context,
    )

    events_df = load_events(path=events_path, provider=events_provider)
    events_norm = (
        normalize_events_for_tactics(events_df, provider=events_provider, team_name_mapping=team_name_mapping)
        if not events_df.empty else events_df
    )
    metrics = compute_metrics(events_norm)
    formation = infer_formation(
        events=events_norm,
        home_team=home_team,
        away_team=away_team,
    )
    tactics_summary = build_tactics_summary(
        metrics, formation, home_team, away_team,
        report_type=report_type,
    )

    injury = get_injury_report(path=injuries_path, home_team=home_team, away_team=away_team)
    # 比赛时间从赛程/比赛数据中读取，不依赖用户输入的 --date/--time
    if fixtures_path and Path(fixtures_path).exists():
        fixture_meta = load_fixture_meta(
            path=fixtures_path,
            round_=round_,
            home_team=home_team,
            away_team=away_team,
        )
        if isinstance(fixture_meta, dict) and not fixture_meta.get("fixtures"):
            if fixture_meta.get("date"):
                match_date = str(fixture_meta["date"])[:10]
            if fixture_meta.get("time"):
                match_time = str(fixture_meta["time"]).strip()[:5]
    competition = get_competition_context(
        home_team, away_team, round_,
        derby_rules_path=derby_rules_path,
        match_date=match_date,
        match_time=match_time,
        league_id=league_id,
    )
    discipline_referee = get_discipline_referee(referee_name=referee_name, referee_stats=referee_stats)
    narrative = get_narrative(home_team, away_team, round_)
    club_manager = get_club_manager_context(home_team, away_team)

    from football_ai.data import load_expected_xg
    from football_ai.predictions import get_predictions, adjust_xg_for_injuries
    # 有事件数据时用本场 xG；无事件时用 --xg-home/--xg-away 或从 expected_xg 表解析
    has_events = events_df is not None and not events_df.empty
    xg_h, xg_a = expected_xg_home, expected_xg_away
    xg_ht_h, xg_ht_a = None, None
    if (xg_h is None or xg_a is None) and expected_xg_path:
        xg_h, xg_a, xg_ht_h, xg_ht_a = load_expected_xg(
            path=expected_xg_path,
            home_team=home_team,
            away_team=away_team,
            round_=round_,
            season=expected_xg_season,
            team_name_mapping=team_name_mapping,
            match_code=match_code,
        )
    use_expected_xg = not has_events and xg_h is not None and xg_a is not None
    if use_expected_xg:
        # 有伤停时对预期 xG 做小幅下调，使加伤停与不加伤停时预测有区别
        if injury.get("home") or injury.get("away"):
            xg_h, xg_a = adjust_xg_for_injuries(xg_h, xg_a, injury.get("home") or [], injury.get("away") or [])
        metrics_out = {"xg": {"home": xg_h, "away": xg_a}}
        if xg_ht_h is not None and xg_ht_a is not None:
            metrics_out["xg_ht"] = {"home": xg_ht_h, "away": xg_ht_a}
        predictions = get_predictions(
            home_team, away_team, round_,
            metrics=metrics_out,
            available=True,
            expected_xg=True,
            league_id=league_id,
        )
    else:
        predictions = get_predictions(
            home_team, away_team, round_,
            metrics=metrics,
            available=predictions_available or has_events,
            league_id=league_id,
        )

    form_home = form_away = h2h = None
    team_stats_home = team_stats_away = None
    elo_block = None
    if historical_path or historical_directory:
        from football_ai.data.historical import load_historical_matches
        from football_ai.data.form import get_team_form
        from football_ai.data.h2h import get_h2h
        from football_ai.data.team_stats import get_team_season_stats
        if historical_path:
            hist_matches = load_historical_matches(path=historical_path)
        else:
            hist_matches = load_historical_matches(directory=historical_directory)
        if hist_matches:
            if any((m.get("league") or "").strip() for m in hist_matches):
                lid = (league_id or "").strip()
                if lid:
                    hist_matches = [m for m in hist_matches if (m.get("league") or "").strip() == lid]
            if season is not None:
                hist_matches = [m for m in hist_matches if int(m.get("season", 0)) == season]
            use_season = season if season is not None else max((int(m.get("season", 0)) for m in hist_matches), default=0)
            if hist_matches and use_season:
                form_home = get_team_form(home_team, hist_matches, use_season, round_before=round_, n_matches=5)
                form_away = get_team_form(away_team, hist_matches, use_season, round_before=round_, n_matches=5)
                h2h = get_h2h(home_team, away_team, hist_matches, last_n=10)
                team_stats_home = get_team_season_stats(home_team, hist_matches, use_season, round_before=round_)
                team_stats_away = get_team_season_stats(away_team, hist_matches, use_season, round_before=round_)
                from football_ai.data.elo import get_elo_for_report
                elo_block = get_elo_for_report(home_team, away_team, hist_matches, use_season, round_)

    result = {
        "competition": competition,
        "injury": injury,
        "discipline_referee": discipline_referee,
        "tactics_summary": tactics_summary,
        "metrics": metrics,
        "formation": formation,
        "narrative": narrative,
        "club_manager": club_manager,
        "predictions": predictions,
        "key_events": [],  # 占位：从 events 中抽取关键事件
        "form_home": form_home,
        "form_away": form_away,
        "h2h": h2h,
        "team_stats_home": team_stats_home,
        "team_stats_away": team_stats_away,
        "elo": elo_block,
        "odds_comparison": None,
    }
    if predictions and (odds_path or (odds_home is not None and odds_draw is not None and odds_away is not None)):
        from football_ai.data.odds import get_odds_comparison, load_odds_for_match
        oh, od, oa = odds_home, odds_draw, odds_away
        if odds_path and Path(odds_path).exists():
            oh, od, oa = load_odds_for_match(odds_path, home_team, away_team, round_, match_code)
        if oh is not None and od is not None and oa is not None:
            result["odds_comparison"] = get_odds_comparison(
                predictions.get("win_draw_lose"), odds_home=oh, odds_draw=od, odds_away=oa,
            )

    # 模型核心依据：说明预测结果基于哪些数据，便于与主流观点对比
    xg_used: tuple[float | None, float | None] = (None, None)
    if use_expected_xg:
        xg_used = (xg_h, xg_a)
    elif metrics and isinstance(metrics.get("xg"), dict):
        xg_used = (metrics["xg"].get("home"), metrics["xg"].get("away"))
    basis_lines = [
        "本模型基于以下数据经 Poisson 模型推算胜负平/让球/比分概率，仅供参考、不构成投注建议：",
    ]
    if xg_used[0] is not None and xg_used[1] is not None:
        basis_lines.append("① 赛前预期 xG：主 %.2f – 客 %.2f" % (xg_used[0], xg_used[1]))
    else:
        basis_lines.append("① 赛前预期 xG：未提供本场数据时使用默认或预期 xG 表匹配。")
    if form_home or form_away or h2h:
        basis_lines.append("② 近期状态与历史交锋：见上文【近期状态与交锋】。")
    if team_stats_home or team_stats_away:
        basis_lines.append("③ 积分与预期积分(xPts)：见上文【积分与预期】。")
    if elo_block:
        basis_lines.append("④ Elo 参考：见上文【Elo 参考】。")
    if result.get("odds_comparison"):
        basis_lines.append("⑤ 与主流市场赔率隐含概率对比：见下文【概率对比】。")
    result["prediction_basis"] = "\n".join(basis_lines)
    return result


def render_report(
    inputs: dict[str, Any],
    report_type: str = "pre",
    version: str = "full",
    use_llm: bool = False,
) -> str:
    """
    将 build_report_inputs 的输出渲染为最终中文报告。
    :param report_type: pre | post
    :param version: full | summary
    :param use_llm: 是否调用 LLM 润色（需配置 report.llm）
    """
    if report_type == "pre":
        text = fill_pre_match_template(
            competition=inputs["competition"],
            injury=inputs["injury"],
            discipline_referee=inputs["discipline_referee"],
            tactics_summary=inputs["tactics_summary"],
            narrative=inputs["narrative"],
            club_manager=inputs["club_manager"],
            predictions=inputs.get("predictions"),
            form_home=inputs.get("form_home"),
            form_away=inputs.get("form_away"),
            h2h=inputs.get("h2h"),
            team_stats_home=inputs.get("team_stats_home"),
            team_stats_away=inputs.get("team_stats_away"),
            elo=inputs.get("elo"),
            odds_comparison=inputs.get("odds_comparison"),
            prediction_basis=inputs.get("prediction_basis"),
            version=version,
        )
    else:
        text = fill_post_match_template(
            competition=inputs["competition"],
            tactics_summary=inputs["tactics_summary"],
            key_events=inputs.get("key_events", []),
            narrative=inputs["narrative"],
            predictions=inputs.get("predictions"),
            version=version,
        )

    if use_llm:
        text = _llm_polish(text, report_type, version) or text
    return text


def _llm_polish(raw: str, report_type: str, version: str) -> str | None:
    """可选 LLM 润色；从 config/settings.yaml 读取 report.llm，失败时返回 None。"""
    from pathlib import Path
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    if not config_path.exists():
        return None
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        llm_config = (data.get("report") or {}).get("llm") or {}
        from football_ai.report.llm import polish_report
        out = polish_report(raw, report_type, version, llm_config)
        return out if out and out != raw else None
    except Exception:
        return None
