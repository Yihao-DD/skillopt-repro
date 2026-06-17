"""Tests for the D_sel reliability governor (RG-SkillOpt component 1).

Pure, zero-API. Given per-candidate per-item D_sel binary outcomes, the governor
estimates whether D_sel can RELIABLY pick the best candidate, and emits
``allow_width``. It NEVER looks at D_test.
"""
from qd.reliability import (
    allow_width,
    candidate_margin,
    reliability_metrics,
)


def _clear_winner(n=40):
    # cand A solves ~90%, cand B ~30% -> A is clearly + stably best
    a = [1 if i < int(0.9 * n) else 0 for i in range(n)]
    b = [1 if i < int(0.3 * n) else 0 for i in range(n)]
    return {"A": a, "B": b}


def _tied(n=40):
    # A solves even items, B solves odd -> both 0.5, no stable winner
    a = [1 if i % 2 == 0 else 0 for i in range(n)]
    b = [1 if i % 2 == 1 else 0 for i in range(n)]
    return {"A": a, "B": b}


def test_clear_winner_is_reliable():
    m = reliability_metrics(_clear_winner(40), seed=1)
    assert m["n_sel"] == 40
    assert m["split_half_best_agreement"] > 0.9
    assert m["bootstrap_prob_best"] > 0.9
    assert m["candidate_margin"] > 0.4
    assert allow_width(m) is True


def test_tied_is_unreliable():
    m = reliability_metrics(_tied(40), seed=1)
    assert m["split_half_best_agreement"] < 0.6 or m["bootstrap_prob_best"] < 0.7
    assert allow_width(m) is False


def test_small_n_sel_blocks_width_even_with_clear_winner():
    m = reliability_metrics(_clear_winner(18), seed=1)  # clear winner, only 18 items
    assert m["n_sel"] == 18
    assert allow_width(m) is False  # n_sel < 30 -> false regardless


def test_allow_width_rules_exact():
    assert allow_width({"n_sel": 29, "split_half_best_agreement": 1.0,
                        "bootstrap_prob_best": 1.0, "candidate_margin": 0.5}) is False
    assert allow_width({"n_sel": 40, "split_half_best_agreement": 0.59,
                        "bootstrap_prob_best": 1.0, "candidate_margin": 0.5}) is False
    assert allow_width({"n_sel": 40, "split_half_best_agreement": 0.9,
                        "bootstrap_prob_best": 0.69, "candidate_margin": 0.5}) is False
    assert allow_width({"n_sel": 40, "split_half_best_agreement": 0.9,
                        "bootstrap_prob_best": 0.8, "candidate_margin": 0.1}) is True


def test_candidate_margin_is_best_minus_second():
    assert abs(candidate_margin(_clear_winner(40)) - 0.6) < 1e-9


def test_determinism():
    r = _clear_winner(40)
    assert reliability_metrics(r, seed=7) == reliability_metrics(r, seed=7)
