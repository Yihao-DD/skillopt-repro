"""Split-half selection-generalization replay (zero API, offline).

Answers: does an arm's argmax-on-selection-set margin survive on a held-out
half? Core statistical contracts:
  - deterministic given seed;
  - winner's curse detected: picking argmax among near-tied skills inflates the
    selection-half score above the holdout-half score (gap > 0);
  - a genuinely dominant arm keeps its holdout margin.
"""
from __future__ import annotations

import random

from tools.analyze_selection_generalization import split_half_replay


def _skill(ids, correct_ids):
    s = set(correct_ids)
    return {i: (1 if i in s else 0) for i in ids}


def _near_tied_pool(ids, n_skills=5, per_skill=50, seed=7):
    rng = random.Random(seed)
    return {f"s{j}": _skill(ids, rng.sample(ids, per_skill)) for j in range(n_skills)}


def test_deterministic_given_seed():
    ids = [str(i) for i in range(100)]
    arms = {"arm": _near_tied_pool(ids)}
    a = split_half_replay(arms, n_trials=50, seed=42)
    b = split_half_replay(arms, n_trials=50, seed=42)
    assert a == b


def test_winners_curse_gap_positive_for_near_tied_pool():
    ids = [str(i) for i in range(100)]
    arms = {"arm": _near_tied_pool(ids)}
    res = split_half_replay(arms, n_trials=300, seed=42)
    # argmax on half A among 5 near-tied skills: selection score must exceed
    # the same skill's holdout score on average (selection tax / winner's curse).
    assert res["arm"]["gap_mean"] > 0.01


def test_dominant_arm_margin_survives_holdout():
    ids = [str(i) for i in range(100)]
    rng = random.Random(3)
    weak = _near_tied_pool(ids, seed=11)                       # ~0.50 skills
    strong = {"best": _skill(ids, rng.sample(ids, 70))}        # 0.70 skill
    res = split_half_replay({"weak": weak, "strong": strong}, n_trials=300, seed=42)
    margins = [h2 - h1 for h1, h2 in zip(res["weak"]["holdout"], res["strong"]["holdout"])]
    assert sum(margins) / len(margins) > 0.10                  # real edge survives
    assert res["strong"]["gap_mean"] < res["weak"]["gap_mean"] + 0.05  # single skill: no selection tax
