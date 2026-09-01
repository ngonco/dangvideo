# =====================================================================
#   🚀 AUTO VIDEO PRO - QUICK INSTALLER (CÀI ĐẶT SIÊU TỐC 1 DÒNG LỆNH)
# =====================================================================

$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "     🚀 AUTO VIDEO PRO - TỰ ĐỘNG CÀI ĐẶT MỚI NHẤT" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Thư mục cài đặt
$InstallDir = Join-Path $HOME "Auto_Video_Pro"
$ZipUrl = "https://github.com/ngonco/dangvideo/archive/refs/heads/main.zip"
$TempZip = Join-Path $env:TEMP "Auto_Video_Pro_latest.zip"
$ExtractTemp = Join-Path $env:TEMP "Auto_Video_Pro_extract"

Write-Host "[1/5] Đang tải mã nguồn mới nhất từ GitHub..." -ForegroundColor Green
Invoke-WebRequest -Uri $ZipUrl -OutFile $TempZip -UseBasicParsing

Write-Host "[2/5] Đang giải nén vào thư mục: $InstallDir..." -ForegroundColor Green
if (Test-Path $ExtractTemp) { Remove-Item -Path $ExtractTemp -Recurse -Force }
Expand-Archive -Path $TempZip -DestinationPath $ExtractTemp -Force

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# Sao chép các tệp từ thư mục dangvideo-main
$SourceFolder = Join-Path $ExtractTemp "dangvideo-main"
if (Test-Path $SourceFolder) {
    Copy-Item -Path "$SourceFolder\*" -Destination $InstallDir -Recurse -Force
} else {
    Copy-Item -Path "$ExtractTemp\*" -Destination $InstallDir -Recurse -Force
}

# Dọn dẹp tệp tạm
Remove-Item -Path $TempZip -Force -ErrorAction SilentlyContinue
Remove-Item -Path $ExtractTemp -Recurse -Force -ErrorAction SilentlyContinue

# 3. Cài đặt thư viện Python & Playwright
Write-Host "[3/5] Đang cài đặt thư viện và trình duyệt Chromium..." -ForegroundColor Green
Set-Location -Path $InstallDir

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "-> Đang cài đặt các thư viện Python..." -ForegroundColor Gray
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt --quiet
    python -m playwright install chromium
} else {
    Write-Host "-> Chưa phát hiện Python trên máy. Sẽ chạy script install.bat khi khởi động." -ForegroundColor Yellow
}

# 4. Tạo Shortcut trên Desktop & Thư mục Startup (Khởi động cùng Windows)
Write-Host "[4/5] Đang tạo Shortcut trên Desktop & Khởi động cùng Windows..." -ForegroundColor Green
$WshShell = New-Object -ComObject WScript.Shell

# Desktop Shortcut
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = $WshShell.CreateShortcut((Join-Path $DesktopPath "Auto Video Pro.lnk"))
$DesktopShortcut.TargetPath = (Join-Path $InstallDir "run.bat")
$DesktopShortcut.WorkingDirectory = $InstallDir
$DesktopShortcut.Description = "Auto Video Pro - Tự động tải & đăng video"
$DesktopShortcut.Save()

# Startup Shortcut (Chạy ngầm khi mở máy tính)
$StartupPath = [Environment]::GetFolderPath("Startup")
$StartupShortcut = $WshShell.CreateShortcut((Join-Path $StartupPath "AutoVideoPro.lnk"))
$StartupTarget = Join-Path $InstallDir "run_hidden.vbs"
if (-not (Test-Path $StartupTarget)) { $StartupTarget = Join-Path $InstallDir "run.bat" }
$StartupShortcut.TargetPath = $StartupTarget
$StartupShortcut.WorkingDirectory = $InstallDir
$StartupShortcut.Description = "Auto Video Pro Startup"
$StartupShortcut.Save()

# 5. Khởi chạy ứng dụng
Write-Host "[5/5] Hoàn tất cài đặt! Đang khởi động Auto Video Pro..." -ForegroundColor Cyan
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "   ✅ CÀI ĐẶT THÀNH CÔNG! PHẦN MỀM ĐÃ SẴN SÀNG SỬ DỤNG" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "📁 Thư mục cài đặt: $InstallDir" -ForegroundColor White
Write-Host "🖥️ Shortcut Desktop: $DesktopPath\Auto Video Pro.lnk" -ForegroundColor White
Write-Host "🚀 Tự khởi động cùng Windows: ĐÃ BẬT" -ForegroundColor White
Write-Host ""

Start-Process (Join-Path $InstallDir "run.bat")
