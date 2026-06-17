"""Pure Attempt-Verify-Patch (AVP) control logic for inference-time repair.

Zero-API: the attempt / verify / repair model calls are injected as callables, so
the control loop and the conservative-repair gate are deterministic and
unit-tested. The LLM prompts + ``chat_target`` calls live in the eval harness
(``repro/official/avp_eval.py``).

Philosophy: the trained skill brings the agent to a good initial trajectory; AVP
then lets the SAME model find and minimally fix a per-item error using task-local
evidence. Conservative by construction — repair ONLY on a FAIL verdict backed by
concrete evidence; otherwise keep the original answer (avoids verifier false
positives turning a correct answer wrong).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

VERDICTS = ("PASS", "FAIL")
ERROR_TYPES = (
    "none", "arithmetic", "evidence_mismatch", "format",
    "constraint_violation", "execution_bug", "unsupported_answer",
)


def _field(text: str, name: str) -> str:
    """Value after a ``NAME:`` line (case-insensitive), or ''."""
    m = re.search(rf"^\s*{name}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def parse_verify_report(text: str) -> dict:
    """Parse the structured verifier report into
    ``{verdict, error_type, evidence, repair_needed}``.

    Conservative defaults: a missing / unrecognized VERDICT is treated as PASS
    (keep the original answer), so an unparseable verifier can never trigger a
    repair."""
    text = text or ""
    verdict = "FAIL" if _field(text, "VERDICT").upper().startswith("FAIL") else "PASS"

    et_raw = _field(text, "ERROR_TYPE").lower()
    error_type = et_raw.split()[0] if et_raw.split() else "none"
    if error_type not in ERROR_TYPES:
        error_type = "other" if error_type and error_type != "none" else "none"

    repair_needed = _field(text, "REPAIR_NEEDED").lower().startswith("y")

    evidence: list[str] = []
    m = re.search(
        r"EVIDENCE\s*:(.*?)(?:\n\s*REPAIR_NEEDED|\n\s*VERDICT|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip().lstrip("-*•").strip()
            if ln:
                evidence.append(ln)

    return {
        "verdict": verdict,
        "error_type": error_type,
        "evidence": evidence,
        "repair_needed": repair_needed,
    }


def has_concrete_evidence(report: dict) -> bool:
    """True iff the report cites >=1 specific evidence line AND names a real
    (non-``none``) error type — the bar for allowing a repair."""
    return bool(report.get("evidence")) and report.get("error_type") not in ("none", "")


def should_repair(report: dict) -> bool:
    """Conservative repair gate: repair ONLY when the verdict is FAIL, a repair is
    requested, AND there is concrete evidence of a specific error. PASS, missing
    evidence, or ``error_type=none`` -> keep the original answer."""
    return (
        report.get("verdict") == "FAIL"
        and bool(report.get("repair_needed", False))
        and has_concrete_evidence(report)
    )


def run_avp_loop(
    *,
    attempt: Callable[[], str],
    verify: Callable[[str], str],
    repair: Callable[[str, dict], str],
    max_repairs: int = 1,
) -> "tuple[str, list[dict]]":
    """Attempt -> (Verify -> conservative Patch) up to ``max_repairs`` times.

    ``attempt()`` returns the initial answer; ``verify(output)`` returns a raw
    report string; ``repair(output, report)`` returns a revised answer. Stops
    early as soon as a verdict is PASS or lacks concrete evidence. Returns
    ``(final_output, trace)`` where trace records each verify step's verdict /
    error_type / whether it repaired."""
    output = attempt()
    trace: list[dict] = [{"stage": "attempt"}]
    for _ in range(max(0, int(max_repairs))):
        report = parse_verify_report(verify(output))
        step = {
            "stage": "verify",
            "verdict": report["verdict"],
            "error_type": report["error_type"],
            "repaired": False,
        }
        if not should_repair(report):
            trace.append(step)
            break
        output = repair(output, report)
        step["repaired"] = True
        trace.append(step)
    return output, trace


def consensus_correction(
    votes: "list[tuple[str, str]]", min_agree: int = 2
) -> "tuple[bool, str]":
    """Noise-filtering inference repair (math-check v2). ``votes`` is a list of
    ``(verdict, corrected_choice)`` from N independent verify passes. Repair ONLY
    when at least ``min_agree`` passes BOTH say FAIL and agree on the SAME non-empty
    corrected choice; that agreed choice is then the deterministic replacement.

    Drops noise-driven false repairs (a lone FAIL, or FAILs that disagree on the
    fix) — the source of the v1 verifier's high trigger rate and its breaks — while
    keeping genuine, consistently-detected corrections."""
    fails = [c for (verdict, c) in votes if verdict == "FAIL" and c]
    if not fails:
        return (False, "")
    choice, count = Counter(fails).most_common(1)[0]
    if count >= int(min_agree):
        return (True, choice)
    return (False, "")
