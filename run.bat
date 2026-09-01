@echo off
chcp 65001 >nul
title Auto Video Pro - Hệ Thống Tự Động Đăng Video

echo ======================================================
echo       ĐANG KHỞI CHẠY AUTO ĐĂNG VIDEO PRO...
echo ======================================================
echo.

:: 1. Tự động kiểm tra cập nhật từ GitHub nếu có Git
where git >nul 2>nul
if %errorlevel% equ 0 (
    if exist ".git" (
        echo [CẬP NHẬT] Đang kiểm tra phiên bản mới từ GitHub...
        git pull --quiet origin main >nul 2>&1
        if %errorlevel% equ 0 (
            echo [CẬP NHẬT] Hệ thống đã ở phiên bản mới nhất!
        )
    )
)
echo.

:: 2. Kích hoạt Virtual Environment nếu có
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: 3. Kiểm tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Không tìm thấy Python trên máy!
    echo Vui lòng cài đặt Python 3.10+ hoặc chạy file install.bat
    pause
    exit /b 1
)

:: 4. Mở Dashboard trên trình duyệt
echo Mở giao diện Dashboard tại http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000

:: 5. Chạy ứng dụng
python app.py
pause
