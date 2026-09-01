@echo off
chcp 65001 >nul
title Auto Video Pro - Hệ Thống Tự Động Đăng Video

echo =================================================================
echo       🚀 ĐANG KHỞI CHẠY AUTO ĐĂNG VIDEO PRO...
echo =================================================================
echo.

cd /d "%~dp0"

:: -------------------------------------------------------------
:: BƯỚC 1: XÁC ĐỊNH MÔI TRƯỜNG PYTHON (VENV / EMBEDDED / SYSTEM)
:: -------------------------------------------------------------
set "PY_EXE="

:: 1.1 Kiểm tra Python Embedded
if exist "%~dp0python_embed\python.exe" (
    set "PY_EXE=%~dp0python_embed\python.exe"
    set "PLAYWRIGHT_BROWSERS_PATH=%~dp0python_embed\browsers"
    goto :FOUND_PYTHON
)

:: 1.2 Kiểm tra Virtual Environment venv
if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0venv\Scripts\python.exe"
    goto :FOUND_PYTHON
)

:: 1.3 Kiểm tra Python hệ thống
where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [MÔI TRƯỜNG] Đang khởi tạo Virtual Environment (venv)...
    python -m venv "%~dp0venv"
    if exist "%~dp0venv\Scripts\python.exe" (
        set "PY_EXE=%~dp0venv\Scripts\python.exe"
        goto :FOUND_PYTHON
    )
)

:: 1.4 Nếu máy chưa có Python: Tự động tải Python 3.11 Embedded x64 (Tự động 100%)
echo [MÔI TRƯỜNG] Không tìm thấy Python. Đang tự động tải Python 3.11 Portable (x64)...
mkdir "%~dp0python_embed" >nul 2>&1
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%~dp0python_embed.zip' -UseBasicParsing"
if %errorlevel% neq 0 (
    echo [LỖI] Không thể tải Python tự động. Vui lòng kiểm tra kết nối mạng!
    pause
    exit /b 1
)
powershell -Command "Expand-Archive -Path '%~dp0python_embed.zip' -DestinationPath '%~dp0python_embed' -Force"
del /f /q "%~dp0python_embed.zip" >nul 2>&1

:: Kích hoạt site-packages trong python311._pth
powershell -Command "$pth = Get-Content '%~dp0python_embed\python311._pth'; $pth = $pth -replace '#import site', 'import site'; $pth | Set-Content '%~dp0python_embed\python311._pth'"

:: Cài đặt PIP
echo [MÔI TRƯỜNG] Đang cài đặt PIP cho Python Portable...
powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%~dp0get-pip.py' -UseBasicParsing"
"%~dp0python_embed\python.exe" "%~dp0get-pip.py" --no-warn-script-location >nul 2>&1
del /f /q "%~dp0get-pip.py" >nul 2>&1

set "PY_EXE=%~dp0python_embed\python.exe"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0python_embed\browsers"

:FOUND_PYTHON
echo [MÔI TRƯỜNG] Sử dụng Python: %PY_EXE%

:: -------------------------------------------------------------
:: BƯỚC 2: TỰ ĐỘNG KIỂM TRA VÀ CÀI ĐẶT THƯ VIỆN & TRÌNH DUYỆT
:: -------------------------------------------------------------
"%PY_EXE%" -c "import fastapi, playwright, apscheduler, uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [CÀI ĐẶT] Đang tự động cài đặt các thư viện cần thiết lần đầu...
    echo (FastAPI, Playwright, APScheduler, Uvicorn - Quá trình này mất khoảng 30 giây)...
    "%PY_EXE%" -m pip install --no-warn-script-location -r "%~dp0requirements.txt"
    echo [CÀI ĐẶT] Đang tải trình duyệt Playwright Chromium...
    "%PY_EXE%" -m playwright install chromium
    echo [CÀI ĐẶT] Hoàn tất thiết lập môi trường 100%!
    echo.
)

:: -------------------------------------------------------------
:: BƯỚC 3: TỰ ĐỘNG KIỂM TRA CẬP NHẬT TỪ GITHUB (NẾU CÓ GIT)
:: -------------------------------------------------------------
where git >nul 2>nul
if %errorlevel% equ 0 (
    if exist "%~dp0.git" (
        echo [CẬP NHẬT] Đang kiểm tra phiên bản mới từ GitHub...
        git pull --quiet origin main >nul 2>&1
        if %errorlevel% equ 0 (
            echo [CẬP NHẬT] Hệ thống đã ở phiên bản mới nhất!
        )
    )
)
echo.

:: -------------------------------------------------------------
:: BƯỚC 4: MỞ GIAO DIỆN WEB VÀ KHỞI CHẠY SERVER
:: -------------------------------------------------------------
echo =================================================================
echo   🌐 GIAO DIỆN ĐANG MỞ TẠI: http://127.0.0.1:8000
echo   💡 Nhấn Ctrl + C để dừng máy chủ khi không sử dụng.
echo =================================================================
echo.

start "" http://127.0.0.1:8000

"%PY_EXE%" "%~dp0app.py"
pause
