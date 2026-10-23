from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..adapters.mock import registry_provider, tax_provider
from .. import notifications, ratelimit
from ..audit import write_audit
from ..auth import current_user, hash_password, issue_token, verify_password
from ..config import settings
from ..db import get_db
from ..schemas import RegisterIn
from .documents import purge_organisation_files

router = APIRouter(tags=["auth"])

# Compared against when the email is unknown, so response time does not reveal which emails exist
_DUMMY_HASH = hash_password("not-a-real-password")


def record_organisation_checks(db: Session, org: m.Organisation) -> None:
    """Registry and tax checks through the adapters. Outcomes only, source labelled."""
    if not org.registration_number:
        return
    flagged = False
    for provider, result in (
        ("registry", registry_provider().lookup(org.registration_number)),
        ("tax", tax_provider().compliance_status(org.registration_number)),
    ):
        flagged |= result.flagged
        db.add(
            m.Verification(
                subject_type="organisation",
                subject_id=org.id,
                provider=provider,
                result=result.result,
                confidence=result.confidence,
                source_label=result.source_label,
                flagged=result.flagged,
                checked_at=result.checked_at,
            )
        )
    org.verification_status = "under_review" if flagged else "verified"


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    org = m.Organisation(
        name=body.organisation_name,
        org_type=body.role,
        registration_number=body.registration_number,
    )
    db.add(org)
    try:
        db.flush()
        user = m.User(
            email=body.email.lower(),
            password_hash=hash_password(body.password),
            full_name=body.full_name,
            phone=body.phone,
            role=body.role,
            organisation_id=org.id,
            consent_version=settings.consent_version,
            consent_at=now,
        )
        db.add(user)
        db.flush()
    except IntegrityError:
        db.rollback()
        # One message for both duplicate email and duplicate registration number
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email or registration already in use"
        ) from None
    if body.role == "sme":
        record_organisation_checks(db, org)
    write_audit(
        db,
        user.id,
        "register",
        "user",
        user.id,
        new={"role": user.role, "consent_version": user.consent_version},
    )
    db.commit()
    notifications.welcome(user)
    return {"access_token": issue_token(user), "token_type": "bearer", "role": user.role}


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    key = form.username.lower()
    wait = ratelimit.retry_after(key)
    if wait:
        write_audit(db, None, "login_locked", "user")
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {max(1, wait // 60)} minutes.",
            headers={"Retry-After": str(wait)},
        )
    user = db.scalar(select(m.User).where(m.User.email == key))
    ok = verify_password(form.password, user.password_hash if user else _DUMMY_HASH)
    if not user or user.deleted_at is not None or not ok:
        ratelimit.record_failure(key)
        write_audit(db, None, "login_failed", "user")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    ratelimit.clear(key)
    write_audit(db, user.id, "login", "user", user.id)
    db.commit()
    return {"access_token": issue_token(user), "token_type": "bearer", "role": user.role}


@router.get("/me")
def me(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(m.Organisation, user.organisation_id) if user.organisation_id else None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "organisation": {
            "id": org.id,
            "name": org.name,
            "verification_status": org.verification_status,
        }
        if org
        else None,
    }


@router.get("/me/audit")
def my_audit(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """The caller's own recent activity, so accountability is visible to the person it concerns."""
    rows = db.scalars(
        select(m.AuditLog)
        .where(m.AuditLog.user_id == user.id)
        .order_by(m.AuditLog.timestamp.desc())
        .limit(15)
    )
    return [
        {"action": a.action, "entity_type": a.entity_type, "timestamp": a.timestamp} for a in rows
    ]


@router.get("/me/data")
def my_data(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """POPIA data subject participation: everything held about the caller, as JSON."""
    org = db.get(m.Organisation, user.organisation_id) if user.organisation_id else None
    profile = (
        db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == org.id))
        if org
        else None
    )
    docs = (
        list(db.scalars(select(m.Document).where(m.Document.organisation_id == org.id)))
        if org
        else []
    )
    checks = (
        list(
            db.scalars(
                select(m.Verification).where(
                    m.Verification.subject_id.in_([org.id, *[d.id for d in docs]])
                )
            )
        )
        if org
        else []
    )
    audit = list(
        db.scalars(
            select(m.AuditLog).where(m.AuditLog.user_id == user.id).order_by(m.AuditLog.timestamp)
        )
    )
    match_rows = (
        db.execute(
            select(m.Match, m.Opportunity)
            .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
            .where(m.Match.sme_id == org.id)
        ).all()
        if org and user.role == "sme"
        else []
    )
    application_rows = (
        list(
            db.scalars(
                select(m.Application)
                .join(m.Match, m.Match.id == m.Application.match_id)
                .where(m.Match.sme_id == org.id)
            )
        )
        if org and user.role == "sme"
        else []
    )
    own_opportunities = (
        list(db.scalars(select(m.Opportunity).where(m.Opportunity.organisation_id == org.id)))
        if org and user.role != "sme"
        else []
    )
    write_audit(db, user.id, "data_export", "user", user.id)
    db.commit()
    return {
        "user": {
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "role": user.role,
            "consent_version": user.consent_version,
            "consent_at": user.consent_at,
        },
        "organisation": {"name": org.name, "registration_number": org.registration_number}
        if org
        else None,
        "sme_profile": {
            "sector": profile.sector,
            "province": profile.province,
            "annual_turnover": float(profile.annual_turnover),
            "years_trading": profile.years_trading,
            "capability_codes": profile.capability_codes,
            "ownership": profile.ownership,
            "visible_to_corporates": profile.visible_to_corporates,
        }
        if profile
        else None,
        "documents": [
            {
                "type": d.document_type,
                "expiry_date": d.expiry_date,
                "uploaded_at": d.uploaded_at,
                "hash_value": d.hash_value,
            }
            for d in docs
        ],
        "verifications": [
            {
                "subject_type": v.subject_type,
                "result": v.result,
                "source": v.source_label,
                "checked_at": v.checked_at,
            }
            for v in checks
        ],
        "matches": [
            {
                "opportunity": o.title,
                "fit_score": float(mt.fit_score),
                "readiness_score": float(mt.readiness_score),
                "quadrant": mt.quadrant,
                "status": mt.status,
                "model_version": mt.model_version,
                "explanation": mt.explanation,
            }
            for mt, o in match_rows
        ],
        "applications": [
            {"status": a.status, "submitted_at": a.submitted_at} for a in application_rows
        ],
        "opportunities_published": [
            {"title": o.title, "kind": o.kind, "status": o.status} for o in own_opportunities
        ],
        "note": "Uploaded files are not included here, only their records. Ask for the files separately.",
        "audit_events": [{"action": a.action, "timestamp": a.timestamp} for a in audit],
    }


@router.post("/me/delete")
def delete_me(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """POPIA erasure by anonymisation: personal fields are nulled, audit rows survive."""
    # The audit row is written first, then the function runs, in one transaction
    files = (
        purge_organisation_files(db, user.organisation_id)
        if user.role == "sme" and user.organisation_id
        else 0
    )
    write_audit(db, user.id, "anonymise_user", "user", user.id, new={"files_deleted": files})
    db.execute(text("SELECT core.anonymise_user(:uid)"), {"uid": user.id})
    db.commit()
    return {"status": "anonymised", "files_deleted": files}
