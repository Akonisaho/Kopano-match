"""Service notices: an in-app notification plus an email, for the people an event concerns.

The in-app copy is stored so it shows in the bell even with no email provider (and offline). The
email goes through the configured provider. Neither carries scores or documents. A failed send
never fails the request.
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


def page(heading: str, paragraphs: list[str], cta: str, link: str) -> str:
    body = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#344054">{html.escape(p)}</p>'
        for p in paragraphs
    )
    href = html.escape(link if link.startswith("http") else settings.app_url.rstrip("/") + link)
    return (
        '<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px">'
        '<div style="font-weight:800;font-size:18px;color:#1d1060;margin-bottom:18px">Kopano Match</div>'
        f'<h1 style="font-size:20px;color:#12213b;margin:0 0 14px">{html.escape(heading)}</h1>{body}'
        f'<a href="{href}" style="display:inline-block;background:#7c3aed;color:#fff;'
        "text-decoration:none;padding:11px 18px;border-radius:10px;font-weight:700;font-size:14px"
        f'">{html.escape(cta)}</a>'
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


def notify(db: Session, user: m.User, subject: str, lines: list[str], cta: str, path: str) -> None:
    """Store the in-app notice and send the email. The caller commits."""
    db.add(m.Notification(user_id=user.id, title=subject, body=" ".join(lines), link=path))
    send(user.email, user.full_name, subject, page(subject, lines, cta, path))


def users_of(db: Session, org_id) -> list[m.User]:
    return list(
        db.scalars(
            select(m.User).where(m.User.organisation_id == org_id, m.User.deleted_at.is_(None))
        )
    )


def welcome(db: Session, user: m.User) -> None:
    first = user.full_name.split()[0]
    nxt = (
        "Next, complete your business profile so we can match you."
        if user.role == "sme"
        else "Next, publish an opportunity and we will rank matching SMEs for you."
    )
    notify(
        db,
        user,
        "Welcome to Kopano Match",
        [f"Welcome, {first}. Your account is ready.", nxt],
        "Open Kopano Match",
        "/app",
    )
    db.commit()


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
        return  # a decision on a business that never applied is not worth a notice
    for u in users_of(db, match.sme_id):
        notify(db, u, subject, lines, "View the match", f"/app/matches/{match.id}")
    db.commit()


def application_received(db: Session, match: m.Match) -> None:
    opp = db.get(m.Opportunity, match.opportunity_id)
    sme = db.get(m.Organisation, match.sme_id)
    subject = f"New application: {sme.name} for {opp.title}"
    lines = [
        f"{sme.name} has applied to {opp.title}.",
        "Open the match to review the full breakdown.",
    ]
    for u in users_of(db, opp.organisation_id):
        notify(db, u, subject, lines, "Review the match", f"/app/matches/{match.id}")
    db.commit()


def match_awarded(db: Session, match: m.Match, value: float) -> None:
    opp = db.get(m.Opportunity, match.opportunity_id)
    provider = db.get(m.Organisation, opp.organisation_id)
    subject = f"Awarded: {opp.title}"
    lines = [
        f"{provider.name} has awarded {opp.title} to your business, valued at R{value:,.0f}.",
        "Open the match to see the record of the decision.",
    ]
    for u in users_of(db, match.sme_id):
        notify(db, u, subject, lines, "View the award", f"/app/matches/{match.id}")
    db.commit()


def consortium_invited(db: Session, cons: m.Consortium) -> None:
    from .services import labels_for

    opp = db.get(m.Opportunity, cons.opportunity_id)
    provider = db.get(m.Organisation, opp.organisation_id)
    members = list(
        db.scalars(select(m.ConsortiumMember).where(m.ConsortiumMember.consortium_id == cons.id))
    )
    for member in members:
        part = ", ".join(labels_for(member.scope_codes)) or "to be agreed"
        subject = f"Consortium invitation: {opp.title}"
        lines = [
            f"{provider.name} proposes that your business joins a group of {len(members)} "
            f"businesses for {opp.title}. Your part: {part}.",
            "Partner names are shared once everyone has accepted. Please respond.",
        ]
        for u in users_of(db, member.sme_id):
            notify(db, u, subject, lines, "Review the invitation", "/app/consortia")
    db.commit()


def consortium_response(db: Session, cons: m.Consortium, member: m.ConsortiumMember) -> None:
    opp = db.get(m.Opportunity, cons.opportunity_id)
    sme = db.get(m.Organisation, member.sme_id)
    members = list(
        db.scalars(select(m.ConsortiumMember).where(m.ConsortiumMember.consortium_id == cons.id))
    )
    names = {
        o.id: o.name
        for o in db.scalars(
            select(m.Organisation).where(m.Organisation.id.in_([x.sme_id for x in members]))
        )
    }
    path = f"/app/opportunities/{opp.id}"
    if cons.status == "declined":
        for u in users_of(db, opp.organisation_id):
            notify(
                db,
                u,
                f"Consortium declined: {opp.title}",
                [
                    f"{sme.name} declined the consortium invitation. The proposal has lapsed; you can invite a new group."
                ],
                "Open the opportunity",
                path,
            )
        for x in members:
            if x.sme_id != member.sme_id:
                for u in users_of(db, x.sme_id):
                    notify(
                        db,
                        u,
                        f"Consortium lapsed: {opp.title}",
                        ["A partner declined, so this proposal has lapsed."],
                        "See your invitations",
                        "/app/consortia",
                    )
    elif cons.status == "formed":
        for u in users_of(db, opp.organisation_id):
            notify(
                db,
                u,
                f"Consortium formed: {opp.title}",
                [f"All {len(members)} businesses accepted: {', '.join(sorted(names.values()))}."],
                "Open the opportunity",
                path,
            )
        for x in members:
            others = sorted(n for i, n in names.items() if i != x.sme_id)
            for u in users_of(db, x.sme_id):
                notify(
                    db,
                    u,
                    f"Consortium formed: {opp.title}",
                    [f"Everyone accepted. Your partners are {', '.join(others)}."],
                    "See the consortium",
                    "/app/consortia",
                )
    else:
        done = sum(1 for x in members if x.response == "accepted")
        for u in users_of(db, opp.organisation_id):
            notify(
                db,
                u,
                f"Consortium update: {opp.title}",
                [f"{sme.name} accepted ({done} of {len(members)})."],
                "Open the opportunity",
                path,
            )
    db.commit()
