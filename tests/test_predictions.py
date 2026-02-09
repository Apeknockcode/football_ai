"""预测模块测试：get_predictions、adjust_xg_for_injuries、概率归一。"""
import unittest

from football_ai.predictions import get_predictions, adjust_xg_for_injuries
from football_ai.predictions.service import (
    _poisson_pmf,
    _probabilities_from_xg,
    most_likely_score_given_xg_and_wdl,
)


class TestPoisson(unittest.TestCase):
    def test_poisson_pmf(self):
        self.assertEqual(_poisson_pmf(0, 0), 1.0)
        self.assertEqual(_poisson_pmf(1, 0), 0.0)
        self.assertLessEqual(abs(sum(_poisson_pmf(k, 1.5) for k in range(20)) - 1.0), 1e-6)

    def test_probabilities_from_xg_sum_to_one(self):
        probs = _probabilities_from_xg(1.2, 1.0)
        wdl = probs["win_draw_lose"]
        self.assertAlmostEqual(wdl["主胜"] + wdl["平"] + wdl["客胜"], 1.0, places=5)
        self.assertAlmostEqual(sum(probs["half_full"].values()), 1.0, places=5)

    def test_most_likely_score_given_xg_and_wdl(self):
        # 主胜最高 -> 应在主胜类别内选概率最大的比分（如 1-0）
        wdl = {"主胜": 0.5, "平": 0.3, "客胜": 0.2}
        s = most_likely_score_given_xg_and_wdl(1.5, 1.0, wdl)
        self.assertIn(s, ("1-0", "2-0", "2-1"))
        # 平最高 -> 平局类别内最可能
        wdl_draw = {"主胜": 0.2, "平": 0.5, "客胜": 0.3}
        s2 = most_likely_score_given_xg_and_wdl(1.2, 1.2, wdl_draw)
        self.assertEqual(s2, "1-1")
        # 客胜最高 -> 客胜类别内最可能
        wdl_away = {"主胜": 0.2, "平": 0.2, "客胜": 0.6}
        s3 = most_likely_score_given_xg_and_wdl(1.0, 1.5, wdl_away)
        self.assertIn(s3, ("0-1", "0-2", "1-2"))


class TestGetPredictions(unittest.TestCase):
    def test_without_xg(self):
        out = get_predictions("曼联", "利物浦", 28, metrics=None, available=False)
        self.assertFalse(out["available"])
        self.assertIn("未提供", out["summary_zh"] or "")

    def test_with_metrics(self):
        out = get_predictions(
            "曼联", "利物浦", 28,
            metrics={"xg": {"home": 1.5, "away": 1.2}},
            available=True,
        )
        self.assertTrue(out["available"])
        wdl = out["win_draw_lose"]
        self.assertAlmostEqual(wdl["主胜"] + wdl["平"] + wdl["客胜"], 1.0, places=5)

    def test_expected_xg_flag(self):
        out = get_predictions(
            "利兹联", "诺丁汉森林", 12,
            metrics={"xg": {"home": 1.2, "away": 1.0}},
            available=True,
            expected_xg=True,
        )
        self.assertTrue(out["available"])
        self.assertIn("赛前预期 xG", out["summary_zh"] or "")


class TestAdjustXgForInjuries(unittest.TestCase):
    def test_empty(self):
        xh, xa = adjust_xg_for_injuries(1.5, 1.2, [], [])
        self.assertEqual(xh, 1.5)
        self.assertEqual(xa, 1.2)

    def test_deducts(self):
        home = [{"reason": "受伤"}, {"reason": "出战成疑"}]
        away = [{"reason": "受伤"}]
        xh, xa = adjust_xg_for_injuries(1.5, 1.2, home, away)
        self.assertLess(xh, 1.5)
        self.assertLess(xa, 1.2)
        self.assertGreaterEqual(xh, 0.25)
        self.assertGreaterEqual(xa, 0.25)

    def test_cap(self):
        many = [{"reason": "受伤"}] * 10
        xh, xa = adjust_xg_for_injuries(1.0, 1.0, many, many)
        self.assertGreaterEqual(xh, 0.25)
        self.assertGreaterEqual(xa, 0.25)
