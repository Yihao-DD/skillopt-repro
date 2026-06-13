"""Epoch structure + slow update (原文 §3.6) in run_search — faithful B path.

Zero-API. The slow/meta core logic lives in the fork (run_slow_update,
format_meta_skill_context); run_search only ORCHESTRATES the epoch boundary:
once per epoch it calls producer.slow_update(prev_epoch_skill, curr_best) and
force-accepts the guidance into the archive's best elite (原文 default mode).

Contracts:
  - num_epochs=1 (default) -> slow_update NEVER called (back-compat: existing
    flat-loop behavior unchanged);
  - num_epochs=E -> slow_update called once per epoch, with the epoch's starting
    skill as prev and the current best as curr;
  - the returned guidance is applied (apply_slow) and the archive best reflects it.
"""
from __future__ import annotations

from qd.loop import CandidateProducer, run_search


def _base_producer(scores, **extra):
    n = {"i": 0}

    def propose(skill, *, step, target_cell=None):
        return {"edits": [{"text": f".s{step}"}]}

    def apply(skill, patch):
        return skill + "".join(e["text"] for e in patch.get("edits", []))

    def score(skill):
        s = scores[min(n["i"], len(scores) - 1)]
        n["i"] += 1
        return s

    return CandidateProducer(propose=propose, apply=apply, score=score, **extra)


def test_num_epochs_1_never_calls_slow_update():
    calls = []
    prod = _base_producer([0.1] * 8,
                          slow_update=lambda prev, curr: calls.append((prev, curr)) or "G",
                          apply_slow=lambda skill, g: skill + g)
    run_search(k=1, baseline_skill="B", baseline_score=0.9, eval_budget=6,
               producer=prod, num_epochs=1)
    assert calls == []          # default: flat loop, no epoch boundary, no slow update


def test_slow_update_called_once_per_epoch():
    calls = []
    prod = _base_producer([0.1] * 12,
                          slow_update=lambda prev, curr: calls.append((prev, curr)) or "G",
                          apply_slow=lambda skill, g: skill + g)
    run_search(k=1, baseline_skill="BASE", baseline_score=0.9, eval_budget=6,
               producer=prod, num_epochs=3)
    assert len(calls) == 3      # one slow update per epoch


def test_slow_guidance_applied_to_best_when_it_helps():
    # epoch produces an improving candidate; slow update then force-injects guidance.
    scores = [0.95] + [0.1] * 10   # first candidate beats baseline 0.9 -> archive best moves
    applied = []
    prod = _base_producer(scores,
                          slow_update=lambda prev, curr: "SLOWGUIDE",
                          apply_slow=lambda skill, g: applied.append((skill, g)) or (skill + "|" + g))
    res = run_search(k=1, baseline_skill="BASE", baseline_score=0.9, eval_budget=4,
                     producer=prod, num_epochs=2)
    assert applied                                   # slow guidance was applied
    assert "SLOWGUIDE" in res.archive.best_skill     # best elite carries the guidance


def test_slow_guidance_injected_into_all_occupied_elites():
    # K>1: slow lesson is a GLOBAL domain lesson -> every occupied elite gets it,
    # not just the best (so any UCB-selected parent next epoch carries the lesson).
    HI = "ws.cell(1, 1)\nws.cell(2, 1)\nws.cell(3, 1)\n"
    LO = "x = 1\ny = 2\nz = 3\nw = 4\n"
    n = {"i": 0}

    def propose(skill, *, step, target_cell=None):
        return {"edits": [{"text": f".{step}"}]}

    def apply(skill, patch):
        i = n["i"]
        n["i"] += 1
        return f"{skill}.{i}{'A' if i % 2 == 0 else 'B'}"

    def score(skill):
        return 0.9 if skill.endswith("A") else 0.8

    def probe(skill):
        return [{"code": HI if skill.endswith("A") else LO}]

    prod = CandidateProducer(propose=propose, apply=apply, score=score, probe=probe,
                             slow_update=lambda prev, curr: "DOMAINLESSON",
                             apply_slow=lambda skill, g: skill + "|" + g)
    res = run_search(k=16, baseline_skill="BASE", baseline_score=0.5, eval_budget=6,
                     producer=prod, num_epochs=2)
    occupied = res.archive.occupied_cells()
    assert len(occupied) >= 2                                  # multi-cell
    for cell in occupied:
        assert "DOMAINLESSON" in res.archive.elite(cell).skill  # every elite carries the lesson
