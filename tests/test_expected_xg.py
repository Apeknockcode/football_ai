"""赛前预期 xG 数据加载测试：按场次表、按球队表、fallback。"""
import unittest
from pathlib import Path

from football_ai.data.expected_xg import load_expected_xg


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class TestLoadExpectedXg(unittest.TestCase):
    def test_no_path(self):
        xh, xa, *_ = load_expected_xg(path=None, home_team="利兹联", away_team="诺丁汉森林", round_=12)
        self.assertIsNone(xh)
        self.assertIsNone(xa)

    def test_team_table(self):
        path = _project_root() / "data" / "test" / "expected_xg_teams.example.csv"
        if not path.exists():
            self.skipTest("data/test/expected_xg_teams.example.csv not found")
        xh, xa, *_ = load_expected_xg(path=path, home_team="利兹联", away_team="诺丁汉森林", round_=12)
        self.assertIsNotNone(xh)
        self.assertIsNotNone(xa)
        self.assertGreater(xh, 0)
        self.assertGreater(xa, 0)

    def test_fixture_table(self):
        path = _project_root() / "data" / "test" / "expected_xg_fixtures.example.csv"
        if not path.exists():
            self.skipTest("data/test/expected_xg_fixtures.example.csv not found")
        xh, xa, *_ = load_expected_xg(
            path=path, home_team="利兹联", away_team="诺丁汉森林", round_=12
        )
        self.assertIsNotNone(xh)
        self.assertIsNotNone(xa)

    def test_fallback_to_example(self):
        path = _project_root() / "data" / "expected_xg_teams.csv"
        example = _project_root() / "data" / "test" / "expected_xg_teams.example.csv"
        if not example.exists():
            self.skipTest("data/test/expected_xg_teams.example.csv not found")
        xh, xa, *_ = load_expected_xg(
            path=path, home_team="利兹联", away_team="诺丁汉森林", round_=12
        )
        if not path.exists():
            self.assertIsNotNone(xh, "fallback to .example should yield values")
            self.assertIsNotNone(xa)

    def test_team_table_with_mapping(self):
        path = _project_root() / "data" / "test" / "expected_xg_teams.example.csv"
        if not path.exists():
            self.skipTest("data/test/expected_xg_teams.example.csv not found")
        xh, xa, *_ = load_expected_xg(
            path=path,
            home_team="利兹联",
            away_team="诺丁汉森林",
            round_=12,
            team_name_mapping={"Leeds United": "利兹联", "Nottingham Forest": "诺丁汉森林"},
        )
        self.assertIsNotNone(xh)
        self.assertIsNotNone(xa)
