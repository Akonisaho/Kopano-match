# Kopano Match

Matches SMEs to corporate opportunities on two axes, **Fit** and **Readiness**, with costed,
dated remediation plans, capacity-risk flags and consortium assembly. Pilot build; see
[docs/SECURITY.md](docs/SECURITY.md) for security, POPIA mapping and the gap to enterprise.

## Run it

```bash
docker compose up -d                 # PostgreSQL 16 on localhost:55432
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python seed.py                       # schema, grants, 40 SMEs, 9 opportunities
python scripts/check_engine.py       # scored table in the terminal (--assert for CI)
python -m uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

Demo logins (password `Demo-Password-1!`, set by `SEED_PASSWORD`):

| Role | Email | Try this |
|---|---|---|
| Corporate buyer | `corporate@kopano.demo` | Open "Provincial roads rehabilitation": quadrant chart, ranked shortlist |
| Funder | `funder@kopano.demo` | Youth growth grant (ownership gate), investor cohort |
| Business support | `support@kopano.demo` | Supplier development accelerator |
| Platform reviewer | `admin@kopano.demo` | Review queue with three planted flags |
| SME, coachable | `sme-001@sme.demo` | Two costed gaps; "next best step" on the dashboard |
| SME, overtrading | `sme-003@sme.demo` | Capacity-risk flags |
| SME, expired B-BBEE only | `sme-002@sme.demo` | One 2-day fix |

`seed.py` drops and recreates every table and refuses to run unless `ENVIRONMENT=dev`.
The API serves docs at `/docs`. The frontend proxies `/api` to `127.0.0.1:8000`.

Tests: `cd backend && python -m pytest -q` (needs the seeded database).

## Layout

- `backend/app/engine/` pure scoring (gate, fit, readiness, gaps, consortium). No DB, no LLM.
- `backend/app/adapters/` interfaces plus deterministic mocks for identity, registry, tax.
- `backend/app/routers/` API. `auth.py` holds the role and object-level checks.
- `backend/db/` schemas, role and grants (append-only audit), `anonymise_user()`.
- `frontend/src/` React, Vite, Tailwind. `QuadrantChart` is plain SVG.

## Honest limits

Verification adapters are mocks and labelled as such in the UI. Catalogue costs and turnarounds
in `engine/taxonomy.py` are indicative: verify before presenting. Not legal advice.
