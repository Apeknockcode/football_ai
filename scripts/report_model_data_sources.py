#!/usr/bin/env python3
"""
获取当前模型的数据并列出数据来源。
输出：校准参数、历史数据文件、数据源追溯。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONFIG_DIR = ROOT / "config"
HIST_DIR = ROOT / "data" / "historical"

# 数据源定义：{ 文件名模式或目录 : (来源名称, 抓取脚本) }
SOURCE_MAP = {
    "pl_*_understat.csv": ("Understat", "fetch_historical_understat.py"),
    "pl_*_fbref.csv": ("FBref", "fetch_historical_fbref_leagues.py"),
    "pl_*_fotmob.csv": ("FotMob (soccerdata)", "fetch_historical_soccerdata.py"),
    "pl_*_whoscored.csv": ("WhoScored", "fetch_historical_soccerdata_extra.py"),
    "pl_*_fd.csv": ("Football-Data.co.uk", "fetch_historical_football_data_uk.py"),
    "pl_*_sofascore.csv": ("Sofascore", "fetch_historical_sofascore_standalone.py"),
    "pl_*_espn.csv": ("ESPN", "fetch_historical_espn_standalone.py"),
}
# 默认主文件 pl_YYYY.csv：通常来自 Understat 或 merge 合并结果
DEFAULT_SOURCE = "Understat（或 merge 多源合并）"

# 杯赛等特殊联赛的数据源覆盖
LEAGUE_SOURCE_OVERRIDE = {
    "UCL": ("FBref", "fetch_historical_fbref_cups.py"),
    "UEL": ("FBref", "fetch_historical_fbref_cups.py"),
    "FA_Cup": ("FBref", "fetch_historical_fbref_cups.py"),
    "League_Cup": ("FBref", "fetch_historical_fbref_cups.py"),
}


def _match_source(filename: str, league_id: str = "") -> tuple[str, str]:
    """根据文件名和联赛推断数据源。"""
    if league_id and league_id in LEAGUE_SOURCE_OVERRIDE:
        return LEAGUE_SOURCE_OVERRIDE[league_id]
    for pattern, (name, script) in SOURCE_MAP.items():
        star = pattern.index("*")
        prefix, suffix = pattern[:star], pattern[star + 1 :]
        if filename.startswith(prefix.replace("*", "")) and filename.endswith(suffix):
            return name, script
    return DEFAULT_SOURCE, "fetch_historical_understat.py / merge_league_sources.py"


def _count_csv_rows(path: Path) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))
    except OSError:
        return 0


def load_calibration(path: Path) -> dict | None:
    try:
        import re
        import yaml
        raw = path.read_text(encoding="utf-8")
        cal = yaml.safe_load(raw)
        if cal and isinstance(cal, dict):
            m = re.search(r"#\s*基于场次:\s*(\d+)", raw)
            if m:
                cal["_match_count"] = int(m.group(1))
        return cal
    except Exception:
        return None


def main() -> None:
    out_lines: list[str] = []

    def w(s: str = "") -> None:
        out_lines.append(s)
        print(s)

    w("# 模型数据与来源报告")
    w()
    w("## 一、校准参数（calibration_*.yaml）")
    w()

    cal_files = sorted(CONFIG_DIR.glob("calibration_*.yaml"))
    cal_files = [p for p in cal_files if "example" not in p.name.lower()]

    for cal_path in cal_files:
        cal = load_calibration(cal_path)
        if not cal:
            continue
        league_id = cal.get("league", cal_path.stem.replace("calibration_", ""))
        draw_rate = cal.get("draw_rate", 0)
        home_factor = cal.get("home_xg_factor", 1.0)
        xg_scale = cal.get("xg_scale", 1.0)
        n = cal.get("_match_count", "")
        w(f"### {league_id} ({cal_path.name})")
        w(f"- draw_rate（平局率）: {draw_rate:.2%}" if isinstance(draw_rate, (int, float)) else f"- draw_rate: {draw_rate}")
        w(f"- home_xg_factor（主队 xG 乘数）: {home_factor:.4f}" if isinstance(home_factor, (int, float)) else f"- home_xg_factor: {home_factor}")
        w(f"- xg_scale（xG 缩放）: {xg_scale:.4f}" if isinstance(xg_scale, (int, float)) else f"- xg_scale: {xg_scale}")
        if n:
            w(f"- 基于场次: {n}")
        w()

    w("## 二、历史数据文件与来源")
    w()

    # 按目录分组
    dirs_seen: set[str] = set()
    for sub in sorted(HIST_DIR.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_"):
            continue
        league_id = sub.name
        dirs_seen.add(league_id)
        csvs = sorted(sub.glob("*.csv"))
        if not csvs:
            continue
        w(f"### {league_id} — `data/historical/{league_id}/`")
        total = 0
        for fp in csvs:
            n = _count_csv_rows(fp)
            total += n
            src_name, src_script = _match_source(fp.name, league_id)
            w(f"  - {fp.name}: {n} 场 — 来源: {src_name} ({src_script})")
        w(f"  - **小计**: {total} 场")
        if league_id == "Combined":
            w("  - 数据来源: merge_five_leagues.py 合并 EPL、La_Liga、Bundesliga、Serie_A、Ligue_1 的 pl_2024.csv、pl_2025.csv")
        w()

    w("## 三、数据管道概览")
    w()
    w("| 阶段 | 说明 | 脚本/命令 |")
    w("|------|------|-----------|")
    w("| 抓取 | 从 Understat 拉取五大联赛 xG+赛果 | `./run.sh fetch all 2024 2025` |")
    w("| 抓取 | 单联赛 Understat | `./run.sh fetch EPL 2025` |")
    w("| 抓取 | FBref、FotMob 等辅源 | `./run.sh fetch fbref EPL 2025` |")
    w("| 合并 | 同联赛多源合并 | `./run.sh merge EPL 2025` |")
    w("| 合并 | 五大联赛汇总 | `./run.sh merge-five` |")
    w("| 校准 | 生成 calibration_*.yaml | `./run.sh calibrate --league EPL` |")
    w()

    w("## 四、外部数据源")
    w()
    w("| 来源 | 网站 | 用途 |")
    w("|------|------|------|")
    w("| Understat | understat.com | 五大联赛 xG、赛果（主源） |")
    w("| FBref | fbref.com | 五大联赛、杯赛 xG、赛果 |")
    w("| FotMob | soccerdata 库 | 联赛 xG、赛果 |")
    w("| WhoScored | 需 Selenium | 联赛 xG、赛果 |")
    w("| Football-Data.co.uk | football-data.co.uk | 赛果、赔率（无 xG） |")
    w()

    # 写出报告文件
    report_path = ROOT / "docs" / "模型数据与来源报告.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\n已保存报告: {report_path}")


if __name__ == "__main__":
    main()
