# Model card: Kopano Match matching engine (v1)

Rerun everything below with `cd backend && python scripts/evaluate_engine.py`. The same numbers are
served live on the public page `/responsible-ai`. CI runs `--assert` so these claims cannot drift.

## What it is
A deterministic rule engine in `backend/app/engine/`. It scores how well a small business suits an
opportunity on two axes:

- **Fit** (0 to 100): capability 40, capacity 20, geography 15, experience 15, transformation 10.
- **Readiness** (0 to 100): whether the required documents are valid (full), expired (40%) or missing (0).

A business is *award ready* at 60 or more on both. Hard requirements (a gate) remove a business
before scoring. There is no learned model in the scoring path. The engine imports no database, web or
AI code.

## Intended use
Rank and explain candidates so a person can shortlist. Never to award, reject or fund automatically.

## Where AI is used (all advisory, all with a fallback)
| Use | Behaviour | Guard |
|---|---|---|
| Document reading | Gemini reads an uploaded certificate and drafts fields | Only on a click, audited, checked against the account, saved only on confirmation |
| Tender text | Drafts requirements from pasted text | Every value checked against fixed lists |
| Meaning check | Compares opportunity text and capabilities by meaning | No name, ownership or size in the prompt; never changes a score |
| Feedback summary | Condenses ratings and comments | Uses only what was written; falls back to figures |
| Match note | Wording of the explanation | Template fallback |

Prompts treat user text as data. Outputs are validated against schemas and enums, so a prompt
injection can at worst give an empty or wrong draft that a person reviews.

## Data
The evaluation uses synthetic data: 40 businesses and 9 opportunities from `seed_data.py` with a fixed
seed. It holds no personal data. Real data would need consent, an operator agreement and an appointed
Information Officer (POPIA).

## Measured behaviour (synthetic data)
- **Planted scenarios:** 11 of 11 behave as promised (a coachable business, an expired affidavit,
  overtrading flagged, award-now cases, a consortium covering 100% of a scope no single business covers).
- **Ranking:** NDCG@5 and precision@3 against a scope-coverage rubric, compared with fit-only ranking,
  sector-only matching and random order. The engine matches fit-only on NDCG and beats it on precision
  because it also weighs readiness. Both beat sector-only and random by a wide margin.
- **Determinism:** two runs give an identical fingerprint.
- **Cost of hard gates:** a small number of rubric-relevant pairs are excluded by hard requirements.
  It is reported, not hidden.

## Fairness
- **Counterfactual test:** flip every business's ownership across all neutral pairs (no transformation
  preference, no ownership requirement). Zero scores change.
- **Disclosed effect:** a buyer's own transformation preference can move fit by at most 10 points
  (5 observed in the data). It appears on the match.
- **Group rates:** the share of businesses matched and award-ready by ownership group, with a
  four-fifths check. In the synthetic cohort the youth-owned group falls outside the four-fifths rule.
  The cause is the sector mix of the 40 businesses and one buyer-set ownership requirement, not a scoring
  rule. It is flagged openly. With real data the check must be rerun and any gap reviewed.

## Limitations
- Synthetic, small data. The numbers show consistency, not real-world accuracy.
- The rubric is not human ground truth. Validation against YES-reviewed outcomes is the next step.
- Credential costs and turnaround times are placeholders until verified with each issuer.
- Registry, tax and identity checks are mocks in this demo and are labelled so in the app.
- Feedback averages from fewer than three reviews are shown as an early signal.
- The jobs figure on the ecosystem dashboard uses a placeholder coefficient (3 per R1m).

## Human oversight
A person shortlists and awards. Flagged items go to a reviewer. Disputed feedback is decided by a
reviewer. Every decision is written to an append-only audit log, and the scores at the moment of award are
frozen into it.
