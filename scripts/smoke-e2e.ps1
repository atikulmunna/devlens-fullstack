param(
    [string]$BackendUrl = "http://localhost:8000",
    [string]$RepoUrl = "https://github.com/psf/requests",
    [int]$MaxPolls = 180,
    [int]$PollDelaySeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "[smoke] backend: $BackendUrl"
Write-Host "[smoke] repo: $RepoUrl"

Write-Host "[smoke] waiting for backend health..."
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-RestMethod -Uri "$BackendUrl/health" -Method Get | Out-Null
        $healthy = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $healthy) {
    throw "Backend health check failed"
}

Invoke-RestMethod -Uri "$BackendUrl/health/deps" -Method Get | Out-Null

Write-Host "[smoke] submitting analyze job..."
$analyzePayload = @{ github_url = $RepoUrl } | ConvertTo-Json
$analyze = Invoke-RestMethod -Uri "$BackendUrl/api/v1/repos/analyze" -Method Post -ContentType "application/json" -Body $analyzePayload
$repoId = [string]$analyze.repo_id
$jobId = [string]$analyze.job_id
if ([string]::IsNullOrWhiteSpace($repoId) -or [string]::IsNullOrWhiteSpace($jobId)) {
    throw "Analyze response missing repo_id/job_id"
}
Write-Host "[smoke] job_id=$jobId repo_id=$repoId"

Write-Host "[smoke] waiting for terminal status..."
$terminalEvent = $null
$terminalPayload = $null
for ($i = 0; $i -lt $MaxPolls; $i++) {
    $sse = (& curl.exe -fsS "$BackendUrl/api/v1/repos/$repoId/status?once=true" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Start-Sleep -Seconds $PollDelaySeconds
        continue
    }
    $eventMatch = [regex]::Match($sse, "(?m)^event:\s*(.+)$")
    $dataMatch = [regex]::Match($sse, "(?m)^data:\s*(.+)$")
    if ($eventMatch.Success) {
        $eventName = $eventMatch.Groups[1].Value.Trim()
        if ($eventName -eq "done" -or $eventName -eq "error") {
            $terminalEvent = $eventName
            if ($dataMatch.Success) {
                $terminalPayload = $dataMatch.Groups[1].Value.Trim()
            }
            break
        }
    }
    Start-Sleep -Seconds $PollDelaySeconds
}
if (-not $terminalEvent) {
    throw "Status polling timed out"
}
if ($terminalEvent -eq "error") {
    throw "Terminal status error: $terminalPayload"
}
Write-Host "[smoke] terminal event: $terminalEvent"

$dashboard = Invoke-RestMethod -Uri "$BackendUrl/api/v1/repos/$repoId/dashboard" -Method Get
if (-not $dashboard.has_analysis) {
    throw "Dashboard has_analysis=false"
}
Write-Host "[smoke] dashboard verified"

Write-Host "[smoke] minting temporary auth token..."
$tokenScript = @"
from sqlalchemy import select
from uuid import uuid4
from app.db.session import SessionLocal
from app.db.models import User
from app.services.tokens import create_access_token

TEST_GITHUB_ID = 999999001
TEST_USERNAME = "smoke-bot"

db = SessionLocal()
try:
    user = db.execute(select(User).where(User.github_id == TEST_GITHUB_ID)).scalar_one_or_none()
    if user is None:
        user = User(id=uuid4(), github_id=TEST_GITHUB_ID, username=TEST_USERNAME, email=None, avatar_url=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    print(create_access_token(user.id))
finally:
    db.close()
"@
$token = ($tokenScript | docker compose exec -T backend python -).Trim()
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Failed to mint access token"
}

Write-Host "[smoke] creating chat session..."
$headers = @{
    Authorization = "Bearer $token"
}
$chatCreateBody = @{ repo_id = $repoId } | ConvertTo-Json
$session = Invoke-RestMethod -Uri "$BackendUrl/api/v1/chat/sessions" -Method Post -Headers $headers -ContentType "application/json" -Body $chatCreateBody
$sessionId = [string]$session.session_id
if ([string]::IsNullOrWhiteSpace($sessionId)) {
    throw "Session create failed"
}

Write-Host "[smoke] streaming chat message..."
$chatBody = @{ content = "What are the main architecture components?"; top_k = 5 } | ConvertTo-Json
$chatBodyFile = [System.IO.Path]::GetTempFileName()
Set-Content -Path $chatBodyFile -Value $chatBody -NoNewline
try {
    $chatSse = (
        & curl.exe -fsS -X POST "$BackendUrl/api/v1/chat/sessions/$sessionId/message" `
            -H "Authorization: Bearer $token" `
            -H "Content-Type: application/json" `
            --data-binary "@$chatBodyFile" | Out-String
    ).Trim()
}
finally {
    Remove-Item -Path $chatBodyFile -ErrorAction SilentlyContinue
}
if ($chatSse -notmatch "(?m)^event:\s*done\s*$") {
    throw "Chat stream missing done event"
}

Write-Host "[smoke] E2E smoke passed"
