# Onboarding: from clone to first pull request

For the second developer joining Kopano Match. Follow it top to bottom. Allow about 45 minutes.

## 1. What this is

Kopano Match matches SMEs to opportunities on two axes, fit and readiness, with costed plans for
every gap. FastAPI and PostgreSQL behind, React and TypeScript in front. Scoring is deterministic
Python with no AI in the loop.

Read these four files before touching code, in this order:
1. `README.md`: what it is and how to run it.
2. `CLAUDE.md`: the rules for any Claude session in this repo, and for you.
3. `docs/MVP.md`: what we are building and what "done" means.
4. `CONTRIBUTING.md`: how changes reach `main`.

## 2. Before you start

| You need | Check |
|---|---|
| Collaborator access to the repo | Accept the invitation email from GitHub |
| Your **personal** GitHub account on the CLI | `gh auth status` shows your personal account as active, not a work one |
| Git identity for this repo only | `git config user.email` is your personal or noreply address |
| Docker Desktop | `docker --version` |
| Python 3.12 | `python --version` |
| Node 20 or newer | `node --version` |
| Claude Code (terminal or VS Code) signed in to your own account | `claude` opens |

If you are on a work laptop, check that your employer is fine with this code on it.

## 3. Clone and run

Fastest path: after cloning, run `.\scripts\dev.ps1` (planted data) or `.\scripts\dev.ps1 -Empty`
from the repository root. It does everything below. The full guide is `docs/SETUP.md`.

Step by step:

```powershell
git clone https://github.com/Akonisaho/Kopano-match.git
cd Kopano-match
git config user.name "Your Name"
git config user.email "your-personal-or-noreply-email"

docker compose up -d                       # PostgreSQL on localhost:55432

cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python seed.py                             # builds the schema and demo data (dev only)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:
```powershell
cd Kopano-match\frontend
npm install
npm run dev                                # http://localhost:5173
```

No secrets are needed to run it. `.env` is optional; defaults work for local development.
An AI key (`GEMINI_API_KEY`) is optional: without it the app uses built-in fallbacks. If you are
given a key, put it in `backend/.env` and never commit it.

## 4. Prove it works

1. Open http://localhost:5173 and log in as `corporate@kopano.demo`, password `Demo-Password-1!`.
2. Open "Provincial roads rehabilitation" and click a dot on the chart.
3. Log in as `sme-001@sme.demo` and open the dashboard and an opportunity match.
4. In `backend/`: `python -m pytest -q`, `python scripts/check_engine.py --assert`, `ruff check .`
5. In `frontend/`: `npx tsc -b` then `npm run build`.

All of these should pass before you change anything. If one fails, tell the team before going on.

## 5. Working with Claude on this repo

Open the repository folder in Claude Code. `CLAUDE.md` loads automatically, and
`.claude/settings.json` blocks pushing to `main`, force-pushes, merging and approving PRs.

Start every session with:

> Read CLAUDE.md, README.md, docs/MVP.md and CONTRIBUTING.md. Summarise the rules you will follow
> and what I should build first. Do not change anything yet.

Ground rules that apply to you and to Claude:
- Claude is never an author or co-author. No attribution lines in commits or PRs.
- Nobody pushes to `main`. Work on `dev2/<topic>`; the other developer approves every PR.
- You run `git push` and `gh` yourself. Claude proposes commands; it does not push for you.
- Keep UI and docs claims true to the code. A mock is labelled as a mock.

## 6. Your first task

Developer B owns the frontend and the demo. Take these in order, one branch and one PR each:
1. `dev2/ui-pass`: walk every screen as every role, list what is broken or confusing, fix it.
2. `dev2/unlock-plan-ui`: the Unlock Plan panel on the SME dashboard, once Developer A's
   simulate endpoint is merged.
3. `dev2/demo-script`: the 60-second demo script in `docs/` and the slide outline.

## 7. Opening and approving a pull request

1. `git switch -c dev2/<topic>`
2. Make the change. Run the checks in section 4 for the part you touched.
3. `git add -A`, then `git status --short`. Look for `.env`, `uploads/`, `node_modules/`.
4. `git commit -m "<what changed and why>"`, then `git push -u origin dev2/<topic>`.
5. `gh pr create --base main` and fill in the template.
6. Developer A reviews and approves. CI must be green. Squash-merge, delete the branch.

When you review: run the branch, read the diff for secrets and unscoped routes, and check the UI
and docs claims against the code.

## 8. When something goes wrong

| Problem | Fix |
|---|---|
| Port 5432 or 5433 is busy | The project already uses 55432; leave the config as it is |
| `seed.py` refuses to run | It needs `ENVIRONMENT=dev`, which is the default. Check `backend/.env` |
| API says it cannot connect | `docker compose ps`; start the database with `docker compose up -d` |
| Pip fails building `psycopg2` | Use Python 3.12 and the pinned `psycopg2-binary` in `requirements.txt` |
| Page is blank after login | Check the API terminal for errors, then the browser console |
| Odd file-lock or sync errors | The folder is in OneDrive: clone somewhere outside it |
| Unsure about a rule | Ask in the PR; do not guess about security or privacy |
