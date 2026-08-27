@echo off
cd /d "%~dp0"

echo ============================================
echo  SEO Brain - starting via Docker Compose
echo ============================================
echo.
echo Starting the local Docker HTTPS bridge ...
echo.

powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%~dp0.venv\Scripts\python.exe' -ArgumentList '%~dp0tools\docker_host_proxy.py','--port','18080','--upstream-socks','127.0.0.1:10808' -WorkingDirectory '%~dp0' -WindowStyle Hidden -RedirectStandardOutput '%~dp0data\docker-host-proxy.out.log' -RedirectStandardError '%~dp0data\docker-host-proxy.err.log' }"
if errorlevel 1 (
    echo Failed to start the local Docker HTTPS bridge.
    pause
    exit /b 1
)

docker compose up -d --build
if errorlevel 1 (
    echo.
    echo Failed to start. Is Docker Desktop running?
    pause
    exit /b 1
)

echo.
echo Backend  (API docs): http://127.0.0.1:8000/api/docs
echo Frontend (dashboard): http://127.0.0.1:3000
echo.
echo View logs:  docker compose logs -f
echo Stop:       docker compose down
echo.
pause
