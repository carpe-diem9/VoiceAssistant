@echo off
echo ==========================================
echo    AI Voice Assistant - Startup Script
echo ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

:: Navigate to backend directory
cd /d "%~dp0backend"

:: Check if virtual environment exists
if not exist "venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

:: Install dependencies
echo [INFO] Installing Python dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo    Starting Backend Server (FastAPI)
echo ==========================================
echo    URL: http://localhost:8000
echo    Docs: http://localhost:8000/docs
echo    Press Ctrl+C to stop
echo ==========================================
echo.

:: Start uvicorn server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
