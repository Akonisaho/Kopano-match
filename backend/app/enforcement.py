"""Risk and enforcement: what an organisation's status allows, and what changing it sets in motion.

Statuses: clear, monitoring, flagged, under_review, restricted, suspended, blacklisted, reinstated.
Suspended and blacklisted are a hard gate. A high capability score never overrides them. Every
decision is made by a person; a score or a fraud signal can raise a flag but never blacklists.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m

BLOCKED = ("suspended", "blacklisted")
STATUSES = (
    "clear",
    "monitoring",
    "flagged",
    "under_review",
    "restricted",
    "suspended",
    "blacklisted",
    "reinstated",
)
RESTRICTIONS = {
    "apply": "Cannot apply for opportunities",
    "post": "Cannot post opportunities",
    "rate": "Cannot submit ratings or reviews",
    "award": "Cannot shortlist or award",
    "upload": "Cannot upload documents",
}
REASONS = {
    "identity_fraud": "Identity fraud",
    "fake_documents": "Fake or altered documents",
    "impersonation": "Impersonation",
    "false_company_info": "False company information",
    "duplicate_identity": "Duplicate identity",
    "duplicate_organisation": "Duplicate organisation",
    "fraudulent_opportunity": "Fraudulent opportunity",
    "fake_funding": "Fake funding opportunity",
    "advance_fee_scam": "Advance-fee scam",
    "suspicious_payment": "Suspicious payment request",
    "misrepresentation": "Misrepresentation",
    "false_programme_history": "False training or programme history",
    "manipulated_reviews": "Manipulated reviews",
    "collusion": "Collusion",
    "account_takeover": "Account takeover",
    "repeated_abuse": "Repeated platform abuse",
    "bypass_suspension": "Attempt to bypass suspension",
    "unlawful_activity": "Unlawful activity",
    "other": "Other verified misconduct",
}
SUSPENDED_MESSAGE = (
    "Your account has been temporarily suspended while a serious trust and safety matter is "
    "reviewed. You can see your case status, send information and appeal."
)
ACTION_BLOCKED = "ACTION BLOCKED: This SME is currently restricted from marketplace participation."


def restriction_for(method: str, path: str) -> str | None:
    """Which restriction a write request falls under, if any."""
    if method in ("GET", "HEAD", "OPTIONS"):
        return None
    p = path.rstrip("/")
    if p.startswith("/applications"):
        return "award" if p.endswith("/award") else "apply"
    if p.endswith("/shortlist") or p.endswith("/reject"):
        return "award"
    if p == "/opportunities" or p.startswith("/opportunities/import"):
        return "post"
    if p.startswith("/feedback"):
        return "rate"
    if p.startswith("/documents"):
        return "upload"
    return None


def guard(db: Session, user: m.User, method: str, path: str) -> None:
    """Stop a suspended or restricted organisation from acting. Reading stays open so it can see why."""
    if user.organisation_id is None or method in ("GET", "HEAD", "OPTIONS"):
        return
    org = db.get(m.Organisation, user.organisation_id)
    if org is None:
        return
    if org.enforcement_status in BLOCKED:
        raise HTTPException(403, "ACCOUNT_SUSPENDED: " + SUSPENDED_MESSAGE)
    if org.enforcement_status == "restricted":
        rule = restriction_for(method, path)
        if rule and rule in (org.restrictions or []):
            raise HTTPException(403, f"ACCOUNT_RESTRICTED: {RESTRICTIONS[rule]}.")


def blocked_ids(db: Session) -> set[uuid.UUID]:
    return set(
        db.scalars(select(m.Organisation.id).where(m.Organisation.enforcement_status.in_(BLOCKED)))
    )


def refuse_if_blocked(db: Session, sme_org_id: uuid.UUID) -> None:
    """A status can change after a match was made, so shortlisting and awarding check it again."""
    org = db.get(m.Organisation, sme_org_id)
    if org is not None and org.enforcement_status in BLOCKED:
        raise HTTPException(409, ACTION_BLOCKED)


def set_status(db: Session, org: m.Organisation, status: str, restrictions: list[str] | None = None):
    """Change a status and apply what follows. An organisation that posts opportunities has them
    paused while it is suspended, and put back if it is reinstated."""
    was = org.enforcement_status
    org.enforcement_status = status
    org.restrictions = list(restrictions or []) if status == "restricted" else []
    if org.org_type != "sme":
        if status in BLOCKED:
            for o in db.scalars(
                select(m.Opportunity).where(
                    m.Opportunity.organisation_id == org.id, m.Opportunity.status == "open"
                )
            ):
                o.status = "paused"
        elif was in BLOCKED:
            for o in db.scalars(
                select(m.Opportunity).where(
                    m.Opportunity.organisation_id == org.id, m.Opportunity.status == "paused"
                )
            ):
                o.status = "open"
    return was
