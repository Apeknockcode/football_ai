"""
数据层：事件、伤停、赛程、历史场次、近期状态、历史交锋等。
- events: 战术用事件流（StatsBomb 等）
- injuries: 伤停（公众号/预留 API）
- fixtures: 赛程与元数据
- expected_xg: 赛前预期 xG（按场次或按球队 CSV）
- historical: 历史场次（校准/回测、近期状态、H2H）
- form: 近期状态（近 N 场）
- h2h: 历史交锋
"""
from football_ai.data.events import load_events
from football_ai.data.expected_xg import load_expected_xg
from football_ai.data.fixtures import load_fixture_meta
from football_ai.data.historical import load_historical_matches
from football_ai.data.injuries import load_injuries
from football_ai.data.form import get_team_form
from football_ai.data.h2h import get_h2h
from football_ai.data.team_stats import get_team_season_stats

__all__ = [
    "load_events",
    "load_fixture_meta",
    "load_injuries",
    "load_expected_xg",
    "load_historical_matches",
    "get_team_form",
    "get_h2h",
    "get_team_season_stats",
]
