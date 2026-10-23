"""Bridges the database and the pure engine. The only place ORM rows become engine dataclasses."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .engine import runner
from .engine.types import (
    SME,
    DocStatus,
    MatchResult,
    Opportunity,
    Requirement,
    RequirementType,
    ScopeItem,
)


def doc_status(doc: m.Document | None, today: date | None = None) -> DocStatus:
    today = today or date.today()
    if doc is None or doc.review_status == "rejected":
        return DocStatus.MISSING
    if doc.expiry_date is not None and doc.expiry_date < today:
        return DocStatus.EXPIRED
    return DocStatus.VALID


def load_smes(db: Session, only_visible: bool = True) -> list[SME]:
    q = select(m.SmeProfile, m.Organisation).join(
        m.Organisation, m.Organisation.id == m.SmeProfile.organisation_id
    )
    if only_visible:
        q = q.where(m.SmeProfile.visible_to_corporates.is_(True))
    rows = db.execute(q).all()
    docs: dict[uuid.UUID, dict[str, m.Document]] = {}
    for d in db.scalars(select(m.Document).order_by(m.Document.uploaded_at)):
        docs.setdefault(d.organisation_id, {})[d.document_type] = d  # latest wins
    out = []
    for p, org in rows:
        by_type = docs.get(org.id, {})
        out.append(
            SME(
                id=str(org.id),
                name=org.name,
                sector=p.sector,
                province=p.province,
                turnover=float(p.annual_turnover),
                years_trading=p.years_trading,
                largest_past_contract=float(p.largest_past_contract or 0),
                capability_codes=list(p.capability_codes or []),
                ownership=list(p.ownership or []),
                documents={t: doc_status(d) for t, d in by_type.items()},
            )
        )
    return out


def to_engine_opportunity(o: m.Opportunity, reqs: list[m.OpportunityRequirement]) -> Opportunity:
    return Opportunity(
        id=str(o.id),
        title=o.title,
        sector=o.sector,
        province=o.province,
        contract_value=float(o.contract_value),
        duration_months=o.duration_months,
        payment_terms_days=o.payment_terms_days,
        scope_items=[ScopeItem(i["code"], float(i["value"])) for i in o.scope_items],
        requirements=[
            Requirement(
                RequirementType(r.requirement_type), r.requirement_value, r.mandatory, r.weight
            )
            for r in reqs
        ],
        transformation_gap=list(o.transformation_gap or []),
        status=o.status,
    )


def load_open_opportunities(db: Session) -> dict[uuid.UUID, Opportunity]:
    opps = list(db.scalars(select(m.Opportunity).where(m.Opportunity.status == "open")))
    reqs: dict[uuid.UUID, list[m.OpportunityRequirement]] = {}
    for r in db.scalars(select(m.OpportunityRequirement)):
        reqs.setdefault(r.opportunity_id, []).append(r)
    return {o.id: to_engine_opportunity(o, reqs.get(o.id, [])) for o in opps}


def explanation_of(r: MatchResult) -> dict:
    return {
        "components": r.components,
        "gaps": [
            {
                "credential": g.credential,
                "label": g.label,
                "status": g.status.value,
                "mandatory": g.mandatory,
                "issuer": g.issuer,
                "days": g.days,
                "cost_zar": g.cost_zar,
                "also_unlocks": g.also_unlocks,
            }
            for g in r.gaps
        ],
        "fail_reasons": r.fail_reasons,
    }


def risk_of(r: MatchResult) -> dict:
    k = r.risk
    return {
        "overtrading": k.overtrading,
        "overtrading_pct": k.overtrading_pct,
        "working_capital_zar": k.working_capital_zar,
        "concentration": k.concentration,
        "concentration_pct": k.concentration_pct,
    }


def run_matching(db: Session, opportunity_id: uuid.UUID) -> list[m.Match]:
    """Re-running updates in place (unique on sme, opportunity, model_version)."""
    open_opps = load_open_opportunities(db)
    opp = open_opps.get(opportunity_id)
    if opp is None:
        return []
    smes = load_smes(db)
    results = runner.match_all(opp, smes, list(open_opps.values()))

    under_review = {
        o.id
        for o in db.scalars(
            select(m.Organisation).where(m.Organisation.verification_status == "under_review")
        )
    }
    existing = {
        (x.sme_id, x.model_version): x
        for x in db.scalars(select(m.Match).where(m.Match.opportunity_id == opportunity_id))
    }
    saved = []
    for r in results:
        sme_id = uuid.UUID(r.sme_id)
        row = existing.get((sme_id, r.model_version))
        if row is None:
            row = m.Match(
                sme_id=sme_id, opportunity_id=opportunity_id, model_version=r.model_version
            )
            db.add(row)
        row.gate = r.gate.value
        row.quadrant = r.quadrant
        row.fit_score = r.fit
        row.readiness_score = r.readiness
        row.overall_score = r.overall
        prior = (row.explanation or {}).get("rationale")
        row.explanation = explanation_of(r)
        if prior:
            row.explanation["stale_rationale"] = prior  # regenerated lazily on next view
        row.risk_flags = risk_of(r)
        row.flagged = sme_id in under_review
        saved.append(row)
    # Matches that no longer pass the gate must not linger in the shortlist
    kept = {uuid.UUID(r.sme_id) for r in results}
    for (sme_id, _), row in existing.items():
        if sme_id not in kept and row.status == "matched":
            db.delete(row)
    return saved


def blockers_for(db: Session, org_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    """Why an SME is not matched to each open opportunity it fails the gate for."""
    from .engine.gate import run_gate
    from .engine.types import Gate

    sme = next((s for s in load_smes(db, only_visible=False) if s.id == str(org_id)), None)
    if sme is None:
        return {}
    out: dict[uuid.UUID, list[str]] = {}
    for opp_id, opp in load_open_opportunities(db).items():
        gate, reasons = run_gate(opp, sme)
        if gate == Gate.FAIL:
            out[opp_id] = reasons
    return out


def consortium(db: Session, opportunity_id: uuid.UUID):
    open_opps = load_open_opportunities(db)
    opp = open_opps.get(opportunity_id)
    if opp is None:
        return None
    smes = load_smes(db)
    results = runner.match_all(opp, smes, list(open_opps.values()))
    return opp, smes, runner.consortium_for(opp, smes, results)
