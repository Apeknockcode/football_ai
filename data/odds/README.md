# 赔率数据目录

用于存放按日或按联赛的赔率快照 CSV，支持时序与赔率变化分析。格式见 [docs/数据采集与整合.md](../../docs/数据采集与整合.md)（列：date, home_team, away_team, round, odds_home, odds_draw, odds_away 等）。

脚本 `scripts/snapshot_odds.py` 可录入或拉取赔率到本目录。
