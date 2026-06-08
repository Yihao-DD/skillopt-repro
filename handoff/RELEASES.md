# Vendored SkillOpt fork — release record

The `qd/` package runs over a **frozen** SkillOpt fork. This file records exactly
which fork snapshot is vendored, for provenance (ADR-0004).

## Current
- **Fork commit:** `05a023c` — "fix(model): OpenAI-compatible backend for DeepSeek (max_tokens, drop reasoning_effort)"
- **Upstream base:** `microsoft/SkillOpt` @ `ee9931e` ("docs: add SkillOpt integration news")
- **Delta vs upstream:** one commit — `skillopt/model/azure_openai.py` openai-compatible adapter
  (`_is_openai_compat_client` → use `max_tokens` not `max_completion_tokens`, drop `reasoning_effort`),
  enabling the DeepSeek (OpenAI-compatible) backend.
- **Recorded:** 2026-06-08.

> Reproduce the fork from scratch: `microsoft/SkillOpt@ee9931e` + the single
> `azure_openai.py` adapter commit. The vendored files under `vendor/SkillOpt/`
> (S13) are this exact snapshot, **minus** the benchmark `data/` (committed
> separately per ADR-0005, `data/benchmarks/`).
