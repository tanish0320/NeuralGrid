param(
    [string]$EnvFile = ".env",
    [string]$BindHost = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
}

$venvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

$resolvedHost = if ($BindHost) { $BindHost } elseif ($env:NEURALGRID_API_HOST) { $env:NEURALGRID_API_HOST } else { "0.0.0.0" }
$resolvedPort = if ($Port -gt 0) { $Port } elseif ($env:NEURALGRID_API_PORT) { [int]$env:NEURALGRID_API_PORT } else { 8000 }

Write-Host "Starting NeuralGrid FastAPI Control Plane on ${resolvedHost}:${resolvedPort}..." -ForegroundColor Cyan
python -m uvicorn apps.api.app.main:app --host $resolvedHost --port $resolvedPort
