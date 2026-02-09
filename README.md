# Football AI · 足球分析

基于《产品与分析规格-第一版》的 AI 足球分析项目：**战术 + 报告 + 伤停 + 政治**。不知道下一步怎么做时，请看 [docs/下一步指南.md](docs/下一步指南.md)。（赛事/国家、纪律/裁判、舆论/叙事、俱乐部/帅位），面向英超、中文报告、内部分析师与球迷。

## 功能范围（第一版）

- **战术**：阵型、压迫、转换、控球区域、强弱侧等，基于事件/阵型数据（建议 StatsBomb）。
- **伤停**：缺阵、复出、累计黄牌；当前以非结构化来源为主，预留结构化接口。
- **政治**：赛事背景、纪律/裁判、舆论/叙事、俱乐部/帅位（可分阶段实现）。
- **报告**：赛前/赛后中文报告，完整版（分析师）+ 摘要版（球迷）；模板 + 可选 LLM 润色。

详见 [docs/产品与分析规格-第一版.md](docs/产品与分析规格-第一版.md)。

## 项目结构

```
football_ai/
├── config/                 # 配置（联赛、数据源、报告选项）
├── football_ai/             # 主包
│   ├── data/                # 数据接入：事件、伤停、赛程
│   ├── tactics/             # 战术：指标、阵型、小结
│   ├── injuries/            # 伤停服务（含预留接口）
│   ├── politics/            # 政治四块：赛事、纪律/裁判、舆论、帅位
│   └── report/              # 报告：组装、模板、可选 LLM
├── docs/                    # 规格与文档
├── tests/                   # 测试
├── requirements.txt
└── README.md
```

## 环境与运行

### 方式一：启动脚本（推荐）

```bash
# Mac / Linux：首次会创建 .venv 并安装依赖，之后直接生成示例赛前报告
./run.sh

# 自定义参数（将参数原样传给 CLI）
./run.sh pre --home 阿森纳 --away 切尔西 --round 15
./run.sh pre --home 曼联 --away 利物浦 --round 28 --referee 奥利弗 --out report.txt
./run.sh post --home 曼联 --away 利物浦 --round 28 --out report_post.txt
```

```bat
REM Windows
scripts\run.bat
scripts\run.bat pre --home 曼联 --away 利物浦 --round 28 --out report.txt
```

### 方式二：手动安装后运行

```bash
# 建议 Python 3.10+
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .            # 或 pip install -r requirements.txt

# 生成报告
python -m football_ai.cli --help
python -m football_ai.cli pre --home 曼联 --away 利物浦 --round 28
```

## 第二版：战术事件数据（已实现）

- **数据源**：StatsBomb，单场 JSON 文件（见 [docs/第二版-战术数据接入-范围.md](docs/第二版-战术数据接入-范围.md)）。
- **报告中的真实指标**：控球率（按事件 duration）、xG、射门次数，来自事件数据时会在「战术复盘」中明确写出。
- **使用方式**：传入 `--events` 指向 StatsBomb 单场 JSON，可选 `--team-mapping` CSV（`statsbomb_name, report_name`）将英文队名映射为中文。

```bash
# 用示例事件生成赛后报告（含控球率、xG、射门）
./run.sh post --home 巴萨 --away 阿拉维斯 --round 10 \
  --events data/test/sample_statsbomb_events.json \
  --team-mapping config/team_name_mapping.example.csv
```

## 预测与赛前预期 xG（已实现）

- **赛后/赛前报告中的【预测】**：有本场事件数据时用实际 xG 算胜负平/让球/比分/半全场概率；**赛前无事件**时可用「赛前预期 xG」推算。
- **赛前预期 xG 来源**：命令行 `--xg-home` / `--xg-away`，或 CSV 表 `--expected-xg`（按场次或按球队，见 [docs/赛前预期xG-数据来源与格式.md](docs/赛前预期xG-数据来源与格式.md)）。表内队名可与报告一致（中文）或英文（配合 `--team-mapping`）。
- **伤停对预测的微调**：提供 `--injuries` 时，会按伤停人数对预期 xG 做小幅下调后再算概率，加伤停与不加伤停的预测会有区别。
- **校准**：若存在 `config/calibration_pl.yaml`（可由 `scripts/calibrate_pl.py` 从历史数据生成），预测时会自动应用主队系数与 xG 缩放。
- **批量预测与 ML（五大联赛）**：`scripts/predict_batch.py` 支持 `--model poisson | ml | ensemble`。不指定 `--ml-model` 时，会按赛程 CSV 中的 `league_id` 从 `artifacts/` 自动选用对应联赛的 XGB 模型（如 `xgb_epl_2024.pkl`、`xgb_la_liga_2024.pkl` 等），并从 `--historical`（目录，如 `data/historical`）下按联赛子目录加载历史数据，实现「都用 ML」混合联赛一次跑完。`./run.sh predict-today` 默认使用 **`data/expected_xg_teams.csv`** 作为预期 xG 表；输出 CSV（如 `data/<日期>/todays_predictions.csv`）包含 **xg_home、xg_away** 列，便于核对每场实际使用的预期 xG。
- **盘口参考**：若赛程 CSV 含主胜/平/客胜赔率（列名 `odds_home` / `odds_draw` / `odds_away` 或 `主胜` / `平` / `客胜`），可在 `config/settings.yaml` 中设置 `predictions.odds_blend_weight`（如 `0.2` 表示 20% 参考赔率隐含概率）。最终胜负平概率 = (1 − 权重) × 模型概率 + 权重 × 赔率隐含概率（归一化）；未填赔率或权重为 0 时不参与计算。
- **自动拉取盘口**：运行 `scripts/fetch_odds.py --csv data/<日期>/todays_matches.csv` 可从 [The Odds API](https://the-odds-api.com) 拉取五大联赛 1X2 赔率并合并到赛程 CSV。需设置环境变量 `THE_ODDS_API_KEY`（免费注册约 500 次/月）。获取赛程后也可用 `scripts/fetch_todays_fixtures.py --date YYYY-MM-DD --fetch-odds` 一次完成赛程+盘口；桌面端「今日预测」页提供「拉取盘口」按钮。一键流程：`./run.sh today-full [--date YYYY-MM-DD]`（拉赛程 → 若有 THE_ODDS_API_KEY 则拉盘口 → 批量预测）。

```bash
# 赛前报告：预期 xG 表 + 伤停（表不存在时会用 data/test/expected_xg_teams.example.csv）
./run.sh pre --home 利兹联 --away 诺丁汉森林 --round 12 \
  --expected-xg data/expected_xg_teams.csv \
  --team-mapping config/team_name_mapping.example.csv \
  --injuries data/test/leeds_forest_injuries_20250206.csv
```

## 伤停、赛程与竞彩场次

- **伤停**：CSV 列 `team, player, reason`（reason 如：受伤、出战成疑、复出、其他原因），`--injuries` 指向该文件即可在报告中展示并在预测中微调 xG。
- **赛程（比赛时间）**：提供 `--fixtures` 赛程表（CSV/JSON，含主客队、轮次、date、time），报告中的比赛时间从表中匹配本场后读取。赛程表可含 `match_code`/竞彩场次列。
- **竞彩场次**：使用 `--match-code 周五012` 且 `--fixtures` 指向含 `match_code` 的赛程表时，可自动解析主客队、轮次与时间，无需单独填 `--home`/`--away`/`--round`。

## 历史数据、校准与回测（第三版 · 多赛事）

- **联赛**：`config/leagues.yaml`；**杯赛**：`config/cups.yaml`（足总杯、欧冠、欧联、联赛杯等），`--league` 可传联赛或杯赛 id。
- **历史场次表**：`data/historical/{competition_id}/` 下 CSV（如 EPL、UCL），列格式见 [data/historical/README.md](data/historical/README.md)。杯赛暂无自动抓取，可手工维护。**⚠️ 当前目录内数据已确认与真实赛果严重不符，请勿直接用于校准/回测，须替换为权威来源或逐条核对后再用。**
- **拉取数据**：`./run.sh fetch 2024 2025` 拉取 EPL；`./run.sh fetch La_Liga 2024 2025` 拉取西甲；写入 `data/historical/{id}/pl_YYYY.csv`（需 understatapi，仅联赛）。
- **校准**：`./run.sh calibrate [--league EPL]`，写入 `config/calibration_{id}.yaml`；杯赛若有历史 CSV 也可校准。
- **回测**：`./run.sh backtest [--league EPL]`。
- **模型数据与来源报告**：`./run.sh report-sources` → 输出校准参数、历史数据文件、数据源追溯，保存至 `docs/模型数据与来源报告.md`。
- **赛前/赛后**：`./run.sh pre --league EPL --home 阿森纳 --away 切尔西 --round 15` 或 `--league UCL` 等；杯赛展示如「本场为欧冠1/8决赛」。
- **杯赛预测**：先导入杯赛历史数据（如 `data/historical/UCL/pl_2024.csv`、`pl_2025.csv`），再对该赛事做一次校准（`python scripts/calibrate_pl.py --league UCL` 生成 `config/calibration_UCL.yaml`），之后用 `--league UCL` 生成赛前报告即可用欧冠校准做胜负平/比分概率；预期 xG 可用 `--xg-home`/`--xg-away` 或 `--expected-xg` CSV（格式同联赛：round, home_team, away_team, xg_home, xg_away）。

## 测试

```bash
python -m unittest tests.test_predictions tests.test_expected_xg tests.test_calibrate_backtest tests.test_report tests.test_tactics tests.test_politics -v
```

## 实现优先级（规格建议）

1. ~~战术数据管道 + 基础指标（英超、StatsBomb）~~（第二版已完成）
2. 伤停模块（试点 + 预留接口）
3. 政治 · 赛事/国家 + 纪律/裁判
4. 报告生成（整合战术+伤停+政治，仅中文）
5. 政治 · 舆论/叙事、俱乐部/帅位

## 常见问题 / 故障排除

### NumPy/Pandas：`mach-o file, but is an incompatible architecture (have 'arm64', need 'x86_64')`

桌面应用或当前运行 Python 的进程是 **x86_64**（如通过 Rosetta 或 Intel 版应用启动），而 `.venv` 里的 numpy/pandas 是按 **arm64** 安装的，会导致导入失败。解决：用与「实际运行脚本时相同架构」的 Python 重建虚拟环境并重装依赖。

- **若报错里写的是 need 'x86_64'**（当前进程是 x86_64，需要 x86_64 的包）：

  ```bash
  cd /path/to/football_ai
  arch -x86_64 python3 -m venv .venv --clear
  .venv/bin/pip install -r requirements.txt
  .venv/bin/pip install -e .
  ```

- **若报错是 need 'arm64'**（当前进程是 arm64，需要 arm64 的包）：用本机默认 Python 重建即可：

  ```bash
  python3 -m venv .venv --clear
  .venv/bin/pip install -r requirements.txt
  .venv/bin/pip install -e .
  ```

重建后，用同一环境跑校准/拉取（终端或桌面应用）即可。

## 许可与合规

- 第一版不做预测、博彩、多语言；政治表述需可追溯、不做价值判断。见规格文档「第一版不做啥」。
