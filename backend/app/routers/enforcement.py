"""Risk and enforcement: investigate, restrict, suspend, blacklist on review, appeal, reinstate.

Administrators only. Permanent blacklisting needs evidence and two different people: one
recommends, another approves. A severe case can be suspended at once, on the record, and is then
reviewed. Nothing here is decided by a score. Entities never see another entity's case.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import enforcement as enf
from .. import models as m
from ..audit import write_audit
from ..auth import current_user, require_role
from ..db import get_db
from ..schemas import AppealDecisionIn, AppealIn, CaseActionIn, CaseIn

router = APIRouter(prefix="/enforcement", tags=["enforcement"])
admin_only = Depends(require_role("admin"))


def _case_view(c: m.EnforcementCase, org: m.Organisation, db: Session) -> dict:
    return {
        "id": c.id,
        "ref": f"KM-{str(c.id)[:8].upper()}",
        "organisation_id": org.id,
        "organisation": org.name,
        "org_type": org.org_type,
        "registration_number": org.registration_number,
        "entity_status": org.enforcement_status,
        "restrictions": org.restrictions or [],
        "verification_status": org.verification_status,
        "reasons": [enf.REASONS.get(r, r) for r in c.reasons],
        "severity": c.severity,
        "notes": c.notes,
        "evidence": c.evidence or [],
        "status": c.status,
        "emergency": c.emergency,
        "emergency_reason": c.emergency_reason,
        "recommended_by": _name(db, c.recommended_by),
        "approved_by": _name(db, c.approved_by),
        "needs_second_person": c.status == "recommended",
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _name(db: Session, uid: uuid.UUID | None) -> str | None:
    u = db.get(m.User, uid) if uid else None
    return u.full_name if u else None


@router.get("/options")
def options(user: m.User = admin_only):
    return {"reasons": enf.REASONS, "restrictions": enf.RESTRICTIONS, "statuses": enf.STATUSES}


@router.get("/overview")
def overview(user: m.User = admin_only, db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(m.Organisation.enforcement_status, func.count()).group_by(
                m.Organisation.enforcement_status
            )
        ).all()
    )
    rows = db.execute(
        select(m.EnforcementCase, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.EnforcementCase.organisation_id)
        .order_by(m.EnforcementCase.updated_at.desc())
    ).all()
    appeals = db.execute(
        select(m.EnforcementAppeal, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.EnforcementAppeal.organisation_id)
        .order_by(m.EnforcementAppeal.created_at.desc())
    ).all()
    return {
        "counts": {s: counts.get(s, 0) for s in enf.STATUSES},
        "cases": [_case_view(c, o, db) for c, o in rows],
        "appeals": [
            {
                "id": a.id,
                "organisation": o.name,
                "text": a.text,
                "status": a.status,
                "decision_note": a.decision_note,
                "created_at": a.created_at,
            }
            for a, o in appeals
        ],
    }


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=80), user: m.User = admin_only, db: Session = Depends(get_db)):
    """Find an organisation by name, registration number, or the name, email or phone of its users."""
    like = f"%{q}%"
    orgs = db.scalars(
        select(m.Organisation)
        .where(
            or_(
                m.Organisation.name.ilike(like),
                m.Organisation.registration_number.ilike(like),
                m.Organisation.id.in_(
                    select(m.User.organisation_id).where(
                        or_(
                            m.User.email.ilike(like),
                            m.User.full_name.ilike(like),
                            m.User.phone.ilike(like),
                        ),
                        m.User.organisation_id.is_not(None),
                    )
                ),
            )
        )
        .limit(20)
    )
    return [
        {
            "id": o.id,
            "name": o.name,
            "org_type": o.org_type,
            "registration_number": o.registration_number,
            "status": o.enforcement_status,
        }
        for o in orgs
    ]


def _log(db, case, org, action, was, note, user):
    db.add(
        m.EnforcementAction(
            case_id=case.id,
            organisation_id=org.id,
            action=action,
            previous_status=was,
            new_status=org.enforcement_status,
            note=note,
            by_user=user.id,
        )
    )
    write_audit(
        db,
        user.id,
        f"enforcement_{action}",
        "organisation",
        org.id,
        old={"status": was},
        new={"status": org.enforcement_status, "case": str(case.id), "note": note[:200]},
    )


@router.post("/cases", status_code=201)
def open_case(body: CaseIn, user: m.User = admin_only, db: Session = Depends(get_db)):
    org = db.get(m.Organisation, body.organisation_id)
    if org is None:
        raise HTTPException(404, "Not found")
    if any(r not in enf.REASONS for r in body.reasons):
        raise HTTPException(422, "Unknown reason")
    case = m.EnforcementCase(
        organisation_id=org.id,
        reasons=body.reasons,
        severity=body.severity,
        notes=body.notes,
        evidence=[e.model_dump() for e in body.evidence],
        opened_by=user.id,
    )
    db.add(case)
    db.flush()
    was = org.enforcement_status
    if was in ("clear", "monitoring", "flagged", "reinstated"):
        enf.set_status(db, org, "under_review")
    _log(db, case, org, "open_case", was, body.notes, user)
    db.commit()
    return _case_view(case, org, db)


@router.get("/cases/{cid}")
def case_detail(cid: uuid.UUID, user: m.User = admin_only, db: Session = Depends(get_db)):
    case = db.get(m.EnforcementCase, cid)
    if case is None:
        raise HTTPException(404, "Not found")
    org = db.get(m.Organisation, case.organisation_id)
    history = db.scalars(
        select(m.EnforcementAction)
        .where(m.EnforcementAction.case_id == cid)
        .order_by(m.EnforcementAction.created_at.desc())
    )
    names = {}
    out = _case_view(case, org, db)
    out["history"] = []
    for h in history:
        names.setdefault(h.by_user, _name(db, h.by_user))
        out["history"].append(
            {
                "action": h.action,
                "from": h.previous_status,
                "to": h.new_status,
                "note": h.note,
                "by": names[h.by_user],
                "at": h.created_at,
            }
        )
    out["linked"] = _linked(db, org)
    return out


def _linked(db: Session, org: m.Organisation) -> list[dict]:
    """Other organisations sharing a document hash with this one. A reason to look, never a verdict."""
    hashes = select(m.Document.hash_value).where(m.Document.organisation_id == org.id)
    rows = db.execute(
        select(m.Organisation.id, m.Organisation.name)
        .join(m.Document, m.Document.organisation_id == m.Organisation.id)
        .where(m.Document.hash_value.in_(hashes), m.Organisation.id != org.id)
        .distinct()
    ).all()
    return [{"id": i, "name": n, "signal": "Same document file as this organisation"} for i, n in rows]


@router.post("/cases/{cid}/action")
def act(
    cid: uuid.UUID,
    body: CaseActionIn,
    user: m.User = admin_only,
    db: Session = Depends(get_db),
):
    case = db.get(m.EnforcementCase, cid)
    if case is None:
        raise HTTPException(404, "Not found")
    org = db.get(m.Organisation, case.organisation_id)
    a, note = body.action, body.note.strip()
    was = org.enforcement_status
    if case.status == "closed" and a not in ("reinstate",):
        raise HTTPException(409, "This case is closed")

    if a == "request_info":
        pass
    elif a == "add_evidence":
        if body.evidence is None:
            raise HTTPException(422, "Add the evidence")
        case.evidence = [*(case.evidence or []), body.evidence.model_dump()]
    elif a == "warn":
        enf.set_status(db, org, "flagged")
    elif a == "restrict":
        if not body.restrictions or any(r not in enf.RESTRICTIONS for r in body.restrictions):
            raise HTTPException(422, "Choose what to restrict")
        enf.set_status(db, org, "restricted", body.restrictions)
    elif a == "suspend":
        enf.set_status(db, org, "suspended")
    elif a == "emergency_suspend":
        # Allowed at once for a severe case, with no warning step. It is protective, not a verdict.
        if len(note) < 10:
            raise HTTPException(422, "Record why emergency suspension is needed")
        if case.severity not in ("high", "critical"):
            raise HTTPException(409, "Emergency suspension is for high or critical risk cases")
        enf.set_status(db, org, "suspended")
        case.emergency, case.emergency_reason = True, note
        case.emergency_at = datetime.now(UTC)
    elif a == "recommend_blacklist":
        if not case.evidence:
            raise HTTPException(409, "Permanent action needs evidence on the case")
        if len(note) < 10:
            raise HTTPException(422, "Give the justification")
        case.status, case.recommended_by = "recommended", user.id
    elif a == "approve_blacklist":
        if case.status != "recommended" or case.recommended_by is None:
            raise HTTPException(409, "A blacklist must be recommended first")
        if case.recommended_by == user.id:
            raise HTTPException(403, "Two people are needed: someone else must approve this")
        if len(note) < 10:
            raise HTTPException(422, "Give the justification")
        case.status, case.approved_by = "blacklisted", user.id
        enf.set_status(db, org, "blacklisted")
    elif a == "reject_blacklist":
        if case.status != "recommended":
            raise HTTPException(409, "There is no recommendation to reject")
        case.status = "open"
    elif a == "close":
        case.status = "closed"
        if org.enforcement_status in ("under_review", "flagged", "monitoring"):
            enf.set_status(db, org, "clear")
    elif a == "reinstate":
        if len(note) < 10:
            raise HTTPException(422, "Give the reason for reinstating")
        enf.set_status(db, org, "reinstated")
        case.status = "closed"
    _log(db, case, org, a, was, note, user)
    db.commit()
    return _case_view(case, org, db)


# ------------------------------------------------------------ the entity's own view and appeal


@router.get("/status")
def my_status(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """What an organisation may see about itself: its status and a case reference, nothing else."""
    org = db.get(m.Organisation, user.organisation_id) if user.organisation_id else None
    if org is None or org.enforcement_status in ("clear", "monitoring", "flagged", "under_review", "reinstated"):
        return {"status": "clear"}
    case = db.scalar(
        select(m.EnforcementCase)
        .where(m.EnforcementCase.organisation_id == org.id)
        .order_by(m.EnforcementCase.created_at.desc())
    )
    appeal = db.scalar(
        select(m.EnforcementAppeal)
        .where(m.EnforcementAppeal.organisation_id == org.id)
        .order_by(m.EnforcementAppeal.created_at.desc())
    )
    return {
        "status": org.enforcement_status,
        "restrictions": [enf.RESTRICTIONS[r] for r in (org.restrictions or []) if r in enf.RESTRICTIONS],
        "reference": f"KM-{str(case.id)[:8].upper()}" if case else None,
        "message": enf.SUSPENDED_MESSAGE if org.enforcement_status in enf.BLOCKED else None,
        "appeal": {"status": appeal.status, "note": appeal.decision_note} if appeal else None,
    }


@router.post("/appeal", status_code=201)
def appeal(body: AppealIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(m.Organisation, user.organisation_id) if user.organisation_id else None
    if org is None or org.enforcement_status not in ("restricted", "suspended", "blacklisted"):
        raise HTTPException(409, "There is nothing to appeal")
    open_one = db.scalar(
        select(m.EnforcementAppeal.id).where(
            m.EnforcementAppeal.organisation_id == org.id,
            m.EnforcementAppeal.status.in_(("submitted", "more_info")),
        )
    )
    if open_one:
        raise HTTPException(409, "You already have an appeal under review")
    case = db.scalar(
        select(m.EnforcementCase)
        .where(m.EnforcementCase.organisation_id == org.id)
        .order_by(m.EnforcementCase.created_at.desc())
    )
    a = m.EnforcementAppeal(case_id=case.id if case else None, organisation_id=org.id, text=body.text)
    db.add(a)
    db.flush()
    write_audit(db, user.id, "enforcement_appeal", "organisation", org.id)
    db.commit()
    return {"id": a.id, "status": a.status}


@router.post("/appeals/{aid}/decide")
def decide_appeal(
    aid: uuid.UUID,
    body: AppealDecisionIn,
    user: m.User = admin_only,
    db: Session = Depends(get_db),
):
    a = db.get(m.EnforcementAppeal, aid)
    if a is None:
        raise HTTPException(404, "Not found")
    a.status = {"approve": "approved", "reject": "rejected", "more_info": "more_info"}[body.decision]
    a.decided_by, a.decision_note, a.decided_at = user.id, body.note, datetime.now(UTC)
    org = db.get(m.Organisation, a.organisation_id)
    if body.decision == "approve":
        was = enf.set_status(db, org, "reinstated")
        case = db.get(m.EnforcementCase, a.case_id) if a.case_id else None
        if case:
            case.status = "closed"
            _log(db, case, org, "reinstate", was, f"Appeal approved: {body.note}", user)
    write_audit(db, user.id, f"enforcement_appeal_{a.status}", "organisation", org.id)
    db.commit()
    return {"status": a.status}
