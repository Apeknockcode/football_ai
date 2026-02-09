# 测试与示例数据

本目录存放用于**测试**和**文档示例**的数据文件，便于新用户跑通流程，无需删除。

| 文件 | 用途 |
|------|------|
| `expected_xg_teams.example.csv` | 按球队的预期 xG 示例（利兹联/诺丁汉森林等） |
| `expected_xg_teams_pl20.example.csv` | 英超 20 队骨架，可复制为 `../expected_xg_teams.csv` 后填数 |
| `expected_xg_fixtures.example.csv` | 按场次的预期 xG 示例 |
| `sample_fixtures.csv` | 赛程表示例（含比赛时间、轮次、主客队） |
| `sample_statsbomb_events.json` | StatsBomb 事件最小示例，用于赛后报告 |
| `leeds_forest_injuries_20250206.csv` | 伤停表示例 |

正式使用的数据（如 `../expected_xg_teams.csv`、`../todays_matches.csv` 等）请放在 `data/` 根目录或相应子目录。
