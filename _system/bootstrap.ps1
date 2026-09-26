param([switch]$SetupOnly)

$ErrorActionPreference = "Stop"

function Get-Sha256Hex([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '') }
        finally { $sha.Dispose() }
    }
    finally { $stream.Dispose() }
}

$AppDir = $PSScriptRoot
Set-Location -Path $AppDir

# 1. Runtime Python rieng; khong chay server bang Python he thong
$RuntimeRoot = Join-Path $AppDir ".runtime\auto-dang-video"
$EmbedDir = Join-Path $RuntimeRoot "python"
$PyExe = Join-Path $EmbedDir "python.exe"
$TempDir = Join-Path $RuntimeRoot "temp"
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
$env:TEMP = $TempDir
$env:TMP = $TempDir
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $RuntimeRoot "playwright"
Remove-Item Env:PIP_NO_INDEX -ErrorAction SilentlyContinue

if (-not (Test-Path $PyExe)) {
    Write-Host "[MOI TRUONG] Dang cai Python Embedded 3.11.9 rieng cho Auto Dang Video..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $EmbedDir -Force | Out-Null
    $ZipPath = Join-Path $RuntimeRoot "python_embed.zip"
    
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip" -OutFile $ZipPath -UseBasicParsing
    Expand-Archive -Path $ZipPath -DestinationPath $EmbedDir -Force
    Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
    
    # Cau hinh pth de ho tro site-packages va pip
    $PthFile = Join-Path $EmbedDir "python311._pth"
    if (Test-Path $PthFile) {
        $PthLines = (Get-Content $PthFile) -replace '#import site', 'import site'
        if ($PthLines -notcontains '..\..\..') {
            $PthLines = @($PthLines[0], '.', '..\..\..') + $PthLines[2..($PthLines.Length - 1)]
        }
        $PthLines | Set-Content $PthFile
    }
    
    # Cai dat pip
    $GetPip = Join-Path $RuntimeRoot "get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip -UseBasicParsing
    & (Join-Path $EmbedDir "python.exe") $GetPip --no-warn-script-location
    Remove-Item $GetPip -Force -ErrorAction SilentlyContinue
    
}

# Python Embedded imports only paths explicitly listed in python311._pth.
$PthFile = Join-Path $EmbedDir "python311._pth"
$PthLines = Get-Content $PthFile
if ($PthLines -notcontains '..\..\..') {
    $PthLines = @($PthLines[0], '.', '..\..\..') + $PthLines[2..($PthLines.Length - 1)]
    $PthLines | Set-Content $PthFile
}

Write-Host "[MOI TRUONG] Su dung Python: $PyExe" -ForegroundColor Cyan

# 2. Kiem tra va cai dat thu vien
$ReqFile = Join-Path $AppDir "requirements.lock"
$StampFile = Join-Path $RuntimeRoot "python-runtime.sha256"
$RequiredHash = Get-Sha256Hex $ReqFile
$InstalledHash = if (Test-Path $StampFile) { (Get-Content -LiteralPath $StampFile -Raw).Trim() } else { "" }
if ($InstalledHash -ne $RequiredHash) {
    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host "  DANG CAI DAT CAC THU VIEN LAN DAU (FastAPI, Camoufox...)" -ForegroundColor Green
    Write-Host "  Qua trinh nay chi dien ra mot lan duy nhat..." -ForegroundColor Yellow
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host ""
    & $PyExe -m pip install --upgrade pip --no-warn-script-location --quiet
    & $PyExe -m pip install --no-warn-script-location -r $ReqFile
    if ($LASTEXITCODE -ne 0) { throw "Khong cai duoc dependency runtime rieng." }
    Set-Content -LiteralPath $StampFile -Value $RequiredHash -NoNewline
    Write-Host "[CAI DAT] Hoan tat thiet lap moi truong 100%!" -ForegroundColor Green
}

# 3. Mo Web Dashboard va chay Server
if ($SetupOnly) {
    Write-Host "[Runtime] San sang: $PyExe" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  GIAO DIEN DANG MO TAI: http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "  Nhan Ctrl + C de dung may chu khi khong su dung." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

Start-Process "http://127.0.0.1:8000"

$TrayScript = Join-Path $AppDir "tray_app.py"
if (Test-Path $TrayScript) {
    & $PyExe $TrayScript
} else {
    $AppScript = Join-Path $AppDir "app.py"
    & $PyExe $AppScript
}
