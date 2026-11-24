@echo off
cd /d "%~dp0"
if not exist "src\adb.exe" (
  echo 还没有 adb，先双击 setup.bat
  pause
  exit /b 1
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "src\gui.py"
  exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
  start "" python "src\gui.py"
  exit /b 0
)
echo [X] 没找到 Python，请先安装 Python 3.10+
pause
