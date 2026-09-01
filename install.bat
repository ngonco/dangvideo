@echo off
chcp 65001 >nul
echo ======================================================
echo    CÀI ĐẶT MÔI TRƯỜNG CHO HỆ THỐNG AUTO ĐĂNG VIDEO
echo ======================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Không tìm thấy Python trên máy! Vui lòng cài Python 3.9+ và tích chọn 'Add Python to PATH'.
    pause
    exit /b
)

echo [1/2] Đang cài đặt các thư viện Python từ requirements.txt...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [LỖI] Cài đặt thư viện thất bại.
    pause
    exit /b
)

echo.
echo [2/2] Đang cài đặt trình duyệt tự động Playwright (Chromium)...
playwright install chromium
if %errorlevel% neq 0 (
    echo [LỖI] Cài đặt Playwright Chromium thất bại.
    pause
    exit /b
)

echo.
echo ======================================================
echo    CÀI ĐẶT HOÀN TẤT THÀNH CÔNG! BÂY GIỜ BẠN CÓ THỂ
echo    CHẠY FILE 'run.bat' ĐỂ BẮT ĐẦU SỬ DỤNG.
echo ======================================================
echo.
pause
