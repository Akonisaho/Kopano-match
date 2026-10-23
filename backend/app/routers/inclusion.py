"""Inclusion: the language a person works in, voice use, and signing a business up with help.

Language is a preference, never an input to a score. Voice use records only that the feature was used,
never the audio. Assisted sign-up lets a support programme help a business that cannot easily do it alone,
with the business's consent, and the business sets its own password from an emailed link.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from .. import notifications
from ..audit import write_audit
from ..auth import current_user, hash_password, require_role
from ..config import settings
from ..db import get_db
from ..schemas import Strict
from .auth import record_organisation_checks

router = APIRouter(tags=["inclusion"])
SETUP_HOURS = 72


class LanguageIn(Strict):
    language: Literal["en", "af", "zu", "st"]


class VoiceIn(Strict):
    feature: Literal["search", "describe", "read_aloud"]


class AssistedIn(Strict):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    organisation_name: str = Field(min_length=2, max_length=200)
    registration_number: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    language: Literal["en", "af", "zu", "st"] = "en"
    consent: bool

    @field_validator("consent")
    @classmethod
    def must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("The business must agree to the privacy notice")
        return v


@router.put("/me/language")
def set_language(
    body: LanguageIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    if user.language != body.language:
        write_audit(db, user.id, "language_set", "user", user.id, new={"language": body.language})
        user.language = body.language
        db.commit()
    return {"language": user.language}


@router.post("/me/voice", status_code=204)
def voice_used(body: VoiceIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """Counts a use of voice input or read-aloud. No audio and no text is sent here."""
    write_audit(db, user.id, "voice_used", "user", user.id, new={"feature": body.feature})
    db.commit()


@router.post("/assist/businesses", status_code=201)
def sign_up_with_help(
    body: AssistedIn,
    officer: m.User = Depends(require_role("support")),
    db: Session = Depends(get_db),
):
    """A support programme signs a business up. The business gets an email to choose its own password,
    so the officer never holds its credentials."""
    now = datetime.now(UTC)
    org = m.Organisation(
        name=body.organisation_name, org_type="sme", registration_number=body.registration_number
    )
    db.add(org)
    try:
        db.flush()
        user = m.User(
            email=body.email.lower(),
            password_hash=hash_password(secrets.token_urlsafe(32)),  # nobody knows it
            full_name=body.full_name,
            phone=body.phone,
            role="sme",
            organisation_id=org.id,
            consent_version=settings.consent_version,
            consent_at=now,
            language=body.language,
            assisted_by=officer.organisation_id,
        )
        db.add(user)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email or registration already in use"
        ) from None
    record_organisation_checks(db, org)
    token = secrets.token_urlsafe(32)
    db.add(
        m.PasswordReset(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now + timedelta(hours=SETUP_HOURS),
        )
    )
    write_audit(
        db,
        officer.id,
        "assisted_signup",
        "organisation",
        org.id,
        new={"language": body.language, "consent_attested": True},
    )
    db.commit()
    link = f"{settings.app_url.rstrip('/')}/reset?token={token}"
    officer_org = db.get(m.Organisation, officer.organisation_id)
    notifications.send(
        user.email,
        user.full_name,
        "Your Kopano Match account is ready",
        notifications.page(
            "Your account is ready",
            [
                f"{officer_org.name} helped set up your business on Kopano Match.",
                f"Choose your own password to finish. The link works once and expires in {SETUP_HOURS} hours.",
            ],
            "Choose your password",
            link,
        ),
    )
    out = {
        "organisation_id": org.id,
        "email": user.email,
        "language": user.language,
        "emailed": True,
    }
    if settings.environment == "dev":
        out["setup_link"] = link  # dev only, so the flow can be shown without an inbox
    return out
