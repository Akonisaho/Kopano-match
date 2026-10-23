# Working together

Two developers, one repo. Every change reaches `main` through a pull request that the **other**
person approves. Nobody approves their own work.

## Flow

1. Branch from `main`: `git switch -c dev1/metrics-endpoint` (use `dev1/` or `dev2/` plus a short name).
2. Keep branches small and short-lived, ideally merged the same day.
3. Run the checks listed in the PR template before pushing.
4. Open a PR into `main`. The template lists what to check.
5. The other developer reviews and approves. CI must be green.
6. Squash-merge, delete the branch, pull `main`.

## Ownership, to avoid conflicts

- **Dev 1:** `backend/`. If a response shape changes, update `frontend/src/api.ts` in the same PR.
- **Dev 2:** `frontend/`, and the demo script and slides.
- Shared files (`docs/`, `.github/`, `README.md`) are fine for either, with review.

## Reviewing

Look for: secrets or personal data in the diff; routes without a role requirement or without
organisation scoping; UI or docs that claim something the code does not do. Run the branch if the
change is visual.

## Commits

Write commits as yourself. Use plain messages that say what changed and why.

## Enforcing the approval rule

The rule is enforced by a GitHub ruleset on `main` (Settings, Rules, Rulesets): pull request
required, 1 approval, stale approvals dismissed on new commits, status checks `backend` and
`frontend` required, force pushes blocked, no bypass. Rulesets and branch protection are free on
public repositories. On a private repository they need a paid GitHub plan; without one, the rule
is only a team agreement.
