"""End-to-end checks of the security and compliance claims. Needs a seeded database."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.db import engine
from app.main import app

client = TestClient(app)
PASSWORD = "Demo-Password-1!"
PDF = b"%PDF-1.4\n%test\n"


def login(email: str, password: str = PASSWORD) -> dict:
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register(role: str, **extra) -> dict:
    n = uuid.uuid4().hex[:8]
    body = {
        "email": f"{n}@kopano-test.com",
        "password": "a-long-test-password",
        "full_name": "Test Person",
        "role": role,
        "organisation_name": f"Org {n}",
        "registration_number": f"2020/{int(n, 16) % 900000 + 100000}/06",
        "consent": True,
        **extra,
    }
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def opp_id(headers: dict, title: str) -> str:
    return next(
        o["id"] for o in client.get("/opportunities", headers=headers).json() if o["title"] == title
    )


# ---- authentication and authorisation ----


def test_routes_deny_by_default():
    for path in ("/me", "/opportunities", "/smes/me", "/documents", "/admin/queue"):
        assert client.get(path).status_code == 401


def test_registration_requires_consent_and_hides_hashes():
    n = uuid.uuid4().hex[:8]
    body = {
        "email": f"{n}@kopano-test.com",
        "password": "a-long-test-password",
        "full_name": "No Consent",
        "role": "sme",
        "organisation_name": "X Org",
        "consent": False,
    }
    assert client.post("/auth/register", json=body).status_code == 422
    assert "password" not in client.get("/me", headers=register("sme")).text


def test_cannot_self_register_as_admin():
    body = {
        "email": "a@kopano-test.com",
        "password": "a-long-test-password",
        "full_name": "Eve",
        "role": "admin",
        "organisation_name": "Evil",
        "consent": True,
    }
    assert client.post("/auth/register", json=body).status_code == 422


def test_role_enforcement():
    sme = login("sme-001@sme.demo")
    assert client.post("/opportunities", headers=sme, json={}).status_code == 403
    assert client.get("/admin/queue", headers=sme).status_code == 403
    corp = login("corporate@kopano.demo")
    assert client.get("/admin/queue", headers=corp).status_code == 403


def test_wrong_password_and_unknown_user_look_the_same():
    a = client.post("/auth/login", data={"username": "sme-001@sme.demo", "password": "nope"})
    b = client.post("/auth/login", data={"username": "ghost@x.invalid", "password": "nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


# ---- documents ----


def test_upload_validation_and_object_level_access():
    owner, other = register("sme"), register("sme")
    up = lambda name, mime, data: client.post(  # noqa: E731
        "/documents",
        headers=owner,
        data={"document_type": "TCS"},
        files={"file": (name, data, mime)},
    )
    assert up("virus.exe", "application/octet-stream", b"MZ").status_code == 415
    assert up("fake.pdf", "application/pdf", b"not a pdf").status_code == 415
    assert up("x.pdf", "image/png", PDF).status_code == 415
    ok = up("tcs.pdf", "application/pdf", PDF)
    assert ok.status_code == 201
    doc_id = ok.json()["id"]
    assert client.get(f"/documents/{doc_id}/file", headers=owner).status_code == 200
    assert client.get(f"/documents/{doc_id}/file", headers=other).status_code == 404
    assert client.get(f"/documents/{doc_id}/file").status_code == 401
    assert client.get("/documents", headers=other).json() == []


def test_duplicate_document_hash_is_flagged():
    first, second = register("sme"), register("sme")
    data = PDF + uuid.uuid4().bytes
    for h in (first, second):
        r = client.post(
            "/documents",
            headers=h,
            data={"document_type": "TCS"},
            files={"file": ("tcs.pdf", data, "application/pdf")},
        )
    assert r.json()["verification"] == "duplicate_hash"


# ---- matching and tenancy ----


def test_corporate_tenancy_and_ranked_matches():
    corp = login("corporate@kopano.demo")
    opp = opp_id(corp, "Provincial roads rehabilitation")
    ranked = client.post(f"/opportunities/{opp}/match", headers=corp).json()
    assert {r["quadrant"] for r in ranked} >= {"award_now", "coachable"}
    assert ranked == sorted(ranked, key=lambda r: -r["overall"])
    stranger = register("corporate")
    assert client.get(f"/opportunities/{opp}", headers=stranger).status_code == 404
    assert client.get(f"/opportunities/{opp}/matches", headers=stranger).status_code == 404


def test_match_detail_gaps_risk_and_isolation():
    corp = login("corporate@kopano.demo")
    opp = opp_id(corp, "Provincial roads rehabilitation")
    ranked = client.get(f"/opportunities/{opp}/matches", headers=corp).json()
    coach = next(r for r in ranked if r["sme_name"] == "Thabo Civils")
    detail = client.get(f"/matches/{coach['match_id']}", headers=corp).json()
    assert len(detail["gaps"]) == 2 and all(g["days"] and g["issuer"] for g in detail["gaps"])
    assert any(g["also_unlocks"] > 0 for g in detail["gaps"])
    assert detail["rationale"]
    over = next(r for r in ranked if r["sme_name"] == "Sizwe Road Works")
    assert over["risk_flags"]["overtrading"]
    # An SME other than the subject cannot read the match; the subject can
    assert (
        client.get(f"/matches/{coach['match_id']}", headers=login("sme-002@sme.demo")).status_code
        == 404
    )
    assert (
        client.get(f"/matches/{coach['match_id']}", headers=login("sme-001@sme.demo")).status_code
        == 200
    )


def test_shortlist_writes_audit_row():
    corp, admin = login("corporate@kopano.demo"), login("admin@kopano.demo")
    opp = opp_id(corp, "Provincial roads rehabilitation")
    mid = client.get(f"/opportunities/{opp}/matches", headers=corp).json()[0]["match_id"]
    assert client.post(f"/matches/{mid}/shortlist", headers=corp).status_code == 200
    trail = client.get(
        "/admin/audit", params={"entity_type": "match", "entity_id": mid}, headers=admin
    ).json()
    assert trail[0]["action"] == "match_shortlisted" and trail[0]["new"]["status"] == "shortlisted"
    # The reasoning is frozen into the append-only log at the moment of decision
    snap = trail[0]["new"]["snapshot"]
    assert snap["model_version"] == "v1" and "components" in snap and "gaps" in snap


def test_consortium_covers_the_uncovered_opportunity():
    corp = login("corporate@kopano.demo")
    opp = opp_id(corp, "Integrated agri-hub build")
    c = client.get(f"/opportunities/{opp}/consortium", headers=corp).json()["consortium"]
    assert c["coverage_pct"] == 100.0 and c["lead"]["name"]


def test_invalid_requirement_rows_are_rejected():
    corp = login("corporate@kopano.demo")
    body = {
        "title": "Bad",
        "sector": "ict",
        "province": "Gauteng",
        "contract_value": 1000,
        "duration_months": 6,
        "scope_items": [{"code": "ICT-DEV", "value": 1000}],
        "requirements": [
            {
                "requirement_type": "capability",
                "requirement_value": {"code": "'; DROP TABLE users;--"},
            }
        ],
    }
    assert client.post("/opportunities", headers=corp, json=body).status_code == 422


# ---- admin review, audit integrity, POPIA ----


def test_admin_queue_flags_and_review_is_audited():
    # A registry number ending in 7 is "not found" in the mock, so it must reach the queue
    n = uuid.uuid4().hex[:6]
    register("sme", organisation_name=f"Flagged {n}", registration_number=f"2021/{n}/07")
    admin = login("admin@kopano.demo")
    q = client.get("/admin/queue", headers=admin).json()
    mine = next(v for v in q["verifications"] if v["organisation"] == f"Flagged {n}")
    assert mine["result"] == "not_found" and "mock" in mine["source_label"]
    r = client.post(
        f"/admin/verifications/{mine['id']}/review", headers=admin, json={"decision": "rejected"}
    )
    assert r.status_code == 200
    trail = client.get(
        "/admin/audit",
        params={"entity_type": "verification", "entity_id": mine["id"]},
        headers=admin,
    ).json()
    assert trail[0]["action"] == "verification_review" and trail[0]["user_id"]
    after = client.get("/admin/queue", headers=admin).json()["verifications"]
    assert all(v["id"] != mine["id"] for v in after)


def test_app_role_cannot_rewrite_audit_log():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_user")).scalar() == "kopano_app"
        for stmt in ("DELETE FROM audit.audit_logs", "UPDATE audit.audit_logs SET action = 'x'"):
            with pytest.raises(ProgrammingError):
                conn.execute(text(stmt))
            conn.rollback()


def test_data_export_and_anonymisation_keep_audit_trail():
    h = register("sme")
    me = client.get("/me", headers=h).json()
    data = client.get("/me/data", headers=h).json()
    assert data["user"]["role"] == "sme" and data["user"]["consent_version"]
    assert client.post("/me/delete", headers=h).status_code == 200
    # Token no longer works once the account is anonymised
    assert client.get("/me", headers=h).status_code == 401
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT full_name, phone FROM core.users WHERE id = :i"), {"i": me["id"]}
        ).one()
        audit = conn.execute(
            text("SELECT count(*) FROM audit.audit_logs WHERE user_id = :i"), {"i": me["id"]}
        ).scalar()
    assert row.full_name == "Anonymised user" and row.phone is None and audit >= 2


def test_security_headers_present():
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


# ---- provider roles, applications, verification, directory ----

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_funder_posts_grants_but_corporate_cannot():
    body = {
        "kind": "grant",
        "title": "Test grant",
        "sector": "ict",
        "province": "Gauteng",
        "contract_value": 100000,
        "duration_months": 6,
        "scope_items": [{"code": "ICT-DEV", "value": 100000}],
        "requirements": [],
    }
    assert (
        client.post("/opportunities", headers=login("funder@kopano.demo"), json=body).status_code
        == 201
    )
    assert (
        client.post("/opportunities", headers=login("corporate@kopano.demo"), json=body).status_code
        == 422
    )
    assert (
        client.post("/opportunities", headers=login("sme-001@sme.demo"), json=body).status_code
        == 403
    )


def test_providers_only_see_their_own_opportunities():
    funder = client.get("/opportunities", headers=login("funder@kopano.demo")).json()
    corp = client.get("/opportunities", headers=login("corporate@kopano.demo")).json()
    assert {o["kind"] for o in corp} == {"procurement"}
    assert {o["kind"] for o in funder} >= {"grant", "investor"}
    assert all(o["provider"] == "Growth Catalyst Fund" for o in funder)


def test_youth_grant_gates_on_ownership():
    from app.seed_data import build_seed

    youth = {s.name for s in build_seed()[0] if "youth" in s.ownership}
    funder = login("funder@kopano.demo")
    opp = opp_id(funder, "Youth enterprise growth grant")
    names = {
        r["sme_name"] for r in client.get(f"/opportunities/{opp}/matches", headers=funder).json()
    }
    assert names, "expected at least one eligible SME"
    # Ownership is a mandatory gate: every match is youth-owned, and Sipho Packaging
    # (relevant capability, but not youth-owned) is dropped as a structural fail
    assert names <= youth
    assert "Sipho Packaging" not in names


def test_application_flow_and_ownership():
    sme = login("sme-002@sme.demo")
    items = client.get("/smes/me/opportunities", headers=sme).json()
    mine = next(i for i in items if i["title"] == "Provincial roads rehabilitation")
    mid = mine["match"]["match_id"]
    first = client.post(f"/applications/{mid}", headers=sme)
    assert first.status_code in (201, 409)
    assert client.post(f"/applications/{mid}", headers=sme).status_code == 409
    assert client.post(f"/applications/{mid}", headers=login("sme-005@sme.demo")).status_code == 404
    corp = login("corporate@kopano.demo")
    assert any(
        a["sme"] == "Nomsa Builders" for a in client.get("/applications", headers=corp).json()
    )
    assert client.get("/applications", headers=login("funder@kopano.demo")).json() is not None


def test_provider_overview_and_directory_hide_sensitive_fields():
    corp = login("corporate@kopano.demo")
    ov = client.get("/providers/overview", headers=corp).json()
    assert ov["active_opportunities"] == 6 and ov["matched_smes"] > 0
    assert ov["organisation"]["verification_status"] == "verified"
    directory = client.get("/providers/smes", headers=corp).json()
    assert len(directory) >= 40 and "ownership" not in directory[0]
    assert client.get("/providers/overview", headers=login("sme-001@sme.demo")).status_code == 403


def test_sme_completion_and_identity_check_retains_outcome_only():
    h = register("sme")
    # Registration with a valid number already passes the registry check: 20%
    assert client.get("/smes/me", headers=h).json()["completion"]["percent"] == 20
    bad = client.post(
        "/smes/me/verify-identity",
        headers=h,
        data={"id_last4": "12"},
        files={"selfie": ("s.png", PNG, "image/png")},
    )
    assert bad.status_code == 422
    notimg = client.post(
        "/smes/me/verify-identity",
        headers=h,
        data={"id_last4": "1234"},
        files={"selfie": ("s.png", b"not an image", "image/png")},
    )
    assert notimg.status_code == 415
    ok = client.post(
        "/smes/me/verify-identity",
        headers=h,
        data={"id_last4": "1234"},
        files={"selfie": ("s.png", PNG, "image/png")},
    )
    assert ok.status_code == 200 and "mock" in ok.json()["source_label"]
    assert "no image" in ok.json()["retained"]
    assert client.get("/smes/me", headers=h).json()["completion"]["percent"] == 40
    assert "1234" not in client.get("/me/data", headers=h).text


def test_my_audit_feed_is_personal():
    h = register("sme")
    events = client.get("/me/audit", headers=h).json()
    assert events and events[0]["action"] == "register"


def test_unmatched_opportunities_explain_why_in_plain_language():
    items = client.get("/smes/me/opportunities", headers=login("sme-002@sme.demo")).json()
    grant = next(i for i in items if i["title"] == "Youth enterprise growth grant")
    assert grant["match"] is None
    assert any("youth ownership" in b for b in grant["blockers"])
    matched = next(i for i in items if i["title"] == "Provincial roads rehabilitation")
    assert matched["match"] is not None and matched["blockers"] == []


def test_data_export_includes_matches_and_applications():
    data = client.get("/me/data", headers=login("sme-001@sme.demo")).json()
    assert data["matches"] and "components" in data["matches"][0]["explanation"]
    assert "applications" in data and "note" in data
