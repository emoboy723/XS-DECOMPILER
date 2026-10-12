$ErrorActionPreference = 'Stop'
$taskEngine = Join-Path $env:GHIDRA_HOME 'support\analyzeHeadless.bat'
& $taskEngine $env:STRATA_PROJECT 'StrataAnalysis' '-import' $env:STRATA_SAMPLE '-scriptPath' $PSScriptRoot '-postScript' 'StrataExport.java' $env:STRATA_SOURCE '-deleteProject'
exit $LASTEXITCODE
