"""Structured feedback after an award: buyers rate, businesses respond or dispute, a reviewer decides.

Feedback is tied to an awarded application, so it cannot be left by someone with no history with
the business. One review per award. A business sees everything said about it and can answer.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import insights, notifications
from .. import models as m
from ..audit import write_audit
from ..auth import PROVIDER_ROLES, require_role
from ..db import get_db
from ..schemas import FeedbackIn, FeedbackResolveIn, FeedbackResponseIn

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _view(f: m.Feedback, names: dict) -> dict:
    return {
        "id": f.id,
        "sme": names.get(f.sme_id),
        "provider": names.get(f.provider_org_id),
        "ratings": f.ratings,
        "comment": f.comment,
        "status": f.status,
        "response": f.sme_response,
        "dispute_reason": f.dispute_reason,
        "resolution_note": f.resolution_note,
        "created_at": f.created_at,
    }


def _names(db: Session, rows: list[m.Feedback]) -> dict:
    ids = {x for f in rows for x in (f.sme_id, f.provider_org_id)}
    if not ids:
        return {}
    return {
        o.id: o.name for o in db.scalars(select(m.Organisation).where(m.Organisation.id.in_(ids)))
    }


@router.get("/awaiting")
def awaiting(user: m.User = Depends(require_role(*PROVIDER_ROLES)), db: Session = Depends(get_db)):
    """Awards this buyer has made and not yet reviewed."""
    rows = db.execute(
        select(m.Application, m.Match, m.Opportunity, m.Organisation)
        .join(m.Match, m.Match.id == m.Application.match_id)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .join(m.Organisation, m.Organisation.id == m.Match.sme_id)
        .where(
            m.Opportunity.organisation_id == user.organisation_id,
            m.Application.awarded_at.is_not(None),
            ~select(m.Feedback.id).where(m.Feedback.application_id == m.Application.id).exists(),
        )
        .order_by(m.Application.awarded_at.desc())
    ).all()
    return [
        {
            "application_id": a.id,
            "sme": org.name,
            "opportunity": opp.title,
            "awarded_value": float(a.awarded_value or 0),
            "awarded_at": a.awarded_at,
        }
        for a, _, opp, org in rows
    ]


@router.get("/given")
def given(user: m.User = Depends(require_role(*PROVIDER_ROLES)), db: Session = Depends(get_db)):
    rows = list(
        db.scalars(
            select(m.Feedback)
            .where(m.Feedback.provider_org_id == user.organisation_id)
            .order_by(m.Feedback.created_at.desc())
        )
    )
    names = _names(db, rows)
    return [_view(f, names) for f in rows]


@router.get("/mine")
def mine(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    rows = list(
        db.scalars(
            select(m.Feedback)
            .where(m.Feedback.sme_id == user.organisation_id)
            .order_by(m.Feedback.created_at.desc())
        )
    )
    names = _names(db, rows)
    return {
        "items": [_view(f, names) for f in rows],
        "performance": insights.performance(db, user.organisation_id),
    }


@router.get("/disputes")
def disputes(user: m.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(m.Feedback).where(m.Feedback.status == "disputed")))
    names = _names(db, rows)
    return [_view(f, names) for f in rows]


@router.get("/performance/{sme_org_id}")
def track_record(
    sme_org_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    """A buyer sees the track record of a business that has chosen to be visible."""
    profile = db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == sme_org_id))
    if profile is None or (user.role != "admin" and not profile.visible_to_corporates):
        raise HTTPException(404, "Not found")
    return insights.performance(db, sme_org_id)


@router.post("/{application_id}", status_code=201)
def leave(
    application_id: uuid.UUID,
    body: FeedbackIn,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    app = db.get(m.Application, application_id)
    match = db.get(m.Match, app.match_id) if app else None
    opp = db.get(m.Opportunity, match.opportunity_id) if match else None
    if app is None or opp.organisation_id != user.organisation_id:
        raise HTTPException(404, "Not found")
    if app.awarded_at is None:
        raise HTTPException(409, "Feedback can be left once the work has been awarded")
    if db.scalar(select(m.Feedback.id).where(m.Feedback.application_id == app.id)):
        raise HTTPException(409, "Feedback has already been left for this award")
    fb = m.Feedback(
        application_id=app.id,
        sme_id=match.sme_id,
        provider_org_id=user.organisation_id,
        author_id=user.id,
        ratings=body.ratings,
        comment=body.comment,
    )
    db.add(fb)
    db.flush()
    write_audit(db, user.id, "feedback_left", "feedback", fb.id, new={"ratings": body.ratings})
    db.commit()
    notifications.feedback_received(db, fb)
    return {"id": fb.id, "status": fb.status}


def _own_feedback(db: Session, user: m.User, fid: uuid.UUID) -> m.Feedback:
    fb = db.get(m.Feedback, fid)
    if fb is None or fb.sme_id != user.organisation_id:
        raise HTTPException(404, "Not found")
    return fb


@router.post("/{fid}/respond")
def respond(
    fid: uuid.UUID,
    body: FeedbackResponseIn,
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    fb = _own_feedback(db, user, fid)
    if fb.sme_response:
        raise HTTPException(409, "You have already responded")
    fb.sme_response = body.text
    fb.responded_at = datetime.now(UTC)
    if fb.status == "published":
        fb.status = "responded"
    write_audit(db, user.id, "feedback_responded", "feedback", fb.id)
    db.commit()
    notifications.feedback_answered(db, fb, disputed=False)
    return {"status": fb.status}


@router.post("/{fid}/dispute")
def dispute(
    fid: uuid.UUID,
    body: FeedbackResponseIn,
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    fb = _own_feedback(db, user, fid)
    if fb.status in ("disputed", "upheld", "removed"):
        raise HTTPException(409, "This feedback has already been disputed")
    fb.status = "disputed"
    fb.dispute_reason = body.text
    write_audit(db, user.id, "feedback_disputed", "feedback", fb.id)
    db.commit()
    notifications.feedback_answered(db, fb, disputed=True)
    return {"status": fb.status}


@router.post("/{fid}/resolve")
def resolve(
    fid: uuid.UUID,
    body: FeedbackResolveIn,
    user: m.User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    fb = db.get(m.Feedback, fid)
    if fb is None:
        raise HTTPException(404, "Not found")
    if fb.status != "disputed":
        raise HTTPException(409, "Only a disputed review can be resolved")
    fb.status = "removed" if body.decision == "remove" else "upheld"
    fb.resolved_by = user.id
    fb.resolution_note = body.note
    fb.resolved_at = datetime.now(UTC)
    write_audit(
        db,
        user.id,
        "feedback_resolved",
        "feedback",
        fb.id,
        new={"decision": body.decision, "note": body.note},
    )
    db.commit()
    notifications.feedback_resolved(db, fb)
    return {"status": fb.status}
