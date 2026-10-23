"""Feedback, AI document reading, semantic relevance, CSV import, deadline alerts, ecosystem view
and the published evaluation. Needs a seeded database, like test_api.py."""

import re
import uuid
import zlib
from datetime import date, timedelta

from sqlalchemy import text

from app.db import engine
from app.llm import client as llm
from app.llm import embed as embed_mod
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


# ---------------------------------------------------------------- semantic search and ingestion


def _fake_embed(texts, task="RETRIEVAL_DOCUMENT"):
    """Stands in for the embedding service: a bag of hashed words, stable across processes."""
    out = []
    for t in texts:
        v = [0.0] * 1024
        for w in re.findall(r"[a-z]{3,}", t.lower()):
            v[zlib.crc32(w.encode()) % 1024] += 1.0
        out.append(v)
    return out


def _clear_embeddings() -> None:
    with engine.begin() as c:
        c.execute(text("delete from core.ai_insights where kind = 'embedding'"))


def test_semantic_search_ranks_by_meaning_and_falls_back_to_keywords(monkeypatch):
    _clear_embeddings()
    calls = []

    def counting(texts, task="RETRIEVAL_DOCUMENT"):
        calls.append(task)
        return _fake_embed(texts, task)

    monkeypatch.setattr(embed_mod, "embed", counting)
    sme = login(_email_of("Khaya Earthworks"))
    r = client.post(
        "/smes/me/search",
        headers=sme,
        json={"query": "rehabilitation of provincial roads and drainage"},
    ).json()
    assert r["source"] == "embeddings" and r["results"]
    assert any("road" in x["title"].lower() for x in r["results"][:3])
    assert r["results"][0]["similarity"] >= r["results"][-1]["similarity"]
    top = r["results"][0]
    assert top["match"] is None or {"fit", "readiness", "quadrant"} <= set(top["match"])
    first_calls = len(calls)
    client.post(
        "/smes/me/search", headers=sme, json={"query": "rehabilitation of provincial roads"}
    )
    assert (
        len(calls) == first_calls + 1
    )  # only the query is embedded again; opportunities are cached

    # A buyer searches businesses by description; hidden businesses never appear
    corp = login("corporate@kopano.demo")
    found = client.post(
        "/providers/search", headers=corp, json={"query": "road construction and civil engineering"}
    ).json()
    assert found["source"] == "embeddings" and found["results"]
    visible = {s["id"] for s in client.get("/providers/smes", headers=corp).json()}
    assert all(x["sme_id"] in visible for x in found["results"])
    assert "ownership" not in str(found)
    assert client.post("/providers/search", headers=sme, json={"query": "roads"}).status_code == 403
    assert client.post("/smes/me/search", headers=corp, json={"query": "roads"}).status_code == 403
    assert client.post("/smes/me/search", headers=sme, json={"query": "ab"}).status_code == 422

    # No embedding service: plain keyword overlap, and it says so
    _clear_embeddings()
    monkeypatch.setattr(embed_mod, "embed", lambda *a, **k: None)
    k = client.post(
        "/smes/me/search", headers=sme, json={"query": "provincial roads drainage"}
    ).json()
    assert k["source"] == "keywords" and k["results"][0]["similarity"] >= 0
    _clear_embeddings()


def _opp_body(title: str) -> dict:
    return {
        "kind": "procurement",
        "title": title,
        "sector": "construction",
        "province": "Gauteng",
        "contract_value": 900_000,
        "duration_months": 6,
        "scope_items": [{"code": "CON-ROADS", "value": 900_000}],
        "requirements": [],
    }


def test_procurement_system_feed_with_api_key():
    corp = login("corporate@kopano.demo")
    other = register("corporate")
    sme = login("sme-001@sme.demo")
    assert client.post("/ingest/keys", headers=sme, json={"name": "mine"}).status_code == 403

    made = client.post("/ingest/keys", headers=corp, json={"name": "SAP export"})
    assert made.status_code == 201
    key = made.json()["key"]
    assert key.startswith("kmk_") and "not shown again" in made.json()["note"]
    # Only a hash is kept: the key is never listed again
    listed = client.get("/ingest/keys", headers=corp).json()
    assert key not in str(listed) and any(k["name"] == "SAP export" for k in listed)

    title = f"Fed from ERP {uuid.uuid4().hex[:6]}"
    body = {"opportunities": [_opp_body(title), _opp_body(title + " B")]}
    assert client.post("/ingest/opportunities", json=body).status_code == 401  # no key
    assert (
        client.post(
            "/ingest/opportunities", headers={"X-API-Key": "kmk_wrong"}, json=body
        ).status_code
        == 401
    )
    ok = client.post("/ingest/opportunities", headers={"X-API-Key": key}, json=body)
    assert ok.status_code == 201 and ok.json()["created"] == 2
    mine = [o["title"] for o in client.get("/opportunities", headers=corp).json()]
    assert title in mine
    assert title not in [o["title"] for o in client.get("/opportunities", headers=other).json()]
    ranked = client.get(f"/opportunities/{opp_id(corp, title)}/matches", headers=corp).json()
    assert ranked  # matched on arrival, so businesses see it straight away

    bad = {"opportunities": [{**_opp_body("x"), "sector": "mining"}]}
    assert (
        client.post("/ingest/opportunities", headers={"X-API-Key": key}, json=bad).status_code
        == 422
    )
    # Another buyer cannot revoke it; the owner can, and the feed stops at once
    kid = next(k["id"] for k in listed if k["name"] == "SAP export")
    assert client.post(f"/ingest/keys/{kid}/revoke", headers=other).status_code == 404
    assert client.post(f"/ingest/keys/{kid}/revoke", headers=corp).json()["revoked"] is True
    assert (
        client.post("/ingest/opportunities", headers={"X-API-Key": key}, json=body).status_code
        == 401
    )
    actions = [a["action"] for a in client.get("/me/audit", headers=corp).json()]
    assert "ingest_key_created" in actions and "ingest_opportunities" in actions


def test_published_evaluation_includes_robustness_to_small_input_changes():
    e = client.get("/meta/evaluation").json()
    assert e["robustness"]["top3_overlap"] >= 0.8 and e["robustness"]["quadrant_stable"] >= 0.8


def test_readiness_passport_is_shared_by_choice_and_exposes_only_safe_facts():
    sme = register("sme")
    own = client.get("/smes/me/passport", headers=sme).json()
    assert own["enabled"] is False and own["link"] is None  # off until the business turns it on

    assert (
        client.post("/smes/me/passport/enable", headers=login("corporate@kopano.demo")).status_code
        == 403
    )
    on = client.post("/smes/me/passport/enable", headers=sme).json()
    assert (
        on["enabled"]
        and on["link"].count("/passport/") == 1
        and on["qr"].startswith("data:image/svg")
    )
    token = on["link"].rsplit("/", 1)[1]

    # Anyone with the link can read it, with no sign-in
    view = client.get(f"/passport/{token}")
    assert view.status_code == 200
    body = view.json()
    for key in ("turnover", "annual_turnover", "ownership", "email", "phone"):
        assert key not in str({k: v for k, v in body.items() if k != "notice"}).lower()
    assert "notice" in body and body["track_record"]["reviews"] == 0

    # A known business shows verified checks with their source, so a mock is labelled a mock
    khaya = login(_email_of("Khaya Earthworks"))
    k = client.post("/smes/me/passport/enable", headers=khaya).json()
    kview = client.get(f"/passport/{k['link'].rsplit('/', 1)[1]}").json()
    assert kview["checks"] and all("mock" in c["source"] for c in kview["checks"])
    assert kview["credentials_valid"] >= 1

    # Rotating kills the old link; switching off hides it
    new = client.post("/smes/me/passport/rotate", headers=sme).json()
    assert client.get(f"/passport/{token}").status_code == 404
    new_token = new["link"].rsplit("/", 1)[1]
    assert client.get(f"/passport/{new_token}").status_code == 200
    off = client.post("/smes/me/passport/disable", headers=sme).json()
    assert off["enabled"] is False and client.get(f"/passport/{new_token}").status_code == 404
    assert client.get("/passport/not-a-real-token").status_code == 404
    actions = [a["action"] for a in client.get("/me/audit", headers=sme).json()]
    assert {"passport_enabled", "passport_rotated", "passport_disabled"} <= set(actions)


def test_uploading_a_missing_document_rescores_the_business_at_once():
    sme = login("sme-001@sme.demo")  # planted: high fit, missing documents
    before = client.get("/smes/me/dashboard", headers=sme).json()
    gaps = before["open_gaps"]
    if not gaps:  # an earlier run already closed them
        return
    code = gaps[0]["credential"]
    ready_before = max(m["readiness"] for m in before["matches"])
    up = client.post(
        "/documents",
        headers=sme,
        data={"document_type": code, "expiry_date": str(date.today() + timedelta(days=300))},
        files={"file": (f"{code}.pdf", PDF + uuid.uuid4().bytes, "application/pdf")},
    )
    assert up.status_code == 201, up.text
    after = client.get("/smes/me/dashboard", headers=sme).json()
    assert code not in [
        g["credential"] for g in after["open_gaps"]
    ]  # the gap closed without any rerun
    assert max(m["readiness"] for m in after["matches"]) >= ready_before
