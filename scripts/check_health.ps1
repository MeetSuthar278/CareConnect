$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try { & (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $projectRoot 'tools\local_runtime.py') health; $result = $LASTEXITCODE } finally { Pop-Location }
exit $result
