"""
Elo 实力分：基于历史场次按时间顺序更新每队 Elo，用于产出 Elo 胜负平概率（可与 Poisson 并列展示）。
排序见 sort_key_match（优先 match_date）。
"""
from typing import Any

from football_ai.data.historical import sort_key_match

DEFAULT_K = 20
DEFAULT_INITIAL = 1500


def _expected_score(elo_self: float, elo_opp: float) -> float:
    """主队视角的期望得分（0–1），即胜率对应的期望分。"""
    return 1.0 / (1.0 + 10.0 ** ((elo_opp - elo_self) / 400.0))


def _actual_points(goals_home: int, goals_away: int) -> tuple[float, float]:
    """主队与客队的实际得分（胜 1/0.5/0 对应 1 / 0.5 / 0）。"""
    if goals_home > goals_away:
        return (1.0, 0.0)
    if goals_home < goals_away:
        return (0.0, 1.0)
    return (0.5, 0.5)


def get_elo_probabilities(elo_home: float, elo_away: float) -> dict[str, float]:
    """
    由主客 Elo 得胜负平概率。主胜 ≈ 1/(1+10^((away-home)/400))，客胜对称，平 = 1 - 主胜 - 客胜 后归一化。
    """
    p_home = 1.0 / (1.0 + 10.0 ** ((elo_away - elo_home) / 400.0))
    p_away = 1.0 / (1.0 + 10.0 ** ((elo_home - elo_away) / 400.0))
    p_draw = max(0.0, 1.0 - p_home - p_away)
    total = p_home + p_draw + p_away
    if total <= 0:
        return {"主胜": 1/3, "平": 1/3, "客胜": 1/3}
    return {"主胜": p_home / total, "平": p_draw / total, "客胜": p_away / total}


def get_elo_for_report(
    home_team: str,
    away_team: str,
    matches: list[dict[str, Any]],
    season: int,
    round_: int,
    k: int = DEFAULT_K,
    initial: float = DEFAULT_INITIAL,
) -> dict[str, Any] | None:
    """
    基于历史场次计算双方本场赛前 Elo，并返回 Elo 胜负平概率与简短说明。供报告展示。
    """
    if not matches or season <= 0:
        return None
    # 按比赛时间升序（优先 match_date）
    sorted_matches = sorted(matches, key=sort_key_match)
    current: dict[str, float] = {}
    elo_after: dict[tuple[str, int, int], float] = {}

    for m in sorted_matches:
        s, r = int(m.get("season", 0)), int(m.get("round", 0))
        home = (m.get("home_team") or "").strip()
        away = (m.get("away_team") or "").strip()
        if not home or not away:
            continue
        gh = int(float(m.get("goals_home", 0)))
        ga = int(float(m.get("goals_away", 0)))
        elo_h = current.get(home, initial)
        elo_a = current.get(away, initial)
        exp_h = _expected_score(elo_h, elo_a)
        exp_a = _expected_score(elo_a, elo_h)
        act_h, act_a = _actual_points(gh, ga)
        current[home] = elo_h + k * (act_h - exp_h)
        current[away] = elo_a + k * (act_a - exp_a)
        elo_after[(home, s, r)] = current[home]
        elo_after[(away, s, r)] = current[away]

    home = home_team.strip()
    away = away_team.strip()
    # 本场赛前 = 上一场赛后的 Elo
    def get_before(team: str) -> float:
        cand = None
        for (t, s, r), v in elo_after.items():
            if t != team or (s, r) >= (season, round_):
                continue
            if cand is None or (s, r) > cand[0]:
                cand = ((s, r), v)
        return cand[1] if cand else initial

    elo_h = get_before(home)
    elo_a = get_before(away)
    probs = get_elo_probabilities(elo_h, elo_a)
    summary_zh = (
        "Elo 概率（仅供参考）：主胜 %.0f%% 平 %.0f%% 客胜 %.0f%%（主队 Elo %.0f，客队 %.0f）。"
        % (probs["主胜"] * 100, probs["平"] * 100, probs["客胜"] * 100, elo_h, elo_a)
    )
    return {
        "elo_home": round(elo_h, 1),
        "elo_away": round(elo_a, 1),
        "win_draw_lose": probs,
        "summary_zh": summary_zh,
    }
