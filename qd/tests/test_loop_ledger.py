"""RCV loop integration (ADR-0007): ledger lifecycle + speculative pre-check.

Zero API. Contracts under test:
  - use_ledger=True (K>1): a RejectionLedger flows into ``producer.propose`` as a
    kwarg, grows by exactly one entry per scored candidate, and records the tried
    direction (patch summary) with parent/candidate fingerprints.
  - K=1 IGNORES RCV flags entirely (red line C0: K=1 == SkillOpt byte-for-byte;
    old-style propose without a ledger kwarg must keep working).
  - pre_check guardrails: skipping never spends expensive budget yet the arm still
    spends its FULL equal budget; a step can never skip ALL survivors; pre_check
    exceptions fail OPEN (candidate evaluated); pre_check without use_ledger is a
    configuration error.
"""
from __future__ import annotations

from qd.ledger import RejectionLedger, skill_fingerprint
from qd.loop import CandidateProducer, run_search

import pytest

HI = "ws.cell(1, 1)\nws.cell(2, 1)\nws.cell(3, 1)\n"  # high op-density probe
LO = "x = 1\ny = 2\nz = 3\nw = 4\n"                    # ~0 op-density probe


def _ledger_aware_producer(seen_sizes: list[int]) -> CandidateProducer:
    """Alternating-behavior producer whose propose RECORDS the ledger size."""
    n = {"i": 0}

    def propose(skill, *, step, target_cell=None, ledger=None):
        assert isinstance(ledger, RejectionLedger)
        seen_sizes.append(len(ledger))
        return {"edits": [{"text": "DIRX"}]}

    def apply(skill, patch):
        i = n["i"]
        n["i"] += 1
        return f"{skill}.{i}{'A' if i % 2 == 0 else 'B'}"

    def score(skill):
        return 0.9 if skill.endswith("A") else 0.8

    def probe(skill):
        return [{"code": HI if skill.endswith("A") else LO}]

    return CandidateProducer(propose=propose, apply=apply, score=score, probe=probe)


def test_ledger_flows_to_propose_and_grows_with_outcomes() -> None:
    sizes: list[int] = []
    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=4,
                     producer=_ledger_aware_producer(sizes), use_ledger=True)
    assert res.expensive_evals == 4
    assert res.ledger is not None
    assert len(res.ledger) == len(res.history) == 4
    assert [e.action for e in res.ledger.entries] == [r.action for r in res.history]
    assert sizes[0] == 0                      # first propose sees an empty ledger
    assert sizes == sorted(sizes)             # ledger only grows
    assert sizes[-1] > 0                      # later proposals see paid-for outcomes


def test_ledger_entries_record_direction_and_fingerprints() -> None:
    sizes: list[int] = []
    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=2,
                     producer=_ledger_aware_producer(sizes), use_ledger=True)
    entry = res.ledger.entries[0]
    assert entry.n_edits == 1
    assert "DIRX" in entry.edits_summary
    assert entry.parent_hash == skill_fingerprint("BASE")
    assert entry.cand_hash and entry.cand_hash != entry.parent_hash


def test_k1_ignores_rcv_flags_and_keeps_old_propose_contract() -> None:
    # propose WITHOUT a ledger kwarg: would TypeError if the loop passed one.
    def propose(skill, *, step, target_cell=None):
        return {"edits": [{"text": f".x{step}"}]}   # step-distinct, else cache-hit stalls

    prod = CandidateProducer(
        propose=propose,
        apply=lambda s, p: s + "".join(e["text"] for e in p.get("edits", [])),
        score=lambda s: 0.1,
    )
    res = run_search(k=1, baseline_skill="B", baseline_score=0.9, eval_budget=2,
                     producer=prod, use_ledger=True, pre_check=lambda pc, led: False)
    assert res.expensive_evals == 2
    assert res.ledger is None
    assert res.precheck_skips == 0


def test_pre_check_skip_spends_no_eval_but_budget_still_fills() -> None:
    sizes: list[int] = []
    skipped: list[str] = []

    def pre_check(pc, ledger):
        if pc.skill.endswith("B"):
            skipped.append(pc.skill)
            return False
        return True

    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=4,
                     producer=_ledger_aware_producer(sizes), use_ledger=True, pre_check=pre_check)
    assert res.expensive_evals == 4                       # equal budget fully spent
    assert res.precheck_skips == len(skipped) > 0
    assert all(not r.candidate.skill.endswith("B") for r in res.history)
    assert len(res.ledger) == len(res.history)            # skipped: no outcome, no entry


def test_pre_check_cannot_skip_all_survivors_in_a_step() -> None:
    sizes: list[int] = []
    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=3,
                     producer=_ledger_aware_producer(sizes), use_ledger=True,
                     pre_check=lambda pc, led: False)      # tries to skip everything
    assert res.expensive_evals == 3                        # forced pass-one per step
    assert res.precheck_skips > 0


def test_pre_check_exceptions_fail_open() -> None:
    sizes: list[int] = []

    def broken(pc, ledger):
        raise RuntimeError("precheck backend down")

    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=2,
                     producer=_ledger_aware_producer(sizes), use_ledger=True, pre_check=broken)
    assert res.expensive_evals == 2
    assert res.precheck_skips == 0                         # never lost a candidate to errors


def test_patch_summary_handles_schema_variants_without_repr_noise() -> None:
    from qd.loop import _patch_summary

    assert _patch_summary(None) == ""
    assert _patch_summary({"edits": [{"text": "T1"}, {"code": "C2"}, {"x": 1}, "raw"]}).startswith("T1; C2")
    out = _patch_summary({"edits": [{"code": "only-code"}]})
    assert "only-code" in out and "{" not in out   # no Python-repr noise in LLM-facing text


def test_pre_check_without_use_ledger_is_a_config_error() -> None:
    sizes: list[int] = []
    with pytest.raises(ValueError):
        run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=1,
                   producer=_ledger_aware_producer(sizes), pre_check=lambda pc, led: True)
