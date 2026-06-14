"""Gate-myopia / stepping-stone latent-value probe (zero API, offline).

Tests the premise behind BOTH the reviewer's QD push and the deep-research
report's Lookahead: SkillOpt's strict-`>` gate selects the val-argmax candidate,
which is MYOPIC — it may discard candidates that generalize better on unseen data.

We cannot test held-out TEST directly (rejected candidates were never test-scored
— see docs/REVIEWER-RESPONSE §Q3/Q5), so we use within-D_sel cross-validation:
split the selection items into a GATE half (the selector sees) and a HOLDOUT half
(unseen), and measure how much held-out value the strict-argmax selector leaves on
the table vs (a) an ORACLE that could pick the holdout-best (ceiling), and (b) an
ACHIEVABLE robust selector (Copeland over gate-half sub-splits).

Compares K=1 (greedy pool) vs K=4 (QD diverse pool): if QD's pool carries MORE
harvestable held-out value that strict selection misses, the QD/Lookahead thesis
has a real target. If the regret is small, or K=4 is no better than K=1, the
premise is weak IN-DISTRIBUTION — cheap evidence against paying for the cure.

CAVEATS (stated, not hidden):
  1. holdout-val is IN-DISTRIBUTION, not the real test set. A positive result here
     is necessary-but-not-sufficient for a test-set win; a NEGATIVE result is strong.
  2. This tests SELECTION over the EXISTING candidate pool, NOT mutation
     stepping-stone CHAINS (those need live runs / lineage logging).
  3. The pools predate the merge_patches faithfulness fix; they reflect the
     candidate distribution the (slightly sub-original) generator produced.

CLI:
  python tools/gate_myopia_probe.py --run-dir runs/full-final-s1
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_selection_generalization import _mean_over, copeland_pick  # noqa: E402


def load_sel_pool(run_dir: str, arm: str) -> dict:
    """Per-candidate D_sel per-item 0/1 from <run>/<arm>/sel/<hash>/results.jsonl."""
    pool = {}
    for p in glob.glob(os.path.join(run_dir, arm, "sel", "*", "results.jsonl")):
        h = os.path.basename(os.path.dirname(p))
        m = {}
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                m[str(r["id"])] = int(float(r.get("hard", 0)) > 0.5)
        if m:
            pool[h] = m
    return pool


def _pct(vals: list, q: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def myopia_regret(arms: dict, *, n_trials: int = 300, n_inner: int = 50, seed: int = 42) -> tuple[dict, list]:
    """Per arm, over random GATE/HOLDOUT splits of the selection items:
      greedy   = argmax over GATE half  (what strict-`>` selection converges to)
      oracle   = argmax over HOLDOUT half (best generalizer in the pool — ceiling)
      copeland = robust pick over GATE-half sub-splits (achievable non-myopic gate)
    all three are then scored on the untouched HOLDOUT half. Deterministic per seed."""
    ids = None
    for pool in arms.values():
        for sk in pool.values():
            ids = set(sk) if ids is None else ids & set(sk)
    if not ids:
        raise ValueError("no common item ids across candidates")
    ids = sorted(ids)
    half = len(ids) // 2
    rng = random.Random(seed)
    raw = {a: {"greedy": [], "oracle": [], "copeland": [], "discard": 0} for a in arms}
    for _ in range(n_trials):
        perm = rng.sample(ids, len(ids))
        gate, hold = perm[:half], perm[half:]
        for a, pool in arms.items():
            greedy = max(sorted(pool), key=lambda k: (_mean_over(pool[k], gate), k))
            oracle = max(sorted(pool), key=lambda k: (_mean_over(pool[k], hold), k))
            cope = copeland_pick(pool, gate, n_splits=n_inner, rng=rng)
            raw[a]["greedy"].append(_mean_over(pool[greedy], hold))
            raw[a]["oracle"].append(_mean_over(pool[oracle], hold))
            raw[a]["copeland"].append(_mean_over(pool[cope], hold))
            if oracle != greedy:
                raw[a]["discard"] += 1
    res = {}
    for a, d in raw.items():
        g = sum(d["greedy"]) / n_trials
        o = sum(d["oracle"]) / n_trials
        c = sum(d["copeland"]) / n_trials
        cope_gain_trials = [ct - gt for ct, gt in zip(d["copeland"], d["greedy"])]
        res[a] = {
            "pool": len(arms[a]),
            "greedy_holdout": round(g, 4),
            "oracle_holdout": round(o, 4),
            "copeland_holdout": round(c, 4),
            "oracle_regret": round(o - g, 4),       # ceiling: latent held-out value strict gate misses
            "copeland_gain": round(c - g, 4),       # ACHIEVABLE non-myopic gain over strict argmax
            "copeland_gain_ci95": [round(_pct(cope_gain_trials, 0.025), 4),
                                   round(_pct(cope_gain_trials, 0.975), 4)],
            "discard_rate": round(d["discard"] / n_trials, 3),  # how often gate-best != holdout-best
            "_greedy": d["greedy"], "_copeland": d["copeland"], "_oracle": d["oracle"],
        }
    return res, ids


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate-myopia latent-value probe over cached D_sel rollouts")
    ap.add_argument("--run-dir", required=True, help="e.g. runs/full-final-s1")
    ap.add_argument("--arms", default="k1,k4")
    ap.add_argument("--n-trials", type=int, default=300)
    ap.add_argument("--n-inner", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="docs/GATE-MYOPIA-probe.json")
    args = ap.parse_args()

    arms = {}
    for a in args.arms.split(","):
        pool = load_sel_pool(args.run_dir, a)
        if pool:
            arms[a] = pool
        else:
            print(f"warn: arm {a} has no sel/*/results.jsonl — skipped")
    if not arms:
        raise SystemExit("no arms loaded")

    res, ids = myopia_regret(arms, n_trials=args.n_trials, n_inner=args.n_inner, seed=args.seed)
    print(f"run={args.run_dir}  |D_sel|={len(ids)}  n_trials={args.n_trials}  seed={args.seed}")
    print(f"{'arm':>5} {'pool':>5} {'greedy':>7} {'oracle':>7} {'copel':>7} "
          f"{'regret':>7} {'cope_gain':>10} {'discard':>8}")
    for a, r in res.items():
        print(f"{a:>5} {r['pool']:>5} {r['greedy_holdout']:>7.4f} {r['oracle_holdout']:>7.4f} "
              f"{r['copeland_holdout']:>7.4f} {r['oracle_regret']:>+7.4f} "
              f"{r['copeland_gain']:>+10.4f} {r['discard_rate']:>8.0%}")

    # cross-arm: does QD's pool carry MORE harvestable held-out value than greedy's pool?
    verdict = {}
    if "k1" in res and "k4" in res:
        k1, k4 = res["k1"], res["k4"]
        oracle_marg = [o4 - o1 for o1, o4 in zip(k1["_oracle"], k4["_oracle"])]
        greedy_marg = [g4 - g1 for g1, g4 in zip(k1["_greedy"], k4["_greedy"])]
        verdict = {
            "k4_oracle_regret": k4["oracle_regret"],
            "k1_oracle_regret": k1["oracle_regret"],
            "k4_copeland_gain": k4["copeland_gain"],
            "k1_copeland_gain": k1["copeland_gain"],
            "k4_oracle_holdout_advantage_over_k1": round(sum(oracle_marg) / len(oracle_marg), 4),
            "k4_greedy_holdout_advantage_over_k1": round(sum(greedy_marg) / len(greedy_marg), 4),
            "robust_gate_beats_strict_either_arm": (k1["copeland_gain"] > 0) or (k4["copeland_gain"] > 0),
            "qd_pool_has_more_latent_value": (k4["oracle_regret"] > k1["oracle_regret"] + 0.01)
            and (sum(oracle_marg) / len(oracle_marg) > 0.01),
        }
        print()
        print(f"  oracle held-out (best generalizer in pool): K4-K1 = {verdict['k4_oracle_holdout_advantage_over_k1']:+.4f}")
        print(f"  greedy held-out (strict-argmax pick):       K4-K1 = {verdict['k4_greedy_holdout_advantage_over_k1']:+.4f}")
        print(f"  robust(Copeland) gate beats strict argmax?  k1={k1['copeland_gain']:+.4f}{tuple(k1['copeland_gain_ci95'])}  "
              f"k4={k4['copeland_gain']:+.4f}{tuple(k4['copeland_gain_ci95'])}")
        print(f"  VERDICT qd_pool_has_more_latent_value = {verdict['qd_pool_has_more_latent_value']}")

    out = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in res.items()}
    payload = {"run": args.run_dir, "n_sel_items": len(ids), "n_trials": args.n_trials,
               "seed": args.seed, "arms": out, "verdict": verdict,
               "caveats": ["holdout-val is in-distribution, NOT test",
                           "tests SELECTION over existing pool, NOT mutation stepping-stone chains",
                           "pools predate the merge_patches fix"]}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
