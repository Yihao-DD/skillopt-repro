"""S4/S8 — integrated loop: K=1 generation path + equal budget + K>1 routing.

Zero API: the model/env is faked via :class:`~qd.loop.CandidateProducer`. Closes
F3 (the K=1 decision path == ``evaluate_gate``, with a *programmatic* cosine edit
budget and the real ``rank_and_select`` no-op branch) and demonstrates the equal
expensive-eval budget red line + descriptor→Archive cell routing at K>1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from skillopt.evaluation.gate import evaluate_gate
from skillopt.optimizer.scheduler import build_scheduler

from qd.budget import EvalCounter
from qd.loop import CandidateProducer, run_search


@dataclass
class FakeProducer:
    """Deterministic zero-API producer; ``scores`` is consumed per distinct candidate."""

    scores: list[float]
    pool_size: int = 1
    _calls: int = field(default=0)

    def propose(self, skill, *, step, target_cell=None):
        return {"edits": [{"text": f"|s{step}.{j}"} for j in range(self.pool_size)], "reasoning": "fake"}

    def apply(self, skill, patch):
        return skill + "".join(e["text"] for e in patch.get("edits", []))

    def score(self, skill):
        s = self.scores[min(self._calls, len(self.scores) - 1)]
        self._calls += 1
        return s

    def as_producer(self) -> CandidateProducer:
        return CandidateProducer(propose=self.propose, apply=self.apply, score=self.score)


def test_edit_budget_follows_cosine_schedule_programmatically() -> None:
    prod = FakeProducer(scores=[0.1] * 8)  # all below baseline → reject, parent fixed
    res = run_search(k=1, baseline_skill="B", baseline_score=0.9, eval_budget=8,
                     producer=prod.as_producer(), max_lr=4, min_lr=2)
    sched = build_scheduler("cosine", max_lr=4, min_lr=2, total_steps=8)  # 8 // cps(1)
    assert res.edit_budgets == [sched.get_lr(s) for s in range(1, 9)]
    assert res.expensive_evals == 8


def test_k1_decision_matches_evaluate_gate() -> None:
    scripted = [0.40, 0.60, 0.55, 0.70]
    prod = FakeProducer(scores=scripted)
    res = run_search(k=1, baseline_skill="BASE", baseline_score=0.50,
                     eval_budget=len(scripted), producer=prod.as_producer())

    # Oracle: feed the SAME candidate scores to evaluate_gate step-by-step.
    cur_sk = best_sk = "BASE"
    cur_s = best_s = 0.50
    best_step = 0
    oracle = []
    for i, cs in enumerate(scripted, start=1):
        g = evaluate_gate("CAND", cs, cur_sk, cur_s, best_sk, best_s, best_step, i)
        oracle.append("accept" if g.action in ("accept", "accept_new_best") else "reject")
        cur_sk, cur_s = g.current_skill, g.current_score
        best_sk, best_s, best_step = g.best_skill, g.best_score, g.best_step

    assert [r.action for r in res.history] == oracle
    assert res.best_score == max(0.50, *scripted)
    assert res.n_occupied == 1


def test_real_rank_and_select_unchanged_when_pool_within_budget() -> None:
    # Real SkillOpt helper, zero API: pool <= budget returns the patch unchanged.
    from skillopt.optimizer.clip import rank_and_select

    patch = {"edits": [{"text": "a"}, {"text": "b"}], "reasoning": "r"}
    assert rank_and_select("SKILL", patch, 4, update_mode="patch") is patch


def _celled_producer() -> CandidateProducer:
    """K>1 producer whose probe behavior alternates → distinct descriptor cells."""
    HI = "ws.cell(1, 1)\nws.cell(2, 1)\nws.cell(3, 1)\n"  # high op-density
    LO = "x = 1\ny = 2\nz = 3\nw = 4\n"                    # ~0 op-density
    n = {"i": 0}

    def propose(skill, *, step, target_cell=None):
        return {"edits": [{"text": f".{step}"}]}

    def apply(skill, patch):
        i = n["i"]
        n["i"] += 1
        return f"{skill}.{i}{'A' if i % 2 == 0 else 'B'}"  # distinct + behavior tag

    def score(skill):
        return 0.9 if skill.endswith("A") else 0.8

    def probe(skill):
        return [{"code": HI if skill.endswith("A") else LO}]

    return CandidateProducer(propose=propose, apply=apply, score=score, probe=probe)


def test_equal_expensive_eval_budget_across_arms() -> None:
    # Same eval_budget → identical expensive-eval spend regardless of candidates/step.
    c1, c4 = EvalCounter(), EvalCounter()
    r1 = run_search(k=1, baseline_skill="B", baseline_score=0.5, eval_budget=6,
                    producer=FakeProducer(scores=[0.3, 0.6, 0.4, 0.7, 0.55, 0.8]).as_producer(), counter=c1)
    r4 = run_search(k=4, baseline_skill="B", baseline_score=0.5, eval_budget=6,
                    producer=_celled_producer(), counter=c4)
    assert r1.expensive_evals == r4.expensive_evals == 6
    assert r1.n_occupied == 1


def test_k_gt_1_routes_distinct_behaviors_to_distinct_cells() -> None:
    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=6,
                     producer=_celled_producer(), baseline_cell=0)
    assert res.expensive_evals == 6
    assert res.n_occupied >= 2, res.archive.occupied_cells()
