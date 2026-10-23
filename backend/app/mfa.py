"""Authenticator-app sign-in (TOTP, RFC 6238) and recovery codes.

The secret is encrypted at rest with an application key. Outside dev that key must be supplied
(MFA_ENCRYPTION_KEY); in dev it is derived from the JWT secret so a local run needs no setup.
A code cannot be used twice: the accepted time step is remembered and must move forward.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time

import segno
from cryptography.fernet import Fernet

from .config import settings

ISSUER = "Kopano Match"
STEP_SECONDS = 30


def _fernet() -> Fernet:
    key = (
        settings.mfa_encryption_key
        or base64.urlsafe_b64encode(
            hashlib.sha256(("mfa:" + settings.jwt_secret).encode()).digest()
        ).decode()
    )
    return Fernet(key.encode())


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def totp(secret: str, at: float | None = None, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    counter = int((time.time() if at is None else at) // STEP_SECONDS)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**digits
    return f"{value:0{digits}d}"


def matching_step(secret: str, code: str, window: int = 1) -> int | None:
    """The time step this code belongs to, within one step either side, or None."""
    code = code.strip().replace(" ", "")
    now = time.time()
    for drift in range(-window, window + 1):
        at = now + drift * STEP_SECONDS
        if hmac.compare_digest(totp(secret, at), code):
            return int(at // STEP_SECONDS)
    return None


def provisioning_uri(secret: str, email: str) -> str:
    return (
        f"otpauth://totp/{ISSUER}:{email}?secret={secret}&issuer={ISSUER}"
        f"&algorithm=SHA1&digits=6&period={STEP_SECONDS}"
    )


def qr_data_uri(uri: str) -> str:
    """The QR code as an image data URI, so the page needs no QR library and renders no raw HTML."""
    return segno.make(uri).svg_data_uri(scale=5, border=2)


def new_recovery_codes(n: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
