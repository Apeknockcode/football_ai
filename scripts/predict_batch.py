#!/usr/bin/env python3
"""
批量预测：读取赛程 CSV，用项目内 xG+Poisson 模型输出每场胜负平/比分/让球概率。
- 赛程 CSV 列：match_id, league_id, league_zh, home_team, away_team, round, handicap_note, xg_home, xg_away
  handicap_note 为竞彩让球数：-1=主让1球，+1=主受让1球，会按该让球数输出让胜/让平/让负。
- 盘口参考：若 CSV 含主胜/平/客胜赔率（odds_home, odds_draw, odds_away 或 主胜/平/客胜），且 config 中 odds_blend_weight > 0，
  最终胜负平概率 = (1 - odds_blend_weight) * 模型概率 + odds_blend_weight * 赔率隐含概率（归一化）。
- xG 来源（按优先级）：① 赛程 CSV 中已填的 xg_home/xg_away；② --expected-xg 指定的表（按球队或按场次）；③ --default-xg。
- 可选 --injuries-dir：从该文件夹读取所有伤停 CSV（格式 team, player, reason），合并后按主客队应用伤停对 xG 的微调。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from football_ai.predictions import get_predictions, adjust_xg_for_injuries
from football_ai.predictions.ml_predictor import load_artifact, predictions_from_ml
from football_ai.data.expected_xg import load_expected_xg
from football_ai.data.historical import load_historical_matches
from football_ai.data.historical import sort_key_match
from football_ai.data.odds import get_odds_comparison, implied_probabilities_from_decimal


def _float_or_default(s: str | None, default: float) -> float:
    if s is None or str(s).strip() == "":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _parse_handicap_line(s: str | None) -> float | None:
    """竞彩让球数：-1 主让1球，+1 主受让1球，返回 -1 / 1，否则 None（用默认 0.5）。"""
    if s is None or str(s).strip() == "":
        return None
    s = str(s).strip()
    try:
        v = int(s)
        return float(v)
    except ValueError:
        pass
    if s in ("+1", "1"):
        return 1.0
    if s == "-1":
        return -1.0
    return None


def _load_injuries_from_dir(dir_path: Path) -> list[dict]:
    """从文件夹内所有 CSV 读取伤停，合并为 list[dict]，每项含 team, player, reason。"""
    import pandas as pd
    out: list[dict] = []
    if not dir_path.exists() or not dir_path.is_dir():
        return out
    for f in sorted(dir_path.glob("*.csv")):
        try:
            df = pd.read_csv(f, encoding="utf-8")
        except Exception:
            continue
        if df.empty:
            continue
        cols = [c.strip() for c in df.columns]
        team_col = "team" if "team" in cols else ("team_name" if "team_name" in cols else None)
        player_col = "player" if "player" in cols else ("player_name" if "player_name" in cols else None)
        reason_col = "reason" if "reason" in cols else ("type" if "type" in cols else None)
        if not team_col or not player_col or not reason_col:
            continue
        for _, row in df.iterrows():
            team = row.get(team_col)
            player = row.get(player_col)
            reason = row.get(reason_col)
            if pd.isna(team) or pd.isna(player):
                continue
            team = str(team).strip()
            player = str(player).strip()
            reason = str(reason).strip() if not pd.isna(reason) else "受伤"
            # 归一化 reason 供 adjust_xg 使用：伤/伤疑/停赛/缺阵
            if "伤疑" in reason or reason == "出战成疑":
                reason = "出战成疑"
            elif reason in ("伤", "受伤", "停赛", "缺阵", "其他原因"):
                pass
            elif "伤" in reason or "停赛" in reason or "缺阵" in reason:
                reason = "受伤" if reason != "停赛" else "停赛"
            out.append({"team": team, "player": player, "reason": reason or "受伤"})
    return out


def _ensemble_weight() -> float:
    """从 config/settings.yaml 读取 predictions.ensemble_ml_weight，默认 0.5。"""
    cfg_path = ROOT / "config" / "settings.yaml"
    if not cfg_path.exists():
        return 0.5
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return float((data.get("predictions") or {}).get("ensemble_ml_weight", 0.5))
    except Exception:
        return 0.5


def _odds_blend_weight() -> float:
    """从 config/settings.yaml 读取 predictions.odds_blend_weight，默认 0（不参考盘口）。"""
    cfg_path = ROOT / "config" / "settings.yaml"
    if not cfg_path.exists():
        return 0.0
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return float((data.get("predictions") or {}).get("odds_blend_weight", 0.0))
    except Exception:
        return 0.0


def _blend_wdl_with_odds(
    wdl: dict[str, float],
    odds_home: float,
    odds_draw: float,
    odds_away: float,
    odds_weight: float,
) -> dict[str, float]:
    """用赔率隐含概率与模型概率加权： (1-w)*模型 + w*隐含，再归一化。仅当 odds_weight > 0 且赔率有效时使用。"""
    if odds_weight <= 0 or odds_home <= 0 or odds_draw <= 0 or odds_away <= 0:
        return wdl
    imp_h, imp_d, imp_a = implied_probabilities_from_decimal(odds_home, odds_draw, odds_away)
    w = max(0.0, min(1.0, odds_weight))
    h = (1 - w) * (wdl.get("主胜") or 0) + w * imp_h
    d = (1 - w) * (wdl.get("平") or 0) + w * imp_d
    a = (1 - w) * (wdl.get("客胜") or 0) + w * imp_a
    total = h + d + a
    if total <= 0:
        return wdl
    return {"主胜": h / total, "平": d / total, "客胜": a / total}


def _blend_wdl(wdl_p: dict, wdl_m: dict, ml_weight: float) -> dict[str, float]:
    """融合 Poisson 与 ML 的胜负平概率： (1-w)*P + w*M，再归一化。"""
    w = max(0.0, min(1.0, ml_weight))
    p_h = (wdl_p.get("主胜") or 0) or 0
    p_d = (wdl_p.get("平") or 0) or 0
    p_a = (wdl_p.get("客胜") or 0) or 0
    m_h = (wdl_m.get("主胜") or 0) or 0
    m_d = (wdl_m.get("平") or 0) or 0
    m_a = (wdl_m.get("客胜") or 0) or 0
    h = (1 - w) * p_h + w * m_h
    d = (1 - w) * p_d + w * m_d
    a = (1 - w) * p_a + w * m_a
    total = h + d + a
    if total <= 0:
        return {"主胜": 1/3, "平": 1/3, "客胜": 1/3}
    return {"主胜": h / total, "平": d / total, "客胜": a / total}


# 五大联赛 league_id -> 默认 ML 模型文件名（不指定 --ml-model 时按联赛自动选用）
DEFAULT_ML_ARTIFACTS: dict[str, str] = {
    "EPL": "xgb_epl_2024.pkl",
    "La_Liga": "xgb_la_liga_2024.pkl",
    "Bundesliga": "xgb_bundesliga_2024.pkl",
    "Serie_A": "xgb_seriea_2024.pkl",
    "Ligue_1": "xgb_ligue_1_2024.pkl",
}


def _load_team_mapping(path: Path | None) -> dict[str, str] | None:
    """从 CSV（statsbomb_name/en -> report_name/zh）加载队名映射，供预期 xG 表英文队名匹配。"""
    if path is None or not path.exists():
        return None
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = (row.get("statsbomb_name") or row.get("en") or "").strip()
            v = (row.get("report_name") or row.get("zh") or "").strip()
            if k:
                out[k] = v or k
    return out if out else None


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="批量预测：从 CSV 读赛程，可选伤停目录与让球数，输出胜负平/让球/比分")
    p.add_argument("csv_path", nargs="?", type=Path, default=ROOT / "data" / "todays_matches.csv", help="赛程 CSV 路径")
    p.add_argument("--default-xg", type=float, default=1.0, help="未填 xG 且未从预期 xG 表匹配到时使用的默认值（主客相同）")
    p.add_argument("--expected-xg", type=Path, default=None, help="赛前预期 xG 表 CSV：按球队(team,xg,xg_home,xg_away)或按场次(round,home_team,away_team,xg_home,xg_away)，未填 xG 时从此表匹配")
    p.add_argument("--expected-xg-season", type=int, default=None, help="预期 xG 按球队表时的赛季年（如 2024），可选")
    p.add_argument("--team-mapping", type=Path, default=None, help="队名映射 CSV（预期 xG 表为英文队名时用，列 en/statsbomb_name, zh/report_name）")
    p.add_argument("--injuries-dir", type=Path, default=ROOT / "data" / "todays_injuries", help="伤停 CSV 所在文件夹，会合并后按主客队应用")
    p.add_argument("--out", type=Path, default=None, help="结果输出 CSV（不指定则只打印）")
    p.add_argument("--model", choices=["poisson", "ml", "ensemble"], default="poisson", help="预测源：poisson / ml / ensemble（Poisson 与 ML 融合）")
    p.add_argument("--ml-model", type=Path, default=None, help="ML 模型 pkl 路径；不填则按 league_id 从 artifacts/ 自动选 xgb_{联赛}_2024.pkl（五大联赛）")
    p.add_argument("--historical", type=Path, default=None, help="历史场次目录或 CSV；不填 --ml-model 时需为 data/historical（按联赛子目录加载）")
    p.add_argument("--season", type=int, default=None, help="赛季年（--model ml 时建议填写，与历史数据一致）")
    args = p.parse_args()

    path = Path(args.csv_path)
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            rows.append(r)

    if not rows:
        print("CSV 无数据。", file=sys.stderr)
        sys.exit(1)

    # 伤停：从目录合并所有 CSV
    injuries_dir = Path(args.injuries_dir)
    all_injuries = _load_injuries_from_dir(injuries_dir) if injuries_dir else []

    default_xg = args.default_xg
    expected_xg_path = Path(args.expected_xg) if args.expected_xg else None
    team_mapping = _load_team_mapping(args.team_mapping) if args.team_mapping else None
    results: list[dict] = []

    use_ml = args.model == "ml"
    use_ensemble = args.model == "ensemble"
    ml_artifact = None
    hist_matches_sorted: list[dict] = []
    auto_ml_by_league = False
    historical_parent: Path | None = None
    ml_artifact_cache: dict[str, dict] = {}
    hist_cache: dict[str, list[dict]] = {}
    ensemble_ml_weight = _ensemble_weight() if use_ensemble else 0.0
    odds_blend_weight = _odds_blend_weight()
    if use_ml or use_ensemble:
        if not args.historical or not Path(args.historical).exists():
            print("--model ml 与 ensemble 需指定 --historical（目录如 data/historical，或单 CSV）。", file=sys.stderr)
            sys.exit(1)
        if args.ml_model and Path(args.ml_model).exists():
            ml_artifact = load_artifact(args.ml_model)
            if args.historical.is_file():
                hist_matches_sorted = load_historical_matches(path=args.historical)
            else:
                hist_matches_sorted = load_historical_matches(directory=args.historical)
            hist_matches_sorted = sorted(hist_matches_sorted, key=sort_key_match)
        else:
            auto_ml_by_league = True
            historical_parent = Path(args.historical)
            if historical_parent.is_file():
                print("未指定 --ml-model 时 --historical 需为目录（如 data/historical），以便按联赛加载。", file=sys.stderr)
                sys.exit(1)

    for r in rows:
        match_id = (r.get("match_id") or "").strip()
        league_id = (r.get("league_id") or "EPL").strip()
        league_zh = (r.get("league_zh") or "").strip()
        home = (r.get("home_team") or "").strip()
        away = (r.get("away_team") or "").strip()
        handicap_note = (r.get("handicap_note") or "").strip()
        if not home or not away:
            continue
        try:
            round_ = int(float(r.get("round") or 1))
        except (ValueError, TypeError):
            round_ = 1

        # xG：优先用赛程 CSV 已填；未填则从预期 xG 表匹配（按球队/按场次）；再否则用 default_xg
        csv_xh, csv_xa = r.get("xg_home"), r.get("xg_away")
        csv_has_xg = (
            csv_xh is not None and str(csv_xh).strip() != ""
            and csv_xa is not None and str(csv_xa).strip() != ""
        )
        if csv_has_xg:
            xg_h = _float_or_default(csv_xh, default_xg)
            xg_a = _float_or_default(csv_xa, default_xg)
        elif expected_xg_path:
            xh, xa, _, _ = load_expected_xg(
                path=expected_xg_path,
                home_team=home,
                away_team=away,
                round_=round_,
                season=args.expected_xg_season,
                team_name_mapping=team_mapping,
            )
            if xh is not None and xa is not None:
                xg_h, xg_a = float(xh), float(xa)
            else:
                xg_h = _float_or_default(csv_xh, default_xg)
                xg_a = _float_or_default(csv_xa, default_xg)
        else:
            xg_h = _float_or_default(csv_xh, default_xg)
            xg_a = _float_or_default(csv_xa, default_xg)

        # 按主客队过滤伤停并微调 xG
        home_list = [{"player": x["player"], "reason": x["reason"]} for x in all_injuries if (x.get("team") or "").strip() == home]
        away_list = [{"player": x["player"], "reason": x["reason"]} for x in all_injuries if (x.get("team") or "").strip() == away]
        if home_list or away_list:
            xg_h, xg_a = adjust_xg_for_injuries(xg_h, xg_a, home_list, away_list)

        handicap_line = _parse_handicap_line(handicap_note)

        current_ml_artifact = ml_artifact
        current_hist: list[dict] = list(hist_matches_sorted)
        current_ml_path: Path | None = args.ml_model
        if (use_ml or use_ensemble) and auto_ml_by_league and historical_parent is not None:
            if league_id not in ml_artifact_cache and league_id in DEFAULT_ML_ARTIFACTS:
                pkl_path = ROOT / "artifacts" / DEFAULT_ML_ARTIFACTS[league_id]
                if pkl_path.exists():
                    ml_artifact_cache[league_id] = load_artifact(pkl_path)
                else:
                    ml_artifact_cache[league_id] = None
            if league_id not in hist_cache:
                league_dir = historical_parent / league_id
                if league_dir.is_dir():
                    hist_cache[league_id] = sorted(load_historical_matches(directory=league_dir), key=sort_key_match)
                else:
                    hist_cache[league_id] = []
            current_ml_artifact = ml_artifact_cache.get(league_id) if league_id in DEFAULT_ML_ARTIFACTS else None
            current_hist = hist_cache.get(league_id) or []
            current_ml_path = (ROOT / "artifacts" / DEFAULT_ML_ARTIFACTS[league_id]) if league_id in DEFAULT_ML_ARTIFACTS else None

        pred_poisson = get_predictions(
            home,
            away,
            round_,
            metrics={"xg": {"home": xg_h, "away": xg_a}},
            available=True,
            expected_xg=True,
            league_id=league_id,
            handicap_line=handicap_line,
        )

        if use_ml and current_ml_artifact is not None and current_hist and current_ml_path:
            season = args.season or max((int(m.get("season", 0)) for m in current_hist), default=0)
            past = [m for m in current_hist if int(m.get("season", 0)) == season and int(m.get("round", 0)) < round_]
            if any((m.get("league") or "").strip() for m in current_hist):
                past = [m for m in past if (m.get("league") or "").strip() == league_id]
            match_dict = {
                "home_team": home,
                "away_team": away,
                "round": round_,
                "season": season,
                "league": league_id,
                "xg_home": xg_h,
                "xg_away": xg_a,
                "goals_home": 0,
                "goals_away": 0,
            }
            try:
                pred = predictions_from_ml(
                    home, away, round_,
                    match=match_dict,
                    past_matches=past,
                    artifact_path=current_ml_path,
                    handicap_line=handicap_line,
                )
            except Exception as e:
                pred = {"available": False, "summary_zh": f"ML 预测异常: {e}"}
        elif use_ensemble and current_ml_artifact is not None and current_hist and current_ml_path:
            season = args.season or max((int(m.get("season", 0)) for m in current_hist), default=0)
            past = [m for m in current_hist if int(m.get("season", 0)) == season and int(m.get("round", 0)) < round_]
            if any((m.get("league") or "").strip() for m in current_hist):
                past = [m for m in past if (m.get("league") or "").strip() == league_id]
            match_dict = {
                "home_team": home,
                "away_team": away,
                "round": round_,
                "season": season,
                "league": league_id,
                "xg_home": xg_h,
                "xg_away": xg_a,
                "goals_home": 0,
                "goals_away": 0,
            }
            try:
                pred_ml = predictions_from_ml(
                    home, away, round_,
                    match=match_dict,
                    past_matches=past,
                    artifact_path=current_ml_path,
                    handicap_line=handicap_line,
                )
            except Exception as e:
                pred_ml = {"available": False}
            if pred_poisson.get("available") and pred_ml.get("available"):
                wdl_blend = _blend_wdl(
                    pred_poisson.get("win_draw_lose") or {},
                    pred_ml.get("win_draw_lose") or {},
                    ensemble_ml_weight,
                )
                pred = {
                    "available": True,
                    "disclaimer_zh": pred_poisson.get("disclaimer_zh", ""),
                    "win_draw_lose": wdl_blend,
                    "handicap": pred_poisson.get("handicap"),
                    "half_full": pred_poisson.get("half_full"),
                    "score": pred_poisson.get("score"),
                    "summary_zh": f"（Poisson 与 ML 融合，ML 权重 {ensemble_ml_weight:.0%}；仅供参考，不构成投注建议。）",
                }
            else:
                pred = pred_poisson
        else:
            pred = pred_poisson

        if not pred.get("available"):
            results.append({
                "match_id": match_id,
                "league_zh": league_zh,
                "home": home,
                "away": away,
                "handicap_note": handicap_note,
                "主胜": None,
                "平": None,
                "客胜": None,
                "最可能比分": pred.get("summary_zh", "无 xG"),
                "次可能比分": "",
                "第三可能比分": "",
                "让胜": None,
                "让平": None,
                "让负": None,
                "value_主胜": 0,
                "value_平": 0,
                "value_客胜": 0,
            })
            continue

        wdl = pred.get("win_draw_lose") or {}
        oh_raw = r.get("odds_home") or r.get("win_home") or r.get("主胜")
        od_raw = r.get("odds_draw") or r.get("draw") or r.get("平")
        oa_raw = r.get("odds_away") or r.get("win_away") or r.get("客胜")
        oh_f = od_f = oa_f = None
        try:
            if oh_raw is not None and od_raw is not None and oa_raw is not None:
                oh_f, od_f, oa_f = float(oh_raw), float(od_raw), float(oa_raw)
                if oh_f > 0 and od_f > 0 and oa_f > 0 and odds_blend_weight > 0:
                    wdl = _blend_wdl_with_odds(wdl, oh_f, od_f, oa_f, odds_blend_weight)
        except (TypeError, ValueError):
            pass
        hcp = pred.get("handicap") or {}
        score = pred.get("score") or {}
        detail = score.get("详情") or []
        second_score = detail[1][0] if len(detail) > 1 else ""
        third_score = detail[2][0] if len(detail) > 2 else ""
        res_row = {
            "match_id": match_id,
            "league_zh": league_zh,
            "home": home,
            "away": away,
            "handicap_note": handicap_note,
            "xg_home": xg_h,
            "xg_away": xg_a,
            "主胜": wdl.get("主胜"),
            "平": wdl.get("平"),
            "客胜": wdl.get("客胜"),
            "最可能比分": score.get("最可能比分"),
            "次可能比分": second_score,
            "第三可能比分": third_score,
            "让胜": hcp.get("让胜"),
            "让平": hcp.get("让平"),
            "让负": hcp.get("让负"),
            "value_主胜": 0,
            "value_平": 0,
            "value_客胜": 0,
        }
        if oh_f is not None and od_f is not None and oa_f is not None and oh_f > 0 and od_f > 0 and oa_f > 0:
            comp = get_odds_comparison(wdl, odds_home=oh_f, odds_draw=od_f, odds_away=oa_f)
            if comp and comp.get("value_indicators"):
                vi = comp["value_indicators"]
                res_row["value_主胜"] = 1 if vi.get("主胜") else 0
                res_row["value_平"] = 1 if vi.get("平") else 0
                res_row["value_客胜"] = 1 if vi.get("客胜") else 0
        results.append(res_row)

    # 打印
    if expected_xg_path and expected_xg_path.exists():
        print("使用预期 xG 表: %s" % expected_xg_path)
    elif expected_xg_path:
        print("未找到预期 xG 表 %s，未匹配到的场次使用默认 xG 1.0" % expected_xg_path)
    print("=" * 72)
    model_label = "基于 Poisson 与 ML 融合" if use_ensemble else ("基于 ML 模型" if use_ml else "基于赛前预期 xG + Poisson")
    if odds_blend_weight > 0:
        model_label += "，含盘口参考 %.0f%%" % (odds_blend_weight * 100)
    print("批量预测结果（%s，仅供参考；不构成投注建议）" % model_label)
    print("=" * 72)
    for res in results:
        mid = res["match_id"]
        league = res["league_zh"]
        vs = f"{res['home']} vs {res['away']}"
        hcp = res["handicap_note"]
        xgh = res.get("xg_home")
        xga = res.get("xg_away")
        xg_str = f"  xG {xgh:.2f}-{xga:.2f}" if xgh is not None and xga is not None else ""
        p1 = res["主胜"]
        pd = res["平"]
        p2 = res["客胜"]
        r_win = res.get("让胜")
        r_draw = res.get("让平")
        r_lose = res.get("让负")
        if p1 is not None and pd is not None and p2 is not None:
            line = f"({mid}) {league}  {vs}  [让球{hcp}]{xg_str}  主胜 {p1*100:.0f}%  平 {pd*100:.0f}%  客胜 {p2*100:.0f}%  最可能 {res['最可能比分']}"
            if r_win is not None and r_lose is not None:
                line += f"  | 让胜 {r_win*100:.0f}%  让平 {(r_draw or 0)*100:.0f}%  让负 {r_lose*100:.0f}%"
        else:
            line = f"({mid}) {league}  {vs}  [让球{hcp}]{xg_str}  {res['最可能比分']}"
        print(line)
    print("=" * 72)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_fields = ["match_id", "league_zh", "home", "away", "handicap_note", "xg_home", "xg_away", "主胜", "平", "客胜", "最可能比分", "次可能比分", "第三可能比分", "让胜", "让平", "让负", "value_主胜", "value_平", "value_客胜"]
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
            w.writeheader()
            for res in results:
                row = {}
                for k in out_fields:
                    v = res.get(k)
                    if k in ("主胜", "平", "客胜", "让胜", "让平", "让负") and isinstance(v, (int, float)):
                        row[k] = f"{v*100:.2f}%"
                    elif k in ("xg_home", "xg_away") and v is not None:
                        row[k] = f"{float(v):.4f}"
                    elif v is not None:
                        row[k] = v
                w.writerow(row)
        print(f"已写入 {out_path}")


if __name__ == "__main__":
    main()
