"""Transactional email behind one interface.

`log` keeps messages in memory (tests, and local runs with no provider). `brevo` sends through
Brevo's transactional API. Brevo needs a verified sender address on the account, and acts as an
operator of personal information, so an operator agreement is needed before real deployment.
"""

import json
import logging
import re
import urllib.request
from abc import ABC, abstractmethod

from ..config import settings

log = logging.getLogger("kopano.email")
OUTBOX: list[dict] = []  # only filled by the log sender
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
TIMEOUT_SECONDS = 10


class EmailSender(ABC):
    @abstractmethod
    def send(self, to_email: str, to_name: str, subject: str, html: str) -> None:
        """Send one message. Raise on failure; the caller decides what a failure means."""


class LogEmailSender(EmailSender):
    def send(self, to_email: str, to_name: str, subject: str, html: str) -> None:
        OUTBOX.append({"to": to_email, "name": to_name, "subject": subject, "html": html})
        links = re.findall(r'href="([^"]+)"', html) if settings.environment == "dev" else []
        log.info("email (log mode) to=%s subject=%r links=%s", to_email, subject, links)


class BrevoEmailSender(EmailSender):
    def send(self, to_email: str, to_name: str, subject: str, html: str) -> None:
        body = json.dumps(
            {
                "sender": {"name": settings.email_from_name, "email": settings.email_from},
                "to": [{"email": to_email, "name": to_name}],
                "subject": subject,
                "htmlContent": html,
            }
        ).encode()
        req = urllib.request.Request(
            BREVO_URL,
            data=body,
            # The key travels in a header, never in the URL
            headers={
                "api-key": settings.brevo_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS):  # noqa: S310  # nosec B310 - fixed https URL
            pass


def email_sender() -> EmailSender:
    if settings.email_provider == "brevo":
        if settings.brevo_api_key and settings.email_from:
            return BrevoEmailSender()
        log.warning(
            "EMAIL_PROVIDER=brevo but BREVO_API_KEY or EMAIL_FROM is missing; using log mode"
        )
    return LogEmailSender()
