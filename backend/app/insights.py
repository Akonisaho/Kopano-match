"""Insights built on top of the stored data: ecosystem aggregates, track record, semantic relevance.

Everything an AI writes here is advisory and cached with a hash of its input. Scores, gates and
shortlists never read from it. Each AI call has a deterministic fallback, so a missing key or a
slow network only costs the nicer wording.
"""

import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE
from .llm import client, prompts
from .config import settings
from .i18n import LANGUAGES, REVIEWED
from .llm import embed as emb

CRITERIA = {
    "quality": "Quality of work",
    "delivery": "Delivery on time",
    "responsiveness": "Responsiveness",
    "compliance": "Compliance",
    "innovation": "Innovation",
    "value_for_money": "Value for money",
}
RELIABLE_AFTER = 3  # fewer reviews than this is an early signal, not a rating
# Placeholder until YES supplies a measured figure. Shown as an assumption wherever it is used.
JOBS_PER_R1M = 3.0
SMALL_CELL = 3  # counts below this are shown as "under 3" so no single business can be picked out


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _cached(db: Session, kind: str, subject: uuid.UUID, h: str) -> dict | None:
    row = db.scalar(
        select(m.AiInsight).where(m.AiInsight.kind == kind, m.AiInsight.subject_id == subject)
    )
    return row.payload if row is not None and row.input_hash == h else None


def _store(db: Session, kind: str, subject: uuid.UUID, h: str, payload: dict) -> None:
    row = db.scalar(
        select(m.AiInsight).where(m.AiInsight.kind == kind, m.AiInsight.subject_id == subject)
    )
    if row is None:
        db.add(m.AiInsight(kind=kind, subject_id=subject, input_hash=h, payload=payload))
    else:
        row.input_hash, row.payload = h, payload
    db.commit()


# ---------------------------------------------------------------- track record


def _counted(f: m.Feedback) -> bool:
    return f.status != "removed"


KINDS = {
    "procurement": "Procurement / Contract Delivery",
    "training": "Training Programme",
    "incubation": "Incubation Programme",
    "acceleration": "Acceleration Programme",
    "mentorship": "Mentorship",
    "funding": "Funding Programme",
    "grant": "Grant Programme",
    "supplier_dev": "Supplier Development Programme",
    "enterprise_dev": "Enterprise Development Programme",
    "business_support": "Business Support Programme",
    "investment": "Investment Relationship",
    "other": "Other Verified Engagement",
}
REVIEWER_TYPES = {"corporate": "Corporate buyer", "funder": "Funder", "support": "Support programme"}


def review_overall(f: m.Feedback) -> float:
    """One review's star rating: the mean of whatever it rated (six criteria, or a single overall)."""
    vals = list(f.ratings.values())
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def _feedback_rows(db: Session, sme_org_id: uuid.UUID) -> list[m.Feedback]:
    return [
        f
        for f in db.scalars(
            select(m.Feedback)
            .where(m.Feedback.sme_id == sme_org_id)
            .order_by(m.Feedback.created_at.desc())
        )
        if _counted(f)
    ]


def star_map(db: Session, sme_ids: list[uuid.UUID]) -> dict:
    """Headline rating for many businesses at once: id -> (rating, number of reviews).

    Shown beside a match. It is never an input to a score, a gate or a shortlist.
    """
    if not sme_ids:
        return {}
    by: dict = defaultdict(list)
    for f in db.scalars(select(m.Feedback).where(m.Feedback.sme_id.in_(sme_ids))):
        if _counted(f):
            by[f.sme_id].append(review_overall(f))
    return {k: (round(sum(v) / len(v), 1), len(v)) for k, v in by.items()}


def performance(db: Session, sme_org_id: uuid.UUID, with_summary: bool = True) -> dict:
    rows = _feedback_rows(db, sme_org_id)
    n = len(rows)
    detailed = [f for f in rows if f.kind == "procurement" and "quality" in f.ratings]
    d = len(detailed)
    avg = {
        k: round(sum(f.ratings.get(k, 0) for f in detailed) / d, 2) if d else None for k in CRITERIA
    }
    out = {
        "reviews": n,
        "reliable": n >= RELIABLE_AFTER,
        "overall": round(sum(review_overall(f) for f in rows) / n, 2) if n else None,
        "criteria": [{"key": k, "label": CRITERIA[k], "average": avg[k]} for k in CRITERIA],
        "disputed_open": sum(1 for f in rows if f.status == "disputed"),
        "responded": sum(1 for f in rows if f.sme_response),
        "summary": None,
    }
    if n and with_summary:
        out["summary"] = summarise(db, sme_org_id, rows, avg)
    return out


def summarise(db: Session, sme_org_id: uuid.UUID, rows: list[m.Feedback], avg: dict) -> dict:
    payload = [
        {
            "ratings": f.ratings,
            "comment": (f.comment or "")[:500],
            "response": (f.sme_response or "")[:300],
        }
        for f in rows[:12]
    ]
    h = _hash(payload)
    hit = _cached(db, "feedback_summary", sme_org_id, h)
    if hit:
        return hit
    ranked = sorted((k for k in CRITERIA if avg[k] is not None), key=lambda k: avg[k], reverse=True)
    fallback = {
        "source": "figures",
        "summary": (
            f"Across {len(rows)} review{'s' if len(rows) != 1 else ''}, the strongest area is "
            f"{CRITERIA[ranked[0]].lower()} ({avg[ranked[0]]}/5) and the weakest is "
            f"{CRITERIA[ranked[-1]].lower()} ({avg[ranked[-1]]}/5)."
            if ranked
            else "No ratings yet."
        ),
        "strengths": [CRITERIA[k] for k in ranked[:2] if avg[k] >= 4],
        "development_areas": [CRITERIA[k] for k in ranked[::-1][:2] if avg[k] < 3.5],
    }
    result = client.call(
        prompts.FEEDBACK_SUMMARY.format(feedback=json.dumps(payload)), prompts.FeedbackSummary
    )
    out = {"source": "ai", **result.model_dump()} if result else fallback
    _store(db, "feedback_summary", sme_org_id, h, out)
    return out


def _badges(rows: list[m.Feedback], awards: int) -> list[dict]:
    """Badges come only from verified records. Nothing here is self-declared."""
    out: list[dict] = []

    def add(key: str, label: str, why: str) -> None:
        out.append({"key": key, "label": label, "why": why})

    proc = [f for f in rows if f.kind == "procurement"]
    if awards:
        add("awarded", "Work awarded", f"{awards} opportunity award{'s' if awards != 1 else ''} recorded")
    if proc:
        add("rated", "Corporate rated", "Rated by a buyer that awarded it work")
    delivery = [f.ratings["delivery"] for f in proc if "delivery" in f.ratings]
    if len(delivery) >= 2 and sum(delivery) / len(delivery) >= 4.5:
        add("delivery", "High delivery rating", "Delivery on time averages 4.5 or more")
    for f in rows:
        c = f.context or {}
        if f.kind in ("incubation", "acceleration") and c.get("completion") == "completed":
            add("graduate", "Programme graduate", f"Completed {f.programme}")
            break
    for f in rows:
        c = f.context or {}
        if f.kind == "training" and c.get("total_sessions"):
            add("training", "Training participant", f"Attendance recorded for {f.programme}")
            break
    for f in rows:
        c = f.context or {}
        if c.get("total_sessions") and c.get("sessions_attended") == c.get("total_sessions"):
            add("attendance", "100% attendance", f"Attended every session of {f.programme}")
            break
    if any(f.kind in ("funding", "grant") for f in rows):
        add("funded", "Funding relationship", "A funder has confirmed a funding or grant programme")
    return out


def reputation(db: Session, sme_org_id: uuid.UUID) -> dict:
    """The familiar view: one star rating and a count, then the individual verified reviews.

    A business with no reviews gets 'no ratings yet', never a zero. The rating is context for a
    buyer. It is not read by the matching engine and does not move a match score.
    """
    rows = _feedback_rows(db, sme_org_id)
    names = {
        o.id: o
        for o in db.scalars(
            select(m.Organisation).where(m.Organisation.id.in_({f.provider_org_id for f in rows}))
        )
    } if rows else {}
    awards = db.execute(
        select(m.Application, m.Opportunity)
        .join(m.Match, m.Match.id == m.Application.match_id)
        .join(m.Opportunity, m.Opportunity.id == m.Match.opportunity_id)
        .where(m.Match.sme_id == sme_org_id, m.Application.awarded_at.is_not(None))
        .order_by(m.Application.awarded_at.desc())
    ).all()
    award_orgs = {
        o.id: o.name
        for o in db.scalars(
            select(m.Organisation).where(m.Organisation.id.in_({opp.organisation_id for _, opp in awards}))
        )
    } if awards else {}

    reviews = []
    for f in rows:
        org = names.get(f.provider_org_id)
        reviews.append(
            {
                "id": f.id,
                "rating": review_overall(f),
                "reviewer": org.name if org else "Organisation",
                "reviewer_type": REVIEWER_TYPES.get(org.org_type, "Organisation") if org else "",
                "kind": f.kind,
                "kind_label": KINDS.get(f.kind, KINDS["other"]),
                "programme": f.programme,
                "comment": f.comment,
                "context": f.context or {},
                "response": f.sme_response,
                "status": f.status,
                "basis": f.basis,
                "created_at": f.created_at,
            }
        )
    n = len(rows)
    dist = Counter(round(review_overall(f)) for f in rows)
    timeline = [
        {
            "when": f.created_at,
            "title": f"{names[f.provider_org_id].name if f.provider_org_id in names else 'Organisation'}"
            f" · {f.programme or KINDS.get(f.kind, '')}",
            "detail": _context_line(f),
            "rating": review_overall(f),
            "type": "review",
        }
        for f in rows
    ] + [
        {
            "when": a.awarded_at,
            "title": f"{award_orgs.get(opp.organisation_id, 'Organisation')} · {opp.title}",
            "detail": "Awarded",
            "rating": None,
            "type": "award",
        }
        for a, opp in awards
    ]
    timeline.sort(key=lambda t: t["when"], reverse=True)
    programmes = sum(1 for f in rows if f.kind != "procurement")
    return {
        "rating": round(sum(review_overall(f) for f in rows) / n, 1) if n else None,
        "reviews": n,
        "reliable": n >= RELIABLE_AFTER,
        "distribution": {str(s): dist.get(s, 0) for s in (5, 4, 3, 2, 1)},
        "stats": {
            "awards": len(awards),
            "reviewed_contracts": sum(1 for f in rows if f.kind == "procurement"),
            "programmes": programmes,
        },
        "badges": _badges(rows, len(awards)),
        "reviews_list": reviews,
        "timeline": timeline,
    }


def _context_line(f: m.Feedback) -> str:
    c = f.context or {}
    bits = []
    if c.get("total_sessions") is not None and c.get("sessions_attended") is not None:
        bits.append(f"{c['sessions_attended']}/{c['total_sessions']} sessions attended")
    if c.get("duration"):
        bits.append(c["duration"])
    if c.get("completion"):
        bits.append(c["completion"].replace("_", " ").capitalize())
    return " · ".join(bits) or KINDS.get(f.kind, "")


# ---------------------------------------------------------------- semantic relevance

_WORD = re.compile(r"[a-z]{3,}")


def _words(text: str) -> set[str]:
    stop = {"and", "the", "for", "with", "services", "service", "work", "works", "provincial"}
    return {w for w in _WORD.findall(text.lower()) if w not in stop}


def semantic(db: Session, match: m.Match) -> dict:
    """Advisory: how well the written description of the opportunity fits the business, by meaning.

    The prompt carries capabilities, sector and the opportunity text only: no name, no ownership,
    no size. It sits beside the rule-based score and never changes it.
    """
    opp = db.get(m.Opportunity, match.opportunity_id)
    profile = db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == match.sme_id))
    scope = [CAPABILITIES.get(i["code"], ("", i["code"]))[1] for i in opp.scope_items]
    opp_text = (
        f"Title: {opp.title}\nSector: {opp.sector}\nProvince: {opp.province}\n"
        f"Scope: {', '.join(scope)}\nDescription: {(opp.description or 'not given')[:1500]}"
    )
    caps = [CAPABILITIES.get(c, ("", c))[1] for c in (profile.capability_codes or [])]
    biz_text = (
        f"Sector: {profile.sector}\nProvince: {profile.province}\n"
        f"Years trading: {profile.years_trading}\nCapabilities: {', '.join(caps) or 'none listed'}"
    )
    h = _hash([opp_text, biz_text])
    hit = _cached(db, "semantic", match.id, h)
    if hit:
        return hit
    # The AI judgement and the embeddings are independent, so they run at the same time
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            client.call,
            prompts.SEMANTIC.format(opportunity=opp_text, business=biz_text),
            prompts.SemanticRelevance,
        )
        vecs = _vectors(db, [(opp.id, _opp_text(opp)), (match.sme_id, _sme_text(profile))])
        result = pending.result()
    if result:
        out = {"source": "ai", **result.model_dump()}
    elif settings.llm_provider == "local":
        out = _local_judgement(opp, profile, caps, scope, vecs, opp.id, match.sme_id)
    else:
        want, have = _words(opp_text), _words(biz_text)
        shared = sorted(want & have)
        out = {
            "source": "keywords",
            "score": round(100 * len(want & have) / max(1, len(want))),
            "matched_themes": shared[:4],
            "concerns": [],
            "rationale": "Keyword overlap only, because the AI reader is not available right now.",
        }
    if vecs:
        out["embedding_similarity"] = emb.calibrated(emb.cosine(vecs[opp.id], vecs[match.sme_id]))
    out["advisory"] = "Shown beside the score. It never changes a score, a gate or a shortlist."
    _store(db, "semantic", match.id, h, out)
    return out


def _local_judgement(opp, profile, caps, scope, vecs, opp_id, sme_id) -> dict:
    """The meaning check with no outside service: scope coverage, sector, and word-vector similarity."""
    have, want = {c.lower() for c in caps}, [s for s in scope]
    covered = [s for s in want if s.lower() in have]
    missing = [s for s in want if s.lower() not in have]
    coverage = len(covered) / max(1, len(want))
    sim = emb.calibrated(emb.cosine(vecs[opp_id], vecs[sme_id])) if vecs else 0
    score = round(60 * coverage + 25 * (profile.sector == opp.sector) + 15 * sim / 100)
    concerns = [f"No {m.lower()} listed" for m in missing[:2]]
    if profile.province != opp.province:
        concerns.append(f"Based in {profile.province}, work is in {opp.province}")
    return {
        "source": "local",
        "score": min(100, score),
        "matched_themes": covered[:4],
        "concerns": concerns[:3],
        "rationale": (
            f"Covers {len(covered)} of {len(want)} areas of the work"
            + (f" ({', '.join(c.lower() for c in covered[:3])})" if covered else "")
            + f", in {'the same' if profile.sector == opp.sector else 'a different'} sector."
        ),
    }


# ---------------------------------------------------------------- profile consistency


def profile_flags(db: Session, org_id: uuid.UUID) -> list[dict]:
    """Deterministic checks for incomplete, inconsistent or doubtful profile information."""
    p = db.scalar(select(m.SmeProfile).where(m.SmeProfile.organisation_id == org_id))
    flags: list[dict] = []
    if p is None:
        return [{"level": "info", "text": "Complete your business profile to start matching."}]
    turnover, largest = float(p.annual_turnover), float(p.largest_past_contract or 0)
    if largest > 3 * turnover:
        flags.append(
            {
                "level": "warn",
                "text": "Your largest past contract is more than three times your annual turnover. "
                "Check both figures, or note that it ran over several years.",
            }
        )
    if p.years_trading == 0 and largest > 0:
        flags.append(
            {"level": "warn", "text": "A past contract is recorded but years trading is 0."}
        )
    if not p.capability_codes:
        flags.append(
            {"level": "warn", "text": "No capabilities are listed, so you cannot be matched."}
        )
    elif any(c.split("-")[0].lower() not in _sector_prefixes(p.sector) for c in p.capability_codes):
        flags.append(
            {
                "level": "info",
                "text": "You list capabilities outside your main sector. That is fine for a "
                "diversified business, but buyers will see it.",
            }
        )
    for d in db.scalars(select(m.Document).where(m.Document.organisation_id == org_id)):
        cred = COMPLIANCE_CATALOGUE.get(d.document_type)
        label = cred.label if cred else d.document_type
        ver = db.scalar(
            select(m.Verification)
            .where(m.Verification.subject_id == d.id)
            .order_by(m.Verification.checked_at.desc())
        )
        if ver is not None and ver.result == "duplicate_hash":
            flags.append(
                {"level": "warn", "text": f"Your {label} matches a file another business uploaded."}
            )
        if d.expiry_date is None:
            flags.append({"level": "info", "text": f"Your {label} has no expiry date recorded."})
    return flags


def _sector_prefixes(sector: str) -> set[str]:
    return {code.split("-")[0].lower() for code, (sec, _) in CAPABILITIES.items() if sec == sector}


# ---------------------------------------------------------------- ecosystem


def _cell(n: int) -> int | str:
    return n if n >= SMALL_CELL else f"under {SMALL_CELL}"


def ecosystem(db: Session) -> dict:
    """Programme-level view for YES. Aggregates only; small counts are suppressed."""
    profiles = list(db.scalars(select(m.SmeProfile)))
    opps = list(db.scalars(select(m.Opportunity)))
    matches = list(db.scalars(select(m.Match)))
    apps = list(db.scalars(select(m.Application)))
    awarded = [a for a in apps if a.awarded_at is not None]
    awarded_value = sum(float(a.awarded_value or 0) for a in awarded)

    sector_supply = Counter(p.sector for p in profiles)
    sector_demand = Counter(o.sector for o in opps)
    sector_value: dict[str, float] = defaultdict(float)
    for o in opps:
        sector_value[o.sector] += float(o.contract_value)
    sectors = sorted(set(sector_supply) | set(sector_demand))
    sector_rows = [
        {
            "sector": s,
            "businesses": _cell(sector_supply[s]),
            "opportunities": _cell(sector_demand[s]),
            "value": sector_value[s],
            "pressure": round(sector_demand[s] / max(1, sector_supply[s]), 2),
        }
        for s in sectors
    ]
    sector_rows.sort(key=lambda r: -r["pressure"])

    prov_supply = Counter(p.province for p in profiles)
    prov_demand = Counter(o.province for o in opps)
    provinces = [
        {
            "province": pr,
            "businesses": _cell(prov_supply[pr]),
            "opportunities": _cell(prov_demand[pr]),
        }
        for pr in sorted(set(prov_supply) | set(prov_demand))
    ]

    demand_codes: Counter = Counter()
    for o in opps:
        for i in o.scope_items:
            demand_codes[i["code"]] += 1
    supply_codes = Counter(c for p in profiles for c in (p.capability_codes or []))
    skills = [
        {
            "code": c,
            "label": CAPABILITIES[c][1],
            "requested": demand_codes[c],
            "businesses": supply_codes[c],
            "shortfall": demand_codes[c] > supply_codes[c],
        }
        for c in CAPABILITIES
        if demand_codes[c] or supply_codes[c]
    ]
    skills.sort(key=lambda r: (-r["requested"], r["businesses"]))
    underserved = [
        {"label": s["label"], "requested": s["requested"], "businesses": s["businesses"]}
        for s in skills
        if s["requested"] >= 1 and s["businesses"] <= 2
    ]

    gaps: Counter = Counter()
    for mt in matches:
        for g in (mt.explanation or {}).get("gaps", []):
            if g.get("mandatory", True):
                gaps[g["label"]] += 1
    quadrants = Counter(mt.quadrant for mt in matches)
    youth = sum(1 for p in profiles if "youth" in (p.ownership or []))
    applied = len({a.match_id for a in apps})
    shortlisted = sum(1 for mt in matches if mt.status == "shortlisted")

    fb = list(db.scalars(select(m.Feedback)))
    live = [f for f in fb if f.status != "removed"]
    crit = {
        k: round(sum(f.ratings.get(k, 0) for f in live) / len(live), 2) if live else None
        for k in CRITERIA
    }
    return {
        "totals": {
            "businesses": len(profiles),
            "youth_owned": youth,
            "opportunities": len(opps),
            "open_value": sum(float(o.contract_value) for o in opps if o.status == "open"),
            "matches": len(matches),
            "applications": applied,
            "awards": len(awarded),
            "awarded_value": awarded_value,
        },
        "funnel": [
            {"stage": "Matched", "count": len(matches)},
            {"stage": "Shortlisted", "count": shortlisted},
            {"stage": "Applied", "count": applied},
            {"stage": "Awarded", "count": len(awarded)},
        ],
        "sectors": sector_rows,
        "provinces": provinces,
        "skills": skills[:10],
        "underserved": underserved,
        "credential_gaps": [{"label": k, "matches_blocked": v} for k, v in gaps.most_common(5)],
        "quadrants": dict(quadrants),
        "quality": {
            "reviews": len(live),
            "criteria": [{"key": k, "label": CRITERIA[k], "average": crit[k]} for k in CRITERIA],
        },
        "inclusion": _inclusion(db),
        "employment": {
            "jobs_potential": round(awarded_value / 1_000_000 * JOBS_PER_R1M),
            "assumption": f"{JOBS_PER_R1M:g} jobs per R1m awarded. This is a placeholder, not a "
            "measured figure; replace it with YES's own coefficient.",
        },
    }


# ---------------------------------------------------------------- semantic search


KIND_WORDS = {
    "procurement": "procurement tender contract supply",
    "grant": "grant funding for businesses",
    "funding": "funding finance loan capital",
    "training": "training course workshop skills learning",
    "support": "business support mentoring accelerator",
}


def _opp_text(o: m.Opportunity) -> str:
    scope = [CAPABILITIES.get(i["code"], ("", i["code"]))[1] for i in o.scope_items]
    return (
        f"{o.title}. Type: {o.kind}, {KIND_WORDS.get(o.kind, '')}. "
        f"Sector {o.sector}, {o.province}. Needs {', '.join(scope)}. "
        f"{(o.description or '')[:1200]}"
    )


def _sme_text(p: m.SmeProfile) -> str:
    caps = [CAPABILITIES.get(c, ("", c))[1] for c in (p.capability_codes or [])]
    return (
        f"Sector {p.sector}, {p.province}. {p.years_trading} years trading. "
        f"Offers {', '.join(caps) or 'nothing listed'}."
    )


def _vectors(
    db: Session, items: list[tuple[uuid.UUID, str]]
) -> dict[uuid.UUID, list[float]] | None:
    """Embeddings for these items, from the cache where the text is unchanged. None if unavailable."""
    found: dict[uuid.UUID, list[float]] = {}
    missing: list[tuple[uuid.UUID, str, str]] = []
    rows = {
        r.subject_id: r
        for r in db.scalars(
            select(m.AiInsight).where(
                m.AiInsight.kind == "embedding", m.AiInsight.subject_id.in_([i for i, _ in items])
            )
        )
    }
    for sid, text in items:
        h = _hash([text, "embedding", emb.DIMENSIONS])
        row = rows.get(sid)
        if row is not None and row.input_hash == h:
            found[sid] = row.payload["v"]
        else:
            missing.append((sid, text, h))
    if missing:
        got = emb.embed([t for _, t, _ in missing], "RETRIEVAL_DOCUMENT")
        if got is None:
            return None
        for (sid, _, h), vec in zip(missing, got, strict=True):
            found[sid] = vec
            row = rows.get(sid)
            if row is None:
                db.add(
                    m.AiInsight(kind="embedding", subject_id=sid, input_hash=h, payload={"v": vec})
                )
            else:
                row.input_hash, row.payload = h, {"v": vec}
        db.commit()
    return found


def _rank(db: Session, query: str, items: list[tuple[uuid.UUID, str]]) -> tuple[str, dict]:
    """Similarity 0-100 for each item against the query. Embeddings if available, else keywords."""
    q = emb.embed([query], "RETRIEVAL_QUERY")
    vecs = _vectors(db, items) if q else None
    if q and vecs:
        return "embeddings", {i: emb.calibrated(emb.cosine(q[0], vecs[i])) for i, _ in items}
    want = _words(query)
    return "keywords", {i: round(100 * len(want & _words(t)) / max(1, len(want))) for i, t in items}


def search_opportunities(db: Session, org_id: uuid.UUID, query: str) -> dict:
    """A business describes what it does or wants; open opportunities come back by meaning, each with
    the rule-based position beside it. Similarity says what to look at, never who is eligible."""
    opps = list(db.scalars(select(m.Opportunity).where(m.Opportunity.status == "open")))
    source, sims = _rank(db, query, [(o.id, _opp_text(o)) for o in opps])
    mine = {
        mt.opportunity_id: mt for mt in db.scalars(select(m.Match).where(m.Match.sme_id == org_id))
    }
    rows = []
    for o in sorted(opps, key=lambda o: -sims[o.id])[:8]:
        mt = mine.get(o.id)
        rows.append(
            {
                "opportunity_id": o.id,
                "title": o.title,
                "kind": o.kind,
                "sector": o.sector,
                "province": o.province,
                "contract_value": float(o.contract_value),
                "similarity": sims[o.id],
                "match": None
                if mt is None
                else {
                    "match_id": mt.id,
                    "quadrant": mt.quadrant,
                    "fit": float(mt.fit_score),
                    "readiness": float(mt.readiness_score),
                },
            }
        )
    return {"source": source, "results": rows}


def search_smes(db: Session, query: str) -> dict:
    """A buyer describes what it needs; businesses that chose to be visible come back by meaning.
    Only sector, location, years and capabilities are compared: no ownership, no size, no name."""
    rows = db.execute(
        select(m.SmeProfile, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.SmeProfile.organisation_id)
        .where(m.SmeProfile.visible_to_corporates.is_(True))
    ).all()
    source, sims = _rank(db, query, [(org.id, _sme_text(p)) for p, org in rows])
    ranked = sorted(rows, key=lambda r: -sims[r[1].id])[:8]
    return {
        "source": source,
        "results": [
            {
                "sme_id": org.id,
                "name": org.name,
                "sector": p.sector,
                "province": p.province,
                "years_trading": p.years_trading,
                "verification_status": org.verification_status,
                "similarity": sims[org.id],
            }
            for p, org in ranked
        ],
    }


def _inclusion(db: Session) -> dict:
    """How many businesses work in their own language, and whether that costs them anything."""
    users = list(
        db.scalars(select(m.User).where(m.User.role == "sme", m.User.deleted_at.is_(None)))
    )
    lang_of = {u.organisation_id: (u.language or "en") for u in users}
    has_profile = {p.organisation_id for p in db.scalars(select(m.SmeProfile))}
    applied: Counter = Counter()
    awarded: Counter = Counter()
    for a in db.scalars(select(m.Application)):
        mt = db.get(m.Match, a.match_id)
        lang = lang_of.get(mt.sme_id) if mt else None
        if lang:
            applied[lang] += 1
            awarded[lang] += a.awarded_at is not None
    voiced = {
        a.user_id for a in db.scalars(select(m.AuditLog).where(m.AuditLog.action == "voice_used"))
    }
    rows = []
    for code, label in LANGUAGES.items():
        mine = [u for u in users if (u.language or "en") == code]
        rows.append(
            {
                "language": code,
                "label": label,
                "reviewed": REVIEWED[code],
                "businesses": len(mine),
                "profile_complete_pct": round(
                    100 * sum(u.organisation_id in has_profile for u in mine) / len(mine)
                )
                if mine
                else None,
                "applied": applied[code],
                "awarded": awarded[code],
            }
        )
    total = len(users)
    home = sum(1 for u in users if (u.language or "en") != "en")
    return {
        "languages": rows,
        "home_language_pct": round(100 * home / total) if total else 0,
        "voice_users": sum(1 for u in users if u.id in voiced),
        "assisted": sum(1 for u in users if u.assisted_by),
        "businesses": total,
        "note": "Language never enters a score. These figures show whether working in your own "
        "language costs you anything at the point of application or award.",
    }
