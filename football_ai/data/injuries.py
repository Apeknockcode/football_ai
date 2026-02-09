"""
伤停数据接入。当前支持非结构化来源（如公众号）的占位与手动录入；
预留结构化 API 接口。
"""
from pathlib import Path
from typing import Any

import pandas as pd


# 预留：未来从 API 拉取
def load_injuries(
    path: str | Path | None = None,
    api_url: str | None = None,
    fixture_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    加载伤停列表。
    :param path: 本地 CSV/JSON（人工整理或解析公众号后的结果）
    :param api_url: 预留；未来伤停 API
    :param fixture_id: 若指定，仅返回与该场相关（主客队）的伤停
    :return: [{"team": "曼联", "player": "A", "reason": "伤缺"|"停赛"|"累计黄牌", "source": "..."}, ...]
    """
    if api_url:
        # 预留：requests.get(api_url) -> 解析 -> list[dict]
        pass

    if path is None:
        return []

    path = Path(path)
    if not path.exists():
        return []

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8")
    elif path.suffix.lower() in (".json",):
        df = pd.read_json(path)
    else:
        return []

    if df.empty:
        return []
    records = df.to_dict("records")
    if fixture_id and "match_id" in df.columns:
        # 此处可按 match_id 关联主客队再过滤
        pass
    return records
