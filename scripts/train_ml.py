#!/usr/bin/env python3
"""
训练 ML 模型（胜负平分类）：从历史 CSV 构建特征与标签，训练逻辑回归等，保存模型与特征名。
用法示例：
  python scripts/train_ml.py --historical data/historical/EPL --season 2024 --out config/ml_wdl_model.pkl
  python scripts/train_ml.py --historical data/historical/Combined --league Combined --season 2025
"""
import argparse
import pickle
import sys
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from football_ai.data.historical import load_historical_matches
from football_ai.ml.features import build_dataset, FEATURE_NAMES


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ML model (win/draw/lose) from historical matches")
    parser.add_argument("--historical", type=Path, required=True, help="历史场次 CSV 或目录")
    parser.add_argument("--league", type=str, default=None, help="若 CSV 含 league 列则过滤")
    parser.add_argument("--season", type=int, default=None, help="只使用该赛季；不指定则用全部")
    parser.add_argument("--target", choices=["wdl"], default="wdl", help="目标：wdl=胜负平分类")
    parser.add_argument("--out", type=Path, default=None, help="保存模型路径（.pkl），含 model + feature_names")
    parser.add_argument("--model", choices=["logistic", "rf", "xgb", "lgb"], default="logistic", help="模型类型")
    args = parser.parse_args()

    path = args.historical
    if path.is_dir():
        matches = load_historical_matches(directory=path)
    else:
        matches = load_historical_matches(path=path)

    if not matches:
        print("未加载到任何场次。", file=sys.stderr)
        sys.exit(1)

    if args.league:
        matches = [m for m in matches if (m.get("league") or "").strip() == args.league.strip()]
    if args.season is not None:
        matches = [m for m in matches if int(m.get("season", 0)) == args.season]

    if len(matches) < 20:
        print("场次过少，至少需约 20 场。", file=sys.stderr)
        sys.exit(1)

    X, y, names = build_dataset(matches, target=args.target)
    if X.shape[0] < 10:
        print("有效样本过少（需每场之前有足够历史）。", file=sys.stderr)
        sys.exit(1)

    scaler = None
    X_scaled = X
    if args.model == "logistic":
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = LogisticRegression(max_iter=500, random_state=42)
        model.fit(X_scaled, y)
        artifact = {"model": model, "scaler": scaler, "feature_names": names, "target": args.target, "model_type": "logistic"}
    elif args.model == "rf":
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_scaled, y)
        artifact = {"model": model, "scaler": scaler, "feature_names": names, "target": args.target, "model_type": "rf"}
    elif args.model == "xgb":
        import xgboost as xgb
        model = xgb.XGBClassifier(n_estimators=100, max_depth=6, random_state=42, eval_metric="mlogloss")
        model.fit(X, y)
        artifact = {"model": model, "scaler": None, "feature_names": names, "target": args.target, "model_type": "xgb"}
    elif args.model == "lgb":
        import lightgbm as lgb
        model = lgb.LGBMClassifier(n_estimators=100, max_depth=6, random_state=42, verbose=-1)
        model.fit(X, y)
        artifact = {"model": model, "scaler": None, "feature_names": names, "target": args.target, "model_type": "lgb"}
    else:
        raise ValueError(f"Unknown model: {args.model}")

    out_path = args.out or ROOT / "config" / "ml_wdl_model.pkl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(artifact, f)
    print(f"已保存模型与特征名至 {out_path}，样本数 {X.shape[0]}，特征数 {len(names)}。")


if __name__ == "__main__":
    main()
