param(
    [string]$DocPath = "docs/planning/Execution_Plan_Issues.md",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required but not found in PATH."
}

if (-not (Test-Path $DocPath)) {
    throw "Issue document not found: $DocPath"
}

$raw = Get-Content -Path $DocPath -Raw

$pattern = @'
## Issue\s+\d+\s+\*\*Title:\*\*\s+`(?<title>[^`]+)`\s+\*\*Body:\*\*\s+```md(?<body>[\s\S]*?)```\s+\*\*Labels:\*\*\s+(?<labels>[^\r\n]+)
'@

$matches = [regex]::Matches($raw, $pattern)
if ($matches.Count -eq 0) {
    throw "No issue blocks were parsed from $DocPath. Validate the document format."
}

Write-Host "Parsed $($matches.Count) issue definitions from $DocPath"

$created = @()

function Ensure-Label {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )
    $exists = & gh label list --limit 200 --search $Name --json name | ConvertFrom-Json
    $match = $exists | Where-Object { $_.name -eq $Name } | Select-Object -First 1
    if (-not $match) {
        # Default neutral color; description can be edited later.
        & gh label create $Name --color "A0AEC0" --description "Auto-created by issue batch script" | Out-Null
    }
}

foreach ($m in $matches) {
    $title = $m.Groups["title"].Value.Trim()
    $body = $m.Groups["body"].Value.Trim()
    $labelsRaw = $m.Groups["labels"].Value.Trim()
    $labels = @()
    if ($labelsRaw) {
        $labels = $labelsRaw.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    }

    if ($DryRun) {
        Write-Host "DRY RUN: $title"
        continue
    }

    foreach ($label in $labels) {
        Ensure-Label -Name $label
    }

    $tmp = New-TemporaryFile
    try {
        Set-Content -Path $tmp.FullName -Value $body -NoNewline
        $args = @("issue", "create", "--title", $title, "--body-file", $tmp.FullName)
        foreach ($label in $labels) {
            $args += @("--label", $label)
        }
        $url = & gh @args
        if ($url) {
            $created += $url.Trim()
            Write-Host "Created: $url"
        } else {
            Write-Warning "Issue creation returned empty output for title: $title"
        }
    }
    finally {
        Remove-Item -Path $tmp.FullName -ErrorAction SilentlyContinue
    }
}

if (-not $DryRun) {
    Write-Host ""
    Write-Host "Created $($created.Count) issues:"
    $created | ForEach-Object { Write-Host " - $_" }
}
