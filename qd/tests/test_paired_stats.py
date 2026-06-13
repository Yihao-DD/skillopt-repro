"""T015 — paired statistical hardening for returned run packages (zero API).

Tests the core stats used to judge whether a small per-task margin (e.g. venus
+6 tasks at N=280) is signal or noise: exact McNemar on the disagreement pairs
and a seeded paired bootstrap CI on the mean difference. Synthetic data only.
"""
from __future__ import annotations

import json

from tools.analyze_returned_stats import (
    load_per_item,
    mcnemar_exact,
    paired_bootstrap_ci,
    paired_from_records,
    pooled_mcnemar,
)


def test_mcnemar_no_disagreement_is_p_one():
    assert mcnemar_exact(0, 0) == 1.0


def test_mcnemar_exact_known_value_one_sided_sweep():
    # b=6, c=0 -> two-sided exact p = 2 * C(6,0)/2^6 = 0.03125
    assert abs(mcnemar_exact(6, 0) - 0.03125) < 1e-12


def test_mcnemar_p_capped_at_one():
    assert mcnemar_exact(3, 3) == 1.0


def test_six_task_margin_at_n280_is_not_significant_alone():
    # venus-shaped scenario: net +6 tasks out of 280 with disagreements 4 vs 10
    # -> exact McNemar p ≈ 0.18: a single run of this size CANNOT settle the claim.
    p = mcnemar_exact(4, 10)
    assert p > 0.05


def test_bootstrap_ci_deterministic_with_seed():
    xs = [0, 1, 0, 1, 0, 0, 1, 0]
    ys = [1, 1, 0, 1, 1, 0, 1, 0]
    a = paired_bootstrap_ci(xs, ys, n_boot=500, seed=42)
    b = paired_bootstrap_ci(xs, ys, n_boot=500, seed=42)
    assert a == b


def test_bootstrap_ci_degenerate_all_improve():
    xs = [0] * 50
    ys = [1] * 50
    lo, hi, diff = paired_bootstrap_ci(xs, ys, n_boot=200, seed=1)
    assert diff == 1.0 and lo == 1.0 and hi == 1.0


def test_bootstrap_ci_identical_arms_is_zero():
    xs = [0, 1, 1, 0, 1]
    lo, hi, diff = paired_bootstrap_ci(xs, xs, n_boot=200, seed=1)
    assert diff == 0.0 and lo == 0.0 and hi == 0.0


def test_paired_from_records_aligns_on_id_intersection():
    a = {"t1": 1, "t2": 0, "t3": 1}
    b = {"t2": 1, "t3": 1, "t4": 0}
    xs, ys, ids = paired_from_records(a, b)
    assert ids == ["t2", "t3"]
    assert xs == [0, 1] and ys == [1, 1]


def test_pooled_mcnemar_sums_discordant_pairs_across_seeds():
    # Two seeds, B (arm b) beats A on net +2 and +3 discordant tasks.
    s1a = {"t1": 1, "t2": 0, "t3": 0}
    s1b = {"t1": 1, "t2": 1, "t3": 1}     # b=0, c=2
    s2a = {"u1": 1, "u2": 0, "u3": 0, "u4": 0}
    s2b = {"u1": 0, "u2": 1, "u3": 1, "u4": 1}  # b=1, c=3
    res = pooled_mcnemar([(s1a, s1b), (s2a, s2b)])
    assert res["b"] == 1 and res["c"] == 5     # pooled discordant counts
    assert res["n_pairs"] == 7
    assert res["p"] == mcnemar_exact(1, 5)
    assert res["net"] == 4                       # c - b, b-arm net wins


def test_pooled_mcnemar_all_seeds_one_direction_is_significant():
    # 3 seeds, b-arm wins 12 discordant tasks each, loses 0 -> clearly significant.
    pairs = []
    for _ in range(3):
        a = {f"t{i}": (1 if i == 0 else 0) for i in range(280)}       # only t0 correct
        b = {f"t{i}": (1 if i < 13 else 0) for i in range(280)}       # t0..t12 correct
        pairs.append((a, b))                                          # per seed: b=0, c=12
    res = pooled_mcnemar(pairs)
    assert res["b"] == 0 and res["c"] == 36
    assert res["p"] < 0.01
    assert res["net"] > 0


def test_load_per_item_reads_json_and_jsonl(tmp_path):
    rows = [{"id": "t1", "correct": 1}, {"id": "t2", "correct": 0}]
    pj = tmp_path / "r.json"
    pj.write_text(json.dumps(rows), encoding="utf-8")
    pl = tmp_path / "r.jsonl"
    pl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    expected = {"t1": 1, "t2": 0}
    assert load_per_item(str(pj), id_key="id", val_key="correct") == expected
    assert load_per_item(str(pl), id_key="id", val_key="correct") == expected
