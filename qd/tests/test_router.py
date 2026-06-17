"""Tests for the RR-SkillOpt router pure logic (qd/router.py).

Zero-API. Covers:
- rver_decision: the §3.2 pre-registered OPEN rule (net / fix>break / precision / trigger cap).
  Must OPEN reliable channels (LiveMath-style fix>>break) and CLOSE the two known-bad ones
  (SSB-AVP 2:18, SearchQA-AVP 3:8).
- should_canonicalize_span: SearchQA span-canonicalizer pure decision (verbatim, shorter, != A).
- ssb_hard_invariant_verdict: execution-grounded verdict from a process_one_codegen result dict
  (trigger ONLY on golden-free exec failures; NEVER on eval-mismatch / semantic).
"""
from __future__ import annotations

from qd.avp import should_repair
from qd.router import (
    build_router_decision,
    rver_decision,
    should_canonicalize_span,
    sign_test_one_sided,
    ssb_hard_invariant_verdict,
)


# ── rver_decision (§3.2 OPEN rule) ────────────────────────────────────────────

def test_rver_opens_on_clear_net_positive_within_trigger_cap():
    d = rver_decision(fix=5, break_=0, n_val=18, trigger_rate=5 / 18, trigger_cap=0.40)
    assert d["open"] is True
    assert d["decision"] == "open"
    assert d["net"] == 5


def test_rver_closes_ssb_avp_2_to_18():
    # The catastrophic SSB code-review AVP ratio must be blocked.
    d = rver_decision(fix=2, break_=18, n_val=40, trigger_rate=1.0, trigger_cap=0.10)
    assert d["open"] is False
    assert d["decision"] == "abstain"


def test_rver_closes_searchqa_avp_3_to_8():
    # The fuzzy-entailment SearchQA AVP ratio must be blocked.
    d = rver_decision(fix=3, break_=8, n_val=200, trigger_rate=0.20, trigger_cap=0.15)
    assert d["open"] is False


def test_rver_closes_when_fix_equals_break():
    d = rver_decision(fix=4, break_=4, n_val=200, trigger_rate=0.04, trigger_cap=0.15)
    assert d["open"] is False  # need fix > break strictly


def test_rver_closes_when_net_below_floor():
    # net=1 < max(2, ceil(0.01*n)); single net fix is not enough.
    d = rver_decision(fix=1, break_=0, n_val=18, trigger_rate=1 / 18, trigger_cap=0.40)
    assert d["open"] is False
    assert d["net_min"] == 2


def test_rver_net_floor_scales_with_n():
    # n=500 -> ceil(0.01*500)=5 dominates the abs floor of 2.
    d = rver_decision(fix=4, break_=0, n_val=500, trigger_rate=0.01, trigger_cap=0.15)
    assert d["net_min"] == 5
    assert d["open"] is False  # net 4 < 5
    d2 = rver_decision(fix=6, break_=0, n_val=500, trigger_rate=0.012, trigger_cap=0.15)
    assert d2["open"] is True


def test_rver_closes_when_trigger_rate_exceeds_cap():
    # Net-positive but it fires on too many items -> not a precise repair -> CLOSE.
    d = rver_decision(fix=10, break_=3, n_val=200, trigger_rate=0.50, trigger_cap=0.15)
    assert d["open"] is False


def test_rver_closes_on_low_precision():
    # net>=2, fix>break, within cap, but precision 7/12 < 0.60 -> CLOSE.
    d = rver_decision(fix=7, break_=5, n_val=200, trigger_rate=0.06, trigger_cap=0.15)
    assert round(d["precision"], 3) == round(7 / 12, 3)
    assert d["open"] is False


def test_rver_opens_at_precision_boundary():
    # precision exactly 0.60 passes (>=).
    d = rver_decision(fix=6, break_=4, n_val=200, trigger_rate=0.05, trigger_cap=0.15)
    assert d["precision"] == 0.6
    assert d["open"] is True


# ── should_canonicalize_span (SearchQA) ───────────────────────────────────────

def test_canonicalize_when_span_verbatim_and_shorter():
    assert should_canonicalize_span(
        candidate="The capital city is Paris, France.",
        span="Paris",
        evidence_text="... the capital city is Paris, France, located on the Seine ...",
    ) is True


def test_no_canonicalize_when_span_absent_from_evidence():
    assert should_canonicalize_span(
        candidate="The answer is Berlin.",
        span="Paris",
        evidence_text="... the capital city is Berlin ...",
    ) is False


def test_no_canonicalize_when_already_exact():
    # Candidate already equals the span (normalized) -> nothing to shorten.
    assert should_canonicalize_span(
        candidate="Paris",
        span="Paris",
        evidence_text="... is Paris ...",
    ) is False


def test_no_canonicalize_on_empty_or_none_span():
    assert should_canonicalize_span(candidate="something", span="", evidence_text="x") is False
    assert should_canonicalize_span(candidate="something", span="NONE", evidence_text="x") is False


def test_no_canonicalize_when_span_longer_than_candidate():
    # Span must be a shortening; a longer span is not a canonicalization.
    assert should_canonicalize_span(
        candidate="Paris",
        span="Paris, the capital of France",
        evidence_text="Paris, the capital of France, is large",
    ) is False


# ── ssb_hard_invariant_verdict (execution-grounded) ───────────────────────────

def test_ssb_invariant_fails_on_exec_not_ok():
    rep = ssb_hard_invariant_verdict({"exec_ok": False, "fail_reason": "exec-error: NameError",
                                      "phase": "eval"})
    assert rep["verdict"] == "FAIL"
    assert rep["repair_needed"] is True
    assert should_repair(rep) is True  # end-to-end with the qd.avp gate


def test_ssb_invariant_fails_on_timeout():
    rep = ssb_hard_invariant_verdict({"exec_ok": False, "phase": "timeout", "fail_reason": ""})
    assert rep["verdict"] == "FAIL"
    assert should_repair(rep) is True


def test_ssb_invariant_fails_on_output_not_found():
    rep = ssb_hard_invariant_verdict({"exec_ok": False, "fail_reason": "output-not-found",
                                      "phase": "eval"})
    assert should_repair(rep) is True


def test_ssb_invariant_passes_on_eval_mismatch_semantic():
    # Code ran + produced output but the answer is wrong (needs golden / semantic).
    # The hard-invariant verifier must NEVER trigger here.
    rep = ssb_hard_invariant_verdict({"exec_ok": True, "fail_reason": "eval-mismatch: A1 expected 5 got 6",
                                      "phase": "eval"})
    assert rep["verdict"] == "PASS"
    assert should_repair(rep) is False


def test_ssb_invariant_passes_on_clean_success():
    rep = ssb_hard_invariant_verdict({"exec_ok": True, "fail_reason": "", "phase": "eval", "hard": 1})
    assert rep["verdict"] == "PASS"
    assert should_repair(rep) is False


# ── build_router_decision (assembly) ──────────────────────────────────────────

def test_build_router_decision_only_open_channels_touch_test():
    rsel = {"open": True, "n_sel": 40}
    rver = rver_decision(fix=2, break_=18, n_val=40, trigger_rate=1.0, trigger_cap=0.10)
    doc = build_router_decision("spreadsheetbench", rsel, rver)
    assert doc["benchmark"] == "spreadsheetbench"
    assert doc["r_sel"]["open"] is True
    assert doc["r_ver"]["open"] is False
    # convenience: the set of channels allowed to touch test
    assert doc["test_channels"] == ["training"]  # r_sel open, r_ver closed


# ── sign test + power-adjusted dual-bar reporting ─────────────────────────────

def test_sign_test_one_sided_values():
    assert round(sign_test_one_sided(3, 0), 4) == 0.125          # 1/8
    assert round(sign_test_one_sided(6, 0), 6) == round(1 / 64, 6)
    assert round(sign_test_one_sided(2, 1), 4) == 0.5            # (3+1)/8
    assert round(sign_test_one_sided(5, 1), 6) == round(7 / 64, 6)
    assert sign_test_one_sided(0, 0) == 1.0                      # no evidence
    assert sign_test_one_sided(0, 2) == 1.0                      # no fixes -> no evidence


def test_rver_reports_both_bars_net_opens_sign_does_not():
    # net>=2 passes but sign test p=0.125 > 0.10 (small discordant n).
    d = rver_decision(fix=3, break_=0, n_val=53, trigger_rate=0.1, trigger_cap=0.4)
    assert d["open"] is True
    assert round(d["p_sign"], 4) == 0.125
    assert d["open_sign"] is False


def test_rver_sign_opens_when_clearly_significant():
    d = rver_decision(fix=6, break_=0, n_val=53, trigger_rate=0.1, trigger_cap=0.4)
    assert d["open"] is True
    assert d["open_sign"] is True            # p=0.0156 <= 0.10


def test_rver_sign_closed_when_fix_not_exceeds_break():
    d = rver_decision(fix=2, break_=1, n_val=18, trigger_rate=0.2, trigger_cap=0.4)
    assert d["open"] is False                # net 1 < 2
    assert d["open_sign"] is False           # also p=0.5


def test_rver_structural_precision_waives_trigger_cap():
    # SSB hard-invariant: 7:0 but trigger 0.133 > cap 0.10 -> normally closed.
    d_closed = rver_decision(fix=7, break_=0, n_val=120, trigger_rate=0.133, trigger_cap=0.10)
    assert d_closed["open"] is False
    # A verifier that only acts on already-failed items cannot break a correct answer
    # (precision structurally 1.0) -> the trigger cap (a precision proxy) is waived.
    d_open = rver_decision(fix=7, break_=0, n_val=120, trigger_rate=0.133, trigger_cap=0.10,
                           structural_precision=True)
    assert d_open["open"] is True            # net 7 >= 2, cap waived
    assert d_open["open_sign"] is True       # p = 1/128 <= 0.10
    assert d_open["structural_precision"] is True


def test_rver_structural_precision_still_needs_fix_gt_break():
    # Even with cap waived, a non-positive verifier stays closed.
    d = rver_decision(fix=1, break_=3, n_val=120, trigger_rate=0.05, trigger_cap=0.10,
                      structural_precision=True)
    assert d["open"] is False
    assert d["open_sign"] is False
