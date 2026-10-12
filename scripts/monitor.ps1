# Runs inside Windows Sandbox only. No host write-back folder is configured.
$ErrorActionPreference = 'Stop'
$taskRoot = Join-Path $env:USERPROFILE 'Desktop\StrataSession'
New-Item -ItemType Directory -Path $taskRoot -Force | Out-Null
Copy-Item -LiteralPath 'C:\StrataInput\sample.exe' -Destination (Join-Path $taskRoot 'sample.exe')
$taskHash = (Get-FileHash -LiteralPath (Join-Path $taskRoot 'sample.exe') -Algorithm SHA256).Hash
$taskLog = Join-Path $taskRoot 'execution.jsonl'
@{time=(Get-Date).ToString('o');event='monitor-start';sha256=$taskHash} | ConvertTo-Json -Compress | Set-Content -LiteralPath $taskLog
# WMI event subscription precedes sample launch. Evidence stays inside the VM.
Register-CimIndicationEvent -ClassName Win32_ProcessStartTrace -SourceIdentifier 'StrataProcessStart' | Out-Null
try {
    $taskProcess = Start-Process -FilePath (Join-Path $taskRoot 'sample.exe') -WorkingDirectory $taskRoot -PassThru
    @{time=(Get-Date).ToString('o');event='sample-start';pid=$taskProcess.Id} | ConvertTo-Json -Compress | Add-Content -LiteralPath $taskLog
    $taskUntil = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $taskUntil) {
        $taskEvent = Wait-Event -SourceIdentifier 'StrataProcessStart' -Timeout 1
        if ($taskEvent) {
            $taskInfo = $taskEvent.SourceEventArgs.NewEvent
            @{time=(Get-Date).ToString('o');event='process-start';name=$taskInfo.ProcessName;pid=$taskInfo.ProcessID;parent=$taskInfo.ParentProcessID} | ConvertTo-Json -Compress | Add-Content -LiteralPath $taskLog
            Remove-Event -EventIdentifier $taskEvent.EventIdentifier
        }
    }
    @{time=(Get-Date).ToString('o');event='observation-end';note='60 seconds; not a full filesystem or registry trace'} | ConvertTo-Json -Compress | Add-Content -LiteralPath $taskLog
} catch {
    @{time=(Get-Date).ToString('o');event='error';message=$_.Exception.Message} | ConvertTo-Json -Compress | Add-Content -LiteralPath $taskLog
} finally {
    Unregister-Event -SourceIdentifier 'StrataProcessStart' -ErrorAction SilentlyContinue
}
Start-Process -FilePath 'notepad.exe' -ArgumentList $taskLog
