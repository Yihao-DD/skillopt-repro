"""Split-half selection-generalization replay (zero API, offline).

Question (operator's hypothesis): our reported arm "best" scores are argmax on
the SAME item set the gate optimized on (selection == report set in the current
harness). How much of each arm's margin survives when the skill is CHOSEN on
one random half and SCORED on the other (winner's curse / selection tax)?

Uses the per-candidate rollout outcomes already on disk
(``runs/<run>/<arm>/<hash>/results.jsonl``) — every number was already paid for.

Caveat (stated, not hidden): the candidate POOL itself was generated under
full-set gate feedback; this replay isolates the SELECTION step only.

CLI:
  python tools/analyze_selection_generalization.py --run-dir runs/full-dpsk-rcv-full
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random


def _mean_over(skill: dict, ids) -> float:
    return sum(skill[i] for i in ids) / len(ids)


def split_half_replay(arms: dict, *, n_trials: int = 200, seed: int = 42) -> dict:
    """For each trial: pick each arm's argmax on a random half (selection),
    score that pick on the other half (holdout).

    ``arms``: arm_name -> {skill_key -> {item_id -> 0/1}}.
    Returns per arm: per-trial selection/holdout lists, their means, the
    selection-tax ``gap_mean``, and ``stability`` (how often the half-set pick
    equals the full-set argmax). Deterministic for a given seed.
    """
    ids = None
    for pool in arms.values():
        for sk in pool.values():
            ids = set(sk) if ids is None else ids & set(sk)
    if not ids:
        raise ValueError("no common item ids across skills")
    ids = sorted(ids)
    half = len(ids) // 2
    rng = random.Random(seed)
    full_best = {arm: max(pool, key=lambda k: (_mean_over(pool[k], ids), k)) for arm, pool in arms.items()}
    raw = {arm: {"selection": [], "holdout": [], "stable": 0} for arm in arms}
    for _ in range(n_trials):
        perm = rng.sample(ids, len(ids))
        a_half, b_half = perm[:half], perm[half:]
        for arm, pool in arms.items():
            best = max(pool, key=lambda k: (_mean_over(pool[k], a_half), k))
            raw[arm]["selection"].append(_mean_over(pool[best], a_half))
            raw[arm]["holdout"].append(_mean_over(pool[best], b_half))
            if best == full_best[arm]:
                raw[arm]["stable"] += 1
    res = {}
    for arm, d in raw.items():
        sel_m = sum(d["selection"]) / n_trials
        hold_m = sum(d["holdout"]) / n_trials
        res[arm] = {
            "selection": d["selection"],
            "holdout": d["holdout"],
            "selection_mean": round(sel_m, 6),
            "holdout_mean": round(hold_m, 6),
            "gap_mean": round(sel_m - hold_m, 6),
            "stability": round(d["stable"] / n_trials, 4),
            "full_best": full_best[arm],
            "pool_size": len(arms[arm]),
        }
    return res


def copeland_pick(pool: dict, ids: list, *, n_splits: int = 100, rng: random.Random) -> str:
    """Robust selection: the candidate that wins the most pairwise half-split
    duels (Copeland) instead of the raw argmax. Ties break by full-ids mean,
    then key — deterministic given the rng state."""
    keys = sorted(pool)
    if len(keys) == 1:
        return keys[0]
    half = len(ids) // 2
    wins = {k: 0.0 for k in keys}
    for _ in range(n_splits):
        a_half = rng.sample(ids, half)
        scores = {k: _mean_over(pool[k], a_half) for k in keys}
        for i, ki in enumerate(keys):
            for kj in keys[i + 1:]:
                if scores[ki] > scores[kj]:
                    wins[ki] += 1
                elif scores[kj] > scores[ki]:
                    wins[kj] += 1
                else:
                    wins[ki] += 0.5
                    wins[kj] += 0.5
    return max(keys, key=lambda k: (wins[k], _mean_over(pool[k], ids), k))


def robust_pick_preview(arms: dict, *, n_trials: int = 200, n_inner: int = 100, seed: int = 42) -> dict:
    """Nested split preview of the robust-selection rule (Z1 / M1 preview).

    Outer trial: split ids into Sel/Hold halves. On the Sel half ONLY, pick the
    final skill two ways — plain argmax vs Copeland over sub-splits of Sel —
    then score both picks on the untouched Hold half. Equal information for
    both rules; the Hold delta is the unbiased preview of the robust rule."""
    ids = None
    for pool in arms.values():
        for sk in pool.values():
            ids = set(sk) if ids is None else ids & set(sk)
    if not ids:
        raise ValueError("no common item ids across skills")
    ids = sorted(ids)
    half = len(ids) // 2
    rng = random.Random(seed)
    raw = {arm: {"argmax_hold": [], "copeland_hold": [], "differ": 0} for arm in arms}
    for _ in range(n_trials):
        perm = rng.sample(ids, len(ids))
        sel, hold = perm[:half], perm[half:]
        for arm, pool in arms.items():
            am = max(sorted(pool), key=lambda k: (_mean_over(pool[k], sel), k))
            cp = copeland_pick(pool, sel, n_splits=n_inner, rng=rng)
            raw[arm]["argmax_hold"].append(_mean_over(pool[am], hold))
            raw[arm]["copeland_hold"].append(_mean_over(pool[cp], hold))
            if am != cp:
                raw[arm]["differ"] += 1
    res = {}
    for arm, d in raw.items():
        am_m = sum(d["argmax_hold"]) / n_trials
        cp_m = sum(d["copeland_hold"]) / n_trials
        res[arm] = {
            "argmax_hold": d["argmax_hold"],
            "copeland_hold": d["copeland_hold"],
            "argmax_hold_mean": round(am_m, 6),
            "copeland_hold_mean": round(cp_m, 6),
            "delta_mean": round(cp_m - am_m, 6),
            "differ_rate": round(d["differ"] / n_trials, 4),
        }
    return res


def _load_pool(arm_dir: str) -> dict:
    pool = {}
    for p in glob.glob(os.path.join(arm_dir, "*", "results.jsonl")):
        h = os.path.basename(os.path.dirname(p))
        m = {}
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                m[str(r["id"])] = int(float(r.get("hard", 0)) > 0.5)
        if m:
            pool[h] = m
    return pool


def _pct(sorted_vals: list, q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> None:
    ap = argparse.ArgumentParser(description="Split-half selection-generalization replay over cached rollouts")
    ap.add_argument("--run-dir", required=True, help="e.g. runs/full-dpsk-rcv-full")
    ap.add_argument("--arms", default="k1,k4,k4rcv")
    ap.add_argument("--n-trials", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--robust-preview", action="store_true",
                    help="Z1: nested-split preview of Copeland robust selection vs argmax (M1 预览)")
    args = ap.parse_args()

    arms = {}
    for a in args.arms.split(","):
        pool = _load_pool(os.path.join(args.run_dir, a))
        if pool:
            arms[a] = pool
        else:
            print(f"warn: arm {a} has no results.jsonl — skipped")
    res = split_half_replay(arms, n_trials=args.n_trials, seed=args.seed)

    print(f"n_trials={args.n_trials}  seed={args.seed}")
    for arm, r in res.items():
        print(f"[{arm}] pool={r['pool_size']}  selection={r['selection_mean']:.4f}  "
              f"holdout={r['holdout_mean']:.4f}  gap={r['gap_mean']:+.4f}  "
              f"stability={r['stability']:.0%}  full_best={r['full_best']}")
    if args.robust_preview:
        prev = robust_pick_preview(arms, n_trials=args.n_trials, n_inner=100, seed=args.seed)
        for arm, r in prev.items():
            print(f"[robust-preview {arm}] argmax_hold={r['argmax_hold_mean']:.4f}  "
                  f"copeland_hold={r['copeland_hold_mean']:.4f}  delta={r['delta_mean']:+.4f}  "
                  f"picks_differ={r['differ_rate']:.0%}")
    names = list(res)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            diffs = sorted(hb - ha for ha, hb in zip(res[a]["holdout"], res[b]["holdout"]))
            mean = sum(diffs) / len(diffs)
            frac_pos = sum(1 for d in diffs if d > 0) / len(diffs)
            print(f"holdout margin {b}-{a}: mean={mean:+.4f}  "
                  f"95%=[{_pct(diffs, 0.025):+.4f},{_pct(diffs, 0.975):+.4f}]  P(>0)={frac_pos:.0%}")


if __name__ == "__main__":
    main()
