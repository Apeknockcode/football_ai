"""
政治模块（四块）：赛事/国家、纪律/裁判、舆论/叙事、俱乐部/帅位。
为报告提供背景与语境，输出可追溯、客观表述。
"""
from football_ai.politics.competition import get_competition_context
from football_ai.politics.discipline_referee import get_discipline_referee
from football_ai.politics.narrative import get_narrative
from football_ai.politics.club_manager import get_club_manager_context

__all__ = [
    "get_competition_context",
    "get_discipline_referee",
    "get_narrative",
    "get_club_manager_context",
]
