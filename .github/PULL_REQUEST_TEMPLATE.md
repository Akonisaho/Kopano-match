## What and why

<!-- One or two sentences. Link the issue or task if there is one. -->

## How I checked it

- [ ] Backend: `ruff check .` and `python -m pytest -q` pass (if `backend/` changed)
- [ ] Engine: `python scripts/check_engine.py --assert` passes (if scoring changed)
- [ ] Frontend: `npx tsc -b` and `npm run build` pass (if `frontend/` changed)
- [ ] I ran the affected screens in the browser, not just the tests

## Reviewer checklist

- [ ] No secrets, `.env` files, uploads or personal data in the diff
- [ ] New routes name the roles they admit, and reads are scoped to the caller's organisation
- [ ] Any change to an API response shape is matched in `frontend/src/api.ts`
- [ ] Claims in the UI and docs are true to the code (nothing marked "in place" that is not)
