"""The Readiness Passport: one shareable page that proves what a business can show a buyer.

The business switches it on, owns the link, and can rotate or switch it off at any time. It carries
only what the business already shows buyers on the platform: verified checks (with their source, so a
mock is labelled a mock), credentials and their dates, capabilities and an aggregate track record.
Never turnover, ownership or contact details.
"""

import secrets
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import insights
from .. import models as m
from ..audit import write_audit
from ..auth import require_role
from ..config import settings
from ..db import get_db
from ..engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE
from ..mfa import qr_data_uri
from ..services import doc_status
from .smes import verification_badges

router = APIRouter(tags=["passport"])

CHECK_LABELS = {
    "registry": "Company registration",
    "tax": "Tax status",
    "identity": "Representative identity",
}


def _link(token: str) -> str:
    return f"{settings.app_url.rstrip('/')}/passport/{token}"


def _passport_for(db: Session, org_id) -> m.Passport | None:
    return db.scalar(select(m.Passport).where(m.Passport.organisation_id == org_id))


def passport_view(db: Session, org_id) -> dict:
    org = db.get(m.Organisation, org_id)
    p = db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == org_id))
    seen: set[str] = set()
    checks = []
    for v in verification_badges(db, org_id):  # newest first, so the first per kind is current
        if v["subject_type"] == "document" or v["provider"] not in CHECK_LABELS:
            continue
        if v["provider"] in seen:
            continue
        seen.add(v["provider"])
        checks.append(
            {
                "label": CHECK_LABELS[v["provider"]],
                "ok": v["result"] == "verified",
                "source": v["source_label"],
            }
        )
    latest: dict[str, m.Document] = {}
    for d in db.scalars(
        select(m.Document)
        .where(m.Document.organisation_id == org_id)
        .order_by(m.Document.uploaded_at)
    ):
        latest[d.document_type] = d
    credentials = [
        {
            "label": COMPLIANCE_CATALOGUE[t].label if t in COMPLIANCE_CATALOGUE else t,
            "status": doc_status(d).value,
            "expires": d.expiry_date,
        }
        for t, d in latest.items()
    ]
    perf = insights.performance(db, org_id, with_summary=False)
    return {
        "name": org.name,
        "sector": p.sector if p else None,
        "province": p.province if p else None,
        "years_trading": p.years_trading if p else None,
        "capabilities": [
            CAPABILITIES[c][1] for c in (p.capability_codes if p else []) if c in CAPABILITIES
        ],
        "checks": checks,
        "credentials": credentials,
        "credentials_valid": sum(1 for c in credentials if c["status"] == "valid"),
        "track_record": {
            "reviews": perf["reviews"],
            "overall": perf["overall"],
            "reliable": perf["reliable"],
        },
        "as_of": date.today(),
        "notice": "Shared by the business. Checks marked mock are simulated in this pilot. "
        "Turnover, ownership and contact details are not part of this page.",
    }


def _state(db: Session, org_id) -> dict:
    row = _passport_for(db, org_id)
    on = row is not None and row.enabled
    return {
        "enabled": on,
        "link": _link(row.token) if on else None,
        "qr": qr_data_uri(_link(row.token)) if on else None,
        "preview": passport_view(db, org_id),
    }


@router.get("/smes/me/passport")
def my_passport(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    return _state(db, user.organisation_id)


@router.post("/smes/me/passport/enable")
def enable(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    row = _passport_for(db, user.organisation_id)
    if row is None:
        row = m.Passport(
            organisation_id=user.organisation_id, token=secrets.token_urlsafe(24), enabled=True
        )
        db.add(row)
    else:
        row.enabled = True
    db.flush()
    write_audit(db, user.id, "passport_enabled", "passport", row.id)
    db.commit()
    return _state(db, user.organisation_id)


@router.post("/smes/me/passport/rotate")
def rotate(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    """A new link. The old one stops working at once."""
    row = _passport_for(db, user.organisation_id)
    if row is None:
        raise HTTPException(404, "Not found")
    row.token = secrets.token_urlsafe(24)
    row.enabled = True
    row.rotated_at = datetime.now(UTC)
    write_audit(db, user.id, "passport_rotated", "passport", row.id)
    db.commit()
    return _state(db, user.organisation_id)


@router.post("/smes/me/passport/disable")
def disable(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    row = _passport_for(db, user.organisation_id)
    if row is not None and row.enabled:
        row.enabled = False
        write_audit(db, user.id, "passport_disabled", "passport", row.id)
        db.commit()
    return _state(db, user.organisation_id)


@router.get("/passport/{token}")
def public_passport(token: str, db: Session = Depends(get_db)):
    """Anyone with the link. No sign-in, nothing beyond the page the business chose to share."""
    row = db.scalar(select(m.Passport).where(m.Passport.token == token))
    if row is None or not row.enabled:
        raise HTTPException(404, "This passport is not available")
    return passport_view(db, row.organisation_id)
