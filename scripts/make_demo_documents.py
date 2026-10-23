"""Make sample PDFs to upload during a demo. No libraries needed.

    python scripts/make_demo_documents.py "Acme Civils" "Zulu Logistics"
    python scripts/make_demo_documents.py "Acme Civils" --types TCS,BBBEE

Writes demo-documents/<company>/<TYPE>.pdf. Each file carries the company name, so every file is
unique (the platform detects the same file reused by two businesses). Every page is stamped as a
sample for demonstration. These are not real government or issuer documents and must never be
presented as such.
"""

import argparse
import hashlib
import re
from pathlib import Path

CATALOGUE = {
    "TCS": ("Tax compliance status PIN", "SARS"),
    "BBBEE": ("B-BBEE affidavit", "Commissioner of oaths"),
    "COID": ("Letter of good standing (COIDA)", "Department of Employment and Labour"),
    "CSD": ("CSD registration", "National Treasury"),
    "CIDB": ("CIDB grading certificate", "CIDB"),
}


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list[str]) -> bytes:
    stream = "BT /F1 12 Tf 56 780 Td 18 TL " + " ".join(f"({escape(x)}) Tj T*" for x in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
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
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("companies", nargs="+")
    ap.add_argument("--types", default=",".join(CATALOGUE), help="comma-separated, default all")
    args = ap.parse_args()
    types = [t.strip().upper() for t in args.types.split(",")]
    bad = [t for t in types if t not in CATALOGUE]
    if bad:
        raise SystemExit(f"Unknown types {bad}. Choose from {list(CATALOGUE)}")
    root = Path(__file__).resolve().parents[1] / "demo-documents"
    for company in args.companies:
        folder = root / re.sub(r"[^A-Za-z0-9 _-]", "", company).strip().replace(" ", "_")
        folder.mkdir(parents=True, exist_ok=True)
        for code in types:
            title, issuer = CATALOGUE[code]
            ref = hashlib.sha256(f"{company}|{code}".encode()).hexdigest()[:10].upper()
            lines = [
                "SAMPLE DOCUMENT FOR DEMONSTRATION ONLY",
                "Not a real issuer document. Do not rely on it.",
                "",
                title,
                f"Issuer named for the demo: {issuer}",
                f"Business: {company}",
                f"Demo reference: {code}-{ref}",
            ]
            (folder / f"{code}.pdf").write_bytes(make_pdf(lines))
        print(f"{company}: {len(types)} files in {folder}")


if __name__ == "__main__":
    main()
