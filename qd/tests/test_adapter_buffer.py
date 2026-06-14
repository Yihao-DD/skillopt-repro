"""缺口 3 — adapter 原文模式: propose renders the rejected buffer PLAIN.

``rcv=False`` (default, faithful) => propose 只 render ledger（被拒方向 + 分数 drop），
绝不调 AIM（target_cell verbalize）或 flips（parent/cand rollout diff）—— 那是 RCV
增强（ADR-0007，已盖棺），仅由 ``rcv=True`` 开启。注入仍走 upstream 的
``step_buffer_context`` 通道（零 fork 改动）。
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
    items = []   # merged mode (gen IS sel) — so flips WOULD be computable if this were RCV
    return SkillOptProducer(adapter=FakeEnvAdapter(rollouts), gen_items=items, sel_items=items,
                            out_root=str(tmp_path))   # rcv defaults to False (原文模式)


def test_default_mode_renders_plain_buffer_without_flips_or_aim(tmp_path):
    # Known parent/cand rollouts (would yield flips under RCV) + a target_cell (would yield AIM).
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
    assert "先前尝试与结果" in ctx                  # plain ledger render IS present
    assert "wrap IO in try/except" in ctx          # the tried direction is rendered
    assert "对→错" not in ctx                       # NO flips (RCV-only)
    assert "操作密度" not in ctx and "复杂度" not in ctx   # NO AIM (RCV-only)
    assert "不要重复" not in ctx                     # NO RCV avoid-instruction


def test_default_mode_no_ledger_is_upstream_identical(tmp_path):
    p = _producer(tmp_path, {"PARENT": [{"id": "1", "hard": 1}]})
    p.propose("PARENT", step=1)
    assert p.adapter.reflect_kwargs == [{}]   # no buffer => no extra kwarg at all
