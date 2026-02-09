#!/usr/bin/env python3
"""
用本机浏览器打开五大联赛 2023-24 FBref 赛程页，将每页 HTML 保存到指定目录。
需安装：pip install seleniumbase（项目已有）。若 FBref 仍 403，请改用手动另存为。

用法：
  python scripts/save_fbref_schedule_html.py [--out-dir data/historical/fbref_schedule_html]
"""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent

# 联赛 id -> (文件名, URL)
LEAGUES = [
    ("EPL", "EPL.html", "https://fbref.com/en/comps/9/2023-2024/schedule/2023-2024-Premier-League-Scores-and-Fixtures"),
    ("La_Liga", "La_Liga.html", "https://fbref.com/en/comps/12/2023-2024/schedule/2023-2024-La-Liga-Scores-and-Fixtures"),
    ("Bundesliga", "Bundesliga.html", "https://fbref.com/en/comps/20/2023-2024/schedule/2023-2024-Bundesliga-Scores-and-Fixtures"),
    ("Serie_A", "Serie_A.html", "https://fbref.com/en/comps/11/2023-2024/schedule/2023-2024-Serie-A-Scores-and-Fixtures"),
    ("Ligue_1", "Ligue_1.html", "https://fbref.com/en/comps/13/2023-2024/schedule/2023-2024-Ligue-1-Scores-and-Fixtures"),
]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="用浏览器抓取五大联赛 FBref 赛程页并保存为 HTML")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data" / "historical" / "fbref_schedule_html",
        help="保存 HTML 的目录，默认 data/historical/fbref_schedule_html",
    )
    parser.add_argument("--headless", action="store_true", help="无头模式（可能更容易被 403）")
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from seleniumbase import Driver
    except ImportError:
        print("请先安装 seleniumbase：pip install seleniumbase", file=sys.stderr)
        sys.exit(1)

    driver = Driver(headless=args.headless, uc=True)  # uc=True 使用 undetected 模式，减少 403
    try:
        for league_id, filename, url in LEAGUES:
            out_path = out_dir / filename
            print(f"正在打开 {league_id}: {url[:60]}...")
            driver.get(url)
            time.sleep(2)  # 等待表格/脚本加载
            html = driver.page_source
            if "403" in html[:2000] or "Forbidden" in html[:2000]:
                print(f"  警告: 可能收到 403，仍写入 {out_path.name}，若解析失败请改用手动另存为。")
            out_path.write_text(html, encoding="utf-8")
            print(f"  已保存 -> {out_path}")
        print("全部完成。可执行：python scripts/replace_pl2024_from_fbref_html.py --html-dir", out_dir)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
