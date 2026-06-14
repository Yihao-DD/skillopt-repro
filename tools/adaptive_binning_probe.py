"""Validate the IMPLEMENTABLE adaptive-binning scheme (zero-API).

The live archive collapses to ~4/16 cells because cell_of() bins the behavior axes
on a fixed [0,1] grid calibrated for 558 diverse TASKS, while a SEARCH occupies a
narrow band. descriptor_rebin showed re-normalizing (min-max) recovers ~13/16, but
min-max is outlier-sensitive and needs the full data up front — not archive-stable.

This validates the scheme we would actually ship: calibrate per-axis QUANTILE
boundaries (or CVT centroids) from a WARMUP subset of skills, FREEZE them, and bin
the remaining (held-out) skills. If held-out occupancy jumps from ~4 (native) to
~12-14 (quantile / CVT), an archive that calibrates its grid from an early warmup
will spread — the prerequisite for the QD search to actually explore.

Reads runs/<run>/<arm>/<hash>/{results.jsonl, predictions/<id>/code.py}. Zero API.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from sklearn.cluster import KMeans

from qd.descriptor import cell_of, descriptor

RUNS = os.path.join(ROOT, "runs")
NBINS = 4
MIN_SKILLS = 24      # need enough skills to split warmup/held-out
MIN_TASKS = 16
TOP_COHORTS = 4
WARMUP_FRAC = 0.5


def _ids(path: str) -> set:
    out = set()
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.add(str(json.loads(line).get("id")))
                except json.JSONDecodeError:
                    pass
    return out


def discover() -> dict:
    skills: dict = {}
    for dirpath, _dirs, files in os.walk(RUNS):
        if "results.jsonl" not in files:
            continue
        rel = os.path.relpath(dirpath, RUNS).split(os.sep)
        if len(rel) < 2:
            continue
        try:
            ids = _ids(os.path.join(dirpath, "results.jsonl"))
        except OSError:
            continue
        if ids:
            skills[(rel[0], os.path.basename(dirpath))] = {"dir": dirpath, "ids": ids}
    return skills


def cohorts(skills: dict) -> list:
    buckets: dict = defaultdict(dict)
    for (run, sh), v in skills.items():
        buckets[(run, frozenset(v["ids"]))].setdefault(sh, v["dir"])
    out = [{"run": run, "tasks": sorted(ts), "skills": sk}
           for (run, ts), sk in buckets.items() if len(sk) >= MIN_SKILLS and len(ts) >= MIN_TASKS]
    out.sort(key=lambda c: -len(c["skills"]))
    return out


def _point(skill_dir: str, tasks: list):
    trajs = []
    for t in tasks:
        cp = os.path.join(skill_dir, "predictions", t, "code.py")
        if os.path.isfile(cp):
            try:
                with open(cp, encoding="utf-8", errors="ignore") as f:
                    trajs.append({"code": f.read()})
            except OSError:
                pass
    return descriptor(trajs).b if trajs else None


def _quantile_edges(pts: np.ndarray) -> tuple:
    qs = [25, 50, 75]
    return (np.percentile(pts[:, 0], qs), np.percentile(pts[:, 1], qs))


def _quant_cell(b, edges) -> int:
    ex, ey = edges
    return int(np.searchsorted(ex, b[0])) * NBINS + int(np.searchsorted(ey, b[1]))


def analyze(cohort: dict) -> dict | None:
    tasks = cohort["tasks"]
    pts = []
    for _h, d in sorted(cohort["skills"].items()):
        b = _point(d, tasks)
        if b is not None:
            pts.append(b)
    pts = np.asarray(pts, float)
    if len(pts) < MIN_SKILLS:
        return None
    w = int(len(pts) * WARMUP_FRAC)
    warm, held = pts[:w], pts[w:]

    native = len({cell_of((x, y), NBINS) for x, y in held})
    edges = _quantile_edges(warm)
    quant = len({_quant_cell(b, edges) for b in held})
    km = KMeans(n_clusters=NBINS * NBINS, n_init=5, random_state=0).fit(warm)
    cvt = len(set(km.predict(held)))

    return {
        "run": cohort["run"], "n_skills": len(pts), "n_warmup": w, "n_heldout": len(held),
        "heldout_native_cells": native,
        "heldout_quantile_cells": quant,
        "heldout_cvt_cells": cvt,
    }


def main() -> None:
    cs = cohorts(discover())
    print(f"-> {len(cs)} cohorts; warmup-calibrated binning on held-out skills (of 16 cells)\n")
    results = []
    for cohort in cs[:TOP_COHORTS]:
        a = analyze(cohort)
        if a is None:
            continue
        results.append(a)
        print(f"== '{a['run']}'  ({a['n_skills']} skills: {a['n_warmup']} warmup / {a['n_heldout']} held-out) ==")
        print(f"  native [0,1] grid      {a['heldout_native_cells']:>2}/16   (the live collapse)")
        print(f"  quantile (warmup)      {a['heldout_quantile_cells']:>2}/16")
        print(f"  CVT centroids (warmup) {a['heldout_cvt_cells']:>2}/16")
        verdict = ("RECOVERS" if max(a["heldout_quantile_cells"], a["heldout_cvt_cells"]) >= 3 * max(a["heldout_native_cells"], 1)
                   else "weak")
        print(f"  -> warmup-calibrated binning {verdict} the spread\n")

    out = os.path.join(ROOT, "docs", "ADAPTIVE-BINNING-probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"warmup_frac": WARMUP_FRAC, "cohorts": results}, f, indent=2, ensure_ascii=False)
    print(f"saved -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
