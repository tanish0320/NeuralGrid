param(
    [string]$EnvFile = ".env",
    [string]$NodeId = "",
    [string]$ControllerUrl = "",
    [string]$NodeToken = "",
    [int]$AgentPort = 0
)

$scriptPath = Join-Path $PSScriptRoot "start-agent.ps1"
& $scriptPath -EnvFile $EnvFile -NodeId $NodeId -ControllerUrl $ControllerUrl -NodeToken $NodeToken -AgentPort $AgentPort
