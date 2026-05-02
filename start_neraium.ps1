param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$BackendUrl = "http://127.0.0.1:$BackendPort/health"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

function Test-HttpReady {
    param(
        [string]$Url,
        [int]$Attempts = 30
    )

    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    return $false
}

if (-not (Test-Path $Frontend)) {
    throw "Frontend directory not found: $Frontend"
}

Write-Host "Starting Neraium backend on port $BackendPort..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$Root`"; python -m uvicorn api.main:app --port $BackendPort"
) -WindowStyle Normal

Write-Host "Waiting for backend..."
if (-not (Test-HttpReady -Url $BackendUrl -Attempts 30)) {
    throw "Backend did not become ready at $BackendUrl"
}

Write-Host "Starting Neraium frontend on port $FrontendPort..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$Frontend`"; if (-not (Test-Path node_modules)) { npm install }; npm run dev -- --host 127.0.0.1 --port $FrontendPort"
) -WindowStyle Normal

Write-Host "Waiting for frontend..."
if (-not (Test-HttpReady -Url $FrontendUrl -Attempts 45)) {
    throw "Frontend did not become ready at $FrontendUrl"
}

Write-Host "Opening Neraium Operator Console..."
Start-Process $FrontendUrl

Write-Host ""
Write-Host "Neraium is running:"
Write-Host "  Backend:  http://127.0.0.1:$BackendPort"
Write-Host "  Frontend: $FrontendUrl"
Write-Host ""
Write-Host "Close the two PowerShell server windows to stop Neraium."
