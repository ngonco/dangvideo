@echo off
chcp 65001 >nul
title Bien dich Tu_dong_dang_video.exe
cd /d "%~dp0"
echo Dang bien dich Tu_dong_dang_video.exe ...
python build_exe.py
exit /b %errorlevel%
