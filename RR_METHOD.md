# RR-SkillOpt / RR-Boost — Reliability-Routed Skill Optimization

A faithful extension of **SkillOpt** (arXiv:2605.23904) that treats **feedback reliability as a
first-class control variable**. Before touching the test set, RR estimates each feedback channel's
reliability on **labeled development data** and automatically routes OPEN / CLOSE / ABSTAIN, writing
the decision to `router_decision.json` (the anti-oracle evidence). Only channels marked open are
allowed to touch test.

> This branch is the **clean, self-contained method** (router + verifiers + eval harness + result),
> extracted from the research branch. Model used: `deepseek-chat` (the only deviation from the paper,
> which uses gpt-5.5). All numbers are paper-style single-seed, with multi-seed robustness where noted.

## The two channels

- **R_sel** (training channel) — is the selection set `D_sel` reliable enough to let validation
  feedback pick candidates? Governor in `qd/reliability.py` (split-half agreement, bootstrap
  stability, candidate margin, and an `n_sel >= 30` size gate).
- **R_ver** (inference channel) — does verify+repair NET-help on labeled dev data, or net-hurt?
  Decided by `qd/router.py::rver_decision` on fix/break/precision/trigger measured on dev. **Never
  calibrated on test.**

## RR-Boost (power-adjusted R_ver)

`D_sel`-only calibration is underpowered on small validation splits. RR-Boost calibrates **HARD_CHECK**
verifiers (execution-grounded / deterministic — math recompute, spreadsheet hard-invariant; never
fuzzy entailment or code-review) on the larger **`D_train ∪ D_sel`**, and decides with a **one-sided
sign test** in addition to a raw net floor. A verifier that only acts on already-failed items
(spreadsheet hard-invariant) has structurally guaranteed precision 1.0, so its trigger cap is waived
(`structural_precision`, recorded in `router_decision.json`).

## The three verifiers (`repro/official/rver_probe.py`)

| benchmark | verifier | kind |
|---|---|---|
| LiveMathematicianBench | **math-check v3** — 3 *different* checks (independent recompute / substitute-back / eliminate-distractors) at temp=0; repair only if ≥2 of 3 independently FAIL; **re-derive** repair | diverse-prompt consensus |
| SearchQA | **evidence-span canonicalizer** — shorten the answer to a verbatim supported span; deterministic; NOT semantic entailment | EM-aware |
| SpreadsheetBench | **hard-invariant check** — repair only on golden-free execution failure (crash / timeout / missing output); NEVER on `eval-mismatch` | execution-grounded |

The LiveMath v3 verifier is the key result: diverse-framing consensus drops both the trigger rate and
the break rate (vs a single-pass verifier), so the gate opens robustly across seeds. A choice-consensus
variant (`qd/avp.py::consensus_correction`, "v2") was tried and **failed** (correlated temp=0 samples +
deterministic apply made it worse) — it is kept, tested, and documented as a negative result.

## Final result — all three benchmarks beat SkillOpt K1

| benchmark | K1 | RR-Boost | gain | robustness |
|---|---|---|---|---|
| **SpreadsheetBench** | 0.507 | RG-trained 0.6107 + execution repair | **+10.4 + 2.86** | RG multi-seed; repair precision 1.0 (0 break on test) |
| **SearchQA** | 0.804 | RG-trained 0.827 (repair correctly abstains) | **+1.9** | single-seed |
| **LiveMath** | 0.468 | K1 + v3 diverse-consensus repair ≈ 0.52 | **+7.3 within-run** | 3-seed robust (gate opens 3/3, net +9 each) |

Full analysis (including the failed v1/v2 attempts and the multi-seed deflation that motivated v3) is
in [`RESULT_RR_SKILLOPT.md`](RESULT_RR_SKILLOPT.md).

## Code map

- `qd/router.py` — `rver_decision` (net + sign-test bars, `structural_precision`), `sign_test_one_sided`,
  `should_canonicalize_span`, `ssb_hard_invariant_verdict`, `build_router_decision`. Pure, zero-API.
- `qd/reliability.py` — the R_sel governor. Pure, zero-API.
- `qd/avp.py` — Attempt-Verify-Patch control logic (`parse_verify_report`, `should_repair`,
  `run_avp_loop`) reused by the verifiers; plus `consensus_correction` (v2, negative result).
- `repro/official/rver_probe.py` — the harness: `--mode probe` (val-only), `probe_cal`
  (D_train∪D_sel, power-adjusted), `test` (routed); the three verifiers + v3 diverse-consensus.
- `repro/official/avp_eval.py` — shared per-env primitives (item building, grading, prompts).
- `qd/tests/` — zero-API unit tests for the router / AVP / reliability logic.
- `tools/_rr_launch.sh`, `tools/_rr_multiseed_lm.sh` — detached-run launchers (key referenced by
  name only; no secrets).

## How to run

Requires the SkillOpt harness (`SkillOpt/`, not included here), the benchmark splits, and a
`deepseek-chat` API key in a local `.env` (also not included). Then, per benchmark:

```bash
# 1. calibrate the inference channel on labeled dev data (writes router_decision.json) — never test
python repro/official/rver_probe.py --env livemathematicianbench --mode probe_cal \
    --lm-consensus 3 --skill <incumbent_best_skill.md> --key <name> --seed 1

# 2. routed test — repair runs only if the router opened it
python repro/official/rver_probe.py --env livemathematicianbench --mode test \
    --lm-consensus 3 --skill <incumbent_best_skill.md> --key <name> --seed 1 \
    --router-json outputs/rr_router/livemathematicianbench_dcal.json --bar sign
```

## Honest caveats

- SearchQA is single-seed. LiveMath repair precision on test is ~0.7 (net-positive, not break-free,
  unlike the spreadsheet execution repair which is structurally break-free).
- The power-adjusted gate is post-hoc-developed (after observing the D_sel-only gate was underpowered)
  but uses **only non-test calibration data** and is now robust across seeds. A held-out 4th-benchmark
  validation would be the cleanest final test.
- deepseek-chat at temp=0 is not bit-deterministic; trust within-run deltas and multi-seed, not single
  absolute numbers.

## Not included (by design)

The SkillOpt fork, benchmark data, trained incumbent skills, API keys, and any infrastructure
credentials are intentionally excluded — this branch is the **method code + results** only.
