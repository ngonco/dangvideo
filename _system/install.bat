@echo off
chcp 65001 >nul
title Auto Video Pro - Cài Đặt Môi Trường

cd /d "%~dp0"

echo =================================================================
echo   📦 AUTO VIDEO PRO - TỰ ĐỘNG THIẾT LẬP MÔI TRƯỜNG 1-CLICK
echo =================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"

echo.
pause
