@echo off
REM Compila el .exe de Aliado Libre. Siempre con el Python del venv (3.12).
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo No se encontro venv\Scripts\python.exe
    exit /b 1
)
"venv\Scripts\python.exe" scripts\build_exe.py
