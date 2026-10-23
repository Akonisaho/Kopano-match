"""The in-app notification bell: the caller's own notices only."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import current_user
from ..db import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def mine(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(m.Notification)
        .where(m.Notification.user_id == user.id)
        .order_by(m.Notification.created_at.desc())
        .limit(20)
    )
    unread = db.scalar(
        select(func.count())
        .select_from(m.Notification)
        .where(m.Notification.user_id == user.id, m.Notification.read_at.is_(None))
    )
    return {
        "unread": unread or 0,
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "created_at": n.created_at,
                "read": n.read_at is not None,
            }
            for n in rows
        ],
    }


@router.post("/read")
def mark_all_read(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(
        update(m.Notification)
        .where(m.Notification.user_id == user.id, m.Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return {"status": "ok"}
