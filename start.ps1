# Incident Response Agent — one-click startup for Windows
# Run from the project root: .\start.ps1
# Requires: Python venv at .\.venv\  and  Node at frontend\node_modules\

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host ""
Write-Host "  Incident Response Agent" -ForegroundColor Cyan
Write-Host "  ========================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Backend ───────────────────────────────────────────────────────
Write-Host "  Starting backend  (http://localhost:8000) ..." -ForegroundColor Yellow
$backend = Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command",
        "Set-Location '$projectRoot'; .\.venv\Scripts\Activate.ps1; uvicorn backend.api.main:api --reload --port 8000" `
    -PassThru

Start-Sleep -Seconds 2   # give uvicorn a moment before Vite opens

# ── 2. Frontend ──────────────────────────────────────────────────────
Write-Host "  Starting frontend (http://localhost:5173) ..." -ForegroundColor Yellow
$frontend = Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command",
        "Set-Location '$projectRoot\frontend'; npm run dev" `
    -PassThru

Write-Host ""
Write-Host "  Both servers are starting. Open http://localhost:5173 in your browser." -ForegroundColor Green
Write-Host "  Close the two terminal windows to stop." -ForegroundColor DarkGray
Write-Host ""
