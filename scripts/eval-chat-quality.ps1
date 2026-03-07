param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$AccessToken,

    [string]$DatasetPath = "docs/evaluation/chat_quality_dataset.sample.json",
    [string]$OutputRoot = "artifacts/chat-quality",
    [int]$StatusMaxPolls = 180,
    [int]$StatusPollDelaySeconds = 2,
    [switch]$AutoMintLocalTokenOn401 = $true
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Ensure-File {
    param([string]$PathValue)
    if (-not (Test-Path $PathValue)) {
        throw "File not found: $PathValue"
    }
}

function Parse-SseDonePayload {
    param([string]$BodyText)
    $done = $null
    foreach ($line in ($BodyText -split "`r?`n")) {
        if ($line.StartsWith("data: ") -and $line.Contains('"message_id"')) {
            $done = $line.Substring(6)
        }
    }
    if (-not $done) { return $null }
    return $done | ConvertFrom-Json
}

function Wait-TerminalStatus {
    param(
        [string]$StatusUrl,
        [int]$MaxPolls,
        [int]$DelaySeconds
    )
    for ($i = 0; $i -lt $MaxPolls; $i++) {
        $sse = (& curl.exe -fsS "${StatusUrl}?once=true" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            Start-Sleep -Seconds $DelaySeconds
            continue
        }
        $eventMatch = [regex]::Match($sse, "(?m)^event:\s*(.+)$")
        $dataMatch = [regex]::Match($sse, "(?m)^data:\s*(.+)$")
        if (-not $eventMatch.Success) {
            Start-Sleep -Seconds $DelaySeconds
            continue
        }
        $eventName = $eventMatch.Groups[1].Value.Trim()
        $payload = if ($dataMatch.Success) { $dataMatch.Groups[1].Value.Trim() } else { "" }
        if ($eventName -eq "done" -or $eventName -eq "error") {
            return @{
                event = $eventName
                payload = $payload
            }
        }
        Start-Sleep -Seconds $DelaySeconds
    }
    throw "Status polling timed out for $StatusUrl"
}

function Evaluate-Answer {
    param(
        [string]$Intent,
        [string]$Answer,
        [int]$CitationCount
    )
    $text = ($Answer ?? "").Trim()
    $intentKey = ($Intent ?? "general").ToLowerInvariant()
    $hasAnswer = -not [string]::IsNullOrWhiteSpace($text)
    $hasCitations = $CitationCount -gt 0
    $qualityFlags = @()
    $score = 0

    if ($hasAnswer) {
        $score += 1
    } else {
        $qualityFlags += "empty_answer"
    }

    if ($hasCitations) {
        $score += 1
    } else {
        $qualityFlags += "missing_citations"
    }

    if ($intentKey -eq "summary") {
        $lineCount = @(
            $text -split "`r?`n" |
            Where-Object { $_.Trim().StartsWith("- ") -or $_.Trim().StartsWith("* ") }
        ).Count

        function Has-Section {
            param(
                [string]$Source,
                [string]$Label
            )
            $plain = "(?im)^\s*[-*]\s*$Label\s*:"
            $markdown = "(?im)^\s*[-*]\s*\*\*$Label\*\*\s*:"
            return ($Source -match $plain) -or ($Source -match $markdown)
        }

        $hasPurpose = Has-Section -Source $text -Label "Purpose"
        $hasModules = Has-Section -Source $text -Label "Core modules"
        $hasFlow = Has-Section -Source $text -Label "Runtime flow"
        $hasOutputs = Has-Section -Source $text -Label "Output formats"
        $hasLang = Has-Section -Source $text -Label "Primary languages"
        $hasNoise = $text -match "(?i)parse/index stage identified|representative paths include"

        if ($lineCount -ge 4 -and $hasPurpose -and $hasModules -and $hasFlow -and $hasOutputs -and $hasLang) {
            $score += 2
        } else {
            $qualityFlags += "summary_structure_incomplete"
        }
        if ($hasNoise) {
            $qualityFlags += "summary_noise_phrase"
        } else {
            $score += 1
        }
    } else {
        if ($text.Length -ge 40) {
            $score += 1
        } else {
            $qualityFlags += "answer_too_short"
        }
    }

    $passed = $score -ge 3 -and $qualityFlags.Count -eq 0
    return @{
        passed = $passed
        score = $score
        flags = $qualityFlags
    }
}

function New-LocalAccessToken {
    $script = @"
from sqlalchemy import select
from uuid import uuid4
from app.db.session import SessionLocal
from app.db.models import User
from app.services.tokens import create_access_token

TEST_GITHUB_ID = 999999331
TEST_USERNAME = "eval-bot"

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
    return ($script | docker compose exec -T backend python -).Trim()
}

Ensure-File -PathValue $DatasetPath

$dataset = Get-Content $DatasetPath -Raw | ConvertFrom-Json
$base = $BaseUrl.TrimEnd("/")
$apiBase = if ($base.EndsWith("/api/v1")) { $base } else { "$base/api/v1" }

$headers = @{
    "Authorization" = "Bearer $AccessToken"
    "Content-Type"  = "application/json"
}

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path $OutputRoot $runId
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$jsonlPath = Join-Path $outputDir "chat_quality_results.jsonl"
$summaryPath = Join-Path $outputDir "chat_quality_summary.md"

$rows = @()
$runtimeToken = $AccessToken

foreach ($repo in $dataset.repos) {
    $repoName = [string]$repo.name
    $repoUrl = [string]$repo.github_url
    if ([string]::IsNullOrWhiteSpace($repoUrl)) {
        Write-Warning "Skipping '$repoName': missing github_url"
        continue
    }

    Write-Host "[eval] analyze => $repoName ($repoUrl)"
    $analyzeResp = Invoke-RestMethod -Method Post -Uri "$apiBase/repos/analyze" -Headers $headers -Body (@{ github_url = $repoUrl } | ConvertTo-Json)
    $repoId = [string]$analyzeResp.repo_id
    if ([string]::IsNullOrWhiteSpace($repoId)) {
        throw "Analyze response missing repo_id for $repoName"
    }

    $terminal = Wait-TerminalStatus -StatusUrl "$apiBase/repos/$repoId/status" -MaxPolls $StatusMaxPolls -DelaySeconds $StatusPollDelaySeconds
    if ($terminal.event -eq "error") {
        throw "Analyze failed for ${repoName}: $($terminal.payload)"
    }

    foreach ($q in $repo.questions) {
        $questionId = [string]$q.id
        $intent = [string]$q.intent
        if ([string]::IsNullOrWhiteSpace($intent)) { $intent = "general" }
        $prompt = [string]$q.prompt
        if ([string]::IsNullOrWhiteSpace($prompt)) {
            Write-Warning "Skipping empty prompt in $repoName/$questionId"
            continue
        }

        $row = [ordered]@{
            run_id = $runId
            timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
            repo_name = $repoName
            github_url = $repoUrl
            repo_id = $repoId
            question_id = $questionId
            intent = $intent
            prompt = $prompt
            status = "ok"
            latency_ms = $null
            answer = $null
            citation_count = 0
            no_citation = $true
            quality_pass = $false
            quality_score = 0
            quality_flags = @()
            error = $null
        }

        $succeeded = $false
        for ($attempt = 0; $attempt -lt 2; $attempt++) {
            $headers["Authorization"] = "Bearer $runtimeToken"
            try {
                $started = Get-Date
                $session = Invoke-RestMethod -Method Post -Uri "$apiBase/chat/sessions" -Headers $headers -Body (@{ repo_id = $repoId } | ConvertTo-Json)
                $sessionId = [string]$session.session_id

                $msgBody = @{ content = $prompt; top_k = 6 } | ConvertTo-Json
                $stream = Invoke-WebRequest -Method Post -Uri "$apiBase/chat/sessions/$sessionId/message" -Headers $headers -Body $msgBody
                $done = Parse-SseDonePayload -BodyText $stream.Content
                if ($done) {
                    $row.citation_count = @($done.citations).Count
                    $row.no_citation = [bool]$done.no_citation
                }

                $detail = Invoke-RestMethod -Method Get -Uri "$apiBase/chat/sessions/$sessionId" -Headers $headers
                $assistant = @($detail.messages | Where-Object { $_.role -eq "assistant" })
                $answer = if ($assistant.Count -gt 0) { [string]$assistant[-1].content } else { "" }

                $row.answer = $answer
                $row.latency_ms = [math]::Round(((Get-Date) - $started).TotalMilliseconds, 2)

                $eval = Evaluate-Answer -Intent $intent -Answer $answer -CitationCount ([int]$row.citation_count)
                $row.quality_pass = [bool]$eval.passed
                $row.quality_score = [int]$eval.score
                $row.quality_flags = @($eval.flags)
                $succeeded = $true
                break
            }
            catch {
                $message = $_.Exception.Message
                $is401 = $message -match "401"
                $canRetryMint = $AutoMintLocalTokenOn401 -and $is401 -and $attempt -eq 0 -and $apiBase -match "^http://localhost(?::\d+)?/api/v1$"
                if ($canRetryMint) {
                    Write-Host "[eval] 401 on local backend, minting local token and retrying..."
                    $minted = New-LocalAccessToken
                    if ([string]::IsNullOrWhiteSpace($minted)) {
                        throw "Failed to mint local access token after 401"
                    }
                    $runtimeToken = $minted
                    continue
                }
                $row.status = "error"
                $row.error = $message
                break
            }
        }
        if (-not $succeeded -and $row.status -eq "ok" -and [string]::IsNullOrWhiteSpace($row.answer)) {
            $row.status = "error"
            $row.error = "Unknown failure during question execution"
        }

        $rows += [pscustomobject]$row
        ([pscustomobject]$row | ConvertTo-Json -Depth 8 -Compress) | Add-Content $jsonlPath
        Write-Host "[eval] $repoName/$questionId => $($row.status) (pass=$($row.quality_pass))"
    }
}

$okRows = @($rows | Where-Object { $_.status -eq "ok" })
$passRows = @($okRows | Where-Object { $_.quality_pass -eq $true })
$avgLatency = if ($okRows.Count -gt 0) { [math]::Round((($okRows | Measure-Object -Property latency_ms -Average).Average), 2) } else { 0 }
$citationCoverage = if ($okRows.Count -gt 0) { [math]::Round(((@($okRows | Where-Object { $_.citation_count -gt 0 }).Count / $okRows.Count) * 100), 2) } else { 0 }
$passRate = if ($okRows.Count -gt 0) { [math]::Round((($passRows.Count / $okRows.Count) * 100), 2) } else { 0 }

$summaryLines = @(
    "# Chat Quality Eval Report",
    "",
    "- Run ID: $runId",
    "- Base URL: $BaseUrl",
    "- Dataset: $DatasetPath",
    "- Total checks: $($rows.Count)",
    "- Successful checks: $($okRows.Count)",
    "- Quality pass rate: $passRate%",
    "- Citation coverage: $citationCoverage%",
    "- Avg latency (ms): $avgLatency",
    "",
    "## Results File",
    "- $jsonlPath",
    "",
    "## Failed Checks",
    ""
)

$failed = @($rows | Where-Object { $_.status -ne "ok" -or $_.quality_pass -ne $true })
if ($failed.Count -eq 0) {
    $summaryLines += "- None"
} else {
    foreach ($f in $failed) {
        $flags = if ($f.quality_flags -and $f.quality_flags.Count -gt 0) { ($f.quality_flags -join ",") } else { "-" }
        $summaryLines += "- $($f.repo_name)/$($f.question_id): status=$($f.status), flags=$flags, error=$($f.error)"
    }
}

$summaryLines -join "`n" | Set-Content -Path $summaryPath
Write-Host "Wrote:"
Write-Host " - $jsonlPath"
Write-Host " - $summaryPath"
