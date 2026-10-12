# Development only. The distributed Strata.exe does not require Python installed.
$ErrorActionPreference = 'Stop'
$taskSource = Join-Path $PSScriptRoot 'src\desktop.py'
$taskIcon = Join-Path $PSScriptRoot 'Strata.ico'
$taskSources = Join-Path $PSScriptRoot 'src'
$taskWork = Join-Path $PSScriptRoot 'build'
$taskDistribution = Join-Path $PSScriptRoot 'compiled'
$taskDependencies = Join-Path $taskWork 'dependencies'
python -m pip install --target $taskDependencies tree-sitter==0.26.0 tree-sitter-javascript==0.25.0
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de parsers.' }
python -m PyInstaller --noconfirm --windowed --onedir --name Strata --icon $taskIcon --distpath $taskDistribution --workpath $taskWork --specpath $taskWork --paths $taskSources --paths $taskDependencies --collect-all tree_sitter --collect-all tree_sitter_javascript $taskSource
if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación.' }
Write-Host 'El EXE recompilado y _internal están en compiled\Strata. Copia ambos a esta carpeta conservando tools, runtime y scripts.'
