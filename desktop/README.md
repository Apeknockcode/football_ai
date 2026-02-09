# Football AI 桌面应用（简化版）

Tauri 2 桌面壳 + 现有 Python 后端，仅本地使用、不上线。界面采用标签页，常用功能前置，高级功能收在「设置」中。

## 前提

- 已安装 [Rust](https://rustup.rs/) 和 [Node.js](https://nodejs.org/)（用于 Tauri CLI）
- 本仓库已配置好 Python 环境：在**项目根目录**执行过 `./run.sh` 或 `pip install -e .`，存在 `.venv` 和 `data/expected_xg_teams.csv` 等

## 启动方式

**请从 football_ai 项目根目录进入 desktop 再启动**，这样「使用建议路径」会指向项目根：

```bash
cd /path/to/football_ai
cd desktop
npm install
npm run dev
```

首次运行 `npm run dev` 时，Rust 会下载并编译依赖，可能需要几分钟，属正常现象。

若从其他目录启动，在应用内顶部或「设置」中填写/使用建议路径，指向 football_ai 仓库根目录（含 `run.sh`、`data`、`config` 的目录）。

## 界面说明

- **顶部**：应用标题 + 项目根目录（可选），点「使用建议路径」自动填入。
- **标签页**：
  - **赛前报告**：主队、客队、轮次、联赛、赛季 → 生成赛前报告。
  - **今日预测**：选日期 → 运行预测；可选展开「上传图片并识别」做截图 OCR。
  - **预测结果**：选日期 → 加载并表格展示 `todays_predictions.csv`。
  - **赛后报告**：主队、客队、轮次 → 生成赛后报告。
  - **设置**：项目路径、拉取/合并五大联赛、校准/回测、校验数据、内置浏览器；底部可展开「每日流程说明」。

## 功能对应

- 赛前报告：`football_ai.cli pre`
- 今日预测：`scripts/predict_batch.py`，使用 `data/<日期>/todays_matches.csv`，结果写入 `todays_predictions.csv`
- 预测结果：读取 `data/<日期>/todays_predictions.csv` 展示
- 赛后报告：`football_ai.cli post`
- 设置内：拉取五大联赛 ≈ `./run.sh fetch all <年>`；合并 ≈ `./run.sh merge-five`；校准/回测 ≈ `./run.sh calibrate/backtest --league <id>`，联赛可选合并/英超/西甲/德甲/意甲/法甲；**数据校验**可选「默认（无效场次）」或「2024/2025/2026 合并数据」，勾选「与参考样本 diff」时与参考 CSV 比对；执行结果区域可滚动，支持「复制」到剪贴板

## 打包（可选）

在 `desktop` 目录下：

```bash
npm run build
```

产物在 `src-tauri/target/release/bundle/`（macOS 为 `.app`）。

## 技术说明

- 前端：静态 HTML/CSS/JS，通过 Tauri 全局 `invoke` 调用 Rust 命令。
- 后端：Rust 在本地用 `std::process::Command` 调用项目根目录下的 `.venv/bin/python`（或系统 `python3`），执行 `predict_batch.py` 和 `football_ai.cli`，不联网、不对外暴露。
