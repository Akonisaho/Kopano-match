"""Fit (0-100), readiness (0-100), quadrant and risk flags. Deterministic, no LLM."""

from .gate import credential_status, fit_requirement_met
from .taxonomy import ADJACENT, sector_of
from .types import (
    READINESS_TYPES,
    SME,
    DocStatus,
    Opportunity,
    RiskFlags,
)

THRESHOLD = 60
READINESS_EXPIRED_CREDIT = 0.4
OVERTRADING_MULTIPLE = 2.5
CONCENTRATION_SHARE = 0.6


def capability_coverage(opp: Opportunity, sme: SME) -> float:
    """Share of scope value covered; half credit for a line in a sector the SME works in."""
    total = sum(i.value for i in opp.scope_items)
    if not total:
        return 0.0
    sme_sectors = {sector_of(c) for c in sme.capability_codes}
    earned = 0.0
    for item in opp.scope_items:
        if item.code in sme.capability_codes:
            earned += item.value
        elif sector_of(item.code) in sme_sectors:
            earned += item.value * 0.5
    return earned / total


def covered_codes(opp: Opportunity, sme: SME) -> set[str]:
    """Scope codes covered exactly (used by consortium assembly)."""
    return {i.code for i in opp.scope_items if i.code in sme.capability_codes}


def score_components(opp: Opportunity, sme: SME) -> dict[str, float]:
    comp: dict[str, float] = {}
    comp["capability"] = 40 * capability_coverage(opp, sme)

    annual_value = opp.contract_value / (opp.duration_months / 12)
    comp["capacity"] = 20 * min(1.0, sme.turnover / annual_value)

    if sme.province == opp.province:
        comp["geography"] = 15
    elif sme.province in ADJACENT.get(opp.province, set()):
        comp["geography"] = 8
    else:
        comp["geography"] = 3

    years = min(sme.years_trading / 5, 1.0) * 8
    ratio = sme.largest_past_contract / opp.contract_value
    if ratio >= 1:
        past = 7.0
    elif ratio >= 0.1:
        past = 3.5 + 3.5 * (ratio - 0.1) / 0.9
    else:
        past = 3.5 * ratio / 0.1
    comp["experience"] = years + past

    if opp.transformation_gap:
        hit = sum(1 for f in opp.transformation_gap if f in sme.ownership)
        comp["transformation"] = 10 * hit / len(opp.transformation_gap)
    else:
        comp["transformation"] = 5.0  # no stated gap: neutral
    return comp


def fit_score(opp: Opportunity, sme: SME) -> tuple[float, dict[str, float]]:
    comp = score_components(opp, sme)
    # Non-mandatory fit-axis rows cost `weight` points when unmet; they never gate.
    penalty = 0.0
    for req in opp.requirements:
        if req.type in READINESS_TYPES or req.mandatory:
            continue
        if not fit_requirement_met(req, sme):
            penalty += req.weight
    comp["preferred_requirements"] = -penalty
    fit = max(0.0, min(100.0, sum(comp.values())))
    return fit, {k: round(v, 1) for k, v in comp.items()}


def readiness_score(opp: Opportunity, sme: SME) -> float:
    mandatory = [r for r in opp.requirements if r.type in READINESS_TYPES and r.mandatory]
    if not mandatory:
        return 100.0
    each = 100 / len(mandatory)
    total = 0.0
    for req in mandatory:
        status = credential_status(req, sme)
        if status == DocStatus.VALID:
            total += each
        elif status == DocStatus.EXPIRED:
            total += each * READINESS_EXPIRED_CREDIT
    return total


def quadrant(fit: float, readiness: float) -> str:
    if fit >= THRESHOLD and readiness >= THRESHOLD:
        return "award_now"
    if fit >= THRESHOLD:
        return "coachable"
    if readiness >= THRESHOLD:
        return "ready_weak_fit"
    return "develop"


def risk_flags(opp: Opportunity, sme: SME) -> RiskFlags:
    """Computed alongside, never subtracted from fit."""
    over = opp.contract_value / sme.turnover
    annual = opp.contract_value / (opp.duration_months / 12)
    share = annual / sme.turnover
    working_capital = opp.contract_value / opp.duration_months * (opp.payment_terms_days / 30)
    return RiskFlags(
        overtrading=over > OVERTRADING_MULTIPLE,
        overtrading_pct=round(over * 100),
        working_capital_zar=round(working_capital),
        concentration=share > CONCENTRATION_SHARE,
        concentration_pct=round(share * 100),
    )


def overall(fit: float, readiness: float) -> float:
    """Sorting aid only. The decision lives on the two axes."""
    return round(0.6 * fit + 0.4 * readiness, 1)
