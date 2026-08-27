# start.ps1
# Launches the full stack: FastAPI backend + React frontend (Windows / PowerShell)
#
# Usage:  powershell -ExecutionPolicy Bypass -File start.ps1
# Backend  -> http://127.0.0.1:8000
# Frontend -> http://localhost:5173

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Write-Host "==> Starting FastAPI backend on :8000" -ForegroundColor Cyan
$be = Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","app.main:app","--port","8000" `
    -WorkingDirectory (Join-Path $root "backend") -PassThru -WindowStyle Hidden

Write-Host "==> Starting React frontend on :5173" -ForegroundColor Cyan
$fe = Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" `
    -WorkingDirectory (Join-Path $root "frontend\app") -PassThru -WindowStyle Hidden

Write-Host ""
Write-Host "Open the dashboard at:  http://localhost:5173" -ForegroundColor Green
Write-Host "API docs at:            http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop. (Close the spawned windows to fully stop servers.)"

try { Read-Host "Press Enter to stop servers" } finally { }
Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $fe.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
Write-Host "Stopped."
