@echo off
chcp 65001 >nul
title Bien dich Tu_dong_dang_video.exe
cd /d "%~dp0" || exit /b 1
echo Dang bien dich Tu_dong_dang_video.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\bootstrap.ps1" -SetupOnly
if %errorlevel% neq 0 exit /b %errorlevel%
".\.runtime\auto-dang-video\python\python.exe" ".\build_exe.py"
exit /b %errorlevel%
