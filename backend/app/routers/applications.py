"""The journey after matching: an SME applies, the provider sees it and decides on the match."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from .. import notifications
from ..audit import write_audit
from ..auth import PROVIDER_ROLES, current_user, require_role
from ..db import get_db
from ..schemas import AwardIn

router = APIRouter(prefix="/applications", tags=["applications"])


def application_status(match: m.Match, app: m.Application | None) -> str | None:
    """One status the UI can show: the provider's decision wins once it is made."""
    if app is None:
        return None
    return {"shortlisted": "shortlisted", "rejected": "declined", "awarded": "awarded"}.get(
        match.status, app.status
    )


@router.post("/{match_id}", status_code=201)
def apply(
    match_id: uuid.UUID,
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    match = db.get(m.Match, match_id)
    if match is None or match.sme_id != user.organisation_id:
        raise HTTPException(404, "Not found")  # same answer for "missing" and "not yours"
    if match.status == "rejected":
        raise HTTPException(409, "This match was declined by the provider")
    if db.get(m.Opportunity, match.opportunity_id).status != "open":
        raise HTTPException(409, "This opportunity is closed")
    app = m.Application(match_id=match.id)
    db.add(app)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You have already applied") from None
    write_audit(
        db, user.id, "application_submit", "application", app.id, new={"match_id": str(match.id)}
    )
    db.commit()
    notifications.application_received(db, match)
    return {"id": app.id, "status": "submitted"}


@router.get("")
def list_applications(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    q = (
        select(m.Application, m.Match, m.Opportunity, m.Organisation)
        .join(m.Match, m.Match.id == m.Application.match_id)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .join(m.Organisation, m.Organisation.id == m.Match.sme_id)
        .order_by(m.Application.submitted_at.desc())
    )
    if user.role == "sme":
        q = q.where(m.Match.sme_id == user.organisation_id)
    elif user.role in PROVIDER_ROLES:
        q = q.where(m.Opportunity.organisation_id == user.organisation_id)
    elif user.role != "admin":
        raise HTTPException(403, "Role not permitted")
    return [
        {
            "id": a.id,
            "match_id": mt.id,
            "opportunity": o.title,
            "sme": org.name,
            "status": application_status(mt, a),
            "fit": float(mt.fit_score),
            "readiness": float(mt.readiness_score),
            "quadrant": mt.quadrant,
            "submitted_at": a.submitted_at,
        }
        for a, mt, o, org in db.execute(q)
    ]


@router.post("/{match_id}/award")
def award(
    match_id: uuid.UUID,
    body: AwardIn,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    """Record an award. The SME must be shortlisted first. The scores at that moment are frozen
    into the append-only audit log, and the SME is told."""
    from datetime import UTC, datetime

    from ..services import decision_snapshot

    match = db.get(m.Match, match_id)
    opp = db.get(m.Opportunity, match.opportunity_id) if match else None
    if match is None or opp.organisation_id != user.organisation_id:
        raise HTTPException(404, "Not found")
    if match.status == "awarded":
        raise HTTPException(409, "Already awarded")
    if match.status != "shortlisted":
        raise HTTPException(409, "Shortlist the SME before awarding")
    now = datetime.now(UTC)
    app = db.scalar(select(m.Application).where(m.Application.match_id == match.id))
    if app is None:
        app = m.Application(match_id=match.id)
        db.add(app)
    app.status = "awarded"
    app.awarded_value = body.value
    app.awarded_at = now
    app.decided_at = now
    app.gate_at_award = match.gate
    app.quadrant_at_award = match.quadrant
    match.status = "awarded"
    db.flush()
    write_audit(
        db,
        user.id,
        "match_awarded",
        "match",
        match.id,
        old={"status": "shortlisted"},
        new={"status": "awarded", "value": body.value, "snapshot": decision_snapshot(match)},
    )
    db.commit()
    notifications.match_awarded(db, match, body.value)
    return {"match_id": match.id, "status": "awarded", "value": body.value}
