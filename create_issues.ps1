param(
    [string]$BatchFile = "docs/planning/GitHub_Issues_Batch.md",
    [switch]$DryRun,
    [switch]$AutoCreateLabels
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-Label {
    param([string]$Label)
    if (-not $Label) { return }
    try {
        gh label create $Label --force | Out-Null
    }
    catch {
        Write-Warning "Failed to create label '$Label': $($_.Exception.Message)"
    }
}

if (-not (Test-Path -LiteralPath $BatchFile)) {
    throw "Batch file not found: $BatchFile"
}

if (-not (Test-CommandExists "gh")) {
    throw "GitHub CLI (gh) is not installed or not in PATH."
}

$authStatus = gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run: gh auth login"
}

$content = Get-Content -LiteralPath $BatchFile -Raw

# Parse each issue block.
$pattern = [regex]'(?ms)^## Issue:\s+\[(?<id>DEV-\d+)\]\s+(?<issueName>.+?)\r?\n\r?\n\*\*Title\*\*\r?\n(?<title>.+?)\r?\n\r?\n\*\*Body Template\*\*\r?\n```markdown\r?\n(?<body>.*?)\r?\n```\r?\n'
$issueBlocks = $pattern.Matches($content)

if ($issueBlocks.Count -eq 0) {
    throw "No issue blocks found in $BatchFile"
}

Write-Host "Found $($issueBlocks.Count) issues in $BatchFile"

$created = 0
$skipped = 0
$failed = 0

foreach ($m in $issueBlocks) {
    $id = $m.Groups["id"].Value.Trim()
    $title = $m.Groups["title"].Value.Trim()
    $body = $m.Groups["body"].Value.Trim()

    # Parse labels from "## Labels" section in body template.
    $labels = @()
    $labelSection = [regex]::Match($body, '(?ms)^## Labels\r?\n(?<lines>.+?)$')
    if ($labelSection.Success) {
        $labelLines = $labelSection.Groups["lines"].Value -split '\r?\n'
        foreach ($line in $labelLines) {
            if ($line -match '^\s*-\s+(.+?)\s*$') {
                $labels += $Matches[1].Trim()
            }
        }
    }

    # Skip if issue with same title already exists.
    $existing = gh issue list --state all --search "`"$title`" in:title" --limit 100 --json title `
        | ConvertFrom-Json `
        | Where-Object { $_.title -eq $title }

    if ($existing) {
        Write-Host "Skipping $id (already exists): $title"
        $skipped++
        continue
    }

    if ($AutoCreateLabels) {
        foreach ($label in $labels) {
            Ensure-Label -Label $label
        }
    }

    if ($DryRun) {
        $labelText = if ($labels.Count -gt 0) { $labels -join ", " } else { "none" }
        Write-Host "[DRY RUN] Would create: $title | labels: $labelText"
        $created++
        continue
    }

    $tempFile = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -LiteralPath $tempFile -Value $body -NoNewline

        $args = @("issue", "create", "--title", $title, "--body-file", $tempFile)
        foreach ($label in $labels) {
            $args += @("--label", $label)
        }

        & gh @args | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "gh issue create failed with exit code $LASTEXITCODE"
        }

        Write-Host "Created ${id}: $title"
        $created++
    }
    catch {
        Write-Warning "Failed ${id}: $($_.Exception.Message)"
        $failed++
    }
    finally {
        Remove-Item -LiteralPath $tempFile -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "Summary"
Write-Host "Created: $created"
Write-Host "Skipped: $skipped"
Write-Host "Failed : $failed"

if ($failed -gt 0) {
    exit 1
}
