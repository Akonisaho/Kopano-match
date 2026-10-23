<#
  Put the demo back to its starting point in about a minute, so you can practise and retake.

    .\scripts\reset-demo.ps1                          # practice: emails stay in the log, nothing is sent
    .\scripts\reset-demo.ps1 -Email you@gmail.com     # practice with your own address on the accounts
    .\scripts\reset-demo.ps1 -RealEmail -Email you@yourdomain.co.za   # recording: real Brevo emails to YOU

  It uses its own database (kopano_test), so it never touches the one the tests use. It serves the fast
  production build on port 5173 (add -Dev to keep the dev server). Needs Docker's database up and
  Python on the path.
#>
param(
    [string]$Email = "demo@kopano-test.com",
    [switch]$RealEmail,
    [string]$Db = "kopano_test",
    [switch]$Dev,
    [switch]$LiveAI
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
Set-Location $backend

function Step($t) { Write-Host "==> $t" -ForegroundColor Cyan }

if ($RealEmail -and $Email -like "*kopano-test.com") {
    throw "Use -Email with an address you own when sending real email, so no stranger receives a message."
}

$env:DATABASE_URL = "postgresql+psycopg2://kopano_app:kopano_app_dev@localhost:55432/$Db"
$env:ADMIN_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:55432/$Db"
$env:ADMIN_EMAIL = "reviewer@kopano-test.com"
$env:ADMIN_PASSWORD = "Another-Strong-Pass-9!"
if (-not $RealEmail) { $env:EMAIL_PROVIDER = "log" }
# Local mode reads documents and compares text on this computer: instant, offline, nothing leaves it.
# Add -LiveAI to use Gemini (needs the key in backend/.env and a network).
if (-not $LiveAI) { $env:LLM_PROVIDER = "local" }

Step "Stop the API if it is running"
Get-NetTCPConnection -State Listen -LocalPort 8000 -LocalAddress 127.0.0.1 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Step "Create a clean database"
python seed.py --empty | Out-Null

Step "Start the API"
$api = Start-Process -WindowStyle Hidden -PassThru -FilePath python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
for ($i = 0; $i -lt 30; $i++) {
    try { if ((Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2).status -eq "ok") { break } } catch { Start-Sleep -Seconds 1 }
}

Step "Build the demo businesses, buyers, awards and feedback"
python scripts/build_demo.py --email $Email
if ($LASTEXITCODE -ne 0) { throw "The demo build failed. Read the message above." }

if (-not $Dev) {
    Step "Serve the fast production build"
    Push-Location (Join-Path $root "frontend")
    npm run build | Out-Null
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "The web build failed." }
    Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Start-Process -WindowStyle Hidden -FilePath npm.cmd -ArgumentList "run", "preview", "--", "--port", "5173", "--strictPort"
    Pop-Location
    for ($i = 0; $i -lt 20; $i++) {
        try { Invoke-WebRequest http://localhost:5173 -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 }
    }
}

Step "Create the sample certificates"
python scripts/make_demo_documents.py "Isizwe Civil Works" | Out-Null
$docs = Join-Path $root "demo-documents\Isizwe_Civil_Works"

Write-Host ""
Write-Host "Ready. API process $($api.Id). Open http://localhost:5173" -ForegroundColor Green
Write-Host "  Business: $($Email -replace '@', '+isizwe@')   Buyer: $($Email -replace '@', '+buyer@')   Password: Demo-Password-1!"
Write-Host "  Upload COID.pdf then CIDB.pdf from: $docs   (no date to type: it is read from the file)"
Start-Process explorer.exe $docs
Start-Process "http://localhost:5173"
