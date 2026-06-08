"""Stage-4 — small REAL K=1 vs K>1 QD validation on SpreadsheetBench + DeepSeek.

Frozen target (temp=0, seed via the fork patch). Both arms start from the SAME
frozen baseline and spend the SAME ``eval_budget`` (equal-budget red line). Prints
per-arm n_occupied / best_score / history / cross-cell + token usage, and the two
verdicts: does QD explore (n_occupied>1) and does K>1 beat K=1 at equal budget.

Reads .env. Tunable via env: N_SELECT, EVAL_BUDGET, K_BIG, MAX_TOKENS, WORKERS.
Run:  python tools/run_qd_validation.py
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

# Role-aware decoding (red line P2) — read by the fork's azure_openai._chat_impl.
os.environ.setdefault("TARGET_TEMPERATURE", "0")        # frozen target → reproducible eval
os.environ.setdefault("TARGET_SEED", "42")
os.environ.setdefault("OPTIMIZER_TEMPERATURE", "0.8")   # diverse optimizer → varied candidates

from skillopt.envs.spreadsheetbench.rollout import load_items  # noqa: E402

from qd.adapter_skillopt import configure_deepseek, make_producer  # noqa: E402
from qd.descriptor import descriptor  # noqa: E402
from qd.loop import run_search  # noqa: E402

N = int(os.environ.get("N_SELECT", "12"))
E = int(os.environ.get("EVAL_BUDGET", "6"))
K_BIG = int(os.environ.get("K_BIG", "4"))
MAXTOK = int(os.environ.get("MAX_TOKENS", "4096"))
WORKERS = int(os.environ.get("WORKERS", "8"))

INITIAL = (
    "You are an expert at spreadsheet manipulation. Read the input workbook with "
    "openpyxl from INPUT_PATH, perform exactly the requested edits, and save to "
    "OUTPUT_PATH. Return a single ```python``` code block."
)

cfg = configure_deepseek()
print(f"frozen: {cfg} temp=0 seed=42")
items = load_items(os.path.join(ROOT, "SkillOpt", "data", "spreadsheetbench_split", "test", "items.json"))[:N]
data_root = os.path.join(ROOT, "SkillOpt", "data", "spreadsheetbench_verified_400")
runs = os.path.join(ROOT, "runs", "val")
print(f"N_select={N} eval_budget={E}  K=1 vs K={K_BIG}  tasks={[it['id'] for it in items]}")

# Shared frozen baseline — scored once, injected into both arms.
base_prod = make_producer(items=items, data_root=data_root, out_root=os.path.join(runs, "baseline"),
                          workers=WORKERS, max_completion_tokens=MAXTOK)
base_score = base_prod.score(INITIAL)
base_cell = descriptor(base_prod.probe(INITIAL)).cell
print(f"baseline: hard={base_score}  cell={base_cell}")


def run_arm(k: int, tag: str):
    prod = make_producer(items=items, data_root=data_root, out_root=os.path.join(runs, tag),
                         workers=WORKERS, max_completion_tokens=MAXTOK)
    res = run_search(k=k, baseline_skill=INITIAL, baseline_score=base_score, eval_budget=E,
                     producer=prod, baseline_cell=(0 if k == 1 else base_cell), max_lr=4, min_lr=2)
    print(f"\n[{tag}] best={res.best_score}  n_occupied={res.n_occupied}  "
          f"cross_cell={res.cross_cell_pickups}  expensive_evals={res.expensive_evals}  n_proposed={res.n_proposed}")
    print(f"      history={[(h.step, h.action, round(h.candidate.score, 3), h.cell) for h in res.history]}")
    return res


r1 = run_arm(1, "k1")
rK = run_arm(K_BIG, f"k{K_BIG}")

try:
    from skillopt.model import get_token_summary
    print("\ntokens:", get_token_summary())
except Exception as e:  # noqa: BLE001
    print("\n(token summary unavailable:", e, ")")

print("\n=== VERDICT ===")
print(f"  baseline hard = {base_score}")
print(f"  K=1    best = {r1.best_score}")
print(f"  K={K_BIG}  best = {rK.best_score}   n_occupied = {rK.n_occupied}   cross_cell = {rK.cross_cell_pickups}")
print(f"  [Q1] QD explores (K>1 n_occupied > 1):              {rK.n_occupied > 1}")
print(f"  [Q2] QD payoff (K>1 best > K=1 best, equal budget): {rK.best_score > r1.best_score}")
