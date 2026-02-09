# 赛前预期 xG：数据来源与格式

赛前报告中的「预测概率」需要**赛前预期进球数（xG）**。每场比赛主客队不同，预期 xG 也应不同。本项目支持两种方式提供这些数：

1. **命令行直接填**：`--xg-home 1.2 --xg-away 1.0`
2. **从 CSV 表自动匹配**：`--expected-xg data/expected_xg_teams.csv` 或按场次表，每场/每队可不同，有据可查。

---

## 一、CSV 两种格式

### 1. 按球队（推荐：一次维护整季）

每行一个**球队**，用该队本赛季（或近期）的场均 xG。生成赛前报告时，程序用**主队的主场 xG**、**客队的客场 xG** 作为本场预期。

| 列名 | 说明 |
|------|------|
| team | 队名，与报告一致（如 利兹联、诺丁汉森林），或英文名（需配合 --team-mapping） |
| xg | 该队场均 xG（整体） |
| xg_home | 该队主场场均 xG（可选，无则用 xg） |
| xg_away | 该队客场场均 xG（可选，无则用 xg） |
| season | 可选；多赛季同文件时用，配合 --expected-xg-season |

示例：`data/test/expected_xg_teams.example.csv`；英超 20 队骨架见 `data/test/expected_xg_teams_pl20.example.csv`（可复制为 `expected_xg_teams.csv` 后按 Understat 等替换数值）。

### 2. 按场次

每行**一场比赛**，适合从第三方「单场预测」抄写或自建模型输出。

| 列名 | 说明 |
|------|------|
| round | 轮次 |
| home_team | 主队名 |
| away_team | 客队名 |
| xg_home | 该场主队预期 xG |
| xg_away | 该场客队预期 xG |
| match_code | 可选，竞彩场次（如 周五012），与赛程表联用时可优先按此匹配 |
| xg_ht_home | 可选，该场主队半场预期 xG（用于半全场概率） |
| xg_ht_away | 可选，该场客队半场预期 xG |

示例：`data/test/expected_xg_fixtures.example.csv`

---

## 二、去哪里找这些数（可靠依据）

- **Understat（understat.com）**  
  - 打开联赛页，如 [EPL 2024/25](https://understat.com/league/EPL/2024)，选「Table」→ 有各队 **xG** 列（整体）。  
  - 切换 **home / away** 可看主场、客场 xG。  
  - 把队名和 xG、xg_home、xg_away 抄到「按球队」CSV；队名用报告里的中文名，或英文名并配合 `--team-mapping`。

- **FBref（fbref.com）**  
  - 联赛 → Teams → 有球队 xG 等指标，可按赛季/主客场整理进按球队表。

- **其他**  
  - 任何提供「预期进球」或「xG」的网站（如 FiveThirtyEight、博彩数据站），只要你能拆成**主队预期 xG** 和**客队预期 xG**，就可填入按场次表或折算进按球队表。

---

## 三、命令示例

- 用**按球队表**（利兹联 vs 诺丁汉森林 第 12 轮，表内为中文队名）：  
  `./run.sh pre --home 利兹联 --away 诺丁汉森林 --round 12 --expected-xg data/test/expected_xg_teams.example.csv --injuries data/test/leeds_forest_injuries_20250206.csv`

- 表里是英文队名时，加队名映射：  
  `./run.sh pre --home 利兹联 --away 诺丁汉森林 --round 12 --expected-xg data/expected_xg_teams.csv --team-mapping config/team_name_mapping.example.csv`

- 用**按场次表**：  
  `./run.sh pre --home 利兹联 --away 诺丁汉森林 --round 12 --expected-xg data/test/expected_xg_fixtures.example.csv --injuries data/test/leeds_forest_injuries_20250206.csv`

- 仍可手动覆盖单场：  
  `--xg-home 1.4 --xg-away 1.1` 优先于表；未提供时再查表。

- **批量预测**：`./run.sh predict-today` 默认使用 `data/expected_xg_teams.csv`；输出 `data/<日期>/todays_predictions.csv` 含 **xg_home、xg_away** 列，终端会打印每场使用的 xG（如 `xG 1.70-0.90`），便于核对是否用表。

这样每场比赛的预计进球数都可以来自同一套可靠依据（如 Understat），并按场次或按队自动区分。
