param([ValidateRange(1,65535)][int]$Port = 5000, [switch]$ProcessPending)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the project virtual environment first.' }
$runtimeArgs = @((Join-Path $projectRoot 'tools\local_runtime.py'), 'start', '--port', "$Port")
if ($ProcessPending) { $runtimeArgs += '--process-pending' }
Push-Location $projectRoot
try { & $pythonPath @runtimeArgs; $result = $LASTEXITCODE } finally { Pop-Location }
exit $result
