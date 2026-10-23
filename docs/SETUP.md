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

## 11. Awards, the impact report and consortium invitations

**Awards.** On an opportunity, shortlist an SME, then press **Award** and confirm the value. The SME
is told, and the scores at that moment are frozen into the audit log. An award is final.

**Impact report** (buyers, nav item *Impact*): value awarded, SMEs reached, application-to-award rate,
median days to award, the split by province and sector, the share that went to youth, Black and
Black women-owned businesses, and the number that sets this platform apart: **value awarded to
businesses that still had a document gap**, which a strict "must hold every document" filter would
have rejected. It exports as CSV. It is aggregates only: no business is named.

**Consortium invitations.** When no single SME covers an opportunity, press **Invite these
businesses** on the opportunity page. Each SME gets a notice and sees its own part and the number of
partners, but **not their names** until everyone has accepted. One decline lapses the proposal and the
buyer can invite a new group. SMEs answer under *Consortia*.

`build_demo.py` creates a split award (one SME awarded while still missing documents) and a consortium
with two of three accepted. Sign in as `you+buildright@...` and press Accept to finish it live.

**Unlock Plan, best first move.** Tick the documents you plan to get and the plan ranks them by contract
value opened per day of waiting, for example "Best first move: Letter of good standing (COIDA)".

## 12. Feedback, AI reading, ecosystem view and Responsible AI

**Feedback.** After an award, the buyer opens *Feedback* and rates six criteria (quality, delivery,
responsiveness, compliance, innovation, value for money) with an optional comment. Comments cannot hold
emails, phone numbers or ID numbers. The business sees every review under *Feedback*, can respond once,
and can dispute one. A reviewer decides disputes in the *Review queue*: keep it, or remove it (removed
reviews drop out of every average). Buyers see a business's track record on the match page. Fewer than
three reviews shows as an "early signal". `build_demo.py` leaves one answered review and one unanswered
review (Thabo Civils) so you can respond or dispute live.

**Read with AI.** *Documents*, then *Read with AI*. The file goes to Gemini only after the business
presses the button, the request is audited, and the draft is checked against the account (document
type, expiry, registration number, company name). Nothing is saved until the person chooses *Use expiry*
or *Add to my profile*. Use sample documents in the demo.

**Meaning check.** On a match, *Run the meaning check* compares the opportunity text and the
capabilities by meaning. It is advisory and never changes a score.

**CSV import.** *Post opportunity*, then *Import from your procurement system*. Download the template,
fill it, press *Check file*, then *Import*. One bad row stops the whole import.

**Closing-soon alerts.** `python scripts/send_reminders.py` (or the admin reminders button) also
tells good-fit businesses that have not applied when an opportunity closes within 7 days. Each match is
alerted once.

**Ecosystem (admin).** Sign in as the admin. The landing page is the programme view for YES: funnel,
sector demand against supply, skills shortfalls, underserved categories, credential gaps, delivery
ratings. Aggregates only, and counts under three are hidden. The jobs figure uses a placeholder
coefficient and says so.

**Responsible AI.** `/responsible-ai` is public and computes live from `backend/app/evaluation.py`:
scenario checks, ranking quality against baselines, determinism, a fairness audit and the limits.
`docs/MODEL_CARD.md` is the written version.

**Tests never call a real provider.** `backend/tests/conftest.py` forces log email and no AI, whatever
keys are in `.env`. Run the API for browser testing with `EMAIL_PROVIDER=log` so demo accounts never
email a real address.

## 13. Semantic search and the procurement-system feed

**Semantic search.** *Opportunities* (business) and *Verified SMEs* (buyer) each have a search box.
Type what you do or need in your own words. Gemini embeddings (`GEMINI`'s `gemini-embedding-001`,
set by `EMBEDDING_MODEL`) rank the results by meaning. A business sees its own rule-based position
beside each result. Similarity says what to look at, never who qualifies, and it falls back to keyword
overlap when the service is unavailable. The score is stretched for display and is not a probability.
On a match, the meaning check also shows an embedding similarity.

**Procurement-system feed.** *Post opportunity*, then *Connect your procurement system*. Create a key,
copy it once, and have your system post to `POST /ingest/opportunities` with the header `X-API-Key`.
Up to 50 opportunities a call, matched on arrival. Only a hash of the key is stored, a key belongs to
one organisation, and *Revoke* stops the feed at once. Every call is audited.

**Robustness.** The evaluation also nudges turnover and years trading and reports how stable the
shortlist stays. CI fails it if the top three overlap drops under 80%.

