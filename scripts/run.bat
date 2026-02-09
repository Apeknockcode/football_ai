@echo off
REM Football AI 启动脚本（Windows）
REM 用法: scripts\run.bat  或  scripts\run.bat pre --home 曼联 --away 利物浦 --round 28

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo 创建虚拟环境 .venv
  python -m venv .venv
  if errorlevel 1 (
    echo 请确保已安装 Python 并加入 PATH
    exit /b 1
  )
)

echo 安装依赖...
.venv\Scripts\pip install -q -e .

if "%~1"=="" (
  echo 生成示例赛前报告（曼联 vs 利物浦 第28轮）...
  .venv\Scripts\python -m football_ai.cli pre --home 曼联 --away 利物浦 --round 28
) else (
  .venv\Scripts\python -m football_ai.cli %*
)
