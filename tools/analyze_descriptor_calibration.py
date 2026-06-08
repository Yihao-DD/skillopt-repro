"""Descriptor calibration analysis (REORG, zero-API).

The DeepSeek feasibility spike showed the current 2-axis grid is too coarse on
real code (3/4 strategies collapsed to cell 0). This reads the 558 REAL
SpreadsheetBench fixture records (best+initial code features) and reports the raw
feature percentiles + how many grid cells the real data occupies under the
current vs candidate normalization refs / nbins — so the recalibration is
data-driven, not guessed.

Run:  python tools/analyze_descriptor_calibration.py
"""
import json
import math
import os
import statistics as st
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qd.descriptor import _CTRL_REF, _LINES_REF, _clip01, cell_of  # noqa: E402

FIX = os.path.join(ROOT, "qd", "tests", "fixtures")


def load(name: str) -> list[dict]:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


recs = load("ssb_best_feat.jsonl") + load("ssb_initial_feat.jsonl")
print(f"n records = {len(recs)}")


def pct(xs, ps=(10, 25, 50, 75, 90, 95, 99)):
    xs = sorted(xs)
    return {p: xs[min(len(xs) - 1, int(p / 100 * len(xs)))] for p in ps}


lines = [r.get("lines", 0) for r in recs]
ctrl = [r.get("n_ctrl", 0) for r in recs]
ops = [r.get("n_ops", 0) for r in recs]
opdens = [r.get("n_ops", 0) / max(r.get("lines", 0), 1) for r in recs]

print("lines  pct:", pct(lines))
print("n_ctrl pct:", pct(ctrl))
print("n_ops  pct:", pct(ops))
print("opdens pct:", {k: round(v, 3) for k, v in pct(opdens).items()})
print("uses_pandas   mean:", round(st.mean(r.get("uses_pandas", 0) for r in recs), 3))
print("uses_openpyxl mean:", round(st.mean(r.get("uses_openpyxl", 0) for r in recs), 3))


def cell_dist(lines_ref: float, ctrl_ref: float, nbins: int, opdens_ref: float = 1.0):
    cells = []
    for r in recs:
        ln = r.get("lines", 0)
        ct = r.get("n_ctrl", 0)
        op = r.get("n_ops", 0)
        code_len = _clip01(ln / lines_ref)
        ctd = _clip01(ct / ctrl_ref)
        opd = _clip01((op / max(ln, 1)) / opdens_ref)
        axis0 = _clip01((code_len + ctd) / 2)
        axis1 = _clip01(opd)
        cells.append(cell_of((axis0, axis1), nbins))
    c = Counter(cells)
    n = len(cells)
    ent = -sum((v / n) * math.log2(v / n) for v in c.values())
    return f"occupied={len(c):2d}/{nbins * nbins}  entropy={ent:.2f}  dist={dict(sorted(c.items()))}"


print(f"\nCURRENT refs (LINES={_LINES_REF}, CTRL={_CTRL_REF}, nbins=4, opdens raw):")
print("  ", cell_dist(_LINES_REF, _CTRL_REF, 4))

print("\nCANDIDATES (rescale op_density by opdens_ref so axis1 spans [0,1]):")
for lr in (90, 117):
    for od in (0.20, 0.15):
        for nb in (4, 5):
            print(f"  LINES_REF={lr:3d} OPDENS_REF={od:.2f} nbins={nb}:  ", cell_dist(lr, 24, nb, od))
