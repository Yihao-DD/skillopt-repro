"""S15 preflight smoke — prove the real SkillOpt+DeepSeek adapter runs end-to-end
on a TINY SpreadsheetBench subset (2 tasks). NOT the 100-item validation.

Stages (each prints before spending the next calls):
  [1] score(initial)  → rollout (DeepSeek codegen) + execute + grade works
  [2] probe(initial)  → real generated code → behavior descriptor cells
  [3] 1-step K=1 loop → the integrated loop drives real DeepSeek + gate

Reads .env. ~a few cents. Run:  python tools/preflight_deepseek_smoke.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_envp = os.path.join(ROOT, ".env")
if os.path.exists(_envp):
    for _line in open(_envp, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from skillopt.envs.spreadsheetbench.rollout import load_items  # noqa: E402

from qd.adapter_skillopt import configure_deepseek, make_producer  # noqa: E402
from qd.descriptor import descriptor  # noqa: E402
from qd.loop import run_search  # noqa: E402

INITIAL = (
    "You are an expert at spreadsheet manipulation. Read the input workbook with "
    "openpyxl from INPUT_PATH, perform exactly the requested edits, and save to "
    "OUTPUT_PATH. Return a single ```python``` code block."
)

cfg = configure_deepseek()
print("model config:", cfg)

items = load_items(os.path.join(ROOT, "SkillOpt", "data", "spreadsheetbench_split", "test", "items.json"))[:2]
print("smoke items:", [it["id"] for it in items])
data_root = os.path.join(ROOT, "SkillOpt", "data", "spreadsheetbench_verified_400")
out_root = os.environ.get("QD_SMOKE_OUT", os.path.join(ROOT, "runs", "_smoke_deepseek"))
os.makedirs(out_root, exist_ok=True)  # fixed path → re-runs resume the cached rollout (free)
print("out_root:", out_root)

prod = make_producer(items=items, data_root=data_root, out_root=out_root, workers=2, max_completion_tokens=4096)

print("\n[1] score(initial) on 2 tasks (real DeepSeek rollout + execute + grade) ...")
s0 = prod.score(INITIAL)
print("    initial hard score =", s0)

print("\n[2] probe(initial) -> descriptor cells (real generated code) ...")
for c in prod.probe(INITIAL):
    d = descriptor([c])
    print(f"    cell={d.cell:2d}  b={tuple(round(x,3) for x in d.b)}  code_len={len(c['code'])}")

print("\n[3] 1-step K=1 run_search (loop drives real DeepSeek + gate) ...")
res = run_search(k=1, baseline_skill=INITIAL, baseline_score=s0, eval_budget=1, producer=prod, max_lr=4, min_lr=2)
print("    history:", [(r.step, r.action, round(r.candidate.score, 3)) for r in res.history])
print("    best_score =", res.best_score, " expensive_evals =", res.expensive_evals)
print("\nSMOKE OK")
