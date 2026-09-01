@echo off
chcp 65001 >nul
title Auto Video Pro - Khởi Chạy Hệ Thống

cd /d "%~dp0"

echo =================================================================
echo       🚀 ĐANG KHỞI CHẠY AUTO ĐĂNG VIDEO PRO...
echo =================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [LỖI] Có sự cố khi khởi chạy hệ thống.
)

echo.
echo [THÔNG BÁO] Cửa sổ sẽ không tự đóng để bạn kiểm tra nhật ký.
pause
