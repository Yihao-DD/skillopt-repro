"""RCV adapter wiring (ADR-0007): extra context flows through the UPSTREAM
``step_buffer_context`` channel — zero fork changes.

Zero API: the SkillOpt env adapter is faked (duck-typed). Contracts:
  - no ledger -> reflect called with NO step_buffer_context kwarg (upstream-identical);
  - with ledger -> step_buffer_context carries AVOID (ledger render + task flips
    diffed from the producer's OWN rollout cache, zero extra calls) + AIM
    (target_cell verbalized via ADR-0006 axis semantics);
  - unknown cache hashes degrade gracefully (no flips, no crash).
"""
from __future__ import annotations

from qd.adapter_skillopt import SkillOptProducer
from qd.ledger import LedgerEntry, RejectionLedger, skill_fingerprint


class FakeEnvAdapter:
    def __init__(self, rollouts: dict):
        self.rollouts = rollouts
        self.reflect_kwargs: list[dict] = []

    def rollout(self, items, skill, outdir):
        return self.rollouts[skill]

    def reflect(self, results, skill, outdir, **kwargs):
        self.reflect_kwargs.append(kwargs)
        return [{"patch": {"edits": [{"text": "E1"}]}}]


def _producer(tmp_path, rollouts):
    items = []   # one object for gen AND sel => merged mode (RCV flips diff same-set)
    return SkillOptProducer(adapter=FakeEnvAdapter(rollouts), gen_items=items, sel_items=items,
                            out_root=str(tmp_path), rcv=True)   # RCV mode: flips + AIM enrichment


def test_propose_without_ledger_is_upstream_identical(tmp_path):
    p = _producer(tmp_path, {"PARENT": [{"id": "1", "hard": 1}]})
    p.propose("PARENT", step=1)
    assert p.adapter.reflect_kwargs == [{}]   # no extra kwarg at all


def test_propose_with_ledger_injects_avoid_flips_and_aim(tmp_path):
    rollouts = {
        "PARENT": [{"id": "1024", "hard": 1}, {"id": "1003", "hard": 0}],
        "CAND": [{"id": "1024", "hard": 0}, {"id": "1003", "hard": 0}],
    }
    p = _producer(tmp_path, rollouts)
    p._rollout("PARENT", p.sel_items)
    p._rollout("CAND", p.sel_items)
    led = RejectionLedger()
    led.append(LedgerEntry(
        step=1, action="reject", score=0.40, parent_score=0.45, cell=5, parent_cell=5,
        edits_summary="wrap IO in try/except",
        parent_hash=skill_fingerprint("PARENT"), cand_hash=skill_fingerprint("CAND"),
    ))
    p.propose("PARENT", step=2, target_cell=6, ledger=led)
    ctx = p.adapter.reflect_kwargs[-1]["step_buffer_context"]
    assert "先前尝试与结果" in ctx                  # AVOID: ledger render
    assert "#1024 对→错" in ctx                    # flips diffed from rollout cache
    assert "操作密度" in ctx and "复杂度" in ctx    # AIM: cell 6 -> complexity bin1, op_density bin2
    assert "不要重复" in ctx                        # avoid instruction
    assert led.entries[0].task_flips == ()         # original ledger NOT mutated


def test_unknown_hashes_degrade_without_flips(tmp_path):
    p = _producer(tmp_path, {"PARENT": [{"id": "1", "hard": 1}]})
    p._rollout("PARENT", p.sel_items)
    led = RejectionLedger()
    led.append(LedgerEntry(step=1, action="reject", score=0.4, parent_score=0.45,
                           parent_hash="deadbeef", cand_hash="cafebabe",
                           edits_summary="some direction"))
    p.propose("PARENT", step=2, ledger=led)
    ctx = p.adapter.reflect_kwargs[-1]["step_buffer_context"]
    assert "some direction" in ctx
    assert "翻转" not in ctx                       # no flips fabricated
