param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$SignalPath = "docs/review_events/review_ready.json",
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"

Write-Host "Waiting for review signal for $Commit"

while ($true) {
    if (Test-Path $SignalPath) {
        $raw = Get-Content -Raw -Path $SignalPath
        $signal = $raw | ConvertFrom-Json
        if ($signal.commit -eq $Commit) {
            Write-Host "Review ready: verdict=$($signal.verdict), doc=$($signal.review_document)"
            if ($signal.verdict -eq "accepted" -and $signal.phase_may_proceed -eq $true) {
                exit 0
            }
            if ($signal.verdict -eq "accepted_with_nonblocking_followup" -and $signal.phase_may_proceed -eq $true) {
                exit 0
            }
            exit 2
        }
    }
    Start-Sleep -Seconds $IntervalSeconds
}
