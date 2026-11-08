@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\PS2Online\venv"

if not exist "%VENV%\Scripts\pythonw.exe" (
    echo [PS2 Online] Primeira execucao: preparando o ambiente, aguarde...
    where python >nul 2>nul || (
        echo.
        echo Python nao encontrado. Instale o Python 3.11+ em https://www.python.org/downloads/
        echo e marque "Add python.exe to PATH" na instalacao.
        pause
        exit /b 1
    )
    python -m venv "%VENV%" || (pause & exit /b 1)
)

"%VENV%\Scripts\python.exe" -c "import PySide6, av, mss, pyaudiowpatch, vgamepad" 2>nul || (
    echo [PS2 Online] Instalando dependencias...
    rem O driver ViGEmBus so e necessario para quem HOSPEDA; instale-o separadamente.
    set VGAMEPAD_SKIP_VIGEMBUS_INSTALL=true
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)

start "" "%VENV%\Scripts\pythonw.exe" app.py
