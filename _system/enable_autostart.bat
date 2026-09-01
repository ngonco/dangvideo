@echo off
chcp 65001 >nul
title Auto Video Pro - Bật Khởi Động Cùng Windows

echo ========================================================
echo   🚀 BẬT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS (AUTO-START)
echo ========================================================
echo.

set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\AutoVideoPro.lnk"
set "TARGET=%APP_DIR%\run_hidden.vbs"

if not exist "%TARGET%" set "TARGET=%APP_DIR%\run.bat"

echo Đang tạo Shortcut tại: %SHORTCUT%
powershell -NoProfile -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%TARGET%'; $Shortcut.WorkingDirectory = '%APP_DIR%'; $Shortcut.Description = 'Auto Video Pro'; $Shortcut.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo ========================================================
    echo   ✅ ĐÃ BẬT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS THÀNH CÔNG!
    echo ========================================================
    echo Mỗi khi mở máy tính, Auto Video Pro sẽ tự động chạy ngầm.
) else (
    echo.
    echo [LỖI] Không thể tạo shortcut khởi động.
)
echo.
pause
