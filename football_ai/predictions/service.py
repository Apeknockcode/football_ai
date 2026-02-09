"""
预测服务：根据本场事件数据（xG 等）推算胜负平、让胜负平、比分、半全场概率。
基于 Poisson(xG) 模型；存在 config/calibration_pl.yaml 时自动应用校准（主队系数、xG 缩放）。
仅供参考，不构成任何投注建议。
"""
import math
from pathlib import Path
from typing import Any

# 免责说明
DISCLAIMER_ZH = (
    "以下概率由本场 xG 数据经 Poisson 模型推算，仅供参考，不构成任何投注建议，请遵守当地法规。"
)

# 不确定性说明：单场 vs 长期
UNCERTAINTY_ZH = (
    "单场结果受红牌、失误、偶然进球等不可预测因素影响；模型目标是在长期统计中保持优势，而非每场命中。"
    "历史回测结果见 backtest 输出，仅供参考。"
)


def _load_calibration(path: Path | None = None) -> dict[str, Any] | None:
    """加载校准参数 YAML；无文件或解析失败返回 None。"""
    if path is None:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "calibration_pl.yaml"
    if not path or not Path(path).exists():
        return None
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or None
    except Exception:
        return None


def _apply_calibration(xg_h: float, xg_a: float, cal: dict[str, Any] | None) -> tuple[float, float]:
    """对 xG 应用校准：home_xg_factor、xg_scale。"""
    if not cal:
        return xg_h, xg_a
    scale = float(cal.get("xg_scale", 1.0))
    home_factor = float(cal.get("home_xg_factor", 1.0))
    return xg_h * home_factor * scale, xg_a * scale


# 伤停扣减默认值（当 config 未配置时使用）
_DEFAULT_INJURY_ADJUST = {
    "deduct_injured": 0.06,
    "deduct_doubtful": 0.03,
    "max_deduct_per_team": 0.25,
    "min_xg_after_injury": 0.25,
}


def _load_injury_adjust_config() -> dict[str, float]:
    """从 config/settings.yaml 的 predictions.injury_xg_adjust 读取；缺则用默认。"""
    path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    if not path.exists():
        return _DEFAULT_INJURY_ADJUST
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        adj = (data.get("predictions") or {}).get("injury_xg_adjust") or {}
        return {
            "deduct_injured": float(adj.get("deduct_injured", _DEFAULT_INJURY_ADJUST["deduct_injured"])),
            "deduct_doubtful": float(adj.get("deduct_doubtful", _DEFAULT_INJURY_ADJUST["deduct_doubtful"])),
            "max_deduct_per_team": float(adj.get("max_deduct_per_team", _DEFAULT_INJURY_ADJUST["max_deduct_per_team"])),
            "min_xg_after_injury": float(adj.get("min_xg_after_injury", _DEFAULT_INJURY_ADJUST["min_xg_after_injury"])),
        }
    except Exception:
        return _DEFAULT_INJURY_ADJUST


def adjust_xg_for_injuries(
    xg_h: float,
    xg_a: float,
    home_list: list[dict[str, Any]],
    away_list: list[dict[str, Any]],
) -> tuple[float, float]:
    """
    根据伤停名单对赛前预期 xG 做小幅下调，使加伤停与不加伤停时预测有区别。
    扣减参数从 config/settings.yaml 的 predictions.injury_xg_adjust 读取，缺则用默认。
    home_list/away_list 每项含 "reason"：受伤/停赛/出战成疑/复出/其他原因。
    """
    cfg = _load_injury_adjust_config()
    di, dd, max_d, min_xg = cfg["deduct_injured"], cfg["deduct_doubtful"], cfg["max_deduct_per_team"], cfg["min_xg_after_injury"]

    def deduct(lst: list) -> float:
        total = 0.0
        for item in lst:
            r = (item.get("reason") or "").strip()
            if r in ("受伤", "停赛", "其他原因"):
                total += di
            elif r == "出战成疑":
                total += dd
        return min(total, max_d)

    xg_h_adj = max(min_xg, xg_h - deduct(home_list))
    xg_a_adj = max(min_xg, xg_a - deduct(away_list))
    return xg_h_adj, xg_a_adj


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def most_likely_score_given_xg_and_wdl(xg_h: float, xg_a: float, wdl: dict[str, float]) -> str:
    """
    在给定 xG 的 Poisson 比分分布下，按 WDL 中概率最高的类别（主胜/平/客胜），
    返回该类别内概率最高的单一比分。供 ML 路径在「有 xG」时产出与胜负平一致的比分。
    """
    max_goals = 8
    score_probs: list[tuple[str, float]] = []
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = _poisson_pmf(i, xg_h) * _poisson_pmf(j, xg_a)
            score_probs.append((f"{i}-{j}", p))
    p_win = p_draw = p_lose = 0.0
    by_cat: dict[str, list[tuple[str, float]]] = {"主胜": [], "平": [], "客胜": []}
    for s, prob in score_probs:
        a, _, b = s.partition("-")
        i, j = int(a.strip()), int(b.strip())
        if i > j:
            p_win += prob
            by_cat["主胜"].append((s, prob))
        elif i == j:
            p_draw += prob
            by_cat["平"].append((s, prob))
        else:
            p_lose += prob
            by_cat["客胜"].append((s, prob))
    p_w = (wdl.get("主胜") or 0.0)
    p_d = (wdl.get("平") or 0.0)
    p_l = (wdl.get("客胜") or 0.0)
    if p_w >= p_d and p_w >= p_l:
        cat_scores = by_cat["主胜"]
    elif p_d >= p_w and p_d >= p_l:
        cat_scores = by_cat["平"]
    else:
        cat_scores = by_cat["客胜"]
    cat_scores_sorted = sorted(cat_scores, key=lambda x: -x[1])
    return cat_scores_sorted[0][0] if cat_scores_sorted else "0-0"


def _probabilities_from_xg(
    xg_h: float,
    xg_a: float,
    xg_ht_h: float | None = None,
    xg_ht_a: float | None = None,
) -> dict[str, Any]:
    """
    用 Poisson(xG) 模型计算胜负平、比分、半全场概率。
    主队进球数 ~ Poisson(xg_h)，客队 ~ Poisson(xg_a)，假设独立。
    若提供 xg_ht_h、xg_ht_a（半场预期 xG），半全场概率按「半场 Poisson × 全场 Poisson」独立计算。
    """
    max_goals = 8
    p_win, p_draw, p_lose = 0.0, 0.0, 0.0
    score_probs: list[tuple[str, float]] = []

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = _poisson_pmf(i, xg_h) * _poisson_pmf(j, xg_a)
            score_probs.append((f"{i}-{j}", p))
            if i > j:
                p_win += p
            elif i == j:
                p_draw += p
            else:
                p_lose += p

    total = p_win + p_draw + p_lose
    if total <= 0:
        p_win, p_draw, p_lose = 1/3, 1/3, 1/3
    else:
        p_win /= total
        p_draw /= total
        p_lose /= total

    # 最可能比分：取「胜负平」中概率最高那一类里，概率最高的单一比分，使比分与胜负平/让球一致
    def _parse_score(s: str) -> tuple[int, int]:
        a, _, b = s.partition("-")
        return int(a.strip()), int(b.strip())

    by_cat: dict[str, list[tuple[str, float]]] = {"主胜": [], "平": [], "客胜": []}
    for s, prob in score_probs:
        i, j = _parse_score(s)
        if i > j:
            by_cat["主胜"].append((s, prob))
        elif i == j:
            by_cat["平"].append((s, prob))
        else:
            by_cat["客胜"].append((s, prob))

    if p_win >= p_draw and p_win >= p_lose:
        cat_scores = by_cat["主胜"]
    elif p_draw >= p_win and p_draw >= p_lose:
        cat_scores = by_cat["平"]
    else:
        cat_scores = by_cat["客胜"]
    cat_scores_sorted = sorted(cat_scores, key=lambda x: -x[1])
    most_likely = cat_scores_sorted[0][0] if cat_scores_sorted else "0-0"

    score_probs.sort(key=lambda x: -x[1])
    top_scores = score_probs[:5]
    other_scores = [f"{s}({p*100:.0f}%)" for s, p in top_scores[1:4]]

    # 半全场：有半场 xG 时用半场 Poisson 算半场胜负平，再与全场独立相乘；否则用同一分布
    if xg_ht_h is not None and xg_ht_a is not None and (xg_ht_h > 0 or xg_ht_a > 0):
        p_win_ht, p_draw_ht, p_lose_ht = 0.0, 0.0, 0.0
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                p = _poisson_pmf(i, xg_ht_h) * _poisson_pmf(j, xg_ht_a)
                if i > j:
                    p_win_ht += p
                elif i == j:
                    p_draw_ht += p
                else:
                    p_lose_ht += p
        t_ht = p_win_ht + p_draw_ht + p_lose_ht
        if t_ht > 0:
            p_win_ht, p_draw_ht, p_lose_ht = p_win_ht / t_ht, p_draw_ht / t_ht, p_lose_ht / t_ht
        else:
            p_win_ht, p_draw_ht, p_lose_ht = p_win, p_draw, p_lose
        p_h, p_d, p_a = p_win_ht, p_draw_ht, p_lose_ht
    else:
        p_h, p_d, p_a = p_win, p_draw, p_lose
    half_full = {
        "胜胜": p_h * p_win, "胜平": p_h * p_draw, "胜负": p_h * p_lose,
        "平胜": p_d * p_win, "平平": p_d * p_draw, "平负": p_d * p_lose,
        "负胜": p_a * p_win, "负平": p_a * p_draw, "负负": p_a * p_lose,
    }
    hf_sum = sum(half_full.values())
    if hf_sum > 0:
        half_full = {k: v / hf_sum for k, v in half_full.items()}

    # 让球 主让 0.5：让胜=主胜，让平=0，让负=平+客胜
    hcp_win = p_win
    hcp_draw = 0.0
    hcp_lose = p_draw + p_lose

    # 竞彩让球数：基于比分分布算 主让1(-1) / 主受让1(+1)
    p_win_1, p_draw_1, p_lose_1 = 0.0, 0.0, 0.0   # 主让1球
    p_win_p1, p_draw_p1, p_lose_p1 = 0.0, 0.0, 0.0  # 主受让1球
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = _poisson_pmf(i, xg_h) * _poisson_pmf(j, xg_a)
            diff = i - j
            # 主让1：让胜=主净胜>=2，让平=主净胜1，让负=平或客胜
            if diff >= 2:
                p_win_1 += p
            elif diff == 1:
                p_draw_1 += p
            else:
                p_lose_1 += p
            # 主受让1：让胜=主胜+平+主输1球，让平=主输1球，让负=主输2+
            if diff >= 0:
                p_win_p1 += p
            elif diff == -1:
                p_draw_p1 += p
            else:
                p_lose_p1 += p
    t1 = p_win_1 + p_draw_1 + p_lose_1
    tp1 = p_win_p1 + p_draw_p1 + p_lose_p1
    if t1 > 0:
        p_win_1, p_draw_1, p_lose_1 = p_win_1 / t1, p_draw_1 / t1, p_lose_1 / t1
    if tp1 > 0:
        p_win_p1, p_draw_p1, p_lose_p1 = p_win_p1 / tp1, p_draw_p1 / tp1, p_lose_p1 / tp1

    return {
        "win_draw_lose": {"主胜": p_win, "平": p_draw, "客胜": p_lose},
        "handicap": {"让球": "主让 0.5", "让胜": hcp_win, "让平": hcp_draw, "让负": hcp_lose},
        "handicap_1": {"让球": "主让 1", "让胜": p_win_1, "让平": p_draw_1, "让负": p_lose_1},
        "handicap_plus1": {"让球": "主受让 1", "让胜": p_win_p1, "让平": p_draw_p1, "让负": p_lose_p1},
        "half_full": half_full,
        "score": {"最可能比分": most_likely, "其他": other_scores, "详情": top_scores},
    }


def get_predictions(
    home_team: str,
    away_team: str,
    round_: int,
    metrics: dict[str, Any] | None = None,
    available: bool = False,
    expected_xg: bool = False,
    league_id: str | None = None,
    handicap_line: float | None = None,
) -> dict[str, Any]:
    """
    根据本场或赛前预期 xG 计算胜负平、让胜负平、比分、半全场概率。
    当 metrics 中有有效 xG 或 available=True 时返回推算结果；expected_xg=True 表示使用赛前预期 xG。
    handicap_line：竞彩让球数，-1=主让1球，1 或 1.0=主受让1球，None/0.5=主让0.5（默认）。
    """
    out: dict[str, Any] = {
        "available": False,
        "disclaimer_zh": DISCLAIMER_ZH,
        "win_draw_lose": None,
        "handicap": None,
        "half_full": None,
        "score": None,
        "summary_zh": "",
    }

    xg_h = 0.0
    xg_a = 0.0
    if metrics and "xg" in metrics:
        xg = metrics["xg"]
        xg_h = float(xg.get(home_team) or xg.get("home") or 0)
        xg_a = float(xg.get(away_team) or xg.get("away") or 0)

    has_xg = (xg_h > 0 or xg_a > 0) or available
    if not has_xg:
        out["summary_zh"] = "未提供本场事件数据，无法基于 xG 推算胜负平/比分等概率。请先提供比赛事件数据（如 --events）。"
        return out

    if not has_xg and not available:
        out["summary_zh"] = "未提供本场事件数据，无法推算概率。"
        return out

    # 无 xG 时用默认 0.5/0.5 做 Poisson，得到接近 33/33/33
    if xg_h == 0 and xg_a == 0 and available:
        xg_h, xg_a = 0.5, 0.5

    cal_path = None
    if league_id:
        from football_ai.leagues import get_calibration_path
        cal_path = get_calibration_path(league_id)
    cal = _load_calibration(cal_path)
    xg_h, xg_a = _apply_calibration(xg_h, xg_a, cal)
    xg_ht_h, xg_ht_a = None, None
    if metrics and "xg_ht" in metrics:
        xht = metrics["xg_ht"]
        xg_ht_h = xht.get("home") or xht.get(home_team)
        xg_ht_a = xht.get("away") or xht.get(away_team)
        if xg_ht_h is not None and xg_ht_a is not None:
            xg_ht_h = float(xg_ht_h)
            xg_ht_a = float(xg_ht_a)
            xg_ht_h, xg_ht_a = _apply_calibration(xg_ht_h, xg_ht_a, cal)
        else:
            xg_ht_h, xg_ht_a = None, None
    probs = _probabilities_from_xg(xg_h, xg_a, xg_ht_h, xg_ht_a)
    # 按竞彩让球数选用对应让球概率
    if handicap_line is not None and handicap_line <= -1:
        out["handicap"] = probs.get("handicap_1") or probs["handicap"]
    elif handicap_line is not None and handicap_line >= 1:
        out["handicap"] = probs.get("handicap_plus1") or probs["handicap"]
    else:
        out["handicap"] = probs["handicap"]
    out["available"] = True
    out["win_draw_lose"] = probs["win_draw_lose"]
    out["half_full"] = probs["half_full"]
    out["score"] = {
        "最可能比分": probs["score"]["最可能比分"],
        "其他": probs["score"]["其他"],
        "详情": probs["score"].get("详情") or [],
    }
    if expected_xg:
        out["summary_zh"] = f"（基于赛前预期 xG 主 {xg_h:.2f} – 客 {xg_a:.2f} 推算，仅供参考；不构成投注建议。）"
    else:
        out["summary_zh"] = f"（基于本场 xG 主 {xg_h:.2f} – 客 {xg_a:.2f} 推算，仅供参考；不构成投注建议。）"
    return out
