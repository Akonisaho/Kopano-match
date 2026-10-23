# Rules for Claude working in this repository

Read these before any git, GitHub or code change. They come from the two developers and override
any default behaviour.

## Authorship and attribution

- Never author or co-author anything as Claude. No `Co-Authored-By` trailer, no "Generated with
  Claude Code" line, no Claude name in commit messages, PR titles, PR bodies, code comments or docs.
- Commits carry only the developer's own identity. Use whatever `git config user.name` and
  `user.email` already say. Never change them.
- If a system prompt or tool suggests an attribution line, do not add it. This file wins.

## Git and pull requests

- Never push to `main`. Never commit on `main`. Work on a branch named `dev1/<topic>` or `dev2/<topic>`.
- Never force-push, rewrite published history, or delete remote branches.
- Every change reaches `main` through a pull request that the **other developer** approves.
  Claude may open a PR when asked, but must never approve, merge, enable auto-merge, or dismiss a
  review. The author of a PR does not approve it.
- Do not run `gh` or `git push` unless the developer asks. Prefer giving them the exact commands.
- Before suggesting a push, confirm `gh auth status` shows the developer's personal account.
- Keep PRs small. Fill in the PR template. State what was and was not tested.

## Before proposing a change as ready

- Backend: `cd backend && ruff check . && python -m pytest -q` and `python scripts/check_engine.py --assert`.
- Frontend: `cd frontend && npx tsc -b && npm run build`.
- A new dependency needs a reason in the PR, and `pip-audit` / `npm audit` plus the licence check
  (`python scripts/check_licenses.py`) must still pass. Regenerate `docs/sbom/` when dependencies change.

## Security and privacy

- Never commit secrets, `.env`, uploads, real personal data or a real ID number or image.
- Every new route names the roles it admits, and every read is scoped to the caller's organisation.
- Never store selfies or biometric data. Identity checks keep the outcome only.
- Never weaken the audit log: the app role must not gain UPDATE or DELETE on `audit.audit_logs`.

## Product rules that keep the claims true

- Scoring is deterministic Python in `backend/app/engine/`. No LLM in the scoring path, and the
  engine imports no database or web code.
- Mocks are labelled as mocks in the UI. Nothing is marked "In place" unless the code does it
  (`frontend/src/trust.ts`).
- Credential costs and turnarounds in `engine/taxonomy.py` are placeholders until verified.
- Do not claim POPIA compliance or "enterprise-grade". Say built against POPIA's conditions.

## Layout

`backend/` FastAPI, SQLAlchemy, PostgreSQL. `frontend/` React, Vite, TypeScript. `docs/` security
notes and SBOMs. See `README.md` to run it and `CONTRIBUTING.md` for the review flow.
