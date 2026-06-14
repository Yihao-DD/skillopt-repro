"""Out-of-sample headroom + descriptor-axis validation (zero-API).

The goal is QD beating greedy on a held-out set — not in-sample set-cover optimism.

Question A (decisive, realizable): split the fixed task set TRAIN/TEST (deterministic
md5 parity). GREEDY picks the best-on-TRAIN skill and is scored on TEST. A TYPE-ROUTER
picks, per task_type, the skill best on that type in TRAIN, and routes TEST tasks by
type. If router_test > greedy_test, the complementarity is REAL and REALIZABLE on
held-out tasks (the gain is not a set-cover artifact). Assumption: task_type is known
at inference (it is a property of the task prompt, not the solution).

Question B (the lever): the router's per-type specialists must be KEPT by the archive.
Under the live D0 code-style descriptor, how many DISTINCT cells do those specialists
occupy? If they collapse into a few cells, the per-cell archive (best per cell) drops
specialists -> the DESCRIPTOR (not the search) loses the gain -> bin by competence.

Reads runs/<run>/<arm>/<hash>/{results.jsonl, predictions/<id>/code.py}. Zero API.
Run:  python tools/competence_headroom_probe.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qd.descriptor import descriptor  # pure stdlib

RUNS = os.path.join(ROOT, "runs")
MIN_SKILLS = 8
MIN_TASKS = 16     # need enough for a train/test split
TOP_COHORTS = 5


def _load(path: str) -> tuple:
    """({task: solved 0/1}, {task: task_type}) from a skill's results.jsonl."""
    sv, ty = {}, {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = str(r.get("id"))
            sv[tid] = 1 if float(r.get("hard", 0) or 0) >= 0.5 else 0
            ty[tid] = str(r.get("task_type") or r.get("instruction_type") or "?")
    return sv, ty


def discover() -> dict:
    skills: dict = {}
    for dirpath, _dirs, files in os.walk(RUNS):
        if "results.jsonl" not in files:
            continue
        rel = os.path.relpath(dirpath, RUNS).split(os.sep)
        if len(rel) < 2:
            continue
        run = rel[0]
        try:
            sv, ty = _load(os.path.join(dirpath, "results.jsonl"))
        except OSError:
            continue
        if sv:
            skills[(run, os.path.basename(dirpath))] = {"dir": dirpath, "solved": sv, "type": ty}
    return skills


def cohorts(skills: dict) -> list:
    buckets: dict = defaultdict(dict)
    for (run, sh), v in skills.items():
        buckets[(run, frozenset(v["solved"].keys()))].setdefault(sh, v)
    out = []
    for (run, taskset), sk in buckets.items():
        if len(sk) >= MIN_SKILLS and len(taskset) >= MIN_TASKS:
            out.append({"run": run, "tasks": sorted(taskset), "skills": sk})
    out.sort(key=lambda c: -len(c["skills"]))
    return out


def _cell(skill_dir: str, tasks: list) -> int | None:
    trajs = []
    for t in tasks:
        cp = os.path.join(skill_dir, "predictions", t, "code.py")
        if os.path.isfile(cp):
            try:
                with open(cp, encoding="utf-8", errors="ignore") as f:
                    trajs.append({"code": f.read()})
            except OSError:
                pass
    return descriptor(trajs).cell if trajs else None


def _is_train(tid: str) -> bool:
    return int(hashlib.md5(tid.encode()).hexdigest(), 16) % 2 == 0


def analyze(cohort: dict) -> dict | None:
    tasks = cohort["tasks"]
    types = next(iter(cohort["skills"].values()))["type"]
    train = [t for t in tasks if _is_train(t)]
    test = [t for t in tasks if not _is_train(t)]
    if not train or not test:
        return None
    items = sorted(cohort["skills"].items())
    hashes = [h for h, _ in items]
    solved = {h: v["solved"] for h, v in items}

    def rate(h: str, ts: list) -> float:
        return sum(solved[h].get(t, 0) for t in ts) / len(ts) if ts else 0.0

    train_rate = {h: rate(h, train) for h in hashes}
    test_rate = {h: rate(h, test) for h in hashes}

    greedy = max(hashes, key=lambda h: (train_rate[h], h))     # select on TRAIN only
    greedy_test = test_rate[greedy]

    # per task_type specialist, chosen on TRAIN
    by_type: dict = defaultdict(list)
    for t in train:
        by_type[types.get(t, "?")].append(t)
    specialist = {}
    for ty, tts in by_type.items():
        specialist[ty] = max(hashes, key=lambda h: (sum(solved[h].get(t, 0) for t in tts) / len(tts),
                                                     train_rate[h], h))
    routed = sum(solved[specialist.get(types.get(t, "?"), greedy)].get(t, 0) for t in test)
    router_test = routed / len(test)
    union_test = sum(1 for t in test if any(solved[h].get(t, 0) for h in hashes)) / len(test)

    # descriptor lever: do the specialists collapse into few D0 cells?
    spec_set = set(specialist.values()) | {greedy}
    spec_cells = {c for c in (_cell(cohort["skills"][h]["dir"], tasks) for h in spec_set) if c is not None}
    all_cells = {c for c in (_cell(v["dir"], tasks) for _h, v in items) if c is not None}

    return {
        "run": cohort["run"], "n_skills": len(items),
        "n_train": len(train), "n_test": len(test), "n_types": len(by_type),
        "greedy_test": round(greedy_test, 3),
        "type_router_test": round(router_test, 3),
        "realizable_gain": round(router_test - greedy_test, 3),
        "oracle_union_test": round(union_test, 3),
        "oracle_gain": round(union_test - greedy_test, 3),
        "n_specialists": len(spec_set),
        "specialists_distinct_D0_cells": len(spec_cells),
        "D0_cells_occupied_total": len(all_cells),
    }


def interpret(a: dict) -> str:
    g = a["realizable_gain"]
    drops = a["n_specialists"] > a["specialists_distinct_D0_cells"]
    msg = []
    if g >= 0.02:
        msg.append(f"REALIZABLE GAIN +{g:.3f} on held-out TEST (router {a['type_router_test']} vs greedy "
                   f"{a['greedy_test']}) — QD library+type-router beats greedy out-of-sample.")
    elif g <= -0.02:
        msg.append(f"NO realizable gain ({g:+.3f}); the type-router does not generalize past greedy here.")
    else:
        msg.append(f"FLAT realizable gain ({g:+.3f}); marginal at best — but oracle ceiling is "
                   f"+{a['oracle_gain']:.3f}, so a better router/recombiner could still help.")
    if drops:
        msg.append(f"DESCRIPTOR LOSES IT: {a['n_specialists']} specialists collapse into "
                   f"{a['specialists_distinct_D0_cells']} D0 cells -> the per-cell archive drops "
                   "specialists; bin by competence to keep them.")
    return " ".join(msg)


def main() -> None:
    if not os.path.isdir(RUNS):
        print(f"no runs/ cache at {RUNS}")
        return
    cs = cohorts(discover())
    print(f"-> {len(cs)} comparable cohorts (train/test md5-parity split)\n")
    results = []
    for cohort in cs[:TOP_COHORTS]:
        a = analyze(cohort)
        if a is None:
            continue
        a["verdict"] = interpret(a)
        results.append(a)
        print(f"== cohort '{a['run']}'  ({a['n_skills']} skills, {a['n_train']}/{a['n_test']} train/test, "
              f"{a['n_types']} task-types) ==")
        print(f"  greedy (train-select -> test)   {a['greedy_test']:.3f}")
        print(f"  type-router (train -> test)     {a['type_router_test']:.3f}   "
              f"realizable gain {a['realizable_gain']:+.3f}")
        print(f"  oracle union (test)             {a['oracle_union_test']:.3f}   ceiling {a['oracle_gain']:+.3f}")
        print(f"  specialists {a['n_specialists']} -> distinct D0 cells {a['specialists_distinct_D0_cells']} "
              f"(of {a['D0_cells_occupied_total']} occupied)")
        print(f"  -> {a['verdict']}\n")

    out = os.path.join(ROOT, "docs", "COMPETENCE-HEADROOM-probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"split": "md5-parity", "cohorts": results}, f, indent=2, ensure_ascii=False)
    print(f"saved -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
