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
    """The email shell. Tables and inline styles only, because mail clients ignore most CSS."""
    body = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.65;color:#344054">{html.escape(p)}</p>'
        for p in paragraphs
    )
    href = html.escape(link if link.startswith("http") else settings.app_url.rstrip("/") + link)
    font = "font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif"
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#f3f1fb" '
        f'style="background:#f3f1fb;padding:28px 12px;{font}"><tr><td align="center">'
        '<table role="presentation" width="580" cellpadding="0" cellspacing="0" '
        'style="width:100%;max-width:580px;background:#ffffff;border-radius:16px;overflow:hidden;'
        'border:1px solid #e6e2f5">'
        # header band, the same gradient as the app's welcome banner
        '<tr><td bgcolor="#1d1060" style="background:#1d1060;'
        'background-image:linear-gradient(135deg,#0f1b4d 0%,#3b1b8f 60%,#7c3aed 100%);padding:26px 32px">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#c4b5fd">DIGI DIVA</div>'
        '<div style="font-size:22px;font-weight:800;color:#ffffff;margin-top:4px">Kopano Match</div>'
        "</td></tr>"
        f'<tr><td style="padding:32px 32px 8px"><h1 style="font-size:22px;line-height:1.3;'
        f'color:#12213b;margin:0 0 16px">{html.escape(heading)}</h1>{body}</td></tr>'
        '<tr><td style="padding:8px 32px 34px">'
        f'<a href="{href}" style="display:inline-block;background:#7c3aed;'
        "background-image:linear-gradient(90deg,#7c3aed,#c026d3);color:#ffffff;text-decoration:none;"
        f'padding:13px 24px;border-radius:10px;font-weight:700;font-size:15px">{html.escape(cta)}</a>'
        "</td></tr>"
        '<tr><td bgcolor="#faf9fe" style="background:#faf9fe;border-top:1px solid #eeeaf8;padding:18px 32px">'
        '<p style="margin:0;font-size:12px;line-height:1.6;color:#8590a3">You are receiving this '
        "service message because of activity on your Kopano Match account. This is a pilot; "
        "verification sources shown in the app are labelled where they are simulated.</p>"
        "</td></tr></table></td></tr></table>"
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


def feedback_received(db: Session, fb: m.Feedback) -> None:
    provider = db.get(m.Organisation, fb.provider_org_id)
    for u in users_of(db, fb.sme_id):
        notify(
            db,
            u,
            "New feedback on your work",
            [
                f"{provider.name} left feedback on a recent award.",
                "You can respond to it, or dispute it if you think it is unfair.",
            ],
            "Read the feedback",
            "/app/feedback",
        )
    db.commit()


def feedback_answered(db: Session, fb: m.Feedback, disputed: bool) -> None:
    sme = db.get(m.Organisation, fb.sme_id)
    if disputed:
        subject = f"Feedback disputed: {sme.name}"
        lines = [f"{sme.name} disputed your feedback. A reviewer will look at it and decide."]
        targets = users_of(db, fb.provider_org_id) + list(
            db.scalars(select(m.User).where(m.User.role == "admin", m.User.deleted_at.is_(None)))
        )
    else:
        subject = f"{sme.name} responded to your feedback"
        lines = ["The business added a response to your feedback."]
        targets = users_of(db, fb.provider_org_id)
    for u in targets:
        notify(db, u, subject, lines, "Open feedback", "/app/feedback")
    db.commit()


def feedback_resolved(db: Session, fb: m.Feedback) -> None:
    outcome = "removed" if fb.status == "removed" else "kept"
    for org_id in (fb.sme_id, fb.provider_org_id):
        for u in users_of(db, org_id):
            notify(
                db,
                u,
                "Feedback dispute decided",
                [
                    f"A reviewer looked at the dispute and the feedback was {outcome}.",
                    fb.resolution_note or "",
                ],
                "Open feedback",
                "/app/feedback",
            )
    db.commit()
