$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$AccessToken,

    [string]$DatasetPath = "docs/evaluation/golden_eval_dataset.json",
    [string]$RepoMapPath = "docs/evaluation/repo_map.local.json",
    [string]$OutputRoot = "artifacts/eval"
)

if (-not (Test-Path $DatasetPath)) {
    throw "Dataset file not found: $DatasetPath"
}

if (-not (Test-Path $RepoMapPath)) {
    throw "Repo map file not found: $RepoMapPath"
}

$dataset = Get-Content $DatasetPath -Raw | ConvertFrom-Json
$repoMap = Get-Content $RepoMapPath -Raw | ConvertFrom-Json

$base = $BaseUrl.TrimEnd("/")
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path $OutputRoot $runId
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$resultsFile = Join-Path $outputDir "results.jsonl"

$headers = @{
    "Authorization" = "Bearer $AccessToken"
    "Content-Type"  = "application/json"
}

function Parse-SseDone {
    param([string]$BodyText)
    $doneLine = $null
    foreach ($line in ($BodyText -split "`r?`n")) {
        if ($line.StartsWith("data: ") -and $line.Contains('"message_id"')) {
            $doneLine = $line.Substring(6)
        }
    }
    if (-not $doneLine) {
        return $null
    }
    return $doneLine | ConvertFrom-Json
}

foreach ($repo in $dataset.repos) {
    $repoKey = [string]$repo.repo_key
    $repoId = $repoMap.$repoKey
    if (-not $repoId) {
        Write-Warning "Skipping repo '$repoKey': no repo_id in map"
        continue
    }

    foreach ($question in $repo.questions) {
        $questionId = [string]$question.id
        $prompt = [string]$question.prompt

        $row = [ordered]@{
            run_id = $runId
            repo_key = $repoKey
            repo_id = $repoId
            question_id = $questionId
            question = $prompt
            answer = $null
            citations = @()
            no_citation = $true
            status = "ok"
            error = $null
        }

        try {
            $sessionResp = Invoke-RestMethod `
                -Method Post `
                -Uri "$base/chat/sessions" `
                -Headers $headers `
                -Body (@{ repo_id = $repoId } | ConvertTo-Json)
            $sessionId = [string]$sessionResp.session_id

            $msgBody = @{
                content = $prompt
                top_k = 5
            } | ConvertTo-Json

            $messageStream = Invoke-WebRequest `
                -Method Post `
                -Uri "$base/chat/sessions/$sessionId/message" `
                -Headers $headers `
                -Body $msgBody

            $donePayload = Parse-SseDone -BodyText $messageStream.Content
            if ($donePayload) {
                $row.citations = @($donePayload.citations)
                $row.no_citation = [bool]$donePayload.no_citation
            }

            $sessionDetail = Invoke-RestMethod `
                -Method Get `
                -Uri "$base/chat/sessions/$sessionId" `
                -Headers $headers

            $assistantMessages = @($sessionDetail.messages | Where-Object { $_.role -eq "assistant" })
            if ($assistantMessages.Count -gt 0) {
                $row.answer = [string]$assistantMessages[-1].content
            }
        }
        catch {
            $row.status = "error"
            $row.error = $_.Exception.Message
        }

        ($row | ConvertTo-Json -Depth 8 -Compress) | Add-Content $resultsFile
        Write-Host "Processed $repoKey / $questionId => $($row.status)"
    }
}

Write-Host "Run complete: $resultsFile"
