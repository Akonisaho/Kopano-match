"""Greedy set-cover over scope items, for opportunities no single SME covers."""

from .scoring import covered_codes
from .types import SME, Consortium, Opportunity

MAX_MEMBERS = 3


def assemble(
    opp: Opportunity, candidates: list[SME], readiness: dict[str, float]
) -> Consortium | None:
    value = {i.code: i.value for i in opp.scope_items}
    uncovered = set(value)
    members: list[SME] = []
    pool = list(candidates)
    while uncovered and pool and len(members) < MAX_MEMBERS:
        best = max(pool, key=lambda s: sum(value[c] for c in covered_codes(opp, s) & uncovered))
        gain = covered_codes(opp, best) & uncovered
        if not gain:
            break
        members.append(best)
        uncovered -= gain
        pool.remove(best)
    if len(members) < 2:
        return None  # a single SME covers it, or nobody can
    total = sum(value.values())
    covered = total - sum(value[c] for c in uncovered)
    lead = max(members, key=lambda s: (readiness.get(s.id, 0), len(covered_codes(opp, s))))
    return Consortium(
        opportunity_id=opp.id,
        lead_sme_id=lead.id,
        member_sme_ids=[m.id for m in members],
        coverage_pct=round(100 * covered / total, 1),
        uncovered_codes=sorted(uncovered),
    )
