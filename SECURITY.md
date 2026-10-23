# Security policy

## Reporting a vulnerability

Please do not open a public issue. Email the maintainers (address to be added before the repository
is made public) with a description, reproduction steps and the affected version. We aim to
acknowledge within 3 working days and to give a remediation plan within 10.

This is a pilot build. There is no bug bounty and no formal vulnerability SLA yet.

## Supply chain

- **SBOM:** CycloneDX 1.6 for the backend and frontend in [docs/sbom/](docs/sbom/), regenerated on
  every CI run as a build artifact (see the `sbom` job in `.github/workflows/security.yml`).
  The backend SBOM is built from a runtime-only environment, so scan tooling is not listed.
- **Vulnerability scanning:** `pip-audit` and `npm audit` in CI; Dependabot opens weekly update PRs
  for pip, npm and GitHub Actions.
- **Static analysis and secrets:** bandit, CodeQL (public repos) and gitleaks in CI.
- **Pinned dependencies:** every Python dependency is pinned in `backend/requirements.txt` and npm
  versions are locked in `package-lock.json`.

Controls, tests and the POPIA mapping are in [docs/SECURITY.md](docs/SECURITY.md). Known limits are
listed there too, including what is on the roadmap and not built.
