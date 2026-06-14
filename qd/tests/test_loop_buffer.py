"""缺口 3 — epoch-local rejected buffer (原文 §3.5, faithful B path).

原文标配：每个 epoch 维护一个 step buffer（被拒 edits + score drop），喂给
propose 让优化器避开已失败方向。trainer.py 在 epoch 循环内 ``step_buffer=[]``
(epoch-local)，每步 ``step_buffer.append`` (accept+reject)，``_format_step_buffer``
渲染后作为 ``step_buffer_context`` 传给 reflect。

我们复用 :class:`~qd.ledger.RejectionLedger` 作为 buffer，**两臂默认开**（含 K=1，
原文 K=1 本就有 buffer）——buffer 只改 propose 的输入，不碰 gate 逻辑，所以
K=1 仍逐字 == SkillOpt（gate 等价由 test_k1_reduces_to_skillopt 守）。

Contracts（zero-API）：
  - K=1 propose 收到一个非 None 的 epoch-local buffer，epoch 内增长、epoch 边界重置；
  - buffer 每步记录尝试方向 + 结果（accept/reject + 分数 delta）；
  - K>1 默认（use_ledger=False）也线程 buffer，但 ``res.ledger``（RCV 工件）保持 None。
"""
from __future__ import annotations

from qd.ledger import RejectionLedger
from qd.loop import CandidateProducer, run_search


def test_k1_propose_receives_epoch_local_buffer_that_grows_and_resets() -> None:
    seen: list[int] = []   # buffer length observed by each propose

    def propose(skill, *, step, target_cell=None, ledger=None):
        assert isinstance(ledger, RejectionLedger)   # 原文：K=1 也有 buffer
        seen.append(len(ledger))
        return {"edits": [{"text": f".s{step}"}]}

    def apply(skill, patch):
        return skill + "".join(e["text"] for e in patch.get("edits", []))

    prod = CandidateProducer(propose=propose, apply=apply, score=lambda s: 0.1)  # all reject vs 0.9
    # eval_budget=4, num_epochs=2 -> 2 steps/epoch; buffer grows 0,1 then RESETS 0,1.
    run_search(k=1, baseline_skill="B", baseline_score=0.9, eval_budget=4, producer=prod, num_epochs=2)
    assert seen == [0, 1, 0, 1]


def test_buffer_records_direction_and_outcome_each_step() -> None:
    holder: dict = {}

    def propose(skill, *, step, target_cell=None, ledger=None):
        holder["buf"] = ledger          # same object, appended after each step
        return {"edits": [{"text": f"DIR{step}"}]}

    def apply(skill, patch):
        return skill + "".join(e["text"] for e in patch.get("edits", []))

    prod = CandidateProducer(propose=propose, apply=apply, score=lambda s: 0.1)
    run_search(k=1, baseline_skill="B", baseline_score=0.9, eval_budget=3, producer=prod, num_epochs=1)

    buf = holder["buf"]
    assert isinstance(buf, RejectionLedger) and len(buf) == 3
    e0 = buf.entries[0]
    assert e0.action == "reject"            # 0.1 < 0.9 (strict >)
    assert e0.score == 0.1
    assert e0.parent_score == 0.9           # K=1: parent == best == baseline
    assert "DIR1" in e0.edits_summary       # the tried direction is recorded


def test_k_gt_1_default_threads_epoch_local_buffer_without_exposing_rcv_ledger() -> None:
    HI = "ws.cell(1, 1)\nws.cell(2, 1)\nws.cell(3, 1)\n"
    LO = "x = 1\ny = 2\nz = 3\nw = 4\n"
    n = {"i": 0}
    seen: list[bool] = []

    def propose(skill, *, step, target_cell=None, ledger=None):
        seen.append(ledger is not None)
        return {"edits": [{"text": f".{step}"}]}

    def apply(skill, patch):
        i = n["i"]
        n["i"] += 1
        return f"{skill}.{i}{'A' if i % 2 == 0 else 'B'}"

    def score(skill):
        return 0.9 if skill.endswith("A") else 0.8

    def probe(skill):
        return [{"code": HI if skill.endswith("A") else LO}]

    prod = CandidateProducer(propose=propose, apply=apply, score=score, probe=probe)
    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=4, producer=prod)
    assert seen and all(seen)        # buffer threaded by default (no use_ledger needed)
    assert res.ledger is None        # RCV artifact stays off without use_ledger
