"""Fine-grained router test (zero-API): does a FINER task-router harvest an
out-of-sample gain over greedy, or is the in-sample complementarity just noise?

The coarse type-router (2 task_types) failed to beat greedy out-of-sample. This
tests finer routers built ONLY from generalizable signal (task DESCRIPTION text):

  - cluster-router: TF-IDF + KMeans(K) on TRAIN descriptions -> per-cluster TRAIN
    specialist -> route each TEST task by its nearest cluster.
  - knn-router: for each TEST task, the skill best on its k nearest TRAIN tasks
    (description cosine) -> route.

Train/test = md5 parity. Greedy = best-TRAIN skill scored on TEST. The clusterer and
TF-IDF are fit on TRAIN only; specialists are chosen on TRAIN only — no test-label
leak. If the best realizable router still does not beat greedy (especially on the
largest test set), the complementarity does not generalize -> QD has no realizable
best-score gain here, and the in-sample headroom was a selection mirage.

Reads runs/<run>/<arm>/<hash>/results.jsonl. Zero API.  Run: python tools/router_test_probe.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

RUNS = os.path.join(ROOT, "runs")
MIN_SKILLS = 8
MIN_TASKS = 16
TOP_COHORTS = 5
KNN = 5


def _records(path: str):
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def discover() -> dict:
    """{(run, hash): {dir, solved}} — light (no descriptions held in memory)."""
    skills: dict = {}
    for dirpath, _dirs, files in os.walk(RUNS):
        if "results.jsonl" not in files:
            continue
        rel = os.path.relpath(dirpath, RUNS).split(os.sep)
        if len(rel) < 2:
            continue
        sv = {}
        try:
            for r in _records(os.path.join(dirpath, "results.jsonl")):
                sv[str(r.get("id"))] = 1 if float(r.get("hard", 0) or 0) >= 0.5 else 0
        except OSError:
            continue
        if sv:
            skills[(rel[0], os.path.basename(dirpath))] = {"dir": dirpath, "solved": sv}
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


def _descriptions(skill_dir: str, taskset: set) -> dict:
    out: dict = {}
    for r in _records(os.path.join(skill_dir, "results.jsonl")):
        tid = str(r.get("id"))
        if tid in taskset:
            out[tid] = str(r.get("task_description") or r.get("task_type") or tid)
    return out


def _is_train(tid: str) -> bool:
    return int(hashlib.md5(tid.encode()).hexdigest(), 16) % 2 == 0


def analyze(cohort: dict) -> dict | None:
    tasks = cohort["tasks"]
    train = [t for t in tasks if _is_train(t)]
    test = [t for t in tasks if not _is_train(t)]
    if len(train) < 8 or len(test) < 4:
        return None
    items = sorted(cohort["skills"].items())
    hashes = [h for h, _ in items]
    solved = {h: v["solved"] for h, v in items}
    desc = _descriptions(items[0][1]["dir"], set(tasks))

    def rate(h, ts):
        return sum(solved[h].get(t, 0) for t in ts) / len(ts) if ts else 0.0

    train_rate = {h: rate(h, train) for h in hashes}
    greedy = max(hashes, key=lambda h: (train_rate[h], h))
    greedy_test = rate(greedy, test)
    oracle = sum(1 for t in test if any(solved[h].get(t, 0) for h in hashes)) / len(test)

    tfidf = TfidfVectorizer(min_df=1, token_pattern=r"[A-Za-z][A-Za-z0-9_]+")
    Xtr = tfidf.fit_transform([desc[t] for t in train])
    Xte = tfidf.transform([desc[t] for t in test])

    def specialist(task_subset: list) -> str:
        return max(hashes, key=lambda h: (sum(solved[h].get(t, 0) for t in task_subset) / max(len(task_subset), 1),
                                           train_rate[h], h))

    routers: dict = {}
    for K in (4, 8):
        if len(train) < 3 * K:
            continue
        km = KMeans(n_clusters=K, n_init=5, random_state=0).fit(Xtr)
        tr_lab, te_lab = km.labels_, km.predict(Xte)
        spec = {c: specialist([train[i] for i in range(len(train)) if tr_lab[i] == c]) or greedy for c in range(K)}
        routed = sum(solved[spec[te_lab[i]]].get(t, 0) for i, t in enumerate(test))
        routers[f"cluster{K}"] = round(routed / len(test), 3)

    sim = cosine_similarity(Xte, Xtr)
    k = min(KNN, len(train))
    routed = 0
    for i, t in enumerate(test):
        nn = np.argsort(sim[i])[::-1][:k]
        routed += solved[specialist([train[j] for j in nn])].get(t, 0)
    routers["knn"] = round(routed / len(test), 3)

    best_router = max(routers.values()) if routers else greedy_test
    return {
        "run": cohort["run"], "n_skills": len(items), "n_train": len(train), "n_test": len(test),
        "greedy_test": round(greedy_test, 3),
        "routers": routers,
        "best_router_test": round(best_router, 3),
        "best_realizable_gain": round(best_router - greedy_test, 3),
        "oracle_union_test": round(oracle, 3),
    }


def interpret(a: dict) -> str:
    g = a["best_realizable_gain"]
    if g >= 0.02:
        return (f"REALIZABLE GAIN +{g:.3f} from a finer router ({a['best_router_test']} vs greedy "
                f"{a['greedy_test']}) — complementarity has harvestable structure; pursue competence router.")
    if g <= -0.02:
        return (f"NO gain ({g:+.3f}); even a fine description router loses to greedy -> "
                "complementarity does not generalize (noise).")
    return (f"FLAT ({g:+.3f}); no finer router beats greedy out-of-sample (oracle ceiling "
            f"+{round(a['oracle_union_test'] - a['greedy_test'], 3):.3f} is unharvestable) -> treat as noise.")


def main() -> None:
    if not os.path.isdir(RUNS):
        print(f"no runs/ cache at {RUNS}")
        return
    cs = cohorts(discover())
    print(f"-> {len(cs)} cohorts (TF-IDF/KMeans fit on TRAIN only; knn k={KNN})\n")
    results = []
    for cohort in cs[:TOP_COHORTS]:
        a = analyze(cohort)
        if a is None:
            continue
        a["verdict"] = interpret(a)
        results.append(a)
        rstr = "  ".join(f"{k}={v}" for k, v in a["routers"].items())
        print(f"== '{a['run']}'  ({a['n_skills']} skills, {a['n_train']}/{a['n_test']} train/test) ==")
        print(f"  greedy_test {a['greedy_test']:.3f}   routers: {rstr}")
        print(f"  best realizable gain {a['best_realizable_gain']:+.3f}   "
              f"(oracle ceiling +{a['oracle_union_test'] - a['greedy_test']:.3f})")
        print(f"  -> {a['verdict']}\n")

    out = os.path.join(ROOT, "docs", "ROUTER-test-probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"split": "md5-parity", "knn": KNN, "cohorts": results}, f, indent=2, ensure_ascii=False)
    print(f"saved -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
