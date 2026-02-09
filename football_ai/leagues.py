"""
联赛与杯赛配置（第三版）：从 config/leagues.yaml、config/cups.yaml 读取赛事与数据路径。
阶段一：联赛；阶段二：杯赛（足总杯、欧冠、欧联等）。
"""
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_LEAGUES_FILE = _CONFIG_DIR / "leagues.yaml"
_CUPS_FILE = _CONFIG_DIR / "cups.yaml"
_DATA_DIR = _ROOT / "data" / "historical"

_DEFAULT_LEAGUE_ID = "EPL"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_leagues() -> list[dict[str, Any]]:
    """返回配置中的联赛列表，每项含 id, name_zh, name_en, understat_code。"""
    return _load_yaml(_LEAGUES_FILE).get("leagues") or []


def get_cups() -> list[dict[str, Any]]:
    """返回配置中的杯赛列表，每项含 id, name_zh, name_en, two_legged 等。"""
    return _load_yaml(_CUPS_FILE).get("cups") or []


def get_league(league_id: str | None) -> dict[str, Any] | None:
    """根据 id 返回联赛配置；仅查 leagues，None 或未找到时返回 EPL（若有）。"""
    if not league_id:
        league_id = _DEFAULT_LEAGUE_ID
    for L in get_leagues():
        if (L.get("id") or "").strip() == league_id.strip():
            return L
    if league_id != _DEFAULT_LEAGUE_ID:
        return get_league(_DEFAULT_LEAGUE_ID)
    return None


def get_competition(competition_id: str | None) -> dict[str, Any] | None:
    """根据 id 返回赛事配置（先查联赛，再查杯赛）；用于报告与校准。"""
    if not competition_id:
        competition_id = _DEFAULT_LEAGUE_ID
    cid = competition_id.strip()
    for L in get_leagues():
        if (L.get("id") or "").strip() == cid:
            return {**L, "type": "league"}
    for C in get_cups():
        if (C.get("id") or "").strip() == cid:
            return {**C, "type": "cup"}
    if cid != _DEFAULT_LEAGUE_ID:
        return get_competition(_DEFAULT_LEAGUE_ID)
    return None


def get_competition_type(competition_id: str | None) -> str:
    """返回 'league' 或 'cup'；未找到时按联赛处理。"""
    c = get_competition(competition_id)
    if not c:
        return "league"
    return c.get("type") or "league"


def get_calibration_path(league_id: str | None) -> Path:
    """该赛事的校准参数文件路径（联赛或杯赛 id 均可）。"""
    c = get_competition(league_id)
    lid = (c or {}).get("id") or _DEFAULT_LEAGUE_ID
    return _CONFIG_DIR / f"calibration_{lid}.yaml"


def get_historical_dir(league_id: str | None) -> Path:
    """该赛事的历史数据目录（联赛或杯赛 id 均可）。"""
    c = get_competition(league_id)
    lid = (c or {}).get("id") or _DEFAULT_LEAGUE_ID
    return _DATA_DIR / lid


def get_understat_code(league_id: str | None) -> str | None:
    """该联赛在 Understat 的代码，用于抓取；杯赛无则返回 None。"""
    L = get_league(league_id)
    if not L:
        return "EPL" if not league_id else None
    code = L.get("understat_code")
    return str(code).strip() if code else None


def get_fbref_cup_config(competition_id: str | None) -> tuple[int | None, str | None]:
    """杯赛在 FBref 的 comp_id 与 URL slug，用于抓取；非杯赛或未配置返回 (None, None)。"""
    c = get_competition(competition_id)
    if not c or c.get("type") != "cup":
        return None, None
    cid = c.get("fbref_comp_id")
    slug = c.get("fbref_slug")
    if cid is not None:
        try:
            return int(cid), (str(slug).strip() if slug else None)
        except (TypeError, ValueError):
            pass
    return None, None


def get_fbref_league_config(league_id: str | None) -> tuple[int | None, str | None]:
    """联赛在 FBref 的 comp_id 与 URL slug（第四版多维度参考）；非联赛或未配置返回 (None, None)。"""
    L = get_league(league_id)
    if not L:
        return None, None
    cid = L.get("fbref_comp_id")
    slug = L.get("fbref_slug")
    if cid is not None and slug:
        try:
            return int(cid), str(slug).strip()
        except (TypeError, ValueError):
            pass
    return None, None


def get_fotmob_league_id(league_id: str | None) -> str | None:
    """联赛在 soccerdata FotMob 中的 league ID（如 ENG-Premier League）；未配置返回 None。"""
    L = get_league(league_id)
    if not L:
        return None
    lid = L.get("fotmob_league_id")
    return str(lid).strip() if lid else None
