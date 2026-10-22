#Requires -Version 5.1
<#
.SYNOPSIS
    Builds a standalone Windows executable for yt-dlp GUI.

.DESCRIPTION
    Creates a local build virtual environment, installs the dependencies,
    downloads the latest yt-dlp.exe, and packages everything with PyInstaller.

    Output:
      dist\ytdlp-gui.exe                    single-file application
      dist\bin\ffmpeg.exe                   only with -WithFfmpeg
      dist\ytdlp-gui-windows-x64.zip        ready-to-share package

.PARAMETER WithFfmpeg
    Also download ffmpeg/ffprobe and place them in dist\bin. Without this
    switch ffmpeg is used from PATH at runtime (if installed).

.PARAMETER UpdateFfmpeg
    Re-download ffmpeg even if bin\ffmpeg.exe already exists.

.PARAMETER NoZip
    Skip creating the ZIP package.
#>
[CmdletBinding()]
param(
    [switch]$WithFfmpeg,
    [switch]$UpdateFfmpeg,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if ($UpdateFfmpeg) {
    # Updating ffmpeg only makes sense if we are going to include it.
    $WithFfmpeg = $true
}

$Root = $PSScriptRoot
Set-Location -Path $Root
$AppName = "ytdlp-gui"
$VenvDir = Join-Path $Root ".venv-build"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$BinDir = Join-Path $Root "bin"
$DistDir = Join-Path $Root "dist"

Write-Host ""
Write-Host "=== yt-dlp GUI - Windows build ===" -ForegroundColor Cyan
Write-Host "Project: $Root"

# ── Locate Python ────────────────────────────────────────────────────
$PythonExe = $null
$PythonArgs = @()

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $PythonExe = $pyLauncher.Source
    $PythonArgs = @("-3")
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $PythonExe = $python.Source
    }
}

if (-not $PythonExe) {
    throw "Python was not found. Install Python 3.8+ from https://www.python.org/downloads/windows/ and enable 'Add python.exe to PATH'."
}

$Version = & $PythonExe @PythonArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$Version -lt [version]"3.8") {
    throw "Python 3.8 or newer is required (found $Version)."
}
Write-Host "Python: $Version ($PythonExe)" -ForegroundColor DarkGray

# ── Build virtual environment ────────────────────────────────────────
if (-not (Test-Path $VenvPython)) {
    Write-Host ""
    Write-Host "==> Creating build environment (.venv-build)..." -ForegroundColor Yellow
    & $PythonExe @PythonArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}

Write-Host "==> Installing dependencies..." -ForegroundColor Yellow
& $VenvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $Root "requirements.txt") pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

# ── Download yt-dlp.exe ──────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$YtDlp = Join-Path $BinDir "yt-dlp.exe"
$YtDlpUrl = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

Write-Host "==> Downloading the latest yt-dlp.exe..." -ForegroundColor Yellow
$YtDlpTemp = "$YtDlp.download"
try {
    Invoke-WebRequest -Uri $YtDlpUrl -OutFile $YtDlpTemp -UseBasicParsing
    Move-Item -Force $YtDlpTemp $YtDlp
} catch {
    Remove-Item -Force $YtDlpTemp -ErrorAction SilentlyContinue
    if (Test-Path $YtDlp) {
        Write-Warning "Could not download yt-dlp; using the existing copy in bin\."
    } else {
        throw "Could not download yt-dlp.exe. Check your internet connection. Details: $($_.Exception.Message)"
    }
}
Write-Host "    yt-dlp $(& $YtDlp --version)" -ForegroundColor DarkGray

# ── Optional ffmpeg download ─────────────────────────────────────────
$Ffmpeg = Join-Path $BinDir "ffmpeg.exe"
$Ffprobe = Join-Path $BinDir "ffprobe.exe"

if ($WithFfmpeg -and ((-not (Test-Path $Ffmpeg)) -or $UpdateFfmpeg)) {
    Write-Host ""
    Write-Host "==> Downloading ffmpeg (this can take a few minutes)..." -ForegroundColor Yellow
    $FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $ZipPath = Join-Path $env:TEMP "ytdlp-gui-ffmpeg.zip"
    $ExtractDir = Join-Path $env:TEMP "ytdlp-gui-ffmpeg"

    Remove-Item -Recurse -Force $ExtractDir -ErrorAction SilentlyContinue
    try {
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $ZipPath -UseBasicParsing
        Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

        $FfmpegFile = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffmpeg.exe" |
            Select-Object -First 1
        if (-not $FfmpegFile) { throw "ffmpeg.exe was not found in the downloaded archive." }
        Copy-Item -Force $FfmpegFile.FullName $Ffmpeg

        $FfprobeFile = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffprobe.exe" |
            Select-Object -First 1
        if ($FfprobeFile) { Copy-Item -Force $FfprobeFile.FullName $Ffprobe }
    } finally {
        Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $ExtractDir -ErrorAction SilentlyContinue
    }
}

if ($WithFfmpeg -and (Test-Path $Ffmpeg)) {
    Write-Host "ffmpeg: $Ffmpeg (will be packaged)" -ForegroundColor DarkGray
} else {
    Write-Host "ffmpeg: not bundled (will be looked up in PATH at runtime)" -ForegroundColor DarkGray
}

# ── Run PyInstaller ──────────────────────────────────────────────────
Write-Host ""
Write-Host "==> Building $AppName.exe..." -ForegroundColor Yellow
Remove-Item -Recurse -Force (Join-Path $Root "build"), $DistDir -ErrorAction SilentlyContinue

$PyInstallerArgs = @(
    "--noconfirm"
    "--clean"
    "--onefile"
    "--windowed"
    "--name", $AppName
    "--icon", (Join-Path $Root "assets\icon.ico")
    "--add-data", "assets;assets"
    "--collect-all", "sv_ttk"
    "--hidden-import", "sv_ttk"
    "--add-binary", "bin\yt-dlp.exe;bin"
)

& $VenvPython -m PyInstaller @PyInstallerArgs (Join-Path $Root "main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

$ExePath = Join-Path $DistDir "$AppName.exe"
if (-not (Test-Path $ExePath)) { throw "Build finished but $ExePath was not created." }

# Put ffmpeg next to the exe instead of embedding it (keeps the app small
# and startup fast).
if ($WithFfmpeg -and (Test-Path $Ffmpeg)) {
    $DistBin = Join-Path $DistDir "bin"
    New-Item -ItemType Directory -Force -Path $DistBin | Out-Null
    Copy-Item -Force $Ffmpeg $DistBin
    if (Test-Path $Ffprobe) { Copy-Item -Force $Ffprobe $DistBin }
}

# ── Package ──────────────────────────────────────────────────────────
if (-not $NoZip) {
    Write-Host "==> Creating ZIP package..." -ForegroundColor Yellow
    $StageDir = Join-Path $env:TEMP "ytdlp-gui-stage"
    $ZipPath = Join-Path $DistDir "ytdlp-gui-windows-x64.zip"
    Remove-Item -Recurse -Force $StageDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
    Copy-Item $ExePath $StageDir
    if (Test-Path (Join-Path $DistDir "bin")) {
        Copy-Item (Join-Path $DistDir "bin") $StageDir -Recurse
    }
    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
    Remove-Item -Recurse -Force $StageDir -ErrorAction SilentlyContinue
    Write-Host "    $ZipPath" -ForegroundColor DarkGray
}

$ExeSize = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
Write-Host ""
Write-Host "Build complete!" -ForegroundColor Green
Write-Host "  Executable: $ExePath ($ExeSize MB)"
if (-not $NoZip) {
    Write-Host "  Package:    $(Join-Path $DistDir 'ytdlp-gui-windows-x64.zip')"
}
Write-Host ""
Write-Host "Tip: to use a newer yt-dlp later, put yt-dlp.exe in a 'bin' folder" -ForegroundColor DarkGray
Write-Host "     next to ytdlp-gui.exe (it takes priority over the bundled copy)." -ForegroundColor DarkGray
Write-Host ""
