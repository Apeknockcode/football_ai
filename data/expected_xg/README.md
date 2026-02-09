# 预期 xG 数据目录

用于存放按赛季或按联赛的预期 xG 表（按球队或按场次 CSV）。格式与列说明见 [docs/赛前预期xG-数据来源与格式.md](../../docs/赛前预期xG-数据来源与格式.md)，数据整合思路见 [docs/数据采集与整合.md](../../docs/数据采集与整合.md)。

## 预测时如何使用

- **默认按球队表**：项目根目录下的 **`data/expected_xg_teams.csv`** 为默认预期 xG 表；`./run.sh predict-today` 会使用该表。输出文件 `data/<日期>/todays_predictions.csv` 包含 **xg_home、xg_away** 列，便于核对每场实际使用的 xG。
- **批量预测**：在 `scripts/predict_batch.py` 中加上 `--expected-xg <本目录或项目下的 CSV 路径>`（不指定时可用默认表）；若表为按球队格式且多赛季，可加 `--expected-xg-season 2024` 指定赛季年。未在赛程 CSV 中填写的 `xg_home`/`xg_away` 会从该表按主客队或按场次匹配。
- **单场报告**：`./run.sh pre` 支持 `--expected-xg`、`--team-mapping`，见 [赛前预期xG-数据来源与格式](../../docs/赛前预期xG-数据来源与格式.md) 第三节命令示例。

有预期 xG 时，Poisson 的胜负平/让球/比分和 ML 的「最可能比分」都会更合理；缺 xG 时程序会用 `--default-xg`（默认 1.0）或 0.5/0.5，信息量较低。

## 拉取脚本

`scripts/fetch_expected_xg_understat.py` 可从 Understat 拉取并写入本目录或项目根下 `expected_xg_teams.csv`（需按实际队名与赛程对齐）。
