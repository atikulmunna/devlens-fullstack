param(
    [string]$RailwayToken = "",
    [string]$ProjectName = "devlens-fullstack",
    [string]$BackendService = "backend",
    [string]$WorkerService = "worker",
    [string]$BackendEnvFile = "backend/.env.staging",
    [string]$WorkerEnvFile = "workers/.env.staging"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackendEnvFile)) {
    throw "Missing staging backend env file: $BackendEnvFile"
}
if (-not (Test-Path $WorkerEnvFile)) {
    throw "Missing staging worker env file: $WorkerEnvFile"
}

./scripts/deploy_railway_prod.ps1 `
  -RailwayToken $RailwayToken `
  -ProjectName $ProjectName `
  -BackendService $BackendService `
  -WorkerService $WorkerService `
  -EnvironmentName "staging" `
  -BackendEnvFile $BackendEnvFile `
  -WorkerEnvFile $WorkerEnvFile
