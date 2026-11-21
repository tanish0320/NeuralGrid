param(
    [string]$ControllerUrl = "http://127.0.0.1:8000",
    [string]$TargetNodeId = "NODE-JUNAID"
)

$scriptPath = Join-Path $PSScriptRoot "demo-smoke-test.ps1"
& $scriptPath -ControllerUrl $ControllerUrl -TargetNodeId $TargetNodeId
