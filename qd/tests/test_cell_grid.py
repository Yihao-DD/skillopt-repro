"""Adaptive behavior grid (qd.descriptor.CellGrid).

The live archive collapses to ~2-4/16 cells because cell_of() bins on a fixed [0,1]
grid calibrated for 558 diverse TASKS, while a SEARCH occupies a narrow band of that
space. CellGrid lets the archive calibrate per-axis QUANTILE boundaries from the
search distribution (a warmup of behavior points) and freeze them — recovering the
spread (validated offline: native 2-4/16 -> quantile 13-15/16 on held-out skills).

Contracts (pure stdlib, zero API):
  - the uniform default grid is byte-for-byte ``cell_of`` (back-compat red line);
  - a grid calibrated on a NARROW band spreads those same points across many cells.
"""
from __future__ import annotations

from qd.descriptor import CellGrid, cell_of


def test_uniform_grid_matches_cell_of() -> None:
    g = CellGrid.uniform(nbins=4)
    for b in [(0.0, 0.0), (0.1, 0.9), (0.5, 0.5), (0.74, 0.26), (0.99, 0.99)]:
        assert g.cell_of(b) == cell_of(b, 4)


def test_calibrated_grid_spreads_a_narrow_band() -> None:
    # 40 points in a tiny 2-D band near the origin (x,y vary independently, like the
    # real complexity/op-density axes): the fixed [0,1] grid lumps them into ~1 cell;
    # a quantile-calibrated grid must spread them across many cells.
    pts = [(0.10 + 0.002 * (i % 8), 0.05 + 0.0015 * (i // 8)) for i in range(40)]
    native = len({cell_of(p, 4) for p in pts})
    g = CellGrid.calibrate(pts, nbins=4)
    spread = len({g.cell_of(p) for p in pts})
    assert native <= 2                      # the live collapse
    assert spread >= 8                      # adaptive binning recovers spread


def test_calibrated_grid_is_frozen_and_deterministic() -> None:
    pts = [(0.10 + 0.002 * i, 0.05 + 0.0015 * i) for i in range(40)]
    g = CellGrid.calibrate(pts, nbins=4)
    # same point -> same cell on repeat (frozen edges, no re-fit)
    assert g.cell_of((0.12, 0.06)) == g.cell_of((0.12, 0.06))
    # a point below all edges lands in cell 0; above all edges in the last cell
    assert g.cell_of((-1.0, -1.0)) == 0
    assert g.cell_of((9.0, 9.0)) == 4 * 4 - 1
