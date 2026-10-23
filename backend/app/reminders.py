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
    db.commit()
    return {"notices_sent": sent, "documents": touched}
