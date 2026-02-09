# 五大联赛 2023-24 赛程页 · 另存为 HTML 说明

方式一（推荐）：本机运行脚本自动保存（需已安装 seleniumbase）
  在项目根目录执行：python scripts/save_fbref_schedule_html.py --out-dir data/historical/fbref_schedule_html
  脚本会用浏览器依次打开 5 个链接并把每页 HTML 保存到本目录，文件名已按联赛命名。

方式二：手动另存为
  请用浏览器依次打开下面 5 个链接，每个页面使用「另存为」→ 选择「网页，全部」或「完整网页」，
  保存到本目录（fbref_schedule_html），并按下表「另存为文件名」命名。

| 联赛   | 另存为文件名   | 链接 |
|--------|----------------|------|
| 英超   | EPL.html       | https://fbref.com/en/comps/9/2023-2024/schedule/2023-2024-Premier-League-Scores-and-Fixtures |
| 西甲   | La_Liga.html   | https://fbref.com/en/comps/12/2023-2024/schedule/2023-2024-La-Liga-Scores-and-Fixtures |
| 德甲   | Bundesliga.html| https://fbref.com/en/comps/20/2023-2024/schedule/2023-2024-Bundesliga-Scores-and-Fixtures |
| 意甲   | Serie_A.html   | https://fbref.com/en/comps/11/2023-2024/schedule/2023-2024-Serie-A-Scores-and-Fixtures |
| 法甲   | Ligue_1.html   | https://fbref.com/en/comps/13/2023-2024/schedule/2023-2024-Ligue-1-Scores-and-Fixtures |

完成后在本项目根目录执行：
  python scripts/replace_pl2024_from_fbref_html.py --html-dir data/historical/fbref_schedule_html
  ./run.sh merge-five
