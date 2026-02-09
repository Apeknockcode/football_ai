"""配置加载：联赛、数据源、报告选项。"""
from pathlib import Path
import yaml

_CONFIG_DIR = Path(__file__).resolve().parent
_DEFAULT_SETTINGS = _CONFIG_DIR / "settings.yaml"


def load_settings(path: Path | None = None) -> dict:
    """加载 settings.yaml，返回字典。"""
    p = path or _DEFAULT_SETTINGS
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
