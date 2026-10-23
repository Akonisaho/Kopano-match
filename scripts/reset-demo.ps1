<#
  Put the demo back to its starting point in about a minute, so you can practise and retake.

    .\scripts\reset-demo.ps1                          # practice: emails stay in the log, nothing is sent
    .\scripts\reset-demo.ps1 -Email you@gmail.com     # practice with your own address on the accounts
    .\scripts\reset-demo.ps1 -RealEmail -Email you@yourdomain.co.za   # recording: real Brevo emails to YOU
    .\scripts\reset-demo.ps1 -Public                  # also give the demo a public https link (see below)

  It uses its own database (kopano_test), so it never touches the one the tests use. It serves the fast
  production build on port 5173 (add -Dev to keep the dev server). Needs Docker's database up and
  Python on the path.

  -Public opens a temporary public link to THIS computer through a Cloudflare quick tunnel. It installs
  Cloudflare's own tool with winget the first time, if it is missing. While it runs, anyone with the
  link can use the demo, so it uses fresh random secrets and a random admin password (printed at the
  end) instead of the ones in the repository. The link stops working when you close the window or the
  computer sleeps. Use -NoTunnel with -Public to check the secure setup without opening a link.
#>
param(
    [string]$Email = "demo@kopano-test.com",
    [switch]$RealEmail,
    [string]$Db = "kopano_test",
    [switch]$Dev,
    [switch]$LiveAI,
    [switch]$Public,
    [switch]$NoTunnel
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
Set-Location $backend

function Step($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function RandomToken($bytes) {
    $b = New-Object byte[] $bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ([BitConverter]::ToString($b) -replace '-', '').ToLower()
}
function StopPort($port) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

if ($RealEmail -and $Email -like "*kopano-test.com") {
    throw "Use -Email with an address you own when sending real email, so no stranger receives a message."
}

$adminPassword = "Another-Strong-Pass-9!"
$env:DATABASE_URL = "postgresql+psycopg2://kopano_app:kopano_app_dev@localhost:55432/$Db"
$env:ADMIN_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:55432/$Db"
$env:ADMIN_EMAIL = "reviewer@kopano-test.com"
if (-not $RealEmail) { $env:EMAIL_PROVIDER = "log" }
# Local mode reads documents and compares text on this computer: instant, offline, nothing leaves it.
# Add -LiveAI to use Gemini (needs the key in backend/.env and a network).
if (-not $LiveAI) { $env:LLM_PROVIDER = "local" }
if ($Public) {
    # A public link must not use secrets that are written down in the repository
    $env:JWT_SECRET = RandomToken 48
    $adminPassword = "Adm-" + (RandomToken 8) + "-Xz9!"
}
$env:ADMIN_PASSWORD = $adminPassword

Step "Stop the API and the web app if they are running"
StopPort 8000
StopPort 5173
Start-Sleep -Seconds 2

function BuildAndServeWeb {
    Push-Location $frontend
    npm run build | Out-Null
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "The web build failed." }
    Start-Process -WindowStyle Hidden -FilePath npm.cmd -ArgumentList "run", "preview", "--", "--port", "5173", "--strictPort"
    Pop-Location
    for ($i = 0; $i -lt 20; $i++) {
        try { Invoke-WebRequest http://localhost:5173 -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 }
    }
}

$link = $null
if ($Public -and -not $NoTunnel) {
    Step "Serve the production build, then open the public link"
    BuildAndServeWeb
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        Write-Host "    Installing Cloudflare's tunnel tool (winget). This happens once." -ForegroundColor Yellow
        winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements | Out-Null
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        throw "cloudflared is not available. Install it with:  winget install --id Cloudflare.cloudflared  then run this again."
    }
    $log = Join-Path $env:TEMP "kopano-tunnel.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    Start-Process -WindowStyle Hidden -FilePath cloudflared -ArgumentList "tunnel", "--url", "http://localhost:5173", "--no-autoupdate" -RedirectStandardError $log
    for ($i = 0; $i -lt 45 -and -not $link; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $link = $m.Matches[0].Value }
        }
    }
    if (-not $link) { throw "The public link did not come up. Read $log" }
    # Passport links and QR codes must point at the public address, not at localhost
    $env:APP_URL = $link
}

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

if (-not $Dev -and -not ($Public -and -not $NoTunnel)) {
    Step "Serve the fast production build"
    BuildAndServeWeb
}

Step "Create the sample certificates"
python scripts/make_demo_documents.py "Isizwe Civil Works" | Out-Null
$docs = Join-Path $root "demo-documents\Isizwe_Civil_Works"

Write-Host ""
Write-Host "Ready. API process $($api.Id)." -ForegroundColor Green
if ($link) { Write-Host "  PUBLIC LINK: $link" -ForegroundColor Green } else { Write-Host "  Open http://localhost:5173" -ForegroundColor Green }
Write-Host "  Business: $($Email -replace '@', '+isizwe@')   Buyer: $($Email -replace '@', '+buyer@')   Support: $($Email -replace '@', '+support@')   Password: Demo-Password-1!"
Write-Host "  Admin (YES dashboard): reviewer@kopano-test.com   Password: $adminPassword"
Write-Host "  Upload COID.pdf then CIDB.pdf from: $docs   (no date to type: it is read from the file)"
if ($link) {
    Write-Host ""
    Write-Host "  Keep this computer awake and this window open. Anyone with the link can use the demo." -ForegroundColor Yellow
    Write-Host "  Open the PUBLIC LINK (not localhost) when you demo, so the passport QR code works on a phone." -ForegroundColor Yellow
}
Start-Process explorer.exe $docs
Start-Process $(if ($link) { $link } else { "http://localhost:5173" })
