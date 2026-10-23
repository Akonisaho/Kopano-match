import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .. import models as m
from ..audit import write_audit
from ..auth import PROVIDER_ROLES, current_user, require_role
from ..db import get_db
from ..llm import client, prompts
from ..routers.smes import verification_badges

router = APIRouter(prefix="/matches", tags=["matches"])


def readable_match(db: Session, user: m.User, match_id: uuid.UUID) -> m.Match:
    """An SME reads its own matches, a corporate reads matches on its own opportunities."""
    match = db.get(m.Match, match_id)
    if match is None:
        raise HTTPException(404, "Not found")
    opp = db.get(m.Opportunity, match.opportunity_id)
    allowed = (
        user.role == "admin"
        or (user.role == "sme" and match.sme_id == user.organisation_id)
        or (user.role in PROVIDER_ROLES and opp.organisation_id == user.organisation_id)
    )
    if not allowed:
        raise HTTPException(404, "Not found")
    return match


def _rationale(match: m.Match, sme_name: str) -> tuple[str, str]:
    facts = {
        "fit_score": float(match.fit_score),
        "readiness_score": float(match.readiness_score),
        "components": match.explanation["components"],
        "gaps": match.explanation["gaps"],
        "risk": match.risk_flags,
    }
    # The prompt carries figures only: no names or identifiers leave the platform
    text = client.call(prompts.RATIONALE.format(match=json.dumps(facts)))
    if text:
        return text, "llm"
    return prompts.fallback_rationale(sme_name, facts), "template"


@router.get("/{match_id}")
def detail(
    match_id: uuid.UUID, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    match = readable_match(db, user, match_id)
    org = db.get(m.Organisation, match.sme_id)
    opp = db.get(m.Opportunity, match.opportunity_id)
    if "rationale" not in match.explanation:
        text, source = _rationale(match, org.name)
        match.explanation = {**match.explanation, "rationale": text, "rationale_source": source}
        flag_modified(match, "explanation")
        db.commit()
    return {
        "match_id": match.id,
        "opportunity": {
            "id": opp.id,
            "title": opp.title,
            "kind": opp.kind,
            "contract_value": float(opp.contract_value),
        },
        "sme": {"id": org.id, "name": org.name, "verification_status": org.verification_status},
        "verifications": verification_badges(db, org.id),
        "gate": match.gate,
        "quadrant": match.quadrant,
        "fit": float(match.fit_score),
        "readiness": float(match.readiness_score),
        "components": match.explanation["components"],
        "gaps": match.explanation["gaps"],
        "risk_flags": match.risk_flags,
        "rationale": match.explanation["rationale"],
        "rationale_source": match.explanation.get("rationale_source"),
        "status": match.status,
        "model_version": match.model_version,
    }


def _decide(match_id: uuid.UUID, new_status: str, user: m.User, db: Session) -> dict:
    match = readable_match(db, user, match_id)
    old = match.status
    match.status = new_status
    write_audit(
        db,
        user.id,
        f"match_{new_status}",
        "match",
        match.id,
        old={"status": old},
        new={"status": new_status},
    )
    db.commit()
    return {"match_id": match.id, "status": match.status}


@router.post("/{match_id}/shortlist")
def shortlist(
    match_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    return _decide(match_id, "shortlisted", user, db)


@router.post("/{match_id}/reject")
def reject(
    match_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    return _decide(match_id, "rejected", user, db)
