"""
赔率与隐含概率：仅用于「模型概率 vs 赔率隐含概率」的对比展示，不输出任何投注建议。
价值方向：模型概率显著高于赔率隐含时标记（仅信息展示）。阈值见 config/settings.yaml predictions.value_threshold。
"""
from pathlib import Path
from typing import Any


def _get_value_threshold() -> float:
    """从 config/settings.yaml 读取 value_threshold，默认 0.05。"""
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    if not cfg_path.exists():
        return 0.05
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return float((data.get("predictions") or {}).get("value_threshold", 0.05))
    except Exception:
        return 0.05


def get_value_indicators(
    model_win_draw_lose: dict[str, float],
    implied_win_draw_lose: dict[str, float],
    threshold: float | None = None,
) -> dict[str, Any]:
    """
    对主胜/平/客胜三项，若「模型概率 − 赔率隐含概率」> threshold，则标记为潜在价值方向。
    仅作信息展示，不构成投注建议。
    :return: {"主胜": bool, "平": bool, "客胜": bool, "deltas": {"主胜": float, ...}, "threshold": float}
    """
    if threshold is None:
        threshold = _get_value_threshold()
    m_h = (model_win_draw_lose.get("主胜") or 0)
    m_d = (model_win_draw_lose.get("平") or 0)
    m_a = (model_win_draw_lose.get("客胜") or 0)
    i_h = (implied_win_draw_lose.get("主胜") or 0)
    i_d = (implied_win_draw_lose.get("平") or 0)
    i_a = (implied_win_draw_lose.get("客胜") or 0)
    deltas = {"主胜": m_h - i_h, "平": m_d - i_d, "客胜": m_a - i_a}
    return {
        "主胜": deltas["主胜"] > threshold,
        "平": deltas["平"] > threshold,
        "客胜": deltas["客胜"] > threshold,
        "deltas": deltas,
        "threshold": threshold,
    }


def implied_probabilities_from_decimal(
    odds_home: float,
    odds_draw: float,
    odds_away: float,
) -> tuple[float, float, float]:
    """
    由欧洲小数赔率计算隐含概率（归一化，去除庄家 margin）。
    :return: (主胜概率, 平概率, 客胜概率)，和为 1
    """
    if odds_home <= 0 or odds_draw <= 0 or odds_away <= 0:
        return (1/3, 1/3, 1/3)
    inv_h = 1.0 / odds_home
    inv_d = 1.0 / odds_draw
    inv_a = 1.0 / odds_away
    total = inv_h + inv_d + inv_a
    if total <= 0:
        return (1/3, 1/3, 1/3)
    return (inv_h / total, inv_d / total, inv_a / total)


def get_odds_comparison(
    model_win_draw_lose: dict[str, float] | None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> dict[str, Any] | None:
    """
    生成「模型概率 vs 赔率隐含概率」对比结构，供报告展示用。不包含任何投注建议。
    :param model_win_draw_lose: 模型输出的 {"主胜": p1, "平": p2, "客胜": p3}
    :param odds_*: 欧洲小数赔率，可选
    :return: 若有模型且至少一组赔率，返回 summary_zh 与数值；否则 None
    """
    if not model_win_draw_lose or (odds_home is None and odds_draw is None and odds_away is None):
        return None
    if odds_home is None:
        odds_home = 0.0
    if odds_draw is None:
        odds_draw = 0.0
    if odds_away is None:
        odds_away = 0.0
    if odds_home <= 0 or odds_draw <= 0 or odds_away <= 0:
        return None
    imp_h, imp_d, imp_a = implied_probabilities_from_decimal(odds_home, odds_draw, odds_away)
    m_h = model_win_draw_lose.get("主胜", 0) or 0
    m_d = model_win_draw_lose.get("平", 0) or 0
    m_a = model_win_draw_lose.get("客胜", 0) or 0
    summary_zh = (
        "概率对比（仅供参考，不构成投注建议）："
        " 模型 主胜 %.0f%% 平 %.0f%% 客胜 %.0f%%；"
        " 赔率隐含 主胜 %.0f%% 平 %.0f%% 客胜 %.0f%%。"
        % (m_h * 100, m_d * 100, m_a * 100, imp_h * 100, imp_d * 100, imp_a * 100)
    )
    implied_wdl = {"主胜": imp_h, "平": imp_d, "客胜": imp_a}
    model_wdl = {"主胜": m_h, "平": m_d, "客胜": m_a}
    value_indicators = get_value_indicators(model_wdl, implied_wdl)
    value_dirs = [k for k in ["主胜", "平", "客胜"] if value_indicators.get(k)]
    if value_dirs:
        summary_zh += " 模型概率高于赔率隐含超过 %.0f%% 的方向：%s。（仅信息展示，不构成投注建议。）" % (
            value_indicators["threshold"] * 100, "、".join(value_dirs)
        )
    return {
        "model": model_wdl,
        "implied": implied_wdl,
        "summary_zh": summary_zh,
        "value_indicators": value_indicators,
    }


def load_odds_for_match(
    path: str | Path,
    home_team: str,
    away_team: str,
    round_: int | None = None,
    match_code: str | None = None,
) -> tuple[float | None, float | None, float | None]:
    """
    从 CSV 读取本场赔率。CSV 需含 home_team, away_team 以及 odds_home, odds_draw, odds_away（或 win_home, draw, win_away 等）。
    可选列：round, match_code 用于匹配。
    :return: (odds_home, odds_draw, odds_away)，未找到则均为 None
    """
    import csv
    p = Path(path)
    if not p.exists() or not p.suffix.lower() == ".csv":
        return (None, None, None)
    home = home_team.strip()
    away = away_team.strip()
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            r_h = (r.get("home_team") or r.get("主队") or "").strip()
            r_a = (r.get("away_team") or r.get("客队") or "").strip()
            if r_h != home or r_a != away:
                continue
            if round_ is not None and r.get("round") is not None:
                try:
                    if int(float(r["round"])) != round_:
                        continue
                except (ValueError, TypeError):
                    pass
            if match_code and r.get("match_code") and (r.get("match_code") or "").strip() != (match_code or "").strip():
                continue
            oh = r.get("odds_home") or r.get("win_home") or r.get("主胜")
            od = r.get("odds_draw") or r.get("draw") or r.get("平")
            oa = r.get("odds_away") or r.get("win_away") or r.get("客胜")
            try:
                return (float(oh), float(od), float(oa))
            except (TypeError, ValueError):
                return (None, None, None)
    return (None, None, None)
