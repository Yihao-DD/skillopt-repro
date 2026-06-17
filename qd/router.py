"""RR-SkillOpt router: pure reliability-routing decisions (zero-API).

The training channel's reliability (``R_sel``) lives in ``qd/reliability.py`` (the
governor). This module is the *inference* channel's reliability (``R_ver``) plus the
two verifier-specific pure decisions and the ``router_decision.json`` assembly.

Everything here is conservative by construction and dependency-free, mirroring the
AVP gate in ``qd/avp.py``: when a channel is not provably reliable on LABELED
development data, it stays CLOSED and the incumbent answer/skill is kept.
"""
from __future__ import annotations

import math
import re
import string


# ── R_ver: the pre-registered OPEN rule (handoff §3.2) ────────────────────────

def sign_test_one_sided(fix: int, break_: int) -> float:
    """One-sided sign test p-value for fix > break among discordant items:
    P(X >= fix | X ~ Binomial(fix+break, 0.5)). Returns 1.0 when there are no
    discordant items (no evidence). This is the power-correct instrument for the
    OPEN rule on larger calibration sets, where a raw net floor is too weak."""
    n = int(fix) + int(break_)
    if n <= 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(int(fix), n + 1)) * (0.5 ** n)


def rver_decision(
    *,
    fix: int,
    break_: int,
    n_val: int,
    trigger_rate: float,
    trigger_cap: float,
    precision_min: float = 0.60,
    abs_net_min: int = 2,
    frac: float = 0.01,
    alpha: float = 0.10,
    structural_precision: bool = False,
) -> dict:
    """Decide whether the verify+repair (AVP) channel may touch test, from its
    fix/break counts measured on LABELED val/D_sel.

    OPEN iff ALL hold:
      net = fix - break >= max(abs_net_min, ceil(frac * n_val))
      fix > break
      precision = fix / (fix + break) >= precision_min
      trigger_rate <= trigger_cap

    Cleanly blocks the known failures (SSB-AVP 2:18, SearchQA-AVP 3:8) and opens a
    net-positive, precise, infrequently-firing repair (LiveMath math-check)."""
    net = int(fix) - int(break_)
    denom = int(fix) + int(break_)
    precision = (fix / denom) if denom else 0.0
    net_min = max(int(abs_net_min), math.ceil(frac * n_val))
    p_sign = sign_test_one_sided(fix, break_)
    # The trigger cap is a PRECISION proxy. A verifier that only acts on already-failed
    # items (e.g. ssb hard-invariant — it re-runs only exec-failed code) cannot break a
    # correct answer, so precision is structurally 1.0 and the cap does not apply.
    cap_ok = structural_precision or (trigger_rate <= trigger_cap)
    common = (fix > break_) and (precision >= precision_min) and cap_ok
    is_open = common and (net >= net_min)        # lenient bar: raw net floor (handoff default)
    open_sign = common and (p_sign <= alpha)     # strong bar: one-sided sign test
    return {
        "open": bool(is_open),
        "decision": "open" if is_open else "abstain",
        "open_sign": bool(open_sign),
        "p_sign": round(p_sign, 4),
        "alpha": float(alpha),
        "structural_precision": bool(structural_precision),
        "fix": int(fix),
        "break": int(break_),
        "net": int(net),
        "net_min": int(net_min),
        "precision": round(precision, 4),
        "trigger_rate": round(float(trigger_rate), 4),
        "trigger_cap": float(trigger_cap),
        "n_val": int(n_val),
    }


# ── SearchQA span canonicalizer (pure decision) ───────────────────────────────

def _normalize(s: str) -> str:
    """SQuAD-style normalization (mirrors searchqa.evaluator.normalize_answer) so
    the verbatim-span check aligns with how EM is graded."""
    s = (s or "").lower()
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split()).strip()


def should_canonicalize_span(candidate: str, span: str, evidence_text: str) -> bool:
    """True iff the candidate answer should be replaced by the (shorter) evidence
    span S. Conservative: S must be non-empty, differ from A, appear VERBATIM in
    the evidence (normalized), and be strictly SHORTER (fewer tokens) than A — i.e.
    a genuine shortening to a supported span, never semantic rewriting."""
    span_raw = (span or "").strip()
    if not span_raw or span_raw.upper() == "NONE":
        return False
    ns, nc, ne = _normalize(span), _normalize(candidate), _normalize(evidence_text)
    if not ns:
        return False
    if ns == nc:
        return False  # candidate already equals the span — nothing to shorten
    if ns not in ne:
        return False  # span is not verbatim-present in the evidence
    if len(ns.split()) >= len(nc.split()):
        return False  # must be a shortening, not a lengthening/rewrite
    return True


# ── SSB hard-invariant verdict (execution-grounded, golden-free) ──────────────

def ssb_hard_invariant_verdict(result: dict) -> dict:
    """Build a verify report (qd.avp shape) from a process_one_codegen result dict
    using ONLY golden-free execution facts. Trigger a repair iff a HARD execution
    invariant is violated (code didn't run / produced no openable output / timed
    out). NEVER trigger on ``eval-mismatch`` (that is a semantic/golden judgment,
    exactly the SSB code-review failure mode we are avoiding)."""
    fail_reason = result.get("fail_reason") or ""
    fr = fail_reason.lower()
    exec_ok = result.get("exec_ok")
    semantic_only = fr.startswith("eval-mismatch")
    exec_failed = (exec_ok is not True) or (result.get("phase") == "timeout")
    if exec_failed and not semantic_only:
        evidence = fail_reason.strip() or f"exec_ok={exec_ok}, phase={result.get('phase')}"
        return {
            "verdict": "FAIL",
            "error_type": "execution_bug",
            "evidence": [f"execution invariant violated: {evidence}"],
            "repair_needed": True,
        }
    return {"verdict": "PASS", "error_type": "none", "evidence": [], "repair_needed": False}


# ── router_decision.json assembly (anti-oracle, written pre-test) ──────────────

def build_router_decision(benchmark: str, r_sel: dict, r_ver: dict) -> dict:
    """Assemble the per-benchmark routing record. ``test_channels`` lists exactly
    the channels allowed to touch test (training if R_sel open, repair if R_ver
    open); an empty list means abstain → evaluate the incumbent single-pass."""
    channels: list[str] = []
    if r_sel.get("open"):
        channels.append("training")
    if r_ver.get("open"):
        channels.append("repair")
    return {
        "benchmark": benchmark,
        "r_sel": r_sel,
        "r_ver": r_ver,
        "test_channels": channels,
    }
