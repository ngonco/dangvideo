@echo off
chcp 65001 >nul
title Bien dich Tu_dong_dang_video.exe
cd /d "%~dp0"
echo Dang bien dich Tu_dong_dang_video.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -SetupOnly
"%~dp0.runtime\auto-dang-video\python\python.exe" "%~dp0build_exe.py"
exit /b %errorlevel%
