#!/usr/bin/env python3
"""
从 Understat 抓取指定联赛、赛季的赛果与 xG，写入 data/historical/{league_id}/pl_YYYY.csv。
联赛见 config/leagues.yaml（EPL/西甲/德甲/意甲/法甲等）。
仅供个人/教育用途，请遵守 understat.com 使用条款与访问频率，勿用于商业爬取。
"""
import csv
import json
import re
import ssl
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEFAULT_SEASON = 2024  # 2023/24 赛季
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _ssl_no_verify_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_url(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    timeout = 45
    ctx = _ssl_no_verify_context()
    # 优先使用不验证证书的上下文，避免 macOS/网络环境导致的握手超时或 CERTIFICATE_VERIFY_FAILED
    for attempt in range(2):
        try:
            with urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read().decode("utf-8", errors="replace")
        except (ssl.SSLCertVerificationError, URLError, TimeoutError, OSError) as e:
            err_str = str(e).lower()
            if attempt == 0 and ("timeout" in err_str or "handshake" in err_str or "certificate" in err_str):
                continue
            raise
    raise URLError("fetch failed after retries")


def _extract_json_from_script(html: str) -> list:
    """从页面 script 中提取 datesData 或类似包含赛果的 JSON 数组。"""
    # Understat 常把数据放在 JSON.parse('...') 中，内容可能带转义
    # 尝试匹配 datesData = JSON.parse('...') 或 含 "xG","goals","h","a" 的 parse
    patterns = [
        r"datesData\s*=\s*JSON\.parse\s*\(\s*['\"](.*?)['\"]\s*\)",
        r"teamsData\s*=\s*JSON\.parse\s*\(\s*['\"](.*?)['\"]\s*\)",
        r"JSON\.parse\s*\(\s*['\"](.*?\"xG\".*?\"goals\".*?)['\"]\s*\)",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if not m:
            continue
        raw = m.group(1)
        # 处理 JS 转义：\" -> ", \\ -> \
        raw = raw.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        try:
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0:
                return data
            if isinstance(data, dict):
                # 可能是 { "1": [...], "2": [...] } 按轮次
                out = []
                for v in data.values():
                    if isinstance(v, list):
                        out.extend(v)
                if out:
                    return out
        except (json.JSONDecodeError, TypeError):
            continue
    return []


def _infer_rounds(matches: list) -> list:
    """按 datetime 排序后按周推断 round（约每轮 10 场）。"""
    for m in matches:
        dt = m.get("datetime") or m.get("date")
        if isinstance(dt, str):
            try:
                m["_parsed_date"] = datetime.strptime(dt[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                m["_parsed_date"] = datetime.min
        else:
            m["_parsed_date"] = datetime.min
    matches.sort(key=lambda x: x["_parsed_date"])
    # 每约 10 场为一轮（英超每轮 10 场）
    round_ = 1
    count = 0
    for m in matches:
        m["_round"] = round_
        count += 1
        if count >= 10:
            count = 0
            round_ += 1
    return matches


def fetch_league_matches_via_api(league: str = "EPL", season: int = DEFAULT_SEASON) -> list[dict] | None:
    """通过 understatapi 库请求联赛场次（走与官网相同的 AJAX），成功返回 list[dict]，不可用时返回 None。"""
    try:
        from understatapi import UnderstatClient
    except ImportError:
        return None
    try:
        with UnderstatClient() as client:
            raw = client.league(league=league).get_match_data(season=str(season))
        if not raw or not isinstance(raw, list):
            return None
        # API 返回结构与页面内 datesData 一致：h, a, goals, xG, datetime 等
        sample = raw[0] if raw else {}
        if not isinstance(sample, dict) or "h" not in sample or "goals" not in sample:
            return None
        return _infer_rounds(raw)
    except Exception:
        return None


def fetch_league_matches(league: str = "EPL", season: int = DEFAULT_SEASON, html: str | None = None) -> list[dict]:
    """抓取指定联赛、赛季的赛果与 xG；若提供 html 则从本地字符串解析，否则优先用 understatapi，再回退到请求 HTML。"""
    if html is not None:
        page_html = html
        data = _extract_json_from_script(page_html)
    else:
        data = fetch_league_matches_via_api(league=league, season=season)
        if data is not None:
            return data
        url = f"https://understat.com/league/{league}/{season}"
        page_html = _fetch_url(url)
        data = _extract_json_from_script(page_html)
    if not data:
        return []
    sample = data[0] if data else {}
    if not isinstance(sample, dict) or "h" not in sample or "goals" not in sample:
        return []
    data = _infer_rounds(data)
    return data


def to_csv_rows(matches: list[dict], season: int) -> list[dict]:
    """转为项目历史表所需格式：season, round, home_team, away_team, xg_home, xg_away, goals_home, goals_away。"""
    rows = []
    for m in matches:
        h = m.get("h") or {}
        a = m.get("a") or {}
        goals = m.get("goals") or {}
        xg = m.get("xG") or {}
        if isinstance(h, dict):
            home_team = (h.get("title") or h.get("short_title") or "").strip()
        else:
            home_team = str(h).strip()
        if isinstance(a, dict):
            away_team = (a.get("title") or a.get("short_title") or "").strip()
        else:
            away_team = str(a).strip()
        goals_h = goals.get("h") if isinstance(goals, dict) else None
        goals_a = goals.get("a") if isinstance(goals, dict) else None
        xg_h = xg.get("h") if isinstance(xg, dict) else None
        xg_a = xg.get("a") if isinstance(xg, dict) else None
        try:
            goals_home = int(float(goals_h)) if goals_h is not None else 0
            goals_away = int(float(goals_a)) if goals_a is not None else 0
            xg_home = float(xg_h) if xg_h is not None else 0.0
            xg_away = float(xg_a) if xg_a is not None else 0.0
        except (TypeError, ValueError):
            continue
        round_ = m.get("_round") or 0
        rows.append({
            "season": season,
            "round": round_,
            "home_team": home_team or "Unknown",
            "away_team": away_team or "Unknown",
            "xg_home": round(xg_home, 4),
            "xg_away": round(xg_away, 4),
            "goals_home": goals_home,
            "goals_away": goals_away,
        })
    return rows


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="从 Understat 抓取英超历史场次并写入 data/historical/")
    parser.add_argument(
        "--season",
        type=int,
        nargs="*",
        default=[DEFAULT_SEASON],
        metavar="YEAR",
        help="赛季结束年，可多个，如 --season 2024 2025；缺省为 2024",
    )
    parser.add_argument("--league", type=str, default=None, help="联赛 id（见 config/leagues.yaml），默认 EPL；决定输出目录与 Understat 代码）")
    parser.add_argument("--out", type=Path, default=None, help="单赛季时指定输出 CSV（多赛季时忽略，写 pl_YYYY.csv）")
    parser.add_argument("--html", type=Path, default=None, help="从本地保存的 HTML 解析（仅单赛季；无法直连时用）")
    args = parser.parse_args()

    from football_ai.leagues import get_historical_dir, get_competition, get_understat_code

    league_id = (args.league or "EPL").strip()
    league_cfg = get_competition(league_id)
    if not league_cfg:
        print(f"未找到赛事配置: {league_id}，请检查 config/leagues.yaml 或 config/cups.yaml。", file=sys.stderr)
        sys.exit(1)
    understat_code = get_understat_code(league_id)
    if not understat_code and not args.html:
        print(f"赛事 {league_id} 无 Understat 代码（杯赛需手工维护数据），无法在线抓取；请用 --html 指定本地 HTML。", file=sys.stderr)
        sys.exit(1)
    hist_dir = get_historical_dir(league_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    # 兼容：原 data/historical/*.csv 若存在且当前为 EPL 且 EPL 子目录为空，可复制进 EPL（不自动移动，避免误删）
    if league_id == "EPL":
        root_historical = ROOT / "data" / "historical"
        for f in (root_historical.glob("pl_*.csv") if root_historical.is_dir() else []):
            if f.parent == root_historical and not (hist_dir / f.name).exists():
                import shutil
                shutil.copy2(f, hist_dir / f.name)
                print(f"已复制 {f.name} → {hist_dir / f.name}", file=sys.stderr)

    seasons = args.season if args.season else [DEFAULT_SEASON]

    if args.html and len(seasons) != 1:
        print("--html 仅支持单赛季，请只指定一个 --season。", file=sys.stderr)
        sys.exit(1)

    total_written = 0
    for season in seasons:
        out_path = args.out if args.out and len(seasons) == 1 else hist_dir / f"pl_{season}.csv"
        html_content = None
        if args.html:
            if not args.html.exists():
                print(f"文件不存在: {args.html}", file=sys.stderr)
                sys.exit(1)
            html_content = args.html.read_text(encoding="utf-8", errors="replace")
            print(f"从本地 HTML 解析: {args.html}", file=sys.stderr)
        else:
            print(f"正在抓取 {league_cfg.get('name_zh', league_id)} {season} 赛季…", file=sys.stderr)
        matches = fetch_league_matches(league=understat_code or "EPL", season=season, html=html_content)
        if not matches:
            print(f"未解析到 {season} 赛季赛果数据。", file=sys.stderr)
            if season >= 2025:
                print(
                    f"  Understat 可能尚未收录 {season - 1}/{season} 赛季，或当前赛季数据在其站内用其他年份标识。可先拉取已结束赛季，例如: ./run.sh fetch all 2024 2025",
                    file=sys.stderr,
                )
            continue
        rows = to_csv_rows(matches, season)
        if not rows:
            print(f"无有效场次可写入: {season}", file=sys.stderr)
            continue
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["season", "round", "home_team", "away_team", "xg_home", "xg_away", "goals_home", "goals_away"])
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {len(rows)} 场 → {out_path}", file=sys.stderr)
        total_written += len(rows)
    if total_written == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
