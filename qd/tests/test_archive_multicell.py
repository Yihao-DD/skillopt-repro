from qd.archive import Archive


def test_multicell_accepts_empty_cell_and_rejects_ties() -> None:
    arch = Archive(k=4, baseline_skill="S0", baseline_score=0.50)

    r1 = arch.update("S1", 0.10, step=1, cell=2)
    assert r1.action == "accept"
    assert arch.elite(2).score == 0.10

    tie = arch.update("S1_tie", 0.10, step=2, cell=2)
    assert tie.action == "reject"
    assert arch.elite(2).skill == "S1"


def test_multicell_per_cell_gate_and_global_best_are_monotone() -> None:
    arch = Archive(k=4, baseline_skill="S0", baseline_score=0.50)
    assert arch.best_score == 0.50

    arch.update("S2", 0.40, step=1, cell=2)  # accepted into empty cell, not global best
    assert arch.best_skill == "S0"
    assert arch.best_score == 0.50

    arch.update("S2_bad", 0.39, step=2, cell=2)
    assert arch.elite(2).score == 0.40

    arch.update("S2_good", 0.70, step=3, cell=2)
    assert arch.best_skill == "S2_good"
    assert arch.best_score == 0.70
    assert arch.best_step == 3


def test_k1_still_normalizes_all_updates_to_cell_zero() -> None:
    arch = Archive(k=1, baseline_skill="S0", baseline_score=0.0)
    res = arch.update("S1", 1.0, step=1, cell=99)
    assert res.cell == 0
    assert arch.occupied_cells() == (0,)


def test_unparameterized_archive_is_truly_empty() -> None:
    # Regression: default args used to seed a phantom baseline (skill='', score=-1.0).
    assert Archive(k=4).occupied_cells() == ()
    assert Archive(k=1).occupied_cells() == ()


def test_baseline_can_seed_an_arbitrary_cell() -> None:
    arch = Archive(k=16, baseline_skill="S0", baseline_score=0.5, baseline_cell=7)
    assert arch.occupied_cells() == (7,)
    assert arch.elite(7).skill == "S0"
    assert arch.best_score == 0.5
