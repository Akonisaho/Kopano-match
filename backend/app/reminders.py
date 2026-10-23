"""Document expiry reminders. Run on a schedule, or from the admin screen.

A business hears once when a credential is about to expire (within 30 days) and once when it has
expired. Each send is recorded in the audit log, which is also how a repeat is avoided.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .audit import write_audit
from .engine.taxonomy import COMPLIANCE_CATALOGUE
from .notifications import notify, users_of

WARN_DAYS = 30
DEADLINE_DAYS = 7
GOOD_FIT = 60


def run(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    horizon = today + timedelta(days=WARN_DAYS)
    done = {
        (a.entity_id, (a.new_value or {}).get("stage"))
        for a in db.scalars(select(m.AuditLog).where(m.AuditLog.action == "document_reminder"))
    }
    docs = db.scalars(
        select(m.Document).where(
            m.Document.expiry_date.is_not(None),
            m.Document.expiry_date <= horizon,
            m.Document.review_status.is_distinct_from("rejected"),
        )
    )
    sent = 0
    touched = 0
    for doc in docs:
        stage = "expired" if doc.expiry_date < today else "expiring"
        if (str(doc.id), stage) in done:
            continue
        cred = COMPLIANCE_CATALOGUE.get(doc.document_type)
        label = cred.label if cred else doc.document_type
        if stage == "expired":
            subject = f"Expired: your {label}"
            lines = [f"Your {label} expired on {doc.expiry_date:%d %b %Y}."]
        else:
            days = (doc.expiry_date - today).days
            subject = f"Expiring soon: your {label}"
            lines = [f"Your {label} expires on {doc.expiry_date:%d %b %Y}, in {days} days."]
        if cred:
            cost = f"R{cred.cost_zar:,}" if cred.cost_zar else "no cost"
            lines.append(
                f"Renewing it with {cred.issuer} takes about {cred.renew_days} days and costs {cost}."
            )
        lines.append("Upload the renewed document to keep your matches award-ready.")
        for u in users_of(db, doc.organisation_id):
            notify(db, u, subject, lines, "Upload the renewal", "/app/documents")
            sent += 1
        write_audit(db, None, "document_reminder", "document", doc.id, new={"stage": stage})
        touched += 1
    alerts = _deadline_alerts(db, today)
    db.commit()
    return {"notices_sent": sent + alerts, "documents": touched, "deadline_alerts": alerts}


def _deadline_alerts(db: Session, today: date) -> int:
    """Tell a good-fit business, once, that an opportunity it has not applied to is closing."""
    done = {
        a.entity_id
        for a in db.scalars(select(m.AuditLog).where(m.AuditLog.action == "deadline_alert"))
    }
    closing = db.scalars(
        select(m.Opportunity).where(
            m.Opportunity.status == "open",
            m.Opportunity.deadline.is_not(None),
            m.Opportunity.deadline >= today,
            m.Opportunity.deadline <= today + timedelta(days=DEADLINE_DAYS),
        )
    )
    sent = 0
    for opp in closing:
        matches = db.scalars(
            select(m.Match).where(
                m.Match.opportunity_id == opp.id,
                m.Match.fit_score >= GOOD_FIT,
                m.Match.gate != "fail",
                m.Match.status.in_(["matched", "shortlisted"]),
            )
        )
        for mt in matches:
            applied = db.scalar(select(m.Application.id).where(m.Application.match_id == mt.id))
            if applied or str(mt.id) in done:
                continue
            days = (opp.deadline - today).days
            open_gaps = len((mt.explanation or {}).get("gaps", []))
            lines = [
                f"{opp.title} closes on {opp.deadline:%d %b %Y}, in {days} day{'s' if days != 1 else ''}.",
                f"You are a strong fit (fit {float(mt.fit_score):.0f}, readiness {float(mt.readiness_score):.0f}).",
                f"{open_gaps} document{'s' if open_gaps != 1 else ''} still stand between you and an award."
                if open_gaps
                else "You have everything the buyer asked for.",
            ]
            for u in users_of(db, mt.sme_id):
                notify(
                    db,
                    u,
                    f"Closing soon: {opp.title}",
                    lines,
                    "Open the match",
                    f"/app/matches/{mt.id}",
                )
                sent += 1
            write_audit(db, None, "deadline_alert", "match", mt.id, new={"stage": "closing"})
    return sent
