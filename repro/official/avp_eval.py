#!/usr/bin/env python3
"""Post-hoc Attempt-Verify-Patch (AVP) inference eval — NO training, NO optimizer.

Loads a FIXED skill and runs each test item through attempt -> verify -> conservative
repair using the SAME target model (temp=0), then grades with the env's deterministic
grader. Tests whether inference-time self-checking lifts an already-trained skill,
WITHOUT touching the optimizer / trainer / D_sel (the proven SSB selection wall).

One arm per invocation (tag + skill + max_repairs). Supported envs:
  livemathematicianbench : MCQ; grade = exact label; per-seed choice shuffle.
  searchqa               : open QA; grade = SQuAD EM; evidence-grounded verifier;
                           seed-independent eval set; context truncated to 6000 chars.

Arms (mirror across envs):
  skill-single   : --skill <best_skill> --max-repairs 0
  skill-AVP-1    : --skill <best_skill> --max-repairs 1
  skill-AVP-2    : --skill <best_skill> --max-repairs 2
  NoSkill-AVP-1  : (omit --skill)        --max-repairs 1

Usage:
  python repro/official/avp_eval.py --env searchqa --key xx \
      --skill outputs/searchqa_dpsk_run1/best_skill.md --max-repairs 1 --tag sq_avp1
  python repro/official/avp_eval.py ... --env-num 8 --dry        # plumbing smoke
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLOPT_DIR = REPO_ROOT / "SkillOpt"
ENV_FILE = REPO_ROOT / ".env"


def load_env_file(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"[avp] .env not found at {path}")
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ── env-specific primitives (dispatch; shared outer AVP protocol) ─────────────

def build_system_for(env: str, skill: str) -> str:
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.rollout import _build_system
        return _build_system(skill)
    if env == "searchqa":
        from skillopt.envs.searchqa.rollout import _build_system
        return _build_system(skill)
    raise ValueError(env)


def build_user_for(env: str, item: dict) -> str:
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.rollout import _build_user
        return _build_user(item, use_theorem=False, use_sketch=False)
    if env == "searchqa":
        from skillopt.envs.searchqa.rollout import _build_user
        return _build_user(item["question"], item.get("context", ""))
    raise ValueError(env)


def answer_of(env: str, output: str, item: dict) -> str:
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.evaluator import parse_choice_label
        return parse_choice_label(output, item["choices"])
    if env == "searchqa":
        from skillopt.envs.searchqa.evaluator import extract_answer
        return extract_answer(output)
    raise ValueError(env)


def grade(env: str, output: str, item: dict) -> int:
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.evaluator import evaluate
        return int(evaluate(output, item["correct_choice"], item["choices"])["em"])
    if env == "searchqa":
        from skillopt.envs.searchqa.evaluator import evaluate
        return int(evaluate(output, item.get("answers", []))["em"])
    raise ValueError(env)


def build_eval_items(env: str, split_dir: str, split: str, env_num: int, seed: int) -> list[dict]:
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.adapter import LiveMathematicianBenchAdapter
        ad = LiveMathematicianBenchAdapter(split_dir=split_dir, split_mode="split_dir",
                                           shuffle_choices=True, max_turns=1, max_completion_tokens=16384)
        ad.setup({"split_dir": split_dir, "split_mode": "split_dir"})
        return ad.build_eval_env(env_num=env_num, split=split, seed=seed)
    if env == "searchqa":
        from skillopt.envs.searchqa.adapter import SearchQAAdapter
        ad = SearchQAAdapter(split_dir=split_dir, split_mode="split_dir",
                             max_turns=1, max_completion_tokens=16384)
        ad.setup({"split_dir": split_dir, "split_mode": "split_dir"})
        return ad.build_eval_env(env_num=env_num, split=split, seed=seed)
    raise ValueError(env)


_VERIFY_SCHEMA = (
    "Output ONLY this structured report and nothing else:\n"
    "VERDICT: PASS or FAIL\n"
    "ERROR_TYPE: none | arithmetic | evidence_mismatch | format | constraint_violation | execution_bug | unsupported_answer\n"
    "EVIDENCE:\n- <concrete check results that justify the verdict>\n"
    "REPAIR_NEEDED: yes or no"
)


def _sq_context(item: dict) -> str:
    from skillopt.envs.searchqa.rollout import _truncate_context
    return _truncate_context(item.get("context", ""))


def build_verify_prompt(env: str, item: dict, output: str, answer: str) -> str:
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.rollout import _format_choices
        return (
            "You are VERIFYING a candidate answer to the math multiple-choice question below. "
            "Do NOT freely rewrite the solution. Run task-local checks: substitute the chosen "
            "option back into the problem, recompute the key equation/quantity, check boundary "
            "and edge conditions, and rule out the distractor options.\n\n"
            f"{_VERIFY_SCHEMA}\nRule: PASS unless you find a concrete, specific error backed by "
            "evidence. If unsure, PASS.\n\n"
            f"## Question\n{item['question']}\n\n## Choices\n{_format_choices(item['choices'])}\n\n"
            f"## Candidate final answer\n{answer}\n\n## Candidate solution\n{output}"
        )
    if env == "searchqa":
        return (
            "You are VERIFYING a candidate answer to the question below, using ONLY the provided "
            "Context. Steps: (1) find the exact sentence/span in the Context that addresses the "
            "question; (2) check whether the candidate answer is DIRECTLY entailed by that span; "
            "(3) FAIL only if the answer is unsupported, contradicted, or not the shortest "
            "span-supported form. Use ERROR_TYPE evidence_mismatch (not supported by any span), "
            "unsupported_answer (no span addresses it), or format (right info, wrong form). Quote "
            "the exact span in EVIDENCE.\n\n"
            f"{_VERIFY_SCHEMA}\nRule: PASS if a span directly supports the answer. If unsure, PASS.\n\n"
            f"## Context\n{_sq_context(item)}\n\n## Question\n{item['question']}\n\n"
            f"## Candidate answer\n{answer}"
        )
    raise ValueError(env)


def build_repair_prompt(env: str, item: dict, output: str, report: dict) -> str:
    ev = "\n".join(f"- {e}" for e in report.get("evidence", []))
    if env == "livemathematicianbench":
        from skillopt.envs.livemathematicianbench.rollout import _format_choices
        return (
            "A verification pass found a SPECIFIC error in your earlier answer to the question "
            "below. Fix ONLY that error; keep everything that was already correct. Re-derive "
            "carefully and output your corrected final choice as <answer>X</answer>.\n\n"
            f"## Verification (ERROR_TYPE={report.get('error_type')})\n{ev}\n\n"
            f"## Question\n{item['question']}\n\n## Choices\n{_format_choices(item['choices'])}\n\n"
            f"## Your earlier answer\n{output}"
        )
    if env == "searchqa":
        return (
            "A verification pass found your earlier answer is NOT directly supported by the "
            "Context. Replace it with the SHORTEST answer that is directly supported by the "
            "evidence span below; do not add unsupported detail. Output your corrected answer as "
            "<answer>...</answer>.\n\n"
            f"## Verification (ERROR_TYPE={report.get('error_type')})\n{ev}\n\n"
            f"## Context\n{_sq_context(item)}\n\n## Question\n{item['question']}\n\n"
            f"## Your earlier answer\n{output}"
        )
    raise ValueError(env)


def solve_item(env: str, item: dict, system: str, max_repairs: int) -> dict:
    """attempt -> verify -> conservative repair; grade attempt AND final (to count flips)."""
    from skillopt.model import chat_target
    from qd.avp import run_avp_loop

    user = build_user_for(env, item)
    holder: dict = {}

    def attempt():
        out, _ = chat_target(system=system, user=user, max_completion_tokens=16384,
                             retries=5, stage="rollout")
        holder["a0"] = out
        return out

    def verify(output):
        ans = answer_of(env, output, item)
        rep, _ = chat_target(system=system,
                             user=build_verify_prompt(env, item, output, ans),
                             max_completion_tokens=4096, retries=3, stage="rollout")
        return rep

    def repair(output, report):
        out2, _ = chat_target(system=system,
                              user=build_repair_prompt(env, item, output, report),
                              max_completion_tokens=16384, retries=5, stage="rollout")
        return out2

    final, trace = run_avp_loop(attempt=attempt, verify=verify, repair=repair, max_repairs=max_repairs)
    hard_attempt = grade(env, holder.get("a0", ""), item)
    hard_final = grade(env, final, item)
    n_repaired = sum(1 for t in trace if t.get("repaired"))
    return {
        "id": str(item.get("id")),
        "hard": hard_final,
        "hard_attempt": hard_attempt,
        "flip": ("fix" if hard_final > hard_attempt else "break" if hard_final < hard_attempt else "none"),
        "n_repaired": n_repaired,
        "verdicts": [t.get("verdict") for t in trace if t["stage"] == "verify"],
        "error_types": [t.get("error_type") for t in trace if t["stage"] == "verify"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default="livemathematicianbench",
                    choices=["livemathematicianbench", "searchqa"])
    ap.add_argument("--skill", default="", help="Path (relative to SkillOpt/) to best_skill.md; '' = no skill.")
    ap.add_argument("--max-repairs", type=int, default=1)
    ap.add_argument("--key", choices=["env", "dion", "yh", "yw", "tt", "xx", "xnyu", "x2"], default="env")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--split", default="valid_unseen", help="valid_unseen=test, valid_seen=D_sel.")
    ap.add_argument("--split-dir", default="", help="Default: data/<env>_split.")
    ap.add_argument("--env-num", type=int, default=0, help="0=all test items; >0 caps (canary/smoke).")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--tag", default="avp_eval")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    if not SKILLOPT_DIR.is_dir():
        sys.exit(f"[avp] SkillOpt/ not found at {SKILLOPT_DIR}")
    split_dir = args.split_dir or f"data/{args.env}_split"
    env_vars = load_env_file(ENV_FILE)
    key_val = env_vars.get("AZURE_OPENAI_API_KEY", "")
    if args.key != "env":
        kname = f"DEEPSEEK_KEY_{args.key.upper()}"
        if kname not in env_vars:
            sys.exit(f"[avp] {kname} not in .env")
        key_val = env_vars[kname]
    endpoint = env_vars.get("AZURE_OPENAI_ENDPOINT", "https://api.deepseek.com")

    # Run with cwd=SkillOpt (relative data/skill/outputs paths) + repo root on path (qd).
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(SKILLOPT_DIR))
    os.chdir(SKILLOPT_DIR)
    os.environ["TARGET_TEMPERATURE"] = "0"
    os.environ["TARGET_SEED"] = "42"
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint
    os.environ["AZURE_OPENAI_API_KEY"] = key_val

    skill = ""
    if args.skill:
        sp = Path(args.skill)
        if not sp.is_file():
            sys.exit(f"[avp] skill not found: {sp} (cwd={os.getcwd()})")
        skill = sp.read_text(encoding="utf-8")

    print("=" * 72)
    print(f"[avp] env={args.env} tag={args.tag} key={args.key} seed={args.seed} "
          f"max_repairs={args.max_repairs} skill={'<none>' if not skill else args.skill} "
          f"({len(skill)} chars)")
    items = build_eval_items(args.env, split_dir, args.split, args.env_num, args.seed)
    print(f"[avp] test items={len(items)} (split={args.split}, env_num={args.env_num}, split_dir={split_dir})")
    print("=" * 72)
    if args.dry:
        print("[avp] --dry: items built, not calling the model.")
        return 0

    from skillopt.model import set_target_backend, set_target_deployment, set_reasoning_effort
    from skillopt.model.azure_openai import configure_azure_openai
    configure_azure_openai(auth_mode="openai_compatible", endpoint=endpoint, api_key=key_val)
    set_target_backend("openai_chat")
    set_target_deployment(env_vars.get("TARGET_MODEL", "deepseek-chat"))
    set_reasoning_effort(None)
    system = build_system_for(args.env, skill)

    out_dir = SKILLOPT_DIR / "outputs" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(solve_item, args.env, it, system, args.max_repairs): it for it in items}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001
                rid = str(futs[fut].get("id"))
                print(f"[avp] item {rid} errored: {e}")
                results.append({"id": rid, "hard": 0, "hard_attempt": 0, "flip": "none",
                                "n_repaired": 0, "verdicts": [], "error_types": [], "error": str(e)})
            if i % 40 == 0:
                print(f"[avp] {i}/{len(items)} done ({time.time()-t0:.0f}s)")

    n = len(results)
    test_hard = sum(r["hard"] for r in results) / n if n else 0.0
    attempt_hard = sum(r["hard_attempt"] for r in results) / n if n else 0.0
    n_fix = sum(1 for r in results if r["flip"] == "fix")
    n_break = sum(1 for r in results if r["flip"] == "break")
    n_repaired = sum(r["n_repaired"] for r in results)
    summary = {
        "tag": args.tag, "env": args.env, "seed": args.seed, "max_repairs": args.max_repairs,
        "skill": args.skill or "<none>", "n": n,
        "attempt_hard": round(attempt_hard, 4),   # = skill-single equivalent on these items
        "test_hard": round(test_hard, 4),         # after AVP
        "delta": round(test_hard - attempt_hard, 4),
        "n_repaired_items": n_repaired, "n_fix": n_fix, "n_break": n_break,
        "wall_s": round(time.time() - t0, 1),
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(out_dir / "results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("=" * 72)
    print(f"[avp] {args.tag}: attempt_hard={attempt_hard:.4f} -> test_hard={test_hard:.4f} "
          f"(delta={summary['delta']:+.4f}) | repaired={n_repaired} fix={n_fix} break={n_break} n={n}")
    print(f"[avp] summary: outputs/{args.tag}/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
