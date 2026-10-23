"""Human review: the AI ranks, a human decides. Every decision writes a reviewer-stamped audit row."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..audit import write_audit
from ..auth import require_role
from ..db import get_db
from ..schemas import ReviewIn

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@router.get("/queue")
def queue(db: Session = Depends(get_db)):
    verifications = db.execute(
        select(m.Verification, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.Verification.subject_id, isouter=True)
        .where(m.Verification.flagged.is_(True), m.Verification.review_status.is_(None))
        .order_by(m.Verification.checked_at.desc())
    ).all()
    doc_info = {
        d.id: (o.name, d.document_type)
        for d, o in db.execute(
            select(m.Document, m.Organisation).join(
                m.Organisation, m.Organisation.id == m.Document.organisation_id
            )
        )
    }
    matches = db.execute(
        select(m.Match, m.Organisation, m.Opportunity)
        .join(m.Organisation, m.Organisation.id == m.Match.sme_id)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .where(m.Match.flagged.is_(True), m.Match.review_status.is_(None))
    ).all()
    return {
        "verifications": [
            {
                "id": v.id,
                "subject_type": v.subject_type,
                "organisation": org.name if org else doc_info.get(v.subject_id, (None, None))[0],
                "document_type": doc_info.get(v.subject_id, (None, None))[1],
                "result": v.result,
                "source_label": v.source_label,
                "checked_at": v.checked_at,
            }
            for v, org in verifications
        ],
        "matches": [
            {
                "id": mt.id,
                "sme": org.name,
                "opportunity": opp.title,
                "fit": float(mt.fit_score),
                "readiness": float(mt.readiness_score),
                "reason": "SME has an unresolved verification flag",
            }
            for mt, org, opp in matches
        ],
    }


@router.post("/verifications/{vid}/review")
def review_verification(
    vid: uuid.UUID,
    body: ReviewIn,
    admin: m.User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    v = db.get(m.Verification, vid)
    if v is None:
        raise HTTPException(404, "Not found")
    old = v.review_status
    v.review_status = body.decision
    v.reviewed_by = admin.id
    if v.subject_type == "document" and body.decision == "rejected":
        doc = db.get(m.Document, v.subject_id)
        if doc:
            doc.review_status = "rejected"  # the engine then treats the credential as missing
    if v.subject_type == "organisation":
        org = db.get(m.Organisation, v.subject_id)
        still_open = db.scalar(
            select(m.Verification.id).where(
                m.Verification.subject_id == org.id,
                m.Verification.flagged.is_(True),
                m.Verification.review_status.is_(None),
                m.Verification.id != v.id,
            )
        )
        if body.decision == "rejected":
            org.verification_status = "rejected"
        elif not still_open:
            org.verification_status = "verified"
    write_audit(
        db,
        admin.id,
        "verification_review",
        "verification",
        v.id,
        old={"review_status": old},
        new={"review_status": body.decision, "note": body.note},
    )
    db.commit()
    return {"id": v.id, "review_status": v.review_status}


@router.post("/matches/{mid}/review")
def review_match(
    mid: uuid.UUID,
    body: ReviewIn,
    admin: m.User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    mt = db.get(m.Match, mid)
    if mt is None:
        raise HTTPException(404, "Not found")
    old = mt.review_status
    mt.review_status = body.decision
    if body.decision == "rejected":
        mt.status = "rejected"
    write_audit(
        db,
        admin.id,
        "match_review",
        "match",
        mt.id,
        old={"review_status": old},
        new={"review_status": body.decision, "note": body.note},
    )
    db.commit()
    return {"id": mt.id, "review_status": mt.review_status}


@router.get("/audit")
def audit_trail(
    entity_type: str = Query(max_length=40),
    entity_id: str = Query(max_length=64),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(m.AuditLog)
        .where(m.AuditLog.entity_type == entity_type, m.AuditLog.entity_id == entity_id)
        .order_by(m.AuditLog.timestamp.desc())
        .limit(200)
    )
    return [
        {
            "action": a.action,
            "user_id": a.user_id,
            "old": a.old_value,
            "new": a.new_value,
            "timestamp": a.timestamp,
        }
        for a in rows
    ]


@router.post("/reminders/run")
def run_reminders(db: Session = Depends(get_db)):
    """Send document expiry reminders now. Also runnable on a schedule: scripts/send_reminders.py."""
    from .. import reminders

    return reminders.run(db)


@router.get("/ecosystem")
def ecosystem(db: Session = Depends(get_db)):
    """The programme view for YES: demand, supply, gaps and outcomes. Aggregates only."""
    from .. import insights

    return insights.ecosystem(db)
