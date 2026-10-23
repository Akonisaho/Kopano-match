import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
ALGORITHM = "HS256"

# Roles that publish opportunities and review matches. Same engine, different opportunity kinds.
PROVIDER_ROLES = ("corporate", "funder", "support")
KINDS_BY_ROLE = {
    "corporate": ("procurement",),
    "funder": ("grant", "funding", "investor"),
    "support": ("support",),
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def issue_token(user: User) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": str(user.id), "role": user.role, "exp": exp}, settings.jwt_secret, ALGORITHM
    )


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    unauthorised = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("purpose") is not None:  # e.g. a half-finished two-step sign-in
            raise KeyError("not an access token")
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorised from None
    if user is None or user.deleted_at is not None:
        raise unauthorised
    return user


def require_role(*roles: str):
    """Deny by default: every route names the roles it admits."""

    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Role not permitted")
        return user

    return dependency


def own_org_or_404(user: User, organisation_id: uuid.UUID) -> None:
    """Object-level authorisation. 404 rather than 403 so ids cannot be probed."""
    if user.role != "admin" and user.organisation_id != organisation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def issue_mfa_token(user: User) -> str:
    """Proves the password step only. Valid for five minutes and useless as an access token."""
    exp = datetime.now(UTC) + timedelta(minutes=5)
    return jwt.encode(
        {"sub": str(user.id), "purpose": "mfa", "exp": exp}, settings.jwt_secret, ALGORITHM
    )


def read_mfa_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("purpose") != "mfa":
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
