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
    assert ov["active_opportunities"] >= 6 and ov["matched_smes"] > 0
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


# ---- throttle, erasure deletes files, scanner, Unlock Plan ----

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def test_login_is_throttled_per_account_and_does_not_leak_which_emails_exist():
    email = f"{uuid.uuid4().hex[:8]}@nobody.example"  # never registered
    codes = [
        client.post("/auth/login", data={"username": email, "password": "wrong"}).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # A real account is not affected by someone else's failures
    ok = client.post("/auth/login", data={"username": "sme-004@sme.demo", "password": PASSWORD})
    assert ok.status_code == 200


def test_upload_scanner_rejects_the_standard_test_signature_and_stores_nothing():
    h = register("sme")
    r = client.post(
        "/documents",
        headers=h,
        data={"document_type": "TCS"},
        files={"file": ("x.pdf", PDF + EICAR, "application/pdf")},
    )
    assert r.status_code == 422 and "security scan" in r.json()["detail"]
    assert client.get("/documents", headers=h).json() == []


def test_erasure_deletes_uploaded_files_from_disk():
    from pathlib import Path

    h = register("sme")
    client.post(
        "/documents",
        headers=h,
        data={"document_type": "TCS"},
        files={"file": ("t.pdf", PDF + uuid.uuid4().bytes, "application/pdf")},
    )
    org = client.get("/me", headers=h).json()["organisation"]["id"]
    with engine.connect() as conn:
        path = conn.execute(
            text("SELECT file_url FROM sensitive.documents WHERE organisation_id = :o"), {"o": org}
        ).scalar_one()
    assert Path(path).is_file()
    out = client.post("/me/delete", headers=h).json()
    assert out["files_deleted"] == 1 and not Path(path).exists()


def test_unlock_plan_moves_the_numbers_using_the_real_rules():
    sme = login("sme-001@sme.demo")
    plan = client.post("/smes/me/simulate", headers=sme, json={"credentials": ["COID", "CIDB"]})
    assert plan.status_code == 200
    p = plan.json()
    assert p["after"]["award_ready"] > p["before"]["award_ready"]
    assert p["after"]["value"] > p["before"]["value"]
    assert p["total_days"] == 30 and p["total_cost_zar"] == 4200  # parallel wait, summed cost
    assert any(o["newly_award_ready"] for o in p["opportunities"])
    # Nothing is saved: the live match is unchanged
    again = client.get("/smes/me/opportunities", headers=sme).json()
    roads = next(i for i in again if i["title"] == "Provincial roads rehabilitation")
    assert roads["match"]["quadrant"] == "coachable"
    bad = client.post("/smes/me/simulate", headers=sme, json={"credentials": ["NOPE"]})
    assert bad.status_code == 422
    corp = login("corporate@kopano.demo")
    assert (
        client.post("/smes/me/simulate", headers=corp, json={"credentials": ["COID"]}).status_code
        == 403
    )


# ---- Unlock Map and decision dossier ----


def test_unlock_map_aggregates_without_names_and_is_provider_only():
    corp = login("corporate@kopano.demo")
    out = client.get("/providers/bottlenecks", headers=corp).json()
    assert out["rows"] and out["total_value_locked"] > 0
    top = out["rows"][0]
    assert top["smes_blocked"] > 0 and top["value_locked"] > 0 and top["days"] > 0
    values = [r["value_locked"] for r in out["rows"]]
    assert values == sorted(values, reverse=True)
    assert "sme" not in str(out).lower().replace("smes", "")  # aggregates only, no names
    assert (
        client.get("/providers/bottlenecks", headers=login("sme-001@sme.demo")).status_code == 403
    )


def test_decision_dossier_has_rules_scores_sources_and_frozen_history():
    corp = login("corporate@kopano.demo")
    opp = opp_id(corp, "Provincial roads rehabilitation")
    ranked = client.get(f"/opportunities/{opp}/matches", headers=corp).json()
    mid = next(r["match_id"] for r in ranked if r["sme_name"] == "Nomsa Builders")
    client.post(f"/matches/{mid}/shortlist", headers=corp)
    d = client.get(f"/matches/{mid}/dossier", headers=corp).json()
    assert d["model_version"] == "v1" and d["rules"] and d["result"]["components"]
    assert any("mock" in v["source_label"] for v in d["verifications"])
    decision = [x for x in d["decisions"] if x["action"] == "match_shortlisted"][-1]
    assert decision["by_role"] == "corporate" and decision["snapshot"]["fit"] == d["result"]["fit"]
    assert d["matches_decision_snapshot"] is True
    # The SME it concerns can read it; another SME and a stranger cannot
    assert (
        client.get(f"/matches/{mid}/dossier", headers=login("sme-002@sme.demo")).status_code == 200
    )
    assert (
        client.get(f"/matches/{mid}/dossier", headers=login("sme-005@sme.demo")).status_code == 404
    )
    assert client.get(f"/matches/{mid}/dossier", headers=register("corporate")).status_code == 404


# ---- service emails (log mode: kept in memory, nothing leaves the machine) ----


def test_service_emails_go_to_the_right_people_and_carry_no_scores():
    from app.adapters.email import OUTBOX

    OUTBOX.clear()
    register("sme")
    assert any(e["subject"] == "Welcome to Kopano Match" for e in OUTBOX)

    OUTBOX.clear()
    corp = login("corporate@kopano.demo")
    opp = opp_id(corp, "Provincial roads rehabilitation")
    ranked = client.get(f"/opportunities/{opp}/matches", headers=corp).json()
    mid = next(r["match_id"] for r in ranked if r["sme_name"] == "Nomsa Builders")
    client.post(f"/matches/{mid}/shortlist", headers=corp)
    mail = [e for e in OUTBOX if e["to"] == "sme-002@sme.demo"]
    assert mail and "shortlisted" in mail[-1]["subject"].lower()
    assert "fit" not in mail[-1]["html"].lower() and "readiness" not in mail[-1]["html"].lower()

    OUTBOX.clear()
    sme = login("sme-005@sme.demo")
    items = client.get("/smes/me/opportunities", headers=sme).json()
    roads = next(i for i in items if i["title"] == "Provincial roads rehabilitation")
    client.post(f"/applications/{roads['match']['match_id']}", headers=sme)
    if not OUTBOX:  # already applied in an earlier run: the seed pre-applied this SME
        return
    assert any(
        e["to"] == "corporate@kopano.demo" and "New application" in e["subject"] for e in OUTBOX
    )


def test_a_failing_email_provider_never_breaks_the_request(monkeypatch):
    from app import notifications

    class Broken:
        def send(self, *a, **k):
            raise RuntimeError("provider down")

    monkeypatch.setattr(notifications, "email_sender", lambda: Broken())
    h = register("sme")  # welcome email fails silently
    assert client.get("/me", headers=h).status_code == 200


# ---- notification bell, reminders, password reset, two-step sign-in ----


def _email_link(to: str, contains: str) -> str:
    import re

    from app.adapters.email import OUTBOX

    mail = [e for e in OUTBOX if e["to"] == to and contains in e["subject"]][-1]
    return re.search(r'href="([^"]+)"', mail["html"]).group(1)


def test_in_app_notifications_work_without_any_email_provider():
    corp = login("corporate@kopano.demo")
    opp = opp_id(corp, "Provincial roads rehabilitation")
    ranked = client.get(f"/opportunities/{opp}/matches", headers=corp).json()
    mid = next(r["match_id"] for r in ranked if r["sme_name"] == "Lerato Civil & Electrical")
    client.post(f"/matches/{mid}/shortlist", headers=corp)
    sme = login("sme-006@sme.demo")
    box = client.get("/notifications", headers=sme).json()
    assert box["unread"] >= 1 and any("shortlisted" in n["title"] for n in box["items"])
    assert client.post("/notifications/read", headers=sme).status_code == 200
    assert client.get("/notifications", headers=sme).json()["unread"] == 0
    # Someone else's bell is empty of this notice
    other = client.get("/notifications", headers=login("sme-005@sme.demo")).json()
    assert not any("Lerato" in n["body"] for n in other["items"])


def test_expiry_reminders_go_out_once_and_only_once():
    admin = login("admin@kopano.demo")
    first = client.post("/admin/reminders/run", headers=admin)
    assert first.status_code == 200
    second = client.post("/admin/reminders/run", headers=admin).json()
    assert second["notices_sent"] == 0 and second["documents"] == 0
    assert client.post("/admin/reminders/run", headers=login("sme-001@sme.demo")).status_code == 403


def test_password_reset_is_single_use_expires_and_does_not_reveal_accounts():
    from app.adapters.email import OUTBOX

    h = register("sme")
    email = client.get("/me", headers=h).json()["email"]
    OUTBOX.clear()
    a = client.post("/auth/forgot", json={"email": email})
    b = client.post("/auth/forgot", json={"email": f"{uuid.uuid4().hex[:8]}@nobody.example"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert len([e for e in OUTBOX if "Reset" in e["subject"]]) == 1  # unknown email: nothing sent
    token = _email_link(email, "Reset").split("token=")[1]
    new = "a-brand-new-password-1"
    assert client.post("/auth/reset", json={"token": token, "new_password": new}).status_code == 200
    assert client.post("/auth/login", data={"username": email, "password": new}).status_code == 200
    assert (
        client.post(
            "/auth/login", data={"username": email, "password": "a-long-test-password"}
        ).status_code
        == 401
    )
    again = client.post("/auth/reset", json={"token": token, "new_password": "another-password-22"})
    assert again.status_code == 400  # single use
    bogus = client.post("/auth/reset", json={"token": "x" * 40, "new_password": new})
    assert bogus.status_code == 400
    weak = client.post("/auth/reset", json={"token": token, "new_password": "short"})
    assert weak.status_code == 422


def test_two_step_sign_in_end_to_end():
    import time

    from sqlalchemy import text

    from app import mfa

    h = register("sme")
    me = client.get("/me", headers=h).json()
    email = me["email"]
    setup = client.post("/auth/mfa/setup", headers=h).json()
    secret = setup["secret"]
    assert setup["qr"].startswith("data:image/svg+xml") and "otpauth://" in setup["otpauth_uri"]
    # The secret is encrypted at rest, never stored as given
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT totp_secret_enc FROM core.users WHERE id = :i"), {"i": me["id"]}
        ).scalar_one()
    assert stored and secret not in stored
    wrong = client.post("/auth/mfa/enable", headers=h, json={"code": "000000"})
    assert wrong.status_code == 400
    now = time.time()
    on = client.post("/auth/mfa/enable", headers=h, json={"code": mfa.totp(secret, now)})
    assert on.status_code == 200
    recovery = on.json()["recovery_codes"]
    assert len(recovery) == 8 and client.get("/me", headers=h).json()["mfa_enabled"] is True

    # Password alone no longer signs you in
    step1 = client.post("/auth/login", data={"username": email, "password": "a-long-test-password"})
    body = step1.json()
    assert step1.status_code == 200 and body["mfa_required"] and "access_token" not in body
    # The half-finished token is useless as an access token
    stolen = {"Authorization": f"Bearer {body['mfa_token']}"}
    assert client.get("/me", headers=stolen).status_code == 401
    bad = client.post("/auth/mfa/verify", json={"mfa_token": body["mfa_token"], "code": "111111"})
    assert bad.status_code == 401
    # The code used to enable cannot be replayed; the next one works
    replay = client.post(
        "/auth/mfa/verify", json={"mfa_token": body["mfa_token"], "code": mfa.totp(secret, now)}
    )
    assert replay.status_code == 401
    ok = client.post(
        "/auth/mfa/verify",
        json={"mfa_token": body["mfa_token"], "code": mfa.totp(secret, now + 30)},
    )
    assert ok.status_code == 200 and ok.json()["access_token"]
    # A recovery code works once
    s2 = client.post(
        "/auth/login", data={"username": email, "password": "a-long-test-password"}
    ).json()
    r1 = client.post("/auth/mfa/verify", json={"mfa_token": s2["mfa_token"], "code": recovery[0]})
    assert r1.status_code == 200
    s3 = client.post(
        "/auth/login", data={"username": email, "password": "a-long-test-password"}
    ).json()
    r2 = client.post("/auth/mfa/verify", json={"mfa_token": s3["mfa_token"], "code": recovery[0]})
    assert r2.status_code == 401
    # Switching it off needs a valid code and then restores plain sign-in
    token = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert (
        client.post("/auth/mfa/disable", headers=token, json={"code": "123456"}).status_code == 400
    )
    assert (
        client.post("/auth/mfa/disable", headers=token, json={"code": recovery[1]}).status_code
        == 200
    )
    plain = client.post("/auth/login", data={"username": email, "password": "a-long-test-password"})
    assert "access_token" in plain.json()


def test_overlong_passwords_get_a_clear_422_not_a_server_error():
    base = {
        "email": f"{uuid.uuid4().hex[:8]}@kopano-test.com",
        "full_name": "Long Password",
        "role": "sme",
        "organisation_name": "Long Org",
        "consent": True,
    }
    r = client.post("/auth/register", json={**base, "password": "A" * 100})
    assert r.status_code == 422
    r = client.post(
        "/auth/register", json={**base, "password": "é" * 50}
    )  # 100 bytes in 50 characters
    assert r.status_code == 422
    assert (
        client.post("/auth/reset", json={"token": "x" * 40, "new_password": "B" * 100}).status_code
        == 422
    )
    ok = client.post("/auth/register", json={**base, "password": "C" * 72})
    assert ok.status_code == 201
    # signing in with an absurdly long password is a plain refusal, never a crash
    login_long = client.post("/auth/login", data={"username": base["email"], "password": "D" * 500})
    assert login_long.status_code == 401


# ---- awards, impact report, fastest route ----


def _match_id(headers, opp_title, sme_name):
    opp = opp_id(headers, opp_title)
    ranked = client.get(f"/opportunities/{opp}/matches", headers=headers).json()
    return next(r["match_id"] for r in ranked if r["sme_name"] == sme_name)


def test_awarding_needs_a_shortlist_freezes_the_record_and_feeds_the_impact_report():
    corp = login("corporate@kopano.demo")
    roads = "Provincial roads rehabilitation"
    khaya = _match_id(corp, roads, "Khaya Earthworks")
    thabo = _match_id(corp, roads, "Thabo Civils")  # has open document gaps
    unshortlisted = _match_id(corp, roads, "Emerging Surfacing")

    # Not shortlisted: refused
    refusal = client.post(
        f"/applications/{unshortlisted}/award", headers=corp, json={"value": 1000}
    )
    assert refusal.status_code == 409 and "Shortlist" in refusal.json()["detail"]

    for mid, value in ((khaya, 4_000_000), (thabo, 3_500_000)):
        assert client.post(f"/matches/{mid}/shortlist", headers=corp).status_code in (200, 409)
        first = client.post(f"/applications/{mid}/award", headers=corp, json={"value": value})
        assert first.status_code in (200, 409)  # 409 only if an earlier run already awarded it
        again = client.post(f"/applications/{mid}/award", headers=corp, json={"value": value})
        assert again.status_code == 409 and "Already awarded" in again.json()["detail"]
        # An award is final: it cannot be quietly turned into a rejection
        assert client.post(f"/matches/{mid}/reject", headers=corp).status_code == 409

    assert (
        client.post(f"/applications/{khaya}/award", headers=corp, json={"value": -5}).status_code
        == 422
    )
    stranger = register("corporate")
    assert (
        client.post(
            f"/applications/{khaya}/award", headers=stranger, json={"value": 1000}
        ).status_code
        == 404
    )
    sme = login("sme-005@sme.demo")
    assert (
        client.post(f"/applications/{khaya}/award", headers=sme, json={"value": 1000}).status_code
        == 403
    )

    # The reasoning at the moment of award is frozen in the audit trail and shows in the dossier
    d = client.get(f"/matches/{khaya}/dossier", headers=corp).json()
    won = [x for x in d["decisions"] if x["action"] == "match_awarded"][-1]
    assert won["snapshot"]["gate"] and won["snapshot"]["model_version"] == "v1"
    assert d["status"] == "awarded"

    # The SME is told, and the provider's application list shows the status
    titles = [n["title"] for n in client.get("/notifications", headers=sme).json()["items"]]
    assert any(t.startswith("Awarded:") for t in titles)
    apps = client.get("/applications", headers=corp).json()
    assert any(a["sme"] == "Khaya Earthworks" and a["status"] == "awarded" for a in apps)

    impact = client.get("/providers/impact", headers=corp).json()
    assert impact["awards"] >= 2 and impact["value_awarded"] >= 7_500_000
    assert impact["awarded_despite_gap"]["awards"] >= 1  # Thabo had open gaps when awarded
    assert impact["ownership"]["youth"]["share_pct"] > 0  # Thabo is youth-owned
    assert impact["by_province"] and impact["by_sector"]
    assert impact["days_to_award_median"] is not None
    # Aggregates only: no business names anywhere in the report
    assert "Thabo" not in str(impact) and "Khaya" not in str(impact)

    csv_text = client.get("/providers/impact.csv", headers=corp)
    assert csv_text.status_code == 200 and csv_text.headers["content-type"].startswith("text/csv")
    assert "Value awarded (ZAR)" in csv_text.text and "Thabo" not in csv_text.text
    assert client.get("/providers/impact", headers=sme).status_code == 403
    assert client.get("/providers/impact", headers=login("admin@kopano.demo")).status_code == 200
    # Another buyer sees none of this buyer's awards
    other = client.get("/providers/impact", headers=login("funder@kopano.demo")).json()
    assert other["value_awarded"] < impact["value_awarded"]


def test_unlock_plan_ranks_the_fastest_route_first():
    sme = login("sme-001@sme.demo")
    both = client.post(
        "/smes/me/simulate", headers=sme, json={"credentials": ["COID", "CIDB"]}
    ).json()
    routes = both["routes"]
    assert {r["code"] for r in routes} == {"COID", "CIDB"}
    # Readiness 75 (three of four documents) already clears the 60 line, so each one alone
    # unlocks the same contract. The faster one is the better first move.
    assert all(r["gain_value"] > 0 and r["newly_award_ready"] == 1 for r in routes)
    assert routes[0]["code"] == "COID" and routes[0]["days"] < routes[1]["days"]
    per_day = [r["gain_value"] / r["days"] for r in routes]
    assert per_day == sorted(per_day, reverse=True)
    single = client.post("/smes/me/simulate", headers=sme, json={"credentials": ["COID"]}).json()
    assert single["after"]["award_ready"] > single["before"]["award_ready"]
    already = client.post(
        "/smes/me/simulate", headers=login("sme-004@sme.demo"), json={"credentials": ["TCS"]}
    ).json()
    assert already["routes"] == []  # nothing to obtain: already valid


# ---- consortium invitations ----


def _email_of(org_id) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT email FROM core.users WHERE organisation_id = :o AND deleted_at IS NULL LIMIT 1"
            ),
            {"o": str(org_id)},
        ).scalar_one()


def test_consortium_invitations_full_lifecycle_and_privacy():
    corp = login("corporate@kopano.demo")
    body = {
        "kind": "procurement",
        "title": f"Consortium test {uuid.uuid4().hex[:6]}",
        "sector": "agriculture",
        "province": "Limpopo",
        "contract_value": 3_000_000,
        "duration_months": 12,
        "scope_items": [
            {"code": "AGR-LOG", "value": 1_500_000},
            {"code": "MFG-FAB", "value": 1_500_000},
        ],
        "requirements": [],
    }
    opp = client.post("/opportunities", headers=corp, json=body).json()["id"]
    client.post(f"/opportunities/{opp}/match", headers=corp)

    first = client.post(f"/opportunities/{opp}/consortium/invite", headers=corp)
    assert first.status_code == 201
    inv = first.json()
    assert inv["status"] == "proposed" and len(inv["members"]) >= 2
    assert all(mm["response"] == "pending" and mm["scope"] for mm in inv["members"])
    assert client.post(f"/opportunities/{opp}/consortium/invite", headers=corp).status_code == 409

    names = [mm["name"] for mm in inv["members"]]
    heads = [login(_email_of(mm["sme_id"])) for mm in inv["members"]]

    # Privacy: an invited SME sees its own part and a count, never the partners' names
    mine = next(
        i
        for i in client.get("/consortia", headers=heads[0]).json()
        if i["opportunity"]["id"] == opp
    )
    assert mine["my_part"] and mine["partners"] == len(names) - 1 and mine["partner_names"] == []
    assert not any(n in str(mine) for n in names[1:])

    # Only invited SMEs can answer; a buyer cannot answer for them
    outsider = login("sme-001@sme.demo")
    assert (
        client.post(
            f"/consortia/{mine['id']}/respond", headers=outsider, json={"accept": True}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/consortia/{mine['id']}/respond", headers=corp, json={"accept": True}
        ).status_code
        == 403
    )
    stranger = register("corporate")
    assert (
        client.post(f"/opportunities/{opp}/consortium/invite", headers=stranger).status_code == 404
    )

    # One decline and the proposal lapses for everybody
    declined = client.post(
        f"/consortia/{mine['id']}/respond", headers=heads[0], json={"accept": False}
    )
    assert declined.json()["status"] == "declined"
    assert (
        client.post(
            f"/consortia/{mine['id']}/respond", headers=heads[1], json={"accept": True}
        ).status_code
        == 409
    )
    assert (
        client.get(f"/opportunities/{opp}/consortium", headers=corp).json()["invitation"]["status"]
        == "declined"
    )
    lapsed = [n["title"] for n in client.get("/notifications", headers=heads[1]).json()["items"]]
    assert any(t.startswith("Consortium lapsed") for t in lapsed)

    # The buyer can invite again, and this time everyone accepts
    again = client.post(f"/opportunities/{opp}/consortium/invite", headers=corp)
    assert again.status_code == 201 and again.json()["id"] != inv["id"]
    for head in heads:
        row = next(
            i
            for i in client.get("/consortia", headers=head).json()
            if i["opportunity"]["id"] == opp and i["status"] == "proposed"
        )
        assert (
            client.post(
                f"/consortia/{row['id']}/respond", headers=head, json={"accept": True}
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/consortia/{row['id']}/respond", headers=head, json={"accept": True}
            ).status_code
            == 409
        )

    formed = client.get(f"/opportunities/{opp}/consortium", headers=corp).json()["invitation"]
    assert formed["status"] == "formed" and all(
        mm["response"] == "accepted" for mm in formed["members"]
    )
    final = next(
        i
        for i in client.get("/consortia", headers=heads[0]).json()
        if i["opportunity"]["id"] == opp and i["status"] == "formed"
    )
    assert sorted(final["partner_names"]) == sorted(names[1:])  # names revealed only now
    assert any(
        t.startswith("Consortium formed")
        for t in [
            n["title"] for n in client.get("/notifications", headers=heads[1]).json()["items"]
        ]
    )
    assert client.post(f"/opportunities/{opp}/consortium/invite", headers=corp).status_code == 409
    trail = client.get(
        "/admin/audit",
        params={"entity_type": "consortium", "entity_id": final["id"]},
        headers=login("admin@kopano.demo"),
    ).json()
    assert any(a["action"] == "consortium_response" for a in trail)
