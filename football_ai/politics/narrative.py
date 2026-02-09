"""
政治 · 舆论/叙事：媒体叙事线（生死战、复仇等）。关键词或摘要，可延后完善。
"""
from typing import Any


def get_narrative(
    home_team: str,
    away_team: str,
    round_: int,
    raw_headlines: list[str] | None = None,
) -> dict[str, Any]:
    """
    返回舆论/叙事小结；第一版可为占位或关键词匹配。
    :param raw_headlines: 本场相关新闻标题/摘要列表
    :return: {"summary_zh": "媒体普遍将本场视为...", "sources": []}
    """
    summary = "媒体普遍关注本场对积分榜形势的影响。"
    if raw_headlines:
        # 占位：关键词匹配或简单摘要
        pass
    return {"summary_zh": summary, "sources": raw_headlines or []}
