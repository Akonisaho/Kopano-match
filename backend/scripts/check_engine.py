"""Score the seed data and print a table. `--assert` turns the planted cases into CI checks.

Run from backend/:  python scripts/check_engine.py [--assert]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.runner import consortium_for, match_all  # noqa: E402
from app.evaluation import scenario_checks  # noqa: E402
from app.seed_data import build_seed  # noqa: E402


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

    for msg, ok in scenario_checks(smes, opps, results):
        if not ok:
            failures.append(msg)

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
