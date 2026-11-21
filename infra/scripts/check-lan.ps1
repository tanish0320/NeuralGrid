param(
    [string]$ControllerUrl = "http://127.0.0.1:8000",
    [int]$ControllerPort = 8000,
    [int]$AgentPort = 8101
)

$ErrorActionPreference = "Continue"

Write-Host "=== Windows Network Profiles ===" -ForegroundColor Cyan
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory | Format-Table -AutoSize

Write-Host "=== Active IPv4 Addresses ===" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object InterfaceAlias, IPAddress, PrefixLength | Format-Table -AutoSize

Write-Host "=== Controller Health Probe ($ControllerUrl/health) ===" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "$($ControllerUrl.TrimEnd('/'))/health" -TimeoutSec 5
    $health | ConvertTo-Json -Depth 4
} catch {
    Write-Host "Controller health check failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check same Wi-Fi/hotspot, Private network profile, VPN disconnected, and Private firewall rule." -ForegroundColor Yellow
}

Write-Host "`n=== Scoped Private-Profile Firewall Commands (run as Admin only if blocked) ===" -ForegroundColor Yellow
Write-Host "New-NetFirewallRule -DisplayName 'NeuralGrid Controller 8000' -Direction Inbound -Profile Private -Protocol TCP -LocalPort $ControllerPort -Action Allow"
Write-Host "New-NetFirewallRule -DisplayName 'NeuralGrid TwinNode Agent 8101' -Direction Inbound -Profile Private -Protocol TCP -LocalPort $AgentPort -Action Allow"
