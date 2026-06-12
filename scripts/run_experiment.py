"""One-command launcher for the QD-over-Skills full run (公司一键入口).

This is the REAL `scripts/run_experiment.py` that `handoff/RUNBOOK.md` advertises.
It runs the SAME validated core as ``tools/run_qd_validation.py``
(``configure_deepseek`` -> ``make_producer`` -> ``run_search``), but parameterized
as a CLI with presets, a written summary, and the frozen-target red line baked in.

公司只做两件事：
  1. 换 API —— 只改根目录 ``.env``（``AZURE_OPENAI_ENDPOINT`` / ``AZURE_OPENAI_API_KEY``
     / ``TARGET_MODEL`` / ``OPTIMIZER_MODEL``）。openai-compatible，换谁都一样。
  2. 启动 ——
       python scripts/run_experiment.py --full        # 全量（test 全集，K=1 贪心 vs K=4 QD，等预算）
       python scripts/run_experiment.py --preflight    # 小试冒烟（2 题，~$0.02）
       python scripts/run_experiment.py --full --dry-run   # 只预览计划 + 检查 fork/数据/key，不花钱

Writes ``runs/<mode>/summary.json`` (plan + baseline + per-arm result + verdict +
tokens, key redacted) so the run is self-describing for hand-off.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Make `import qd` (repo root) and `import skillopt` (the fork) resolve on a clean
# unzip WITHOUT relying on a per-machine editable install — same logic as conftest.py.
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
for _cand in ("vendor/SkillOpt", "SkillOpt"):
    _pkg_parent = os.path.join(ROOT, _cand)
    if os.path.exists(os.path.join(_pkg_parent, "skillopt", "__init__.py")):
        if _pkg_parent not in sys.path:
            sys.path.insert(0, _pkg_parent)
        FORK_DIR = _pkg_parent
        break
else:
    FORK_DIR = os.path.join(ROOT, "SkillOpt")  # reported as missing in --dry-run

# The fixed starting skill both arms improve from (identical to the validation run).
INITIAL = (
    "You are an expert at spreadsheet manipulation. Read the input workbook with "
    "openpyxl from INPUT_PATH, perform exactly the requested edits, and save to "
    "OUTPUT_PATH. Return a single ```python``` code block."
)

# n=None means "all items in the split". Overridable on the CLI.
PRESETS = {
    "preflight": {"n": 2, "eval_budget": 6, "k": 4},
    "full": {"n": None, "eval_budget": 24, "k": 4},
}


@dataclass
class Plan:
    mode: str          # "full" | "preflight"
    n: int | None      # None => all items in the test split
    eval_budget: int   # expensive evals PER ARM (equal-budget red line)
    k: int             # K for the QD arm (K=1 arm is always run as the greedy baseline)
    workers: int
    max_tokens: int
    tag: str | None = None   # optional run label -> runs/<mode>-<tag>/ (multi-API compare)
    rcv: bool = False        # third arm: K=k + rejection-ledger conditioning (ADR-0007)


def resolve_plan(
    *,
    full: bool,
    n: int | None = None,
    eval_budget: int | None = None,
    k: int | None = None,
    workers: int = 8,
    max_tokens: int = 4096,
    tag: str | None = None,
    rcv: bool = False,
) -> Plan:
    """Pure plan resolution (no IO, no model) — preset defaults, CLI overrides win."""
    if tag is not None and not re.fullmatch(r"[A-Za-z0-9._-]+", tag):
        raise ValueError(f"--tag 只能含字母/数字/.-_（要拿来做目录名）: {tag!r}")
    mode = "full" if full else "preflight"
    base = PRESETS[mode]
    return Plan(
        mode=mode,
        n=n if n is not None else base["n"],
        eval_budget=eval_budget if eval_budget is not None else base["eval_budget"],
        k=k if k is not None else base["k"],
        workers=workers,
        max_tokens=max_tokens,
        tag=tag,
        rcv=rcv,
    )


def load_dotenv(root: str) -> None:
    """Load ``.env`` into os.environ (setdefault) — the ONE file the company edits."""
    envp = os.path.join(root, ".env")
    if not os.path.exists(envp):
        return
    with open(envp, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")  # tolerate KEY="..." / KEY='...'
                os.environ.setdefault(k.strip(), v)


def _data_paths() -> tuple[str, str]:
    items_json = os.path.join(FORK_DIR, "data", "spreadsheetbench_split", "test", "items.json")
    data_root = os.path.join(FORK_DIR, "data", "spreadsheetbench_verified_400")
    return items_json, data_root


def _out_dir(plan: Plan) -> str:
    """Run output dir; --tag separates multi-API runs (runs/full-deepseek vs runs/full-gpt)."""
    sub = plan.mode if not plan.tag else f"{plan.mode}-{plan.tag}"
    return os.path.join(ROOT, "runs", sub)


def preflight_checks(plan: Plan) -> bool:
    """Print PASS/FAIL for everything a real run needs; return True iff all green."""
    items_json, data_root = _data_paths()
    checks = [
        ("fork engine present", os.path.exists(os.path.join(FORK_DIR, "skillopt", "__init__.py")), FORK_DIR),
        ("test items.json present", os.path.exists(items_json), items_json),
        ("verified_400 data present", os.path.isdir(data_root) and bool(os.listdir(data_root)), data_root),
        ("API key set (.env)", bool(os.environ.get("AZURE_OPENAI_API_KEY")), "AZURE_OPENAI_API_KEY"),
    ]
    all_ok = True
    for label, ok, detail in checks:
        shown = "set" if (ok and label.startswith("API key")) else detail
        print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {shown}")
        all_ok = all_ok and ok
    n_resolved = plan.n
    if plan.n is None and os.path.exists(items_json):
        with open(items_json, encoding="utf-8") as fh:
            n_resolved = len(json.load(fh))
    print(f"  resolved N (tasks per arm) = {n_resolved if n_resolved is not None else '<needs items.json>'}")
    print(f"  expensive evals per arm    = {plan.eval_budget}   (K=1 greedy vs K={plan.k} QD, equal budget)")
    print(f"  output dir = runs/{os.path.basename(_out_dir(plan))}/")
    if plan.mode == "full":
        print(f"  coverage = ALL {n_resolved} test tasks（全量，非子集）；搜索深度 = {plan.eval_budget} evals/臂")
        if plan.eval_budget <= 12:
            print(f"  注意：深度 {plan.eval_budget} 较浅（≤12，与小验证同档）；"
                  "要更深搜索用 --eval-budget 提高（成本/时间随之线性增长）。")
    return all_ok


def _arm_summary(res) -> dict:
    return {
        "best": res.best_score,
        "n_occupied": res.n_occupied,
        "cross_cell": res.cross_cell_pickups,
        "expensive_evals": res.expensive_evals,
        "n_proposed": res.n_proposed,
        "history": [(h.step, h.action, round(h.candidate.score, 3), h.cell) for h in res.history],
    }


def run(plan: Plan) -> dict:
    """Execute the real (paid) run. Both arms share one frozen baseline + equal budget."""
    # Frozen-target red line (P2): reproducible target, diverse optimizer.
    os.environ.setdefault("TARGET_TEMPERATURE", "0")
    os.environ.setdefault("TARGET_SEED", "42")
    os.environ.setdefault("OPTIMIZER_TEMPERATURE", "0.8")

    from skillopt.envs.spreadsheetbench.rollout import load_items

    from qd.adapter_skillopt import configure_deepseek, make_producer
    from qd.descriptor import descriptor
    from qd.loop import run_search

    cfg = configure_deepseek()  # raises if AZURE_OPENAI_API_KEY missing
    items_json, data_root = _data_paths()
    items = load_items(items_json)
    if plan.n is not None:
        items = items[: plan.n]
    out = _out_dir(plan)
    print(f"frozen: {cfg} temp=0 seed=42")
    print(f"mode={plan.mode}  N={len(items)}  eval_budget={plan.eval_budget}  K=1 vs K={plan.k}")

    def producer(tag):
        return make_producer(items=items, data_root=data_root, out_root=os.path.join(out, tag),
                             workers=plan.workers, max_completion_tokens=plan.max_tokens)

    base_prod = producer("baseline")
    base_score = base_prod.score(INITIAL)
    base_cell = descriptor(base_prod.probe(INITIAL)).cell
    print(f"baseline: hard={base_score}  cell={base_cell}")

    def run_arm(k: int, tag: str, *, use_ledger: bool = False):
        res = run_search(k=k, baseline_skill=INITIAL, baseline_score=base_score,
                         eval_budget=plan.eval_budget, producer=producer(tag),
                         baseline_cell=(0 if k == 1 else base_cell), max_lr=4, min_lr=2,
                         use_ledger=use_ledger)
        print(f"[{tag}] best={res.best_score} n_occupied={res.n_occupied} "
              f"cross_cell={res.cross_cell_pickups} evals={res.expensive_evals}"
              + (f" ledger={len(res.ledger)}" if res.ledger is not None else ""))
        return res

    r1 = run_arm(1, "k1")
    rk = run_arm(plan.k, f"k{plan.k}")
    rrcv = run_arm(plan.k, f"k{plan.k}rcv", use_ledger=True) if plan.rcv else None

    try:
        from skillopt.model import get_token_summary
        tokens = get_token_summary()
    except Exception as exc:  # noqa: BLE001
        tokens = {"error": str(exc)}

    summary = {
        "created": datetime.now(timezone.utc).isoformat(),
        "plan": asdict(plan),
        "tasks": [it["id"] for it in items],
        "backend": cfg,  # endpoint + models, NO key
        "frozen": {"target_temperature": 0, "target_seed": 42, "optimizer_temperature": 0.8},
        "baseline_hard": base_score,
        "baseline_cell": base_cell,
        "k1": _arm_summary(r1),
        f"k{plan.k}": _arm_summary(rk),
        "verdict": {
            "q1_qd_explores": bool(rk.n_occupied > 1),
            "q2_qd_payoff_at_equal_budget": bool(rk.best_score > r1.best_score),
        },
        "tokens": tokens,
    }
    if rrcv is not None:
        summary[f"k{plan.k}_rcv"] = {
            **_arm_summary(rrcv),
            "ledger_entries": len(rrcv.ledger) if rrcv.ledger is not None else 0,
            "ledger_note": "ledger_entries 含缓存命中的判决；expensive_evals 只计缓存未命中",
            "precheck_skips": rrcv.precheck_skips,
        }
        summary["verdict"]["q3_rcv_payoff_over_plain_qd"] = bool(rrcv.best_score > rk.best_score)
        summary["verdict"]["q3_rcv_payoff_over_greedy"] = bool(rrcv.best_score > r1.best_score)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print("\n=== VERDICT ===")
    print(f"  baseline hard = {base_score}")
    print(f"  K=1   best = {r1.best_score}")
    print(f"  K={plan.k} best = {rk.best_score}  n_occupied={rk.n_occupied}  cross_cell={rk.cross_cell_pickups}")
    print(f"  [Q1] QD explores (n_occupied>1):              {summary['verdict']['q1_qd_explores']}")
    print(f"  [Q2] QD payoff (K>1 best > K=1, equal budget): {summary['verdict']['q2_qd_payoff_at_equal_budget']}")
    if rrcv is not None:
        print(f"  K={plan.k}+RCV best = {rrcv.best_score}  n_occupied={rrcv.n_occupied}  "
              f"ledger={len(rrcv.ledger) if rrcv.ledger is not None else 0}  precheck_skips={rrcv.precheck_skips}")
        print(f"  [Q3] RCV payoff (RCV > plain QD, equal budget): {summary['verdict']['q3_rcv_payoff_over_plain_qd']}")
    if rk.n_occupied <= 1:
        print("  ⚠️ QD 臂只占 1 格 → descriptor 在此模型上塌缩，QD 退化成贪心、本次对比无意义；"
              "先跑 --probe-descriptor 复查并回我方重标定。")
    print(f"  summary -> {os.path.join(out, 'summary.json')}")
    return summary


def probe_descriptor(n: int) -> dict:
    """Cheap pre-full check: does the descriptor resolve THIS model's code outputs?

    Runs the baseline skill once over n items and bins each item's generated code.
    If the per-item cells collapse to <3 distinct cells, the descriptor has no
    resolution on this model (the Qwen3 morning-run failure mode) and the QD arm
    will degenerate to greedy — STOP before spending a full run. Writes runs/probe/probe.json.
    """
    os.environ.setdefault("TARGET_TEMPERATURE", "0")
    os.environ.setdefault("TARGET_SEED", "42")
    from skillopt.envs.spreadsheetbench.rollout import load_items

    from qd.adapter_skillopt import configure_deepseek, make_producer
    from qd.descriptor import descriptor

    cfg = configure_deepseek()
    items_json, data_root = _data_paths()
    items = load_items(items_json)[:n]
    out = os.path.join(ROOT, "runs", "probe")
    print("== QD-over-Skills · probe-descriptor ==")
    print(f"backend: {cfg}")
    prod = make_producer(items=items, data_root=data_root, out_root=out, max_completion_tokens=4096)
    trajs = prod.probe(INITIAL)
    per_item = [descriptor([t]).cell for t in trajs]
    agg = descriptor(trajs).cell
    distinct = sorted(set(per_item))
    ok = len(distinct) >= 3
    print(f"probe: baseline skill over {len(items)} items")
    print(f"  per-item cells = {per_item}")
    print(f"  distinct cells = {len(distinct)}/16 -> {distinct}   (aggregate skill cell = {agg})")
    if ok:
        print("  PROBE OK: descriptor 在此模型上有分辨率（≥3 格），可以继续 --full。")
    else:
        print("  ⚠️ PROBE FAIL: descriptor 在此模型上塌缩（<3 格）== 今早 Qwen3 那次。")
        print("     先别烧全量；把这个 probe 结果发回我方，给该模型重标定 descriptor 再跑。")
    summary = {"backend": cfg, "n_items": len(items), "per_item_cells": per_item,
               "distinct_cells": distinct, "aggregate_cell": agg, "probe_ok": ok}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "probe.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(f"  probe -> {os.path.join(out, 'probe.json')}")
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="QD-over-Skills launcher (full / preflight).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--full", action="store_true", help="全量：test 全集，K=1 贪心 vs K=4 QD，等预算")
    g.add_argument("--preflight", action="store_true", help="小试冒烟（默认 2 题）")
    p.add_argument("--n", type=int, default=None, help="覆盖任务数（默认 full=全集 / preflight=2）")
    p.add_argument("--eval-budget", type=int, default=None, help="每臂昂贵评估预算（默认 full=24 / preflight=6）")
    p.add_argument("--k", type=int, default=None, help="QD 臂的 K（默认 4；K=1 臂始终作为贪心对照）")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--tag", default=None, help="本次运行标签 → 写到 runs/<mode>-<tag>/（多 API 对比时分目录，不互相覆盖）")
    p.add_argument("--rcv", action="store_true",
                   help="加跑第三臂：K=k + 拒绝账本条件化变异（ADR-0007；等预算，三臂消融 贪心/QD/QD+RCV）")
    p.add_argument("--probe-descriptor", action="store_true",
                   help="探针：跑 ~8 题 baseline 算 descriptor 占格，验该模型散不散（几毛钱，全量前先跑）")
    p.add_argument("--probe-n", type=int, default=8, help="--probe-descriptor 的题数（默认 8）")
    p.add_argument("--dry-run", action="store_true", help="只解析计划 + 检查 fork/数据/key，不调模型、不花钱")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    load_dotenv(ROOT)
    if args.probe_descriptor:
        if not os.environ.get("AZURE_OPENAI_API_KEY"):
            print("ERROR: AZURE_OPENAI_API_KEY 未设置（probe 要真调一次模型）。先填 .env。", file=sys.stderr)
            return 2
        return 0 if probe_descriptor(args.probe_n)["probe_ok"] else 3
    if not args.full and not args.preflight:
        parser.error("必须指定 --full（全量 280 题）/ --preflight（2 题冒烟）/ --probe-descriptor（descriptor 探针）。")
    plan = resolve_plan(full=args.full, n=args.n, eval_budget=args.eval_budget,
                        k=args.k, workers=args.workers, max_tokens=args.max_tokens, tag=args.tag,
                        rcv=args.rcv)
    print(f"== QD-over-Skills · mode={plan.mode} ==")
    if args.dry_run:
        ok = preflight_checks(plan)
        print("DRY-RUN:", "READY — drop the API key into .env and drop --dry-run to launch."
              if ok else "NOT READY — fix the FAIL lines above.")
        return 0 if ok else 2
    if not os.environ.get("AZURE_OPENAI_API_KEY"):
        print("ERROR: AZURE_OPENAI_API_KEY 未设置。把 .env.example 复制成 .env 并填好 endpoint/key，再跑。",
              file=sys.stderr)
        return 2
    run(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
