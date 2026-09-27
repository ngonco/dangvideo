@echo off
chcp 65001 >nul
title Auto Video Pro - Cap Nhat Ma Nguon Cho Lap Trinh Vien

echo ========================================================
echo        AUTO VIDEO PRO - CAP NHAT MA NGUON PHAT TRIEN
echo ========================================================
echo.

echo File nay chi dung cho ban chay tu MA NGUON.
echo Ban Tu_dong_dang_video.exe se tu cap nhat qua GitHub Releases.
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
    echo [LOI] Khong the keo ma nguon (co the do mat mang hoac xung dot file).
    echo Khong tu dong ghi de thay doi dang lam.
    pause
    exit /b 1
)

:: 3. Cập nhật runtime Python riêng theo lockfile
echo.
echo [2/3] Đang kiểm tra và cập nhật các gói thư viện Python...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -SetupOnly
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo ========================================================
echo        ✅ ĐÃ CẬP NHẬT PHẦN MỀM LÊN BẢN MỚI NHẤT!
echo ========================================================
echo.
echo Bạn có thể khởi động lại hệ thống bằng cách chạy file: run.bat
echo.
pause
