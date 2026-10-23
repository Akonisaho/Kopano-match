"""Score the seed data and print a table. `--assert` turns the planted cases into CI checks.

Run from backend/:  python scripts/check_engine.py [--assert]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.runner import consortium_for, match_all  # noqa: E402
from app.engine.scoring import THRESHOLD, covered_codes  # noqa: E402
from app.engine.types import Gate  # noqa: E402
from app.seed_data import PLANTED, build_seed  # noqa: E402


def main(check: bool) -> int:
    smes, opps, _ = build_seed()
    by_id = {s.id: s for s in smes}
    results = {o.id: match_all(o, smes, opps) for o in opps}
    failures: list[str] = []

    for o in opps:
        print(
            f"\n{o.id}  {o.title}  R{o.contract_value / 1e6:.1f}m  "
            f"{len(results[o.id])}/{len(smes)} kept"
        )
        print(
            f"  {'sme':<28}{'fit':>6}{'ready':>7}{'overall':>8}  {'quadrant':<15}{'gate':<11}flags"
        )
        for r in results[o.id]:
            flags = [
                f
                for f, on in (
                    ("OVERTRADING", r.risk.overtrading),
                    ("CONCENTRATION", r.risk.concentration),
                )
                if on
            ]
            gaps = ",".join(f"{g.credential}:{g.days}d/R{g.cost_zar}" for g in r.gaps)
            print(
                f"  {by_id[r.sme_id].name:<28}{r.fit:>6}{r.readiness:>7}{r.overall:>8}  "
                f"{r.quadrant:<15}{r.gate.value:<11}{' '.join(flags)} {gaps}"
            )
        c = consortium_for(o, smes, results[o.id])
        if c:
            print(
                f"  consortium: {[by_id[m].name for m in c.member_sme_ids]} "
                f"lead={by_id[c.lead_sme_id].name} covers {c.coverage_pct}%"
            )

    if not check:
        return 0

    def get(opp_id: str, sme_id: str):
        return next((r for r in results[opp_id] if r.sme_id == sme_id), None)

    def expect(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    r = get("opp-1", PLANTED["coachable"])
    expect(r and r.fit > THRESHOLD and r.readiness < THRESHOLD, "coachable: fit>60, readiness<60")
    expect(
        r and len(r.gaps) == 2 and all(g.days and g.issuer for g in r.gaps),
        "coachable: two dated gaps with issuer",
    )
    expect(r and any(g.also_unlocks > 0 for g in r.gaps), "coachable: a gap has also_unlocks>0")

    r = get("opp-1", PLANTED["expired_only"])
    expect(
        r and r.gate == Gate.REMEDIABLE and len(r.gaps) == 1 and r.gaps[0].credential == "BBBEE",
        "expired_only: one remediable BBBEE gap",
    )

    r = get("opp-1", PLANTED["overtrading"])
    expect(r and r.risk.overtrading and r.fit > THRESHOLD, "overtrading flag on a high-fit match")

    for sid in PLANTED["ready"]:
        r = get("opp-1", sid)
        expect(r and r.quadrant == "award_now" and r.gate == Gate.PASS, f"{sid}: award_now")

    quads = {r.quadrant for r in results["opp-1"]}
    expect(len(quads) >= 3, f"opp-1 chart spans >=3 quadrants (got {sorted(quads)})")

    opp4 = next(o for o in opps if o.id == "opp-4")
    expect(
        all(covered_codes(opp4, s) != {i.code for i in opp4.scope_items} for s in smes),
        "opp-4: no single SME covers the scope",
    )
    c = consortium_for(opp4, smes, results["opp-4"])
    expect(
        c is not None and c.coverage_pct == 100.0 and c.lead_sme_id in c.member_sme_ids,
        "opp-4: consortium covers 100% and names a lead",
    )

    print()
    if failures:
        print("ENGINE CHECK FAILED")
        for f in failures:
            print("  -", f)
        return 1
    print("engine check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main("--assert" in sys.argv))
