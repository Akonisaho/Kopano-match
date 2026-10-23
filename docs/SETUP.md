# Setup: the shortest path

About 15 minutes the first time. Windows, PowerShell.

## 1. Install once

- Docker Desktop (running)
- Python 3.12
- Node 20 or newer
- Git

## 2. Get the code and start everything

```powershell
git clone https://github.com/Akonisaho/Kopano-match.git
cd Kopano-match
$env:ADMIN_EMAIL = "you@yourdomain.co.za"
$env:ADMIN_PASSWORD = "<a strong password, 12+ characters>"
.\scripts\dev.ps1 -Empty
```

That starts the database, installs what is needed, creates an empty system with **one admin
account**, and opens the API and the web app at http://localhost:5173. Use `.\scripts\dev.ps1`
without `-Empty` for planted sample data, and `-DryRun` to see what it would do.

## 3. Add the two optional keys

Without them everything still works: summaries use a built-in template and notices appear in the
bell. With them, summaries are AI-written and real emails are sent. Full steps are in
[KEYS_AND_EMAIL.md](KEYS_AND_EMAIL.md). In short:

```powershell
Copy-Item .env.example backend\.env      # then paste your keys into backend\.env
cd backend
python scripts/check_keys.py --send-test you@gmail.com
```

`check_keys.py` tells you exactly what to fix if anything is wrong.

## 4. Fill it with a realistic demo

One command builds a full cast through the real sign-up, upload and matching code:

```powershell
cd backend
python scripts/build_demo.py --email you@gmail.com
```

It creates a buyer, a funder, ten SMEs with uploaded sample certificates, three opportunities,
matches, a shortlist, applications, and two items waiting in the admin review queue. Accounts are
plus-addresses of your email (`you+buyer@gmail.com`, `you+thabo@gmail.com`, and so on), so every
email lands in your one inbox. The script prints every login. Password: `Demo-Password-1!`.

Run it once, right after the empty start. To start over: `.\scripts\dev.ps1 -Empty` again.

## 5. Or build the data by hand, with your own fake certificates

```powershell
cd backend
python scripts/make_demo_documents.py "Acme Civils" "Zulu Logistics"
python scripts/make_demo_documents.py "Acme Civils" --types TCS,BBBEE --expired BBBEE
```

Certificates land in `demo-documents/<company>/` with a `README.txt` that lists the expiry date to
type into the upload form. Each has a large SAMPLE watermark and a demonstration-only line. They
are not real issuer documents. See [DEMO_DATA.md](DEMO_DATA.md) for a scripted storyline.

## 6. What people receive, and when

| Event | In the app (bell) | By email |
|---|---|---|
| Someone signs up | Welcome | Welcome to Kopano Match |
| A buyer shortlists an SME | "You have been shortlisted" | Same, with a button to the match |
| An SME applies | Buyer sees "New application" | Same |
| A buyer rejects an SME that applied | "Update on your application" | Same |
| A document is within 30 days of expiry, or expired | Reminder with the renewal cost and days | Same (sent once per stage) |
| Someone forgets their password | None | A single-use link, valid 30 minutes |

Emails carry no scores or documents. Run reminders from the admin account
(`POST /admin/reminders/run`) or on a schedule with `python scripts/send_reminders.py`.
Everything also works with no email provider: the bell still shows each notice, and in local
development the password reset link is printed in the API window.

## 7. Two-step sign-in

Any user can turn it on from **Trust and security**: scan a QR code with Google Authenticator or
a similar app, enter the code, and save the eight recovery codes shown once.

## 8. If something is wrong

| Problem | Fix |
|---|---|
| `dev.ps1` says the database did not start | Start Docker Desktop and run it again |
| The app will not start after copying `.env.example` | Update to the latest code; blank entries now fall back to defaults |
| Gemini or Brevo not working | `python scripts/check_keys.py` names the problem |
| Emails land in spam | Normal for a new sender. Mark them as not spam, or authenticate your sending domain |
| Port in use | Close old windows. The database uses 55432, the API 8000, the web app 5173 |

## 9. Malware scanning (ClamAV)

Every uploaded file is scanned before it is stored. The engine is **ClamAV**, a free open-source
antivirus that runs as its own service. It needs no key.

```powershell
.\scripts\dev.ps1 -Empty -Scan        # starts ClamAV and points the API at it
# or by hand:
docker compose --profile scan up -d clamav
$env:SCANNER_PROVIDER = "clamav"        # then start the API
```

The first start downloads the virus definitions and can take a few minutes. It uses roughly 1 to 2 GB
of memory. Check it: `python scripts/check_keys.py` should print `Scanner PASS`.

- **If the scanner is down, uploads are refused** with a clear "try again" message and nothing is
  stored. A file is never accepted unscanned.
- Without `SCANNER_PROVIDER=clamav`, local runs use a mock that only catches the standard test file.
  Outside development the app refuses to start with the mock.
- **See it work in a demo:** `python scripts/make_demo_documents.py "Acme" --virus-test` writes
  `virus-test.pdf`, the industry-standard harmless antivirus test file. Upload it and the scan
  rejects it. Your own antivirus may delete the file the moment it is written, which is the same
  test string doing its job. Allow it for the demo folder, or skip this moment.

## 10. Test everything

With the API and web app running and the demo built, one command checks the whole system:

```powershell
cd backend
python scripts/smoke_test.py --email you@gmail.com --admin-email you@yourdomain.co.za --admin-password "..."
python scripts/check_keys.py          # Gemini, Brevo and the scanner
python -m pytest -q                   # the full automated suite (needs the planted seed)
```

The smoke test prints one PASS or FAIL per check: sign-in and roles, matching, the quadrant chart
data, consortium, dossier, Unlock Map, Unlock Plan, notifications, other SMEs being blocked from
your data, throttling, uploads, the virus test file, two-step setup and erasure. It creates one
throwaway account (erased at the end, so one welcome email arrives) and asks for one password
reset for a demo SME, so one reset email may arrive.
