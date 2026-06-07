from qd.scheduler import PlateauScheduler, choose_parent_cell, is_plateau


def test_plateau_detection_requires_full_window() -> None:
    assert not is_plateau([0.1, 0.1, 0.1], window=3)
    assert is_plateau([0.5, 0.5, 0.5, 0.5], window=3)
    assert not is_plateau([0.5, 0.5, 0.6, 0.6], window=3)


def test_scheduler_increases_candidates_and_novelty_on_plateau() -> None:
    scheduler = PlateauScheduler(base_n=4, plateau_n=10, window=2, novelty_fraction=0.4)
    normal = scheduler.decide([0.1, 0.2, 0.3])
    plateau = scheduler.decide([0.3, 0.3, 0.3])

    assert not normal.plateau and normal.n_candidates == 4 and normal.min_novel == 0
    assert plateau.plateau and plateau.n_candidates == 10 and plateau.min_novel == 4
    assert plateau.gamma > normal.gamma


def test_choose_parent_cell_uses_gain_uncertainty_and_novelty() -> None:
    stats = {
        0: {"predicted_gain": 0.1, "eval_count": 10, "novelty": 0.0},
        1: {"predicted_gain": 0.0, "eval_count": 1, "novelty": 1.0},
    }
    assert choose_parent_cell(stats, gamma=0.0, beta=0.0) == 0
    assert choose_parent_cell(stats, gamma=0.5, beta=0.0) == 1
