"""Open to everyone, no account: browse what is on offer and see how the platform would judge you.

Nothing here reads or stores a business's data. The check runs the real engine on the answers typed
into the page and returns the answer; the answers are discarded. It is limited per visitor, and the
only thing it shows about a buyer is what the buyer published in the opportunity.
"""

import time
import uuid
from collections import defaultdict, deque
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..engine.runner import match_one
from ..engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE, PROVINCES, SECTORS
from ..engine.types import SME, DocStatus
from ..llm import prompts
from ..schemas import Strict
from ..services import explanation_of, load_open_opportunities, risk_of

router = APIRouter(prefix="/public", tags=["public"])

PREVIEWS_PER_WINDOW = 60
WINDOW_SECONDS = 600
_seen: dict[str, deque[float]] = defaultdict(deque)


def _allow(ip: str) -> bool:
    now = time.monotonic()
    q = _seen[ip]
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    if len(q) >= PREVIEWS_PER_WINDOW:
        return False
    q.append(now)
    if len(_seen) > 5000:  # bound memory against floods of made-up visitors
        for k in [k for k, v in _seen.items() if not v]:
            del _seen[k]
    return True


class PreviewIn(Strict):
    sector: Literal[tuple(SECTORS)]  # type: ignore[valid-type]
    province: Literal[tuple(PROVINCES)]  # type: ignore[valid-type]
    years_trading: int = Field(ge=0, le=100)
    annual_turnover: float = Field(gt=0, le=1e10)
    largest_past_contract: float = Field(default=0, ge=0, le=1e10)
    capability_codes: list[str] = Field(default_factory=list, max_length=15)
    documents: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("capability_codes")
    @classmethod
    def _caps(cls, v: list[str]) -> list[str]:
        if any(c not in CAPABILITIES for c in v):
            raise ValueError("Unknown capability")
        return sorted(set(v))

    @field_validator("documents")
    @classmethod
    def _docs(cls, v: list[str]) -> list[str]:
        if any(c not in COMPLIANCE_CATALOGUE for c in v):
            raise ValueError("Unknown document")
        return sorted(set(v))


def _cap(code: str) -> str:
    return CAPABILITIES.get(code, ("", code))[1]


def _requirement(r: m.OpportunityRequirement) -> dict:
    t, v = r.requirement_type, r.requirement_value
    out = {"mandatory": r.mandatory, "kind": t}
    if t == "capability":
        out["text"] = f"Can deliver {_cap(v['code']).lower()}"
    elif t in ("compliance_doc", "certification"):
        c = COMPLIANCE_CATALOGUE.get(v["doc"])
        out["text"] = f"{c.label} from {c.issuer}" if c else v["doc"]
        if c:
            out.update(days=c.days, cost_zar=c.cost_zar)
    elif t == "min_years":
        out["text"] = f"At least {v['years']} years trading"
    elif t == "min_turnover":
        out["text"] = f"Annual turnover of at least R{int(v['amount']):,}".replace(",", " ")
    elif t == "province":
        out["text"] = f"Based in {v['province']}"
    elif t == "sector":
        out["text"] = f"Works in {v['sector'].replace('_', ' ')}"
    elif t == "ownership":
        out["text"] = f"{v['flag'].replace('_', ' ')}-owned business"
    else:
        out["text"] = t
    return out


def _card(o: m.Opportunity, provider: str | None) -> dict:
    return {
        "id": o.id,
        "title": o.title,
        "kind": o.kind,
        "sector": o.sector,
        "province": o.province,
        "contract_value": float(o.contract_value),
        "deadline": o.deadline,
        "provider": provider,
    }


@router.get("/opportunities")
def open_opportunities(db: Session = Depends(get_db)):
    rows = db.execute(
        select(m.Opportunity, m.Organisation.name)
        .join(m.Organisation, m.Organisation.id == m.Opportunity.organisation_id)
        .where(m.Opportunity.status == "open")
        .order_by(m.Opportunity.deadline.asc().nulls_last(), m.Opportunity.created_at.desc())
    ).all()
    return [_card(o, name) for o, name in rows]


@router.get("/opportunities/{opp_id}")
def open_opportunity(opp_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.execute(
        select(m.Opportunity, m.Organisation.name)
        .join(m.Organisation, m.Organisation.id == m.Opportunity.organisation_id)
        .where(m.Opportunity.id == opp_id, m.Opportunity.status == "open")
    ).first()
    if row is None:
        raise HTTPException(404, "This opportunity is not open")
    o, provider = row
    reqs = list(
        db.scalars(
            select(m.OpportunityRequirement).where(m.OpportunityRequirement.opportunity_id == o.id)
        )
    )
    return {
        **_card(o, provider),
        "description": o.description,
        "duration_months": o.duration_months,
        "payment_terms_days": o.payment_terms_days,
        "scope": [{"label": _cap(i["code"]), "value": float(i["value"])} for i in o.scope_items],
        "requirements": sorted((_requirement(r) for r in reqs), key=lambda x: not x["mandatory"]),
        "preference": list(o.transformation_gap or []),
    }


@router.post("/opportunities/{opp_id}/preview")
def preview(opp_id: uuid.UUID, body: PreviewIn, request: Request, db: Session = Depends(get_db)):
    """Run the real engine on typed answers. Nothing is saved."""
    if not _allow(request.client.host if request.client else "unknown"):
        raise HTTPException(429, "That is a lot of checks. Create a free account to keep going.")
    open_opps = load_open_opportunities(db)
    opp = open_opps.get(opp_id)
    if opp is None:
        raise HTTPException(404, "This opportunity is not open")
    sme = SME(
        id="visitor",
        name="Your business",
        sector=body.sector,
        province=body.province,
        turnover=body.annual_turnover,
        years_trading=body.years_trading,
        largest_past_contract=body.largest_past_contract,
        capability_codes=body.capability_codes,
        ownership=[],  # ownership is never asked for here, and never changes a score unless the buyer set a preference
        documents={c: DocStatus.VALID for c in body.documents},
    )
    r = match_one(opp, sme, list(open_opps.values()))
    expl, risk = explanation_of(r), risk_of(r)
    facts = {
        "fit_score": r.fit,
        "readiness_score": r.readiness,
        "gaps": expl["gaps"],
        "risk": risk,
    }
    mandatory = [g for g in expl["gaps"] if g["mandatory"]]
    return {
        "gate": r.gate.value,
        "quadrant": r.quadrant,
        "fit": r.fit,
        "readiness": r.readiness,
        "components": expl["components"],
        "gaps": expl["gaps"],
        "risk": risk,
        "fail_reasons": r.fail_reasons,
        "summary": prompts.fallback_rationale("Your business", facts)
        if r.gate.value != "fail"
        else "Not eligible: " + "; ".join(r.fail_reasons),
        "unlock": {
            "days": max((g["days"] for g in mandatory), default=0),
            "cost_zar": sum(g["cost_zar"] for g in mandatory),
            "documents": len(mandatory),
        },
        "stored": False,
    }
