"""校准与回测脚本的简单集成测试：用 sample 数据跑一遍，检查无报错、输出含关键字段。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


class TestCalibrateBacktest(unittest.TestCase):
    def test_calibrate_pl_runs(self):
        root = _root()
        hist_dir = root / "data" / "historical" / "EPL"
        if not hist_dir.exists() or not list(hist_dir.glob("*.csv")):
            hist_dir = root / "data" / "historical" / "_common"
        if not hist_dir.exists() or not list(hist_dir.glob("*.csv")):
            self.skipTest("data/historical/EPL/*.csv 或 _common/*.csv 未找到")
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            out_yaml = Path(f.name)
        try:
            result = subprocess.run(
                [sys.executable, str(root / "scripts" / "calibrate_pl.py"), "--league", "EPL", "--historical", str(hist_dir), "--out", str(out_yaml)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, (result.stdout or "") + (result.stderr or ""))
            if out_yaml.exists():
                content = out_yaml.read_text(encoding="utf-8")
                self.assertIn("draw_rate", content)
                self.assertIn("xg_scale", content)
        finally:
            out_yaml.unlink(missing_ok=True)

    def test_backtest_pl_runs(self):
        root = _root()
        hist_dir = root / "data" / "historical" / "EPL"
        if not hist_dir.exists() or not list(hist_dir.glob("*.csv")):
            hist_dir = root / "data" / "historical" / "_common"
        if not hist_dir.exists() or not list(hist_dir.glob("*.csv")):
            self.skipTest("data/historical/EPL 或 _common 下无可用 CSV")
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "backtest_pl.py"), "--league", "EPL", "--historical", str(hist_dir)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, (result.stdout or "") + (result.stderr or ""))
        out = result.stdout or ""
        self.assertTrue("场次" in out or "Brier" in out)
