#!/usr/bin/env python3
"""
从 FBref 抓取杯赛（欧冠、欧联、足总杯、联赛杯）指定赛季的赛果与 xG，写入 data/historical/{cup_id}/pl_YYYY.csv。
依赖：requests, pandas。请遵守 fbref.com 使用条款与访问频率，仅供个人/教育用途。
"""
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# 更接近浏览器的请求头，部分站点可减少 403
FBREF_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def _fetch_tables(url: str):
    """请求 URL 并用 pandas 解析 HTML 表格；返回 tables 列表。"""
    import ssl
    import pandas as pd
    from urllib.error import URLError, HTTPError
    from urllib.request import Request, urlopen
    req = Request(url, headers=FBREF_HEADERS)
    timeout = 25
    if __import__("os").environ.get("FBREF_NO_SSL_VERIFY"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urlopen(req, timeout=timeout, context=ctx) as r:
            html = r.read().decode("utf-8", errors="replace")
        return pd.read_html(html, flavor="bs4")
    try:
        with urlopen(req, timeout=timeout) as r:
            html = r.read().decode("utf-8", errors="replace")
        return pd.read_html(html, flavor="bs4")
    except (ssl.SSLCertVerificationError, URLError) as e:
        # URLError 可能包装 SSLCertVerificationError（如 macOS 未装证书）
        if isinstance(e, URLError) and not isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            raise RuntimeError(f"请求或解析失败: {url} — {e!r}") from e
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urlopen(req, timeout=timeout, context=ctx) as r:
            html = r.read().decode("utf-8", errors="replace")
        return pd.read_html(html, flavor="bs4")
    except HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                f"FBref 返回 403（拒绝脚本访问）。请用浏览器打开该页并「另存为」完整网页，再执行：\n"
                f"  .venv/bin/python scripts/fetch_historical_fbref_cups.py --cup UCL --season 2024 --html 你保存的网页.html"
            ) from e
        raise RuntimeError(f"请求失败: {url} — HTTP {e.code}") from e
    except Exception as e:
        raise RuntimeError(f"请求或解析失败: {url} — {e!r}") from e


def _parse_score(score_str: str) -> tuple[int, int]:
    """解析比分字符串如 '2–1' 或 '2-1' 为 (2, 1)。"""
    if not score_str or not isinstance(score_str, str):
        return 0, 0
    s = score_str.strip()
    for sep in ["–", "-", ":", " "]:
        if sep in s:
            parts = s.split(sep, 1)
            try:
                return int(parts[0].strip()), int(parts[1].strip())
            except (ValueError, IndexError):
                pass
    return 0, 0


def _infer_round_from_row(idx: int, wk_val, round_val) -> int:
    """从 Wk/Round 列或行号推断轮次。优先用 Wk（Matchweek），支持整数或浮点如 4.0。"""
    def _to_int(v):
        if v is None:
            return None
        try:
            if isinstance(v, (int, float)):
                if isinstance(v, float) and v != v:  # NaN
                    return None
                return int(v)
            s = str(v).strip()
            if s and s.isdigit():
                return int(s)
            return int(float(s))
        except (ValueError, TypeError):
            return None
    r = _to_int(wk_val)
    if r is not None and r >= 1:
        return r
    r = _to_int(round_val)
    if r is not None and r >= 1:
        return r
    return max(1, idx + 1)


def fetch_cup_matches_fbref(comp_id: int, slug: str, season_end_year: int, html: str | None = None) -> list[dict]:
    """
    从 FBref 赛程页抓取杯赛场次。season_end_year 为赛季结束年，如 2025 表示 2024/25。
    返回 list[dict]，每项含 home_team, away_team, goals_home, goals_away, xg_home, xg_away, round。
    """
    import pandas as pd
    season_str = f"{season_end_year - 1}-{season_end_year}"
    if html is not None:
        try:
            # 用 StringIO 传入内容，避免 pandas 把长字符串当文件路径
            tables = pd.read_html(io.StringIO(html), flavor="bs4")
        except Exception as e:
            raise RuntimeError(f"解析 HTML 失败: {e}") from e
    else:
        url = f"https://fbref.com/en/comps/{comp_id}/{season_str}/schedule/{season_str}-{slug}-Scores-and-Fixtures"
        try:
            tables = _fetch_tables(url)
        except Exception as e:
            raise RuntimeError(f"抓取失败: {e}") from e

    rows_out = []
    for tbl in tables:
        df = tbl
        cols = [c for c in df.columns if isinstance(c, str)]
        # 找包含 Home / Away / Score 或 xG 的表
        has_home = any("home" in c.lower() or c == "Home" for c in cols)
        has_away = any("away" in c.lower() or c == "Away" for c in cols)
        has_score = any("score" in c.lower() or c == "Score" for c in cols)
        if not (has_home and has_away):
            continue
        # 列名可能是多级索引，取最后一级
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[-1] if isinstance(c, tuple) else c for c in df.columns]
        col_map = {str(c).strip(): c for c in df.columns}
        home_col = None
        away_col = None
        score_col = None
        xg_h_col = None
        xg_a_col = None
        wk_col = None
        round_col = None
        for k in col_map:
            kk = k.lower()
            if k == "Home" or (kk == "home" and home_col is None):
                home_col = col_map[k]
            if k == "Away" or (kk == "away" and away_col is None):
                away_col = col_map[k]
            if "score" in kk and score_col is None:
                score_col = col_map[k]
            if k == "xG" and xg_h_col is None:
                xg_h_col = col_map[k]
            if k == "xG.1" or (kk == "xg.1" and xg_a_col is None):
                xg_a_col = col_map[k]
            if k == "Wk" or kk == "wk":
                wk_col = col_map[k]
            if "round" in kk:
                round_col = col_map[k]
        if home_col is None or away_col is None:
            continue
        for idx, row in df.iterrows():
            home = row.get(home_col)
            away = row.get(away_col)
            if pd.isna(home) or pd.isna(away):
                continue
            home_team = str(home).strip()
            away_team = str(away).strip()
            if not home_team or not away_team or home_team == "Home" or away_team == "Away":
                continue
            # 跳过未开球场次（无比分）
            score_val = row.get(score_col) if score_col else None
            if score_val is None or (isinstance(score_val, float) and pd.isna(score_val)):
                continue
            score_str = str(score_val).strip()
            if not score_str or score_str in ["", "—", "–", "vs"]:
                continue
            g_h, g_a = _parse_score(score_str)
            if g_h == 0 and g_a == 0 and "–" not in score_str and "-" not in score_str:
                continue
            xg_h = 0.0
            xg_a = 0.0
            if xg_h_col is not None:
                try:
                    v = row.get(xg_h_col)
                    if v is not None and not (isinstance(v, float) and pd.isna(v)):
                        xg_h = float(v)
                except (TypeError, ValueError):
                    pass
            if xg_a_col is not None:
                try:
                    v = row.get(xg_a_col)
                    if v is not None and not (isinstance(v, float) and pd.isna(v)):
                        xg_a = float(v)
                except (TypeError, ValueError):
                    pass
            round_ = _infer_round_from_row(
                idx,
                row.get(wk_col) if wk_col else None,
                row.get(round_col) if round_col else None,
            )
            rows_out.append({
                "home_team": home_team,
                "away_team": away_team,
                "goals_home": g_h,
                "goals_away": g_a,
                "xg_home": round(xg_h, 4),
                "xg_away": round(xg_a, 4),
                "round": round_,
            })
        if rows_out:
            break
    return rows_out


def main() -> None:
    import argparse
    from football_ai.leagues import get_competition, get_historical_dir, get_fbref_cup_config

    parser = argparse.ArgumentParser(description="从 FBref 抓取杯赛历史场次并写入 data/historical/{cup_id}/")
    parser.add_argument("--cup", type=str, required=True, help="杯赛 id（UCL、UEL、FA_Cup、League_Cup）")
    parser.add_argument(
        "--season",
        type=int,
        nargs="*",
        default=[2025],
        metavar="YEAR",
        help="赛季结束年，如 2025 表示 2024/25；可多个",
    )
    parser.add_argument("--out", type=Path, default=None, help="单赛季时指定输出 CSV（多赛季时忽略）")
    parser.add_argument("--html", type=Path, default=None, help="从本地保存的 FBref 赛程页 HTML 解析（遇 403 时可浏览器另存为完整网页）")
    args = parser.parse_args()

    cup_id = args.cup.strip()
    c = get_competition(cup_id)
    if not c or c.get("type") != "cup":
        print(f"未找到杯赛配置或非杯赛: {cup_id}，请检查 config/cups.yaml。", file=sys.stderr)
        sys.exit(1)
    comp_id, slug = get_fbref_cup_config(cup_id)
    if comp_id is None or not slug:
        print(f"杯赛 {cup_id} 未配置 fbref_comp_id/fbref_slug，无法抓取。", file=sys.stderr)
        sys.exit(1)

    hist_dir = get_historical_dir(cup_id)
    hist_dir.mkdir(parents=True, exist_ok=True)
    seasons = args.season if args.season else [2025]
    total_written = 0

    html_content = None
    if args.html:
        if not args.html.exists():
            print(f"文件不存在: {args.html}", file=sys.stderr)
            sys.exit(1)
        html_content = args.html.read_text(encoding="utf-8", errors="replace")
        if len(seasons) != 1:
            print("--html 仅支持单赛季，将只解析一次。", file=sys.stderr)
            seasons = seasons[:1]

    for season_end in seasons:
        try:
            matches = fetch_cup_matches_fbref(comp_id, slug, season_end, html=html_content)
        except RuntimeError as e:
            print(f"抓取 {cup_id} {season_end} 失败: {e}", file=sys.stderr)
            continue
        if not matches:
            print(f"未解析到 {cup_id} {season_end} 场次。", file=sys.stderr)
            continue
        out_path = args.out if args.out and len(seasons) == 1 else hist_dir / f"pl_{season_end}.csv"
        rows = [
            {
                "season": season_end,
                "round": m["round"],
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "xg_home": m["xg_home"],
                "xg_away": m["xg_away"],
                "goals_home": m["goals_home"],
                "goals_away": m["goals_away"],
            }
            for m in matches
        ]
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
