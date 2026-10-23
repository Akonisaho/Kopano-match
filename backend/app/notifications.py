"""Service emails: a welcome, a shortlist notice, an application notice.

Each one goes to the people the event concerns and carries no scores, documents or personal
details beyond the names already known to the recipient. A failed send never fails the request.
"""

import html
import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .adapters.email import email_sender
from .config import settings

log = logging.getLogger("kopano.notifications")


def _page(heading: str, paragraphs: list[str], cta: str, path: str) -> str:
    body = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#344054">{html.escape(p)}</p>'
        for p in paragraphs
    )
    return (
        '<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px">'
        '<div style="font-weight:800;font-size:18px;color:#1d1060;margin-bottom:18px">Kopano Match</div>'
        f'<h1 style="font-size:20px;color:#12213b;margin:0 0 14px">{html.escape(heading)}</h1>{body}'
        f'<a href="{html.escape(settings.app_url.rstrip("/") + path)}" '
        'style="display:inline-block;background:#7c3aed;color:#fff;text-decoration:none;'
        f'padding:11px 18px;border-radius:10px;font-weight:700;font-size:14px">{html.escape(cta)}</a>'
        '<p style="margin-top:28px;font-size:12px;color:#8590a3">You are receiving this service '
        "message because of activity on your Kopano Match account. This is a pilot; verification "
        "sources shown in the app are labelled where they are simulated.</p></div>"
    )


def send(to_email: str, to_name: str, subject: str, html_body: str) -> None:
    """Fire and forget. Log mode runs inline; a real provider runs on a short-lived thread."""

    def run() -> None:
        try:
            email_sender().send(to_email, to_name, subject, html_body)
        except Exception:  # noqa: BLE001 - never let an email problem reach the user
            log.warning("email send failed", exc_info=False)

    if settings.email_provider == "brevo":
        threading.Thread(target=run, daemon=True).start()
    else:
        run()


def _users_of(db: Session, org_id) -> list[m.User]:
    return list(
        db.scalars(
            select(m.User).where(m.User.organisation_id == org_id, m.User.deleted_at.is_(None))
        )
    )


def welcome(user: m.User) -> None:
    first = user.full_name.split()[0]
    nxt = (
        "Next, complete your business profile so we can match you."
        if user.role == "sme"
        else "Next, publish an opportunity and we will rank matching SMEs for you."
    )
    send(
        user.email,
        user.full_name,
        "Welcome to Kopano Match",
        _page(f"Welcome, {first}", ["Your account is ready.", nxt], "Open Kopano Match", "/app"),
    )


def match_decided(db: Session, match: m.Match, new_status: str) -> None:
    opp = db.get(m.Opportunity, match.opportunity_id)
    provider = db.get(m.Organisation, opp.organisation_id)
    applied = db.scalar(select(m.Application.id).where(m.Application.match_id == match.id))
    if new_status == "shortlisted":
        subject = f"You have been shortlisted: {opp.title}"
        lines = [
            f"{provider.name} has shortlisted your business for {opp.title}.",
            "Open the match to see where you stand and what is left to do.",
        ]
    elif new_status == "rejected" and applied:
        subject = f"Update on your application: {opp.title}"
        lines = [
            f"{provider.name} has decided not to take your application for {opp.title} further.",
            "You can see your position and the gaps on other opportunities in your dashboard.",
        ]
    else:
        return  # a decision on a business that never applied is not worth an email
    for u in _users_of(db, match.sme_id):
        send(
            u.email,
            u.full_name,
            subject,
            _page(subject, lines, "View the match", f"/app/matches/{match.id}"),
        )


def application_received(db: Session, match: m.Match) -> None:
    opp = db.get(m.Opportunity, match.opportunity_id)
    sme = db.get(m.Organisation, match.sme_id)
    subject = f"New application: {sme.name} for {opp.title}"
    lines = [
        f"{sme.name} has applied to {opp.title}.",
        "Open the match to review the full breakdown.",
    ]
    for u in _users_of(db, opp.organisation_id):
        send(
            u.email,
            u.full_name,
            subject,
            _page(subject, lines, "Review the match", f"/app/matches/{match.id}"),
        )
