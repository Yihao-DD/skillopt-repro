#!/usr/bin/env python3
"""RR-SkillOpt reliability probe + reliability-routed test eval.

Two modes (NO training, NO optimizer — operates on a FIXED incumbent skill):

  --mode probe : run the per-benchmark verifier+repair on LABELED val (split="val"),
                 measure fix/break/trigger_rate against gold, apply the §3.2 OPEN
                 rule (qd.router.rver_decision) with the per-benchmark trigger cap,
                 and write router_decision.json (anti-oracle, PRE-test). Never test.

  --mode test  : read router_decision.json; if the repair channel is OPEN, evaluate
                 the incumbent skill on test WITH verified repair; else single-pass.
                 Reports attempt_hard (incumbent) -> test_hard (after routed repair).

Verifiers (handoff §3.5), per env:
  livemathematicianbench : math-check  (recompute / substitute-back / rule out distractors)
  searchqa               : evidence-span canonicalizer (shorten to a VERBATIM supported span;
                           deterministic repair; NOT fuzzy entailment)
  spreadsheetbench       : hard-invariant check (EXECUTION-grounded: repair only on exec
                           failure / timeout / missing output; NEVER on eval-mismatch)

Usage:
  # probe (val-only, $: small) -> router_decision.json
  python repro/official/rver_probe.py --env livemathematicianbench --mode probe \
      --skill outputs/lm_k1_s1/best_skill.md --key xx --tag rr_probe_lm
  # routed test eval (paid)
  python repro/official/rver_probe.py --env livemathematicianbench --mode test \
      --skill outputs/lm_k1_s1/best_skill.md --key xx --tag rr_test_lm
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLOPT_DIR = REPO_ROOT / "SkillOpt"
ENV_FILE = REPO_ROOT / ".env"
# Make sibling avp_eval.py importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Per-benchmark trigger caps — upper bound of each pre-registered range (§3.2).
TRIGGER_CAP = {"livemathematicianbench": 0.40, "searchqa": 0.15, "spreadsheetbench": 0.10}
ENVS = ("livemathematicianbench", "searchqa", "spreadsheetbench")


def load_env_file(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"[rr] .env not found at {path}")
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# ── SearchQA evidence-span canonicalizer (verify prompt + parse) ──────────────

_CANON_SCHEMA = (
    "Output ONLY this structured report and nothing else:\n"
    "VERDICT: PASS or FAIL\n"
    "CANONICAL_SPAN: <the SHORTEST span copied VERBATIM from the Context that directly answers "
    "the question, or NONE if the candidate is already a short exact answer or no single span "
    "answers it>\n"
    "REPAIR_NEEDED: yes or no"
)


def _sq_canon_verify_prompt(item: dict, answer: str, context: str) -> str:
    return (
        "You CANONICALIZE a candidate answer to a SHORT exact-match answer using ONLY the Context. "
        "Do NOT judge whether the answer is semantically correct or true. Your ONLY job: if the "
        "candidate is verbose / an explanation / longer than necessary, find the SHORTEST span "
        "copied VERBATIM from the Context that directly answers the question and propose it. If the "
        "candidate is already a short exact answer, or no single short span answers the question, "
        "return CANONICAL_SPAN: NONE.\n\n"
        f"{_CANON_SCHEMA}\n\n"
        f"## Context\n{context}\n\n## Question\n{item['question']}\n\n## Candidate answer\n{answer}"
    )


def _parse_canonical_span(text: str) -> str:
    m = re.search(r"^\s*CANONICAL_SPAN\s*:\s*(.+)$", text or "", re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


# ── LiveMath math-check v2 (consensus correction): verify prompt + vote parse ──

def _lm_v2_verify_prompt(item: dict, answer: str, output: str) -> str:
    from skillopt.envs.livemathematicianbench.rollout import _format_choices
    return (
        "You CHECK a candidate answer to a math multiple-choice question by INDEPENDENT "
        "recomputation. Recompute the decisive quantity yourself from scratch, substitute the chosen "
        "option back, and test the nearest competing options. FAIL ONLY if your independent "
        "recomputation shows the chosen option is WRONG and identifies a SPECIFIC correct option; if "
        "your recomputation agrees with the chosen option, or you are unsure, PASS.\n\n"
        "Output ONLY:\n"
        "VERDICT: PASS or FAIL\n"
        "CORRECTED_CHOICE: <the correct option letter if FAIL, else NONE>\n"
        "EVIDENCE: <your independent recomputation>\n\n"
        f"## Question\n{item['question']}\n\n## Choices\n{_format_choices(item['choices'])}\n\n"
        f"## Candidate answer\n{answer}\n\n## Candidate solution\n{output}"
    )


def _parse_lm_vote(text: str) -> tuple:
    """Parse one v2 verify pass into (verdict, corrected_choice_letter). A PASS, a
    missing/NONE choice, or an unparseable report yields ('PASS','') — conservative."""
    text = text or ""
    vm = re.search(r"^\s*VERDICT\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    verdict = "FAIL" if (vm and vm.group(1).strip().upper().startswith("FAIL")) else "PASS"
    choice = ""
    cm = re.search(r"^\s*CORRECTED_CHOICE\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if cm:
        raw = cm.group(1).strip()
        if raw and not raw.upper().startswith("NONE"):
            lm = re.search(r"[A-Za-z]", raw)
            if lm:
                choice = lm.group(0).upper()
    return (verdict, choice)


# math-check v3 (diverse-prompt consensus): true diversity at temp=0 via DIFFERENT checks,
# not sampling noise. Repair re-derives (recovery), only if >=min_agree framings independently FAIL.
_LM_FRAMINGS = (
    "Independently RECOMPUTE the decisive quantity from scratch and compare it to the chosen option.",
    "SUBSTITUTE the chosen option back into every condition stated in the problem and check each holds.",
    "ELIMINATE each NON-chosen option by testing it against the conditions; confirm the chosen option "
    "is the only one that survives.",
)


def _lm_v3_verify_prompt(item: dict, answer: str, output: str, framing: str) -> str:
    from avp_eval import _VERIFY_SCHEMA
    from skillopt.envs.livemathematicianbench.rollout import _format_choices
    return (
        "You are VERIFYING a candidate answer to a math multiple-choice question using ONE specific "
        f"check, nothing else. {framing} Do NOT freely rewrite the whole solution.\n\n"
        f"{_VERIFY_SCHEMA}\nRule: PASS unless THIS check finds a concrete, specific error backed by "
        "evidence. If this check is inconclusive, or it agrees with the chosen option, PASS.\n\n"
        f"## Question\n{item['question']}\n\n## Choices\n{_format_choices(item['choices'])}\n\n"
        f"## Candidate final answer\n{answer}\n\n## Candidate solution\n{output}"
    )


# ── per-item solvers (attempt -> verify -> conservative repair) ───────────────

def _solve_qa(env: str, item: dict, system: str, max_repairs: int,
              lm_consensus: int = 0, lm_min_agree: int = 2) -> dict:
    """LiveMath (math-check) / SearchQA (span-canonicalizer). Grades attempt AND
    final against gold so the probe can count fix/break; ``triggered`` = a repair
    actually fired (for trigger_rate)."""
    from avp_eval import answer_of, build_repair_prompt, build_user_for, grade, _sq_context
    from skillopt.model import chat_target
    from qd.avp import parse_verify_report, should_repair
    from qd.router import should_canonicalize_span

    user = build_user_for(env, item)
    out0, _ = chat_target(system=system, user=user, max_completion_tokens=16384,
                          retries=5, stage="rollout")
    hard0 = grade(env, out0, item)
    output = out0
    triggered = False

    for _ in range(max(0, max_repairs)):
        ans = answer_of(env, output, item)
        if env == "livemathematicianbench":
            if lm_consensus >= 2:
                from avp_eval import build_repair_prompt
                n_fail, last_report = 0, None
                for fr in _LM_FRAMINGS:   # diverse checks at temp=0 (true diversity, not sampling)
                    vt, _ = chat_target(system=system, user=_lm_v3_verify_prompt(item, ans, output, fr),
                                        max_completion_tokens=4096, retries=3, stage="rollout")
                    rep = parse_verify_report(vt)
                    if should_repair(rep):
                        n_fail += 1
                        last_report = rep
                if n_fail < lm_min_agree:   # consensus: need >=min_agree independent framings to FAIL
                    break
                triggered = True
                output, _ = chat_target(system=system, user=build_repair_prompt(env, item, output, last_report),
                                        max_completion_tokens=16384, retries=5, stage="rollout")
            else:
                from avp_eval import build_verify_prompt
                rep_text, _ = chat_target(system=system, user=build_verify_prompt(env, item, output, ans),
                                          max_completion_tokens=4096, retries=3, stage="rollout")
                report = parse_verify_report(rep_text)
                if not should_repair(report):
                    break
                triggered = True
                output, _ = chat_target(system=system, user=build_repair_prompt(env, item, output, report),
                                        max_completion_tokens=16384, retries=5, stage="rollout")
        elif env == "searchqa":
            ctx = _sq_context(item)
            rep_text, _ = chat_target(system=system, user=_sq_canon_verify_prompt(item, ans, ctx),
                                      max_completion_tokens=1024, retries=3, stage="rollout")
            span = _parse_canonical_span(rep_text)
            if not should_canonicalize_span(ans, span, ctx):
                break
            triggered = True
            output = f"<answer>{span}</answer>"  # deterministic A<-S; no semantic rewrite
        else:
            raise ValueError(env)

    final_hard = grade(env, output, item)
    return {
        "id": str(item.get("id")), "hard": final_hard, "hard_attempt": hard0,
        "flip": ("fix" if final_hard > hard0 else "break" if final_hard < hard0 else "none"),
        "triggered": triggered,
    }


def _solve_ssb(item: dict, skill: str, data_root: str, out_root: str, max_repairs: int) -> dict:
    """SpreadsheetBench hard-invariant: verify is a PURE function of the codegen
    result dict (golden-free exec facts) — repair (re-run with feedback) fires ONLY
    on a hard execution failure, so it can only touch already-failed items."""
    from skillopt.envs.spreadsheetbench.rollout import process_one_codegen
    from qd.avp import should_repair
    from qd.router import ssb_hard_invariant_verdict

    tid = str(item["id"])
    res = process_one_codegen(item, data_root, out_root, skill, mode="single",
                              max_turns=1, task_timeout=600)
    hard0 = int(res.get("hard", 0) or 0)
    final_hard = hard0
    triggered = False
    cur_out = out_root

    for r in range(max(0, max_repairs)):
        report = ssb_hard_invariant_verdict(res)
        if not should_repair(report):
            break
        triggered = True
        code = _read(os.path.join(cur_out, "predictions", tid, "code.py"))
        feedback = "\n".join(f"- {e}" for e in report.get("evidence", []))
        ctx = (f"Prior solution code:\n{code}\n\nThe prior run FAILED a hard execution check "
               f"(it did not run, timed out, or produced no usable output). Fix the execution "
               f"problem and regenerate the FULL corrected code:\n{feedback}")
        rep_out = os.path.join(out_root, f"rep{r}")
        res = process_one_codegen(item, data_root, rep_out, skill, mode="single",
                                  max_turns=1, task_timeout=600, diagnostic_trace_context=ctx)
        final_hard = int(res.get("hard", 0) or 0)
        cur_out = rep_out

    return {
        "id": tid, "hard": final_hard, "hard_attempt": hard0,
        "flip": ("fix" if final_hard > hard0 else "break" if final_hard < hard0 else "none"),
        "triggered": triggered,
    }


# ── item construction ─────────────────────────────────────────────────────────

def build_items(env: str, split: str, args) -> list[dict]:
    if env == "spreadsheetbench":
        from skillopt.envs.spreadsheetbench.adapter import SpreadsheetBenchAdapter
        split_dir = args.split_dir or "data/spreadsheetbench_split"
        ad = SpreadsheetBenchAdapter(split_dir=split_dir, split_mode="split_dir",
                                     data_root=args.data_root, mode="single", max_turns=1,
                                     max_completion_tokens=16384)
        ad.setup({"split_dir": split_dir, "split_mode": "split_dir", "data_root": args.data_root})
        return ad.build_eval_env(env_num=args.env_num, split=split, seed=args.seed)
    from avp_eval import build_eval_items
    split_dir = args.split_dir or f"data/{env}_split"
    return build_eval_items(env, split_dir, split, args.env_num, args.seed)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True, choices=list(ENVS))
    ap.add_argument("--mode", required=True, choices=["probe", "probe_cal", "test"],
                    help="probe=val-only(D_sel); probe_cal=train+val(D_cal, power-adjusted); test=routed.")
    ap.add_argument("--bar", choices=["net", "sign"], default="net",
                    help="test-mode gate field: net (raw floor) or sign (one-sided sign test).")
    ap.add_argument("--structural-precision", action="store_true",
                    help="test mode: waive the trigger cap for a structurally-safe verifier "
                         "(only re-runs already-failed items -> precision structurally 1.0). "
                         "Recomputes + persists the router decision with the documented override.")
    ap.add_argument("--lm-consensus", type=int, default=0,
                    help="LiveMath math-check v2: N independent verify passes; repair (deterministic "
                         "A<-choice) iff >=lm-min-agree agree FAIL + same corrected choice. 0=off=v1.")
    ap.add_argument("--lm-min-agree", type=int, default=2)
    ap.add_argument("--skill", default="", help="Path (rel SkillOpt/) to incumbent best_skill.md.")
    ap.add_argument("--max-repairs", type=int, default=1)
    ap.add_argument("--key", choices=["env", "dion", "yh", "yw", "tt", "xx", "xnyu", "x2"], default="env")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--split-dir", default="", help="Default: data/<env>_split.")
    ap.add_argument("--data-root", default="data/spreadsheetbench_verified_400", help="SSB only.")
    ap.add_argument("--env-num", type=int, default=0, help="0=all items in split; >0 caps (smoke).")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--trigger-cap", type=float, default=-1.0, help="Override; default per-env §3.2.")
    ap.add_argument("--router-json", default="", help="Path (rel SkillOpt/) to router_decision.json. "
                    "Default outputs/rr_router/<env>.json. probe WRITES it; test READS it.")
    ap.add_argument("--tag", default="rr")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    if not SKILLOPT_DIR.is_dir():
        sys.exit(f"[rr] SkillOpt/ not found at {SKILLOPT_DIR}")
    env_vars = load_env_file(ENV_FILE)
    key_val = env_vars.get("AZURE_OPENAI_API_KEY", "")
    if args.key != "env":
        kname = f"DEEPSEEK_KEY_{args.key.upper()}"
        if kname not in env_vars:
            sys.exit(f"[rr] {kname} not in .env")
        key_val = env_vars[kname]
    endpoint = env_vars.get("AZURE_OPENAI_ENDPOINT", "https://api.deepseek.com")

    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(SKILLOPT_DIR))
    os.chdir(SKILLOPT_DIR)
    os.environ["TARGET_TEMPERATURE"] = "0"
    os.environ["TARGET_SEED"] = "42"
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint
    os.environ["AZURE_OPENAI_API_KEY"] = key_val

    # SAFETY: probe=val-only, probe_cal=train+val (non-test dev), test=test-only. Never a footgun.
    is_probe = args.mode in ("probe", "probe_cal")
    trigger_cap = args.trigger_cap if args.trigger_cap >= 0 else TRIGGER_CAP[args.env]
    default_router = (f"outputs/rr_router/{args.env}_dcal.json" if args.mode == "probe_cal"
                      else f"outputs/rr_router/{args.env}.json")
    router_json = args.router_json or default_router

    skill = ""
    if args.skill:
        sp = Path(args.skill)
        if not sp.is_file():
            sys.exit(f"[rr] skill not found: {sp} (cwd={os.getcwd()})")
        skill = sp.read_text(encoding="utf-8")

    # In test mode, the router decides whether the repair channel may run.
    repair_open = True
    router_doc = None
    if args.mode == "test":
        rp = Path(router_json)
        if not rp.is_file():
            sys.exit(f"[rr] test mode needs router_decision.json at {rp} — run --mode probe first.")
        router_doc = json.loads(rp.read_text(encoding="utf-8"))
        gate_field = "open_sign" if args.bar == "sign" else "open"
        rv = router_doc.get("r_ver", {})
        if args.structural_precision:
            from qd.router import rver_decision
            rv = rver_decision(fix=int(rv.get("fix", 0)), break_=int(rv.get("break", 0)),
                               n_val=int(rv.get("n_val", 0)),
                               trigger_rate=float(rv.get("trigger_rate", 0.0)),
                               trigger_cap=float(rv.get("trigger_cap", 1.0)),
                               structural_precision=True)
            rv["override_reason"] = ("trigger cap waived: verifier only re-runs already-failed "
                                     "items (precision structurally 1.0)")
            router_doc["r_ver"] = rv
            chans = ["training"] if router_doc.get("r_sel", {}).get("open") else []
            if rv.get(gate_field):
                chans.append("repair")
            router_doc["test_channels"] = chans
            rp.write_text(json.dumps(router_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        repair_open = bool(rv.get(gate_field))
    max_repairs = args.max_repairs if (is_probe or repair_open) else 0

    # Build items per mode (probe=val / probe_cal=train+val / test=test). n_dsel = D_sel size for R_sel.
    if args.mode == "probe_cal":
        val_items = build_items(args.env, "val", args)
        items = build_items(args.env, "train", args) + val_items
        n_dsel = len(val_items)
        split = "dcal_train+val"
    else:
        split = "val" if args.mode == "probe" else "test"
        items = build_items(args.env, split, args)
        n_dsel = len(items) if args.mode == "probe" else 0
    print("=" * 72)
    print(f"[rr] env={args.env} mode={args.mode} split={split} tag={args.tag} key={args.key} "
          f"skill={'<none>' if not skill else args.skill} items={len(items)} "
          f"max_repairs={max_repairs} trigger_cap={trigger_cap}")
    if args.mode == "test":
        print(f"[rr] router {router_json}: repair_open={repair_open} "
              f"(r_ver={router_doc.get('r_ver') if router_doc else None})")
    print("=" * 72)
    if args.dry:
        print("[rr] --dry: items built, model not called.")
        return 0

    from skillopt.model import set_target_backend, set_target_deployment, set_reasoning_effort
    from skillopt.model.azure_openai import configure_azure_openai
    configure_azure_openai(auth_mode="openai_compatible", endpoint=endpoint, api_key=key_val)
    set_target_backend("openai_chat")
    set_target_deployment(env_vars.get("TARGET_MODEL", "deepseek-chat"))
    set_reasoning_effort(None)

    out_dir = SKILLOPT_DIR / "outputs" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    system = ""
    if args.env != "spreadsheetbench":
        from avp_eval import build_system_for
        system = build_system_for(args.env, skill)

    def run_one(it: dict) -> dict:
        if args.env == "spreadsheetbench":
            return _solve_ssb(it, skill, args.data_root, str(out_dir), max_repairs)
        return _solve_qa(args.env, it, system, max_repairs, args.lm_consensus, args.lm_min_agree)

    t0 = time.time()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, it): it for it in items}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001
                rid = str(futs[fut].get("id"))
                print(f"[rr] item {rid} errored: {e}")
                results.append({"id": rid, "hard": 0, "hard_attempt": 0, "flip": "none",
                                "triggered": False, "error": str(e)})
            if i % 40 == 0:
                print(f"[rr] {i}/{len(items)} done ({time.time()-t0:.0f}s)")

    n = len(results)
    attempt_hard = sum(r["hard_attempt"] for r in results) / n if n else 0.0
    test_hard = sum(r["hard"] for r in results) / n if n else 0.0
    n_fix = sum(1 for r in results if r["flip"] == "fix")
    n_break = sum(1 for r in results if r["flip"] == "break")
    n_trig = sum(1 for r in results if r.get("triggered"))
    trigger_rate = (n_trig / n) if n else 0.0

    summary = {
        "tag": args.tag, "env": args.env, "mode": args.mode, "split": split, "seed": args.seed,
        "skill": args.skill or "<none>", "n": n,
        "attempt_hard": round(attempt_hard, 4), "test_hard": round(test_hard, 4),
        "delta": round(test_hard - attempt_hard, 4),
        "n_fix": n_fix, "n_break": n_break, "n_triggered": n_trig,
        "trigger_rate": round(trigger_rate, 4), "wall_s": round(time.time() - t0, 1),
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(out_dir / "results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if is_probe:
        from qd.router import build_router_decision, rver_decision
        r_ver = rver_decision(fix=n_fix, break_=n_break, n_val=n,
                              trigger_rate=trigger_rate, trigger_cap=trigger_cap)
        r_sel = {"open": n_dsel >= 30, "n_sel": n_dsel, "rule": "n_sel>=30 (full governor ran in RG training)"}
        doc = build_router_decision(args.env, r_sel, r_ver)
        doc["probe_tag"] = args.tag
        doc["incumbent_skill"] = args.skill or "<none>"
        doc["calibration_set"] = "D_train+D_sel" if args.mode == "probe_cal" else "D_sel"
        doc["n_cal"] = n
        rp = SKILLOPT_DIR / router_json
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("=" * 72)
        print(f"[rr] PROBE {args.env} ({doc['calibration_set']}, n_cal={n}): attempt={attempt_hard:.4f} "
              f"fix={n_fix} break={n_break} net={n_fix - n_break} precision={r_ver['precision']} "
              f"trigger_rate={trigger_rate:.3f} cap={trigger_cap}")
        print(f"[rr] R_ver: net-bar open={r_ver['open']} (net_min={r_ver['net_min']}) | "
              f"sign-bar open={r_ver['open_sign']} (p={r_ver['p_sign']}, alpha={r_ver['alpha']}) | "
              f"R_sel open={r_sel['open']} (n_sel={n_dsel})")
        print(f"[rr] router_decision -> {router_json}")
    else:
        print("=" * 72)
        print(f"[rr] TEST {args.env}: attempt_hard={attempt_hard:.4f} -> test_hard={test_hard:.4f} "
              f"(delta={summary['delta']:+.4f}) repair_open={repair_open} "
              f"fix={n_fix} break={n_break} triggered={n_trig} n={n}")
    print(f"[rr] summary: outputs/{args.tag}/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
