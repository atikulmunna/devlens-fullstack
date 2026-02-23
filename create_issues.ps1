param(
    [string]$BatchFile = "docs/planning/GitHub_Issues_Batch.md",
    [string]$ChecklistFile = "docs/planning/Implementation_Checklist.md",
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

if (-not (Test-Path -LiteralPath $BatchFile) -and -not (Test-Path -LiteralPath $ChecklistFile)) {
    throw "Neither batch file nor checklist file found. Looked for: $BatchFile and $ChecklistFile"
}

if (-not (Test-CommandExists "gh")) {
    throw "GitHub CLI (gh) is not installed or not in PATH."
}

$authStatus = gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run: gh auth login"
}

function Parse-BatchContent {
    param([string]$Content)
    $pattern = [regex]'(?ms)^## Issue:\s+\[(?<id>DEV-\d+)\]\s+(?<issueName>.+?)\r?\n\r?\n\*\*Title\*\*\r?\n(?<title>.+?)\r?\n\r?\n\*\*Body Template\*\*\r?\n```markdown\r?\n(?<body>.*?)\r?\n```\r?\n'
    return $pattern.Matches($Content)
}

function Build-IssueBlocksFromChecklist {
    param([string]$Path)
    $lines = Get-Content -LiteralPath $Path
    $items = New-Object System.Collections.Generic.List[object]

    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match '^### (DEV-\d+) \(`(P\d)`\) (.+)$') {
            $id = $Matches[1]
            $priority = $Matches[2]
            $name = $Matches[3]
            $scope = ''
            $tasks = New-Object System.Collections.Generic.List[string]
            $acceptance = New-Object System.Collections.Generic.List[string]
            $entryCriteria = New-Object System.Collections.Generic.List[string]
            $deps = 'None'

            for ($j = $i + 1; $j -lt $lines.Length; $j++) {
                $line = $lines[$j]
                if ($line -match '^### DEV-') { break }
                if ($line -match '^- Scope: (.+)$') { $scope = $Matches[1] }
                if ($line -match '^- Dependencies: (.+)$') { $deps = $Matches[1] }

                if ($line -eq '- Tasks:') {
                    for ($k = $j + 1; $k -lt $lines.Length; $k++) {
                        $t = $lines[$k]
                        if ($t -match '^- Acceptance criteria:' -or $t -match '^- Dependencies:' -or $t -match '^- Entry criteria:' -or $t -match '^### DEV-') { break }
                        if ($t -match '^- \[ \] (.+)$') { $tasks.Add($Matches[1]) }
                    }
                }
                if ($line -eq '- Acceptance criteria:') {
                    for ($k = $j + 1; $k -lt $lines.Length; $k++) {
                        $t = $lines[$k]
                        if ($t -match '^- Dependencies:' -or $t -match '^### DEV-' -or $t -match '^## ') { break }
                        if ($t -match '^- \[ \] (.+)$') { $acceptance.Add($Matches[1]) }
                    }
                }
                if ($line -eq '- Entry criteria:') {
                    for ($k = $j + 1; $k -lt $lines.Length; $k++) {
                        $t = $lines[$k]
                        if ($t -match '^### DEV-' -or $t -match '^## ') { break }
                        if ($t -match '^- \[ \] (.+)$') { $entryCriteria.Add($Matches[1]) }
                    }
                }
            }

            $bodyLines = New-Object System.Collections.Generic.List[string]
            $bodyLines.Add('## Summary')
            $bodyLines.Add($scope)
            $bodyLines.Add('')
            $bodyLines.Add('## Priority')
            $bodyLines.Add($priority)
            $bodyLines.Add('')
            $bodyLines.Add('## Tasks')
            if ($tasks.Count -eq 0) { $bodyLines.Add('- [ ] Define implementation tasks') }
            foreach ($task in $tasks) { $bodyLines.Add('- [ ] ' + $task) }
            if ($entryCriteria.Count -gt 0) {
                $bodyLines.Add('')
                $bodyLines.Add('## Entry Criteria')
                foreach ($entry in $entryCriteria) { $bodyLines.Add('- [ ] ' + $entry) }
            }
            $bodyLines.Add('')
            $bodyLines.Add('## Acceptance Criteria')
            if ($acceptance.Count -eq 0) { $bodyLines.Add('- [ ] Meets agreed requirements') }
            foreach ($criterion in $acceptance) { $bodyLines.Add('- [ ] ' + $criterion) }
            $bodyLines.Add('')
            $bodyLines.Add('## Dependencies')
            $bodyLines.Add('- ' + $deps)
            $bodyLines.Add('')
            $bodyLines.Add('## Labels')
            $bodyLines.Add('- ' + $priority)
            $bodyLines.Add('- ' + $id)

            $items.Add([PSCustomObject]@{
                id    = $id
                title = "[$id][$priority] $name"
                body  = ($bodyLines -join "`n")
            })
        }
    }

    return $items
}

$issueBlocks = @()
if (Test-Path -LiteralPath $BatchFile) {
    $content = Get-Content -LiteralPath $BatchFile -Raw
    $issueBlocks = Parse-BatchContent -Content $content
}
else {
    $issueBlocks = Build-IssueBlocksFromChecklist -Path $ChecklistFile
}

if ($issueBlocks.Count -eq 0) {
    throw "No issue blocks found."
}

Write-Host "Found $($issueBlocks.Count) issues."

$created = 0
$skipped = 0
$failed = 0

foreach ($m in $issueBlocks) {
    if ($m -is [System.Text.RegularExpressions.Match]) {
        $id = $m.Groups["id"].Value.Trim()
        $title = $m.Groups["title"].Value.Trim()
        $body = $m.Groups["body"].Value.Trim()
    }
    else {
        $id = $m.id.Trim()
        $title = $m.title.Trim()
        $body = $m.body.Trim()
    }

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
