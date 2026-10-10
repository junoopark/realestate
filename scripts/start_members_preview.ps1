param([switch]$InstallDependencies)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & python -m venv (Join-Path $repoPath '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    $InstallDependencies = $true
}
if ($InstallDependencies) {
    & $venvPython -m pip install -r (Join-Path $repoPath 'backend\requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
foreach ($previewPort in @(8000, 5500)) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $previewPort -ErrorAction SilentlyContinue
    if ($busy) { throw "Port $previewPort is already in use. Stop that local server before running this script." }
}
$logPath = Join-Path $repoPath 'tmp\members-preview'
New-Item -ItemType Directory -Path $logPath -Force | Out-Null
$apiProcess = Start-Process -FilePath $venvPython -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory (Join-Path $repoPath 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath 'api.log') -RedirectStandardError (Join-Path $logPath 'api-error.log')
try {
    $webProcess = Start-Process -FilePath $venvPython -ArgumentList @('-m', 'http.server', '5500', '--bind', '127.0.0.1') -WorkingDirectory (Join-Path $repoPath 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath 'web.log') -RedirectStandardError (Join-Path $logPath 'web-error.log')
} catch {
    Stop-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue
    throw
}
Write-Output 'Popular:   http://127.0.0.1:5500/popular.html'
Write-Output 'Downloads: http://127.0.0.1:5500/downloads.html'
Write-Output "Logs: $logPath"
Write-Output "Stop these preview servers: Stop-Process -Id $($apiProcess.Id),$($webProcess.Id)"
Write-Output 'Check setup: python scripts/check_members.py'
