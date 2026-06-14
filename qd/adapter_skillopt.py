"""Real SkillOpt + DeepSeek adapter for the QD loop (REORG S15).

Wires :class:`qd.loop.CandidateProducer` to the FROZEN SkillOpt fork's actual
SpreadsheetBench rollout / reflect / apply against DeepSeek. ONE rollout per
skill is cached (by skill hash) and serves all three of:
  - ``score(skill)``  → ``compute_score`` (hard accuracy on the selection set),
  - ``probe(skill)``  → the generated code per item → behavior descriptor,
  - ``propose(skill)``→ ``reflect`` on the rollout results → an edit patch.

The model client is configured from ``.env`` (openai-compatible / DeepSeek).
This is the EXPENSIVE path — used only by run_experiment / the preflight smoke,
never in unit tests. SkillOpt is imported lazily so ``import qd.loop`` stays
model-free.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from qd.ledger import LedgerEntry, RejectionLedger, skill_fingerprint
from qd.loop import CandidateProducer

_AXIS_LEVELS = ("很低", "较低", "较高", "很高")
_NBINS = 4  # == qd.descriptor cell grid (cell = complexity_bin * 4 + op_density_bin)


def _verbalize_cell(cell: int) -> str:
    """AIM: turn a target cell into ADR-0006 axis language the optimizer can act on."""
    row, col = (cell // _NBINS) % _NBINS, cell % _NBINS
    return (f"瞄准行为格 {cell}：解法复杂度{_AXIS_LEVELS[row]}、"
            f"spreadsheet 操作密度{_AXIS_LEVELS[col]}的实现风格。")


def _split_patches(raw_patches: list | None) -> tuple[list[dict], list[dict]]:
    """Split reflect's raw patches into (failure_patches, success_patches), faithful
    to ``SkillOpt/skillopt/engine/trainer.py::_normalise_patches`` (the stage between
    ② reflect and ③ aggregate): extract the inner ``patch`` sub-dict and route by
    ``source_type`` ("success" -> success list; missing/anything else -> failure,
    matching the trainer's ``p.get("source_type", "failure")`` default).

    run_minibatch_reflect tags each raw patch with ``source_type`` (reflect.py docstring
    "Patch dicts (with source_type 'failure' or 'success')"); empty-edit patches are
    dropped so they don't dilute the merge, exactly as the trainer does.
    """
    failure: list[dict] = []
    success: list[dict] = []
    for p in raw_patches or []:
        if not isinstance(p, dict):
            continue
        inner = p.get("patch", p)
        if not isinstance(inner, dict) or not inner.get("edits"):
            continue
        if p.get("source_type", "failure") == "success":
            success.append(inner)
        else:
            failure.append(inner)
    return failure, success


def _flips(parent_results: list, cand_results: list, cap: int = 8) -> tuple:
    """Per-task correctness flips (parent vs candidate), from already-paid rollouts."""
    def _hardmap(results: list) -> dict:
        return {str(r.get("id")): int(float(r.get("hard", 0)) > 0.5) for r in results}

    pa, ca = _hardmap(parent_results), _hardmap(cand_results)
    flips = [(tid, pa[tid], ca[tid]) for tid in sorted(pa.keys() & ca.keys()) if pa[tid] != ca[tid]]
    flips.sort(key=lambda f: (f[2] - f[1], f[0]))  # regressions (对→错) first
    return tuple(flips[:cap])


def configure_deepseek(*, optimizer_model: str | None = None, target_model: str | None = None) -> dict:
    """Configure SkillOpt's model clients for DeepSeek (openai-compatible) from .env.

    Reads ``AZURE_OPENAI_ENDPOINT`` / ``AZURE_OPENAI_API_KEY`` (+ optional
    ``TARGET_MODEL`` / ``OPTIMIZER_MODEL``). Returns the resolved {endpoint, models}
    WITHOUT the key (safe to log).
    """
    from skillopt.model.azure_openai import (
        configure_azure_openai,
        set_optimizer_deployment,
        set_target_deployment,
    )

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://api.deepseek.com")
    key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("AZURE_OPENAI_API_KEY not set (load .env first)")
    configure_azure_openai(auth_mode="openai_compatible", endpoint=endpoint, api_key=key)
    tm = target_model or os.environ.get("TARGET_MODEL", "deepseek-chat")
    om = optimizer_model or os.environ.get("OPTIMIZER_MODEL", "deepseek-chat")
    set_target_deployment(tm)
    set_optimizer_deployment(om)
    return {"endpoint": endpoint, "target_model": tm, "optimizer_model": om}


def _skill_hash(s: str) -> str:
    return skill_fingerprint(s)  # single hash source (qd.ledger) — same algo as before


@dataclass
class SkillOptProducer:
    """Faithful to SkillOpt Eq 2/3: candidates are GENERATED on D_tr (``gen_items``,
    propose) and GATED on D_sel (``sel_items``, score/probe). Caches one rollout
    per (skill, split); when ``gen_items is sel_items`` (merged mode) the two
    collapse to a single shared rollout (back-compat with the old single-set runs)."""

    adapter: object              # skillopt SpreadsheetBenchAdapter
    gen_items: list              # D_tr — generation/reflection set (propose)
    sel_items: list              # D_sel — validation-gate set (score/probe)
    out_root: str
    slow_n: int = 20             # 原文 §3.6 slow-update sample count (from D_tr)
    rcv: bool = False            # False=原文模式(plain buffer render) / True=RCV(flips+AIM, ADR-0007)
    _cache: dict = field(default_factory=dict)   # (skill_hash, tag) -> rollout results

    def _tag(self, items: list) -> str:
        # Same object as sel_items -> "sel" (also the merged-mode single tag);
        # the generation set gets its own "gen" tag only when truly separate.
        return "sel" if items is self.sel_items else "gen"

    def _rollout(self, skill: str, items: list) -> list[dict]:
        tag = self._tag(items)
        key = (_skill_hash(skill), tag)
        if key not in self._cache:
            self._cache[key] = self.adapter.rollout(
                items, skill, os.path.join(self.out_root, tag, _skill_hash(skill)))
        return self._cache[key]

    def score(self, skill: str) -> float:
        from skillopt.utils import compute_score

        hard, _soft = compute_score(self._rollout(skill, self.sel_items))
        return float(hard)

    def probe(self, skill: str) -> list[dict]:
        # Behavior trajectories from the SEL rollout (cell ~ gate behavior): the
        # code DeepSeek generated per item, saved to predictions/<id>/code.py.
        results = self._rollout(skill, self.sel_items)
        pred_dir = os.path.join(self.out_root, self._tag(self.sel_items), _skill_hash(skill), "predictions")
        trajs = []
        for r in results:
            code_path = os.path.join(pred_dir, str(r.get("id", "")), "code.py")
            code = ""
            if os.path.exists(code_path):
                with open(code_path, encoding="utf-8") as f:
                    code = f.read()
            trajs.append({"code": code, "n_turns": r.get("n_turns", 1)})
        return trajs

    def _enrich(self, e: LedgerEntry) -> LedgerEntry:
        """Lazily attach per-task flips from the rollout cache. Parent was rolled
        out at generation (gen tag unless merged), candidate at the gate (sel).
        Under true split the two sets are disjoint, so flips degrade to empty."""
        if e.task_flips:
            return e
        ptag = "sel" if self.gen_items is self.sel_items else "gen"
        pk, ck = (e.parent_hash, ptag), (e.cand_hash, "sel")
        if pk not in self._cache or ck not in self._cache:
            return e
        return replace(e, task_flips=_flips(self._cache[pk], self._cache[ck]))

    def _rcv_context(self, *, target_cell: int | None, ledger: "RejectionLedger | None") -> str:
        """AVOID (ledger render + flips) + AIM (verbalized target cell), or ""."""
        parts = []
        if ledger is not None and len(ledger):
            enriched = RejectionLedger(entries=[self._enrich(e) for e in ledger.entries])
            parts.append(enriched.render())
        guidance = []
        if target_cell is not None:
            guidance.append(_verbalize_cell(target_cell))
        if parts:
            guidance.append("不要重复上述被拒方向的同类编辑；优先提出与失败方向语义不同的修改。")
        if guidance:
            parts.append("== 指引 ==\n" + "\n".join(guidance))
        return "\n".join(parts)

    def _buffer_context(self, ledger: "RejectionLedger | None") -> str:
        """原文模式 (缺口 3): 只 render 被拒 buffer（方向 + 分数 drop），不调 AIM/flips。"""
        if ledger is not None and len(ledger):
            return ledger.render()
        return ""

    def propose(self, skill: str, *, step: int, target_cell: int | None = None,
                ledger: "RejectionLedger | None" = None, meta: str = "") -> dict:
        results = self._rollout(skill, self.gen_items)   # generate candidates on D_tr
        kwargs = {}
        # 原文模式(默认)只 render buffer；RCV(ADR-0007)才叠加 flips+AIM。
        ctx = (self._rcv_context(target_cell=target_cell, ledger=ledger)
               if self.rcv else self._buffer_context(ledger))
        if ctx:
            # Upstream-blessed injection channel: reflect renders this under
            # "## Previous Steps in This Epoch" — exactly the AVOID semantics.
            kwargs["step_buffer_context"] = ctx
        meta_ctx = ""
        if meta:   # 缺口 2: optimizer meta skill -> fork reflect's meta_skill_context (zero fork change)
            from skillopt.optimizer.meta_skill import format_meta_skill_context
            meta_ctx = format_meta_skill_context(meta)
            kwargs["meta_skill_context"] = meta_ctx
        patches = self.adapter.reflect(
            results, skill, os.path.join(self.out_root, self._tag(self.gen_items), _skill_hash(skill)), **kwargs)
        # RED-LINE faithfulness: route reflect's patches through the SAME aggregate/merge
        # stage as the fork (trainer.py ③: reflect→_normalise_patches→merge_patches), NOT
        # flat-concat. K=1 thus reproduces apply(rank(MERGE(patches))), and meta flows to
        # merge too (trainer passes meta_skill_context=active_meta_skill to merge as well).
        failure_patches, success_patches = _split_patches(patches)
        if not failure_patches and not success_patches:
            # Mirrors the trainer's skip_no_patches guard — nothing to aggregate.
            return {"edits": [], "reasoning": f"deepseek-reflect@step{step}(no patches)"}
        from skillopt.gradient.aggregate import merge_patches
        merged = merge_patches(
            skill, failure_patches, success_patches,
            update_mode="patch", meta_skill_context=meta_ctx,
        )
        return {"edits": (merged or {}).get("edits", []),
                "reasoning": (merged or {}).get("reasoning", f"deepseek-reflect@step{step}")}

    def apply(self, skill: str, patch: dict) -> str:
        from skillopt.optimizer.skill import apply_patch_with_report

        new_skill, _reports = apply_patch_with_report(skill, patch)
        return new_skill

    def _slow_rollout(self, skill: str) -> list[dict]:
        """Roll out `skill` on the slow-update sample set, cached (shared by slow_update
        & meta_update so the adjacent-epoch comparison is paid for only once)."""
        key = (_skill_hash(skill), "slow")
        if key not in self._cache:
            self._cache[key] = self.adapter.rollout(
                self.gen_items[: self.slow_n], skill, os.path.join(self.out_root, "slow", _skill_hash(skill)))
        return self._cache[key]

    def slow_update(self, prev_skill: str, curr_skill: str) -> str:
        """原文 §3.6: roll out prev & curr skill on slow-update samples (from D_tr),
        call the fork's run_slow_update → longitudinal guidance string."""
        from skillopt.optimizer.slow_update import run_slow_update

        samples = self.gen_items[: self.slow_n]
        if not samples:
            return ""
        rp, rc = self._slow_rollout(prev_skill), self._slow_rollout(curr_skill)
        res = run_slow_update(curr_skill, rp, rc, samples, prev_skill=prev_skill)
        return (res or {}).get("slow_update_content", "")

    def meta_update(self, prev_skill: str, curr_skill: str, prev_meta: str) -> str:
        """原文 §3.6: optimizer-side memory from the adjacent-epoch comparison (same slow
        samples as slow_update — rollouts reused). Accumulates on prev_meta; does NOT
        modify the skill. Returns prev_meta unchanged when the optimizer produces nothing."""
        from skillopt.optimizer.meta_skill import run_meta_skill
        from skillopt.optimizer.slow_update import build_comparison_pairs

        samples = self.gen_items[: self.slow_n]
        if not samples:
            return prev_meta
        rp, rc = self._slow_rollout(prev_skill), self._slow_rollout(curr_skill)
        pairs = build_comparison_pairs(rp, rc, samples)
        res = run_meta_skill(prev_skill, curr_skill, pairs, prev_meta_skill_content=prev_meta)
        return (res or {}).get("meta_skill_content", prev_meta) or prev_meta

    def apply_slow(self, skill: str, guidance: str) -> str:
        """原文 §3.6: inject the guidance into the skill's protected slow-update field."""
        if not guidance:
            return skill
        from skillopt.optimizer.slow_update import replace_slow_update_field

        return replace_slow_update_field(skill, guidance)


def make_producer(
    *,
    items: list | None = None,
    gen_items: list | None = None,
    sel_items: list | None = None,
    data_root: str,
    out_root: str,
    mode: str = "single",
    workers: int = 8,
    max_completion_tokens: int = 4096,
    edit_budget: int = 4,
    rcv: bool = False,   # False=原文模式(faithful buffer render) / True=RCV(flips+AIM, ADR-0007)
) -> CandidateProducer:
    """Build a DeepSeek-backed CandidateProducer over SpreadsheetBench items.

    Call :func:`configure_deepseek` first. Two modes:
      - faithful split (原文 Eq 2/3): pass ``gen_items`` (D_tr, generate) and
        ``sel_items`` (D_sel, gate);
      - merged/legacy: pass ``items`` (gen == sel == one set; old single-set runs).
    ``data_root`` is the dir holding the task xlsx.
    """
    if items is not None:
        gen_items = sel_items = items   # legacy single-set == merged mode
    if gen_items is None or sel_items is None:
        raise ValueError("make_producer needs either items=, or both gen_items= and sel_items=")
    from skillopt.envs.spreadsheetbench.adapter import SpreadsheetBenchAdapter

    adapter = SpreadsheetBenchAdapter(
        data_root=data_root,
        mode=mode,
        workers=workers,
        max_completion_tokens=max_completion_tokens,
        edit_budget=edit_budget,
    )
    p = SkillOptProducer(adapter=adapter, gen_items=gen_items, sel_items=sel_items, out_root=out_root, rcv=rcv)
    return CandidateProducer(propose=p.propose, apply=p.apply, score=p.score, probe=p.probe,
                             slow_update=p.slow_update, apply_slow=p.apply_slow, meta_update=p.meta_update)
