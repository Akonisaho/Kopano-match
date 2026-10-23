"""Fail the build on licences we should not ship. Reads the CycloneDX SBOMs in docs/sbom/.

Run from the repository root:  python scripts/check_licenses.py [sbom.json ...]
Strong copyleft (GPL, AGPL, SSPL) and components with no declared licence fail the check.
Weak copyleft (LGPL) needs a named, reviewed exception below.
"""

import json
import sys
from pathlib import Path

# Reviewed exceptions. psycopg2 is LGPL with a linking exception, used unmodified as a library.
REVIEWED_LGPL = {"psycopg2-binary", "psycopg2"}

ROOT = Path(__file__).resolve().parents[1]


def declared(component: dict) -> list[str]:
    out = []
    for entry in component.get("licenses", []):
        lic = entry.get("license", {})
        out.append(lic.get("id") or lic.get("name") or entry.get("expression") or "")
    return [x for x in out if x]


def classify(name: str, licences: list[str]) -> str:
    if not licences:
        return "unknown"
    joined = " ".join(licences).upper()
    weak = "LGPL" in joined or "LESSER GENERAL" in joined
    strong = "AGPL" in joined or "SSPL" in joined or (
        "GPL" in joined.replace("LGPL", "") and "GENERAL PUBLIC" in joined.replace("LESSER", "")
        or "GPL-" in joined.replace("LGPL-", "").replace("AGPL-", "")
    )
    if strong and not weak:
        return "strong-copyleft"
    if weak:
        return "reviewed" if name.lower() in REVIEWED_LGPL else "weak-copyleft"
    return "permissive"


def main(paths: list[Path]) -> int:
    failed = False
    for path in paths:
        data = json.loads(path.read_text(encoding="utf8"))
        counts: dict[str, int] = {}
        problems = []
        for c in data.get("components", []):
            kind = classify(c.get("name", ""), declared(c))
            counts[kind] = counts.get(kind, 0) + 1
            if kind in ("strong-copyleft", "weak-copyleft", "unknown"):
                problems.append(f"  {kind}: {c.get('name')} {c.get('version', '')} {declared(c)}")
        print(f"{path.name}: {sum(counts.values())} components, {counts}")
        for line in problems:
            print(line)
        failed |= bool(problems)
    print("licence check FAILED" if failed else "licence check passed")
    return 1 if failed else 0


if __name__ == "__main__":
    args = [Path(a) for a in sys.argv[1:]] or sorted((ROOT / "docs" / "sbom").glob("*.cdx.json"))
    sys.exit(main(args))
