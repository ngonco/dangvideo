@echo off
chcp 65001 >nul
title Auto Video Pro - Cập Nhật Hệ Thống

echo ========================================================
echo        🔄 AUTO VIDEO PRO - TỰ ĐỘNG CẬP NHẬT PHẦN MỀM
echo ========================================================
echo.

:: 1. Kiểm tra Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [LỖI] Máy tính chưa cài đặt Git.
    echo Vui lòng tải và cài đặt Git từ: https://git-scm.com/
    pause
    exit /b 1
)

:: 2. Kéo mã nguồn mới nhất từ GitHub
echo [1/3] Đang tải mã nguồn mới nhất từ GitHub (origin/main)...
git pull origin main
if %errorlevel% neq 0 (
    echo.
    echo [CẢNH BÁO] Không thể kéo code tự động (có thể do mất mạng hoặc xung đột file).
    echo Đang thử đồng bộ ép buộc...
    git fetch origin main
    git reset --hard origin/main
)

:: 3. Cập nhật thư viện Python nếu có file requirements.txt
echo.
echo [2/3] Đang kiểm tra và cập nhật các gói thư viện Python...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul 2>nul
    pip install -r requirements.txt
    playwright install chromium
) else (
    echo [THÔNG BÁO] Thư mục venv chưa được khởi tạo. Vui lòng chạy install.bat trước.
)

echo.
echo ========================================================
echo        ✅ ĐÃ CẬP NHẬT PHẦN MỀM LÊN BẢN MỚI NHẤT!
echo ========================================================
echo.
echo Bạn có thể khởi động lại hệ thống bằng cách chạy file: run.bat
echo.
pause
