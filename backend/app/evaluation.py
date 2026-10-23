"""Reproducible evaluation of the matching engine: accuracy, determinism and a fairness audit.

Pure and database-free. It runs on the seeded synthetic data (`seed_data.build_seed`, fixed seed),
so anyone can rerun it and get the same numbers: `python scripts/evaluate_engine.py`.

Be honest about what this is. The relevance labels come from a simple independent rubric, not from
human reviewers or real award outcomes, and the data is synthetic. It shows the engine ranks sensibly
and behaves consistently. It does not prove real-world accuracy; that needs YES-reviewed outcomes.
"""

import hashlib
import json
import random
from dataclasses import replace
from functools import lru_cache
from math import log2

from .engine.runner import consortium_for, match_all
from .engine.scoring import THRESHOLD, covered_codes
from .engine.types import MODEL_VERSION, SME, Gate, Opportunity, RequirementType
from .seed_data import PLANTED, build_seed

TOP_K_NDCG = 5
TOP_K_PRECISION = 3
GROUPS = {
    "youth-owned": lambda s: "youth" in s.ownership,
    "black-owned": lambda s: "black" in s.ownership,
    "black women-owned": lambda s: "black_women" in s.ownership,
}

RUBRIC = (
    "Relevance 3 if the business covers the full scope in the right sector, 2 if it covers at least "
    "half the scope value, 1 if it covers any of it, 0 otherwise. Scope coverage only: documents, "
    "capacity and ownership are deliberately left out so the rubric is not the engine marking itself."
)

LIMITATIONS = [
    "The data is synthetic and small (40 businesses, 6 opportunities). Results show consistency, not real-world accuracy.",
    "Relevance labels come from a simple rubric, not human reviewers or real award outcomes.",
    "Credential costs and turnaround times are placeholders until verified with each issuer.",
    "Ownership affects a score only when a buyer sets a transformation preference. That is the buyer's criterion, capped at 10 fit points, and is disclosed on every match.",
    "Document checks use mock registry, tax and identity sources in this demo and are labelled as mocks in the app.",
    "The AI reads documents and drafts text. It never sets a score, a gate or a shortlist. A person decides.",
    "Feedback averages from fewer than three reviews are shown as an early signal, not a rating.",
]

HUMAN_OVERSIGHT = [
    "Scores come from deterministic rules. There is no model in the scoring path, so every number can be traced.",
    "Every match shows its components, gaps and risk flags. Nothing is hidden behind one number.",
    "A buyer shortlists and awards. The platform ranks; it never decides.",
    "AI drafts (document reading, tender requirements, summaries) are shown for review and saved only after a person confirms.",
    "Flagged matches and verifications go to a human reviewer. Each decision is written to an append-only audit log.",
    "A business can respond to or dispute any feedback, and a reviewer resolves disputes.",
]


def _signature(r) -> tuple:
    return (r.gate.value, r.fit, r.readiness, r.quadrant)


def _relevance(opp: Opportunity, sme: SME) -> int:
    total = sum(i.value for i in opp.scope_items) or 1
    covered = sum(i.value for i in opp.scope_items if i.code in sme.capability_codes) / total
    if covered >= 0.99 and sme.sector == opp.sector:
        return 3
    if covered >= 0.5:
        return 2
    return 1 if covered > 0 else 0


def _dcg(gains: list[int]) -> float:
    return sum(g / log2(i + 2) for i, g in enumerate(gains))


def _ndcg(ranked_ids: list[str], rel: dict[str, int], k: int) -> float:
    ideal = _dcg(sorted(rel.values(), reverse=True)[:k])
    if ideal == 0:
        return 1.0
    return _dcg([rel.get(i, 0) for i in ranked_ids[:k]]) / ideal


def _precision(ranked_ids: list[str], rel: dict[str, int], k: int) -> float:
    top = ranked_ids[:k]
    return sum(1 for i in top if rel.get(i, 0) >= 2) / k if top else 0.0


def scenario_checks(smes, opps, results) -> list[tuple[str, bool]]:
    """The planted cases: each is a behaviour the product promises. Used by CI and the report."""
    out: list[tuple[str, bool]] = []

    def get(opp_id: str, sme_id: str):
        return next((r for r in results[opp_id] if r.sme_id == sme_id), None)

    def check(msg: str, ok) -> None:
        out.append((msg, bool(ok)))

    r = get("opp-1", PLANTED["coachable"])
    check(
        "coachable: high fit, readiness under 60",
        r and r.fit > THRESHOLD and r.readiness < THRESHOLD,
    )
    check(
        "coachable: two dated gaps with an issuer",
        r and len(r.gaps) == 2 and all(g.days and g.issuer for g in r.gaps),
    )
    check(
        "coachable: a gap also unlocks other matches", r and any(g.also_unlocks > 0 for g in r.gaps)
    )
    r = get("opp-1", PLANTED["expired_only"])
    check(
        "expired affidavit: one remediable gap",
        r and r.gate == Gate.REMEDIABLE and len(r.gaps) == 1 and r.gaps[0].credential == "BBBEE",
    )
    r = get("opp-1", PLANTED["overtrading"])
    check("overtrading flagged on a high-fit match", r and r.risk.overtrading and r.fit > THRESHOLD)
    for sid in PLANTED["ready"]:
        r = get("opp-1", sid)
        check(f"{sid}: award now", r and r.quadrant == "award_now" and r.gate == Gate.PASS)
    check(
        "the opportunity chart spans at least three quadrants",
        len({r.quadrant for r in results["opp-1"]}) >= 3,
    )
    opp4 = next(o for o in opps if o.id == "opp-4")
    scope = {i.code for i in opp4.scope_items}
    check(
        "agri-hub: no single business covers the scope",
        all(covered_codes(opp4, s) != scope for s in smes),
    )
    c = consortium_for(opp4, smes, results["opp-4"])
    check(
        "agri-hub: a consortium covers 100% and names a lead",
        c is not None and c.coverage_pct == 100.0 and c.lead_sme_id in c.member_sme_ids,
    )
    return out


def _benchmark(smes, opps, results) -> dict:
    rng = random.Random(7)
    methods: dict[str, list[tuple[float, float]]] = {
        "Kopano engine (overall)": [],
        "Fit score only": [],
        "Sector match only": [],
        "Random order (average of 200)": [],
    }
    excluded_relevant = 0
    relevant_total = 0
    for o in opps:
        rel = {s.id: _relevance(o, s) for s in smes}
        relevant_total += sum(1 for v in rel.values() if v >= 2)
        kept = results[o.id]
        kept_ids = {r.sme_id for r in kept}
        excluded_relevant += sum(1 for sid, v in rel.items() if v >= 2 and sid not in kept_ids)
        orderings = {
            "Kopano engine (overall)": [r.sme_id for r in kept],
            "Fit score only": [r.sme_id for r in sorted(kept, key=lambda r: r.fit, reverse=True)],
            "Sector match only": [
                s.id for s in sorted(smes, key=lambda s: (s.sector != o.sector, s.id))
            ],
        }
        for name, ids in orderings.items():
            methods[name].append(
                (_ndcg(ids, rel, TOP_K_NDCG), _precision(ids, rel, TOP_K_PRECISION))
            )
        trials = []
        for _ in range(200):
            ids = [s.id for s in smes]
            rng.shuffle(ids)
            trials.append((_ndcg(ids, rel, TOP_K_NDCG), _precision(ids, rel, TOP_K_PRECISION)))
        methods["Random order (average of 200)"].append(
            (sum(t[0] for t in trials) / 200, sum(t[1] for t in trials) / 200)
        )
    rows = [
        {
            "method": name,
            "ndcg_at_5": round(sum(v[0] for v in vals) / len(vals), 3),
            "precision_at_3": round(sum(v[1] for v in vals) / len(vals), 3),
        }
        for name, vals in methods.items()
    ]
    return {
        "opportunities": len(opps),
        "businesses": len(smes),
        "rubric": RUBRIC,
        "methods": rows,
        "relevant_pairs": relevant_total,
        "relevant_excluded_by_gates": excluded_relevant,
    }


def _determinism(smes, opps) -> dict:
    def run() -> str:
        blob = [
            [
                (r.sme_id, r.gate.value, r.fit, r.readiness, r.overall, r.quadrant)
                for r in match_all(o, smes, opps)
            ]
            for o in opps
        ]
        return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()

    a, b = run(), run()
    return {"identical": a == b, "fingerprint": a[:16], "runs": 2}


def _fairness(smes, opps) -> dict:
    neutral = [
        replace(
            o,
            transformation_gap=[],
            requirements=[r for r in o.requirements if r.type != RequirementType.OWNERSHIP],
        )
        for o in opps
    ]
    pairs = changed = 0
    for o in neutral:
        for s in smes:
            flipped = replace(s, ownership=[] if s.ownership else ["youth", "black", "black_women"])
            before = match_all(o, [s], neutral)
            after = match_all(o, [flipped], neutral)
            pairs += 1
            if [_signature(r) for r in before] != [_signature(r) for r in after]:
                changed += 1

    # The disclosed effect: what a buyer's own transformation preference can move
    max_delta = 0.0
    for o in opps:
        if not o.transformation_gap:
            continue
        plain = replace(o, transformation_gap=[])
        for s in smes:
            a = match_all(o, [s], opps)
            b = match_all(plain, [s], opps)
            if a and b:
                max_delta = max(max_delta, abs(a[0].fit - b[0].fit))

    results = {o.id: match_all(o, smes, opps) for o in opps}
    groups = []
    for name, test in GROUPS.items():
        for label, members in (
            (name, [s for s in smes if test(s)]),
            (f"not {name}", [s for s in smes if not test(s)]),
        ):
            if not members:
                continue
            total = len(members) * len(opps)
            kept = ready = 0
            for o in opps:
                by = {r.sme_id: r for r in results[o.id]}
                for s in members:
                    r = by.get(s.id)
                    if r:
                        kept += 1
                        ready += r.quadrant == "award_now"
            groups.append(
                {
                    "group": label,
                    "businesses": len(members),
                    "kept_rate": round(kept / total, 3),
                    "award_ready_rate": round(ready / total, 3),
                }
            )
    ratios = []
    for name in GROUPS:
        a = next((g for g in groups if g["group"] == name), None)
        b = next((g for g in groups if g["group"] == f"not {name}"), None)
        if a and b and max(a["kept_rate"], b["kept_rate"]) > 0:
            ratio = min(a["kept_rate"], b["kept_rate"]) / max(a["kept_rate"], b["kept_rate"])
            ratios.append(
                {"attribute": name, "ratio": round(ratio, 2), "within_four_fifths": ratio >= 0.8}
            )
    return {
        "counterfactual_pairs": pairs,
        "scores_changed_by_ownership": changed,
        "disclosed_max_fit_effect": round(max_delta, 1),
        "groups": groups,
        "disparate_impact": ratios,
        "note": (
            "A ratio under 0.8 is flagged, not hidden. In this synthetic cohort the youth-owned gap "
            "comes from the sector mix of the 40 businesses and one buyer-set ownership requirement, "
            "not from a scoring rule. With real data this check should be rerun and any gap reviewed."
        ),
    }


@lru_cache(maxsize=1)
def evaluate() -> dict:
    smes, opps, _ = build_seed()
    results = {o.id: match_all(o, smes, opps) for o in opps}
    scenarios = scenario_checks(smes, opps, results)
    return {
        "model_version": MODEL_VERSION,
        "data": {
            "source": "Synthetic, generated by seed_data.py with a fixed seed",
            "businesses": len(smes),
            "opportunities": len(opps),
            "personal_data": False,
        },
        "scenarios": {
            "passed": sum(1 for _, ok in scenarios if ok),
            "total": len(scenarios),
            "items": [{"name": n, "ok": ok} for n, ok in scenarios],
        },
        "benchmark": _benchmark(smes, opps, results),
        "determinism": _determinism(smes, opps),
        "fairness": _fairness(smes, opps),
        "limitations": LIMITATIONS,
        "human_oversight": HUMAN_OVERSIGHT,
    }
