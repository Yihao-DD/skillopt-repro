"""Three-split fidelity (原文 Eq 2/3): propose on D_tr (gen), gate on D_sel (sel).

Zero-API (duck-typed adapter). Faithful-to-paper contract:
  - propose(parent)  rolls out on gen_items (D_tr, generate candidates)
  - score(candidate) rolls out on sel_items (D_sel, the validation gate)
  - probe(candidate) uses the sel_items rollout (behavior cell ~ gate behavior)
  - cache keyed by (skill, set) so gen and sel never collide
  - merged mode (gen_items IS sel_items) collapses to a single rollout (back-compat)
"""
from __future__ import annotations

from qd.adapter_skillopt import SkillOptProducer


class RecordingAdapter:
    def __init__(self):
        self.calls = []  # (items_obj, skill)

    def rollout(self, items, skill, outdir):
        self.calls.append((items, skill))
        return [{"id": x, "hard": 1.0} for x in items]

    def reflect(self, results, skill, outdir, **kwargs):
        return [{"patch": {"edits": [{"text": "E"}]}}]


def _producer(tmp_path, gen, sel):
    return SkillOptProducer(adapter=RecordingAdapter(), gen_items=gen, sel_items=sel, out_root=str(tmp_path))


def test_propose_rolls_gen_and_score_rolls_sel(tmp_path):
    gen, sel = ["g1", "g2"], ["s1", "s2"]
    p = _producer(tmp_path, gen, sel)
    p.propose("SK", step=1)
    p.score("SK")
    # propose used the generation set; score used the selection set.
    assert (gen, "SK") in p.adapter.calls
    assert (sel, "SK") in p.adapter.calls


def test_separate_sets_cache_independently(tmp_path):
    gen, sel = ["g1"], ["s1"]
    p = _producer(tmp_path, gen, sel)
    p.propose("SK", step=1)   # gen rollout
    p.score("SK")             # sel rollout — different set, same skill
    p.propose("SK", step=2)   # gen cache hit
    p.score("SK")             # sel cache hit
    same_skill = [c for c in p.adapter.calls if c[1] == "SK"]
    assert len(same_skill) == 2                       # exactly one gen + one sel
    assert {c[0][0] for c in same_skill} == {"g1", "s1"}


def test_merged_mode_collapses_to_single_rollout(tmp_path):
    both = ["t1", "t2"]
    p = _producer(tmp_path, both, both)               # gen IS sel
    p.propose("SK", step=1)
    p.score("SK")
    p.probe("SK")
    assert len([c for c in p.adapter.calls if c[1] == "SK"]) == 1   # one shared rollout


def test_score_reflects_sel_set_not_gen(tmp_path):
    # gen all-correct, sel all-wrong -> score must read the SEL rollout.
    class Split(RecordingAdapter):
        def rollout(self, items, skill, outdir):
            self.calls.append((items, skill))
            hard = 1.0 if items is gen else 0.0
            return [{"id": x, "hard": hard} for x in items]

    gen, sel = ["g1", "g2"], ["s1", "s2"]
    p = SkillOptProducer(adapter=Split(), gen_items=gen, sel_items=sel, out_root=str(tmp_path))
    assert p.score("SK") == 0.0                       # gate score from sel, not gen
