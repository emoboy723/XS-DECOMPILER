# This script is intended for a disposable Windows guest, not the host.
$ErrorActionPreference = 'Stop'
$taskSystem = Get-CimInstance Win32_ComputerSystem
if (($taskSystem.Model + ' ' + $taskSystem.Manufacturer) -notmatch 'Virtual|VMware|VirtualBox|QEMU|KVM|Xen|Parallels') {
    throw 'No se detecta una VM compatible. No se abrirá la muestra.'
}
if (Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object Status -eq 'Up') {
    throw 'Desactiva los adaptadores de red de esta VM antes de continuar.'
}
$taskExpected = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'sha256.txt') -Raw).Trim()
$taskSample = Join-Path $PSScriptRoot 'sample.exe'
$taskActual = (Get-FileHash -LiteralPath $taskSample -Algorithm SHA256).Hash
if ($taskActual -ne $taskExpected) { throw 'El SHA-256 no coincide.' }
Write-Host "Muestra SHA-256: $taskActual"
$taskConfirmation = Read-Host 'Confirma VM desechable, snapshot limpio, integraciones desactivadas y ausencia de credenciales. Escribe EJECUTAR'
if ($taskConfirmation -cne 'EJECUTAR') { throw 'Ejecución cancelada.' }
$taskLog = Join-Path $PSScriptRoot 'execution.jsonl'
@{time=(Get-Date).ToString('o');event='monitor-start';sha256=$taskActual} | ConvertTo-Json -Compress | Set-Content -LiteralPath $taskLog
Register-CimIndicationEvent -ClassName Win32_ProcessStartTrace -SourceIdentifier 'StrataProcessStart' | Out-Null
try {
    $taskProcess = Start-Process -FilePath $taskSample -WorkingDirectory $PSScriptRoot -PassThru
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
} catch {
    @{time=(Get-Date).ToString('o');event='error';message=$_.Exception.Message} | ConvertTo-Json -Compress | Add-Content -LiteralPath $taskLog
} finally { Unregister-Event -SourceIdentifier 'StrataProcessStart' -ErrorAction SilentlyContinue }
Start-Process -FilePath 'notepad.exe' -ArgumentList $taskLog
