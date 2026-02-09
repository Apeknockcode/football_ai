"""
报告模板：赛前、赛后；完整版与摘要版。仅中文。
"""
from typing import Any


def _format_predictions(pred: dict[str, Any]) -> list[str]:
    """将预测结构格式化为报告行。"""
    lines = []
    lines.append(pred.get("disclaimer_zh", ""))

    if not pred.get("available"):
        lines.append(pred.get("summary_zh", "第一版不提供预测。"))
        return lines

    wdl = pred.get("win_draw_lose")
    if wdl:
        lines.append("胜负平（仅供参考）：主胜 %.0f%% / 平 %.0f%% / 客胜 %.0f%%" % (
            wdl.get("主胜", 0) * 100, wdl.get("平", 0) * 100, wdl.get("客胜", 0) * 100))
    hcp = pred.get("handicap")
    if hcp:
        lines.append("让胜负平（%s）：让胜 %.0f%% / 让平 %.0f%% / 让负 %.0f%%" % (
            hcp.get("让球", ""), hcp.get("让胜", 0) * 100, hcp.get("让平", 0) * 100, hcp.get("让负", 0) * 100))
    hf = pred.get("half_full")
    if hf:
        top3 = sorted(hf.items(), key=lambda x: -x[1])[:3]
        lines.append("半全场（前三种）：" + "、".join("%s %.0f%%" % (k, v * 100) for k, v in top3))
    sc = pred.get("score")
    if sc:
        other = sc.get("其他", [])[:5]
        lines.append("比分（参考）：%s；其他可能 %s" % (sc.get("最可能比分", "-"), "、".join(other) if other else "-"))
    if pred.get("summary_zh"):
        lines.append(pred["summary_zh"])
    return lines


def fill_pre_match_template(
    competition: dict[str, Any],
    injury: dict[str, Any],
    discipline_referee: dict[str, Any],
    tactics_summary: str,
    narrative: dict[str, Any],
    club_manager: dict[str, Any],
    predictions: dict[str, Any] | None = None,
    form_home: dict[str, Any] | None = None,
    form_away: dict[str, Any] | None = None,
    h2h: dict[str, Any] | None = None,
    team_stats_home: dict[str, Any] | None = None,
    team_stats_away: dict[str, Any] | None = None,
    elo: dict[str, Any] | None = None,
    odds_comparison: dict[str, Any] | None = None,
    prediction_basis: str | None = None,
    version: str = "full",
) -> str:
    """
    填充赛前报告模板。
    :param version: full | summary
    :param predictions: 预测模块输出（胜负平、让胜负平、半全场、比分）；可为 None
    :param form_home/form_away: 近期状态（近 N 场）；可为 None
    :param h2h: 历史交锋；可为 None
    :param team_stats_home/team_stats_away: 赛季统计与 xPts；可为 None
    :param elo: Elo 概率块；可为 None
    :param odds_comparison: 模型 vs 赔率隐含概率对比；可为 None（不构成投注建议）
    :param prediction_basis: 模型核心依据说明（基于 xG/状态/交锋/Elo 等），便于与主流观点对比
    """
    parts = []
    parts.append("【赛事与背景】")
    parts.append(competition.get("summary_zh", ""))

    if form_home or form_away or h2h:
        parts.append("\n【近期状态与交锋】")
        if form_home and form_home.get("summary_zh"):
            parts.append("主队：" + form_home["summary_zh"])
        if form_away and form_away.get("summary_zh"):
            parts.append("客队：" + form_away["summary_zh"])
        if h2h and h2h.get("summary_zh"):
            parts.append("交锋：" + h2h["summary_zh"])

    if team_stats_home or team_stats_away:
        parts.append("\n【积分与预期】")
        if team_stats_home and team_stats_home.get("summary_zh"):
            parts.append(team_stats_home["summary_zh"])
        if team_stats_away and team_stats_away.get("summary_zh"):
            parts.append(team_stats_away["summary_zh"])

    parts.append("\n【伤停与纪律】")
    parts.append(injury.get("summary_zh", "暂无伤停信息。"))
    if discipline_referee.get("summary_zh"):
        parts.append(discipline_referee["summary_zh"])

    parts.append("\n【战术预期】")
    parts.append(tactics_summary)

    if predictions is not None:
        parts.append("\n【预测】")
        parts.append("\n".join(_format_predictions(predictions)))
    if prediction_basis:
        parts.append("\n【预测依据】")
        parts.append(prediction_basis)
    # 不确定性说明：长期统计优势，不保证单场
    try:
        from football_ai.predictions.service import UNCERTAINTY_ZH
        parts.append("\n【说明】")
        parts.append(UNCERTAINTY_ZH)
    except Exception:
        parts.append("\n【说明】")
        parts.append("单场结果受多种不可预测因素影响；模型追求长期统计表现，不保证单场命中。历史回测见 backtest 输出，仅供参考。")
    if elo and elo.get("summary_zh"):
        parts.append("\n【Elo 参考】")
        parts.append(elo["summary_zh"])
    if odds_comparison and odds_comparison.get("summary_zh"):
        parts.append("\n【概率对比】")
        parts.append(odds_comparison["summary_zh"])

    if version == "full":
        parts.append("\n【舆论与压力】")
        parts.append(narrative.get("summary_zh", ""))
        if club_manager.get("summary_zh"):
            parts.append(club_manager["summary_zh"])
            if club_manager.get("sources"):
                parts.append("（据 " + "、".join(club_manager["sources"][:2]) + "）")

    if version == "summary":
        summary_lines = [competition.get("summary_zh", "")]
        if form_home or form_away or h2h:
            if form_home and form_home.get("summary_zh"):
                summary_lines.append("主队近况：" + form_home["summary_zh"])
            if form_away and form_away.get("summary_zh"):
                summary_lines.append("客队近况：" + form_away["summary_zh"])
            if h2h and h2h.get("summary_zh"):
                summary_lines.append("交锋：" + h2h["summary_zh"])
        if team_stats_home or team_stats_away:
            if team_stats_home and team_stats_home.get("summary_zh"):
                summary_lines.append(team_stats_home["summary_zh"])
            if team_stats_away and team_stats_away.get("summary_zh"):
                summary_lines.append(team_stats_away["summary_zh"])
        summary_lines.append(injury.get("summary_zh", ""))
        summary_lines.append("战术预期：" + tactics_summary[:80] + ("..." if len(tactics_summary) > 80 else ""))
        summary_lines.append("预测：" + (predictions.get("summary_zh", "第一版不提供。") if predictions else "第一版不提供。"))
        return "\n".join(summary_lines)
    return "\n".join(parts)


def fill_post_match_template(
    competition: dict[str, Any],
    tactics_summary: str,
    key_events: list[str],
    narrative: dict[str, Any],
    predictions: dict[str, Any] | None = None,
    version: str = "full",
) -> str:
    """
    填充赛后报告模板。
    """
    parts = []
    if competition.get("summary_zh") or competition.get("match_datetime_zh"):
        parts.append("【赛事信息】")
        if competition.get("summary_zh"):
            parts.append(competition["summary_zh"])
        elif competition.get("match_datetime_zh"):
            parts.append("本场时间：" + competition["match_datetime_zh"] + "。")
        parts.append("")
    parts.append("【战术复盘】")
    parts.append(tactics_summary)

    if predictions and predictions.get("available") and version == "full":
        parts.append("\n【预测概率】")
        parts.append("\n".join(_format_predictions(predictions)))

    if key_events and version == "full":
        parts.append("\n【关键事件】")
        for ev in key_events[:5]:
            parts.append(f"- {ev}")

    parts.append("\n【背景与叙事】")
    parts.append(narrative.get("summary_zh", "本场结果对积分榜形势的影响以当轮为准。"))

    if version == "summary":
        return "\n".join([tactics_summary, narrative.get("summary_zh", "")])
    return "\n".join(parts)
