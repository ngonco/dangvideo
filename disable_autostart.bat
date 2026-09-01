@echo off
chcp 65001 >nul
title Auto Video Pro - Tắt Khởi Động Cùng Windows

echo ========================================================
echo   🛑 TẮT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS (AUTO-START)
echo ========================================================
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\AutoVideoPro.lnk"

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo ========================================================
    echo   ✅ ĐÃ TẮT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS THÀNH CÔNG!
    echo ========================================================
) else (
    echo [THÔNG BÁO] Tính năng tự khởi động cùng Windows hiện đang TẮT.
)
echo.
pause
