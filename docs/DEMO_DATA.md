# Build your own demo data

A demo that you created through the app looks real because it is real: every record went through
sign-up, the registry and tax checks, the upload checks and the matching engine. Allow 30 minutes.

## 1. Start clean

Stop the API first (Ctrl+C), then, in `backend/`:

```powershell
$env:ADMIN_EMAIL = "you@yourdomain.co.za"
$env:ADMIN_PASSWORD = "<a strong password, 12+ characters>"
python seed.py --empty
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This drops every table and recreates them with **one admin account and nothing else**. It refuses
to run unless `ENVIRONMENT=dev`. Tests and CI still use the planted seed (`python seed.py`) on a
separate database, so keep them apart: run local tests with
`DATABASE_URL` and `ADMIN_DATABASE_URL` pointing at `kopano_test`.

## 2. Make sample documents

```powershell
python scripts/make_demo_documents.py "Masego Infrastructure" "Thabo Civils" "Nomsa Builders" "Sizwe Road Works" "Tumelo Roadworks"
```

Files land in `demo-documents/<company>/` (TCS, BBBEE, COID, CSD, CIDB). Each is a one-page PDF
stamped "sample for demonstration only", unique per company. They are not real issuer documents
and must never be presented as such.

## 3. Create the buyer and an opportunity

Register a **Corporate buyer** in the app, then post this opportunity. Matching runs on publish,
and you re-run it once the SMEs exist.

| Field | Value |
|---|---|
| Title | Provincial roads rehabilitation |
| Sector, province | Construction, Gauteng |
| Value, duration, payment terms | R4,200,000, 12 months, 30 days |
| Scope lines | Road construction R2.5m, Civil engineering R1.2m, Electrical R0.5m |
| Transformation goal | Youth |
| Requirement rows | Capability CON-ROADS (mandatory); min years 3 (mandatory); TCS, BBBEE, COID (mandatory); CIDB certification (mandatory); province Gauteng (preferred, weight 5) |

## 4. Create the SMEs

For each: register as an SME, complete the profile, upload the listed documents (set an expiry
date in the future unless stated), and run the identity check with any four digits and any small
PNG or JPG. Registration numbers must be unique and must **not end in 7** unless you want the
registry flag.

| SME | Profile | Documents | What it shows |
|---|---|---|---|
| Masego Infrastructure | Gauteng, turnover R12m, 11 years, past contract R4m, CON-ROADS and CON-CIVIL | TCS, BBBEE, COID, CIDB | Award ready |
| Thabo Civils | Gauteng, R6m, 8 years, past R3m, CON-ROADS, CON-CIVIL, CON-ELEC, youth-owned | TCS, BBBEE only | Coachable: two gaps, 14 and 30 days |
| Nomsa Builders | Gauteng, R7m, 9 years, past R3.5m, CON-ROADS, CON-CIVIL | All four, but give BBBEE an **expiry in the past** | One 2-day renewal |
| Sizwe Road Works | Gauteng, R1.4m, 12 years, past R4.5m, CON-ROADS, CON-CIVIL | TCS, BBBEE only | Overtrading flag (contract is 300% of turnover) |
| Tumelo Roadworks | Western Cape, R1.6m, 3 years, past R0.2m, CON-ROADS only | All four | Ready but weak fit |

## 5. Trigger the review queue

- **Registry not found:** register one more SME with a registration number ending in 7.
- **Reused document:** upload another company's `TCS.pdf` from a second SME. The platform flags the
  duplicate across organisations.
- Sign in as the admin to approve or reject both.

## 6. Show consortium assembly

Post a second opportunity that no single SME covers: Agri-hub build, Limpopo, R6.5m, scope lines
Agro-processing R2.0m, Cold chain R1.5m, Networking R1.0m, Building works R2.0m, with TCS and BBBEE
mandatory. Register three SMEs that each cover part: one with AGR-PROC and AGR-LOG, one with
ICT-NET, one with CON-BLDG. The opportunity page proposes the three as a consortium with a lead.

## 7. Finish

1. Sign in as the corporate, open each opportunity and press **Re-run matching**.
2. Shortlist two SMEs, then open one match and its **Decision dossier**.
3. Open the **Unlock Map** to see which credential holds back the most value.
4. Sign in as Thabo Civils and use the **Unlock Plan** on the dashboard.

## Notes

- The registry, tax and identity checks are simulated and labelled as mocks in the app.
- The mock tax provider returns non-compliant for one fixed registration number, and the registry
  returns not found for numbers ending in 7. Everything else verifies.
- Credential costs and turnarounds are placeholders until verified with the issuers.

## Make it feel live: AI summaries and real emails

Both are optional. Without them the app uses built-in fallbacks and never breaks.

**AI match summaries (Gemini).** Create a key in Google AI Studio and put it in `backend/.env`:
```
GEMINI_API_KEY=<your key>
GEMINI_MODEL=gemini-2.0-flash
```
Change `GEMINI_MODEL` if Google retires that name. With a key, the summary on each match reads
"AI-written from the figures". The prompt carries figures only: no names or identifiers. Scores
are never set by the model.

**Real emails (Brevo).** Create a Brevo account, verify a sender address, create an API key, then:
```
EMAIL_PROVIDER=brevo
BREVO_API_KEY=<your key>
EMAIL_FROM=<the verified sender address>
EMAIL_FROM_NAME=Kopano Match
APP_URL=http://localhost:5173
```
Three emails go out: a welcome on sign-up, "you have been shortlisted" to the SME, and "new
application" to the buyer. They carry no scores or documents. Register your demo accounts with
real inboxes you control, for example `you+sme1@gmail.com`, `you+buyer@gmail.com`, so every email
lands in one place you can show on a second screen. Do not register other people's addresses.
Check Brevo's current free-plan limits. Brevo acts as an operator of personal information, so an
operator agreement is needed before any real deployment.

Never commit `.env`. It is git-ignored.
