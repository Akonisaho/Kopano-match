"""Make sample certificates to upload in a demo. No libraries needed.

Run from backend/:
    python scripts/make_demo_documents.py "Acme Civils" "Zulu Logistics"
    python scripts/make_demo_documents.py "Acme Civils" --types TCS,BBBEE --expired BBBEE

Writes demo-documents/<company>/<TYPE>.pdf and a README.txt listing the expiry date to type into
the upload form. Every page carries a large SAMPLE watermark and a "demonstration only" line.
These use a generic design with no real logos or seals, and must never be presented as real
documents from SARS, a commissioner of oaths, the Department of Employment and Labour, National
Treasury or the CIDB.
"""

import argparse
import hashlib
import re
from datetime import date, timedelta
from pathlib import Path

CATALOGUE = {
    "TCS": ("Tax Compliance Status", "Confirmation of tax compliance status", "SARS (demo issuer)"),
    "BBBEE": (
        "B-BBEE Affidavit",
        "Sworn affidavit of B-BBEE status",
        "Commissioner of Oaths (demo)",
    ),
    "COID": (
        "Letter of Good Standing",
        "Compensation fund good standing",
        "Dept. of Employment and Labour (demo)",
    ),
    "CSD": (
        "CSD Registration",
        "Central Supplier Database registration",
        "National Treasury (demo issuer)",
    ),
    "CIDB": ("CIDB Grading Certificate", "Contractor grading certificate", "CIDB (demo issuer)"),
}
W, H = 842, 595  # A4 landscape
NAVY, PURPLE = "0.11 0.13 0.38", "0.49 0.23 0.93"


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def circle(cx: float, cy: float, r: float) -> str:
    k = r * 0.5523
    return (
        f"{cx + r:.1f} {cy:.1f} m {cx + r:.1f} {cy + k:.1f} {cx + k:.1f} {cy + r:.1f} {cx:.1f} {cy + r:.1f} c "
        f"{cx - k:.1f} {cy + r:.1f} {cx - r:.1f} {cy + k:.1f} {cx - r:.1f} {cy:.1f} c "
        f"{cx - r:.1f} {cy - k:.1f} {cx - k:.1f} {cy - r:.1f} {cx:.1f} {cy - r:.1f} c "
        f"{cx + k:.1f} {cy - r:.1f} {cx + r:.1f} {cy - k:.1f} {cx + r:.1f} {cy:.1f} c S"
    )


def pdf_document(stream: str) -> bytes:
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def make_certificate(company: str, code: str, expiry: date, issued: date | None = None) -> bytes:
    title, line, issuer = CATALOGUE[code]
    issued = issued or (expiry - timedelta(days=365))
    ref = hashlib.sha256(f"{company}|{code}".encode()).hexdigest()[:10].upper()
    ops: list[str] = []

    def text(
        x: float, y: float, s: str, size: float, bold: bool = False, colour: str = "0.1 0.1 0.15"
    ) -> None:
        ops.append(
            f"BT {colour} rg /{'F2' if bold else 'F1'} {size} Tf {x:.1f} {y:.1f} Td ({esc(s)}) Tj ET"
        )

    def centred(
        y: float, s: str, size: float, bold: bool = False, colour: str = "0.1 0.1 0.15"
    ) -> None:
        width = len(s) * size * (0.56 if bold else 0.5)
        text((W - width) / 2, y, s, size, bold, colour)

    # watermark first, so everything sits on top of it
    ops.append("q 0.9 g BT /F2 150 Tf 0.866 0.5 -0.5 0.866 150 120 Tm (SAMPLE) Tj ET Q")
    ops.append(f"{NAVY} RG 3 w 24 24 {W - 48} {H - 48} re S")
    ops.append(f"{PURPLE} RG 0.8 w 34 34 {W - 68} {H - 68} re S")
    centred(520, "KOPANO MATCH DEMONSTRATION RECORD", 11, True, PURPLE)
    centred(480, title.upper(), 30, True, NAVY)
    centred(452, line, 12, False, "0.35 0.38 0.45")
    centred(400, "This is to certify that", 13)
    centred(362, company, 28, True)
    centred(
        334,
        "has been recorded as meeting this requirement for the purposes of a product demonstration.",
        11,
        False,
        "0.35 0.38 0.45",
    )
    rows = [
        ("Reference", f"{code}-{ref}"),
        ("Date of issue", f"{issued:%d %B %Y}"),
        ("Valid until", f"{expiry:%d %B %Y}"),
    ]
    y = 280
    for label, value in rows:
        text(160, y, label, 11, False, "0.35 0.38 0.45")
        text(300, y, value, 13, True)
        y -= 26
    text(160, 170, f"Issued by: {issuer}", 11)
    ops.append("0.4 w 0.1 0.1 0.15 RG 560 176 m 760 176 l S")
    text(560, 160, "Authorised signatory (demo)", 9, False, "0.35 0.38 0.45")
    ops.append(f"{PURPLE} RG 2 w {circle(130, 110, 36)}")
    centred_x = 130 - 3 * 4.2
    text(centred_x, 106, "DEMO", 11, True, PURPLE)
    centred(
        60,
        "SAMPLE DOCUMENT FOR DEMONSTRATION ONLY. NOT A REAL ISSUER DOCUMENT. DO NOT RELY ON IT.",
        9,
        True,
        "0.7 0.1 0.1",
    )
    return pdf_document("\n".join(ops))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("companies", nargs="+")
    ap.add_argument("--types", default=",".join(CATALOGUE), help="comma-separated, default all")
    ap.add_argument("--expired", default="", help="types that should already be expired")
    ap.add_argument(
        "--out", default=None, help="output folder (default demo-documents/ at the repo root)"
    )
    ap.add_argument(
        "--virus-test",
        action="store_true",
        help="also write virus-test.pdf, the standard harmless antivirus test file",
    )
    args = ap.parse_args()
    types = [t.strip().upper() for t in args.types.split(",") if t.strip()]
    expired = {t.strip().upper() for t in args.expired.split(",") if t.strip()}
    bad = [t for t in types + sorted(expired) if t not in CATALOGUE]
    if bad:
        raise SystemExit(f"Unknown types {bad}. Choose from {list(CATALOGUE)}")
    root = Path(args.out) if args.out else Path(__file__).resolve().parents[2] / "demo-documents"
    today = date.today()
    if args.virus_test:
        root.mkdir(parents=True, exist_ok=True)
        # The industry-standard harmless test string, built in two parts. Your own antivirus may
        # remove this file the moment it is written: that is the test string doing its job.
        (root / "virus-test.pdf").write_bytes(
            rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        )
        print(f"virus-test.pdf written to {root}: upload it to see the security scan reject it")
    for company in args.companies:
        folder = root / re.sub(r"[^A-Za-z0-9 _-]", "", company).strip().replace(" ", "_")
        folder.mkdir(parents=True, exist_ok=True)
        notes = [f"Expiry dates to enter in the upload form for {company}:", ""]
        for code in types:
            expiry = today - timedelta(days=30) if code in expired else today + timedelta(days=330)
            (folder / f"{code}.pdf").write_bytes(make_certificate(company, code, expiry))
            notes.append(
                f"{code}.pdf   expiry {expiry:%Y-%m-%d}"
                + ("   (already expired, on purpose)" if code in expired else "")
            )
        (folder / "README.txt").write_text("\n".join(notes) + "\n", encoding="utf8")
        print(f"{company}: {len(types)} certificates in {folder}")


if __name__ == "__main__":
    main()
