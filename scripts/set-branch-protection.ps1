param(
    [string]$Repo,
    [string]$Branch = "main",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required."
}

if (-not $Repo) {
    $Repo = gh repo view --json nameWithOwner -q ".nameWithOwner"
}

if (-not $Repo) {
    throw "Unable to resolve repository slug. Pass -Repo owner/name."
}

$requiredChecks = @(
    "Lint And Static Checks",
    "Backend Tests",
    "Worker Tests",
    "Build Service Images",
    "Backend Coverage"
)

$payload = @{
    required_status_checks = @{
        strict   = $true
        contexts = $requiredChecks
    }
    enforce_admins                      = $true
    required_pull_request_reviews       = @{
        dismiss_stale_reviews           = $true
        require_code_owner_reviews      = $false
        required_approving_review_count = 1
    }
    restrictions                        = $null
    required_linear_history             = $true
    allow_force_pushes                  = $false
    allow_deletions                     = $false
    block_creations                     = $false
    required_conversation_resolution    = $true
    lock_branch                         = $false
    allow_fork_syncing                  = $false
}

$json = $payload | ConvertTo-Json -Depth 8

Write-Host "Repo: $Repo"
Write-Host "Branch: $Branch"
Write-Host "Required checks:"
$requiredChecks | ForEach-Object { Write-Host "- $_" }

if ($DryRun) {
    Write-Host ""
    Write-Host "[DryRun] Payload:"
    Write-Host $json
    exit 0
}

$tmp = [System.IO.Path]::GetTempFileName()
try {
    Set-Content -LiteralPath $tmp -Value $json -NoNewline
    gh api `
        --method PUT `
        --header "Accept: application/vnd.github+json" `
        --input $tmp `
        "repos/$Repo/branches/$Branch/protection" | Out-Null
}
finally {
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
}

Write-Host "Branch protection updated for $Repo ($Branch)."
