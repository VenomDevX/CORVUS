# Release smoke test: silently install the freshly built Corvus installer,
# launch it, and wait for the backend to log its start line. Run after
# `npm run dist`; used by CI and runnable locally (close Corvus first).
$ErrorActionPreference = "Stop"

$installer = Get-ChildItem -Path "dist-installer" -Filter "Corvus-Setup-*.exe" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $installer) { throw "No Corvus-Setup-*.exe in dist-installer/" }

$installDir = Join-Path $env:LOCALAPPDATA "Programs\Corvus"
$log = Join-Path $env:LOCALAPPDATA "Corvus\logs\corvus.log"
$startedAt = Get-Date

Write-Host "Installing $($installer.Name)..."
Start-Process -FilePath $installer.FullName -ArgumentList "/S" -Wait
$exe = Join-Path $installDir "Corvus.exe"
if (-not (Test-Path $exe)) { throw "Corvus.exe not found at $exe after install" }

Write-Host "Launching Corvus..."
$app = Start-Process -FilePath $exe -PassThru
try {
  $deadline = (Get-Date).AddSeconds(90)
  $ok = $false
  while ((Get-Date) -lt $deadline) {
    if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $startedAt -and
        (Select-String -Path $log -Pattern '"event": "corvus_start"' -SimpleMatch -Quiet)) {
      $ok = $true
      break
    }
    if ($app.HasExited) { throw "Corvus exited early with code $($app.ExitCode)" }
    Start-Sleep -Seconds 2
  }
  if (-not $ok) { throw "Backend never logged corvus_start within 90s" }
  Write-Host "Smoke test passed: app launched and backend started."
} finally {
  Stop-Process -Name "Corvus", "corvus-backend" -Force -ErrorAction SilentlyContinue
}
