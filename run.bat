@echo off
cd /d "%~dp0"

REM Neu co file Tu_dong_dang_video.exe thi khoi chay truc tiep
if exist "%~dp0Tu_dong_dang_video.exe" (
    start "" "%~dp0Tu_dong_dang_video.exe"
    exit /b 0
)

REM Khoi chay thong qua bootstrap PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
