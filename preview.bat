@echo off
rem Double-click to start the live preview (same as: uv run python scripts/dev.py).
rem Close the window or press Ctrl+C to stop it.
title Pollen map preview
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo uv was not found on PATH. Install it from https://docs.astral.sh/uv/ and try again.
  pause
  exit /b 1
)

uv run python scripts/dev.py %*

echo.
echo Preview stopped.
pause
