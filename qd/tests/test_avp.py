"""Tests for the pure AVP (Attempt-Verify-Patch) control logic. Zero-API: the
attempt/verify/repair model calls are injected as callables, so the control loop
and the conservative-repair gate are unit-tested without the model. The LLM
prompts + chat_target calls live in the eval harness (repro/official/avp_eval.py).
"""
from qd.avp import (
    consensus_correction,
    has_concrete_evidence,
    parse_verify_report,
    run_avp_loop,
    should_repair,
)

PASS_REPORT = """VERDICT: PASS
ERROR_TYPE: none
EVIDENCE:
- substituted option B back, equation holds
REPAIR_NEEDED: no
"""

FAIL_REPORT = """VERDICT: FAIL
ERROR_TYPE: arithmetic
EVIDENCE:
- recomputed 3*7=21 not 24, so option C is wrong
- boundary x=0 excluded by the constraint
REPAIR_NEEDED: yes
"""

FAIL_NO_EVIDENCE = """VERDICT: FAIL
ERROR_TYPE: none
EVIDENCE:
REPAIR_NEEDED: yes
"""


# ── parsing ──────────────────────────────────────────────────────────────────

def test_parse_pass_report():
    r = parse_verify_report(PASS_REPORT)
    assert r["verdict"] == "PASS"
    assert r["error_type"] == "none"
    assert r["repair_needed"] is False


def test_parse_fail_report_collects_evidence():
    r = parse_verify_report(FAIL_REPORT)
    assert r["verdict"] == "FAIL"
    assert r["error_type"] == "arithmetic"
    assert r["repair_needed"] is True
    assert len(r["evidence"]) == 2


def test_parse_unparseable_defaults_to_pass():
    # conservative: garbage / missing VERDICT -> treat as PASS (keep A0)
    r = parse_verify_report("the answer looks fine to me")
    assert r["verdict"] == "PASS"
    assert should_repair(r) is False


# ── concrete-evidence gate ───────────────────────────────────────────────────

def test_has_concrete_evidence():
    assert has_concrete_evidence(parse_verify_report(FAIL_REPORT)) is True
    assert has_concrete_evidence(parse_verify_report(FAIL_NO_EVIDENCE)) is False
    assert has_concrete_evidence(parse_verify_report(PASS_REPORT)) is False  # error_type none


# ── conservative repair gate ─────────────────────────────────────────────────

def test_should_repair_only_on_fail_with_evidence():
    assert should_repair(parse_verify_report(FAIL_REPORT)) is True
    assert should_repair(parse_verify_report(PASS_REPORT)) is False
    assert should_repair(parse_verify_report(FAIL_NO_EVIDENCE)) is False  # no evidence -> keep


# ── control loop (injected callables, zero-API) ──────────────────────────────

def test_loop_max_repairs_zero_is_attempt_only():
    # K1-single: max_repairs=0 -> never verify, return the attempt
    out, trace = run_avp_loop(attempt=lambda: "A0", verify=lambda o: FAIL_REPORT,
                              repair=lambda o, r: "REPAIRED", max_repairs=0)
    assert out == "A0"
    assert [t["stage"] for t in trace] == ["attempt"]


def test_loop_pass_keeps_attempt():
    calls = {"repair": 0}

    def _repair(o, r):
        calls["repair"] += 1
        return "REPAIRED"

    out, _ = run_avp_loop(attempt=lambda: "A0", verify=lambda o: PASS_REPORT,
                          repair=_repair, max_repairs=1)
    assert out == "A0"
    assert calls["repair"] == 0  # PASS -> no repair


def test_loop_fail_with_evidence_repairs_once():
    out, trace = run_avp_loop(attempt=lambda: "A0", verify=lambda o: FAIL_REPORT,
                              repair=lambda o, r: "REPAIRED", max_repairs=1)
    assert out == "REPAIRED"
    assert trace[-1]["repaired"] is True


def test_loop_fail_no_evidence_does_not_repair():
    out, _ = run_avp_loop(attempt=lambda: "A0", verify=lambda o: FAIL_NO_EVIDENCE,
                          repair=lambda o, r: "REPAIRED", max_repairs=1)
    assert out == "A0"  # conservative: no concrete evidence -> keep


def test_loop_two_repairs_stops_when_pass():
    # verify returns FAIL then PASS -> exactly one repair even with max_repairs=2
    seq = [FAIL_REPORT, PASS_REPORT]
    out, trace = run_avp_loop(attempt=lambda: "A0", verify=lambda o: seq.pop(0),
                              repair=lambda o, r: "R1", max_repairs=2)
    assert out == "R1"
    assert sum(1 for t in trace if t.get("repaired")) == 1


# ── consensus_correction (math-check v2: noise-filtering inference repair) ─────

def test_consensus_repairs_on_majority_agreement():
    # >=2 independent verify passes FAIL and agree on the same corrected choice.
    votes = [("FAIL", "B"), ("FAIL", "B"), ("PASS", "")]
    assert consensus_correction(votes, min_agree=2) == (True, "B")


def test_consensus_no_repair_on_disagreeing_fails():
    # Two FAILs but they propose DIFFERENT corrections -> noise, do not repair.
    votes = [("FAIL", "B"), ("FAIL", "C"), ("PASS", "")]
    assert consensus_correction(votes, min_agree=2) == (False, "")


def test_consensus_no_repair_on_single_fail():
    # A lone noise-FAIL must not trigger (this is the break-avoidance property).
    votes = [("PASS", ""), ("PASS", ""), ("FAIL", "B")]
    assert consensus_correction(votes, min_agree=2) == (False, "")


def test_consensus_no_repair_all_pass():
    assert consensus_correction([("PASS", ""), ("PASS", "")], min_agree=2) == (False, "")


def test_consensus_unanimous_fail():
    assert consensus_correction([("FAIL", "D"), ("FAIL", "D"), ("FAIL", "D")], min_agree=2) == (True, "D")


def test_consensus_ignores_fail_with_no_choice():
    # A FAIL vote without a concrete corrected choice does not count toward agreement.
    votes = [("FAIL", ""), ("FAIL", "B"), ("PASS", "")]
    assert consensus_correction(votes, min_agree=2) == (False, "")
