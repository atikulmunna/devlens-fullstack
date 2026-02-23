param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$AccessToken,

    [Parameter(Mandatory = $true)]
    [string]$RepoUrl,

    [int]$Runs = 3,
    [int]$PollIntervalSec = 2,
    [int]$MaxWaitSec = 900,
    [string]$ChatPrompt = "Where is authentication refresh handled?",
    [string]$OutputRoot = "artifacts/load"
)

$ErrorActionPreference = "Stop"

function Get-Percentile {
    param(
        [double[]]$Values,
        [double]$Percentile
    )
    if (-not $Values -or $Values.Count -eq 0) {
        return $null
    }
    $sorted = $Values | Sort-Object
    $rank = [math]::Ceiling(($Percentile / 100.0) * $sorted.Count) - 1
    if ($rank -lt 0) { $rank = 0 }
    if ($rank -ge $sorted.Count) { $rank = $sorted.Count - 1 }
    return [double]$sorted[$rank]
}

function Get-StatusOnce {
    param(
        [string]$BaseUrl,
        [string]$RepoId,
        [hashtable]$Headers
    )
    $resp = Invoke-WebRequest -Method Get -Uri "$BaseUrl/repos/$RepoId/status?once=true" -Headers $Headers -SkipHttpErrorCheck
    if ($resp.StatusCode -ge 400) {
        throw "Status endpoint returned HTTP $($resp.StatusCode): $($resp.Content)"
    }

    $eventName = $null
    $dataRaw = $null
    foreach ($line in ($resp.Content -split "`r?`n")) {
        if ($line.StartsWith("event: ")) {
            $eventName = $line.Substring(7).Trim()
        }
        elseif ($line.StartsWith("data: ")) {
            $dataRaw = $line.Substring(6).Trim()
        }
    }

    $payload = $null
    if ($dataRaw) {
        $payload = $dataRaw | ConvertFrom-Json
    }
    return @{
        event = $eventName
        payload = $payload
    }
}

function Test-IsUnauthorized {
    param([object]$ErrorRecord)
    try {
        if ($null -ne $ErrorRecord.Exception.Response -and $null -ne $ErrorRecord.Exception.Response.StatusCode) {
            return ([int]$ErrorRecord.Exception.Response.StatusCode -eq 401)
        }
    }
    catch {}
    return $false
}

function Measure-ChatSse {
    param(
        [string]$Url,
        [string]$AccessToken,
        [string]$BodyJson
    )

    $httpClient = [System.Net.Http.HttpClient]::new()
    try {
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $Url)
        $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $AccessToken)
        $request.Content = [System.Net.Http.StringContent]::new($BodyJson, [System.Text.Encoding]::UTF8, "application/json")

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $response = $httpClient.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
        $response.EnsureSuccessStatusCode()

        $stream = $response.Content.ReadAsStreamAsync().Result
        $reader = [System.IO.StreamReader]::new($stream)

        $firstDeltaMs = $null
        $donePayload = $null
        $currentEvent = $null

        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if ($line.StartsWith("event: ")) {
                $currentEvent = $line.Substring(7).Trim()
                continue
            }
            if ($line.StartsWith("data: ")) {
                $data = $line.Substring(6).Trim()
                if ($currentEvent -eq "delta" -and $firstDeltaMs -eq $null) {
                    $firstDeltaMs = [double]$sw.ElapsedMilliseconds
                }
                if ($currentEvent -eq "done") {
                    $donePayload = $data | ConvertFrom-Json
                }
            }
        }

        $sw.Stop()
        return @{
            first_delta_ms = $firstDeltaMs
            stream_total_ms = [double]$sw.ElapsedMilliseconds
            done_payload = $donePayload
        }
    }
    finally {
        $httpClient.Dispose()
    }
}

$base = $BaseUrl.TrimEnd("/")
$headers = @{
    "Authorization" = "Bearer $AccessToken"
    "Content-Type" = "application/json"
}

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path $OutputRoot $runId
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$rows = @()

for ($i = 1; $i -le $Runs; $i++) {
    Write-Host ("Run {0}/{1}: submitting analyze job" -f $i, $Runs)
    $idem = "sla-$runId-$i"
    $analyzeBody = @{
        github_url = $RepoUrl
        force_reanalyze = $true
    } | ConvertTo-Json
    $analyzeHeaders = @{
        "Authorization" = "Bearer $AccessToken"
        "Content-Type" = "application/json"
        "Idempotency-Key" = $idem
    }
    try {
        $analyzeResp = Invoke-RestMethod -Method Post -Uri "$base/repos/analyze" -Headers $analyzeHeaders -Body $analyzeBody
    }
    catch {
        if (Test-IsUnauthorized -ErrorRecord $_) {
            throw "Access token expired or unauthorized before analyze submission. Refresh token and rerun."
        }
        throw
    }
    $repoId = [string]$analyzeResp.repo_id
    $jobId = [string]$analyzeResp.job_id

    $analysisSw = [System.Diagnostics.Stopwatch]::StartNew()
    $analysisDone = $false
    $analysisError = $null
    $waitedSec = 0

    while ($true) {
        Start-Sleep -Seconds $PollIntervalSec
        $waitedSec += $PollIntervalSec
        try {
            $statusSnap = Get-StatusOnce -BaseUrl $base -RepoId $repoId -Headers $headers
            $eventName = [string]$statusSnap.event
            $payload = $statusSnap.payload
            $statusJobId = if ($payload) { [string]$payload.job_id } else { "" }

            if ($statusJobId -ne $jobId) {
                continue
            }

            if ($eventName -eq "done") {
                $analysisDone = $true
                break
            }
            if ($eventName -eq "error") {
                $analysisError = if ($payload -and $payload.message) { [string]$payload.message } else { "Analysis failed" }
                break
            }
        }
        catch {
            if (Test-IsUnauthorized -ErrorRecord $_) {
                throw "Access token expired or unauthorized during benchmark polling. Refresh token and rerun."
            }
            $analysisError = $_.Exception.Message
        }
        if ($waitedSec -ge $MaxWaitSec) {
            $analysisError = "Analysis wait timeout (${MaxWaitSec}s)"
            break
        }
    }
    $analysisSw.Stop()

    if (-not $analysisDone) {
        $rows += [pscustomobject]@{
            run_index = $i
            repo_id = $repoId
            job_id = $jobId
            analysis_duration_sec = [math]::Round($analysisSw.Elapsed.TotalSeconds, 3)
            analysis_status = "error"
            first_token_ms = $null
            chat_stream_total_ms = $null
            chat_status = "skipped"
            error = if ($analysisError) { $analysisError } else { "analysis did not complete" }
        }
        continue
    }

    try {
        $sessionResp = Invoke-RestMethod -Method Post -Uri "$base/chat/sessions" -Headers $headers -Body (@{ repo_id = $repoId } | ConvertTo-Json)
    }
    catch {
        if (Test-IsUnauthorized -ErrorRecord $_) {
            throw "Access token expired or unauthorized before chat benchmark. Refresh token and rerun."
        }
        throw
    }
    $sessionId = [string]$sessionResp.session_id
    $chatBody = @{
        content = $ChatPrompt
        top_k = 5
    } | ConvertTo-Json

    $chat = Measure-ChatSse -Url "$base/chat/sessions/$sessionId/message" -AccessToken $AccessToken -BodyJson $chatBody

    $rows += [pscustomobject]@{
        run_index = $i
        repo_id = $repoId
        job_id = $jobId
        analysis_duration_sec = [math]::Round($analysisSw.Elapsed.TotalSeconds, 3)
        analysis_status = "done"
        first_token_ms = $chat.first_delta_ms
        chat_stream_total_ms = $chat.stream_total_ms
        chat_status = if ($chat.done_payload) { "done" } else { "unknown" }
        error = $null
    }
}

$analysisDone = @($rows | Where-Object { $_.analysis_status -eq "done" } | ForEach-Object { [double]$_.analysis_duration_sec })
$firstToken = @($rows | Where-Object { $_.first_token_ms -ne $null } | ForEach-Object { [double]$_.first_token_ms })

$summary = [ordered]@{
    run_id = $runId
    created_at = (Get-Date).ToString("o")
    runs = $Runs
    repo_url = $RepoUrl
    sla_targets = @{
        analysis_under_seconds = 180
        chat_first_token_under_ms = 1000
    }
    metrics = @{
        analysis_p95_sec = Get-Percentile -Values $analysisDone -Percentile 95
        analysis_p50_sec = Get-Percentile -Values $analysisDone -Percentile 50
        first_token_p95_ms = Get-Percentile -Values $firstToken -Percentile 95
        first_token_p50_ms = Get-Percentile -Values $firstToken -Percentile 50
    }
    rows = $rows
}

$jsonPath = Join-Path $outDir "sla-report.json"
$csvPath = Join-Path $outDir "sla-runs.csv"

$summary | ConvertTo-Json -Depth 8 | Set-Content $jsonPath
$rows | Export-Csv -NoTypeInformation -Path $csvPath

Write-Host "SLA benchmark complete."
Write-Host "JSON: $jsonPath"
Write-Host "CSV:  $csvPath"
Write-Host ("analysis_p95_sec={0}" -f $summary.metrics.analysis_p95_sec)
Write-Host ("first_token_p95_ms={0}" -f $summary.metrics.first_token_p95_ms)
