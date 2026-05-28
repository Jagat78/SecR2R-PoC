param(
    [switch]$Rebuild,
    [switch]$SkipReplay,
    [switch]$StopWhenDone
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$healthTimeoutSec = 90
$composeRunner = $null

function Set-ComposeRunner {
    $venvCompose = Join-Path (Split-Path -Parent $root) ".venv\Scripts\podman-compose.exe"

    if (Get-Command podman-compose -ErrorAction SilentlyContinue) {
        $script:composeRunner = "global-podman-compose"
        return
    }

    if (Test-Path $venvCompose) {
        $script:composeRunner = $venvCompose
        return
    }

    try {
        podman compose version | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $script:composeRunner = "podman-compose-plugin"
            return
        }
    }
    catch {
        # Ignore and continue to final error.
    }

    throw "No compose provider found. Install podman-compose (global or in .venv) or configure 'podman compose' provider."
}

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)][string[]]$Args
    )

    switch ($script:composeRunner) {
        "global-podman-compose" {
            & podman-compose @Args
        }
        "podman-compose-plugin" {
            & podman compose @Args
        }
        default {
            & $script:composeRunner @Args
        }
    }
}

function Wait-Health {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSec = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 4
            if ($null -ne $resp.status -and $resp.status -eq "ok") {
                return $true
            }
        }
        catch {
            # Keep retrying until timeout.
        }
        Start-Sleep -Milliseconds 1200
    }

    throw "Timed out waiting for service health: $Url"
}

function Register-Robot {
    param(
        [Parameter(Mandatory = $true)][string]$RobotId,
        [Parameter(Mandatory = $true)][hashtable]$Attributes
    )

    $body = @{
        robot_id = $RobotId
        attributes = $Attributes
    } | ConvertTo-Json -Depth 6

    Invoke-RestMethod -Method Post -Uri "http://localhost:8000/register" -ContentType "application/json" -Body $body -TimeoutSec 12
}

function Invoke-ProtocolFlow {
    param(
        [Parameter(Mandatory = $true)][string]$TargetRobot,
        [Parameter(Mandatory = $true)][hashtable]$Attributes
    )

    $body = @{
        target_robot = $TargetRobot
        attributes = $Attributes
    } | ConvertTo-Json -Depth 6

    Invoke-RestMethod -Method Post -Uri "http://localhost:8001/session-run" -ContentType "application/json" -Body $body -TimeoutSec 20
}

function Show-MetricsSummary {
    param(
        [string]$Timestamp = ""
    )

    $csvFiles = @(
        Join-Path $logsDir "server_metrics.csv"
        Join-Path $logsDir "robot_a_metrics.csv"
        Join-Path $logsDir "robot_b_metrics.csv"
    )

    $rows = @()
    foreach ($f in $csvFiles) {
        if (Test-Path $f) {
            $rows += Import-Csv $f
        }
    }

    if ($rows.Count -eq 0) {
        Write-Host "No metrics rows found yet in logs/."
        return @()
    }

    $summary = $rows |
        Group-Object component, event |
        ForEach-Object {
            $g = @($_.Group)
            $sampleCount = @($g).Count
            $avgMs = ($g | Measure-Object -Property elapsed_ms -Average).Average
            $avgIn = ($g | Measure-Object -Property bytes_in -Average).Average
            $avgOut = ($g | Measure-Object -Property bytes_out -Average).Average
            $okCount = @($g | Where-Object { $_.ok -eq "1" }).Count
            $okRate = ($okCount / [double]$sampleCount) * 100.0

            [PSCustomObject]@{
                component = $g[0].component
                event = $g[0].event
                samples = $sampleCount
                avg_elapsed_ms = [Math]::Round($avgMs, 3)
                avg_bytes_in = [Math]::Round($avgIn, 1)
                avg_bytes_out = [Math]::Round($avgOut, 1)
                ok_rate_pct = [Math]::Round($okRate, 1)
            }
        }

    Write-Host "`n=== Metrics Summary ==="
    $sortedSummary = $summary | Sort-Object component, event
    $sortedSummary | Format-Table -AutoSize

    if ([string]::IsNullOrWhiteSpace($Timestamp)) {
        $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    }

    $paperSummaryPath = Join-Path $logsDir "paper_metrics_summary_$Timestamp.csv"
    $latestSummaryPath = Join-Path $logsDir "paper_metrics_summary_latest.csv"
    $sortedSummary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $paperSummaryPath
    $sortedSummary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $latestSummaryPath
    Write-Host "Paper-ready summary exported to: $paperSummaryPath"
    Write-Host "Latest summary snapshot: $latestSummaryPath"

    return $sortedSummary
}

Push-Location $root
try {
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir | Out-Null
    }

    Write-Host "Starting Podman machine..."
    podman machine start | Out-Null

    Set-ComposeRunner
    Write-Host "Using compose runner: $composeRunner"

    if ($Rebuild) {
        Write-Host "Bringing stack up with rebuild..."
        Invoke-Compose -Args @("up", "--build", "-d")
    }
    else {
        Write-Host "Bringing stack up..."
        Invoke-Compose -Args @("up", "-d")
    }

    Write-Host "Waiting for services to become healthy..."
    Wait-Health -Url "http://localhost:8000/health" -TimeoutSec $healthTimeoutSec | Out-Null
    Wait-Health -Url "http://localhost:8001/health" -TimeoutSec $healthTimeoutSec | Out-Null
    Wait-Health -Url "http://localhost:8002/health" -TimeoutSec $healthTimeoutSec | Out-Null

    Write-Host "Registering robots..."
    $regA = Register-Robot -RobotId "R_A" -Attributes @{ joint = "A1"; sensor = "S1"; profile = "industrial" }
    $regB = Register-Robot -RobotId "R_B" -Attributes @{ joint = "B1"; sensor = "S2"; profile = "industrial" }

    Write-Host "Running one baseline session..."
    $session = Invoke-ProtocolFlow -TargetRobot "R_B" -Attributes @{ joint = "A1"; sensor = "S1"; profile = "industrial" }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $regA | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $logsDir "last_register_A_$timestamp.json") -Encoding UTF8
    $regB | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $logsDir "last_register_B_$timestamp.json") -Encoding UTF8
    $session | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $logsDir "last_session_$timestamp.json") -Encoding UTF8

    Write-Host "Baseline session result:"
    $session | ConvertTo-Json -Depth 8

    if (-not $SkipReplay) {
        Write-Host "Running replay test from attacker script..."
        podman exec secr2r_robot_a python attacker/replay_attack.py --server http://server:8000 --delay 35
    }

    $null = Show-MetricsSummary -Timestamp $timestamp

    Write-Host "`nDemo completed. Logs and JSON outputs are in: $logsDir"

    if ($StopWhenDone) {
        Write-Host "Stopping stack (--StopWhenDone requested)..."
        Invoke-Compose -Args @("down")
    }
}
finally {
    Pop-Location
}
