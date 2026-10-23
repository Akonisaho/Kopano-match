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

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE
from .llm import client, prompts

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


def performance(db: Session, sme_org_id: uuid.UUID, with_summary: bool = True) -> dict:
    rows = [
        f
        for f in db.scalars(
            select(m.Feedback)
            .where(m.Feedback.sme_id == sme_org_id)
            .order_by(m.Feedback.created_at.desc())
        )
        if _counted(f)
    ]
    n = len(rows)
    avg = {k: round(sum(f.ratings.get(k, 0) for f in rows) / n, 2) if n else None for k in CRITERIA}
    scored = [v for v in avg.values() if v is not None]
    out = {
        "reviews": n,
        "reliable": n >= RELIABLE_AFTER,
        "overall": round(sum(scored) / len(scored), 2) if scored else None,
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
    result = client.call(
        prompts.SEMANTIC.format(opportunity=opp_text, business=biz_text), prompts.SemanticRelevance
    )
    if result:
        out = {"source": "ai", **result.model_dump()}
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
    out["advisory"] = "Shown beside the score. It never changes a score, a gate or a shortlist."
    _store(db, "semantic", match.id, h, out)
    return out


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
        "employment": {
            "jobs_potential": round(awarded_value / 1_000_000 * JOBS_PER_R1M),
            "assumption": f"{JOBS_PER_R1M:g} jobs per R1m awarded. This is a placeholder, not a "
            "measured figure; replace it with YES's own coefficient.",
        },
    }
