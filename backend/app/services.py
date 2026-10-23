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


def rematch_for_sme(db: Session, org_id: uuid.UUID) -> int:
    """Re-score every opportunity this business already has a match on, so a new or renewed
    document shows in its numbers at once. Shortlist and award status are kept. The caller commits."""
    ids = list(
        db.scalars(select(m.Match.opportunity_id).where(m.Match.sme_id == org_id).distinct())
    )
    for oid in ids:
        run_matching(db, oid)
    return len(ids)


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


def labels_for(codes: list[str] | None) -> list[str]:
    from .engine.taxonomy import CAPABILITIES

    return [CAPABILITIES.get(c, ("", c))[1] for c in (codes or [])]


def consortium_invitation(db: Session, opportunity_id: uuid.UUID) -> dict | None:
    """The latest invitation for an opportunity, with every member's name and answer (buyer view)."""
    cons = db.scalar(
        select(m.Consortium)
        .where(m.Consortium.opportunity_id == opportunity_id)
        .order_by(m.Consortium.created_at.desc())
        .limit(1)
    )
    if cons is None:
        return None
    members = list(
        db.scalars(select(m.ConsortiumMember).where(m.ConsortiumMember.consortium_id == cons.id))
    )
    names = {
        o.id: o.name
        for o in db.scalars(
            select(m.Organisation).where(m.Organisation.id.in_([x.sme_id for x in members]))
        )
    }
    return {
        "id": cons.id,
        "status": cons.status,
        "coverage_pct": float(cons.coverage_pct),
        "members": [
            {
                "sme_id": x.sme_id,
                "name": names[x.sme_id],
                "role": x.role,
                "scope": labels_for(x.scope_codes),
                "response": x.response,
            }
            for x in members
        ],
    }


def decision_snapshot(match: m.Match) -> dict:
    """A frozen copy of what the decision-maker saw. Stored in the append-only audit log."""
    return {
        "model_version": match.model_version,
        "gate": match.gate,
        "quadrant": match.quadrant,
        "fit": float(match.fit_score),
        "readiness": float(match.readiness_score),
        "components": match.explanation.get("components"),
        "gaps": match.explanation.get("gaps"),
        "risk_flags": match.risk_flags,
    }


def simulate(db: Session, org_id: uuid.UUID, credentials: list[str]) -> dict | None:
    """What changes if this SME obtains these credentials. Same rules, same catalogue, no guessing."""
    from dataclasses import replace

    from .engine.runner import match_one
    from .engine.taxonomy import COMPLIANCE_CATALOGUE
    from .engine.types import Gate

    sme = next((s for s in load_smes(db, only_visible=False) if s.id == str(org_id)), None)
    if sme is None:
        return None
    everything = list(load_open_opportunities(db).values())
    titles = {
        str(o.id): (o.title, float(o.contract_value))
        for o in db.scalars(select(m.Opportunity).where(m.Opportunity.status == "open"))
    }

    def with_docs(codes: list[str]):
        return replace(sme, documents={**sme.documents, **{c: DocStatus.VALID for c in codes}})

    def evaluate(variant):
        ready, value, rows = 0, 0.0, {}
        for opp in everything:
            r = match_one(opp, variant, everything)
            if r.gate == Gate.FAIL:
                continue
            title, worth = titles[opp.id]
            now = r.quadrant == "award_now"
            ready += now
            value += worth if now else 0
            rows[opp.id] = (r, title, worth)
        return ready, value, rows

    def view(r):
        return {
            "quadrant": r.quadrant,
            "fit": r.fit,
            "readiness": r.readiness,
            "gate": r.gate.value,
        }

    b_ready, b_value, b_rows = evaluate(sme)
    a_ready, a_value, a_rows = evaluate(with_docs(credentials))
    rows = []
    for oid in sorted(set(b_rows) | set(a_rows)):
        before = b_rows.get(oid)
        after = a_rows[oid]
        rows.append(
            {
                "opportunity_id": oid,
                "title": after[1],
                "contract_value": after[2],
                "before": view(before[0]) if before else None,
                "after": view(after[0]),
                "newly_award_ready": after[0].quadrant == "award_now"
                and not (before and before[0].quadrant == "award_now"),
            }
        )
    chosen, routes = [], []
    for code in credentials:
        c = COMPLIANCE_CATALOGUE[code]
        status = sme.documents.get(code, DocStatus.MISSING)
        if status == DocStatus.VALID:
            continue
        days = c.renew_days if status == DocStatus.EXPIRED else c.days
        item = {
            "code": code,
            "label": c.label,
            "issuer": c.issuer,
            "days": days,
            "cost_zar": c.cost_zar,
        }
        chosen.append(item)
        one_ready, one_value, _ = evaluate(with_docs([code]))
        routes.append(
            {**item, "gain_value": one_value - b_value, "newly_award_ready": one_ready - b_ready}
        )
    # Best first move: the most contract value unlocked per day of waiting
    routes.sort(key=lambda r: (-(r["gain_value"] / max(r["days"], 1)), r["days"]))
    return {
        "selected": chosen,
        # Credentials are obtained in parallel, so the wait is the longest one
        "total_days": max((c["days"] for c in chosen), default=0),
        "total_cost_zar": sum(c["cost_zar"] for c in chosen),
        "before": {"award_ready": b_ready, "value": b_value},
        "after": {"award_ready": a_ready, "value": a_value},
        "routes": routes,
        "opportunities": sorted(
            rows, key=lambda r: (not r["newly_award_ready"], -r["contract_value"])
        ),
    }


def impact(db: Session, org_id: uuid.UUID | None) -> dict:
    """What actually reached SMEs: awards, value, who, how fast, and how many a strict filter would
    have turned away. Aggregates only, no names. org_id None means every provider (admin)."""
    import statistics

    q = (
        select(m.Application, m.Match, m.Opportunity, m.SmeProfile)
        .join(m.Match, m.Match.id == m.Application.match_id)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .join(m.SmeProfile, m.SmeProfile.organisation_id == m.Match.sme_id)
    )
    if org_id is not None:
        q = q.where(m.Opportunity.organisation_id == org_id)
    rows = list(db.execute(q))
    awarded = [r for r in rows if r[0].awarded_at is not None]
    total = sum(float(a.awarded_value) for a, *_ in awarded)

    def share(flag: str) -> dict:
        hit = [(a, p) for a, _, _, p in awarded if flag in (p.ownership or [])]
        value = sum(float(a.awarded_value) for a, _ in hit)
        return {
            "awards": len(hit),
            "value": value,
            "share_pct": round(100 * value / total, 1) if total else 0.0,
        }

    def by(key) -> list[dict]:
        out: dict[str, float] = {}
        for a, mt, o, p in awarded:
            out[key(o, p)] = out.get(key(o, p), 0.0) + float(a.awarded_value)
        return [{"name": k, "value": v} for k, v in sorted(out.items(), key=lambda kv: -kv[1])]

    days = [(a.awarded_at - o.created_at).days for a, _, o, _ in awarded]
    gap = [a for a, *_ in awarded if a.gate_at_award == "remediable"]
    return {
        "applications": len(rows),
        "awards": len(awarded),
        "smes_awarded": len({mt.sme_id for _, mt, _, _ in awarded}),
        "value_awarded": total,
        "conversion_pct": round(100 * len(awarded) / len(rows), 1) if rows else 0.0,
        "days_to_award_median": statistics.median(days) if days else None,
        "days_to_award_mean": round(sum(days) / len(days), 1) if days else None,
        "awarded_despite_gap": {
            "awards": len(gap),
            "value": sum(float(a.awarded_value) for a in gap),
            "meaning": "Awarded to businesses that still had a document gap, so a strict "
            "'must hold every document' filter would have rejected them.",
        },
        "ownership": {f: share(f) for f in ("youth", "black", "black_women")},
        "by_province": by(lambda o, p: p.province),
        "by_sector": by(lambda o, p: o.sector),
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
