@echo off
cd /d "%~dp0"

echo ============================================
echo  SEO Brain - starting (native, no Docker)
echo ============================================
echo.
echo NOTE: Docker on this machine currently blocks outbound HTTPS
echo from inside containers (likely VPN/firewall/antivirus only
echo trusting the real network adapter). Until that is fixed,
echo this script runs the backend and frontend directly on Windows.
echo Once Docker networking works again, use start-docker.bat instead.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv not found. Run setup first:
    echo   uv venv --python 3.13 .venv
    echo   uv pip install --python .venv -e "backend[dev]"
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo ERROR: frontend\node_modules not found. Run setup first:
    echo   cd frontend
    echo   corepack pnpm install
    pause
    exit /b 1
)

echo Starting backend (http://127.0.0.1:8000) ...
start "SEO Brain - backend" cmd /k ".venv\Scripts\python.exe backend\cli\api.py --host 127.0.0.1 --port 8000"

echo Starting frontend (http://127.0.0.1:3000) ...
start "SEO Brain - frontend" cmd /k "cd /d "%~dp0frontend" && corepack pnpm dev"

echo.
echo Backend  (API docs): http://127.0.0.1:8000/api/docs
echo Frontend (dashboard): http://127.0.0.1:3000
echo.
echo Two new windows were opened - close them (or Ctrl+C inside them) to stop the servers.
echo.
pause
