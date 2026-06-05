"""T001 — K=1 regression: QD archive at K=1 is decision-equivalent to SkillOpt.

Oracle = SkillOpt's pure gate ``skillopt.evaluation.gate.evaluate_gate``.
We feed the SAME ``(skill, score)`` stream to the oracle and to QD's K=1
archive ``U`` and assert identical state evolution. Zero paid API, ms-fast.

Semantics confirmed in QD-over-Skills/decisions/ADR-0001:
- gate compares ``cand > current_score`` (strict, ties reject), vs *current*.
- in the step loop ``current == best`` always holds, so SkillOpt emits only
  ``accept_new_best`` / ``reject``; the bare ``accept`` branch never fires.
- K=1 correspondence: QD "accept" ↔ SkillOpt "accept_new_best".
"""
from __future__ import annotations

from skillopt.evaluation.gate import evaluate_gate

from qd.archive import Archive

# K=1 action correspondence (SkillOpt vocabulary -> QD-native).
_SKILLOPT_TO_QD = {"accept_new_best": "accept", "accept": "accept", "reject": "reject"}


def test_k1_accepts_strictly_better_candidate_like_skillopt() -> None:
    # SkillOpt oracle: baseline current==best at 0.50; one strictly-better candidate.
    g = evaluate_gate(
        candidate_skill="S1",
        cand_hard=0.60,
        current_skill="S0",
        current_score=0.50,
        best_skill="S0",
        best_score=0.50,
        best_step=0,
        global_step=1,
        cand_soft=0.0,
        metric="hard",
    )

    arch = Archive(k=1, baseline_skill="S0", baseline_score=0.50)
    res = arch.update(candidate_skill="S1", cand_score=0.60, step=1)

    assert res.action == _SKILLOPT_TO_QD[g.action]  # "accept" (SkillOpt: accept_new_best)
    assert arch.current_score == g.current_score == 0.60
    assert arch.best_skill == g.best_skill == "S1"
    assert arch.best_score == g.best_score == 0.60
    assert arch.best_step == g.best_step == 1


# ── Oracle helpers: replay a (skill, score) stream through both engines ────────

def _oracle_trajectory(baseline_skill, baseline_score, sequence):
    """SkillOpt reference: iterate ``evaluate_gate`` exactly as the trainer does
    (force-accept default; per-step; current==best baseline). Returns the
    per-step ``(qd_action, current_skill, current_score, best_skill, best_score,
    best_step)`` tuple."""
    cur_s = best_s = baseline_skill
    cur_v = best_v = baseline_score
    best_step = 0
    traj = []
    for step, (cand_skill, cand_score) in enumerate(sequence, start=1):
        g = evaluate_gate(
            candidate_skill=cand_skill,
            cand_hard=cand_score,
            current_skill=cur_s,
            current_score=cur_v,
            best_skill=best_s,
            best_score=best_v,
            best_step=best_step,
            global_step=step,
            cand_soft=0.0,
            metric="hard",
        )
        cur_s, cur_v = g.current_skill, g.current_score
        best_s, best_v, best_step = g.best_skill, g.best_score, g.best_step
        traj.append((_SKILLOPT_TO_QD[g.action], cur_s, cur_v, best_s, best_v, best_step))
    return traj


def _archive_trajectory(baseline_skill, baseline_score, sequence):
    arch = Archive(k=1, baseline_skill=baseline_skill, baseline_score=baseline_score)
    traj = []
    for step, (cand_skill, cand_score) in enumerate(sequence, start=1):
        r = arch.update(candidate_skill=cand_skill, cand_score=cand_score, step=step)
        traj.append(
            (r.action, arch.current_skill, arch.current_score, arch.best_skill, arch.best_score, arch.best_step)
        )
    return traj


def test_k1_matches_skillopt_step_by_step_on_mixed_sequence() -> None:
    # 0.50 baseline, then: accept / reject(worse) / reject(tie w/ current) /
    # accept(new best) / reject(tie w/ best).
    sequence = [
        ("S1", 0.60),
        ("S2", 0.55),
        ("S3", 0.60),
        ("S4", 0.70),
        ("S5", 0.70),
    ]
    assert _archive_trajectory("S0", 0.50, sequence) == _oracle_trajectory("S0", 0.50, sequence)
