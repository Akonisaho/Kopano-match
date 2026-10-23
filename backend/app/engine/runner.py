"""match_all(opportunity) -> ranked results. Pure: callers supply SMEs and open opportunities."""

from .consortium import assemble
from .gaps import build_gaps
from .gate import run_gate
from .scoring import fit_score, overall, quadrant, readiness_score, risk_flags
from .types import SME, Consortium, Gate, MatchResult, Opportunity


def match_one(opp: Opportunity, sme: SME, all_open: list[Opportunity]) -> MatchResult:
    gate, reasons = run_gate(opp, sme)
    fit, comp = fit_score(opp, sme)
    ready = readiness_score(opp, sme)
    return MatchResult(
        sme_id=sme.id,
        opportunity_id=opp.id,
        gate=gate,
        fit=round(fit, 1),
        readiness=round(ready, 1),
        overall=overall(fit, ready),
        quadrant=quadrant(fit, ready),
        components=comp,
        gaps=build_gaps(opp, sme, all_open) if gate != Gate.FAIL else [],
        risk=risk_flags(opp, sme),
        fail_reasons=reasons,
    )


def match_all(opp: Opportunity, smes: list[SME], all_open: list[Opportunity]) -> list[MatchResult]:
    """Only `fail` is dropped. Sorted by overall, descending (sorting aid only)."""
    kept = [r for r in (match_one(opp, s, all_open) for s in smes) if r.gate != Gate.FAIL]
    return sorted(kept, key=lambda r: r.overall, reverse=True)


def consortium_for(
    opp: Opportunity, smes: list[SME], results: list[MatchResult]
) -> Consortium | None:
    ready = {r.sme_id: r.readiness for r in results}
    return assemble(opp, [s for s in smes if s.id in ready], ready)
