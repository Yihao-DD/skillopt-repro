"""T002 — descriptor v0 tests (behavioral fingerprint from trajectory).

Validates the Tier-A code-level descriptor (`qd/descriptor.py`):
  - φ(τ) is bounded in [0,1]^p and deterministic;
  - `code_features` parses library/control-flow/op strategy from generated code;
  - **stability (SPEC 命题 3.2)**: a skill's behavior point b is stable under
    probe-set resampling (small per-axis std) — uses the real SpreadsheetBench
    best-skill trajectory fixture;
  - **separation (命题 3.8 dep ii)**: best vs initial land at different b
    (best leans openpyxl+complexity, initial leans pandas) — the behavioral gap
    result-level fields could NOT see.

Fixtures: qd/tests/fixtures/ssb_{best,initial}_feat.jsonl (279 per-task
code-feature records each, extracted from outputs/ssb_dpsk_run1). Zero API.
"""
from __future__ import annotations

import json
import os
import random
import statistics as st

from qd.descriptor import (
    PHI_LABELS,
    code_features,
    descriptor,
    mu,
    phi,
    project,
)

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> list[dict]:
    with open(os.path.join(_FIX, name), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ── φ bounded + deterministic ─────────────────────────────────────────────────

def test_phi_bounded_and_sized() -> None:
    for fx in ("ssb_best_feat.jsonl", "ssb_initial_feat.jsonl"):
        for t in _load(fx):
            v = phi(t)
            assert len(v) == len(PHI_LABELS) == 5
            assert all(0.0 <= x <= 1.0 for x in v), f"out-of-range φ={v}"


def test_phi_deterministic() -> None:
    t = _load("ssb_best_feat.jsonl")[0]
    assert phi(t) == phi(t)


# ── code parsing ──────────────────────────────────────────────────────────────

def test_code_features_parsing() -> None:
    code = (
        "import pandas as pd\n"
        "import openpyxl\n"
        "for i in range(3):\n"
        "    if i:\n"
        "        pd.read_excel('x')\n"
        "wb.cell(1, 1).value = 5\n"
    )
    f = code_features(code)
    assert f["uses_pandas"] == 1
    assert f["uses_openpyxl"] == 1
    assert f["n_ctrl"] == 2  # one for + one if
    assert f["n_ops"] >= 2   # read_excel + .cell(
    assert code_features("")["lines"] == 0


def test_phi_accepts_raw_code() -> None:
    v = phi({"code": "import openpyxl\nfor r in rows:\n    ws.cell(r,1)\n", "n_turns": 2})
    assert len(v) == 5 and all(0.0 <= x <= 1.0 for x in v)
    assert v[1] == 0.0  # no pandas


# ── stability under probe resampling (命题 3.2) ───────────────────────────────

def test_descriptor_stable_under_probe_resampling() -> None:
    trajs = _load("ssb_best_feat.jsonl")
    rng = random.Random(0)
    points = []
    for _ in range(30):
        sub = rng.sample(trajs, 50)  # probe set size m=50
        points.append(descriptor(sub).b)
    for axis in (0, 1):
        sd = st.pstdev(p[axis] for p in points)
        assert sd < 0.08, f"axis {axis} unstable under resampling: sd={sd:.4f}"


def test_cell_deterministic_and_in_range() -> None:
    trajs = _load("ssb_best_feat.jsonl")
    d1 = descriptor(trajs, nbins=4)
    d2 = descriptor(trajs, nbins=4)
    assert d1 == d2
    assert 0 <= d1.cell < 16


# ── separation: best vs initial (命题 3.8 dep ii) ─────────────────────────────

def test_descriptor_separates_best_from_initial() -> None:
    best = descriptor(_load("ssb_best_feat.jsonl"))
    initial = descriptor(_load("ssb_initial_feat.jsonl"))
    # library-strategy axis (1 - pandas): initial uses pandas more → lower.
    assert best.b[1] > initial.b[1], (best.b, initial.b)
    # behavior points are not identical (unlike result-level fields).
    assert best.b != initial.b


def test_strategy_axis_tracks_pandas_usage() -> None:
    # μ separates on the pandas axis even if the projected cells happen to share a bin.
    mu_best = mu(_load("ssb_best_feat.jsonl"))
    mu_init = mu(_load("ssb_initial_feat.jsonl"))
    assert mu_init[1] > mu_best[1]  # initial has higher mean uses_pandas
    assert project(mu_best)[1] > project(mu_init)[1]
