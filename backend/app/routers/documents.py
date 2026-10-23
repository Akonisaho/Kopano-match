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
from ..engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE, PROVINCES, SECTORS
from ..llm import client, prompts
from ..schemas import Strict
from ..services import doc_status, rematch_for_sme

router = APIRouter(prefix="/documents", tags=["documents"])

# extension -> (allowed MIME types, magic-byte prefixes)
ALLOWED = {
    ".pdf": ({"application/pdf"}, (b"%PDF",)),
    ".png": ({"image/png"}, (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ({"image/jpeg"}, (b"\xff\xd8\xff",)),
    ".jpeg": ({"image/jpeg"}, (b"\xff\xd8\xff",)),
}
RETENTION_YEARS = 5


class ExpiryIn(Strict):
    expiry_date: date


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
    rematch_for_sme(db, user.organisation_id)  # the new document counts straight away
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


def _own_document(db: Session, user: m.User, doc_id: uuid.UUID) -> m.Document:
    doc = db.get(m.Document, doc_id)
    if doc is None or doc.organisation_id != user.organisation_id:
        raise HTTPException(404, "Not found")
    return doc


def _same_number(a: str | None, b: str | None) -> bool:
    digits = lambda x: "".join(ch for ch in (x or "") if ch.isdigit())  # noqa: E731
    return bool(digits(a)) and digits(a) == digits(b)


def extraction_checks(db: Session, doc: m.Document, got: prompts.DocumentExtraction) -> list[dict]:
    """Plain checks of what the AI read against what is already on file. A person decides."""
    org = db.get(m.Organisation, doc.organisation_id)
    out: list[dict] = []
    if got.document_type and got.document_type != doc.document_type:
        read = COMPLIANCE_CATALOGUE[got.document_type].label
        filed = COMPLIANCE_CATALOGUE[doc.document_type].label
        out.append(
            {"level": "warn", "text": f"This reads like a {read}, but it is filed as a {filed}."}
        )
    if got.expiry_date:
        if got.expiry_date < date.today():
            out.append(
                {
                    "level": "warn",
                    "text": f"The document says it expired on {got.expiry_date:%d %b %Y}.",
                }
            )
        if doc.expiry_date and doc.expiry_date != got.expiry_date:
            out.append(
                {
                    "level": "warn",
                    "text": f"The document shows {got.expiry_date:%d %b %Y} but you entered {doc.expiry_date:%d %b %Y}.",
                }
            )
    if got.registration_number and org.registration_number:
        if not _same_number(got.registration_number, org.registration_number):
            out.append(
                {
                    "level": "warn",
                    "text": "The registration number on the document does not match your account.",
                }
            )
    if (
        got.company_name
        and org.name.lower() not in got.company_name.lower()
        and got.company_name.lower() not in org.name.lower()
    ):
        out.append(
            {"level": "warn", "text": f'The document names "{got.company_name}", not "{org.name}".'}
        )
    if not out:
        out.append({"level": "ok", "text": "Nothing on the document contradicts what is on file."})
    return out


@router.post("/{doc_id}/extract")
def read_with_ai(
    doc_id: uuid.UUID, user: m.User = Depends(require_role("sme")), db: Session = Depends(get_db)
):
    """AI reads one uploaded document and drafts what it says. Sends the file to the AI provider,
    so it only runs when the business asks, and the request is audited. Nothing is saved from it."""
    doc = _own_document(db, user, doc_id)
    path = Path(doc.file_url)
    if not path.is_file() or settings.upload_dir.resolve() not in path.resolve().parents:
        raise HTTPException(404, "Not found")
    prompt = prompts.EXTRACT_DOCUMENT.format(
        docs=sorted(COMPLIANCE_CATALOGUE),
        sectors=SECTORS,
        provinces=PROVINCES,
        codes=sorted(CAPABILITIES),
    )
    got = client.call(prompt, prompts.DocumentExtraction, file=(path.read_bytes(), doc.mime_type))
    write_audit(
        db,
        user.id,
        "document_ai_read",
        "document",
        doc.id,
        new={"provider": settings.llm_provider, "read": got is not None},
    )
    db.commit()
    if got is None:
        return {"source": "unavailable", "draft": None, "checks": []}
    return {
        "source": "ai",
        "provider": settings.llm_provider,
        "draft": got.model_dump(mode="json"),
        "checks": extraction_checks(db, doc, got),
    }


@router.put("/{doc_id}/expiry")
def set_expiry(
    doc_id: uuid.UUID,
    body: ExpiryIn,
    user: m.User = Depends(require_role("sme")),
    db: Session = Depends(get_db),
):
    doc = _own_document(db, user, doc_id)
    old = doc.expiry_date
    doc.expiry_date = body.expiry_date
    write_audit(
        db,
        user.id,
        "document_expiry_set",
        "document",
        doc.id,
        old={"expiry": str(old)},
        new={"expiry": str(body.expiry_date)},
    )
    db.commit()
    rematch_for_sme(db, user.organisation_id)
    db.commit()
    return _view(doc)
