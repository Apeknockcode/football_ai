#!/usr/bin/env bash
# Football AI 启动脚本：安装依赖并运行 CLI / 数据与校准
# 用法：
#   ./run.sh                    # 默认生成赛前报告（曼联 vs 利物浦 第28轮）
#   ./run.sh pre --home 阿森纳 --away 切尔西 --round 15
#   ./run.sh post --home 曼联 --away 利物浦 --round 28 --out report.txt
#   ./run.sh fetch 2025         # 拉取 EPL 2024/25 → data/historical/EPL/pl_2025.csv
#   ./run.sh fetch 2026         # 拉取 EPL 2025/26（2026 年）单赛季
#   ./run.sh fetch all 2026     # 一键拉取 2026 年：EPL/西甲/德甲/意甲/法甲
#   ./run.sh fetch 2024 2025    # 拉取 EPL 多赛季
#   ./run.sh fetch La_Liga 2024 2025  # 拉取西甲 2024、2025
#   ./run.sh fetch cup UCL 2025       # 拉取欧冠 2024/25（FBref）
#   ./run.sh fetch fbref EPL 2026     # 第四版：拉取联赛 FBref → pl_YYYY_fbref.csv
#   ./run.sh fetch fotmob EPL 2026    # 第四版：soccerdata 拉取 FotMob → pl_YYYY_fotmob.csv
#   ./run.sh fetch fd EPL 2025       # Football-Data.co.uk（赛果+赔率，无xG）→ pl_YYYY_fd.csv
#   ./run.sh fetch sofascore EPL 2025  # Sofascore → pl_YYYY_sofascore.csv
#   ./run.sh fetch espn EPL 2025     # ESPN → pl_YYYY_espn.csv
#   ./run.sh fetch whoscored EPL 2025   # WhoScored（需 Selenium）→ pl_YYYY_whoscored.csv
#   ./run.sh fetch whoscored all 2025   # WhoScored 五大联赛
#   ./run.sh merge EPL 2026          # 第四版：合并多源 → pl_YYYY.csv
#   ./run.sh merge-five              # 合并五大联赛 → data/historical/Combined/
#   ./run.sh calibrate [--league EPL]  # 生成 config/calibration_{league_id}.yaml
#   ./run.sh backtest [--league EPL]  # 回测
#   ./run.sh report-sources           # 模型数据与来源报告
#   ./run.sh validate-data            # 校验历史数据质量（无效场次统计）
#   ./run.sh validate-data --merged-2024   # 2024 合并数据自动化核对（场次/重复/轮次/比分）
#   ./run.sh validate-data --merged-2024 --ref data/historical/_common/validation_ref_2024_sample.csv  # 与参考样本 diff
#   ./run.sh predict-today [--date YYYY-MM-DD]  # 批量预测，结果存 data/YYYY-MM-DD/
#   ./run.sh today-full [--date YYYY-MM-DD]     # 一键：拉赛程 → 拉盘口(需 THE_ODDS_API_KEY) → 批量预测

set -e
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
SCRIPTS_DIR="scripts"

# 若无虚拟环境则创建
if [ ! -d "$VENV_DIR" ]; then
  echo "创建虚拟环境: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# 安装/更新依赖与包（首次或依赖变更时执行）
if [ ! -f "${VENV_DIR}/.installed" ] || [ requirements.txt -nt "${VENV_DIR}/.installed" ] || [ pyproject.toml -nt "${VENV_DIR}/.installed" ]; then
  echo "安装依赖..."
  "$PIP" install -q -e .
  touch "${VENV_DIR}/.installed"
fi

# 数据与校准：fetch / calibrate / backtest
case "${1:-}" in
  fetch)
    shift
    if [ $# -eq 0 ]; then
      "$PYTHON" "$SCRIPTS_DIR/fetch_historical_understat.py"
    elif [ "$1" = "all" ]; then
      shift
      if [ $# -eq 0 ]; then
        echo "用法: ./run.sh fetch all <赛季年...>  例: ./run.sh fetch all 2026" 1>&2
        exit 1
      fi
      for league in EPL La_Liga Bundesliga Serie_A Ligue_1; do
        echo "拉取 $league 赛季: $* ..."
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_understat.py" --league "$league" --season "$@" || true
      done
      echo "一键拉取完成。"
      exit 0
    elif [ "$1" = "cup" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch cup <杯赛id> [赛季年...]" 1>&2
        echo "杯赛 id: UCL（欧冠）、UEL（欧联）、FA_Cup（足总杯）、League_Cup（联赛杯）" 1>&2
        echo "示例:   ./run.sh fetch cup UCL 2025" 1>&2
        exit 1
      fi
      CUP="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_fbref_cups.py" --cup "$CUP"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_fbref_cups.py" --cup "$CUP" --season "$@"
      fi
    elif [ "$1" = "fbref" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch fbref <联赛id> [赛季年...]  第四版多源，例: ./run.sh fetch fbref EPL 2026" 1>&2
        exit 1
      fi
      LEAGUE="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_fbref_leagues.py" --league "$LEAGUE"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_fbref_leagues.py" --league "$LEAGUE" --season "$@"
      fi
    elif [ "$1" = "fotmob" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch fotmob <联赛id> [赛季年...]  第四版多源（soccerdata），例: ./run.sh fetch fotmob EPL 2026" 1>&2
        exit 1
      fi
      LEAGUE="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_soccerdata.py" --league "$LEAGUE"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_soccerdata.py" --league "$LEAGUE" --season "$@"
      fi
    elif [ "$1" = "fd" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch fd <联赛id> [赛季年...]  Football-Data.co.uk，例: ./run.sh fetch fd EPL 2025" 1>&2
        exit 1
      fi
      LEAGUE="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_football_data_uk.py" --league "$LEAGUE"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_football_data_uk.py" --league "$LEAGUE" --season "$@"
      fi
    elif [ "$1" = "sofascore" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch sofascore <联赛id> [赛季年...]  使用独立脚本（不依赖 soccerdata TLS）" 1>&2
        exit 1
      fi
      LEAGUE="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_sofascore_standalone.py" --league "$LEAGUE"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_sofascore_standalone.py" --league "$LEAGUE" --season "$@"
      fi
    elif [ "$1" = "espn" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch espn <联赛id> [赛季年...]  使用独立脚本（不依赖 soccerdata TLS）" 1>&2
        exit 1
      fi
      LEAGUE="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_espn_standalone.py" --league "$LEAGUE"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_espn_standalone.py" --league "$LEAGUE" --season "$@"
      fi
    elif [ "$1" = "whoscored" ]; then
      shift
      if [ $# -lt 1 ]; then
        echo "用法: ./run.sh fetch whoscored <联赛id|all> [赛季年...]  需 Selenium" 1>&2
        echo "  例: ./run.sh fetch whoscored EPL 2025" 1>&2
        echo "      ./run.sh fetch whoscored all 2025   # 五大联赛" 1>&2
        exit 1
      fi
      LEAGUE="$1"
      shift
      if [ "$LEAGUE" = "all" ]; then
        if [ $# -eq 0 ]; then
          echo "用法: ./run.sh fetch whoscored all <赛季年...>  例: ./run.sh fetch whoscored all 2025" 1>&2
          exit 1
        fi
        for lg in EPL La_Liga Bundesliga Serie_A Ligue_1; do
          echo "抓取 WhoScored $lg 赛季: $* ..."
          "$PYTHON" "$SCRIPTS_DIR/fetch_historical_soccerdata_extra.py" --source whoscored --league "$lg" --season "$@" || true
        done
        echo "WhoScored 五大联赛抓取完成。"
      else
        if [ $# -eq 0 ]; then
          "$PYTHON" "$SCRIPTS_DIR/fetch_historical_soccerdata_extra.py" --source whoscored --league "$LEAGUE"
        else
          "$PYTHON" "$SCRIPTS_DIR/fetch_historical_soccerdata_extra.py" --source whoscored --league "$LEAGUE" --season "$@"
        fi
      fi
    elif [ -n "$1" ] && [ "$1" -eq "$1" ] 2>/dev/null; then
      "$PYTHON" "$SCRIPTS_DIR/fetch_historical_understat.py" --season "$@"
    else
      LEAGUE="$1"
      shift
      if [ $# -eq 0 ]; then
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_understat.py" --league "$LEAGUE"
      else
        "$PYTHON" "$SCRIPTS_DIR/fetch_historical_understat.py" --league "$LEAGUE" --season "$@"
      fi
    fi
    exit 0
    ;;
  calibrate)
    shift
    "$PYTHON" "$SCRIPTS_DIR/calibrate_pl.py" "$@"
    exit 0
    ;;
  backtest)
    shift
    "$PYTHON" "$SCRIPTS_DIR/backtest_pl.py" "$@"
    exit 0
    ;;
  merge)
    shift
    if [ $# -lt 2 ]; then
      echo "用法: ./run.sh merge <联赛id> <赛季年>  第四版多源合并，例: ./run.sh merge EPL 2026" 1>&2
      exit 1
    fi
    "$PYTHON" "$SCRIPTS_DIR/merge_league_sources.py" --league "$1" --season "$2"
    exit 0
    ;;
  merge-five)
    shift
    "$PYTHON" "$SCRIPTS_DIR/merge_five_leagues.py" "$@"
    exit 0
    ;;
  report-sources)
    shift
    "$PYTHON" "$SCRIPTS_DIR/report_model_data_sources.py" "$@"
    exit 0
    ;;
  validate-data)
    shift
    "$PYTHON" "$SCRIPTS_DIR/validate_historical_data.py" "$@"
    exit 0
    ;;
  validate-2024)
    shift
    "$PYTHON" "$SCRIPTS_DIR/validate_historical_data.py" --merged-2024 "$@"
    exit 0
    ;;
  validate-2025)
    shift
    "$PYTHON" "$SCRIPTS_DIR/validate_historical_data.py" --merged-2025 "$@"
    exit 0
    ;;
  validate-2026)
    shift
    "$PYTHON" "$SCRIPTS_DIR/validate_historical_data.py" --merged-2026 "$@"
    exit 0
    ;;
  predict-today)
    shift
    DATE_DIR="data/$(date +%Y-%m-%d)"
    while [ $# -gt 0 ]; do
      if [ "$1" = "--date" ] && [ -n "${2:-}" ]; then
        DATE_DIR="data/$2"
        shift 2
        continue
      fi
      break
    done
    mkdir -p "$DATE_DIR" "$DATE_DIR/todays_injuries"
    CSV="${1:-$DATE_DIR/todays_matches.csv}"
    [ -n "$1" ] && shift
    "$PYTHON" "$SCRIPTS_DIR/predict_batch.py" "$CSV" \
      --expected-xg "data/expected_xg_teams.csv" \
      --out "$DATE_DIR/todays_predictions.csv" \
      --injuries-dir "$DATE_DIR/todays_injuries" \
      "$@"
    exit 0
    ;;
  today-full)
    shift
    DATE_STR="$(date +%Y-%m-%d)"
    while [ $# -gt 0 ]; do
      if [ "$1" = "--date" ] && [ -n "${2:-}" ]; then
        DATE_STR="$2"
        shift 2
        continue
      fi
      break
    done
    DATE_DIR="data/$DATE_STR"
    mkdir -p "$DATE_DIR" "$DATE_DIR/todays_injuries"
    CSV="$DATE_DIR/todays_matches.csv"
    echo "1) 拉取今日五大联赛赛程..."
    "$PYTHON" "$SCRIPTS_DIR/fetch_todays_fixtures.py" --date "$DATE_STR" --out "$CSV"
    if [ -n "${THE_ODDS_API_KEY:-}" ]; then
      echo "2) 拉取盘口并合并..."
      "$PYTHON" "$SCRIPTS_DIR/fetch_odds.py" --csv "$CSV"
    else
      echo "2) 跳过盘口（未设置 THE_ODDS_API_KEY）"
    fi
    echo "3) 批量预测..."
    "$PYTHON" "$SCRIPTS_DIR/predict_batch.py" "$CSV" \
      --expected-xg "data/expected_xg_teams.csv" \
      --out "$DATE_DIR/todays_predictions.csv" \
      --injuries-dir "$DATE_DIR/todays_injuries" \
      --historical data/historical
    echo "完成 → $DATE_DIR/todays_predictions.csv"
    exit 0
    ;;
esac

# 若未传参则使用默认示例（赛前报告，含比赛时间）
if [ $# -eq 0 ]; then
  echo "生成示例赛前报告（曼联 vs 利物浦 第28轮）..."
  "$PYTHON" -m football_ai.cli pre --home 曼联 --away 利物浦 --round 28 --date 2025-03-15 --time 20:00
  exit 0
fi

# 否则将参数交给 CLI
"$PYTHON" -m football_ai.cli "$@"
