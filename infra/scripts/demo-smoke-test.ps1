param(
    [string]$ControllerUrl = "http://127.0.0.1:8000",
    [string]$TargetNodeId = "NODE-JUNAID"
)

$ErrorActionPreference = "Stop"
$base = $ControllerUrl.TrimEnd("/")

Write-Host "1. Checking controller /health..." -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri "$base/health" -TimeoutSec 5
if ($health.status -ne "ok" -or $health.network_cell_count -ne 100) {
    throw "Health check failed: $($health | ConvertTo-Json -Compress)"
}
Write-Host "   OK: cells=$($health.network_cell_count), db_mode=$($health.db_journal_mode)" -ForegroundColor Green

Write-Host "2. Checking registered TwinNode agents..." -ForegroundColor Cyan
$nodes = Invoke-RestMethod -Uri "$base/api/v1/nodes" -TimeoutSec 5
$target = $nodes | Where-Object { $_.node_id -eq $TargetNodeId }
if (-not $target) {
    throw "Target node '$TargetNodeId' is not registered yet. Start the node agent first."
}
Write-Host "   Found $TargetNodeId (hostname=$($target.hostname), status=$($target.status), ip=$($target.ip_last_seen))" -ForegroundColor Green

if ($target.status -ne "ACTIVE") {
    Write-Host "3. Activating software worker on $TargetNodeId..." -ForegroundColor Cyan
    $null = Invoke-RestMethod -Method Post -Uri "$base/api/v1/nodes/$TargetNodeId/activate" -ContentType "application/json" -Body '{"operator_id":"smoke-test"}'
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 1
        $nodes = Invoke-RestMethod -Uri "$base/api/v1/nodes"
        $target = $nodes | Where-Object { $_.node_id -eq $TargetNodeId }
        if ($target.status -eq "ACTIVE" -and $target.worker_active) { break }
    }
    if ($target.status -ne "ACTIVE") {
        throw "$TargetNodeId failed to transition to ACTIVE (current=$($target.status))"
    }
}
Write-Host "   $TargetNodeId is ACTIVE (worker_active=$($target.worker_active))." -ForegroundColor Green

Write-Host "4. Dispatching allowlisted counterfactual_batch compute task to $TargetNodeId..." -ForegroundColor Cyan
$idemKey = "smoke-" + [guid]::NewGuid().ToString()
$taskBody = @{
    idempotency_key = $idemKey
    task_type = "counterfactual_batch"
    origin_node_id = "NODE-TANISH"
    assigned_node_id = $TargetNodeId
    seed = 42
    payload = @{ horizon_ticks = 4 }
} | ConvertTo-Json -Depth 5

$task = Invoke-RestMethod -Method Post -Uri "$base/api/v1/tasks" -ContentType "application/json" -Body $taskBody
Write-Host "   Task dispatched: $($task.task_id)" -ForegroundColor Yellow

$completedTask = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    $check = Invoke-RestMethod -Uri "$base/api/v1/tasks/$($task.task_id)"
    if ($check.status -eq "COMPLETED") {
        $completedTask = $check
        break
    }
    if ($check.status -in @("FAILED", "REJECTED", "CANCELLED")) {
        throw "Task failed with status=$($check.status): $($check.error_message)"
    }
}

if (-not $completedTask) {
    throw "Timed out waiting for task $($task.task_id) completion."
}

Write-Host "5. Verified remote completion!" -ForegroundColor Green
Write-Host "   Task ID  : $($completedTask.task_id)"
Write-Host "   Checksum : $($completedTask.checksum)"
Write-Host "   Host     : $($completedTask.result.executed_on_hostname)"
Write-Host "   Baseline Congested Min     : $($completedTask.result.baseline_congested_cell_minutes)"
Write-Host "   Intervention Congested Min : $($completedTask.result.intervention_congested_cell_minutes)"
