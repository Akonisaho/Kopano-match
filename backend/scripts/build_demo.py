"""Build a complete, realistic demo through the real API. No planted data.

Every account signs up, every profile is saved, every certificate is uploaded through the same
checks a real user hits, and matching runs on the real rules. Emails and in-app notices fire as
they would for real.

Run once, from backend/, with the API running and a clean database:
    python seed.py --empty
    python scripts/build_demo.py --email you@gmail.com

Accounts use plus-addresses of your email (you+buyer@gmail.com, you+sme1@gmail.com ...), so every
email lands in one inbox you control. Use only an address you own.
"""

import argparse
import io
import json
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_demo_documents import make_certificate  # noqa: E402

TODAY = date.today()
PNG = (
    bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
)  # stands in for a selfie; the mock provider discards it

SMES = [
    dict(
        tag="masego",
        name="Masego Infrastructure",
        owner="Masego Dlamini",
        sector="construction",
        province="Gauteng",
        turnover=12_000_000,
        years=11,
        past=4_000_000,
        caps=["CON-ROADS", "CON-CIVIL"],
        own=["black", "black_women"],
        docs={"TCS": "ok", "BBBEE": "ok", "COID": "ok", "CIDB": "ok"},
    ),
    dict(
        tag="isizwe",
        name="Isizwe Civil Works",
        owner="Lerato Mokoena",
        sector="construction",
        province="Gauteng",
        turnover=6_000_000,
        years=8,
        past=3_000_000,
        caps=["CON-ROADS", "CON-CIVIL", "CON-ELEC"],
        own=["black", "youth", "black_women"],
        docs={"TCS": "ok", "BBBEE": "ok"},
    ),
    dict(
        tag="nomsa",
        name="Nomsa Builders",
        owner="Nomsa Khumalo",
        sector="construction",
        province="Gauteng",
        turnover=7_000_000,
        years=9,
        past=3_500_000,
        caps=["CON-ROADS", "CON-CIVIL"],
        own=["black", "black_women"],
        docs={"TCS": "ok", "BBBEE": "expired", "COID": "ok", "CIDB": "ok"},
    ),
    dict(
        tag="sizwe",
        name="Sizwe Road Works",
        owner="Sizwe Mokoena",
        sector="construction",
        province="Gauteng",
        turnover=1_400_000,
        years=12,
        past=4_500_000,
        caps=["CON-ROADS", "CON-CIVIL", "CON-ELEC"],
        own=["black", "youth", "black_women"],
        docs={"TCS": "ok", "BBBEE": "ok"},
    ),
    dict(
        tag="tumelo",
        name="Tumelo Roadworks",
        owner="Tumelo Sithole",
        sector="construction",
        province="Western Cape",
        turnover=1_600_000,
        years=3,
        past=200_000,
        caps=["CON-ROADS"],
        own=[],
        docs={"TCS": "ok", "BBBEE": "ok", "COID": "ok", "CIDB": "ok"},
    ),
    dict(
        tag="agrifresh",
        name="AgriFresh Processors",
        owner="Lindiwe Mahlangu",
        sector="agriculture",
        province="Limpopo",
        turnover=5_000_000,
        years=7,
        past=2_000_000,
        caps=["AGR-PROC", "AGR-LOG"],
        own=["black", "black_women"],
        docs={"TCS": "ok", "BBBEE": "ok"},
    ),
    dict(
        tag="linknet",
        name="LinkNet Solutions",
        owner="Sipho Zulu",
        sector="ict",
        province="Gauteng",
        turnover=4_000_000,
        years=6,
        past=1_500_000,
        caps=["ICT-NET"],
        own=["black", "youth"],
        docs={"TCS": "ok", "BBBEE": "ok"},
    ),
    dict(
        tag="buildright",
        name="BuildRight Contractors",
        owner="Pule Molefe",
        sector="construction",
        province="Limpopo",
        turnover=6_000_000,
        years=8,
        past=2_500_000,
        caps=["CON-BLDG"],
        own=["black"],
        docs={"TCS": "ok", "BBBEE": "ok"},
    ),
    # planted for the admin review queue: a registration number the registry cannot find ...
    dict(
        tag="vuyo",
        name="Vuyo Catering",
        owner="Vuyo Ndlovu",
        sector="services",
        province="Western Cape",
        turnover=2_000_000,
        years=4,
        past=500_000,
        caps=["SVC-CATER"],
        own=["black", "youth"],
        docs={"TCS": "ok"},
        reg_suffix="07",
    ),
    # ... and a business that reuses another business's document
    dict(
        tag="zanele",
        name="Zanele Fabrication",
        owner="Zanele Dube",
        sector="manufacturing",
        province="Western Cape",
        turnover=3_200_000,
        years=7,
        past=1_200_000,
        caps=["MFG-FAB", "MFG-PACK"],
        own=["black_women"],
        docs={"TCS": "reused", "BBBEE": "ok"},
    ),
]

PROVIDERS = [
    dict(
        tag="buyer",
        role="corporate",
        name="Metro Enterprise Group",
        owner="Corporate Procurement Lead",
    ),
    dict(
        tag="funder", role="funder", name="Growth Catalyst Fund", owner="Funding Programme Manager"
    ),
]


def req(kind, value, mandatory=True, weight=5):
    return {
        "requirement_type": kind,
        "requirement_value": value,
        "mandatory": mandatory,
        "weight": weight,
    }


OPPORTUNITIES = [
    dict(
        by="buyer",
        body=dict(
            kind="procurement",
            title="Provincial roads rehabilitation",
            sector="construction",
            province="Gauteng",
            description="Rehabilitation of 42 km of provincial road, including drainage and signage.",
            deadline=str(TODAY + timedelta(days=16)),
            contract_value=4_200_000,
            duration_months=12,
            payment_terms_days=30,
            scope_items=[
                {"code": "CON-ROADS", "value": 2_500_000},
                {"code": "CON-CIVIL", "value": 1_200_000},
                {"code": "CON-ELEC", "value": 500_000},
            ],
            transformation_gap=["youth"],
            requirements=[
                req("capability", {"code": "CON-ROADS"}, True, 10),
                req("min_years", {"years": 3}),
                req("province", {"province": "Gauteng"}, False, 5),
                req("compliance_doc", {"doc": "TCS"}, True, 10),
                req("compliance_doc", {"doc": "BBBEE"}, True, 10),
                req("compliance_doc", {"doc": "COID"}, True, 10),
                req("certification", {"doc": "CIDB"}, True, 10),
            ],
        ),
    ),
    dict(
        by="buyer",
        body=dict(
            kind="procurement",
            title="Integrated agri-hub build",
            sector="agriculture",
            province="Limpopo",
            description="Design and build of an agro-processing hub. Too broad for one supplier: consortium bids expected.",
            deadline=str(TODAY + timedelta(days=30)),
            contract_value=6_500_000,
            duration_months=18,
            payment_terms_days=30,
            scope_items=[
                {"code": "AGR-PROC", "value": 2_000_000},
                {"code": "AGR-LOG", "value": 1_500_000},
                {"code": "ICT-NET", "value": 1_000_000},
                {"code": "CON-BLDG", "value": 2_000_000},
            ],
            transformation_gap=["black_women"],
            requirements=[
                req("compliance_doc", {"doc": "TCS"}, True, 10),
                req("compliance_doc", {"doc": "BBBEE"}, True, 10),
            ],
        ),
    ),
    dict(
        by="funder",
        body=dict(
            kind="grant",
            title="Youth enterprise growth grant",
            sector="services",
            province="Gauteng",
            description="Grants of up to R250k for youth-owned businesses. Applicants must be tax compliant.",
            deadline=str(TODAY + timedelta(days=6)),
            contract_value=250_000,
            duration_months=12,
            payment_terms_days=30,
            scope_items=[
                {"code": c, "value": 50_000}
                for c in ("ICT-NET", "CON-ROADS", "SVC-CATER", "ICT-DEV", "MFG-FAB")
            ],
            transformation_gap=["youth"],
            requirements=[
                req("ownership", {"flag": "youth"}, True, 10),
                req("min_years", {"years": 1}),
                req("compliance_doc", {"doc": "TCS"}, True, 10),
            ],
        ),
    ),
]


def multipart(fields, files, boundary):
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    for k, (filename, content, ctype) in files.items():
        out.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode()
        )
        out.write(content)
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue()


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, token=None, body=None, form=None, files=None, urlencoded=None):
        headers, data = {}, None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        elif urlencoded is not None:
            data, headers["Content-Type"] = (
                urllib.parse.urlencode(urlencoded).encode(),
                "application/x-www-form-urlencoded",
            )
        elif files is not None:
            boundary = uuid.uuid4().hex
            data = multipart(form or {}, files, boundary)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310  # nosec B310 - local API
                raw = resp.read()
                if "json" not in resp.headers.get("content-type", "json"):
                    return resp.status, {"text": raw.decode("utf8", "replace")}
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"detail": raw.decode("utf8", "replace")[:200]}


def plus(email, tag):
    local, domain = email.split("@")
    return f"{local}+{tag}@{domain}"


def fail(msg):
    print(f"\nStopped: {msg}")
    sys.exit(1)


def signup(api, email, password, name, org, role, reg):
    status, body = api.call(
        "POST",
        "/auth/register",
        body={
            "email": email,
            "password": password,
            "full_name": name,
            "role": role,
            "organisation_name": org,
            "registration_number": reg,
            "consent": True,
        },
    )
    if status == 409:  # already there from an earlier run: sign in instead
        status, body = api.call(
            "POST", "/auth/login", urlencoded={"username": email, "password": password}
        )
    if status not in (200, 201) or "access_token" not in body:
        fail(f"could not sign up {email}: {status} {body.get('detail')}")
    return body["access_token"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--email", required=True, help="an inbox you own; accounts become you+tag@domain"
    )
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--password", default="Demo-Password-1!")
    args = ap.parse_args()
    api = Api(args.api)
    status, _ = api.call("GET", "/health")
    if status != 200:
        fail(f"the API is not answering at {args.api}. Start it first.")
    rnd = random.Random()
    year = TODAY.year - 6

    def reg(suffix="06"):
        return f"{year}/{rnd.randint(100000, 999999)}/{suffix}"

    print("Creating buyers and funders ...")
    ptoken = {}
    for p in PROVIDERS:
        ptoken[p["tag"]] = signup(
            api, plus(args.email, p["tag"]), args.password, p["owner"], p["name"], p["role"], reg()
        )

    print("Creating SMEs, uploading certificates ...")
    stokens, first_tcs = {}, None
    for i, s in enumerate(SMES, start=1):
        token = signup(
            api,
            plus(args.email, s["tag"]),
            args.password,
            s["owner"],
            s["name"],
            "sme",
            reg(s.get("reg_suffix", "06")),
        )
        stokens[s["name"]] = token
        status, body = api.call(
            "PUT",
            "/smes/me",
            token,
            body={
                "sector": s["sector"],
                "province": s["province"],
                "annual_turnover": s["turnover"],
                "years_trading": s["years"],
                "largest_past_contract": s["past"],
                "capability_codes": s["caps"],
                "ownership": s["own"],
                "visible_to_corporates": True,
            },
        )
        if status != 200:
            fail(f"profile for {s['name']}: {status} {body.get('detail')}")
        api.call(
            "POST",
            "/smes/me/verify-identity",
            token,
            form={"id_last4": "1234"},
            files={"selfie": ("selfie.png", PNG, "image/png")},
        )
        for code, kind in s["docs"].items():
            expiry = (
                TODAY - timedelta(days=30) if kind == "expired" else TODAY + timedelta(days=330)
            )
            content = make_certificate(s["name"], code, expiry)
            if kind == "reused" and first_tcs:
                content = first_tcs  # the same file another business already uploaded
            if s["tag"] == "masego" and code == "TCS":
                first_tcs = content
            status, body = api.call(
                "POST",
                "/documents",
                token,
                form={"document_type": code, "expiry_date": str(expiry)},
                files={"file": (f"{code}.pdf", content, "application/pdf")},
            )
            if status != 201:
                fail(f"{code} for {s['name']}: {status} {body.get('detail')}")
        print(f"  {i:2}. {s['name']}")

    print("Publishing opportunities and matching ...")
    opp_ids = {}
    for o in OPPORTUNITIES:
        status, body = api.call("POST", "/opportunities", ptoken[o["by"]], body=o["body"])
        if status != 201:
            fail(f"opportunity {o['body']['title']}: {status} {body.get('detail')}")
        opp_ids[o["body"]["title"]] = (o["by"], body["id"])
    for title, (by, oid) in opp_ids.items():
        status, ranked = api.call("POST", f"/opportunities/{oid}/match", ptoken[by])
        print(f"  {title}: {len(ranked) if isinstance(ranked, list) else 0} matches")

    print("Shortlisting and applying ...")
    by, roads = opp_ids["Provincial roads rehabilitation"]
    _, ranked = api.call("GET", f"/opportunities/{roads}/matches", ptoken[by])
    for row in ranked:
        if row["sme_name"] in ("Masego Infrastructure", "Isizwe Civil Works"):
            api.call("POST", f"/matches/{row['match_id']}/shortlist", ptoken[by])
        if row["sme_name"] in ("Masego Infrastructure", "Nomsa Builders"):
            api.call("POST", f"/applications/{row['match_id']}", stokens[row["sme_name"]])

    print("Recording awards and inviting a consortium ...")
    # A split award on the roads tender. Isizwe still had open document gaps when awarded, which
    # is exactly the case a strict "must hold every document" filter would have rejected.
    by_name = {row["sme_name"]: row["match_id"] for row in ranked}
    for name, value in (("Masego Infrastructure", 2_500_000), ("Isizwe Civil Works", 1_700_000)):
        status, body = api.call(
            "POST", f"/applications/{by_name[name]}/award", ptoken[by], body={"value": value}
        )
        if status != 200:
            fail(f"award for {name}: {status} {body.get('detail')}")
    print("Leaving buyer feedback on the awards ...")
    keys = ("quality", "delivery", "responsiveness", "compliance", "innovation", "value_for_money")
    reviews = {
        "Masego Infrastructure": (
            [5, 5, 4, 5, 4, 5],
            "Delivered the first phase ahead of schedule and the paperwork was complete.",
        ),
        "Isizwe Civil Works": (
            [4, 3, 4, 4, 3, 4],
            "Good quality work, but two milestones slipped by about a week.",
        ),
    }
    _, owed = api.call("GET", "/feedback/awaiting", ptoken[by])
    for item in owed:
        if item["sme"] in reviews:
            scores, comment = reviews[item["sme"]]
            status, body = api.call(
                "POST",
                f"/feedback/{item['application_id']}",
                ptoken[by],
                body={"ratings": dict(zip(keys, scores)), "comment": comment},
            )
            if status != 201:
                fail(f"feedback for {item['sme']}: {status} {body.get('detail')}")
    _, got = api.call("GET", "/feedback/mine", stokens["Masego Infrastructure"])
    api.call(
        "POST",
        f"/feedback/{got['items'][0]['id']}/respond",
        stokens["Masego Infrastructure"],
        body={"text": "Thank you. The second phase is already scheduled with the same crew."},
    )
    print("  Isizwe Civil Works has not answered its review yet: respond or dispute it live.")
    by2, agri = opp_ids["Integrated agri-hub build"]
    status, inv = api.call("POST", f"/opportunities/{agri}/consortium/invite", ptoken[by2])
    if status != 201:
        fail(f"consortium invite: {status} {inv.get('detail')}")
    # Two of three accept now. The last answer is left for you to give live in the demo.
    for member in inv["members"]:
        if member["name"] in ("AgriFresh Processors", "LinkNet Solutions"):
            _, mine = api.call("GET", "/consortia", stokens[member["name"]])
            row = next(i for i in mine if i["opportunity"]["id"] == agri)
            api.call(
                "POST",
                f"/consortia/{row['id']}/respond",
                stokens[member["name"]],
                body={"accept": True},
            )
    print(
        "  BuildRight Contractors has not answered yet: sign in as that account to accept it live."
    )

    print("Warming the AI results so every page opens instantly ...")
    from concurrent.futures import ThreadPoolExecutor

    jobs = []
    for _title, (by_role, oid) in opp_ids.items():
        _, rows = api.call("GET", f"/opportunities/{oid}/matches", ptoken[by_role])
        for row in rows if isinstance(rows, list) else []:
            jobs.append((ptoken[by_role], row["match_id"], row["sme_id"]))

    def warm(job):
        tok, mid, sid = job
        api.call("GET", f"/matches/{mid}", tok)
        api.call("GET", f"/matches/{mid}/semantic", tok)
        api.call("GET", f"/feedback/performance/{sid}", tok)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(warm, jobs))
    api.call(
        "POST", "/smes/me/search", next(iter(stokens.values())), body={"query": "road construction"}
    )
    api.call("POST", "/providers/search", ptoken["buyer"], body={"query": "road construction"})
    print(f"  {len(jobs)} matches ready.")

    print("\nDone. Sign in with password:", args.password)
    for p in PROVIDERS:
        print(f"  {p['role']:10} {plus(args.email, p['tag'])}   {p['name']}")
    for s in SMES:
        print(f"  {'sme':10} {plus(args.email, s['tag'])}   {s['name']}")
    print(
        "\nSign in as the admin you created with `python seed.py --empty` to see the review queue "
        "(a registry mismatch and a reused document are waiting)."
    )


if __name__ == "__main__":
    main()
