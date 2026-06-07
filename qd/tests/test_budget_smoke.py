from qd.budget import BehaviorCandidate, EvalCounter, deduplicate_by_behavior


def test_deduplicate_by_behavior_keeps_best_probe_per_cell_radius() -> None:
    cands = [
        BehaviorCandidate("A", (0.10, 0.10), cell=1, probe_score=0.2),
        BehaviorCandidate("B", (0.11, 0.10), cell=1, probe_score=0.9),
        BehaviorCandidate("C", (0.80, 0.80), cell=1, probe_score=0.1),
        BehaviorCandidate("D", (0.10, 0.10), cell=2, probe_score=0.3),
    ]

    reps = deduplicate_by_behavior(cands, epsilon=0.05)
    assert [c.skill for c in reps] == ["B", "D", "C"]


def test_eval_counter_tracks_cheap_expensive_and_cache_hits() -> None:
    counter = EvalCounter()
    cands = [
        BehaviorCandidate("A", (0.0, 0.0), cell=0),
        BehaviorCandidate("B", (1.0, 0.0), cell=1),
    ]
    counter.record_probe(n_candidates=4, probe_size=3)
    scores1 = counter.evaluate_expensive(cands, selection_size=20, scorer=lambda c: float(c.cell))
    scores2 = counter.evaluate_expensive(cands, selection_size=20, scorer=lambda c: 999.0)

    assert counter.cheap_rollouts == 12
    assert counter.expensive_evals == 2
    assert counter.expensive_rollouts == 40
    assert counter.cache_hits == 2
    assert scores1 == scores2
