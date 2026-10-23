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


def simulate(db: Session, org_id: uuid.UUID, credentials: list[str]) -> dict | None:
    """What changes if this SME obtains these credentials. Same rules, same catalogue, no guessing."""
    from dataclasses import replace

    from .engine.runner import match_one
    from .engine.taxonomy import COMPLIANCE_CATALOGUE
    from .engine.types import Gate

    sme = next((s for s in load_smes(db, only_visible=False) if s.id == str(org_id)), None)
    if sme is None:
        return None
    after_sme = replace(
        sme, documents={**sme.documents, **{c: DocStatus.VALID for c in credentials}}
    )
    opps = load_open_opportunities(db)
    everything = list(opps.values())
    titles = {
        str(o.id): (o.title, float(o.contract_value))
        for o in db.scalars(select(m.Opportunity).where(m.Opportunity.status == "open"))
    }

    def view(r):
        return {
            "quadrant": r.quadrant,
            "fit": r.fit,
            "readiness": r.readiness,
            "gate": r.gate.value,
        }

    rows, ready_before, ready_after, value_before, value_after = [], 0, 0, 0.0, 0.0
    for opp in everything:
        b = match_one(opp, sme, everything)
        a = match_one(opp, after_sme, everything)
        if b.gate == Gate.FAIL and a.gate == Gate.FAIL:
            continue
        title, value = titles[opp.id]
        was, now = b.quadrant == "award_now", a.quadrant == "award_now"
        ready_before += was
        ready_after += now
        value_before += value if was else 0
        value_after += value if now else 0
        rows.append(
            {
                "opportunity_id": opp.id,
                "title": title,
                "contract_value": value,
                "before": None if b.gate == Gate.FAIL else view(b),
                "after": view(a),
                "newly_award_ready": now and not was,
            }
        )
    chosen = []
    for code in credentials:
        c = COMPLIANCE_CATALOGUE[code]
        status = sme.documents.get(code, DocStatus.MISSING)
        if status == DocStatus.VALID:
            continue
        days = c.renew_days if status == DocStatus.EXPIRED else c.days
        chosen.append(
            {
                "code": code,
                "label": c.label,
                "issuer": c.issuer,
                "days": days,
                "cost_zar": c.cost_zar,
            }
        )
    return {
        "selected": chosen,
        # Credentials are obtained in parallel, so the wait is the longest one
        "total_days": max((c["days"] for c in chosen), default=0),
        "total_cost_zar": sum(c["cost_zar"] for c in chosen),
        "before": {"award_ready": ready_before, "value": value_before},
        "after": {"award_ready": ready_after, "value": value_after},
        "opportunities": sorted(
            rows, key=lambda r: (not r["newly_award_ready"], -r["contract_value"])
        ),
    }


def bottlenecks(db: Session) -> dict:
    """Which credential blocks the most good-fit SMEs, and how much contract value sits behind it.

    Aggregates only: no SME names. A pair counts when the SME fits the opportunity (fit 60+),
    is not structurally excluded, and is missing or has an expired mandatory credential.
    """
    from .engine.runner import match_one
    from .engine.types import Gate

    smes = load_smes(db)
    opps = load_open_opportunities(db)
    everything = list(opps.values())
    value = {
        str(o.id): float(o.contract_value)
        for o in db.scalars(select(m.Opportunity).where(m.Opportunity.status == "open"))
    }
    agg: dict[str, dict] = {}
    for opp in everything:
        for sme in smes:
            r = match_one(opp, sme, everything)
            if r.gate == Gate.FAIL or r.fit < 60:
                continue
            gaps = [g for g in r.gaps if g.mandatory]
            for g in gaps:
                a = agg.setdefault(
                    g.credential,
                    {
                        "label": g.label,
                        "issuer": g.issuer,
                        "days": g.days,
                        "cost_zar": g.cost_zar,
                        "smes": set(),
                        "opps": set(),
                        "sole": set(),
                    },
                )
                a["smes"].add(sme.id)
                a["opps"].add(opp.id)
                if len(gaps) == 1:  # this credential is the only thing in the way
                    a["sole"].add((sme.id, opp.id))
    rows = [
        {
            "credential": code,
            "label": a["label"],
            "issuer": a["issuer"],
            "days": a["days"],
            "cost_zar": a["cost_zar"],
            "smes_blocked": len(a["smes"]),
            "opportunities_blocked": len(a["opps"]),
            "value_locked": sum(value[o] for o in a["opps"]),
            "would_unlock": len(a["sole"]),
        }
        for code, a in agg.items()
    ]
    rows.sort(key=lambda r: (-r["value_locked"], -r["smes_blocked"]))
    locked = {o for a in agg.values() for o in a["opps"]}
    return {
        "rows": rows,
        "total_value_locked": sum(value[o] for o in locked),
        "smes_considered": len(smes),
        "opportunities_considered": len(everything),
    }


def consortium(db: Session, opportunity_id: uuid.UUID):
    open_opps = load_open_opportunities(db)
    opp = open_opps.get(opportunity_id)
    if opp is None:
        return None
    smes = load_smes(db)
    results = runner.match_all(opp, smes, list(open_opps.values()))
    return opp, smes, runner.consortium_for(opp, smes, results)
