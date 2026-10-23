"""Mandatory requirements -> pass | remediable | fail."""

from .taxonomy import CAPABILITIES
from .types import (
    READINESS_TYPES,
    SME,
    DocStatus,
    Gate,
    Opportunity,
    Requirement,
    RequirementType,
)


def fit_requirement_met(req: Requirement, sme: SME) -> bool:
    t, v = req.type, req.value
    if t == RequirementType.SECTOR:
        return sme.sector == v["sector"]
    if t == RequirementType.PROVINCE:
        return sme.province in v.get("provinces", [v.get("province")])
    if t == RequirementType.MIN_YEARS_TRADING:
        return sme.years_trading >= v["years"]
    if t == RequirementType.MIN_TURNOVER:
        return sme.turnover >= v["amount"]
    if t == RequirementType.OWNERSHIP:
        return v["flag"] in sme.ownership
    if t == RequirementType.CAPABILITY:
        return v["code"] in sme.capability_codes
    raise ValueError(f"not a fit requirement: {t}")


def explain_failure(req: Requirement) -> str:
    """Plain-language reason a mandatory fit requirement was not met."""
    t, v = req.type, req.value
    if t == RequirementType.SECTOR:
        return f"Must operate in the {v['sector'].replace('_', ' ')} sector"
    if t == RequirementType.PROVINCE:
        places = v.get("provinces") or [v.get("province")]
        return "Must be based in " + " or ".join(str(p) for p in places)
    if t == RequirementType.MIN_YEARS_TRADING:
        return f"Needs at least {v['years']} years trading"
    if t == RequirementType.MIN_TURNOVER:
        return f"Needs annual turnover of at least R{v['amount']:,.0f}"
    if t == RequirementType.OWNERSHIP:
        return f"Requires {v['flag'].replace('_', ' ')} ownership"
    if t == RequirementType.CAPABILITY:
        return f"Needs the capability: {CAPABILITIES.get(v['code'], ('', v['code']))[1]}"
    return f"Mandatory {t.value} not met"


def credential_status(req: Requirement, sme: SME) -> DocStatus:
    return sme.documents.get(req.value["doc"], DocStatus.MISSING)


def run_gate(opp: Opportunity, sme: SME) -> tuple[Gate, list[str]]:
    reasons: list[str] = []
    scope_codes = {i.code for i in opp.scope_items}
    if scope_codes and not scope_codes & set(sme.capability_codes):
        reasons.append("None of your capabilities overlap this scope")

    for req in opp.requirements:
        if not req.mandatory or req.type in READINESS_TYPES:
            continue
        if not fit_requirement_met(req, sme):
            reasons.append(explain_failure(req))
    if reasons:
        return Gate.FAIL, reasons

    for req in opp.requirements:
        if req.mandatory and req.type in READINESS_TYPES:
            if credential_status(req, sme) != DocStatus.VALID:
                return Gate.REMEDIABLE, []
    return Gate.PASS, []
