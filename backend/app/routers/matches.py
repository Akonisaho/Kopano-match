import json
import threading
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .. import models as m
from .. import notifications
from ..audit import write_audit
from ..auth import PROVIDER_ROLES, current_user, require_role
from ..config import settings
from ..db import SessionLocal, get_db
from ..i18n import rationale as say_in
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


def _said(match: m.Match, name: str, lang: str) -> tuple[str, str | None]:
    """The explanation in the reader's language. English keeps the stored (possibly AI-worded) text;
    any other language is built from fixed templates, so it translates exactly."""
    if lang == "en":
        return match.explanation["rationale"], match.explanation.get("rationale_source")
    facts = {
        "fit_score": float(match.fit_score),
        "readiness_score": float(match.readiness_score),
        "gaps": match.explanation["gaps"],
        "risk": match.risk_flags,
    }
    return say_in(name, facts, lang), "template"


def warm_rationales(org_id: uuid.UUID) -> None:
    """After a rescore, write the plain-words summary in the background so the next page view is
    instant. Only with a live AI provider: otherwise the template is quick and nothing is needed."""
    if not (settings.llm_provider == "gemini" and settings.gemini_api_key):
        return

    def run() -> None:
        try:
            with SessionLocal() as db:
                for mt in db.scalars(select(m.Match).where(m.Match.sme_id == org_id)):
                    if "rationale" in (mt.explanation or {}):
                        continue
                    org = db.get(m.Organisation, mt.sme_id)
                    text, source = _rationale(mt, org.name)
                    mt.explanation = {
                        **mt.explanation,
                        "rationale": text,
                        "rationale_source": source,
                    }
                    flag_modified(mt, "explanation")
                db.commit()
        except Exception:  # noqa: BLE001 - a warm-up must never matter
            pass

    threading.Thread(target=run, daemon=True).start()


@router.get("/{match_id}/dossier")
def dossier(
    match_id: uuid.UUID, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    """Everything needed to defend a decision later: the rules, the scores, the sources, the history."""
    match = readable_match(db, user, match_id)
    org = db.get(m.Organisation, match.sme_id)
    opp = db.get(m.Opportunity, match.opportunity_id)
    provider = db.get(m.Organisation, opp.organisation_id)
    rules = db.scalars(
        select(m.OpportunityRequirement).where(m.OpportunityRequirement.opportunity_id == opp.id)
    )
    history = db.execute(
        select(m.AuditLog, m.User, m.Organisation)
        .join(m.User, m.User.id == m.AuditLog.user_id, isouter=True)
        .join(m.Organisation, m.Organisation.id == m.User.organisation_id, isouter=True)
        .where(m.AuditLog.entity_type == "match", m.AuditLog.entity_id == str(match.id))
        .order_by(m.AuditLog.timestamp.asc())
    ).all()
    decisions = [
        {
            "action": a.action,
            "at": a.timestamp,
            "by_role": u.role if u else None,
            "by_organisation": o.name if o else None,
            "snapshot": (a.new_value or {}).get("snapshot"),
        }
        for a, u, o in history
    ]
    frozen = next((d["snapshot"] for d in reversed(decisions) if d["snapshot"]), None)
    current = {"fit": float(match.fit_score), "readiness": float(match.readiness_score)}
    return {
        "generated_at": datetime.now(UTC),
        "match_id": match.id,
        "model_version": match.model_version,
        "opportunity": {
            "title": opp.title,
            "kind": opp.kind,
            "provider": provider.name,
            "contract_value": float(opp.contract_value),
            "duration_months": opp.duration_months,
            "payment_terms_days": opp.payment_terms_days,
            "deadline": opp.deadline,
        },
        "sme": {
            "name": org.name,
            "verification_status": org.verification_status,
        },
        "rules": [
            {
                "type": r.requirement_type,
                "value": r.requirement_value,
                "mandatory": r.mandatory,
                "weight": r.weight,
            }
            for r in rules
        ],
        "result": {
            "gate": match.gate,
            "quadrant": match.quadrant,
            "fit": current["fit"],
            "readiness": current["readiness"],
            "components": match.explanation.get("components"),
            "gaps": match.explanation.get("gaps"),
            "risk_flags": match.risk_flags,
        },
        "status": match.status,
        "verifications": verification_badges(db, org.id),
        "decisions": decisions,
        # True when the live scores still equal the ones frozen at the moment of decision
        "matches_decision_snapshot": None
        if frozen is None
        else (frozen["fit"] == current["fit"] and frozen["readiness"] == current["readiness"]),
    }


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
    said = _said(match, org.name, user.language)
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
        "rationale": said[0],
        "rationale_source": said[1],
        "status": match.status,
        "model_version": match.model_version,
    }


def _decide(match_id: uuid.UUID, new_status: str, user: m.User, db: Session) -> dict:
    match = readable_match(db, user, match_id)
    if match.status == "awarded":
        raise HTTPException(409, "This match has already been awarded")
    if new_status == "shortlisted":
        from ..enforcement import refuse_if_blocked

        refuse_if_blocked(db, match.sme_id)  # its status may have changed since it was matched
    old = match.status
    match.status = new_status
    write_audit(
        db,
        user.id,
        f"match_{new_status}",
        "match",
        match.id,
        old={"status": old},
        # A frozen copy of the reasoning at the moment of decision. Matching can be re-run
        # later and change the live row, but the audit log cannot be rewritten.
        new={
            "status": new_status,
            "snapshot": {
                "model_version": match.model_version,
                "gate": match.gate,
                "quadrant": match.quadrant,
                "fit": float(match.fit_score),
                "readiness": float(match.readiness_score),
                "components": match.explanation.get("components"),
                "gaps": match.explanation.get("gaps"),
                "risk_flags": match.risk_flags,
            },
        },
    )
    db.commit()
    notifications.match_decided(db, match, new_status)
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


@router.get("/{match_id}/semantic")
def semantic_relevance(
    match_id: uuid.UUID, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    """Advisory, meaning-based reading of how the opportunity text fits the business."""
    from .. import insights

    return insights.semantic(db, readable_match(db, user, match_id))
