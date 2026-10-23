import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..audit import write_audit
from ..auth import KINDS_BY_ROLE, PROVIDER_ROLES, current_user, require_role
from ..db import get_db
from ..llm import client, prompts
from ..schemas import ExtractIn, OpportunityIn
from ..services import consortium as build_consortium
from ..services import consortium_invitation
from ..services import run_matching

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _summary(o: m.Opportunity, provider_name: str | None = None) -> dict:
    return {
        "id": o.id,
        "title": o.title,
        "sector": o.sector,
        "province": o.province,
        "contract_value": float(o.contract_value),
        "duration_months": o.duration_months,
        "status": o.status,
        "kind": o.kind,
        "deadline": o.deadline,
        "provider": provider_name,
    }


def owned_opportunity(db: Session, user: m.User, opp_id: uuid.UUID) -> m.Opportunity:
    """Object-level authorisation: a corporate only reaches its own opportunities."""
    o = db.get(m.Opportunity, opp_id)
    if o is None or (user.role != "admin" and o.organisation_id != user.organisation_id):
        raise HTTPException(404, "Not found")
    return o


@router.post("", status_code=201)
def create(
    body: OpportunityIn,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    if body.kind not in KINDS_BY_ROLE[user.role]:
        raise HTTPException(
            422, f"A {user.role} account can post: {', '.join(KINDS_BY_ROLE[user.role])}"
        )
    o = m.Opportunity(
        organisation_id=user.organisation_id,
        kind=body.kind,
        description=body.description,
        deadline=body.deadline,
        title=body.title,
        sector=body.sector,
        province=body.province,
        contract_value=body.contract_value,
        duration_months=body.duration_months,
        payment_terms_days=body.payment_terms_days,
        scope_items=[i.model_dump() for i in body.scope_items],
        transformation_gap=body.transformation_gap,
    )
    db.add(o)
    db.flush()
    for r in body.requirements:
        db.add(
            m.OpportunityRequirement(
                opportunity_id=o.id,
                requirement_type=r.requirement_type.value,
                requirement_value=r.requirement_value,
                mandatory=r.mandatory,
                weight=r.weight,
            )
        )
    write_audit(
        db,
        user.id,
        "opportunity_create",
        "opportunity",
        o.id,
        new={"title": o.title, "requirements": len(body.requirements)},
    )
    db.commit()
    return _summary(o)


@router.post("/extract")
def extract(body: ExtractIn, user: m.User = Depends(require_role(*PROVIDER_ROLES))):
    prompt = prompts.EXTRACT_REQUIREMENTS.format(
        sectors=sorted({*prompts.SECTORS}),
        provinces=prompts.PROVINCES,
        docs=sorted(prompts.COMPLIANCE_CATALOGUE),
        codes=sorted(prompts.CAPABILITIES),
        text=body.text,
    )
    result = client.call(prompt, prompts.RequirementExtraction)
    if result is None:
        return {"source": "fallback", "draft": prompts.RequirementExtraction().model_dump()}
    return {"source": "llm", "draft": result.model_dump()}


@router.get("")
def list_opportunities(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(m.Opportunity).order_by(m.Opportunity.created_at.desc())
    if user.role in PROVIDER_ROLES:
        q = q.where(m.Opportunity.organisation_id == user.organisation_id)
    elif user.role == "sme":
        q = q.where(m.Opportunity.status == "open")
    elif user.role != "admin":
        raise HTTPException(403, "Role not permitted")
    opps = list(db.scalars(q))
    counts: dict[uuid.UUID, Counter] = {}
    if user.role in (*PROVIDER_ROLES, "admin"):
        for opp_id, quadrant in db.execute(select(m.Match.opportunity_id, m.Match.quadrant)):
            counts.setdefault(opp_id, Counter())[quadrant] += 1
    names = {i: n for i, n in db.execute(select(m.Organisation.id, m.Organisation.name))}
    return [
        {
            **_summary(o, names.get(o.organisation_id)),
            **({"quadrants": dict(counts.get(o.id, {}))} if user.role != "sme" else {}),
        }
        for o in opps
    ]


@router.get("/{opp_id}")
def detail(opp_id: uuid.UUID, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "sme":
        o = db.get(m.Opportunity, opp_id)
        if o is None or o.status != "open":
            raise HTTPException(404, "Not found")
    else:
        o = owned_opportunity(db, user, opp_id)
    reqs = db.scalars(
        select(m.OpportunityRequirement).where(m.OpportunityRequirement.opportunity_id == o.id)
    )
    return {
        **_summary(o, db.get(m.Organisation, o.organisation_id).name),
        "description": o.description,
        "payment_terms_days": o.payment_terms_days,
        "scope_items": o.scope_items,
        "transformation_gap": o.transformation_gap,
        "requirements": [
            {
                "id": r.id,
                "requirement_type": r.requirement_type,
                "requirement_value": r.requirement_value,
                "mandatory": r.mandatory,
                "weight": r.weight,
            }
            for r in reqs
        ],
    }


def _match_row(match: m.Match, org: m.Organisation) -> dict:
    return {
        "match_id": match.id,
        "sme_id": match.sme_id,
        "sme_name": org.name,
        "verification_status": org.verification_status,
        "gate": match.gate,
        "quadrant": match.quadrant,
        "fit": float(match.fit_score),
        "readiness": float(match.readiness_score),
        "overall": float(match.overall_score),
        "risk_flags": match.risk_flags,
        "gap_count": len(match.explanation.get("gaps", [])),
        "status": match.status,
    }


@router.post("/{opp_id}/match")
def run_match(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    o = owned_opportunity(db, user, opp_id)
    saved = run_matching(db, o.id)
    write_audit(
        db,
        user.id,
        "match_run",
        "opportunity",
        o.id,
        new={"matches": len(saved), "model_version": "v1"},
    )
    db.commit()
    return _ranked(db, o.id)


@router.get("/{opp_id}/matches")
def matches(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    o = owned_opportunity(db, user, opp_id)
    return _ranked(db, o.id)


def _ranked(db: Session, opp_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(m.Match, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.Match.sme_id)
        .where(m.Match.opportunity_id == opp_id)
        .order_by(m.Match.overall_score.desc())
    ).all()
    return [_match_row(match, org) for match, org in rows]


@router.get("/{opp_id}/consortium")
def consortium(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    o = owned_opportunity(db, user, opp_id)
    built = build_consortium(db, o.id)
    if built is None:
        raise HTTPException(404, "Not found")
    _, smes, c = built
    invitation = consortium_invitation(db, o.id)
    if c is None:
        return {"consortium": None, "invitation": invitation}
    names = {s.id: s.name for s in smes}
    return {
        "consortium": {
            "lead": {"sme_id": c.lead_sme_id, "name": names[c.lead_sme_id]},
            "members": [{"sme_id": i, "name": names[i]} for i in c.member_sme_ids],
            "coverage_pct": c.coverage_pct,
            "uncovered_codes": c.uncovered_codes,
        },
        "invitation": invitation,
    }
