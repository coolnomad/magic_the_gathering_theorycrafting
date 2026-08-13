# UserPromptSubmit hook: append the user's prompt to CONVERSATION_LOG.md (append-only).
# Reads the hook payload (JSON) from stdin. Never blocks the session: all errors are swallowed.
$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $data = $raw | ConvertFrom-Json
    $prompt = [string]$data.prompt
    if ([string]::IsNullOrWhiteSpace($prompt)) { exit 0 }

    # Log path: env override (for testing) else <repo root>/CONVERSATION_LOG.md, resolved from this script's location.
    $log = $env:CLAUDE_CONV_LOG
    if ([string]::IsNullOrWhiteSpace($log)) {
        $log = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\CONVERSATION_LOG.md'))
    }

    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $entry = "`r`n### [$ts] USER`r`n$prompt`r`n"
    [System.IO.File]::AppendAllText($log, $entry, (New-Object System.Text.UTF8Encoding($false)))
} catch { }
exit 0
