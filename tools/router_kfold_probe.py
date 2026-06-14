"""K-fold CV of the description-router gain (zero-API).

The single-split test showed a +5pt out-of-sample gain (knn description-router vs
greedy) on the 280-task cohort. Is that robust or a lucky split? This runs F-fold CV
(folds = md5(task) % F): each fold is held out as TEST, the rest is TRAIN; greedy =
best-TRAIN skill scored on TEST; routers (knn over description cosine, + KMeans-8
cluster specialists) are built on TRAIN and scored on TEST. Reports per-fold and
mean +/- std of (best_router_test - greedy_test).

Robust positive mean (and mean-std > 0) on the large cohort => the gain is real and
the QD library+router path is worth building. Noisy/zero => variance, treat as noise.

Reads runs/<run>/<arm>/<hash>/results.jsonl. Zero API.  Run: python tools/router_kfold_probe.py
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
FOLDS = 5


def _records(path: str):
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def discover() -> dict:
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
    out = [{"run": run, "tasks": sorted(ts), "skills": sk}
           for (run, ts), sk in buckets.items() if len(sk) >= MIN_SKILLS and len(ts) >= MIN_TASKS]
    out.sort(key=lambda c: -len(c["skills"]))
    return out


def _descriptions(skill_dir: str, taskset: set) -> dict:
    out: dict = {}
    for r in _records(os.path.join(skill_dir, "results.jsonl")):
        tid = str(r.get("id"))
        if tid in taskset:
            out[tid] = str(r.get("task_description") or r.get("task_type") or tid)
    return out


def _fold(tid: str, f: int) -> int:
    return int(hashlib.md5(tid.encode()).hexdigest(), 16) % f


def _eval_split(train, test, hashes, solved, desc) -> tuple:
    def rate(h, ts):
        return sum(solved[h].get(t, 0) for t in ts) / len(ts) if ts else 0.0

    train_rate = {h: rate(h, train) for h in hashes}
    greedy = max(hashes, key=lambda h: (train_rate[h], h))
    greedy_test = rate(greedy, test)

    tfidf = TfidfVectorizer(min_df=1, token_pattern=r"[A-Za-z][A-Za-z0-9_]+")
    Xtr = tfidf.fit_transform([desc[t] for t in train])
    Xte = tfidf.transform([desc[t] for t in test])

    def specialist(sub):
        return max(hashes, key=lambda h: (sum(solved[h].get(t, 0) for t in sub) / max(len(sub), 1),
                                           train_rate[h], h))

    routers = []
    if len(train) >= 24:
        km = KMeans(n_clusters=8, n_init=5, random_state=0).fit(Xtr)
        tr_lab, te_lab = km.labels_, km.predict(Xte)
        spec = {c: specialist([train[i] for i in range(len(train)) if tr_lab[i] == c]) for c in range(8)}
        routers.append(sum(solved[spec[te_lab[i]]].get(t, 0) for i, t in enumerate(test)) / len(test))
    sim = cosine_similarity(Xte, Xtr)
    k = min(KNN, len(train))
    routers.append(sum(solved[specialist([train[int(j)] for j in np.argsort(sim[i])[::-1][:k]])].get(t, 0)
                       for i, t in enumerate(test)) / len(test))
    return greedy_test, max(routers)


def analyze(cohort: dict) -> dict | None:
    tasks = cohort["tasks"]
    items = sorted(cohort["skills"].items())
    hashes = [h for h, _ in items]
    solved = {h: v["solved"] for h, v in items}
    desc = _descriptions(items[0][1]["dir"], set(tasks))
    f = FOLDS
    folds = {i: [t for t in tasks if _fold(t, f) == i] for i in range(f)}
    if any(len(v) < 3 for v in folds.values()):
        f = max(2, len(tasks) // 6)
        folds = {i: [t for t in tasks if _fold(t, f) == i] for i in range(f)}

    gains, greedy_s, router_s = [], [], []
    for i in range(f):
        test = folds[i]
        train = [t for t in tasks if t not in set(test)]
        if len(train) < 8 or len(test) < 3:
            continue
        g, r = _eval_split(train, test, hashes, solved, desc)
        greedy_s.append(g)
        router_s.append(r)
        gains.append(r - g)
    if not gains:
        return None
    arr = np.array(gains)
    return {
        "run": cohort["run"], "n_skills": len(items), "n_tasks": len(tasks), "folds": len(gains),
        "mean_greedy": round(float(np.mean(greedy_s)), 3),
        "mean_router": round(float(np.mean(router_s)), 3),
        "mean_gain": round(float(arr.mean()), 3),
        "std_gain": round(float(arr.std()), 3),
        "min_gain": round(float(arr.min()), 3),
        "max_gain": round(float(arr.max()), 3),
        "per_fold_gain": [round(x, 3) for x in gains],
    }


def main() -> None:
    if not os.path.isdir(RUNS):
        print(f"no runs/ cache at {RUNS}")
        return
    cs = cohorts(discover())
    print(f"-> {len(cs)} cohorts, {FOLDS}-fold CV (md5 folds)\n")
    results = []
    for cohort in cs[:TOP_COHORTS]:
        a = analyze(cohort)
        if a is None:
            continue
        results.append(a)
        robust = a["mean_gain"] - a["std_gain"] > 0
        tag = "ROBUST +" if robust else ("mixed" if a["mean_gain"] > 0 else "no gain")
        print(f"== '{a['run']}'  ({a['n_skills']} skills x {a['n_tasks']} tasks, {a['folds']} folds) ==")
        print(f"  greedy {a['mean_greedy']:.3f}  router {a['mean_router']:.3f}")
        print(f"  gain  mean {a['mean_gain']:+.3f}  std {a['std_gain']:.3f}  "
              f"[min {a['min_gain']:+.3f}, max {a['max_gain']:+.3f}]   per-fold {a['per_fold_gain']}")
        print(f"  -> {tag} (mean-std {'>' if robust else '<='} 0)\n")

    out = os.path.join(ROOT, "docs", "ROUTER-KFOLD-probe.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"folds": FOLDS, "knn": KNN, "cohorts": results}, fh, indent=2, ensure_ascii=False)
    print(f"saved -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
