@echo off
chcp 65001 >nul
title Auto Video Pro - Đẩy Mã Nguồn Lên GitHub

echo ========================================================
echo        🚀 AUTO VIDEO PRO - BACKUP MÃ NGUỒN LÊN GITHUB
echo ========================================================
echo.

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [LỖI] Máy tính chưa cài đặt Git.
    pause
    exit /b 1
)

set /p commit_msg="Nhập mô tả cập nhật (Enter để dùng mặc định 'Update Auto Video Pro'): "
if "%commit_msg%"=="" set commit_msg=Update Auto Video Pro

echo.
echo [1/3] Thêm các thay đổi vào Git...
git add .

echo [2/3] Lưu phiên bản: "%commit_msg%"...
git commit -m "%commit_msg%"

echo [3/3] Đẩy lên GitHub (origin main)...
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo        ✅ ĐÃ BACKUP MÃ NGUỒN LÊN GITHUB THÀNH CÔNG!
    echo ========================================================
) else (
    echo.
    echo [LỖI] Không thể đẩy lên GitHub. Vui lòng kiểm tra kết nối mạng hoặc quyền truy cập.
)
echo.
pause
