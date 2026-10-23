"""Print the engine evaluation: benchmark, determinism and the fairness audit.

Run from backend/:  python scripts/evaluate_engine.py [--assert]
`--assert` fails when the engine is not deterministic, ownership changes a neutral score, or the
engine does not beat the baselines. It runs in CI so the claims on the Responsible AI page stay true.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation import evaluate  # noqa: E402


def main(check: bool) -> int:
    r = evaluate()
    b, f = r["benchmark"], r["fairness"]
    print(f"Model {r['model_version']}  data: {r['data']['source']}")
    print(f"\nScenario checks: {r['scenarios']['passed']}/{r['scenarios']['total']}")
    for i in r["scenarios"]["items"]:
        print(f"  {'ok  ' if i['ok'] else 'FAIL'} {i['name']}")
    print(f"\nRanking vs rubric ({b['opportunities']} opportunities, {b['businesses']} businesses)")
    for m in b["methods"]:
        print(
            f"  {m['method']:<34} NDCG@5 {m['ndcg_at_5']:.3f}   precision@3 {m['precision_at_3']:.3f}"
        )
    print(
        f"  relevant pairs excluded by hard gates: {b['relevant_excluded_by_gates']} of {b['relevant_pairs']}"
    )
    print(
        f"\nDeterminism: identical={r['determinism']['identical']} fingerprint {r['determinism']['fingerprint']}"
    )
    print(
        f"\nFairness: {f['scores_changed_by_ownership']} of {f['counterfactual_pairs']} neutral pairs changed when ownership was flipped"
    )
    print(
        f"  buyer transformation preference moves fit by at most {f['disclosed_max_fit_effect']} points"
    )
    for d in f["disparate_impact"]:
        print(
            f"  {d['attribute']:<20} kept-rate ratio {d['ratio']}  {'within' if d['within_four_fifths'] else 'OUTSIDE'} the four-fifths rule"
        )
    if not check:
        return 0
    failures = []
    if r["scenarios"]["passed"] != r["scenarios"]["total"]:
        failures.append("a planted scenario failed")
    if not r["determinism"]["identical"]:
        failures.append("matching is not deterministic")
    if f["scores_changed_by_ownership"]:
        failures.append("ownership changed a score on a neutral opportunity")
    engine, fit_only = b["methods"][0], b["methods"][1]
    for m in b["methods"][2:]:
        if engine["ndcg_at_5"] <= m["ndcg_at_5"]:
            failures.append(f"engine NDCG@5 does not beat '{m['method']}'")
    if engine["ndcg_at_5"] < fit_only["ndcg_at_5"] - 0.02:
        failures.append("engine NDCG@5 fell more than 0.02 below fit-only ranking")
    if engine["precision_at_3"] < fit_only["precision_at_3"]:
        failures.append("engine precision@3 fell below fit-only ranking")
    print()
    if failures:
        print("EVALUATION FAILED")
        for x in failures:
            print("  -", x)
        return 1
    print("evaluation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main("--assert" in sys.argv))
