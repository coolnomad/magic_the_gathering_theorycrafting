# Stop hook: append the assistant's response for the just-finished turn to CONVERSATION_LOG.md (append-only).
# Reads the hook payload (JSON) from stdin, opens the session transcript, extracts the text of the
# assistant turn that followed the most recent real user prompt, and appends it.
# De-duplicates on the last assistant message's uuid so re-fires (resume/compact/clear) don't double-log.
# Never blocks the session: all errors are swallowed.
$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $data = $raw | ConvertFrom-Json
    $tp = [string]$data.transcript_path
    if ([string]::IsNullOrWhiteSpace($tp) -or -not (Test-Path -LiteralPath $tp)) { exit 0 }

    $log = $env:CLAUDE_CONV_LOG
    if ([string]::IsNullOrWhiteSpace($log)) {
        $log = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\CONVERSATION_LOG.md'))
    }
    $marker = Join-Path $PSScriptRoot '.last_assistant_uuid'

    # Parse the JSONL transcript into objects.
    $entries = New-Object System.Collections.Generic.List[object]
    foreach ($line in (Get-Content -LiteralPath $tp)) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            try { $entries.Add(($line | ConvertFrom-Json)) } catch { }
        }
    }
    if ($entries.Count -eq 0) { exit 0 }

    # Find the most recent genuine user prompt (type=user, and NOT a tool_result carrier).
    $lastUser = -1
    for ($i = 0; $i -lt $entries.Count; $i++) {
        $e = $entries[$i]
        if ($e.type -eq 'user' -and -not ($e.PSObject.Properties.Name -contains 'toolUseResult')) {
            $lastUser = $i
        }
    }

    # Collect assistant text blocks after that prompt; track the last assistant uuid for dedup.
    $texts = New-Object System.Collections.Generic.List[string]
    $lastUuid = $null
    for ($i = $lastUser + 1; $i -lt $entries.Count; $i++) {
        $e = $entries[$i]
        if ($e.type -eq 'assistant' -and $e.message -and $e.message.content) {
            foreach ($block in $e.message.content) {
                if ($block.type -eq 'text' -and -not [string]::IsNullOrWhiteSpace([string]$block.text)) {
                    $texts.Add([string]$block.text)
                    if ($e.PSObject.Properties.Name -contains 'uuid') { $lastUuid = [string]$e.uuid }
                }
            }
        }
    }
    if ($texts.Count -eq 0) { exit 0 }

    # Skip if we already logged this exact assistant turn.
    if ($lastUuid -and (Test-Path -LiteralPath $marker)) {
        $prev = (Get-Content -LiteralPath $marker -Raw).Trim()
        if ($prev -eq $lastUuid) { exit 0 }
    }

    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $body = ($texts -join "`r`n`r`n")
    $entry = "`r`n### [$ts] ASSISTANT`r`n$body`r`n"
    [System.IO.File]::AppendAllText($log, $entry, (New-Object System.Text.UTF8Encoding($false)))
    if ($lastUuid) {
        [System.IO.File]::WriteAllText($marker, $lastUuid, (New-Object System.Text.UTF8Encoding($false)))
    }
} catch { }
exit 0
