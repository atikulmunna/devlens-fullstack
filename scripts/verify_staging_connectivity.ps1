param(
    [Parameter(Mandatory = $true)]
    [string]$BackendBaseUrl,
    [string]$WorkerMetricsUrl = "",
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"
$base = $BackendBaseUrl.TrimEnd("/")

function Assert-Ok {
    param(
        [string]$Name,
        [string]$Url
    )
    Write-Host "[check] $Name -> $Url"
    $resp = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec $TimeoutSeconds
    return $resp
}

$health = Assert-Ok -Name "backend-health" -Url "$base/health"
if ($health.status -ne "ok") {
    throw "Backend /health is not ok"
}

$deps = Assert-Ok -Name "backend-health-deps" -Url "$base/health/deps"
if (-not $deps.all_healthy) {
    throw "Dependency health check failed: all_healthy=false"
}
if (-not $deps.postgres) {
    throw "Postgres connectivity check failed"
}
if (-not $deps.redis) {
    throw "Redis connectivity check failed"
}
if (-not $deps.qdrant) {
    throw "Qdrant connectivity check failed"
}

if ($WorkerMetricsUrl) {
    $metrics = Invoke-WebRequest -Method Get -Uri $WorkerMetricsUrl -TimeoutSec $TimeoutSeconds
    if ($metrics.StatusCode -ne 200) {
        throw "Worker metrics endpoint returned status $($metrics.StatusCode)"
    }
    Write-Host "[ok] worker-metrics -> $WorkerMetricsUrl"
}

Write-Host "[ok] staging managed-provider connectivity verified"
