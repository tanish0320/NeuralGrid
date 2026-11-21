# Start the NeuralGrid Operations Console (Vite React frontend)
[CmdletBinding()]
param(
    [string]$Port = "5173"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   NeuralGrid Operations Console - Web Frontend           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

Set-Location (Join-Path $ProjectRoot "apps\web")

Write-Host "Starting Vite frontend server on port $Port..." -ForegroundColor Green
npm run dev -- --port $Port --host 0.0.0.0
