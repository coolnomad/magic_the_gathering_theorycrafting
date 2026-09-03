param(
    [string]$Ref = "origin/main",
    [int]$IntervalSeconds = 10,
    [string]$StatePath = "docs/review_events/new_commit.json"
)

$ErrorActionPreference = "Stop"

function Get-Commit($refName) {
    $sha = git rev-parse $refName 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve ref '$refName'"
    }
    return $sha.Trim()
}

New-Item -ItemType Directory -Force -Path (Split-Path $StatePath) | Out-Null

$last = Get-Commit $Ref
Write-Host "Watching $Ref at $last"

while ($true) {
    Start-Sleep -Seconds $IntervalSeconds
    $current = Get-Commit $Ref
    if ($current -ne $last) {
        $payload = [ordered]@{
            event = "new_commit"
            schema_version = 1
            ref = $Ref
            previous_commit = $last
            commit = $current
            detected_at = (Get-Date).ToString("o")
        }
        $payload | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -Path $StatePath
        Write-Host "New commit on ${Ref}: $current"
        $last = $current
    }
}
