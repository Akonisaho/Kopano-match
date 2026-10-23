"""Reference data for the UI pickers, and an anonymised showcase for the landing page.

Public by design and contains nothing personal: counts, scores and one example gap, no names.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE, PROVINCES, SECTORS
from ..schemas import OWNERSHIP_FLAGS
from ..services import consortium as build_consortium

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/taxonomy")
def taxonomy():
    return {
        "sectors": SECTORS,
        "provinces": PROVINCES,
        "ownership": list(OWNERSHIP_FLAGS),
        "capabilities": [
            {"code": c, "sector": s, "label": lbl} for c, (s, lbl) in CAPABILITIES.items()
        ],
        "credentials": [
            {
                "code": c.code,
                "label": c.label,
                "issuer": c.issuer,
                "days": c.days,
                "cost_zar": c.cost_zar,
            }
            for c in COMPLIANCE_CATALOGUE.values()
        ],
    }


@router.get("/showcase")
def showcase(db: Session = Depends(get_db)):
    """Real aggregates from the live data, shaped for the landing page. No identities."""
    smes = db.scalar(select(func.count()).select_from(m.SmeProfile)) or 0
    open_opps = list(
        db.scalars(
            select(m.Opportunity).where(
                m.Opportunity.status == "open", m.Opportunity.kind == "procurement"
            )
        )
    )
    total_opps = db.scalar(
        select(func.count()).select_from(m.Opportunity).where(m.Opportunity.status == "open")
    )
    if not open_opps:
        return {"smes": smes, "opportunities": total_opps or 0, "chart": None}

    counts = dict(
        db.execute(
            select(m.Match.opportunity_id, func.count()).group_by(m.Match.opportunity_id)
        ).all()
    )
    opp = max(open_opps, key=lambda o: counts.get(o.id, 0))
    rows = list(db.scalars(select(m.Match).where(m.Match.opportunity_id == opp.id)))
    dots = [
        {
            "fit": float(r.fit_score),
            "readiness": float(r.readiness_score),
            "quadrant": r.quadrant,
            "overtrading": bool(r.risk_flags.get("overtrading")),
        }
        for r in rows
    ]
    # One real, anonymous example of a coachable match and what stands in its way
    example = None
    for r in sorted(rows, key=lambda x: -float(x.fit_score)):
        gaps = [g for g in r.explanation.get("gaps", []) if g["mandatory"]]
        if r.quadrant == "coachable" and gaps:
            example = {
                "fit": float(r.fit_score),
                "readiness": float(r.readiness_score),
                "days": max(g["days"] for g in gaps),
                "cost_zar": sum(g["cost_zar"] for g in gaps),
                "gaps": [
                    {
                        "label": g["label"],
                        "issuer": g["issuer"],
                        "days": g["days"],
                        "cost_zar": g["cost_zar"],
                        "also_unlocks": g["also_unlocks"],
                    }
                    for g in gaps
                ],
            }
            break
    group = None
    for o in sorted(open_opps, key=lambda x: -float(x.contract_value)):
        built = build_consortium(db, o.id)
        if built and built[2]:
            c = built[2]
            group = {
                "opportunity_value": float(o.contract_value),
                "members": len(c.member_sme_ids),
                "coverage_pct": c.coverage_pct,
                "scope_lines": len(o.scope_items),
            }
            break
    return {
        "smes": smes,
        "opportunities": total_opps or 0,
        "chart": {"contract_value": float(opp.contract_value), "dots": dots},
        "example": example,
        "consortium": group,
    }


@router.get("/evaluation")
def evaluation_report():
    """The engine's measured behaviour on synthetic data, with its limits. Public by design."""
    from ..evaluation import evaluate

    return evaluate()


@router.get("/mode")
def mode():
    """How AI and email are wired right now, so the pages can say so truthfully."""
    from ..config import settings

    return {
        "ai": settings.llm_provider
        if settings.llm_provider == "local" or settings.gemini_api_key
        else "off",
        "email": settings.email_provider,
    }
