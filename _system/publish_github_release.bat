@echo off
chcp 65001 >nul
title Phat hanh Tu_dong_dang_video.exe len GitHub Release
cd /d "%~dp0"

if "%~1"=="" (
    python publish_github_release.py
    exit /b %errorlevel%
)

echo %~1 | findstr /I /B "v" >nul
if %errorlevel%==0 (
    python publish_github_release.py --tag %*
) else (
    python publish_github_release.py %*
)
exit /b %errorlevel%
