# MVP, not prototype

## The difference

A **prototype** shows that the idea works on demo data. An **MVP** lets one real customer run one
real procurement on it without us being embarrassed or exposed.

Kopano Match is a strong prototype today. It becomes an MVP when a real corporate can publish a
real opportunity, real SMEs can register and be checked against real sources, and the data is
kept safely, with nothing in the product claiming more than the code does.

## MVP definition

One corporate, one sector, about 50 SMEs, live company-registry and tax checks, hosted in South
Africa, and one award made through the platform. This is phase 1 of the roadmap in the business
model.

## What is real today and what is not

| Area | Today | MVP needs |
|---|---|---|
| Matching engine, scoring, gaps, consortium | Real, tested | Keep; verify credential costs and thresholds |
| Roles, audit log, object-level access | Real, tested | Keep |
| Registry, tax, identity checks | Mock adapters | Live providers behind the same interfaces |
| Database schema | Created by `create_all`, reseeded | Migrations (Alembic), so real data survives changes |
| Hosting | Local only | Dockerfile, deployment in Azure South Africa North, HTTPS, secrets in a vault |
| Files | Local disk, unencrypted. Uploads are scanned by ClamAV when it is running, and refused if it is down | Blob storage, encryption at rest, scanning always on and monitored in production |
| Sign-in | Password, optional authenticator-app step with recovery codes, single-use password reset, login throttle | Email verification at sign-up, MFA required for admins and providers, a shared store for the throttle |
| Erasure and retention | Anonymises the person and deletes their uploaded files | A retention job and a documented schedule |
| Notifications | In-app bell plus email (Brevo) for welcome, shortlist, application and expiry reminders | Delivery tracking, user preferences, review-outcome notices, a scheduled reminder job in production |
| Admin | Review queue only | Invite-only provider and admin accounts, user and opportunity management |
| Operations | Server logs | Error tracking, backups with a tested restore, a short runbook |
| Legal | Privacy notice, no Information Officer | DPIA, Information Officer, operator agreements, terms, legal review |
| Outcomes | Awards recorded with value and date, frozen decision record, impact report with CSV export | Award value reconciled against signed contracts, and outcome follow-up after delivery |

## Order of work

1. **Make real data safe:** migrations, deployment, secrets, backups, sign-in hardening.
2. **Make checks real:** registry and tax first, then identity. This depends on getting API access,
   so start that conversation now.
3. **Make files safe:** blob storage, encryption, malware scan, purge on erasure.
4. **Make the value provable:** outcomes tracking, then the Unlock Plan, bottleneck view and
   decision dossier.
5. **Make it operable:** notifications, admin tools, runbook.
6. **Make it legal:** in parallel from day one, because it has the longest lead time.

## Definition of done for the MVP

- A real corporate has published a real opportunity and reviewed matches.
- Registry and tax results come from the live sources, and identity from a real provider.
- The app runs in South Africa with HTTPS, backups and a tested restore.
- CI, vulnerability, licence and static scans are green on every merge.
- An Information Officer is named and the privacy notice is reviewed by someone qualified.
- Every claim in the UI, docs and pitch is true of the code (see the trust list in
  `frontend/src/trust.ts`).

## Estimate

About 6 to 10 weeks for two developers, assuming provider API access arrives within the first two
weeks. Provider access and legal review are outside our control and are the main schedule risk.
