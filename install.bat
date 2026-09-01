@echo off
chcp 65001 >nul
title Auto Video Pro - Cài Đặt Môi Trường Tự Động

echo =================================================================
echo   📦 AUTO VIDEO PRO - TỰ ĐỘNG THIẾT LẬP MÔI TRƯỜNG 1-CLICK
echo =================================================================
echo.

cd /d "%~dp0"

set "PY_EXE="

:: 1. Kiểm tra Python Embedded
if exist "%~dp0python_embed\python.exe" (
    set "PY_EXE=%~dp0python_embed\python.exe"
    goto :INSTALL_DEPS
)

:: 2. Kiểm tra Python hệ thống
where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [1/3] Đang tạo Virtual Environment (venv)...
    python -m venv "%~dp0venv"
    if exist "%~dp0venv\Scripts\python.exe" (
        set "PY_EXE=%~dp0venv\Scripts\python.exe"
        goto :INSTALL_DEPS
    )
)

:: 3. Nếu chưa có Python: Tải Python 3.11 Embedded x64
echo [1/3] Máy chưa có Python. Đang tự động tải Python 3.11 Embedded x64...
mkdir "%~dp0python_embed" >nul 2>&1
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%~dp0python_embed.zip' -UseBasicParsing"
powershell -Command "Expand-Archive -Path '%~dp0python_embed.zip' -DestinationPath '%~dp0python_embed' -Force"
del /f /q "%~dp0python_embed.zip" >nul 2>&1

powershell -Command "$pth = Get-Content '%~dp0python_embed\python311._pth'; $pth = $pth -replace '#import site', 'import site'; $pth | Set-Content '%~dp0python_embed\python311._pth'"

powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%~dp0get-pip.py' -UseBasicParsing"
"%~dp0python_embed\python.exe" "%~dp0get-pip.py" --no-warn-script-location >nul 2>&1
del /f /q "%~dp0get-pip.py" >nul 2>&1

set "PY_EXE=%~dp0python_embed\python.exe"

:INSTALL_DEPS
echo.
echo [2/3] Đang cài đặt các thư viện Python (FastAPI, Playwright, Uvicorn, APScheduler)...
"%PY_EXE%" -m pip install --upgrade pip --no-warn-script-location >nul 2>&1
"%PY_EXE%" -m pip install --no-warn-script-location -r "%~dp0requirements.txt"

echo.
echo [3/3] Đang tải trình duyệt Playwright Chromium...
"%PY_EXE%" -m playwright install chromium

echo.
echo =================================================================
echo   ✅ CÀI ĐẶT HOÀN TẤT THÀNH CÔNG 100%!
echo   👉 BÂY GIỜ BẠN CÓ THỂ CHẠY FILE 'run.bat' ĐỂ BẮT ĐẦU SỬ DỤNG.
echo =================================================================
echo.
pause
