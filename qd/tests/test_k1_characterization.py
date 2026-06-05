"""T001 — K=1 characterization tests (slow-update protection + real-history replay).

Complements ``test_k1_reduces_to_skillopt.py`` (gate-oracle equivalence) with two
characterization tests pinned to *real* SkillOpt behavior:

  1. **Protected slow-update region** (ADR-0001 §5): a step edit whose ``target``
     lands inside the ``<!-- SLOW_UPDATE_* -->`` region is silently skipped
     (skill unchanged) — SkillOpt's ``optimizer/skill.py`` contract. A normal
     ``append`` still applies, landing *before* ``SLOW_UPDATE_START``.
  2. **Real-history replay**: the (candidate_gate_score, action, current/best/step)
     trajectory of the SpreadsheetBench vanilla run
     (``results/ssb_dpsk_run1/history.json``, baseline 0.40) replays
     decision-for-decision through the K=1 archive ``U``. Fixture frozen inline →
     self-contained, zero paid API, ms-fast.
"""
from __future__ import annotations

from skillopt.optimizer.skill import (
    SLOW_UPDATE_END,
    SLOW_UPDATE_START,
    apply_patch,
    apply_patch_with_report,
)

from qd.archive import Archive

# SkillOpt action vocabulary -> QD-native (see ADR-0001 §"决策").
_SKILLOPT_TO_QD = {"accept_new_best": "accept", "accept": "accept", "reject": "reject"}


# ── 1. Protected slow-update region (ADR-0001 §5) ─────────────────────────────

def _skill_with_protected_region() -> str:
    return (
        "# Skill\n\n"
        "Editable guidance here.\n\n"
        f"{SLOW_UPDATE_START}\n"
        "PROTECTED slow-update guidance - must survive step edits.\n"
        f"{SLOW_UPDATE_END}\n"
    )


def test_step_edit_into_protected_region_is_skipped() -> None:
    """A step edit targeting the protected region is a no-op (SkillOpt parity)."""
    skill = _skill_with_protected_region()
    patch = {"edits": [{"op": "replace", "target": "PROTECTED slow-update guidance", "content": "HACKED"}]}
    updated, reports = apply_patch_with_report(skill, patch)

    assert updated == skill  # skill unchanged
    assert reports[0]["status"] == "skipped_protected_slow_update_region"
    assert "PROTECTED slow-update guidance" in updated
    assert "HACKED" not in updated


def test_normal_append_lands_before_protected_region() -> None:
    """A non-protected edit still applies, inserted before SLOW_UPDATE_START."""
    skill = _skill_with_protected_region()
    updated = apply_patch(skill, {"edits": [{"op": "append", "content": "New editable tip."}]})

    assert "New editable tip." in updated
    assert updated.index("New editable tip.") < updated.index(SLOW_UPDATE_START)
    assert SLOW_UPDATE_START in updated and SLOW_UPDATE_END in updated  # block intact


# ── 2. Real-history replay (SpreadsheetBench vanilla run) ─────────────────────

# Frozen from results/ssb_dpsk_run1/{history,summary}.json (baseline_selection_hard=0.40).
# (step, candidate_gate_score, skillopt_action, current_score, best_score, best_step)
_SSB_BASELINE = 0.40
_SSB_HISTORY = [
    (1, 0.600, "accept_new_best", 0.600, 0.600, 1),
    (2, 0.600, "reject",          0.600, 0.600, 1),  # tie with current -> reject (strict >)
    (3, 0.525, "reject",          0.600, 0.600, 1),
    (4, 0.550, "reject",          0.600, 0.600, 1),
    (5, 0.550, "reject",          0.600, 0.600, 1),
    (6, 0.625, "accept_new_best", 0.625, 0.625, 6),
    (7, 0.575, "reject",          0.625, 0.625, 6),
    (8, 0.550, "reject",          0.625, 0.625, 6),
]


def test_k1_replays_real_spreadsheetbench_history() -> None:
    """K=1 archive reproduces the real run's per-step decisions exactly."""
    arch = Archive(k=1, baseline_skill="S0", baseline_score=_SSB_BASELINE)
    for step, cand, sk_action, cur, best, best_step in _SSB_HISTORY:
        r = arch.update(candidate_skill=f"cand_{step}", cand_score=cand, step=step)
        assert r.action == _SKILLOPT_TO_QD[sk_action], f"step {step}: action"
        assert arch.current_score == cur, f"step {step}: current_score"
        assert arch.best_score == best, f"step {step}: best_score"
        assert arch.best_step == best_step, f"step {step}: best_step"

    # end-state: 2 accepts total, best 0.625 first reached at step 6
    assert arch.best_score == 0.625
    assert arch.best_step == 6
