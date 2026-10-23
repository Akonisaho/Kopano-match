"""Connect a procurement system. A buyer creates an API key, and its system posts opportunities.

The key is shown once and only a hash is stored. It belongs to one organisation and can only add
opportunities to it. Revoking it stops the feed at once.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..audit import write_audit
from ..auth import PROVIDER_ROLES, require_role
from ..db import get_db
from ..schemas import OpportunityIn, Strict
from ..services import run_matching
from .opportunities import _persist, _summary

router = APIRouter(prefix="/ingest", tags=["ingest"])
MAX_PER_CALL = 50
MAX_KEYS = 5


class KeyIn(Strict):
    name: str = Field(min_length=2, max_length=60)


class IngestIn(Strict):
    opportunities: list[OpportunityIn] = Field(min_length=1, max_length=MAX_PER_CALL)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _view(k: m.ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
        "revoked": k.revoked_at is not None,
    }


@router.get("/keys")
def keys(user: m.User = Depends(require_role(*PROVIDER_ROLES)), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(m.ApiKey)
        .where(m.ApiKey.organisation_id == user.organisation_id)
        .order_by(m.ApiKey.created_at.desc())
    )
    return [_view(k) for k in rows]


@router.post("/keys", status_code=201)
def create_key(
    body: KeyIn,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    live = db.scalars(
        select(m.ApiKey.id).where(
            m.ApiKey.organisation_id == user.organisation_id, m.ApiKey.revoked_at.is_(None)
        )
    ).all()
    if len(live) >= MAX_KEYS:
        raise HTTPException(409, f"At most {MAX_KEYS} active keys. Revoke one first.")
    key = "kmk_" + secrets.token_urlsafe(32)
    row = m.ApiKey(
        organisation_id=user.organisation_id,
        created_by=user.id,
        name=body.name,
        prefix=key[:10],
        key_hash=_hash(key),
    )
    db.add(row)
    db.flush()
    write_audit(db, user.id, "ingest_key_created", "api_key", row.id, new={"name": body.name})
    db.commit()
    return {**_view(row), "key": key, "note": "Copy it now. It is not shown again."}


@router.post("/keys/{key_id}/revoke")
def revoke_key(
    key_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    row = db.get(m.ApiKey, key_id)
    if row is None or row.organisation_id != user.organisation_id:
        raise HTTPException(404, "Not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        write_audit(db, user.id, "ingest_key_revoked", "api_key", row.id)
        db.commit()
    return _view(row)


@router.post("/opportunities", status_code=201)
def ingest(
    body: IngestIn,
    x_api_key: str = Header(default=""),
    match: bool = True,
    db: Session = Depends(get_db),
):
    """Called by the buyer's own system, with the key in the X-API-Key header."""
    row = (
        db.scalar(select(m.ApiKey).where(m.ApiKey.key_hash == _hash(x_api_key)))
        if x_api_key
        else None
    )
    author = db.get(m.User, row.created_by) if row and row.revoked_at is None else None
    if author is None or author.deleted_at is not None:
        raise HTTPException(401, "Invalid or revoked API key")
    created = [_persist(db, author, o) for o in body.opportunities]
    row.last_used_at = datetime.now(UTC)
    write_audit(
        db,
        author.id,
        "ingest_opportunities",
        "api_key",
        row.id,
        new={"count": len(created), "prefix": row.prefix},
    )
    db.commit()
    if match:
        for o in created:
            run_matching(db, o.id)
        db.commit()
    return {"created": len(created), "opportunities": [_summary(o) for o in created]}
