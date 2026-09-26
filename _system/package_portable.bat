@echo off
chcp 65001 >nul
title Auto Video Pro - Build Onefile
cd /d "%~dp0"

echo Ban portable kem san Python/browser da ngung phat hanh de tranh dong goi runtime gan 1 GB.
echo Dang build ban onefile; Camoufox se tu cai vao runtime rieng o lan chay dau.
call "%~dp0build_exe.bat"
exit /b %errorlevel%
