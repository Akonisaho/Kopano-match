"""Feedback, AI document reading, semantic relevance, CSV import, deadline alerts, ecosystem view
and the published evaluation. Needs a seeded database, like test_api.py."""

import uuid
from datetime import date, timedelta

from sqlalchemy import text

from app.db import engine
from app.llm import client as llm
from app.llm import prompts

from .test_api import PDF, _match_id, client, login, opp_id, register

RATINGS = {
    "quality": 5,
    "delivery": 4,
    "responsiveness": 4,
    "compliance": 5,
    "innovation": 3,
    "value_for_money": 4,
}


def _email_of(org_name: str) -> str:
    with engine.connect() as c:
        return c.execute(
            text(
                "select u.email from core.users u join core.organisations o "
                "on o.id = u.organisation_id where o.name = :n limit 1"
            ),
            {"n": org_name},
        ).scalar_one()


AWARD_VALUE = {"Khaya Earthworks": 4_000_000, "Thabo Civils": 3_500_000}  # as in test_api


def _awarded(corp, sme_name: str) -> None:
    mid = _match_id(corp, "Provincial roads rehabilitation", sme_name)
    client.post(f"/matches/{mid}/shortlist", headers=corp)
    r = client.post(
        f"/applications/{mid}/award", headers=corp, json={"value": AWARD_VALUE[sme_name]}
    )
    assert r.status_code in (200, 409)


def _feedback_id(corp, sme_name: str) -> str:
    """Leave feedback if it is still owed, otherwise find what was left on an earlier run."""
    waiting = [
        a for a in client.get("/feedback/awaiting", headers=corp).json() if a["sme"] == sme_name
    ]
    if waiting:
        r = client.post(
            f"/feedback/{waiting[0]['application_id']}",
            headers=corp,
            json={"ratings": RATINGS, "comment": "Solid work, finished on time."},
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]
    given = [f for f in client.get("/feedback/given", headers=corp).json() if f["sme"] == sme_name]
    return given[0]["id"]


def test_feedback_lifecycle_response_dispute_and_review():
    corp = login("corporate@kopano.demo")
    admin = login("admin@kopano.demo")
    _awarded(corp, "Khaya Earthworks")
    _awarded(corp, "Thabo Civils")

    # The ratings must cover all six criteria, and comments keep personal details out
    waiting = client.get("/feedback/awaiting", headers=corp).json()
    target = waiting[0]["application_id"] if waiting else str(uuid.uuid4())
    short = {k: v for k, v in RATINGS.items() if k != "quality"}
    assert (
        client.post(f"/feedback/{target}", headers=corp, json={"ratings": short}).status_code == 422
    )
    leak = client.post(
        f"/feedback/{target}",
        headers=corp,
        json={"ratings": RATINGS, "comment": "Call me on 082 123 4567"},
    )
    assert leak.status_code == 422

    khaya_fb = _feedback_id(corp, "Khaya Earthworks")
    thabo_fb = _feedback_id(corp, "Thabo Civils")

    # One review per award, only for your own awards, only from a buyer
    app_ids = [a["application_id"] for a in client.get("/feedback/awaiting", headers=corp).json()]
    assert all(a != target or not waiting for a in app_ids)
    stranger = register("corporate")
    assert (
        client.post(f"/feedback/{target}", headers=stranger, json={"ratings": RATINGS}).status_code
        == 404
    )
    khaya = login(_email_of("Khaya Earthworks"))
    assert (
        client.post(f"/feedback/{target}", headers=khaya, json={"ratings": RATINGS}).status_code
        == 403
    )

    # The business sees it and may answer once; nobody else can answer for it
    mine = client.get("/feedback/mine", headers=khaya).json()
    assert any(i["id"] == khaya_fb for i in mine["items"]) and mine["performance"]["reviews"] >= 1
    other_sme = login("sme-020@sme.demo")
    answer = {"text": "Thank you, the follow-up work is booked."}
    assert (
        client.post(f"/feedback/{khaya_fb}/respond", headers=other_sme, json=answer).status_code
        == 404
    )
    first = client.post(f"/feedback/{khaya_fb}/respond", headers=khaya, json=answer)
    assert first.status_code in (200, 409)
    assert (
        client.post(f"/feedback/{khaya_fb}/respond", headers=khaya, json=answer).status_code == 409
    )

    # Dispute: the buyer and a reviewer are told, a reviewer decides, the record keeps the reason
    thabo = login(_email_of("Thabo Civils"))
    d = client.post(
        f"/feedback/{thabo_fb}/dispute",
        headers=thabo,
        json={"text": "Delivery dates were agreed late."},
    )
    assert d.status_code in (200, 409)
    queue = client.get("/feedback/disputes", headers=admin).json()
    assert client.get("/feedback/disputes", headers=corp).status_code == 403
    if any(q["id"] == thabo_fb for q in queue):
        r = client.post(
            f"/feedback/{thabo_fb}/resolve",
            headers=admin,
            json={"decision": "remove", "note": "Dates were not in writing."},
        )
        assert r.status_code == 200 and r.json()["status"] == "removed"
    perf = client.get("/feedback/mine", headers=thabo).json()["performance"]
    removed = [
        i
        for i in client.get("/feedback/mine", headers=thabo).json()["items"]
        if i["id"] == thabo_fb
    ]
    assert removed[0]["status"] in ("removed", "upheld")
    if removed[0]["status"] == "removed":
        assert perf["reviews"] == sum(
            1
            for i in client.get("/feedback/mine", headers=thabo).json()["items"]
            if i["status"] != "removed"
        )
    titles = [n["title"] for n in client.get("/notifications", headers=khaya).json()["items"]]
    assert any("feedback" in t.lower() for t in titles)

    # A buyer can read the track record of a visible business; a stranger buyer too, an SME cannot
    org_id = client.get("/providers/smes", headers=corp).json()
    khaya_org = next(s["id"] for s in org_id if s["name"] == "Khaya Earthworks")
    tr = client.get(f"/feedback/performance/{khaya_org}", headers=corp)
    assert tr.status_code == 200 and tr.json()["reliable"] is False  # one review is an early signal
    assert client.get(f"/feedback/performance/{khaya_org}", headers=khaya).status_code == 403


def test_ai_reads_a_document_for_review_and_checks_it_against_the_account(monkeypatch):
    sme = register("sme")
    body = PDF + uuid.uuid4().bytes
    up = client.post(
        "/documents",
        headers=sme,
        data={"document_type": "TCS", "expiry_date": str(date.today() + timedelta(days=200))},
        files={"file": ("tcs.pdf", body, "application/pdf")},
    )
    assert up.status_code == 201, up.text
    doc = up.json()["id"]

    # No AI reader available: a clear answer, nothing invented
    monkeypatch.setattr(llm, "call", lambda *a, **k: None)
    r = client.post(f"/documents/{doc}/extract", headers=sme)
    assert r.status_code == 200 and r.json()["source"] == "unavailable"

    # The AI reads a different expiry date and a different company: both are flagged for the person
    seen = {}

    def fake(prompt, schema=None, file=None):
        seen["file"] = file
        return prompts.DocumentExtraction(
            document_type="TCS",
            company_name="Someone Else (Pty) Ltd",
            expiry_date=date.today() + timedelta(days=90),
        )

    monkeypatch.setattr(llm, "call", fake)
    r = client.post(f"/documents/{doc}/extract", headers=sme).json()
    assert r["source"] == "ai" and seen["file"][1] == "application/pdf"
    texts = " ".join(c["text"] for c in r["checks"])
    assert "you entered" in texts and "Someone Else" in texts
    assert r["draft"]["expiry_date"] == str(date.today() + timedelta(days=90))

    # Another business cannot read it; the expiry is only changed when the owner says so
    other = register("sme")
    assert client.post(f"/documents/{doc}/extract", headers=other).status_code == 404
    new = str(date.today() + timedelta(days=90))
    assert (
        client.put(f"/documents/{doc}/expiry", headers=other, json={"expiry_date": new}).status_code
        == 404
    )
    ok = client.put(f"/documents/{doc}/expiry", headers=sme, json={"expiry_date": new})
    assert ok.status_code == 200 and ok.json()["expiry_date"] == new
    actions = [a["action"] for a in client.get("/me/audit", headers=sme).json()]
    assert "document_ai_read" in actions and "document_expiry_set" in actions


def test_semantic_relevance_is_advisory_cached_and_scoped(monkeypatch):
    corp = login("corporate@kopano.demo")
    mid = _match_id(corp, "Provincial roads rehabilitation", "Emerging Surfacing")
    before = client.get(f"/matches/{mid}", headers=corp).json()

    with engine.begin() as c:  # a note cached by an earlier run would hide the call
        c.execute(
            text("delete from core.ai_insights where kind = 'semantic' and subject_id = :m"),
            {"m": mid},
        )
    calls = []

    def fake(prompt, schema=None, file=None):
        calls.append(prompt)
        assert "Surfacing" not in prompt  # the business name never reaches the model
        return prompts.SemanticRelevance(
            score=77, matched_themes=["road works"], rationale="Close fit."
        )

    monkeypatch.setattr(llm, "call", fake)
    a = client.get(f"/matches/{mid}/semantic", headers=corp).json()
    b = client.get(f"/matches/{mid}/semantic", headers=corp).json()
    assert a["source"] == "ai" and a["score"] == 77 and "never changes" in a["advisory"]
    assert len(calls) == 1 and b["score"] == 77  # second read comes from the cache

    # It sits beside the score and changes nothing
    after = client.get(f"/matches/{mid}", headers=corp).json()
    assert (before["fit"], before["readiness"], before["gate"]) == (
        after["fit"],
        after["readiness"],
        after["gate"],
    )

    # Without an AI reader it falls back to keyword overlap and says so
    monkeypatch.setattr(llm, "call", lambda *a, **k: None)
    other = _match_id(corp, "Provincial roads rehabilitation", "Khaya Earthworks")
    fb = client.get(f"/matches/{other}/semantic", headers=corp).json()
    assert fb["source"] == "keywords" and 0 <= fb["score"] <= 100

    assert client.get(f"/matches/{mid}/semantic", headers=register("corporate")).status_code == 404


def _csv(title: str, sector: str = "construction") -> bytes:
    head = "title,kind,sector,province,contract_value,duration_months,payment_terms_days,deadline,description,capabilities,documents,min_years\n"
    deadline = date.today() + timedelta(days=3)
    row = f'{title},procurement,{sector},Gauteng,3000000,12,30,{deadline},"Road resurfacing",CON-ROADS:2000000;CON-CIVIL:1000000,TCS;BBBEE,2\n'
    return (head + row).encode()


def test_csv_import_is_all_or_nothing_and_alerts_fire_once_per_match():
    corp = login("corporate@kopano.demo")
    files = lambda b: {"file": ("opps.csv", b, "text/csv")}  # noqa: E731
    title = f"Imported roads {uuid.uuid4().hex[:6]}"

    dry = client.post("/opportunities/import?dry_run=true", headers=corp, files=files(_csv(title)))
    assert dry.status_code == 200 and dry.json()["rows"] == 1 and dry.json()["created"] == 0
    assert not any(o["title"] == title for o in client.get("/opportunities", headers=corp).json())

    bad_title = f"Bad row {uuid.uuid4().hex[:6]}"
    bad = client.post(
        "/opportunities/import", headers=corp, files=files(_csv(bad_title, sector="mining"))
    )
    assert bad.status_code == 422 and bad.json()["detail"]["errors"][0]["row"] == 2
    assert not any(
        o["title"] == bad_title for o in client.get("/opportunities", headers=corp).json()
    )

    ok = client.post("/opportunities/import", headers=corp, files=files(_csv(title)))
    assert ok.status_code == 200 and ok.json()["created"] == 1
    assert client.get("/opportunities/import/template", headers=corp).status_code == 200
    assert (
        client.post(
            "/opportunities/import", headers=login("sme-001@sme.demo"), files=files(_csv(title))
        ).status_code
        == 403
    )

    # Closing in three days: good-fit businesses that have not applied are told, once
    oid = opp_id(corp, title)
    assert client.post(f"/opportunities/{oid}/match", headers=corp).status_code == 200
    admin = login("admin@kopano.demo")
    first = client.post("/admin/reminders/run", headers=admin).json()
    assert first["deadline_alerts"] >= 1
    assert client.post("/admin/reminders/run", headers=admin).json()["deadline_alerts"] == 0


def test_ecosystem_view_is_for_the_programme_owner_and_names_no_one():
    admin = login("admin@kopano.demo")
    r = client.get("/admin/ecosystem", headers=admin)
    assert r.status_code == 200
    e = r.json()
    assert e["totals"]["businesses"] >= 40 and e["funnel"][0]["stage"] == "Matched"
    assert e["sectors"] and e["provinces"] and e["skills"] and "assumption" in e["employment"]
    assert "Khaya" not in str(e) and "Thabo" not in str(e)
    assert client.get("/admin/ecosystem", headers=login("corporate@kopano.demo")).status_code == 403
    assert client.get("/admin/ecosystem", headers=login("sme-001@sme.demo")).status_code == 403


def test_published_evaluation_is_public_deterministic_and_neutral_on_ownership():
    r = client.get("/meta/evaluation")  # no sign-in
    assert r.status_code == 200
    e = r.json()
    assert e["scenarios"]["passed"] == e["scenarios"]["total"]
    assert e["determinism"]["identical"] is True
    assert e["fairness"]["scores_changed_by_ownership"] == 0
    assert e["data"]["personal_data"] is False and e["limitations"] and e["human_oversight"]
    engine_row, random_row = e["benchmark"]["methods"][0], e["benchmark"]["methods"][-1]
    assert engine_row["ndcg_at_5"] > random_row["ndcg_at_5"]


def test_profile_quality_flags_inconsistent_figures():
    sme = register("sme")
    put = client.put(
        "/smes/me",
        headers=sme,
        json={
            "sector": "construction",
            "province": "Gauteng",
            "annual_turnover": 500000,
            "years_trading": 0,
            "largest_past_contract": 5000000,
            "capability_codes": ["CON-ROADS"],
            "ownership": [],
            "visible_to_corporates": True,
        },
    )
    assert put.status_code == 200, put.text
    flags = " ".join(f["text"] for f in client.get("/smes/me/quality", headers=sme).json()["flags"])
    assert "three times" in flags and "years trading is 0" in flags
