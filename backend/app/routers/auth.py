import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..adapters.mock import registry_provider, tax_provider
from .. import mfa, notifications, ratelimit
from ..audit import write_audit
from ..auth import (
    current_user,
    hash_password,
    issue_mfa_token,
    issue_token,
    read_mfa_token,
    verify_password,
)
from ..config import settings
from ..db import get_db
from ..schemas import ForgotIn, MfaCodeIn, MfaVerifyIn, RegisterIn, ResetIn
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
    notifications.welcome(db, user)
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
    if user.totp_enabled:
        write_audit(db, user.id, "login_mfa_challenge", "user", user.id)
        db.commit()
        return {"mfa_required": True, "mfa_token": issue_mfa_token(user)}
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
        "mfa_enabled": user.totp_enabled,
        "language": user.language,
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
    db.execute(delete(m.Notification).where(m.Notification.user_id == user.id))
    db.execute(
        update(m.PasswordReset)
        .where(m.PasswordReset.user_id == user.id, m.PasswordReset.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )
    write_audit(db, user.id, "anonymise_user", "user", user.id, new={"files_deleted": files})
    db.execute(text("SELECT core.anonymise_user(:uid)"), {"uid": user.id})
    db.commit()
    return {"status": "anonymised", "files_deleted": files}


# ---------------------------------------------------------------- password reset

RESET_MINUTES = 30
_FORGOT_REPLY = {"status": "If that email is registered, a reset link is on its way."}


@router.post("/auth/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot(body: ForgotIn, db: Session = Depends(get_db)):
    """Always the same answer, so the page cannot be used to find out who has an account."""
    email = body.email.lower()
    key = f"forgot:{email}"
    if ratelimit.retry_after(key):
        return _FORGOT_REPLY
    ratelimit.record_failure(key)  # every request counts toward the limit
    user = db.scalar(select(m.User).where(m.User.email == email))
    if user and user.deleted_at is None:
        token = secrets.token_urlsafe(32)
        db.add(
            m.PasswordReset(
                user_id=user.id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(minutes=RESET_MINUTES),
            )
        )
        write_audit(db, user.id, "password_reset_requested", "user", user.id)
        db.commit()
        link = f"{settings.app_url.rstrip('/')}/reset?token={token}"
        notifications.send(
            user.email,
            user.full_name,
            "Reset your Kopano Match password",
            notifications.page(
                "Reset your password",
                [
                    "We received a request to reset your password.",
                    f"This link works once and expires in {RESET_MINUTES} minutes. "
                    "If you did not ask for it, you can ignore this email.",
                ],
                "Choose a new password",
                link,
            ),
        )
    return _FORGOT_REPLY


@router.post("/auth/reset")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    bad = HTTPException(status.HTTP_400_BAD_REQUEST, "This link is invalid or has expired.")
    row = db.scalar(
        select(m.PasswordReset).where(
            m.PasswordReset.token_hash == hashlib.sha256(body.token.encode()).hexdigest()
        )
    )
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at < now:
        raise bad
    user = db.get(m.User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise bad
    user.password_hash = hash_password(body.new_password)
    # Every outstanding link for this person dies with the first one used
    db.execute(
        update(m.PasswordReset)
        .where(m.PasswordReset.user_id == user.id, m.PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    ratelimit.clear(user.email)
    write_audit(db, user.id, "password_reset_completed", "user", user.id)
    db.commit()
    return {"status": "password_changed"}


# ---------------------------------------------------------------- two-step sign-in (authenticator app)


def _throttle(key: str) -> None:
    wait = ratelimit.retry_after(key)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Try again in {max(1, wait // 60)} minutes.",
            headers={"Retry-After": str(wait)},
        )


def _accept_code(user: m.User, code: str) -> bool:
    """A current authenticator code (never reused) or an unused recovery code. Caller commits."""
    if user.totp_secret_enc:
        step = mfa.matching_step(mfa.decrypt(user.totp_secret_enc), code)
        if step is not None and step > (user.totp_last_step or 0):
            user.totp_last_step = step
            return True
    hashed = mfa.hash_code(code)
    if hashed in (user.recovery_hashes or []):
        user.recovery_hashes = [h for h in user.recovery_hashes if h != hashed]
        return True
    return False


@router.post("/auth/mfa/setup")
def mfa_setup(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on")
    secret = mfa.new_secret()
    user.totp_secret_enc = mfa.encrypt(secret)
    user.totp_last_step = 0
    write_audit(db, user.id, "mfa_setup_started", "user", user.id)
    db.commit()
    uri = mfa.provisioning_uri(secret, user.email)
    return {"secret": secret, "otpauth_uri": uri, "qr": mfa.qr_data_uri(uri)}


@router.post("/auth/mfa/enable")
def mfa_enable(
    body: MfaCodeIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on")
    if not user.totp_secret_enc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start setup first")
    key = f"mfa:{user.id}"
    _throttle(key)
    step = mfa.matching_step(mfa.decrypt(user.totp_secret_enc), body.code)
    if step is None:
        ratelimit.record_failure(key)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That code is not right. Check the clock on your phone and try the next code.",
        )
    codes = mfa.new_recovery_codes()
    user.totp_enabled = True
    user.totp_last_step = step
    user.recovery_hashes = [mfa.hash_code(c) for c in codes]
    ratelimit.clear(key)
    write_audit(db, user.id, "mfa_enabled", "user", user.id)
    db.commit()
    return {"recovery_codes": codes}


@router.post("/auth/mfa/disable")
def mfa_disable(
    body: MfaCodeIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is not on")
    key = f"mfa:{user.id}"
    _throttle(key)
    if not _accept_code(user, body.code):
        ratelimit.record_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is not right.")
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.recovery_hashes = []
    ratelimit.clear(key)
    write_audit(db, user.id, "mfa_disabled", "user", user.id)
    db.commit()
    return {"status": "disabled"}


@router.post("/auth/mfa/verify")
def mfa_verify(body: MfaVerifyIn, db: Session = Depends(get_db)):
    """Second step of sign-in: the challenge token from the password step plus a code."""
    denied = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again.")
    uid = read_mfa_token(body.mfa_token)
    user = db.get(m.User, uid) if uid else None
    if user is None or user.deleted_at is not None or not user.totp_enabled:
        raise denied
    key = f"mfa:{user.id}"
    _throttle(key)
    if not _accept_code(user, body.code):
        ratelimit.record_failure(key)
        write_audit(db, None, "login_failed", "user")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is not right.")
    ratelimit.clear(key)
    write_audit(db, user.id, "login", "user", user.id)
    db.commit()
    return {"access_token": issue_token(user), "token_type": "bearer", "role": user.role}
