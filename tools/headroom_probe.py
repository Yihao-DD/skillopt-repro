"""Offline HEADROOM probe (zero-API) — can QD beat greedy here AT ALL?

The goal is a GAIN over greedy on best-score, not coverage. A diverse archive can
only beat the single best skill if behaviorally-distinct elites solve COMPLEMENTARY
tasks (building blocks a recombiner/selector can harvest). If the best single skill
already solves (almost) every task any skill solves, NO descriptor / binning /
operator can make QD win — that is a hard ceiling.

This probe reads cached per-task correctness (results.jsonl: {id, hard}) and the
generated code (for the live D0 behavior cell) from
    runs/<run>/<arm>/<skill_hash>/{results.jsonl, predictions/<id>/code.py}
holds the task set FIXED, dedups distinct skills, and reports per cohort:

  greedy_best        = max over skills of per-task solve-rate      (greedy ceiling)
  archive_union      = tasks solved by >=1 D0-cell ELITE (best per cell)
  recomb_best2/4     = set-cover greedy union of 2 / 4 skills       (realistic recomb ceiling)
  union_all          = tasks solved by >=1 skill                    (loose ceiling)
  headroom_*         = (union) - greedy_best  = MAX gain a perfect harvester could add
  cross_cell_pairs   = complementary skill pairs that sit in DIFFERENT cells
                       (does the descriptor align with complementarity?)

Interpretation:
  - headroom ~ 0           => no upside; QD cannot beat greedy here -> honest negative.
  - headroom > 0 AND the complementary skills are cross-cell => real, harvestable
    upside aligned with behavior diversity -> the lever is a cross-cell RECOMBINATION
    operator (condition propose on complementary elites), not binning/descriptor.
  - headroom > 0 but complementarity is within-cell => upside exists but the current
    behavior axis does not capture it -> descriptor must target the complementarity axis.

Run:  python tools/headroom_probe.py        (reads cache only, writes one JSON; zero API)
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qd.descriptor import descriptor  # pure stdlib

RUNS = os.path.join(ROOT, "runs")
MIN_SKILLS = 8
MIN_TASKS = 10
TOP_COHORTS = 5


def _solved(results_path: str) -> dict:
    """{task_id: 1/0} from a skill's results.jsonl (hard >= 0.5 == solved)."""
    out: dict = {}
    with open(results_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = str(r.get("id"))
            out[tid] = 1 if float(r.get("hard", 0) or 0) >= 0.5 else 0
    return out


def discover() -> dict:
    """{(run, arm, skill_hash): {dir, solved}} from results.jsonl files."""
    skills: dict = {}
    for dirpath, _dirs, files in os.walk(RUNS):
        if "results.jsonl" not in files:
            continue
        rel = os.path.relpath(dirpath, RUNS).split(os.sep)
        if len(rel) < 2:
            continue
        run, arm, sh = rel[0], (rel[1] if len(rel) > 2 else "?"), os.path.basename(dirpath)
        try:
            sv = _solved(os.path.join(dirpath, "results.jsonl"))
        except OSError:
            continue
        if sv:
            skills[(run, arm, sh)] = {"dir": dirpath, "solved": sv}
    return skills


def cohorts(skills: dict) -> list:
    buckets: dict = defaultdict(dict)
    for (run, _arm, sh), v in skills.items():
        buckets[(run, frozenset(v["solved"].keys()))].setdefault(sh, v)
    out = []
    for (run, taskset), sk in buckets.items():
        if len(sk) >= MIN_SKILLS and len(taskset) >= MIN_TASKS:
            out.append({"run": run, "tasks": sorted(taskset), "skills": sk})
    out.sort(key=lambda c: -len(c["skills"]))
    return out


def _cell(skill_dir: str, tasks: list) -> int | None:
    """Live D0 behavior cell from the skill's generated code over the fixed tasks."""
    trajs = []
    for t in tasks:
        cp = os.path.join(skill_dir, "predictions", t, "code.py")
        if os.path.isfile(cp):
            try:
                with open(cp, encoding="utf-8", errors="ignore") as f:
                    trajs.append({"code": f.read()})
            except OSError:
                pass
    if not trajs:
        return None
    return descriptor(trajs).cell


def _set_cover(solve_sets: list, k: int) -> set:
    """Greedy max-coverage union of k skills."""
    union: set = set()
    pool = list(range(len(solve_sets)))
    for _ in range(k):
        best_i, best_gain = None, 0
        for i in pool:
            g = len(solve_sets[i] - union)
            if g > best_gain:
                best_gain, best_i = g, i
        if best_i is None:
            break
        union |= solve_sets[best_i]
        pool.remove(best_i)
    return union


def analyze(cohort: dict) -> dict:
    tasks = cohort["tasks"]
    n = len(tasks)
    items = sorted(cohort["skills"].items())                       # [(hash, {dir,solved})]
    solve_sets = [frozenset(t for t in tasks if v["solved"].get(t, 0)) for _h, v in items]
    rates = [len(s) / n for s in solve_sets]
    greedy_best = max(rates)

    union_all = set().union(*solve_sets) if solve_sets else set()
    cov_all = len(union_all) / n
    cov2 = len(_set_cover(solve_sets, 2)) / n
    cov4 = len(_set_cover(solve_sets, 4)) / n

    # per-task solver count (saturation check)
    solvers = [sum(1 for s in solve_sets if t in s) for t in tasks]
    partial = sum(1 for c in solvers if 0 < c < len(items))        # tasks SOME-but-not-all solve

    # complementary pairs (each solves >=1 the other fails) + are they cross-cell?
    cells = [_cell(v["dir"], tasks) for _h, v in items]
    comp_pairs = cross_cell = 0
    for i, j in itertools.combinations(range(len(items)), 2):
        a, b = solve_sets[i], solve_sets[j]
        if (a - b) and (b - a):
            comp_pairs += 1
            if cells[i] is not None and cells[j] is not None and cells[i] != cells[j]:
                cross_cell += 1

    # archive ceiling: union over the BEST skill per live D0 cell (the actual elites)
    best_per_cell: dict = {}
    for idx, c in enumerate(cells):
        if c is None:
            continue
        if c not in best_per_cell or rates[idx] > rates[best_per_cell[c]]:
            best_per_cell[c] = idx
    elite_union = set().union(*(solve_sets[i] for i in best_per_cell.values())) if best_per_cell else set()
    archive_union = len(elite_union) / n

    return {
        "run": cohort["run"], "n_skills": len(items), "n_tasks": n,
        "greedy_best": round(greedy_best, 3),
        "archive_union_cellelites": round(archive_union, 3),
        "recomb_best2": round(cov2, 3),
        "recomb_best4": round(cov4, 3),
        "union_all": round(cov_all, 3),
        "headroom_archive": round(archive_union - greedy_best, 3),
        "headroom_best2": round(cov2 - greedy_best, 3),
        "headroom_best4": round(cov4 - greedy_best, 3),
        "headroom_all": round(cov_all - greedy_best, 3),
        "n_cells_occupied": len(best_per_cell),
        "tasks_partial_solved": partial, "tasks_total": n,
        "complementary_pairs": comp_pairs,
        "complementary_pairs_cross_cell": cross_cell,
    }


def interpret(a: dict) -> str:
    hr2, hra = a["headroom_best2"], a["headroom_archive"]
    if a["union_all"] - a["greedy_best"] < 0.02:
        return ("NO HEADROOM — the best single skill already solves ~everything any skill solves "
                f"(greedy {a['greedy_best']} vs union-all {a['union_all']}). No harvester can beat "
                "greedy -> QD cannot win here. Honest negative.")
    aligned = a["complementary_pairs"] and a["complementary_pairs_cross_cell"] / max(a["complementary_pairs"], 1) >= 0.5
    if max(hr2, hra) >= 0.03 and aligned:
        return (f"HARVESTABLE UPSIDE — combining 2 complementary skills could reach {a['recomb_best2']} "
                f"vs greedy {a['greedy_best']} ({hr2:+.3f}); complementarity is mostly CROSS-CELL "
                "-> lever = cross-cell RECOMBINATION operator.")
    if max(hr2, hra) >= 0.03:
        return (f"UPSIDE BUT MIS-ALIGNED — headroom exists ({max(hr2, hra):+.3f}) but complementary "
                "skills are mostly WITHIN the same cell -> the current behavior axis does not capture "
                "the complementarity; redesign the descriptor to target it.")
    return (f"THIN — small headroom (best2 {hr2:+.3f}, archive {hra:+.3f}); upside is marginal, "
            "QD gain over greedy would be small at best.")


def main() -> None:
    if not os.path.isdir(RUNS):
        print(f"no runs/ cache at {RUNS}")
        return
    skills = discover()
    cs = cohorts(skills)
    print(f"discovered {len(skills)} skills with results.jsonl -> {len(cs)} comparable cohorts\n")
    if not cs:
        print("No cohort large enough.")
        return

    results = []
    for cohort in cs[:TOP_COHORTS]:
        a = analyze(cohort)
        a["verdict"] = interpret(a)
        results.append(a)
        print(f"== cohort '{a['run']}'  ({a['n_skills']} skills x {a['n_tasks']} fixed tasks) ==")
        print(f"  greedy best single        {a['greedy_best']:.3f}   (the deliverable both arms search for)")
        print(f"  QD archive (cell elites)  {a['archive_union_cellelites']:.3f}   "
              f"headroom {a['headroom_archive']:+.3f}   ({a['n_cells_occupied']} cells)")
        print(f"  recomb best-2 (set cover) {a['recomb_best2']:.3f}   headroom {a['headroom_best2']:+.3f}")
        print(f"  recomb best-4             {a['recomb_best4']:.3f}   headroom {a['headroom_best4']:+.3f}")
        print(f"  union ALL skills          {a['union_all']:.3f}   headroom {a['headroom_all']:+.3f}")
        print(f"  tasks partially solved    {a['tasks_partial_solved']}/{a['tasks_total']}   "
              f"complementary pairs {a['complementary_pairs']} (cross-cell {a['complementary_pairs_cross_cell']})")
        print(f"  -> {a['verdict']}\n")

    out = os.path.join(ROOT, "docs", "HEADROOM-probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"min_skills": MIN_SKILLS, "min_tasks": MIN_TASKS, "cohorts": results}, f,
                  indent=2, ensure_ascii=False)
    print(f"saved -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
