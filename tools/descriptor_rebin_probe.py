"""Offline descriptor RE-BIN probe (zero-API).

Question: is the live archive's ~2/16-cell collapse a DESCRIPTOR artifact, or a
REAL "editing the skill barely changes generated behavior" fact?

Method: reuse cached generated code
    runs/<run>/<arm>/<skill_hash>/predictions/<task_id>/code.py
from prior DeepSeek runs. Group DISTINCT skills that were probed on an IDENTICAL
task set (so the task set is FIXED — we measure SKILL-induced diversity, not the
task-induced diversity the descriptor was calibrated on). Then look at each skill
through three lenses (mean over the fixed task set) plus one confound-free linchpin.

  D0 = current LIVE descriptor (qd.descriptor): complexity x op-density, 4x4 grid.
  D1 = richer hand-coded code metrics  -> PCA 2D -> 4x4 (min-max binned).
  D2 = TF-IDF code embedding           -> PCA 2D -> 4x4 (the "learned descriptor" proxy).
  Metric A (linchpin) = per-task code variation across skills: do different skills
       actually emit STRUCTURALLY different programs for the SAME task? (identifier-
       abstracted token signature; cosmetic var-name / comment diffs do not count.)

Interpretation:
  - Metric A near-zero (skills -> same program structure) => REAL collapse: no
    descriptor can manufacture diversity from identical artifacts -> honest negative.
  - Metric A high but D0 occupancy << D1/D2 occupancy => DESCRIPTOR artifact: the
    skills DO vary, the current axes just bin them together -> salvage via descriptor.
  - Metric A high and ALL descriptors stay flat => behavioral diversity genuinely
    low despite textual variation -> QD weak here.

Run:  python tools/descriptor_rebin_probe.py
Pure offline: reads only cached files, writes one JSON report. Zero API.
"""
from __future__ import annotations

import io
import itertools
import json
import keyword
import math
import os
import re
import sys
import tokenize
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

from qd.descriptor import cell_of, code_features
from qd.descriptor import mu as d0_mu
from qd.descriptor import project as d0_project

RUNS = os.path.join(ROOT, "runs")
NBINS = 4
N_CELLS = NBINS * NBINS
MIN_SKILLS = 8       # need enough distinct skills to talk about spread
MIN_TASKS = 10       # need enough tasks for a stable per-skill mean
TOP_COHORTS = 5
_API_RE = re.compile(r"\.([A-Za-z_]\w*)\s*\(")


# ── discovery ────────────────────────────────────────────────────────────────
def discover() -> dict:
    """{(run, arm, skill_hash): {task_id: code}} from the rollout cache."""
    skills: dict = {}
    for dirpath, _dirs, _files in os.walk(RUNS):
        if os.path.basename(dirpath) != "predictions":
            continue
        skill_dir = os.path.dirname(dirpath)
        skill_hash = os.path.basename(skill_dir)
        rel = os.path.relpath(skill_dir, RUNS).split(os.sep)
        run = rel[0]
        arm = rel[1] if len(rel) > 2 else "?"
        code_by_task: dict = {}
        for tid in os.listdir(dirpath):
            cp = os.path.join(dirpath, tid, "code.py")
            if os.path.isfile(cp):
                try:
                    with open(cp, encoding="utf-8", errors="ignore") as f:
                        code_by_task[tid] = f.read()
                except OSError:
                    pass
        if code_by_task:
            skills[(run, arm, skill_hash)] = code_by_task
    return skills


def cohorts(skills: dict) -> list:
    """Group distinct skills (dedup by hash) that share an IDENTICAL task set."""
    buckets: dict = defaultdict(dict)
    for (run, _arm, sh), cbt in skills.items():
        buckets[(run, frozenset(cbt.keys()))].setdefault(sh, cbt)
    out = []
    for (run, taskset), sk in buckets.items():
        if len(sk) >= MIN_SKILLS and len(taskset) >= MIN_TASKS:
            out.append({"run": run, "tasks": sorted(taskset), "skills": sk})
    out.sort(key=lambda c: -len(c["skills"]))
    return out


# ── features / signatures ────────────────────────────────────────────────────
def rich_features(code: str) -> list:
    f = code_features(code)
    lines = f["lines"] or 1
    apis = set(_API_RE.findall(code))
    indents = [len(ln) - len(ln.lstrip(" ")) for ln in code.splitlines() if ln.strip()]
    return [
        f["lines"], f["n_ctrl"], f["n_ops"], f["n_ops"] / lines,
        code.count("import "), len(apis),
        (max(indents) if indents else 0) // 4,
        len(re.findall(r"\bdef\b", code)), len(re.findall(r"\btry\b", code)),
        float(f["uses_pandas"]), float(f["uses_openpyxl"]), len(re.findall(r"\bfor\b", code)),
    ]


def sig_struct(code: str) -> str:
    """Identifier-abstracted token signature: keeps keywords, operators, and
    ATTRIBUTE/method names (the op-density / API behavioral signal), but abstracts
    bare variable names -> N, numbers -> 0, strings -> S, and drops comments. So
    two programs with the same API structure but different var names / comments
    collapse to the same signature (cosmetic diversity does not count)."""
    try:
        out, prev = [], None
        for t in tokenize.generate_tokens(io.StringIO(code).readline):
            tt, ts = t.type, t.string
            if tt in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                      tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            if tt == tokenize.NAME:
                out.append(ts if (keyword.iskeyword(ts) or prev == ".") else "N")
            elif tt == tokenize.NUMBER:
                out.append("0")
            elif tt == tokenize.STRING:
                out.append("S")
            else:
                out.append(ts)
            prev = ts
        return " ".join(out)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return re.sub(r"\s+", " ", re.sub(r"#.*", "", code)).strip()


def _jacc(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


# ── binning / spread helpers ─────────────────────────────────────────────────
def _entropy(cells: list) -> float:
    counts: dict = defaultdict(int)
    for c in cells:
        counts[c] += 1
    n = len(cells)
    return -sum((v / n) * math.log2(v / n) for v in counts.values())


def occ_native(points: np.ndarray) -> tuple:
    cells = [cell_of((float(x), float(y)), NBINS) for x, y in points]
    return len(set(cells)), _entropy(cells)


def _minmax(arr: np.ndarray) -> np.ndarray:
    lo, hi = arr.min(0), arr.max(0)
    rng = np.where(hi > lo, hi - lo, 1.0)
    return (arr - lo) / rng


def occ_minmax(points: np.ndarray) -> tuple:
    return occ_native(_minmax(points))


def mean_pair_dist(points: np.ndarray) -> float:
    """Mean pairwise euclidean distance on min-max'd coords, normalized by sqrt(2)
    (the max distance in the unit square) so 0 = identical, ~1 = maximally spread."""
    p = _minmax(points)
    m = len(p)
    if m < 2:
        return 0.0
    tot, cnt = 0.0, 0
    for i in range(m):
        d = np.sqrt(((p[i + 1:] - p[i]) ** 2).sum(1))
        tot += float(d.sum())
        cnt += len(d)
    return tot / cnt / math.sqrt(2.0)


def reduce2(X: np.ndarray) -> np.ndarray:
    if X.shape[1] <= 2:
        return X
    Xs = StandardScaler().fit_transform(X)
    return PCA(n_components=2, random_state=0).fit_transform(Xs)


# ── per-cohort analysis ──────────────────────────────────────────────────────
def analyze(cohort: dict) -> dict:
    tasks = cohort["tasks"]
    items = sorted(cohort["skills"].items())          # [(hash, {task: code})]

    # per-skill mean over the fixed task set
    d0_pts, d1_rows, d2_docs = [], [], []
    for _h, cbt in items:
        codes = [cbt[t] for t in tasks]
        d0_pts.append(d0_project(d0_mu([{"code": c} for c in codes])))
        d1_rows.append(np.mean([rich_features(c) for c in codes], axis=0))
        d2_docs.append("\n".join(codes))
    d0_pts = np.asarray(d0_pts, float)
    d1 = reduce2(np.asarray(d1_rows, float))
    tf = TfidfVectorizer(token_pattern=r"[A-Za-z_][A-Za-z0-9_.]+", max_features=4000).fit_transform(d2_docs)
    d2 = PCA(n_components=2, random_state=0).fit_transform(tf.toarray())

    d0_native = occ_native(d0_pts)
    d0_mm = occ_minmax(d0_pts)
    d1_mm = occ_minmax(d1)
    d2_mm = occ_minmax(d2)

    # Metric A — per-task structural variation across skills
    raw_d, struct_d, jac, struct_le2 = [], [], [], 0
    for t in tasks:
        codes = [cbt[t] for _h, cbt in items]
        sigs = [sig_struct(c) for c in codes]
        raw_d.append(len(set(codes)))
        sd = len(set(sigs))
        struct_d.append(sd)
        struct_le2 += int(sd <= 2)
        tok = [set(s.split()) for s in sigs]
        pairs = list(itertools.combinations(range(len(tok)), 2))
        jac.append(np.mean([_jacc(tok[i], tok[j]) for i, j in pairs]) if pairs else 0.0)

    return {
        "run": cohort["run"], "n_skills": len(items), "n_tasks": len(tasks),
        "D0_live_native": {"occupied": d0_native[0], "entropy": round(d0_native[1], 3),
                           "pair_dist": round(mean_pair_dist(d0_pts), 3)},
        "D0_minmax": {"occupied": d0_mm[0], "entropy": round(d0_mm[1], 3)},
        "D1_hand_minmax": {"occupied": d1_mm[0], "entropy": round(d1_mm[1], 3),
                           "pair_dist": round(mean_pair_dist(d1), 3)},
        "D2_embed_minmax": {"occupied": d2_mm[0], "entropy": round(d2_mm[1], 3),
                            "pair_dist": round(mean_pair_dist(d2), 3)},
        "metricA": {
            "mean_raw_distinct": round(float(np.mean(raw_d)), 2),
            "mean_struct_distinct": round(float(np.mean(struct_d)), 2),
            "max_struct_distinct": int(np.max(struct_d)),
            "frac_tasks_struct_le2": round(struct_le2 / len(tasks), 3),
            "mean_pair_jaccard": round(float(np.mean(jac)), 3),
        },
    }


def interpret(a: dict) -> str:
    mA = a["metricA"]
    structurally_collapsed = mA["mean_struct_distinct"] <= 1.5 and mA["mean_pair_jaccard"] < 0.15
    d0 = a["D0_minmax"]["occupied"]
    best_alt = max(a["D1_hand_minmax"]["occupied"], a["D2_embed_minmax"]["occupied"])
    if structurally_collapsed:
        return ("REAL COLLAPSE — distinct skills emit near-identical program structure "
                f"(mean struct-distinct {mA['mean_struct_distinct']}, jaccard {mA['mean_pair_jaccard']}). "
                "No descriptor can manufacture diversity from identical artifacts -> honest negative.")
    if best_alt >= max(6, 2 * max(d0, 1)) and d0 <= 3:
        return ("DESCRIPTOR ARTIFACT — skills DO vary structurally, but the current axes bin them "
                f"into {d0} cells while a richer/learned descriptor reaches {best_alt} -> swap the descriptor.")
    return ("MIXED — skills vary textually but behavioral spread stays low under every descriptor "
            f"(D0={d0}, best alt={best_alt}); diversity is genuinely thin, QD has little to illuminate.")


def main() -> None:
    if not os.path.isdir(RUNS):
        print(f"no runs/ cache at {RUNS}")
        return
    skills = discover()
    cs = cohorts(skills)
    print(f"discovered {len(skills)} (run,arm,skill) dirs -> {len(cs)} comparable cohorts "
          f"(>={MIN_SKILLS} skills on an identical >={MIN_TASKS}-task set)\n")
    if not cs:
        print("No cohort large enough — need more distinct skills on one fixed task set.")
        return

    results = []
    for cohort in cs[:TOP_COHORTS]:
        a = analyze(cohort)
        a["verdict"] = interpret(a)
        results.append(a)
        print(f"== cohort '{a['run']}'  ({a['n_skills']} skills x {a['n_tasks']} fixed tasks) ==")
        print(f"  D0 live (native bins)  occupied {a['D0_live_native']['occupied']:>2}/16   "
              f"entropy {a['D0_live_native']['entropy']:.2f}   pair-dist {a['D0_live_native']['pair_dist']:.3f}")
        print(f"  D0 (min-max bins)      occupied {a['D0_minmax']['occupied']:>2}/16")
        print(f"  D1 hand (min-max)      occupied {a['D1_hand_minmax']['occupied']:>2}/16   "
              f"pair-dist {a['D1_hand_minmax']['pair_dist']:.3f}")
        print(f"  D2 embed (min-max)     occupied {a['D2_embed_minmax']['occupied']:>2}/16   "
              f"pair-dist {a['D2_embed_minmax']['pair_dist']:.3f}")
        mA = a["metricA"]
        print(f"  Metric A  struct-distinct/task mean {mA['mean_struct_distinct']} (max {mA['max_struct_distinct']}, "
              f"of {a['n_skills']} skills)   tasks<=2-struct {mA['frac_tasks_struct_le2']:.0%}   "
              f"pair-jaccard {mA['mean_pair_jaccard']:.3f}")
        print(f"  -> {a['verdict']}\n")

    out = os.path.join(ROOT, "docs", "DESCRIPTOR-REBIN-probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"min_skills": MIN_SKILLS, "min_tasks": MIN_TASKS, "cohorts": results}, f,
                  indent=2, ensure_ascii=False)
    print(f"saved -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
