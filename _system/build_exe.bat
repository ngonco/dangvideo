@echo off
chcp 65001 >nul
title Biên Dịch Tu_dong_dang_video.exe

echo ========================================================
echo   🔨 ĐANG BIÊN DỊCH FILE THỰC THI Tu_dong_dang_video.exe
echo ========================================================
echo.

cd /d "%~dp0"

pyinstaller --noconsole --onefile ^
    --name "Tu_dong_dang_video" ^
    --add-data "static;static" ^
    --add-data "config.json;." ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols" ^
    --hidden-import "uvicorn.protocols.http" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    --hidden-import "uvicorn.protocols.websockets" ^
    --hidden-import "uvicorn.protocols.websockets.auto" ^
    --hidden-import "uvicorn.lifespans" ^
    --hidden-import "uvicorn.lifespans.on" ^
    --hidden-import "pystray._win32" ^
    --hidden-import "PIL" ^
    --clean ^
    tray_app.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo   ✅ BIÊN DỊCH THÀNH CÔNG!
    echo   📁 File thực thi: dist\Tu_dong_dang_video.exe
    echo ========================================================
    copy "dist\Tu_dong_dang_video.exe" "Tu_dong_dang_video.exe" /y
) else (
    echo.
    echo [LỖI] Biên dịch thất bại!
)
echo.
pause
