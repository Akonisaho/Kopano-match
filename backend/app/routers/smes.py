import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..adapters.mock import identity_provider
from ..audit import write_audit
from ..auth import require_role
from ..db import get_db
from ..llm import client, prompts
from ..schemas import ExtractIn, ProfileIn
from ..services import blockers_for
from .applications import application_status
from .auth import record_organisation_checks

router = APIRouter(prefix="/smes", tags=["smes"])


def _profile_view(p: m.SmeProfile) -> dict:
    return {
        "sector": p.sector,
        "province": p.province,
        "annual_turnover": float(p.annual_turnover),
        "years_trading": p.years_trading,
        "largest_past_contract": float(p.largest_past_contract or 0),
        "capability_codes": p.capability_codes,
        "ownership": p.ownership,
        "visible_to_corporates": p.visible_to_corporates,
    }


def verification_badges(db: Session, org_id: uuid.UUID) -> list[dict]:
    doc_types = {
        d.id: d.document_type
        for d in db.scalars(select(m.Document).where(m.Document.organisation_id == org_id))
    }
    doc_ids = list(doc_types)
    rows = db.scalars(
        select(m.Verification)
        .where(m.Verification.subject_id.in_([org_id, *doc_ids]))
        .order_by(m.Verification.checked_at.desc())
    )
    return [
        {
            "id": v.id,
            "subject_type": v.subject_type,
            "provider": v.provider,
            "document_type": doc_types.get(v.subject_id),
            "result": v.result,
            "source_label": v.source_label,
            "flagged": v.flagged,
            "review_status": v.review_status,
        }
        for v in rows
    ]


def _latest_ok(db: Session, org_id: uuid.UUID, subject_type: str) -> bool:
    v = db.scalar(
        select(m.Verification)
        .where(m.Verification.subject_id == org_id, m.Verification.subject_type == subject_type)
        .order_by(m.Verification.checked_at.desc())
        .limit(1)
    )
    return bool(v and (v.result == "verified" or v.review_status == "approved"))


def completion(db: Session, org_id: uuid.UUID, p: m.SmeProfile | None) -> dict:
    """Explainable onboarding progress: four named steps, each worth a fixed share."""
    has_doc = db.scalar(select(m.Document.id).where(m.Document.organisation_id == org_id).limit(1))
    steps = [
        ("Business capability profile", 40, bool(p and p.capability_codes)),
        ("Company registration verified", 20, _latest_ok(db, org_id, "organisation")),
        ("Representative identity verified", 20, _latest_ok(db, org_id, "identity")),
        ("Compliance document uploaded", 20, bool(has_doc)),
    ]
    return {
        "percent": sum(w for _, w, done in steps if done),
        "steps": [{"label": label, "done": done} for label, _, done in steps],
    }


@router.get("/me")
def get_profile(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    p = db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == user.organisation_id))
    org = db.get(m.Organisation, user.organisation_id)
    return {
        "profile": _profile_view(p) if p else None,
        "organisation": {
            "name": org.name,
            "registration_number": org.registration_number,
            "verification_status": org.verification_status,
        },
        "verifications": verification_badges(db, user.organisation_id),
        "completion": completion(db, user.organisation_id, p),
    }


@router.put("/me")
def put_profile(
    body: ProfileIn, user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)
):
    p = db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == user.organisation_id))
    old = _profile_view(p) if p else None
    if p is None:
        p = m.SmeProfile(organisation_id=user.organisation_id)
        db.add(p)
    for key, value in body.model_dump().items():
        setattr(p, key, value)
    db.flush()
    write_audit(db, user.id, "profile_change", "sme_profile", p.id, old=old, new=_profile_view(p))
    db.commit()
    return _profile_view(p)


@router.post("/me/extract")
def extract_profile(body: ExtractIn, user: m.User = Depends(require_role("sme"))):
    """LLM draft of the profile from pasted text. The user reviews it before saving."""
    prompt = prompts.EXTRACT_PROFILE.format(
        sectors=sorted({*prompts.SECTORS}),
        provinces=prompts.PROVINCES,
        codes=sorted(prompts.CAPABILITIES),
        text=body.text,
    )
    result = client.call(prompt, prompts.ProfileExtraction)
    if result is None:
        # Fallback: an empty draft, so the form simply stays blank rather than erroring
        return {"source": "fallback", "draft": prompts.ProfileExtraction().model_dump()}
    return {"source": "llm", "draft": result.model_dump()}


@router.get("/me/dashboard")
def dashboard(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    rows = db.execute(
        select(m.Match, m.Opportunity)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .where(m.Match.sme_id == user.organisation_id)
        .order_by(m.Match.overall_score.desc())
    ).all()
    if (
        not rows
        and db.scalar(
            select(m.SmeProfile.id).where(m.SmeProfile.organisation_id == user.organisation_id)
        )
        is None
    ):
        raise HTTPException(404, "Complete your profile first")
    gaps: dict[str, dict] = {}
    matches = []
    for match, opp in rows:
        for g in match.explanation.get("gaps", []):
            entry = gaps.setdefault(g["credential"], {**g, "blocks": []})
            entry["blocks"].append(opp.title)
        matches.append(
            {
                "match_id": match.id,
                "opportunity": opp.title,
                "contract_value": float(opp.contract_value),
                "quadrant": match.quadrant,
                "fit": float(match.fit_score),
                "readiness": float(match.readiness_score),
                "gate": match.gate,
                "status": match.status,
            }
        )
    avg = round(sum(x["readiness"] for x in matches) / len(matches), 1) if matches else None
    return {"readiness_score": avg, "open_gaps": list(gaps.values()), "matches": matches}


@router.post("/me/verify")
def reverify(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    """Re-run the registry and tax checks through the adapters."""
    org = db.get(m.Organisation, user.organisation_id)
    if not org.registration_number:
        raise HTTPException(422, "Add a registration number to your organisation first")
    record_organisation_checks(db, org)
    write_audit(
        db,
        user.id,
        "verification_refresh",
        "organisation",
        org.id,
        new={"status": org.verification_status},
    )
    db.commit()
    return {"verification_status": org.verification_status}


SELFIE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")
MAX_SELFIE_BYTES = 3 * 1024 * 1024


@router.post("/me/verify-identity")
async def verify_identity(
    id_last4: str = Form(...),
    selfie: UploadFile = File(...),
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    """The image is checked, passed to the provider and discarded. Only the outcome is stored."""
    if not re.fullmatch(r"\d{4}", id_last4):
        raise HTTPException(422, "Enter the last four digits of the ID number only")
    data = await selfie.read(MAX_SELFIE_BYTES + 1)
    if len(data) > MAX_SELFIE_BYTES:
        raise HTTPException(413, "Image exceeds the size limit")
    if not data.startswith(SELFIE_MAGIC):
        raise HTTPException(415, "Upload a JPG or PNG image")
    result = identity_provider().verify(f"*********{id_last4}", data)
    del data
    org = db.get(m.Organisation, user.organisation_id)
    db.add(
        m.Verification(
            subject_type="identity",
            subject_id=org.id,
            provider="identity",
            result=result.result,
            confidence=result.confidence,
            source_label=result.source_label,
            flagged=result.flagged,
            checked_at=result.checked_at,
        )
    )
    write_audit(
        db,
        user.id,
        "identity_check",
        "organisation",
        org.id,
        new={"result": result.result, "source": result.source_label},
    )
    db.commit()
    return {
        "result": result.result,
        "confidence": result.confidence,
        "source_label": result.source_label,
        "retained": "outcome only, no image or ID number stored",
    }


@router.get("/me/opportunities")
def my_opportunities(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    """Every open opportunity, with this SME's match and application where there is one."""
    opps = db.execute(
        select(m.Opportunity, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.Opportunity.organisation_id)
        .where(m.Opportunity.status == "open")
        .order_by(m.Opportunity.deadline.asc().nulls_last())
    ).all()
    mine = {
        mt.opportunity_id: (mt, app)
        for mt, app in db.execute(
            select(m.Match, m.Application)
            .join(m.Application, m.Application.match_id == m.Match.id, isouter=True)
            .where(m.Match.sme_id == user.organisation_id)
        )
    }
    blockers = blockers_for(db, user.organisation_id)
    out = []
    for o, provider in opps:
        mt, app = mine.get(o.id, (None, None))
        out.append(
            {
                "opportunity_id": o.id,
                "title": o.title,
                "kind": o.kind,
                "provider": provider.name,
                "provider_status": provider.verification_status,
                "sector": o.sector,
                "province": o.province,
                "contract_value": float(o.contract_value),
                "deadline": o.deadline,
                "blockers": blockers.get(o.id, []),
                "match": None
                if mt is None
                else {
                    "match_id": mt.id,
                    "quadrant": mt.quadrant,
                    "fit": float(mt.fit_score),
                    "readiness": float(mt.readiness_score),
                    "gate": mt.gate,
                    "gap_count": len(mt.explanation.get("gaps", [])),
                    "status": mt.status,
                    "application": application_status(mt, app),
                },
            }
        )
    return out
