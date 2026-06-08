# Vendored SkillOpt fork — release record

The `qd/` package runs over a **frozen** SkillOpt fork. This file records exactly
which fork snapshot is vendored, for provenance (ADR-0004).

## Current
- **Fork commit:** `0948d2d` — "feat(model): role-aware decoding for openai-compat" (on top of `05a023c`)
- **Upstream base:** `microsoft/SkillOpt` @ `ee9931e` ("docs: add SkillOpt integration news")
- **Delta vs upstream:** two commits to `skillopt/model/azure_openai.py` —
  (1) `05a023c` openai-compatible adapter (`_is_openai_compat_client` → `max_tokens`, drop `reasoning_effort`);
  (2) `0948d2d` role-aware decoding from env (`TARGET_TEMPERATURE`/`TARGET_SEED` = frozen target;
  `OPTIMIZER_TEMPERATURE` = diverse variation), enabling the QD frozen-target red line on DeepSeek.
- **Recorded:** 2026-06-08.

> Reproduce the fork from scratch: `microsoft/SkillOpt@ee9931e` + the single
> `azure_openai.py` adapter commit. The vendored files under `vendor/SkillOpt/`
> (S13) are this exact snapshot, **minus** the benchmark `data/` (committed
> separately per ADR-0005, `data/benchmarks/`).
