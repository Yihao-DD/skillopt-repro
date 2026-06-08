"""Feasibility spike (REORG) — NOT the headline run.

Proves two things cheaply on the REAL DeepSeek API (temperature=0, deterministic):
  1. connectivity — the key + OpenAI-compatible endpoint work;
  2. the behavior descriptor (``qd.descriptor``, ADR-0006) separates REAL DeepSeek
     code-generation behaviors into >1 cell — the necessary condition for QD to
     help, and the open question flagged by the audit / ADR-0006.

It does NOT run the full QD loop or score on SpreadsheetBench. It asks DeepSeek to
solve ONE fixed task under a few hand-written skill strategies and bins each
generated program with the real descriptor. ~5 calls, a few cents.

Run:  python tools/spike_deepseek_feasibility.py     (reads .env for the key)
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

from openai import OpenAI  # noqa: E402

from qd.descriptor import code_features, descriptor  # noqa: E402

KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
BASE = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://api.deepseek.com")
MODEL = os.environ.get("TARGET_MODEL", "deepseek-chat")
if not KEY:
    sys.exit("no AZURE_OPENAI_API_KEY in .env")

client = OpenAI(api_key=KEY, base_url=BASE)


def call(system: str, user: str, max_tokens: int = 700) -> str:
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=max_tokens,
    )
    return r.choices[0].message.content or ""


def extract_code(text: str) -> str:
    if "```" in text:
        seg = text.split("```", 2)[1]
        if seg.lower().startswith("python"):
            seg = seg[6:]
        return seg.strip()
    return text.strip()


print("== Tier 1: connectivity ==")
try:
    pong = call("You are a ping endpoint.", "Reply with the single word OK.", max_tokens=5)
    print("  reply:", repr(pong.strip()[:40]))
except Exception as e:  # noqa: BLE001
    sys.exit(f"  CONNECTIVITY FAILED: {type(e).__name__}: {e}")

print("\n== Tier 2: descriptor diversity on REAL DeepSeek behavior ==")
TASK = (
    "Task: read 'sales.xlsx' with columns Region and Amount, compute the total "
    "Amount per Region, and write 'summary.xlsx' with columns Region, Total. "
    "Return ONLY one python code block."
)
STRATEGIES = {
    "pandas-groupby": "Solve spreadsheet tasks with pandas only: read_excel, groupby, to_excel. Vectorized and concise.",
    "openpyxl-manual": "Solve with openpyxl ONLY (never import pandas): load_workbook, iterate rows with for-loops, accumulate totals in a dict, write cells one by one.",
    "pandas-iterrows": "Solve with pandas but use explicit for-loops over df.iterrows() (no groupby) to accumulate totals.",
    "minimal": "Write the shortest correct pandas solution, as few lines as possible.",
}

cells: dict[str, int] = {}
for name, sysp in STRATEGIES.items():
    code = extract_code(call(sysp, TASK))
    d = descriptor([{"code": code}])
    f = code_features(code)
    cells[name] = d.cell
    print(
        f"  {name:16s} cell={d.cell:2d}  b={tuple(round(x, 3) for x in d.b)}  "
        f"lines={f['lines']} pandas={f['uses_pandas']} openpyxl={f['uses_openpyxl']} "
        f"ctrl={f['n_ctrl']} ops={f['n_ops']}"
    )

distinct = sorted(set(cells.values()))
print(f"\n  n_occupied (distinct descriptor cells) = {len(distinct)}  cells={distinct}")
print(f"  FEASIBLE (real DeepSeek behaviors separate into >1 cell): {len(distinct) > 1}")
