"""RED-LINE faithfulness (reflect→MERGE→edits): ``propose`` must route the
reflect output through the SAME aggregate/merge LLM stage the original SkillOpt
trainer uses (``skillopt.gradient.aggregate.merge_patches``), NOT flat-concatenate
every minibatch patch's edits.

Original fork data flow (``SkillOpt/skillopt/engine/trainer.py`` ~1040-1130):
  ② reflect -> raw patches each tagged ``source_type`` "failure"/"success"
  (``_normalise_patches``) split into ``failure_patches`` / ``success_patches``
  ③ ``merge_patches(skill, failure_patches, success_patches, ...,
      meta_skill_context=active_meta_skill)`` -> ONE merged ``{edits, reasoning}``.

So K=1 must produce ``apply(rank(MERGE(patches)))``, not
``apply(rank(CONCAT(patches)))``. These tests fake ``adapter.reflect`` to return
known failure+success raw patches and fake ``merge_patches`` to RECORD that it was
called with the correctly-separated failure/success patch lists, then assert
``propose`` returns the merged edits (proving the merge stage is on the path).

Zero API: both the env adapter and the merge LLM call are faked (duck-typed /
monkeypatched). NEVER hits a real model.
"""
from __future__ import annotations

import skillopt.gradient.aggregate as aggregate_mod

from qd.adapter_skillopt import SkillOptProducer


class _RecordingMerge:
    """Replaces ``merge_patches``; records inputs and returns a sentinel merged patch."""

    def __init__(self, merged: dict):
        self.merged = merged
        self.calls: list[dict] = []

    def __call__(self, skill_content, failure_patches, success_patches,
                 *args, **kwargs):
        self.calls.append({
            "skill_content": skill_content,
            "failure_patches": failure_patches,
            "success_patches": success_patches,
            "args": args,
            "kwargs": kwargs,
        })
        return self.merged


class FakeEnvAdapter:
    """Fakes ``adapter.rollout`` + ``adapter.reflect``; reflect returns labeled raw
    patches exactly like ``run_minibatch_reflect`` (source_type failure/success)."""

    def __init__(self, reflect_return: list[dict]):
        self.reflect_return = reflect_return
        self.reflect_kwargs: list[dict] = []

    def rollout(self, items, skill, outdir):
        return [{"id": "1", "hard": 0}]   # one failing rollout (content irrelevant here)

    def reflect(self, results, skill, outdir, **kwargs):
        self.reflect_kwargs.append(kwargs)
        return self.reflect_return


def _patch_merge(monkeypatch, merged: dict) -> _RecordingMerge:
    rec = _RecordingMerge(merged)
    # propose lazily imports from this module, so patching the module attr is seen.
    monkeypatch.setattr(aggregate_mod, "merge_patches", rec)
    return rec


def _producer(tmp_path, reflect_return, **kw):
    items = []   # merged mode (gen IS sel); irrelevant to the merge routing under test
    return SkillOptProducer(adapter=FakeEnvAdapter(reflect_return),
                            gen_items=items, sel_items=items,
                            out_root=str(tmp_path), **kw)


# Two labeled minibatch patches: one failure-driven, one success-driven.
_FAIL_PATCH = {"patch": {"edits": [{"op": "add", "content": "F1"}]}, "source_type": "failure"}
_SUCC_PATCH = {"patch": {"edits": [{"op": "add", "content": "S1"}]}, "source_type": "success"}
_MERGED = {"edits": [{"op": "add", "content": "MERGED"}], "reasoning": "agg"}


def test_propose_routes_reflect_output_through_merge_stage(tmp_path, monkeypatch):
    rec = _patch_merge(monkeypatch, _MERGED)
    p = _producer(tmp_path, [_FAIL_PATCH, _SUCC_PATCH])

    out = p.propose("SKILL", step=3)

    # merge_patches was called exactly once with the separated failure/success lists.
    assert len(rec.calls) == 1
    call = rec.calls[0]
    assert call["skill_content"] == "SKILL"
    assert call["failure_patches"] == [{"edits": [{"op": "add", "content": "F1"}]}]
    assert call["success_patches"] == [{"edits": [{"op": "add", "content": "S1"}]}]
    # propose returns the MERGED edits — NOT the flat concat of F1+S1.
    assert out["edits"] == [{"op": "add", "content": "MERGED"}]
    assert out["edits"] != [{"op": "add", "content": "F1"}, {"op": "add", "content": "S1"}]


def test_unlabeled_patch_defaults_to_failure_like_trainer(tmp_path, monkeypatch):
    # trainer._normalise_patches defaults missing source_type -> "failure".
    rec = _patch_merge(monkeypatch, _MERGED)
    unlabeled = {"patch": {"edits": [{"op": "add", "content": "U1"}]}}   # no source_type
    p = _producer(tmp_path, [unlabeled])

    p.propose("SKILL", step=1)

    call = rec.calls[0]
    assert call["failure_patches"] == [{"edits": [{"op": "add", "content": "U1"}]}]
    assert call["success_patches"] == []


def test_propose_passes_meta_into_merge_meta_skill_context(tmp_path, monkeypatch):
    # trainer passes meta_skill_context=active_meta_skill to BOTH reflect AND merge.
    rec = _patch_merge(monkeypatch, _MERGED)
    p = _producer(tmp_path, [_FAIL_PATCH])

    p.propose("SKILL", step=1, meta="REMEMBER X")

    # reflect still gets meta (existing behavior, not regressed) ...
    from skillopt.optimizer.meta_skill import format_meta_skill_context
    expected = format_meta_skill_context("REMEMBER X")
    assert p.adapter.reflect_kwargs[-1]["meta_skill_context"] == expected
    # ... and merge now gets the SAME meta_skill_context.
    assert rec.calls[0]["kwargs"].get("meta_skill_context") == expected


def test_propose_uses_patch_update_mode_for_merge(tmp_path, monkeypatch):
    # QD runs use the fork default update_mode="patch" (SpreadsheetBenchAdapter has
    # no _cfg). merge must be called in patch mode so its return carries `edits`.
    rec = _patch_merge(monkeypatch, _MERGED)
    p = _producer(tmp_path, [_FAIL_PATCH])

    p.propose("SKILL", step=1)

    km = rec.calls[0]["kwargs"]
    assert km.get("update_mode", "patch") == "patch"


def test_empty_reflect_returns_no_edits_without_calling_merge(tmp_path, monkeypatch):
    # No patches at all -> nothing to merge (mirrors trainer's skip_no_patches guard).
    rec = _patch_merge(monkeypatch, _MERGED)
    p = _producer(tmp_path, [])

    out = p.propose("SKILL", step=1)

    assert out["edits"] == []
    assert rec.calls == []   # merge LLM stage NOT invoked when there is nothing to merge


def test_buffer_context_still_injected_into_reflect(tmp_path, monkeypatch):
    # Regression guard: faithful-mode step_buffer_context injection must survive.
    from qd.ledger import LedgerEntry, RejectionLedger, skill_fingerprint

    _patch_merge(monkeypatch, _MERGED)
    p = _producer(tmp_path, [_FAIL_PATCH])
    led = RejectionLedger()
    led.append(LedgerEntry(
        step=1, action="reject", score=0.40, parent_score=0.45,
        edits_summary="wrap IO in try/except",
        parent_hash=skill_fingerprint("PARENT"), cand_hash=skill_fingerprint("CAND"),
    ))

    p.propose("PARENT", step=2, ledger=led)

    ctx = p.adapter.reflect_kwargs[-1]["step_buffer_context"]
    assert "wrap IO in try/except" in ctx
