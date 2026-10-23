"""Check the two optional keys and say exactly what to fix.

Run from backend/:
    python scripts/check_keys.py
    python scripts/check_keys.py --send-test you@gmail.com     # also sends one real test email

Reads backend/.env. Never prints a key.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.email import BrevoEmailSender  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import client as llm  # noqa: E402


def http_message(err: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(err.read().decode("utf8", "replace"))
        inner = body.get("error", body)
        return (
            str(inner.get("message") or inner)[:200]
            if isinstance(inner, dict)
            else str(inner)[:200]
        )
    except Exception:  # noqa: BLE001
        return err.reason or "no detail"


def check_gemini() -> bool | None:
    if not settings.gemini_api_key:
        print(
            "Gemini   not set     Summaries and drafting use the built-in fallbacks. See docs/KEYS_AND_EMAIL.md."
        )
        return None
    try:
        reply = llm._gemini("Reply with the single word OK.")  # noqa: SLF001
        print(
            f"Gemini   PASS        model {settings.gemini_model} answered: {reply.strip()[:30]!r}"
        )
        return True
    except urllib.error.HTTPError as e:
        hint = {
            400: "The key looks malformed or not valid. Create a new one and paste it with no spaces or quotes.",
            403: "The key is not allowed to use this API. Create it in Google AI Studio.",
            404: f"Model '{settings.gemini_model}' was not found. Set GEMINI_MODEL to a current model name.",
            429: "You are out of quota or rate-limited. Wait a minute, or check your plan.",
        }.get(e.code, "Unexpected answer from Google.")
        print(f"Gemini   FAIL ({e.code})   {http_message(e)}\n                     {hint}")
        return False
    except Exception as e:  # noqa: BLE001
        print(
            f"Gemini   FAIL        {type(e).__name__}: could not reach Google. Check the internet connection."
        )
        return False


def brevo_get(path: str):
    req = urllib.request.Request(
        "https://api.brevo.com/v3" + path,
        headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  # nosec B310 - fixed https URL
        return json.load(resp)


def check_brevo(send_to: str | None) -> bool | None:
    if settings.email_provider != "brevo":
        print(
            "Email    off         EMAIL_PROVIDER is not 'brevo'. Notices still appear in the app bell."
        )
        return None
    if not settings.brevo_api_key or not settings.email_from:
        print("Email    FAIL        BREVO_API_KEY and EMAIL_FROM must both be set in backend/.env.")
        return False
    try:
        account = brevo_get("/account")
        print(f"Email    PASS        Brevo key works (account {account.get('email', '?')}).")
    except urllib.error.HTTPError as e:
        print(
            f"Email    FAIL ({e.code})   {http_message(e)}\n                     The Brevo API key is not valid. Create a new one under SMTP & API."
        )
        return False
    except Exception as e:  # noqa: BLE001
        print(f"Email    FAIL        {type(e).__name__}: could not reach Brevo.")
        return False
    try:
        senders = brevo_get("/senders").get("senders", [])
        mine = next(
            (s for s in senders if s.get("email", "").lower() == settings.email_from.lower()), None
        )
        if mine is None:
            print(
                f"Sender   FAIL        {settings.email_from} is not a sender on your Brevo account. Add it under Senders and verify it."
            )
            return False
        if not mine.get("active", False):
            print(
                f"Sender   FAIL        {settings.email_from} exists but is not verified yet. Open the verification email from Brevo."
            )
            return False
        print(f"Sender   PASS        {settings.email_from} is verified.")
    except Exception:  # noqa: BLE001
        print(
            "Sender   unknown     Could not read the sender list; the test email below will tell you."
        )
    if send_to:
        try:
            BrevoEmailSender().send(
                send_to,
                "Kopano Match test",
                "Kopano Match test email",
                "<p>If you can read this, Brevo is set up correctly for Kopano Match.</p>",
            )
            print(f"Test     PASS        Sent to {send_to}. Check the inbox, and the spam folder.")
        except urllib.error.HTTPError as e:
            print(f"Test     FAIL ({e.code})   {http_message(e)}")
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--send-test", metavar="EMAIL", help="send one real test email to this address")
    args = ap.parse_args()
    print(f"Environment: {settings.environment}\n")
    results = [check_gemini(), check_brevo(args.send_test)]
    if settings.environment == "dev" and not settings.mfa_encryption_key:
        print(
            "MFA key  dev default  Fine locally. Outside dev, set MFA_ENCRYPTION_KEY (see docs/KEYS_AND_EMAIL.md)."
        )
    sys.exit(1 if any(r is False for r in results) else 0)


if __name__ == "__main__":
    main()
