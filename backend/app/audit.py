import uuid

from sqlalchemy.orm import Session

from .models import AuditLog


def write_audit(
    db: Session,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: object = None,
    old: dict | None = None,
    new: dict | None = None,
) -> None:
    """Added to the caller's transaction, so the state change and its audit row commit together."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            old_value=old,
            new_value=new,
        )
    )
