param(
    [string]$EnvFile = ".env",
    [string]$NodeId = "",
    [string]$ControllerUrl = "",
    [string]$NodeToken = "",
    [int]$AgentPort = 0
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

if ($NodeId) { $env:TWINNODE_NODE_ID = $NodeId }
if ($ControllerUrl) { $env:TWINNODE_CONTROLLER_URL = $ControllerUrl }
if ($NodeToken) { $env:TWINNODE_NODE_TOKEN = $NodeToken }
if ($AgentPort -gt 0) { $env:TWINNODE_AGENT_PORT = "$AgentPort" }

if (-not $env:TWINNODE_NODE_ID) { throw "TWINNODE_NODE_ID must be set in .env or passed via -NodeId" }
if (-not $env:TWINNODE_CONTROLLER_URL -or $env:TWINNODE_CONTROLLER_URL -like "*<TANISH_PRIVATE_IP>*") {
    throw "TWINNODE_CONTROLLER_URL must point to Tanish's actual private IPv4 (check ipconfig)"
}
if (-not $env:TWINNODE_NODE_TOKEN -or $env:TWINNODE_NODE_TOKEN -eq "GENERATE_A_RANDOM_LOCAL_TOKEN") {
    throw "TWINNODE_NODE_TOKEN must be configured with the shared per-node token"
}

$venvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

Write-Host "Local IPv4 addresses (for operator reference):" -ForegroundColor Yellow
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object InterfaceAlias, IPAddress | Format-Table -AutoSize

Write-Host "Starting TwinNode Agent '$($env:TWINNODE_NODE_ID)' -> Controller $($env:TWINNODE_CONTROLLER_URL)" -ForegroundColor Cyan
python -m agents.twinnode.node_agent.run_agent
