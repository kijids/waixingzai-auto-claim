@echo off
cd /d "%~dp0"
echo === 首次准备：下载 adb 和 OCR 运行库 ===
where python >nul 2>nul
if errorlevel 1 (
  echo [X] 没找到 python，请先装 Python 3.10+ 并勾选 Add to PATH
  pause
  exit /b 1
)
python tools\setup.py
echo.
pause
