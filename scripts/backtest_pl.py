#!/usr/bin/env python3
"""
用历史场次回测预测模型：逐场用当前（或校准后）模型得到概率，计算 Brier、对数似然。
先数据 → 再校准 → 再回测 → 再升级模型。联赛见 config/leagues.yaml。
"""
import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from football_ai.data.historical import load_historical_matches
from football_ai.data.historical import sort_key_match
from football_ai.leagues import get_league, get_calibration_path, get_historical_dir
from football_ai.predictions.service import (
    _probabilities_from_xg,
    _load_calibration,
    _apply_calibration,
)
from football_ai.predictions.ml_predictor import load_artifact, predict_wdl


def main() -> None:
    parser = argparse.ArgumentParser(description="联赛回测：Brier、对数似然")
    parser.add_argument("--league", type=str, default="EPL", help="联赛 id（见 config/leagues.yaml）")
    parser.add_argument(
        "--historical",
        type=Path,
        default=None,
        help="历史数据目录或 CSV；不指定时用 data/historical/{league_id}/",
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        default=None,
        help="校准参数 YAML（可选）；不指定时用 config/calibration_{league_id}.yaml",
    )
    parser.add_argument("--model", choices=["poisson", "ml"], default="poisson", help="预测源：poisson（默认）或 ml")
    parser.add_argument("--ml-model", type=Path, default=None, help="ML 模型 pkl 路径（--model ml 时必填）")
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    league_cfg = get_league(league_id)
    if not league_cfg:
        print(f"未找到联赛配置: {league_id}。", file=sys.stderr)
        sys.exit(1)

    hist_path = args.historical
    if hist_path is None:
        hist_dir = get_historical_dir(league_id)
        if not hist_dir.exists() and league_id == "EPL":
            hist_dir = ROOT / "data" / "historical"
        hist_path = hist_dir
    cal_path = args.calibration if args.calibration is not None else get_calibration_path(league_id)

    if hist_path.is_file():
        matches = load_historical_matches(path=hist_path)
    else:
        matches = load_historical_matches(directory=hist_path)

    if not matches:
        print("未找到历史场次。", file=sys.stderr)
        sys.exit(1)

    use_ml = args.model == "ml"
    ml_artifact = None
    if use_ml:
        if not args.ml_model or not args.ml_model.exists():
            print("--model ml 需指定存在的 --ml-model 路径。", file=sys.stderr)
            sys.exit(1)
        ml_artifact = load_artifact(args.ml_model)
        print("使用 ML 模型:", args.ml_model)
    else:
        cal = _load_calibration(cal_path) if cal_path and cal_path.exists() else None
        if cal:
            print("使用校准参数:", cal_path)
        else:
            print("未使用校准（无校准文件）")

    sorted_matches = sorted(matches, key=sort_key_match)
    brier_sum = 0.0
    log_likelihood_sum = 0.0
    correct_wdl = 0
    correct_score = 0
    in_top3_score = 0
    n = 0
    for i, m in enumerate(sorted_matches):
        g_h, g_a = m["goals_home"], m["goals_away"]
        if g_h > g_a:
            actual = (1, 0, 0)
        elif g_h < g_a:
            actual = (0, 0, 1)
        else:
            actual = (0, 1, 0)

        if use_ml and ml_artifact is not None:
            past = sorted_matches[:i]
            try:
                wdl = predict_wdl(m, past, ml_artifact)
            except Exception:
                wdl = {"主胜": 1/3, "平": 1/3, "客胜": 1/3}
            p_win, p_draw, p_lose = wdl["主胜"], wdl["平"], wdl["客胜"]
            most_likely = "-"
            top_scores = []
        else:
            xg_h, xg_a = m["xg_home"], m["xg_away"]
            xg_h, xg_a = _apply_calibration(xg_h, xg_a, cal)
            probs = _probabilities_from_xg(xg_h, xg_a)
            wdl = probs["win_draw_lose"]
            p_win, p_draw, p_lose = wdl["主胜"], wdl["平"], wdl["客胜"]
            most_likely = probs["score"]["最可能比分"]
            top_scores = [s for s, _ in probs["score"]["详情"][:3]]

        # Brier: (p_win - actual_win)^2 + (p_draw - actual_draw)^2 + (p_lose - actual_lose)^2
        brier_sum += (p_win - actual[0]) ** 2 + (p_draw - actual[1]) ** 2 + (p_lose - actual[2]) ** 2
        p_actual = p_win * actual[0] + p_draw * actual[1] + p_lose * actual[2]
        if p_actual <= 0:
            p_actual = 1e-10
        log_likelihood_sum += math.log(p_actual)

        pred_wdl = "主胜" if p_win >= p_draw and p_win >= p_lose else ("平" if p_draw >= p_lose else "客胜")
        actual_wdl = "主胜" if g_h > g_a else ("平" if g_h == g_a else "客胜")
        if pred_wdl == actual_wdl:
            correct_wdl += 1

        actual_score = f"{g_h}-{g_a}"
        if most_likely == actual_score:
            correct_score += 1
        if actual_score in top_scores:
            in_top3_score += 1

        n += 1

    brier = brier_sum / n if n else 0
    mean_ll = log_likelihood_sum / n if n else 0
    print(f"场次: {n}")
    print(f"Brier（越小越好）: {brier:.4f}")
    print(f"平均对数似然（越大越好）: {mean_ll:.4f}")
    print(f"胜负平命中率: {correct_wdl}/{n} = {correct_wdl/n*100:.1f}%" if n else "胜负平命中率: 0/0")
    print(f"最可能比分命中率: {correct_score}/{n} = {correct_score/n*100:.1f}%" if n else "最可能比分命中率: 0/0")
    print(f"Top-3 比分覆盖率: {in_top3_score}/{n} = {in_top3_score/n*100:.1f}%" if n else "Top-3 比分覆盖率: 0/0")
    print("本回测用于评估长期统计表现（如 Brier、校准），不保证未来单场结果。")


if __name__ == "__main__":
    main()
