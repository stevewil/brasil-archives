@echo off
rem Windows entry point for database-update.sh. Run from PowerShell or cmd:
rem     .\database-update.bat
rem Hands off to the bash that ships with Git for Windows.
rem A bare "bash.exe" on PATH is usually the WSL launcher, not this one.
setlocal
cd /d "%~dp0"

set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%BASH%" set "BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%BASH%" (
    echo Could not find Git Bash at the usual locations.
    echo From a Git Bash shell instead, run:  ./database-update.sh
    exit /b 1
)

"%BASH%" database-update.sh
