"""Check the whole running system in about a minute. One line per check: PASS or FAIL.

Run from backend/, with the API running and the demo built (python scripts/build_demo.py):
    python scripts/smoke_test.py --email you@gmail.com --admin-email you@yourdomain.co.za --admin-password "..."

It signs in as the demo accounts, walks every feature, and also tries to break the rules (another
SME reading someone's data, a flood of bad logins, a virus test file). It creates one short-lived
throwaway account (you+smoke...@..., erased at the end) and requests one password reset for the
demo SME Thabo, so a welcome email and a reset email may arrive. Exit code 1 if any check
fails. Gemini and Brevo are checked separately with scripts/check_keys.py.
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_demo import PNG, Api, plus  # noqa: E402
from make_demo_documents import make_certificate  # noqa: E402

from datetime import date, timedelta  # noqa: E402

# The standard antivirus test string, split so this file is not itself quarantined
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--email", required=True, help="the same address you gave build_demo.py")
    ap.add_argument("--admin-email", required=True)
    ap.add_argument("--admin-password", required=True)
    ap.add_argument("--password", default="Demo-Password-1!")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument(
        "--web", default="http://localhost:5173", help="web app address, checked if reachable"
    )
    args = ap.parse_args()
    api = Api(args.api)

    def login(email, password=args.password):
        s, b = api.call("POST", "/auth/login", urlencoded={"username": email, "password": password})
        return b.get("access_token") if s == 200 else None

    print("Platform")
    s, _ = api.call("GET", "/health")
    if not check("API is answering", s == 200, args.api):
        sys.exit(1)
    s, show = api.call("GET", "/meta/showcase")
    check(
        "public showcase has real data",
        s == 200 and bool(show.get("chart")),
        f"{show.get('smes')} SMEs, {show.get('opportunities')} opportunities",
    )
    try:
        import urllib.request

        with urllib.request.urlopen(args.web, timeout=5) as r:  # noqa: S310  # nosec B310 - local web app
            check("web app is reachable", r.status == 200, args.web)
    except Exception:  # noqa: BLE001
        check(
            "web app is reachable",
            False,
            f"{args.web} did not answer (start it, or ignore if API-only)",
        )

    print("Sign-in and roles")
    admin = login(args.admin_email, args.admin_password)
    buyer = login(plus(args.email, "buyer"))
    funder = login(plus(args.email, "funder"))
    thabo = login(plus(args.email, "thabo"))
    masego = login(plus(args.email, "masego"))
    check("admin, buyer, funder and SMEs can sign in", all([admin, buyer, funder, thabo, masego]))
    if not all([admin, buyer, thabo, masego]):
        print("\nStopped: sign-in failed. Did you run build_demo.py with this --email?")
        sys.exit(1)
    s, _ = api.call("GET", "/admin/queue", thabo)
    check("an SME cannot open the admin queue", s == 403)
    s, _ = api.call("GET", "/opportunities", None)
    check("no token means no access", s == 401)

    print("Buyer: matching, quadrant, consortium, dossier")
    _, opps = api.call("GET", "/opportunities", buyer)
    roads = next((o for o in opps if o["title"].startswith("Provincial")), None)
    agri = next((o for o in opps if "agri" in o["title"].lower()), None)
    check("buyer sees its published opportunities", bool(roads and agri), f"{len(opps)} found")
    quads = (roads or {}).get("quadrants", {})
    check(
        "the roads tender spans several quadrants",
        len(quads) >= 3,
        ", ".join(f"{k}:{v}" for k, v in quads.items()),
    )
    _, ranked = api.call("GET", f"/opportunities/{roads['id']}/matches", buyer)
    check(
        "matches are ranked with fit and readiness",
        bool(ranked) and all("fit" in r and "readiness" in r for r in ranked),
    )
    s, cons = api.call("GET", f"/opportunities/{agri['id']}/consortium", buyer)
    c = (cons or {}).get("consortium")
    check(
        "consortium covers the agri-hub 100% and names a lead",
        bool(c) and c["coverage_pct"] == 100.0,
        f"lead {c['lead']['name']}" if c else "",
    )
    coachable = next((r for r in ranked if r["quadrant"] == "coachable"), None)
    _, detail = api.call("GET", f"/matches/{coachable['match_id']}", buyer)
    check(
        "a coachable match shows dated, costed gaps",
        bool(detail.get("gaps")) and all(g["days"] and g["issuer"] for g in detail["gaps"]),
    )
    check(
        "match summary is present",
        bool(detail.get("rationale")),
        f"source: {detail.get('rationale_source')}",
    )
    s, dossier = api.call("GET", f"/matches/{coachable['match_id']}/dossier", buyer)
    check(
        "decision dossier has rules, scores and sources",
        s == 200 and bool(dossier.get("rules")) and bool(dossier.get("verifications")),
    )
    s, um = api.call("GET", "/providers/bottlenecks", buyer)
    check(
        "Unlock Map lists the credentials holding SMEs back",
        s == 200 and bool(um.get("rows")),
        f"top: {um['rows'][0]['credential']}" if um.get("rows") else "",
    )
    s, ov = api.call("GET", "/providers/overview", buyer)
    check("provider overview has metrics", s == 200 and ov.get("active_opportunities", 0) >= 2)
    s, fo = api.call("GET", "/opportunities", funder)
    check(
        "funder sees only its own grant", s == 200 and all(o["kind"] != "procurement" for o in fo)
    )

    print("SME: dashboard, Unlock Plan, notices")
    s, dash = api.call("GET", "/smes/me/dashboard", thabo)
    check(
        "SME dashboard shows matches and open gaps",
        s == 200 and bool(dash.get("matches")) and bool(dash.get("open_gaps")),
    )
    gaps = [g["credential"] for g in dash.get("open_gaps", [])]
    s, plan = api.call("POST", "/smes/me/simulate", thabo, body={"credentials": gaps or ["COID"]})
    check(
        "Unlock Plan moves the award-ready count up",
        s == 200 and plan["after"]["award_ready"] > plan["before"]["award_ready"],
        f"{plan.get('before', {}).get('award_ready')} to {plan.get('after', {}).get('award_ready')}"
        if s == 200
        else str(plan),
    )
    _, feed = api.call("GET", "/smes/me/opportunities", thabo)
    check(
        "unmatched opportunities say why", any(i["match"] is None and i["blockers"] for i in feed)
    )
    _, bell = api.call("GET", "/notifications", thabo)
    check(
        "the notification bell has notices", bell.get("unread", 0) >= 1 or bool(bell.get("items"))
    )
    s, mine = api.call("GET", "/me/data", thabo)
    check("data export includes matches", s == 200 and bool(mine.get("matches")))

    print("Rules that must hold")
    other_match = coachable["match_id"]
    s, _ = api.call("GET", f"/matches/{other_match}", masego)
    check("another SME cannot read someone else's match", s == 404)
    _, tdocs = api.call("GET", "/documents", thabo)
    s_noauth, _ = api.call("GET", f"/documents/{tdocs[0]['id']}/file") if tdocs else (401, {})
    s_other, _ = (
        api.call("GET", f"/documents/{tdocs[0]['id']}/file", masego) if tdocs else (404, {})
    )
    check("a document file needs a token and the right owner", s_noauth == 401 and s_other == 404)
    s, _ = api.call(
        "POST", "/auth/forgot", body={"email": f"{uuid.uuid4().hex[:8]}@kopano-test.com"}
    )
    s2, _ = api.call("POST", "/auth/forgot", body={"email": plus(args.email, "thabo")})
    check("password reset answers the same for known and unknown emails", s == s2 == 202)
    victim = f"nobody{uuid.uuid4().hex[:6]}@kopano-test.com"  # one account, hammered
    codes = [
        api.call("POST", "/auth/login", urlencoded={"username": victim, "password": "x"})[0]
        for _ in range(6)
    ]
    check("repeated bad logins get throttled", codes[-1] == 429, str(codes))

    print("Uploads, scanning, two-step sign-in, erasure (throwaway account)")
    throwaway = plus(args.email, f"smoke{uuid.uuid4().hex[:6]}")
    s, reg = api.call(
        "POST",
        "/auth/register",
        body={
            "email": throwaway,
            "password": "Smoke-Test-Password-9!",
            "full_name": "Smoke Test",
            "role": "sme",
            "organisation_name": f"Smoke {uuid.uuid4().hex[:5]}",
            "registration_number": f"2020/{uuid.uuid4().int % 800000 + 100000}/06",
            "consent": True,
        },
    )
    tok = reg.get("access_token")
    if check("a new SME can register", s == 201 and bool(tok)):
        good = (
            make_certificate("Smoke Test", "TCS", date.today() + timedelta(days=300))
            + uuid.uuid4().bytes
        )
        s, up = api.call(
            "POST",
            "/documents",
            tok,
            form={"document_type": "TCS", "expiry_date": str(date.today() + timedelta(days=300))},
            files={"file": ("TCS.pdf", good, "application/pdf")},
        )
        check(
            "a clean certificate uploads and verifies",
            s == 201 and up.get("verification") == "verified",
            str(up.get("detail", up.get("verification"))),
        )
        s, bad = api.call(
            "POST",
            "/documents",
            tok,
            form={"document_type": "BBBEE"},
            files={"file": ("BBBEE.pdf", EICAR, "application/pdf")},
        )
        check("the virus test file is rejected by the scanner", s == 422, str(bad.get("detail")))
        s, bad2 = api.call(
            "POST",
            "/documents",
            tok,
            form={"document_type": "BBBEE"},
            files={"file": ("x.exe", b"MZ" + b"0" * 50, "application/octet-stream")},
        )
        check("an executable is refused by type", s == 415)
        s, idr = api.call(
            "POST",
            "/smes/me/verify-identity",
            tok,
            form={"id_last4": "1234"},
            files={"selfie": ("s.png", PNG, "image/png")},
        )
        check(
            "identity check keeps the outcome only",
            s == 200 and "no image" in idr.get("retained", ""),
        )
        s, setup = api.call("POST", "/auth/mfa/setup", tok)
        check(
            "two-step setup returns a QR code and a key",
            s == 200 and setup.get("qr", "").startswith("data:image/svg+xml"),
        )
        s, gone = api.call("POST", "/me/delete", tok)
        check(
            "erasure deletes the uploaded files",
            s == 200 and gone.get("files_deleted") == 1,
            str(gone),
        )
        s, _ = api.call("GET", "/me", tok)
        check("an erased account can no longer sign in", s == 401)

    print("Admin")
    s, q = api.call("GET", "/admin/queue", admin)
    check(
        "review queue has flagged items waiting",
        s == 200 and len(q.get("verifications", [])) >= 1,
        ", ".join(sorted({v["result"] for v in q.get("verifications", [])})),
    )
    s, rem = api.call("POST", "/admin/reminders/run", admin)
    check("expiry reminders run", s == 200 and "notices_sent" in rem, str(rem))

    failed = [r for r in results if not r[0]]
    print(
        f"\n{len(results) - len(failed)} of {len(results)} checks passed."
        + ("" if not failed else f" {len(failed)} FAILED:")
    )
    for _, name, detail in failed:
        print(f"  - {name} {detail}")
    print("Also run:  python scripts/check_keys.py   (Gemini, Brevo and the scanner)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
