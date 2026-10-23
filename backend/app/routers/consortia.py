"""Consortium invitations: turn a proposed group of SMEs into one that has actually said yes.

Privacy by design: an invited SME sees its own part and how many partners there are, but not their
names. Names are shared with the members only once every one of them has accepted. The buyer sees
all names from the start, since it already sees every match.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import notifications
from ..audit import write_audit
from ..auth import PROVIDER_ROLES, require_role
from ..db import get_db
from ..engine.scoring import covered_codes
from ..schemas import RespondIn
from ..services import consortium as build_consortium
from ..services import consortium_invitation, labels_for
from .opportunities import owned_opportunity

router = APIRouter(tags=["consortia"])


@router.post("/opportunities/{opp_id}/consortium/invite", status_code=201)
def invite(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    opp = owned_opportunity(db, user, opp_id)
    live = db.scalar(
        select(m.Consortium.id).where(
            m.Consortium.opportunity_id == opp.id, m.Consortium.status.in_(("proposed", "formed"))
        )
    )
    if live:
        raise HTTPException(409, "A consortium invitation is already open for this opportunity")
    built = build_consortium(db, opp.id)
    if built is None or built[2] is None:
        raise HTTPException(422, "No consortium can be assembled for this opportunity")
    engine_opp, smes, c = built
    by_id = {s.id: s for s in smes}
    assigned: set[str] = set()
    parts = []
    for sme_id in c.member_sme_ids:  # each scope line goes to the first member that covers it
        codes = sorted(covered_codes(engine_opp, by_id[sme_id]) - assigned)
        assigned.update(codes)
        parts.append((sme_id, codes))
    cons = m.Consortium(
        opportunity_id=opp.id,
        proposed_by=user.id,
        lead_sme_id=uuid.UUID(c.lead_sme_id),
        coverage_pct=c.coverage_pct,
    )
    db.add(cons)
    db.flush()
    for sme_id, codes in parts:
        db.add(
            m.ConsortiumMember(
                consortium_id=cons.id,
                sme_id=uuid.UUID(sme_id),
                role="lead" if sme_id == c.lead_sme_id else "member",
                scope_codes=codes,
            )
        )
    write_audit(
        db,
        user.id,
        "consortium_invited",
        "consortium",
        cons.id,
        new={"opportunity": str(opp.id), "members": len(parts), "coverage_pct": c.coverage_pct},
    )
    db.commit()
    notifications.consortium_invited(db, cons)
    return consortium_invitation(db, opp.id)


@router.get("/consortia")
def my_invitations(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    """Invitations addressed to my business. Partner names appear only once the group has formed."""
    rows = db.execute(
        select(m.ConsortiumMember, m.Consortium, m.Opportunity)
        .join(m.Consortium, m.Consortium.id == m.ConsortiumMember.consortium_id)
        .join(m.Opportunity, m.Opportunity.id == m.Consortium.opportunity_id)
        .where(m.ConsortiumMember.sme_id == user.organisation_id)
        .order_by(m.Consortium.created_at.desc())
    ).all()
    out = []
    for me, cons, opp in rows:
        members = list(
            db.scalars(
                select(m.ConsortiumMember).where(m.ConsortiumMember.consortium_id == cons.id)
            )
        )
        names = {
            o.id: o.name
            for o in db.scalars(
                select(m.Organisation).where(m.Organisation.id.in_([x.sme_id for x in members]))
            )
        }
        formed = cons.status == "formed"
        out.append(
            {
                "id": cons.id,
                "status": cons.status,
                "opportunity": {
                    "id": opp.id,
                    "title": opp.title,
                    "contract_value": float(opp.contract_value),
                    "provider": db.get(m.Organisation, opp.organisation_id).name,
                },
                "my_role": me.role,
                "my_part": labels_for(me.scope_codes),
                "my_response": me.response,
                "partners": len(members) - 1,
                "accepted": sum(1 for x in members if x.response == "accepted"),
                "coverage_pct": float(cons.coverage_pct),
                "partner_names": [names[x.sme_id] for x in members if x.sme_id != me.sme_id]
                if formed
                else [],
            }
        )
    return out


@router.post("/consortia/{consortium_id}/respond")
def respond(
    consortium_id: uuid.UUID,
    body: RespondIn,
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    cons = db.get(m.Consortium, consortium_id)
    me = (
        db.scalar(
            select(m.ConsortiumMember).where(
                m.ConsortiumMember.consortium_id == consortium_id,
                m.ConsortiumMember.sme_id == user.organisation_id,
            )
        )
        if cons
        else None
    )
    if me is None:
        raise HTTPException(404, "Not found")  # not invited: same answer as not existing
    if cons.status != "proposed":
        raise HTTPException(409, "This invitation is no longer open")
    if me.response != "pending":
        raise HTTPException(409, "You have already responded")
    now = datetime.now(UTC)
    me.response = "accepted" if body.accept else "declined"
    me.responded_at = now
    members = list(
        db.scalars(select(m.ConsortiumMember).where(m.ConsortiumMember.consortium_id == cons.id))
    )
    if not body.accept:
        cons.status, cons.resolved_at = "declined", now
    elif all(x.response == "accepted" for x in members):
        cons.status, cons.resolved_at = "formed", now
    write_audit(
        db,
        user.id,
        "consortium_response",
        "consortium",
        cons.id,
        new={"response": me.response, "consortium_status": cons.status},
    )
    db.commit()
    notifications.consortium_response(db, cons, me)
    return {"status": cons.status, "my_response": me.response}
