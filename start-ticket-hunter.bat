@echo off
rem Ticket Hunter - starts the local server (if not running) and opens the dashboard.
rem To stop the server: close the minimized window "Ticket Hunter server".
cd /d "%~dp0backend"

curl -s -o nul http://127.0.0.1:8765/api/health
if not errorlevel 1 goto open

start "Ticket Hunter server" /min "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --port 8765

set /a tries=0
:wait
timeout /t 1 /nobreak >nul
curl -s -o nul http://127.0.0.1:8765/api/health
if not errorlevel 1 goto open
set /a tries+=1
if %tries% lss 30 goto wait
echo The server did not start. Check the "Ticket Hunter server" window for errors.
pause
exit /b 1

:open
start "" http://localhost:8765
exit /b 0
