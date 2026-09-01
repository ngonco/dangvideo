@echo off
chcp 65001 >nul
title Auto Video Pro - Đóng Gói Bản Portable (Python Embedded)

echo =================================================================
echo   📦 AUTO VIDEO PRO - ĐÓNG GÓI BẢN PORTABLE (PYTHON EMBEDDED)
echo =================================================================
echo.
echo Bản Portable sẽ tích hợp sẵn Python 3.11 và trình duyệt Chromium.
echo Người dùng ở máy khác chỉ cần tải về giải nén là chạy ngay 100%%
echo mà KHÔNG CẦN CÀI ĐẶT BẤT KỲ PHẦN MỀM NÀO KHÁC!
echo.

set "ROOT_DIR=%~dp0"
set "BUILD_DIR=%ROOT_DIR%portable_build"
set "DIST_DIR=%BUILD_DIR%\Auto_Video_Pro_Portable"
set "ZIP_OUT=%ROOT_DIR%Auto_Video_Pro_Portable.zip"

:: 1. Dọn dẹp thư mục build cũ
if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
if exist "%ZIP_OUT%" del /f /q "%ZIP_OUT%"
mkdir "%DIST_DIR%"
mkdir "%DIST_DIR%\python_embed"
mkdir "%DIST_DIR%\downloads"
mkdir "%DIST_DIR%\browser_profiles"

:: 2. Tải Python Embedded 3.11.9 x64
echo [1/6] Đang tải gói Python 3.11.9 Embedded (x64)...
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%BUILD_DIR%\python_embed.zip'"
if %errorlevel% neq 0 (
    echo [LỖI] Không thể tải Python Embedded. Vui lòng kiểm tra kết nối mạng.
    pause
    exit /b 1
)

:: 3. Giải nén Python Embedded
echo [2/6] Đang giải nén Python Embedded...
powershell -Command "Expand-Archive -Path '%BUILD_DIR%\python_embed.zip' -DestinationPath '%DIST_DIR%\python_embed' -Force"

:: 4. Kích hoạt 'import site' trong file python311._pth
echo [3/6] Cấu hình môi trường Python Embedded...
powershell -Command "$pth = Get-Content '%DIST_DIR%\python_embed\python311._pth'; $pth = $pth -replace '#import site', 'import site'; $pth | Set-Content '%DIST_DIR%\python_embed\python311._pth'"

:: 5. Tải và cài đặt PIP vào Python Embedded
echo [4/6] Cài đặt PIP và các gói thư viện (FastAPI, Playwright, Uvicorn)...
powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%BUILD_DIR%\get-pip.py'"
"%DIST_DIR%\python_embed\python.exe" "%BUILD_DIR%\get-pip.py" --no-warn-script-location

"%DIST_DIR%\python_embed\python.exe" -m pip install --no-warn-script-location -r "%ROOT_DIR%requirements.txt"
set "PLAYWRIGHT_BROWSERS_PATH=%DIST_DIR%\python_embed\browsers"
"%DIST_DIR%\python_embed\python.exe" -m playwright install chromium

:: 6. Sao chép mã nguồn ứng dụng vào thư mục Portable
echo [5/6] Đang sao chép mã nguồn ứng dụng...
xcopy "%ROOT_DIR%app.py" "%DIST_DIR%\" /y /q
xcopy "%ROOT_DIR%config.json" "%DIST_DIR%\" /y /q
xcopy "%ROOT_DIR%README.md" "%DIST_DIR%\" /y /q
xcopy "%ROOT_DIR%SYSTEM_MAP.MD" "%DIST_DIR%\" /y /q
xcopy "%ROOT_DIR%run_hidden.vbs" "%DIST_DIR%\" /y /q
xcopy "%ROOT_DIR%enable_autostart.bat" "%DIST_DIR%\" /y /q
xcopy "%ROOT_DIR%disable_autostart.bat" "%DIST_DIR%\" /y /q

xcopy "%ROOT_DIR%core" "%DIST_DIR%\core\" /s /e /y /q
xcopy "%ROOT_DIR%automation" "%DIST_DIR%\automation\" /s /e /y /q
xcopy "%ROOT_DIR%scheduler" "%DIST_DIR%\scheduler\" /s /e /y /q
xcopy "%ROOT_DIR%static" "%DIST_DIR%\static\" /s /e /y /q

:: 7. Tạo launcher riêng cho bản Portable
(
echo @echo off
echo chcp 65001 ^>nul
echo title Auto Video Pro - Portable Edition
echo cd /d "%%~dp0"
echo set "PLAYWRIGHT_BROWSERS_PATH=%%~dp0python_embed\browsers"
echo.
echo echo ======================================================
echo echo      ĐANG KHỞI CHẠY AUTO ĐĂNG VIDEO PRO (PORTABLE)
echo echo ======================================================
echo echo.
echo echo Mở Dashboard tại http://127.0.0.1:8000 ...
echo start "" http://127.0.0.1:8000
echo.
echo python_embed\python.exe app.py
echo pause
) > "%DIST_DIR%\run.bat"

(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo Set FSO = CreateObject^("Scripting.FileSystemObject"^)
echo ScriptDir = FSO.GetParentFolderName^(WScript.ScriptFullName^)
echo WshShell.CurrentDirectory = ScriptDir
echo WshShell.Run "cmd /c run.bat", 0, False
) > "%DIST_DIR%\run_hidden.vbs"

:: 8. Nén toàn bộ thành file zip Portable
echo [6/6] Đang nén thành tệp '%ZIP_OUT%'...
powershell -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%ZIP_OUT%' -Force"

:: Dọn dẹp thư mục tạm
rd /s /q "%BUILD_DIR%"

echo.
echo =================================================================
echo   ✅ ĐÃ TẠO THÀNH CÔNG BẢN PORTABLE HOÀN CHỈNH!
echo =================================================================
echo.
echo 📁 File nén: %ZIP_OUT%
echo.
echo Hướng dẫn:
echo 1. Bạn chỉ cần gửi file 'Auto_Video_Pro_Portable.zip' này sang máy khác.
echo 2. Giải nén ra thư mục bất kỳ.
echo 3. Click đúp vào file 'run.bat' là phần mềm chạy ngay lập tức!
echo.
pause
