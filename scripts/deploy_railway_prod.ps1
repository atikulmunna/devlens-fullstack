param(
    [Parameter(Mandatory = $true)]
    [string]$RailwayToken,
    [string]$ProjectName = "devlens-fullstack",
    [string]$BackendService = "backend",
    [string]$WorkerService = "worker",
    [string]$EnvironmentName = "production",
    [string]$BackendEnvFile = "backend/.env",
    [string]$WorkerEnvFile = "workers/.env"
)

$ErrorActionPreference = "Stop"

function Require-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required file not found: $Path"
    }
}

function Parse-EnvFile {
    param([string]$Path)
    $map = @{}
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith("#")) { return }
        $parts = $line.Split("=", 2)
        if ($parts.Length -ne 2) { return }
        $k = $parts[0].Trim()
        $v = $parts[1]
        $map[$k] = $v
    }
    return $map
}

function Set-ServiceVarsFromMap {
    param(
        [string]$ServiceName,
        [hashtable]$Vars,
        [string[]]$AllowList
    )

    foreach ($key in $AllowList) {
        if ($Vars.ContainsKey($key)) {
            $value = [string]$Vars[$key]
            railway variable set --service $ServiceName --environment $EnvironmentName --skip-deploys "$key=$value" | Out-Null
        }
    }
}

$env:RAILWAY_TOKEN = $RailwayToken

Require-File -Path $BackendEnvFile
Require-File -Path $WorkerEnvFile

railway whoami | Out-Null

# Create a project if current directory is not linked.
$statusOk = $true
try {
    railway status --json | Out-Null
} catch {
    $statusOk = $false
}

if (-not $statusOk) {
    railway init -n $ProjectName | Out-Null
}

# Ensure target environment link exists.
try {
    railway environment link $EnvironmentName | Out-Null
} catch {
    # Keep default environment if named env does not exist.
}

# Ensure services exist (idempotent enough for first run).
try { railway add --service $BackendService | Out-Null } catch {}
try { railway add --service $WorkerService | Out-Null } catch {}

$backendVars = Parse-EnvFile -Path $BackendEnvFile
$workerVars = Parse-EnvFile -Path $WorkerEnvFile

$backendAllow = @(
    "APP_NAME","ENV","DATABASE_URL","REDIS_URL","QDRANT_URL","QDRANT_COLLECTION",
    "GITHUB_CLIENT_ID","GITHUB_CLIENT_SECRET","GITHUB_OAUTH_REDIRECT_URI","FRONTEND_URL",
    "OPENROUTER_API_KEY","GROQ_API_KEY","JWT_SECRET","JWT_ACCESS_TTL_MINUTES","JWT_REFRESH_TTL_DAYS",
    "SHARE_TOKEN_TTL_DAYS","RATE_LIMIT_WINDOW_SECONDS","RATE_LIMIT_GUEST_PER_WINDOW","RATE_LIMIT_AUTH_PER_WINDOW",
    "R2_BUCKET","R2_ACCESS_KEY","R2_SECRET_KEY"
)

$workerAllow = @(
    "ENV","REDIS_URL","DATABASE_URL","QDRANT_URL","QDRANT_COLLECTION",
    "PARSE_CLONE_TIMEOUT_SECONDS","PARSE_MAX_FILES","PARSE_MAX_CHUNKS","PARSE_CHUNK_LINES","PARSE_CHUNK_OVERLAP_LINES",
    "EMBED_VECTOR_SIZE","EMBED_BATCH_SIZE","EMBED_RETRY_ATTEMPTS",
    "WORKER_RETRY_MAX_ATTEMPTS","WORKER_RETRY_BASE_DELAY_SECONDS","WORKER_METRICS_PORT",
    "LLM_SUMMARY_PROVIDER","LLM_SUMMARY_MODEL","LLM_SUMMARY_TIMEOUT_SECONDS","OPENROUTER_API_KEY","OPENROUTER_BASE_URL"
)

Set-ServiceVarsFromMap -ServiceName $BackendService -Vars $backendVars -AllowList $backendAllow
Set-ServiceVarsFromMap -ServiceName $WorkerService -Vars $workerVars -AllowList $workerAllow

railway up backend --service $BackendService --environment $EnvironmentName --path-as-root --ci
railway up workers --service $WorkerService --environment $EnvironmentName --path-as-root --ci

$backendDomain = railway domain --service $BackendService
Write-Host "Backend domain:"
Write-Host $backendDomain
