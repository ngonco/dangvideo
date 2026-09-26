@echo off
chcp 65001 >nul
title Phat hanh Tu_dong_dang_video.exe len GitHub Release
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -SetupOnly
if %errorlevel% neq 0 exit /b %errorlevel%
set "RUNTIME_PY=%~dp0.runtime\auto-dang-video\python\python.exe"

if "%~1"=="" (
    "%RUNTIME_PY%" publish_github_release.py
    exit /b %errorlevel%
)

echo %~1 | findstr /I /B "v" >nul
if %errorlevel%==0 (
    "%RUNTIME_PY%" publish_github_release.py --tag %*
) else (
    "%RUNTIME_PY%" publish_github_release.py %*
)
exit /b %errorlevel%
