"""RCV rejection ledger (ADR-0007): entry semantics + deterministic render.

Zero-API. The ledger is the serialization of already-paid (direction, outcome)
pairs; render() is the pseudo-gradient prompt fragment. Contract under test:
  - delta = score - parent_score; fingerprint == adapter/_skill_hash algo
  - render: deterministic; OPRO ascending score order; action/delta/cell
    movement markers; task-flip lines; lesson preferred but evidence kept;
    char_budget respected by dropping OLDEST entries, folded into a count line;
    selection keeps best accept + biggest |delta| reject beyond recency window.
"""
from __future__ import annotations

from qd.budget import BehaviorCandidate
from qd.ledger import LedgerEntry, RejectionLedger, skill_fingerprint


def _entry(step, action, score, parent_score, *, cell=0, parent_cell=0, **kw):
    return LedgerEntry(
        step=step, action=action, score=score, parent_score=parent_score,
        cell=cell, parent_cell=parent_cell, **kw,
    )


def test_entry_delta_and_fingerprint_match_budget_hash():
    e = _entry(1, "reject", 0.40, 0.45)
    assert abs(e.delta - (-0.05)) < 1e-12
    skill = "## skill text\nsome body"
    assert skill_fingerprint(skill) == BehaviorCandidate(skill=skill, b=(0.0,), cell=0).skill_hash


def test_ledger_counts_accepts_and_rejects():
    led = RejectionLedger()
    led.append(_entry(1, "accept", 0.45, 0.40))
    led.append(_entry(2, "reject", 0.40, 0.45))
    led.append(_entry(3, "reject", 0.45, 0.45))
    assert len(led) == 3
    assert led.n_accepts == 1
    assert led.n_rejects == 2


def test_render_empty_ledger_is_empty_string():
    assert RejectionLedger().render() == ""


def test_render_is_deterministic():
    led = RejectionLedger()
    led.append(_entry(1, "accept", 0.45, 0.40, edits_summary="add schema-first rule"))
    led.append(_entry(2, "reject", 0.40, 0.45, edits_summary="wrap IO in try/except"))
    assert led.render() == led.render()


def test_render_orders_entries_by_score_ascending():
    led = RejectionLedger()
    led.append(_entry(1, "reject", 0.60, 0.50, edits_summary="EDIT-HI"))
    led.append(_entry(2, "reject", 0.40, 0.50, edits_summary="EDIT-LO"))
    led.append(_entry(3, "reject", 0.50, 0.50, edits_summary="EDIT-MID"))
    out = led.render()
    assert out.index("EDIT-LO") < out.index("EDIT-MID") < out.index("EDIT-HI")


def test_render_marks_action_delta_and_cell_movement():
    led = RejectionLedger()
    led.append(_entry(2, "reject", 0.40, 0.45, cell=5, parent_cell=5, edits_summary="stay"))
    led.append(_entry(3, "accept", 0.50, 0.45, cell=9, parent_cell=5, edits_summary="move"))
    out = led.render()
    assert "被拒" in out and "接受" in out
    assert "-0.05" in out and "+0.05" in out
    assert "cell 5→5（行为未移动）" in out
    assert "cell 5→9" in out


def test_render_respects_char_budget_and_folds_oldest():
    led = RejectionLedger()
    for step in range(1, 11):
        led.append(_entry(step, "reject", 0.40, 0.45, edits_summary=f"direction-{step:02d}"))
    out = led.render(char_budget=400, top_m=10)
    assert len(out) <= 400
    assert "direction-10" in out          # newest survives
    assert "direction-01" not in out      # oldest dropped first
    n_shown = sum(1 for s in range(1, 11) if f"direction-{s:02d}" in out)
    assert f"另有 {10 - n_shown} 条更早记录未列出" in out


def test_render_selection_keeps_best_accept_and_biggest_reject_beyond_recency():
    led = RejectionLedger()
    led.append(_entry(1, "accept", 0.70, 0.40, edits_summary="OLD-BEST-ACCEPT"))
    led.append(_entry(2, "reject", 0.10, 0.40, edits_summary="OLD-BIG-REJECT"))
    for step in range(3, 9):
        led.append(_entry(step, "reject", 0.39, 0.40, edits_summary=f"recent-{step}"))
    out = led.render(top_m=2)
    assert "OLD-BEST-ACCEPT" in out
    assert "OLD-BIG-REJECT" in out
    assert "recent-8" in out and "recent-7" in out   # recency window
    assert "recent-3" not in out                      # not selected


def test_render_shows_task_flips():
    led = RejectionLedger()
    led.append(_entry(
        2, "reject", 0.40, 0.45,
        task_flips=(("1024", 1, 0), ("1003", 0, 1)),
        edits_summary="rewrite section 4",
    ))
    out = led.render()
    assert "#1024 对→错" in out
    assert "#1003 错→对" in out


def test_render_prefers_lesson_but_keeps_evidence():
    led = RejectionLedger()
    led.append(_entry(
        2, "reject", 0.40, 0.45,
        edits_summary="raw edit text",
        lesson="defensive try/except guidance hurts formula tasks",
    ))
    out = led.render()
    assert "defensive try/except guidance hurts formula tasks" in out
    assert "0.45→0.4" in out          # evidence line always attached
    assert "raw edit text" not in out  # lesson replaces the raw summary
