"""
ML 预测器：加载 train_ml 保存的 pkl，对单场特征输出主胜/平/客胜概率。
与 get_predictions（Poisson）输出结构兼容，供 predict_batch / backtest 双轨使用。
"""
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from football_ai.ml.features import FEATURE_NAMES, build_feature_row


def load_artifact(path: Path | str) -> dict[str, Any]:
    """加载 train_ml 保存的 pkl。返回含 model, scaler, feature_names, model_type 的字典。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"模型文件不存在: {path}")
    import pickle
    with open(path, "rb") as f:
        artifact = pickle.load(f)
    if "model" not in artifact or "feature_names" not in artifact:
        raise ValueError("pkl 需含 model 与 feature_names")
    return artifact


def predict_wdl(
    match: dict[str, Any],
    past_matches: list[dict[str, Any]],
    artifact: dict[str, Any],
    n_form: int = 5,
    n_h2h: int = 10,
) -> dict[str, float]:
    """
    对单场比赛用 ML 模型输出胜负平概率。
    :param match: 本场，含 season, round, home_team, away_team, xg_home, xg_away 等
    :param past_matches: 该场之前的历史场次（同联赛/同赛季，已排序）
    :param artifact: load_artifact() 的返回值
    :return: {"主胜": float, "平": float, "客胜": float}，和为 1
    """
    model = artifact["model"]
    scaler = artifact.get("scaler")
    feature_names = artifact.get("feature_names") or FEATURE_NAMES

    row = build_feature_row(match, past_matches, n_form=n_form, n_h2h=n_h2h)
    X = np.array([[row.get(k, 0.0) for k in feature_names]], dtype=np.float64)
    if scaler is not None:
        X = scaler.transform(X)
    X_df = pd.DataFrame(X, columns=feature_names)
    proba = model.predict_proba(X_df)[0]
    # 训练时 target wdl: 0=客胜 1=平 2=主胜，predict_proba 列顺序即 0,1,2
    return {
        "客胜": float(proba[0]),
        "平": float(proba[1]),
        "主胜": float(proba[2]),
    }


def _get_win_by_one_ratio() -> float:
    """从 config/settings.yaml 读取 predictions.win_by_one_ratio，默认 0.55。"""
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    if not cfg_path.exists():
        return 0.55
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return float((data.get("predictions") or {}).get("win_by_one_ratio", 0.55))
    except Exception:
        return 0.55


def wdl_to_most_likely_score(wdl: dict[str, float]) -> str:
    """由胜负平概率取最大可能结果，给出最可能比分（启发式，无比分分布）。"""
    p_win = wdl.get("主胜") or 0.0
    p_draw = wdl.get("平") or 0.0
    p_lose = wdl.get("客胜") or 0.0
    if p_win >= p_draw and p_win >= p_lose:
        return "1-0"
    if p_lose >= p_win and p_lose >= p_draw:
        return "0-1"
    return "1-1"


def wdl_to_handicap(
    wdl: dict[str, float],
    handicap_line: float | None,
) -> dict[str, Any]:
    """
    用 ML 的胜负平概率按让球线换算让胜/让平/让负（无比分分布时的近似）。
    主让 0.5：让胜=主胜、让平=0、让负=平+客胜（精确）；
    主让 1：让负=平+客胜，主胜按比例拆成让胜(净胜2+)/让平(净胜1)；
    主受让 1：让胜=主胜+平+客胜中主输1球，让平/让负由客胜拆成主输1球/主输2+。
    """
    p_win = wdl.get("主胜") or 0.0
    p_draw = wdl.get("平") or 0.0
    p_lose = wdl.get("客胜") or 0.0
    if handicap_line is None or handicap_line == 0.5:
        # 主让 0.5：让胜=主胜，让平=0，让负=平+客胜
        return {
            "让球": "主让 0.5",
            "让胜": p_win,
            "让平": 0.0,
            "让负": p_draw + p_lose,
        }
    if handicap_line <= -1:
        # 主让 1：让负=平+客胜；主胜拆成 让平=主胜*λ(一球小胜), 让胜=主胜*(1-λ)
        r = _get_win_by_one_ratio()
        return {
            "让球": "主让 1",
            "让胜": p_win * (1 - r),
            "让平": p_win * r,
            "让负": p_draw + p_lose,
        }
    if handicap_line >= 1:
        # 主受让 1：让胜=主胜+平+客胜中主输1球，让平=客胜中主输1球，让负=客胜中主输2+
        r = _get_win_by_one_ratio()
        return {
            "让球": "主受让 1",
            "让胜": p_win + p_draw + p_lose * r,
            "让平": p_lose * r,
            "让负": p_lose * (1 - r),
        }
    # 其他让球数暂按主让 0.5 处理
    return {
        "让球": "主让 0.5",
        "让胜": p_win,
        "让平": 0.0,
        "让负": p_draw + p_lose,
    }


def _most_likely_score_ml(wdl: dict[str, float], match: dict[str, Any]) -> str:
    """
    有 xG 时用 Poisson 在 ML 胜负平对应类别内选最可能比分；无 xG 时用 1-0/0-1/1-1 启发式。
    """
    xh, xa = match.get("xg_home"), match.get("xg_away")
    try:
        xg_h = float(xh) if xh is not None and str(xh).strip() != "" else None
        xg_a = float(xa) if xa is not None and str(xa).strip() != "" else None
    except (TypeError, ValueError):
        xg_h = xg_a = None
    if xg_h is not None and xg_a is not None:
        from football_ai.predictions.service import most_likely_score_given_xg_and_wdl
        return most_likely_score_given_xg_and_wdl(xg_h, xg_a, wdl)
    return wdl_to_most_likely_score(wdl)


def predictions_from_ml(
    home_team: str,
    away_team: str,
    round_: int,
    match: dict[str, Any],
    past_matches: list[dict[str, Any]],
    artifact_path: Path | str,
    handicap_line: float | None = None,
) -> dict[str, Any]:
    """
    用 ML 模型生成与 get_predictions 同结构的预测字典（主含 win_draw_lose；handicap/score 由 WDL 推导）。
    有 xG 时比分由 Poisson 在胜负平对应类别内取最可能比分，无 xG 时为 1-0/0-1/1-1 启发式。
    供 predict_batch / backtest 使用。
    """
    from football_ai.predictions.service import DISCLAIMER_ZH

    artifact = load_artifact(artifact_path)
    wdl = predict_wdl(match, past_matches, artifact)
    out: dict[str, Any] = {
        "available": True,
        "disclaimer_zh": DISCLAIMER_ZH,
        "win_draw_lose": wdl,
        "handicap": wdl_to_handicap(wdl, handicap_line),
        "half_full": None,
        "score": {"最可能比分": _most_likely_score_ml(wdl, match), "其他": []},
        "summary_zh": "（基于 ML 模型胜负平概率，仅供参考；不构成投注建议。）",
    }
    return out
