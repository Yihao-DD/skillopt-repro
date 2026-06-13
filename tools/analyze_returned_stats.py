"""Paired statistical hardening for returned run packages (T015, zero API).

Judges whether a small per-task margin between two arms (e.g. venus QD 168 vs
greedy 162 solved out of 280) is signal or noise, from per-item 0/1 outcomes:

  - exact McNemar over the disagreeing pairs (binomial, p=1/2, two-sided);
  - seeded paired bootstrap percentile CI on the accuracy difference.

Core functions are pure and unit-tested (``qd/tests/test_paired_stats.py``);
the CLI is a thin wrapper for when a returned package lands:

  python tools/analyze_returned_stats.py --a greedy_items.json --b qd_items.json \
      --id-key id --val-key correct
"""
from __future__ import annotations

import argparse
import json
import math
import random


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value over the b+c disagreeing pairs.

    ``b`` = #(arm A correct, arm B wrong); ``c`` = #(A wrong, B correct).
    Agreeing pairs carry no information about the difference and are ignored.
    """
    if b < 0 or c < 0:
        raise ValueError("counts must be >= 0")
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def paired_bootstrap_ci(
    xs: list[int],
    ys: list[int],
    *,
    n_boot: int = 10000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Percentile CI for mean(ys) - mean(xs) under paired resampling.

    Deterministic for a given seed. Returns ``(lo, hi, observed_diff)``.
    """
    if len(xs) != len(ys):
        raise ValueError("paired vectors must have equal length")
    if not xs:
        raise ValueError("empty input")
    n = len(xs)
    diff = sum(ys) / n - sum(xs) / n
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        s = 0
        for _ in range(n):
            i = rng.randrange(n)
            s += ys[i] - xs[i]
        diffs.append(s / n)
    diffs.sort()
    lo = diffs[min(n_boot - 1, int((alpha / 2) * n_boot))]
    hi = diffs[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi, diff)


def pooled_mcnemar(seed_pairs: list[tuple[dict, dict]]) -> dict:
    """Pool discordant pairs across independent seeds, then exact McNemar.

    Each element is ``(arm_a_map, arm_b_map)`` of ``{item_id: 0/1}`` for one seed
    (item ids may differ across seeds — each seed aligned on its own intersection).
    Pooling the discordant counts is the standard way to combine paired binary
    outcomes from repeated runs into one significance test. ``b`` = A-correct
    /B-wrong, ``c`` = B-correct/A-wrong; ``net = c - b`` (arm-b net wins)."""
    b = c = n = 0
    for a_map, b_map in seed_pairs:
        xs, ys, ids = paired_from_records(a_map, b_map)
        n += len(ids)
        b += sum(1 for x, y in zip(xs, ys) if x == 1 and y == 0)
        c += sum(1 for x, y in zip(xs, ys) if x == 0 and y == 1)
    return {"b": b, "c": c, "net": c - b, "n_pairs": n, "p": mcnemar_exact(b, c)}


def paired_from_records(a: dict, b: dict) -> tuple[list[int], list[int], list[str]]:
    """Align two ``{item_id: 0/1}`` maps on their id intersection (sorted)."""
    ids = sorted(set(a) & set(b))
    xs = [int(a[i]) for i in ids]
    ys = [int(b[i]) for i in ids]
    return xs, ys, ids


def load_per_item(path: str, *, id_key: str = "id", val_key: str = "correct") -> dict:
    """Load ``{id: int(val)}`` from a .json (list of dicts) or .jsonl file."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    rows = None
    try:
        data = json.loads(text)
        if isinstance(data, list):
            rows = data
    except json.JSONDecodeError:
        pass
    if rows is None:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return {str(r[id_key]): int(r[val_key]) for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="Paired McNemar + bootstrap over two per-item result files")
    ap.add_argument("--a", required=True, help="arm A per-item results (json/jsonl), e.g. greedy")
    ap.add_argument("--b", required=True, help="arm B per-item results (json/jsonl), e.g. QD")
    ap.add_argument("--id-key", default="id")
    ap.add_argument("--val-key", default="correct")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    ra = load_per_item(args.a, id_key=args.id_key, val_key=args.val_key)
    rb = load_per_item(args.b, id_key=args.id_key, val_key=args.val_key)
    xs, ys, ids = paired_from_records(ra, rb)
    only_a = len(ra) - len(ids)
    only_b = len(rb) - len(ids)
    b_cnt = sum(1 for x, y in zip(xs, ys) if x == 1 and y == 0)
    c_cnt = sum(1 for x, y in zip(xs, ys) if x == 0 and y == 1)
    p = mcnemar_exact(b_cnt, c_cnt)
    lo, hi, diff = paired_bootstrap_ci(xs, ys, n_boot=args.n_boot, seed=args.seed)

    print(f"n_common={len(ids)} (only_a={only_a}, only_b={only_b})")
    print(f"arm A solved {sum(xs)}/{len(xs)} = {sum(xs)/len(xs):.4f}")
    print(f"arm B solved {sum(ys)}/{len(ys)} = {sum(ys)/len(ys):.4f}")
    print(f"disagreements: A-only-correct b={b_cnt}, B-only-correct c={c_cnt} (net {c_cnt - b_cnt:+d})")
    print(f"McNemar exact (two-sided): p={p:.4f}")
    print(f"paired bootstrap 95% CI for diff(B-A): [{lo:+.4f}, {hi:+.4f}], observed {diff:+.4f}")
    verdict = "SIGNIFICANT" if p < 0.05 and lo > 0 else "NOT settled by this run alone"
    print(f"verdict: {verdict}")


if __name__ == "__main__":
    main()
