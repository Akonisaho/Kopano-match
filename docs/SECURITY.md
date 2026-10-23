# Security and POPIA

This is a pilot built against POPIA's conditions. It does not claim compliance: that is an
organisational state (registration, operator agreements, an appointed Information Officer).
Confirm specifics with someone qualified before any real deployment. Not legal advice.

## Controls that ship, and the test that proves each

| Control | Where | Proven by (`backend/tests/test_api.py`) |
|---|---|---|
| bcrypt hashing, JWT with 30 min expiry, deny-by-default role dependency | `auth.py` | `test_routes_deny_by_default`, `test_role_enforcement` |
| Same response for unknown user and wrong password, constant-time-ish | `routers/auth.py` | `test_wrong_password_and_unknown_user_look_the_same` |
| Roles `funder`/`admin` cannot be self-registered | `schemas.RegisterIn` | `test_cannot_self_register_as_admin` |
| Object-level authorisation (404 not 403) | `own_org_or_404`, `owned_opportunity`, `readable_match` | `test_upload_validation_and_object_level_access`, `test_corporate_tenancy_and_ranked_matches`, `test_match_detail_gaps_risk_and_isolation` |
| Upload allow-list: extension, MIME, magic bytes, 5 MB cap, random stored name | `routers/documents.py` | `test_upload_validation_and_object_level_access` |
| Files only via authenticated endpoint, path confined to `uploads/` | `routers/documents.py` | same test (401 without token) |
| Duplicate-document detection by SHA-256 across organisations | `routers/documents.py` | `test_duplicate_document_hash_is_flagged` |
| Append-only audit log enforced by database grant | `db/grants.sql` | `test_app_role_cannot_rewrite_audit_log` |
| Audit row on register, login, failed login, profile change, upload, download, match run, shortlist/reject, reviewer action, export, erasure | routers | `test_shortlist_writes_audit_row`, `test_admin_queue_flags_and_review_is_audited` |
| Pydantic validation on every body, closed enums for requirement rows, parameter-bound SQL | `schemas.py` | `test_invalid_requirement_rows_are_rejected` |
| Secrets in `.env`; JWT secret required outside dev; LLM key sent in a header, never a URL | `config.py`, `main.py`, `llm/client.py` | startup check |
| Security headers, explicit CORS list, no cookies | `main.py` | `test_security_headers_present` |
| Three schemas (`core`, `sensitive`, `audit`) and a least-privilege app role | `db/init.sql`, `db/grants.sql` | grant test above |
| LLM never scores; prompts treat input as data; outputs validated to fixed enums; deterministic fallbacks | `llm/` | rationale present with no key set |

## POPIA conditions, mapped to the build

| Condition | In the build |
|---|---|
| Accountability | Audit log on every state change. Information Officer **not yet appointed**: stated on the privacy page |
| Processing limitation | Consent checkbox stores `consent_version` and timestamp. `visible_to_corporates` toggle controls exposure |
| Purpose specification | A hint beside each form field says why it is collected and who sees it |
| Further processing limitation | Match data stays in the match context. No analytics in the MVP |
| Information quality | Expiry checks, hash-based duplicate detection, registry and tax checks via adapters, human review queue |
| Openness | Short privacy notice at `/privacy` |
| Security safeguards | The controls above, plus schema separation |
| Data subject participation | `GET /me/data` exports everything held. `POST /me/delete` runs `core.anonymise_user()`; audit rows survive without the person's details (`test_data_export_and_anonymisation_keep_audit_trail`) |

Special personal information: no selfie or biometric is stored (the mock identity provider
discards it and returns an outcome and confidence). Ownership flags are used only to match a
buyer's stated transformation goal. Retention dates are stored on documents and verifications;
**no purge job exists yet**.

Data residency: the production commitment is Azure South Africa North (section 72). A local
demo does not demonstrate residency.

## Roadmap, not built

MFA and OTP, password reset, Azure Key Vault, a real antivirus engine for uploads (a scanner interface with a mock exists), encryption at rest with customer-managed keys, API gateway, penetration
test, disaster recovery, incident response runbook, retention purge job, row-level security in
PostgreSQL, per-corporate delegated admin, SSO (Entra ID/SAML), OpenTelemetry, versioned `/v1`
routes and idempotency keys, operator agreements and a DPIA.

## Known limits to say out loud

- The JWT sits in `sessionStorage`. An XSS bug could read it; React escaping and no raw HTML
  rendering are the mitigation, and an httpOnly cookie plus CSRF protection is the production answer.
- Seed data uses one shared demo password. Never run the seed outside a demo.
- Uploaded files are stored unencrypted on local disk.
- A rejected document is treated as missing; there is no appeal flow.
- The mocks decide the review-queue cases; they say so in the UI.

## Supply chain and scan results (2026-10-23)

| Check | Result |
|---|---|
| `pip-audit` on `backend/requirements.txt` | No known vulnerabilities. Before the fix it reported 50 advisories in starlette 0.38.6, python-multipart 0.0.12 and PyJWT 2.9.0; upgraded to starlette 1.9.0, python-multipart 0.0.32, PyJWT 2.15.1, fastapi 0.161.1 |
| `npm audit` | 0 vulnerabilities. Three moderate findings in Tailwind's build-time chain were cleared with an override of `postcss-selector-parser` |
| bandit (medium and above) | No findings. Low findings are false positives (the word "bearer" and the enum value "pass" flagged as passwords, a seeded random generator in demo data) |
| Secrets sweep | None found. Only throwaway passwords in test fixtures |
| SBOM | CycloneDX 1.6 in `docs/sbom/`: 30 backend runtime components, 7 frontend production components, licences recorded |

Findings the scan surfaced that were fixed: the dev JWT secret was 18 bytes, below the 32-byte HMAC
minimum PyJWT now warns on. The dev default is longer, and the app refuses to start outside dev with
a default or short secret.

Licence note for customers: `psycopg2-binary` is LGPL-licensed (with the usual linking exception).

Not yet done: GitHub Actions are referenced by version tag rather than pinned commit SHA; SBOM signing
and build provenance attestation; container image scanning (there is no image yet); a signed release.

## Added since the first version

| Control | Where | Proven by |
|---|---|---|
| Login throttle: 5 failures per account in 15 minutes, then a lockout. Keyed by submitted email, so it does not reveal which accounts exist. In-process memory, so per server process; production needs a shared store | `app/ratelimit.py`, `routers/auth.py` | `test_login_is_throttled_per_account_and_does_not_leak_which_emails_exist` |
| Uploads pass a malware scanner interface before storage. Today the scanner is a mock that catches only the standard test file | `adapters/`, `routers/documents.py` | `test_upload_scanner_rejects_the_standard_test_signature_and_stores_nothing` |
| Erasure deletes the organisation's uploaded files from disk, then anonymises the person | `routers/auth.py`, `routers/documents.py` | `test_erasure_deletes_uploaded_files_from_disk` |
| A shortlist or reject decision stores a frozen copy of the scores, rules and gaps in the append-only audit log | `routers/matches.py` | `test_shortlist_writes_audit_row` |
| The data export includes matches and applications | `routers/auth.py` | `test_data_export_includes_matches_and_applications` |
| Unlock Plan: a what-if that re-runs the real rules, saves nothing and is limited to the signed-in SME | `services.simulate`, `routers/smes.py` | `test_unlock_plan_moves_the_numbers_using_the_real_rules` |

## Email and AI providers (optional, off by default)

| Provider | Receives | Does not receive | Needed before real use |
|---|---|---|---|
| Brevo (service emails) | Recipient address and name, the message text | Scores, documents, ID data | Operator agreement; sender domain authentication (SPF, DKIM); confirm data location |
| Gemini (summaries, drafting) | Figures from a match, or text the user pastes | Names and identifiers in match summaries | Operator agreement; decide what users may paste |

A failed send or a failed model call never fails a request. Both providers sit behind adapters.

## Two-step sign-in, password reset, notifications

| Control | Where | Proven by |
|---|---|---|
| Optional authenticator-app sign-in (TOTP). The secret is encrypted at rest with an application key; a code cannot be used twice; recovery codes are stored hashed and work once | `app/mfa.py`, `routers/auth.py` | `test_two_step_sign_in_end_to_end` |
| The half-finished sign-in token is useless as an access token | `app/auth.py` | the same test (stolen challenge token returns 401) |
| Attempts at the second step are throttled per account | `routers/auth.py` | login throttle tests |
| Password reset: single-use link, 30 minutes, only a hash stored, every outstanding link dies on use, same answer whether or not the email exists | `routers/auth.py` | `test_password_reset_is_single_use_expires_and_does_not_reveal_accounts` |
| In-app notifications are private to the recipient, and erasure removes them | `routers/notifications.py` | `test_in_app_notifications_work_without_any_email_provider` |
| Document expiry reminders are sent once per stage, recorded in the audit log | `app/reminders.py` | `test_expiry_reminders_go_out_once_and_only_once` |

Honest limits: two-step sign-in is optional and not required for any role yet. The password-reset
endpoint does slightly more work for a registered email than an unknown one, so a patient attacker
could measure a timing difference; the response itself is identical. Existing access tokens stay
valid until they expire (30 minutes) after a password reset. Outside development the app refuses
to start without `MFA_ENCRYPTION_KEY`.

## Malware scanning

| Property | State |
|---|---|
| Engine | ClamAV, run as a separate service (`docker compose --profile scan`), spoken to over its network protocol. Local runs default to a mock that only catches the standard test file |
| When it runs | After the filename, type and size checks and before anything is stored or its type header is trusted |
| If it cannot answer | The upload is refused (HTTP 503) and nothing is stored. An error or an odd answer is never treated as clean |
| Outside development | The app refuses to start with the mock scanner |
| Proven by | Tests against a stand-in ClamAV server (run in CI), and tests against a real ClamAV container when one is running, including the standard test file being rejected and a clean certificate being accepted |

Honest limits: antivirus is signature-based and does not catch everything, so it is one layer, not
a guarantee. Uploads are limited to PDF, PNG and JPG with content checks, which narrows the risk.
ClamAV's test signature matches only a file that is the test string, so test files carry no
header. The real-ClamAV tests do not run in CI because the container is large; the protocol tests
do. Definitions update inside the container, so a production deployment needs a plan for keeping it
running and current.

## Awards, impact reporting and consortium invitations

| Control | Where | Proven by |
|---|---|---|
| Only the buyer that owns an opportunity can award on it, and only after a shortlist. An award is final | `routers/applications.py` | `test_awarding_needs_a_shortlist_freezes_the_record_and_feeds_the_impact_report` |
| The scores at the moment of award are frozen in the append-only audit log | `services.decision_snapshot` | the same test (dossier shows the awarded snapshot) |
| The impact report is aggregates only, scoped to the buyer's own awards, with no business named | `services.impact` | the same test, plus the browser check |
| Consortium invitees see their own part and a partner count, never the partners' names, until everyone accepts | `routers/consortia.py` | `test_consortium_invitations_full_lifecycle_and_privacy` |
| Only invited SMEs can answer, only once, and a decline lapses the proposal | `routers/consortia.py` | the same test |

Honest limits: the impact report states ownership in aggregate, which is further use of special
personal information beyond matching, so the privacy notice says so. A buyer enters the award value
itself; it is not reconciled against a signed contract. Consortium formation records the businesses'
agreement to bid together, not a legal agreement between them.
