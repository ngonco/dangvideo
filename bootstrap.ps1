$ErrorActionPreference = "Stop"

$AppDir = $PSScriptRoot
Set-Location -Path $AppDir

# 1. Xac dinh trinh thuc thi Python
$PyExe = $null

# Kiem tra Python Embedded
$EmbedPy = Join-Path $AppDir "python_embed\python.exe"
if (Test-Path $EmbedPy) {
    $PyExe = $EmbedPy
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $AppDir "python_embed\browsers"
}

# Kiem tra venv
if (-not $PyExe) {
    $VenvPy = Join-Path $AppDir "venv\Scripts\python.exe"
    if (Test-Path $VenvPy) {
        $PyExe = $VenvPy
    }
}

# Kiem tra Python he thong
if (-not $PyExe) {
    $SysPy = Get-Command python -ErrorAction SilentlyContinue
    if ($SysPy) {
        try {
            & python -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[MOI TRUONG] Phat hien Python he thong. Khoi tao venv..." -ForegroundColor Green
                & python -m venv (Join-Path $AppDir "venv")
                $VenvPy = Join-Path $AppDir "venv\Scripts\python.exe"
                if (Test-Path $VenvPy) {
                    $PyExe = $VenvPy
                } else {
                    $PyExe = "python"
                }
            }
        } catch {}
    }
}

# Neu may chua co Python: Tu dong tai Python 3.11 Embedded
if (-not $PyExe) {
    Write-Host "[MOI TRUONG] May tinh chua co Python. Dang tu dong tai Python 3.11 Portable..." -ForegroundColor Yellow
    $EmbedDir = Join-Path $AppDir "python_embed"
    New-Item -ItemType Directory -Path $EmbedDir -Force | Out-Null
    $ZipPath = Join-Path $AppDir "python_embed.zip"
    
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip" -OutFile $ZipPath -UseBasicParsing
    Expand-Archive -Path $ZipPath -DestinationPath $EmbedDir -Force
    Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
    
    # Cau hinh pth de ho tro site-packages va pip
    $PthFile = Join-Path $EmbedDir "python311._pth"
    if (Test-Path $PthFile) {
        (Get-Content $PthFile) -replace '#import site', 'import site' | Set-Content $PthFile
    }
    
    # Cai dat pip
    $GetPip = Join-Path $AppDir "get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip -UseBasicParsing
    & (Join-Path $EmbedDir "python.exe") $GetPip --no-warn-script-location
    Remove-Item $GetPip -Force -ErrorAction SilentlyContinue
    
    $PyExe = Join-Path $EmbedDir "python.exe"
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $EmbedDir "browsers"
}

Write-Host "[MOI TRUONG] Su dung Python: $PyExe" -ForegroundColor Cyan

# 2. Kiem tra va cai dat thu vien
$ReqFile = Join-Path $AppDir "requirements.txt"
$depsOk = $false
try {
    & $PyExe -c "import fastapi, playwright, apscheduler, uvicorn" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $depsOk = $true
    }
} catch {
    $depsOk = $false
}

if (-not $depsOk) {
    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host "  📦 DANG CAI DAT CAC THU VIEN LAN DAU (FastAPI, Playwright...)" -ForegroundColor Green
    Write-Host "  ⏳ Qua trinh nay chi dien ra mot lan duy nhat (~30 giay)..." -ForegroundColor Yellow
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host ""
    & $PyExe -m pip install --upgrade pip --no-warn-script-location --quiet
    & $PyExe -m pip install --no-warn-script-location -r $ReqFile
    Write-Host "[CAI DAT] Dang tai trinh duyet Playwright Chromium..." -ForegroundColor Green
    & $PyExe -m playwright install chromium
    Write-Host "[CAI DAT] Hoan tat thiet lap moi truong 100%!" -ForegroundColor Green
}

# 3. Mo Web Dashboard va chay Server
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  🌐 GIAO DIEN DANG MO TAI: http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "  💡 Nhan Ctrl + C de dung may chu khi khong su dung." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

Start-Process "http://127.0.0.1:8000"

$AppScript = Join-Path $AppDir "app.py"
& $PyExe $AppScript
