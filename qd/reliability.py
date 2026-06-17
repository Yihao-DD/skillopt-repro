"""RG-SkillOpt component 1: the D_sel reliability governor.

Pure, dependency-free. Given per-candidate per-item D_sel binary outcomes
(``{candidate_id: [0/1 per item]}``, all candidates sharing the same item order),
it estimates whether D_sel can RELIABLY pick the best candidate, and emits
``allow_width``. It NEVER looks at D_test.

Metrics:
- ``n_sel``: number of D_sel items.
- ``split_half_best_agreement``: over random equal-half splits of the items, the
  fraction where the argmax candidate on half A equals the argmax on half B
  (does the "best" candidate hold up across item subsets?).
- ``bootstrap_prob_best``: over item bootstrap resamples, the fraction where the
  full-data best candidate is still the argmax (stability of the chosen winner).
- ``candidate_margin``: best minus second-best candidate D_sel mean.

Width rule (initial): allow width only when D_sel is big AND reliably ranks
candidates — otherwise a wider beam just lets noise pick the winner.
"""
from __future__ import annotations

import random


def candidate_means(results: dict) -> dict:
    return {c: (sum(v) / len(v) if v else 0.0) for c, v in results.items()}


def _best_on(results: dict, idxs: list) -> str:
    if not idxs:
        idxs = list(range(len(next(iter(results.values())))))
    means = {c: sum(v[i] for i in idxs) / len(idxs) for c, v in results.items()}
    # deterministic tie-break: sort candidate ids first, then argmax
    return max(sorted(means), key=lambda c: means[c])


def best_candidate(results: dict) -> str:
    n = len(next(iter(results.values())))
    return _best_on(results, list(range(n)))


def candidate_margin(results: dict) -> float:
    means = sorted(candidate_means(results).values(), reverse=True)
    if len(means) >= 2:
        return float(means[0] - means[1])
    return float(means[0]) if means else 0.0


def split_half_best_agreement(results: dict, *, n_splits: int = 200, seed: int = 0) -> float:
    n = len(next(iter(results.values()))) if results else 0
    if n < 2 or len(results) < 2:
        return 1.0
    rng = random.Random(seed)
    idx = list(range(n))
    h = n // 2
    agree = 0
    for _ in range(n_splits):
        rng.shuffle(idx)
        if _best_on(results, idx[:h]) == _best_on(results, idx[h: 2 * h]):
            agree += 1
    return agree / n_splits


def bootstrap_prob_best(results: dict, *, n_boot: int = 500, seed: int = 0) -> float:
    n = len(next(iter(results.values()))) if results else 0
    if n < 1 or len(results) < 2:
        return 1.0
    overall = best_candidate(results)
    rng = random.Random(seed)
    idx = list(range(n))
    hits = 0
    for _ in range(n_boot):
        sample = [rng.choice(idx) for _ in range(n)]
        if _best_on(results, sample) == overall:
            hits += 1
    return hits / n_boot


def reliability_metrics(results: dict, *, seed: int = 0) -> dict:
    n = len(next(iter(results.values()))) if results else 0
    return {
        "n_sel": n,
        "split_half_best_agreement": split_half_best_agreement(results, seed=seed),
        "bootstrap_prob_best": bootstrap_prob_best(results, seed=seed + 1),
        "candidate_margin": candidate_margin(results),
    }


def allow_width(
    metrics: dict,
    *,
    min_n_sel: int = 30,
    min_agreement: float = 0.6,
    min_prob_best: float = 0.7,
) -> bool:
    """Allow a wider beam only when D_sel is large enough AND reliably ranks
    candidates. Mirrors the RG-SkillOpt initial rule; tunable thresholds."""
    if metrics["n_sel"] < min_n_sel:
        return False
    if metrics["split_half_best_agreement"] < min_agreement:
        return False
    if metrics["bootstrap_prob_best"] < min_prob_best:
        return False
    return True
