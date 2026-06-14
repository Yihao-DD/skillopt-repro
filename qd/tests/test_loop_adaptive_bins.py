"""Adaptive binning in run_search (task #11): warmup-calibrate a frozen CellGrid.

The live archive collapses because cell_of() bins on a fixed [0,1] grid calibrated
for cross-TASK spread, while a SEARCH occupies a narrow band. With ``adaptive_bins``,
K>1 collects the behavior points of the first ``warmup_evals`` candidates, calibrates
a frozen quantile :class:`~qd.descriptor.CellGrid`, re-bins the archive, and bins the
rest of the search by it — so a narrow-band producer occupies far more cells.

Red lines (zero API): adaptive OFF == native (the 118 existing tests); equal budget
preserved (warmup = normal evals, no extra); K=1 untouched (single cell).
"""
from __future__ import annotations

from qd.loop import CandidateProducer, run_search

# 16 narrow-band behaviors: complexity (lines/234) stays in ONE native axis-0 bin,
# but spans 4 distinct values a quantile grid resolves; op-density varies too.
_COMBOS = [(40 + (i % 4) * 5, 1 + (i // 4) * 2) for i in range(16)]  # (lines, n_ops)


def _code(lines: int, nops: int) -> str:
    ops = ["ws.cell(1, 1)"] * nops          # ".cell(" -> op-density signal
    return "\n".join(ops + ["x = 1"] * max(0, lines - nops))


def _narrow_producer() -> CandidateProducer:
    n = {"i": 0}

    def propose(skill, *, step, target_cell=None, ledger=None, meta=""):
        return {"edits": [{"text": "+"}]}

    def apply(skill, patch):
        i = n["i"]
        n["i"] += 1
        return f"S|{i}"                       # fresh distinct skill carrying its index

    def score(skill):
        return 0.5 + 0.0001 * int(skill.rsplit("|", 1)[-1])   # mild monotone

    def probe(skill):
        lines, nops = _COMBOS[int(skill.rsplit("|", 1)[-1]) % 16]
        return [{"code": _code(lines, nops)}]

    return CandidateProducer(propose=propose, apply=apply, score=score, probe=probe)


_KW = dict(k=16, baseline_skill="S|0", baseline_score=0.4, eval_budget=48,
           candidates_per_step=4, baseline_cell=0, baseline_b=(0.171, 0.125))


def test_adaptive_bins_spreads_more_cells_than_native() -> None:
    native = run_search(producer=_narrow_producer(), adaptive_bins=False, **_KW)
    adaptive = run_search(producer=_narrow_producer(), adaptive_bins=True, warmup_evals=16, **_KW)
    assert native.expensive_evals == adaptive.expensive_evals == 48   # equal budget preserved
    assert adaptive.n_occupied > native.n_occupied                    # calibration spreads the band
    assert adaptive.n_occupied >= 8                                   # narrow band now fills many cells


def test_adaptive_bins_without_baseline_b_falls_back_to_native() -> None:
    kw = {**_KW}
    kw.pop("baseline_b")
    r = run_search(producer=_narrow_producer(), adaptive_bins=True, warmup_evals=16, baseline_b=None, **kw)
    assert r.expensive_evals == 48          # no crash, runs to budget (uniform grid)


def test_k1_ignores_adaptive_bins() -> None:
    def propose(skill, *, step, target_cell=None, ledger=None, meta=""):
        return {"edits": [{"text": f".x{step}"}]}

    prod = CandidateProducer(propose=propose,
                             apply=lambda s, p: s + "".join(e["text"] for e in p.get("edits", [])),
                             score=lambda s: 0.1)   # step-distinct candidates (no cache-hit stall)
    r = run_search(k=1, baseline_skill="B", baseline_score=0.9, eval_budget=4, producer=prod,
                   adaptive_bins=True, warmup_evals=2, baseline_b=(0.3, 0.3))
    assert r.expensive_evals == 4
    assert r.n_occupied == 1                # K=1 stays single-cell regardless of adaptive_bins
