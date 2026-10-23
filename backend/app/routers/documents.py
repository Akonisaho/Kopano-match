"""Uploads. Files go to local disk under uploads/<org_id>/<uuid>.<ext>, metadata to PostgreSQL.

Served only through an authenticated endpoint, never as static files.
"""

import hashlib
import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..adapters.base import ScannerUnavailable
from ..adapters.mock import malware_scanner
from ..audit import write_audit
from ..auth import current_user, own_org_or_404, require_role
from ..config import settings
from ..db import get_db
from ..engine.taxonomy import COMPLIANCE_CATALOGUE
from ..services import doc_status

router = APIRouter(prefix="/documents", tags=["documents"])

# extension -> (allowed MIME types, magic-byte prefixes)
ALLOWED = {
    ".pdf": ({"application/pdf"}, (b"%PDF",)),
    ".png": ({"image/png"}, (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ({"image/jpeg"}, (b"\xff\xd8\xff",)),
    ".jpeg": ({"image/jpeg"}, (b"\xff\xd8\xff",)),
}
RETENTION_YEARS = 5


def _view(d: m.Document) -> dict:
    return {
        "id": d.id,
        "document_type": d.document_type,
        "issuer": d.issuer,
        "expiry_date": d.expiry_date,
        "status": doc_status(d).value,
        "uploaded_at": d.uploaded_at,
        "has_file": d.file_url != "none",
    }


def purge_organisation_files(db: Session, org_id: uuid.UUID) -> int:
    """Delete an organisation's uploaded files from disk. Records stay, with no file attached."""
    root = settings.upload_dir.resolve()
    deleted = 0
    for doc in db.scalars(select(m.Document).where(m.Document.organisation_id == org_id)):
        path = Path(doc.file_url)
        if doc.file_url != "none" and path.is_file() and root in path.resolve().parents:
            path.unlink()
            deleted += 1
        doc.file_url = "none"
    return deleted


@router.post("", status_code=201)
async def upload(
    document_type: str = Form(...),
    expiry_date: date | None = Form(default=None),
    file: UploadFile = File(...),
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    if document_type not in COMPLIANCE_CATALOGUE:
        raise HTTPException(422, "Unknown document type")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Only PDF, PNG and JPG files are accepted")
    mimes, magics = ALLOWED[ext]
    if file.content_type not in mimes:
        raise HTTPException(415, "File type does not match its extension")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File exceeds the size limit")
    try:
        scan = malware_scanner().scan(data)
    except ScannerUnavailable:
        # Fail closed: an unscanned file is never stored
        write_audit(db, user.id, "document_scan_unavailable", "document", None)
        db.commit()
        raise HTTPException(
            503, "The security scan is not available right now. Try again in a few minutes."
        ) from None
    if not scan.clean:
        write_audit(
            db,
            user.id,
            "document_rejected_malware",
            "document",
            None,
            new={"signature": scan.signature, "scanner": scan.source_label},
        )
        db.commit()
        raise HTTPException(422, "This file was rejected by the security scan")
    # The scanner sees everything that passed the cheap checks; the type check comes last
    if not data.startswith(magics):
        raise HTTPException(415, "File content does not match its type")

    digest = hashlib.sha256(data).hexdigest()
    reused_elsewhere = db.scalar(
        select(m.Document.id).where(
            m.Document.hash_value == digest, m.Document.organisation_id != user.organisation_id
        )
    )
    org_dir = settings.upload_dir / str(user.organisation_id)
    org_dir.mkdir(parents=True, exist_ok=True)
    path = org_dir / f"{uuid.uuid4()}{ext}"  # random name: the client's filename is never used
    path.write_bytes(data)

    issuer = COMPLIANCE_CATALOGUE[document_type].issuer
    doc = m.Document(
        organisation_id=user.organisation_id,
        document_type=document_type,
        issuer=issuer,
        file_url=str(path),
        mime_type=file.content_type,
        size_bytes=len(data),
        hash_value=digest,
        expiry_date=expiry_date,
        retention_until=date.today() + timedelta(days=365 * RETENTION_YEARS),
    )
    db.add(doc)
    db.flush()
    expired = expiry_date is not None and expiry_date < date.today()
    result = "duplicate_hash" if reused_elsewhere else ("expired" if expired else "verified")
    db.add(
        m.Verification(
            subject_type="document",
            subject_id=doc.id,
            provider="internal",
            result=result,
            confidence=1.0 if result == "verified" else 0.0,
            source_label="internal checks (type, size, expiry, hash)",
            flagged=result == "duplicate_hash",
            retention_until=doc.retention_until,
        )
    )
    write_audit(
        db,
        user.id,
        "document_upload",
        "document",
        doc.id,
        new={"type": document_type, "result": result},
    )
    db.commit()
    return {**_view(doc), "verification": result}


@router.get("")
def list_documents(user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)):
    docs = db.scalars(
        select(m.Document)
        .where(m.Document.organisation_id == user.organisation_id)
        .order_by(m.Document.uploaded_at.desc())
    )
    return [_view(d) for d in docs]


@router.get("/{doc_id}/file")
def download(
    doc_id: uuid.UUID, user: m.User = Depends(current_user), db: Session = Depends(get_db)
):
    doc = db.get(m.Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Not found")
    own_org_or_404(user, doc.organisation_id)
    path = Path(doc.file_url)
    if not path.is_file() or settings.upload_dir.resolve() not in path.resolve().parents:
        raise HTTPException(404, "Not found")
    write_audit(db, user.id, "document_download", "document", doc.id)
    db.commit()
    return FileResponse(
        path, media_type=doc.mime_type, headers={"Content-Disposition": "attachment"}
    )
