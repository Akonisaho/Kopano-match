<#
  Start everything with one command. From the repository root:

    .\scripts\dev.ps1            # planted demo data (for tests and quick looks)
    .\scripts\dev.ps1 -Empty     # clean start: one admin account, build your own data
    .\scripts\dev.ps1 -DryRun    # print what it would do

  Needs Docker Desktop, Python 3.12 and Node 20+. Opens the API and the web app in two windows.
#>
param([switch]$Empty, [switch]$DryRun)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

function Step($text, [scriptblock]$action) {
    Write-Host "==> $text" -ForegroundColor Cyan
    if ($DryRun) { Write-Host "    [dry run] skipped" -ForegroundColor DarkGray } else { & $action }
}

Step "Start the database (Docker)" {
    Set-Location $root
    docker compose up -d | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        docker compose exec -T postgres pg_isready -U postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw "The database did not become ready. Is Docker Desktop running?"
}

Step "Set up the Python environment" {
    Set-Location $backend
    if (-not (Test-Path $py)) { python -m venv .venv }
    & $py -m pip install -q -r requirements.txt -r requirements-dev.txt
}

Step ("Create the database contents (" + $(if ($Empty) { "empty, admin only" } else { "planted demo data" }) + ")") {
    Set-Location $backend
    if ($Empty -and -not $env:ADMIN_PASSWORD) {
        Write-Host "    Tip: set `$env:ADMIN_EMAIL and `$env:ADMIN_PASSWORD first to choose your own admin login." -ForegroundColor Yellow
    }
    if ($Empty) { & $py seed.py --empty } else { & $py seed.py }
}

Step "Install the web app packages" {
    Set-Location $frontend
    if (-not (Test-Path "node_modules")) { npm install }
}

Step "Open the API and the web app" {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev"
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:5173"
}

Write-Host ""
Write-Host "Running: web app http://localhost:5173, API http://127.0.0.1:8000/docs" -ForegroundColor Green
if ($Empty) { Write-Host "Next: python scripts/build_demo.py --email you@gmail.com   (from backend/, optional)" -ForegroundColor Green }
