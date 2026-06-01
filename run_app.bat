@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS_FILE=%CD%\requirements.txt"
set "MAIN_FILE=%CD%\main.py"

if not exist "%MAIN_FILE%" (
    echo [ERROR] main.py was not found.
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo [INFO] Creating virtual environment...
    py -3 -m venv "%VENV_DIR%" >nul 2>&1
    if errorlevel 1 (
        python -m venv "%VENV_DIR%"
        if errorlevel 1 (
            echo [ERROR] Failed to create virtual environment.
            echo [HINT] Check whether Python is installed.
            pause
            exit /b 1
        )
    )
)

echo [INFO] Installing / syncing requirements...
"%VENV_PYTHON%" -m pip install -r "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo [INFO] Starting application...
"%VENV_PYTHON%" "%MAIN_FILE%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Application exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
