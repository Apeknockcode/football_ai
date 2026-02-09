"""
政治 · 俱乐部/帅位：主帅压力、管理层/更衣室背景。需标注信源；可简化或延后。
"""
from typing import Any


def get_club_manager_context(
    home_team: str,
    away_team: str,
    raw_news: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    返回双方帅位/俱乐部压力等描述；第一版可占位。
    :param raw_news: [{"team": "曼联", "pressure": "high", "source": "..."}]
    :return: {"summary_zh": "...（据 XX 报道）", "sources": []}
    """
    summary = "双方帅位与俱乐部动态以当轮报道为准。"
    sources = []
    if raw_news:
        for n in raw_news:
            if n.get("source"):
                sources.append(n["source"])
    return {"summary_zh": summary, "sources": sources}
