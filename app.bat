@echo off
setlocal
cd /d "%~dp0"

set PORT=9000
set LOG=dev-server.log
set PYTHON=.venv\Scripts\python.exe

rem Double-clicked (no argument) => default to start, and pause at the end
rem so the window doesn't flash and vanish before you can read it. Called
rem with an explicit argument (from a terminal, or by app-dashboard's
rem controller-api.ts, which shells out and waits on this with a timeout)
rem => never pause, since nothing would be there to press a key.
set ACTION=%~1
set INTERACTIVE=0
if "%ACTION%"=="" (
    set ACTION=start
    set INTERACTIVE=1
)

if /i "%ACTION%"=="start" (
    call :start
) else if /i "%ACTION%"=="stop" (
    call :stop
) else if /i "%ACTION%"=="restart" (
    call :restart
) else if /i "%ACTION%"=="status" (
    call :status
) else (
    goto usage
)

if "%INTERACTIVE%"=="1" (
    echo.
    echo ^(This window can be closed - brasil-archives keeps running on its own.^)
    pause
)
goto :eof

:start
call :is_running
if "%RUNNING_PID%"=="" (
    echo Starting brasil-archives on port %PORT%...
    start "brasil-archives-dev" /min cmd /c ""%PYTHON%" wsgi.py > %LOG% 2>&1"
    ping -n 4 127.0.0.1 >nul
    start "" http://127.0.0.1:%PORT%
    echo Started. Logs: %LOG%
) else (
    echo Already running ^(PID %RUNNING_PID%^).
)
goto :eof

:stop
call :is_running
if "%RUNNING_PID%"=="" (
    echo Not running.
) else (
    echo Stopping PID %RUNNING_PID%...
    taskkill /F /PID %RUNNING_PID% >nul 2>&1
    echo Stopped.
)
goto :eof

:restart
call :stop
ping -n 2 127.0.0.1 >nul
call :start
goto :eof

:status
call :is_running
if "%RUNNING_PID%"=="" (
    echo brasil-archives: not running.
) else (
    echo brasil-archives: running ^(PID %RUNNING_PID%^) on port %PORT%.
)
goto :eof

:is_running
set RUNNING_PID=
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do set RUNNING_PID=%%p
goto :eof

:usage
echo Usage: %~nx0 [start^|stop^|restart^|status]
exit /b 1
