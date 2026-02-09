#!/usr/bin/env python3
"""
根据 data/historical/{id}/*.csv 计算校准参数，写入 config/calibration_{id}.yaml。
支持联赛（config/leagues.yaml）与杯赛（config/cups.yaml）。先数据 → 再校准 → 再回测。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from football_ai.data.historical import load_historical_matches
from football_ai.leagues import get_calibration_path, get_competition, get_historical_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="赛事校准：从历史数据生成 calibration_{id}.yaml（联赛或杯赛）")
    parser.add_argument("--league", type=str, default="EPL", help="赛事 id：联赛见 config/leagues.yaml，杯赛见 config/cups.yaml（如 UCL）")
    parser.add_argument(
        "--historical",
        type=Path,
        default=None,
        help="历史数据目录或单个 CSV 路径；不指定时用 data/historical/{league_id}/",
    )
    parser.add_argument("--out", type=Path, default=None, help="输出 YAML 路径；不指定时用 config/calibration_{league_id}.yaml")
    args = parser.parse_args()

    league_id = (args.league or "EPL").strip()
    comp = get_competition(league_id)
    if not comp:
        print(f"未找到赛事配置: {league_id}（请检查 config/leagues.yaml 与 config/cups.yaml）。", file=sys.stderr)
        sys.exit(1)

    hist_path = args.historical
    if hist_path is None:
        hist_dir = get_historical_dir(league_id)
        if not hist_dir.exists() and league_id == "EPL":
            hist_dir = ROOT / "data" / "historical"
        hist_path = hist_dir
    out_path = args.out or get_calibration_path(league_id)

    if hist_path.is_file():
        matches = load_historical_matches(path=hist_path)
    else:
        matches = load_historical_matches(directory=hist_path)

    if not matches:
        print(f"未找到历史场次数据，请将 CSV 放入 data/historical/{league_id}/ 或指定 --historical。", file=sys.stderr)
        sys.exit(1)

    n = len(matches)
    n_draw = sum(1 for m in matches if m["goals_home"] == m["goals_away"])
    draw_rate = n_draw / n if n else 0.25

    sum_xg_h = sum(m["xg_home"] for m in matches)
    sum_xg_a = sum(m["xg_away"] for m in matches)
    sum_goals_h = sum(m["goals_home"] for m in matches)
    sum_goals_a = sum(m["goals_away"] for m in matches)
    total_xg = sum_xg_h + sum_xg_a
    total_goals = sum_goals_h + sum_goals_a
    xg_scale = total_goals / total_xg if total_xg > 0 else 1.0

    # 主队 xG 乘数：使 (主队实际/主队xG) 与 (客队实际/客队xG) 的比值体现主队优势
    rate_h = sum_goals_h / sum_xg_h if sum_xg_h > 0 else 1.0
    rate_a = sum_goals_a / sum_xg_a if sum_xg_a > 0 else 1.0
    home_xg_factor = rate_h / rate_a if rate_a > 0 else 1.0
    # 限制在合理范围
    home_xg_factor = max(0.9, min(1.15, home_xg_factor))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# {comp.get('name_zh', league_id)} 校准参数（由 scripts/calibrate_pl.py 根据历史数据生成）
league: {league_id}
draw_rate: {draw_rate:.4f}
home_xg_factor: {home_xg_factor:.4f}
xg_scale: {xg_scale:.4f}
# 基于场次: {n}
"""
    out_path.write_text(content, encoding="utf-8")
    print(f"已写入 {out_path}（基于 {n} 场）：draw_rate={draw_rate:.2%}, home_xg_factor={home_xg_factor:.4f}, xg_scale={xg_scale:.4f}")


if __name__ == "__main__":
    main()
