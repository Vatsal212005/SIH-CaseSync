[CmdletBinding()]
param(
    [switch]$OpenBrave
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$stateFile = Join-Path $projectRoot ".casesync-dev-processes.json"
$logRoot = Join-Path $projectRoot ".runlogs"
$backendUrl = "http://localhost:8000/api/v1/health"
$frontendUrl = "http://localhost:3000"

function Get-PortOwner([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Test-BackendHealth {
    try {
        $health = Invoke-RestMethod $backendUrl -TimeoutSec 5
        return $health.status -eq "ok" -and $health.database -eq "connected"
    } catch { return $false }
}

function Test-FrontendHealth {
    try {
        $response = Invoke-WebRequest $frontendUrl -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200 -and $response.Content -match "CaseSync"
    } catch { return $false }
}

function Wait-ForService([string]$Name, [scriptblock]$Probe, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (& $Probe) { return }
        Start-Sleep -Milliseconds 750
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become healthy within $TimeoutSeconds seconds. Check .runlogs for details."
}

function New-ProcessRecord([int]$Id, [string]$Role) {
    $process = Get-Process -Id $Id -ErrorAction Stop
    return [ordered]@{
        Role = $Role
        Id = $process.Id
        Name = $process.ProcessName
        StartTimeUtc = $process.StartTime.ToUniversalTime().ToString("o")
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment not found at $python"
}
$pythonVersion = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
if ($LASTEXITCODE -ne 0 -or -not $pythonVersion.StartsWith("3.12.")) {
    throw "CaseSync requires its Python 3.12 virtual environment; found '$pythonVersion'."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Frontend dependencies are missing. Restore the existing frontend/node_modules before starting CaseSync."
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$records = @()
if (Test-Path -LiteralPath $stateFile) {
    try {
        $savedState = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if ($savedState.ProjectRoot -eq $projectRoot) {
            foreach ($record in @($savedState.Processes)) {
                $process = Get-Process -Id ([int]$record.Id) -ErrorAction SilentlyContinue
                if (-not $process) { continue }
                $expected = [datetime]::Parse($record.StartTimeUtc).ToUniversalTime()
                if ($process.ProcessName -eq $record.Name -and
                    [math]::Abs(($process.StartTime.ToUniversalTime() - $expected).TotalSeconds) -lt 2) {
                    $records += $record
                }
            }
        }
    } catch {
        Write-Warning "Ignoring stale CaseSync process state: $($_.Exception.Message)"
    }
}

$env:DATABASE_URL = "sqlite:///./casesync.db"
$env:DEMO_MODE = "true"
$env:DEMO_PASSWORD = "CaseSync@2026"
$env:CORS_ORIGINS = "http://localhost:3000"
$env:UPLOAD_DIR = "storage"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:USE_TF = "0"
$env:TRANSFORMERS_NO_TF = "1"
$env:TOKENIZERS_PARALLELISM = "false"
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000/api/v1"

$backendOwner = Get-PortOwner 8000
if ($backendOwner) {
    if (-not (Test-BackendHealth)) {
        throw "Port 8000 is occupied by PID $backendOwner, but it is not a healthy CaseSync backend. It was not terminated."
    }
    Write-Host "Reusing healthy CaseSync backend (PID $backendOwner)." -ForegroundColor DarkGreen
    $records += New-ProcessRecord $backendOwner "backend-listener"
} else {
    Push-Location $backendRoot
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
        & $python -m app.seed
        if ($LASTEXITCODE -ne 0) { throw "Synthetic dataset initialization failed." }
    } finally {
        Pop-Location
    }

    $backendOut = Join-Path $logRoot "backend-$stamp.out.log"
    $backendErr = Join-Path $logRoot "backend-$stamp.err.log"
    $backendProcess = Start-Process -FilePath $python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $backendRoot -WindowStyle Hidden `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr -PassThru
    $records += New-ProcessRecord $backendProcess.Id "backend-launcher"
    Wait-ForService "FastAPI backend" ${function:Test-BackendHealth} 90
    $backendOwner = Get-PortOwner 8000
    $records += New-ProcessRecord $backendOwner "backend-listener"
    Write-Host "Started CaseSync backend (PID $backendOwner)." -ForegroundColor Green
}

$frontendOwner = Get-PortOwner 3000
if ($frontendOwner) {
    if (-not (Test-FrontendHealth)) {
        throw "Port 3000 is occupied by PID $frontendOwner, but it is not a healthy CaseSync frontend. It was not terminated."
    }
    Write-Host "Reusing healthy CaseSync frontend (PID $frontendOwner)." -ForegroundColor DarkGreen
    $records += New-ProcessRecord $frontendOwner "frontend-listener"
} else {
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $frontendOut = Join-Path $logRoot "frontend-$stamp.out.log"
    $frontendErr = Join-Path $logRoot "frontend-$stamp.err.log"
    $frontendProcess = Start-Process -FilePath $npm -ArgumentList "run", "dev" `
        -WorkingDirectory $frontendRoot -WindowStyle Hidden `
        -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr -PassThru
    $records += New-ProcessRecord $frontendProcess.Id "frontend-launcher"
    Wait-ForService "Next.js frontend" ${function:Test-FrontendHealth} 90
    $frontendOwner = Get-PortOwner 3000
    $records += New-ProcessRecord $frontendOwner "frontend-listener"
    Write-Host "Started CaseSync frontend (PID $frontendOwner)." -ForegroundColor Green
}

$uniqueRecords = @{}
foreach ($record in $records) {
    $uniqueRecords["$($record.Role):$($record.Id)"] = $record
}
$state = [ordered]@{
    ProjectRoot = $projectRoot
    CreatedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    PythonVersion = $pythonVersion
    Processes = @($uniqueRecords.Values)
}
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $stateFile -Encoding UTF8

Write-Host ""
Write-Host "CaseSync is ready." -ForegroundColor Cyan
Write-Host "Frontend: $frontendUrl"
Write-Host "Backend:  http://localhost:8000"
Write-Host "Health:   $backendUrl"
Write-Host "Logs:     $logRoot"

if ($OpenBrave) {
    $brave = Get-Process brave -ErrorAction SilentlyContinue |
        Where-Object { $_.Path } | Select-Object -First 1 -ExpandProperty Path
    if (-not $brave) {
        $candidates = @(
            "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            "C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            (Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\Application\brave.exe")
        )
        $brave = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if ($brave) {
        Start-Process -FilePath $brave -ArgumentList $frontendUrl | Out-Null
        Write-Host "Opened CaseSync in Brave."
    } else {
        Write-Warning "Brave was not found; open $frontendUrl manually."
    }
}
