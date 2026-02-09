# 历史数据 · 多联赛（第三版）

用于**校准**、**回测**、**赛前报告（近期状态、历史交锋、积分/xPts、Elo）**及 **ML 特征/训练**。先有数据，再校准，再回测，再升级模型。

**当前范围**：仅维护**五大联赛**（EPL、La_Liga、Bundesliga、Serie_A、Ligue_1）及合并数据（Combined）。杯赛数据已移除，待五大联赛做完整后再考虑杯赛。

**2025 赛季**：曾存在过的 2025 年数据已因校验问题全部删除（各联赛 `pl_2025*.csv` 及 `Combined/pl_2025.csv`）。待有可靠数据源后再按需拉取或手工补全。

---

## ⚠️ 当前数据与真实赛果严重不符（必读）

**本目录下现有数据（含 Understat 拉取的 2024 五大联赛）与真实赛果严重不符**，存在大量比分错误、轮次混乱等问题。

- **请勿**将当前 CSV 直接用于：校准、回测、赛前报告中的近期状态/历史交锋/积分/xPts/Elo，以及 ML 训练。
- **建议**：
  1. **替换数据源**：从权威来源重新拉取（见下文「可选数据源」），或使用 FBref/FotMob 等脚本生成新 CSV 后替换。
  2. **逐条核对**：若保留当前文件，须与联赛官网、ESPN、Transfermarkt 等逐场核对比分与轮次，修正后再用。
  3. 完成替换或核对前，仅可将本目录数据用于**格式参考**或**探索性查看**，不得作为分析依据。

**换源方式一（推荐，避免 403）**：用 **FBref 本地 HTML** 覆盖 `pl_2024.csv`：  
1. 在浏览器打开各联赛 2023-24 赛程页（见下方 URL），另存为「完整网页」到同一目录。  
2. 将文件命名为 `EPL.html`、`La_Liga.html`、`Bundesliga.html`、`Serie_A.html`、`Ligue_1.html`。  
3. 执行：`python scripts/replace_pl2024_from_fbref_html.py --html-dir <存放HTML的目录>`  
4. 执行：`./run.sh merge-five` 重新生成 `Combined/pl_2024.csv`  
5. 执行：`./run.sh validate-2024`（或 `./run.sh validate-data --merged-2024`）做**自动化核对**，确保场次数、无重复、轮次与比分范围正确；可选 `--ref data/historical/_common/validation_ref_2024_sample.csv` 与参考样本逐场比对比分。详见 [2024 合并数据核对流程](../docs/历史数据-2024合并数据核对流程.md)。

赛程页 URL（2023-2024）：  
- 英超 https://fbref.com/en/comps/9/2023-2024/schedule/2023-2024-Premier-League-Scores-and-Fixtures  
- 西甲 https://fbref.com/en/comps/12/2023-2024/schedule/2023-2024-La-Liga-Scores-and-Fixtures  
- 德甲 https://fbref.com/en/comps/20/2023-2024/schedule/2023-2024-Bundesliga-Scores-and-Fixtures  
- 意甲 https://fbref.com/en/comps/11/2023-2024/schedule/2023-2024-Serie-A-Scores-and-Fixtures  
- 法甲 https://fbref.com/en/comps/13/2023-2024/schedule/2023-2024-Ligue-1-Scores-and-Fixtures  

**换源方式二（需网络畅通）**：直接拉取（可能遇 403 或 TLS 问题）：FBref `./run.sh fetch fbref EPL 2024`、FotMob `./run.sh fetch fotmob EPL 2024`、Football-Data.co.uk `./run.sh fetch fd EPL 2024`。拉取后需按 [定义与清洗](../docs/历史数据-定义与清洗.md) 核对列格式与比分。

---

## 数据质量与清洗（三步流程）

详见 → [docs/历史数据-定义与清洗.md](../docs/历史数据-定义与清洗.md)。

- **轮次 (round)**：当前 `round` **并非**严格按「连续、唯一的比赛周」编号，存在轮次混乱、与官方赛程不一致等风险；不应未经校验即用于「近 N 场」「第 R 轮前」等逻辑。
- **比分**：须与联赛官网、ESPN、Transfermarkt 等逐条核对，与真实赛果一致后再用于校准/回测。
- **建议**：优先为每场补全 **match_date**（YYYY-MM-DD），以比赛日为排序与索引的首要依据；并完成「来源核对 → 建立正确索引 → 核对比分」三步清洗（见上链文档）。

## 目录结构

- **按赛事分目录**：`data/historical/{league_id}/`，如 `data/historical/EPL/`、`data/historical/La_Liga/`。联赛 id 见 `config/leagues.yaml`。
- **五大联赛合并**：`data/historical/Combined/`，由 `scripts/merge_five_leagues.py` 生成，用于统一校准。
- **通用资源**：`data/historical/_common/` 放示例与模板（`sample_pl.csv`、`pl_2024_template.csv`），供格式参考或复制后填数。
- 杯赛配置与抓取见 `config/cups.yaml`、[docs/杯赛历史数据-如何维护.md](../docs/杯赛历史数据-如何维护.md)，当前不在此目录下存放杯赛 CSV。

## 数据质量与无效场次

- **无效场次**：`goals_home=0` 且 `goals_away=0` 且 `xg_home=0` 且 `xg_away=0` 的行，多为**未开赛赛程**或数据缺失（如 2025 赛季未来场次），非真实 0-0。
- **自动过滤**：`load_historical_matches` 会排除上述无效行，校准与回测仅使用有效场次。
- **校验**：`python scripts/validate_historical_data.py` 可统计无效场次数量。
- **报告**：生成赛前报告时加 `--historical data/historical/EPL`（或单文件）及可选 `--season 2025`，可输出近期状态、历史交锋、积分与 xPts、Elo；见 `docs/可补充清单.md`。
- **ML 训练**：`python scripts/train_ml.py --historical data/historical/EPL --season 2024 --out config/ml_wdl_model.pkl`（需安装 `scikit-learn`）。

## 文件格式

- CSV 编码：UTF-8。

## 列定义（必选与推荐）

### 必选列

| 列名 | 说明 |
|------|------|
| season | 赛季年，如 2023、2024 |
| round | 轮次/比赛周编号。**注意**：仅当与官方「连续、唯一」的比赛周一致时才可信；否则仅作占位，排序应以 match_date 为准（见 [定义与清洗](../docs/历史数据-定义与清洗.md)）。 |
| home_team | 主队名（与报告/映射一致） |
| away_team | 客队名 |
| xg_home | 主队 xG |
| xg_away | 客队 xG |
| goals_home | 主队实际进球（须与权威来源核对） |
| goals_away | 客队实际进球 |

### 强烈推荐列（用于正确排序与清洗）

| 列名 | 说明 |
|------|------|
| **match_date** | 比赛日，格式 YYYY-MM-DD。作为时间排序与「近 N 场」「第 R 轮前」的**首要依据**；无此项时退化为 (season, round)，但 round 未校验时可能出错。 |

### 可选列（用于半全场/进阶）

| 列名 | 说明 |
|------|------|
| ht_goals_home | 半场主队进球 |
| ht_goals_away | 半场客队进球 |

## 示例与模板

- 示例：`_common/sample_pl.csv`（仅 4 场，用于格式参考）。
- 一季模板：`_common/pl_2024_template.csv`（仅表头，可复制到某联赛目录后按行粘贴整季数据）。
- **杯赛模板**：`_common/cup_season_template.csv`（表头 + 2 行示例），复制到 `data/historical/UCL/` 或 `FA_Cup/` 等后改名为 `pl_YYYY.csv` 再按场次填写。
- **带日期的表头示例**：`season,match_date,round,home_team,away_team,xg_home,xg_away,goals_home,goals_away`（`match_date` 为 YYYY-MM-DD，用于正确排序，见 [定义与清洗](../docs/历史数据-定义与清洗.md)）。
- **联赛详细步骤**：见 [docs/历史数据-一季英超如何添加.md](../docs/历史数据-一季英超如何添加.md)（数据来源、队名统一、校准与回测命令）。
- **杯赛如何维护**：见 [docs/杯赛历史数据-如何维护.md](../docs/杯赛历史数据-如何维护.md)（目录、CSV 格式、轮次约定、数据来源、校准与回测命令）。

## 从 Understat 抓取（可选）

抓取结果写入 `data/historical/{league_id}/pl_YYYY.csv`，联赛见 `config/leagues.yaml`。

- **推荐**（项目根目录）：
  ```bash
  ./run.sh fetch 2024 2025              # EPL 多赛季
  ./run.sh fetch La_Liga 2024 2025      # 西甲多赛季
  ```
- **直接调脚本**（需安装 `understatapi`）：
  ```bash
  python scripts/fetch_historical_understat.py --league EPL --season 2024 2025
  python scripts/fetch_historical_understat.py --league La_Liga --season 2024
  ```
- **无法直连时**：浏览器打开 Understat 选联赛与赛季后「另存为」完整网页，再执行：
  ```bash
  python scripts/fetch_historical_understat.py --league EPL --season 2024 --html 你保存的网页.html
  ```
- 若本机 SSL 证书报错，可设 `UNDERSTAT_NO_SSL_VERIFY=1`（仅限本地）。请遵守网站使用条款与访问频率，仅供个人/教育用途。

## 杯赛从 FBref 抓取（可选）

- **命令**：`./run.sh fetch cup UCL 2025`、`./run.sh fetch cup UEL 2024 2025` 等，写入 `data/historical/UCL/pl_2025.csv`。
- 遇 403 时可在浏览器打开 [FBref 欧冠赛程](https://fbref.com/en/comps/8/2024-2025/schedule/2024-2025-Champions-League-Scores-and-Fixtures) 等，另存为完整网页后：`python scripts/fetch_historical_fbref_cups.py --cup UCL --season 2025 --html 网页.html`。
- 详见 [docs/杯赛历史数据-如何维护.md](../docs/杯赛历史数据-如何维护.md)。
