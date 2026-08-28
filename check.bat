@echo off
setlocal enabledelayedexpansion
set PY=venv\Scripts\python.exe

echo [check] ruff lint...
%PY% -m ruff check .
if errorlevel 1 (
    echo [FALLO] ruff check
    exit /b 1
)

echo [check] ruff format --check...
%PY% -m ruff format --check .
if errorlevel 1 (
    echo [FALLO] ruff format --check
    exit /b 1
)

echo [check] pytest...
%PY% -m pytest tests\ -q
if errorlevel 1 (
    echo [FALLO] pytest
    exit /b 1
)

echo [OK] todo paso
exit /b 0
