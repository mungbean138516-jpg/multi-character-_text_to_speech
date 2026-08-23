# VoxCast Windows quick launcher. No administrator permission is required;
# dependencies stay inside the repository's .voxcast-venv directory.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$VenvDirectory = Join-Path $ProjectRoot ".voxcast-venv"
$VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
$PortText = if ($env:VOXCAST_PORT) { $env:VOXCAST_PORT } else { "8000" }
$Port = 0
if (-not [int]::TryParse($PortText, [ref]$Port) -or $Port -lt 1 -or $Port -gt 65535) {
    throw "VOXCAST_PORT 必须是 1–65535 之间的数字。"
}
$AppUrl = "http://127.0.0.1:$Port"

function Test-VoxCastHealth {
    param([string]$Url)
    try {
        $response = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 1
        return $response.status -eq "ok"
    } catch {
        return $false
    }
}

function Find-CompatiblePython {
    if ($env:VOXCAST_QUICKSTART_PYTHON) {
        return [pscustomobject]@{ Command = $env:VOXCAST_QUICKSTART_PYTHON; Prefix = @() }
    }
    foreach ($name in @("python3.13", "python3.12", "python3.11", "python3.10", "python")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $found) { continue }
        & $found.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [pscustomobject]@{ Command = $found.Source; Prefix = @() }
        }
    }
    $launcher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($selector in @("-3.13", "-3.12", "-3.11", "-3.10", "-3")) {
            & $launcher.Source $selector -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return [pscustomobject]@{ Command = $launcher.Source; Prefix = @($selector) }
            }
        }
    }
    return $null
}

Write-Host ""
Write-Host "🎧 声场 VoxCast · Windows 快速启动"
$Python = Find-CompatiblePython
if (-not $Python) {
    throw "没有找到 Python 3.10 或更高版本；请从 python.org 安装并勾选 Add Python to PATH。"
}
$PythonCommand = $Python.Command
$PythonPrefix = @($Python.Prefix)

if ($env:VOXCAST_QUICKSTART_DRY_RUN -eq "1") {
    Write-Host "Python：$PythonCommand $PythonPrefix"
    Write-Host "虚拟环境：$VenvDirectory"
    Write-Host "网址：$AppUrl"
    Write-Host "VOXCAST_QUICKSTART_OK=1"
    exit 0
}

if (Test-VoxCastHealth $AppUrl) {
    Write-Host "✅ 声场已经在运行，正在打开浏览器。"
    Start-Process $AppUrl
    exit 0
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "[1/3] 正在创建项目独立环境…"
    & $PythonCommand @PythonPrefix -m venv $VenvDirectory
    if ($LASTEXITCODE -ne 0) { throw "无法创建虚拟环境。" }
} else {
    Write-Host "[1/3] 项目独立环境已准备好。"
}

& $VenvPython -c "import audiobook_app, edge_tts, miniaudio" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[2/3] 项目与免费 Neural 声线已安装。"
} else {
    Write-Host "[2/3] 正在安装项目与免费 Neural 声线（第一次需联网）…"
    & $VenvPython -m pip install --disable-pip-version-check -e ".[neural]"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Neural 依赖安装失败，将尝试启动基础版；下次联网后会自动重试。"
    }
}

& $VenvPython -c "import audiobook_app"
if ($LASTEXITCODE -ne 0) { throw "项目依赖不完整，无法启动 audiobook_app。" }

Write-Host "[3/3] 正在启动：$AppUrl"
Write-Host "关闭程序时，在当前窗口按 Control + C。"
Start-Job -ScriptBlock {
    param($Url)
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 1
            if ($health.status -eq "ok") {
                Start-Process $Url
                return
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
} -ArgumentList $AppUrl | Out-Null

& $VenvPython -m audiobook_app serve --port $Port
