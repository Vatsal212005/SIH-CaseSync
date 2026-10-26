[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$stateFile = Join-Path $projectRoot ".casesync-dev-processes.json"

function Get-PortOwner([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

$snapshot = @(Get-CimInstance Win32_Process)

function Test-CaseSyncProcessTree([int]$Id) {
    $seen = @{}
    $current = $Id
    while ($current -and -not $seen.ContainsKey($current)) {
        $seen[$current] = $true
        $row = $snapshot | Where-Object ProcessId -eq $current | Select-Object -First 1
        if (-not $row) { break }
        if ($row.CommandLine -and $row.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
        $current = [int]$row.ParentProcessId
    }
    return $false
}

function Get-DescendantIds([int]$ParentId) {
    $result = @()
    $children = @($snapshot | Where-Object ParentProcessId -eq $ParentId)
    foreach ($child in $children) {
        $result += Get-DescendantIds ([int]$child.ProcessId)
        $result += [int]$child.ProcessId
    }
    return $result
}

function Convert-ToUtcDate($Value) {
    if ($Value -is [datetime]) { return $Value.ToUniversalTime() }
    return [datetime]::Parse(
        [string]$Value,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    ).ToUniversalTime()
}

$targets = @()
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    if ($state.ProjectRoot -ne $projectRoot) {
        throw "The saved process state belongs to a different project root; no processes were stopped."
    }
    foreach ($record in @($state.Processes)) {
        $process = Get-Process -Id ([int]$record.Id) -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        $expected = Convert-ToUtcDate $record.StartTimeUtc
        $actual = $process.StartTime.ToUniversalTime()
        if ($process.ProcessName -eq $record.Name -and [math]::Abs(($actual - $expected).TotalSeconds) -lt 2) {
            $targets += Get-DescendantIds $process.Id
            $targets += $process.Id
        } else {
            Write-Warning "PID $($record.Id) no longer matches its saved identity and was not stopped."
        }
    }
}

foreach ($port in @(3000, 8000)) {
    $owner = Get-PortOwner $port
    if ($owner -and (Test-CaseSyncProcessTree $owner)) {
        $targets += Get-DescendantIds $owner
        $targets += $owner
    } elseif ($owner) {
        Write-Warning "Port $port is owned by unrelated PID $owner and was left untouched."
    }
}

$targets = @($targets | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique)
if ($targets.Count) {
    Stop-Process -Id $targets -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped CaseSync process IDs: $($targets -join ', ')" -ForegroundColor Green
} else {
    Write-Host "No running CaseSync processes were found."
}

Start-Sleep -Seconds 1
foreach ($port in @(3000, 8000)) {
    $owner = Get-PortOwner $port
    if ($owner) {
        Write-Warning "Port $port remains occupied by PID $owner; it was not identified as a CaseSync process."
    }
}

if (Test-Path -LiteralPath $stateFile) {
    Remove-Item -LiteralPath $stateFile -Force
}
