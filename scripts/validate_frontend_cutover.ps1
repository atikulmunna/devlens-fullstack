param(
    [Parameter(Mandatory = $true)]
    [string]$LegacyBaseUrl,
    [Parameter(Mandatory = $true)]
    [string]$NextBaseUrl,
    [string]$SampleRepoId = "",
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

function Assert-RouteOk {
    param(
        [string]$Base,
        [string]$Path
    )
    $url = "$($Base.TrimEnd('/'))$Path"
    $resp = Invoke-WebRequest -Uri $url -TimeoutSec $TimeoutSeconds -Method Get
    if ($resp.StatusCode -ne 200) {
        throw "Route check failed: $url (status=$($resp.StatusCode))"
    }
    Write-Host "[ok] $url"
}

Assert-RouteOk -Base $LegacyBaseUrl -Path "/"
Assert-RouteOk -Base $LegacyBaseUrl -Path "/analyze"
Assert-RouteOk -Base $NextBaseUrl -Path "/"
Assert-RouteOk -Base $NextBaseUrl -Path "/analyze"

if ($SampleRepoId) {
    Assert-RouteOk -Base $LegacyBaseUrl -Path "/dashboard/$SampleRepoId"
    Assert-RouteOk -Base $NextBaseUrl -Path "/dashboard/$SampleRepoId"
}

Write-Host "[ok] frontend cutover route validation passed"
