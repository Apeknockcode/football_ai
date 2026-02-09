#!/usr/bin/env python3
"""
赔率快照：按日或按场次将赔率写入 data/odds/ 目录，供时序与价值判断使用。
格式见 docs/数据采集与整合.md（date, home_team, away_team, round, odds_home, odds_draw, odds_away 等）。

本脚本为占位实现：支持从已有 CSV 按日期合并/复制到 data/odds/<date>.csv，
或按模板生成空 CSV 供人工填写。若接入稳定数据源，可在此扩展拉取逻辑。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ODDS_DIR = ROOT / "data" / "odds"

ODDS_HEADERS = ["date", "home_team", "away_team", "round", "match_code", "odds_home", "odds_draw", "odds_away"]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="赔率快照：写入 data/odds/ 或从已有 CSV 按日期整理")
    parser.add_argument("--date", type=str, default=None, help="日期 YYYY-MM-DD；不指定则用今天")
    parser.add_argument("--in-csv", type=Path, default=None, help="已有赔率 CSV，将按 date 列过滤或整表复制到 data/odds/<date>.csv")
    parser.add_argument("--init-only", action="store_true", help="仅初始化 data/odds/ 目录并写出示例表头 CSV（空数据）")
    args = parser.parse_args()

    from datetime import date
    today = date.today().isoformat()
    target_date = (args.date or today).strip()

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ODDS_DIR / f"{target_date.replace('-', '')}.csv"

    if args.init_only:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ODDS_HEADERS)
            w.writeheader()
        print(f"已初始化 {out_path}（空表，可人工填写或由其他脚本写入）。")
        print("格式列：date, home_team, away_team, round, match_code, odds_home, odds_draw, odds_away")
        return

    if args.in_csv and args.in_csv.exists():
        rows_in = []
        with open(args.in_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or ODDS_HEADERS
            for r in reader:
                r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
                row_date = (r.get("date") or "").strip()[:10]
                if row_date == target_date or not row_date:
                    rows_in.append(r)
        if not rows_in:
            print(f"输入 CSV 中无 date={target_date} 的行，写出空表。", file=sys.stderr)
        out_headers = [c for c in ODDS_HEADERS if c in (headers or [])] or ODDS_HEADERS
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_headers, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows_in)
        print(f"已写入 {len(rows_in)} 行至 {out_path}。")
        return

    # 无 --in-csv 且非 init-only：写出空表并提示
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ODDS_HEADERS)
        w.writeheader()
    print(f"已创建空表 {out_path}。请人工填写或使用 --in-csv 指定已有 CSV。")


if __name__ == "__main__":
    main()
