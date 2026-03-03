param(
    [Parameter(Mandatory = $true)]
    [string]$BaselineResultsPath,

    [Parameter(Mandatory = $true)]
    [string]$CandidateResultsPath,

    [Parameter(Mandatory = $true)]
    [string]$BaselineScorecardPath,

    [Parameter(Mandatory = $true)]
    [string]$CandidateScorecardPath,

    [string]$OutputPath = "docs/evaluation/DEV-045_Reranker_Delta_Report.md"
)

$ErrorActionPreference = "Stop"

function Assert-Exists {
    param([string]$PathValue)
    if (-not (Test-Path $PathValue)) {
        throw "File not found: $PathValue"
    }
}

function Read-Jsonl {
    param([string]$PathValue)
    $rows = @()
    foreach ($line in (Get-Content $PathValue)) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $rows += ($line | ConvertFrom-Json)
    }
    return $rows
}

function Avg {
    param([object[]]$Values)
    if (-not $Values -or $Values.Count -eq 0) {
        return 0.0
    }
    return [math]::Round((($Values | Measure-Object -Average).Average), 3)
}

function Compute-Latency {
    param([object[]]$Rows)
    $ok = @($Rows | Where-Object { $_.status -eq "ok" -and $_.latency_ms -ne $null })
    return @{
        avg_ms = Avg -Values ($ok | ForEach-Object { [double]$_.latency_ms })
        sample_size = $ok.Count
    }
}

function Build-ScoreIndex {
    param([object[]]$Rows)
    $map = @{}
    foreach ($row in $Rows) {
        $key = "$($row.repo_key)|$($row.question_id)"
        $map[$key] = $row
    }
    return $map
}

function Compute-ScoreMetrics {
    param(
        [object[]]$ScoreRows,
        [hashtable]$ResultIndex
    )
    $scored = @($ScoreRows | Where-Object { $_.question_id -and $_.repo_key })
    $relevanceAvg = Avg -Values ($scored | ForEach-Object { [double]$_.answer_relevance_0_3 })
    $citationCorrectnessAvg = Avg -Values ($scored | ForEach-Object { [double]$_.citation_correctness_0_3 })
    $totalAvg = Avg -Values ($scored | ForEach-Object { [double]$_.total_0_10 })

    $citedRows = 0
    $correctAndCited = 0
    foreach ($row in $scored) {
        $key = "$($row.repo_key)|$($row.question_id)"
        $result = $ResultIndex[$key]
        if ($null -eq $result) {
            continue
        }
        $hasCitation = -not [bool]$result.no_citation
        if ($hasCitation) {
            $citedRows++
            if ([double]$row.citation_correctness_0_3 -ge 2.0) {
                $correctAndCited++
            }
        }
    }

    $precision = if ($citedRows -gt 0) { [math]::Round($correctAndCited / $citedRows, 3) } else { 0.0 }
    $recall = if ($scored.Count -gt 0) { [math]::Round($correctAndCited / $scored.Count, 3) } else { 0.0 }
    return @{
        relevance_avg = $relevanceAvg
        citation_correctness_avg = $citationCorrectnessAvg
        total_avg = $totalAvg
        citation_precision = $precision
        citation_recall = $recall
        scored_rows = $scored.Count
    }
}

Assert-Exists -PathValue $BaselineResultsPath
Assert-Exists -PathValue $CandidateResultsPath
Assert-Exists -PathValue $BaselineScorecardPath
Assert-Exists -PathValue $CandidateScorecardPath

$baselineResults = Read-Jsonl -PathValue $BaselineResultsPath
$candidateResults = Read-Jsonl -PathValue $CandidateResultsPath
$baselineScores = Import-Csv $BaselineScorecardPath
$candidateScores = Import-Csv $CandidateScorecardPath

$baselineLatency = Compute-Latency -Rows $baselineResults
$candidateLatency = Compute-Latency -Rows $candidateResults
$baselineIndex = Build-ScoreIndex -Rows $baselineResults
$candidateIndex = Build-ScoreIndex -Rows $candidateResults
$baselineMetrics = Compute-ScoreMetrics -ScoreRows $baselineScores -ResultIndex $baselineIndex
$candidateMetrics = Compute-ScoreMetrics -ScoreRows $candidateScores -ResultIndex $candidateIndex

$lines = @(
    "# DEV-045 Reranker Golden-Set Evaluation Report",
    "",
    ("Generated: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")),
    "",
    "## Inputs",
    "- Baseline results: $BaselineResultsPath",
    "- Candidate results: $CandidateResultsPath",
    "- Baseline scorecard: $BaselineScorecardPath",
    "- Candidate scorecard: $CandidateScorecardPath",
    "",
    "## Metrics",
    "| Metric | Baseline | Candidate (reranker-on) | Delta (cand - base) |",
    "|---|---:|---:|---:|",
    "| Relevance avg (0-3) | $($baselineMetrics.relevance_avg) | $($candidateMetrics.relevance_avg) | $([math]::Round($candidateMetrics.relevance_avg - $baselineMetrics.relevance_avg, 3)) |",
    "| Citation correctness avg (0-3) | $($baselineMetrics.citation_correctness_avg) | $($candidateMetrics.citation_correctness_avg) | $([math]::Round($candidateMetrics.citation_correctness_avg - $baselineMetrics.citation_correctness_avg, 3)) |",
    "| Citation precision (proxy) | $($baselineMetrics.citation_precision) | $($candidateMetrics.citation_precision) | $([math]::Round($candidateMetrics.citation_precision - $baselineMetrics.citation_precision, 3)) |",
    "| Citation recall (proxy) | $($baselineMetrics.citation_recall) | $($candidateMetrics.citation_recall) | $([math]::Round($candidateMetrics.citation_recall - $baselineMetrics.citation_recall, 3)) |",
    "| Total avg (0-10) | $($baselineMetrics.total_avg) | $($candidateMetrics.total_avg) | $([math]::Round($candidateMetrics.total_avg - $baselineMetrics.total_avg, 3)) |",
    "| Avg latency (ms) | $($baselineLatency.avg_ms) | $($candidateLatency.avg_ms) | $([math]::Round($candidateLatency.avg_ms - $baselineLatency.avg_ms, 3)) |",
    "",
    "## Sample Sizes",
    "- Baseline scored rows: $($baselineMetrics.scored_rows)",
    "- Candidate scored rows: $($candidateMetrics.scored_rows)",
    "- Baseline latency rows: $($baselineLatency.sample_size)",
    "- Candidate latency rows: $($candidateLatency.sample_size)",
    "",
    "## Recommendation",
    "- Set based on thresholds: if total/relevance/citation metrics improve and latency impact is acceptable, enable reranker by default.",
    "- Record the final decision in this file before merging default-on config changes."
)

$parent = Split-Path -Parent $OutputPath
if ($parent -and -not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$lines -join "`n" | Set-Content -Path $OutputPath
Write-Host "Wrote report: $OutputPath"
