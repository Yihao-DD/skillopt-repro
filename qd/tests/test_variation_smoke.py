from qd.archive import Archive
from qd.variation import CandidateEdit, VariationRequest, build_variation_prompt, select_candidate_edits


def test_variation_prompt_includes_archive_and_novelty_contract() -> None:
    arch = Archive(k=4, baseline_skill="S0", baseline_score=0.5)
    arch.update("S2", 0.4, step=1, cell=2)
    prompt = build_variation_prompt(arch, VariationRequest(n_candidates=4, min_novel=2, top_k=8, top_p=0.9))

    assert "Return 4 bounded edit candidates" in prompt
    assert "At least 2 candidates" in prompt
    assert "cell=0 score=0.5" in prompt
    assert "cell=2 score=0.4" in prompt
    assert "top_k=8" in prompt and "top_p=0.9" in prompt


def test_select_candidate_edits_honors_novelty_quota_when_available() -> None:
    req = VariationRequest(n_candidates=3, min_novel=2)
    candidates = [
        CandidateEdit({"edits": []}, parent_cell=0, target_cell=0, priority=10),
        CandidateEdit({"edits": []}, parent_cell=0, target_cell=1, priority=5),
        CandidateEdit({"edits": []}, parent_cell=0, target_cell=2, priority=4),
        CandidateEdit({"edits": []}, parent_cell=0, target_cell=0, priority=3),
    ]

    selected = select_candidate_edits(candidates, req)
    assert len(selected) == 3
    assert sum(c.is_novel for c in selected) >= 2
    assert selected[0].target_cell == 1
    assert selected[1].target_cell == 2


def test_select_keeps_distinct_value_equal_candidates() -> None:
    # Regression: previous `cand not in selected` value-dedup collapsed two distinct
    # but value-equal candidates into one (returned 1 for n_candidates=2).
    req = VariationRequest(n_candidates=2, min_novel=2)
    a = CandidateEdit({"edits": []}, parent_cell=0, target_cell=1, priority=5.0)
    b = CandidateEdit({"edits": []}, parent_cell=0, target_cell=1, priority=5.0)
    assert a == b and a is not b  # value-equal, distinct objects
    selected = select_candidate_edits([a, b], req)
    assert len(selected) == 2


def test_strict_novelty_raises_when_quota_unmet() -> None:
    import pytest

    req = VariationRequest(n_candidates=3, min_novel=2)
    cands = [
        CandidateEdit({"edits": []}, parent_cell=0, target_cell=0, priority=3.0),  # not novel
        CandidateEdit({"edits": []}, parent_cell=0, target_cell=1, priority=2.0),  # 1 novel
    ]
    assert len(select_candidate_edits(cands, req)) == 2  # best-effort: no raise
    with pytest.raises(ValueError):
        select_candidate_edits(cands, req, strict_novelty=True)
