param(
    [string]$ControllerUrl = "http://127.0.0.1:8000",
    [int]$Seed = 42
)

$ErrorActionPreference = "Stop"
$base = $ControllerUrl.TrimEnd("/")

Write-Host "Resetting NeuralGrid synthetic 100-cell network (seed=$Seed)..." -ForegroundColor Cyan
$netBody = @{
    seed = $Seed
    cell_count = 100
} | ConvertTo-Json

$net = Invoke-RestMethod -Method Post -Uri "$base/api/v1/networks/seed" -ContentType "application/json" -Body $netBody
Write-Host "Network seeded: $($net.network_id) with $($net.cell_count) cells." -ForegroundColor Green

$simBody = @{
    seed = $Seed
    step_minutes = 5
} | ConvertTo-Json

$sim = Invoke-RestMethod -Method Post -Uri "$base/api/v1/simulations" -ContentType "application/json" -Body $simBody
Write-Host "Fresh simulation run created: $($sim.simulation_id) (tick=$($sim.tick), state_version=$($sim.state_version))." -ForegroundColor Green
