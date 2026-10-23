"""Local mode: reads and compares text on this computer, with no outside service.

It is real parsing, not a pretend answer. A PDF with readable text is read, and its facts are pulled out
with plain rules. A scanned image has no text to read, so it returns nothing and the person types the
details. Search and the meaning check use hashed word vectors, which are crude but honest and instant.
Set LLM_PROVIDER=gemini to use a hosted model instead.
"""

import math
import re
import zlib
from datetime import date, datetime

from ..engine.taxonomy import COMPLIANCE_CATALOGUE
from .prompts import DocumentExtraction

KEYWORDS = {
    "TCS": ("tax compliance", "compliance status"),
    "BBBEE": ("b-bbee", "bbbee", "broad-based black economic"),
    "COID": ("good standing", "coida", "compensation fund"),
    "CSD": ("central supplier database", "csd registration"),
    "CIDB": ("cidb", "construction industry development board", "contractor grading"),
}
DIMENSIONS = 512


# ---------------------------------------------------------------- reading a PDF without a library

_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_PIECE = re.compile(rb"\(((?:\\.|[^\\)])*)\)")


def _unescape(raw: bytes) -> str:
    out = re.sub(rb"\\([\\()])", rb"\1", raw)
    return out.decode("latin-1", errors="replace").strip()


def pdf_text(data: bytes) -> str:
    """The lines of text in a simple PDF, in drawing order. Empty if there is none to read."""
    lines: list[str] = []
    for body in _STREAM.findall(data):
        try:
            body = zlib.decompress(body) if body[:2] in (b"x\x9c", b"x\x01", b"x\xda") else body
        except zlib.error:
            continue
        for m in re.finditer(rb"\(((?:\\.|[^\\)])*)\)\s*Tj|\[((?:\\.|[^\]])*)\]\s*TJ", body):
            if m.group(1) is not None:
                text = _unescape(m.group(1))
            else:
                text = "".join(_unescape(p) for p in _PIECE.findall(m.group(2)))
            if text:
                lines.append(text)
    return "\n".join(lines)


_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y")


def _parse_date(text: str) -> date | None:
    text = text.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def read_document(data: bytes, mime: str) -> DocumentExtraction | None:
    """Pull the facts out of a document's text. None when there is no readable text."""
    text = pdf_text(data) if mime == "application/pdf" else ""
    if not text.strip():
        return None
    lower = text.lower()
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    doc_type = None
    ref = re.search(r"\b(TCS|BBBEE|COID|CSD|CIDB)-[A-Z0-9]{6,}\b", text)
    if ref:
        doc_type = ref.group(1)
    else:
        for code, words in KEYWORDS.items():
            if code in COMPLIANCE_CATALOGUE and any(w in lower for w in words):
                doc_type = code
                break

    company = None
    for i, ln in enumerate(lines):
        if "certify that" in ln.lower() and i + 1 < len(lines):
            company = lines[i + 1]
            break

    expiry = None
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(k in low for k in ("valid until", "expiry date", "expires", "expiry:")):
            tail = re.split(r"(?i)valid until|expiry date|expires|expiry:", ln, maxsplit=1)[
                -1
            ].strip(" :")
            expiry = _parse_date(tail) or (
                _parse_date(lines[i + 1]) if i + 1 < len(lines) else None
            )
            if expiry:
                break

    reg = re.search(r"\b\d{4}/\d{6}/\d{2}\b", text)
    issuer = next(
        (ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("issued by:")), None
    )
    return DocumentExtraction(
        document_type=doc_type,
        company_name=company,
        registration_number=reg.group(0) if reg else None,
        issuer=issuer,
        expiry_date=expiry,
    )


# ---------------------------------------------------------------- local vectors

_WORD = re.compile(r"[a-z]{3,}")
_STOP = {
    "and",
    "the",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "our",
    "work",
    "works",
    "services",
    "service",
}


def _vector(text: str) -> list[float]:
    counts: dict[int, float] = {}
    words = [w for w in _WORD.findall(text.lower()) if w not in _STOP]
    for w in words:
        counts[zlib.crc32(w.encode()) % DIMENSIONS] = (
            counts.get(zlib.crc32(w.encode()) % DIMENSIONS, 0.0) + 1.0
        )
        if len(w) > 5:  # a word stem shares a bucket with its relatives: road, roads, roadworks
            stem = w[:5]
            counts[zlib.crc32(stem.encode()) % DIMENSIONS] = (
                counts.get(zlib.crc32(stem.encode()) % DIMENSIONS, 0.0) + 0.7
            )
    vec = [0.0] * DIMENSIONS
    for k, v in counts.items():
        vec[k] = 1.0 + math.log(v)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed(texts: list[str]) -> list[list[float]]:
    return [_vector(t) for t in texts]
