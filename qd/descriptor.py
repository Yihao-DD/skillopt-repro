"""QD behavioral descriptor ``b`` — Tier-A v0 (T002).

Maps a skill to a behavior cell from its *trajectory* τ, **never from the skill
text** (BRIEF §4 red line / SPEC §3.1). For SpreadsheetBench codegen, τ exposes
the generated program (``predictions/<id>/code.py``) + ``n_turns``. We extract a
bounded feature vector φ(τ)∈[0,1]^p describing *how* the skill solves (code
length, library strategy, control-flow & op density, iteration), average over a
probe set to μ(s), then a hand-set Tier-A projection ``g`` → 2 interpretable
axes → grid cell.

Why code-level (see qd/tests/fixtures + T002 status): result-level fields
(``n_turns``/``exec_ok``) *saturate* across skills (best≈initial → they track
performance, not strategy). Code-level features separate strategy — best favors
verbose openpyxl + control flow, initial leans pandas. The descriptor must see
that behavioral gap, else QD binning collapses onto fitness.

Pure stdlib, deterministic, zero API.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── bounded-normalization references (from observed SpreadsheetBench code stats)
_LINES_REF = 120.0   # ~2x observed mean; caps long programs to 1.0
_CTRL_REF = 24.0     # for+if count
_OPS_REF = 16.0      # spreadsheet-op count
_TURNS_REF = 5.0     # observed max n_turns

_OPS_RE = re.compile(
    r"\.iloc|\.loc|\.drop|read_excel|to_excel|load_workbook|\.cell\(|\.append\("
    r"|\.sort|\.groupby|\.apply\(|\.fillna|\.str\."
)
_FOR_RE = re.compile(r"\bfor\b")
_IF_RE = re.compile(r"\bif\b")
_PD_RE = re.compile(r"\bpd\.")

# φ axis labels (p = 5), in order.
PHI_LABELS = ("code_len", "uses_pandas", "ctrl_density", "op_density", "iter_depth")


def code_features(code: str) -> dict:
    """Raw (unbounded) code-strategy counts from one generated program."""
    code = code or ""
    return {
        "lines": code.count("\n") + 1 if code else 0,
        "uses_pandas": 1 if (("pandas" in code) or (_PD_RE.search(code) is not None)) else 0,
        "uses_openpyxl": 1 if "openpyxl" in code else 0,
        "n_ctrl": len(_FOR_RE.findall(code)) + len(_IF_RE.findall(code)),
        "n_ops": len(_OPS_RE.findall(code)),
    }


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def phi(traj: dict) -> list[float]:
    """Bounded behavioral features φ(τ) ∈ [0,1]^5 for one rollout.

    ``traj`` may carry raw ``code`` (str) — parsed here — or pre-extracted
    ``lines/uses_pandas/n_ctrl/n_ops`` counts. ``n_turns`` optional (default 1).
    """
    f = code_features(traj["code"]) if "code" in traj else traj
    n_turns = traj.get("n_turns") or 1
    return [
        _clip01(f.get("lines", 0) / _LINES_REF),
        _clip01(float(f.get("uses_pandas", 0))),
        _clip01(f.get("n_ctrl", 0) / _CTRL_REF),
        _clip01(f.get("n_ops", 0) / _OPS_REF),
        _clip01(n_turns / _TURNS_REF),
    ]


def mu(trajs: list[dict]) -> list[float]:
    """Probe-set mean μ(s) = E_{x∈P} φ(τ(s;x)) ∈ [0,1]^p."""
    if not trajs:
        raise ValueError("empty probe set")
    vecs = [phi(t) for t in trajs]
    p = len(vecs[0])
    return [sum(v[i] for v in vecs) / len(vecs) for i in range(p)]


def project(mu_vec: list[float]) -> tuple[float, float]:
    """Tier-A hand-set g: μ∈[0,1]^5 → 2 interpretable axes ∈ [0,1]^2.

    axis0 = solution complexity (code length + control flow + op density).
    axis1 = library strategy (0 = pandas-heavy … 1 = openpyxl/manual-heavy).
    """
    code_len, uses_pandas, ctrl, ops, _iter = mu_vec
    complexity = _clip01((code_len + ctrl + ops) / 3.0)
    strategy = _clip01(1.0 - uses_pandas)
    return (complexity, strategy)


def cell_of(b: tuple[float, float], nbins: int = 4) -> int:
    """Map a 2-D behavior point to a flat grid cell index in [0, nbins^2)."""
    def _bin(x: float) -> int:
        return min(int(_clip01(x) * nbins), nbins - 1)
    return _bin(b[0]) * nbins + _bin(b[1])


@dataclass(frozen=True)
class Descriptor:
    b: tuple[float, float]
    cell: int


def descriptor(trajs: list[dict], nbins: int = 4) -> Descriptor:
    """Full pipeline: probe trajectories → μ → Tier-A b → cell."""
    b = project(mu(trajs))
    return Descriptor(b=b, cell=cell_of(b, nbins))
