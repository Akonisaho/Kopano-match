"""Views for corporate, funder and business-support accounts."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import PROVIDER_ROLES, require_role
from ..db import get_db
from ..services import bottlenecks
from ..services import impact as impact_report
from .applications import application_status

router = APIRouter(
    prefix="/providers",
    tags=["providers"],
    dependencies=[Depends(require_role(*PROVIDER_ROLES, "admin"))],
)


def _own(user: m.User):
    """Admins see everything; providers only their own organisation's opportunities."""
    return None if user.role == "admin" else user.organisation_id


@router.get("/overview")
def overview(
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")), db: Session = Depends(get_db)
):
    own = _own(user)
    opp_q = select(m.Opportunity)
    if own:
        opp_q = opp_q.where(m.Opportunity.organisation_id == own)
    opps = list(db.scalars(opp_q))
    ids = [o.id for o in opps]
    matches = (
        list(db.scalars(select(m.Match).where(m.Match.opportunity_id.in_(ids)))) if ids else []
    )
    soon = date.today() + timedelta(days=14)
    org = db.get(m.Organisation, user.organisation_id) if user.organisation_id else None
    by_quadrant: dict[str, int] = {}
    for mt in matches:
        by_quadrant[mt.quadrant] = by_quadrant.get(mt.quadrant, 0) + 1
    return {
        "organisation": {"name": org.name, "verification_status": org.verification_status}
        if org
        else None,
        "active_opportunities": sum(1 for o in opps if o.status == "open"),
        "closing_soon": sum(1 for o in opps if o.deadline and date.today() <= o.deadline <= soon),
        "matched_smes": len({mt.sme_id for mt in matches}),
        "high_fit": sum(1 for mt in matches if float(mt.fit_score) >= 60),
        "shortlisted": sum(1 for mt in matches if mt.status == "shortlisted"),
        "flagged": sum(1 for mt in matches if mt.flagged and mt.review_status is None),
        "by_quadrant": by_quadrant,
    }


@router.get("/smes")
def verified_smes(db: Session = Depends(get_db)):
    """Directory of SMEs who chose to be visible. Ownership details are deliberately not listed."""
    rows = db.execute(
        select(m.SmeProfile, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.SmeProfile.organisation_id)
        .where(m.SmeProfile.visible_to_corporates.is_(True))
        .order_by(m.Organisation.name)
    ).all()
    ok = dict(
        db.execute(
            select(m.Verification.subject_id, func.count())
            .where(m.Verification.subject_type == "organisation", m.Verification.flagged.is_(False))
            .group_by(m.Verification.subject_id)
        ).all()
    )
    docs = dict(
        db.execute(
            select(m.Document.organisation_id, func.count()).group_by(m.Document.organisation_id)
        ).all()
    )
    return [
        {
            "id": org.id,
            "name": org.name,
            "sector": p.sector,
            "province": p.province,
            "years_trading": p.years_trading,
            "capability_codes": p.capability_codes,
            "verification_status": org.verification_status,
            "checks_passed": ok.get(org.id, 0),
            "documents_on_file": docs.get(org.id, 0),
        }
        for p, org in rows
    ]


@router.get("/bottlenecks")
def unlock_map(db: Session = Depends(get_db)):
    """The Unlock Map: the credentials holding back good-fit SMEs, with the value behind each."""
    return bottlenecks(db)


@router.get("/shortlist")
def shortlist(
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")), db: Session = Depends(get_db)
):
    own = _own(user)
    q = (
        select(m.Match, m.Opportunity, m.Organisation, m.Application)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .join(m.Organisation, m.Organisation.id == m.Match.sme_id)
        .join(m.Application, m.Application.match_id == m.Match.id, isouter=True)
        .where(m.Match.status == "shortlisted")
        .order_by(m.Match.overall_score.desc())
    )
    if own:
        q = q.where(m.Opportunity.organisation_id == own)
    return [
        {
            "match_id": mt.id,
            "opportunity": o.title,
            "sme": org.name,
            "fit": float(mt.fit_score),
            "readiness": float(mt.readiness_score),
            "quadrant": mt.quadrant,
            "risk_flags": mt.risk_flags,
            "gap_count": len(mt.explanation.get("gaps", [])),
            "application": application_status(mt, a),
        }
        for mt, o, org, a in db.execute(q)
    ]


@router.get("/impact")
def impact(
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")), db: Session = Depends(get_db)
):
    """The buyer's own impact: what was awarded, to whom (in aggregate), and how fast."""
    return impact_report(db, _own(user))


@router.get("/impact.csv")
def impact_csv(
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")), db: Session = Depends(get_db)
):
    import csv
    import io

    d = impact_report(db, _own(user))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Metric", "Value"])
    for label, value in [
        ("Applications", d["applications"]),
        ("Awards", d["awards"]),
        ("SMEs awarded", d["smes_awarded"]),
        ("Value awarded (ZAR)", round(d["value_awarded"])),
        ("Application to award conversion (%)", d["conversion_pct"]),
        ("Median days from publication to award", d["days_to_award_median"]),
        ("Awards despite an open document gap", d["awarded_despite_gap"]["awards"]),
        (
            "Value awarded despite an open document gap (ZAR)",
            round(d["awarded_despite_gap"]["value"]),
        ),
    ]:
        w.writerow([label, value])
    for flag, v in d["ownership"].items():
        w.writerow(
            [
                f"Share of value awarded to {flag.replace('_', ' ')}-owned businesses (%)",
                v["share_pct"],
            ]
        )
    for row in d["by_province"]:
        w.writerow([f"Value awarded in {row['name']} (ZAR)", round(row["value"])])
    for row in d["by_sector"]:
        w.writerow([f"Value awarded in sector {row['name']} (ZAR)", round(row["value"])])
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="kopano-impact.csv"'},
    )
